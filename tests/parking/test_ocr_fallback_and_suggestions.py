"""
Empirical Boundary & Performance Stress Tests for OCR Fallback and Trigram Suggestions:
1. Fallback Detection Retry (A4) latency penalty and execution verification.
2. Dual-OCR Ensemble fault tolerance against empty crops, abnormal sizes, corrupted images.
3. Trigram Plate Suggestions (A5) boundary limits (0, 1, 5 -> max 3) and DB write-safety.
4. FastAlprPlateRecognizer Singleton thread-safety under concurrent multi-threaded execution.
"""

from __future__ import annotations

import concurrent.futures
import time
from unittest.mock import MagicMock

import numpy as np
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test.utils import CaptureQueriesContext
from PIL import Image

from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer
from apps.parking.models import PlateBlacklist
from apps.parking.services.ocr import (
    BoundingBox,
    FastAlprPlateRecognizer,
    PlateScanResult,
    get_plate_recognizer,
    set_global_recognizer,
)
from apps.parking.services.plate_correction import (
    ReviewReasonCode,
    _levenshtein_distance,
    evaluate_review_policy,
    get_plate_suggestions,
)
from apps.parking.services.upload import process_uploaded_image
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


class TestFallbackDetectionRetryBoundary:
    """
    Empirical tests for Fallback Detection Retry (Requirement A4).
    Verifies:
    1. Zero latency penalty (0.00 ms) on images where detector succeeds on first pass.
    2. Fallback detector is ONLY invoked when first pass detector returns 0 candidates.
    3. Proper flag propagation (`used_detection_fallback=True`) and review policy tagging.
    """

    def test_fallback_not_invoked_when_first_pass_succeeds(self) -> None:
        """Prove fallback detector is bypassed completely when primary detector succeeds."""
        recognizer = FastAlprPlateRecognizer()

        mock_bbox = MagicMock()
        mock_bbox.x1 = 10
        mock_bbox.y1 = 10
        mock_bbox.x2 = 120
        mock_bbox.y2 = 60
        mock_det = MagicMock()
        mock_det.bounding_box = mock_bbox

        mock_primary = MagicMock()
        mock_primary.predict.return_value = [mock_det]

        mock_fallback = MagicMock()

        recognizer._detector = mock_primary
        recognizer._fallback_detector = mock_fallback

        dummy_img = Image.new("RGB", (320, 240), color="white")
        result = recognizer.recognize(dummy_img)

        # Assert primary was called exactly once
        assert mock_primary.predict.call_count == 1
        # Assert fallback was NEVER called
        assert mock_fallback.predict.call_count == 0
        # Assert fallback flag is False
        assert result.used_detection_fallback is False

    def test_fallback_triggered_when_first_pass_empty(self) -> None:
        """Prove fallback detector is called when primary detector finds 0 plates."""
        recognizer = FastAlprPlateRecognizer()

        mock_primary = MagicMock()
        mock_primary.predict.return_value = []

        mock_bbox = MagicMock()
        mock_bbox.x1 = 20
        mock_bbox.y1 = 20
        mock_bbox.x2 = 140
        mock_bbox.y2 = 70
        mock_fallback_det = MagicMock()
        mock_fallback_det.bounding_box = mock_bbox

        mock_fallback = MagicMock()
        mock_fallback.predict.return_value = [mock_fallback_det]

        recognizer._detector = mock_primary
        recognizer._fallback_detector = mock_fallback

        dummy_img = Image.new("RGB", (320, 240), color="white")
        result = recognizer.recognize(dummy_img)

        # Assert both detectors were called
        assert mock_primary.predict.call_count == 1
        assert mock_fallback.predict.call_count == 1
        # Assert fallback flag is True
        assert result.used_detection_fallback is True

        # Assert review policy correctly flags NO_DETECTION_RETRY
        review_status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=95.0,
            threshold=85.0,
            is_valid_format=True,
            used_detection_fallback=result.used_detection_fallback,
        )
        assert review_status == "NEEDS_REVIEW"
        assert ReviewReasonCode.NO_DETECTION_RETRY in reasons

    def test_fallback_zero_overhead_deterministic(self) -> None:
        """
        Deterministic verification that fallback detector introduces zero computational overhead
        when primary detector yields valid detections:
        - Primary detector returns detection.
        - Fallback detector is configured with mock.
        - Verifies fallback detector predict is never invoked.
        """
        recognizer = FastAlprPlateRecognizer()

        mock_bbox = MagicMock()
        mock_bbox.x1, mock_bbox.y1, mock_bbox.x2, mock_bbox.y2 = 10, 10, 60, 40
        mock_det = MagicMock(bounding_box=mock_bbox)
        mock_primary = MagicMock(predict=MagicMock(return_value=[mock_det]))

        mock_fallback = MagicMock()
        recognizer._detector = mock_primary
        recognizer._fallback_detector = mock_fallback

        mock_ocr = MagicMock(
            run_one=MagicMock(
                return_value=MagicMock(
                    plate="51K99214", char_probs=np.array([0.98] * 8)
                )
            )
        )
        recognizer._ocr_cct = mock_ocr
        recognizer._ocr_mv2 = mock_ocr

        dummy_img = Image.new("RGB", (100, 100), color="white")
        res = recognizer.recognize(dummy_img)

        assert res.used_detection_fallback is False
        mock_primary.predict.assert_called_once()
        mock_fallback.predict.assert_not_called()

    @pytest.mark.perf
    def test_empirical_latency_penalty_on_first_pass_is_zero(self) -> None:
        """
        Empirically measure latency on first-pass success:
        Compare 200 interleaved runs with fallback detector present vs fallback detector = None.
        Prove the latency penalty on first-pass success is negligible.
        Gated under @pytest.mark.perf.
        """
        recognizer = FastAlprPlateRecognizer()

        mock_bbox = MagicMock()
        mock_bbox.x1, mock_bbox.y1, mock_bbox.x2, mock_bbox.y2 = 10, 10, 60, 40
        mock_det = MagicMock(bounding_box=mock_bbox)
        mock_primary = MagicMock(predict=MagicMock(return_value=[mock_det]))
        real_fallback = recognizer._fallback_detector

        # Mock OCR prediction to eliminate ONNX inference CPU noise from measurement
        mock_ocr = MagicMock(
            run_one=MagicMock(
                return_value=MagicMock(
                    plate="51K99214", char_probs=np.array([0.98] * 8)
                )
            )
        )
        recognizer._detector = mock_primary
        recognizer._ocr_cct = mock_ocr
        recognizer._ocr_mv2 = mock_ocr

        dummy_img = Image.new("RGB", (100, 100), color="white")

        # Interleaved A/B measurement
        times_with_fallback: list[float] = []
        times_without_fallback: list[float] = []

        for _ in range(100):
            # A: with fallback configured
            recognizer._fallback_detector = real_fallback
            t0 = time.perf_counter()
            res_a = recognizer.recognize(dummy_img)
            times_with_fallback.append((time.perf_counter() - t0) * 1000.0)
            assert res_a.used_detection_fallback is False

            # B: without fallback configured
            recognizer._fallback_detector = None
            t1 = time.perf_counter()
            res_b = recognizer.recognize(dummy_img)
            times_without_fallback.append((time.perf_counter() - t1) * 1000.0)
            assert res_b.used_detection_fallback is False

        avg_with = float(np.mean(times_with_fallback))
        avg_without = float(np.mean(times_without_fallback))
        diff_ms = abs(avg_with - avg_without)

        # Overhead of `if not detections and fallback:` is negligible (< 2.5 ms under coverage tracing)
        assert diff_ms <= 2.5, (
            f"Latency penalty on first pass should be <= 2.5 ms under coverage tracing, observed diff: {diff_ms:.4f} ms"
        )


