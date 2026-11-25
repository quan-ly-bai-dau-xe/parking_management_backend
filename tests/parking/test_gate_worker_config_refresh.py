"""
Unit and integration tests for Dynamic Gate Config Refresh (TL-75).
Verifies:
1. Dynamic flip of is_active=False in DB is detected, stops OCR processing on that gate without restart, retains advisory lock.
2. Dynamic flip back to is_active=True automatically resumes processing.
3. Dynamic flip of is_auto_scan=False shifts gate decision to manual review without restarting stream.
4. Single batch query complexity: refresh_gate_configs executes exactly 1 SELECT query with 0 UPDATEs.
5. Periodic invocation timing in run() loop.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
from apps.parking.models import ParkingGate, VehicleEntryExitLog
from apps.parking.services.gate_decision import (
    ACTION_AUTO_CHECK_IN,
    ACTION_HOLD,
    REASON_AUTO_SCAN_DISABLED,
    REASON_VALID_REGISTERED,
)
from apps.parking.services.ocr import PlateCandidate, PlateScanResult
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache():
    """Wipe cache before and after each test."""
    cache.clear()
    yield
    cache.clear()


def _create_mock_scan_result(
    plate_text: str, confidence: float = 95.0, review_status: str = "AUTO"
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
        review_status=review_status,
    )


def test_refresh_gate_configs_single_batch_query(django_assert_num_queries):
    """
    S2-B3: Verify refresh_gate_configs executes exactly ONE single SELECT query
    regardless of how many gates are managed, with 0 UPDATEs and unchanged row_version.
    """
    gates = list(ParkingGate.objects.filter(is_active=True)[:3])
    assert len(gates) >= 1

    streams = {g.code: f"http://mock/{g.code}" for g in gates}
    coordinator = GateWorkerCoordinator(streams_override=streams)
    for g in gates:
        coordinator._managed_gates[g.id] = g

    # Record row versions before refresh
    initial_versions = {
        g.id: ParkingGate.objects.get(id=g.id).row_version for g in gates
    }

    # Exactly 1 SELECT query must be executed
    with django_assert_num_queries(1):
        coordinator.refresh_gate_configs()

    # Ensure row_version is untouched on all gates
    for g in gates:
        current_version = ParkingGate.objects.get(id=g.id).row_version
        assert current_version == initial_versions[g.id]


def test_dynamic_flip_is_active_false_releases_lock_and_stops_reader():
    """
    Round 90 (G5, Decision 5): When is_active=False in DB:
    1. refresh_gate_configs() releases advisory lock, stops StreamReader,
       updates camera_status to 'OFFLINE', and removes gate from _managed_gates.
    2. API/pg_locks shows gate is offline so browser takes over.
    """
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/in"})
    coordinator.initialize()
    assert gate.id in coordinator._managed_gates
    assert coordinator._locks[gate.id].is_locked is True

    try:
        # Flip is_active -> False in database
        ParkingGate.objects.filter(id=gate.id).update(is_active=False)
        coordinator.refresh_gate_configs()

        # Gate must be de-acquired: removed from _managed_gates, lock released
        assert gate.id not in coordinator._managed_gates
        assert gate.id not in coordinator._locks
        assert gate.id not in coordinator._readers

        # In DB, camera_status must be OFFLINE
        gate.refresh_from_db()
        assert gate.camera_status == "OFFLINE"
    finally:
        ParkingGate.objects.filter(id=gate.id).update(is_active=True)
        coordinator.shutdown()


def test_dynamic_flip_is_active_true_resumes_processing():
    """
    Round 90 (G5, Decision 5): A gate that starts inactive and is activated later
    is acquired dynamically on refresh_gate_configs() without requiring a worker restart.
    """
    gate = ParkingGate.objects.filter(direction="IN").first()
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

    VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm, exit_time__isnull=True
    ).update(exit_time=timezone.now())

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/in"})
    scan_result = _create_mock_scan_result(vehicle.license_plate, confidence=95.0)

    try:
        # Start inactive in DB
        ParkingGate.objects.filter(id=gate.id).update(is_active=False)
        coordinator.initialize()
        assert gate.id not in coordinator._managed_gates

        # Flip to active in DB
        ParkingGate.objects.filter(id=gate.id).update(is_active=True, is_auto_scan=True)
        coordinator.refresh_gate_configs()

        # Gate must be dynamically acquired without worker restart!
        assert gate.id in coordinator._managed_gates
        assert coordinator._locks[gate.id].is_locked is True
        assert coordinator._managed_gates[gate.id].is_active is True

        decision_active = coordinator._evaluate_and_execute(
            coordinator._managed_gates[gate.id], vehicle.license_plate, scan_result
        )
        assert decision_active.action == ACTION_AUTO_CHECK_IN
        assert decision_active.reason_code == REASON_VALID_REGISTERED
    finally:
        ParkingGate.objects.filter(id=gate.id).update(is_active=True, is_auto_scan=True)
        coordinator.shutdown()


def test_dynamic_flip_is_auto_scan_false_shifts_to_manual_review():
    """
    S2-B3 (F5): Flipping is_auto_scan -> False shifts gate decision to manual review
    (HOLD with AUTO_SCAN_DISABLED) without interrupting camera stream or restarting worker.
    """
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None
    scan_result = _create_mock_scan_result(vehicle.license_plate, confidence=95.0)

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/in"})
    coordinator._managed_gates[gate.id] = gate

    try:
        # Flip is_auto_scan -> False
        ParkingGate.objects.filter(id=gate.id).update(is_auto_scan=False)
        coordinator.refresh_gate_configs()
        assert coordinator._managed_gates[gate.id].is_auto_scan is False

        decision = coordinator._evaluate_and_execute(
            coordinator._managed_gates[gate.id], vehicle.license_plate, scan_result
        )
        assert decision.action == ACTION_HOLD
        assert decision.audit_action is None  # No spam audit for manual review
        assert decision.reason_code == REASON_AUTO_SCAN_DISABLED

        # Flip back to True
        ParkingGate.objects.filter(id=gate.id).update(is_auto_scan=True)
        coordinator.refresh_gate_configs()
        assert coordinator._managed_gates[gate.id].is_auto_scan is True
    finally:
        ParkingGate.objects.filter(id=gate.id).update(is_auto_scan=True)


def test_dynamic_flip_direction_updates_evaluation():
    """
    S2-B3: Changing direction in DB (IN <-> OUT) updates in-memory gate direction.
    """
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/in"})
    coordinator._managed_gates[gate.id] = gate

    try:
        ParkingGate.objects.filter(id=gate.id).update(direction="OUT")
        coordinator.refresh_gate_configs()
        assert coordinator._managed_gates[gate.id].direction == "OUT"

        ParkingGate.objects.filter(id=gate.id).update(direction="IN")
        coordinator.refresh_gate_configs()
        assert coordinator._managed_gates[gate.id].direction == "IN"
    finally:
        ParkingGate.objects.filter(id=gate.id).update(direction="IN")


def test_periodic_refresh_invocation_timing_in_coordinator():
    """
    S2-B3: Verify coordinator run loop triggers refresh_gate_configs periodically
    when monotonic elapsed time exceeds config_refresh_interval.
    """
    gate = ParkingGate.objects.filter(is_active=True).first()
    assert gate is not None

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/cam"})
    coordinator._managed_gates[gate.id] = gate
    coordinator._config_refresh_interval = 0.05
    coordinator._last_config_refresh_ts = time.monotonic() - 1.0

    with patch.object(coordinator, "refresh_gate_configs") as mock_refresh:
        coordinator.run(duration=0.1)
        assert mock_refresh.call_count >= 1


def test_refresh_gate_configs_marks_missing_or_soft_deleted_gate_inactive():
    """If a managed gate is missing or soft-deleted in DB, refresh marks it inactive safely."""
    gate = ParkingGate.objects.filter(is_active=True).first()
    assert gate is not None

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/in"})
    fake_gate = ParkingGate(
        id=999999,
        lot_id=gate.lot_id,
        code="MISSING_GATE",
        name="Missing Gate",
        direction="IN",
        is_active=True,
        is_auto_scan=True,
    )
    coordinator._managed_gates[gate.id] = gate
    coordinator._managed_gates[fake_gate.id] = fake_gate

    coordinator.refresh_gate_configs()
    assert fake_gate.id not in coordinator._managed_gates
    assert coordinator._managed_gates[gate.id].is_active is True
