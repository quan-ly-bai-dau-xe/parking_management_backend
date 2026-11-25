"""
Gate serializers for parking app.
Provides representation for barrier gate list and worker telemetry (ADR-0011, TL-70, TL-72).
"""

import json
import re
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.audit.models import ActivityLog
from apps.core.logging import mask_plate
from apps.parking.gate_worker.locks import get_active_gate_worker_lock_ids
from apps.parking.models import ParkingGate

AUTO_AUDIT_ACTIONS = [
    "GATE_AUTO_CHECK_IN",
    "GATE_AUTO_CHECK_OUT",
    "GATE_AUTO_NEEDS_STAFF",
    "GATE_AUTO_PAYMENT_REQUIRED",
]


class GateAutoEventSerializer(serializers.Serializer):
    """Serializer cho sự kiện tự động gần nhất tại cổng barrier (telemetry)."""

    action = serializers.CharField(
        help_text="Mã hành động tự động: GATE_AUTO_CHECK_IN, GATE_AUTO_CHECK_OUT, GATE_AUTO_NEEDS_STAFF, GATE_AUTO_PAYMENT_REQUIRED"
    )
    license_plate_masked = serializers.CharField(
        help_text="Biển số xe đã che mờ bảo mật (vd: 51A-***.14 hoặc 30A***35)"
    )
    reason = serializers.CharField(
        help_text="Mã lý do kỹ thuật (vd: VALID_REGISTERED, VALID_FEE_ZERO, NEEDS_REVIEW, etc.)"
    )
    occurred_at = serializers.DateTimeField(
        help_text="Thời điểm ghi nhận quyết định tự động (ISO 8601 UTC)"
    )
    snapshot_error = serializers.CharField(
        required=False,
        allow_null=True,
        default=None,
        help_text="Lý do lỗi tải ảnh chụp nhanh bất đồng bộ (nếu có; None khi bình thường)",
    )


AUTO_DECISION_ACTIONS = [
    "GATE_AUTO_CHECK_IN",
    "GATE_AUTO_CHECK_OUT",
    "GATE_AUTO_NEEDS_STAFF",
    "GATE_AUTO_PAYMENT_REQUIRED",
]


def _parse_auto_event_log(log: ActivityLog) -> dict[str, Any]:
    """Extract action, license_plate_masked, reason, occurred_at, and snapshot_error from ActivityLog."""
    action = log.action
    plate_masked = ""
    reason = ""
    snapshot_error: str | None = getattr(log, "_snapshot_error", None)
    msg = log.message or ""

    # 1. Try parsing JSON message
    if msg.startswith("{") and msg.endswith("}"):
        try:
            payload = json.loads(msg)
            if isinstance(payload, dict):
                plate_masked = payload.get("license_plate_masked") or payload.get(
                    "plate", ""
                )
                reason = payload.get("reason", "")
                raw_snap_err = payload.get("snapshot_error")
                if isinstance(raw_snap_err, str) and raw_snap_err.strip():
                    snapshot_error = raw_snap_err.strip()
        except Exception:
            pass

    # 2. Extract plate if not found in JSON
    if not plate_masked:
        plate_match = re.search(
            r"(?:biển số|biển|plate)[\s:=]+([^\s,;|\n]+)", msg, re.IGNORECASE
        )
        if plate_match:
            plate_masked = plate_match.group(1).strip().rstrip(".,;:|")
        else:
            raw_match = re.search(r"[0-9]{2}[A-Z0-9*.-]{4,12}", msg)
            if raw_match:
                plate_masked = raw_match.group(0).strip().rstrip(".,;:|")

    # Ensure extracted plate number is masked to protect customer PII (Rule 07, Decree 13/2023/ND-CP)
    if plate_masked and "*" not in plate_masked:
        plate_masked = mask_plate(plate_masked)

    # 3. Extract reason if not found in JSON
    if not reason:
        reason_match = re.search(
            r"(?:lý do|reason)[\s:=]+([A-Z0-9_]+)", msg, re.IGNORECASE
        )
        if reason_match:
            reason = reason_match.group(1).strip()
        else:
            known_reasons = [
                "VALID_REGISTERED",
                "VALID_FEE_ZERO",
                "VALID_WALLET_PAID",
                "WALLET_INSUFFICIENT",
                "UNREGISTERED_VEHICLE",
                "FEE_PAYMENT_REQUIRED",
                "BLACKLISTED",
                "OPEN_SESSION_ALREADY_EXISTS",
                "NO_OPEN_SESSION",
                "NO_AVAILABLE_SLOT",
                "LOW_CONFIDENCE",
                "PLATE_UNSTABLE",
                "GATE_INACTIVE",
                "AUTO_SCAN_DISABLED",
                "NEEDS_REVIEW",
                "EXECUTION_FAILED",
            ]
            for kr in known_reasons:
                if kr in msg:
                    reason = kr
                    break

    return {
        "action": action,
        "license_plate_masked": plate_masked,
        "reason": reason,
        "occurred_at": log.occurred_at,
        "snapshot_error": snapshot_error,
    }


