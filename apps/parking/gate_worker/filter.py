"""
Cheap pixel motion pre-filter and rate limiter for camera streams.
Adheres to ADR-0011 Section 2.3 Item 2 (TL-68).
Computes Mean Absolute Difference (MAD) on 64x64 downscaled thumbnails
to skip expensive OCR when no vehicle movement is detected.
"""

from __future__ import annotations

import time

import cv2
import numpy as np


class MotionFilter:
    """
    Evaluates consecutive video frames to filter out static scenes and rate limit OCR.
    1. Downscales frame to 64x64 grayscale.
    2. Calculates Mean Absolute Difference (MAD) against previous processed frame.
    3. Enforces maximum inferences per second (max_fps).
    """

    THUMBNAIL_SIZE = (64, 64)

    def __init__(
        self,
        mad_threshold: float = 5.0,
        max_fps: float = 2.0,
    ) -> None:
        self.mad_threshold = float(mad_threshold)
        self.max_fps = max(0.1, float(max_fps))
        self._min_interval = 1.0 / self.max_fps

        self._prev_thumbnail: np.ndarray | None = None
        self._last_processed_time: float = 0.0

    @staticmethod
    def to_grayscale_thumbnail(frame: np.ndarray) -> np.ndarray:
        """Convert an arbitrary frame to a 64x64 single-channel uint8 thumbnail."""
        if frame.ndim == 3 and frame.shape[2] == 3:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        elif frame.ndim == 3 and frame.shape[2] == 4:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        else:
            gray = frame

        if gray.shape[:2] != MotionFilter.THUMBNAIL_SIZE:
            gray = cv2.resize(
                gray, MotionFilter.THUMBNAIL_SIZE, interpolation=cv2.INTER_AREA
            )
        return gray

    @staticmethod
    def compute_mad(thumb1: np.ndarray, thumb2: np.ndarray) -> float:
        """Compute Mean Absolute Difference (MAD) between two 64x64 thumbnails."""
        diff = np.abs(thumb1.astype(np.float32) - thumb2.astype(np.float32))
        return float(np.mean(diff))

    def should_process(
        self,
        frame: np.ndarray,
        now: float | None = None,
    ) -> tuple[bool, str, float]:
        """
        Evaluate whether the given frame should proceed to OCR inference.

        Returns:
            (should_process: bool, reason: str, mad_value: float)
            reasons:
              - 'INITIAL_FRAME': First frame observed, accepted as baseline.
              - 'RATE_LIMITED': Throttled by max_fps cap.
              - 'NO_MOTION': Pixel difference below mad_threshold.
              - 'MOTION_DETECTED': Pixel difference >= mad_threshold.
        """
        current_time = time.monotonic() if now is None else float(now)

        # 1. Rate limiting check
        if (current_time - self._last_processed_time) < self._min_interval:
            return False, "RATE_LIMITED", 0.0

        thumbnail = self.to_grayscale_thumbnail(frame)

        # 2. Initial frame baseline
        if self._prev_thumbnail is None:
            self._prev_thumbnail = thumbnail
            self._last_processed_time = current_time
            return True, "INITIAL_FRAME", 0.0

        # 3. Motion calculation (Mean Absolute Difference)
        mad = self.compute_mad(self._prev_thumbnail, thumbnail)

        if mad < self.mad_threshold:
            # Below threshold -> no significant motion -> bypass OCR
            return False, "NO_MOTION", mad

        # Motion detected -> accept frame and update baseline reference
        self._prev_thumbnail = thumbnail
        self._last_processed_time = current_time
        return True, "MOTION_DETECTED", mad

    def reset(self) -> None:
        """Reset internal history and timing."""
        self._prev_thumbnail = None
        self._last_processed_time = 0.0
