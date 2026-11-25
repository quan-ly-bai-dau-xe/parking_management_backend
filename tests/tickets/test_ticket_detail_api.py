"""
Tests for Ticket Detail API (GET /api/v1/tickets/{lookup}/).
Covers:
- Lookup by integer ID.
- Lookup by string business code (VT0001).
- Nested relationships: customer, vehicle, slot, ticket_type, renewals list.
- 404 for non-existent ticket or soft-deleted ticket.
- RBAC permissions.
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from rest_framework import status

from apps.tickets.models import Ticket

pytestmark = pytest.mark.django_db

TICKETS_URL = "/api/v1/tickets/"


def test_ticket_detail_by_id(employee_client):
    """GET /api/v1/tickets/{id}/ trả về chi tiết vé đầy đủ."""
    t = Ticket.objects.filter(deleted_at__isnull=True).first()
    assert t is not None

    response = employee_client.get(f"{TICKETS_URL}{t.id}/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == t.id
    assert data["code"] == t.code
    assert data["customer_id"] == t.customer_id
    assert data["vehicle_id"] == t.vehicle_id
    assert "ticket_type" in data
    assert "slot_location" in data
    assert "renewals" in data
    assert isinstance(data["renewals"], list)


def test_ticket_detail_by_code(employee_client):
    """GET /api/v1/tickets/{code}/ tra cứu bằng string business code (VT0001)."""
    response = employee_client.get(f"{TICKETS_URL}VT0001/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["code"] == "VT0001"
    assert data["license_plate"] != ""


def test_ticket_detail_not_found(employee_client):
    """GET /api/v1/tickets/999999/ trả về 404 với mã lỗi PROP-4.6.4-P05."""
    response = employee_client.get(f"{TICKETS_URL}999999/")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data.get("code") == "PROP-4.6.4-P05"
    assert "không tồn tại" in data.get("message", "")


def test_ticket_detail_soft_deleted_returns_404(employee_client):
    """Vé đã bị soft delete (deleted_at IS NOT NULL) tra cứu sẽ trả về 404 PROP-4.6.4-P05."""
    t = Ticket.objects.filter(deleted_at__isnull=True).last()
    assert t is not None
    t.deleted_at = timezone.now()
    t.save(update_fields=["deleted_at"])

    # Tra cứu bằng ID
    res_id = employee_client.get(f"{TICKETS_URL}{t.id}/")
    assert res_id.status_code == status.HTTP_404_NOT_FOUND
    assert res_id.json().get("code") == "PROP-4.6.4-P05"

    # Tra cứu bằng Code
    res_code = employee_client.get(f"{TICKETS_URL}{t.code}/")
    assert res_code.status_code == status.HTTP_404_NOT_FOUND
    assert res_code.json().get("code") == "PROP-4.6.4-P05"


def test_ticket_detail_permissions(
    anonymous_client, customer_client, employee_client, manager_client
):
    """
    Phân quyền truy cập Ticket Detail:
    - Anonymous -> 401
    - Customer -> 403
    - Employee -> 200
    - Manager -> 200
    """
    url = f"{TICKETS_URL}VT0001/"
    assert anonymous_client.get(url).status_code == status.HTTP_401_UNAUTHORIZED
    assert customer_client.get(url).status_code == status.HTTP_403_FORBIDDEN
    assert employee_client.get(url).status_code == status.HTTP_200_OK
    assert manager_client.get(url).status_code == status.HTTP_200_OK
