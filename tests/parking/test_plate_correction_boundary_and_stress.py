"""
Boundary Stress Test Suite for Plate Correction Boundary & Edge Cases.
Comprehensive empirical validation of:
1. is_valid_vietnamese_plate
2. correct_plate_characters (zero broken correct reads, classic OCR fixes, dual-letter protection)
3. evaluate_review_policy (boundary conditions, 16-state truth table, exact review reasons)
4. PlateScan API end-to-end response contracts

Complies with Project Testing Standards and Senior Developer Empirical Verification.
"""

from __future__ import annotations

import io
import itertools
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.parking.services.ocr import PlateCandidate, PlateScanResult
from apps.parking.services.plate_correction import (
    VALID_PROVINCES,
    ReviewReasonCode,
    correct_plate_characters,
    evaluate_review_policy,
    is_valid_vietnamese_plate,
)

# ==============================================================================
# SECTION 1: EMPIRICAL PROOF OF 0 BROKEN CORRECT READS (LARGE-SCALE GENERATION)
# ==============================================================================


class TestEmpiricalZeroBrokenReads:
    """
    Stress-tests correct_plate_characters with a massive variety of valid plates.
    Proves empirically that 0 valid plates are broken or corrupted by correction rules.
    """

    def test_all_63_provinces_standard_cars_zero_broken(self) -> None:
        """
        Generates standard car plates across all 63 valid provinces with multiple series
        letters (A-Z) and both 4-digit and 5-digit number patterns.
        Proves: 100% untouched, 0 corrections, 0 broken reads.
        """
        series_samples = [
            "A",
            "B",
            "C",
            "D",
            "E",
            "F",
            "G",
            "H",
            "K",
            "L",
            "M",
            "N",
            "P",
            "S",
            "T",
            "U",
            "V",
            "X",
            "Y",
            "Z",
        ]
        number_samples = ["1234", "5678", "9999", "12345", "67890", "99214"]

        tested_count = 0
        for prov in VALID_PROVINCES:
            for s in series_samples:
                for num in number_samples:
                    plate = f"{prov}{s}{num}"
                    assert is_valid_vietnamese_plate(plate) is True, (
                        f"Valid plate {plate} failed format regex"
                    )
                    corrected, corrs = correct_plate_characters(plate)
                    assert corrected == plate, (
                        f"Broken correct read! {plate} was altered to {corrected}"
                    )
                    assert corrs == [], (
                        f"Unexpected corrections applied to valid plate {plate}: {corrs}"
                    )
                    tested_count += 1

        # 63 provinces * 20 series * 6 numbers = 7,560 test plates
        assert tested_count >= 7000

    def test_dual_letter_cars_zero_broken(self) -> None:
        """
        Tests joint-venture (LD), project (DA), diplomatic (NG, NN), and international (QT) plates.
        Proves: 100% untouched, 0 corrections, 0 broken reads.
        """
        dual_series = ["LD", "DA", "NG", "NN", "QT"]
        provinces = ["29", "30", "50", "51", "80", "43", "60"]
        numbers = ["04411", "00123", "12345", "5678", "9999"]

        tested_count = 0
        for prov in provinces:
            for ds in dual_series:
                for num in numbers:
                    plate = f"{prov}{ds}{num}"
                    assert is_valid_vietnamese_plate(plate) is True, (
                        f"Valid dual-letter plate {plate} failed regex"
                    )
                    corrected, corrs = correct_plate_characters(plate)
                    assert corrected == plate, (
                        f"Broken correct read! {plate} altered to {corrected}"
                    )
                    assert corrs == [], f"Unexpected corrections for {plate}: {corrs}"
                    tested_count += 1

        assert tested_count == len(provinces) * len(dual_series) * len(numbers)

    def test_government_agency_plates_zero_broken(self) -> None:
        """
        Tests central government (80A, 80B, 80M) and municipal government plates (29A, 30B).
        Proves: 100% untouched, 0 corrections, 0 broken reads.
        """
        gov_plates = [
            "80A12345",
            "80B56789",
            "80M00123",
            "80A9999",
            "80B1111",
            "29A12345",
            "30B67890",
            "51A0001",
        ]
        for plate in gov_plates:
            assert is_valid_vietnamese_plate(plate) is True
            corrected, corrs = correct_plate_characters(plate)
            assert corrected == plate
            assert corrs == []

    def test_motorbike_plates_zero_broken(self) -> None:
        """
        Tests motorbike plates (2 digits + 1 letter + 1 digit/letter + 4/5 digits).
        Proves: Rejected from car-only parking facility (is_valid is False), and untouched by correction.
        """
        motorbike_plates = [
            "29B199988",
            "59P212345",
            "43E156789",
            "79B112345",
            "29AA12345",
            "50AB56789",
            "60F199999",
            "99K188888",
        ]
        for plate in motorbike_plates:
            assert is_valid_vietnamese_plate(plate) is False
            corrected, corrs = correct_plate_characters(plate)
            assert corrected == plate
            assert corrs == []

    def test_military_plates_zero_broken(self) -> None:
        """
        Tests military vehicle plate formats (e.g. QA, QB, QC, QD, TC, TH, TT, TM, HA, PK, BP, CS).
        Although military plates are red-plated state vehicles outside standard civilian regex,
        correct_plate_characters must NEVER corrupt or break them!
        """
        military_prefixes = [
            "QA",
            "QB",
            "QC",
            "QD",
            "TC",
            "TH",
            "TT",
            "TM",
            "HA",
            "HB",
            "HC",
            "HD",
            "HE",
            "HT",
            "HQ",
            "PK",
            "BP",
            "CS",
        ]
        number_samples = ["1234", "5678", "9999", "12345", "67890"]

        for prefix in military_prefixes:
            for num in number_samples:
                military_plate = f"{prefix}{num}"
                corrected, corrs = correct_plate_characters(military_plate)
                assert corrected == military_plate, (
                    f"Military plate {military_plate} was corrupted into {corrected}!"
                )
                assert corrs == [], (
                    f"Military plate {military_plate} had unexpected corrections: {corrs}"
                )

    def test_plates_with_standard_separators_normalized_cleanly(self) -> None:
        """
        Tests plates containing dots, dashes, and spaces (e.g. 51K-992.14, 29B1-999.88).
        Ensures separators are stripped and normalized cleanly without erroneous modifications.
        """
        raw_plates = [
            ("51K-992.14", "51K99214"),
            ("30H-123.45", "30H12345"),
            ("50LD-044.11", "50LD04411"),
            ("29B1-999.88", "29B199988"),
            ("80-NG-123.45", "80NG12345"),
            ("29 DA 001.23", "29DA00123"),
        ]
        for raw, expected_norm in raw_plates:
            corrected, corrs = correct_plate_characters(raw)
            assert corrected == expected_norm
            assert corrs == []