def get_latest_gate_activity_logs_map(
    gate_ids: list[int] | set[int],
    window_hours: int | None = None,
) -> dict[int, ActivityLog]:
    """
    Batch retrieve latest automated decision activity_log entry for a collection of gates in a single query.
    Filters action strictly to AUTO_DECISION_ACTIONS:
    ['GATE_AUTO_CHECK_IN', 'GATE_AUTO_CHECK_OUT', 'GATE_AUTO_NEEDS_STAFF', 'GATE_AUTO_PAYMENT_REQUIRED'].
    Limits query to past `window_hours` (default: settings.GATE_LAST_EVENT_WINDOW_HOURS or 24)
    to leverage idx_activity_log_occurred_at index and maintain O(1) < 2ms latency.
    If a subsequent snapshot failure event ('GATE_AUTO_SNAPSHOT_FAILED') exists for that gate,
    attaches its snapshot_error to the decision log.
    """
    if not gate_ids:
        return {}

    gate_ids_list = list(gate_ids)
    if window_hours is None:
        window_hours = getattr(settings, "GATE_LAST_EVENT_WINDOW_HOURS", 24)

    now = timezone.now()
    since = now - timedelta(hours=window_hours)

    # 1. Latest automated decision log per gate via DISTINCT ON (entity_id) with .only(...)
    decision_qs = (
        ActivityLog.objects.filter(
            action__in=AUTO_DECISION_ACTIONS,
            entity_type__in=["parking_gate", "gate", "PARKING_GATE", "GATE"],
            entity_id__in=gate_ids_list,
            occurred_at__gte=since,
        )
        .order_by("entity_id", "-occurred_at", "-id")
        .distinct("entity_id")
        .only("id", "entity_id", "action", "message", "occurred_at")
    )
    decision_logs: dict[int, ActivityLog] = {
        log.entity_id: log for log in decision_qs if log.entity_id is not None
    }

    if not decision_logs:
        return {}

    # 2. Latest snapshot failure log per gate (only for gates with an active decision)
    snapshot_qs = (
        ActivityLog.objects.filter(
            action="GATE_AUTO_SNAPSHOT_FAILED",
            entity_type__in=["parking_gate", "gate", "PARKING_GATE", "GATE"],
            entity_id__in=list(decision_logs.keys()),
            occurred_at__gte=since,
        )
        .order_by("entity_id", "-occurred_at", "-id")
        .distinct("entity_id")
        .only("id", "entity_id", "action", "message", "occurred_at")
    )
    snapshot_fail_logs: dict[int, ActivityLog] = {
        log.entity_id: log for log in snapshot_qs if log.entity_id is not None
    }

    # 3. Attach snapshot failure error if newer or equal occurred_at/id
    for gid, dec_log in decision_logs.items():
        snap_log = snapshot_fail_logs.get(gid)
        if snap_log and (
            snap_log.occurred_at >= dec_log.occurred_at or snap_log.id > dec_log.id
        ):
            snap_err = None
            msg = snap_log.message or ""
            if msg.startswith("{") and msg.endswith("}"):
                try:
                    payload = json.loads(msg)
                    if isinstance(payload, dict):
                        snap_err = payload.get("snapshot_error")
                except Exception:
                    pass
            if not snap_err:
                snap_err = msg
            dec_log._snapshot_error = snap_err  # type: ignore[attr-defined]

    return decision_logs


def _get_latest_gate_activity_log(gate: ParkingGate) -> ActivityLog | None:
    """Retrieve latest automated activity_log entry associated with this gate."""
    return get_latest_gate_activity_logs_map([gate.id]).get(gate.id)


