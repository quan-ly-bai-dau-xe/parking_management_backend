"""
Unit and integration tests for Gate Worker Failure Events & Cooldown (TL-74).
Verifies:
1. Exceptions in check_in_vehicle or check_out_vehicle create ActivityLog with GATE_AUTO_NEEDS_STAFF and EXECUTION_FAILED.
2. 60-second cooldown is activated on failure, preventing retry storms.
3. Raw license plate PII is masked in error description per Decree 13/2023/ND-CP.
4. Serializer and API reflect last_auto_event with reason=EXECUTION_FAILED.
"""

from __future__ import annotations

import json
import logging
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from django.core.cache import cache
from django.db.models import Max
from django.utils import timezone

from apps.audit.models import ActivityLog
from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
from apps.parking.gate_worker.filter import MotionFilter
from apps.parking.gate_worker.reader import STATUS_STREAMING
from apps.parking.models import ParkingGate, ParkingSlot, VehicleEntryExitLog
from apps.parking.serializers.gates import ParkingGateSerializer
from apps.parking.services.gate_decision import (
    ACTION_HOLD,
    AUDIT_GATE_AUTO_NEEDS_STAFF,
    REASON_EXECUTION_FAILED,
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


def test_coordinator_auto_check_in_exception_creates_activity_log_and_cooldown_s2_b2():
    """
    S2-B2 (F4): When check_in_vehicle raises an unhandled exception during automated check-in:
    1. Exception is caught gracefully without crashing worker coordinator.
    2. Exactly one ActivityLog entry is created with action GATE_AUTO_NEEDS_STAFF,
       reason EXECUTION_FAILED, masked license plate, and error description.
    3. Voter cooldown is immediately activated for at least 60 seconds.
    4. Subsequent observations for the same plate within 60s do NOT trigger retry storm.
    5. Gate status API / serializer reflects last_auto_event with action GATE_AUTO_NEEDS_STAFF
       and reason EXECUTION_FAILED.
    """
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None

    # Ensure vehicle has an active ticket
    ticket = Ticket.objects.filter(
        vehicle=vehicle, status="ACTIVE", deleted_at__isnull=True
    ).first()
    if not ticket:
        t = Ticket.objects.filter(status="ACTIVE", deleted_at__isnull=True).first()
        if t and t.vehicle:
            vehicle = t.vehicle

    plate = vehicle.license_plate

    # Clean existing open sessions and mark baseline log id
    VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm,
        exit_time__isnull=True,
    ).update(exit_time=timezone.now())
    start_log_id = ActivityLog.objects.aggregate(max_id=Max("id"))["max_id"] or 0

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/in"})
    coordinator._managed_gates[gate.id] = gate

    scan_result = _create_mock_scan_result(plate, confidence=96.0)

    # 1. Simulate check_in_vehicle raising an exception (e.g. database error, slot collision)
    with patch(
        "apps.parking.services.check_in.check_in_vehicle",
        side_effect=RuntimeError(f"Simulated DB constraint failure for {plate}"),
    ) as mock_check_in:
        decision = coordinator._evaluate_and_execute(gate, plate, scan_result)

    assert mock_check_in.call_count == 1
    assert decision.action == ACTION_HOLD
    assert decision.audit_action == AUDIT_GATE_AUTO_NEEDS_STAFF
    assert decision.reason_code == REASON_EXECUTION_FAILED

    # 2. Verify ActivityLog was created with action GATE_AUTO_NEEDS_STAFF and reason EXECUTION_FAILED
    logs = ActivityLog.objects.filter(
        id__gt=start_log_id,
        entity_type="parking_gate",
        entity_id=gate.id,
        action=AUDIT_GATE_AUTO_NEEDS_STAFF,
    ).order_by("-id")
    assert logs.count() == 1
    log = logs.first()
    assert log is not None
    assert log.actor_account is None

    payload = json.loads(log.message)
    assert payload["action"] == AUDIT_GATE_AUTO_NEEDS_STAFF
    assert payload["reason"] == REASON_EXECUTION_FAILED
    assert "*" in payload["license_plate_masked"]
    assert payload["gate_code"] == gate.code
    # PII plate must not appear in description, which uses format_failure_text
    assert plate not in payload.get("description", "")
    from apps.parking.services.ocr import PlateRecognizer

    assert PlateRecognizer.normalize_plate(plate) not in payload.get("description", "")
    assert "RuntimeError: auto check-in failed" in payload.get("description", "")

    # 3. Verify voter cooldown is active for at least 60 seconds
    assert coordinator._voter.is_in_cooldown(gate.id, plate) is True
    from apps.parking.services.ocr import PlateRecognizer

    norm_plate = PlateRecognizer.normalize_plate(plate)
    expiry = coordinator._voter._local_cooldowns.get((gate.id, norm_plate), 0.0)
    remaining_cooldown = expiry - time.monotonic()
    assert remaining_cooldown >= 58.0, (
        f"Expected at least 60s cooldown, got {remaining_cooldown:.1f}s"
    )

    # 4. Verify retry storm prevention: voter rejects observations during cooldown
    for _ in range(10):
        is_stable, voted = coordinator._voter.add_observation(gate.id, plate)
        assert is_stable is False
        assert voted is None

    # ActivityLog count remains strictly 1 (no spam)
    assert (
        ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=gate.id,
            action=AUDIT_GATE_AUTO_NEEDS_STAFF,
        ).count()
        == 1
    )

    # 5. Verify telemetry via serializer
    serializer = ParkingGateSerializer(gate)
    assert serializer.data["last_auto_event"] is not None
    assert serializer.data["last_auto_event"]["action"] == AUDIT_GATE_AUTO_NEEDS_STAFF
    assert serializer.data["last_auto_event"]["reason"] == REASON_EXECUTION_FAILED


