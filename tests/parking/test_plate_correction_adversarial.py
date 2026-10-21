"""
Empirical Stress-Testing Harness for Plate Correction.

Verifies:
1. Non-silent character substitution enforcement (J4):
   - Dynamic fuzzing harness testing >= 50 synthetic plates undergoing character corrections.
   - 100% / extreme confidence bypass resistance.
   - Zero tolerance: ANY non-empty corrections list MUST result in NEEDS_REVIEW + POSITION_CORRECTED.
   - Adversarial bypass exploration (has_corrections vs corrections precedence, falsy containers, etc.).
2. Backward compatibility & regression verification:
   - corrections=None and corrections=[] return AUTO when conditions are met.
   - Re-exports from apps.parking.services.plate_correction are identical (identity check).
   - ReviewReasonCode.POSITION_CORRECTED in CHOICES and ALL_CODES.
3. Multi-reason deduplication and integrity:
   - Co-occurrence of POSITION_CORRECTED with all other failure reasons.
   - Strict uniqueness (0 duplicates).
4. Full API and Service integration tests with test doubles (non-circular contract alignment).
5. Invariants: Zero committed dataset images in repo tree.
"""

from __future__ import annotations

import inspect
import io
import os
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.parking.enums import ReviewReasonCode, ReviewStatus
from apps.parking.services.ocr import (
    BoundingBox,
    DummyPlateRecognizer,
    PlateCandidate,
    set_global_recognizer,
)
from apps.parking.services.plate_correction import (
    CorrectionDetail,
    correct_plate_characters,
    evaluate_review_policy,
)
from apps.parking.services.plate_scan import execute_plate_scan

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

pytestmark = pytest.mark.django_db


def _create_jpeg_file(name: str = "scan.jpg") -> SimpleUploadedFile:
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 100), color="white")
    img.save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


# ==============================================================================
# 1. SYNTHETIC PLATE GENERATOR FOR NON-SILENT SUBSTITUTION FUZZING
# ==============================================================================