# ==============================================================================
# SECTION 2: CLASSIC OCR CONFUSIONS & POSITION-AWARE CORRECTION VERIFICATION
# ==============================================================================


class TestClassicOCRConfusionCorrections:
    """
    Stress-tests the specific positional grammar rules for known OCR confusions:
    - Pos 1: D -> 0 in province code (e.g. 5DZ1630 -> 50Z1630)
    - Pos 0: Confusables in first digit of province
    - Pos 2: 5 -> S, 8 -> B in series letter
    - Pos 3..end: O -> 0, I -> 1, Z -> 2, A -> 4, S -> 5, G -> 6, B -> 8 in number group
    - Protection of dual-letter series: LD, DA, NG, NN
    """

    def test_province_pos_1_d_to_0_comprehensive(self) -> None:
        """
        Tests D -> 0 replacement at position 1 across diverse provinces and series.
        Verifies exact correction details: position=1, original='D', corrected='0', rule='province_second_digit_fix'.
        """
        test_cases = [
            ("5DZ1630", "50Z1630"),
            ("3DA12345", "30A12345"),
            ("2DA5678", "20A5678"),
            ("8DA12345", "80A12345"),
            ("6DZ9999", "60Z9999"),
            ("7DZ12345", "70Z12345"),
            ("9DZ8888", "90Z8888"),
        ]
        for corrupted, expected in test_cases:
            corrected, corrs = correct_plate_characters(corrupted)
            assert corrected == expected
            assert len(corrs) == 1
            assert corrs[0].position == 1
            assert corrs[0].original_char == "D"
            assert corrs[0].corrected_char == "0"
            assert corrs[0].rule == "province_second_digit_fix"
            assert is_valid_vietnamese_plate(corrected) is True

    def test_province_pos_0_confusables(self) -> None:
        """
        Tests pos 0 confusable fix: when pos 0 is letter confusable and pos 1 is digit.
        e.g. I1A12345 -> 11A12345 (I -> 1).
        """
        corrupted = "I1A12345"
        expected = "11A12345"
        corrected, corrs = correct_plate_characters(corrupted)
        assert corrected == expected
        assert len(corrs) == 1
        assert corrs[0].position == 0
        assert corrs[0].original_char == "I"
        assert corrs[0].corrected_char == "1"
        assert corrs[0].rule == "province_first_digit_fix"
        assert is_valid_vietnamese_plate(corrected) is True

    def test_series_pos_2_digit_to_letter_fixes(self) -> None:
        """
        Tests position 2 series letter confusion:
        - 5 -> S (e.g. 51599214 -> 51S99214)
        - 8 -> B (e.g. 30812345 -> 30B12345)
        - 2 -> Z (e.g. 2925678 -> 29Z5678)
        - 0 -> D (e.g. 51099214 -> 51D99214)
        """
        cases = [
            ("51599214", "51S99214", "5", "S"),
            ("30812345", "30B12345", "8", "B"),
            ("2955678", "29S5678", "5", "S"),
            ("2985678", "29B5678", "8", "B"),
            ("51299214", "51Z99214", "2", "Z"),
            ("51099214", "51D99214", "0", "D"),
        ]
        for corrupted, expected, orig_c, corr_c in cases:
            corrected, corrs = correct_plate_characters(corrupted)
            assert corrected == expected
            assert len(corrs) == 1
            assert corrs[0].position == 2
            assert corrs[0].original_char == orig_c
            assert corrs[0].corrected_char == corr_c
            assert corrs[0].rule == "series_letter_fix"
            assert is_valid_vietnamese_plate(corrected) is True

    def test_number_group_confusables_comprehensive(self) -> None:
        """
        Tests confusable character replacement in number positions (pos 3..end).
        Tests: O->0, I->1, Z->2, A->4, S->5, G->6, B->8.
        """
        confusable_cases = [
            ("51K9921O", "51K99210", 7, "O", "0"),
            ("30H1234I", "30H12341", 7, "I", "1"),
            ("29A567O", "29A5670", 6, "O", "0"),
            ("51K9O214", "51K90214", 4, "O", "0"),
            ("51K1I345", "51K11345", 4, "I", "1"),
            ("51KI234", "51K1234", 3, "I", "1"),
            ("51K9921Z", "51K99212", 7, "Z", "2"),
            ("51K9921A", "51K99214", 7, "A", "4"),
            ("51K9921S", "51K99215", 7, "S", "5"),
            ("51K9921G", "51K99216", 7, "G", "6"),
            ("51K9921B", "51K99218", 7, "B", "8"),
        ]
        for corrupted, expected, pos, orig_c, corr_c in confusable_cases:
            corrected, corrs = correct_plate_characters(corrupted)
            assert corrected == expected
            assert len(corrs) == 1
            assert corrs[0].position == pos
            assert corrs[0].original_char == orig_c
            assert corrs[0].corrected_char == corr_c
            assert is_valid_vietnamese_plate(corrected) is True

    def test_motorbike_dual_letter_series_preserved(self) -> None:
        """
        Boundary edge case: Motorbikes with 2-letter series (e.g. 51KI2345, 29AA12345).
        Because this facility is car-only (SRS v4.1), is_valid_vietnamese_plate returns False.
        '51KI2345' has 'I' at position 3 corrected to digit '1', yielding valid car plate '51K12345'.
        Uncataloged series '29AA12345' and '50AB56789' are preserved untouched.
        """
        assert is_valid_vietnamese_plate("51KI2345") is False
        corrected, corrs = correct_plate_characters("51KI2345")
        assert corrected == "51K12345"
        assert len(corrs) == 1
        assert corrs[0].position == 3
        assert corrs[0].corrected_char == "1"

        uncorrected_motorbikes = ["29AA12345", "50AB56789"]
        for mb in uncorrected_motorbikes:
            assert is_valid_vietnamese_plate(mb) is False
            corrected, corrs = correct_plate_characters(mb)
            assert corrected == mb
            assert corrs == []

    def test_dual_letter_series_protected_during_number_group_fixes(self) -> None:
        """
        Verifies that dual-letter series characters (LD, DA, NG, NN) are strictly protected:
        - 50LD04411: pos 3 'D' is NOT converted to '0'
        - 29DA00123: pos 3 'A' is NOT converted to '4'
        - 80NG12345: pos 3 'G' is NOT converted to '6'
        - 50LD0441O: pos 3 'D' is preserved, while pos 8 'O' is converted to '0' -> 50LD04410
        - 29DA0012I: pos 3 'A' is preserved, while pos 8 'I' is converted to '1' -> 29DA00121
        - 80NG1234S: pos 3 'G' is preserved, while pos 8 'S' is converted to '5' -> 80NG12345
        """
        protected_cases = [
            ("50LD0441O", "50LD04410", 8, "O", "0"),
            ("29DA0012I", "29DA00121", 8, "I", "1"),
            ("80NG1234S", "80NG12345", 8, "S", "5"),
        ]
        for corrupted, expected, pos, orig_c, corr_c in protected_cases:
            corrected, corrs = correct_plate_characters(corrupted)
            assert corrected == expected
            assert len(corrs) == 1
            assert corrs[0].position == pos
            assert corrs[0].original_char == orig_c
            assert corrs[0].corrected_char == corr_c
            assert is_valid_vietnamese_plate(corrected) is True

    def test_multiple_independent_corrections_on_single_plate(self) -> None:
        """
        Tests plates with multiple independent OCR errors that can be solved sequentially:
        - '5DZ163O' -> Pos 1: D->0, Pos 6: O->0 -> '50Z1630' (2 corrections)
        - '5DA1234I' -> Pos 1: D->0, Pos 7: I->1 -> '50A12341' (2 corrections)
        """
        multi_cases = [
            ("5DZ163O", "50Z1630", 2),
            ("5DA1234I", "50A12341", 2),
        ]
        for corrupted, expected, expected_corr_len in multi_cases:
            corrected, corrs = correct_plate_characters(corrupted)
            assert corrected == expected
            assert len(corrs) == expected_corr_len
            assert is_valid_vietnamese_plate(corrected) is True


