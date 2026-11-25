"""
Temporal stability plate voter and duplicate event cooldown tracker.
Adheres to ADR-0011 Section 2.3 Item 4 & Section 2.4 (TL-68, TL-69).
Requires 3 identical normalized plates out of the last 4 frames before triggering decision.
Prevents duplicate event spamming via per-(gate_id, normalized_plate) cooldown.
"""

from __future__ import annotations

import collections
import threading
import time
from collections.abc import Callable

from django.conf import settings
from django.core.cache import cache

from apps.parking.services.ocr import PlateRecognizer


class PlateVoter:
    """
    Tracks license plate observations per gate over a sliding window (default: 4 frames).
    Enforces temporal stability requirement: 3 identical normalized plates out of 4 frames.
    Maintains cooldown timestamps per (gate_id, normalized_plate) pair to prevent repeated decisions.
    """

    def __init__(
        self,
        window_size: int = 4,
        required_matches: int = 3,
        cooldown_seconds: int = 30,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self.window_size = max(1, int(window_size))
        self.required_matches = max(1, int(required_matches))
        self.cooldown_seconds = max(1, int(cooldown_seconds))
        self._clock: Callable[[], float] = (
            clock if clock is not None else time.monotonic
        )

        # gate_id -> deque of normalized plates (length <= window_size)
        self._gate_histories: dict[int, collections.deque[str | None]] = {}
        # (gate_id, normalized_plate) -> expiry_monotonic
        self._local_cooldowns: dict[tuple[int, str], float] = {}
        # (gate_id, normalized_plate) -> first observation timestamp (monotonic)
        self._first_seen_ts: dict[tuple[int, str], float] = {}
        self._lock = threading.RLock()

    def add_observation(
        self,
        gate_id: int,
        plate_text: str | None,
        frame_ts: float | None = None,
    ) -> tuple[bool, str | None]:
        """
        Record a newly detected plate for a specific gate.

        Args:
            gate_id: ID of the parking gate.
            plate_text: Raw or normalized plate string (or None/empty if no plate detected).
            frame_ts: Optional monotonic timestamp of the frame.

        Returns:
            (is_stable: bool, voted_plate: str | None)
            is_stable is True if at least required_matches (default 3) identical normalized
            plates are present within the last window_size (default 4) observations.
        """
        norm_plate = (
            PlateRecognizer.normalize_plate(plate_text)
            if plate_text and plate_text.strip()
            else None
        )

        with self._lock:
            if gate_id not in self._gate_histories:
                self._gate_histories[gate_id] = collections.deque(
                    maxlen=self.window_size
                )

            history = self._gate_histories[gate_id]

            now_ts = float(self._clock()) if frame_ts is None else float(frame_ts)
            if norm_plate:
                if self.is_in_cooldown(gate_id, norm_plate, now=now_ts):
                    return False, None
                key = (gate_id, norm_plate)
                if norm_plate not in history or key not in self._first_seen_ts:
                    self._first_seen_ts[key] = now_ts

            history.append(norm_plate)

            # Count frequencies of non-None plates in history
            counter = collections.Counter(p for p in history if p is not None)
            for plate, count in counter.items():
                if count >= self.required_matches:
                    return True, plate

            return False, None

    def pop_first_seen_ts(
        self,
        gate_id: int,
        normalized_plate: str | None,
        default_ts: float | None = None,
    ) -> float:
        """Pop and return the earliest observation timestamp for this (gate_id, plate) sequence."""
        if not normalized_plate:
            return default_ts if default_ts is not None else float(self._clock())
        norm = PlateRecognizer.normalize_plate(normalized_plate)
        key = (gate_id, norm)
        with self._lock:
            ts = self._first_seen_ts.pop(key, None)
        if ts is not None:
            return ts
        return default_ts if default_ts is not None else float(self._clock())

    def is_in_cooldown(
        self,
        gate_id: int,
        normalized_plate: str | None,
        now: float | None = None,
    ) -> bool:
        """
        Check if the (gate_id, normalized_plate) pair is currently under cooldown.
        Checks local in-memory monotonic timestamp first, then shared cache.
        """
        if not normalized_plate:
            return False

        norm = PlateRecognizer.normalize_plate(normalized_plate)
        key = (gate_id, norm)

        with self._lock:
            # 1. Check local in-memory cooldown
            if key in self._local_cooldowns:
                current_time = float(self._clock()) if now is None else float(now)
                expiry = self._local_cooldowns[key]
                if current_time < expiry:
                    return True
                # Expired in local memory: evict from memory and shared cache
                self._local_cooldowns.pop(key, None)
                cache.delete(f"gate_worker_cooldown:{gate_id}:{norm}")
                return False

        # 2. Check shared Django cache (for multi-worker replica coordination)
        if now is None:
            cache_key = f"gate_worker_cooldown:{gate_id}:{norm}"
            if cache.get(cache_key):
                return True

        return False

    def set_cooldown(
        self,
        gate_id: int,
        normalized_plate: str,
        seconds: int | None = None,
        now: float | None = None,
    ) -> None:
        """
        Mark the (gate_id, normalized_plate) pair in cooldown.
        Persists to in-memory dictionary and shared Django cache.
        """
        if not normalized_plate:
            return

        norm = PlateRecognizer.normalize_plate(normalized_plate)
        cd_sec = (
            int(seconds)
            if seconds is not None
            else getattr(
                settings, "GATE_WORKER_COOLDOWN_SECONDS", self.cooldown_seconds
            )
        )
        current_time = float(self._clock()) if now is None else float(now)

        with self._lock:
            # Set local in-memory cooldown
            self._local_cooldowns[(gate_id, norm)] = current_time + cd_sec
            # Remove from first seen tracker and clear gate window as cooldown started
            self._first_seen_ts.pop((gate_id, norm), None)
            if gate_id in self._gate_histories:
                self._gate_histories[gate_id].clear()

        # Set shared cache cooldown
        cache_key = f"gate_worker_cooldown:{gate_id}:{norm}"
        cache.set(cache_key, True, timeout=cd_sec)

    def reset_gate(self, gate_id: int) -> None:
        """Clear observation history for a gate."""
        with self._lock:
            if gate_id in self._gate_histories:
                self._gate_histories[gate_id].clear()
            keys_to_remove = [k for k in self._first_seen_ts if k[0] == gate_id]
            for k in keys_to_remove:
                self._first_seen_ts.pop(k, None)
