"""
Tests for Vehicle Create API (POST /api/v1/vehicles/).

Verifies:
- Auto-generated sequential vehicle code (XE%04d, e.g. XE0031).
- Client-supplied custom vehicle code complying with ck_vehicle_code_format.
- Duplicate active plate conflict -> 409 (MSG-4.3.1-M05).
- Re-registration of a soft-deleted vehicle's plate is permitted (partial unique index uq_vehicle_license_plate_active).
- Invalid license plate format validation -> 400 (PROP-GEN-P01).
- Non-existent customer ID -> 400 (PROP-GEN-P01).
- Soft-deleted customer ID -> 400 (PROP-GEN-P01).
- Invalid vehicle type (non-existent or not CAR/EV) -> 400 (PROP-GEN-P01).
- Read-only fields (ticket_type_id, ticket_expires_at) ignored per OQ-52.
- RBAC permissions: Anonymous -> 401, Customer -> 403, Employee -> 201, Manager -> 201.
- CSRF middleware enforcement: missing token -> 403 (PROP-4.1-P06).
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.customers.models import Customer
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db

ENDPOINT_URL = "/api/v1/vehicles/"


def test_vehicle_create_auto_code_generation(manager_client, car_type, active_customer):
    """Tạo xe mới không truyền 'code' -> hệ thống tự sinh mã tuần tự XE%04d (ví dụ: XE0031)."""
    payload = {
        "license_plate": "51K-999.01",
        "model_name": "VF8",
        "brand": "VinFast",
        "color": "Đỏ",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["code"] == "XE0031"
    assert data["license_plate"] == "51K-999.01"
    assert data["license_plate_norm"] == "51K99901"
    assert data["row_version"] == 1
    assert data["customer"]["id"] == active_customer.id
    assert data["vehicle_type"]["id"] == car_type.id


def test_vehicle_create_client_supplied_code(manager_client, car_type, active_customer):
    """Tạo xe mới với mã tự chọn hợp lệ (XE-CUSTOM-01) -> lưu đúng mã được cấp."""
    payload = {
        "code": "XE-CUST-01",
        "license_plate": "51K-999.02",
        "model_name": "VF9",
        "brand": "VinFast",
        "color": "Xanh",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["code"] == "XE-CUST-01"


def test_vehicle_create_duplicate_active_plate_conflict(
    manager_client, car_type, active_customer
):
    """Đăng ký biển số đã tồn tại và đang hoạt động (ví dụ: 43K-860.50) -> 409 Conflict (MSG-4.3.1-M05)."""
    payload = {
        "license_plate": "43K-860.50",  # XE0001
        "model_name": "Camry",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json().get("code") == "MSG-4.3.1-M05"


def test_vehicle_create_re_register_soft_deleted_plate_allowed(
    manager_client, auth_manager, car_type, active_customer
):
    """
    Biển số của xe đã bị xóa mềm được phép đăng ký lại
    nhờ chỉ mục một phần uq_vehicle_license_plate_active (WHERE deleted_at IS NULL).
    """
    v_to_delete = Vehicle.objects.filter(code="XE0030", deleted_at__isnull=True).first()
    assert v_to_delete is not None
    deleted_plate = v_to_delete.license_plate
    v_to_delete.soft_delete(user=auth_manager)

    payload = {
        "license_plate": deleted_plate,
        "model_name": "Wuling Mini EV Reborn",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.json()["license_plate"] == deleted_plate


def test_vehicle_create_invalid_plate_format(manager_client, car_type, active_customer):
    """Biển số xe không chứa ký tự chữ/số nào sau khi chuẩn hóa -> 400 Bad Request (PROP-4.5.1-P16)."""
    payload = {
        "license_plate": "---",  # No alphanumeric characters -> empty normalized plate
        "model_name": "Test Car",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json().get("code") == "PROP-4.5.1-P16"


@pytest.mark.parametrize(
    "invalid_plate",
    [
        "A",  # Too short (1 char)
        "000000000000",  # Too long, all digits (12 chars)
        "59P1-678.90",  # Motorbike format (2 digits + letter + digit)
        "13A-123.45",  # Reserved/never issued province code 13
        "TM-12.34",  # Military syntax
        "51I-123.45",  # Invalid civilian series letter 'I'
    ],
)
def test_vehicle_create_weak_and_invalid_plates_rejected(
    manager_client, car_type, active_customer, invalid_plate
):
    """
    K3: Thẩm định nghiêm ngặt biển số xe ô tô dân sự Việt Nam (Thông tư 79/2024/TT-BCA).
    Từ chối các biển số yếu, biển xe máy, biển quân đội, mã tỉnh chưa cấp -> 400 Bad Request (PROP-4.5.1-P16).
    """
    payload = {
        "license_plate": invalid_plate,
        "model_name": "Test Car",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json().get("code") == "PROP-4.5.1-P16"


def test_vehicle_create_unknown_customer(manager_client, car_type):
    """customer_id không tồn tại trong hệ thống -> 400 Bad Request (PROP-4.4.4-P02)."""
    payload = {
        "license_plate": "51K-999.05",
        "model_name": "Test Car",
        "vehicle_type_id": car_type.id,
        "customer_id": 999999,
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json().get("code") == "PROP-4.4.4-P02"


def test_vehicle_create_deleted_customer(manager_client, car_type, auth_manager):
    """customer_id thuộc khách hàng đã bị xóa mềm -> 400 Bad Request (PROP-4.4.4-P02)."""
    cust = Customer.objects.create(
        code="KH-DEL-01",
        full_name="Khách Hàng Xóa",
        phone="0911002233",
        identity_card_number="049090123999",
    )
    cust.soft_delete(user=auth_manager)

    payload = {
        "license_plate": "51K-999.06",
        "model_name": "Test Car",
        "vehicle_type_id": car_type.id,
        "customer_id": cust.id,
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json().get("code") == "PROP-4.4.4-P02"


def test_vehicle_create_invalid_vehicle_type(manager_client, active_customer):
    """vehicle_type_id không tồn tại hoặc không phải CAR/EV -> 400 Bad Request."""
    payload = {
        "license_plate": "51K-999.07",
        "model_name": "Test Car",
        "vehicle_type_id": 999999,
        "customer_id": active_customer.id,
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json().get("code") == "PROP-GEN-P01"


def test_vehicle_create_read_only_fields_ignored(
    manager_client, car_type, active_customer
):
    """Các trường vé (ticket_type_id, ticket_expires_at) là read-only (OQ-52) -> không được ghi đè."""
    payload = {
        "license_plate": "51K-999.08",
        "model_name": "Test Car",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
        "ticket_type_id": 1,
        "ticket_expires_at": "2030-01-01T00:00:00Z",
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["ticket"] is None


def test_vehicle_create_permissions(
    anonymous_client, customer_client, employee_client, car_type, active_customer
):
    """
    Quyền tạo xe:
    - Anonymous -> 401
    - Customer -> 403
    - Employee -> 201 (Task V0: Employee và Manager đều có quyền ghi)
    """
    payload = {
        "license_plate": "51K-999.09",
        "model_name": "Test Car",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    assert (
        anonymous_client.post(ENDPOINT_URL, payload, format="json").status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        customer_client.post(ENDPOINT_URL, payload, format="json").status_code
        == status.HTTP_403_FORBIDDEN
    )
    res_emp = employee_client.post(ENDPOINT_URL, payload, format="json")
    assert res_emp.status_code == status.HTTP_201_CREATED
    assert res_emp.json()["license_plate"] == "51K-999.09"


def test_vehicle_create_csrf_enforcement(auth_manager, car_type, active_customer):
    """
    Khi kích hoạt enforce_csrf_checks=True trên Session client:
    - Thiếu token CSRF -> 403 Forbidden (PROP-4.1-P06).
    - Có CSRF token hợp lệ -> 201 Created.
    """
    client = APIClient(enforce_csrf_checks=True)
    client.force_login(auth_manager)

    payload = {
        "license_plate": "51K-999.10",
        "model_name": "Test Car",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }

    # 1. Gửi request POST không kèm header CSRF -> 403 Forbidden
    res_no_csrf = client.post(ENDPOINT_URL, payload, format="json")
    assert res_no_csrf.status_code == status.HTTP_403_FORBIDDEN
    assert res_no_csrf.json().get("code") in ("MSG-4.2-M01", "PROP-4.1-P06")

    # 2. Khởi tạo cookie CSRF qua auth-csrf và gửi kèm token hợp lệ -> 201 Created
    csrf_res = client.get(reverse("auth-csrf"))
    csrf_token = csrf_res.cookies["csrftoken"].value

    res_with_csrf = client.post(
        ENDPOINT_URL,
        payload,
        format="json",
        HTTP_X_CSRFTOKEN=csrf_token,
    )
    assert res_with_csrf.status_code == status.HTTP_201_CREATED
    assert res_with_csrf.json()["license_plate"] == "51K-999.10"