# ==============================================================================
# SECTION 3: EXHAUSTIVE REVIEW POLICY BOUNDARY & 16-STATE TRUTH TABLE
# ==============================================================================


class TestReviewPolicyBoundary:
    """
    Stress-tests evaluate_review_policy against all boundary conditions:
    - 84.99 vs 85.00 strict boundary
    - Fractional (0.85) vs percentage (85.0) threshold formats
    - 16-state truth table (4 independent boolean conditions)
    - Verification of exact ReviewReasonCode sets
    """

    @pytest.mark.parametrize(
        "conf,threshold,expected_status,expected_reasons",
        [
            (85.0000, 85.0, "AUTO", []),
            (85.0001, 85.0, "AUTO", []),
            (84.9999, 85.0, "NEEDS_REVIEW", [ReviewReasonCode.LOW_CHAR_CONFIDENCE]),
            (84.9900, 85.0, "NEEDS_REVIEW", [ReviewReasonCode.LOW_CHAR_CONFIDENCE]),
            (85.0000, 0.85, "AUTO", []),
            (85.0100, 0.85, "AUTO", []),
            (84.9900, 0.85, "NEEDS_REVIEW", [ReviewReasonCode.LOW_CHAR_CONFIDENCE]),
            (0.0, 85.0, "NEEDS_REVIEW", [ReviewReasonCode.LOW_CHAR_CONFIDENCE]),
            (100.0, 85.0, "AUTO", []),
            (100.0, 100.0, "AUTO", []),
            (99.99, 100.0, "NEEDS_REVIEW", [ReviewReasonCode.LOW_CHAR_CONFIDENCE]),
        ],
    )
    def test_review_policy_threshold_boundaries(
        self,
        conf: float,
        threshold: float,
        expected_status: str,
        expected_reasons: list[str],
    ) -> None:
        """Tests floating-point edge cases around the 85.0% threshold."""
        status_res, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=conf,
            threshold=threshold,
            is_valid_format=True,
            used_detection_fallback=False,
        )
        assert status_res == expected_status
        assert reasons == expected_reasons

    def test_full_16_state_truth_table(self) -> None:
        """
        Exhaustively tests all 2^4 = 16 combinations of the 4 review policy conditions:
        1. model_agreement (True / False)
        2. confidence >= 85.0 (True / False)
        3. is_valid_format (True / False)
        4. used_detection_fallback (False / True)

        Invariant: Status is 'AUTO' if and only if ALL 4 conditions pass.
        In all other 15 states, status is 'NEEDS_REVIEW', and reasons contains
        EXACTLY the set of failing conditions.
        """
        threshold = 85.0

        for agreement, high_conf, valid_fmt, fallback_used in itertools.product(
            [True, False], [True, False], [True, False], [True, False]
        ):
            conf_val = 90.0 if high_conf else 80.0

            expected_reasons: list[str] = []
            if not agreement:
                expected_reasons.append(ReviewReasonCode.MODEL_DISAGREEMENT)
            if not high_conf:
                expected_reasons.append(ReviewReasonCode.LOW_CHAR_CONFIDENCE)
            if not valid_fmt:
                expected_reasons.append(ReviewReasonCode.INVALID_FORMAT)
            if fallback_used:
                expected_reasons.append(ReviewReasonCode.NO_DETECTION_RETRY)

            expected_status = "AUTO" if not expected_reasons else "NEEDS_REVIEW"

            status_res, reasons = evaluate_review_policy(
                model_agreement=agreement,
                min_char_confidence=conf_val,
                threshold=threshold,
                is_valid_format=valid_fmt,
                used_detection_fallback=fallback_used,
            )

            assert status_res == expected_status, (
                f"Failed status for state ({agreement}, {high_conf}, {valid_fmt}, {fallback_used})"
            )
            assert sorted(reasons) == sorted(expected_reasons), (
                f"Reasons mismatch for state ({agreement}, {high_conf}, {valid_fmt}, {fallback_used}): "
                f"expected {expected_reasons}, got {reasons}"
            )


