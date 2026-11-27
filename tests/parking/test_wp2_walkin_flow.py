"""
Round 93 WP2 (K2 / D2): Walk-In Registration, Plate Normalization & Pending Gate Event Transitions.

Failing-first tests covering:
(a) POST /api/v1/me/vehicles/ normalizes customer plate variants
    (" 51a - 897.14 ", "51a\\t89714", "  51k  992.15  ") to match license_plate_norm,
    while keeping staff validate_raw_license_plate strict.
(b) Duplicate plate owned by another customer (even with varied formatting/whitespace)
    is rejected with HTTP 409 MSG-4.3.1-M05 ("Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.").
(c) GateWorkerCoordinator emits ActivityLog(action="GATE_AUTO_NEEDS_STAFF", reason="PENDING_ENTRY_EXPIRED",
    license_plate_masked=mask_plate(...)) ONLY on actual eviction (>60s unseen or >900s total) when
    no other alive pending entry remains on that gate_id (0 queries/logs in (20s, 60s]).
(d) GET /api/v1/parking/gates/ last_auto_event transitions:
    UNREGISTERED_VEHICLE -> PENDING_ENTRY_EXPIRED (on eviction) and
    UNREGISTERED_VEHICLE -> GATE_AUTO_CHECK_IN (on registration while still seen).
"""

from __future__ import annotations

import threading
import uuid
from unittest.mock import MagicMock

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.audit.models import ActivityLog
from apps.core.logging import mask_plate
from apps.customers.models import Customer
from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
from apps.parking.gate_worker.locks import clear_mock_lock_registry
from apps.parking.models import (
    ParkingGate,
    ParkingLot,
    ParkingSlot,
    VehicleEntryExitLog,
)
from apps.parking.services.ocr import PlateCandidate, PlateRecognizer, PlateScanResult
from apps.vehicles.models import Vehicle, VehicleType
from apps.wallet.services.wallet import ensure_wallet_for_customer

pytestmark = pytest.mark.django_db


class FakeClock:
    """Thread-safe deterministic monotonic clock without time.sleep()."""

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
def clean_wp2_state():
    cache.clear()
    clear_mock_lock_registry()
    yield
    cache.clear()
    clear_mock_lock_registry()


def _create_customer_client(prefix: str) -> tuple[Account, Customer, APIClient]:
    suffix = uuid.uuid4().hex[:6]
    acc = Account.objects.create_user(
        email=f"{prefix}_{suffix}@example.com",
        password="TestPassword123!",
        role="CUSTOMER",
    )
    cust = Customer.objects.create(
        code=f"KHW{suffix[:4].upper()}",
        full_name=f"Khách Walk-In {suffix}",
        identity_card_number=f"079{uuid.uuid4().int % 10**9:09d}",
        phone=f"09{uuid.uuid4().int % 10**8:08d}",
        email=acc.email,
        account=acc,
        status="ACTIVE",
    )
    ensure_wallet_for_customer(cust.id)
    client = APIClient()
    client.force_authenticate(user=acc)
    return acc, cust, client


def _create_staff_client() -> tuple[Account, APIClient]:
    suffix = uuid.uuid4().hex[:6]
    acc = Account.objects.create_user(
        email=f"staff_wp2_{suffix}@example.com",
        password="TestPassword123!",
        role="EMPLOYEE",
    )
    client = APIClient()
    client.force_authenticate(user=acc)
    return acc, client


def _make_scan_result(plate_text: str, confidence: float = 96.5) -> PlateScanResult:
    norm = PlateRecognizer.normalize_plate(plate_text) or plate_text
    cand = PlateCandidate(
        plate_text=plate_text,
        plate_normalized=norm,
        confidence=confidence,
    )
    return PlateScanResult(
        candidates=[cand],
        best_candidate=cand,
        engine_name="fast_alpr",
        raw_text=plate_text,
        latency_ms=10.0,
        review_status="AUTO",
    )


def _ensure_available_slot(lot_id: int) -> ParkingSlot:
    slot = ParkingSlot.objects.filter(
        zone__floor__lot_id=lot_id,
        status="AVAILABLE",
        deleted_at__isnull=True,
    ).first()
    if slot is not None:
        return slot
    slot = ParkingSlot.objects.filter(
        zone__floor__lot_id=lot_id,
        deleted_at__isnull=True,
    ).first()
    assert slot is not None
    slot.status = "AVAILABLE"
    slot.save(update_fields=["status"])
    return slot


