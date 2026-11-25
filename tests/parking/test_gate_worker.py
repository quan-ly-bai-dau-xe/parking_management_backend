"""
Integration and unit tests for Background Gate Worker Process (Round 88, ADR-0011, TL-66 to TL-71).
Tests StreamReader, MotionFilter, PlateVoter, GateAdvisoryLock, GateWorkerCoordinator,
and Django management command run_gate_worker.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.utils import timezone

from apps.audit.models import ActivityLog
from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
from apps.parking.gate_worker.filter import MotionFilter
from apps.parking.gate_worker.locks import (
    GateAdvisoryLock,
    get_active_gate_worker_lock_ids,
)
from apps.parking.gate_worker.reader import (
    STATUS_DEGRADED,
    STATUS_OFFLINE,
    STATUS_STREAMING,
    StreamReader,
)
from apps.parking.gate_worker.voter import PlateVoter
from apps.parking.models import ParkingGate, ParkingSlot, VehicleEntryExitLog
from apps.parking.serializers.gates import ParkingGateSerializer
from apps.parking.services.gate_decision import (
    ACTION_AUTO_CHECK_IN,
    ACTION_AUTO_CHECK_OUT,
    ACTION_HOLD,
    AUDIT_GATE_AUTO_CHECK_IN,
    AUDIT_GATE_AUTO_CHECK_OUT,
    AUDIT_GATE_AUTO_NEEDS_STAFF,
    AUDIT_GATE_AUTO_PAYMENT_REQUIRED,
    REASON_FEE_PAYMENT_REQUIRED,
    REASON_UNREGISTERED_VEHICLE,
    REASON_VALID_FEE_ZERO,
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


# ==============================================================================
# 1. StreamReader Tests
# ==============================================================================


def test_stream_reader_initial_status_and_empty_frame():
    """StreamReader starts in OFFLINE status and returns (None, 0.0) initially."""
    reader = StreamReader(gate_code="IN_01", stream_url="http://fake-camera/video")
    assert reader.status == STATUS_OFFLINE
    frame, ts = reader.get_latest_frame()
    assert frame is None
    assert ts == 0.0
    assert not reader.is_alive()


def test_stream_reader_latest_frame_wins_buffer():
    """StreamReader single-frame buffer always returns the newest frame (no backlog)."""
    reader = StreamReader(gate_code="IN_01", stream_url="http://fake-camera/video")

    frame1 = np.zeros((100, 100, 3), dtype=np.uint8)
    frame2 = np.ones((100, 100, 3), dtype=np.uint8) * 255

    # Simulate reader thread writing consecutive frames
    with reader._frame_lock:
        reader._latest_frame = frame1
        reader._last_frame_timestamp = 100.0

    with reader._frame_lock:
        reader._latest_frame = frame2
        reader._last_frame_timestamp = 105.0

    latest, ts = reader.get_latest_frame()
    assert latest is not None
    assert np.array_equal(latest, frame2)
    assert ts == 105.0


def test_stream_reader_privacy_no_credential_leak():
    """Stream URL and credentials are never exposed in string representations."""
    secret_url = "rtsp://admin:P@ssw0rd123!@192.168.1.100:554/stream"
    reader = StreamReader(gate_code="IN_01", stream_url=secret_url)

    rep = repr(reader)
    assert secret_url not in rep
    assert "P@ssw0rd123!" not in rep


@patch("cv2.VideoCapture")
def test_stream_reader_successful_streaming_and_stop(mock_video_capture):
    """StreamReader connects, transitions to STREAMING, reads frames, and stops cleanly."""
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    test_frame = np.full((64, 64, 3), 128, dtype=np.uint8)
    mock_cap.read.return_value = (True, test_frame)
    mock_video_capture.return_value = mock_cap

    status_changes = []

    def on_change(code, st):
        status_changes.append((code, st))

    reader = StreamReader(
        gate_code="IN_01",
        stream_url="http://fake-camera/video",
        reconnect_initial=0.1,
        reconnect_max=0.5,
        on_status_change=on_change,
    )

    reader.start()
    assert reader.is_alive()

    # Wait for at least one frame read
    timeout = time.monotonic() + 2.0
    while time.monotonic() < timeout:
        latest, _ = reader.get_latest_frame()
        if latest is not None:
            break
        time.sleep(0.02)

    assert reader.status == STATUS_STREAMING
    assert ("IN_01", STATUS_STREAMING) in status_changes

    reader.stop(timeout=1.0)
    assert not reader.is_alive()
    assert reader.status == STATUS_OFFLINE
    assert mock_cap.release.called


@patch("cv2.VideoCapture")
def test_stream_reader_reconnect_backoff_on_failure(mock_video_capture):
    """When stream fails to open, reader transitions to DEGRADED and attempts reconnect."""
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = False
    mock_video_capture.return_value = mock_cap

    reader = StreamReader(
        gate_code="OUT_01",
        stream_url="http://fake-camera/down",
        reconnect_initial=0.1,
        reconnect_max=0.3,
    )

    reader.start()
    time.sleep(0.2)

    assert reader.status == STATUS_DEGRADED
    reader.stop(timeout=1.0)
    assert reader.status == STATUS_OFFLINE


# ==============================================================================
# 2. MotionFilter Tests
# ==============================================================================


def test_motion_filter_thumbnail_conversion():
    """Frame is converted to 64x64 single-channel uint8 thumbnail."""
    color_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    thumb = MotionFilter.to_grayscale_thumbnail(color_frame)
    assert thumb.shape == (64, 64)
    assert thumb.dtype == np.uint8


def test_motion_filter_mad_computation():
    """Identical thumbnails have MAD 0.0; distinct thumbnails have correct difference."""
    thumb1 = np.zeros((64, 64), dtype=np.uint8)
    thumb2 = np.full((64, 64), 10, dtype=np.uint8)

    assert MotionFilter.compute_mad(thumb1, thumb1) == 0.0
    assert MotionFilter.compute_mad(thumb1, thumb2) == 10.0


def test_motion_filter_initial_frame_accepted():
    """First frame observed is accepted as baseline reference."""
    flt = MotionFilter(mad_threshold=5.0, max_fps=2.0)
    frame = np.full((100, 100, 3), 50, dtype=np.uint8)

    should_process, reason, mad = flt.should_process(frame, now=10.0)
    assert should_process is True
    assert reason == "INITIAL_FRAME"
    assert mad == 0.0


def test_motion_filter_static_scene_skipped():
    """Consecutive static frames with MAD < threshold are skipped."""
    flt = MotionFilter(mad_threshold=5.0, max_fps=2.0)
    frame1 = np.full((100, 100, 3), 50, dtype=np.uint8)
    frame2 = np.full((100, 100, 3), 52, dtype=np.uint8)  # Diff is 2.0 < 5.0

    flt.should_process(frame1, now=10.0)
    # Advance time beyond 1/max_fps (0.5s)
    should_proc, reason, mad = flt.should_process(frame2, now=11.0)
    assert should_proc is False
    assert reason == "NO_MOTION"
    assert mad == pytest.approx(2.0, abs=0.1)


def test_motion_filter_motion_detected_accepted():
    """Frames with MAD >= threshold are accepted and update baseline."""
    flt = MotionFilter(mad_threshold=5.0, max_fps=2.0)
    frame1 = np.full((100, 100, 3), 50, dtype=np.uint8)
    frame2 = np.full((100, 100, 3), 70, dtype=np.uint8)  # Diff is 20.0 >= 5.0

    flt.should_process(frame1, now=10.0)
    should_proc, reason, mad = flt.should_process(frame2, now=11.0)
    assert should_proc is True
    assert reason == "MOTION_DETECTED"
    assert mad == pytest.approx(20.0, abs=0.1)


def test_motion_filter_rate_limiting():
    """Frames arriving faster than 1.0 / max_fps are throttled."""
    flt = MotionFilter(mad_threshold=5.0, max_fps=2.0)  # interval 0.5s
    frame1 = np.full((100, 100, 3), 50, dtype=np.uint8)
    frame2 = np.full((100, 100, 3), 90, dtype=np.uint8)

    flt.should_process(frame1, now=10.0)
    # Only 0.2s elapsed (< 0.5s)
    should_proc, reason, _ = flt.should_process(frame2, now=10.2)
    assert should_proc is False
    assert reason == "RATE_LIMITED"


def test_motion_filter_reset():
    """Reset clears history so next frame is treated as initial frame."""
    flt = MotionFilter(mad_threshold=5.0, max_fps=2.0)
    frame = np.full((100, 100, 3), 50, dtype=np.uint8)
    flt.should_process(frame, now=10.0)
    flt.reset()

    should_proc, reason, _ = flt.should_process(frame, now=10.1)
    assert should_proc is True
    assert reason == "INITIAL_FRAME"


# ==============================================================================
# 3. PlateVoter Tests
# ==============================================================================


def test_plate_voter_requires_3_out_of_4_matches():
    """Requires 3 identical normalized plates out of the last 4 frames."""
    voter = PlateVoter(window_size=4, required_matches=3, cooldown_seconds=30)
    gate_id = 1

    # Frame 1: 51A-897.14
    stable, plate = voter.add_observation(gate_id, "51A-897.14")
    assert not stable
    assert plate is None

    # Frame 2: 51A-897.14
    stable, plate = voter.add_observation(gate_id, "51A 897 14")
    assert not stable
    assert plate is None

    # Frame 3: Noise frame 29B-999.99
    stable, plate = voter.add_observation(gate_id, "29B-999.99")
    assert not stable
    assert plate is None

    # Frame 4: 51A-897.14 (now 3 of 4 match!)
    stable, plate = voter.add_observation(gate_id, "51A89714")
    assert stable is True
    assert plate == "51A89714"


def test_plate_voter_unstable_plate_rejected():
    """When plates are all distinct or less than 3/4 match, is_stable is False."""
    voter = PlateVoter(window_size=4, required_matches=3, cooldown_seconds=30)
    gate_id = 2

    voter.add_observation(gate_id, "51F-111.11")
    voter.add_observation(gate_id, "51F-222.22")
    voter.add_observation(gate_id, "51F-111.11")
    stable, plate = voter.add_observation(gate_id, "51F-333.33")

    assert not stable
    assert plate is None


def test_plate_voter_cooldown_tracking():
    """Cooldown prevents duplicate decisions for the same (gate, plate) within interval."""
    voter = PlateVoter(window_size=4, required_matches=3, cooldown_seconds=30)
    gate_id = 3
    plate = "51K-992.14"

    assert not voter.is_in_cooldown(gate_id, plate, now=100.0)

    # Set cooldown for 30s
    voter.set_cooldown(gate_id, plate, seconds=30, now=100.0)

    # Active cooldown
    assert voter.is_in_cooldown(gate_id, plate, now=115.0)
    assert voter.is_in_cooldown(gate_id, "51K99214", now=120.0)

    # Different gate is not in cooldown
    assert not voter.is_in_cooldown(gate_id=99, normalized_plate=plate, now=115.0)

    # Different plate on same gate is not in cooldown
    assert not voter.is_in_cooldown(gate_id, "43A-111.11", now=115.0)

    # Cooldown expires after 30s
    assert not voter.is_in_cooldown(gate_id, plate, now=131.0)


def test_plate_voter_reset_gate():
    """Reset gate clears history."""
    voter = PlateVoter(window_size=4, required_matches=3)
    gate_id = 4
    voter.add_observation(gate_id, "51A-897.14")
    voter.add_observation(gate_id, "51A-897.14")
    voter.reset_gate(gate_id)

    # After reset, needs 3 new observations
    voter.add_observation(gate_id, "51A-897.14")
    stable, _ = voter.add_observation(gate_id, "51A-897.14")
    assert not stable


# ==============================================================================
# 4. GateAdvisoryLock Tests
# ==============================================================================


def test_gate_advisory_lock_mutual_exclusion():
    """Advisory lock enforces single worker ownership per gate."""
    gate_id = 8801
    lock1 = GateAdvisoryLock(gate_id=gate_id)
    lock2 = GateAdvisoryLock(gate_id=gate_id)

    try:
        # First worker acquires lock successfully
        assert lock1.acquire() is True
        assert lock1.is_locked is True

        # Second worker attempts to acquire same gate -> fails
        assert lock2.acquire() is False
        assert lock2.is_locked is False

        # First worker releases lock
        lock1.release()
        assert lock1.is_locked is False

        # Now second worker can acquire lock
        assert lock2.acquire() is True
        assert lock2.is_locked is True
    finally:
        lock1.release()
        lock2.release()


def test_gate_advisory_lock_context_manager():
    """Context manager correctly acquires and releases lock."""
    gate_id = 8802
    with GateAdvisoryLock(gate_id=gate_id) as lock:
        assert lock.is_locked is True

    # After exiting block, lock is released
    assert lock.is_locked is False

    # Another instance can acquire immediately
    with GateAdvisoryLock(gate_id=gate_id) as lock2:
        assert lock2.is_locked is True


# ==============================================================================
# 5. GateWorkerCoordinator Integration Tests
# ==============================================================================


def _create_mock_scan_result(
    plate_text: str, confidence: float = 95.0, review_status: str = "AUTO"
):
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


def test_coordinator_auto_check_in_registered_vehicle():
    """Autonomous entry check-in for registered vehicle with valid ticket and available slot."""
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None

    # Ensure vehicle has an active ticket
    ticket = Ticket.objects.filter(
        vehicle=vehicle, status="ACTIVE", deleted_at__isnull=True
    ).first()
    if not ticket:
        # If no ticket, use any active ticket's vehicle
        t = Ticket.objects.filter(status="ACTIVE", deleted_at__isnull=True).first()
        if t and t.vehicle:
            vehicle = t.vehicle
            ticket = t

    # Ensure no open session exists for this vehicle
    VehicleEntryExitLog.objects.filter(vehicle=vehicle, exit_time__isnull=True).update(
        exit_time=timezone.now()
    )

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/in"})
    coordinator._managed_gates[gate.id] = gate

    scan_result = _create_mock_scan_result(vehicle.license_plate, confidence=96.0)

    # Evaluate and execute auto check-in
    decision = coordinator._evaluate_and_execute(
        gate, vehicle.license_plate, scan_result
    )

    assert decision.action == ACTION_AUTO_CHECK_IN
    assert decision.audit_action == AUDIT_GATE_AUTO_CHECK_IN
    assert decision.reason_code == REASON_VALID_REGISTERED

    # Verify database session created with recognition_source='AI' and handled_by=NULL
    session = VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm,
        exit_time__isnull=True,
    ).first()
    assert session is not None
    assert session.recognition_source == "AI"
    assert session.entry_handled_by is None
    assert session.entry_gate_id == gate.id

    # Verify ActivityLog written with masked plate
    log = (
        ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=gate.id,
            action=AUDIT_GATE_AUTO_CHECK_IN,
        )
        .order_by("-id")
        .first()
    )
    assert log is not None
    assert log.actor_account is None
    log_data = json.loads(log.message)
    assert log_data["reason"] == REASON_VALID_REGISTERED
    assert "*" in log_data["license_plate_masked"]

    # Verify telemetry in ActivityLog via serializer (Round 89: cache path dropped)
    serializer = ParkingGateSerializer(gate)
    assert serializer.data["last_auto_event"] is not None
    assert serializer.data["last_auto_event"]["action"] == AUDIT_GATE_AUTO_CHECK_IN
    assert "*" in serializer.data["last_auto_event"]["license_plate_masked"]
    assert cache.get(f"gate_last_auto_event:{gate.id}") is None

    # Verify voter cooldown set
    assert coordinator._voter.is_in_cooldown(gate.id, vehicle.license_plate)


def test_coordinator_auto_check_out_fee_zero():
    """Autonomous exit check-out for parked vehicle with zero fee (covered by active ticket)."""
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    assert gate is not None

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None

    ticket = Ticket.objects.filter(
        vehicle=vehicle, status="ACTIVE", deleted_at__isnull=True
    ).first()

    # Create an active open session
    entry_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    slot = ParkingSlot.objects.filter(
        status="AVAILABLE", deleted_at__isnull=True
    ).first()

    # Close previous sessions
    VehicleEntryExitLog.objects.filter(vehicle=vehicle, exit_time__isnull=True).update(
        exit_time=timezone.now()
    )

    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-TEST-{int(time.time())}",
        vehicle=vehicle,
        slot=slot,
        ticket=ticket,
        entry_gate=entry_gate,
        license_plate=vehicle.license_plate,
        recognition_source="AI",
        review_status="AUTO",
        entry_time=timezone.now(),
        fee_amount=Decimal("0.00"),
    )

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/out"})
    coordinator._managed_gates[gate.id] = gate

    scan_result = _create_mock_scan_result(vehicle.license_plate, confidence=95.0)

    with patch(
        "apps.parking.gate_worker.coordinator.calculate_parking_fee",
        return_value=Decimal("0.00"),
    ):
        decision = coordinator._evaluate_and_execute(
            gate, vehicle.license_plate, scan_result
        )

    assert decision.action == ACTION_AUTO_CHECK_OUT
    assert decision.audit_action == AUDIT_GATE_AUTO_CHECK_OUT
    assert decision.reason_code == REASON_VALID_FEE_ZERO

    # Verify session closed with exit_handled_by=NULL
    session.refresh_from_db()
    assert session.exit_time is not None
    assert session.exit_handled_by is None
    assert session.exit_gate_id == gate.id

    # Verify ActivityLog
    log = (
        ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=gate.id,
            action=AUDIT_GATE_AUTO_CHECK_OUT,
        )
        .order_by("-id")
        .first()
    )
    assert log is not None
    assert log.actor_account is None


def test_coordinator_hold_for_unregistered_vehicle():
    """Unregistered casual visitor at entry barrier results in HOLD (GATE_AUTO_NEEDS_STAFF)."""
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    unregistered_plate = "88B8-888.88"
    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/in"})
    coordinator._managed_gates[gate.id] = gate

    scan_result = _create_mock_scan_result(unregistered_plate, confidence=95.0)

    decision = coordinator._evaluate_and_execute(gate, unregistered_plate, scan_result)

    assert decision.action == ACTION_HOLD
    assert decision.audit_action == AUDIT_GATE_AUTO_NEEDS_STAFF
    assert decision.reason_code == REASON_UNREGISTERED_VEHICLE

    # Verify ActivityLog created for staff notification
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


def test_coordinator_hold_when_exit_fee_required():
    """Parked vehicle with fee > 0 holds barrier for cashier fee collection."""
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    assert gate is not None

    plate = "29A-999.99"
    # Create open session without active ticket
    entry_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    VehicleEntryExitLog.objects.create(
        session_code=f"#PK-TEST-FEE-{int(time.time())}",
        vehicle=None,
        slot=None,
        ticket=None,
        entry_gate=entry_gate,
        license_plate=plate,
        recognition_source="AI",
        entry_time=timezone.now(),
        fee_amount=Decimal("0.00"),
    )

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/out"})
    coordinator._managed_gates[gate.id] = gate
    scan_result = _create_mock_scan_result(plate, confidence=95.0)

    with patch(
        "apps.parking.gate_worker.coordinator.calculate_parking_fee",
        return_value=Decimal("20000.00"),
    ):
        decision = coordinator._evaluate_and_execute(gate, plate, scan_result)

    assert decision.action == ACTION_HOLD
    assert decision.audit_action == AUDIT_GATE_AUTO_PAYMENT_REQUIRED
    assert decision.reason_code == REASON_FEE_PAYMENT_REQUIRED

    # Verify ActivityLog
    log = (
        ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=gate.id,
            action=AUDIT_GATE_AUTO_PAYMENT_REQUIRED,
        )
        .order_by("-id")
        .first()
    )
    assert log is not None


def test_coordinator_heartbeat_and_camera_status():
    """Coordinator maintains camera_status in DB and holds advisory locks."""
    gate = ParkingGate.objects.filter(is_active=True).first()
    assert gate is not None

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/cam"})
    coordinator._managed_gates[gate.id] = gate

    lock = GateAdvisoryLock(gate.id)
    assert lock.acquire() is True
    try:
        coordinator._locks[gate.id] = lock
        assert lock.is_locked is True

        coordinator._update_gate_camera_status(gate, "DEGRADED")
        gate.refresh_from_db()
        assert gate.camera_status == "DEGRADED"

        coordinator._update_gate_camera_status(gate, "ONLINE")
        gate.refresh_from_db()
        assert gate.camera_status == "ONLINE"
    finally:
        coordinator.shutdown()
        lock.release()


def test_coordinator_concurrency_semaphore_limit():
    """OCR inference is gated by bounded concurrency semaphore."""
    coordinator = GateWorkerCoordinator(concurrency_limit=2)
    assert coordinator._ocr_semaphore._value == 2

    # Acquire all permits
    assert coordinator._ocr_semaphore.acquire(blocking=False) is True
    assert coordinator._ocr_semaphore.acquire(blocking=False) is True
    # Next acquisition fails (over capacity)
    assert coordinator._ocr_semaphore.acquire(blocking=False) is False

    # Release permit
    coordinator._ocr_semaphore.release()
    assert coordinator._ocr_semaphore.acquire(blocking=False) is True


# ==============================================================================
# 6. Management Command Tests
# ==============================================================================


def test_run_gate_worker_bounded_run_empty_streams():
    """run_gate_worker command with --duration runs for bounded time and exits cleanly."""
    t0 = time.monotonic()
    call_command("run_gate_worker", duration=0.2)
    elapsed = time.monotonic() - t0
    assert elapsed >= 0.15


def test_run_gate_worker_with_gate_filter(settings):
    """run_gate_worker with --gate filters and initializes only the specified gate."""
    settings.GATE_WORKER_STREAMS = json.dumps(
        {
            "IN_01": "http://mock/in1",
            "OUT_01": "http://mock/out1",
        }
    )

    coordinator = GateWorkerCoordinator(gate_code_filter="IN_01")
    assert "IN_01" in coordinator._streams_map
    assert "OUT_01" not in coordinator._streams_map


def test_run_gate_worker_clean_shutdown():
    """Coordinator shutdown stops readers, releases locks, and marks offline."""
    gate = ParkingGate.objects.filter(is_active=True).first()
    assert gate is not None

    coordinator = GateWorkerCoordinator(streams_override={gate.code: "http://mock/cam"})
    coordinator._managed_gates[gate.id] = gate
    lock = GateAdvisoryLock(gate.id)
    assert lock.acquire() is True
    coordinator._locks[gate.id] = lock

    coordinator.shutdown()

    assert not coordinator._is_running
    assert len(coordinator._locks) == 0
    assert len(coordinator._readers) == 0
    assert not lock.is_locked


@patch("apps.parking.gate_worker.coordinator.StreamReader")
def test_coordinator_initialize_and_process_gate_tick_end_to_end(mock_reader_cls):
    """Coordinator initializes configured gate, processes frames through voter, and executes decision."""
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    mock_reader = MagicMock()
    mock_reader.status = STATUS_STREAMING
    mock_reader.frames_read_count = 4
    mock_reader_cls.return_value = mock_reader

    coordinator = GateWorkerCoordinator(
        streams_override={gate.code: "http://mock/in"},
        concurrency_limit=2,
    )
    try:
        init_count = coordinator.initialize()
        assert init_count == 1
        assert gate.id in coordinator._managed_gates

        # Disable rate limit for fast 4-tick test
        coordinator._filters[gate.id] = MotionFilter(mad_threshold=1.0, max_fps=1000.0)

        mock_rec = MagicMock()
        mock_rec.recognize.return_value = _create_mock_scan_result(
            "88Z-999.99", confidence=95.0
        )

        with patch(
            "apps.parking.gate_worker.coordinator.get_plate_recognizer",
            return_value=mock_rec,
        ):
            for idx in range(1, 5):
                frame = np.full((64, 64, 3), idx * 30, dtype=np.uint8)
                mock_reader.get_latest_frame.return_value = (frame, float(idx))
                coordinator._process_gate_tick(gate)
                time.sleep(0.002)

        assert coordinator._ocr_processed_count >= 3
        coordinator._log_frame_stats()
    finally:
        coordinator.shutdown()


@patch("cv2.VideoCapture")
def test_stream_reader_resizes_oversized_frame_and_counts(mock_video_capture):
    """StreamReader resizes frames wider than max_width and increments frames_read_count."""
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True
    big_frame = np.full((720, 1280, 3), 100, dtype=np.uint8)
    mock_cap.read.return_value = (True, big_frame)
    mock_video_capture.return_value = mock_cap

    reader = StreamReader(
        gate_code="IN_RESIZE",
        stream_url="http://mock/hd",
        max_width=640,
    )
    reader.start()
    timeout = time.monotonic() + 2.0
    while time.monotonic() < timeout:
        if reader.frames_read_count > 0:
            break
        time.sleep(0.02)
    frame, _ = reader.get_latest_frame()
    reader.stop(timeout=1.0)
    assert frame is not None
    assert frame.shape[1] == 640
    assert reader.frames_read_count >= 1


# ==============================================================================
# 8. Multi-Replica Gate Filtering & Partitioning Tests (F7, TL-77)
# ==============================================================================


def test_run_gate_worker_with_comma_separated_gate_filter(settings):
    """Coordinator filters multiple comma-separated gate codes into streams map."""
    settings.GATE_WORKER_STREAMS = {
        "IN_01": "http://cam1",
        "IN_02": "http://cam2",
        "OUT_01": "http://cam3",
    }
    coordinator = GateWorkerCoordinator(gate_code_filter="IN_01, IN_02")
    assert "IN_01" in coordinator._streams_map
    assert "IN_02" in coordinator._streams_map
    assert "OUT_01" not in coordinator._streams_map
    assert len(coordinator._streams_map) == 2


def test_run_gate_worker_with_gate_id_filter(settings):
    """Coordinator resolves numeric gate IDs to gate codes via database."""
    gate = ParkingGate.objects.filter(is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Filter Test Gate",
            code="IN_FILTER_ID",
            gate_type="IN",
            is_active=True,
            camera_status="ONLINE",
        )
    settings.GATE_WORKER_STREAMS = {
        gate.code: "http://cam/filter_id",
        "OTHER_GATE": "http://cam/other",
    }
    coordinator = GateWorkerCoordinator(gate_code_filter=str(gate.id))
    assert gate.code in coordinator._streams_map
    assert "OTHER_GATE" not in coordinator._streams_map
    assert len(coordinator._streams_map) == 1


def test_run_gate_worker_command_comma_separated(settings):
    """run_gate_worker command accepts comma-separated --gate filter and duration."""
    gate = ParkingGate.objects.filter(is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="CLI Test Gate",
            code="IN_CLI_01",
            gate_type="IN",
            is_active=True,
            camera_status="ONLINE",
        )
    settings.GATE_WORKER_STREAMS = {
        gate.code: "http://mock/cli",
    }
    with patch("cv2.VideoCapture") as mock_cap:
        mock_instance = MagicMock()
        mock_instance.isOpened.return_value = True
        mock_instance.read.return_value = (
            True,
            np.zeros((100, 100, 3), dtype=np.uint8),
        )
        mock_cap.return_value = mock_instance
        call_command("run_gate_worker", gate=f"{gate.code},NON_EXISTENT", duration=0.1)


def test_multi_replica_gate_subset_partitioning(settings):
    """Two worker replicas partition gate subsets with mutual exclusive advisory locks."""
    gates = list(ParkingGate.objects.filter(is_active=True)[:2])
    if len(gates) < 2:
        g1 = ParkingGate.objects.create(
            name="Replica Gate 1",
            code="REP_01",
            gate_type="IN",
            is_active=True,
        )
        g2 = ParkingGate.objects.create(
            name="Replica Gate 2",
            code="REP_02",
            gate_type="OUT",
            is_active=True,
        )
        gates = [g1, g2]

    gate1, gate2 = gates[0], gates[1]
    streams_map = {
        gate1.code: "http://cam/rep1",
        gate2.code: "http://cam/rep2",
    }
    settings.GATE_WORKER_STREAMS = streams_map

    with patch("cv2.VideoCapture") as mock_cap:
        mock_instance = MagicMock()
        mock_instance.isOpened.return_value = True
        mock_instance.read.return_value = (True, np.zeros((64, 64, 3), dtype=np.uint8))
        mock_cap.return_value = mock_instance

        coord1 = GateWorkerCoordinator(gate_code_filter=gate1.code)
        coord2 = GateWorkerCoordinator(gate_code_filter=gate2.code)

        try:
            assert coord1.initialize() == 1
            assert coord2.initialize() == 1

            assert gate1.id in coord1._locks
            assert gate2.id not in coord1._locks

            assert gate2.id in coord2._locks
            assert gate1.id not in coord2._locks

            active_locks = get_active_gate_worker_lock_ids()
            assert gate1.id in active_locks
            assert gate2.id in active_locks
        finally:
            coord1.shutdown()
            coord2.shutdown()


def test_get_active_gate_worker_lock_ids_postgresql_database_filter():
    """
    Round 90 (G9d, Decision 9d): In PostgreSQL, get_active_gate_worker_lock_ids must join pg_database
    and filter by d.datname = current_database() to avoid picking up locks from other databases.
    """
    from django.db import connection

    if connection.vendor == "postgresql":
        res = get_active_gate_worker_lock_ids()
        assert isinstance(res, set)
    else:
        with patch.object(connection, "vendor", "postgresql"):
            mock_cursor = MagicMock()
            mock_cursor.fetchall.return_value = [(101,), (102,)]
            with patch.object(connection, "cursor") as mock_conn_cursor:
                mock_conn_cursor.return_value.__enter__.return_value = mock_cursor
                res = get_active_gate_worker_lock_ids()
                assert res == {101, 102}
                mock_cursor.execute.assert_called_once()
                sql = mock_cursor.execute.call_args[0][0]
                assert "JOIN pg_database d ON l.database = d.oid" in sql
                assert "d.datname = current_database()" in sql
                assert "l.classid = %s" in sql


def test_coordinator_auto_checkout_via_wallet_when_sufficient():
    """
    WP4 D6 Row 11: Registered vehicle with fee > 0 and sufficient ACTIVE wallet
    triggers AUTO_CHECK_OUT / VALID_WALLET_PAID and debits wallet via PARKING_FEE.
    """
    import uuid
    from datetime import timedelta

    from apps.accounts.models import Account
    from apps.content.models import Notification
    from apps.customers.models import Customer
    from apps.parking.services.gate_decision import (
        ACTION_AUTO_CHECK_OUT,
        REASON_VALID_WALLET_PAID,
    )
    from apps.tickets.models import Payment
    from apps.vehicles.models import Vehicle, VehicleType
    from apps.wallet.models import Wallet, WalletTransaction
    from apps.wallet.services.wallet import credit_wallet

    in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    assert in_gate and out_gate

    suffix = f"{uuid.uuid4().int % 100000:05d}"
    acct = Account.objects.create(
        email=f"gw_wal_{suffix}@parking.local",
        role="CUSTOMER",
        is_active=True,
        password="!dummy_password_hash",
    )
    cust = Customer.objects.create(
        account=acct,
        code=f"KHG{suffix}",
        full_name=f"Khach GW {suffix}",
        phone=f"0955{suffix[-6:].zfill(6)}",
        identity_card_number=f"079097{suffix[-6:].zfill(6)}",
    )
    vtype = VehicleType.objects.first()
    veh = Vehicle.objects.create(
        code=f"XEG{suffix}",
        license_plate=f"51J-{suffix[-5:].zfill(5)}",
        license_plate_norm=f"51J{suffix[-5:].zfill(5)}",
        vehicle_type=vtype,
        customer=cust,
        model_name="Mazda 3",
    )
    wallet = Wallet.objects.create(
        customer=cust, balance=Decimal("0.00"), status="ACTIVE"
    )
    credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("100000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"gw-init-{suffix}",
    )

    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-GW-{suffix}",
        vehicle=veh,
        entry_gate=in_gate,
        license_plate=veh.license_plate,
        license_plate_norm=veh.license_plate_norm,
        entry_time=timezone.now() - timedelta(hours=2),
        recognition_source="AI",
        review_status="AUTO",
    )

    coordinator = GateWorkerCoordinator(
        streams_override={out_gate.code: "http://mock/out"}
    )
    coordinator._managed_gates[out_gate.id] = out_gate
    scan_result = _create_mock_scan_result(veh.license_plate, confidence=97.0)

    decision = coordinator._evaluate_and_execute(
        out_gate, veh.license_plate, scan_result
    )
    assert decision.action == ACTION_AUTO_CHECK_OUT
    assert decision.reason_code == REASON_VALID_WALLET_PAID

    session.refresh_from_db()
    wallet.refresh_from_db()
    assert session.exit_time is not None
    assert session.fee_amount == Decimal("20000.00")
    assert wallet.balance == Decimal("80000.00")
    assert Payment.objects.filter(
        session=session, method="WALLET", status="PAID"
    ).exists()
    assert WalletTransaction.objects.filter(
        wallet=wallet,
        kind="PARKING_FEE",
        idempotency_key=f"checkout-session-{session.id}",
    ).exists()
    assert Notification.objects.filter(recipient_account=acct).count() == 0


def test_coordinator_pending_exit_d8_reevaluation_on_topup():
    """
    WP4 D8: When wallet is insufficient at exit:
    - Holds with WALLET_INSUFFICIENT, sends 1 PAYMENT notification, does NOT set 30s voter cooldown.
    - Registers pending exit; recheck runs even with stationary vehicle (before motion_filter).
    - After wallet is topped up, _recheck_pending_exits auto-checks out via WALLET & sets cooldown.
    """
    import uuid
    from datetime import timedelta

    from apps.accounts.models import Account
    from apps.content.models import Notification
    from apps.customers.models import Customer
    from apps.parking.services.gate_decision import REASON_WALLET_INSUFFICIENT
    from apps.tickets.models import Payment
    from apps.vehicles.models import Vehicle, VehicleType
    from apps.wallet.models import Wallet
    from apps.wallet.services.wallet import credit_wallet

    in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    assert in_gate and out_gate

    suffix = f"{uuid.uuid4().int % 100000:05d}"
    acct = Account.objects.create(
        email=f"gw_d8_{suffix}@parking.local",
        role="CUSTOMER",
        is_active=True,
        password="!dummy_password_hash",
    )
    cust = Customer.objects.create(
        account=acct,
        code=f"KHD{suffix}",
        full_name=f"Khach D8 {suffix}",
        phone=f"0944{suffix[-6:].zfill(6)}",
        identity_card_number=f"079096{suffix[-6:].zfill(6)}",
    )
    vtype = VehicleType.objects.first()
    veh = Vehicle.objects.create(
        code=f"XED{suffix}",
        license_plate=f"51L-{suffix[-5:].zfill(5)}",
        license_plate_norm=f"51L{suffix[-5:].zfill(5)}",
        vehicle_type=vtype,
        customer=cust,
        model_name="K3",
    )
    wallet = Wallet.objects.create(
        customer=cust, balance=Decimal("0.00"), status="ACTIVE"
    )
    credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("5000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"d8-init-{suffix}",
    )

    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-D8-{suffix}",
        vehicle=veh,
        entry_gate=in_gate,
        license_plate=veh.license_plate,
        license_plate_norm=veh.license_plate_norm,
        entry_time=timezone.now() - timedelta(hours=2),  # fee = 20,000
        recognition_source="AI",
        review_status="AUTO",
    )

    coordinator = GateWorkerCoordinator(
        streams_override={out_gate.code: "http://mock/out"}
    )
    coordinator._managed_gates[out_gate.id] = out_gate
    coordinator._pending_recheck_seconds = (
        0.0  # Immediate recheck for deterministic test
    )
    mock_reader = MagicMock()
    mock_reader.status = "STREAMING"
    mock_reader.get_latest_frame.return_value = (None, 0.0)  # Stationary / no new frame
    coordinator._readers[out_gate.id] = mock_reader
    coordinator._filters[out_gate.id] = MagicMock()

    scan_result = _create_mock_scan_result(veh.license_plate, confidence=96.0)
    decision = coordinator._evaluate_and_execute(
        out_gate, veh.license_plate, scan_result
    )

    assert decision.action == ACTION_HOLD
    assert decision.reason_code == REASON_WALLET_INSUFFICIENT
    assert not coordinator._voter.is_in_cooldown(out_gate.id, veh.license_plate)
    assert (out_gate.id, veh.license_plate_norm) in coordinator._pending_exits
    assert (
        Notification.objects.filter(
            recipient_account=acct, notification_type="PAYMENT"
        ).count()
        == 1
    )

    # Tick while still insufficient: no duplicate notifications, still pending
    coordinator._process_gate_tick(out_gate)
    assert (
        Notification.objects.filter(
            recipient_account=acct, notification_type="PAYMENT"
        ).count()
        == 1
    )
    assert (out_gate.id, veh.license_plate_norm) in coordinator._pending_exits
    session.refresh_from_db()
    assert session.exit_time is None

    # Customer tops up wallet!
    credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("50000.00"),
        kind="TOPUP_VIETQR",
        idempotency_key=f"d8-topup-{suffix}",
    )

    # Next tick (with stationary camera frame=None): _recheck_pending_exits runs before motion filter and auto-checks out!
    coordinator._process_gate_tick(out_gate)
    assert (out_gate.id, veh.license_plate_norm) not in coordinator._pending_exits
    session.refresh_from_db()
    wallet.refresh_from_db()
    assert session.exit_time is not None
    assert session.fee_amount == Decimal("20000.00")
    assert wallet.balance == Decimal("35000.00")
    assert Payment.objects.filter(
        session=session, method="WALLET", status="PAID"
    ).exists()