class TestDualOcrEnsembleFaultTolerance:
    """
    Stress-testing fault tolerance of the Dual-OCR Ensemble (CCT-xs-v2 + Mobile-ViT-v2).
    Verifies resilience against:
    - Empty crops (0x0, x2 <= x1, y2 <= y1)
    - Abnormal crop dimensions (1x1, 1x500, 500x1, 2x1000, 1000x2)
    - Corrupted, non-image, and truncated bytes
    - Degenerate uniform images (solid black, solid white)
    - Null / empty char_probs arrays without numpy crashes
    """

    def test_empty_crops_gracefully_ignored(self) -> None:
        """Prove that empty bounding boxes or 0-area crops are discarded without error."""
        recognizer = FastAlprPlateRecognizer()

        # Detector returns boxes with x2 <= x1 or y2 <= y1 or out of bounds
        bad_boxes = [
            MagicMock(bounding_box=BoundingBox(x1=50, y1=50, x2=50, y2=50)),  # 0 area
            MagicMock(bounding_box=BoundingBox(x1=80, y1=50, x2=40, y2=50)),  # x2 < x1
            MagicMock(bounding_box=BoundingBox(x1=50, y1=80, x2=50, y2=40)),  # y2 < y1
            MagicMock(
                bounding_box=BoundingBox(x1=-10, y1=-10, x2=-5, y2=-5)
            ),  # negative
        ]
        mock_detector = MagicMock()
        mock_detector.predict.return_value = bad_boxes

        recognizer._detector = mock_detector
        dummy_img = Image.new("RGB", (200, 200), color="gray")

        result = recognizer.recognize(dummy_img)
        assert result.candidates == []
        assert result.best_candidate is None

    def test_abnormal_crop_dimensions_direct_ocr(self) -> None:
        """
        Feed degenerate aspect-ratio crops directly into both CCT and MV2 OCR models.
        Must execute without raising unhandled exceptions.
        """
        recognizer = FastAlprPlateRecognizer()
        assert recognizer._ocr_cct is not None
        assert recognizer._ocr_mv2 is not None

        abnormal_crops = [
            np.zeros((1, 1, 3), dtype=np.uint8),
            np.zeros((1, 400, 3), dtype=np.uint8),
            np.zeros((400, 1, 3), dtype=np.uint8),
            np.zeros((2, 800, 3), dtype=np.uint8),
            np.zeros((800, 2, 3), dtype=np.uint8),
        ]

        import cv2

        for crop in abnormal_crops:
            crop_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

            # Neither model should crash on extreme dimensions
            pred_cct = recognizer._ocr_cct.run_one(crop_rgb, return_confidence=True)
            pred_mv2 = recognizer._ocr_mv2.run_one(crop_gray, return_confidence=True)

            assert isinstance(pred_cct.plate, str)
            assert isinstance(pred_mv2.plate, str)

    def test_corrupt_and_truncated_image_bytes(self) -> None:
        """Ensure corrupted and non-image payloads are rejected safely by the upload pipeline."""
        corrupt_payloads = [
            b"",  # Empty
            b"\x00" * 1024,  # Null bytes
            b"GARBAGE_PAYLOAD_NOT_IMAGE",  # Random text
            b"\xff\xd8\xff\xe0" + b"\x00" * 20,  # Truncated JPEG header
        ]

        for payload in corrupt_payloads:
            uploaded = SimpleUploadedFile("bad.jpg", payload, content_type="image/jpeg")
            with pytest.raises(BusinessAPIException) as exc_info:
                process_uploaded_image(uploaded)
            assert exc_info.value.status_code == 400
            assert exc_info.value.code in (
                "PROP-4.5.1-P02",
                "PROP-4.5.1-P04",
                "PROP-4.5.1-P05",
            )

    def test_degenerate_solid_black_and_white_images(self) -> None:
        """Full image with zero contrast (solid black, solid white) returns safely."""
        recognizer = FastAlprPlateRecognizer()

        black_img = Image.new("RGB", (320, 240), color="black")
        white_img = Image.new("RGB", (320, 240), color="white")

        res_black = recognizer.recognize(black_img)
        res_white = recognizer.recognize(white_img)

        assert isinstance(res_black, PlateScanResult)
        assert isinstance(res_white, PlateScanResult)
        assert res_black.candidates == []
        assert res_white.candidates == []

    def test_char_probs_none_or_empty_resilience(self) -> None:
        """
        Verify that if an OCR model returns char_probs = None or empty array,
        PlateCandidate and PlateScanResult handle it without numpy reduction exceptions.
        """
        recognizer = FastAlprPlateRecognizer()

        mock_cct = MagicMock()
        mock_cct.run_one.return_value = MagicMock(plate="51K99214", char_probs=None)

        mock_mv2 = MagicMock()
        mock_mv2.run_one.return_value = MagicMock(
            plate="51K99214", char_probs=np.array([])
        )

        mock_bbox = MagicMock()
        mock_bbox.x1 = 10
        mock_bbox.y1 = 10
        mock_bbox.x2 = 100
        mock_bbox.y2 = 50
        mock_det = MagicMock(bounding_box=mock_bbox)

        recognizer._detector = MagicMock(predict=MagicMock(return_value=[mock_det]))
        recognizer._ocr_cct = mock_cct
        recognizer._ocr_mv2 = mock_mv2

        img = Image.new("RGB", (200, 100), color="white")
        result = recognizer.recognize(img)

        assert len(result.candidates) == 1
        cand = result.candidates[0]
        assert cand.min_char_confidence == 0.0
        assert cand.confidence == 0.0