def generate_adversarial_synthetic_plates() -> list[tuple[str, str, int, str, str]]:
    """
    Generate > 60 distinct synthetic plates covering every positional correction rule:
    Returns tuples of (raw_plate, expected_corrected_plate, position, from_char, to_char).
    """
    cases: list[tuple[str, str, int, str, str]] = []

    pos1_mappings = [
        ("5DZ1630", "50Z1630", 1, "D", "0"),
        ("5OZ1630", "50Z1630", 1, "O", "0"),
        ("5QZ1630", "50Z1630", 1, "Q", "0"),
        ("5ZY6490", "52Y6490", 1, "Z", "2"),
        ("3QA1234", "30A1234", 1, "Q", "0"),
        ("2IA12345", "21A12345", 1, "I", "1"),
        ("2LA12345", "21A12345", 1, "L", "1"),
        ("2AA12345", "24A12345", 1, "A", "4"),
        ("2SA12345", "25A12345", 1, "S", "5"),
        ("2GA12345", "26A12345", 1, "G", "6"),
        ("2BA12345", "28A12345", 1, "B", "8"),
        ("5DA12345", "50A12345", 1, "D", "0"),
        ("5OA12345", "50A12345", 1, "O", "0"),
        ("5QA12345", "50A12345", 1, "Q", "0"),
        ("5ZA12345", "52A12345", 1, "Z", "2"),
        ("6DA12345", "60A12345", 1, "D", "0"),
        ("7DA12345", "70A12345", 1, "D", "0"),
        ("8DA12345", "80A12345", 1, "D", "0"),
        ("9DA12345", "90A12345", 1, "D", "0"),
    ]
    cases.extend(pos1_mappings)

    pos0_mappings = [
        ("I1A12345", "11A12345", 0, "I", "1"),
        ("L1A12345", "11A12345", 0, "L", "1"),
        ("Z9A12345", "29A12345", 0, "Z", "2"),
        ("A9A12345", "49A12345", 0, "A", "4"),
        ("S1A12345", "51A12345", 0, "S", "5"),
        ("G1A12345", "61A12345", 0, "G", "6"),
        ("B1A12345", "81A12345", 0, "B", "8"),
        ("S9A12345", "59A12345", 0, "S", "5"),
        ("B9A12345", "89A12345", 0, "B", "8"),
        ("Z1A12345", "21A12345", 0, "Z", "2"),
        ("A1A12345", "41A12345", 0, "A", "4"),
        ("I2A12345", "12A12345", 0, "I", "1"),
        ("L2A12345", "12A12345", 0, "L", "1"),
    ]
    cases.extend(pos0_mappings)

    pos2_mappings = [
        ("51599214", "51S99214", 2, "5", "S"),
        ("51899214", "51B99214", 2, "8", "B"),
        ("51299214", "51Z99214", 2, "2", "Z"),
        ("51099214", "51D99214", 2, "0", "D"),
        ("29512345", "29S12345", 2, "5", "S"),
        ("29812345", "29B12345", 2, "8", "B"),
        ("29212345", "29Z12345", 2, "2", "Z"),
        ("29012345", "29D12345", 2, "0", "D"),
        ("30512345", "30S12345", 2, "5", "S"),
        ("30812345", "30B12345", 2, "8", "B"),
        ("30212345", "30Z12345", 2, "2", "Z"),
        ("30012345", "30D12345", 2, "0", "D"),
        ("43512345", "43S12345", 2, "5", "S"),
        ("43812345", "43B12345", 2, "8", "B"),
        ("43212345", "43Z12345", 2, "2", "Z"),
        ("43012345", "43D12345", 2, "0", "D"),
    ]
    cases.extend(pos2_mappings)

    pos_num_mappings = [
        ("29A1B234", "29A18234", 4, "B", "8"),
        ("30E1234S", "30E12345", 7, "S", "5"),
        ("51K9921D", "51K99210", 7, "D", "0"),
        ("51K9921O", "51K99210", 7, "O", "0"),
        ("51K9921Q", "51K99210", 7, "Q", "0"),
        ("51K9921I", "51K99211", 7, "I", "1"),
        ("51K9921L", "51K99211", 7, "L", "1"),
        ("51K9921Z", "51K99212", 7, "Z", "2"),
        ("51K9921A", "51K99214", 7, "A", "4"),
        ("51K9921G", "51K99216", 7, "G", "6"),
        ("51K9921B", "51K99218", 7, "B", "8"),
        ("51A1234D", "51A12340", 7, "D", "0"),
        ("51A1234I", "51A12341", 7, "I", "1"),
        ("51A1234Z", "51A12342", 7, "Z", "2"),
        ("51A1234A", "51A12344", 7, "A", "4"),
        ("51A1234S", "51A12345", 7, "S", "5"),
        ("51A1234G", "51A12346", 7, "G", "6"),
        ("51A1234B", "51A12348", 7, "B", "8"),
        ("29LD1234D", "29LD12340", 8, "D", "0"),
        ("29LD1234I", "29LD12341", 8, "I", "1"),
        ("29LD1234Z", "29LD12342", 8, "Z", "2"),
        ("29LD1234A", "29LD12344", 8, "A", "4"),
        ("29LD1234S", "29LD12345", 8, "S", "5"),
    ]
    cases.extend(pos_num_mappings)

    return cases


# ==============================================================================
# 2. ADVERSARIAL STRESS TESTS: FUZZING & NON-SILENT SUBSTITUTION (J4)
# ==============================================================================


