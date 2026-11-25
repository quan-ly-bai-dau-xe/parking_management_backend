"""
Background snapshot upload module for headless gate worker.
Adheres to ADR-0011 Section 2 and TL-73 (Snapshot Off-Critical-Path).
Encodes decisive frame to bounded JPEG (max_side <= 1280, quality 85),
dispatches upload asynchronously via bounded ThreadPoolExecutor,
and attaches resulting Cloudinary URL to VehicleEntryExitLog.
Upload failures fail gracefully without raising exceptions or stalling the barrier,
and append the sanitized failure reason to the gate's immutable ActivityLog feed.
"""

from __future__ import annotations

import io
import json
import logging
import re
import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

import cv2
import numpy as np
from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone
from PIL import Image

from apps.audit.models import ActivityLog
from apps.core.logging import mask_plate
from apps.parking.models import VehicleEntryExitLog
from apps.parking.services.upload import ProcessedImage, save_processed_image

logger = logging.getLogger(__name__)

ACTION_GATE_AUTO_SNAPSHOT_FAILED = "GATE_AUTO_SNAPSHOT_FAILED"

DEFAULT_SNAPSHOT_MAX_SIDE = 1280
DEFAULT_SNAPSHOT_JPEG_QUALITY = 85
DEFAULT_SNAPSHOT_TIMEOUT = 5.0
DEFAULT_SNAPSHOT_MAX_WORKERS = 2

_CREDENTIAL_REDACT_RE = re.compile(
    r"(cloudinary://[^\s\"']+|(?:api_key|api_secret|secret|token|password)\s*[:=]?\s*[^\s,;\"')]+)",
    re.IGNORECASE,
)


def _sanitize_snapshot_error(raw_reason: str, plate: str | None = None) -> str:
    """Redact credential tokens and mask any license plate text in upload error strings."""
    cleaned = _CREDENTIAL_REDACT_RE.sub("[REDACTED]", raw_reason or "")
    if plate:
        for candidate in {
            plate,
            plate.replace("-", "").replace(".", "").replace(" ", "").upper(),
        }:
            if candidate and candidate in cleaned:
                cleaned = cleaned.replace(candidate, mask_plate(plate))
    return cleaned.strip()[:240]


def resize_and_encode_jpeg(
    frame: np.ndarray,
    max_side: int = DEFAULT_SNAPSHOT_MAX_SIDE,
    quality: int = DEFAULT_SNAPSHOT_JPEG_QUALITY,
) -> tuple[bytes, int, int]:
    """
    Downscale decisive frame so max(width, height) <= max_side,
    and compress to JPEG quality in an in-memory buffer.

    Args:
        frame: OpenCV image ndarray (BGR).
        max_side: Maximum allowed dimension in pixels.
        quality: JPEG compression quality (1-100).

    Returns:
        tuple of (jpeg_bytes, width, height).
    """
    if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
        raise ValueError("Cannot encode an empty or invalid frame")

    h, w = frame.shape[:2]
    long_side = max(h, w)
    if long_side > max_side:
        # Scale proportionally to prevent image distortion while bounding frame memory
        scale = max_side / float(long_side)
        new_w = max(1, int(round(w * scale)))
        new_h = max(1, int(round(h * scale)))
        resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
    else:
        resized = frame
        new_w, new_h = w, h

    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
    success, buffer = cv2.imencode(".jpg", resized, encode_params)
    if not success or buffer is None:
        raise ValueError("cv2.imencode failed to compress frame to JPEG")

    return buffer.tobytes(), new_w, new_h