class TestTrigramSuggestionsEmpiricalSafety:
    """
    Empirical tests for Trigram Suggestions (Requirement A5).
    Verifies:
    1. 0 matches in DB -> returns [] (len 0).
    2. 1 match in DB -> returns exactly 1 item.
    3. 5 matches in DB -> returns at most 3 items (capped at limit=3).
    4. Distance > 1 plates are NEVER returned.
    5. Exact query plate is NEVER suggested to itself.
    6. Safety: Absolutely ZERO database INSERT or UPDATE operations occur during suggestion lookup.
    """

    def _get_customer_and_vtype(self) -> tuple[Customer, VehicleType]:
        cust = Customer.objects.first()
        if cust is None:
            cust = Customer.objects.create(
                full_name="Nguyễn Văn Test",
                phone="0901234567",
                code="CUST_T1",
            )
        vtype = VehicleType.objects.first()
        if vtype is None:
            vtype = VehicleType.objects.create(
                code="CAR_TEST",
                name="Ô tô con",
            )
        return cust, vtype

    def test_suggestions_zero_similar_plates_returns_empty(self) -> None:
        """When DB has 0 plates with edit distance <= 1, returns empty list."""
        suggestions = get_plate_suggestions("99Z99999", limit=3)
        assert suggestions == []

    def test_suggestions_one_similar_plate(self) -> None:
        """When DB has exactly 1 similar plate, returns that 1 plate."""
        cust, vtype = self._get_customer_and_vtype()
        Vehicle.objects.create(
            customer=cust,
            vehicle_type=vtype,
            license_plate="30A-123.44",
            license_plate_norm="30A12344",
            model_name="Sedan",
            code="VEH-001",
        )

        # Query for '30A12345' (edit distance 1 from '30A12344')
        suggestions = get_plate_suggestions("30A12345", limit=3)
        assert len(suggestions) == 1
        assert suggestions[0] == "30A-123.44"

    def test_suggestions_five_similar_plates_capped_at_three(self) -> None:
        """
        When DB has 5 plates with edit distance <= 1,
        get_plate_suggestions must return AT MOST 3 suggestions.
        """
        cust, vtype = self._get_customer_and_vtype()
        target_norm = "29A11110"

        # Create 5 vehicles with edit distance 1 from target_norm
        similar_norms = ["29A11111", "29A11112", "29A11113", "29A11114", "29A11115"]
        for idx, norm in enumerate(similar_norms):
            Vehicle.objects.create(
                customer=cust,
                vehicle_type=vtype,
                license_plate=f"29A-111.1{idx + 1}",
                license_plate_norm=norm,
                model_name="Sedan",
                code=f"VEH-C{idx}",
            )

        suggestions = get_plate_suggestions(target_norm, limit=3)
        assert len(suggestions) == 3
        # Ensure all returned suggestions have edit distance <= 1
        for s in suggestions:
            s_norm = s.replace("-", "").replace(".", "").upper()
            assert _levenshtein_distance(target_norm, s_norm) <= 1

    def test_suggestions_excludes_dissimilar_plates(self) -> None:
        """Plates with no trigram similarity / large edit distance must NEVER be returned in suggestions."""
        cust, vtype = self._get_customer_and_vtype()
        target_norm = "51K99214"

        # Completely dissimilar plate: '88A-000.00' (distance 8)
        Vehicle.objects.create(
            customer=cust,
            vehicle_type=vtype,
            license_plate="88A-000.00",
            license_plate_norm="88A00000",
            model_name="Sedan",
            code="VEH-002",
        )

        suggestions = get_plate_suggestions(target_norm, limit=3)
        assert suggestions == []

    def test_suggestions_never_suggests_exact_query_plate(self) -> None:
        """The query plate itself must never be included in its own suggestions."""
        cust, vtype = self._get_customer_and_vtype()
        Vehicle.objects.create(
            customer=cust,
            vehicle_type=vtype,
            license_plate="51K-992.14",
            license_plate_norm="51K99214",
            model_name="Sedan",
            code="VEH-003",
        )

        suggestions = get_plate_suggestions("51K99214", limit=3)
        assert "51K-992.14" not in suggestions

    def test_suggestions_absolute_database_write_safety(self) -> None:
        """
        Verify that get_plate_suggestions is strictly read-only:
        - 0 INSERT queries
        - 0 UPDATE queries
        - 0 DELETE queries
        - Table counts unchanged
        """
        cust, vtype = self._get_customer_and_vtype()
        Vehicle.objects.create(
            customer=cust,
            vehicle_type=vtype,
            license_plate="51K-992.15",
            license_plate_norm="51K99215",
            model_name="Sedan",
            code="VEH-004",
        )

        count_veh_before = Vehicle.objects.count()
        count_blk_before = PlateBlacklist.objects.count()

        with CaptureQueriesContext(connection) as captured:
            suggestions = get_plate_suggestions("51K99214", limit=3)

        count_veh_after = Vehicle.objects.count()
        count_blk_after = PlateBlacklist.objects.count()

        assert count_veh_before == count_veh_after
        assert count_blk_before == count_blk_after
        assert len(suggestions) >= 1

        for query_info in captured:
            sql = query_info["sql"].strip().upper()
            assert not sql.startswith("INSERT"), f"Unsafe INSERT query detected: {sql}"
            assert not sql.startswith("UPDATE"), f"Unsafe UPDATE query detected: {sql}"
            assert not sql.startswith("DELETE"), f"Unsafe DELETE query detected: {sql}"


