"""
Boundary empirical stress tests for Core Image Pipeline and Health APIs:
- Image Pipeline: single-pass decode, EXIF orientation 6 transpose, 12MP downscale to <= 1280px.
- Plate Scans 422: zero residual garbage files in storage root.
- OCR Singleton: thread-safe instance reuse, warmup idempotency, multithread inference.
- Health Check: JSON payload contract including boolean ocr_ready flag.
"""

import concurrent.futures
import io
import statistics
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.exceptions import BusinessAPIException
from apps.parking.services.ocr import (
    DummyPlateRecognizer,
    get_plate_recognizer,
    is_ocr_ready,
    set_global_recognizer,
    warmup_ocr,
)
from apps.parking.services.upload import (
    TARGET_MAX_SIDE,
    process_uploaded_image,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def test_employee() -> Account:
    """Fixture creating an authorized staff member for API testing."""
    user, _ = Account.objects.get_or_create(
        email="verification_m1_2_emp@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return user


# ==============================================================================
# 1. EXIF ORIENTATION 6 EMPIRICAL STRESS TEST
# ==============================================================================
class TestExifOrientation6Stress:
    """Empirical verification that phone images with orientation 6 are upright."""

    def test_exif_orientation_6_auto_transposes_upright(self):
        """
        Create a landscape JPEG (1600x1200) with EXIF Orientation = 6 (rotated 90 CW).
        Verifies that process_uploaded_image transposes the dimensions upright (1200x1600)
        and downscales so the longest side is <= 1280 (width=960, height=1280).
        """
        raw_img = Image.new("RGB", (1600, 1200), color=(50, 100, 150))
        exif_dict = raw_img.getexif()
        exif_dict[0x0112] = 6  # Orientation 6
        buf = io.BytesIO()
        raw_img.save(buf, format="JPEG", exif=exif_dict)

        upload_file = SimpleUploadedFile(
            "camera_rotated.jpg", buf.getvalue(), content_type="image/jpeg"
        )
        processed = process_uploaded_image(upload_file)

        # Original dimensions before transpose
        assert processed.original_size == (1600, 1200)
        # Transposed to 1200x1600, then downscaled by 1280/1600 = 0.8
        assert processed.width == 960
        assert processed.height == 1280
        assert max(processed.width, processed.height) <= TARGET_MAX_SIDE
        assert processed.pil_image.size == (960, 1280)

        # Encoded image has stripped metadata and is physically upright
        saved_img = Image.open(io.BytesIO(processed.image_bytes))
        assert saved_img.size == (960, 1280)
        assert saved_img.getexif().get(0x0112) is None

    def test_exif_orientation_6_aspect_ratio_and_resampling(self):
        """
        Test smaller landscape image (800x600) with orientation 6:
        Transposed size should be exactly (600, 800) with scale factor 1.0 (no downscale needed).
        """
        raw_img = Image.new("RGB", (800, 600), color=(80, 120, 200))
        exif_dict = raw_img.getexif()
        exif_dict[0x0112] = 6
        buf = io.BytesIO()
        raw_img.save(buf, format="JPEG", exif=exif_dict)

        upload_file = SimpleUploadedFile(
            "phone_800x600.jpg", buf.getvalue(), content_type="image/jpeg"
        )
        processed = process_uploaded_image(upload_file)

        assert processed.width == 600
        assert processed.height == 800
        assert processed.scale_factor == 1.0
        assert processed.pil_image.size == (600, 800)

    @pytest.mark.parametrize("orientation_tag", [1, 3, 6, 8])
    def test_multiple_exif_orientations_processed_safely(self, orientation_tag: int):
        """Verify orientations 1 (normal), 3 (180 deg), 6 (90 CW), 8 (270 CW) process without crash."""
        raw_img = Image.new("RGB", (640, 480), color=(100, 100, 100))
        exif_dict = raw_img.getexif()
        exif_dict[0x0112] = orientation_tag
        buf = io.BytesIO()
        raw_img.save(buf, format="JPEG", exif=exif_dict)

        upload_file = SimpleUploadedFile(
            f"orient_{orientation_tag}.jpg",
            buf.getvalue(),
            content_type="image/jpeg",
        )
        processed = process_uploaded_image(upload_file)
        assert processed.pil_image is not None
        assert processed.format == "JPEG"
        if orientation_tag in (6, 8):
            assert processed.width == 480
            assert processed.height == 640
        else:
            assert processed.width == 640
            assert processed.height == 480


# ==============================================================================
# 2. LARGE 12MP IMAGE SINGLE-PASS DECODE & DOWNSCALE LATENCY BENCHMARK
# ==============================================================================
class TestLargeImageDecodeAndLatency:
    """Empirical verification of 12MP processing and single-pass latency goals."""

    def test_12mp_single_pass_downscaling_functional(self):
        """
        Generate a 12MP (4000x3000) image.
        Deterministic functional verification:
        - Downscaled longest side is <= 1280 (target max side).
        - Dimensions become exactly 1280 x 960.
        - Preserves RGB channels and valid byte representation.
        """
        raw_img = Image.new("RGB", (4000, 3000), color=(100, 150, 200))
        buf = io.BytesIO()
        raw_img.save(buf, format="JPEG", quality=85)
        raw_bytes = buf.getvalue()

        upload_file = SimpleUploadedFile(
            "photo_12mp.jpg", raw_bytes, content_type="image/jpeg"
        )
        processed = process_uploaded_image(upload_file)

        assert processed.width == 1280
        assert processed.height == 960
        assert max(processed.width, processed.height) <= TARGET_MAX_SIDE
        assert processed.pil_image.mode == "RGB"

    def test_1080p_single_pass_downscaling_functional(self):
        """
        Generate a 1080p (1920x1080) image.
        Deterministic functional verification:
        - Downscaled to exactly 1280 x 720.
        - Longest side <= 1280 px.
        - Preserves RGB channels.
        """
        raw_img = Image.new("RGB", (1920, 1080), color=(120, 80, 220))
        buf = io.BytesIO()
        raw_img.save(buf, format="JPEG", quality=85)
        raw_bytes = buf.getvalue()

        upload_file = SimpleUploadedFile(
            "photo_1080p.jpg", raw_bytes, content_type="image/jpeg"
        )
        processed = process_uploaded_image(upload_file)

        assert processed.width == 1280
        assert processed.height == 720
        assert max(processed.width, processed.height) <= TARGET_MAX_SIDE
        assert processed.pil_image.mode == "RGB"

    @pytest.mark.perf
    def test_12mp_single_pass_downscaling_relative_speedup(self):
        """
        Measure single-pass draft mode speedup vs naive full decode on 12MP.
        Evaluates relative ratio in same process rather than wall-clock milliseconds.
        Target: T_optimized / T_naive <= 0.70 (>= 30% latency reduction).
        """
        raw_img = Image.new("RGB", (4000, 3000), color=(100, 150, 200))
        buf = io.BytesIO()
        raw_img.save(buf, format="JPEG", quality=85)
        raw_bytes = buf.getvalue()

        # Naive baseline: Full decode and separate resize
        naive_times: list[float] = []
        for _ in range(5):
            t0 = time.perf_counter()
            with Image.open(io.BytesIO(raw_bytes)) as img_naive:
                img_naive.load()
                _ = img_naive.resize((1280, 960), Image.Resampling.BILINEAR)
            naive_times.append(time.perf_counter() - t0)
        t_naive = statistics.median(naive_times)

        # Optimized: Single-pass draft decode
        opt_times: list[float] = []
        for _ in range(5):
            upload_file = SimpleUploadedFile(
                "photo_12mp.jpg", raw_bytes, content_type="image/jpeg"
            )
            t0 = time.perf_counter()
            _ = process_uploaded_image(upload_file)
            opt_times.append(time.perf_counter() - t0)
        t_opt = statistics.median(opt_times)

        speedup_ratio = t_opt / t_naive
        assert speedup_ratio <= 0.70, (
            f"12MP draft decode ({t_opt * 1000:.1f}ms) did not achieve >= 30% speedup "
            f"over naive decode ({t_naive * 1000:.1f}ms), ratio: {speedup_ratio:.3f}"
        )

    @pytest.mark.perf
    def test_1080p_single_pass_downscaling_relative_speedup(self):
        """
        Measure 1080p downscaling overhead vs naive baseline.
        Since 1920x1080 to 1280x720 is a 1.5x downscale (below Pillow's 2x integer IDCT draft threshold),
        draft mode decodes at 1:1 and resizes. Verifies processing pipeline overhead is <= 10%
        over raw naive decode (T_optimized / T_naive <= 1.10).
        """
        raw_img = Image.new("RGB", (1920, 1080), color=(120, 80, 220))
        buf = io.BytesIO()
        raw_img.save(buf, format="JPEG", quality=85)
        raw_bytes = buf.getvalue()

        # Naive baseline
        naive_times: list[float] = []
        for _ in range(5):
            t0 = time.perf_counter()
            with Image.open(io.BytesIO(raw_bytes)) as img_naive:
                img_naive.load()
                _ = img_naive.resize((1280, 720), Image.Resampling.BILINEAR)
            naive_times.append(time.perf_counter() - t0)
        t_naive = statistics.median(naive_times)

        # Optimized
        opt_times: list[float] = []
        for _ in range(5):
            upload_file = SimpleUploadedFile(
                "photo_1080p.jpg", raw_bytes, content_type="image/jpeg"
            )
            t0 = time.perf_counter()
            _ = process_uploaded_image(upload_file)
            opt_times.append(time.perf_counter() - t0)
        t_opt = statistics.median(opt_times)

        speedup_ratio = t_opt / t_naive
        assert speedup_ratio <= 1.10, (
            f"1080p draft decode ({t_opt * 1000:.1f}ms) exceeded overhead bound "
            f"over naive decode ({t_naive * 1000:.1f}ms), ratio: {speedup_ratio:.3f}"
        )

    def test_oversized_dimension_and_stream_guards(self):
        """
        Verify security boundaries:
        - Dimension > 4096 px is rejected with HTTP 400 PROP-4.5.1-P05.
        - Stream with declared size > 5MB rejected with HTTP 400 PROP-4.5.1-P03.
        """
        # Exceeds max dimension 4096
        oversized = Image.new("RGB", (4097, 100), color="red")
        buf = io.BytesIO()
        oversized.save(buf, format="JPEG")
        file_obj = SimpleUploadedFile(
            "too_wide.jpg", buf.getvalue(), content_type="image/jpeg"
        )
        with pytest.raises(BusinessAPIException) as exc_info:
            process_uploaded_image(file_obj)
        assert exc_info.value.code == "PROP-4.5.1-P05"

        # Declared size exceeds limit
        file_oversized = SimpleUploadedFile(
            "fake_big.jpg", b"\xff\xd8\xff" + b"\x00" * 100, content_type="image/jpeg"
        )
        file_oversized.size = 6 * 1024 * 1024  # 6 MB declared
        with pytest.raises(BusinessAPIException) as exc_info2:
            process_uploaded_image(file_oversized)
        assert exc_info2.value.code == "PROP-4.5.1-P03"


# ==============================================================================
# 3. HTTP 422 RESIDUAL ARTIFACTS TEST (0 BYTES GARBAGE)
# ==============================================================================
class TestPlateScans422ZeroResidualArtifacts:
    """Empirical verification that 422 unrecognized plate scans leave zero disk garbage."""

    def test_unrecognized_plate_422_leaves_zero_bytes_in_media_root(
        self, test_employee: Account
    ):
        """
        Post an image where OCR detects no plate (HTTP 422).
        Prove that MEDIA_ROOT contains 0 new files and 0 bytes added.
        """
        client = APIClient()
        client.force_authenticate(user=test_employee)

        # Force dummy recognizer returning empty candidates
        dummy = DummyPlateRecognizer(preset_candidates=[])
        set_global_recognizer(dummy)

        media_path = Path(settings.MEDIA_ROOT)
        media_path.mkdir(parents=True, exist_ok=True)
        files_before = set(media_path.rglob("*"))
        bytes_before = sum(f.stat().st_size for f in files_before if f.is_file())

        buf = io.BytesIO()
        Image.new("RGB", (320, 240), color="white").save(buf, format="JPEG")
        file_obj = SimpleUploadedFile(
            "blank.jpg", buf.getvalue(), content_type="image/jpeg"
        )

        response = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": file_obj},
            format="multipart",
        )

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        assert response.data["code"] == "PROP-4.5.1-P06"

        files_after = set(media_path.rglob("*"))
        bytes_after = sum(f.stat().st_size for f in files_after if f.is_file())

        new_files = [f for f in (files_after - files_before) if f.is_file()]
        bytes_diff = bytes_after - bytes_before

        assert len(new_files) == 0, f"Found unexpected residual files: {new_files}"
        assert bytes_diff == 0, f"Detected {bytes_diff} bytes garbage in media root"

        set_global_recognizer(None)

    def test_burst_422_requests_leave_zero_garbage_files(self, test_employee: Account):
        """Send 10 consecutive 422 scan requests; verify zero disk accumulation."""
        client = APIClient()
        client.force_authenticate(user=test_employee)

        dummy = DummyPlateRecognizer(preset_candidates=[])
        set_global_recognizer(dummy)

        media_path = Path(settings.MEDIA_ROOT)
        media_path.mkdir(parents=True, exist_ok=True)
        files_before = set(media_path.rglob("*"))

        for idx in range(10):
            buf = io.BytesIO()
            Image.new("RGB", (200 + idx * 10, 150), color="gray").save(
                buf, format="JPEG"
            )
            file_obj = SimpleUploadedFile(
                f"unrecognized_{idx}.jpg", buf.getvalue(), content_type="image/jpeg"
            )
            resp = client.post(
                "/api/v1/parking/plate-scans/",
                {"image": file_obj},
                format="multipart",
            )
            assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

        files_after = set(media_path.rglob("*"))
        leftover_files = [f for f in (files_after - files_before) if f.is_file()]
        assert len(leftover_files) == 0, f"Leftover files after burst: {leftover_files}"

        set_global_recognizer(None)


# ==============================================================================
# 4. OCR SINGLETON THREAD-SAFETY & WARMUP
# ==============================================================================
class TestOcrSingletonAndWarmupStress:
    """Empirical verification of thread-safe singleton, warmup, and concurrency."""

    def test_ocr_singleton_same_instance_multithreaded(self):
        """Verify that get_plate_recognizer called from 16 concurrent threads returns the exact same object."""
        set_global_recognizer(None)

        def fetch_instance(_: int) -> int:
            rec = get_plate_recognizer()
            return id(rec)

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            ids = list(executor.map(fetch_instance, range(32)))

        unique_ids = set(ids)
        assert len(unique_ids) == 1, (
            f"Expected 1 singleton instance, got {len(unique_ids)}"
        )

    def test_ocr_warmup_execution_and_idempotence(self):
        """Verify warmup_ocr is idempotent and safely sets readiness flag."""
        ready_initial = is_ocr_ready()
        assert isinstance(ready_initial, bool)

        result1 = warmup_ocr()
        assert result1 is True
        assert is_ocr_ready() is True

        result2 = warmup_ocr()
        assert result2 is True
        assert is_ocr_ready() is True

    def test_ocr_concurrent_multithreaded_inference(self):
        """Stress-test 16 threads calling recognizer.recognize simultaneously with zero crashes."""
        rec = get_plate_recognizer()
        test_img = Image.new("RGB", (320, 240), color="white")

        errors: list[str] = []

        def worker(thread_idx: int) -> bool:
            try:
                res = rec.recognize(test_img)
                return res is not None
            except Exception as exc:
                errors.append(f"Thread {thread_idx} failed: {exc}")
                return False

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            outcomes = list(executor.map(worker, range(32)))

        assert len(errors) == 0, f"Multithreaded OCR errors: {errors}"
        assert all(outcomes)


# ==============================================================================
# 5. HEALTH CHECK ENDPOINT JSON CONTRACT
# ==============================================================================
class TestHealthCheckJsonContract:
    """Empirical verification of /api/health/ response schema."""

    def test_health_check_payload_structure(self):
        """Verify /api/health/ returns HTTP 200 with status, database, and ocr_ready boolean."""
        client = APIClient()
        response = client.get("/api/health/")

        assert response.status_code == status.HTTP_200_OK
        data: dict[str, Any] = response.json()

        assert "status" in data
        assert "database" in data
        assert "ocr_ready" in data

        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert isinstance(data["ocr_ready"], bool)
        assert data["ocr_ready"] is True

    def test_health_check_database_down_reflects_503_and_ocr_ready(self):
        """Verify /api/health/ returns HTTP 503 when DB fails, while preserving ocr_ready flag."""
        client = APIClient()
        with patch(
            "django.db.connection.cursor",
            side_effect=DatabaseError("Simulated DB connection failure"),
        ):
            response = client.get("/api/health/")

        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data: dict[str, Any] = response.json()

        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
        assert isinstance(data["ocr_ready"], bool)
        # Raw internal exception text must not leak to client
        assert "Simulated DB connection failure" not in response.content.decode("utf-8")