class SnapshotUploader:
    """
    Asynchronous snapshot uploader running off the barrier critical path.
    Uses a bounded thread pool and hard timeout to guarantee zero delay
    on barrier decisions.
    """

    def __init__(
        self,
        max_workers: int | None = None,
        timeout: float | None = None,
        upload_service: Callable[[ProcessedImage], tuple[Any, str]] | None = None,
    ) -> None:
        workers = (
            int(max_workers)
            if max_workers is not None
            else getattr(
                settings,
                "GATE_WORKER_SNAPSHOT_MAX_WORKERS",
                DEFAULT_SNAPSHOT_MAX_WORKERS,
            )
        )
        self._max_workers = max(1, workers)

        t_val = (
            float(timeout)
            if timeout is not None
            else getattr(
                settings, "GATE_WORKER_SNAPSHOT_TIMEOUT", DEFAULT_SNAPSHOT_TIMEOUT
            )
        )
        self._timeout = max(0.5, t_val)

        # Injectable upload service allowing test mocking and production Cloudinary binding
        self._upload_service = upload_service or save_processed_image
        self._executor = ThreadPoolExecutor(
            max_workers=self._max_workers,
            thread_name_prefix="snapshot-upload",
        )
        self._shutdown_lock = threading.Lock()
        self._is_shutdown = False

    @property
    def is_shutdown(self) -> bool:
        with self._shutdown_lock:
            return self._is_shutdown

    def dispatch_upload(
        self,
        session_id: int,
        frame: np.ndarray,
        is_entry: bool,
        *,
        gate_id: int | None = None,
        gate_code: str | None = None,
        gate_name: str | None = None,
        audit_action: str | None = None,
        reason_code: str | None = None,
        plate: str | None = None,
    ) -> Future[str | None] | None:
        """
        Dispatch background snapshot compression and upload task without blocking caller.

        Args:
            session_id: Target VehicleEntryExitLog primary key.
            frame: Raw decisive frame from camera stream reader.
            is_entry: True for check-in entry_image_url, False for check-out exit_image_url.
            gate_id: Optional gate ID for recording upload failure in ActivityLog.
            gate_code: Optional gate code for event payload.
            gate_name: Optional gate display name for event payload.
            audit_action: Optional GATE_AUTO_* action code for failure event.
            reason_code: Optional decision reason code for failure event.
            plate: Optional raw/display plate (always masked before writing to ActivityLog).

        Returns:
            Future instance representing background task, or None if uploader is stopped.
        """
        with self._shutdown_lock:
            if self._is_shutdown:
                logger.warning(
                    "SnapshotUploader is shut down; dropping upload for session #%d",
                    session_id,
                )
                return None

            if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
                logger.warning(
                    "Invalid frame provided for session #%d; skipping upload",
                    session_id,
                )
                return None

            # Copy frame array to isolate snapshot from future reader buffer modifications
            frame_copy = frame.copy()
            return self._executor.submit(
                self._worker_upload_task,
                session_id=session_id,
                frame=frame_copy,
                is_entry=is_entry,
                gate_id=gate_id,
                gate_code=gate_code,
                gate_name=gate_name,
                audit_action=audit_action,
                reason_code=reason_code,
                plate=plate,
            )

    def _record_snapshot_failure_event(
        self,
        *,
        gate_id: int | None,
        gate_code: str | None,
        gate_name: str | None,
        audit_action: str | None,
        reason_code: str | None,
        plate: str | None,
        failure_reason: str,
    ) -> None:
        """Append an immutable ActivityLog entry noting the snapshot upload failure reason."""
        if gate_id is None:
            return
        now = timezone.now()
        sanitized = _sanitize_snapshot_error(failure_reason, plate=plate)
        payload: dict[str, Any] = {
            "action": ACTION_GATE_AUTO_SNAPSHOT_FAILED,
            "decision_action": audit_action or "",
            "license_plate_masked": mask_plate(plate) if plate else "",
            "reason": reason_code or "",
            "gate_code": gate_code or "",
            "gate_name": gate_name or "",
            "snapshot_error": sanitized,
            "occurred_at": now.isoformat(),
        }
        try:
            ActivityLog.objects.create(
                actor_account=None,
                action=ACTION_GATE_AUTO_SNAPSHOT_FAILED,
                entity_type="parking_gate",
                entity_id=gate_id,
                message=json.dumps(payload),
                occurred_at=now,
            )
        except Exception as log_exc:
            logger.warning(
                "Failed to record snapshot failure event for gate #%s: %s",
                gate_id,
                log_exc,
            )

    def _worker_upload_task(
        self,
        session_id: int,
        frame: np.ndarray,
        is_entry: bool,
        *,
        gate_id: int | None = None,
        gate_code: str | None = None,
        gate_name: str | None = None,
        audit_action: str | None = None,
        reason_code: str | None = None,
        plate: str | None = None,
    ) -> str | None:
        """
        Background worker routine: encodes image, calls upload service with timeout,
        and updates database record upon success or notes failure reason on error.
        """
        # Ensure fresh database connection per background thread
        close_old_connections()
        try:
            # 1. Compress to bounded JPEG in-memory buffer
            max_side = getattr(
                settings, "GATE_WORKER_SNAPSHOT_MAX_SIDE", DEFAULT_SNAPSHOT_MAX_SIDE
            )
            quality = getattr(
                settings,
                "GATE_WORKER_SNAPSHOT_JPEG_QUALITY",
                DEFAULT_SNAPSHOT_JPEG_QUALITY,
            )
            jpeg_bytes, w, h = resize_and_encode_jpeg(
                frame, max_side=max_side, quality=quality
            )

            # 2. Build ProcessedImage for upload service compatibility
            pil_img = Image.open(io.BytesIO(jpeg_bytes))
            processed = ProcessedImage(
                pil_image=pil_img,
                width=w,
                height=h,
                format="JPEG",
                ext=".jpg",
                image_bytes=jpeg_bytes,
            )

            # 3. Execute upload service bounded by hard timeout
            inner_exec = ThreadPoolExecutor(max_workers=1)
            try:
                future = inner_exec.submit(self._upload_service, processed)
                _, secure_url = future.result(timeout=self._timeout)
            finally:
                # Avoid hanging background threads on shutdown
                inner_exec.shutdown(wait=False)

            if not secure_url or not isinstance(secure_url, str):
                raise ValueError(f"Upload service returned invalid URL: {secure_url!r}")

            # 4. Patch URL into database record
            if is_entry:
                VehicleEntryExitLog.objects.filter(id=session_id).update(
                    entry_image_url=secure_url
                )
            else:
                VehicleEntryExitLog.objects.filter(id=session_id).update(
                    exit_image_url=secure_url
                )

            logger.info(
                "Snapshot upload succeeded for session #%d (%s): %s",
                session_id,
                "IN" if is_entry else "OUT",
                secure_url,
            )
            return secure_url

        except FutureTimeoutError:
            reason_msg = f"TimeoutError: upload timed out after {self._timeout:.1f}s"
            logger.warning(
                "Snapshot upload failed for session #%d (%s): %s",
                session_id,
                "IN" if is_entry else "OUT",
                reason_msg,
            )
            self._record_snapshot_failure_event(
                gate_id=gate_id,
                gate_code=gate_code,
                gate_name=gate_name,
                audit_action=audit_action,
                reason_code=reason_code,
                plate=plate,
                failure_reason=reason_msg,
            )
            return None
        except Exception as exc:
            err_desc = f"{exc.__class__.__name__}: {exc}"
            if getattr(exc, "__cause__", None):
                err_desc = (
                    f"{err_desc} ({exc.__cause__.__class__.__name__}: {exc.__cause__})"
                )
            reason_msg = _sanitize_snapshot_error(err_desc, plate=plate)
            logger.warning(
                "Snapshot upload failed for session #%d (%s): %s",
                session_id,
                "IN" if is_entry else "OUT",
                reason_msg,
            )
            self._record_snapshot_failure_event(
                gate_id=gate_id,
                gate_code=gate_code,
                gate_name=gate_name,
                audit_action=audit_action,
                reason_code=reason_code,
                plate=plate,
                failure_reason=reason_msg,
            )
            return None
        finally:
            # Clean up thread connection
            close_old_connections()

    def shutdown(self, wait: bool = True) -> None:
        """Gracefully terminate background upload thread pool."""
        with self._shutdown_lock:
            if self._is_shutdown:
                return
            self._is_shutdown = True

        logger.info("Shutting down SnapshotUploader (wait=%s)...", wait)
        self._executor.shutdown(wait=wait)
        close_old_connections()


_DEFAULT_UPLOADER: SnapshotUploader | None = None
_DEFAULT_UPLOADER_LOCK = threading.Lock()


def get_default_snapshot_uploader() -> SnapshotUploader:
    """Retrieve or initialize singleton default SnapshotUploader instance."""
    global _DEFAULT_UPLOADER
    with _DEFAULT_UPLOADER_LOCK:
        if _DEFAULT_UPLOADER is None or _DEFAULT_UPLOADER.is_shutdown:
            _DEFAULT_UPLOADER = SnapshotUploader()
        return _DEFAULT_UPLOADER


def upload_session_snapshot_async(
    session_id: int,
    frame: np.ndarray,
    is_entry: bool,
    uploader: SnapshotUploader | None = None,
) -> Future[str | None] | None:
    """
    Convenience function matching Master Blueprint contract to dispatch snapshot upload.
    """
    target_uploader = uploader or get_default_snapshot_uploader()
    return target_uploader.dispatch_upload(
        session_id=session_id,
        frame=frame,
        is_entry=is_entry,
    )
