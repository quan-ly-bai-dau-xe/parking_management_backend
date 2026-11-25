"""
Tests for background snapshot upload in headless gate worker (Round 89, F3, TL-2).
Covers:
- Bounded JPEG frame encoding (max_side <= 1280px, quality 85).
- Asynchronous ThreadPoolExecutor dispatch off the barrier critical path.
- Success path: URL attached to VehicleEntryExitLog for check-in and check-out.
- Failure path with real upload service (fake credentials): URL remains None, session unaffected, worker does not crash.
- Hard timeout handling without stalling coordinator.
- Non-blocking barrier decision latency verification.
- Safe coordinator shutdown and thread cleanup.
"""

from __future__ import annotations

import io
import logging
import time
from decimal import Decimal
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from django.core.cache import cache
from django.db.models import Max
from django.utils import timezone
from PIL import Image

from apps.audit.models import ActivityLog
from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
from apps.parking.gate_worker.snapshot import (
    SnapshotUploader,
    resize_and_encode_jpeg,
    upload_session_snapshot_async,
)
from apps.parking.models import (
    ParkingGate,
    ParkingSlot,
    SlotAllowedVehicleType,
    VehicleEntryExitLog,
)
from apps.parking.services.gate_decision import (
    ACTION_AUTO_CHECK_IN,
    ACTION_AUTO_CHECK_OUT,
    AUDIT_GATE_AUTO_CHECK_IN,
    AUDIT_GATE_AUTO_CHECK_OUT,
)
from apps.parking.services.ocr import PlateCandidate, PlateScanResult
from apps.parking.services.upload import save_processed_image
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle


@pytest.fixture(autouse=True)
def clean_cache():
    """Wipe cache before and after each test."""
    cache.clear()
    yield
    cache.clear()


def io_open(raw_bytes: bytes) -> Image.Image:
    """Helper to open JPEG bytes into PIL Image."""
    return Image.open(io.BytesIO(raw_bytes))


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


# ==============================================================================
# 1. Bounded JPEG Frame Encoding Tests
# ==============================================================================


def test_resize_and_encode_jpeg_downscale_oversized_landscape():
    """1080p (1920x1080) landscape frame is scaled down so max dimension is <= 1280px."""
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    frame[:, :, 0] = 50
    frame[:, :, 1] = 100
    frame[:, :, 2] = 150

    jpeg_bytes, w, h = resize_and_encode_jpeg(frame, max_side=1280, quality=85)

    assert max(w, h) <= 1280
    assert w == 1280
    assert h == 720  # 16:9 ratio preserved

    pil_img = io_open(jpeg_bytes)
    assert pil_img.format == "JPEG"
    assert pil_img.size == (1280, 720)


def test_resize_and_encode_jpeg_downscale_oversized_portrait():
    """2K (1440x2560) portrait frame is scaled down so max dimension is <= 1280px."""
    frame = np.zeros((2560, 1440, 3), dtype=np.uint8)

    jpeg_bytes, w, h = resize_and_encode_jpeg(frame, max_side=1280, quality=85)

    assert max(w, h) <= 1280
    assert h == 1280
    assert w == 720

    pil_img = io_open(jpeg_bytes)
    assert pil_img.format == "JPEG"
    assert pil_img.size == (720, 1280)


def test_resize_and_encode_jpeg_preserves_smaller_dimensions():
    """Frame smaller than 1280px (640x480) is not upscaled."""
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    jpeg_bytes, w, h = resize_and_encode_jpeg(frame, max_side=1280, quality=85)

    assert w == 640
    assert h == 480
    pil_img = io_open(jpeg_bytes)
    assert pil_img.size == (640, 480)


def test_resize_and_encode_jpeg_empty_frame_raises_error():
    """Empty ndarray or None raises ValueError without corrupting state."""
    with pytest.raises(ValueError, match="Cannot encode"):
        resize_and_encode_jpeg(np.zeros((0, 0, 3), dtype=np.uint8))

    with pytest.raises(ValueError, match="Cannot encode"):
        resize_and_encode_jpeg(None)


# ==============================================================================
# 2. Success Path Tests (Mock / Fake Uploader)
# ==============================================================================


