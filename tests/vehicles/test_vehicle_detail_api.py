"""
Tests for Vehicle Detail API (GET /api/v1/vehicles/{id}/).

Verifies:
- Complete vehicle specification payload (brand, model_name, color, notes, row_version, timestamps).
- Owner block: customer profile, registered_vehicles_count, PII masking when is_anonymized=True.
- Ticket block: subscription type, remaining days, lifecycle progress percentage (progress_pct).
- Current slot formatting when parked or ticket-assigned.
- Non-existent vehicle ID -> 404 (MSG-4.4.1-M01).
- Soft-deleted vehicle ID -> 404 (MSG-4.4.1-M01).
- Permission matrix: Anonymous -> 401, Customer -> 403, Employee -> 200, Manager -> 200.
"""

import pytest
from rest_framework import status

from apps.customers.models import Customer
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db

BASE_URL = "/api/v1/vehicles/"


def test_vehicle_detail_success_parked_with_ticket(employee_client):
    """
    Xem chi tiết phương tiện đang đỗ và có vé hợp lệ (XE0001).
    Khẳng định đầy đủ các trường thông số, chủ xe, vị trí đỗ và vé.
    """
    v1 = Vehicle.objects.get(code="XE0001")
    response = employee_client.get(f"{BASE_URL}{v1.id}/")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["id"] == v1.id
    assert data["code"] == "XE0001"
    assert data["license_plate"] == "43K-860.50"
    assert data["brand"] == "Toyota"
    assert data["model_name"] == "Vios 1.5G"
    assert data["color"] == "Trắng"
    assert data["status"] == "parked"
    assert data["status_display"] == "Đang đỗ"
    assert data["row_version"] == v1.row_version

    # Current slot
    assert data["current_slot"] is not None
    assert "Khu" in data["current_slot"]
    assert "Slot" in data["current_slot"]

    # Owner block
    owner = data["customer"]
    assert owner["code"] == "KH0001"
    assert owner["full_name"] == "Trịnh Xuân Trường"
    assert owner["registered_vehicles_count"] >= 1
    assert owner["is_anonymized"] is False

    # Ticket block
    ticket = data["ticket"]
    assert ticket is not None
    assert ticket["ticket_type_name"] == "Vé tháng"
    assert ticket["is_valid"] is True
    assert ticket["days_remaining"] > 0
    assert 0.0 <= ticket["progress_pct"] <= 100.0


def test_vehicle_detail_without_ticket(employee_client):
    """Xem chi tiết phương tiện không có vé (XE0026) -> ticket is null."""
    v26 = Vehicle.objects.get(code="XE0026")
    response = employee_client.get(f"{BASE_URL}{v26.id}/")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["code"] == "XE0026"
    assert data["ticket"] is None
    assert data["status"] == "left"


def test_vehicle_detail_anonymized_customer(employee_client, car_type):
    """Khách hàng bị ẩn danh (is_anonymized=True) -> tên, sđt, email bị che mờ."""
    from django.utils import timezone

    anon_cust = Customer.objects.create(
        code="KH-ANON-01",
        full_name="Bí Mật Khách Hàng",
        phone="0911223344",
        email="secret@example.com",
        identity_card_number="049090123456",
        is_anonymized=True,
        anonymized_at=timezone.now(),
    )
    v_anon = Vehicle.objects.create(
        code="XE-ANON-01",
        license_plate="51K-000.01",
        license_plate_norm="51K00001",
        model_name="VF9",
        vehicle_type=car_type,
        customer=anon_cust,
    )

    response = employee_client.get(f"{BASE_URL}{v_anon.id}/")
    assert response.status_code == status.HTTP_200_OK

    owner = response.json()["customer"]
    assert owner["is_anonymized"] is True
    assert owner["full_name"] == "Khách hàng ẩn danh"
    assert owner["phone"] == "***"
    assert owner["email"] == "***"


def test_vehicle_detail_not_found(employee_client):
    """ID phương tiện không tồn tại -> 404 (MSG-4.4.1-M01)."""
    response = employee_client.get(f"{BASE_URL}999999/")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json().get("code") == "MSG-4.4.1-M01"


def test_vehicle_detail_soft_deleted_returns_404(employee_client, auth_manager):
    """Phương tiện đã bị xóa mềm -> 404 (MSG-4.4.1-M01)."""
    v = Vehicle.objects.filter(code="XE0030", deleted_at__isnull=True).first()
    assert v is not None
    v.soft_delete(user=auth_manager)

    response = employee_client.get(f"{BASE_URL}{v.id}/")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json().get("code") == "MSG-4.4.1-M01"


def test_vehicle_detail_permissions(
    anonymous_client, customer_client, employee_client, manager_client
):
    """Kiểm tra ma trận phân quyền trên endpoint chi tiết xe."""
    v1 = Vehicle.objects.get(code="XE0001")
    url = f"{BASE_URL}{v1.id}/"

    # Anonymous -> 401
    assert anonymous_client.get(url).status_code == status.HTTP_401_UNAUTHORIZED
    # Customer -> 403
    assert customer_client.get(url).status_code == status.HTTP_403_FORBIDDEN
    # Employee -> 200
    assert employee_client.get(url).status_code == status.HTTP_200_OK
    # Manager -> 200
    assert manager_client.get(url).status_code == status.HTTP_200_OK
