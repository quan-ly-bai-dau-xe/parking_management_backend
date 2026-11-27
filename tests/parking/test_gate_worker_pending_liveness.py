"""
Round 93 WP1 (K1 / D1): Pending Vehicle Liveness ("Still Seen" Rule) Tests.

Tests all 11 D1 scenarios (a)-(k) using an injectable FakeClock with zero time.sleep():
(a) Unregistered entry vehicle leaves; registers 10m later -> NO check-in, NO slot taken, NO audit row.
(b) Unregistered entry vehicle still seen when registered -> auto check-in within 1 recheck interval.
(c) Exit vehicle with insufficient wallet leaves; topped up >60s later -> NO debit, NO check-out.
(d1) Exit vehicle reappears after eviction -> completes check-out exactly once.
(d2) D1(5) Inside transaction: changed fee (> balance) or manually closed session -> NO wrong/double debit.
(e) Pending items expire by BOTH unseen limit (> 3 * seen_seconds = 60s) and total age (> pending_minutes = 900s).
(f) Silent wait window (20s, 60s]: 0 DB queries, 0 logs, 0 actions; resumes when re-sighted.
(g1) Refreshes last_seen_at on ignored readings (cooldown, partial vote, same decision, stationary NO_MOTION probe).
(g2) D1(4) Fresh sighting verified at exact moment of action (before check_in_vehicle / check_out_vehicle).
(h) Two gates holding the same plate remain completely isolated per (gate_id, norm_plate).
(i) Bounded per-gate memory cap evicts the oldest pending entry/exit without touching other gates.
(j) Thread-safety stress test under concurrent _evaluate_and_execute / _recheck_* / _release_gate.
(k) GateWorkerCoordinator accepts injectable clock & pending_max_per_gate; settings default == 20.
"""

from __future__ import annotations

import inspect
import logging
import threading
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

from apps.accounts.models import Account
from apps.audit.models import ActivityLog
from apps.content.models import Notification
from apps.customers.models import Customer
from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
from apps.parking.gate_worker.filter import MotionFilter
from apps.parking.models import (
    ParkingGate,
    ParkingLot,
    ParkingSlot,
    VehicleEntryExitLog,
)
from apps.parking.services.gate_decision import (
    ACTION_HOLD,
    REASON_UNREGISTERED_VEHICLE,
    REASON_WALLET_INSUFFICIENT,
)
from apps.parking.services.ocr import PlateCandidate, PlateRecognizer, PlateScanResult
from apps.tickets.models import Payment
from apps.vehicles.models import Vehicle, VehicleType
from apps.wallet.models import Wallet, WalletTransaction
from apps.wallet.services.wallet import credit_wallet

pytestmark = pytest.mark.django_db


class FakeClock:
    """Thread-safe deterministic monotonic clock for testing without time.sleep()."""

    def __init__(self, initial: float = 1000.0) -> None:
        self._lock = threading.Lock()
        self._now = float(initial)

    def __call__(self) -> float:
        with self._lock:
            return self._now

    def advance(self, seconds: float) -> float:
        with self._lock:
            self._now += float(seconds)
            return self._now


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def fake_clock(monkeypatch) -> FakeClock:
    """
    Return a deterministic FakeClock.
    When GateWorkerCoordinator does not yet accept an injectable `clock` parameter
    (unmodified baseline for failing-first reproduction), patch time.monotonic.
    Once `clock` is supported, inject it directly without monkeypatching time.monotonic.
    """
    clock = FakeClock(1000.0)
    params = inspect.signature(GateWorkerCoordinator.__init__).parameters
    if "clock" not in params:
        monkeypatch.setattr(
            "apps.parking.gate_worker.coordinator.time.monotonic", clock
        )
        monkeypatch.setattr("apps.parking.gate_worker.voter.time.monotonic", clock)
    return clock


def _build_coordinator(
    gates: list[ParkingGate],
    fake_clock: FakeClock,
    *,
    pending_recheck_seconds: float = 5.0,
    pending_max_per_gate: int | None = None,
    use_real_motion_filter: bool = False,
) -> tuple[GateWorkerCoordinator, dict[int, MagicMock]]:
    params = inspect.signature(GateWorkerCoordinator.__init__).parameters
    kwargs: dict[str, object] = {
        "streams_override": {g.code: f"http://mock/{g.code}" for g in gates},
        "snapshot_uploader": MagicMock(),
    }
    if "clock" in params:
        kwargs["clock"] = fake_clock
    if "pending_max_per_gate" in params and pending_max_per_gate is not None:
        kwargs["pending_max_per_gate"] = pending_max_per_gate

    coordinator = GateWorkerCoordinator(**kwargs)  # type: ignore[arg-type]
    coordinator._pending_recheck_seconds = pending_recheck_seconds

    readers: dict[int, MagicMock] = {}
    for gate in gates:
        gate.is_active = True
        gate.is_auto_scan = True
        coordinator._managed_gates[gate.id] = gate
        mock_reader = MagicMock()
        mock_reader.status = "STREAMING"
        mock_reader.get_latest_frame.return_value = (None, 0.0)
        coordinator._readers[gate.id] = mock_reader
        if use_real_motion_filter:
            coordinator._filters[gate.id] = MotionFilter(
                mad_threshold=1.0, max_fps=1000.0
            )
        else:
            coordinator._filters[gate.id] = MagicMock()
        readers[gate.id] = mock_reader

    return coordinator, readers


def _make_scan_result(
    plate: str, confidence: float = 96.5, review_status: str = "AUTO"
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
        latency_ms=10.0,
        review_status=review_status,
    )


def _make_customer_with_vehicle(
    prefix: str,
    vtype: VehicleType,
    plate: str,
    *,
    initial_balance: Decimal = Decimal("0.00"),
) -> tuple[Account, Customer, Vehicle, Wallet]:
    suffix = uuid.uuid4().hex[:6].upper()
    acct = Account.objects.create_user(
        email=f"{prefix}_{suffix}@parking.local",
        phone=f"09{int(uuid.uuid4().int % 100000000):08d}",
        password="ValidPassword123!",
        role="CUSTOMER",
        is_active=True,
    )
    cust = Customer.objects.create(
        account=acct,
        code=f"K{suffix}"[:10],
        full_name=f"Khach {prefix} {suffix}",
        phone=acct.phone,
        identity_card_number=f"079{int(uuid.uuid4().int % 1000000000):09d}",
        status="ACTIVE",
    )
    norm = PlateRecognizer.normalize_plate(plate) or plate
    veh = Vehicle.objects.create(
        code=f"V{suffix}"[:10],
        license_plate=plate,
        license_plate_norm=norm,
        vehicle_type=vtype,
        customer=cust,
        model_name="Test Sedan",
    )
    wallet = Wallet.objects.create(
        customer=cust, balance=Decimal("0.00"), status="ACTIVE"
    )
    if initial_balance > Decimal("0.00"):
        credit_wallet(
            wallet_id=wallet.id,
            amount=initial_balance,
            kind="TOPUP_CASH",
            idempotency_key=f"init-{suffix}",
        )
        wallet.refresh_from_db()
    return acct, cust, veh, wallet


def _ensure_two_active_in_gates() -> tuple[ParkingGate, ParkingGate]:
    gates = list(ParkingGate.objects.filter(direction="IN", is_active=True)[:2])
    if len(gates) >= 2:
        return gates[0], gates[1]
    lot = ParkingLot.objects.first()
    assert lot is not None
    suffix = uuid.uuid4().hex[:4].upper()
    g2 = ParkingGate.objects.create(
        lot=lot,
        code=f"IN_T{suffix}"[:20],
        name=f"Test In Gate {suffix}",
        direction="IN",
        is_active=True,
        is_auto_scan=True,
    )
    return gates[0], g2


def _make_distinct_frame(seed_value: int) -> np.ndarray:
    return np.full((64, 64, 3), seed_value % 255, dtype=np.uint8)


