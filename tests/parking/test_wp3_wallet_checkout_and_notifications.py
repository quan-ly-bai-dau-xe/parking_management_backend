"""
WP3 (K3 / D3): Full-Flow Integration Tests for Wallet Check-Out & Notifications (Cases 1–5).

Covers:
- Case 1: Sufficient wallet -> worker auto check-out (VALID_WALLET_PAID), exact debit,
  1 WALLET PAID Payment, 1 PARKING_FEE ledger row, 1 ActivityLog, history API shows fee & WALLET.
- Case 2: Insufficient wallet -> Worker holds barrier, 0 debit, 1 ActivityLog(WALLET_INSUFFICIENT),
  1 Notification with missing_amount ("15,000" / "còn thiếu"); LOCKED wallet gets locked message;
  sync POST /api/v1/parking/sessions/check-out/ returns 409 PROP-WALLET-INSUFFICIENT with rollback.
- Case 3: Customer tops up via POST /api/v1/me/wallet/topups/ while vehicle still seen (<= 20s)
  -> worker auto check-outs on recheck tick, reconcile_wallets passes.
- Case 4: Customer tops up after vehicle left (> 20s silent / > 60s expired) -> 0 debit, 0 checkout.
- Case 5: Package ticket inside validity (VALID_FEE_ZERO, 0 Payment, 0 WalletTransaction) and
  package overage (+14m = 10,000, +1h10m = 20,000) with both sufficient and insufficient wallet.
"""

from __future__ import annotations

import threading
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.audit.models import ActivityLog
from apps.content.models import Notification
from apps.customers.models import Customer
from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
from apps.parking.models import (
    ParkingGate,
    ParkingSlot,
    ParkingZone,
    SlotAllowedVehicleType,
    VehicleEntryExitLog,
)
from apps.parking.services.ocr import PlateCandidate, PlateRecognizer, PlateScanResult
from apps.tickets.models import Payment, Ticket, TicketType
from apps.vehicles.models import Vehicle, VehicleType
from apps.wallet.models import Wallet, WalletTransaction
from apps.wallet.services.wallet import credit_wallet

pytestmark = pytest.mark.django_db


class FakeClock:
    def __init__(self, initial: float = 2000.0) -> None:
        self._lock = threading.Lock()
        self._now = float(initial)

    def __call__(self) -> float:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> float:
        with self._lock:
            self._now += float(seconds)
            return self._now


def _make_scan_result(
    plate: str, confidence: float = 97.0, review_status: str = "AUTO"
) -> PlateScanResult:
    norm = PlateRecognizer.normalize_plate(plate) or plate
    cand = PlateCandidate(
        plate_text=plate,
        plate_normalized=norm,
        confidence=confidence,
    )
    return PlateScanResult(
        candidates=[cand],
        best_candidate=cand,
        engine_name="mock_ocr",
        raw_text=plate,
        latency_ms=8.0,
        review_status=review_status,
    )


def _setup_out_coordinator(
    out_gate: ParkingGate, clock: FakeClock
) -> GateWorkerCoordinator:
    coord = GateWorkerCoordinator(
        streams_override={out_gate.code: f"http://mock/{out_gate.code}"},
        snapshot_uploader=MagicMock(),
        clock=clock,
    )
    coord._pending_recheck_seconds = 5.0
    out_gate.is_active = True
    out_gate.is_auto_scan = True
    coord._managed_gates[out_gate.id] = out_gate
    mock_reader = MagicMock()
    mock_reader.status = "STREAMING"
    mock_reader.get_latest_frame.return_value = (None, 0.0)
    coord._readers[out_gate.id] = mock_reader
    coord._filters[out_gate.id] = MagicMock()
    return coord


