"""
Tests for Vehicle Summary KPI API (GET /api/v1/vehicles/summary/).

Verifies:
- 4 KPI counts on baseline seed data asserted against independent raw SQL:
  - total_vehicles: 30
  - active_vehicles: 15 (parked + active ticket)
  - expiring_soon_tickets: 0
  - expired_tickets: 12
- Filtered KPI summaries (by vehicle_type and customer) compared against raw SQL.
- Dynamic ticket state updates affecting KPI aggregations.
- Permission matrix: Anonymous -> 401, Customer -> 403, Employee -> 200, Manager -> 200.
- HTTP method restrictions: POST/PUT/PATCH/DELETE -> 405 Method Not Allowed.
"""

from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework import status

from apps.tickets.models import Ticket, TicketType
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db

ENDPOINT_URL = "/api/v1/vehicles/summary/"


def _get_independent_sql_kpis(extra_where=""):
    """
    Thực thi câu truy vấn SQL độc lập thuần túy trực tiếp trên database để tính 4 KPI.
    Sử dụng CTE độc lập xác định vé đại diện theo 2 tầng ưu tiên (TL-28.1, OQ-52):
      - Tầng 1: Vé ACTIVE hoặc RENEWING có effective_to >= CURRENT_TIMESTAMP.
      - Tầng 2: Vé không bị CANCELLED có effective_to mới nhất trong quá khứ.
      - Loại trừ vé CANCELLED.
    """
    sql = f"""
        WITH rep_ticket AS (
            SELECT v.id AS vehicle_id,
                   COALESCE(
                       (
                           SELECT t.id
                           FROM ticket t
                           WHERE t.vehicle_id = v.id
                             AND t.deleted_at IS NULL
                             AND t.status IN ('ACTIVE', 'RENEWING')
                             AND t.effective_to >= CURRENT_TIMESTAMP
                           ORDER BY t.effective_to DESC, t.id DESC
                           LIMIT 1
                       ),
                       (
                           SELECT t.id
                           FROM ticket t
                           WHERE t.vehicle_id = v.id
                             AND t.deleted_at IS NULL
                             AND t.status != 'CANCELLED'
                           ORDER BY t.effective_to DESC, t.id DESC
                           LIMIT 1
                       )
                   ) AS ticket_id
            FROM vehicle v
            WHERE v.deleted_at IS NULL
        ),
        vehicle_ticket_classification AS (
            SELECT rt.vehicle_id,
                   t.id AS ticket_id,
                   t.effective_to,
                   CASE
                       WHEN t.id IS NULL THEN 'none'
                       WHEN t.effective_to < CURRENT_TIMESTAMP THEN 'expired'
                       WHEN t.effective_to <= CURRENT_TIMESTAMP + INTERVAL '7 days' THEN 'expiring_soon'
                       ELSE 'valid'
                   END AS ticket_state
            FROM rep_ticket rt
            LEFT JOIN ticket t ON t.id = rt.ticket_id
        )
        SELECT
            COUNT(v.id) AS total_vehicles,
            COUNT(v.id) FILTER (WHERE EXISTS (
                SELECT 1 FROM vehicle_entry_exit_log l WHERE l.vehicle_id = v.id AND l.exit_time IS NULL
            ) OR vtc.ticket_state IN ('valid', 'expiring_soon')) AS active_vehicles,
            COUNT(v.id) FILTER (WHERE vtc.ticket_state = 'expiring_soon') AS expiring_soon_tickets,
            COUNT(v.id) FILTER (WHERE vtc.ticket_state = 'expired') AS expired_tickets
        FROM vehicle v
        JOIN vehicle_ticket_classification vtc ON vtc.vehicle_id = v.id
        JOIN vehicle_type vt ON v.vehicle_type_id = vt.id
        JOIN customer c ON v.customer_id = c.id
        WHERE v.deleted_at IS NULL {extra_where};
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    return {
        "total_vehicles": row[0],
        "active_vehicles": row[1],
        "expiring_soon_tickets": row[2],
        "expired_tickets": row[3],
    }


def test_vehicle_summary_matches_independent_sql_seed_baseline(employee_client):
    """
    GET /api/v1/vehicles/summary/ đối soát khớp tuyệt đối với kết quả SQL độc lập
    trên dữ liệu seed: {total_vehicles: 30, active_vehicles: 15, expiring_soon_tickets: 0, expired_tickets: 12}.
    """
    expected = _get_independent_sql_kpis()
    assert expected["total_vehicles"] == 30
    assert expected["active_vehicles"] == 15
    assert expected["expiring_soon_tickets"] == 0
    assert expected["expired_tickets"] == 12

    response = employee_client.get(ENDPOINT_URL)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["total_vehicles"] == expected["total_vehicles"]
    assert data["active_vehicles"] == expected["active_vehicles"]
    assert data["expiring_soon_tickets"] == expected["expiring_soon_tickets"]
    assert data["expired_tickets"] == expected["expired_tickets"]


def test_vehicle_summary_filter_by_vehicle_type_ev(employee_client):
    """Lọc KPI theo vehicle_type=EV đối soát với SQL độc lập."""
    expected = _get_independent_sql_kpis("AND vt.code = 'EV'")
    response = employee_client.get(f"{ENDPOINT_URL}?vehicle_type=EV")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["total_vehicles"] == expected["total_vehicles"]
    assert data["active_vehicles"] == expected["active_vehicles"]
    assert data["expiring_soon_tickets"] == expected["expiring_soon_tickets"]
    assert data["expired_tickets"] == expected["expired_tickets"]


def test_vehicle_summary_filter_by_customer(employee_client):
    """Lọc KPI theo customer=KH0001 đối soát với SQL độc lập."""
    expected = _get_independent_sql_kpis(
        "AND (c.code ILIKE '%KH0001%' OR c.full_name ILIKE '%KH0001%')"
    )
    response = employee_client.get(f"{ENDPOINT_URL}?customer=KH0001")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["total_vehicles"] == expected["total_vehicles"]
    assert data["active_vehicles"] == expected["active_vehicles"]
    assert data["expiring_soon_tickets"] == expected["expiring_soon_tickets"]
    assert data["expired_tickets"] == expected["expired_tickets"]


def test_vehicle_summary_dynamic_ticket_expiring_soon(employee_client, auth_manager):
    """
    Khi thêm vé có ngày hết hạn trong vòng 7 ngày (ví dụ: now + 3 ngày),
    chỉ số expiring_soon_tickets phải tăng chính xác từ 0 lên 1.
    """
    initial_res = employee_client.get(ENDPOINT_URL)
    assert initial_res.json()["expiring_soon_tickets"] == 0

    now = timezone.now()
    from apps.parking.models import ParkingSlot

    # Tìm slot không bị trùng thời gian vé
    slot = ParkingSlot.objects.exclude(
        tickets__deleted_at__isnull=True,
        tickets__effective_to__gt=now,
    ).first()
    tt = TicketType.objects.first()
    v = Vehicle.objects.filter(code="XE0030", deleted_at__isnull=True).first()

    Ticket.objects.create(
        code="VE-EXP-01",
        vehicle=v,
        customer=v.customer,
        ticket_type=tt,
        slot=slot,
        status="ACTIVE",
        effective_from=now - timedelta(days=20),
        effective_to=now + timedelta(days=3),
        price=100000,
    )

    updated_res = employee_client.get(ENDPOINT_URL)
    assert updated_res.status_code == status.HTTP_200_OK
    assert updated_res.json()["expiring_soon_tickets"] == 1


def test_vehicle_summary_permissions(
    anonymous_client, customer_client, employee_client, manager_client
):
    """Kiểm tra phân quyền trên endpoint summary."""
    # Anonymous -> 401
    assert (
        anonymous_client.get(ENDPOINT_URL).status_code == status.HTTP_401_UNAUTHORIZED
    )
    # Customer -> 403
    assert customer_client.get(ENDPOINT_URL).status_code == status.HTTP_403_FORBIDDEN
    # Employee -> 200
    assert employee_client.get(ENDPOINT_URL).status_code == status.HTTP_200_OK
    # Manager -> 200
    assert manager_client.get(ENDPOINT_URL).status_code == status.HTTP_200_OK


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_vehicle_summary_disallowed_methods(manager_client, method):
    """Endpoint summary chỉ cho phép GET, cấm các phương thức ghi -> 405."""
    client_method = getattr(manager_client, method)
    assert (
        client_method(ENDPOINT_URL, {}).status_code
        == status.HTTP_405_METHOD_NOT_ALLOWED
    )