def test_coordinator_auto_check_out_exception_creates_activity_log_and_cooldown_s2_b2():
    """
    S2-B2 (F4): When check_out_vehicle raises an unhandled exception during automated check-out (fee=0):
    1. Exception is caught gracefully.
    2. ActivityLog created with GATE_AUTO_NEEDS_STAFF and reason EXECUTION_FAILED.
    3. 60-second cooldown is activated.
    4. Session remains open (not deleted/corrupted).
    5. Retry storm is prevented.
    """
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    assert gate is not None

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None
    plate = vehicle.license_plate

    # Create active open session with 0 fee
    entry_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    slot = ParkingSlot.objects.filter(
        status="AVAILABLE", deleted_at__isnull=True
    ).first()
    VehicleEntryExitLog.objects.filter(vehicle=vehicle, exit_time__isnull=True).update(
        exit_time=timezone.now()
    )

    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-TEST-ERR-{int(time.time())}",
        vehicle=vehicle,
        slot=slot,
        entry_gate=entry_gate,
        license_plate=plate,
        recognition_source="AI",
        review_status="AUTO",
        entry_time=timezone.now(),
        fee_amount=Decimal("0.00"),
    )
    start_log_id = ActivityLog.objects.aggregate(max_id=Max("id"))["max_id"] or 0

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/out"})
    coordinator._managed_gates[gate.id] = gate
    scan_result = _create_mock_scan_result(plate, confidence=95.0)

    with (
        patch(
            "apps.parking.gate_worker.coordinator.calculate_parking_fee",
            return_value=Decimal("0.00"),
        ),
        patch(
            "apps.parking.services.check_out.check_out_vehicle",
            side_effect=RuntimeError(
                f"Simulated barrier controller deadlock for {plate}"
            ),
        ) as mock_check_out,
    ):
        decision = coordinator._evaluate_and_execute(gate, plate, scan_result)

    assert mock_check_out.call_count == 1
    assert decision.action == ACTION_HOLD
    assert decision.audit_action == AUDIT_GATE_AUTO_NEEDS_STAFF
    assert decision.reason_code == REASON_EXECUTION_FAILED

    session.refresh_from_db()
    assert session.exit_time is None, "Session must remain open when check-out fails"

    # Verify ActivityLog
    log = (
        ActivityLog.objects.filter(
            id__gt=start_log_id,
            entity_type="parking_gate",
            entity_id=gate.id,
            action=AUDIT_GATE_AUTO_NEEDS_STAFF,
        )
        .order_by("-id")
        .first()
    )
    assert log is not None
    payload = json.loads(log.message)
    assert payload["reason"] == REASON_EXECUTION_FAILED
    assert "RuntimeError: auto check-out failed" in payload.get("description", "")
    assert plate not in payload.get("description", "")
    from apps.parking.services.ocr import PlateRecognizer

    assert PlateRecognizer.normalize_plate(plate) not in payload.get("description", "")

    # Verify 60s cooldown
    assert coordinator._voter.is_in_cooldown(gate.id, plate) is True