def _make_customer_vehicle_session(
    *,
    plate: str,
    hours_ago: float,
    balance: Decimal = Decimal("0.00"),
    wallet_status: str = "ACTIVE",
):
    suffix = uuid.uuid4().hex[:6].upper()
    vtype = (
        VehicleType.objects.filter(code="CAR").first() or VehicleType.objects.first()
    )
    zone = ParkingZone.objects.first()
    in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    out_gate = ParkingGate.objects.filter(
        direction="OUT", is_active=True, is_auto_scan=True
    ).first()
    assert (
        vtype is not None
        and zone is not None
        and in_gate is not None
        and out_gate is not None
    )

    acc = Account.objects.create_user(
        email=f"wp3_{suffix}@parking.local",
        phone=f"09{int(uuid.uuid4().int % 100000000):08d}",
        password="TestPassword123!",
        role="CUSTOMER",
        is_active=True,
    )
    cust = Customer.objects.create(
        account=acc,
        code=f"K3{suffix}"[:10],
        full_name=f"Khach WP3 {suffix}",
        phone=acc.phone,
        identity_card_number=f"079{int(uuid.uuid4().int % 1000000000):09d}",
        status="ACTIVE",
    )
    norm = PlateRecognizer.normalize_plate(plate) or plate
    veh = Vehicle.objects.create(
        code=f"V3{suffix}"[:10],
        license_plate=plate,
        license_plate_norm=norm,
        vehicle_type=vtype,
        customer=cust,
        model_name="Mazda 3",
    )
    slot = ParkingSlot.objects.create(
        zone=zone,
        code=f"W3{suffix[:6]}",
        slot_kind="STANDARD",
        status="AVAILABLE",
    )
    SlotAllowedVehicleType.objects.get_or_create(slot=slot, vehicle_type=vtype)

    wallet = Wallet.objects.create(
        customer=cust, balance=Decimal("0.00"), currency="VND", status="ACTIVE"
    )
    if balance > Decimal("0.00"):
        credit_wallet(
            wallet_id=wallet.id,
            amount=balance,
            kind="TOPUP_CASH",
            idempotency_key=f"wp3-seed-{suffix}",
        )
        wallet.refresh_from_db()
    if wallet_status != "ACTIVE":
        wallet.status = wallet_status
        wallet.save(update_fields=["status"])

    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-WP3-{suffix}",
        vehicle=veh,
        slot=slot,
        entry_gate=in_gate,
        license_plate=plate,
        license_plate_norm=norm,
        entry_time=now - timedelta(hours=hours_ago),
        recognition_source="AI",
        review_status="AUTO",
    )
    slot.status = "OCCUPIED"
    slot.save(update_fields=["status"])
    return acc, cust, veh, slot, wallet, session, out_gate


def test_case1_sufficient_wallet_auto_checkout_and_history():
    """Case 1: Sufficient wallet -> worker auto check-out, exact debit, Payment WALLET PAID, history shows fee."""
    acc, cust, veh, slot, wallet, session, out_gate = _make_customer_vehicle_session(
        plate="51K-112.01",
        hours_ago=2.0,
        balance=Decimal("100000.00"),
    )
    clock = FakeClock(2000.0)
    coord = _setup_out_coordinator(out_gate, clock)

    coord._evaluate_and_execute(
        out_gate, veh.license_plate, _make_scan_result(veh.license_plate)
    )

    session.refresh_from_db()
    wallet.refresh_from_db()
    slot.refresh_from_db()

    assert session.exit_time is not None
    assert session.exit_gate_id == out_gate.id
    assert session.fee_amount == Decimal("20000.00")
    assert wallet.balance == Decimal("80000.00")
    assert slot.status == "AVAILABLE"

    pay = Payment.objects.get(session=session)
    assert pay.method == "WALLET"
    assert pay.status == "PAID"
    assert pay.amount == Decimal("20000.00")

    tx = WalletTransaction.objects.get(
        wallet=wallet, idempotency_key=f"checkout-session-{session.id}"
    )
    assert tx.transaction_type == "DEBIT"
    assert tx.kind == "PARKING_FEE"
    assert tx.amount == Decimal("-20000.00")

    log = ActivityLog.objects.filter(
        entity_type="parking_gate", entity_id=out_gate.id, action="GATE_AUTO_CHECK_OUT"
    ).latest("id")
    assert "VALID_WALLET_PAID" in log.message

    # History API for staff shows fee_amount and payment_method == WALLET
    staff = Account.objects.create_user(
        email=f"emp_wp3_{uuid.uuid4().hex[:6]}@parking.local",
        password="TestPassword123!",
        role="EMPLOYEE",
        is_active=True,
    )
    staff_client = APIClient()
    staff_client.force_authenticate(user=staff)
    hist_resp = staff_client.get(
        f"/api/v1/parking/sessions/?session_code={session.session_code.replace('#', '')}"
    )
    assert hist_resp.status_code == 200
    rows = hist_resp.json()["results"]
    assert len(rows) == 1
    assert Decimal(rows[0]["fee_amount"]) == Decimal("20000.00")
    assert rows[0]["payment_method"] == "WALLET"

    call_command("reconcile_wallets", "--fail-on-mismatch")


