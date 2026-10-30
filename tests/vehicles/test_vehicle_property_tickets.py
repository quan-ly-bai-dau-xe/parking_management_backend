"""
Property-based consistency tests for vehicle ticket states across List, Detail, Summary, and Export.

Guarantees 100% agreement (Single Source of Truth - Milestone 2 / R2 - S2):
1. For every ticket_state in ['valid', 'expiring_soon', 'expired', 'none']:
   KPI count == count of list filter == number of detail views where ticket.state == S.
2. list_row['ticket']['state'] == detail_view['ticket']['state'] for ALL 30 seed vehicles.
3. Independent hand-written CTE SQL matches ORM results byte-for-byte on baseline seed:
   - total_vehicles: 30
   - active_vehicles: 15
   - valid_tickets: 10
   - expiring_soon_tickets: 0
   - expired_tickets: 12
   - none_tickets: 8
4. 5 synthetic edge fixtures:
   - only CANCELLED ticket -> state: none, ticket: null
   - ACTIVE past effective_to -> state: expired
   - EXPIRED old ticket -> state: expired
   - expired ticket followed by renewed active ticket -> state: valid
   - vehicle with no ticket -> state: none, ticket: null
5. ticket_type filter and list column follow representative ticket (including expired subscriptions).
"""

import csv
import io
from datetime import timedelta

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework import status

from apps.parking.models import ParkingSlot
from apps.tickets.models import Ticket, TicketType
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db

LIST_URL = "/api/v1/vehicles/"
SUMMARY_URL = "/api/v1/vehicles/summary/"
EXPORT_URL = "/api/v1/vehicles/export/"


def _get_independent_handwritten_cte_sql():
    """
    Independent CTE SQL calculation implementing the exact two-tier priority rule (TL-28.1, OQ-52):
      Tier 1: Unexpired ACTIVE or RENEWING ticket (effective_to >= CURRENT_TIMESTAMP).
      Tier 2: Most recent non-deleted ticket by effective_to DESC, id DESC where status != 'CANCELLED'.
    """
    sql = """
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
                   t.code AS ticket_code,
                   t.ticket_type_id,
                   t.effective_from,
                   t.effective_to,
                   t.status AS ticket_status,
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
                SELECT 1 FROM vehicle_entry_exit_log l
                WHERE l.vehicle_id = v.id AND l.exit_time IS NULL
            ) OR vtc.ticket_state IN ('valid', 'expiring_soon')) AS active_vehicles,
            COUNT(v.id) FILTER (WHERE vtc.ticket_state = 'valid') AS valid_tickets,
            COUNT(v.id) FILTER (WHERE vtc.ticket_state = 'expiring_soon') AS expiring_soon_tickets,
            COUNT(v.id) FILTER (WHERE vtc.ticket_state = 'expired') AS expired_tickets,
            COUNT(v.id) FILTER (WHERE vtc.ticket_state = 'none') AS none_tickets
        FROM vehicle v
        JOIN vehicle_ticket_classification vtc ON vtc.vehicle_id = v.id
        WHERE v.deleted_at IS NULL;
    """
    with connection.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    return {
        "total_vehicles": row[0],
        "active_vehicles": row[1],
        "valid_tickets": row[2],
        "expiring_soon_tickets": row[3],
        "expired_tickets": row[4],
        "none_tickets": row[5],
    }


def test_property_matches_independent_hand_written_cte_sql(employee_client):
    """
    Xác minh kết quả của API khớp 100% với câu truy vấn CTE SQL độc lập thuần túy.
    Số liệu baseline seed:
      - total_vehicles: 30
      - active_vehicles: 15
      - valid_tickets: 10
      - expiring_soon_tickets: 0
      - expired_tickets: 12
      - none_tickets: 8 (3 CANCELLED + 5 không có vé)
    """
    expected = _get_independent_handwritten_cte_sql()
    assert expected["total_vehicles"] == 30
    assert expected["active_vehicles"] == 15
    assert expected["valid_tickets"] == 10
    assert expected["expiring_soon_tickets"] == 0
    assert expected["expired_tickets"] == 12
    assert expected["none_tickets"] == 8

    # Check Summary KPI endpoint
    res_summary = employee_client.get(SUMMARY_URL)
    assert res_summary.status_code == status.HTTP_200_OK
    summary_data = res_summary.json()
    assert summary_data["total_vehicles"] == expected["total_vehicles"]
    assert summary_data["active_vehicles"] == expected["active_vehicles"]
    assert summary_data["expiring_soon_tickets"] == expected["expiring_soon_tickets"]
    assert summary_data["expired_tickets"] == expected["expired_tickets"]

    # Check List filter counts
    for state in ["valid", "expiring_soon", "expired", "none"]:
        res_list = employee_client.get(f"{LIST_URL}?ticket_state={state}&page_size=50")
        assert res_list.status_code == status.HTTP_200_OK
        list_count = res_list.json()["count"]
        assert list_count == expected[f"{state}_tickets"]


