"""
Tests for Vehicle Delete API (DELETE /api/v1/vehicles/{id}/).

Verifies:
- All 3 DEL-03 Database Trigger Guards returning HTTP 409 Conflict:
  - Guard 1 (open parking session): XE0001 -> 409 (PROP-DEL-03-OPEN-SES).
  - Guard 2 (active unexpired ticket): XE0007 -> 409 (PROP-DEL-03-ACTIVE-TKT).
  - Guard 3 (active slot reservation): XE0016 / active reservation -> 409 (PROP-DEL-03-ACTIVE-RSV).
- Raw PostgreSQL database trigger level verification:
  - Soft-delete update on blocked vehicle raises Postgres check_violation with trigger HINT.
  - Plain SQL DELETE raises SQLSTATE 55000 (trg_prevent_plain_delete_vehicle).
- Successful soft-delete on an unblocked vehicle:
  - Sets deleted_at and deleted_by.
  - Returns 200 OK with code MSG-4.3.1-M01.
  - Record disappears from GET /api/v1/vehicles/.
  - Record disappears from GET /api/v1/parking/vehicle-search/.
  - Returns 404 in GET /api/v1/vehicles/{id}/ and GET /api/v1/parking/vehicle-lookup/.
- Permission matrix: Anonymous -> 401, Customer -> 403, Employee -> 403, Manager -> 200.
"""

from datetime import timedelta

import pytest
from django.db import connection, transaction
from django.utils import timezone
from rest_framework import status

from apps.parking.models import SlotReservation
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db

BASE_URL = "/api/v1/vehicles/"


def test_vehicle_delete_guard_1_open_parking_session(manager_client):
    """
    DEL-03 Guard 1: Xe đang có phiên đỗ mở trong bãi (exit_time IS NULL)
    như XE0001 không được phép xóa -> 409 Conflict (PROP-DEL-03-OPEN-SES).
    """
    v1 = Vehicle.objects.get(code="XE0001")
    response = manager_client.delete(f"{BASE_URL}{v1.id}/")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json().get("code") == "PROP-DEL-03-OPEN-SES"
    assert "phiên đỗ đang mở" in response.json().get("message", "")


def test_vehicle_delete_guard_2_active_ticket(manager_client):
    """
    DEL-03 Guard 2: Xe không đỗ trong bãi nhưng đang có vé còn hạn
    như XE0007 không được phép xóa -> 409 Conflict (PROP-DEL-03-ACTIVE-TKT).
    """
    v7 = Vehicle.objects.get(code="XE0007")
    response = manager_client.delete(f"{BASE_URL}{v7.id}/")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json().get("code") == "PROP-DEL-03-ACTIVE-TKT"
    assert "vé đỗ xe còn hiệu lực" in response.json().get("message", "")


def test_vehicle_delete_guard_3_active_slot_reservation(manager_client):
    """
    DEL-03 Guard 3: Xe đang có đặt trước vị trí đỗ xe còn hiệu lực (status='ACTIVE' và reserved_until > now)
    như XE0016 không được phép xóa -> 409 Conflict (PROP-DEL-03-ACTIVE-RSV).
    """
    v16 = Vehicle.objects.get(code="XE0016")
    now = timezone.now()
    rsv = SlotReservation.objects.get(code="RSV-2026-0001")
    rsv.status = "ACTIVE"
    rsv.reserved_until = now + timedelta(hours=2)
    rsv.save(update_fields=["status", "reserved_until"])

    response = manager_client.delete(f"{BASE_URL}{v16.id}/")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json().get("code") == "PROP-DEL-03-ACTIVE-RSV"
    assert "đặt trước vị trí đỗ" in response.json().get("message", "")