def test_case2_insufficient_wallet_notification_includes_missing_amount_and_locked_distinct():
    """Case 2: Insufficient wallet creates Notification with missing_amount ('15,000' / 'còn thiếu'), 0 debit; locked wallet gets locked notice."""
    acc, cust, veh, _, wallet, session, out_gate = _make_customer_vehicle_session(
        plate="51K-223.02",
        hours_ago=2.0,  # fee = 20,000.00
        balance=Decimal("5000.00"),  # missing = 15,000.00
    )
    clock = FakeClock(2000.0)
    coord = _setup_out_coordinator(out_gate, clock)

    coord._evaluate_and_execute(
        out_gate, veh.license_plate, _make_scan_result(veh.license_plate)
    )

    session.refresh_from_db()
    wallet.refresh_from_db()
    assert session.exit_time is None
    assert wallet.balance == Decimal("5000.00")
    assert Payment.objects.filter(session=session).count() == 0
    assert (
        WalletTransaction.objects.filter(wallet=wallet, kind="PARKING_FEE").count() == 0
    )

    log = ActivityLog.objects.filter(
        entity_type="parking_gate",
        entity_id=out_gate.id,
        action="GATE_AUTO_PAYMENT_REQUIRED",
    ).latest("id")
    assert "WALLET_INSUFFICIENT" in log.message

    notif = Notification.objects.filter(recipient_account_id=acc.id).latest("id")
    assert notif.notification_type == "PAYMENT"
    assert "20,000" in notif.content
    assert "5,000" in notif.content
    assert "15,000" in notif.content
    assert "còn thiếu" in notif.content.lower()

    # Sync POST check-out -> 409 PROP-WALLET-INSUFFICIENT with complete rollback
    staff = Account.objects.create_user(
        email=f"emp_wp3_c2_{uuid.uuid4().hex[:6]}@parking.local",
        password="TestPassword123!",
        role="EMPLOYEE",
        is_active=True,
    )
    staff_client = APIClient()
    staff_client.force_authenticate(user=staff)
    sync_resp = staff_client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": "WALLET",
        },
        format="json",
    )
    assert sync_resp.status_code == status.HTTP_409_CONFLICT
    assert sync_resp.json()["code"] == "PROP-WALLET-INSUFFICIENT"
    assert Decimal(sync_resp.json()["details"]["missing_amount"]) == Decimal("15000.00")

    # Locked wallet with sufficient balance -> distinct notification (not asking to top up)
    acc_l, _, veh_l, _, wallet_l, session_l, out_gate_l = (
        _make_customer_vehicle_session(
            plate="51K-223.99",
            hours_ago=2.0,
            balance=Decimal("100000.00"),
            wallet_status="LOCKED",
        )
    )
    coord._evaluate_and_execute(
        out_gate_l, veh_l.license_plate, _make_scan_result(veh_l.license_plate)
    )
    notif_l = Notification.objects.filter(recipient_account_id=acc_l.id).latest("id")
    assert "khóa" in notif_l.title.lower() or "khóa" in notif_l.content.lower()
    assert "còn thiếu" not in notif_l.content.lower()
    assert session_l.exit_time is None