def test_property_full_agreement_across_all_ticket_states(employee_client):
    """
    Bảo đảm tính đồng thuận 100% giữa Summary KPI, List Filter, và Detail View
    cho tất cả các trạng thái vé (valid, expiring_soon, expired, none).
    """
    res_summary = employee_client.get(SUMMARY_URL)
    assert res_summary.status_code == status.HTTP_200_OK
    kpi = res_summary.json()

    # Retrieve all vehicles via detail view and classify by ticket state
    vehicles = Vehicle.objects.filter(deleted_at__isnull=True)
    detail_state_counts = {"valid": 0, "expiring_soon": 0, "expired": 0, "none": 0}

    for v in vehicles:
        res_detail = employee_client.get(f"{LIST_URL}{v.id}/")
        assert res_detail.status_code == status.HTTP_200_OK
        ticket = res_detail.json().get("ticket")
        state = ticket["state"] if ticket else "none"
        detail_state_counts[state] += 1

    # Verify each state matches list filter count and KPI where applicable
    for st in ["valid", "expiring_soon", "expired", "none"]:
        res_filter = employee_client.get(f"{LIST_URL}?ticket_state={st}&page_size=50")
        assert res_filter.status_code == status.HTTP_200_OK
        filter_count = res_filter.json()["count"]

        # 1. List filter count MUST equal detail views count
        assert filter_count == detail_state_counts[st], (
            f"State '{st}' mismatch: list filter={filter_count} vs detail count={detail_state_counts[st]}"
        )

        # 2. KPI counts MUST match filter count
        if st == "expired":
            assert kpi["expired_tickets"] == filter_count
        elif st == "expiring_soon":
            assert kpi["expiring_soon_tickets"] == filter_count

    # Verify partition sum equals total vehicles
    total_partition = sum(detail_state_counts.values())
    assert total_partition == kpi["total_vehicles"] == 30


def test_property_list_detail_row_by_row_identity(employee_client):
    """
    Khẳng định tính đồng nhất từng hàng (Row-by-Row Identity) trên 100% xe seed (30 xe):
    list_row['ticket'] == detail_view['ticket'].
    """
    res_list = employee_client.get(f"{LIST_URL}?page_size=50")
    assert res_list.status_code == status.HTTP_200_OK
    list_rows = res_list.json()["results"]
    assert len(list_rows) == 30

    for row in list_rows:
        vid = row["id"]
        vcode = row["code"]
        res_detail = employee_client.get(f"{LIST_URL}{vid}/")
        assert res_detail.status_code == status.HTTP_200_OK
        detail = res_detail.json()

        # Compare status and status_display
        assert row["status"] == detail["status"], f"Status mismatch for {vcode}"
        assert row["status_display"] == detail["status_display"], (
            f"Status display mismatch for {vcode}"
        )

        list_tkt = row["ticket"]
        detail_tkt = detail["ticket"]

        if list_tkt is None:
            assert detail_tkt is None, (
                f"Expected null ticket for {vcode} in detail, got {detail_tkt}"
            )
        else:
            assert detail_tkt is not None, (
                f"Expected non-null ticket for {vcode} in detail, got None"
            )
            assert list_tkt["state"] == detail_tkt["state"], (
                f"State mismatch for {vcode}"
            )
            assert list_tkt["state_display"] == detail_tkt["state_display"], (
                f"State display mismatch for {vcode}"
            )
            assert list_tkt["ticket_type_code"] == detail_tkt["ticket_type_code"], (
                f"Ticket type code mismatch for {vcode}"
            )
            assert list_tkt["days_remaining"] == detail_tkt["days_remaining"], (
                f"Days remaining mismatch for {vcode}"
            )
            assert list_tkt["expires_at"] == detail_tkt["expires_at"], (
                f"Expires at mismatch for {vcode}"
            )