class TestGateWorkerPendingLiveness:
    """WP1 (K1 / D1) pending entry & exit liveness tests."""

    def test_k1_entry_plate_registers_10m_after_vehicle_left_no_checkin(
        self, fake_clock: FakeClock
    ):
        """(a) Unregistered vehicle leaves; registers 10m later -> NO check-in, NO slot taken, NO audit row."""
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        assert in_gate is not None

        plate = "51A-897.14"
        norm_plate = "51A89714"
        Vehicle.all_objects.filter(license_plate_norm=norm_plate).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )
        VehicleEntryExitLog.objects.filter(
            license_plate_norm=norm_plate, exit_time__isnull=True
        ).update(exit_time=timezone.now())

        coordinator, _ = _build_coordinator(
            [in_gate], fake_clock, pending_recheck_seconds=5.0
        )

        avail_slots_before = ParkingSlot.objects.filter(
            zone__floor__lot_id=in_gate.lot_id,
            status="AVAILABLE",
            deleted_at__isnull=True,
        ).count()
        checkin_audit_before = ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=in_gate.id,
            action="GATE_AUTO_CHECK_IN",
        ).count()

        # t=1000.0: first sighting -> HOLD / UNREGISTERED_VEHICLE
        decision = coordinator._evaluate_and_execute(
            in_gate, plate, _make_scan_result(plate, 97.0)
        )
        assert decision.action == ACTION_HOLD
        assert decision.reason_code == REASON_UNREGISTERED_VEHICLE
        assert (in_gate.id, norm_plate) in coordinator._pending_entries

        # Vehicle drives away; 10 minutes pass without any sighting
        fake_clock.advance(600.0)

        # Owner registers vehicle 10 minutes later
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None
        _make_customer_with_vehicle("k1a", vtype_car, plate)

        # Worker ticks with empty camera
        coordinator._process_gate_tick(in_gate)

        assert not VehicleEntryExitLog.objects.filter(
            license_plate_norm=norm_plate, exit_time__isnull=True
        ).exists()
        assert (
            ParkingSlot.objects.filter(
                zone__floor__lot_id=in_gate.lot_id,
                status="AVAILABLE",
                deleted_at__isnull=True,
            ).count()
            == avail_slots_before
        )
        assert (
            ActivityLog.objects.filter(
                entity_type="parking_gate",
                entity_id=in_gate.id,
                action="GATE_AUTO_CHECK_IN",
            ).count()
            == checkin_audit_before
        )
        assert (in_gate.id, norm_plate) not in coordinator._pending_entries

    def test_k1_entry_plate_still_seen_when_registered_auto_checkin_within_one_recheck(
        self, fake_clock: FakeClock
    ):
        """(b) Vehicle remains seen; once registered, auto check-in completes within 1 recheck tick."""
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        assert in_gate is not None

        plate = "51B-777.01"
        norm_plate = "51B77701"
        Vehicle.all_objects.filter(license_plate_norm=norm_plate).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )

        coordinator, readers = _build_coordinator(
            [in_gate],
            fake_clock,
            pending_recheck_seconds=5.0,
            use_real_motion_filter=True,
        )

        checkin_audit_before = ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=in_gate.id,
            action="GATE_AUTO_CHECK_IN",
        ).count()

        # t=1000.0: pending entry created
        decision = coordinator._evaluate_and_execute(
            in_gate, plate, _make_scan_result(plate, 96.0)
        )
        assert decision.reason_code == REASON_UNREGISTERED_VEHICLE

        # t=1015.0: vehicle is still seen by camera (single OCR reading -> partial vote refreshes last_seen_at)
        fake_clock.advance(15.0)
        readers[in_gate.id].get_latest_frame.return_value = (
            _make_distinct_frame(50),
            fake_clock(),
        )
        mock_recognizer = MagicMock()
        mock_recognizer.recognize.return_value = _make_scan_result(plate, 96.0)
        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_recognizer,
        ):
            coordinator._process_gate_tick(in_gate)

        # t=1020.0: 5s since last_seen_at (<= 20s) and >= 5s since recheck; register vehicle and run 1 tick
        fake_clock.advance(5.0)
        readers[in_gate.id].get_latest_frame.return_value = (None, 0.0)
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None
        _make_customer_with_vehicle("k1b", vtype_car, plate)

        coordinator._process_gate_tick(in_gate)

        session = VehicleEntryExitLog.objects.filter(
            license_plate_norm=norm_plate, exit_time__isnull=True
        ).first()
        assert session is not None
        assert session.recognition_source == "AI"
        assert session.review_status == "AUTO"
        assert session.entry_handled_by is None
        assert (
            ActivityLog.objects.filter(
                entity_type="parking_gate",
                entity_id=in_gate.id,
                action="GATE_AUTO_CHECK_IN",
            ).count()
            == checkin_audit_before + 1
        )
        assert (in_gate.id, norm_plate) not in coordinator._pending_entries

    def test_k1_exit_vehicle_left_wallet_topped_up_no_debit_no_checkout(
        self, fake_clock: FakeClock
    ):
        """(c) Exit vehicle with insufficient wallet leaves; topped up >60s later -> NO debit, NO check-out."""
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        assert in_gate and out_gate

        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None
        plate = f"51L-{uuid.uuid4().int % 90000 + 10000}"
        acct, cust, veh, wallet = _make_customer_with_vehicle(
            "k1c", vtype_car, plate, initial_balance=Decimal("5000.00")
        )
        session = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-K1C-{uuid.uuid4().hex[:6].upper()}",
            vehicle=veh,
            entry_gate=in_gate,
            license_plate=veh.license_plate,
            license_plate_norm=veh.license_plate_norm,
            entry_time=timezone.now() - timedelta(hours=2),  # fee = 20,000 VND
            recognition_source="AI",
            review_status="AUTO",
        )

        coordinator, _ = _build_coordinator(
            [out_gate], fake_clock, pending_recheck_seconds=5.0
        )

        checkout_audit_before = ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=out_gate.id,
            action="GATE_AUTO_CHECK_OUT",
        ).count()

        # t=1000.0: WALLET_INSUFFICIENT -> HOLD + 1 Notification + pending exit
        decision = coordinator._evaluate_and_execute(
            out_gate, veh.license_plate, _make_scan_result(veh.license_plate, 96.0)
        )
        assert decision.action == ACTION_HOLD
        assert decision.reason_code == REASON_WALLET_INSUFFICIENT
        assert (out_gate.id, veh.license_plate_norm) in coordinator._pending_exits
        assert (
            Notification.objects.filter(
                recipient_account=acct, notification_type="PAYMENT"
            ).count()
            == 1
        )

        # Vehicle drives away; 65s pass (> 60s unseen limit), then customer tops up 50,000 VND
        fake_clock.advance(65.0)
        credit_wallet(
            wallet_id=wallet.id,
            amount=Decimal("50000.00"),
            kind="TOPUP_VIETQR",
            idempotency_key=f"k1c-topup-{uuid.uuid4().hex[:8]}",
        )

        coordinator._process_gate_tick(out_gate)

        wallet.refresh_from_db()
        session.refresh_from_db()
        assert wallet.balance == Decimal("55000.00")
        assert (
            WalletTransaction.objects.filter(wallet=wallet, kind="PARKING_FEE").count()
            == 0
        )
        assert Payment.objects.filter(session=session).count() == 0
        assert session.exit_time is None
        assert (
            ActivityLog.objects.filter(
                entity_type="parking_gate",
                entity_id=out_gate.id,
                action="GATE_AUTO_CHECK_OUT",
            ).count()
            == checkout_audit_before
        )
        assert (out_gate.id, veh.license_plate_norm) not in coordinator._pending_exits

    def test_k1_exit_vehicle_reappears_after_eviction_completes_checkout_once(
        self, fake_clock: FakeClock
    ):
        """(d1) After eviction (>60s), wallet is topped up and vehicle reappears -> completes exit exactly once."""
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        assert in_gate and out_gate

        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None
        plate = f"51M-{uuid.uuid4().int % 90000 + 10000}"
        _, _, veh, wallet = _make_customer_with_vehicle(
            "k1d1", vtype_car, plate, initial_balance=Decimal("5000.00")
        )
        session = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-K1D1-{uuid.uuid4().hex[:6].upper()}",
            vehicle=veh,
            entry_gate=in_gate,
            license_plate=veh.license_plate,
            license_plate_norm=veh.license_plate_norm,
            entry_time=timezone.now() - timedelta(hours=2),  # fee = 20,000 VND
            recognition_source="AI",
            review_status="AUTO",
        )

        coordinator, readers = _build_coordinator(
            [out_gate],
            fake_clock,
            pending_recheck_seconds=5.0,
            use_real_motion_filter=True,
        )

        # t=1000.0: pending exit registered
        coordinator._evaluate_and_execute(
            out_gate, veh.license_plate, _make_scan_result(veh.license_plate, 96.0)
        )

        # t=1065.0: vehicle left -> tick evicts pending exit
        fake_clock.advance(65.0)
        coordinator._process_gate_tick(out_gate)
        assert (out_gate.id, veh.license_plate_norm) not in coordinator._pending_exits

        # Top up wallet
        credit_wallet(
            wallet_id=wallet.id,
            amount=Decimal("50000.00"),
            kind="TOPUP_VIETQR",
            idempotency_key=f"k1d1-topup-{uuid.uuid4().hex[:8]}",
        )

        # t=1080.0: vehicle reappears for 3 frames (3/4 voting)
        fake_clock.advance(15.0)
        mock_recognizer = MagicMock()
        mock_recognizer.recognize.return_value = _make_scan_result(
            veh.license_plate, 96.5
        )
        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_recognizer,
        ):
            for idx in range(3):
                fake_clock.advance(0.2)
                readers[out_gate.id].get_latest_frame.return_value = (
                    _make_distinct_frame(30 + idx * 40),
                    fake_clock(),
                )
                coordinator._process_gate_tick(out_gate)

            # Subsequent ticks do not double-debit
            for idx in range(2):
                fake_clock.advance(2.5)
                readers[out_gate.id].get_latest_frame.return_value = (
                    _make_distinct_frame(180 + idx * 40),
                    fake_clock(),
                )
                coordinator._process_gate_tick(out_gate)

        session.refresh_from_db()
        wallet.refresh_from_db()
        assert session.exit_time is not None
        assert session.fee_amount == Decimal("20000.00")
        assert wallet.balance == Decimal("35000.00")
        assert (
            Payment.objects.filter(
                session=session, method="WALLET", status="PAID"
            ).count()
            == 1
        )
        assert (
            WalletTransaction.objects.filter(wallet=wallet, kind="PARKING_FEE").count()
            == 1
        )

    def test_d1_5_pending_exit_changed_fee_or_closed_session_inside_tx_never_debits_wrongly(
        self, fake_clock: FakeClock
    ):
        """
        (d2) D1(5):
        (i) Fee increases inside check_out_vehicle transaction above wallet balance -> rollback, 0 debit.
        (ii) Session closed manually right before check_out_vehicle tx -> PROP-4.5.1-P10, 0 debit, pending evicted.
        """
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        assert in_gate and out_gate
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None

        # --- Sub-case (i): Fee jumps from 10,000 preview to 20,000 inside tx when balance is 15,000 ---
        plate1 = f"51N-{uuid.uuid4().int % 90000 + 10000}"
        _, _, veh1, wallet1 = _make_customer_with_vehicle(
            "k1d2a", vtype_car, plate1, initial_balance=Decimal("5000.00")
        )
        session1 = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-D15A-{uuid.uuid4().hex[:6].upper()}",
            vehicle=veh1,
            entry_gate=in_gate,
            license_plate=veh1.license_plate,
            license_plate_norm=veh1.license_plate_norm,
            entry_time=timezone.now() - timedelta(minutes=50),  # 10,000 VND initially
            recognition_source="AI",
            review_status="AUTO",
        )
        coordinator, _ = _build_coordinator(
            [out_gate], fake_clock, pending_recheck_seconds=0.0
        )
        # Force initial hold with mocked higher fee preview (or low balance vs 10,000)
        coordinator._evaluate_and_execute(
            out_gate, veh1.license_plate, _make_scan_result(veh1.license_plate, 96.0)
        )
        assert (out_gate.id, veh1.license_plate_norm) in coordinator._pending_exits

        # Top up to 15,000 VND (enough for 10,000 preview, NOT enough if fee crosses 2h -> 20,000)
        credit_wallet(
            wallet_id=wallet1.id,
            amount=Decimal("10000.00"),
            kind="TOPUP_VIETQR",
            idempotency_key=f"d15a-top-{uuid.uuid4().hex[:8]}",
        )
        fake_clock.advance(5.0)

        from apps.parking.services import check_out as check_out_module

        real_check_out = check_out_module.check_out_vehicle

        def _bump_entry_time_before_tx(*args, **kwargs):
            # Simulate boundary crossing right before atomic tx executes
            VehicleEntryExitLog.objects.filter(id=session1.id).update(
                entry_time=timezone.now() - timedelta(hours=2)
            )
            return real_check_out(*args, **kwargs)

        with patch(
            "apps.parking.services.check_out.check_out_vehicle",
            side_effect=_bump_entry_time_before_tx,
        ):
            coordinator._recheck_pending_exits(out_gate)

        wallet1.refresh_from_db()
        session1.refresh_from_db()
        assert wallet1.balance == Decimal("15000.00")
        assert (
            WalletTransaction.objects.filter(wallet=wallet1, kind="PARKING_FEE").count()
            == 0
        )
        assert Payment.objects.filter(session=session1).count() == 0
        assert session1.exit_time is None

        # --- Sub-case (ii): Session manually closed right before check_out_vehicle tx ---
        plate2 = f"51P-{uuid.uuid4().int % 90000 + 10000}"
        _, _, veh2, wallet2 = _make_customer_with_vehicle(
            "k1d2b", vtype_car, plate2, initial_balance=Decimal("5000.00")
        )
        session2 = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-D15B-{uuid.uuid4().hex[:6].upper()}",
            vehicle=veh2,
            entry_gate=in_gate,
            license_plate=veh2.license_plate,
            license_plate_norm=veh2.license_plate_norm,
            entry_time=timezone.now() - timedelta(hours=2),
            recognition_source="AI",
            review_status="AUTO",
        )
        coordinator._pending_exits.clear()
        coordinator._evaluate_and_execute(
            out_gate, veh2.license_plate, _make_scan_result(veh2.license_plate, 96.0)
        )
        credit_wallet(
            wallet_id=wallet2.id,
            amount=Decimal("50000.00"),
            kind="TOPUP_VIETQR",
            idempotency_key=f"d15b-top-{uuid.uuid4().hex[:8]}",
        )
        fake_clock.advance(5.0)

        def _close_session_at_counter_before_tx(*args, **kwargs):
            VehicleEntryExitLog.objects.filter(id=session2.id).update(
                exit_time=timezone.now(),
                exit_gate_id=out_gate.id,
                fee_amount=Decimal("20000.00"),
            )
            return real_check_out(*args, **kwargs)

        with patch(
            "apps.parking.services.check_out.check_out_vehicle",
            side_effect=_close_session_at_counter_before_tx,
        ):
            coordinator._recheck_pending_exits(out_gate)

        wallet2.refresh_from_db()
        assert wallet2.balance == Decimal("55000.00")
        assert (
            WalletTransaction.objects.filter(wallet=wallet2, kind="PARKING_FEE").count()
            == 0
        )
        assert Payment.objects.filter(session=session2, method="WALLET").count() == 0
        assert (out_gate.id, veh2.license_plate_norm) not in coordinator._pending_exits

    def test_k1_pending_expires_by_both_limits_seen_and_total_minutes(
        self, fake_clock: FakeClock
    ):
        """(e) Both pending_entries and pending_exits expire by unseen (>60s) AND total age (>900s)."""
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        assert in_gate and out_gate
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None

        coordinator, _ = _build_coordinator(
            [in_gate, out_gate], fake_clock, pending_recheck_seconds=5.0
        )

        # 1. Unseen limit (> 3 * 20s = 60s) for ENTRY & EXIT
        entry_plate = "51E-100.01"
        entry_norm = "51E10001"
        Vehicle.all_objects.filter(license_plate_norm=entry_norm).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )
        coordinator._evaluate_and_execute(
            in_gate, entry_plate, _make_scan_result(entry_plate, 96.0)
        )

        exit_plate = f"51E-{uuid.uuid4().int % 90000 + 10000}"
        _, _, veh_exit, _ = _make_customer_with_vehicle(
            "k1e", vtype_car, exit_plate, initial_balance=Decimal("1000.00")
        )
        VehicleEntryExitLog.objects.create(
            session_code=f"#PK-K1E-{uuid.uuid4().hex[:6].upper()}",
            vehicle=veh_exit,
            entry_gate=in_gate,
            license_plate=veh_exit.license_plate,
            license_plate_norm=veh_exit.license_plate_norm,
            entry_time=timezone.now() - timedelta(hours=2),
            recognition_source="AI",
            review_status="AUTO",
        )
        coordinator._evaluate_and_execute(
            out_gate,
            veh_exit.license_plate,
            _make_scan_result(veh_exit.license_plate, 96.0),
        )

        # Exactly at 60.0s: still kept
        fake_clock.advance(60.0)
        coordinator._recheck_pending_entries(in_gate)
        coordinator._recheck_pending_exits(out_gate)
        assert (in_gate.id, entry_norm) in coordinator._pending_entries
        assert (out_gate.id, veh_exit.license_plate_norm) in coordinator._pending_exits

        # At 60.1s: evicted
        fake_clock.advance(0.1)
        coordinator._recheck_pending_entries(in_gate)
        coordinator._recheck_pending_exits(out_gate)
        assert (in_gate.id, entry_norm) not in coordinator._pending_entries
        assert (
            out_gate.id,
            veh_exit.license_plate_norm,
        ) not in coordinator._pending_exits

        # Reappearance starts a new cycle
        fake_clock.advance(9.9)  # t=1070.0
        coordinator._evaluate_and_execute(
            in_gate, entry_plate, _make_scan_result(entry_plate, 96.0)
        )
        assert (
            coordinator._pending_entries[(in_gate.id, entry_norm)]["first_seen_at"]
            == 1070.0
        )

        # 2. Total age limit (> 15 * 60s = 900s) even while continually seen every 15s
        coordinator._pending_entries.clear()
        coordinator._pending_exits.clear()

        t_start = fake_clock()
        coordinator._evaluate_and_execute(
            in_gate, entry_plate, _make_scan_result(entry_plate, 96.0)
        )
        coordinator._evaluate_and_execute(
            out_gate,
            veh_exit.license_plate,
            _make_scan_result(veh_exit.license_plate, 96.0),
        )

        # Keep vehicle seen every 15s up to +885s, then check at +900.0s (still kept)
        for _ in range(59):  # 59 * 15 = 885s
            fake_clock.advance(15.0)
            coordinator._evaluate_and_execute(
                in_gate, entry_plate, _make_scan_result(entry_plate, 96.0)
            )
            coordinator._evaluate_and_execute(
                out_gate,
                veh_exit.license_plate,
                _make_scan_result(veh_exit.license_plate, 96.0),
            )

        fake_clock.advance(15.0)  # t_start + 900.0s, unseen = 15.0s <= 20s
        assert fake_clock() == t_start + 900.0
        coordinator._recheck_pending_entries(in_gate)
        coordinator._recheck_pending_exits(out_gate)
        assert (in_gate.id, entry_norm) in coordinator._pending_entries
        assert (out_gate.id, veh_exit.license_plate_norm) in coordinator._pending_exits

        # At t_start + 900.1s: evicted by total age limit!
        fake_clock.advance(0.1)
        coordinator._recheck_pending_entries(in_gate)
        coordinator._recheck_pending_exits(out_gate)
        assert (in_gate.id, entry_norm) not in coordinator._pending_entries
        assert (
            out_gate.id,
            veh_exit.license_plate_norm,
        ) not in coordinator._pending_exits

    def test_k1_silent_wait_window_20s_to_60s_zero_queries_zero_logs_zero_actions(
        self, fake_clock: FakeClock, django_assert_num_queries, caplog
    ):
        """(f) In (20s, 60s], recheck runs 0 SQL queries, 0 logs, 0 actions; resumes on re-sighting."""
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        assert in_gate and out_gate
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None

        entry_plate = "51F-200.01"
        entry_norm = "51F20001"
        Vehicle.all_objects.filter(license_plate_norm=entry_norm).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )

        exit_plate = f"51F-{uuid.uuid4().int % 90000 + 10000}"
        _, _, veh_exit, wallet_exit = _make_customer_with_vehicle(
            "k1f", vtype_car, exit_plate, initial_balance=Decimal("1000.00")
        )
        VehicleEntryExitLog.objects.create(
            session_code=f"#PK-K1F-{uuid.uuid4().hex[:6].upper()}",
            vehicle=veh_exit,
            entry_gate=in_gate,
            license_plate=veh_exit.license_plate,
            license_plate_norm=veh_exit.license_plate_norm,
            entry_time=timezone.now() - timedelta(hours=2),
            recognition_source="AI",
            review_status="AUTO",
        )

        coordinator, _ = _build_coordinator(
            [in_gate, out_gate], fake_clock, pending_recheck_seconds=5.0
        )

        # t=1000.0: create both pending items
        coordinator._evaluate_and_execute(
            in_gate, entry_plate, _make_scan_result(entry_plate, 96.0)
        )
        coordinator._evaluate_and_execute(
            out_gate,
            veh_exit.license_plate,
            _make_scan_result(veh_exit.license_plate, 96.0),
        )

        # Fulfill registration & wallet top-up so any unintended DB query would trigger action
        _make_customer_with_vehicle("k1freg", vtype_car, entry_plate)
        credit_wallet(
            wallet_id=wallet_exit.id,
            amount=Decimal("50000.00"),
            kind="TOPUP_VIETQR",
            idempotency_key=f"k1f-top-{uuid.uuid4().hex[:8]}",
        )

        from apps.parking.services import check_in as check_in_module
        from apps.parking.services import check_out as check_out_module

        # Check silent wait at t=1020.1, t=1035.0, t=1060.0 -> 0 queries, 0 logs, 0 actions
        with (
            patch(
                "apps.parking.services.check_in.check_in_vehicle",
                wraps=check_in_module.check_in_vehicle,
            ) as spy_checkin,
            patch(
                "apps.parking.services.check_out.check_out_vehicle",
                wraps=check_out_module.check_out_vehicle,
            ) as spy_checkout,
        ):
            for delta in (20.1, 14.9, 25.0):
                fake_clock.advance(delta)
                caplog.clear()
                with (
                    caplog.at_level(logging.DEBUG),
                    django_assert_num_queries(0),
                ):
                    coordinator._recheck_pending_entries(in_gate)
                    coordinator._recheck_pending_exits(out_gate)
                assert len(caplog.records) == 0
                assert spy_checkin.call_count == 0
                assert spy_checkout.call_count == 0
                assert (in_gate.id, entry_norm) in coordinator._pending_entries
                assert (
                    out_gate.id,
                    veh_exit.license_plate_norm,
                ) in coordinator._pending_exits

        # Now prove re-sighting at t=1055.0 (simulated via fresh cycle at t=2000 -> silent at 2030 -> seen at 2055 -> rechecks at 2060)
        coordinator._pending_entries.clear()
        coordinator._pending_exits.clear()
        fake_clock.advance(940.0)  # t=2000.0
        entry_plate2 = "51F-200.02"
        entry_norm2 = "51F20002"
        Vehicle.all_objects.filter(license_plate_norm=entry_norm2).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )
        coordinator._evaluate_and_execute(
            in_gate, entry_plate2, _make_scan_result(entry_plate2, 96.0)
        )
        _make_customer_with_vehicle("k1freg2", vtype_car, entry_plate2)
        fake_clock.advance(55.0)  # t=2055.0 (still <= 60s, silent window)
        # Sighting refreshes last_seen_at -> 2055.0 (via _touch_pending_plate or _evaluate)
        coordinator._touch_pending_plate(
            in_gate.id, entry_plate2, now_mono=fake_clock()
        )
        fake_clock.advance(5.0)  # t=2060.0 (5s since 2055.0 <= 20s)
        coordinator._recheck_pending_entries(in_gate)
        assert VehicleEntryExitLog.objects.filter(
            license_plate_norm=entry_norm2, exit_time__isnull=True
        ).exists()

    def test_k1_refresh_last_seen_at_on_ignored_readings_cooldown_and_same_decision(
        self, fake_clock: FakeClock
    ):
        """(g1) Refreshes last_seen_at on voter cooldown, partial vote, same decision, and stationary NO_MOTION probe."""
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        assert in_gate is not None

        plate = "51G-300.01"
        norm_plate = "51G30001"
        Vehicle.all_objects.filter(license_plate_norm=norm_plate).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )

        coordinator, readers = _build_coordinator(
            [in_gate],
            fake_clock,
            pending_recheck_seconds=5.0,
            use_real_motion_filter=True,
        )

        logs_before = ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=in_gate.id,
            action="GATE_AUTO_NEEDS_STAFF",
        ).count()

        # t=1000.0: pending entry created
        coordinator._evaluate_and_execute(
            in_gate, plate, _make_scan_result(plate, 96.0)
        )
        entry = coordinator._pending_entries[(in_gate.id, norm_plate)]

        # 1. Ignored due to voter cooldown
        coordinator._voter.set_cooldown(in_gate.id, plate, seconds=30, now=1000.0)
        fake_clock.advance(18.0)  # t=1018.0
        readers[in_gate.id].get_latest_frame.return_value = (
            _make_distinct_frame(20),
            fake_clock(),
        )
        mock_recognizer = MagicMock()
        # Different raw formatting ("51g 300.01") must normalize and refresh
        mock_recognizer.recognize.return_value = _make_scan_result("51g 300.01", 95.0)
        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_recognizer,
        ):
            coordinator._process_gate_tick(in_gate)
        assert entry.get("last_seen_at") == 1018.0

        # 2. Ignored due to partial voting (< 3/4 frames)
        fake_clock.advance(13.0)  # t=1031.0 (cooldown expired)
        readers[in_gate.id].get_latest_frame.return_value = (
            _make_distinct_frame(90),
            fake_clock(),
        )
        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_recognizer,
        ):
            coordinator._process_gate_tick(in_gate)
        assert entry.get("last_seen_at") == 1031.0

        # 3. Repeated same decision (_evaluate_and_execute)
        fake_clock.advance(11.0)  # t=1042.0
        coordinator._evaluate_and_execute(
            in_gate, plate, _make_scan_result(plate, 96.0)
        )
        assert entry.get("last_seen_at") == 1042.0
        assert (
            ActivityLog.objects.filter(
                entity_type="parking_gate",
                entity_id=in_gate.id,
                action="GATE_AUTO_NEEDS_STAFF",
            ).count()
            == logs_before + 1
        )

        # 4. Stationary vehicle (identical frame -> NO_MOTION) triggers presence probe every pending_recheck_seconds
        fake_clock.advance(8.0)  # t=1050.0 (>= 5.0s probe interval)
        readers[in_gate.id].get_latest_frame.return_value = (
            _make_distinct_frame(90),  # Identical to previous frame -> NO_MOTION!
            fake_clock(),
        )
        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_recognizer,
        ):
            coordinator._process_gate_tick(in_gate)
        assert entry.get("last_seen_at") == 1050.0

    def test_k1_fresh_sighting_checked_at_exact_moment_of_action(
        self, fake_clock: FakeClock
    ):
        """(g2) D1(4): If sighting ages past seen_seconds during DB lookup, check_in/check_out is aborted."""
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        assert in_gate and out_gate
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None

        # 1. Entry freshness check right before check_in_vehicle
        entry_plate = "51G-400.01"
        entry_norm = "51G40001"
        Vehicle.all_objects.filter(license_plate_norm=entry_norm).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )
        coordinator, _ = _build_coordinator(
            [in_gate, out_gate], fake_clock, pending_recheck_seconds=5.0
        )
        coordinator._evaluate_and_execute(
            in_gate, entry_plate, _make_scan_result(entry_plate, 96.0)
        )
        _make_customer_with_vehicle("k1g2a", vtype_car, entry_plate)

        fake_clock.advance(10.0)  # t=1010.0 (still seen <= 20s)
        from apps.parking.selectors import vehicles as veh_selectors
        from apps.parking.services import check_in as check_in_module

        real_get_ctx = veh_selectors.get_combined_vehicle_context

        def _advance_clock_on_ctx(*args, **kwargs):
            fake_clock.advance(25.0)  # becomes 35s > 20s right before action!
            return real_get_ctx(*args, **kwargs)

        with (
            patch(
                "apps.parking.gate_worker.coordinator.get_combined_vehicle_context",
                side_effect=_advance_clock_on_ctx,
            ),
            patch(
                "apps.parking.services.check_in.check_in_vehicle",
                wraps=check_in_module.check_in_vehicle,
            ) as spy_checkin,
        ):
            coordinator._recheck_pending_entries(in_gate)
        assert spy_checkin.call_count == 0
        assert not VehicleEntryExitLog.objects.filter(
            license_plate_norm=entry_norm, exit_time__isnull=True
        ).exists()

        # 2. Exit freshness check right before check_out_vehicle
        exit_plate = f"51G-{uuid.uuid4().int % 90000 + 10000}"
        _, _, veh_exit, wallet_exit = _make_customer_with_vehicle(
            "k1g2b", vtype_car, exit_plate, initial_balance=Decimal("1000.00")
        )
        session = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-G2-{uuid.uuid4().hex[:6].upper()}",
            vehicle=veh_exit,
            entry_gate=in_gate,
            license_plate=veh_exit.license_plate,
            license_plate_norm=veh_exit.license_plate_norm,
            entry_time=timezone.now() - timedelta(hours=2),
            recognition_source="AI",
            review_status="AUTO",
        )
        coordinator._evaluate_and_execute(
            out_gate,
            veh_exit.license_plate,
            _make_scan_result(veh_exit.license_plate, 96.0),
        )
        credit_wallet(
            wallet_id=wallet_exit.id,
            amount=Decimal("50000.00"),
            kind="TOPUP_VIETQR",
            idempotency_key=f"g2b-{uuid.uuid4().hex[:8]}",
        )
        fake_clock.advance(10.0)  # 10s <= 20s

        from apps.parking.services import check_out as check_out_module
        from apps.parking.services import tariff as tariff_module

        real_calc_fee = tariff_module.calculate_parking_fee

        def _advance_clock_on_fee(*args, **kwargs):
            fake_clock.advance(25.0)  # 35s > 20s right before check_out_vehicle!
            return real_calc_fee(*args, **kwargs)

        with (
            patch(
                "apps.parking.gate_worker.coordinator.calculate_parking_fee",
                side_effect=_advance_clock_on_fee,
            ),
            patch(
                "apps.parking.services.check_out.check_out_vehicle",
                wraps=check_out_module.check_out_vehicle,
            ) as spy_checkout,
        ):
            coordinator._recheck_pending_exits(out_gate)
        assert spy_checkout.call_count == 0
        session.refresh_from_db()
        assert session.exit_time is None

    def test_k1_two_gates_same_plate_per_gate_isolation(
        self, fake_clock: FakeClock, django_assert_num_queries
    ):
        """(h) Same plate pending on two gates keeps independent liveness, silent wait, and eviction."""
        g1, g2 = _ensure_two_active_in_gates()
        plate = "51H-500.01"
        norm_plate = "51H50001"
        Vehicle.all_objects.filter(license_plate_norm=norm_plate).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )

        coordinator, _ = _build_coordinator(
            [g1, g2], fake_clock, pending_recheck_seconds=5.0
        )

        # t=1000.0: both gates record pending entry for same plate
        coordinator._evaluate_and_execute(g1, plate, _make_scan_result(plate, 96.0))
        coordinator._evaluate_and_execute(g2, plate, _make_scan_result(plate, 96.0))

        # t=1018.0: only g1 sees the plate again
        fake_clock.advance(18.0)
        coordinator._evaluate_and_execute(g1, plate, _make_scan_result(plate, 96.0))

        # t=1025.0: g2 is in silent wait (25s > 20s -> 0 queries), g1 is still active (7s <= 20s)
        fake_clock.advance(7.0)
        with django_assert_num_queries(0):
            coordinator._recheck_pending_entries(g2)
        assert (g2.id, norm_plate) in coordinator._pending_entries
        assert (g1.id, norm_plate) in coordinator._pending_entries

        # t=1050.0: g1 sees plate again; t=1065.0: g2 evicted (>60s), g1 still alive (15s <= 20s)
        fake_clock.advance(25.0)  # t=1050.0
        coordinator._evaluate_and_execute(g1, plate, _make_scan_result(plate, 96.0))
        fake_clock.advance(15.0)  # t=1065.0

        coordinator._recheck_pending_entries(g2)
        assert (g2.id, norm_plate) not in coordinator._pending_entries
        assert (g1.id, norm_plate) in coordinator._pending_entries

        # Register vehicle -> g1 checks it in cleanly without touching g2
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None
        _make_customer_with_vehicle("k1h", vtype_car, plate)
        coordinator._recheck_pending_entries(g1)
        assert (g1.id, norm_plate) not in coordinator._pending_entries
        assert VehicleEntryExitLog.objects.filter(
            license_plate_norm=norm_plate, exit_time__isnull=True
        ).exists()

    def test_k1_bounded_memory_cap_per_gate_evicts_oldest(self, fake_clock: FakeClock):
        """(i) Per-gate bounded pending cap evicts oldest item by (last_seen_at, first_seen_at) without touching other gates."""
        g1, g2 = _ensure_two_active_in_gates()
        out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        assert out_gate is not None
        lot = ParkingLot.objects.first()
        assert lot is not None
        out_gate2 = ParkingGate.objects.create(
            lot=lot,
            code=f"OUT_T{uuid.uuid4().hex[:4].upper()}",
            name="Test Out Gate 2",
            direction="OUT",
            is_active=True,
            is_auto_scan=True,
        )

        coordinator, _ = _build_coordinator(
            [g1, g2, out_gate, out_gate2],
            fake_clock,
            pending_recheck_seconds=5.0,
            pending_max_per_gate=3,
        )

        # 1. Pending entries cap=3 on g1
        plates = ["51I-000.01", "51I-000.02", "51I-000.03", "51I-000.04"]
        for p in plates:
            norm = PlateRecognizer.normalize_plate(p) or p
            Vehicle.all_objects.filter(license_plate_norm=norm).update(
                deleted_at=timezone.now(), deleted_by_id=None
            )

        coordinator._evaluate_and_execute(
            g2, "51I-999.99", _make_scan_result("51I-999.99", 96.0)
        )
        for p in plates:
            fake_clock.advance(1.0)
            coordinator._evaluate_and_execute(g1, p, _make_scan_result(p, 96.0))

        g1_entries = [k for k in coordinator._pending_entries if k[0] == g1.id]
        assert len(g1_entries) <= 3
        assert len(g1_entries) == 3
        assert (g1.id, "51I00001") not in coordinator._pending_entries
        assert (g1.id, "51I00002") in coordinator._pending_entries
        assert (g1.id, "51I00003") in coordinator._pending_entries
        assert (g1.id, "51I00004") in coordinator._pending_entries
        assert (g2.id, "51I99999") in coordinator._pending_entries

        # 2. Pending exits cap=3 on out_gate
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None
        in_gate = g1
        _, _, veh_q, _ = _make_customer_with_vehicle(
            "k1iq",
            vtype_car,
            f"51Q-{uuid.uuid4().int % 90000 + 10000}",
            initial_balance=Decimal("1000.00"),
        )
        VehicleEntryExitLog.objects.create(
            session_code=f"#PK-IQ-{uuid.uuid4().hex[:6].upper()}",
            vehicle=veh_q,
            entry_gate=in_gate,
            license_plate=veh_q.license_plate,
            license_plate_norm=veh_q.license_plate_norm,
            entry_time=timezone.now() - timedelta(hours=2),
            recognition_source="AI",
            review_status="AUTO",
        )
        coordinator._evaluate_and_execute(
            out_gate2, veh_q.license_plate, _make_scan_result(veh_q.license_plate, 96.0)
        )

        exit_norms: list[str] = []
        for idx in range(4):
            fake_clock.advance(1.0)
            _, _, veh_x, _ = _make_customer_with_vehicle(
                f"k1ix{idx}",
                vtype_car,
                f"51X-{uuid.uuid4().int % 90000 + 10000}",
                initial_balance=Decimal("1000.00"),
            )
            VehicleEntryExitLog.objects.create(
                session_code=f"#PK-IX{idx}-{uuid.uuid4().hex[:6].upper()}",
                vehicle=veh_x,
                entry_gate=in_gate,
                license_plate=veh_x.license_plate,
                license_plate_norm=veh_x.license_plate_norm,
                entry_time=timezone.now() - timedelta(hours=2),
                recognition_source="AI",
                review_status="AUTO",
            )
            exit_norms.append(veh_x.license_plate_norm)
            coordinator._evaluate_and_execute(
                out_gate,
                veh_x.license_plate,
                _make_scan_result(veh_x.license_plate, 96.0),
            )

        out1_exits = [k for k in coordinator._pending_exits if k[0] == out_gate.id]
        assert len(out1_exits) <= 3
        assert len(out1_exits) == 3
        assert (out_gate.id, exit_norms[0]) not in coordinator._pending_exits
        assert (out_gate2.id, veh_q.license_plate_norm) in coordinator._pending_exits

    def test_k1_pending_thread_safety_stress(self, fake_clock: FakeClock):
        """(j) Concurrent writers, recheckers, touchers, and gate releasers produce zero exceptions and bounded state."""
        g1 = MagicMock(spec=ParkingGate)
        g1.id = 901
        g1.code = "IN_STRESS_1"
        g1.name = "Stress IN 1"
        g1.direction = "IN"
        g1.is_active = True
        g1.is_auto_scan = True
        g1.lot_id = 1
        g1.camera_status = "ONLINE"

        g2 = MagicMock(spec=ParkingGate)
        g2.id = 902
        g2.code = "OUT_STRESS_2"
        g2.name = "Stress OUT 2"
        g2.direction = "OUT"
        g2.is_active = True
        g2.is_auto_scan = True
        g2.lot_id = 1
        g2.camera_status = "ONLINE"

        cap = 10
        coordinator, _ = _build_coordinator(
            [g1, g2],
            fake_clock,
            pending_recheck_seconds=0.0,
            pending_max_per_gate=cap,
        )
        assert hasattr(coordinator, "_pending_lock"), (
            "Coordinator must expose _pending_lock (RLock)"
        )

        errors: list[Exception] = []
        barrier = threading.Barrier(9)

        unreg_ctx = MagicMock()
        unreg_ctx.vehicle = None
        unreg_ctx.is_blacklisted = False
        unreg_ctx.active_ticket = None
        unreg_ctx.open_session = None
        unreg_ctx.open_session_data = None
        unreg_ctx.customer = None
        unreg_ctx.wallet = None

        exit_ctx = MagicMock()
        exit_ctx.vehicle = MagicMock(id=500, vehicle_type_id=1, vehicle_type=None)
        exit_ctx.is_blacklisted = False
        exit_ctx.active_ticket = None
        exit_ctx.open_session = MagicMock(id=777, session_code="#PK-STRESS")
        exit_ctx.open_session_data = {"id": 777, "session_code": "#PK-STRESS"}
        exit_ctx.customer = MagicMock(id=50, account_id=60)
        exit_ctx.wallet = MagicMock(balance=Decimal("1000.00"), status="ACTIVE")

        def _fake_ctx(plate_str, include_open_session=True):
            return exit_ctx if plate_str.startswith("51O") else unreg_ctx

        from django.db import close_old_connections

        with (
            patch.object(
                coordinator, "_resolve_entry_slot", return_value=(None, None, None)
            ),
            patch(
                "apps.parking.gate_worker.coordinator.get_combined_vehicle_context",
                side_effect=_fake_ctx,
            ),
            patch(
                "apps.parking.gate_worker.coordinator.calculate_parking_fee",
                return_value=Decimal("20000.00"),
            ),
            patch("apps.parking.gate_worker.coordinator.ActivityLog.objects.create"),
            patch("apps.parking.gate_worker.coordinator.Notification.objects.create"),
            patch(
                "apps.parking.gate_worker.coordinator.Vehicle.objects.filter"
            ) as mock_vf,
            patch(
                "apps.parking.gate_worker.coordinator.VehicleEntryExitLog.objects.select_related"
            ) as mock_sl,
            patch(
                "apps.parking.gate_worker.coordinator.Wallet.objects.filter"
            ) as mock_wf,
            patch("apps.parking.gate_worker.coordinator.ParkingGate.objects.filter"),
        ):
            mock_vf.return_value.only.return_value.first.return_value = None
            mock_sl.return_value.filter.return_value.first.return_value = MagicMock(
                id=777, session_code="#PK-STRESS"
            )
            mock_wf.return_value.only.return_value.first.return_value = MagicMock(
                id=1, balance=Decimal("1000.00"), status="ACTIVE"
            )

            def _writer(tid: int):
                try:
                    barrier.wait(timeout=5.0)
                    for i in range(60):
                        fake_clock.advance(0.05)
                        in_p = f"51I-{tid:01d}{i % 20:02d}.00"
                        out_p = f"51O-{tid:01d}{i % 20:02d}.00"
                        coordinator._evaluate_and_execute(
                            g1, in_p, _make_scan_result(in_p, 96.0)
                        )
                        coordinator._evaluate_and_execute(
                            g2, out_p, _make_scan_result(out_p, 96.0)
                        )
                except Exception as exc:
                    errors.append(exc)
                finally:
                    close_old_connections()

            def _rechecker():
                try:
                    barrier.wait(timeout=5.0)
                    for _ in range(60):
                        coordinator._recheck_pending_entries(g1)
                        coordinator._recheck_pending_exits(g2)
                except Exception as exc:
                    errors.append(exc)
                finally:
                    close_old_connections()

            def _toucher(tid: int):
                try:
                    barrier.wait(timeout=5.0)
                    for i in range(60):
                        if hasattr(coordinator, "_touch_pending_plate"):
                            coordinator._touch_pending_plate(
                                g1.id, f"51I-0{i % 20:02d}.00"
                            )
                        if tid == 0 and i % 20 == 19:
                            coordinator._release_gate(g1.id)
                            g1.is_active = True
                            coordinator._managed_gates[g1.id] = g1
                except Exception as exc:
                    errors.append(exc)
                finally:
                    close_old_connections()

            threads = (
                [threading.Thread(target=_writer, args=(t,)) for t in range(3)]
                + [threading.Thread(target=_rechecker) for _ in range(3)]
                + [threading.Thread(target=_toucher, args=(t,)) for t in range(3)]
            )
            for th in threads:
                th.start()
            for th in threads:
                th.join(timeout=15.0)

        assert errors == [], f"Thread safety errors occurred: {errors}"
        g1_count = sum(1 for k in coordinator._pending_entries if k[0] == g1.id)
        g2_count = sum(1 for k in coordinator._pending_exits if k[0] == g2.id)
        assert g1_count <= cap
        assert g2_count <= cap

    def test_coordinator_accepts_injectable_clock_and_settings_default(self):
        """(k) GateWorkerCoordinator accepts injectable clock & pending_max_per_gate; setting default is 20."""
        assert getattr(settings, "GATE_WORKER_PENDING_SEEN_SECONDS", None) == 20
        clk = FakeClock(5000.0)
        coord = GateWorkerCoordinator(
            streams_override={},
            clock=clk,
            pending_max_per_gate=12,
        )
        assert coord._clock() == 5000.0
        assert coord._voter._clock() == 5000.0
        assert coord._pending_max_per_gate == 12
        clk.advance(7.5)
        assert coord._now_monotonic() == 5007.5

    def test_k1_empty_road_after_4_of_4_frames_does_not_refresh_or_log_needs_review(
        self, fake_clock: FakeClock
    ):
        """
        Regression (Defect 1):
        - 4/4 frames [A, A, A, A] followed by empty road (OCR -> None) must NOT refresh last_seen_at,
          must NOT create ActivityLog(NEEDS_REVIEW), must NOT set voter cooldown, and evicts cleanly > 60s.
        - [A, A, A, X] with different plate X != A must NOT refresh A's last_seen_at.
        """
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        assert in_gate is not None

        plate_a = "51P-111.02"
        norm_a = "51P11102"
        plate_x = "51X-222.03"
        norm_x = "51X22203"
        for norm in (norm_a, norm_x):
            Vehicle.all_objects.filter(license_plate_norm=norm).update(
                deleted_at=timezone.now(), deleted_by_id=None
            )
            VehicleEntryExitLog.objects.filter(
                license_plate_norm=norm, exit_time__isnull=True
            ).update(exit_time=timezone.now())

        coordinator, readers = _build_coordinator(
            [in_gate],
            fake_clock,
            pending_recheck_seconds=5.0,
            use_real_motion_filter=True,
        )
        mock_rec = MagicMock()

        def _empty_scan_result() -> PlateScanResult:
            return PlateScanResult(
                candidates=[],
                best_candidate=None,
                engine_name="mock_ocr",
                raw_text="",
                latency_ms=5.0,
                review_status="NEEDS_REVIEW",
            )

        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_rec,
        ):
            # 4 frames of plate A: 3 arrival frames + 1 NO_MOTION presence probe -> [A, A, A, A]
            mock_rec.recognize.return_value = _make_scan_result(plate_a, 96.5)
            for idx in range(3):
                fake_clock.advance(0.5)
                readers[in_gate.id].get_latest_frame.return_value = (
                    _make_distinct_frame(20 + idx * 35),
                    fake_clock(),
                )
                coordinator._process_gate_tick(in_gate)

            fake_clock.advance(5.5)
            readers[in_gate.id].get_latest_frame.return_value = (
                _make_distinct_frame(90),
                fake_clock(),
            )
            coordinator._process_gate_tick(in_gate)

            entry_a = coordinator._pending_entries.get((in_gate.id, norm_a))
            assert entry_a is not None
            last_seen_after_4 = float(entry_a["last_seen_at"])
            audit_count_before = ActivityLog.objects.filter(
                entity_type="parking_gate",
                entity_id=in_gate.id,
            ).count()

            # Advance 25s into silent wait (20s, 60s]; feed empty road frame (OCR -> None)
            fake_clock.advance(25.0)
            mock_rec.recognize.return_value = _empty_scan_result()
            readers[in_gate.id].get_latest_frame.return_value = (
                _make_distinct_frame(140),
                fake_clock(),
            )
            coordinator._process_gate_tick(in_gate)

            assert (
                coordinator._pending_entries[(in_gate.id, norm_a)]["last_seen_at"]
                == last_seen_after_4
            )
            assert (
                ActivityLog.objects.filter(
                    entity_type="parking_gate",
                    entity_id=in_gate.id,
                ).count()
                == audit_count_before
            )
            assert (
                coordinator._voter.is_in_cooldown(in_gate.id, plate_a, now=fake_clock())
                is False
            )

            # Advance past 60s unseen timeout -> pending entry evicts cleanly
            fake_clock.advance(36.0)
            readers[in_gate.id].get_latest_frame.return_value = (None, 0.0)
            coordinator._process_gate_tick(in_gate)
            assert (in_gate.id, norm_a) not in coordinator._pending_entries

            # Now verify [A, A, A, X] (X != A) does NOT refresh A's last_seen_at
            coordinator._voter.reset_gate(in_gate.id)
            mock_rec.recognize.return_value = _make_scan_result(plate_a, 96.5)
            for idx in range(3):
                fake_clock.advance(2.5)
                readers[in_gate.id].get_latest_frame.return_value = (
                    _make_distinct_frame(170 + idx * 25),
                    fake_clock(),
                )
                coordinator._process_gate_tick(in_gate)

            entry_a2 = coordinator._pending_entries.get((in_gate.id, norm_a))
            assert entry_a2 is not None
            last_seen_a2 = float(entry_a2["last_seen_at"])

            # Advance 25s and feed different plate X -> voter window [A, A, A, X] returns (True, A)
            fake_clock.advance(25.0)
            mock_rec.recognize.return_value = _make_scan_result(plate_x, 96.5)
            readers[in_gate.id].get_latest_frame.return_value = (
                _make_distinct_frame(245),
                fake_clock(),
            )
            coordinator._process_gate_tick(in_gate)

            assert (
                coordinator._pending_entries[(in_gate.id, norm_a)]["last_seen_at"]
                == last_seen_a2
            )

    def test_k1_touch_pending_plate_with_stale_ts_does_not_resurrect_or_regress(
        self, fake_clock: FakeClock
    ):
        """
        Regression (Defect 2):
        - Stale now_mono passed after pending entry has expired by current clock must evict, NOT resurrect.
        - Stale now_mono passed while entry is still alive must NOT move last_seen_at backwards.
        """
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        assert in_gate is not None

        # Set clock to 4000.0
        fake_clock.advance(4000.0 - fake_clock())
        assert fake_clock() == 4000.0

        plate1 = "51W-100.02"
        norm1 = "51W10002"
        plate2 = "51W-100.03"
        norm2 = "51W10003"
        for norm in (norm1, norm2):
            Vehicle.all_objects.filter(license_plate_norm=norm).update(
                deleted_at=timezone.now(), deleted_by_id=None
            )

        coordinator, _ = _build_coordinator(
            [in_gate], fake_clock, pending_recheck_seconds=5.0
        )

        # Create pending entry for plate1 at t=4000.0
        coordinator._evaluate_and_execute(
            in_gate, plate1, _make_scan_result(plate1, 96.5)
        )
        assert (in_gate.id, norm1) in coordinator._pending_entries
        assert (
            coordinator._pending_entries[(in_gate.id, norm1)]["last_seen_at"] == 4000.0
        )

        # Advance to t=4070.0 (> 60s unseen limit); stale now_mono=4015.0 must evict, NOT resurrect
        fake_clock.advance(70.0)
        assert fake_clock() == 4070.0
        coordinator._touch_pending_plate(in_gate.id, plate1, now_mono=4015.0)
        assert coordinator._pending_entries.get((in_gate.id, norm1)) is None

        # Create pending entry for plate2 at t=4070.0, touch at t=4088.0 (alive: 18s <= 20s)
        coordinator._evaluate_and_execute(
            in_gate, plate2, _make_scan_result(plate2, 96.5)
        )
        fake_clock.advance(18.0)
        assert fake_clock() == 4088.0
        coordinator._touch_pending_plate(in_gate.id, plate2, now_mono=4088.0)
        assert (
            coordinator._pending_entries[(in_gate.id, norm2)]["last_seen_at"] == 4088.0
        )

        # Stale now_mono=4080.0 while alive must NOT move last_seen_at backwards
        coordinator._touch_pending_plate(in_gate.id, plate2, now_mono=4080.0)
        assert (
            coordinator._pending_entries[(in_gate.id, norm2)]["last_seen_at"] == 4088.0
        )

    def test_k1_cross_plate_spillover_in_gate_unregistered_does_not_checkin_a(
        self, fake_clock: FakeClock
    ):
        """
        Regression [A, A, A, X] (i):
        IN gate: [A, A, A] pending UNREGISTERED_VEHICLE -> A leaves -> 25s silent wait ->
        A registers -> X arrives ([A, A, A, X]): A must NOT be checked in; subsequent [X, X]
        completes [A, X, X, X] for X cleanly.
        """
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        assert in_gate is not None
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None

        plate_a = f"51A-{uuid.uuid4().int % 90000 + 10000}"
        norm_a = PlateRecognizer.normalize_plate(plate_a) or plate_a
        plate_x = f"51X-{uuid.uuid4().int % 90000 + 10000}"
        norm_x = PlateRecognizer.normalize_plate(plate_x) or plate_x

        for norm in (norm_a, norm_x):
            Vehicle.all_objects.filter(license_plate_norm=norm).update(
                deleted_at=timezone.now(), deleted_by_id=None
            )
            VehicleEntryExitLog.objects.filter(
                license_plate_norm=norm, exit_time__isnull=True
            ).update(exit_time=timezone.now())

        # X is a registered customer vehicle; A is initially unregistered
        _make_customer_with_vehicle("k1x_reg", vtype_car, plate_x)

        coordinator, readers = _build_coordinator(
            [in_gate],
            fake_clock,
            pending_recheck_seconds=5.0,
            use_real_motion_filter=True,
        )
        mock_rec = MagicMock()

        avail_slots_before = ParkingSlot.objects.filter(
            zone__floor__lot_id=in_gate.lot_id,
            status="AVAILABLE",
            deleted_at__isnull=True,
        ).count()
        checkin_audit_before = ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=in_gate.id,
            action="GATE_AUTO_CHECK_IN",
        ).count()

        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_rec,
        ):
            # 3 frames of A -> [A, A, A] stable -> pending UNREGISTERED_VEHICLE
            mock_rec.recognize.return_value = _make_scan_result(plate_a, 96.5)
            for idx in range(3):
                fake_clock.advance(0.5)
                readers[in_gate.id].get_latest_frame.return_value = (
                    _make_distinct_frame(10 + idx * 35),
                    fake_clock(),
                )
                coordinator._process_gate_tick(in_gate)

            assert (in_gate.id, norm_a) in coordinator._pending_entries

            # A leaves; 25s silent wait passes; A registers remotely
            fake_clock.advance(25.0)
            _make_customer_with_vehicle("k1a_late", vtype_car, plate_a)

            # Different vehicle X arrives -> voter window [A, A, A, X] returns (True, A)
            mock_rec.recognize.return_value = _make_scan_result(plate_x, 96.5)
            readers[in_gate.id].get_latest_frame.return_value = (
                _make_distinct_frame(120),
                fake_clock(),
            )
            coordinator._process_gate_tick(in_gate)

            assert not VehicleEntryExitLog.objects.filter(
                license_plate_norm=norm_a, exit_time__isnull=True
            ).exists()
            assert (
                ParkingSlot.objects.filter(
                    zone__floor__lot_id=in_gate.lot_id,
                    status="AVAILABLE",
                    deleted_at__isnull=True,
                ).count()
                == avail_slots_before
            )
            assert (
                ActivityLog.objects.filter(
                    entity_type="parking_gate",
                    entity_id=in_gate.id,
                    action="GATE_AUTO_CHECK_IN",
                ).count()
                == checkin_audit_before
            )

            # Subsequent 2 frames of X ([A, A, X, X] -> [A, X, X, X]) check in X cleanly
            for idx in range(2):
                fake_clock.advance(0.5)
                readers[in_gate.id].get_latest_frame.return_value = (
                    _make_distinct_frame(160 + idx * 35),
                    fake_clock(),
                )
                coordinator._process_gate_tick(in_gate)

            assert VehicleEntryExitLog.objects.filter(
                license_plate_norm=norm_x, exit_time__isnull=True
            ).exists()
            assert not VehicleEntryExitLog.objects.filter(
                license_plate_norm=norm_a, exit_time__isnull=True
            ).exists()

    def test_k1_cross_plate_spillover_out_gate_wallet_insufficient_does_not_checkout_or_debit_b(
        self, fake_clock: FakeClock
    ):
        """
        Regression [B, B, B, X] (ii):
        OUT gate: [B, B, B] pending WALLET_INSUFFICIENT -> B leaves -> 25s silent wait ->
        B tops up wallet -> X arrives ([B, B, B, X]): B must NOT be checked out or debited.
        """
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        assert in_gate and out_gate
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None

        plate_b = f"51B-{uuid.uuid4().int % 90000 + 10000}"
        plate_x = f"51Y-{uuid.uuid4().int % 90000 + 10000}"
        _, _, veh_b, wallet_b = _make_customer_with_vehicle(
            "k1b_out", vtype_car, plate_b, initial_balance=Decimal("5000.00")
        )
        session_b = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-K1B-{uuid.uuid4().hex[:6].upper()}",
            vehicle=veh_b,
            entry_gate=in_gate,
            license_plate=veh_b.license_plate,
            license_plate_norm=veh_b.license_plate_norm,
            entry_time=timezone.now() - timedelta(hours=2),  # fee = 20,000 VND
            recognition_source="AI",
            review_status="AUTO",
        )

        coordinator, readers = _build_coordinator(
            [out_gate],
            fake_clock,
            pending_recheck_seconds=5.0,
            use_real_motion_filter=True,
        )
        mock_rec = MagicMock()
        checkout_audit_before = ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=out_gate.id,
            action="GATE_AUTO_CHECK_OUT",
        ).count()

        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_rec,
        ):
            # 3 frames of B at OUT gate -> WALLET_INSUFFICIENT pending exit
            mock_rec.recognize.return_value = _make_scan_result(plate_b, 96.5)
            for idx in range(3):
                fake_clock.advance(0.5)
                readers[out_gate.id].get_latest_frame.return_value = (
                    _make_distinct_frame(20 + idx * 35),
                    fake_clock(),
                )
                coordinator._process_gate_tick(out_gate)

            assert (out_gate.id, veh_b.license_plate_norm) in coordinator._pending_exits

            # B leaves; 25s silent wait passes; B tops up wallet to 55,000 VND
            fake_clock.advance(25.0)
            credit_wallet(
                wallet_id=wallet_b.id,
                amount=Decimal("50000.00"),
                kind="TOPUP_VIETQR",
                idempotency_key=f"k1b-topup-{uuid.uuid4().hex[:8]}",
            )

            # Different vehicle X arrives -> voter window [B, B, B, X] returns (True, B)
            mock_rec.recognize.return_value = _make_scan_result(plate_x, 96.5)
            readers[out_gate.id].get_latest_frame.return_value = (
                _make_distinct_frame(140),
                fake_clock(),
            )
            coordinator._process_gate_tick(out_gate)

            session_b.refresh_from_db()
            wallet_b.refresh_from_db()
            assert session_b.exit_time is None
            assert wallet_b.balance == Decimal("55000.00")
            assert (
                WalletTransaction.objects.filter(
                    wallet=wallet_b, kind="PARKING_FEE"
                ).count()
                == 0
            )
            assert Payment.objects.filter(session=session_b).count() == 0
            assert (
                ActivityLog.objects.filter(
                    entity_type="parking_gate",
                    entity_id=out_gate.id,
                    action="GATE_AUTO_CHECK_OUT",
                ).count()
                == checkout_audit_before
            )

    def test_k1_cross_plate_spillover_post_eviction_does_not_resurrect_or_log(
        self, fake_clock: FakeClock
    ):
        """
        Regression [C, C, C, X] (iii):
        Post-eviction >60s: [C, C, C] pending -> 62s evicted -> X arrives ([C, C, C, X]):
        C must NOT be resurrected into _pending_entries/_pending_exits and must NOT create
        extra ActivityLog or Notification.
        """
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        assert in_gate and out_gate
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None

        plate_c_in = f"51C-{uuid.uuid4().int % 90000 + 10000}"
        norm_c_in = PlateRecognizer.normalize_plate(plate_c_in) or plate_c_in
        plate_x_in = f"51Z-{uuid.uuid4().int % 90000 + 10000}"
        for norm in (norm_c_in, PlateRecognizer.normalize_plate(plate_x_in)):
            Vehicle.all_objects.filter(license_plate_norm=norm).update(
                deleted_at=timezone.now(), deleted_by_id=None
            )

        plate_c_out = f"51D-{uuid.uuid4().int % 90000 + 10000}"
        plate_x_out = f"51W-{uuid.uuid4().int % 90000 + 10000}"
        acct_out, _, veh_c_out, _ = _make_customer_with_vehicle(
            "k1c_out", vtype_car, plate_c_out, initial_balance=Decimal("1000.00")
        )
        VehicleEntryExitLog.objects.create(
            session_code=f"#PK-K1C-{uuid.uuid4().hex[:6].upper()}",
            vehicle=veh_c_out,
            entry_gate=in_gate,
            license_plate=veh_c_out.license_plate,
            license_plate_norm=veh_c_out.license_plate_norm,
            entry_time=timezone.now() - timedelta(hours=2),
            recognition_source="AI",
            review_status="AUTO",
        )

        coordinator, readers = _build_coordinator(
            [in_gate, out_gate],
            fake_clock,
            pending_recheck_seconds=5.0,
            use_real_motion_filter=True,
        )
        mock_rec = MagicMock()

        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_rec,
        ):
            # --- Part 1: IN gate post-eviction ---
            mock_rec.recognize.return_value = _make_scan_result(plate_c_in, 96.5)
            for idx in range(3):
                fake_clock.advance(0.5)
                readers[in_gate.id].get_latest_frame.return_value = (
                    _make_distinct_frame(15 + idx * 35),
                    fake_clock(),
                )
                coordinator._process_gate_tick(in_gate)
            assert (in_gate.id, norm_c_in) in coordinator._pending_entries

            # --- Part 2: OUT gate post-eviction ---
            mock_rec.recognize.return_value = _make_scan_result(plate_c_out, 96.5)
            for idx in range(3):
                fake_clock.advance(0.5)
                readers[out_gate.id].get_latest_frame.return_value = (
                    _make_distinct_frame(25 + idx * 35),
                    fake_clock(),
                )
                coordinator._process_gate_tick(out_gate)
            assert (
                out_gate.id,
                veh_c_out.license_plate_norm,
            ) in coordinator._pending_exits

            # Advance 62s -> evict both C_in and C_out
            fake_clock.advance(62.0)
            readers[in_gate.id].get_latest_frame.return_value = (None, 0.0)
            readers[out_gate.id].get_latest_frame.return_value = (None, 0.0)
            coordinator._process_gate_tick(in_gate)
            coordinator._process_gate_tick(out_gate)
            assert (in_gate.id, norm_c_in) not in coordinator._pending_entries
            assert (
                out_gate.id,
                veh_c_out.license_plate_norm,
            ) not in coordinator._pending_exits

            in_logs_before = ActivityLog.objects.filter(
                entity_type="parking_gate", entity_id=in_gate.id
            ).count()
            out_logs_before = ActivityLog.objects.filter(
                entity_type="parking_gate", entity_id=out_gate.id
            ).count()
            notifs_before = Notification.objects.filter(
                recipient_account=acct_out
            ).count()

            # X arrives at both gates -> [C, C, C, X]
            mock_rec.recognize.return_value = _make_scan_result(plate_x_in, 96.5)
            readers[in_gate.id].get_latest_frame.return_value = (
                _make_distinct_frame(180),
                fake_clock(),
            )
            coordinator._process_gate_tick(in_gate)

            mock_rec.recognize.return_value = _make_scan_result(plate_x_out, 96.5)
            readers[out_gate.id].get_latest_frame.return_value = (
                _make_distinct_frame(200),
                fake_clock(),
            )
            coordinator._process_gate_tick(out_gate)

            assert (in_gate.id, norm_c_in) not in coordinator._pending_entries
            assert (
                out_gate.id,
                veh_c_out.license_plate_norm,
            ) not in coordinator._pending_exits
            assert (
                ActivityLog.objects.filter(
                    entity_type="parking_gate", entity_id=in_gate.id
                ).count()
                == in_logs_before
            )
            assert (
                ActivityLog.objects.filter(
                    entity_type="parking_gate", entity_id=out_gate.id
                ).count()
                == out_logs_before
            )
            assert (
                Notification.objects.filter(recipient_account=acct_out).count()
                == notifs_before
            )

    def test_k1_cross_plate_spillover_low_confidence_x_does_not_log_or_cooldown_a_or_pause_gate(
        self, fake_clock: FakeClock
    ):
        """
        Regression [A, A, A, X(NEEDS_REVIEW)] (iv):
        [A, A, A] pending -> 25s silent wait -> X arrives with review_status="NEEDS_REVIEW":
        must NOT emit ActivityLog(NEEDS_REVIEW), must NOT set 30s cooldown on A,
        and must NOT block X with 2s gate cooldown pause.
        """
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        assert in_gate is not None
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None

        plate_a = f"51E-{uuid.uuid4().int % 90000 + 10000}"
        norm_a = PlateRecognizer.normalize_plate(plate_a) or plate_a
        plate_x = f"51F-{uuid.uuid4().int % 90000 + 10000}"
        norm_x = PlateRecognizer.normalize_plate(plate_x) or plate_x
        for norm in (norm_a, norm_x):
            Vehicle.all_objects.filter(license_plate_norm=norm).update(
                deleted_at=timezone.now(), deleted_by_id=None
            )
        _make_customer_with_vehicle("k1x_low", vtype_car, plate_x)

        coordinator, readers = _build_coordinator(
            [in_gate],
            fake_clock,
            pending_recheck_seconds=5.0,
            use_real_motion_filter=True,
        )
        mock_rec = MagicMock()

        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_rec,
        ):
            mock_rec.recognize.return_value = _make_scan_result(plate_a, 96.5)
            for idx in range(3):
                fake_clock.advance(0.5)
                readers[in_gate.id].get_latest_frame.return_value = (
                    _make_distinct_frame(15 + idx * 35),
                    fake_clock(),
                )
                coordinator._process_gate_tick(in_gate)

            assert (in_gate.id, norm_a) in coordinator._pending_entries
            audit_before = ActivityLog.objects.filter(
                entity_type="parking_gate", entity_id=in_gate.id
            ).count()

            # 25s silent wait -> X arrives with low confidence (NEEDS_REVIEW)
            fake_clock.advance(25.0)
            x_arrival_ts = fake_clock()
            mock_rec.recognize.return_value = _make_scan_result(
                plate_x, 55.0, review_status="NEEDS_REVIEW"
            )
            readers[in_gate.id].get_latest_frame.return_value = (
                _make_distinct_frame(145),
                x_arrival_ts,
            )
            coordinator._process_gate_tick(in_gate)

            assert (
                ActivityLog.objects.filter(
                    entity_type="parking_gate", entity_id=in_gate.id
                ).count()
                == audit_before
            )
            assert (
                coordinator._voter.is_in_cooldown(in_gate.id, plate_a, now=fake_clock())
                is False
            )
            assert (
                coordinator._gate_cooldown_pause_until.get(in_gate.id, 0.0)
                <= x_arrival_ts
            )

            # Next 2 high-confidence frames of X within < 2s are NOT blocked by gate pause and check in X
            mock_rec.recognize.return_value = _make_scan_result(plate_x, 96.5)
            for idx in range(2):
                fake_clock.advance(0.5)
                readers[in_gate.id].get_latest_frame.return_value = (
                    _make_distinct_frame(180 + idx * 35),
                    fake_clock(),
                )
                coordinator._process_gate_tick(in_gate)

            assert VehicleEntryExitLog.objects.filter(
                license_plate_norm=norm_x, exit_time__isnull=True
            ).exists()

    def test_k1_occlusion_recovery_and_touch_liveness_false_defense_in_depth(
        self, fake_clock: FakeClock
    ):
        """
        Verify:
        - Occlusion patterns [A, A, None, A] and [A, None, A, A] refresh last_seen_at normally.
        - Defense-in-depth: _evaluate_and_execute(..., touch_liveness=False) when existing_pending is None
          does NOT insert pending entries/exits and does NOT emit ActivityLog or Notification.
        """
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        assert in_gate and out_gate
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None

        for seq_idx, pattern in enumerate(
            (["A", "A", None, "A"], ["A", None, "A", "A"])
        ):
            plate = f"51G-{uuid.uuid4().int % 90000 + 10000}"
            norm = PlateRecognizer.normalize_plate(plate) or plate
            Vehicle.all_objects.filter(license_plate_norm=norm).update(
                deleted_at=timezone.now(), deleted_by_id=None
            )
            coordinator, readers = _build_coordinator(
                [in_gate],
                fake_clock,
                pending_recheck_seconds=5.0,
                use_real_motion_filter=True,
            )
            mock_rec = MagicMock()
            empty_res = PlateScanResult(
                candidates=[],
                best_candidate=None,
                engine_name="mock_ocr",
                raw_text="",
                latency_ms=5.0,
                review_status="NEEDS_REVIEW",
            )
            with patch(
                "apps.parking.gate_worker.coordinator.get_plate_recognizer",
                return_value=mock_rec,
            ):
                # Prime pending entry
                mock_rec.recognize.return_value = _make_scan_result(plate, 96.5)
                for idx in range(3):
                    fake_clock.advance(0.5)
                    readers[in_gate.id].get_latest_frame.return_value = (
                        _make_distinct_frame(10 + idx * 35),
                        fake_clock(),
                    )
                    coordinator._process_gate_tick(in_gate)
                assert (in_gate.id, norm) in coordinator._pending_entries

                # Silent wait 25s, then feed occlusion recovery sequence
                fake_clock.advance(25.0)
                coordinator._voter.reset_gate(in_gate.id)
                for step_idx, item in enumerate(pattern):
                    fake_clock.advance(0.5)
                    mock_rec.recognize.return_value = (
                        _make_scan_result(plate, 96.5) if item == "A" else empty_res
                    )
                    readers[in_gate.id].get_latest_frame.return_value = (
                        _make_distinct_frame(130 + (seq_idx * 4 + step_idx) * 25),
                        fake_clock(),
                    )
                    coordinator._process_gate_tick(in_gate)

                assert (
                    coordinator._pending_entries[(in_gate.id, norm)]["last_seen_at"]
                    == fake_clock()
                )

        # Defense-in-depth check: _evaluate_and_execute(..., touch_liveness=False) when existing_pending is None
        plate_in_dd = f"51H-{uuid.uuid4().int % 90000 + 10000}"
        norm_in_dd = PlateRecognizer.normalize_plate(plate_in_dd) or plate_in_dd
        Vehicle.all_objects.filter(license_plate_norm=norm_in_dd).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )
        plate_out_dd = f"51J-{uuid.uuid4().int % 90000 + 10000}"
        acct_dd, _, veh_out_dd, _ = _make_customer_with_vehicle(
            "k1dd", vtype_car, plate_out_dd, initial_balance=Decimal("1000.00")
        )
        VehicleEntryExitLog.objects.create(
            session_code=f"#PK-K1DD-{uuid.uuid4().hex[:6].upper()}",
            vehicle=veh_out_dd,
            entry_gate=in_gate,
            license_plate=veh_out_dd.license_plate,
            license_plate_norm=veh_out_dd.license_plate_norm,
            entry_time=timezone.now() - timedelta(hours=2),
            recognition_source="AI",
            review_status="AUTO",
        )

        dd_coord, _ = _build_coordinator(
            [in_gate, out_gate], fake_clock, pending_recheck_seconds=5.0
        )
        in_logs_before = ActivityLog.objects.filter(
            entity_type="parking_gate", entity_id=in_gate.id
        ).count()
        out_logs_before = ActivityLog.objects.filter(
            entity_type="parking_gate", entity_id=out_gate.id
        ).count()
        notifs_before = Notification.objects.filter(recipient_account=acct_dd).count()

        dd_coord._evaluate_and_execute(
            in_gate,
            plate_in_dd,
            _make_scan_result(plate_in_dd, 96.5),
            touch_liveness=False,
        )
        dd_coord._evaluate_and_execute(
            out_gate,
            plate_out_dd,
            _make_scan_result(plate_out_dd, 96.5),
            touch_liveness=False,
        )

        assert (in_gate.id, norm_in_dd) not in dd_coord._pending_entries
        assert (
            out_gate.id,
            veh_out_dd.license_plate_norm,
        ) not in dd_coord._pending_exits
        assert (
            ActivityLog.objects.filter(
                entity_type="parking_gate", entity_id=in_gate.id
            ).count()
            == in_logs_before
        )
        assert (
            ActivityLog.objects.filter(
                entity_type="parking_gate", entity_id=out_gate.id
            ).count()
            == out_logs_before
        )
        assert (
            Notification.objects.filter(recipient_account=acct_dd).count()
            == notifs_before
        )