def test_case3_topup_via_api_while_still_seen_completes_checkout():
    """Case 3: Customer tops up via POST /api/v1/me/wallet/topups/ while <=20s still seen -> worker completes exit."""
    acc, cust, veh, _, wallet, session, out_gate = _make_customer_vehicle_session(
        plate="51K-334.03",
        hours_ago=2.0,
        balance=Decimal("5000.00"),
    )
    clock = FakeClock(3000.0)
    coord = _setup_out_coordinator(out_gate, clock)

    # Initial hold
    coord._evaluate_and_execute(
        out_gate, veh.license_plate, _make_scan_result(veh.license_plate)
    )
    session.refresh_from_db()
    assert session.exit_time is None

    # Advance 10s (<= 20s) and keep sighting alive
    clock.advance(10.0)
    coord._touch_pending_plate(out_gate.id, veh.license_plate, now_mono=clock())

    # Customer tops up 20,000 VND via real API
    cust_client = APIClient()
    cust_client.force_authenticate(user=acc)
    topup_resp = cust_client.post(
        "/api/v1/me/wallet/topups/",
        {"amount": 20000, "idempotency_key": f"c3-{uuid.uuid4().hex}"},
        format="json",
    )
    assert topup_resp.status_code == 201

    # Advance 6s (>= 5s recheck, total since last_seen_at = 6s <= 20s) -> auto checkout!
    clock.advance(6.0)
    coord._recheck_pending_exits(out_gate)

    session.refresh_from_db()
    wallet.refresh_from_db()
    assert session.exit_time is not None
    assert session.fee_amount == Decimal("20000.00")
    assert wallet.balance == Decimal("5000.00")  # 5,000 + 20,000 - 20,000
    assert (
        Payment.objects.filter(session=session, method="WALLET", status="PAID").count()
        == 1
    )
    call_command("reconcile_wallets", "--fail-on-mismatch")


def test_case4_topup_via_api_after_vehicle_left_no_debit_no_checkout():
    """Case 4: Customer tops up via API after vehicle left (>20s and >60s) -> 0 debit, 0 checkout."""
    acc, cust, veh, _, wallet, session, out_gate = _make_customer_vehicle_session(
        plate="51K-445.04",
        hours_ago=2.0,
        balance=Decimal("5000.00"),
    )
    clock = FakeClock(4000.0)
    coord = _setup_out_coordinator(out_gate, clock)

    coord._evaluate_and_execute(
        out_gate, veh.license_plate, _make_scan_result(veh.license_plate)
    )

    # Vehicle leaves: advance 25s (in silent window (20s, 60s])
    clock.advance(25.0)
    cust_client = APIClient()
    cust_client.force_authenticate(user=acc)
    topup_resp = cust_client.post(
        "/api/v1/me/wallet/topups/",
        {"amount": 50000, "idempotency_key": f"c4-{uuid.uuid4().hex}"},
        format="json",
    )
    assert topup_resp.status_code == 201

    coord._recheck_pending_exits(out_gate)
    session.refresh_from_db()
    wallet.refresh_from_db()
    assert session.exit_time is None
    assert wallet.balance == Decimal("55000.00")
    assert Payment.objects.filter(session=session).count() == 0

    # Advance past 60s -> evicted cleanly, still 0 debit
    clock.advance(40.0)
    coord._recheck_pending_exits(out_gate)
    session.refresh_from_db()
    wallet.refresh_from_db()
    assert session.exit_time is None
    assert wallet.balance == Decimal("55000.00")
    assert (out_gate.id, veh.license_plate_norm) not in coord._pending_exits
    call_command("reconcile_wallets", "--fail-on-mismatch")