@pytest.mark.django_db(transaction=True)
def test_coordinator_snapshot_upload_success_check_in():
    """
    On automated check-in, decisive frame is dispatched to background uploader,
    and entry_image_url is attached to the session in the database.
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

    # Ensure no open session exists for this plate
    VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm, exit_time__isnull=True
    ).update(exit_time=timezone.now())

    fake_url = "https://res.cloudinary.com/fake-cloud/image/upload/v1/parking_scans/2026/11/09/abcdef1234567890abcdef1234567890.jpg"
    fake_uploader_service = MagicMock(return_value=(None, fake_url))

    uploader = SnapshotUploader(upload_service=fake_uploader_service)
    coordinator = GateWorkerCoordinator(
        streams_override={gate.code: "http://mock/in"},
        snapshot_uploader=uploader,
    )
    coordinator._managed_gates[gate.id] = gate

    scan_result = _create_mock_scan_result(vehicle.license_plate, confidence=96.0)
    test_frame = np.ones((720, 1280, 3), dtype=np.uint8) * 120

    decision = coordinator._evaluate_and_execute(
        gate=gate,
        voted_plate=vehicle.license_plate,
        scan_result=scan_result,
        decisive_frame=test_frame,
    )

    assert decision.action == ACTION_AUTO_CHECK_IN

    # Wait for background snapshot upload task to finish
    uploader.shutdown(wait=True)

    # Verify session was updated in database
    session = (
        VehicleEntryExitLog.objects.filter(
            license_plate_norm=vehicle.license_plate_norm,
            exit_time__isnull=True,
        )
        .order_by("-id")
        .first()
    )
    assert session is not None
    assert session.entry_image_url == fake_url
    assert session.exit_image_url is None

    # Verify ActivityLog created for automated check-in
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


@pytest.mark.django_db(transaction=True)
def test_coordinator_snapshot_upload_success_check_out():
    """
    On automated check-out, decisive frame is dispatched to background uploader,
    and exit_image_url is attached to the session in the database.
    """
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    assert gate is not None

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None

    ticket = Ticket.objects.filter(
        vehicle=vehicle, status="ACTIVE", deleted_at__isnull=True
    ).first()
    if not ticket:
        t = (
            Ticket.objects.filter(status="ACTIVE", deleted_at__isnull=True)
            .select_related("vehicle")
            .first()
        )
        if t and t.vehicle:
            vehicle = t.vehicle
            ticket = t

    entry_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()

    # Ensure slot is compatible with vehicle.vehicle_type to satisfy trigger TL-38
    allowed_slot_ids = SlotAllowedVehicleType.objects.filter(
        vehicle_type=vehicle.vehicle_type
    ).values_list("slot_id", flat=True)
    slot = ParkingSlot.objects.filter(
        id__in=allowed_slot_ids, status="AVAILABLE", deleted_at__isnull=True
    ).first()
    if slot is None:
        slot = ParkingSlot.objects.filter(id__in=allowed_slot_ids).first()
        if slot:
            slot.status = "AVAILABLE"
            slot.save(update_fields=["status"])
    assert slot is not None

    # Close previous sessions
    VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm, exit_time__isnull=True
    ).update(exit_time=timezone.now())

    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-SNAP-{int(time.time())}",
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

    fake_url = "https://res.cloudinary.com/fake-cloud/image/upload/v1/parking_scans/2026/11/09/99887766554433221100aabbccddeeff.jpg"
    fake_uploader_service = MagicMock(return_value=(None, fake_url))

    uploader = SnapshotUploader(upload_service=fake_uploader_service)
    coordinator = GateWorkerCoordinator(
        streams_override={gate.code: "http://mock/out"},
        snapshot_uploader=uploader,
    )
    coordinator._managed_gates[gate.id] = gate

    scan_result = _create_mock_scan_result(vehicle.license_plate, confidence=95.0)
    test_frame = np.ones((720, 1280, 3), dtype=np.uint8) * 200

    with patch(
        "apps.parking.gate_worker.coordinator.calculate_parking_fee",
        return_value=Decimal("0.00"),
    ):
        decision = coordinator._evaluate_and_execute(
            gate=gate,
            voted_plate=vehicle.license_plate,
            scan_result=scan_result,
            decisive_frame=test_frame,
        )

    assert decision.action == ACTION_AUTO_CHECK_OUT

    # Wait for background upload completion
    uploader.shutdown(wait=True)

    # Verify session has exit_image_url
    session.refresh_from_db()
    assert session.exit_image_url == fake_url

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


# ==============================================================================
# 3. Failure Path Tests (Real Upload Service with Fake Credentials & Timeout)
# ==============================================================================


@pytest.mark.django_db(transaction=True)
def test_coordinator_snapshot_upload_failure_with_real_upload_service(
    caplog, fake_cloudinary_storage
):
    """
    When the real upload service fails (e.g. invalid Cloudinary credentials in test environment),
    the session remains valid in database, image URL remains None/empty, the worker does NOT crash,
    and a warning log is recorded with the failure details.
    """
    import cloudinary.exceptions

    fake_cloudinary_storage.force_upload_failure = (
        cloudinary.exceptions.AuthorizationRequired("Invalid api_key test-key")
    )
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None

    # Ensure no open session exists for this plate
    VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm, exit_time__isnull=True
    ).update(exit_time=timezone.now())

    # Use the REAL save_processed_image function (with fake credentials in test settings)
    uploader = SnapshotUploader(upload_service=save_processed_image)
    coordinator = GateWorkerCoordinator(
        streams_override={gate.code: "http://mock/in"},
        snapshot_uploader=uploader,
    )
    coordinator._managed_gates[gate.id] = gate

    scan_result = _create_mock_scan_result(vehicle.license_plate, confidence=96.0)
    test_frame = np.ones((720, 1280, 3), dtype=np.uint8) * 50

    start_log_id = ActivityLog.objects.aggregate(max_id=Max("id"))["max_id"] or 0

    with caplog.at_level(logging.WARNING):
        # Decision executes without raising any exception
        decision = coordinator._evaluate_and_execute(
            gate=gate,
            voted_plate=vehicle.license_plate,
            scan_result=scan_result,
            decisive_frame=test_frame,
        )
        assert decision.action == ACTION_AUTO_CHECK_IN

        # Wait for upload attempt to fail gracefully
        uploader.shutdown(wait=True)

    # Session exists in database with entry_image_url empty (None)
    session = (
        VehicleEntryExitLog.objects.filter(
            license_plate_norm=vehicle.license_plate_norm,
            exit_time__isnull=True,
        )
        .order_by("-id")
        .first()
    )
    assert session is not None
    assert session.entry_image_url is None

    # Verify warning log was emitted and failure reason recorded on the gate auto event
    assert "Snapshot upload failed for session" in caplog.text
    from apps.parking.serializers.gates import ParkingGateSerializer

    latest_event = ParkingGateSerializer(gate).data["last_auto_event"]
    assert latest_event is not None
    assert latest_event["action"] == AUDIT_GATE_AUTO_CHECK_IN
    assert latest_event["snapshot_error"] is not None
    assert "AuthorizationRequired" in latest_event["snapshot_error"]
    assert "test-key" not in latest_event["snapshot_error"]

    # Verify Finding G7: exactly 1 decision row and 1 snapshot failure row (not two decision rows)
    assert (
        ActivityLog.objects.filter(
            id__gt=start_log_id,
            entity_type="parking_gate",
            entity_id=gate.id,
            action=AUDIT_GATE_AUTO_CHECK_IN,
        ).count()
        == 1
    )
    assert (
        ActivityLog.objects.filter(
            id__gt=start_log_id,
            entity_type="parking_gate",
            entity_id=gate.id,
            action="GATE_AUTO_SNAPSHOT_FAILED",
        ).count()
        == 1
    )


@pytest.mark.django_db(transaction=True)
def test_coordinator_snapshot_upload_hard_timeout(caplog):
    """
    When upload service hangs or exceeds timeout (default 5.0s, configured to 0.5s for test),
    it times out gracefully, leaves URL empty, logs warning, and does not block worker.
    """
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None

    VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm, exit_time__isnull=True
    ).update(exit_time=timezone.now())

    def slow_upload_service(processed):
        # Simulate network hang exceeding timeout
        time.sleep(2.0)
        return None, "https://res.cloudinary.com/late/image/upload/late.jpg"

    uploader = SnapshotUploader(timeout=0.5, upload_service=slow_upload_service)
    coordinator = GateWorkerCoordinator(
        streams_override={gate.code: "http://mock/in"},
        snapshot_uploader=uploader,
    )
    coordinator._managed_gates[gate.id] = gate

    scan_result = _create_mock_scan_result(vehicle.license_plate, confidence=96.0)
    test_frame = np.ones((480, 640, 3), dtype=np.uint8) * 80

    with caplog.at_level(logging.WARNING):
        decision = coordinator._evaluate_and_execute(
            gate=gate,
            voted_plate=vehicle.license_plate,
            scan_result=scan_result,
            decisive_frame=test_frame,
        )
        assert decision.action == ACTION_AUTO_CHECK_IN

        # Wait for timeout to fire in background
        uploader.shutdown(wait=True)

    session = (
        VehicleEntryExitLog.objects.filter(
            license_plate_norm=vehicle.license_plate_norm,
            exit_time__isnull=True,
        )
        .order_by("-id")
        .first()
    )
    assert session is not None
    assert session.entry_image_url is None
    assert "upload timed out after" in caplog.text
    from apps.parking.serializers.gates import ParkingGateSerializer

    timeout_event = ParkingGateSerializer(gate).data["last_auto_event"]
    assert timeout_event is not None
    assert (
        timeout_event["snapshot_error"] == "TimeoutError: upload timed out after 0.5s"
    )


@pytest.mark.django_db(transaction=True)
def test_n_checkins_produce_exactly_n_checkin_rows_on_snapshot_failure():
    """
    Finding G7 / Decision 7: Verify that N automated check-ins with failed snapshot uploads
    produce EXACTLY N GATE_AUTO_CHECK_IN ActivityLog rows (not 2N) and N GATE_AUTO_SNAPSHOT_FAILED rows.
    Additionally, last_auto_event must maintain the decision action and attach the snapshot error.
    """
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    def failing_upload_service(processed):
        raise ConnectionError("Cloudinary gateway unreachable (injected)")

    uploader = SnapshotUploader(upload_service=failing_upload_service)
    coordinator = GateWorkerCoordinator(
        streams_override={gate.code: "http://mock/in"},
        snapshot_uploader=uploader,
    )
    coordinator._managed_gates[gate.id] = gate

    vehicles = list(Vehicle.objects.filter(deleted_at__isnull=True)[:3])
    assert len(vehicles) >= 2

    # Baseline log id for gate (ActivityLog is strictly append-only)
    start_log_id = ActivityLog.objects.aggregate(max_id=Max("id"))["max_id"] or 0

    n = len(vehicles)
    for i, v in enumerate(vehicles):
        VehicleEntryExitLog.objects.filter(
            license_plate_norm=v.license_plate_norm, exit_time__isnull=True
        ).update(exit_time=timezone.now())

        scan_result = _create_mock_scan_result(v.license_plate, confidence=95.0)
        test_frame = np.ones((480, 640, 3), dtype=np.uint8) * (50 + i * 10)

        decision = coordinator._evaluate_and_execute(
            gate=gate,
            voted_plate=v.license_plate,
            scan_result=scan_result,
            decisive_frame=test_frame,
        )
        assert decision.action == ACTION_AUTO_CHECK_IN

    # Wait for all background uploads to complete/fail
    uploader.shutdown(wait=True)

    # 1 decision = 1 decision row
    checkin_count = ActivityLog.objects.filter(
        id__gt=start_log_id,
        entity_type="parking_gate",
        entity_id=gate.id,
        action=AUDIT_GATE_AUTO_CHECK_IN,
    ).count()
    assert checkin_count == n, (
        f"Expected exactly {n} check-in rows, got {checkin_count}"
    )

    snapshot_fail_count = ActivityLog.objects.filter(
        id__gt=start_log_id,
        entity_type="parking_gate",
        entity_id=gate.id,
        action="GATE_AUTO_SNAPSHOT_FAILED",
    ).count()
    assert snapshot_fail_count == n, (
        f"Expected exactly {n} failure rows, got {snapshot_fail_count}"
    )

    from apps.parking.serializers.gates import ParkingGateSerializer

    last_event = ParkingGateSerializer(gate).data["last_auto_event"]
    assert last_event is not None
    assert last_event["action"] == AUDIT_GATE_AUTO_CHECK_IN
    assert last_event["snapshot_error"] is not None
    assert "ConnectionError" in last_event["snapshot_error"]


# ==============================================================================
# 4. Barrier Latency Isolation Test
# ==============================================================================


@pytest.mark.django_db(transaction=True)
def test_barrier_decision_latency_unaffected_by_slow_upload():
    """
    Confirm deterministically that an in-flight upload does NOT block barrier opening:
    _evaluate_and_execute returns before slow_uploader is allowed to finish.
    """
    import threading

    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert gate is not None

    vehicle = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert vehicle is not None

    VehicleEntryExitLog.objects.filter(
        license_plate_norm=vehicle.license_plate_norm, exit_time__isnull=True
    ).update(exit_time=timezone.now())

    allow_upload_finish = threading.Event()
    upload_completed = threading.Event()

    def slow_uploader(processed):
        allow_upload_finish.wait(timeout=5.0)
        upload_completed.set()
        return None, "https://res.cloudinary.com/slow/upload/v1/test.jpg"

    uploader = SnapshotUploader(timeout=5.0, upload_service=slow_uploader)
    coordinator = GateWorkerCoordinator(
        streams_override={gate.code: "http://mock/in"},
        snapshot_uploader=uploader,
    )
    coordinator._managed_gates[gate.id] = gate

    scan_result = _create_mock_scan_result(vehicle.license_plate, confidence=96.0)
    test_frame = np.ones((720, 1280, 3), dtype=np.uint8) * 100

    decision = coordinator._evaluate_and_execute(
        gate=gate,
        voted_plate=vehicle.license_plate,
        scan_result=scan_result,
        decisive_frame=test_frame,
    )

    assert decision.action == ACTION_AUTO_CHECK_IN
    assert upload_completed.is_set() is False

    allow_upload_finish.set()
    uploader.shutdown(wait=True)
    assert upload_completed.is_set() is True


# ==============================================================================
# 5. Coordinator Shutdown & Standalone Function Tests
# ==============================================================================


@pytest.mark.django_db
def test_coordinator_shutdown_safely_terminates_uploader():
    """coordinator.shutdown() properly shuts down the snapshot uploader thread pool."""
    gate = ParkingGate.objects.filter(is_active=True).first()
    assert gate is not None

    uploader = SnapshotUploader()
    coordinator = GateWorkerCoordinator(
        streams_override={gate.code: "http://mock/in"},
        snapshot_uploader=uploader,
    )
    coordinator._managed_gates[gate.id] = gate

    assert uploader.is_shutdown is False

    coordinator.shutdown()

    assert uploader.is_shutdown is True
    assert coordinator._is_running is False


@pytest.mark.django_db(transaction=True)
def test_upload_session_snapshot_async_standalone_helper():
    """upload_session_snapshot_async standalone function dispatches task and updates DB."""
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-STANDALONE-{int(time.time())}",
        entry_gate=gate,
        license_plate="51A-999.99",
        entry_time=timezone.now(),
    )

    fake_url = "https://res.cloudinary.com/test/image/upload/v1/standalone.jpg"
    uploader = SnapshotUploader(upload_service=MagicMock(return_value=(None, fake_url)))

    test_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    future = upload_session_snapshot_async(
        session_id=session.id,
        frame=test_frame,
        is_entry=True,
        uploader=uploader,
    )
    assert future is not None

    uploader.shutdown(wait=True)

    session.refresh_from_db()
    assert session.entry_image_url == fake_url

    from django.db import connections

    connections.close_all()


@pytest.mark.django_db
def test_snapshot_uploader_handles_malformed_frames_and_idempotent_shutdown():
    """Empty, None, NaN, and post-shutdown frames are safely ignored without crashing."""
    uploader = SnapshotUploader(
        upload_service=MagicMock(return_value=(None, "https://example.com/ok.jpg"))
    )
    assert uploader.dispatch_upload(session_id=1, frame=None, is_entry=True) is None
    assert (
        uploader.dispatch_upload(session_id=1, frame=np.array([]), is_entry=True)
        is None
    )

    uploader.shutdown(wait=True)
    uploader.shutdown(wait=True)
    assert uploader.is_shutdown is True
    assert (
        uploader.dispatch_upload(
            session_id=1,
            frame=np.zeros((64, 64, 3), dtype=np.uint8),
            is_entry=True,
        )
        is None
    )