def test_me_vehicle_create_normalizes_plate_variants_to_license_plate_norm():
    """
    (a) POST /api/v1/me/vehicles/ accepts whitespace/tab/separator variants
    (" 51a - 897.14 ", "51a\\t89714", "  51k  992.15  ") and stores normalized
    license_plate_norm matching DB fn_normalize_license_plate.
    """
    _, cust, client = _create_customer_client("wp2_norm")
    vtype = VehicleType.objects.filter(code="CAR", deleted_at__isnull=True).first()
    assert vtype is not None

    # Soft-delete seeded 51A89714 / 51K99215 if present in test DB
    for norm in ("51A89714", "51K99215"):
        Vehicle.all_objects.filter(license_plate_norm=norm).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )

    resp1 = client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": " 51a - 897.14 ",
            "model_name": "Toyota Vios",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert resp1.status_code == status.HTTP_201_CREATED, resp1.json()
    veh1 = Vehicle.objects.get(id=resp1.json()["id"], customer_id=cust.id)
    assert veh1.license_plate_norm == "51A89714"

    # Soft-delete veh1 so we can verify tab variant on same normalized plate
    veh1.deleted_at = timezone.now()
    veh1.save(update_fields=["deleted_at"])

    resp2 = client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": "51a\t89714",
            "model_name": "Toyota Vios",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert resp2.status_code == status.HTTP_201_CREATED, resp2.json()
    veh2 = Vehicle.objects.get(id=resp2.json()["id"], customer_id=cust.id)
    assert veh2.license_plate_norm == "51A89714"

    resp3 = client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": "  51k  992.15  ",
            "model_name": "VinFast VF8",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert resp3.status_code == status.HTTP_201_CREATED, resp3.json()
    veh3 = Vehicle.objects.get(id=resp3.json()["id"], customer_id=cust.id)
    assert veh3.license_plate_norm == "51K99215"


def test_me_vehicle_create_rejects_duplicate_plate_owned_by_another_customer_409():
    """
    (b) Duplicate plate owned by another customer (even submitted with extra
    whitespace/separators like " 51k - 992.14 ") returns HTTP 409 MSG-4.3.1-M05.
    """
    _, _, client_a = _create_customer_client("wp2_owner_a")
    _, _, client_b = _create_customer_client("wp2_owner_b")
    vtype = VehicleType.objects.filter(code="CAR", deleted_at__isnull=True).first()
    assert vtype is not None

    Vehicle.all_objects.filter(license_plate_norm="51K99214").update(
        deleted_at=timezone.now(), deleted_by_id=None
    )

    create_a = client_a.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": "51K-992.14",
            "model_name": "Mazda 3",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert create_a.status_code == status.HTTP_201_CREATED, create_a.json()

    expected_msg = "Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp."

    dup_resp_variant = client_b.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": " 51k - 992.14 ",
            "model_name": "Mazda 3",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert dup_resp_variant.status_code == status.HTTP_409_CONFLICT
    assert dup_resp_variant.json()["code"] == "MSG-4.3.1-M05"
    assert dup_resp_variant.json()["message"] == expected_msg

    dup_resp_compact = client_b.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": "51k99214",
            "model_name": "Mazda 3",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert dup_resp_compact.status_code == status.HTTP_409_CONFLICT
    assert dup_resp_compact.json()["code"] == "MSG-4.3.1-M05"
    assert dup_resp_compact.json()["message"] == expected_msg


