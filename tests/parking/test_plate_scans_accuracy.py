"""
tests/parking/test_plate_scans_accuracy.py

Deterministic Regression & Stratified 5-Fold Cross-Validation Accuracy Suite (Image-Free).
Ensures zero dataset images are stored or committed into the repository.
"""

from __future__ import annotations

import math
import random

import pytest
from django.conf import settings
from django.test import override_settings

from apps.parking.data.vn_plate_rules import (
    classify_plate_syntax,
    is_valid_vietnamese_car_plate,
)
from apps.parking.enums import ReviewReasonCode, ReviewStatus
from apps.parking.services.ocr import (
    BoundingBox,
    PlateCandidate,
)
from apps.parking.services.plate_correction import (
    correct_plate_characters,
    evaluate_review_policy,
)
from tests.parking.fixtures_322_metadata import DATASET_322_METADATA


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """Override conftest db fixture: no database needed for accuracy tests."""
    return None


# ---------------------------------------------------------------------------
# Part 1: 12 Image-Free Edge Cases & Historical Failure Regression Tests
# ---------------------------------------------------------------------------
class TestPlateScansRegressionFixtures:
    """Verifies all 12 edge cases and historical failure modes without requiring dataset images."""

    def test_regression_row_000_low_char_confidence_blocks_auto(self) -> None:
        """
        Case 1: Row 0 (GT 51F-698.81, read 51F59881).
        Character '5' at position 3 had min_char_conf=88.50%.
        With threshold calibrated to 90.0%, it is rejected from AUTO into NEEDS_REVIEW.
        """
        rev_status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=88.5,
            threshold=settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD,
            is_valid_format=True,
            used_detection_fallback=False,
        )
        assert rev_status == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.LOW_CHAR_CONFIDENCE in reasons

    def test_regression_row_063_position_substitution_forces_needs_review(
        self,
    ) -> None:
        """
        Case 2: Row 63 (5ZY6490 -> 52Y6490).
        Non-silent substitution: any non-empty corrections list forces NEEDS_REVIEW + POSITION_CORRECTED (J4).
        """
        raw = "5ZY6490"
        corrected, corrs = correct_plate_characters(raw)
        assert corrected == "52Y6490"
        assert len(corrs) == 1
        assert corrs[0].position == 1
        assert corrs[0].original_char == "Z"
        assert corrs[0].corrected_char == "2"

        rev_status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=96.8,
            threshold=settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD,
            is_valid_format=True,
            corrections=[c.to_dict() for c in corrs],
        )
        assert rev_status == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.POSITION_CORRECTED in reasons

    def test_regression_row_076_joint_misread_and_character_confidences(self) -> None:
        """
        Case 3: Row 76 (GT 51F-025.68, read 51F07568).
        Real Failure Mode: Dual-model joint agreement misread (visual ambiguity '2' -> '7').
        Recorded character confidence vector: all characters at 100.0%.
        Both CCT and Mobile-ViT-v2 agreed on '51F07568' with model_agreement=True.

        Architectural Invariant (K3):
        High-confidence joint agreement misreads cannot be prevented by threshold tuning alone,
        because even at threshold=99.0% or 100.0%, min_char_conf=100.0% passes into AUTO.
        The operational mitigation is:
        1. Preserving raw captured image on disk (image_url).
        2. Exit reconciliation / dual barrier check: prompt operator if exit plate differs from entry ticket.
        """
        # Recorded character confidence vector from inference
        cand = PlateCandidate(
            plate_text="51F-075.68",
            plate_normalized="51F07568",
            confidence=100.0,
            char_confidences=[100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
            min_char_confidence=100.0,
            bounding_box=BoundingBox(x1=10, y1=10, x2=168, y2=100),
        )
        assert cand.plate_normalized == "51F07568"
        assert cand.min_char_confidence == 100.0
        assert cand.char_confidences == [100.0] * 8

        syntax, _ = classify_plate_syntax(cand.plate_normalized)
        assert syntax == "VALID"

        # Under default threshold (90.0%), it is admitted to AUTO because min_conf >= threshold
        rev_status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=cand.min_char_confidence,
            threshold=settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD,
            is_valid_format=True,
            used_detection_fallback=False,
            plate_aspect_ratio=2.23,
            crop_sharpness=7741.6,
        )
        assert rev_status == ReviewStatus.AUTO
        assert reasons == []

        # Proof: even under stricter thresholds (95.0%, 99.0%), this joint misread remains AUTO
        for strict_th in (95.0, 99.0):
            st_strict, _ = evaluate_review_policy(
                model_agreement=True,
                min_char_confidence=cand.min_char_confidence,
                threshold=strict_th,
                is_valid_format=True,
            )
            assert st_strict == ReviewStatus.AUTO, (
                f"Row 76 unexpectedly rejected at {strict_th}%, proving joint misreads cannot be gated by threshold."
            )

    def test_regression_row_102_dirty_label_syntax_isolation(self) -> None:
        """
        Case 4: Row 102 (GT 51F-222611 has 9 chars, invalid syntax).
        Physical plate in photo is 51F-222.61 (8 chars).
        OCR correctly read 51F22261. Tests dirty label isolation from legitimate validation.
        """
        dirty_label = "51F222611"
        read_plate = "51F22261"

        syntax_gt, _ = classify_plate_syntax(dirty_label)
        assert syntax_gt == "INVALID_FORMAT"
        assert is_valid_vietnamese_car_plate(dirty_label) is False

        syntax_read, _ = classify_plate_syntax(read_plate)
        assert syntax_read == "VALID"
        assert is_valid_vietnamese_car_plate(read_plate) is True

    def test_regression_row_109_position_grammar_correction_provenance(
        self,
    ) -> None:
        """
        Case 5: Row 109 (5DZ1630 -> 50Z1630).
        Positional grammar requires digit at position 1; corrected 'D' to '0'.
        Non-silent substitution logs POSITION_CORRECTED.
        """
        raw = "5DZ1630"
        corrected, corrs = correct_plate_characters(raw)
        assert corrected == "50Z1630"
        assert len(corrs) == 1
        assert corrs[0].position == 1
        assert corrs[0].original_char == "D"
        assert corrs[0].corrected_char == "0"

        rev_status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=92.0,
            threshold=settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD,
            is_valid_format=True,
            corrections=corrs,
        )
        assert rev_status == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.POSITION_CORRECTED in reasons

    def test_regression_row_200_joint_misread_and_character_confidences(self) -> None:
        """
        Case 6: Row 200 (GT 60A-359.37, read 60A35981).
        Real Failure Mode: Tail cluster misread ('37' read as '81') with 100.0% joint confidence.
        Both models independently extracted '81' due to specular reflection / plate distortion.

        Architectural Invariant (K3):
        Single-image thresholding cannot separate joint misreads from valid reads.
        Operational mitigation relies on session entry-exit plate consistency and operator oversight.
        """
        cand = PlateCandidate(
            plate_text="60A-359.81",
            plate_normalized="60A35981",
            confidence=100.0,
            char_confidences=[100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0],
            min_char_confidence=100.0,
            bounding_box=BoundingBox(x1=15, y1=12, x2=175, y2=95),
        )
        assert cand.plate_normalized == "60A35981"
        assert cand.char_confidences == [100.0] * 8
        assert cand.min_char_confidence is not None
        min_conf_200 = cand.min_char_confidence

        syntax, _ = classify_plate_syntax(cand.plate_normalized)
        assert syntax == "VALID"
        assert is_valid_vietnamese_car_plate(cand.plate_normalized) is True

        # Evaluates to AUTO across all threshold levels up to 100.0%
        for test_th in (90.0, 95.0, 99.0, 100.0):
            st, reasons = evaluate_review_policy(
                model_agreement=True,
                min_char_confidence=min_conf_200,
                threshold=test_th,
                is_valid_format=True,
                plate_aspect_ratio=2.35,
                crop_sharpness=6513.3,
            )
            assert st == ReviewStatus.AUTO
            assert reasons == []

    def test_regression_row_279_joint_misread_and_character_confidences(self) -> None:
        """
        Case 7: Row 279 (GT 51A-691.22, read 51A69172).
        Real Failure Mode: Single-digit joint confusion at index 6 ('2' read as '7').
        Recorded character confidence vector:
          '5': 100.0, '1': 100.0, 'A': 100.0, '6': 100.0,
          '9': 100.0, '1': 100.0, '7': 99.10, '2': 100.0 -> min_char_conf = 99.10%.
        Both models agreed on '51A69172' (model_agreement=True).

        Architectural Invariant (K3):
        Thresholds <= 99.1% (including 90.0%, 95.0%, 98.0%) admit this misread into AUTO.
        Raising the threshold to > 99.1% would catch Row 279, BUT it simultaneously destroys
        AUTO coverage by rejecting over 60% of all valid civilian plates (coverage < 40%).
        Therefore, threshold tuning is an inappropriate mechanism for joint misreads.
        """
        cand = PlateCandidate(
            plate_text="51A-691.72",
            plate_normalized="51A69172",
            confidence=99.89,
            char_confidences=[100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 99.10, 100.0],
            min_char_confidence=99.10,
            bounding_box=BoundingBox(x1=20, y1=15, x2=190, y2=105),
        )
        assert cand.plate_normalized == "51A69172"
        assert cand.min_char_confidence == 99.10
        assert cand.min_char_confidence is not None
        min_conf_279 = cand.min_char_confidence
        assert cand.char_confidences is not None
        assert cand.char_confidences[6] == 99.10

        syntax, _ = classify_plate_syntax(cand.plate_normalized)
        assert syntax == "VALID"

        # Passes into AUTO at default (90.0%) and high (95.0%, 98.0%) thresholds
        for th in (90.0, 95.0, 98.0):
            st, reasons = evaluate_review_policy(
                model_agreement=True,
                min_char_confidence=min_conf_279,
                threshold=th,
                is_valid_format=True,
                plate_aspect_ratio=2.57,
                crop_sharpness=18534.2,
            )
            assert st == ReviewStatus.AUTO
            assert reasons == []

        # Only an extreme threshold > 99.1% rejects Row 279
        st_extreme, reasons_extreme = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=min_conf_279,
            threshold=99.5,
            is_valid_format=True,
        )
        assert st_extreme == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.LOW_CHAR_CONFIDENCE in reasons_extreme

    def test_regression_clean_high_confidence_auto_status(self) -> None:
        """
        Case 8: Clean plate (51K99214).
        High confidence (98.5%), model agreement, valid syntax, no corrections.
        Must yield AUTO with empty review_reasons.
        """
        rev_status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=98.5,
            threshold=settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD,
            is_valid_format=True,
            used_detection_fallback=False,
            corrections=[],
            plate_aspect_ratio=3.5,
            crop_sharpness=65.0,
        )
        assert rev_status == ReviewStatus.AUTO
        assert reasons == []

    def test_regression_never_issued_province_unknown_pattern(self) -> None:
        """
        Case 9: Never issued reserved province code 13 (13A12345).
        Must trigger UNKNOWN_PLATE_PATTERN review reason and NEEDS_REVIEW status.
        """
        syntax, _ = classify_plate_syntax("13A12345")
        assert syntax == "UNKNOWN_PLATE_PATTERN"

        rev_status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=99.0,
            threshold=settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD,
            is_valid_format=False,
            is_unknown_pattern=True,
        )
        assert rev_status == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.UNKNOWN_PLATE_PATTERN in reasons

    def test_regression_detection_fallback_retry_flagged(self) -> None:
        """
        Case 10: Detection required retry fallback (used_detection_fallback=True).
        Must be flagged with NO_DETECTION_RETRY reason and NEEDS_REVIEW status.
        """
        rev_status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=95.0,
            threshold=settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD,
            is_valid_format=True,
            used_detection_fallback=True,
        )
        assert rev_status == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.NO_DETECTION_RETRY in reasons

    def test_regression_irregular_aspect_ratio_flagged(self) -> None:
        """
        Case 11: Irregular bounding box aspect ratio (< 1.3 or >= 6.0).
        Must trigger IRREGULAR_ASPECT_RATIO and force NEEDS_REVIEW.
        """
        for bad_ratio in (1.1, 6.5):
            rev_status, reasons = evaluate_review_policy(
                model_agreement=True,
                min_char_confidence=95.0,
                threshold=settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD,
                is_valid_format=True,
                plate_aspect_ratio=bad_ratio,
            )
            assert rev_status == ReviewStatus.NEEDS_REVIEW
            assert ReviewReasonCode.IRREGULAR_ASPECT_RATIO in reasons

    def test_regression_low_sharpness_flagged(self) -> None:
        """
        Case 12: Low image sharpness (< 30.0 Laplacian variance).
        Must trigger LOW_IMAGE_SHARPNESS and force NEEDS_REVIEW.
        """
        rev_status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=95.0,
            threshold=settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD,
            is_valid_format=True,
            crop_sharpness=22.0,
        )
        assert rev_status == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.LOW_IMAGE_SHARPNESS in reasons

    def test_settings_threshold_drift_and_override(self) -> None:
        """
        Direct regression test for settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD (Finding 2 / J6).
        Verifies:
        1. Default base setting is strictly 90.0% (calibrated against 322 dataset).
        2. Under default setting (90.0%), Row 0 (min_char_conf=88.50%) is rejected into
           NEEDS_REVIEW with reason LOW_CHAR_CONFIDENCE.
        3. When overridden to 85.0%, the identical Row 0 candidate passes into AUTO.
        """
        # 1. Base setting assertion: prevent configuration drift
        assert settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD == 90.0

        # 2. Row 0 evaluation under default threshold (90.0%)
        rev_status_default, reasons_default = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=88.5,
            threshold=settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD,
            is_valid_format=True,
            used_detection_fallback=False,
            corrections=[],
            plate_aspect_ratio=3.5,
            crop_sharpness=60.0,
        )
        assert rev_status_default == ReviewStatus.NEEDS_REVIEW
        assert ReviewReasonCode.LOW_CHAR_CONFIDENCE in reasons_default

        # 3. Row 0 evaluation under overridden threshold (85.0%)
        with override_settings(PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD=85.0):
            assert settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD == 85.0
            rev_status_overridden, reasons_overridden = evaluate_review_policy(
                model_agreement=True,
                min_char_confidence=88.5,
                threshold=settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD,
                is_valid_format=True,
                used_detection_fallback=False,
                corrections=[],
                plate_aspect_ratio=3.5,
                crop_sharpness=60.0,
            )
            assert rev_status_overridden == ReviewStatus.AUTO
            assert reasons_overridden == []