def test_case5_package_ticket_valid_fee_zero_and_overage_hour_blocks():
    """Case 5: Valid package ticket -> fee=0 (0 Payment, 0 debit); expired overage (+14m=10k, +1h10m=20k) via worker."""
    tt = TicketType.objects.filter(deleted_at__isnull=True).first()
    assert tt is not None

    # 5a: Valid ticket covering entire session (wallet balance = 0.00) -> VALID_FEE_ZERO
    acc_0, cust_0, veh_0, slot_0, wallet_0, session_0, out_gate = (
        _make_customer_vehicle_session(
            plate="51K-556.01",
            hours_ago=1.0,
            balance=Decimal("0.00"),
        )
    )
    now = timezone.now()
    Ticket.objects.create(
        code=f"TK0{uuid.uuid4().hex[:6].upper()}",
        customer=cust_0,
        vehicle=veh_0,
        ticket_type=tt,
        slot=slot_0,
        effective_from=now - timedelta(days=2),
        effective_to=now + timedelta(days=5),
        price=tt.default_price,
        status="ACTIVE",
    )
    clock = FakeClock(5000.0)
    coord = _setup_out_coordinator(out_gate, clock)
    coord._evaluate_and_execute(
        out_gate, veh_0.license_plate, _make_scan_result(veh_0.license_plate)
    )
    session_0.refresh_from_db()
    assert session_0.exit_time is not None
    assert session_0.fee_amount == Decimal("0.00")
    assert Payment.objects.filter(session=session_0).count() == 0
    assert WalletTransaction.objects.filter(wallet=wallet_0).count() == 0

    # 5b: Overage +14m -> 10,000.00 VND (1h block) with sufficient wallet
    acc_14, cust_14, veh_14, slot_14, wallet_14, session_14, _ = (
        _make_customer_vehicle_session(
            plate="51K-556.02",
            hours_ago=2.0,
            balance=Decimal("50000.00"),
        )
    )
    Ticket.objects.create(
        code=f"TK1{uuid.uuid4().hex[:6].upper()}",
        customer=cust_14,
        vehicle=veh_14,
        ticket_type=tt,
        slot=slot_14,
        effective_from=now - timedelta(days=5),
        effective_to=now - timedelta(minutes=14),
        price=tt.default_price,
        status="ACTIVE",
    )
    coord._evaluate_and_execute(
        out_gate, veh_14.license_plate, _make_scan_result(veh_14.license_plate)
    )
    session_14.refresh_from_db()
    wallet_14.refresh_from_db()
    assert session_14.exit_time is not None
    assert session_14.fee_amount == Decimal("10000.00")
    assert wallet_14.balance == Decimal("40000.00")

    # 5c: Overage +1h10m -> 20,000.00 VND (2h block) with insufficient wallet (5,000) -> missing 15,000
    acc_70, cust_70, veh_70, slot_70, wallet_70, session_70, _ = (
        _make_customer_vehicle_session(
            plate="51K-556.03",
            hours_ago=3.0,
            balance=Decimal("5000.00"),
        )
    )
    Ticket.objects.create(
        code=f"TK2{uuid.uuid4().hex[:6].upper()}",
        customer=cust_70,
        vehicle=veh_70,
        ticket_type=tt,
        slot=slot_70,
        effective_from=now - timedelta(days=5),
        effective_to=now - timedelta(hours=1, minutes=10),
        price=tt.default_price,
        status="ACTIVE",
    )
    coord._evaluate_and_execute(
        out_gate, veh_70.license_plate, _make_scan_result(veh_70.license_plate)
    )
    session_70.refresh_from_db()
    wallet_70.refresh_from_db()
    assert session_70.exit_time is None
    assert wallet_70.balance == Decimal("5000.00")
    notif_70 = Notification.objects.filter(recipient_account_id=acc_70.id).latest("id")
    assert "20,000" in notif_70.content
    assert "15,000" in notif_70.content
    call_command("reconcile_wallets", "--fail-on-mismatch")