class TestSingletonFastAlprThreadSafety:
    """
    Stress-testing Singleton FastAlprPlateRecognizer thread-safety.
    Verifies:
    1. Concurrent calls to get_plate_recognizer() return identical singleton instance.
    2. Concurrent recognize() calls across multiple threads execute safely without race conditions.
    """

    def test_singleton_get_plate_recognizer_concurrency(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Ensure get_plate_recognizer() is strictly thread-safe under concurrent requests."""
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "fast_alpr")
        set_global_recognizer(None)

        results: list[int] = []

        def worker() -> int:
            rec = get_plate_recognizer()
            return id(rec)

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as executor:
            futures = [executor.submit(worker) for _ in range(32)]
            for fut in concurrent.futures.as_completed(futures):
                results.append(fut.result())

        # All 32 calls must return the EXACT same instance ID
        assert len(set(results)) == 1, (
            f"Expected single instance, got {len(set(results))} distinct IDs"
        )

    def test_concurrent_recognize_calls_on_singleton(self) -> None:
        """
        Verify that multiple threads calling recognize() concurrently on the same
        FastAlprPlateRecognizer instance complete without crash or state corruption.
        """
        recognizer = FastAlprPlateRecognizer()
        assert recognizer.warmup() is True

        img = Image.new("RGB", (320, 240), color="white")

        errors: list[Exception] = []
        scan_results: list[PlateScanResult] = []

        def run_recognition(idx: int) -> PlateScanResult:
            return recognizer.recognize(img)

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(run_recognition, i) for i in range(25)]
            for fut in concurrent.futures.as_completed(futures):
                try:
                    res = fut.result()
                    scan_results.append(res)
                except Exception as exc:
                    errors.append(exc)

        assert len(errors) == 0, f"Thread execution encountered errors: {errors}"
        assert len(scan_results) == 25
        for res in scan_results:
            assert isinstance(res, PlateScanResult)
            assert res.latency_ms >= 0.0