def test_coordinator_tick_retry_storm_suppressed_by_cooldown():
    """
    S2-B2: Full tick cycle test verifying that when a plate is in cooldown after failure,
    _process_gate_tick bypasses OCR and evaluation, completely stopping the retry storm.
    """
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/in"})
    coordinator._managed_gates[gate.id] = gate

    mock_reader = MagicMock()
    fake_frame = np.full((64, 64, 3), 100, dtype=np.uint8)
    mock_reader.get_latest_frame.return_value = (fake_frame, time.monotonic())
    mock_reader.status = STATUS_STREAMING
    coordinator._readers[gate.id] = mock_reader
    coordinator._filters[gate.id] = MotionFilter(mad_threshold=1.0, max_fps=1000.0)

    test_plate = "51A-897.14"

    # Put plate into 60s cooldown
    coordinator._voter.set_cooldown(gate.id, test_plate, seconds=60)
    assert coordinator._voter.is_in_cooldown(gate.id, test_plate) is True

    # Setup OCR mock returning the cooling plate
    scan_result = _create_mock_scan_result(test_plate, confidence=95.0)
    mock_ocr = MagicMock()
    mock_ocr.recognize.return_value = scan_result

    with (
        patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_ocr,
        ),
        patch("apps.parking.services.check_in.check_in_vehicle") as mock_check_in,
    ):
        # Run 5 consecutive ticks
        for i in range(5):
            mock_reader.get_latest_frame.return_value = (
                fake_frame,
                time.monotonic() + (i * 0.1),
            )
            coordinator._process_gate_tick(gate)

        # Check-in should NEVER be called while in cooldown
        assert mock_check_in.call_count == 0


def test_failure_cooldown_isolation_and_unpunctuated_pii_masking():
    """
    Verify:
    1. Independent per-plate and per-gate failure cooldowns.
    2. Exception messages containing formatted plate when OCR voted unpunctuated plate are masked.
    """
    gates = list(ParkingGate.objects.filter(direction="IN", is_active=True)[:2])
    assert len(gates) >= 1
    gate = gates[0]

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None
    VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm, exit_time__isnull=True
    ).update(exit_time=timezone.now())

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/in"})
    coordinator._managed_gates[gate.id] = gate

    compact_plate = vehicle.license_plate_norm
    formatted_plate = vehicle.license_plate
    scan_result = _create_mock_scan_result(compact_plate, confidence=96.0)

    with patch(
        "apps.parking.services.check_in.check_in_vehicle",
        side_effect=RuntimeError(f"Slot lock timeout for {formatted_plate}"),
    ):
        decision = coordinator._evaluate_and_execute(gate, compact_plate, scan_result)

    assert decision.reason_code == REASON_EXECUTION_FAILED
    log = (
        ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=gate.id,
            action=AUDIT_GATE_AUTO_NEEDS_STAFF,
        )
        .order_by("-id")
        .first()
    )
    assert log is not None
    payload = json.loads(log.message)
    assert formatted_plate not in payload.get("description", "")
    assert compact_plate not in payload.get("description", "")
    assert coordinator._voter.is_in_cooldown(gate.id, compact_plate) is True
    assert coordinator._voter.is_in_cooldown(gate.id, "43A-000.01") is False
    if len(gates) >= 2:
        assert coordinator._voter.is_in_cooldown(gates[1].id, compact_plate) is False


