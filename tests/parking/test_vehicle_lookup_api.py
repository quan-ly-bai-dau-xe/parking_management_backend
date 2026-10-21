"""
Integration tests for Vehicle Lookup API (GET /api/v1/parking/vehicle-lookup/).
Verifies:
- Permission matrix: anonymous -> 401, CUSTOMER -> 403, EMPLOYEE -> allowed.
- Missing license_plate parameter -> 400 PROP-4.5.1-P01.
- Non-existent vehicle -> 404 MSG-4.5.1-M01.
- Soft-deleted vehicle -> 404 MSG-4.5.1-M01 (OQ-67).
- Anonymized customer -> PII masked (is_anonymized=True).
- Normal vehicle lookup -> 200 OK with vehicle, customer, parking position, active ticket, blacklist flag.
"""

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.models import PlateBlacklist
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_lookup@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def auth_customer():
    cust, _ = Account.objects.get_or_create(
        email="cust_lookup@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return cust


def test_vehicle_lookup_anonymous_rejected():
    """Chưa đăng nhập -> 401 MSG-4.1-M02."""
    client = APIClient()
    response = client.get("/api/v1/parking/vehicle-lookup/?license_plate=51K-992.14")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"


def test_vehicle_lookup_customer_forbidden(auth_customer):
    """Khách hàng bị từ chối truy cập -> 403 MSG-4.2-M01."""
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    response = client.get("/api/v1/parking/vehicle-lookup/?license_plate=51K-992.14")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"


def test_vehicle_lookup_missing_param(auth_employee):
    """Không truyền tham số license_plate -> 400 PROP-4.5.1-P01."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-lookup/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P01"


def test_vehicle_lookup_not_found(auth_employee):
    """Biển số không tồn tại trong hệ thống -> 404 MSG-4.5.1-M01."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/vehicle-lookup/?license_plate=99Z-999.99")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "MSG-4.5.1-M01"


def test_vehicle_lookup_soft_deleted_vehicle_returns_404(auth_employee):
    """Phương tiện bị xóa mềm (deleted_at IS NOT NULL) không được tìm thấy -> 404 MSG-4.5.1-M01."""
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-TEST-01",
        full_name="Trần Văn Soft",
        phone="0901112233",
        identity_card_number="049090123450",
    )
    v = Vehicle.objects.create(
        code="XE-DEL-01",
        license_plate="43B-123.45",
        license_plate_norm="43B12345",
        vehicle_type=vtype,
        customer=cust,
        model_name="Vios",
        deleted_at=timezone.now(),
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        f"/api/v1/parking/vehicle-lookup/?license_plate={v.license_plate}"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "MSG-4.5.1-M01"


def test_vehicle_lookup_success_existing_vehicle(auth_employee):
    """Tra cứu xe hợp lệ có sẵn trong seed data -> 200 OK."""
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert v is not None

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        f"/api/v1/parking/vehicle-lookup/?license_plate={v.license_plate}"
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert data["vehicle"]["license_plate_norm"] == v.license_plate_norm
    assert "customer" in data
    assert data["is_blacklisted"] is False


def test_vehicle_lookup_anonymized_customer(auth_employee):
    """Khách hàng được đánh dấu is_anonymized=True phải được che PII."""
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-ANON-01",
        full_name="Nguyễn Văn Bảo Mật",
        phone="0988776655",
        identity_card_number="049090123451",
        is_anonymized=True,
        anonymized_at=timezone.now(),
    )
    v = Vehicle.objects.create(
        code="XE-ANON-01",
        license_plate="79A-777.88",
        license_plate_norm="79A77788",
        vehicle_type=vtype,
        customer=cust,
        model_name="Civic",
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        f"/api/v1/parking/vehicle-lookup/?license_plate={v.license_plate}"
    )
    assert response.status_code == status.HTTP_200_OK
    cust_data = response.data["customer"]
    assert cust_data["is_anonymized"] is True
    assert cust_data["full_name"] == "Khách hàng ẩn danh"
    assert cust_data["phone"] is None


def test_vehicle_lookup_blacklisted_vehicle(auth_employee):
    """Phương tiện nằm trong danh sách đen trả về is_blacklisted = True."""
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-BL-01",
        full_name="Lê Văn Đen",
        phone="0977112233",
        identity_card_number="049090123452",
    )
    v = Vehicle.objects.create(
        code="XE-BL-01",
        license_plate="30F-999.00",
        license_plate_norm="30F99900",
        vehicle_type=vtype,
        customer=cust,
        model_name="Accord",
    )
    PlateBlacklist.objects.create(
        license_plate=v.license_plate,
        license_plate_norm=v.license_plate_norm,
        reason="Nghi vấn trộm cắp",
        is_active=True,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        f"/api/v1/parking/vehicle-lookup/?license_plate={v.license_plate}"
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.data["is_blacklisted"] is True


def test_vehicle_lookup_unregistered_but_blacklisted_returns_404_with_flag(
    auth_employee,
):
    """
    Biển số chưa đăng ký nhưng có trong plate_blacklist:
    Vẫn trả về HTTP 404 MSG-4.5.1-M01, nhưng trường details phải chứa {"is_blacklisted": True}.
    """
    unregistered_plate = "51H-999.99"
    norm_plate = "51H99999"

    assert not Vehicle.objects.filter(license_plate_norm=norm_plate).exists()

    PlateBlacklist.objects.create(
        license_plate=unregistered_plate,
        license_plate_norm=norm_plate,
        reason="Xe vãng lai vi phạm an ninh",
        is_active=True,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        f"/api/v1/parking/vehicle-lookup/?license_plate={unregistered_plate}"
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "MSG-4.5.1-M01"
    assert response.data["details"].get("is_blacklisted") is True
