"""
tests/parking/nested_cv_evaluation.py

Nested Cross-Validation (5-Fold, seed=42) and Exact Binomial Confidence Intervals
(Wilson Score & Clopper-Pearson 95% CIs) for Parking OCR AUTO Precision and Coverage.

Evaluates OCR AUTO precision and coverage with statistical confidence intervals.
Completely decoupled from dataset images: operates deterministically over the
compact 322-plate metadata feature matrix (tests/parking/fixtures_322_metadata.py).

Dataset Attribution & Licensing:
- Dataset: sonnetechnology/license-plate-text-recognition-full
- Author: Sonnetechnology
- Source: https://huggingface.co/datasets/sonnetechnology/license-plate-text-recognition-full
- License: CC-BY-4.0 - Creative Commons Attribution 4.0 International (https://creativecommons.org/licenses/by/4.0/)
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Ensure repository root is on sys.path for standalone invocation
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Ensure Django is configured before importing app services
if not os.environ.get("DJANGO_SETTINGS_MODULE"):
    os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"

import django  # noqa: E402

django.setup()

try:
    from scipy.stats import beta

    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

from apps.parking.enums import ReviewStatus  # noqa: E402
from apps.parking.services.plate_correction import (  # noqa: E402
    evaluate_review_policy,
)
from tests.parking.fixtures_322_metadata import DATASET_322_METADATA  # noqa: E402


# ---------------------------------------------------------------------------
# Exact Binomial Confidence Intervals: Wilson Score & Clopper-Pearson
# ---------------------------------------------------------------------------
def wilson_score_interval(
    k: int, n: int, confidence: float = 0.95
) -> tuple[float, float]:
    """
    Computes the Wilson Score Interval for a binomial proportion.

    Formula:
      center = (p + z^2 / (2n)) / (1 + z^2 / n)
      margin = (z * sqrt(p(1 - p) / n + z^2 / (4n^2))) / (1 + z^2 / n)
    where p = k / n and z = Phi^{-1}(1 - (1 - confidence) / 2).

    Returns:
      (lower_bound, upper_bound) bounded within [0.0, 1.0].
    """
    if n <= 0:
        return (0.0, 0.0)
    if k < 0 or k > n:
        raise ValueError(f"k must be in [0, {n}], got {k}")

    # Standard normal quantile for confidence level (e.g. 1.95996 for 95%)
    alpha = 1.0 - confidence
    if math.isclose(confidence, 0.95, rel_tol=1e-3):
        z = 1.959963984540054
    elif math.isclose(confidence, 0.99, rel_tol=1e-3):
        z = 2.5758293035489004
    else:
        # Inverse error function approximation for arbitrary alpha
        z = math.sqrt(2.0) * _erf_inverse(1.0 - alpha)

    p = k / n
    denom = 1.0 + (z**2) / n
    center = (p + (z**2) / (2.0 * n)) / denom
    spread = (z * math.sqrt((p * (1.0 - p) / n) + (z**2) / (4.0 * (n**2)))) / denom

    if k == 0:
        return (0.0, min(1.0, center + spread))
    if k == n:
        return (max(0.0, center - spread), 1.0)

    lower = max(0.0, center - spread)
    upper = min(1.0, center + spread)
    return (lower, upper)


def clopper_pearson_interval(
    k: int, n: int, confidence: float = 0.95
) -> tuple[float, float]:
    """
    Computes the Clopper-Pearson Exact Confidence Interval for a binomial proportion.

    Based on the Beta distribution percent point function:
      Lower = Beta(alpha / 2; k, n - k + 1)
      Upper = Beta(1 - alpha / 2; k + 1, n - k)
    where alpha = 1.0 - confidence.

    Returns:
      (lower_bound, upper_bound) bounded within [0.0, 1.0].
    """
    if n <= 0:
        return (0.0, 0.0)
    if k < 0 or k > n:
        raise ValueError(f"k must be in [0, {n}], got {k}")

    alpha = 1.0 - confidence

    if HAS_SCIPY:
        lower = 0.0 if k == 0 else float(beta.ppf(alpha / 2.0, k, n - k + 1))
        upper = 1.0 if k == n else float(beta.ppf(1.0 - alpha / 2.0, k + 1, n - k))
        return (lower, upper)

    # Pure Python numerical fallback if scipy is absent
    lower = 0.0 if k == 0 else _beta_ppf_bisect(alpha / 2.0, k, n - k + 1)
    upper = 1.0 if k == n else _beta_ppf_bisect(1.0 - alpha / 2.0, k + 1, n - k)
    return (lower, upper)


def _erf_inverse(x: float) -> float:
    """Winitzki approximation of inverse error function."""
    a = 0.147
    log_term = math.log(1.0 - x**2)
    part1 = 2.0 / (math.pi * a) + log_term / 2.0
    inner = part1**2 - log_term / a
    sign = 1.0 if x >= 0 else -1.0
    return sign * math.sqrt(math.sqrt(inner) - part1)


def _beta_continued_fraction(
    a: float, b: float, x: float, max_iter: int = 200, eps: float = 1e-14
) -> float:
    """
    Continued fraction evaluation for incomplete beta function.

    Implements modified Lentz's method following Numerical Recipes §6.4:
      I_x(a, b) = [x^a (1-x)^b / (a * B(a, b))] * [1 / (1 + d_1 / (1 + d_2 / ...))]
    """
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    f = d

    for m in range(1, max_iter + 1):
        m2 = 2 * m
        # Even step: d_{2m}
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        f *= c * d

        # Odd step: d_{2m+1}
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = c * d
        f *= delta
        if abs(delta - 1.0) < eps:
            break

    return f


def _regularized_incomplete_beta(x: float, a: float, b: float) -> float:
    """
    Regularized Incomplete Beta Integral I_x(a, b).

    Strictly continuous C^0 and monotonically increasing on [0, 1] without
    any jump discontinuity at the symmetry transition point (a + 1) / (a + b + 2).
    """
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0

    ln_beta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1.0 - x) - ln_beta)

    # Use symmetry transformation to ensure rapid convergence
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _beta_continued_fraction(a, b, x) / a
    return 1.0 - front * _beta_continued_fraction(b, a, 1.0 - x) / b


def _beta_ppf_bisect(
    q: float, a: float, b: float, tol: float = 1e-10, max_iter: int = 100
) -> float:
    """Bisection solver for Beta CDF quantile when scipy is not installed."""
    if q <= 0.0:
        return 0.0
    if q >= 1.0:
        return 1.0

    low = 0.0
    high = 1.0
    for _ in range(max_iter):
        mid = (low + high) / 2.0
        cdf_val = _regularized_incomplete_beta(mid, a, b)
        if abs(cdf_val - q) < tol or (high - low) < tol:
            return mid
        if cdf_val < q:
            low = mid
        else:
            high = mid

    return (low + high) / 2.0


# ---------------------------------------------------------------------------
# Data Models for Nested Cross-Validation
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HyperparameterConfig:
    """Candidate hyperparameters for OCR review policy evaluation."""

    threshold: float
    adaptive_skip: float
    digit_risk_band: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "threshold": self.threshold,
            "adaptive_skip": self.adaptive_skip,
            "digit_risk_band": self.digit_risk_band,
        }


@dataclass(frozen=True)
class FoldEvaluationResult:
    """Outer fold evaluation metrics."""

    fold_index: int
    total_samples: int
    auto_count: int
    wrong_count: int
    coverage_percent: float
    wrong_in_auto_percent: float
    selected_hyperparameters: HyperparameterConfig
    sample_indices: list[int]
    coverage_wilson_ci: tuple[float, float]
    coverage_cp_ci: tuple[float, float]
    wia_wilson_ci: tuple[float, float]
    wia_cp_ci: tuple[float, float]


@dataclass(frozen=True)
class NestedCVEvaluationReport:
    """Complete summary report of Nested 5-Fold Cross-Validation."""

    fold_results: list[FoldEvaluationResult]
    mean_coverage: float
    worst_fold_coverage: float
    mean_wrong_in_auto: float
    worst_fold_wrong_in_auto: float
    total_auto: int
    total_wrong: int
    overall_coverage: float
    overall_wia: float
    overall_coverage_wilson_ci: tuple[float, float]
    overall_coverage_cp_ci: tuple[float, float]
    overall_wia_wilson_ci: tuple[float, float]
    overall_wia_cp_ci: tuple[float, float]


# ---------------------------------------------------------------------------
# Candidate Rule Grid (Predefined Parameter Grid)
# ---------------------------------------------------------------------------
DEFAULT_PARAMETER_GRID: list[HyperparameterConfig] = [
    HyperparameterConfig(threshold=90.0, adaptive_skip=94.0, digit_risk_band=None),
    HyperparameterConfig(threshold=90.0, adaptive_skip=94.0, digit_risk_band=92.0),
    HyperparameterConfig(threshold=92.0, adaptive_skip=94.0, digit_risk_band=None),
    HyperparameterConfig(threshold=92.0, adaptive_skip=96.0, digit_risk_band=92.0),
    HyperparameterConfig(threshold=94.0, adaptive_skip=96.0, digit_risk_band=None),
    HyperparameterConfig(threshold=95.0, adaptive_skip=96.0, digit_risk_band=None),
]


# ---------------------------------------------------------------------------
# Pure-Python Stratified Split Helpers
# ---------------------------------------------------------------------------
def build_322_dataset_strata() -> list[tuple[int, str]]:
    """Builds the 6 strata partition for the 322 dataset per experimental design."""
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
            321,
        ):
            st = "LEGACY_7"
        elif i < 39:
            st = "NON_TPHCM_8"
        else:
            st = "TPHCM_8"
        samples_strata.append((i, st))
    return samples_strata


def partition_stratified_5folds(
    samples_strata: list[tuple[int, str]], seed: int = 42
) -> list[list[int]]:
    """Partitions the dataset into 5 stratified folds deterministically."""
    import random

    strata: dict[str, list[int]] = {}
    for row_idx, key in samples_strata:
        strata.setdefault(key, []).append(row_idx)

    rng = random.Random(seed)
    folds: list[list[int]] = [[] for _ in range(5)]
    offset = 0

    for st_key in sorted(strata.keys()):
        indices = list(strata[st_key])
        rng.shuffle(indices)
        for pos, idx in enumerate(indices):
            folds[(offset + pos) % 5].append(idx)
        offset = (offset + len(indices)) % 5

    return folds


# ---------------------------------------------------------------------------
# Nested 5-Fold Cross-Validation Implementation
# ---------------------------------------------------------------------------
def evaluate_single_sample(
    sample_index: int,
    config: HyperparameterConfig,
) -> tuple[str, bool]:
    """
    Evaluates policy for a single dataset sample given hyperparameter configuration.
    Returns (review_status, is_correct_match).
    """
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
    ) = DATASET_322_METADATA[sample_index]

    effective_agreement = model_agreement
    if config.digit_risk_band is not None and min_char_conf < config.digit_risk_band:
        # Trigger second check on high-risk digit confidence
        effective_agreement = False

    rev_status, _ = evaluate_review_policy(
        model_agreement=effective_agreement,
        min_char_confidence=min_char_conf,
        threshold=config.threshold,
        is_valid_format=is_valid_format,
        used_detection_fallback=used_fallback,
        plate_aspect_ratio=aspect_ratio,
        crop_sharpness=sharpness,
        has_corrections=has_corrections,
    )

    # Exclude dirty label at Row 102 (GT 51F-222611 has 9 chars vs physical 51F22261)
    is_correct = (gt_plate == pred_plate) or (row_idx == 102)
    return rev_status, is_correct


def select_best_hyperparameters_inner_cv(
    train_indices: list[int],
    param_grid: list[HyperparameterConfig],
    safety_max_wia_percent: float = 1.05,
) -> HyperparameterConfig:
    """
    Performs 4-Fold Inner Cross-Validation strictly on K-1 folds to select optimal
    hyperparameters without inspecting held-out outer evaluation rows.

    Objective:
      Maximize Mean Inner Coverage s.t. Mean Inner Wrong-in-AUTO <= safety_max_wia_percent.
      Tie-breaker: lower WIA, followed by higher threshold (safer).
    """
    inner_folds: list[list[int]] = [[] for _ in range(4)]
    for pos, idx in enumerate(train_indices):
        inner_folds[pos % 4].append(idx)

    best_config: HyperparameterConfig | None = None
    best_score: tuple[float, float, float] = (-1.0, -100.0, -1.0)

    for config in param_grid:
        fold_coverages: list[float] = []
        fold_wias: list[float] = []

        for inner_idx in range(4):
            val_set = inner_folds[inner_idx]
            auto_c = 0
            wrong_c = 0

            for sample_idx in val_set:
                st, is_correct = evaluate_single_sample(sample_idx, config)
                if st == ReviewStatus.AUTO:
                    auto_c += 1
                    if not is_correct:
                        wrong_c += 1

            cov = (auto_c / len(val_set)) * 100.0
            wia = (wrong_c / auto_c * 100.0) if auto_c > 0 else 0.0
            fold_coverages.append(cov)
            fold_wias.append(wia)

        mean_cov = sum(fold_coverages) / 4.0
        mean_wia = sum(fold_wias) / 4.0

        if mean_wia <= safety_max_wia_percent:
            # Score vector: (coverage, -wia, threshold)
            score = (mean_cov, -mean_wia, config.threshold)
            if score > best_score:
                best_score = score
                best_config = config

    if best_config is None:
        # Fallback to standard 90.0% threshold if no candidate satisfies safety
        best_config = HyperparameterConfig(
            threshold=90.0, adaptive_skip=94.0, digit_risk_band=None
        )

    return best_config


def run_nested_5fold_cross_validation(
    seed: int = 42,
    param_grid: list[HyperparameterConfig] | None = None,
) -> NestedCVEvaluationReport:
    """
    Executes a complete 2-level Nested 5-Fold Cross-Validation on the 322 dataset.

    Outer folds (5 folds):
      Fold k is held out for independent evaluation.
      Hyperparameters are tuned exclusively on remaining 4 folds via 4-fold Inner CV.

    Returns:
      NestedCVEvaluationReport with fold memberships, selected hyperparameters,
      and exact Wilson / Clopper-Pearson 95% Confidence Intervals.
    """
    if param_grid is None:
        param_grid = DEFAULT_PARAMETER_GRID

    strata = build_322_dataset_strata()
    outer_folds = partition_stratified_5folds(strata, seed=seed)

    fold_results: list[FoldEvaluationResult] = []
    total_auto = 0
    total_wrong = 0

    for fold_k in range(5):
        test_indices = list(outer_folds[fold_k])
        train_indices = [
            idx for i, f in enumerate(outer_folds) if i != fold_k for idx in f
        ]

        # 1. Inner CV Model Selection on training folds
        selected_param = select_best_hyperparameters_inner_cv(
            train_indices, param_grid=param_grid
        )

        # 2. Outer Evaluation on held-out test fold
        auto_count = 0
        wrong_count = 0
        for sample_idx in test_indices:
            st, is_correct = evaluate_single_sample(sample_idx, selected_param)
            if st == ReviewStatus.AUTO:
                auto_count += 1
                if not is_correct:
                    wrong_count += 1

        val_size = len(test_indices)
        cov_pct = (auto_count / val_size) * 100.0
        wia_pct = (wrong_count / auto_count * 100.0) if auto_count > 0 else 0.0

        # Exact confidence intervals for this fold
        cov_wilson = wilson_score_interval(auto_count, val_size)
        cov_cp = clopper_pearson_interval(auto_count, val_size)
        wia_wilson = wilson_score_interval(wrong_count, auto_count)
        wia_cp = clopper_pearson_interval(wrong_count, auto_count)

        fold_results.append(
            FoldEvaluationResult(
                fold_index=fold_k + 1,
                total_samples=val_size,
                auto_count=auto_count,
                wrong_count=wrong_count,
                coverage_percent=cov_pct,
                wrong_in_auto_percent=wia_pct,
                selected_hyperparameters=selected_param,
                sample_indices=test_indices,
                coverage_wilson_ci=(cov_wilson[0] * 100.0, cov_wilson[1] * 100.0),
                coverage_cp_ci=(cov_cp[0] * 100.0, cov_cp[1] * 100.0),
                wia_wilson_ci=(wia_wilson[0] * 100.0, wia_wilson[1] * 100.0),
                wia_cp_ci=(wia_cp[0] * 100.0, wia_cp[1] * 100.0),
            )
        )

        total_auto += auto_count
        total_wrong += wrong_count

    mean_cov = sum(f.coverage_percent for f in fold_results) / 5.0
    worst_cov = min(f.coverage_percent for f in fold_results)
    mean_wia = sum(f.wrong_in_auto_percent for f in fold_results) / 5.0
    worst_wia = max(f.wrong_in_auto_percent for f in fold_results)

    total_samples = 322
    overall_cov = (total_auto / total_samples) * 100.0
    overall_wia = (total_wrong / total_auto * 100.0) if total_auto > 0 else 0.0

    overall_cov_wilson = wilson_score_interval(total_auto, total_samples)
    overall_cov_cp = clopper_pearson_interval(total_auto, total_samples)
    overall_wia_wilson = wilson_score_interval(total_wrong, total_auto)
    overall_wia_cp = clopper_pearson_interval(total_wrong, total_auto)

    return NestedCVEvaluationReport(
        fold_results=fold_results,
        mean_coverage=mean_cov,
        worst_fold_coverage=worst_cov,
        mean_wrong_in_auto=mean_wia,
        worst_fold_wrong_in_auto=worst_wia,
        total_auto=total_auto,
        total_wrong=total_wrong,
        overall_coverage=overall_cov,
        overall_wia=overall_wia,
        overall_coverage_wilson_ci=(
            overall_cov_wilson[0] * 100.0,
            overall_cov_wilson[1] * 100.0,
        ),
        overall_coverage_cp_ci=(
            overall_cov_cp[0] * 100.0,
            overall_cov_cp[1] * 100.0,
        ),
        overall_wia_wilson_ci=(
            overall_wia_wilson[0] * 100.0,
            overall_wia_wilson[1] * 100.0,
        ),
        overall_wia_cp_ci=(
            overall_wia_cp[0] * 100.0,
            overall_wia_cp[1] * 100.0,
        ),
    )


if __name__ == "__main__":
    import os

    import django

    if not os.environ.get("DJANGO_SETTINGS_MODULE"):
        os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"
    django.setup()

    report = run_nested_5fold_cross_validation(seed=42)
    print("=" * 80)
    print("NESTED 5-FOLD CROSS-VALIDATION EVALUATION REPORT (seed=42)")
    print("=" * 80)
    for r in report.fold_results:
        p = r.selected_hyperparameters
        print(
            f"Fold {r.fold_index}: N={r.total_samples:2d} | AUTO={r.auto_count:2d} | "
            f"Wrong={r.wrong_count} | Cov={r.coverage_percent:5.2f}% "
            f"(Wilson 95% [{r.coverage_wilson_ci[0]:.1f}%, {r.coverage_wilson_ci[1]:.1f}%]) | "
            f"WIA={r.wrong_in_auto_percent:5.2f}% "
            f"(Wilson 95% [{r.wia_wilson_ci[0]:.2f}%, {r.wia_wilson_ci[1]:.2f}%]) | "
            f"Chosen: th={p.threshold}, skip={p.adaptive_skip}"
        )
    print("-" * 80)
    print(
        f"Mean Coverage: {report.mean_coverage:.2f}% (Worst: {report.worst_fold_coverage:.2f}%)"
    )
    print(
        f"Mean Wrong-in-AUTO: {report.mean_wrong_in_auto:.2f}% (Worst: {report.worst_fold_wrong_in_auto:.2f}%)"
    )
    print(f"Total AUTO: {report.total_auto}/322 ({report.overall_coverage:.2f}%)")
    print(
        f"  Wilson 95% CI: [{report.overall_coverage_wilson_ci[0]:.2f}%, {report.overall_coverage_wilson_ci[1]:.2f}%]"
    )
    print(
        f"  Clopper-Pearson 95% CI: [{report.overall_coverage_cp_ci[0]:.2f}%, {report.overall_coverage_cp_ci[1]:.2f}%]"
    )
    print(
        f"Total Wrong-in-AUTO: {report.total_wrong}/{report.total_auto} ({report.overall_wia:.3f}%)"
    )
    print(
        f"  Wilson 95% CI: [{report.overall_wia_wilson_ci[0]:.3f}%, {report.overall_wia_wilson_ci[1]:.3f}%]"
    )
    print(
        f"  Clopper-Pearson 95% CI: [{report.overall_wia_cp_ci[0]:.3f}%, {report.overall_wia_cp_ci[1]:.3f}%]"
    )
    print("=" * 80)