def test_vehicle_delete_database_trigger_direct_soft_delete_violation():
    """
    Kiểm chứng trực tiếp trigger CSDL fn_guard_soft_delete_and_restore() bằng câu lệnh SQL raw:
    Thực thi UPDATE vehicle SET deleted_at = now() trên xe XE0001 (phiên đỗ mở)
    phải bị PostgreSQL chặn với ngoại lệ check_violation chứa HINT PROP-DEL-03-OPEN-SES.
    """
    v1 = Vehicle.objects.get(code="XE0001")
    with (
        pytest.raises(Exception) as exc_info,
        transaction.atomic(),
        connection.cursor() as cur,
    ):
        cur.execute(
            "UPDATE vehicle SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s;",
            [v1.id],
        )
    err_text = str(exc_info.value)
    assert (
        "Phương tiện đang đỗ trong bãi xe" in err_text
        or "PROP-DEL-03-OPEN-SES" in err_text
    )


def test_vehicle_delete_database_trigger_prevents_plain_hard_delete():
    """
    Kiểm chứng trigger CSDL trg_prevent_plain_delete_vehicle:
    Thực thi DELETE FROM vehicle WHERE id = ... bị chặn tuyệt đối với SQLSTATE 55000.
    """
    v = Vehicle.objects.filter(deleted_at__isnull=True).last()
    with (
        pytest.raises(Exception) as exc_info,
        transaction.atomic(),
        connection.cursor() as cur,
    ):
        cur.execute("DELETE FROM vehicle WHERE id = %s;", [v.id])
    err_text = str(exc_info.value)
    assert "plain DELETE" in err_text or "xóa trực tiếp" in err_text


def test_vehicle_delete_successful_soft_delete(manager_client, auth_manager):
    """
    Xóa mềm thành công xe không bị ràng buộc (XE0029):
    - Trả về 200 OK với thông điệp thành công MSG-4.3.1-M01.
    - Cập nhật deleted_at và deleted_by = actor.
    - Biến mất ngay khỏi danh sách GET /api/v1/vehicles/.
    - Biến mất ngay khỏi tìm kiếm GET /api/v1/parking/vehicle-search/.
    - Trả về 404 trong GET /api/v1/vehicles/{id}/ và GET /api/v1/parking/vehicle-lookup/.
    """
    v = Vehicle.objects.get(code="XE0029")
    original_id = v.id
    plate = v.license_plate

    # 1. Gọi API DELETE
    response = manager_client.delete(f"{BASE_URL}{original_id}/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json().get("code") == "MSG-4.3.1-M01"

    # 2. Kiểm tra trực tiếp trong DB
    v.refresh_from_db()
    assert v.deleted_at is not None
    assert v.deleted_by_id == auth_manager.id

    # 3. Biến mất khỏi API danh sách
    res_list = manager_client.get(f"{BASE_URL}?code=XE0029")
    assert res_list.status_code == status.HTTP_200_OK
    assert res_list.json()["count"] == 0

    # 4. Biến mất khỏi API tra cứu chi tiết -> 404
    res_detail = manager_client.get(f"{BASE_URL}{original_id}/")
    assert res_detail.status_code == status.HTTP_404_NOT_FOUND

    # 5. Biến mất khỏi parking vehicle-search
    res_search = manager_client.get("/api/v1/parking/vehicle-search/?q=XE0029")
    assert res_search.status_code == status.HTTP_200_OK
    assert res_search.json()["count"] == 0

    # 6. Biến mất khỏi parking vehicle-lookup -> 404
    res_lookup = manager_client.get(
        f"/api/v1/parking/vehicle-lookup/?license_plate={plate}"
    )
    assert res_lookup.status_code == status.HTTP_404_NOT_FOUND


def test_vehicle_delete_permissions(anonymous_client, customer_client, employee_client):
    """
    Quyền xóa xe (DELETE):
    - Anonymous -> 401
    - Customer -> 403
    - Employee -> 403 (chỉ Manager được xóa)
    """
    v = Vehicle.objects.get(code="XE0030")
    url = f"{BASE_URL}{v.id}/"

    assert anonymous_client.delete(url).status_code == status.HTTP_401_UNAUTHORIZED
    assert customer_client.delete(url).status_code == status.HTTP_403_FORBIDDEN
    assert employee_client.delete(url).status_code == status.HTTP_403_FORBIDDEN
