"""
Tests for Ticket Delete API (DELETE /api/v1/tickets/{lookup}/ - SRS 4.6.4 / DEL-04).
Covers:
- Strict RBAC: Manager-only (Employee and Customer forbidden).
- DEL-04 Guard 1: Active unexpired ticket -> 400 PROP-4.6.4-P01.
- DEL-04 Guard 2: Renewed ticket -> 400 PROP-4.6.4-P02.
- DEL-04 Guard 3: Parked vehicle (open session) -> 400 PROP-DEL-04-OPEN-SES.
- Successful soft-delete on expired non-renewed ticket -> 200 MSG-4.6.4-M01.
- Database trigger protections (check_violation and immutable plain DELETE).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection, transaction
from django.utils import timezone
from rest_framework import status

from apps.parking.models import VehicleEntryExitLog
from apps.tickets.models import Ticket, TicketRenewal

pytestmark = pytest.mark.django_db

TICKETS_URL = "/api/v1/tickets/"


def test_ticket_delete_rbac_manager_only(
    anonymous_client, customer_client, employee_client, manager_client
):
    """
    SRS 4.6.4 / OQ-39: Thao tác xóa vé chỉ dành riêng cho Quản lý (MANAGER-only).
    - Anonymous -> 401
    - Customer -> 403
    - Employee -> 403 Forbidden (chỉ Manager được xóa vé)
    """
    t = Ticket.objects.filter(deleted_at__isnull=True).first()
    url = f"{TICKETS_URL}{t.id}/"

    assert anonymous_client.delete(url).status_code == status.HTTP_401_UNAUTHORIZED
    assert customer_client.delete(url).status_code == status.HTTP_403_FORBIDDEN
    assert employee_client.delete(url).status_code == status.HTTP_403_FORBIDDEN


def test_ticket_delete_guard_1_active_unexpired_ticket(manager_client):
    """
    DEL-04 Guard 1: Chặn xóa vé chưa hết hạn (effective_to > now, status='ACTIVE').
    Trả về HTTP 400 Bad Request với mã PROP-4.6.4-P01.
    """
    # VT0001 là vé active còn hạn
    t = Ticket.objects.get(code="VT0001")
    assert t.effective_to > timezone.now()

    response = manager_client.delete(f"{TICKETS_URL}{t.code}/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data.get("code") == "PROP-4.6.4-P01"
    assert "chưa hết hạn" in data.get("message", "")


def test_ticket_delete_guard_2_renewed_ticket(manager_client):
    """
    DEL-04 Guard 2: Chặn xóa vé đã từng được gia hạn (có bản ghi trong TicketRenewal).
    Trả về HTTP 400 Bad Request với mã PROP-4.6.4-P02.
    """
    now = timezone.now()
    # Lấy 1 vé đã hết hạn
    t = Ticket.objects.filter(code="VT0021").first()
    assert t is not None
    t.effective_to = now - timedelta(days=5)
    t.status = "EXPIRED"
    t.save()

    # Tạo 1 bản ghi renewal giả lập đã từng gia hạn
    TicketRenewal.objects.create(
        ticket=t,
        old_slot=t.slot,
        new_slot=t.slot,
        old_ticket_type=t.ticket_type,
        new_ticket_type=t.ticket_type,
        old_price=t.price,
        new_price=t.price,
        old_effective_to=t.effective_to - timedelta(days=30),
        new_effective_to=t.effective_to,
        additional_price=0,
        notes="Gia hạn trước đó",
    )

    response = manager_client.delete(f"{TICKETS_URL}{t.id}/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data.get("code") == "PROP-4.6.4-P02"
    assert "đã được gia hạn" in data.get("message", "")


def test_ticket_delete_guard_3_parked_vehicle_open_session(manager_client):
    """
    DEL-04 Guard 3: Chặn xóa vé khi phương tiện liên kết đang có phiên đỗ mở trong bãi.
    Vé VT0006 đã hết hạn, chưa từng gia hạn, nhưng xe XE0006 đang có phiên đỗ mở -> 400 PROP-DEL-04-OPEN-SES.
    """
    t = Ticket.objects.get(code="VT0006")
    assert t.effective_to < timezone.now() or t.status == "EXPIRED"
    assert not TicketRenewal.objects.filter(ticket_id=t.id).exists()
    assert VehicleEntryExitLog.objects.filter(
        vehicle_id=t.vehicle_id, exit_time__isnull=True
    ).exists()

    response = manager_client.delete(f"{TICKETS_URL}{t.id}/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data.get("code") == "PROP-DEL-04-OPEN-SES"
    assert "đang đỗ trong bãi xe" in data.get("message", "")


def test_ticket_delete_successful_soft_delete(manager_client, auth_manager):
    """
    Xóa mềm thành công vé đã hết hạn, chưa gia hạn, xe không trong bãi (VT0022):
    - Trả về 200 OK với {"code": "MSG-4.6.4-M01", "message": "Xóa thành công"}.
    - CSDL cập nhật: deleted_at = now, deleted_by = auth_manager.
    - TUYỆT ĐỐI KHÔNG gán status = 'TERMINATED' để không vi phạm constraint ck_ticket_status_enum.
    - row_version được tăng thêm 1.
    - Gọi lại GET /api/v1/tickets/{id}/ trả về 404 PROP-4.6.4-P05.
    """
    now = timezone.now()
    t = Ticket.objects.get(code="VT0022")
    # Đảm bảo vé hết hạn, không có renewal, không có phiên đỗ mở
    t.effective_to = now - timedelta(days=20)
    t.status = "EXPIRED"
    t.save()
    t.refresh_from_db()
    TicketRenewal.objects.filter(ticket_id=t.id).delete()
    VehicleEntryExitLog.objects.filter(
        vehicle_id=t.vehicle_id, exit_time__isnull=True
    ).delete()

    initial_version = t.row_version

    response = manager_client.delete(f"{TICKETS_URL}{t.code}/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data.get("code") == "MSG-4.6.4-M01"
    assert data.get("message") == "Xóa thành công"

    # Kiểm tra trực tiếp bản ghi trong CSDL
    t.refresh_from_db()
    assert t.deleted_at is not None
    assert t.deleted_by_id == auth_manager.id
    assert t.status != "TERMINATED"  # Không được gán TERMINATED
    assert t.row_version == initial_version + 1

    # Tra cứu lại qua API phải ra 404
    res_get = manager_client.get(f"{TICKETS_URL}{t.code}/")
    assert res_get.status_code == status.HTTP_404_NOT_FOUND
    assert res_get.json().get("code") == "PROP-4.6.4-P05"


def test_ticket_delete_database_trigger_direct_soft_delete_violation():
    """
    Kiểm chứng trigger CSDL trg_guard_soft_delete_and_restore_ticket bằng raw SQL:
    UPDATE ticket SET deleted_at = now() trên vé chưa hết hạn (VT0001)
    phải bị PostgreSQL chặn với ngoại lệ check_violation chứa HINT PROP-4.6.4-P01.
    """
    t = Ticket.objects.get(code="VT0001")
    with (
        pytest.raises(Exception) as exc_info,
        transaction.atomic(),
        connection.cursor() as cur,
    ):
        cur.execute(
            "UPDATE ticket SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s;",
            [t.id],
        )
    err_text = str(exc_info.value)
    assert "Vé chưa hết hạn" in err_text or "PROP-4.6.4-P01" in err_text


def test_ticket_delete_database_trigger_prevents_plain_hard_delete():
    """
    Kiểm chứng trigger CSDL trg_guard_ticket_immutable bằng raw SQL:
    DELETE FROM ticket WHERE id = ... bị chặn tuyệt đối với SQLSTATE 55000.
    """
    t = Ticket.objects.filter(deleted_at__isnull=True).last()
    with (
        pytest.raises(Exception) as exc_info,
        transaction.atomic(),
        connection.cursor() as cur,
    ):
        cur.execute("DELETE FROM ticket WHERE id = %s;", [t.id])
    err_text = str(exc_info.value)
    assert (
        "plain DELETE" in err_text
        or "bất biến" in err_text
        or "không được phép xóa" in err_text
    )