def test_coordinator_emits_pending_entry_expired_on_eviction_and_zero_logs_in_silent_window(
    django_assert_num_queries,
):
    """
    (c) coordinator.py emits GATE_AUTO_NEEDS_STAFF reason="PENDING_ENTRY_EXPIRED"
    with masked plate ONLY when evicting >60s unseen or >900s total and no other
    alive pending entry remains on that gate_id (0 queries/logs in (20s, 60s]).
    """
    in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert in_gate is not None
    in_gate.is_auto_scan = True
    in_gate.save(update_fields=["is_auto_scan"])

    plate_a = "30A-612.35"
    norm_a = "30A61235"
    plate_b = "30A-612.99"
    norm_b = "30A61299"
    for norm in (norm_a, norm_b):
        Vehicle.all_objects.filter(license_plate_norm=norm).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )

    clock = FakeClock(1000.0)
    coordinator = GateWorkerCoordinator(
        streams_override={in_gate.code: f"http://mock/{in_gate.code}"},
        snapshot_uploader=MagicMock(),
        clock=clock,
    )
    coordinator._managed_gates[in_gate.id] = in_gate

    # t=1000: plate_a unregistered -> pending created + 1 UNREGISTERED_VEHICLE log
    coordinator._evaluate_and_execute(
        in_gate, plate_a, _make_scan_result(plate_a, 96.5)
    )
    assert (in_gate.id, norm_a) in coordinator._pending_entries

    logs_after_initial = ActivityLog.objects.filter(
        entity_type="parking_gate", entity_id=in_gate.id
    ).count()

    # t=1040 (40s in silent wait window (20s, 60s]) -> 0 queries, 0 logs
    clock.advance(40.0)
    with django_assert_num_queries(0):
        coordinator._recheck_pending_entries(in_gate)
    assert (in_gate.id, norm_a) in coordinator._pending_entries
    assert (
        ActivityLog.objects.filter(
            entity_type="parking_gate", entity_id=in_gate.id
        ).count()
        == logs_after_initial
    )

    # t=1061 (>60s unseen) -> evicted, emits exactly 1 PENDING_ENTRY_EXPIRED with masked plate
    clock.advance(21.0)
    coordinator._recheck_pending_entries(in_gate)
    assert (in_gate.id, norm_a) not in coordinator._pending_entries

    latest_log = (
        ActivityLog.objects.filter(entity_type="parking_gate", entity_id=in_gate.id)
        .order_by("-occurred_at", "-id")
        .first()
    )
    assert latest_log is not None
    assert latest_log.action == "GATE_AUTO_NEEDS_STAFF"
    assert '"PENDING_ENTRY_EXPIRED"' in latest_log.message
    assert mask_plate(plate_a) in latest_log.message
    assert plate_a not in latest_log.message
    assert norm_a not in latest_log.message

    # Also check: when another alive pending entry remains on same gate_id, evicting the first
    # must NOT emit PENDING_ENTRY_EXPIRED prematurely.
    clock.advance(100.0)
    coordinator._evaluate_and_execute(
        in_gate, plate_a, _make_scan_result(plate_a, 96.5)
    )
    clock.advance(30.0)
    coordinator._evaluate_and_execute(
        in_gate, plate_b, _make_scan_result(plate_b, 96.5)
    )
    count_before_partial_evict = ActivityLog.objects.filter(
        entity_type="parking_gate", entity_id=in_gate.id
    ).count()

    # At +31s from plate_b (total +61s from plate_a): plate_a evicts, plate_b still alive
    clock.advance(31.0)
    coordinator._recheck_pending_entries(in_gate)
    assert (in_gate.id, norm_a) not in coordinator._pending_entries
    assert (in_gate.id, norm_b) in coordinator._pending_entries
    assert (
        ActivityLog.objects.filter(
            entity_type="parking_gate", entity_id=in_gate.id
        ).count()
        == count_before_partial_evict
    )

    # Now evict plate_b via >900s total age limit -> emits PENDING_ENTRY_EXPIRED
    for _ in range(59):
        clock.advance(15.0)
        coordinator._touch_pending_plate(in_gate.id, plate_b, now_mono=clock())
    clock.advance(16.0)  # > 900s from plate_b first_seen_at
    coordinator._recheck_pending_entries(in_gate)
    assert (in_gate.id, norm_b) not in coordinator._pending_entries
    final_log = (
        ActivityLog.objects.filter(entity_type="parking_gate", entity_id=in_gate.id)
        .order_by("-occurred_at", "-id")
        .first()
    )
    assert final_log is not None
    assert final_log.action == "GATE_AUTO_NEEDS_STAFF"
    assert '"PENDING_ENTRY_EXPIRED"' in final_log.message
    assert mask_plate(plate_b) in final_log.message


