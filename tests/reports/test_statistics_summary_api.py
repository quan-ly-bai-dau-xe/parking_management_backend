"""
Integration tests for Statistics Summary API (SRS 4.7.1: GET /api/v1/reports/statistics/summary/).
Verifies:
- RBAC: 401 anonymous, 403 CUSTOMER, 403 EMPLOYEE, 200 MANAGER.
- Query param validation: PROP-4.7.1-P01 on invalid date format or start_date > end_date.
- Deterministic revenue breakdown across 5 ticket types (HOURLY, DAILY, MONTHLY, QUARTERLY, YEARLY)
  and 3 payment methods (CASH, VIETQR, WALLET), including package overage session payments -> HOURLY.
- Non-Revenue wallet top-up isolation (TOPUP_CASH, TOPUP_VIETQR do NOT inflate total_revenue).
- Exclusion of UNPAID, CANCELLED, REFUNDED, and TL-27 soft-deleted entities.
- Asia/Ho_Chi_Minh (UTC+7) cross-day boundary accuracy and exit-in-period counting.
- O(1) query count bound (no N+1 queries).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.messages import get_message
from apps.customers.models import Customer
from apps.parking.models import ParkingGate, ParkingSlot, VehicleEntryExitLog
from apps.tickets.models import Payment, Ticket, TicketRenewal, TicketType
from apps.vehicles.models import Vehicle, VehicleType
from apps.wallet.models import Wallet, WalletTransaction

pytestmark = pytest.mark.django_db

HCM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
SUMMARY_URL = "/api/v1/reports/statistics/summary/"


@pytest.fixture
def manager_user():
    acc, _ = Account.objects.get_or_create(
        email="mgr_stats_471@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return acc


@pytest.fixture
def employee_user():
    acc, _ = Account.objects.get_or_create(
        email="emp_stats_471@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return acc


@pytest.fixture
def customer_user():
    acc, _ = Account.objects.get_or_create(
        email="cust_stats_471@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return acc


def _create_customer_and_vehicle(prefix: str = "ST") -> tuple[Customer, Vehicle]:
    suffix = uuid.uuid4().hex[:6].upper()
    vtype = VehicleType.objects.filter(deleted_at__isnull=True).first()
    assert vtype is not None

    customer = Customer.objects.create(
        code=f"{prefix}{suffix[:6]}",
        full_name=f"Khach Hang {suffix}",
        identity_card_number=f"079{uuid.uuid4().int % 10**9:09d}",
        phone=f"09{uuid.uuid4().int % 10**8:08d}",
        email=f"cust_{suffix.lower()}@example.com",
        status="ACTIVE",
    )
    vehicle = Vehicle.objects.create(
        code=f"VH{suffix[:6]}",
        customer=customer,
        vehicle_type=vtype,
        license_plate=f"51A-{uuid.uuid4().int % 90000 + 10000}",
        model_name="Camry",
        brand="Toyota",
        color="Trang",
    )
    return customer, vehicle


def _get_available_slot() -> ParkingSlot:
    slot = ParkingSlot.objects.filter(
        deleted_at__isnull=True,
        status="AVAILABLE",
    ).first()
    assert slot is not None
    return slot


def _create_closed_session(
    *,
    entry_time: datetime,
    exit_time: datetime,
    fee_amount: Decimal,
    vehicle: Vehicle | None = None,
    slot: ParkingSlot | None = None,
    ticket: Ticket | None = None,
) -> VehicleEntryExitLog:
    gate_in = ParkingGate.objects.filter(
        direction="IN", deleted_at__isnull=True
    ).first()
    gate_out = ParkingGate.objects.filter(
        direction="OUT", deleted_at__isnull=True
    ).first()
    suffix = uuid.uuid4().hex[:8].upper()
    return VehicleEntryExitLog.objects.create(
        session_code=f"#PK-ST-{suffix}",
        vehicle=vehicle,
        slot=slot,
        ticket=ticket,
        entry_gate=gate_in,
        exit_gate=gate_out,
        license_plate=vehicle.license_plate if vehicle else f"59B-{suffix[:5]}",
        recognition_source="AI",
        review_status="AUTO",
        fee_amount=fee_amount,
        entry_time=entry_time,
        exit_time=exit_time,
    )


def test_statistics_summary_rbac_matrix(manager_user, employee_user, customer_user):
    """Chỉ MANAGER được phép truy cập (200); Anonymous -> 401; EMPLOYEE/CUSTOMER -> 403."""
    anon_client = APIClient()
    assert anon_client.get(SUMMARY_URL).status_code == status.HTTP_401_UNAUTHORIZED

    cust_client = APIClient()
    cust_client.force_authenticate(user=customer_user)
    cust_resp = cust_client.get(SUMMARY_URL)
    assert cust_resp.status_code == status.HTTP_403_FORBIDDEN

    emp_client = APIClient()
    emp_client.force_authenticate(user=employee_user)
    emp_resp = emp_client.get(SUMMARY_URL)
    assert emp_resp.status_code == status.HTTP_403_FORBIDDEN

    mgr_client = APIClient()
    mgr_client.force_authenticate(user=manager_user)
    mgr_resp = mgr_client.get(SUMMARY_URL)
    assert mgr_resp.status_code == status.HTTP_200_OK


def test_statistics_summary_invalid_date_filters_return_400_prop_4_7_1_p01(
    manager_user,
):
    """Sai định dạng ngày hoặc start_date > end_date -> 400 với PROP-4.7.1-P01."""
    client = APIClient()
    client.force_authenticate(user=manager_user)
    expected_msg = get_message("PROP-4.7.1-P01")

    bad_queries = [
        "?start_date=2026-11-20&end_date=2026-11-01",
        "?start_date=not-a-date&end_date=2026-11-10",
        "?start_date=2026-99-99&end_date=2026-11-10",
        "?start_date=2026-11-01&end_date=18-11-2026",
    ]
    for query in bad_queries:
        resp = client.get(f"{SUMMARY_URL}{query}")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        payload = resp.json()
        assert payload["code"] == "PROP-4.7.1-P01"
        assert payload["message"] == expected_msg


def test_statistics_summary_empty_period_returns_zero_metrics(manager_user):
    """Khoảng thời gian tương lai không có giao dịch vẫn trả 200 với giá trị 0.00 hợp lệ."""
    client = APIClient()
    client.force_authenticate(user=manager_user)

    resp = client.get(f"{SUMMARY_URL}?start_date=2035-01-01&end_date=2035-01-31")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["period"] == {"start_date": "2035-01-01", "end_date": "2035-01-31"}
    assert data["total_revenue"] == "0.00"
    assert data["revenue_by_ticket_type"] == {
        "HOURLY": "0.00",
        "DAILY": "0.00",
        "MONTHLY": "0.00",
        "QUARTERLY": "0.00",
        "YEARLY": "0.00",
    }
    assert data["revenue_by_payment_method"] == {
        "CASH": "0.00",
        "VIETQR": "0.00",
        "WALLET": "0.00",
    }
    assert data["non_revenue"]["wallet_topup_total"] == "0.00"
    assert data["traffic"]["total_entries"] == 0
    assert data["traffic"]["total_exits"] == 0
    assert data["traffic"]["currently_parked"] >= 0
    assert data["occupancy"]["total_slots"] >= 0
    assert 0.0 <= data["occupancy"]["occupancy_rate"] <= 100.0

    # Truyền chỉ end_date -> start_date tự lấy ngày 1 của tháng chứa end_date
    resp_end_only = client.get(f"{SUMMARY_URL}?end_date=2035-02-15")
    assert resp_end_only.status_code == status.HTTP_200_OK
    assert resp_end_only.json()["period"] == {
        "start_date": "2035-02-01",
        "end_date": "2035-02-15",
    }

    # Truyền chỉ start_date trong quá khứ -> end_date tự lấy hôm nay (Asia/Ho_Chi_Minh)
    resp_start_only = client.get(f"{SUMMARY_URL}?start_date=2026-01-01")
    assert resp_start_only.status_code == status.HTTP_200_OK
    assert resp_start_only.json()["period"]["start_date"] == "2026-01-01"


def test_statistics_summary_deterministic_revenue_and_non_revenue_isolation(
    manager_user,
):
    """
    Kiểm tra chính xác từng đồng cho:
    - 5 loại vé (HOURLY gồm cả cước quá hạn vé gói, DAILY, MONTHLY, QUARTERLY, YEARLY)
    - 3 phương thức thanh toán (CASH, VIETQR, WALLET)
    - Tiền nạp ví (TOPUP_CASH, TOPUP_VIETQR) là Non-Revenue, không cộng vào total_revenue
    - Không tính DEBIT/REFUND/ADJUSTMENT ví vào wallet_topup_total
    """
    t_mid = datetime(2027, 3, 15, 10, 0, tzinfo=HCM_TZ)
    slot = _get_available_slot()

    ticket_types = {
        tt.code: tt
        for tt in TicketType.objects.filter(
            code__in=["DAILY", "MONTHLY", "QUARTERLY", "YEARLY"],
            deleted_at__isnull=True,
        )
    }
    assert set(ticket_types.keys()) == {"DAILY", "MONTHLY", "QUARTERLY", "YEARLY"}

    # Tạo khách hàng & phương tiện tách biệt
    cust1, veh1 = _create_customer_and_vehicle("A")
    cust2, veh2 = _create_customer_and_vehicle("B")
    cust3, veh3 = _create_customer_and_vehicle("C")
    cust4, veh4 = _create_customer_and_vehicle("D")

    # 1. Tạo các vé & chứng từ thanh toán tương ứng
    t_daily = Ticket.objects.create(
        code=f"TD{uuid.uuid4().hex[:6].upper()}",
        vehicle=veh1,
        customer=cust1,
        slot=slot,
        ticket_type=ticket_types["DAILY"],
        price=Decimal("50000.00"),
        effective_from=t_mid,
        effective_to=t_mid + timedelta(days=1),
        status="EXPIRED",
    )
    Payment.objects.create(
        code=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        amount=Decimal("50000.00"),
        method="CASH",
        status="PAID",
        paid_at=t_mid,
        ticket=t_daily,
    )

    t_monthly = Ticket.objects.create(
        code=f"TM{uuid.uuid4().hex[:6].upper()}",
        vehicle=veh2,
        customer=cust2,
        slot=slot,
        ticket_type=ticket_types["MONTHLY"],
        price=Decimal("500000.00"),
        effective_from=t_mid,
        effective_to=t_mid + timedelta(days=30),
        status="EXPIRED",
    )
    Payment.objects.create(
        code=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        amount=Decimal("500000.00"),
        method="WALLET",
        status="PAID",
        paid_at=t_mid + timedelta(minutes=5),
        ticket=t_monthly,
    )

    # Gia hạn vé tháng
    renewal_monthly = TicketRenewal.objects.create(
        ticket=t_monthly,
        old_slot=slot,
        new_slot=slot,
        old_ticket_type=ticket_types["MONTHLY"],
        new_ticket_type=ticket_types["MONTHLY"],
        old_price=Decimal("500000.00"),
        new_price=Decimal("500000.00"),
        old_effective_to=t_mid + timedelta(days=30),
        new_effective_to=t_mid + timedelta(days=60),
        additional_price=Decimal("500000.00"),
        created_at=t_mid + timedelta(minutes=10),
    )
    Payment.objects.create(
        code=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        amount=Decimal("500000.00"),
        method="WALLET",
        status="PAID",
        paid_at=t_mid + timedelta(minutes=10),
        renewal=renewal_monthly,
    )

    t_quarterly = Ticket.objects.create(
        code=f"TQ{uuid.uuid4().hex[:6].upper()}",
        vehicle=veh3,
        customer=cust3,
        slot=slot,
        ticket_type=ticket_types["QUARTERLY"],
        price=Decimal("1200000.00"),
        effective_from=t_mid,
        effective_to=t_mid + timedelta(days=90),
        status="EXPIRED",
    )
    Payment.objects.create(
        code=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        amount=Decimal("1200000.00"),
        method="VIETQR",
        status="PAID",
        paid_at=t_mid + timedelta(minutes=15),
        ticket=t_quarterly,
    )

    t_yearly = Ticket.objects.create(
        code=f"TY{uuid.uuid4().hex[:6].upper()}",
        vehicle=veh4,
        customer=cust4,
        slot=slot,
        ticket_type=ticket_types["YEARLY"],
        price=Decimal("4800000.00"),
        effective_from=t_mid,
        effective_to=t_mid + timedelta(days=365),
        status="EXPIRED",
    )
    Payment.objects.create(
        code=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        amount=Decimal("4800000.00"),
        method="WALLET",
        status="PAID",
        paid_at=t_mid + timedelta(minutes=20),
        ticket=t_yearly,
    )

    # 2. Phiên gửi xe theo giờ (walk-in CASH, WALLET, và cước quá hạn vé gói VIETQR -> HOURLY)
    sess_cash = _create_closed_session(
        entry_time=t_mid,
        exit_time=t_mid + timedelta(hours=2),
        fee_amount=Decimal("30000.00"),
    )
    Payment.objects.create(
        code=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        amount=Decimal("30000.00"),
        method="CASH",
        status="PAID",
        paid_at=t_mid + timedelta(hours=2),
        session=sess_cash,
    )

    sess_wallet = _create_closed_session(
        entry_time=t_mid,
        exit_time=t_mid + timedelta(hours=1),
        fee_amount=Decimal("20000.00"),
        vehicle=veh1,
    )
    Payment.objects.create(
        code=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        amount=Decimal("20000.00"),
        method="WALLET",
        status="PAID",
        paid_at=t_mid + timedelta(hours=1),
        session=sess_wallet,
    )

    sess_overage = _create_closed_session(
        entry_time=t_mid,
        exit_time=t_mid + timedelta(hours=3),
        fee_amount=Decimal("10000.00"),
        vehicle=veh2,
        ticket=t_monthly,
    )
    Payment.objects.create(
        code=f"PAY-{uuid.uuid4().hex[:8].upper()}",
        amount=Decimal("10000.00"),
        method="VIETQR",
        status="PAID",
        paid_at=t_mid + timedelta(hours=3),
        session=sess_overage,
    )

    # 3. Giao dịch ví (Non-Revenue TOPUP_CASH 300k + TOPUP_VIETQR 700k = 1,000,000đ)
    wallet = Wallet.objects.create(
        customer=cust1,
        balance=Decimal("1030000.00"),
        currency="VND",
        status="ACTIVE",
    )
    WalletTransaction.objects.create(
        wallet=wallet,
        amount=Decimal("300000.00"),
        balance_after=Decimal("300000.00"),
        transaction_type="CREDIT",
        kind="TOPUP_CASH",
        idempotency_key=f"topup-cash-{uuid.uuid4().hex}",
        created_at=t_mid,
    )
    WalletTransaction.objects.create(
        wallet=wallet,
        amount=Decimal("700000.00"),
        balance_after=Decimal("1000000.00"),
        transaction_type="CREDIT",
        kind="TOPUP_VIETQR",
        idempotency_key=f"topup-qr-{uuid.uuid4().hex}",
        created_at=t_mid + timedelta(minutes=2),
    )
    # Các loại giao dịch ví khác KHÔNG được tính vào wallet_topup_total
    WalletTransaction.objects.create(
        wallet=wallet,
        amount=Decimal("-20000.00"),
        balance_after=Decimal("980000.00"),
        transaction_type="DEBIT",
        kind="PARKING_FEE",
        idempotency_key=f"debit-{uuid.uuid4().hex}",
        created_at=t_mid + timedelta(minutes=3),
    )
    WalletTransaction.objects.create(
        wallet=wallet,
        amount=Decimal("50000.00"),
        balance_after=Decimal("1030000.00"),
        transaction_type="CREDIT",
        kind="REFUND",
        idempotency_key=f"refund-{uuid.uuid4().hex}",
        created_at=t_mid + timedelta(minutes=4),
    )

    client = APIClient()
    client.force_authenticate(user=manager_user)
    resp = client.get(f"{SUMMARY_URL}?start_date=2027-03-01&end_date=2027-03-31")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    # Kiểm tra từng con số chính xác
    assert data["total_revenue"] == "7110000.00"
    assert data["revenue_by_ticket_type"] == {
        "HOURLY": "60000.00",
        "DAILY": "50000.00",
        "MONTHLY": "1000000.00",
        "QUARTERLY": "1200000.00",
        "YEARLY": "4800000.00",
    }
    assert data["revenue_by_payment_method"] == {
        "CASH": "80000.00",
        "VIETQR": "1210000.00",
        "WALLET": "5820000.00",
    }

    # Tổng 5 loại vé == Tổng 3 phương thức == total_revenue
    sum_types = sum(Decimal(v) for v in data["revenue_by_ticket_type"].values())
    sum_methods = sum(Decimal(v) for v in data["revenue_by_payment_method"].values())
    assert sum_types == Decimal(data["total_revenue"])
    assert sum_methods == Decimal(data["total_revenue"])

    # Tiền nạp ví tách biệt hoàn toàn (Non-Revenue)
    assert data["non_revenue"]["wallet_topup_total"] == "1000000.00"
    assert data["non_revenue"]["topup_cash_total"] == "300000.00"
    assert data["non_revenue"]["topup_vietqr_total"] == "700000.00"
    assert data["non_revenue"]["topup_vnpay_total"] == "0.00"
    assert "không tính vào doanh thu" in data["non_revenue"]["description"].lower()

    # Lưu lượng xe trong kỳ
    assert data["traffic"]["total_entries"] == 3
    assert data["traffic"]["total_exits"] == 3


def test_statistics_summary_excludes_invalid_statuses_and_tl27_soft_deletes(
    manager_user,
):
    """
    Loại trừ:
    - Payment có status UNPAID, CANCELLED, REFUNDED
    - Payment có deleted_at IS NOT NULL
    - Payment / WalletTransaction / VehicleEntryExitLog gắn với thực thể bị soft-delete (TL-27)
    """
    t_mid = datetime(2027, 5, 10, 12, 0, tzinfo=HCM_TZ)
    slot = _get_available_slot()
    daily_type = TicketType.objects.get(code="DAILY", deleted_at__isnull=True)
    cust_ok, veh_ok = _create_customer_and_vehicle("OK")
    cust_del, veh_del = _create_customer_and_vehicle("DL")

    # 1. Giao dịch hợp lệ duy nhất: 50,000 CASH
    t_ok = Ticket.objects.create(
        code=f"OK{uuid.uuid4().hex[:6].upper()}",
        vehicle=veh_ok,
        customer=cust_ok,
        slot=slot,
        ticket_type=daily_type,
        price=Decimal("50000.00"),
        effective_from=t_mid,
        effective_to=t_mid + timedelta(days=1),
        status="EXPIRED",
    )
    Payment.objects.create(
        code=f"PAY-OK-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal("50000.00"),
        method="CASH",
        status="PAID",
        paid_at=t_mid,
        ticket=t_ok,
    )

    # 2. Các trạng thái không được tính doanh thu
    for bad_status in ("UNPAID", "CANCELLED", "REFUNDED"):
        sess = _create_closed_session(
            entry_time=t_mid,
            exit_time=t_mid + timedelta(hours=1),
            fee_amount=Decimal("99000.00"),
        )
        Payment.objects.create(
            code=f"PAY-{bad_status[:3]}-{uuid.uuid4().hex[:6].upper()}",
            amount=Decimal("99000.00"),
            method="VIETQR",
            status=bad_status,
            paid_at=t_mid if bad_status == "REFUNDED" else None,
            created_at=t_mid,
            session=sess,
        )

    # 3. Payment UNPAID bị soft-delete trực tiếp
    sess_del_pay = _create_closed_session(
        entry_time=t_mid,
        exit_time=t_mid + timedelta(hours=1),
        fee_amount=Decimal("77000.00"),
    )
    Payment.objects.create(
        code=f"PAY-DEL-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal("77000.00"),
        method="CASH",
        status="UNPAID",
        deleted_at=timezone.now(),
        created_at=t_mid,
        session=sess_del_pay,
    )

    # 4. Payment PAID gắn với vehicle đã soft-delete (TL-27)
    sess_del_veh = _create_closed_session(
        entry_time=t_mid,
        exit_time=t_mid + timedelta(hours=1),
        fee_amount=Decimal("40000.00"),
        vehicle=veh_del,
    )
    Payment.objects.create(
        code=f"PAY-TL27-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal("40000.00"),
        method="CASH",
        status="PAID",
        paid_at=t_mid,
        session=sess_del_veh,
    )

    # Soft-delete veh_del và wallet của cust_del
    w_ok = Wallet.objects.create(
        customer=cust_ok,
        balance=Decimal("100000.00"),
        currency="VND",
        status="ACTIVE",
    )
    WalletTransaction.objects.create(
        wallet=w_ok,
        amount=Decimal("100000.00"),
        balance_after=Decimal("100000.00"),
        transaction_type="CREDIT",
        kind="TOPUP_CASH",
        idempotency_key=f"wok-{uuid.uuid4().hex}",
        created_at=t_mid,
    )
    w_del = Wallet.objects.create(
        customer=cust_del,
        balance=Decimal("0.00"),
        currency="VND",
        status="CLOSED",
        deleted_at=timezone.now(),
    )
    WalletTransaction.objects.create(
        wallet=w_del,
        amount=Decimal("888000.00"),
        balance_after=Decimal("888000.00"),
        transaction_type="CREDIT",
        kind="TOPUP_VIETQR",
        idempotency_key=f"wdel-{uuid.uuid4().hex}",
        created_at=t_mid,
    )

    Vehicle.all_objects.filter(pk=veh_del.pk).update(deleted_at=timezone.now())

    client = APIClient()
    client.force_authenticate(user=manager_user)
    resp = client.get(f"{SUMMARY_URL}?start_date=2027-05-10&end_date=2027-05-10")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    # Chỉ giữ lại đúng 50,000đ hợp lệ; loại veh_del khỏi cả revenue và traffic
    assert data["total_revenue"] == "50000.00"
    assert data["non_revenue"]["wallet_topup_total"] == "100000.00"
    # 4 phiên hợp lệ (3 bad_status + 1 sess_del_pay), loại sess_del_veh (TL-27)
    assert data["traffic"]["total_entries"] == 4
    assert data["traffic"]["total_exits"] == 4


def test_statistics_summary_asia_ho_chi_minh_timezone_boundaries(manager_user):
    """
    Kiểm tra biên ngày theo múi giờ Asia/Ho_Chi_Minh (UTC+7):
    - 2027-06-10 23:30:00+07:00 (= 16:30 UTC) thuộc ngày 2027-06-10
    - 2027-06-11 00:15:00+07:00 (= 2027-06-10 17:15 UTC) thuộc ngày 2027-06-11
    - Xe vào ngày 2027-06-10 và ra ngày 2027-06-11: ngày 2027-06-11 vẫn đếm total_exits = 1
    """
    dt_day1_late = datetime(2027, 6, 10, 23, 30, tzinfo=HCM_TZ)
    dt_day2_early = datetime(2027, 6, 11, 0, 15, tzinfo=HCM_TZ)

    sess_cross = _create_closed_session(
        entry_time=dt_day1_late,
        exit_time=dt_day2_early,
        fee_amount=Decimal("25000.00"),
    )
    Payment.objects.create(
        code=f"PAY-D2-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal("25000.00"),
        method="VIETQR",
        status="PAID",
        paid_at=dt_day2_early,
        session=sess_cross,
    )

    sess_day1 = _create_closed_session(
        entry_time=dt_day1_late - timedelta(hours=1),
        exit_time=dt_day1_late,
        fee_amount=Decimal("15000.00"),
    )
    Payment.objects.create(
        code=f"PAY-D1-{uuid.uuid4().hex[:6].upper()}",
        amount=Decimal("15000.00"),
        method="CASH",
        status="PAID",
        paid_at=dt_day1_late,
        session=sess_day1,
    )

    client = APIClient()
    client.force_authenticate(user=manager_user)

    resp_d1 = client.get(f"{SUMMARY_URL}?start_date=2027-06-10&end_date=2027-06-10")
    assert resp_d1.status_code == status.HTTP_200_OK
    d1 = resp_d1.json()
    assert d1["total_revenue"] == "15000.00"
    assert d1["traffic"]["total_entries"] == 2
    assert d1["traffic"]["total_exits"] == 1

    resp_d2 = client.get(f"{SUMMARY_URL}?start_date=2027-06-11&end_date=2027-06-11")
    assert resp_d2.status_code == status.HTTP_200_OK
    d2 = resp_d2.json()
    assert d2["total_revenue"] == "25000.00"
    assert d2["traffic"]["total_entries"] == 0
    assert d2["traffic"]["total_exits"] == 1


def test_statistics_summary_query_count_is_o1(
    manager_user, django_assert_max_num_queries
):
    """Đảm bảo số lượng truy vấn SQL là hằng số O(1) (<= 10 queries), không N+1."""
    t_mid = datetime(2027, 7, 15, 10, 0, tzinfo=HCM_TZ)
    for i in range(15):
        sess = _create_closed_session(
            entry_time=t_mid + timedelta(minutes=i),
            exit_time=t_mid + timedelta(minutes=i + 30),
            fee_amount=Decimal("10000.00"),
        )
        Payment.objects.create(
            code=f"PAY-O1-{i}-{uuid.uuid4().hex[:5].upper()}",
            amount=Decimal("10000.00"),
            method="CASH" if i % 2 == 0 else "VIETQR",
            status="PAID",
            paid_at=t_mid + timedelta(minutes=i + 30),
            session=sess,
        )

    client = APIClient()
    client.force_authenticate(user=manager_user)
    with django_assert_max_num_queries(10):
        resp = client.get(f"{SUMMARY_URL}?start_date=2027-07-01&end_date=2027-07-31")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["total_revenue"] == "150000.00"


def test_statistics_summary_large_15_plus_digit_amounts_return_200(manager_user):
    """
    Tổng hợp số tiền lớn (>= 15 chữ số, >= 1,000,000,000,000.00 VND) từ cả Payment
    và WalletTransaction phải serialize chính xác và trả về HTTP 200 (không 500 InvalidOperation).
    """
    t_mid = datetime(2028, 4, 15, 10, 0, tzinfo=HCM_TZ)
    cust_a, _ = _create_customer_and_vehicle("LA")
    cust_b, _ = _create_customer_and_vehicle("LB")
    wallet_a = Wallet.objects.create(
        customer=cust_a,
        balance=Decimal("999999999999.99"),
        currency="VND",
        status="ACTIVE",
    )
    wallet_b = Wallet.objects.create(
        customer=cust_b,
        balance=Decimal("999999999999.99"),
        currency="VND",
        status="ACTIVE",
    )

    # 2 giao dịch nạp ví 999,999,999,999.99 -> tổng 1,999,999,999,999.98 (15 chữ số)
    WalletTransaction.objects.create(
        wallet=wallet_a,
        amount=Decimal("999999999999.99"),
        balance_after=Decimal("999999999999.99"),
        transaction_type="CREDIT",
        kind="TOPUP_VIETQR",
        idempotency_key=f"large-qr-1-{uuid.uuid4().hex}",
        created_at=t_mid,
    )
    WalletTransaction.objects.create(
        wallet=wallet_b,
        amount=Decimal("999999999999.99"),
        balance_after=Decimal("999999999999.99"),
        transaction_type="CREDIT",
        kind="TOPUP_VIETQR",
        idempotency_key=f"large-qr-2-{uuid.uuid4().hex}",
        created_at=t_mid + timedelta(minutes=1),
    )

    # 105 giao dịch Payment 9,999,999,999.99 -> tổng 1,049,999,999,998.95 (15 chữ số)
    gate_in = ParkingGate.objects.filter(
        direction="IN", deleted_at__isnull=True
    ).first()
    gate_out = ParkingGate.objects.filter(
        direction="OUT", deleted_at__isnull=True
    ).first()
    batch_tag = uuid.uuid4().hex[:6].upper()
    sessions = VehicleEntryExitLog.objects.bulk_create(
        [
            VehicleEntryExitLog(
                session_code=f"#PK-LG-{batch_tag}-{i:03d}",
                entry_gate=gate_in,
                exit_gate=gate_out,
                license_plate=f"51L-{10000 + i}",
                recognition_source="AI",
                review_status="AUTO",
                fee_amount=Decimal("9999999999.99"),
                entry_time=t_mid,
                exit_time=t_mid + timedelta(minutes=15),
            )
            for i in range(105)
        ]
    )
    Payment.objects.bulk_create(
        [
            Payment(
                code=f"PAY-LG-{batch_tag}-{i:03d}",
                amount=Decimal("9999999999.99"),
                method="VIETQR",
                status="PAID",
                paid_at=t_mid + timedelta(minutes=15),
                session=sess,
            )
            for i, sess in enumerate(sessions)
        ]
    )

    client = APIClient()
    client.force_authenticate(user=manager_user)
    resp = client.get(f"{SUMMARY_URL}?start_date=2028-04-01&end_date=2028-04-30")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["total_revenue"] == "1049999999998.95"
    assert data["revenue_by_ticket_type"]["HOURLY"] == "1049999999998.95"
    assert data["revenue_by_payment_method"]["VIETQR"] == "1049999999998.95"
    assert data["non_revenue"]["wallet_topup_total"] == "1999999999999.98"
    assert data["non_revenue"]["topup_vietqr_total"] == "1999999999999.98"


def test_statistics_summary_end_date_max_9999_12_31_no_overflow(manager_user):
    """Truyền end_date=9999-12-31 (date.max) không gây OverflowError HTTP 500."""
    client = APIClient()
    client.force_authenticate(user=manager_user)
    resp = client.get(f"{SUMMARY_URL}?start_date=2026-01-01&end_date=9999-12-31")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["period"] == {
        "start_date": "2026-01-01",
        "end_date": "9999-12-31",
    }


def test_statistics_summary_separates_cash_vietqr_and_vnpay_topups(manager_user):
    """Tách biệt rạch ròi non_revenue theo 3 kênh: TOPUP_CASH, TOPUP_VIETQR, TOPUP_VNPAY."""
    t_mid = datetime(2028, 6, 15, 10, 0, tzinfo=HCM_TZ)
    cust, _ = _create_customer_and_vehicle("VP")
    wallet = Wallet.objects.create(
        customer=cust,
        balance=Decimal("950000.00"),
        currency="VND",
        status="ACTIVE",
    )
    WalletTransaction.objects.create(
        wallet=wallet,
        amount=Decimal("150000.00"),
        balance_after=Decimal("150000.00"),
        transaction_type="CREDIT",
        kind="TOPUP_CASH",
        idempotency_key=f"vp-cash-{uuid.uuid4().hex}",
        created_at=t_mid,
    )
    WalletTransaction.objects.create(
        wallet=wallet,
        amount=Decimal("250000.00"),
        balance_after=Decimal("400000.00"),
        transaction_type="CREDIT",
        kind="TOPUP_VIETQR",
        idempotency_key=f"vp-qr-{uuid.uuid4().hex}",
        created_at=t_mid + timedelta(minutes=1),
    )
    WalletTransaction.objects.create(
        wallet=wallet,
        amount=Decimal("600000.00"),
        balance_after=Decimal("1000000.00"),
        transaction_type="CREDIT",
        kind="TOPUP_VNPAY",
        idempotency_key=f"vp-vnpay-{uuid.uuid4().hex}",
        reference_type="VNPAY_TXN",
        created_at=t_mid + timedelta(minutes=2),
    )
    WalletTransaction.objects.create(
        wallet=wallet,
        amount=Decimal("-50000.00"),
        balance_after=Decimal("950000.00"),
        transaction_type="DEBIT",
        kind="PARKING_FEE",
        idempotency_key=f"vp-debit-{uuid.uuid4().hex}",
        created_at=t_mid + timedelta(minutes=3),
    )

    client = APIClient()
    client.force_authenticate(user=manager_user)
    resp = client.get(f"{SUMMARY_URL}?start_date=2028-06-01&end_date=2028-06-30")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["total_revenue"] == "0.00"
    assert data["non_revenue"]["topup_cash_total"] == "150000.00"
    assert data["non_revenue"]["topup_vietqr_total"] == "250000.00"
    assert data["non_revenue"]["topup_vnpay_total"] == "600000.00"
    assert data["non_revenue"]["wallet_topup_total"] == "1000000.00"
