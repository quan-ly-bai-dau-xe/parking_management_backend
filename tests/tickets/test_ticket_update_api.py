"""
Tests for Ticket Update API (PATCH /api/v1/tickets/{lookup}/ - SRS 4.6.3).
Covers:
- Optimistic Concurrency Control (OCC) with row_version (409 PROP-4.6.3-P03).
- Extending ticket validity period (effective_to validation).
- Renewal history record created in TicketRenewal.
- Changing slot, ticket_type, price, and notes.
- RBAC permissions (Employee & Manager allowed, Customer forbidden).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from rest_framework import status

from apps.parking.models import ParkingSlot
from apps.tickets.models import Ticket, TicketRenewal, TicketType

pytestmark = pytest.mark.django_db

TICKETS_URL = "/api/v1/tickets/"


def test_ticket_update_success(employee_client):
    """
    SRS 4.6.3: Cập nhật thành công vé đỗ xe khi gửi đúng row_version và ngày hết hạn hợp lệ:
    - effective_to mới > effective_to cũ.
    - row_version được tăng lên 1 (nhờ DB trigger trg_ticket_row_version).
    - Tự động ghi nhật ký vào TicketRenewal.
    """
    t = Ticket.objects.filter(deleted_at__isnull=True, status="ACTIVE").first()
    assert t is not None
    initial_version = t.row_version
    old_effective_to = t.effective_to
    new_effective_to = old_effective_to + timedelta(days=30)

    payload = {
        "row_version": initial_version,
        "effective_to": new_effective_to.isoformat(),
        "notes": "Gia hạn thêm 30 ngày qua test_ticket_update_success",
    }

    response = employee_client.patch(
        f"{TICKETS_URL}{t.code}/", data=payload, format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["row_version"] == initial_version + 1
    assert data["notes"] == payload["notes"]

    # Kiểm tra bản ghi trong TicketRenewal
    renewal = TicketRenewal.objects.filter(ticket_id=t.id).order_by("-id").first()
    assert renewal is not None
    assert renewal.old_effective_to == old_effective_to
    assert abs((renewal.new_effective_to - new_effective_to).total_seconds()) < 2


def test_ticket_update_occ_conflict_returns_409(employee_client):
    """
    Kiểm soát đồng thời lạc quan (OCC):
    Nếu client gửi row_version không khớp với CSDL hiện tại -> 409 Conflict với mã PROP-4.6.3-P03.
    """
    t = Ticket.objects.filter(deleted_at__isnull=True, status="ACTIVE").first()
    assert t is not None
    stale_version = t.row_version + 999  # Giả lập phiên bản lỗi thời

    payload = {
        "row_version": stale_version,
        "effective_to": (t.effective_to + timedelta(days=10)).isoformat(),
    }

    response = employee_client.patch(
        f"{TICKETS_URL}{t.id}/", data=payload, format="json"
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    data = response.json()
    assert data.get("code") == "PROP-4.6.3-P03"
    assert "người dùng khác" in data.get("message", "")


def test_ticket_update_invalid_new_date_returns_400(employee_client):
    """
    Validation SRS 4.6.3: Ngày gia hạn mới phải lớn hơn ngày hết hạn cũ:
    Nếu gửi effective_to mới <= effective_to cũ -> 400 Bad Request với MSG-4.6.3-M01.
    """
    t = Ticket.objects.filter(deleted_at__isnull=True, status="ACTIVE").first()
    assert t is not None

    invalid_date = t.effective_to - timedelta(days=1)  # Ngày mới nhỏ hơn ngày cũ

    payload = {
        "row_version": t.row_version,
        "effective_to": invalid_date.isoformat(),
    }

    response = employee_client.patch(
        f"{TICKETS_URL}{t.id}/", data=payload, format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data.get("code") == "MSG-4.6.3-M01"
    assert "lớn hơn ngày cũ" in data.get("message", "")


def test_ticket_update_slot_and_type(employee_client):
    """Cập nhật loại vé mới và vị trí đỗ mới cho vé."""
    t = Ticket.objects.filter(deleted_at__isnull=True, status="ACTIVE").first()
    assert t is not None

    # Tìm slot khả dụng khác
    new_slot = (
        ParkingSlot.objects.filter(deleted_at__isnull=True, status="AVAILABLE")
        .exclude(id=t.slot_id)
        .first()
    )
    new_type = TicketType.objects.exclude(id=t.ticket_type_id).first()

    payload = {
        "row_version": t.row_version,
        "slot_id": new_slot.id if new_slot else None,
        "ticket_type_id": new_type.id if new_type else None,
        "price": "1500000.00",
        "notes": "Đổi sang loại vé và vị trí mới",
    }

    response = employee_client.patch(
        f"{TICKETS_URL}{t.id}/", data=payload, format="json"
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert Decimal(str(data["price"])) == Decimal("1500000.00")
    if new_slot:
        assert data["slot_id"] == new_slot.id


def test_ticket_update_permissions(
    anonymous_client, customer_client, employee_client, manager_client
):
    """
    Phân quyền cập nhật vé (PATCH):
    - Anonymous -> 401
    - Customer -> 403
    - Employee -> 200
    - Manager -> 200
    """
    t = Ticket.objects.filter(deleted_at__isnull=True, status="ACTIVE").first()
    url = f"{TICKETS_URL}{t.id}/"
    payload = {"row_version": t.row_version, "notes": "Test auth"}

    assert (
        anonymous_client.patch(url, data=payload, format="json").status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    assert (
        customer_client.patch(url, data=payload, format="json").status_code
        == status.HTTP_403_FORBIDDEN
    )

    # Employee được phép cập nhật
    res_emp = employee_client.patch(url, data=payload, format="json")
    assert res_emp.status_code == status.HTTP_200_OK

    # Manager cũng được phép cập nhật
    t.refresh_from_db()
    res_mgr = manager_client.patch(
        url, data={"row_version": t.row_version, "notes": "Test mgr"}, format="json"
    )
    assert res_mgr.status_code == status.HTTP_200_OK
