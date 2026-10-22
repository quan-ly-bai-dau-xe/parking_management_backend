"""
Bounded Concurrency Gate implementation for heavy workload back-pressure (P2).
Provides thread-safe semaphore gating with configurable timeout and standard error envelope.
"""

import logging
import threading
from collections.abc import Generator
from contextlib import contextmanager

from django.conf import settings
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import ALL_MESSAGES

logger = logging.getLogger(__name__)


class OCRConcurrencyGate:
    """
    Cổng kiểm soát đồng thời có giới hạn (Bounded Concurrency Gate) cho suy luận OCR.
    Bảo vệ CPU/RAM khỏi tình trạng quá tải bằng BoundedSemaphore và timeout có thể cấu hình.
    """

    def __init__(
        self,
        limit: int | None = None,
        timeout: float | None = None,
        retry_after: int | None = None,
    ) -> None:
        import os

        default_timeout = float(os.getenv("PARKING_OCR_QUEUE_TIMEOUT", "2.0"))

        self.limit = (
            limit if limit is not None else int(settings.PARKING_OCR_CONCURRENCY_LIMIT)
        )
        self.timeout = (
            timeout
            if timeout is not None
            else float(
                settings.PARKING_OCR_QUEUE_TIMEOUT
                if settings.PARKING_OCR_QUEUE_TIMEOUT is not None
                else default_timeout
            )
        )
        self.retry_after = (
            retry_after
            if retry_after is not None
            else int(settings.PARKING_OCR_RETRY_AFTER)
        )
        self._semaphore = threading.BoundedSemaphore(self.limit)

    @contextmanager
    def acquire(self, timeout: float | None = None) -> Generator[None]:
        wait_time = self.timeout if timeout is None else timeout
        acquired = self._semaphore.acquire(timeout=wait_time)
        if not acquired:
            logger.warning(
                "OCRConcurrencyGate queue timeout exceeded (%.2fs, limit=%d). "
                "Returning HTTP 503 Back-pressure.",
                wait_time,
                self.limit,
            )
            exc = BusinessAPIException(
                code="PROP-4.5.1-P15",
                message=ALL_MESSAGES.get(
                    "PROP-4.5.1-P15",
                    "Hệ thống nhận diện biển số xe đang quá tải, vui lòng thử lại sau.",
                ),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={"Retry-After": str(self.retry_after)},
                wait=self.retry_after,
            )
            raise exc

        try:
            yield
        finally:
            self._semaphore.release()


_GLOBAL_OCR_GATE: OCRConcurrencyGate | None = None
_GATE_LOCK = threading.Lock()


def get_ocr_concurrency_gate() -> OCRConcurrencyGate:
    """Lấy hoặc khởi tạo singleton OCRConcurrencyGate theo cấu hình settings."""
    global _GLOBAL_OCR_GATE
    if _GLOBAL_OCR_GATE is None:
        with _GATE_LOCK:
            if _GLOBAL_OCR_GATE is None:
                _GLOBAL_OCR_GATE = OCRConcurrencyGate()
    return _GLOBAL_OCR_GATE


def set_ocr_concurrency_gate(gate: OCRConcurrencyGate | None) -> None:
    """Hỗ trợ ghi đè gate trong test suite."""
    global _GLOBAL_OCR_GATE
    with _GATE_LOCK:
        _GLOBAL_OCR_GATE = gate


class ImageDecodeConcurrencyGate:
    """
    Cổng kiểm soát đồng thời giải mã ảnh kích thước lớn (12MP).
    Bảo vệ CPU L2/L3 cache và băng thông RAM khỏi tranh chấp khi burst ảnh lớn ập đến.
    """

    def __init__(self, limit: int = 4, timeout: float = 3.0) -> None:
        self.limit = limit
        self.timeout = timeout
        self._semaphore = threading.BoundedSemaphore(self.limit)

    @contextmanager
    def acquire(self, timeout: float | None = None) -> Generator[None]:
        wait_time = self.timeout if timeout is None else timeout
        acquired = self._semaphore.acquire(timeout=wait_time)
        if not acquired:
            logger.warning(
                "ImageDecodeConcurrencyGate queue timeout exceeded (%.2fs, limit=%d). "
                "Returning HTTP 503 Back-pressure.",
                wait_time,
                self.limit,
            )
            raise BusinessAPIException(
                code="PROP-4.5.1-P15",
                message=ALL_MESSAGES.get(
                    "PROP-4.5.1-P15",
                    "Hệ thống nhận diện biển số xe đang quá tải, vui lòng thử lại sau.",
                ),
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={"Retry-After": "3"},
                wait=3,
            )
        try:
            yield
        finally:
            self._semaphore.release()


_GLOBAL_IMAGE_DECODE_GATE: ImageDecodeConcurrencyGate | None = None
_DECODE_GATE_LOCK = threading.Lock()


def get_image_decode_concurrency_gate() -> ImageDecodeConcurrencyGate:
    """Lấy hoặc khởi tạo singleton ImageDecodeConcurrencyGate."""
    global _GLOBAL_IMAGE_DECODE_GATE
    if _GLOBAL_IMAGE_DECODE_GATE is None:
        with _DECODE_GATE_LOCK:
            if _GLOBAL_IMAGE_DECODE_GATE is None:
                _GLOBAL_IMAGE_DECODE_GATE = ImageDecodeConcurrencyGate()
    return _GLOBAL_IMAGE_DECODE_GATE


def set_image_decode_concurrency_gate(gate: ImageDecodeConcurrencyGate | None) -> None:
    """Hỗ trợ ghi đè decode gate trong test suite."""
    global _GLOBAL_IMAGE_DECODE_GATE
    with _DECODE_GATE_LOCK:
        _GLOBAL_IMAGE_DECODE_GATE = gate
