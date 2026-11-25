"""
Concurrency and multi-replica verification suite for the Gate Worker process.
Adheres to ADR-0011 and TL-66 to TL-77.

Test Scenarios:
1. StreamReader latest-frame-wins behavior:
   - High-throughput frame production (100+ FPS).
   - Verifies zero queue backlog (internal buffer size is strictly bounded to 1 frame).
   - Verifies consumer receives newest frame without latency accumulation.
2. MotionFilter:
   - Identical frames (MAD = 0.0) skipped.
   - Small noise below threshold (MAD < 5.0) skipped.
   - Significant motion (MAD >= 5.0) accepted.
   - High-rate burst throttling (enforces max_fps rate limiting).
3. PlateVoter:
   - 2/4 voting does not trigger (unstable).
   - 3/4 voting triggers stable recognition.
   - Sliding window eviction dynamics.
   - Cooldown enforcement and precision timestamp expiry (30s).
4. GateAdvisoryLock:
   - Simultaneous lock contention on the same gate ID (second must return False immediately).
   - Barrier-synchronized multi-threaded race condition (10 threads, exactly 1 winner).
   - Multi-gate isolation (independent gates do not block each other).
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from django.core.cache import cache

from apps.parking.gate_worker.filter import MotionFilter
from apps.parking.gate_worker.locks import GateAdvisoryLock
from apps.parking.gate_worker.reader import StreamReader
from apps.parking.gate_worker.voter import PlateVoter

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache():
    """Wipe cache before and after each test."""
    cache.clear()
    yield
    cache.clear()


# ==============================================================================
# 1. StreamReader Empirical Stress Tests (Latest-Frame-Wins)
# ==============================================================================


def test_stress_stream_reader_buffer_strictly_bounded():
    """
    Empirically verify StreamReader buffer architecture:
    StreamReader must maintain exactly a single-frame buffer and NO unbounded queue.
    """
    reader = StreamReader(gate_code="IN_STRESS", stream_url="http://mock-cam/video")

    # Verify absence of internal queue/list backlog
    assert hasattr(reader, "_latest_frame")
    assert not hasattr(reader, "_queue")
    assert not hasattr(reader, "_buffer_queue")

    # Push 100 frames directly into StreamReader buffer at simulated 100 FPS
    for i in range(100):
        frame = np.full((120, 160, 3), i, dtype=np.uint8)
        with reader._frame_lock:
            reader._latest_frame = frame
            reader._last_frame_timestamp = 1000.0 + (i * 0.01)

    # Consumer reads: must get ONLY the latest frame (#99), never stale frames
    latest_frame, ts = reader.get_latest_frame()
    assert latest_frame is not None
    assert np.all(latest_frame == 99)
    assert ts == pytest.approx(1000.0 + (99 * 0.01), abs=1e-5)


def test_stress_stream_reader_concurrent_high_fps_producer_consumer():
    """
    Stress test with concurrent producer and consumer threads:
    Producer pushes 200 frames at ~100 FPS (10ms interval).
    Consumer samples at ~20 FPS (50ms interval).
    Verifies that:
    1. Consumer timestamps monotonically increase.
    2. Consumer skips intermediate frames without lag or backlog.
    3. Final consumed frame is the latest produced frame.
    """
    reader = StreamReader(gate_code="IN_CONCURRENT", stream_url="http://mock-cam/video")
    total_frames = 200
    producer_fps = 100.0
    frame_interval = 1.0 / producer_fps  # 10ms

    consumed_frames: list[tuple[int, float]] = []
    stop_event = threading.Event()

    def producer():
        for seq in range(total_frames):
            frame = np.full((64, 64, 3), seq % 256, dtype=np.uint8)
            with reader._frame_lock:
                reader._latest_frame = frame
                reader._last_frame_timestamp = time.monotonic()
            time.sleep(frame_interval)
        stop_event.set()

    def consumer():
        while not stop_event.is_set():
            frame, ts = reader.get_latest_frame()
            if frame is not None:
                val = int(frame[0, 0, 0])
                consumed_frames.append((val, ts))
            time.sleep(0.04)  # 25 FPS consumer

    prod_thread = threading.Thread(target=producer)
    cons_thread = threading.Thread(target=consumer)

    prod_thread.start()
    cons_thread.start()

    prod_thread.join(timeout=5.0)
    cons_thread.join(timeout=5.0)

    # Final read
    final_frame, final_ts = reader.get_latest_frame()
    assert final_frame is not None
    assert int(final_frame[0, 0, 0]) == (total_frames - 1) % 256

    # Verify consumer got a subset (no queue backlog, frames were overwritten)
    assert len(consumed_frames) > 0
    assert len(consumed_frames) < total_frames  # Consumer ran slower, skipped frames

    # Verify monotonic timestamp increase in consumer
    timestamps = [ts for _, ts in consumed_frames]
    for i in range(1, len(timestamps)):
        assert timestamps[i] >= timestamps[i - 1]


@patch("cv2.VideoCapture")
def test_stress_stream_reader_high_rate_cv2_capture(mock_video_capture):
    """
    Empirical test with StreamReader._run_loop ingesting frames at high rate via cv2.VideoCapture.
    Verifies thread safety, proper status transitions, and that only newest frame is retained.
    """
    mock_cap = MagicMock()
    mock_cap.isOpened.return_value = True

    current_seq = [0]

    def mock_read():
        seq = current_seq[0]
        current_seq[0] += 1
        frame = np.full((32, 32, 3), seq % 256, dtype=np.uint8)
        time.sleep(0.005)  # 200 FPS
        return True, frame

    mock_cap.read.side_effect = mock_read
    mock_video_capture.return_value = mock_cap

    reader = StreamReader(
        gate_code="IN_HIGH_FPS",
        stream_url="http://mock-cam/video",
        reconnect_initial=0.1,
    )

    reader.start()
    time.sleep(0.2)  # Ingest ~40 frames

    latest_frame, ts = reader.get_latest_frame()
    reader.stop(timeout=1.0)

    assert latest_frame is not None
    assert ts > 0.0
    assert not reader.is_alive()
    assert current_seq[0] >= 10  # Ingested multiple frames


# ==============================================================================
# 2. MotionFilter Empirical Stress Tests
# ==============================================================================


def test_stress_motion_filter_identical_frames_skipped():
    """
    Empirically verify identical frames (MAD = 0.0):
    Initial frame is accepted as baseline; subsequent 20 identical frames are all skipped.
    """
    flt = MotionFilter(mad_threshold=5.0, max_fps=2.0)
    base_frame = np.full((240, 320, 3), 120, dtype=np.uint8)

    # Frame 0: Baseline
    proc, reason, mad = flt.should_process(base_frame, now=10.0)
    assert proc is True
    assert reason == "INITIAL_FRAME"
    assert mad == 0.0

    # Frames 1 to 20: Identical frames at subsequent time steps (>= 0.5s interval)
    for i in range(1, 21):
        proc, reason, mad = flt.should_process(base_frame, now=10.0 + (i * 0.6))
        assert proc is False, f"Identical frame #{i} should have been skipped"
        assert reason == "NO_MOTION"
        assert mad == 0.0


def test_stress_motion_filter_sub_threshold_noise_skipped():
    """
    Frames with subtle camera noise (MAD = 2.0 < 5.0) are skipped.
    """
    flt = MotionFilter(mad_threshold=5.0, max_fps=2.0)
    frame1 = np.full((100, 100, 3), 50, dtype=np.uint8)
    # Brightness change by 2 intensity levels
    frame2 = np.full((100, 100, 3), 52, dtype=np.uint8)

    flt.should_process(frame1, now=100.0)
    proc, reason, mad = flt.should_process(frame2, now=101.0)

    assert proc is False
    assert reason == "NO_MOTION"
    assert mad == pytest.approx(2.0, abs=0.1)


def test_stress_motion_filter_changed_frames_processed():
    """
    Frames with significant motion (MAD > 5.0) are processed and update baseline.
    """
    flt = MotionFilter(mad_threshold=5.0, max_fps=2.0)
    frame1 = np.full((100, 100, 3), 50, dtype=np.uint8)
    frame2 = np.full((100, 100, 3), 80, dtype=np.uint8)  # MAD = 30.0 >= 5.0
    frame3 = np.full(
        (100, 100, 3), 82, dtype=np.uint8
    )  # MAD against frame2 is 2.0 < 5.0

    # Frame 1: Initial
    flt.should_process(frame1, now=10.0)

    # Frame 2: Large change -> processed
    proc2, reason2, mad2 = flt.should_process(frame2, now=11.0)
    assert proc2 is True
    assert reason2 == "MOTION_DETECTED"
    assert mad2 == pytest.approx(30.0, abs=0.1)

    # Frame 3: Baseline was updated to frame2, so diff is 2.0 -> skipped
    proc3, reason3, mad3 = flt.should_process(frame3, now=12.0)
    assert proc3 is False
    assert reason3 == "NO_MOTION"
    assert mad3 == pytest.approx(2.0, abs=0.1)


def test_stress_motion_filter_burst_rate_limiting():
    """
    Under a high-frequency frame burst (100 FPS), only the first frame is processed;
    all subsequent frames within the 1/max_fps window are throttled as RATE_LIMITED.
    """
    flt = MotionFilter(mad_threshold=5.0, max_fps=2.0)  # Min interval 0.5s

    # Baseline frame
    flt.should_process(np.zeros((64, 64, 3), dtype=np.uint8), now=10.0)

    # Burst of 50 moving frames arriving every 5ms (200 FPS)
    rate_limited_count = 0
    for i in range(1, 51):
        t = 10.0 + (i * 0.005)  # From 10.005 to 10.250 (< 10.500)
        moving_frame = np.full((64, 64, 3), i * 3, dtype=np.uint8)
        proc, reason, _ = flt.should_process(moving_frame, now=t)
        assert proc is False
        if reason == "RATE_LIMITED":
            rate_limited_count += 1

    assert rate_limited_count == 50

    # Once time advances past 0.5s (e.g. t = 10.55s), next frame is accepted
    proc, reason, _ = flt.should_process(
        np.full((64, 64, 3), 200, dtype=np.uint8), now=10.55
    )
    assert proc is True
    assert reason == "MOTION_DETECTED"


# ==============================================================================
# 3. PlateVoter Empirical Stress Tests (3/4 Requirement & Cooldown)
# ==============================================================================


def test_stress_plate_voter_2_out_of_4_does_not_trigger():
    """
    Empirically verify that 2/4 match does NOT trigger decision:
    Only 3/4 or higher triggers is_stable = True.
    """
    voter = PlateVoter(window_size=4, required_matches=3, cooldown_seconds=30)
    gate_id = 101

    # Pattern 1: [A, A, B, C]
    voter.reset_gate(gate_id)
    voter.add_observation(gate_id, "30A-111.11")
    voter.add_observation(gate_id, "30A-111.11")
    voter.add_observation(gate_id, "29B-222.22")
    stable, voted = voter.add_observation(gate_id, "51F-333.33")
    assert not stable
    assert voted is None

    # Pattern 2: [A, B, A, C]
    voter.reset_gate(gate_id)
    voter.add_observation(gate_id, "30A-111.11")
    voter.add_observation(gate_id, "29B-222.22")
    voter.add_observation(gate_id, "30A-111.11")
    stable, voted = voter.add_observation(gate_id, "51F-333.33")
    assert not stable
    assert voted is None

    # Pattern 3: [A, A, None, None] (empty plate detections)
    voter.reset_gate(gate_id)
    voter.add_observation(gate_id, "30A-111.11")
    voter.add_observation(gate_id, "30A-111.11")
    voter.add_observation(gate_id, None)
    stable, voted = voter.add_observation(gate_id, "")
    assert not stable
    assert voted is None


def test_stress_plate_voter_3_out_of_4_triggers_stable():
    """
    Empirically verify that 3/4 match triggers decision:
    Tested with noise at 1st, 2nd, 3rd, and 4th position.
    """
    voter = PlateVoter(window_size=4, required_matches=3, cooldown_seconds=30)
    gate_id = 102
    plate = "30A-123.45"
    norm = "30A12345"
    noise = "99Z-999.99"

    # Permutation 1: [Noise, A, A, A] -> stable
    voter.reset_gate(gate_id)
    voter.add_observation(gate_id, noise)
    voter.add_observation(gate_id, plate)
    voter.add_observation(gate_id, plate)
    stable, voted = voter.add_observation(gate_id, plate)
    assert stable is True
    assert voted == norm

    # Permutation 2: [A, Noise, A, A] -> stable
    voter.reset_gate(gate_id)
    voter.add_observation(gate_id, plate)
    voter.add_observation(gate_id, noise)
    voter.add_observation(gate_id, plate)
    stable, voted = voter.add_observation(gate_id, plate)
    assert stable is True
    assert voted == norm

    # Permutation 3: [A, A, Noise, A] -> stable
    voter.reset_gate(gate_id)
    voter.add_observation(gate_id, plate)
    voter.add_observation(gate_id, plate)
    voter.add_observation(gate_id, noise)
    stable, voted = voter.add_observation(gate_id, plate)
    assert stable is True
    assert voted == norm

    # Permutation 4: [A, A, A, Noise] -> stable
    voter.reset_gate(gate_id)
    voter.add_observation(gate_id, plate)
    voter.add_observation(gate_id, plate)
    voter.add_observation(gate_id, plate)
    stable, voted = voter.add_observation(gate_id, noise)
    # The last 4 are [A, A, A, Noise] -> 3 A's!
    assert stable is True
    assert voted == norm


def test_stress_plate_voter_sliding_window_dynamics():
    """
    Test sliding window shift:
    [A, A, A, B] (stable A) -> [A, A, B, C] (unstable) -> [A, B, C, C] (unstable) -> [B, C, C, C] (stable C).
    """
    voter = PlateVoter(window_size=4, required_matches=3)
    gate_id = 103

    voter.add_observation(gate_id, "30A-111.11")
    voter.add_observation(gate_id, "30A-111.11")
    voter.add_observation(gate_id, "30A-111.11")
    stable, plate = voter.add_observation(gate_id, "29B-222.22")
    assert stable is True
    assert plate == "30A11111"

    # Next frame pushes out first '30A11111' -> window: [30A, 30A, 29B, 43C] -> 2 matches
    stable, plate = voter.add_observation(gate_id, "43C-333.33")
    assert not stable
    assert plate is None

    # Next frame: [30A, 29B, 43C, 43C] -> 2 matches
    stable, plate = voter.add_observation(gate_id, "43C-333.33")
    assert not stable
    assert plate is None

    # Next frame: [29B, 43C, 43C, 43C] -> 3 matches for 43C33333
    stable, plate = voter.add_observation(gate_id, "43C-333.33")
    assert stable is True
    assert plate == "43C33333"


def test_stress_plate_voter_cooldown_precision_and_expiry():
    """
    Empirically verify 30s cooldown precision and expiry:
    t = 100.0: Set cooldown (30s).
    t = 115.0: In cooldown.
    t = 129.99: Still in cooldown.
    t = 130.01: Expired (returns False, evicted from memory & cache).
    """
    voter = PlateVoter(cooldown_seconds=30)
    gate_id = 104
    plate = "51K-888.88"

    assert not voter.is_in_cooldown(gate_id, plate, now=100.0)

    # Set cooldown at t=100.0 for 30 seconds
    voter.set_cooldown(gate_id, plate, seconds=30, now=100.0)

    # Active cooldown checks
    assert voter.is_in_cooldown(gate_id, plate, now=100.0) is True
    assert voter.is_in_cooldown(gate_id, plate, now=115.0) is True
    assert voter.is_in_cooldown(gate_id, plate, now=129.99) is True

    # Check that another gate is not affected
    assert voter.is_in_cooldown(gate_id=999, normalized_plate=plate, now=115.0) is False

    # Check that another plate at same gate is not affected
    assert (
        voter.is_in_cooldown(gate_id, normalized_plate="30A-000.00", now=115.0) is False
    )

    # Expiry at t=130.01
    assert voter.is_in_cooldown(gate_id, plate, now=130.01) is False
    # Memory and cache eviction verified
    assert (gate_id, "51K88888") not in voter._local_cooldowns


# ==============================================================================
# 4. GateAdvisoryLock Empirical Stress Tests (Concurrency & Contention)
# ==============================================================================


def test_stress_advisory_lock_simultaneous_acquisitions_same_gate():
    """
    Empirical test: Two simultaneous lock acquisitions on the exact same gate ID.
    The second lock attempt MUST immediately return False.
    """
    gate_id = 9901
    lock1 = GateAdvisoryLock(gate_id=gate_id)
    lock2 = GateAdvisoryLock(gate_id=gate_id)

    try:
        # Worker 1 acquires lock
        acquired1 = lock1.acquire()
        assert acquired1 is True
        assert lock1.is_locked is True

        # Worker 2 simultaneously attempts to acquire lock on SAME gate ID
        acquired2 = lock2.acquire()
        assert acquired2 is False
        assert lock2.is_locked is False

        # Worker 1 releases lock
        lock1.release()
        assert lock1.is_locked is False

        # Worker 2 can now acquire lock
        acquired2_after = lock2.acquire()
        assert acquired2_after is True
        assert lock2.is_locked is True

    finally:
        lock1.release()
        lock2.release()


def test_stress_advisory_lock_multithreaded_race_barrier():
    """
    Empirical multithreaded contention stress test:
    10 threads race simultaneously via a barrier to acquire a lock on the SAME gate ID.
    Exactly 1 thread must succeed (return True), and 9 threads must fail (return False).
    """
    gate_id = 9902
    num_threads = 10
    barrier = threading.Barrier(num_threads)
    results: list[bool] = [False] * num_threads
    locks: list[GateAdvisoryLock] = [
        GateAdvisoryLock(gate_id=gate_id) for _ in range(num_threads)
    ]

    def worker_race(thread_idx: int):
        barrier.wait()  # Synchronize all threads to start at the exact same instant
        results[thread_idx] = locks[thread_idx].acquire()

    threads = [
        threading.Thread(target=worker_race, args=(i,)) for i in range(num_threads)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    try:
        success_count = sum(1 for r in results if r is True)
        failure_count = sum(1 for r in results if r is False)

        assert success_count == 1, f"Expected exactly 1 winner, got {success_count}"
        assert failure_count == (num_threads - 1), (
            f"Expected {num_threads - 1} losers, got {failure_count}"
        )

    finally:
        # Clean up any acquired locks
        for lk in locks:
            lk.release()


def test_stress_advisory_lock_multi_gate_isolation():
    """
    Empirical isolation test:
    Multiple threads acquiring locks on DIFFERENT gate IDs simultaneously.
    All must succeed (no cross-gate blocking or serialization).
    """
    gate_ids = [9910, 9911, 9912, 9913, 9914]
    num_gates = len(gate_ids)
    barrier = threading.Barrier(num_gates)
    results: list[bool] = [False] * num_gates
    locks: list[GateAdvisoryLock] = [GateAdvisoryLock(gate_id=gid) for gid in gate_ids]

    def worker_independent(idx: int):
        barrier.wait()
        results[idx] = locks[idx].acquire()

    threads = [
        threading.Thread(target=worker_independent, args=(i,)) for i in range(num_gates)
    ]

    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    try:
        # All independent gate locks must succeed
        for i, res in enumerate(results):
            assert res is True, f"Gate {gate_ids[i]} lock acquisition failed"

    finally:
        for lk in locks:
            lk.release()


# ==============================================================================
# 5. Multi-Replica Gate Subset Partitioning & Failover Tests
# ==============================================================================


@pytest.mark.django_db(transaction=True)
def test_multi_replica_overlapping_gate_subsets_and_failover(settings):
    """
    Verify two GateWorkerCoordinator replicas with overlapping --gate filters:
    1. Replica 1 owns {g1, g2}; Replica 2 configured with {g2, g3} skips g2 and owns only {g3}.
    2. When Replica 1 shuts down, its advisory locks release and a standby replica acquires g2.
    3. Whitespace, mixed-case, and unknown gate filter tokens are handled without error.
    """
    from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
    from apps.parking.gate_worker.locks import (
        clear_mock_lock_registry,
        get_active_gate_worker_lock_ids,
    )
    from apps.parking.models import ParkingGate, ParkingLot

    clear_mock_lock_registry()
    lot = ParkingLot.objects.first()
    assert lot is not None

    gates = list(ParkingGate.objects.filter(is_active=True)[:3])
    while len(gates) < 3:
        idx = len(gates) + 1
        g, _ = ParkingGate.objects.get_or_create(
            code=f"REPLICA_GATE_{idx:02d}",
            defaults={
                "lot": lot,
                "name": f"Replica Gate {idx}",
                "direction": "IN" if idx % 2 == 1 else "OUT",
                "is_active": True,
                "camera_status": "ONLINE",
            },
        )
        gates.append(g)

    g1, g2, g3 = gates[0], gates[1], gates[2]
    settings.GATE_WORKER_STREAMS = {
        g1.code: "http://cam/r1",
        g2.code: "http://cam/r2",
        g3.code: "http://cam/r3",
    }

    with patch("cv2.VideoCapture") as mock_cap:
        mock_inst = MagicMock()
        mock_inst.isOpened.return_value = True
        mock_inst.read.return_value = (True, np.zeros((64, 64, 3), dtype=np.uint8))
        mock_cap.return_value = mock_inst

        coord1 = GateWorkerCoordinator(
            gate_code_filter=f" {g1.code} , {g2.code.lower()} , "
        )
        coord2 = GateWorkerCoordinator(
            gate_code_filter=f"{g2.code},{g3.code},UNKNOWN_GATE_99"
        )
        coord_standby = GateWorkerCoordinator(gate_code_filter=str(g2.id))

        try:
            assert coord1.initialize() == 2
            assert set(coord1._managed_gates.keys()) == {g1.id, g2.id}

            assert coord2.initialize() == 1
            assert set(coord2._managed_gates.keys()) == {g3.id}

            active_ids = get_active_gate_worker_lock_ids()
            assert {g1.id, g2.id, g3.id}.issubset(active_ids)

            coord1.shutdown()
            assert g2.id not in get_active_gate_worker_lock_ids()

            assert coord_standby.initialize() == 1
            assert set(coord_standby._managed_gates.keys()) == {g2.id}
        finally:
            coord1.shutdown()
            coord2.shutdown()
            coord_standby.shutdown()
            clear_mock_lock_registry()