class TestAdversarialNonSilentSubstitutionFuzzing:
    """Adversarial challenge tests targeting J4 non-silent character substitution."""

    def test_fuzz_synthetic_plates_count_at_least_50(self):
        """Verify the test generator creates at least 50 synthetic plates."""
        cases = generate_adversarial_synthetic_plates()
        assert len(cases) >= 50, f"Expected >= 50 synthetic cases, got {len(cases)}"

    @pytest.mark.parametrize(
        "raw_plate, expected_plate, pos, from_char, to_char",
        generate_adversarial_synthetic_plates(),
    )
    def test_fuzz_plate_correction_and_review_policy_zero_tolerance(
        self, raw_plate, expected_plate, pos, from_char, to_char
    ):
        """
        Adversarial fuzzing on every synthetic plate:
        1. Plate correction must yield non-empty corrections.
        2. Even with 100% confidence, review policy MUST force NEEDS_REVIEW + POSITION_CORRECTED.
        """
        corrected, corrs = correct_plate_characters(raw_plate)
        assert len(corrs) >= 1, f"Failed to correct synthetic plate: {raw_plate}"
        assert corrected == expected_plate, f"Mismatch: {corrected} != {expected_plate}"

        status_val, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=99.999,
            threshold=90.0,
            is_valid_format=True,
            used_detection_fallback=False,
            is_unknown_pattern=False,
            detector_box_confidence=99.9,
            plate_aspect_ratio=2.5,
            crop_sharpness=80.0,
            corrections=corrs,
        )

        assert status_val == ReviewStatus.NEEDS_REVIEW, (
            f"Adversarial breach! Plate {raw_plate} -> {expected_plate} returned {status_val} "
            f"instead of NEEDS_REVIEW despite non-empty corrections!"
        )
        assert ReviewReasonCode.POSITION_CORRECTED in reasons, (
            f"POSITION_CORRECTED missing from reasons for corrected plate {raw_plate}! Reasons: {reasons}"
        )

    def test_extreme_confidence_values_cannot_bypass_position_corrected(self):
        """
        Adversarially probe boundary confidences: 100.0, 99.99999, 1000.0 (anomalous).
        All must strictly yield NEEDS_REVIEW + POSITION_CORRECTED when corrections is non-empty.
        """
        dummy_corr = [
            CorrectionDetail(
                position=1,
                original_char="D",
                corrected_char="0",
                rule="province_second_digit_fix",
            )
        ]

        extreme_confs = [90.0, 95.0, 99.0, 99.99, 100.0, 100.000001, 1000.0]
        for conf in extreme_confs:
            status_val, reasons = evaluate_review_policy(
                model_agreement=True,
                min_char_confidence=conf,
                threshold=90.0,
                is_valid_format=True,
                corrections=dummy_corr,
            )
            assert status_val == ReviewStatus.NEEDS_REVIEW, f"Bypassed at conf={conf}"
            assert ReviewReasonCode.POSITION_CORRECTED in reasons

    def test_various_sequence_types_for_corrections(self):
        """
        Adversarially test various non-empty container types for corrections:
        list, tuple, custom iterable, list of dicts.
        """
        sample_dict = {"position": 1, "from": "D", "to": "0"}
        containers = [
            [sample_dict],
            (sample_dict,),
            [1],
            ("arbitrary_correction",),
        ]

        for container in containers:
            status_val, reasons = evaluate_review_policy(
                model_agreement=True,
                min_char_confidence=98.0,
                threshold=90.0,
                is_valid_format=True,
                corrections=container,
            )
            assert status_val == ReviewStatus.NEEDS_REVIEW
            assert ReviewReasonCode.POSITION_CORRECTED in reasons

    def test_adversarial_bypass_probe_has_corrections_override(self):
        """
        Adversarial probe: What happens if caller passes non-empty corrections AND has_corrections=False?
        Verify that execute_plate_scan does NOT expose has_corrections to external callers.
        """
        dummy_corr = [
            CorrectionDetail(
                position=1,
                original_char="D",
                corrected_char="0",
                rule="province_second_digit_fix",
            )
        ]

        status_val, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=98.0,
            threshold=90.0,
            is_valid_format=True,
            corrections=dummy_corr,
            has_corrections=False,
        )
        assert status_val == ReviewStatus.AUTO
        sig_scan = inspect.signature(execute_plate_scan)
        assert "has_corrections" not in sig_scan.parameters, (
            "Security risk! execute_plate_scan exposes has_corrections parameter to callers!"
        )


# ==============================================================================
# 3. BACKWARD COMPATIBILITY & REGRESSION FUZZING
# ==============================================================================


class TestBackwardCompatibilityAndModuleIntegrity:
    """Verify 100% backward compatibility and re-export integrity."""

    def test_re_exports_identity_from_plate_correction(self):
        """
        Verify that imports from `apps.parking.services.plate_correction`
        are byte-for-byte identical objects (not copies or re-definitions).
        """
        from apps.parking.enums import (
            ReviewReasonCode as EnumReviewReasonCode,
        )
        from apps.parking.enums import (
            ReviewStatus as EnumReviewStatus,
        )
        from apps.parking.services.plate_correction import (
            ReviewReasonCode as PCReviewReasonCode,
        )
        from apps.parking.services.plate_correction import (
            ReviewStatus as PCReviewStatus,
        )
        from apps.parking.services.plate_correction import (
            evaluate_review_policy as PCEvalPolicy,
        )
        from apps.parking.services.review_policy import (
            evaluate_review_policy as ServEvalPolicy,
        )

        assert PCReviewReasonCode is EnumReviewReasonCode
        assert PCReviewStatus is EnumReviewStatus
        assert PCEvalPolicy is ServEvalPolicy

    def test_review_reason_code_registration(self):
        """Verify POSITION_CORRECTED is registered in CHOICES and ALL_CODES."""
        assert ReviewReasonCode.POSITION_CORRECTED == "POSITION_CORRECTED"
        assert ReviewReasonCode.POSITION_CORRECTED in ReviewReasonCode.ALL_CODES
        choice_codes = [c[0] for c in ReviewReasonCode.CHOICES]
        assert ReviewReasonCode.POSITION_CORRECTED in choice_codes

    def test_backward_compatibility_none_and_empty_corrections(self):
        """
        Verify that corrections=None and corrections=[] behave identically
        and allow AUTO status when all other conditions are satisfied.
        """
        for empty_val in [None, []]:
            status_val, reasons = evaluate_review_policy(
                model_agreement=True,
                min_char_confidence=95.0,
                threshold=90.0,
                is_valid_format=True,
                corrections=empty_val,
            )
            assert status_val == ReviewStatus.AUTO
            assert reasons == []
            assert ReviewReasonCode.POSITION_CORRECTED not in reasons

    def test_clean_plates_fuzzing_no_false_corrections(self):
        """
        Fuzz 25 clean standard Vietnamese plates:
        None should produce corrections, and all should receive AUTO.
        """
        clean_plates = [
            "51K99214",
            "29A12345",
            "30E99999",
            "43A11122",
            "14A56789",
            "50E12345",
            "51F67890",
            "51G12345",
            "51H54321",
            "29B12345",
            "30F12345",
            "30G54321",
            "43B12345",
            "60A12345",
            "61A12345",
            "62A12345",
            "63A12345",
            "64A12345",
            "65A12345",
            "66A12345",
            "67A12345",
            "68A12345",
            "69A12345",
            "70A12345",
            "71A12345",
        ]
        for plate in clean_plates:
            cleaned, corrs = correct_plate_characters(plate)
            assert cleaned == plate
            assert corrs == [], f"False correction on clean plate: {plate} -> {corrs}"

            status_val, reasons = evaluate_review_policy(
                model_agreement=True,
                min_char_confidence=95.0,
                threshold=90.0,
                is_valid_format=True,
                corrections=corrs,
            )
            assert status_val == ReviewStatus.AUTO
            assert reasons == []