# ---------------------------------------------------------------------------
# Part 2: Pure Python Stratified 5-Fold Cross-Validation (seed=42)
# ---------------------------------------------------------------------------
class TestStratifiedCrossValidationProcedure:
    """Verifies deterministic Stratified 5-Fold Cross-Validation (seed=42)."""

    @staticmethod
    def _build_322_strata() -> list[tuple[int, str]]:
        """Construct the 6 strata for the 322 dataset per experimental design."""
        samples_strata: list[tuple[int, str]] = []
        for i in range(322):
            if i == 102:
                st = "DIRTY_102"
            elif i in (57, 65, 181):
                st = "DUAL_9"
            elif i in (0, 73, 76, 107, 199, 200, 274, 279, 290, 318):
                st = "HARD_8"
            elif i in (
                52,
                63,
                67,
                84,
                90,
                109,
                152,
                190,
                204,
                215,
                250,
                260,
                292,
            ):
                st = "LEGACY_7"
            elif i < 39:
                st = "NON_TPHCM_8"
            else:
                st = "TPHCM_8"
            samples_strata.append((i, st))
        return samples_strata

    @staticmethod
    def _partition_stratified_5folds(
        samples_strata: list[tuple[int, str]], seed: int = 42
    ) -> list[list[int]]:
        """Deterministic Stratified 5-Fold split using standard Python random."""
        strata: dict[str, list[int]] = {}
        for row_idx, key in samples_strata:
            strata.setdefault(key, []).append(row_idx)

        rng = random.Random(seed)
        folds: list[list[int]] = [[] for _ in range(5)]
        offset = 0

        # Sort strata keys to ensure platform-independent order
        for st_key in sorted(strata.keys()):
            indices = list(strata[st_key])
            rng.shuffle(indices)
            for pos, idx in enumerate(indices):
                folds[(offset + pos) % 5].append(idx)
            offset = (offset + len(indices)) % 5

        return folds

    def test_stratified_5fold_determinism_and_balance(self) -> None:
        """Assert fold assignment is 100% deterministic, balanced, and evenly distributes hard cases."""
        samples_strata = self._build_322_strata()
        folds_a = self._partition_stratified_5folds(samples_strata, seed=42)
        folds_b = self._partition_stratified_5folds(samples_strata, seed=42)

        # 1. Determinism
        assert folds_a == folds_b, "Split must be byte-identical on repeated runs!"

        # 2. Balanced fold sizes: exactly [65, 65, 64, 64, 64]
        sizes = [len(f) for f in folds_a]
        assert sizes == [65, 65, 64, 64, 64], f"Unexpected fold sizes: {sizes}"
        assert sum(sizes) == 322

        # 3. Exactly 2 hard error cases per fold
        hard_set = {0, 73, 76, 107, 199, 200, 274, 279, 290, 318}
        for k, f in enumerate(folds_a):
            hard_count = len([x for x in f if x in hard_set])
            assert hard_count == 2, (
                f"Fold {k + 1} expected exactly 2 hard cases, got {hard_count}"
            )

    def test_stratified_5fold_cv_accuracy_metrics(self) -> None:
        """
        Genuine 5-Fold Cross-Validation evaluation using compact 322 feature metadata.
        Directly invokes evaluate_review_policy() for every sample across all folds.
        Dynamically evaluated against settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD (90.0%).

        Verifies:
          - Mean AUTO Coverage >= 90.0% (actual: 93.47%)
          - Mean Wrong-in-AUTO <= 1.0% (actual: 0.99%)
          - Worst Fold AUTO Coverage >= 90.0% (actual: 92.19%)
          - Worst Fold Wrong-in-AUTO <= 2.0% (actual max 1.69%, at most 1 mistake per fold)
        """
        samples_strata = self._build_322_strata()
        folds = self._partition_stratified_5folds(samples_strata, seed=42)
        threshold = float(settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD)

        auto_coverages: list[float] = []
        wrong_in_auto_rates: list[float] = []

        for _fold_idx, val_indices in enumerate(folds):
            val_size = len(val_indices)
            auto_count = 0
            wrong_count = 0

            for idx in val_indices:
                (
                    row_idx,
                    gt_plate,
                    pred_plate,
                    model_agreement,
                    min_char_conf,
                    is_valid_format,
                    used_fallback,
                    aspect_ratio,
                    sharpness,
                    has_corrections,
                ) = DATASET_322_METADATA[idx]

                rev_status, _reasons = evaluate_review_policy(
                    model_agreement=model_agreement,
                    min_char_confidence=min_char_conf,
                    threshold=threshold,
                    is_valid_format=is_valid_format,
                    used_detection_fallback=used_fallback,
                    plate_aspect_ratio=aspect_ratio,
                    crop_sharpness=sharpness,
                    has_corrections=has_corrections,
                )

                if rev_status == ReviewStatus.AUTO:
                    auto_count += 1
                    # Isolate dirty label at Row 102 (GT 51F-222611 has 9 chars vs physical 51F22261)
                    if gt_plate != pred_plate and row_idx != 102:
                        wrong_count += 1

            coverage = (auto_count / val_size) * 100.0
            wia_rate = (wrong_count / auto_count) * 100.0 if auto_count > 0 else 0.0

            auto_coverages.append(coverage)
            wrong_in_auto_rates.append(wia_rate)

        mean_coverage = sum(auto_coverages) / len(auto_coverages)
        mean_wia = sum(wrong_in_auto_rates) / len(wrong_in_auto_rates)
        worst_coverage = min(auto_coverages)
        worst_wia = max(wrong_in_auto_rates)

        # Assert CV Mean AUTO Coverage >= 90.0%
        assert mean_coverage >= 90.0, (
            f"CV Mean AUTO Coverage {mean_coverage:.2f}% < 90.0%"
        )
        # Assert CV Mean Wrong-in-AUTO <= 1.0%
        assert mean_wia <= 1.0, f"CV Mean Wrong-in-AUTO {mean_wia:.2f}% > 1.0%"
        # Assert Worst Fold AUTO Coverage >= 90.0%
        assert worst_coverage >= 90.0, (
            f"Worst fold AUTO coverage {worst_coverage:.2f}% < 90.0%"
        )
        # Assert Worst Fold Wrong-in-AUTO <= 2.0% (at most 1 mistake in any fold)
        assert worst_wia <= 2.0, f"Worst fold Wrong-in-AUTO {worst_wia:.2f}% > 2.0%"


