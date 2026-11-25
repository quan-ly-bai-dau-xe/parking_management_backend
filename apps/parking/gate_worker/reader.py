"""
Camera stream reader worker thread using OpenCV VideoCapture.
Adheres to ADR-0011 Section 2.3 & 2.4 (TL-67, TL-68).
Enforces latest-frame-wins (zero queue backlog) and exponential backoff reconnection.
Zero credential leakage: Stream URLs are never logged or exposed.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time
from collections.abc import Callable

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# State constants matching ADR-0011 Section 2.4
STATUS_OFFLINE = "OFFLINE"
STATUS_STREAMING = "STREAMING"
STATUS_DEGRADED = "DEGRADED"


class StreamReader:
    """
    Independent reader thread per camera stream.
    Ingests frames via cv2.VideoCapture into a single-frame buffer (latest-frame-wins).
    Automatically reconnects with exponential backoff on network dropouts.
    """

    def __init__(
        self,
        gate_code: str,
        stream_url: str,
        reconnect_initial: float = 2.0,
        reconnect_max: float = 30.0,
        frame_timeout: float = 5.0,
        max_width: int = 640,
        on_status_change: Callable[[str, str], None] | None = None,
    ) -> None:
        self.gate_code = gate_code
        self._stream_url = stream_url  # Strictly private, never logged or exposed
        self._reconnect_initial = max(0.1, float(reconnect_initial))
        self._reconnect_max = max(self._reconnect_initial, float(reconnect_max))
        self._frame_timeout = max(0.5, float(frame_timeout))
        self._max_width = max(64, int(max_width))
        self._on_status_change = on_status_change

        self._status = STATUS_OFFLINE
        self._status_lock = threading.Lock()

        # Latest-frame-wins buffer: single frame + timestamp
        self._frame_lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._last_frame_timestamp: float = 0.0
        self._frames_read_count: int = 0

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._cap: cv2.VideoCapture | None = None

    @property
    def frames_read_count(self) -> int:
        """Total frames ingested from the camera stream."""
        with self._frame_lock:
            return self._frames_read_count

    @property
    def status(self) -> str:
        """Current camera stream status: OFFLINE, STREAMING, or DEGRADED."""
        with self._status_lock:
            return self._status

    def _set_status(self, new_status: str) -> None:
        """Transition status and notify listener if changed."""
        with self._status_lock:
            if self._status != new_status:
                old_status = self._status
                self._status = new_status
                logger.info(
                    "Gate %s stream status changed: %s -> %s",
                    self.gate_code,
                    old_status,
                    new_status,
                )
                if self._on_status_change:
                    try:
                        self._on_status_change(self.gate_code, new_status)
                    except Exception as exc:
                        logger.error(
                            "Status change callback failed for gate %s: %s",
                            self.gate_code,
                            exc,
                        )

    def start(self) -> None:
        """Start reader thread if not already running."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name=f"StreamReader-{self.gate_code}",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        """Signal reader thread to stop and wait for termination."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None
        self._cleanup_cap()
        self._set_status(STATUS_OFFLINE)

    def is_alive(self) -> bool:
        """Return True if background reader thread is active."""
        return self._thread is not None and self._thread.is_alive()

    def get_latest_frame(self) -> tuple[np.ndarray | None, float]:
        """
        Thread-safe fetch of latest ingested frame and monotonic timestamp.
        Zero queue backlog: returns latest frame without queue delays.
        """
        with self._frame_lock:
            frame = (
                self._latest_frame.copy() if self._latest_frame is not None else None
            )
            timestamp = self._last_frame_timestamp
            return frame, timestamp

    def _cleanup_cap(self) -> None:
        """Release underlying OpenCV VideoCapture resources safely."""
        if self._cap is not None:
            with contextlib.suppress(Exception):
                self._cap.release()
            self._cap = None

    def _open_capture(self) -> cv2.VideoCapture | None:
        """Instantiate VideoCapture for stream URL without logging credentials."""
        try:
            cap = cv2.VideoCapture(self._stream_url)
            if cap.isOpened():
                return cap
            cap.release()
        except Exception as exc:
            logger.debug(
                "VideoCapture initialization error for gate %s: %s",
                self.gate_code,
                exc,
            )
        return None

    def _run_loop(self) -> None:
        """Main ingestion loop with exponential backoff reconnection."""
        current_backoff = self._reconnect_initial

        while not self._stop_event.is_set():
            cap = self._open_capture()
            if cap is None:
                self._set_status(STATUS_DEGRADED)
                # Exponential backoff sleep checking stop_event periodically
                sleep_end = time.monotonic() + current_backoff
                while time.monotonic() < sleep_end and not self._stop_event.is_set():
                    time.sleep(0.1)
                current_backoff = min(current_backoff * 2.0, self._reconnect_max)
                continue

            self._cap = cap
            self._set_status(STATUS_STREAMING)
            current_backoff = self._reconnect_initial
            last_successful_read = time.monotonic()

            while not self._stop_event.is_set():
                try:
                    ret, frame = cap.read()
                except Exception as exc:
                    logger.warning(
                        "Stream read exception on gate %s: %s",
                        self.gate_code,
                        exc,
                    )
                    ret, frame = False, None

                now = time.monotonic()
                if not ret or frame is None:
                    # Check frame timeout
                    if now - last_successful_read > self._frame_timeout:
                        logger.warning(
                            "Gate %s stream read timeout (>%.1fs), reconnecting...",
                            self.gate_code,
                            self._frame_timeout,
                        )
                        break
                    time.sleep(0.01)
                    continue

                last_successful_read = now
                if frame.ndim >= 2 and frame.shape[1] > self._max_width:
                    scale = self._max_width / float(frame.shape[1])
                    new_h = max(1, int(round(frame.shape[0] * scale)))
                    frame = cv2.resize(
                        frame, (self._max_width, new_h), interpolation=cv2.INTER_AREA
                    )
                # Latest-frame-wins: overwrite previous frame immediately
                with self._frame_lock:
                    self._latest_frame = frame
                    self._last_frame_timestamp = now
                    self._frames_read_count += 1

            self._cleanup_cap()
            if not self._stop_event.is_set():
                self._set_status(STATUS_DEGRADED)
                # Short pause before reconnect
                time.sleep(0.2)

        self._cleanup_cap()
        self._set_status(STATUS_OFFLINE)