@pytest.mark.django_db(transaction=True)
def test_all_failure_paths_never_leak_raw_or_normalized_plate_in_logs_or_audit(
    caplog,
):
    """
    Round 90 (G6, Decision 6): Across all failure paths (check-in, check-out, fee preview,
    snapshot, OCR failure), verify that the unmasked plate and normalized plate
    never appear in any caplog line or ActivityLog message.
    """
    from apps.parking.gate_worker.snapshot import SnapshotUploader

    test_plate = "51A-999.88"
    norm_plate = "51A99988"

    in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    assert in_gate is not None
    assert out_gate is not None

    coordinator = GateWorkerCoordinator(
        streams_override={
            in_gate.code: "http://mock/in",
            out_gate.code: "http://mock/out",
        }
    )
    coordinator._managed_gates[in_gate.id] = in_gate
    coordinator._managed_gates[out_gate.id] = out_gate

    scan_result = _create_mock_scan_result(test_plate, confidence=95.0)

    # Mark baseline log id for these gates (ActivityLog is append-only)
    start_log_id = ActivityLog.objects.aggregate(max_id=Max("id"))["max_id"] or 0

    with caplog.at_level(logging.DEBUG):
        # 1. Check-in failure path
        with patch(
            "apps.parking.services.check_in.check_in_vehicle",
            side_effect=RuntimeError(
                f"Simulated check-in failure with sensitive {test_plate}"
            ),
        ):
            coordinator._evaluate_and_execute(in_gate, test_plate, scan_result)

        # 2. Fee preview failure path (OUT gate with open session)
        fake_session = MagicMock()
        with patch(
            "apps.parking.gate_worker.coordinator.get_combined_vehicle_context"
        ) as mock_ctx:
            mock_ctx.return_value = MagicMock(
                vehicle_match={"id": 1, "status": "ACTIVE"},
                open_session=fake_session,
                available_slot=None,
            )
            with (
                patch(
                    "apps.parking.gate_worker.coordinator.calculate_parking_fee",
                    side_effect=RuntimeError(
                        f"Tariff calculation error on {test_plate}"
                    ),
                ),
                patch(
                    "apps.parking.services.check_out.check_out_vehicle",
                    return_value=(fake_session, None, None),
                ),
            ):
                coordinator._evaluate_and_execute(out_gate, test_plate, scan_result)

        # 3. Check-out failure path
        with patch(
            "apps.parking.gate_worker.coordinator.get_combined_vehicle_context"
        ) as mock_ctx:
            mock_ctx.return_value = MagicMock(
                vehicle_match={"id": 1, "status": "ACTIVE"},
                open_session=fake_session,
                available_slot=None,
            )
            with (
                patch(
                    "apps.parking.gate_worker.coordinator.calculate_parking_fee",
                    return_value=Decimal("0.00"),
                ),
                patch(
                    "apps.parking.services.check_out.check_out_vehicle",
                    side_effect=RuntimeError(
                        f"Simulated check-out barrier deadlock {test_plate}"
                    ),
                ),
            ):
                coordinator._evaluate_and_execute(out_gate, test_plate, scan_result)

        # 4. Snapshot failure path
        def failing_uploader(processed):
            raise RuntimeError(f"Snapshot upload failed for {test_plate}")

        snap_uploader = SnapshotUploader(upload_service=failing_uploader)
        snap_uploader.dispatch_upload(
            session_id=99999,
            frame=np.zeros((100, 100, 3), dtype=np.uint8),
            is_entry=True,
            gate_id=in_gate.id,
            gate_code=in_gate.code,
            gate_name=in_gate.name,
            audit_action="GATE_AUTO_CHECK_IN",
            reason_code="VALID_REGISTERED",
            plate=test_plate,
        )
        snap_uploader.shutdown(wait=True)

        # 5. OCR recognition failure path
        fake_reader = MagicMock()
        fake_reader.status = "STREAMING"
        fake_reader.get_latest_frame.return_value = (
            np.ones((100, 100, 3), dtype=np.uint8) * 128,
            time.monotonic(),
        )
        coordinator._readers[in_gate.id] = fake_reader

        fake_filter = MagicMock()
        fake_filter.should_process.return_value = (True, "motion", 15.0)
        coordinator._filters[in_gate.id] = fake_filter

        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer"
        ) as mock_rec_getter:
            mock_rec = MagicMock()
            mock_rec.recognize.side_effect = RuntimeError(
                f"OCR model internal exception with raw plate {test_plate}"
            )
            mock_rec_getter.return_value = mock_rec
            coordinator._process_gate_tick(in_gate)

    # ASSERTION: Neither raw plate nor normalized plate ever appears in caplog
    for record in caplog.records:
        log_msg = record.getMessage()
        assert test_plate not in log_msg, (
            f"Raw plate {test_plate} leaked in log: {log_msg}"
        )
        assert norm_plate not in log_msg, (
            f"Normalized plate {norm_plate} leaked in log: {log_msg}"
        )

    # ASSERTION: Neither raw plate nor normalized plate ever appears in ActivityLog messages
    recent_logs = ActivityLog.objects.filter(
        id__gt=start_log_id, entity_id__in=[in_gate.id, out_gate.id]
    )
    assert recent_logs.exists()
    for alog in recent_logs:
        raw_msg = alog.message or ""
        assert test_plate not in raw_msg, (
            f"Raw plate {test_plate} leaked in ActivityLog #{alog.id}: {raw_msg}"
        )
        assert norm_plate not in raw_msg, (
            f"Normalized plate {norm_plate} leaked in ActivityLog #{alog.id}: {raw_msg}"
        )