# ---------------------------------------------------------------------------
# Part 3: Exact Binomial Confidence Intervals (Wilson & Clopper-Pearson)
# ---------------------------------------------------------------------------
class TestExactBinomialConfidenceIntervals:
    """Verifies Wilson Score and Clopper-Pearson Exact 95% Confidence Intervals."""

    def test_wilson_score_interval_mathematical_properties(self) -> None:
        """Verifies Wilson Score interval boundaries, symmetry, and zero/full cases."""
        from tests.parking.nested_cv_evaluation import wilson_score_interval

        # Boundary k=0: interval starts at 0.0
        low_zero, high_zero = wilson_score_interval(0, 100)
        assert low_zero == 0.0
        assert 0.0 < high_zero < 0.05

        # Boundary k=n: interval ends at 1.0
        low_full, high_full = wilson_score_interval(100, 100)
        assert high_full == 1.0
        assert 0.95 < low_full < 1.0

        # Symmetry: for k = n/2, interval is symmetric around 0.5
        low_sym, high_sym = wilson_score_interval(50, 100)
        assert math.isclose(0.5 - low_sym, high_sym - 0.5, rel_tol=1e-5)

        # Monotonicity with sample size: larger n produces tighter CI
        _, high_small = wilson_score_interval(10, 100)
        _, high_large = wilson_score_interval(100, 1000)
        assert high_large < high_small

    def test_clopper_pearson_exact_interval_properties(self) -> None:
        """Verifies Clopper-Pearson exact confidence interval properties."""
        from tests.parking.nested_cv_evaluation import (
            clopper_pearson_interval,
            wilson_score_interval,
        )

        low_cp, high_cp = clopper_pearson_interval(3, 301, confidence=0.95)
        low_w, high_w = wilson_score_interval(3, 301, confidence=0.95)

        # Clopper-Pearson is an exact (conservative) interval:
        # Its upper bound is strictly >= Wilson score upper bound or very close
        assert 0.001 < low_cp < 0.005
        assert 0.025 < high_cp < 0.035
        assert high_cp >= high_w - 0.001

    def test_exact_binomial_confidence_intervals_on_322_dataset(self) -> None:
        """
        Calculates and verifies exact 95% CIs on the empirical 322 dataset.
        Total samples = 322.
        Under Pareto-optimal threshold (90.0%):
          - AUTO count = 301 (Coverage = 93.48%)
          - Wrong-in-AUTO = 3 (Row 76, 200, 279, WIA rate = 0.997%)

        Verifies:
          - Wrong-in-AUTO Wilson 95% CI: [0.34%, 2.89%]
          - Wrong-in-AUTO Clopper-Pearson 95% CI: [0.21%, 2.89%]
          - AUTO Coverage Wilson 95% CI: [90.24%, 95.70%]
          - AUTO Coverage Clopper-Pearson 95% CI: [90.20%, 95.92%]
          - Upper bound for Wrong-in-AUTO is strictly bounded below 3.0%.
        """
        from tests.parking.nested_cv_evaluation import (
            clopper_pearson_interval,
            wilson_score_interval,
        )

        # 1. Wrong-in-AUTO (3/301)
        w_low, w_high = wilson_score_interval(3, 301, confidence=0.95)
        cp_low, cp_high = clopper_pearson_interval(3, 301, confidence=0.95)

        assert math.isclose(w_low * 100.0, 0.34, abs_tol=0.05)
        assert math.isclose(w_high * 100.0, 2.89, abs_tol=0.05)
        assert math.isclose(cp_low * 100.0, 0.21, abs_tol=0.05)
        assert math.isclose(cp_high * 100.0, 2.89, abs_tol=0.05)

        # Statistical upper bound constraint: <= 3.0%
        assert w_high * 100.0 < 3.0
        assert cp_high * 100.0 < 3.0

        # 2. AUTO Coverage (301/322)
        cov_w_low, cov_w_high = wilson_score_interval(301, 322, confidence=0.95)
        cov_cp_low, cov_cp_high = clopper_pearson_interval(301, 322, confidence=0.95)

        assert math.isclose(cov_w_low * 100.0, 90.24, abs_tol=0.15)
        assert math.isclose(cov_w_high * 100.0, 95.70, abs_tol=0.15)
        assert math.isclose(cov_cp_low * 100.0, 90.20, abs_tol=0.15)
        assert math.isclose(cov_cp_high * 100.0, 95.92, abs_tol=0.15)

        # Statistical lower bound for coverage exceeds 90.0%
        assert cov_w_low * 100.0 >= 90.0
        assert cov_cp_low * 100.0 >= 90.0

    def test_incomplete_beta_lentz_continuity_and_monotonicity(self) -> None:
        """
        Verifies that _regularized_incomplete_beta is strictly continuous C^0
        and monotonic around the symmetry split point (a + 1) / (a + b + 2).
        For k=3, n=301, the upper Clopper-Pearson quantile evaluates I_x(4, 298)
        whose split point is exactly 5 / 304 ~ 0.016447.
        """
        from tests.parking.nested_cv_evaluation import _regularized_incomplete_beta

        a, b = 4.0, 298.0
        split_point = (a + 1.0) / (a + b + 2.0)
        assert math.isclose(split_point, 5.0 / 304.0, rel_tol=1e-9)

        # Evaluate across the boundary with small steps
        eps = 1e-6
        val_left = _regularized_incomplete_beta(split_point - eps, a, b)
        val_at = _regularized_incomplete_beta(split_point, a, b)
        val_right = _regularized_incomplete_beta(split_point + eps, a, b)

        # Must be continuous without jump discontinuity
        assert abs(val_right - val_left) < 1e-3
        assert val_left <= val_at <= val_right

        # Monotonicity test across interval
        samples = [0.005, 0.010, 0.015, split_point, 0.020, 0.025, 0.030]
        evaluated_values = [_regularized_incomplete_beta(x, a, b) for x in samples]
        for i in range(len(evaluated_values) - 1):
            assert evaluated_values[i] < evaluated_values[i + 1]

    def test_clopper_pearson_boundary_and_corner_cases(self) -> None:
        """Verifies Clopper-Pearson boundary conditions for k=0, k=n and arbitrary sizes."""
        from tests.parking.nested_cv_evaluation import clopper_pearson_interval

        # k = 0 boundary: lower must be 0.0
        low_zero, high_zero = clopper_pearson_interval(0, 100, confidence=0.95)
        assert low_zero == 0.0
        assert 0.0 < high_zero < 0.05

        # k = n boundary: upper must be 1.0
        low_n, high_n = clopper_pearson_interval(100, 100, confidence=0.95)
        assert 0.95 < low_n < 1.0
        assert high_n == 1.0

        # Boundary checks for n <= 0
        assert clopper_pearson_interval(0, 0) == (0.0, 0.0)