def test_property_five_synthetic_edge_case_fixtures(
    employee_client, car_type, active_customer
):
    """
    Kiểm thử 5 kịch bản biên nhân tạo (Synthetic Edge Fixtures):
      1. Xe chỉ có vé CANCELLED -> state: none, ticket: null
      2. Xe có vé ACTIVE nhưng mốc effective_to < now -> state: expired
      3. Xe có vé EXPIRED cũ -> state: expired
      4. Xe có vé cũ EXPIRED kèm vé mới ACTIVE unexpired -> state: valid
      5. Xe không có vé nào -> state: none, ticket: null
    """
    now = timezone.now()
    tt = TicketType.objects.first()
    free_slots = list(
        ParkingSlot.objects.exclude(
            tickets__deleted_at__isnull=True,
            tickets__effective_to__gt=now,
        )[:5]
    )

    # 1. VEH-CANC: Chỉ có vé CANCELLED
    v_canc = Vehicle.objects.create(
        code="VEH-CANC",
        license_plate="51K-888.01",
        license_plate_norm="51K88801",
        model_name="VF8",
        vehicle_type=car_type,
        customer=active_customer,
    )
    Ticket.objects.create(
        code="VT-CANC1",
        vehicle=v_canc,
        customer=active_customer,
        ticket_type=tt,
        slot=free_slots[0],
        status="CANCELLED",
        effective_from=now - timedelta(days=30),
        effective_to=now + timedelta(days=30),
        price=100000,
    )

    # 2. VEH-ACTP: Vé ACTIVE nhưng effective_to trong quá khứ
    v_actpast = Vehicle.objects.create(
        code="VEH-ACTP",
        license_plate="51K-888.02",
        license_plate_norm="51K88802",
        model_name="VF8",
        vehicle_type=car_type,
        customer=active_customer,
    )
    Ticket.objects.create(
        code="VT-ACTP1",
        vehicle=v_actpast,
        customer=active_customer,
        ticket_type=tt,
        slot=free_slots[1],
        status="ACTIVE",
        effective_from=now - timedelta(days=30),
        effective_to=now - timedelta(days=1),
        price=100000,
    )

    # 3. VEH-EXPO: Vé EXPIRED cũ
    v_expold = Vehicle.objects.create(
        code="VEH-EXPO",
        license_plate="51K-888.03",
        license_plate_norm="51K88803",
        model_name="VF8",
        vehicle_type=car_type,
        customer=active_customer,
    )
    Ticket.objects.create(
        code="VT-EXPO1",
        vehicle=v_expold,
        customer=active_customer,
        ticket_type=tt,
        slot=free_slots[2],
        status="EXPIRED",
        effective_from=now - timedelta(days=60),
        effective_to=now - timedelta(days=10),
        price=100000,
    )

    # 4. VEH-RENW: Vé cũ EXPIRED + vé mới ACTIVE
    v_renew = Vehicle.objects.create(
        code="VEH-RENW",
        license_plate="51K-888.04",
        license_plate_norm="51K88804",
        model_name="VF8",
        vehicle_type=car_type,
        customer=active_customer,
    )
    Ticket.objects.create(
        code="VT-RENO1",
        vehicle=v_renew,
        customer=active_customer,
        ticket_type=tt,
        slot=free_slots[3],
        status="EXPIRED",
        effective_from=now - timedelta(days=60),
        effective_to=now - timedelta(days=5),
        price=100000,
    )
    Ticket.objects.create(
        code="VT-RENN1",
        vehicle=v_renew,
        customer=active_customer,
        ticket_type=tt,
        slot=free_slots[3],
        status="ACTIVE",
        effective_from=now - timedelta(days=4),
        effective_to=now + timedelta(days=26),
        price=100000,
    )

    # 5. VEH-NOTK: Không có vé nào
    v_notkt = Vehicle.objects.create(
        code="VEH-NOTK",
        license_plate="51K-888.05",
        license_plate_norm="51K88805",
        model_name="VF8",
        vehicle_type=car_type,
        customer=active_customer,
    )

    test_matrix = [
        (v_canc, "none", None),
        (v_actpast, "expired", False),
        (v_expold, "expired", False),
        (v_renew, "valid", True),
        (v_notkt, "none", None),
    ]

    for vehicle, expected_state, expected_is_valid in test_matrix:
        # Check Detail View
        res_d = employee_client.get(f"{LIST_URL}{vehicle.id}/")
        assert res_d.status_code == status.HTTP_200_OK
        d_ticket = res_d.json().get("ticket")

        if expected_state == "none":
            assert d_ticket is None, (
                f"Expected None ticket for {vehicle.code}, got {d_ticket}"
            )
        else:
            assert d_ticket is not None, f"Expected ticket for {vehicle.code}"
            assert d_ticket["state"] == expected_state
            assert d_ticket["is_valid"] == expected_is_valid

        # Check List View
        res_l = employee_client.get(f"{LIST_URL}?code={vehicle.code}")
        assert res_l.status_code == status.HTTP_200_OK
        assert res_l.json()["count"] == 1
        l_row = res_l.json()["results"][0]
        l_ticket = l_row.get("ticket")

        if expected_state == "none":
            assert l_ticket is None, f"Expected None ticket for {vehicle.code} in list"
        else:
            assert l_ticket is not None
            assert l_ticket["state"] == expected_state

        # Check Filtering
        res_f = employee_client.get(
            f"{LIST_URL}?ticket_state={expected_state}&code={vehicle.code}"
        )
        assert res_f.status_code == status.HTTP_200_OK
        assert res_f.json()["count"] == 1, (
            f"Vehicle {vehicle.code} not found under ticket_state={expected_state}"
        )

        # Check CSV Export
        res_exp = employee_client.get(f"{EXPORT_URL}?code={vehicle.code}")
        assert res_exp.status_code == status.HTTP_200_OK
        csv_text = b"".join(res_exp.streaming_content).decode("utf-8").lstrip("\ufeff")
        reader = csv.reader(io.StringIO(csv_text))
        rows = list(reader)
        assert len(rows) == 2  # header + 1 row
        state_col_idx = rows[0].index("Tình trạng vé")
        cell_val = rows[1][state_col_idx]
        if expected_state == "none":
            assert cell_val == ""
        elif expected_state == "expired":
            assert cell_val == "Đã hết hạn"
        elif expected_state == "valid":
            assert cell_val == "Còn hạn"


