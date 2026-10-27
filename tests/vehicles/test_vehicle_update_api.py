"""
Tests for Vehicle Update API (PATCH /api/v1/vehicles/{id}/).

Verifies:
- Optimistic Concurrency Control (OCC) using row_version:
  - Missing row_version in PATCH payload -> 400 Bad Request (PROP-GEN-P01).
  - Stale row_version token -> 409 Conflict (MSG-4.3.1-M03).
- Successful update:
  - Modifies allowed attributes (model_name, brand, color, notes, image_url).
  - Database trigger automatically increments row_version (new = old + 1).
- Partial update: modifies single attribute while preserving remaining attributes.
- Read-only fields (code, ticket_type_id, ticket_expires_at) ignored per OQ-52.
- Foreign key updates (customer_id, vehicle_type_id) and validation errors:
  - Unknown / deleted customer -> 400 (PROP-4.4.4-P02).
  - Invalid vehicle type (not CAR/EV) -> 400 (PROP-GEN-P01).
- Non-existent vehicle ID -> 404 (MSG-4.4.1-M01).
- Soft-deleted vehicle ID -> 404 (MSG-4.4.1-M01).
- RBAC permissions: Anonymous -> 401, Customer -> 403, Employee -> 403, Manager -> 200.
"""

import pytest
from rest_framework import status

from apps.customers.models import Customer
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db

BASE_URL = "/api/v1/vehicles/"