# ==============================================================================
# 4. MULTI-REASON DEDUPLICATION & INTEGRITY
# ==============================================================================


class TestMultiReasonDeduplicationAndIntegrity:
    """Verify review reasons co-occurrence, ordering, and deduplication."""

    def test_multi_reason_co_occurrence_all_eight_reasons(self):
        """Trigger all 8 distinct failure reasons simultaneously and verify zero duplicates."""
        dummy_corr = [
            CorrectionDetail(
                position=1,
                original_char="D",
                corrected_char="0",
                rule="province_second_digit_fix",
            )
        ]

        status_val, reasons = evaluate_review_policy(
            model_agreement=False,
            min_char_confidence=50.0,
            threshold=90.0,
            is_valid_format=False,
            used_detection_fallback=True,
            is_unknown_pattern=False,
            detector_box_confidence=60.0,
            plate_aspect_ratio=1.0,
            crop_sharpness=15.0,
            corrections=dummy_corr,
        )

        assert status_val == ReviewStatus.NEEDS_REVIEW
        expected_reasons = {
            ReviewReasonCode.MODEL_DISAGREEMENT,
            ReviewReasonCode.LOW_CHAR_CONFIDENCE,
            ReviewReasonCode.INVALID_FORMAT,
            ReviewReasonCode.NO_DETECTION_RETRY,
            ReviewReasonCode.LOW_DETECTION_CONFIDENCE,
            ReviewReasonCode.IRREGULAR_ASPECT_RATIO,
            ReviewReasonCode.LOW_IMAGE_SHARPNESS,
            ReviewReasonCode.POSITION_CORRECTED,
        }
        assert set(reasons) == expected_reasons
        assert len(reasons) == len(set(reasons)) == 8

    def test_unknown_pattern_mutually_exclusive_with_invalid_format(self):
        """Verify is_unknown_pattern takes precedence over INVALID_FORMAT."""
        dummy_corr = [
            CorrectionDetail(
                position=1,
                original_char="D",
                corrected_char="0",
                rule="province_second_digit_fix",
            )
        ]

        status_val, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=95.0,
            threshold=90.0,
            is_valid_format=False,
            is_unknown_pattern=True,
            corrections=dummy_corr,
        )

        assert status_val == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.UNKNOWN_PLATE_PATTERN in reasons
        assert ReviewReasonCode.INVALID_FORMAT not in reasons
        assert ReviewReasonCode.POSITION_CORRECTED in reasons
        assert len(reasons) == len(set(reasons)) == 2

    def test_both_low_confidence_and_position_corrected(self):
        """Test typical edge case: plate has both low char confidence AND position correction."""
        dummy_corr = [
            CorrectionDetail(
                position=1,
                original_char="D",
                corrected_char="0",
                rule="province_second_digit_fix",
            )
        ]

        status_val, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=75.0,
            threshold=90.0,
            is_valid_format=True,
            corrections=dummy_corr,
        )

        assert status_val == ReviewStatus.NEEDS_REVIEW
        assert reasons == [
            ReviewReasonCode.LOW_CHAR_CONFIDENCE,
            ReviewReasonCode.POSITION_CORRECTED,
        ]
        assert len(reasons) == len(set(reasons)) == 2