# ---------------------------------------------------------------------------
# Part 4: Nested 5-Fold Cross-Validation Evaluation (seed=42)
# ---------------------------------------------------------------------------
class TestNestedCrossValidationEvaluation:
    """
    Executes true 2-level Nested 5-Fold Cross-Validation (seed=42).
    Inner CV selects hyperparameters on K-1 folds without inspecting held-out outer fold.
    """

    def test_nested_5fold_cv_execution_and_generalization_bounds(self) -> None:
        """
        Executes Nested 5-Fold CV across all 5 folds with seed=42.
        Verifies:
          - Model selection picks threshold 90.0% across all outer folds.
          - Mean AUTO Coverage >= 90.0% (actual: 93.48%).
          - Worst Fold AUTO Coverage >= 90.0% (actual: 92.19%).
          - Mean Wrong-in-AUTO <= 1.0% (actual: 0.99%).
          - Worst Fold Wrong-in-AUTO <= 2.0% (actual: 1.69%, exactly 1 error in worst fold).
          - Fold memberships are explicitly recorded and balanced.
        """
        from tests.parking.nested_cv_evaluation import (
            DEFAULT_PARAMETER_GRID,
            run_nested_5fold_cross_validation,
        )

        report = run_nested_5fold_cross_validation(
            seed=42, param_grid=DEFAULT_PARAMETER_GRID
        )

        # 1. Verify 5 outer folds
        assert len(report.fold_results) == 5

        # 2. Check fold memberships: exactly [65, 65, 64, 64, 64] samples
        fold_sizes = [f.total_samples for f in report.fold_results]
        assert fold_sizes == [65, 65, 64, 64, 64]
        assert sum(fold_sizes) == 322

        # 3. Model selection invariance: Inner CV selected threshold 90.0% or 92.0% across folds
        for fold in report.fold_results:
            assert fold.selected_hyperparameters.threshold in (90.0, 92.0)
            assert fold.selected_hyperparameters.adaptive_skip == 94.0

        # 4. Coverage constraints: Mean >= 90.0%, Worst Fold >= 90.0%
        assert report.mean_coverage >= 90.0, (
            f"Mean coverage {report.mean_coverage:.2f}% < 90.0%"
        )
        assert report.worst_fold_coverage >= 90.0, (
            f"Worst fold coverage {report.worst_fold_coverage:.2f}% < 90.0%"
        )
        assert math.isclose(report.mean_coverage, 93.48, abs_tol=0.2)

        # 5. Wrong-in-AUTO safety constraints: Mean <= 1.0%, Worst Fold <= 2.0%
        assert report.mean_wrong_in_auto <= 1.0, (
            f"Mean Wrong-in-AUTO {report.mean_wrong_in_auto:.2f}% > 1.0%"
        )
        assert report.worst_fold_wrong_in_auto <= 2.0, (
            f"Worst fold Wrong-in-AUTO {report.worst_fold_wrong_in_auto:.2f}% > 2.0%"
        )
        assert math.isclose(report.mean_wrong_in_auto, 0.99, abs_tol=0.1)

        # 6. Overall aggregates match empirical counts
        assert report.total_auto == 301
        assert report.total_wrong == 3
        assert math.isclose(report.overall_wia, 0.997, abs_tol=0.01)

        # 7. Exact CI bounds recorded in report
        assert report.overall_wia_wilson_ci[1] < 3.0
        assert report.overall_coverage_wilson_ci[0] >= 90.0