class ParkingGateListSerializer(serializers.ListSerializer):
    """
    Custom ListSerializer to batch load advisory locks and activity logs for all gates in 2 queries total,
    achieving strict O(1) query complexity regardless of gate count.
    """

    def to_representation(self, data):
        # Prefetch advisory lock IDs once for the entire list
        if "_active_gate_lock_ids" not in self.context:
            self.context["_active_gate_lock_ids"] = get_active_gate_worker_lock_ids()

        # Prefetch latest activity logs once for the entire list
        if "_gate_activity_logs_map" not in self.context:
            gate_ids = (
                [item.id for item in data]
                if isinstance(data, (list, tuple))
                else [g.id for g in data]
            )
            self.context["_gate_activity_logs_map"] = get_latest_gate_activity_logs_map(
                gate_ids
            )

        return super().to_representation(data)


class ParkingGateSerializer(serializers.ModelSerializer):
    """
    Serializer cho cổng kiểm soát barrier xe vào/ra kèm trạng thái worker (ADR-0011, TL-72).
    Trạng thái worker_online được xác thực trực tiếp qua PostgreSQL session advisory lock (pg_locks).
    Khi worker offline, camera_status tự động được ánh xạ thành 'OFFLINE' ở tầng đọc (pure-read,
    không phát sinh UPDATE lên bảng parking_gate để tránh kích hoạt trg_parking_gate_row_version).
    """

    worker_online = serializers.SerializerMethodField(
        help_text="Trạng thái trực tuyến của tiến trình gate-worker (xác thực qua PostgreSQL session advisory lock)"
    )
    last_auto_event = serializers.SerializerMethodField(
        help_text="Sự kiện tự động gần nhất tại cổng barrier từ activity_log"
    )

    class Meta:
        model = ParkingGate
        list_serializer_class = ParkingGateListSerializer
        fields = [
            "id",
            "lot_id",
            "code",
            "name",
            "direction",
            "camera_status",
            "is_auto_scan",
            "is_active",
            "worker_online",
            "last_auto_event",
        ]
        read_only_fields = ["worker_online", "last_auto_event"]

    _cached_active_lock_ids: set[int] | None = None

    def _get_active_lock_ids(self) -> set[int]:
        """Memoize active gate worker lock IDs on serializer context or instance."""
        if (
            self.context is not None
            and isinstance(self.context, dict)
            and "_active_gate_lock_ids" in self.context
        ):
            active_ids_val = self.context["_active_gate_lock_ids"]
            if isinstance(active_ids_val, set):
                return active_ids_val
        if self._cached_active_lock_ids is not None:
            return self._cached_active_lock_ids
        active_ids = get_active_gate_worker_lock_ids()
        if self.context is not None and isinstance(self.context, dict):
            self.context["_active_gate_lock_ids"] = active_ids
        self._cached_active_lock_ids = active_ids
        return active_ids

    def _get_gate_event_log(self, gate: ParkingGate) -> ActivityLog | None:
        """Memoize gate event log on serializer context or instance to prevent redundant DB queries."""
        if self.context is not None and "_gate_activity_logs_map" in self.context:
            return self.context["_gate_activity_logs_map"].get(gate.id)
        cache_attr = f"_gate_log_{gate.id}"
        if not hasattr(self, cache_attr):
            setattr(
                self,
                cache_attr,
                get_latest_gate_activity_logs_map([gate.id]).get(gate.id),
            )
        return getattr(self, cache_attr)

    @extend_schema_field(serializers.BooleanField())
    def get_worker_online(self, obj: ParkingGate) -> bool:
        """
        Check if gate worker currently holds the session advisory lock.
        PostgreSQL advisory lock in pg_locks is the single source of truth.
        """
        active_locks = self._get_active_lock_ids()
        return obj.id in active_locks

    def to_representation(self, instance: ParkingGate) -> dict[str, Any]:
        """
        Dynamically serialize gate representation.
        If the gate's worker is offline (no active advisory lock), map camera_status to 'OFFLINE'.
        Pure-read: avoids any UPDATE statement on parking_gate, preserving row_version and concurrency.
        """
        data = super().to_representation(instance)
        if not data.get("worker_online", False):
            data["camera_status"] = "OFFLINE"
        return data

    @extend_schema_field(GateAutoEventSerializer(allow_null=True))
    def get_last_auto_event(self, obj: ParkingGate) -> dict[str, Any] | None:
        """Extract last automated event for this gate solely from activity_log."""
        event_log = self._get_gate_event_log(obj)
        if event_log:
            parsed = _parse_auto_event_log(event_log)
            return GateAutoEventSerializer(parsed).data

        return None
