"""
Gate worker coordinator module for autonomous barrier control.
Adheres to ADR-0011 Section 2 (TL-66 to TL-77).
Coordinates multi-camera streams, semaphore OCR dispatching, pure decision evaluation,
atomic check-in / fee-0 check-out execution, audit logging, telemetry, and graceful shutdown.
"""

from __future__ import annotations

import contextlib
import json
import logging
import signal
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import Any

import cv2
import numpy as np
from django.conf import settings
from django.db import close_old_connections
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone
from PIL import Image

from apps.audit.models import ActivityLog
from apps.content.models import Notification
from apps.core.exceptions import BusinessAPIException
from apps.core.logging import mask_plate
from apps.parking.gate_worker.filter import MotionFilter
from apps.parking.gate_worker.locks import GateAdvisoryLock
from apps.parking.gate_worker.reader import (
    STATUS_DEGRADED,
    STATUS_OFFLINE,
    STATUS_STREAMING,
    StreamReader,
)
from apps.parking.gate_worker.snapshot import SnapshotUploader
from apps.parking.gate_worker.voter import PlateVoter
from apps.parking.models import (
    ParkingGate,
    ParkingSlot,
    SlotReservation,
    VehicleEntryExitLog,
)
from apps.parking.selectors.vehicles import get_combined_vehicle_context
from apps.parking.services.gate_decision import (
    ACTION_AUTO_CHECK_IN,
    ACTION_AUTO_CHECK_OUT,
    ACTION_HOLD,
    AUDIT_GATE_AUTO_CHECK_OUT,
    AUDIT_GATE_AUTO_NEEDS_STAFF,
    REASON_EXECUTION_FAILED,
    REASON_UNREGISTERED_VEHICLE,
    REASON_VALID_FEE_ZERO,
    REASON_VALID_WALLET_PAID,
    REASON_WALLET_INSUFFICIENT,
    DecisionResult,
    decide_gate_action,
)
from apps.parking.services.ocr import PlateRecognizer, get_plate_recognizer
from apps.parking.services.tariff import calculate_parking_fee
from apps.vehicles.models import Vehicle
from apps.wallet.models import Wallet
from apps.wallet.services.wallet import InsufficientWalletBalanceError

logger = logging.getLogger(__name__)

DEFAULT_MAX_PENDING_PER_GATE: int = 50


def format_failure_text(exc: Exception, operation: str) -> str:
    """
    Format a concise, PII-free failure summary for logs and ActivityLog messages.
    Never includes str(exc) to prevent unmasked license plate leaks.
    """
    return f"{exc.__class__.__name__}: {operation} failed"