def test_gate_status_api_last_auto_event_transitions_unregistered_to_expired_and_checkin():
    """
    (d) GET /api/v1/parking/gates/ last_auto_event transitions:
    1. UNREGISTERED_VEHICLE -> PENDING_ENTRY_EXPIRED (when evicted >60s unseen)
    2. UNREGISTERED_VEHICLE -> GATE_AUTO_CHECK_IN (when customer registers while still seen)
    """
    in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert in_gate is not None
    in_gate.is_auto_scan = True
    in_gate.save(update_fields=["is_auto_scan"])
    if in_gate.lot_id:
        _ensure_available_slot(in_gate.lot_id)
    else:
        lot = ParkingLot.objects.filter(deleted_at__isnull=True).first()
        assert lot is not None
        in_gate.lot = lot
        in_gate.save(update_fields=["lot"])
        _ensure_available_slot(lot.id)

    _, staff_client = _create_staff_client()
    _, _, cust_client = _create_customer_client("wp2_trans")
    vtype = VehicleType.objects.filter(code="CAR", deleted_at__isnull=True).first()
    assert vtype is not None

    plate = "30A-612.35"
    norm = "30A61235"
    Vehicle.all_objects.filter(license_plate_norm=norm).update(
        deleted_at=timezone.now(), deleted_by_id=None
    )

    clock = FakeClock(2000.0)
    coordinator = GateWorkerCoordinator(
        streams_override={in_gate.code: f"http://mock/{in_gate.code}"},
        snapshot_uploader=MagicMock(),
        clock=clock,
    )
    coordinator._pending_recheck_seconds = 5.0
    coordinator._managed_gates[in_gate.id] = in_gate

    def _get_gate_event() -> dict | None:
        resp = staff_client.get("/api/v1/parking/gates/?direction=IN")
        assert resp.status_code == status.HTTP_200_OK
        row = next((g for g in resp.json() if g["id"] == in_gate.id), None)
        assert row is not None
        return row["last_auto_event"]

    # 1. Unregistered vehicle arrives -> UNREGISTERED_VEHICLE
    coordinator._evaluate_and_execute(in_gate, plate, _make_scan_result(plate, 96.5))
    ev1 = _get_gate_event()
    assert ev1 is not None
    assert ev1["action"] == "GATE_AUTO_NEEDS_STAFF"
    assert ev1["reason"] == "UNREGISTERED_VEHICLE"
    assert "*" in ev1["license_plate_masked"]

    # 2. Vehicle leaves >60s -> PENDING_ENTRY_EXPIRED
    clock.advance(61.0)
    coordinator._recheck_pending_entries(in_gate)
    ev2 = _get_gate_event()
    assert ev2 is not None
    assert ev2["action"] == "GATE_AUTO_NEEDS_STAFF"
    assert ev2["reason"] == "PENDING_ENTRY_EXPIRED"
    assert "*" in ev2["license_plate_masked"]

    # 3. Vehicle arrives again -> UNREGISTERED_VEHICLE, customer registers while still seen -> GATE_AUTO_CHECK_IN
    clock.advance(5.0)
    coordinator._evaluate_and_execute(in_gate, plate, _make_scan_result(plate, 96.5))
    ev3 = _get_gate_event()
    assert ev3 is not None
    assert ev3["reason"] == "UNREGISTERED_VEHICLE"

    reg_resp = cust_client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": " 30a - 612.35 ",
            "model_name": "Sedan",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert reg_resp.status_code == status.HTTP_201_CREATED

    clock.advance(6.0)
    coordinator._touch_pending_plate(in_gate.id, plate, now_mono=clock())
    coordinator._recheck_pending_entries(in_gate)

    ev4 = _get_gate_event()
    assert ev4 is not None
    assert ev4["action"] == "GATE_AUTO_CHECK_IN"
    assert ev4["reason"] == "VALID_REGISTERED"
    assert "*" in ev4["license_plate_masked"]
    assert VehicleEntryExitLog.objects.filter(
        license_plate_norm=norm, exit_time__isnull=True
    ).exists()


