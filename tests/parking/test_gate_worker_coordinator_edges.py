"""
Unit tests for Coordinator Edge Cases (H6, TL Decision 6):
- (a) Failing snapshot upload does NOT mark successful check-in/out as EXECUTION_FAILED or apply 60s cooldown.
- (b) Released gate deactivates in-memory instance and halts in-flight tick before execution.
- (c) refresh_gate_configs includes lot_id in .only(...) avoiding deferred query on gate.lot_id.
- (d) Reconciliation isolates individual gate acquire exceptions so subsequent gates are still acquired.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
from apps.parking.models import ParkingGate, VehicleEntryExitLog
from apps.parking.services.gate_decision import (
    ACTION_AUTO_CHECK_IN,
    ACTION_HOLD,
    REASON_EXECUTION_FAILED,
)
from apps.parking.services.ocr import PlateCandidate, PlateScanResult
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


def _create_mock_scan_result(
    plate_text: str, confidence: float = 95.0
) -> PlateScanResult:
    norm = plate_text.replace("-", "").replace(".", "").replace(" ", "").upper()
    cand = PlateCandidate(
        plate_text=plate_text,
        plate_normalized=norm,
        confidence=confidence,
    )
    return PlateScanResult(
        candidates=[cand],
        best_candidate=cand,
        engine_name="mock_ocr",
        raw_text=plate_text,
        latency_ms=10.0,
        review_status="AUTO",
    )


def test_h6a_snapshot_dispatch_failure_does_not_abort_committed_session():
    """
    H6(a): When check_in_vehicle succeeds but dispatch_upload raises an exception:
    - The decision must NOT become ACTION_HOLD / REASON_EXECUTION_FAILED.
    - Voter cooldown must NOT be set to 60s.
    - The parking session in DB must exist.
    """
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None
    # Ensure active ticket
    ticket = Ticket.objects.filter(
        vehicle=vehicle, status="ACTIVE", deleted_at__isnull=True
    ).first()
    if not ticket:
        t = Ticket.objects.filter(status="ACTIVE", deleted_at__isnull=True).first()
        if t and t.vehicle:
            vehicle = t.vehicle

    plate = vehicle.license_plate
    VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm, exit_time__isnull=True
    ).update(exit_time=timezone.now())

    coordinator = GateWorkerCoordinator(
        streams_override={gate.code: "http://localhost/dummy"}
    )
    coordinator._managed_gates[gate.id] = gate

    mock_uploader = MagicMock()
    mock_uploader.dispatch_upload.side_effect = RuntimeError(
        "Snapshot threadpool full or queue rejected"
    )
    coordinator._snapshot_uploader = mock_uploader

    scan_res = _create_mock_scan_result(plate)
    fake_frame = np.zeros((100, 100, 3), dtype=np.uint8)

    decision = coordinator._evaluate_and_execute(
        gate=gate,
        voted_plate=plate,
        scan_result=scan_res,
        first_frame_ts=100.0,
        decisive_frame=fake_frame,
    )

    # In pre-fix code, decision.action is overwritten to ACTION_HOLD and reason_code to REASON_EXECUTION_FAILED
    assert decision.action == ACTION_AUTO_CHECK_IN, (
        f"Expected AUTO_CHECK_IN, got {decision.action}"
    )
    assert decision.reason_code != REASON_EXECUTION_FAILED, (
        "Should not be EXECUTION_FAILED on snapshot error"
    )

    # Cooldown should NOT be 60s
    import time

    from apps.parking.services.ocr import PlateRecognizer

    norm = PlateRecognizer.normalize_plate(plate)
    expiry = coordinator._voter._local_cooldowns.get((gate.id, norm))
    assert expiry is not None, "Voter cooldown must be set"
    remaining = expiry - time.monotonic()
    assert remaining <= 31, (
        f"Expected <= 31s normal cooldown, got {remaining}s (failed with 60s cooldown)"
    )

    # Session exists in DB
    session = VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm, exit_time__isnull=True
    ).first()
    assert session is not None, "Session should exist in DB"


def test_h6b_in_flight_tick_stops_when_gate_released():
    """
    H6(b): When _release_gate is called:
    - gate.is_active on the in-memory instance must become False.
    - An in-flight tick calling _evaluate_and_execute must abort and NOT perform check-in.
    """
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None
    ticket = Ticket.objects.filter(
        vehicle=vehicle, status="ACTIVE", deleted_at__isnull=True
    ).first()
    if not ticket:
        t = Ticket.objects.filter(status="ACTIVE", deleted_at__isnull=True).first()
        if t and t.vehicle:
            vehicle = t.vehicle

    plate = vehicle.license_plate
    VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm, exit_time__isnull=True
    ).update(exit_time=timezone.now())

    coordinator = GateWorkerCoordinator(
        streams_override={gate.code: "http://localhost/dummy"}
    )
    coordinator._managed_gates[gate.id] = gate

    # Simulate release while tick is in flight
    coordinator._release_gate(gate.id)

    # In pre-fix code, gate.is_active is still True on the gate object
    assert gate.is_active is False, "gate.is_active must be set to False upon release"

    scan_res = _create_mock_scan_result(plate)
    decision = coordinator._evaluate_and_execute(
        gate=gate,
        voted_plate=plate,
        scan_result=scan_res,
        first_frame_ts=100.0,
        decisive_frame=None,
    )

    # In pre-fix code, check-in is executed anyway
    assert decision.action == ACTION_HOLD, (
        f"Expected ACTION_HOLD on released gate, got {decision.action}"
    )
    assert decision.reason_code == "GATE_DEACTIVATED", (
        f"Expected GATE_DEACTIVATED, got {decision.reason_code}"
    )

    # No session should have been created
    session = VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm, exit_time__isnull=True
    ).first()
    assert session is None, "Should not create session when gate is released"


def test_h6c_refresh_gate_configs_includes_lot_id_no_deferred_query(
    django_assert_num_queries,
):
    """
    H6(c): refresh_gate_configs must include 'lot_id' in .only(...),
    so accessing gate.lot_id triggers 0 additional deferred SQL queries.
    """
    gate = ParkingGate.objects.filter(is_active=True).first()
    assert gate is not None

    coordinator = GateWorkerCoordinator(
        streams_override={gate.code: "http://localhost/dummy"}
    )
    coordinator.refresh_gate_configs()

    managed_gate = coordinator._managed_gates.get(gate.id)
    assert managed_gate is not None

    # In pre-fix code, lot_id was not in .only(...), so accessing managed_gate.lot_id issues 1 query
    with django_assert_num_queries(0):
        _ = managed_gate.lot_id


def test_h6d_reconciliation_isolates_individual_gate_acquire_failure():
    """
    H6(d): If acquiring gate 1 raises an exception, gate 2 must still be acquired successfully.
    """
    gates = list(ParkingGate.objects.filter(is_active=True)[:2])
    assert len(gates) >= 2, "Need at least 2 active gates for test"
    g1, g2 = gates[0], gates[1]

    coordinator = GateWorkerCoordinator(
        streams_override={g1.code: "http://localhost/1", g2.code: "http://localhost/2"}
    )

    original_acquire = coordinator._acquire_gate

    def mock_acquire(db_gate):
        if db_gate.id == g1.id:
            raise RuntimeError(f"Simulated failure acquiring gate {db_gate.code}")
        return original_acquire(db_gate)

    with patch.object(coordinator, "_acquire_gate", side_effect=mock_acquire):
        coordinator.refresh_gate_configs()

    # In pre-fix code, the single try/except aborts the loop, so g2 is not acquired
    assert g1.id not in coordinator._managed_gates, "g1 should fail"
    assert g2.id in coordinator._managed_gates, (
        "g2 should be successfully acquired despite g1 failure"
    )