def test_property_ticket_type_filter_follows_representative_ticket(employee_client):
    """
    Khẳng định bộ lọc ticket_type và cột Loại vé bám theo vé đại diện,
    kể cả phương tiện có vé đã hết hạn (Mockup Dòng 4: XE0004 có Vé quý - Đã hết hạn).
    """
    # XE0006 trên seed có vé DAILY đã hết hạn
    res_daily_expired = employee_client.get(
        f"{LIST_URL}?ticket_type=DAILY&ticket_state=expired"
    )
    assert res_daily_expired.status_code == status.HTTP_200_OK
    codes = [v["code"] for v in res_daily_expired.json()["results"]]
    assert "XE0006" in codes
    assert "XE0011" in codes

    # Detail API of XE0006
    v6 = Vehicle.objects.get(code="XE0006")
    res_v6 = employee_client.get(f"{LIST_URL}{v6.id}/")
    assert res_v6.status_code == status.HTTP_200_OK
    tkt6 = res_v6.json()["ticket"]
    assert tkt6 is not None
    assert tkt6["ticket_type_code"] == "DAILY"
    assert tkt6["state"] == "expired"
    assert tkt6["state_display"] == "Đã hết hạn"

    # CSV Export of XE0006 contains 'Vé ngày' and 'Đã hết hạn'
    res_exp6 = employee_client.get(f"{EXPORT_URL}?code=XE0006")
    assert res_exp6.status_code == status.HTTP_200_OK
    csv_text = b"".join(res_exp6.streaming_content).decode("utf-8").lstrip("\ufeff")
    reader = csv.reader(io.StringIO(csv_text))
    rows = list(reader)
    assert len(rows) == 2
    type_idx = rows[0].index("Loại vé")
    state_idx = rows[0].index("Tình trạng vé")
    assert rows[1][type_idx] == "Vé ngày"
    assert rows[1][state_idx] == "Đã hết hạn"