class GateWorkerCoordinator:
    """
    Long-running background coordinator managing camera streams, motion pre-filtering,
    concurrency-bounded OCR, temporal voting, and autonomous gate operations.
    """

    def __init__(
        self,
        streams_override: dict[str, str] | None = None,
        gate_code_filter: str | list[str] | set[str] | None = None,
        concurrency_limit: int | None = None,
        snapshot_uploader: SnapshotUploader | None = None,
        clock: Callable[[], float] | None = None,
        pending_max_per_gate: int | None = None,
    ) -> None:
        self.gate_code_filter = gate_code_filter
        self._clock: Callable[[], float] = (
            clock if clock is not None else time.monotonic
        )
        self._streams_map = self._load_streams_config(streams_override)
        if self.gate_code_filter:
            self._streams_map = self._filter_streams(
                self._streams_map, self.gate_code_filter
            )

        self._snapshot_uploader = (
            snapshot_uploader if snapshot_uploader is not None else SnapshotUploader()
        )

        limit = (
            int(concurrency_limit)
            if concurrency_limit is not None
            else getattr(settings, "GATE_WORKER_CONCURRENCY_LIMIT", 4)
        )
        self._concurrency_limit = max(1, limit)
        self._ocr_semaphore = threading.Semaphore(self._concurrency_limit)
        self._tick_lock = threading.Lock()
        self._active_gate_ticks: set[int] = set()

        # Per-gate state containers
        self._locks: dict[int, GateAdvisoryLock] = {}
        self._readers: dict[int, StreamReader] = {}
        self._filters: dict[int, MotionFilter] = {}
        self._managed_gates: dict[int, ParkingGate] = {}
        self._last_evaluated_timestamps: dict[int, float] = {}
        self._gate_cooldown_pause_until: dict[int, float] = {}

        # Frame and OCR telemetry counters
        self._stats_lock = threading.Lock()
        self._ocr_processed_count: int = 0
        self._filtered_or_skipped_count: int = 0
        self._last_stats_log_ts: float = 0.0

        self._voter = PlateVoter(
            window_size=4,
            required_matches=3,
            cooldown_seconds=getattr(settings, "GATE_WORKER_COOLDOWN_SECONDS", 30),
            clock=self._clock,
        )

        self._stop_event = threading.Event()
        self._is_running = False

        # Dynamic gate configuration refresh interval (TL Decision 4, F5)
        self._config_refresh_interval = float(
            getattr(settings, "GATE_WORKER_CONFIG_REFRESH_INTERVAL", 10.0)
        )
        self._last_config_refresh_ts: float = 0.0

        # Pending entry & exit re-evaluation state (WP5 D7, WP4 D8, Round 93 D1)
        self._pending_lock = threading.RLock()
        self._pending_entries: dict[tuple[int, str], dict[str, Any]] = {}
        self._pending_exits: dict[tuple[int, str], dict[str, Any]] = {}
        self._pending_minutes: int = int(
            getattr(settings, "GATE_WORKER_PENDING_MINUTES", 15)
        )
        self._pending_recheck_seconds: float = float(
            getattr(settings, "GATE_WORKER_PENDING_RECHECK_SECONDS", 5.0)
        )
        self._pending_seen_seconds: float = float(
            getattr(settings, "GATE_WORKER_PENDING_SEEN_SECONDS", 20)
        )
        self._pending_max_per_gate: int = (
            max(1, int(pending_max_per_gate))
            if pending_max_per_gate is not None
            else DEFAULT_MAX_PENDING_PER_GATE
        )
        self._last_pending_ocr_probe_ts: dict[int, float] = {}

    def _now_monotonic(self) -> float:
        """Read current monotonic clock, supporting __new__() instances in legacy unit tests."""
        clock = getattr(self, "_clock", None)
        return float(clock()) if clock is not None else time.monotonic()

    def _pending_guard(self) -> threading.RLock:
        """Return the pending state RLock, initializing lazily for __new__() test instances."""
        lock = getattr(self, "_pending_lock", None)
        if lock is None:
            lock = threading.RLock()
            self._pending_lock = lock
        return lock

    def _get_pending_seen_seconds(self) -> float:
        return max(
            0.0,
            float(
                getattr(
                    self,
                    "_pending_seen_seconds",
                    getattr(settings, "GATE_WORKER_PENDING_SEEN_SECONDS", 20),
                )
            ),
        )

    def _get_pending_minutes(self) -> int:
        return max(
            1,
            int(
                getattr(
                    self,
                    "_pending_minutes",
                    getattr(settings, "GATE_WORKER_PENDING_MINUTES", 15),
                )
            ),
        )

    def _get_pending_max_per_gate(self) -> int:
        return max(
            1,
            int(getattr(self, "_pending_max_per_gate", DEFAULT_MAX_PENDING_PER_GATE)),
        )

    def _is_pending_expired(self, entry: dict[str, Any], now_mono: float) -> bool:
        """
        Check whether a pending item exceeded total age (> GATE_WORKER_PENDING_MINUTES)
        or unseen timeout (> GATE_WORKER_PENDING_SEEN_SECONDS * 3).
        Falls back to expires_at only for legacy manual test dicts lacking first_seen_at/last_seen_at.
        """
        first_seen_at = entry.get("first_seen_at")
        last_seen_at = entry.get("last_seen_at")
        if first_seen_at is None or last_seen_at is None:
            if "expires_at" in entry and now_mono >= float(entry["expires_at"]):
                return True
            if first_seen_at is not None and (now_mono - float(first_seen_at)) > (
                self._get_pending_minutes() * 60.0
            ):
                return True
            return bool(
                last_seen_at is not None
                and (now_mono - float(last_seen_at))
                > (self._get_pending_seen_seconds() * 3.0)
            )

        total_limit = self._get_pending_minutes() * 60.0
        unseen_limit = self._get_pending_seen_seconds() * 3.0
        return (now_mono - float(first_seen_at)) > total_limit or (
            now_mono - float(last_seen_at)
        ) > unseen_limit

    def _is_pending_still_seen(self, entry: dict[str, Any], now_mono: float) -> bool:
        """Return True iff plate was seen within GATE_WORKER_PENDING_SEEN_SECONDS."""
        last_seen_at = entry.get("last_seen_at")
        if last_seen_at is None:
            return True
        return (now_mono - float(last_seen_at)) <= self._get_pending_seen_seconds()

    def _has_alive_pending_for_gate(self, gate_id: int, now_mono: float) -> bool:
        """Return True if this gate currently has at least one non-expired pending entry or exit."""
        with self._pending_guard():
            for pending_dict in (
                getattr(self, "_pending_entries", None),
                getattr(self, "_pending_exits", None),
            ):
                if not pending_dict:
                    continue
                for key, entry in pending_dict.items():
                    if key[0] == gate_id and not self._is_pending_expired(
                        entry, now_mono
                    ):
                        return True
        return False

    def _evict_oldest_if_needed(
        self,
        pending_dict: dict[tuple[int, str], dict[str, Any]],
        gate_id: int,
        incoming_key: tuple[int, str],
        now_mono: float,
    ) -> None:
        """
        Enforce bounded per-gate memory before inserting incoming_key.
        Must be called while holding self._pending_guard().
        """
        if incoming_key in pending_dict:
            return

        # Prune already-expired entries for this gate first
        for k in [
            k
            for k, v in pending_dict.items()
            if k[0] == gate_id and self._is_pending_expired(v, now_mono)
        ]:
            pending_dict.pop(k, None)

        max_per_gate = self._get_pending_max_per_gate()
        gate_items = [(k, v) for k, v in pending_dict.items() if k[0] == gate_id]
        while len(gate_items) >= max_per_gate:
            oldest_key, _ = min(
                gate_items,
                key=lambda kv: (
                    float(kv[1].get("last_seen_at", kv[1].get("last_recheck_ts", 0.0))),
                    float(kv[1].get("first_seen_at", 0.0)),
                    kv[0][1],
                ),
            )
            pending_dict.pop(oldest_key, None)
            gate_items = [(k, v) for k, v in pending_dict.items() if k[0] == gate_id]

    def _touch_pending_plate(
        self,
        gate_id: int,
        plate: str | None,
        *,
        now_mono: float | None = None,
        decisive_frame: np.ndarray | None = None,
    ) -> None:
        """
        Refresh last_seen_at for an active pending entry/exit when this plate is sighted
        at gate_id (including readings ignored by voter cooldown or partial votes).
        Never resurrects expired items.
        """
        if not plate:
            return
        norm_plate = PlateRecognizer.normalize_plate(plate)
        if not norm_plate:
            return
        ts = self._now_monotonic() if now_mono is None else float(now_mono)
        effective_now = max(ts, self._now_monotonic())
        key = (gate_id, norm_plate)
        evicted_pending_entry: dict[str, Any] | None = None
        has_alive_entry_remaining = False
        with self._pending_guard():
            pending_entries = getattr(self, "_pending_entries", None)
            pending_exits = getattr(self, "_pending_exits", None)
            for pending_dict in (pending_entries, pending_exits):
                if pending_dict is None:
                    continue
                entry = pending_dict.get(key)
                if entry is None:
                    continue
                if self._is_pending_expired(entry, effective_now):
                    popped = pending_dict.pop(key, None)
                    if pending_dict is pending_entries and popped is not None:
                        evicted_pending_entry = popped
                    continue
                existing_last = entry.get("last_seen_at")
                entry["last_seen_at"] = (
                    ts if existing_last is None else max(float(existing_last), ts)
                )
                if decisive_frame is not None:
                    entry["decisive_frame"] = decisive_frame
            if evicted_pending_entry is not None and pending_entries is not None:
                has_alive_entry_remaining = any(
                    k[0] == gate_id and not self._is_pending_expired(v, effective_now)
                    for k, v in pending_entries.items()
                )

        if evicted_pending_entry is not None and not has_alive_entry_remaining:
            gate = self._managed_gates.get(gate_id)
            if gate is not None:
                self._record_pending_entry_expired(gate, evicted_pending_entry["plate"])

    @staticmethod
    def _load_streams_config(override: dict[str, str] | None = None) -> dict[str, str]:
        """Load streams configuration from parameter or Django settings."""
        if override is not None:
            return dict(override)

        raw = getattr(settings, "GATE_WORKER_STREAMS", "{}")
        if isinstance(raw, dict):
            return dict(raw)
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    return parsed
            except Exception as exc:
                logger.error("Failed to parse GATE_WORKER_STREAMS setting: %s", exc)
        return {}

    @classmethod
    def _parse_gate_tokens(cls, gate_filter: str | list[str] | set[str]) -> set[str]:
        """Normalize gate filter specification into a set of uppercase tokens."""
        if isinstance(gate_filter, str):
            raw_items = gate_filter.split(",")
        elif isinstance(gate_filter, (list, tuple, set)):
            raw_items = []
            for item in gate_filter:
                if isinstance(item, str):
                    raw_items.extend(item.split(","))
                else:
                    raw_items.append(str(item))
        else:
            raw_items = [str(gate_filter)]

        return {t.strip().upper() for t in raw_items if t.strip()}

    @classmethod
    def _filter_streams(
        cls, streams_map: dict[str, str], gate_filter: str | list[str] | set[str]
    ) -> dict[str, str]:
        """Filter streams map by gate code or numeric database ID tokens."""
        tokens = cls._parse_gate_tokens(gate_filter)
        if not tokens:
            return dict(streams_map)

        # Resolve numeric IDs to gate codes from database if available
        numeric_ids = [int(t) for t in tokens if t.isdigit()]
        if numeric_ids:
            try:
                from apps.parking.models import ParkingGate

                db_codes = ParkingGate.objects.filter(id__in=numeric_ids).values_list(
                    "code", flat=True
                )
                tokens.update(c.strip().upper() for c in db_codes if c)
            except Exception as exc:
                logger.debug("Could not resolve numeric gate IDs to codes: %s", exc)

        return {
            k: v
            for k, v in streams_map.items()
            if k.strip().upper() in tokens or str(k).strip() in tokens
        }

    def _setup_signal_handlers(self) -> None:
        """Register graceful shutdown signal handlers on main thread."""

        def _handler(signum: int, frame: Any) -> None:
            logger.info(
                "Received termination signal %d, initiating shutdown...", signum
            )
            self._stop_event.set()

        try:
            signal.signal(signal.SIGINT, _handler)
            signal.signal(signal.SIGTERM, _handler)
        except ValueError, AttributeError:
            # Not in main thread or signal not supported on platform
            pass

    def _acquire_gate(self, gate: ParkingGate) -> bool:
        """
        Acquire PostgreSQL advisory lock, initialize StreamReader & MotionFilter,
        update camera_status="ONLINE", and add to managed gates.
        Returns True if acquired and started, False if locked by another replica or error.
        """
        if gate.id in self._managed_gates:
            return True

        stream_url = self._streams_map.get(gate.code)
        if not stream_url:
            return False

        # 1. Acquire PostgreSQL session advisory lock
        lock = GateAdvisoryLock(gate.id)
        if not lock.acquire():
            logger.info(
                "Gate %s (#%d) is locked by another worker replica, bypassing.",
                gate.code,
                gate.id,
            )
            return False

        self._locks[gate.id] = lock
        self._managed_gates[gate.id] = gate

        mad_thresh = getattr(settings, "GATE_WORKER_MOTION_MAD_THRESHOLD", 5.0)
        max_fps = getattr(settings, "GATE_WORKER_MAX_OCR_RATE_FPS", 2.0)

        # 2. Instantiate stream reader
        reader = StreamReader(gate_code=gate.code, stream_url=stream_url)
        self._readers[gate.id] = reader

        # 3. Instantiate motion filter
        motion_filter = MotionFilter(mad_threshold=mad_thresh, max_fps=max_fps)
        self._filters[gate.id] = motion_filter

        self._last_evaluated_timestamps[gate.id] = 0.0

        # Start reader thread and update camera status
        reader.start()
        self._update_gate_camera_status(gate, "ONLINE")

        logger.info(
            "Gate %s (#%d, direction=%s) worker initialized successfully.",
            gate.code,
            gate.id,
            gate.direction,
        )
        return True

    def _release_gate(self, gate_id: int) -> None:
        """
        Stop StreamReader, release PostgreSQL advisory lock, mark camera_status="OFFLINE",
        and remove from managed gate registries.
        """
        gate = self._managed_gates.pop(gate_id, None)
        if gate is not None:
            gate.is_active = (
                False  # Deactivate in-memory instance to halt any in-flight ticks
            )
        reader = self._readers.pop(gate_id, None)
        lock = self._locks.pop(gate_id, None)
        self._filters.pop(gate_id, None)
        self._last_evaluated_timestamps.pop(gate_id, None)
        self._gate_cooldown_pause_until.pop(gate_id, None)
        with self._pending_guard():
            last_probe = getattr(self, "_last_pending_ocr_probe_ts", None)
            if last_probe is not None:
                last_probe.pop(gate_id, None)
            pending_entries = getattr(self, "_pending_entries", None)
            if pending_entries is not None:
                for pending_key in [k for k in pending_entries if k[0] == gate_id]:
                    pending_entries.pop(pending_key, None)
            pending_exits = getattr(self, "_pending_exits", None)
            if pending_exits is not None:
                for pending_key in [k for k in pending_exits if k[0] == gate_id]:
                    pending_exits.pop(pending_key, None)

        if reader:
            try:
                reader.stop(timeout=2.0)
            except Exception as exc:
                logger.error("Error stopping reader for gate #%d: %s", gate_id, exc)

        if lock:
            try:
                lock.release()
            except Exception as exc:
                logger.error("Error releasing lock for gate #%d: %s", gate_id, exc)

        if gate:
            with contextlib.suppress(Exception):
                self._update_gate_camera_status(gate, "OFFLINE")
            logger.info("Gate %s (#%d) released successfully.", gate.code, gate_id)
        else:
            with contextlib.suppress(Exception):
                ParkingGate.objects.filter(id=gate_id).update(camera_status="OFFLINE")

    def initialize(self) -> int:
        """
        Query database for configured gates, acquire advisory locks,
        and start stream reader threads via reconciliation.

        Returns:
            Number of successfully initialized and locked camera streams.
        """
        if not self._streams_map:
            logger.warning(
                "No camera streams configured in GATE_WORKER_STREAMS%s.",
                f" for gate {self.gate_code_filter}" if self.gate_code_filter else "",
            )
            return 0

        self.refresh_gate_configs()
        self._last_config_refresh_ts = self._now_monotonic()
        return len(self._managed_gates)

    def _update_gate_camera_status(self, gate: ParkingGate, new_status: str) -> None:
        """Persist camera_status change to database without modifying other fields."""
        if gate.camera_status != new_status:
            gate.camera_status = new_status
            try:
                ParkingGate.objects.filter(id=gate.id).update(camera_status=new_status)
            except Exception as exc:
                logger.error(
                    "Failed to update camera_status for gate #%d: %s",
                    gate.id,
                    exc,
                )

    def _record_auto_event(
        self,
        gate: ParkingGate,
        decision: DecisionResult,
        plate: str,
        description: str | None = None,
    ) -> ActivityLog | None:
        """
        Record immutable audit ActivityLog and cached telemetry for the automated decision.
        Always masks license plate PII per Decree 13/2023/ND-CP and Rule 07.
        """
        if not decision.audit_action:
            return None

        masked_plate = mask_plate(plate)
        now = timezone.now()

        # 1. Structure JSON payload for ActivityLog message
        payload: dict[str, Any] = {
            "action": decision.audit_action,
            "license_plate_masked": masked_plate,
            "reason": decision.reason_code,
            "gate_code": gate.code,
            "gate_name": gate.name,
            "occurred_at": now.isoformat(),
        }
        if description:
            payload["description"] = description

        try:
            return ActivityLog.objects.create(
                actor_account=None,
                action=decision.audit_action,
                entity_type="parking_gate",
                entity_id=gate.id,
                message=json.dumps(payload),
                occurred_at=now,
            )
        except Exception as exc:
            logger.error("Failed to write ActivityLog for gate #%d: %s", gate.id, exc)
            return None

    def _record_pending_entry_expired(
        self,
        gate: ParkingGate,
        plate: str,
    ) -> ActivityLog | None:
        """
        Record ActivityLog when an unregistered pending entry expires (>60s unseen or >900s total)
        and no other alive pending entry remains on this gate, so GET /parking/gates/ transitions
        last_auto_event from UNREGISTERED_VEHICLE -> PENDING_ENTRY_EXPIRED (D2, masked PII only).
        """
        masked_plate = mask_plate(plate)
        now = timezone.now()
        payload: dict[str, Any] = {
            "action": "GATE_AUTO_NEEDS_STAFF",
            "license_plate_masked": masked_plate,
            "reason": "PENDING_ENTRY_EXPIRED",
            "gate_code": gate.code,
            "gate_name": gate.name,
            "occurred_at": now.isoformat(),
        }
        try:
            return ActivityLog.objects.create(
                actor_account=None,
                action="GATE_AUTO_NEEDS_STAFF",
                entity_type="parking_gate",
                entity_id=gate.id,
                message=json.dumps(payload),
                occurred_at=now,
            )
        except Exception as exc:
            logger.error(
                "Failed to write PENDING_ENTRY_EXPIRED ActivityLog for gate #%d: %s",
                gate.id,
                exc,
            )
            return None

    def _resolve_entry_slot(
        self, gate: ParkingGate, context: Any
    ) -> tuple[dict[str, Any] | None, int | None, int | None]:
        """
        Resolve entry slot for a vehicle following J4 priority:
        1. Active ticket's assigned slot (if AVAILABLE or RESERVED).
        2. Active SlotReservation owned by this vehicle in the gate's lot.
        3. Available slot matching vehicle_type (preferring EV_CHARGING for EV, STANDARD otherwise).
        Returns (available_slot_data, target_slot_id, reservation_id).
        """
        if gate.direction != "IN":
            return None, None, None

        if context.active_ticket and context.active_ticket.slot_id:
            slot_obj = context.active_ticket.slot
            if (
                slot_obj
                and slot_obj.deleted_at is None
                and slot_obj.status in ("AVAILABLE", "RESERVED")
            ):
                return (
                    {"slot_id": slot_obj.id, "slot_code": slot_obj.code},
                    slot_obj.id,
                    None,
                )

        now = timezone.now()
        vehicle_type_id = context.vehicle.vehicle_type_id if context.vehicle else None
        is_ev = False
        if context.vehicle and getattr(context.vehicle, "vehicle_type", None):
            vt_code = getattr(context.vehicle.vehicle_type, "code", "") or ""
            vt_name = getattr(context.vehicle.vehicle_type, "name", "") or ""
            if "EV" in vt_code.upper() or "ĐIỆN" in vt_name.upper():
                is_ev = True

        # Prioritize active SlotReservation belonging to this vehicle in the same lot
        my_reservation = None
        if context.vehicle:
            my_reservation = (
                SlotReservation.objects.select_related("slot")
                .filter(
                    vehicle_id=context.vehicle.id,
                    slot__zone__floor__lot_id=gate.lot_id,
                    status="ACTIVE",
                    reserved_from__lte=now,
                    reserved_until__gt=now,
                    deleted_at__isnull=True,
                )
                .first()
            )

        if (
            my_reservation
            and my_reservation.slot
            and my_reservation.slot.status in ("AVAILABLE", "RESERVED")
            and my_reservation.slot.deleted_at is None
        ):
            return (
                {
                    "slot_id": my_reservation.slot.id,
                    "slot_code": my_reservation.slot.code,
                },
                my_reservation.slot.id,
                my_reservation.id,
            )

        # Exclude slots currently reserved by other vehicles
        active_reserved_slot_ids = SlotReservation.objects.filter(
            status="ACTIVE",
            reserved_from__lte=now,
            reserved_until__gt=now,
            deleted_at__isnull=True,
        ).values_list("slot_id", flat=True)

        slots_qs = ParkingSlot.objects.filter(
            zone__floor__lot_id=gate.lot_id,
            status="AVAILABLE",
            deleted_at__isnull=True,
        ).exclude(id__in=active_reserved_slot_ids)

        if vehicle_type_id is not None:
            slots_qs = slots_qs.filter(
                allowed_vehicle_types__vehicle_type_id=vehicle_type_id
            )

        if is_ev:
            kind_order = Case(
                When(slot_kind="EV_CHARGING", then=Value(0)),
                When(slot_kind="STANDARD", then=Value(1)),
                default=Value(2),
                output_field=IntegerField(),
            )
        else:
            kind_order = Case(
                When(slot_kind="STANDARD", then=Value(0)),
                When(slot_kind="EV_CHARGING", then=Value(2)),
                default=Value(1),
                output_field=IntegerField(),
            )

        available_slot_obj = slots_qs.order_by(kind_order, "id").first()
        if available_slot_obj:
            return (
                {
                    "slot_id": available_slot_obj.id,
                    "slot_code": available_slot_obj.code,
                },
                available_slot_obj.id,
                None,
            )

        return None, None, None

    def _evaluate_and_execute(
        self,
        gate: ParkingGate,
        voted_plate: str,
        scan_result: Any,
        first_frame_ts: float | None = None,
        decisive_frame: np.ndarray | None = None,
        sighting_ts: float | None = None,
        touch_liveness: bool = True,
    ) -> DecisionResult:
        """
        Assemble contextual database state, evaluate pure decide_gate_action,
        and execute automated check-in or fee-0 check-out in an atomic transaction.
        """
        # Guard (H6b): Ensure gate remains actively managed by this coordinator before proceeding
        if gate.id not in self._managed_gates or not gate.is_active:
            logger.warning(
                "Gate %s (#%d) was released or deactivated; aborting autonomous execution.",
                gate.code,
                gate.id,
            )
            return DecisionResult(
                action=ACTION_HOLD,
                audit_action=None,
                reason_code="GATE_DEACTIVATED",
            )

        effective_sighting_ts = (
            self._now_monotonic() if sighting_ts is None else float(sighting_ts)
        )
        # Refresh active pending liveness only when the current frame matched voted_plate
        if touch_liveness:
            self._touch_pending_plate(
                gate.id,
                voted_plate,
                now_mono=effective_sighting_ts,
                decisive_frame=decisive_frame,
            )

        # 1. Load combined vehicle context
        context = get_combined_vehicle_context(voted_plate, include_open_session=True)
        vehicle_match = {
            "is_registered": context.vehicle is not None,
            "is_blacklisted": context.is_blacklisted,
            "vehicle_id": context.vehicle.id if context.vehicle else None,
        }
        open_session_data = context.open_session_data

        # 2. Determine slot availability for entry
        available_slot_data, target_slot_id, reservation_id = self._resolve_entry_slot(
            gate, context
        )

        # 3. Calculate fee preview for exit
        fee_preview: Decimal | None = None
        if gate.direction == "OUT":
            if context.open_session:
                try:
                    fee_preview = calculate_parking_fee(
                        context.open_session, timezone.now()
                    )
                except Exception as exc:
                    logger.warning(
                        "Fee preview calculation failed for plate %s: %s",
                        mask_plate(voted_plate),
                        format_failure_text(exc, "fee preview calculation"),
                    )
                    fee_preview = Decimal("1.00")
            else:
                fee_preview = None

        # 4. Extract confidence and review status
        best_candidate = getattr(scan_result, "best_candidate", None)
        confidence = float(best_candidate.confidence) if best_candidate else 0.0
        review_status = getattr(scan_result, "review_status", "AUTO")
        conf_thresh = float(
            getattr(settings, "PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD", 90.0)
        )

        # 5. Evaluate pure decision policy (with customer wallet state on exit)
        wallet = context.wallet if gate.direction == "OUT" else None
        decision = decide_gate_action(
            direction=gate.direction,
            gate_active=gate.is_active,
            is_auto_scan=gate.is_auto_scan,
            review_status=review_status,
            confidence=confidence,
            confidence_threshold=conf_thresh,
            is_plate_stable=True,
            vehicle_match=vehicle_match,
            open_session=open_session_data,
            available_slot=available_slot_data,
            fee_preview=fee_preview,
            customer_has_wallet=(wallet is not None),
            wallet_balance=(wallet.balance if wallet is not None else None),
            wallet_status=(wallet.status if wallet is not None else "ACTIVE"),
        )

        logger.info(
            "Gate %s decision for %s: action=%s, audit=%s, reason=%s",
            gate.code,
            mask_plate(voted_plate),
            decision.action,
            decision.audit_action,
            decision.reason_code,
        )

        # 6. Execute automated actions
        if decision.action == ACTION_AUTO_CHECK_IN:
            if (
                gate.id not in self._managed_gates
                or not self._managed_gates[gate.id].is_active
            ):
                logger.warning(
                    "Gate %s (#%d) was deactivated or unmanaged before check-in execution; aborting.",
                    gate.code,
                    gate.id,
                )
                return DecisionResult(
                    action=ACTION_HOLD,
                    audit_action=None,
                    reason_code="GATE_DEACTIVATED",
                )
            if (
                self._now_monotonic() - effective_sighting_ts
            ) > self._get_pending_seen_seconds():
                logger.info(
                    "Sighting for %s at gate %s aged past seen window before check-in; aborting.",
                    mask_plate(voted_plate),
                    gate.code,
                )
                return DecisionResult(
                    action=ACTION_HOLD,
                    audit_action=None,
                    reason_code="STALE_SIGHTING",
                )
            session = None
            try:
                from apps.parking.services.check_in import check_in_vehicle

                session, _ = check_in_vehicle(
                    license_plate=voted_plate,
                    entry_gate_id=gate.id,
                    slot_id=target_slot_id,
                    recognition_source="AI",
                    ai_confidence=confidence,
                    user=None,  # Handled automatically: entry_handled_by = NULL
                )
                if reservation_id is not None:
                    SlotReservation.objects.filter(
                        id=reservation_id, status="ACTIVE"
                    ).update(status="COMPLETED")
                norm_plate = PlateRecognizer.normalize_plate(voted_plate) or voted_plate
                with self._pending_guard():
                    pending_entries = getattr(self, "_pending_entries", None)
                    if pending_entries is not None:
                        pending_entries.pop((gate.id, norm_plate), None)
                self._voter.set_cooldown(
                    gate.id, voted_plate, now=self._now_monotonic()
                )
                self._record_auto_event(gate, decision, voted_plate)
            except Exception as exc:
                fail_text = format_failure_text(exc, "auto check-in")
                logger.error(
                    "Auto check-in execution failed for %s at gate %s: %s",
                    mask_plate(voted_plate),
                    gate.code,
                    fail_text,
                )
                decision = DecisionResult(
                    action=ACTION_HOLD,
                    audit_action=AUDIT_GATE_AUTO_NEEDS_STAFF,
                    reason_code=REASON_EXECUTION_FAILED,
                )
                self._voter.set_cooldown(
                    gate.id, voted_plate, seconds=60, now=self._now_monotonic()
                )
                self._record_auto_event(
                    gate,
                    decision,
                    voted_plate,
                    description=f"Auto check-in execution failed: {fail_text}",
                )

            # Dispatch background snapshot upload off barrier critical path in isolated guard (H6a)
            if (
                session is not None
                and getattr(session, "id", None)
                and decisive_frame is not None
            ):
                try:
                    self._snapshot_uploader.dispatch_upload(
                        session_id=session.id,
                        frame=decisive_frame,
                        is_entry=True,
                        gate_id=gate.id,
                        gate_code=gate.code,
                        gate_name=gate.name,
                        audit_action=decision.audit_action,
                        reason_code=decision.reason_code,
                        plate=voted_plate,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to dispatch background snapshot upload for auto check-in session #%s: %s",
                        session.id,
                        exc,
                    )
        elif decision.action == ACTION_AUTO_CHECK_OUT:
            if (
                gate.id not in self._managed_gates
                or not self._managed_gates[gate.id].is_active
            ):
                logger.warning(
                    "Gate %s (#%d) was deactivated or unmanaged before check-out execution; aborting.",
                    gate.code,
                    gate.id,
                )
                return DecisionResult(
                    action=ACTION_HOLD,
                    audit_action=None,
                    reason_code="GATE_DEACTIVATED",
                )
            if (
                self._now_monotonic() - effective_sighting_ts
            ) > self._get_pending_seen_seconds():
                logger.info(
                    "Sighting for %s at gate %s aged past seen window before check-out; aborting.",
                    mask_plate(voted_plate),
                    gate.code,
                )
                return DecisionResult(
                    action=ACTION_HOLD,
                    audit_action=None,
                    reason_code="STALE_SIGHTING",
                )
            session = None
            try:
                from apps.parking.services.check_out import check_out_vehicle

                checkout_payment_method = (
                    "WALLET"
                    if decision.reason_code == REASON_VALID_WALLET_PAID
                    else None
                )
                session, _, _ = check_out_vehicle(
                    license_plate=voted_plate,
                    exit_gate_id=gate.id,
                    payment_method=checkout_payment_method,
                    user=None,  # Handled automatically: exit_handled_by = NULL
                )
                norm_plate = PlateRecognizer.normalize_plate(voted_plate) or voted_plate
                with self._pending_guard():
                    pending_exits = getattr(self, "_pending_exits", None)
                    if pending_exits is not None:
                        pending_exits.pop((gate.id, norm_plate), None)
                self._voter.set_cooldown(
                    gate.id, voted_plate, now=self._now_monotonic()
                )
                self._record_auto_event(gate, decision, voted_plate)
            except Exception as exc:
                fail_text = format_failure_text(exc, "auto check-out")
                logger.error(
                    "Auto check-out execution failed for %s at gate %s: %s",
                    mask_plate(voted_plate),
                    gate.code,
                    fail_text,
                )
                decision = DecisionResult(
                    action=ACTION_HOLD,
                    audit_action=AUDIT_GATE_AUTO_NEEDS_STAFF,
                    reason_code=REASON_EXECUTION_FAILED,
                )
                self._voter.set_cooldown(
                    gate.id, voted_plate, seconds=60, now=self._now_monotonic()
                )
                self._record_auto_event(
                    gate,
                    decision,
                    voted_plate,
                    description=f"Auto check-out execution failed: {fail_text}",
                )

            # Dispatch background snapshot upload off barrier critical path in isolated guard (H6a)
            if (
                session is not None
                and getattr(session, "id", None)
                and decisive_frame is not None
            ):
                try:
                    self._snapshot_uploader.dispatch_upload(
                        session_id=session.id,
                        frame=decisive_frame,
                        is_entry=False,
                        gate_id=gate.id,
                        gate_code=gate.code,
                        gate_name=gate.name,
                        audit_action=decision.audit_action,
                        reason_code=decision.reason_code,
                        plate=voted_plate,
                    )
                except Exception as exc:
                    logger.warning(
                        "Failed to dispatch background snapshot upload for auto check-out session #%s: %s",
                        session.id,
                        exc,
                    )
        elif decision.action == ACTION_HOLD and decision.audit_action is not None:
            if decision.reason_code == REASON_WALLET_INSUFFICIENT:
                # D8 / D1: Do not apply 30s voter cooldown; register pending exit with still-seen liveness
                norm_plate = PlateRecognizer.normalize_plate(voted_plate) or voted_plate
                pending_key = (gate.id, norm_plate)
                open_session_id = (
                    context.open_session.id if context.open_session else None
                )
                now_mono = self._now_monotonic()
                needs_register = False
                with self._pending_guard():
                    pending_exits = getattr(self, "_pending_exits", None)
                    if pending_exits is None:
                        pending_exits = {}
                        self._pending_exits = pending_exits
                    existing_pending = pending_exits.get(pending_key)
                    if existing_pending is not None and self._is_pending_expired(
                        existing_pending, now_mono
                    ):
                        pending_exits.pop(pending_key, None)
                        existing_pending = None
                    already_registered = (
                        existing_pending is not None
                        and existing_pending.get("session_id") == open_session_id
                    )
                    if already_registered and existing_pending is not None:
                        if touch_liveness:
                            existing_last = existing_pending.get("last_seen_at")
                            existing_pending["last_seen_at"] = (
                                now_mono
                                if existing_last is None
                                else max(float(existing_last), now_mono)
                            )
                            if decisive_frame is not None:
                                existing_pending["decisive_frame"] = decisive_frame
                    elif open_session_id is not None and touch_liveness:
                        needs_register = True

                if needs_register and open_session_id is not None:
                    self._record_auto_event(gate, decision, voted_plate)
                    account_id = (
                        context.customer.account_id
                        if context.customer is not None
                        else None
                    )
                    if account_id is not None:
                        try:
                            fee_val = (
                                Decimal(str(fee_preview))
                                if fee_preview is not None
                                else Decimal("0.00")
                            )
                            bal_val = (
                                wallet.balance
                                if wallet is not None
                                else Decimal("0.00")
                            )
                            missing_val = max(
                                Decimal("0.00"),
                                (fee_val - bal_val).quantize(Decimal("0.01")),
                            )
                            fee_str = f"{fee_val:,.0f}"
                            bal_str = f"{bal_val:,.0f}"
                            missing_str = f"{missing_val:,.0f}"
                            is_wallet_locked = (
                                wallet is not None
                                and str(wallet.status).upper() != "ACTIVE"
                            )
                            if is_wallet_locked:
                                notif_title = (
                                    f"Ví đang bị khóa tại cổng ra ({gate.name})"
                                )[:200]
                                notif_content = (
                                    f"Ví của xe {mask_plate(voted_plate)} hiện đang tạm khóa "
                                    f"hoặc đã đóng nên không thể thanh toán phí {fee_str} VND. "
                                    "Vui lòng liên hệ nhân viên hoặc thanh toán tại quầy."
                                )
                            elif missing_val > Decimal("0.00"):
                                notif_title = (
                                    f"Số dư ví không đủ tại cổng ra ({gate.name})"
                                )[:200]
                                notif_content = (
                                    f"Xe {mask_plate(voted_plate)} cần thanh toán {fee_str} VND "
                                    f"nhưng số dư ví hiện tại là {bal_str} VND "
                                    f"(còn thiếu {missing_str} VND). "
                                    f"Vui lòng nạp thêm tối thiểu {missing_str} VND vào ví "
                                    "hoặc thanh toán tại quầy."
                                )
                            else:
                                notif_title = (
                                    f"Số dư ví không đủ tại cổng ra ({gate.name})"
                                )[:200]
                                notif_content = (
                                    f"Xe {mask_plate(voted_plate)} cần thanh toán {fee_str} VND "
                                    f"nhưng số dư ví hiện tại là {bal_str} VND. "
                                    "Vui lòng nạp thêm tiền vào ví hoặc thanh toán tại quầy."
                                )
                            Notification.objects.create(
                                recipient_account_id=account_id,
                                title=notif_title,
                                content=notif_content,
                                notification_type="PAYMENT",
                            )
                        except Exception as exc:
                            logger.warning(
                                "Failed to create WALLET_INSUFFICIENT notification: %s",
                                exc,
                            )
                    insert_mono = self._now_monotonic()
                    with self._pending_guard():
                        pending_exits = getattr(self, "_pending_exits", None)
                        if pending_exits is None:
                            pending_exits = {}
                            self._pending_exits = pending_exits
                        existing_now = pending_exits.get(pending_key)
                        if (
                            existing_now is not None
                            and not self._is_pending_expired(existing_now, insert_mono)
                            and existing_now.get("session_id") == open_session_id
                        ):
                            if touch_liveness:
                                existing_last = existing_now.get("last_seen_at")
                                existing_now["last_seen_at"] = (
                                    insert_mono
                                    if existing_last is None
                                    else max(float(existing_last), insert_mono)
                                )
                                if decisive_frame is not None:
                                    existing_now["decisive_frame"] = decisive_frame
                        else:
                            self._evict_oldest_if_needed(
                                pending_exits, gate.id, pending_key, insert_mono
                            )
                            pending_exits[pending_key] = {
                                "plate": voted_plate,
                                "norm_plate": norm_plate,
                                "session_id": open_session_id,
                                "customer_id": context.customer.id
                                if context.customer is not None
                                else None,
                                "account_id": account_id,
                                "first_seen_at": insert_mono,
                                "last_seen_at": insert_mono,
                                "expires_at": insert_mono
                                + (self._get_pending_minutes() * 60.0),
                                "last_recheck_ts": insert_mono,
                                "decisive_frame": decisive_frame,
                            }
            elif (
                decision.reason_code == REASON_UNREGISTERED_VEHICLE
                and gate.direction == "IN"
            ):
                # D7 / D1: Do not apply 30s voter cooldown; register pending entry with still-seen liveness
                norm_plate = PlateRecognizer.normalize_plate(voted_plate) or voted_plate
                pending_key = (gate.id, norm_plate)
                now_mono = self._now_monotonic()
                needs_register = False
                with self._pending_guard():
                    pending_entries = getattr(self, "_pending_entries", None)
                    if pending_entries is None:
                        pending_entries = {}
                        self._pending_entries = pending_entries
                    existing_pending = pending_entries.get(pending_key)
                    if existing_pending is not None and self._is_pending_expired(
                        existing_pending, now_mono
                    ):
                        pending_entries.pop(pending_key, None)
                        existing_pending = None
                    if existing_pending is not None:
                        if touch_liveness:
                            existing_last = existing_pending.get("last_seen_at")
                            existing_pending["last_seen_at"] = (
                                now_mono
                                if existing_last is None
                                else max(float(existing_last), now_mono)
                            )
                            if decisive_frame is not None:
                                existing_pending["decisive_frame"] = decisive_frame
                    elif touch_liveness:
                        needs_register = True

                if needs_register:
                    self._record_auto_event(gate, decision, voted_plate)
                    insert_mono = self._now_monotonic()
                    pending_minutes = self._get_pending_minutes()
                    with self._pending_guard():
                        pending_entries = getattr(self, "_pending_entries", None)
                        if pending_entries is None:
                            pending_entries = {}
                            self._pending_entries = pending_entries
                        existing_now = pending_entries.get(pending_key)
                        if existing_now is not None and not self._is_pending_expired(
                            existing_now, insert_mono
                        ):
                            if touch_liveness:
                                existing_last = existing_now.get("last_seen_at")
                                existing_now["last_seen_at"] = (
                                    insert_mono
                                    if existing_last is None
                                    else max(float(existing_last), insert_mono)
                                )
                                if decisive_frame is not None:
                                    existing_now["decisive_frame"] = decisive_frame
                        else:
                            self._evict_oldest_if_needed(
                                pending_entries, gate.id, pending_key, insert_mono
                            )
                            pending_entries[pending_key] = {
                                "plate": voted_plate,
                                "norm_plate": norm_plate,
                                "confidence": confidence,
                                "first_seen_at": insert_mono,
                                "last_seen_at": insert_mono,
                                "expires_at": insert_mono + (pending_minutes * 60.0),
                                "last_recheck_ts": insert_mono,
                                "decisive_frame": decisive_frame,
                            }
            else:
                self._voter.set_cooldown(
                    gate.id, voted_plate, now=self._now_monotonic()
                )
                self._record_auto_event(gate, decision, voted_plate)

        if first_frame_ts is not None:
            commit_ts = self._now_monotonic()
            latency_ms = round((commit_ts - first_frame_ts) * 1000.0, 2)
            logger.info(
                "DECISION_LATENCY gate=%s plate=%s latency_ms=%.2f first_frame_ts=%.4f commit_ts=%.4f action=%s reason=%s",
                gate.code,
                mask_plate(voted_plate),
                latency_ms,
                first_frame_ts,
                commit_ts,
                decision.action,
                decision.reason_code,
            )

        return decision

    def _log_frame_stats(self) -> None:
        """Emit cumulative frame ingestion and OCR processing telemetry."""
        total_ingested = sum(
            cnt if isinstance(cnt := getattr(r, "frames_read_count", 0), int) else 0
            for r in self._readers.values()
        )
        with self._stats_lock:
            ocr_processed = self._ocr_processed_count
            skipped = self._filtered_or_skipped_count
        dropped = max(0, total_ingested - ocr_processed)
        logger.info(
            "WORKER_FRAME_STATS ingested=%d ocr_processed=%d dropped=%d skipped=%d",
            total_ingested,
            ocr_processed,
            dropped,
            skipped,
        )

    def refresh_gate_configs(self) -> dict[int, ParkingGate]:
        """
        Dynamically reconcile managed gates:
        1. Query database for all gates in streams_map (subject to gate_code_filter).
        2. De-acquire gates that are inactive, soft-deleted, or missing (release advisory lock, stop reader, camera_status="OFFLINE").
        3. Acquire newly active gates (acquire advisory lock, start reader & filter, camera_status="ONLINE").
        4. Skip gates locked by another replica.
        5. Update dynamic fields (is_auto_scan, direction, name) in-place for active managed gates.

        Returns:
            dict mapping gate_id to ParkingGate for all currently managed gates.
        """
        if not self._streams_map:
            # If no streams mapped, release any remaining gates
            for gate_id in list(self._managed_gates.keys()):
                self._release_gate(gate_id)
            return {}

        target_codes = list(self._streams_map.keys())

        try:
            db_gates = ParkingGate.objects.filter(
                code__in=target_codes,
                deleted_at__isnull=True,
            ).only(
                "id",
                "code",
                "name",
                "direction",
                "is_active",
                "is_auto_scan",
                "camera_status",
                "lot_id",
            )
            db_gate_map = {g.id: g for g in db_gates}

            # 1. De-acquire gates that are inactive, soft-deleted, or missing
            for gate_id in list(self._managed_gates.keys()):
                try:
                    updated = db_gate_map.get(gate_id)
                    if updated is None or not updated.is_active:
                        gate_code = (
                            self._managed_gates[gate_id].code
                            if gate_id in self._managed_gates
                            else str(gate_id)
                        )
                        logger.info(
                            "Gate %s (#%d) is inactive or missing, releasing...",
                            gate_code,
                            gate_id,
                        )
                        self._release_gate(gate_id)
                    else:
                        managed = self._managed_gates[gate_id]
                        if managed.is_auto_scan != updated.is_auto_scan:
                            logger.info(
                                "Gate %s (#%d) is_auto_scan changed: %s -> %s",
                                managed.code,
                                gate_id,
                                managed.is_auto_scan,
                                updated.is_auto_scan,
                            )
                            managed.is_auto_scan = updated.is_auto_scan
                        if managed.direction != updated.direction:
                            logger.info(
                                "Gate %s (#%d) direction changed: %s -> %s",
                                managed.code,
                                gate_id,
                                managed.direction,
                                updated.direction,
                            )
                            managed.direction = updated.direction
                        if managed.name != updated.name:
                            managed.name = updated.name
                        managed.is_active = updated.is_active
                        managed.lot_id = updated.lot_id
                except Exception as exc:
                    logger.error(
                        "Error reconciling existing gate #%d: %s", gate_id, exc
                    )

            # 2. Acquire newly active gates (isolated per-gate try/except)
            for db_gate in db_gates:
                try:
                    if db_gate.is_active and db_gate.id not in self._managed_gates:
                        self._acquire_gate(db_gate)
                except Exception as exc:
                    logger.error(
                        "Failed to acquire gate %s (#%d): %s",
                        db_gate.code,
                        db_gate.id,
                        exc,
                    )

        except Exception as exc:
            logger.error("Failed to dynamically refresh gate configs: %s", exc)

        return self._managed_gates

    _refresh_gate_configs = refresh_gate_configs

    def _recheck_pending_entries(self, gate: ParkingGate) -> None:
        """
        Re-evaluate pending entries (D7 / D1) while the vehicle is still seen at the gate.
        - Evicts entries exceeding GATE_WORKER_PENDING_MINUTES or 3 * GATE_WORKER_PENDING_SEEN_SECONDS.
        - Silently waits with 0 DB queries / 0 logs / 0 actions in (seen_seconds, 3 * seen_seconds].
        - Re-checks freshness right before executing check_in_vehicle (D1(4)) without holding _pending_lock across DB calls.
        """
        if gate.direction != "IN":
            return

        now_mono = self._now_monotonic()
        recheck_seconds = float(getattr(self, "_pending_recheck_seconds", 5.0))
        conf_thresh = float(
            getattr(settings, "PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD", 90.0)
        )

        candidates: list[tuple[tuple[int, str], dict[str, Any]]] = []
        evicted_entries: list[dict[str, Any]] = []
        has_alive_remaining = False
        with self._pending_guard():
            pending_entries = getattr(self, "_pending_entries", None)
            if not pending_entries:
                return
            gate_keys = [k for k in list(pending_entries.keys()) if k[0] == gate.id]
            for key in gate_keys:
                entry = pending_entries.get(key)
                if not entry:
                    continue
                if self._is_pending_expired(entry, now_mono):
                    popped = pending_entries.pop(key, None)
                    if popped is not None:
                        evicted_entries.append(popped)
                    continue
                has_alive_remaining = True
                if not self._is_pending_still_seen(entry, now_mono):
                    # Silent wait window (seen_seconds, 3 * seen_seconds]: zero DB queries, zero logs, zero actions
                    continue
                if entry.get("in_flight"):
                    continue
                if (
                    now_mono - float(entry.get("last_recheck_ts", 0.0))
                ) < recheck_seconds:
                    continue
                entry["last_recheck_ts"] = now_mono
                candidates.append((key, dict(entry)))

        if evicted_entries and not has_alive_remaining:
            self._record_pending_entry_expired(gate, evicted_entries[-1]["plate"])

        if not candidates:
            return

        for key, snapshot in candidates:
            if (
                gate.id not in self._managed_gates
                or not gate.is_active
                or not gate.is_auto_scan
            ):
                return

            try:
                veh = (
                    Vehicle.objects.filter(
                        license_plate_norm=snapshot["norm_plate"],
                        deleted_at__isnull=True,
                        customer__isnull=False,
                        customer__deleted_at__isnull=True,
                        customer__status="ACTIVE",
                    )
                    .only("id", "license_plate")
                    .first()
                )
                if veh is None:
                    continue

                context = get_combined_vehicle_context(
                    snapshot["plate"], include_open_session=True
                )
                if context.vehicle is None:
                    continue

                available_slot_data, target_slot_id, reservation_id = (
                    self._resolve_entry_slot(gate, context)
                )
                vehicle_match = {
                    "is_registered": True,
                    "is_blacklisted": context.is_blacklisted,
                    "vehicle_id": context.vehicle.id,
                }
                decision = decide_gate_action(
                    direction=gate.direction,
                    gate_active=gate.is_active,
                    is_auto_scan=gate.is_auto_scan,
                    review_status="AUTO",
                    confidence=snapshot["confidence"],
                    confidence_threshold=conf_thresh,
                    is_plate_stable=True,
                    vehicle_match=vehicle_match,
                    open_session=context.open_session_data,
                    available_slot=available_slot_data,
                )

                if decision.action == ACTION_AUTO_CHECK_IN:
                    if (
                        gate.id not in self._managed_gates
                        or not self._managed_gates[gate.id].is_active
                    ):
                        return

                    # D1(4): Verify freshness & per-key in_flight guard right before action
                    expired_plate: str | None = None
                    has_alive_remaining_for_gate = False
                    with self._pending_guard():
                        current = pending_entries.get(key)
                        action_now = self._now_monotonic()
                        if current is None:
                            continue
                        if self._is_pending_expired(current, action_now):
                            popped = pending_entries.pop(key, None)
                            if popped is not None:
                                expired_plate = popped["plate"]
                                has_alive_remaining_for_gate = any(
                                    k[0] == gate.id
                                    and not self._is_pending_expired(v, action_now)
                                    for k, v in pending_entries.items()
                                )
                        elif not self._is_pending_still_seen(
                            current, action_now
                        ) or current.get("in_flight"):
                            continue
                        else:
                            current["in_flight"] = True

                    if expired_plate is not None:
                        if not has_alive_remaining_for_gate:
                            self._record_pending_entry_expired(gate, expired_plate)
                        continue

                    try:
                        from apps.parking.services.check_in import check_in_vehicle

                        session, _ = check_in_vehicle(
                            license_plate=snapshot["plate"],
                            entry_gate_id=gate.id,
                            slot_id=target_slot_id,
                            recognition_source="AI",
                            ai_confidence=snapshot["confidence"],
                            user=None,
                        )
                        if reservation_id is not None:
                            SlotReservation.objects.filter(
                                id=reservation_id, status="ACTIVE"
                            ).update(status="COMPLETED")

                        with self._pending_guard():
                            pending_entries.pop(key, None)
                        self._voter.set_cooldown(
                            gate.id, snapshot["plate"], now=self._now_monotonic()
                        )
                        self._record_auto_event(gate, decision, snapshot["plate"])

                        decisive_frame = snapshot.get("decisive_frame")
                        uploader = getattr(self, "_snapshot_uploader", None)
                        if (
                            uploader is not None
                            and session is not None
                            and getattr(session, "id", None)
                            and decisive_frame is not None
                        ):
                            with contextlib.suppress(Exception):
                                uploader.dispatch_upload(
                                    session_id=session.id,
                                    frame=decisive_frame,
                                    is_entry=True,
                                    gate_id=gate.id,
                                    gate_code=gate.code,
                                    gate_name=gate.name,
                                    audit_action=decision.audit_action,
                                    reason_code=decision.reason_code,
                                    plate=snapshot["plate"],
                                )
                    finally:
                        with self._pending_guard():
                            if key in pending_entries:
                                pending_entries[key].pop("in_flight", None)
                elif (
                    decision.action == ACTION_HOLD and decision.audit_action is not None
                ):
                    with self._pending_guard():
                        pending_entries.pop(key, None)
                    self._voter.set_cooldown(
                        gate.id, snapshot["plate"], now=self._now_monotonic()
                    )
                    self._record_auto_event(gate, decision, snapshot["plate"])
            except Exception as exc:
                fail_text = format_failure_text(exc, "pending entry recheck")
                logger.warning(
                    "Pending entry recheck failed on gate %s: %s",
                    gate.code,
                    fail_text,
                )
                with self._pending_guard():
                    pending_entries.pop(key, None)
                self._voter.set_cooldown(
                    gate.id, snapshot["plate"], seconds=60, now=self._now_monotonic()
                )
                fail_decision = DecisionResult(
                    action=ACTION_HOLD,
                    audit_action=AUDIT_GATE_AUTO_NEEDS_STAFF,
                    reason_code=REASON_EXECUTION_FAILED,
                )
                self._record_auto_event(
                    gate,
                    fail_decision,
                    snapshot["plate"],
                    description=f"Pending entry auto check-in failed: {fail_text}",
                )

    def _recheck_pending_exits(self, gate: ParkingGate) -> None:
        """
        Re-evaluate pending exits (D8 / D1) while the vehicle is still seen at the gate.
        - Evicts entries exceeding GATE_WORKER_PENDING_MINUTES or 3 * GATE_WORKER_PENDING_SEEN_SECONDS.
        - Silently waits with 0 DB queries / 0 logs / 0 actions in (seen_seconds, 3 * seen_seconds].
        - Re-checks freshness right before check_out_vehicle (D1(4)) and relies on atomic tx re-verification (D1(5)).
        """
        if gate.direction != "OUT":
            return

        now_mono = self._now_monotonic()
        recheck_seconds = float(getattr(self, "_pending_recheck_seconds", 5.0))

        candidates: list[tuple[tuple[int, str], dict[str, Any]]] = []
        with self._pending_guard():
            pending_exits = getattr(self, "_pending_exits", None)
            if not pending_exits:
                return
            gate_keys = [k for k in list(pending_exits.keys()) if k[0] == gate.id]
            for key in gate_keys:
                entry = pending_exits.get(key)
                if not entry:
                    continue
                if self._is_pending_expired(entry, now_mono):
                    pending_exits.pop(key, None)
                    continue
                if not self._is_pending_still_seen(entry, now_mono):
                    # Silent wait window (seen_seconds, 3 * seen_seconds]: zero DB queries, zero logs, zero actions
                    continue
                if entry.get("in_flight"):
                    continue
                if (
                    now_mono - float(entry.get("last_recheck_ts", 0.0))
                ) < recheck_seconds:
                    continue
                entry["last_recheck_ts"] = now_mono
                candidates.append((key, dict(entry)))

        if not candidates:
            return

        for key, snapshot in candidates:
            if gate.id not in self._managed_gates or not gate.is_active:
                return

            try:
                open_session = (
                    VehicleEntryExitLog.objects.select_related(
                        "ticket", "vehicle__customer"
                    )
                    .filter(id=snapshot["session_id"], exit_time__isnull=True)
                    .first()
                )
                if open_session is None:
                    with self._pending_guard():
                        pending_exits.pop(key, None)
                    continue

                fee = calculate_parking_fee(open_session, timezone.now())
                if fee > Decimal("0.00"):
                    customer_id = snapshot.get("customer_id")
                    if not customer_id:
                        with self._pending_guard():
                            pending_exits.pop(key, None)
                        continue
                    wallet = (
                        Wallet.objects.filter(
                            customer_id=customer_id, deleted_at__isnull=True
                        )
                        .only("id", "balance", "status")
                        .first()
                    )
                    if not wallet or wallet.status != "ACTIVE" or wallet.balance < fee:
                        continue
                    checkout_method: str | None = "WALLET"
                    reason_code = REASON_VALID_WALLET_PAID
                else:
                    checkout_method = None
                    reason_code = REASON_VALID_FEE_ZERO

                # D1(4): Verify freshness & per-key in_flight guard right before action
                with self._pending_guard():
                    current = pending_exits.get(key)
                    action_now = self._now_monotonic()
                    if current is None:
                        continue
                    if self._is_pending_expired(current, action_now):
                        pending_exits.pop(key, None)
                        continue
                    if not self._is_pending_still_seen(current, action_now):
                        continue
                    if current.get("in_flight"):
                        continue
                    current["in_flight"] = True

                try:
                    from apps.parking.services.check_out import check_out_vehicle

                    session, _, _ = check_out_vehicle(
                        session_code=open_session.session_code,
                        exit_gate_id=gate.id,
                        payment_method=checkout_method,
                        user=None,
                    )
                    with self._pending_guard():
                        pending_exits.pop(key, None)
                    self._voter.set_cooldown(
                        gate.id, snapshot["plate"], now=self._now_monotonic()
                    )
                    resolved_decision = DecisionResult(
                        action=ACTION_AUTO_CHECK_OUT,
                        audit_action=AUDIT_GATE_AUTO_CHECK_OUT,
                        reason_code=reason_code,
                    )
                    self._record_auto_event(gate, resolved_decision, snapshot["plate"])

                    decisive_frame = snapshot.get("decisive_frame")
                    if (
                        session is not None
                        and getattr(session, "id", None)
                        and decisive_frame is not None
                    ):
                        with contextlib.suppress(Exception):
                            self._snapshot_uploader.dispatch_upload(
                                session_id=session.id,
                                frame=decisive_frame,
                                is_entry=False,
                                gate_id=gate.id,
                                gate_code=gate.code,
                                gate_name=gate.name,
                                audit_action=resolved_decision.audit_action,
                                reason_code=resolved_decision.reason_code,
                                plate=snapshot["plate"],
                            )
                except InsufficientWalletBalanceError:
                    continue
                except BusinessAPIException as exc:
                    if getattr(exc, "code", None) == "PROP-4.5.1-P10":
                        # Session was already closed concurrently; evict cleanly without error
                        with self._pending_guard():
                            pending_exits.pop(key, None)
                        continue
                    logger.warning(
                        "Pending exit recheck failed on gate %s: %s",
                        gate.code,
                        format_failure_text(exc, "pending exit recheck"),
                    )
                finally:
                    with self._pending_guard():
                        if key in pending_exits:
                            pending_exits[key].pop("in_flight", None)
            except Exception as exc:
                logger.warning(
                    "Pending exit recheck failed on gate %s: %s",
                    gate.code,
                    format_failure_text(exc, "pending exit recheck"),
                )

    def _process_gate_tick(self, gate: ParkingGate) -> None:
        """Process one iteration tick for a single camera gate."""
        reader = self._readers.get(gate.id)
        motion_filter = self._filters.get(gate.id)
        if not reader or not motion_filter:
            return

        # 1. Update camera status in DB if reader status shifted
        r_status = reader.status
        if r_status == STATUS_STREAMING:
            self._update_gate_camera_status(gate, "ONLINE")
        elif r_status == STATUS_DEGRADED:
            self._update_gate_camera_status(gate, "DEGRADED")
        elif r_status == STATUS_OFFLINE:
            self._update_gate_camera_status(gate, "OFFLINE")

        # Inactive gate bypasses frame processing, OCR inference, and semaphore contention
        if not gate.is_active:
            with self._stats_lock:
                self._filtered_or_skipped_count += 1
            return

        # D7 & D8: Re-evaluate pending entries and pending exits before frame/motion filters (stationary vehicles)
        self._recheck_pending_entries(gate)
        self._recheck_pending_exits(gate)

        # 2. Pull newest frame (latest-frame-wins)
        frame, frame_ts = reader.get_latest_frame()
        if frame is None or frame_ts <= self._last_evaluated_timestamps.get(
            gate.id, 0.0
        ):
            return

        self._last_evaluated_timestamps[gate.id] = frame_ts

        # 3.5. Skip OCR while gate is in short post-decision cooldown backoff
        if frame_ts < self._gate_cooldown_pause_until.get(gate.id, 0.0):
            with self._stats_lock:
                self._filtered_or_skipped_count += 1
            return

        # 4. Motion pre-filter check (allow stationary presence-probe OCR every recheck interval when pending exists)
        now_mono = self._now_monotonic()
        should_proc, reason, _ = motion_filter.should_process(frame, now=now_mono)
        if not should_proc:
            allow_presence_probe = False
            if reason == "NO_MOTION" and self._has_alive_pending_for_gate(
                gate.id, now_mono
            ):
                with self._pending_guard():
                    probe_map = getattr(self, "_last_pending_ocr_probe_ts", None)
                    if probe_map is None:
                        probe_map = {}
                        self._last_pending_ocr_probe_ts = probe_map
                    last_probe_ts = probe_map.get(gate.id, 0.0)
                    recheck_interval = float(
                        getattr(self, "_pending_recheck_seconds", 5.0)
                    )
                    if (now_mono - last_probe_ts) >= recheck_interval:
                        probe_map[gate.id] = now_mono
                        allow_presence_probe = True
            if not allow_presence_probe:
                with self._stats_lock:
                    self._filtered_or_skipped_count += 1
                return
        else:
            with self._pending_guard():
                probe_map = getattr(self, "_last_pending_ocr_probe_ts", None)
                if probe_map is not None:
                    probe_map[gate.id] = now_mono

        # 5. Acquire bounded concurrency semaphore for OCR
        acquired = self._ocr_semaphore.acquire(blocking=False)
        if not acquired:
            # Overloaded/busy: skip frame (newest-frame-wins principle)
            with self._stats_lock:
                self._filtered_or_skipped_count += 1
            return

        scan_result = None
        try:
            recognizer = get_plate_recognizer()
            # Convert BGR frame to PIL Image for OCR pipeline
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_image = Image.fromarray(rgb)
            scan_result = recognizer.recognize(pil_image)
            with self._stats_lock:
                self._ocr_processed_count += 1
        except Exception as exc:
            logger.warning(
                "OCR recognition failed on gate %s: %s",
                gate.code,
                format_failure_text(exc, "OCR recognition"),
            )
        finally:
            self._ocr_semaphore.release()

        if scan_result is None:
            return

        # 6. Feed detected plate to temporal stability voter
        best_candidate = getattr(scan_result, "best_candidate", None)
        raw_detected_plate = best_candidate.plate_normalized if best_candidate else None
        detected_plate = (
            (PlateRecognizer.normalize_plate(raw_detected_plate) or None)
            if raw_detected_plate and str(raw_detected_plate).strip()
            else None
        )

        if detected_plate:
            self._touch_pending_plate(
                gate.id,
                detected_plate,
                now_mono=now_mono,
                decisive_frame=frame.copy(),
            )

        if detected_plate and self._voter.is_in_cooldown(
            gate.id, detected_plate, now=frame_ts
        ):
            self._gate_cooldown_pause_until[gate.id] = frame_ts + 2.0
            return

        is_stable, voted_plate = self._voter.add_observation(
            gate.id, detected_plate, frame_ts=frame_ts
        )
        if not is_stable or not voted_plate:
            return

        # Empty-road (OCR -> None) or cross-plate spillover ([A, A, A, X] where X != voted_plate)
        # must not pop first_seen_ts, touch cooldowns, trigger evaluation, or pause the gate.
        voted_norm = PlateRecognizer.normalize_plate(voted_plate) or voted_plate
        if not detected_plate or detected_plate != voted_norm:
            return

        # 7. Check cooldown
        if self._voter.is_in_cooldown(gate.id, voted_plate):
            self._gate_cooldown_pause_until[gate.id] = frame_ts + 2.0
            return

        # 8. Retrieve first frame timestamp for decision latency calculation
        first_frame_ts = self._voter.pop_first_seen_ts(
            gate.id, voted_plate, default_ts=frame_ts
        )

        # 9. Evaluate and execute autonomous decision with decisive frame
        self._evaluate_and_execute(
            gate,
            voted_plate,
            scan_result,
            first_frame_ts=first_frame_ts,
            decisive_frame=frame.copy(),
            sighting_ts=now_mono,
            touch_liveness=(detected_plate == voted_norm),
        )
        self._gate_cooldown_pause_until[gate.id] = self._now_monotonic() + 2.0

    def run(self, duration: float | None = None) -> None:
        """
        Run the main coordinator loop.

        Args:
            duration: Maximum seconds to run (for testing/bounded executions).
                      If None, runs indefinitely until SIGINT/SIGTERM or stop().
        """
        self._setup_signal_handlers()
        self._is_running = True
        self._stop_event.clear()

        start_time = self._now_monotonic()
        self._last_stats_log_ts = start_time
        logger.info(
            "GateWorkerCoordinator started (duration=%s, managed_gates=%d)",
            f"{duration}s" if duration is not None else "infinite",
            len(self._managed_gates),
        )

        def _run_gate_tick_safe(g: ParkingGate) -> None:
            try:
                self._process_gate_tick(g)
            except Exception as exc:
                logger.error(
                    "Error processing gate %s tick: %s",
                    g.code,
                    format_failure_text(exc, "gate tick"),
                )
            finally:
                close_old_connections()
                with self._tick_lock:
                    self._active_gate_ticks.discard(g.id)

        try:
            with ThreadPoolExecutor(max_workers=self._concurrency_limit) as executor:
                while not self._stop_event.is_set():
                    now_mono = self._now_monotonic()
                    if duration is not None and (now_mono - start_time) >= duration:
                        logger.info(
                            "Reached specified duration %.1fs, exiting...", duration
                        )
                        break

                    if (now_mono - self._last_stats_log_ts) >= 2.0:
                        self._log_frame_stats()
                        self._last_stats_log_ts = now_mono

                    # Dynamic gate configuration refresh (TL Decision 4, F5)
                    if (
                        now_mono - self._last_config_refresh_ts
                    ) >= self._config_refresh_interval:
                        self.refresh_gate_configs()
                        self._last_config_refresh_ts = now_mono

                    for gate in list(self._managed_gates.values()):
                        if self._stop_event.is_set():
                            break
                        with self._tick_lock:
                            if gate.id in self._active_gate_ticks:
                                continue
                            self._active_gate_ticks.add(gate.id)
                        executor.submit(_run_gate_tick_safe, gate)

                    # Short tick pause to avoid tight spin-loop
                    time.sleep(0.05)
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        """Stop all stream reader threads, release advisory locks, and mark offline."""
        self._stop_event.set()
        logger.info("Shutting down GateWorkerCoordinator...")
        self._log_frame_stats()

        # 1. Stop all stream readers
        for gate_id, reader in self._readers.items():
            try:
                reader.stop(timeout=2.0)
            except Exception as exc:
                logger.error("Error stopping reader for gate #%d: %s", gate_id, exc)
        self._readers.clear()

        # 2. Release advisory locks and close connections
        for gate_id, lock in self._locks.items():
            try:
                lock.release()
            except Exception as exc:
                logger.error("Error releasing lock for gate #%d: %s", gate_id, exc)
        self._locks.clear()

        # 3. Mark managed gates OFFLINE & clear pending state
        for gate in self._managed_gates.values():
            with contextlib.suppress(Exception):
                self._update_gate_camera_status(gate, "OFFLINE")
        self._managed_gates.clear()

        with self._pending_guard():
            pending_entries = getattr(self, "_pending_entries", None)
            if pending_entries is not None:
                pending_entries.clear()
            pending_exits = getattr(self, "_pending_exits", None)
            if pending_exits is not None:
                pending_exits.clear()
            last_probe = getattr(self, "_last_pending_ocr_probe_ts", None)
            if last_probe is not None:
                last_probe.clear()

        # 4. Shut down background snapshot uploader threads
        try:
            self._snapshot_uploader.shutdown(wait=True)
        except Exception as exc:
            logger.error("Error shutting down snapshot uploader: %s", exc)

        self._is_running = False
        logger.info("GateWorkerCoordinator shutdown complete.")

    def stop(self) -> None:
        """Signal the coordinator to stop."""
        self._stop_event.set()