# ==============================================================================
# SECTION 4: ROBUSTNESS & FUZZING ON BOUNDARY MALFORMED INPUTS
# ==============================================================================


class TestRobustnessAndBoundaryFuzzing:
    """
    Stress-tests plate validation and correction functions against boundary,
    malformed, degenerate, and boundary inputs to verify no unexpected crashes.
    """

    @pytest.mark.parametrize(
        "bad_input",
        [
            "",
            "   ",
            "\t\n\r",
            "None",
            "null",
            "NaN",
            "123",
            "ABC",
            "!@#$%^&*()_+",
            "<script>alert('xss')</script>",
            "SELECT * FROM vehicle;",
            "A" * 1000,
            "51K" + "9" * 500,
            "51K-BÍCH-12345",  # Accented Vietnamese
            "🚗🛵🚙",  # Emojis
        ],
    )
    def test_boundary_inputs_do_not_crash(self, bad_input: str) -> None:
        """Verifies that none of the functions raise unhandled exceptions on extreme inputs."""
        assert is_valid_vietnamese_plate(bad_input) is False
        corrected, corrs = correct_plate_characters(bad_input)
        assert isinstance(corrected, str)
        assert isinstance(corrs, list)

    def test_none_input_gracefully_handled(self) -> None:
        """Verifies type safety when None is passed as plate string."""
        assert is_valid_vietnamese_plate(None) is False  # type: ignore[arg-type]
        corrected, corrs = correct_plate_characters(None)  # type: ignore[arg-type]
        assert corrected == ""
        assert corrs == []


