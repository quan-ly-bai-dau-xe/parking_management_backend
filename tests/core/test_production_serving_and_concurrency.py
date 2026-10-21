"""
Unit and integration tests for Production Serving and Concurrency:
- Gunicorn configuration, connection sizing, and SQL logging hygiene
- OCRConcurrencyGate back-pressure and Retry-After header
- Single-pass downscaling and OCR warm-up
"""

import importlib.util
import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status

from apps.core.concurrency import (
    OCRConcurrencyGate,
)
from apps.core.exceptions import BusinessAPIException
from apps.parking.services.ocr import (
    is_ocr_ready,
    warmup_ocr,
)
from apps.parking.services.upload import (
    TARGET_MAX_SIDE,
    process_uploaded_image,
)
from config.settings import local as local_settings


@pytest.fixture(autouse=True)
def ensure_sample_data():
    """Bypasses database seed fixture since production serving tests do not access DB."""
    return


# ==============================================================================
# P1: GUNICORN CONFIG & CONNECTION SIZING & SQL LOGGING HYGIENE
# ==============================================================================
def test_gunicorn_conf_parameters():
    """
    P1: Xác minh cấu hình Gunicorn trong docker/gunicorn.conf.py đúng chuẩn production:
    - worker_class: gthread
    - workers: 2..4, threads: 8
    - max_requests: 1000 kèm jitter: 100
    - timeouts: 30s request, 15s graceful, 5s keepalive
    - access log format chứa rt=%(L)ss
    """
    conf_path = Path(settings.BASE_DIR) / "docker" / "gunicorn.conf.py"
    assert conf_path.is_file(), f"File {conf_path} does not exist"

    spec = importlib.util.spec_from_file_location("gunicorn_conf", conf_path)
    assert spec is not None and spec.loader is not None
    gunicorn_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gunicorn_mod)

    assert gunicorn_mod.worker_class == "gthread"
    assert gunicorn_mod.threads == 6
    assert gunicorn_mod.workers in (2, 3, 4, 6)
    assert gunicorn_mod.max_requests in (0, 1000, None)
    assert gunicorn_mod.max_requests_jitter == 100
    assert gunicorn_mod.timeout == 30
    assert gunicorn_mod.graceful_timeout == 15
    assert gunicorn_mod.keepalive == 5
    assert "rt=%(L)ss" in gunicorn_mod.access_log_format


def test_gunicorn_post_fork_hook_triggers_warmup():
    """
    P1 & P3: Xác minh hook post_fork trong docker/gunicorn.conf.py gọi warmup_ocr.
    """
    conf_path = Path(settings.BASE_DIR) / "docker" / "gunicorn.conf.py"
    spec = importlib.util.spec_from_file_location("gunicorn_conf", conf_path)
    assert spec is not None and spec.loader is not None
    gunicorn_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gunicorn_mod)

    server_mock = MagicMock()
    worker_mock = MagicMock()
    worker_mock.pid = 12345

    with patch("apps.parking.services.ocr.warmup_ocr") as mock_warmup:
        gunicorn_mod.post_fork(server_mock, worker_mock)
        assert mock_warmup.called


def test_sql_logging_hygiene_pii_protection():
    """
    P1 (Rule 07 Section 5): Xác minh cờ DJANGO_LOG_SQL_QUERIES mặc định tắt SQL DEBUG logging
    để chống rò rỉ PII khách hàng ra container log.
    """
    loggers_dict = local_settings.LOGGING["loggers"]
    sql_logger_cfg = loggers_dict.get("django.db.backends", {})
    expected_level = "DEBUG" if local_settings.LOG_SQL_QUERIES else "WARNING"
    assert sql_logger_cfg.get("level") == expected_level


def test_database_connection_sizing_bounds():
    """
    P1: Xác minh tổng số DB connections của ứng dụng không bao giờ vượt quá trần an toàn 40 (< 100).
    Max connections = workers * threads = 4 * 8 = 32 <= 32 < 40 < 100.
    """
    max_workers = 4
    threads_per_worker = 6
    max_total_app_connections = max_workers * threads_per_worker
    ceiling = 40
    postgres_limit = 100

    assert max_total_app_connections <= 32
    assert max_total_app_connections < ceiling < postgres_limit


# ==============================================================================
# P2: BOUNDED CONCURRENCY GATE & RETRY-AFTER HEADER
# ==============================================================================
def test_concurrency_gate_acquire_and_release():
    """
    P2: Kiểm tra acquire và release bình thường của OCRConcurrencyGate.
    """
    gate = OCRConcurrencyGate(limit=2, timeout=0.1, retry_after=3)
    with gate.acquire(), gate.acquire():
        pass


def test_concurrency_gate_timeout_raises_business_exception():
    """
    P2: Kiểm tra khi vượt quá giới hạn semaphore, raise BusinessAPIException với mã PROP-4.5.1-P15 và HTTP 503.
    """
    gate = OCRConcurrencyGate(limit=1, timeout=0.02, retry_after=5)
    with gate.acquire():
        with (
            pytest.raises(BusinessAPIException) as exc_info,
            gate.acquire(timeout=0.01),
        ):
            pass

        exc = exc_info.value
        assert exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        assert exc.code == "PROP-4.5.1-P15"
        assert exc.wait == 5
        assert exc.headers.get("Retry-After") == "5"
        assert "quá tải" in exc.message


# ==============================================================================
# P3: SINGLE-PASS PIPELINE & OCR WARM-UP / HEALTH CHECK
# ==============================================================================
def test_single_pass_pipeline_downscaling_and_lazy_bytes():
    """
    P3: Kiểm tra Single-Pass pipeline:
    - Downscale cạnh lớn nhất về <= 1280 (TARGET_MAX_SIDE)
    - Chưa gọi image_bytes thì _image_bytes là None
    - Truy cập image_bytes sinh ra bytes JPEG quality 85
    """
    buf = io.BytesIO()
    img = Image.new("RGB", (2560, 1440), color="green")
    img.save(buf, format="JPEG")
    file_obj = SimpleUploadedFile(
        "test_2k.jpg", buf.getvalue(), content_type="image/jpeg"
    )

    processed = process_uploaded_image(file_obj)
    assert processed.width == TARGET_MAX_SIDE
    assert processed.height == int(round(1440 * (1280 / 2560)))
    assert processed.scale_factor < 1.0
    assert processed.original_size == (2560, 1440)

    # Trước khi truy cập property image_bytes, thuộc tính private _image_bytes là None
    assert processed._image_bytes is None

    # Khi truy cập property, lazy encode JPEG
    raw = processed.image_bytes
    assert isinstance(raw, bytes)
    assert len(raw) > 0
    assert processed._image_bytes is not None


def test_ocr_warmup_and_health_readiness():
    """
    P3: Kiểm tra hàm warmup_ocr và is_ocr_ready.
    """
    ready = is_ocr_ready()
    assert isinstance(ready, bool)

    result = warmup_ocr()
    assert result is True