# ==============================================================================
# 5. FULL API AND SERVICE INTEGRATION
# ==============================================================================


class TestFullScanIntegrationAdversarial:
    """Test full scan pipeline integration via PlateScanView and execute_plate_scan."""

    @pytest.fixture
    def auth_employee(self):
        emp, _ = Account.objects.get_or_create(
            email="emp_plate_scan@parking.local",
            defaults={
                "role": "EMPLOYEE",
                "is_active": True,
                "password": "!dummy_password_hash",
            },
        )
        return emp

    def test_execute_plate_scan_enforces_position_corrected(self):
        """
        Verify plate scan pipeline end-to-end:
        When PlateCandidate triggers position correction, review_status is forced to NEEDS_REVIEW
        and POSITION_CORRECTED is registered in reasons.
        """
        from apps.parking.services.plate_scan import execute_plate_scan

        cand = PlateCandidate(
            plate_text="5DZ-1630",
            plate_normalized="5DZ1630",
            confidence=99.0,
            char_confidences=[99.0] * 7,
            min_char_confidence=99.0,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
        )

        dummy = DummyPlateRecognizer(preset_candidates=[cand], default_confidence=99.0)
        file_obj = _create_jpeg_file()
        result = execute_plate_scan(
            image_file=file_obj,
            recognizer=dummy,
        )
        payload = result.payload

        assert payload["plate_raw"] == "5DZ-1630"
        assert payload["plate_final"] == "50Z1630"
        assert payload["review_status"] == "NEEDS_REVIEW"
        assert "POSITION_CORRECTED" in payload["review_reasons"]
        assert len(payload["corrections"]) == 1
        corr = payload["corrections"][0]
        assert corr["position"] == 1
        assert corr["from"] == "D"
        assert corr["to"] == "0"

    def test_api_view_enforces_position_corrected_http_multipart(self, auth_employee):
        """
        Verify PlateScanView API endpoint end-to-end with HTTP multipart POST:
        Asserts HTTP 200, JSON schema envelope, review_status NEEDS_REVIEW, and POSITION_CORRECTED.
        """
        client = APIClient()
        client.force_authenticate(user=auth_employee)

        cand = PlateCandidate(
            plate_text="29A1B234",
            plate_normalized="29A1B234",
            confidence=99.5,
            char_confidences=[99.5] * 8,
            min_char_confidence=99.5,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
        )

        dummy = DummyPlateRecognizer(preset_candidates=[cand], default_confidence=99.5)
        set_global_recognizer(dummy)
        try:
            file_obj = _create_jpeg_file()
            response = client.post(
                "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.data
            assert data["plate_raw"] == "29A1B234"
            assert data["plate_final"] == "29A18234"
            assert data["review_status"] == "NEEDS_REVIEW"
            assert "POSITION_CORRECTED" in data["review_reasons"]
            assert len(data["corrections"]) == 1
            assert data["corrections"][0]["from"] == "B"
            assert data["corrections"][0]["to"] == "8"
        finally:
            set_global_recognizer(None)


# ==============================================================================
# 6. INVARIANT CHECKS: NO DATASET IMAGES COMMITTED
# ==============================================================================


class TestMandatoryInvariants:
    """Verify no dataset images or parquet files are committed in repository tree."""

    def test_zero_dataset_images_in_git(self) -> None:
        """Dataset images and parquet files must NEVER exist in the repository tree."""
        excluded_dirs = {
            ".git",
            ".venv",
            "venv",
            ".agents",
            "media",
            "__pycache__",
            ".mypy_cache",
            ".pytest_cache",
            ".ruff_cache",
            "node_modules",
            "build",
            "dist",
        }
        forbidden_exts = {".jpg", ".jpeg", ".bmp", ".webp", ".parquet"}

        found_dataset_files: list[str] = []
        for root, dirs, files in os.walk(REPO_ROOT):
            # Prune excluded directories in-place to avoid descending into cache/venv/agents trees
            dirs[:] = [d for d in dirs if d not in excluded_dirs]
            for file_name in files:
                file_path = Path(root) / file_name
                if file_path.suffix.lower() in forbidden_exts:
                    found_dataset_files.append(str(file_path.relative_to(REPO_ROOT)))

        assert len(found_dataset_files) == 0, (
            f"Found forbidden dataset image/parquet files in repository tree: {found_dataset_files}"
        )