# ==============================================================================
# SECTION 5: API END-TO-END SCAN INTEGRATION BOUNDARY STRESS
# ==============================================================================


@pytest.mark.django_db
class TestPlateScanAPIBoundaryIntegration:
    """
    Integration tests on POST /api/v1/parking/plate-scans/ with mocked OCR outputs
    to verify payload serialization, review_status, review_reasons, corrections, and suggestions.
    """

    @pytest.fixture(autouse=True)
    def setup_client(self) -> None:
        self.client = APIClient()
        self.user = Account.objects.create_user(
            email="stress_officer@parking.local",
            password="TestPassword123!",
            role="EMPLOYEE",
            is_active=True,
        )
        self.client.force_authenticate(user=self.user)

    def _create_test_image(self) -> io.BytesIO:
        img = Image.new("RGB", (640, 480), color=(128, 128, 128))
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)
        buf.name = "test_plate.jpg"
        return buf

    def test_scan_api_auto_review_response_contract(self) -> None:
        """
        When OCR produces high confidence, agreement, valid plate, no fallback:
        API response MUST have review_status = 'AUTO', review_reasons = [], and empty corrections.
        """
        mock_cand = PlateCandidate(
            plate_text="51K-992.14",
            plate_normalized="51K99214",
            confidence=98.5,
            bounding_box=None,
            char_confidences=[99.0, 98.5, 99.1, 98.0, 98.4, 98.0, 99.2, 98.7],
            min_char_confidence=98.0,
        )
        mock_result = PlateScanResult(
            candidates=[mock_cand],
            best_candidate=mock_cand,
            engine_name="dual_ensemble",
            raw_text="51K-992.14",
            latency_ms=35.0,
            model_agreement=True,
            used_detection_fallback=False,
        )

        with patch("apps.parking.views.scans.get_plate_recognizer") as mock_get_rec:
            mock_rec = MagicMock()
            mock_rec.recognize.return_value = mock_result
            mock_rec.preset_result = None
            mock_get_rec.return_value = mock_rec

            image_file = self._create_test_image()
            resp = self.client.post(
                "/api/v1/parking/plate-scans/",
                data={"image": image_file},
                format="multipart",
            )

            assert resp.status_code == status.HTTP_200_OK, resp.data
            data = resp.data
            assert data["review_status"] == "AUTO"
            assert data["review_reasons"] == []
            assert data["corrections"] == []
            assert data["best_candidate"]["plate_normalized"] == "51K99214"
            assert data["best_candidate"]["min_char_confidence"] == 98.0

    def test_scan_api_needs_review_with_reasons_and_corrections(self) -> None:
        """
        When OCR produces a plate requiring correction (5DZ-1630) with low confidence:
        API response MUST have:
        1. review_status = 'NEEDS_REVIEW'
        2. review_reasons containing LOW_CHAR_CONFIDENCE
        3. corrections list containing the position-1 D->0 fix
        """
        mock_cand = PlateCandidate(
            plate_text="5DZ-1630",
            plate_normalized="5DZ1630",
            confidence=80.0,
            bounding_box=None,
            char_confidences=[95.0, 65.0, 92.0, 90.0, 89.0, 91.0, 92.0],
            min_char_confidence=65.0,  # Below 85.0 threshold
        )
        mock_result = PlateScanResult(
            candidates=[mock_cand],
            best_candidate=mock_cand,
            engine_name="dual_ensemble",
            raw_text="5DZ-1630",
            latency_ms=42.0,
            model_agreement=True,
            used_detection_fallback=False,
        )

        with patch("apps.parking.views.scans.get_plate_recognizer") as mock_get_rec:
            mock_rec = MagicMock()
            mock_rec.recognize.return_value = mock_result
            mock_rec.preset_result = None
            mock_get_rec.return_value = mock_rec

            image_file = self._create_test_image()
            resp = self.client.post(
                "/api/v1/parking/plate-scans/",
                data={"image": image_file},
                format="multipart",
            )

            assert resp.status_code == status.HTTP_200_OK, resp.data
            data = resp.data
            assert data["review_status"] == "NEEDS_REVIEW"
            assert ReviewReasonCode.LOW_CHAR_CONFIDENCE in data["review_reasons"]
            assert len(data["corrections"]) == 1
            corr = data["corrections"][0]
            assert corr["position"] == 1
            assert corr["original_char"] == "D"
            assert corr["corrected_char"] == "0"
            assert corr["rule"] == "province_second_digit_fix"

    def test_scan_api_empty_form_returns_400_prop_4_5_1_p02(self) -> None:
        """Leftover c verification: empty form returns 400 Bad Request with PROP-4.5.1-P02."""
        resp = self.client.post("/api/v1/parking/plate-scans/", data={})
        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["code"] == "PROP-4.5.1-P02"