def test_vehicle_update_missing_row_version_rejected(manager_client):
    """PATCH không truyền row_version -> 400 Bad Request (PROP-GEN-P01)."""
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    payload = {"color": "Xanh lam"}
    response = manager_client.patch(f"{BASE_URL}{v.id}/", payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json().get("code") == "PROP-GEN-P01"


def test_vehicle_update_stale_row_version_conflict(manager_client):
    """
    PATCH truyền row_version cũ (stale token) -> 409 Conflict (MSG-4.3.1-M03).
    Bảo vệ chống Lost Updates khi có 2 quản lý cùng chỉnh sửa phương tiện.
    """
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    stale_version = v.row_version + 999  # Out of sync version

    payload = {
        "row_version": stale_version,
        "color": "Vàng cát",
    }
    response = manager_client.patch(f"{BASE_URL}{v.id}/", payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json().get("code") == "MSG-4.3.1-M03"


def test_vehicle_update_success_increments_row_version(manager_client):
    """
    Cập nhật thành công các trường thông số:
    - Giá trị mới được lưu trữ và trả về đúng.
    - row_version tự động tăng thêm 1 qua trigger CSDL.
    """
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    initial_version = v.row_version

    payload = {
        "row_version": initial_version,
        "brand": "Mazda",
        "model_name": "CX-5 Premium",
        "color": "Đỏ pha lê",
        "notes": "Ghi chú cập nhật bởi quản lý",
    }
    response = manager_client.patch(f"{BASE_URL}{v.id}/", payload, format="json")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["brand"] == "Mazda"
    assert data["model_name"] == "CX-5 Premium"
    assert data["color"] == "Đỏ pha lê"
    assert data["notes"] == "Ghi chú cập nhật bởi quản lý"
    assert data["row_version"] == initial_version + 1

    # Verify directly in DB
    v.refresh_from_db()
    assert v.model_name == "CX-5 Premium"
    assert v.row_version == initial_version + 1


def test_vehicle_update_partial_fields(manager_client):
    """Cập nhật từng phần (chỉ sửa color) -> các trường khác giữ nguyên."""
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    original_model = v.model_name
    current_version = v.row_version

    payload = {
        "row_version": current_version,
        "color": "Xám xi măng",
    }
    response = manager_client.patch(f"{BASE_URL}{v.id}/", payload, format="json")
    assert response.status_code == status.HTTP_200_OK

    v.refresh_from_db()
    assert v.color == "Xám xi măng"
    assert v.model_name == original_model  # Unchanged
    assert v.row_version == current_version + 1


def test_vehicle_update_read_only_fields_ignored(manager_client):
    """Cố tình truyền trường code hoặc thông tin vé trong PATCH -> bị bỏ qua per OQ-52."""
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    original_code = v.code
    current_version = v.row_version

    payload = {
        "row_version": current_version,
        "code": "XE-MUTATED",
        "ticket_type_id": 999,
        "ticket_expires_at": "2099-01-01T00:00:00Z",
    }
    response = manager_client.patch(f"{BASE_URL}{v.id}/", payload, format="json")
    assert response.status_code == status.HTTP_200_OK

    v.refresh_from_db()
    assert v.code == original_code  # Read-only code remains intact


def test_vehicle_update_unknown_or_deleted_customer(manager_client, auth_manager):
    """Cập nhật customer_id không tồn tại hoặc đã bị xóa mềm -> 400 Bad Request."""
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()

    # 1. Unknown customer
    res_unknown = manager_client.patch(
        f"{BASE_URL}{v.id}/",
        {"row_version": v.row_version, "customer_id": 999999},
        format="json",
    )
    assert res_unknown.status_code == status.HTTP_400_BAD_REQUEST
    assert res_unknown.json().get("code") == "PROP-4.4.4-P02"

    # 2. Deleted customer
    cust = Customer.objects.create(
        code="KH-DEL-02",
        full_name="Khách Xóa",
        phone="0911003344",
        identity_card_number="049090123888",
    )
    cust.soft_delete(user=auth_manager)
    res_deleted = manager_client.patch(
        f"{BASE_URL}{v.id}/",
        {"row_version": v.row_version, "customer_id": cust.id},
        format="json",
    )
    assert res_deleted.status_code == status.HTTP_400_BAD_REQUEST
    assert res_deleted.json().get("code") == "PROP-4.4.4-P02"


def test_vehicle_update_invalid_vehicle_type(manager_client):
    """Cập nhật vehicle_type_id sang loại không hợp lệ -> 400 Bad Request (PROP-GEN-P01)."""
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    res = manager_client.patch(
        f"{BASE_URL}{v.id}/",
        {"row_version": v.row_version, "vehicle_type_id": 999999},
        format="json",
    )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert res.json().get("code") == "PROP-GEN-P01"


def test_vehicle_update_not_found_or_soft_deleted(manager_client, auth_manager):
    """Cập nhật xe không tồn tại hoặc đã bị xóa mềm -> 404 (MSG-4.4.1-M01)."""
    # Non-existent
    res_404 = manager_client.patch(
        f"{BASE_URL}999999/", {"row_version": 1}, format="json"
    )
    assert res_404.status_code == status.HTTP_404_NOT_FOUND
    assert res_404.json().get("code") == "MSG-4.4.1-M01"

    # Soft-deleted
    v_del = Vehicle.objects.filter(code="XE0030", deleted_at__isnull=True).first()
    assert v_del is not None
    v_del.soft_delete(user=auth_manager)

    res_del = manager_client.patch(
        f"{BASE_URL}{v_del.id}/", {"row_version": 1}, format="json"
    )
    assert res_del.status_code == status.HTTP_404_NOT_FOUND
    assert res_del.json().get("code") == "MSG-4.4.1-M01"


def test_vehicle_update_permissions(anonymous_client, customer_client, employee_client):
    """
    Quyền cập nhật xe (PATCH):
    - Anonymous -> 401
    - Customer -> 403
    - Employee -> 403 (chỉ Manager được cập nhật)
    """
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    url = f"{BASE_URL}{v.id}/"
    payload = {"row_version": v.row_version, "color": "Xanh lá"}

    assert (
        anonymous_client.patch(url, payload, format="json").status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        customer_client.patch(url, payload, format="json").status_code
        == status.HTTP_403_FORBIDDEN
    )
    assert (
        employee_client.patch(url, payload, format="json").status_code
        == status.HTTP_403_FORBIDDEN
    )


def test_vehicle_update_license_plate_ignored(manager_client):
    """
    K3: license_plate là bất biến (read-only).
    Khi client cố tình gửi license_plate mới trong PATCH payload -> bị bỏ qua,
    biển số cũ trong CSDL giữ nguyên không đổi.
    """
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert v is not None
    original_plate = v.license_plate
    current_version = v.row_version

    payload = {
        "row_version": current_version,
        "license_plate": "51K-999.88",
    }
    response = manager_client.patch(f"{BASE_URL}{v.id}/", payload, format="json")
    assert response.status_code == status.HTTP_200_OK

    v.refresh_from_db()
    assert v.license_plate == original_plate


def test_vehicle_update_owner_reassignment_rejected_when_tickets_exist(
    manager_client, active_customer
):
    """
    K4: Đổi chủ sở hữu (customer_id) trên phương tiện đang có vé đỗ xe
    -> 409 Conflict (PROP-VEH-OWNER-CHANGE-CONFLICT).
    Không được trả về MSG-4.3.1-M03 (OCC stale token).
    """
    v = Vehicle.objects.filter(deleted_at__isnull=True, tickets__isnull=False).first()
    assert v is not None, "Seed data must contain vehicles with tickets"

    new_cust = Customer.objects.create(
        code="KH9901",
        full_name="Chủ Mới Test",
        phone="0911998877",
        identity_card_number="049090123777",
    )

    payload = {
        "row_version": v.row_version,
        "customer_id": new_cust.id,
    }
    response = manager_client.patch(f"{BASE_URL}{v.id}/", payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT
    data = response.json()
    assert data.get("code") == "PROP-VEH-OWNER-CHANGE-CONFLICT"
    assert "Không thể thay đổi chủ sở hữu" in data.get("message", "")
    assert data.get("details", {}).get("has_tickets") is True


def test_vehicle_update_owner_reassignment_success_when_no_active_links(
    manager_client, car_type, active_customer
):
    """
    K4: Đổi chủ sở hữu (customer_id) trên phương tiện KHÔNG có vé, phiên đỗ, hoặc đặt chỗ
    -> Thành công (200 OK) và cập nhật customer_id đúng.
    """
    from apps.vehicles.services.vehicles import create_vehicle

    v = create_vehicle(
        license_plate="51K-889.99",
        model_name="Unlinked Vehicle",
        vehicle_type_id=car_type.id,
        customer_id=active_customer.id,
    )

    new_cust = Customer.objects.create(
        code="KH9902",
        full_name="Chủ Mới Hợp Lệ",
        phone="0911998866",
        identity_card_number="049090123666",
    )

    try:
        payload = {
            "row_version": v.row_version,
            "customer_id": new_cust.id,
        }
        response = manager_client.patch(f"{BASE_URL}{v.id}/", payload, format="json")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["customer"]["id"] == new_cust.id

        v.refresh_from_db()
        assert v.customer_id == new_cust.id
    finally:
        v.delete()