def test_coordinator_d1_4_freshness_expiration_race_emits_pending_entry_expired(
    monkeypatch,
):
    """
    (e) D1(4) race at coordinator.py:1501-1503:
    If a pending entry expires between candidate selection and the pre-check_in freshness
    guard, popping it must emit PENDING_ENTRY_EXPIRED (masked plate) when no other alive
    pending entry remains on that gate.id, and suppress it when another alive entry remains.
    """
    in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    assert in_gate is not None
    in_gate.is_auto_scan = True
    in_gate.save(update_fields=["is_auto_scan"])
    if in_gate.lot_id:
        _ensure_available_slot(in_gate.lot_id)
    else:
        lot = ParkingLot.objects.filter(deleted_at__isnull=True).first()
        assert lot is not None
        in_gate.lot = lot
        in_gate.save(update_fields=["lot"])
        _ensure_available_slot(lot.id)

    _, _, cust_client = _create_customer_client("wp2_d1_4_race")
    vtype = VehicleType.objects.filter(code="CAR", deleted_at__isnull=True).first()
    assert vtype is not None

    plate_a = "30A-612.35"
    norm_a = "30A61235"
    plate_b = "30A-612.99"
    norm_b = "30A61299"
    for norm in (norm_a, norm_b):
        Vehicle.all_objects.filter(license_plate_norm=norm).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )

    clock = FakeClock(4000.0)
    coordinator = GateWorkerCoordinator(
        streams_override={in_gate.code: f"http://mock/{in_gate.code}"},
        snapshot_uploader=MagicMock(),
        clock=clock,
    )
    coordinator._pending_recheck_seconds = 5.0
    coordinator._managed_gates[in_gate.id] = in_gate

    # 1. Single pending entry approaches total 900s limit (still alive at t=4899.5)
    coordinator._evaluate_and_execute(
        in_gate, plate_a, _make_scan_result(plate_a, 96.5)
    )
    assert (in_gate.id, norm_a) in coordinator._pending_entries

    for _ in range(59):
        clock.advance(15.0)
        coordinator._touch_pending_plate(in_gate.id, plate_a, now_mono=clock())
    # t = 4000 + 885 = 4885; advance +14.5s -> t = 4899.5 (< 4900 expires_at, < 20s seen)
    clock.advance(14.5)

    reg_resp = cust_client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": plate_a,
            "model_name": "Sedan",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert reg_resp.status_code == status.HTTP_201_CREATED

    logs_before = ActivityLog.objects.filter(
        entity_type="parking_gate", entity_id=in_gate.id
    ).count()

    orig_resolve_slot = coordinator._resolve_entry_slot

    def _advance_past_expiry_during_lookup(gate, context):
        clock.advance(1.0)  # t = 4900.5 (> 4900.0 total limit) right before D1(4) guard
        return orig_resolve_slot(gate, context)

    monkeypatch.setattr(
        coordinator, "_resolve_entry_slot", _advance_past_expiry_during_lookup
    )
    coordinator._recheck_pending_entries(in_gate)

    assert (in_gate.id, norm_a) not in coordinator._pending_entries
    assert not VehicleEntryExitLog.objects.filter(
        license_plate_norm=norm_a, exit_time__isnull=True
    ).exists()

    logs_after = ActivityLog.objects.filter(
        entity_type="parking_gate", entity_id=in_gate.id
    ).count()
    assert logs_after == logs_before + 1
    latest_log = (
        ActivityLog.objects.filter(entity_type="parking_gate", entity_id=in_gate.id)
        .order_by("-occurred_at", "-id")
        .first()
    )
    assert latest_log is not None
    assert latest_log.action == "GATE_AUTO_NEEDS_STAFF"
    assert '"PENDING_ENTRY_EXPIRED"' in latest_log.message
    assert mask_plate(plate_a) in latest_log.message
    assert plate_a not in latest_log.message

    # 2. Multi-entry suppression: if plate_b is still alive on in_gate.id when plate_a
    # hits the D1(4) race, PENDING_ENTRY_EXPIRED must NOT fire prematurely.
    Vehicle.all_objects.filter(license_plate_norm=norm_a).update(
        deleted_at=timezone.now(), deleted_by_id=None
    )
    clock2 = FakeClock(6000.0)
    coord2 = GateWorkerCoordinator(
        streams_override={in_gate.code: f"http://mock/{in_gate.code}"},
        snapshot_uploader=MagicMock(),
        clock=clock2,
    )
    coord2._pending_recheck_seconds = 5.0
    coord2._managed_gates[in_gate.id] = in_gate

    coord2._evaluate_and_execute(in_gate, plate_a, _make_scan_result(plate_a, 96.5))
    for _ in range(58):
        clock2.advance(15.0)
        coord2._touch_pending_plate(in_gate.id, plate_a, now_mono=clock2())
    # t = 6870; add plate_b at 6885 (fresh!) and keep plate_a touched until 6899.5
    clock2.advance(15.0)  # t = 6885
    coord2._touch_pending_plate(in_gate.id, plate_a, now_mono=clock2())
    coord2._evaluate_and_execute(in_gate, plate_b, _make_scan_result(plate_b, 96.5))
    clock2.advance(14.5)  # t = 6899.5

    reg_resp2 = cust_client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": plate_a,
            "model_name": "Sedan",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert reg_resp2.status_code == status.HTTP_201_CREATED

    logs_before_multi = ActivityLog.objects.filter(
        entity_type="parking_gate", entity_id=in_gate.id
    ).count()
    orig_resolve_slot2 = coord2._resolve_entry_slot

    def _advance_past_expiry_multi(gate, context):
        clock2.advance(1.0)  # t = 6900.5 -> plate_a expired, plate_b alive
        return orig_resolve_slot2(gate, context)

    monkeypatch.setattr(coord2, "_resolve_entry_slot", _advance_past_expiry_multi)
    coord2._recheck_pending_entries(in_gate)

    assert (in_gate.id, norm_a) not in coord2._pending_entries
    assert (in_gate.id, norm_b) in coord2._pending_entries
    assert (
        ActivityLog.objects.filter(
            entity_type="parking_gate", entity_id=in_gate.id
        ).count()
        == logs_before_multi
    )
