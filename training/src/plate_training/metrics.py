"""Benchmark metrics calculation: Levenshtein distance, Exact Match, Character Accuracy, CER, and Review Policy."""

from dataclasses import dataclass, field
from typing import Any


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute the Levenshtein edit distance between two strings using dynamic programming."""
    m, n = len(s1), len(s2)
    if m == 0:
        return n
    if n == 0:
        return m

    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j

    for i in range(1, m + 1):
        c1 = s1[i - 1]
        for j in range(1, n + 1):
            c2 = s2[j - 1]
            cost = 0 if c1 == c2 else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,  # deletion
                dp[i][j - 1] + 1,  # insertion
                dp[i - 1][j - 1] + cost,  # substitution
            )

    return dp[m][n]


def compute_exact_match(gts: list[str], preds: list[str]) -> float:
    """Calculate exact match percentage (0.0 to 100.0)."""
    if not gts:
        return 0.0
    matches = sum(1 for g, p in zip(gts, preds, strict=False) if g == p)
    return (matches / len(gts)) * 100.0


def compute_character_accuracy(
    gts: list[str], preds: list[str], mode: str = "backend"
) -> float:
    """
    Calculate character-level recognition accuracy percentage.

    Modes:
    - 'backend': Matches test_ocr_benchmark.py and ADR-0007 benchmark where denominator
                 is sum(max(len(gt), len(pred))).
    - 'standard': Standard CER-derived accuracy where denominator is sum(len(gt)).
    """
    if not gts:
        return 0.0

    total_dist = 0
    total_chars = 0

    for gt, pred in zip(gts, preds, strict=False):
        dist = levenshtein_distance(gt, pred)
        total_dist += dist
        if mode == "backend":
            total_chars += max(len(gt), len(pred))
        else:
            total_chars += len(gt)

    if total_chars == 0:
        return 100.0

    acc = (1.0 - (total_dist / total_chars)) * 100.0
    return max(0.0, acc)


def compute_cer(gts: list[str], preds: list[str]) -> float:
    """Calculate Character Error Rate (CER) percentage (0.0 to 100.0)."""
    if not gts:
        return 0.0

    total_dist = 0
    total_gt_len = 0

    for gt, pred in zip(gts, preds, strict=False):
        total_dist += levenshtein_distance(gt, pred)
        total_gt_len += len(gt)

    if total_gt_len == 0:
        return 0.0

    return (total_dist / total_gt_len) * 100.0


def compute_auto_metrics(
    gts: list[str],
    preds: list[str],
    confidences: list[float],
    threshold: float = 85.0,
) -> dict[str, float]:
    """
    Compute Review Policy classification metrics at confidence threshold (default 85.0%).

    Returns:
    - auto_coverage_pct: percentage of samples routed to AUTO
    - wrong_in_auto_pct: percentage of AUTO samples that had an incorrect prediction
    """
    total = len(gts)
    if total == 0:
        return {
            "auto_coverage_pct": 0.0,
            "wrong_in_auto_pct": 0.0,
            "auto_count": 0.0,
            "wrong_in_auto_count": 0.0,
        }

    auto_count = 0
    wrong_in_auto_count = 0

    for gt, pred, conf in zip(gts, preds, confidences, strict=False):
        if conf >= threshold:
            auto_count += 1
            if pred != gt:
                wrong_in_auto_count += 1

    auto_coverage_pct = (auto_count / total) * 100.0
    wrong_in_auto_pct = (
        (wrong_in_auto_count / auto_count * 100.0) if auto_count > 0 else 0.0
    )

    return {
        "auto_coverage_pct": round(auto_coverage_pct, 4),
        "wrong_in_auto_pct": round(wrong_in_auto_pct, 4),
        "auto_count": float(auto_count),
        "wrong_in_auto_count": float(wrong_in_auto_count),
    }


@dataclass
class EvaluationReport:
    """Evaluation summary report containing all benchmark metrics."""

    total_samples: int
    exact_match_pct: float
    character_accuracy_pct: float
    cer_pct: float
    auto_coverage_pct: float | None = None
    wrong_in_auto_pct: float | None = None
    wrong_samples: list[dict[str, Any]] = field(default_factory=list)

    def to_markdown_table(self) -> str:
        """Render evaluation report as a GitHub-flavored Markdown table."""
        lines = [
            "| Metric | Value |",
            "|---|---|",
            f"| Total Samples | {self.total_samples} |",
            f"| Exact Match % | {self.exact_match_pct:.2f}% |",
            f"| Character Accuracy % | {self.character_accuracy_pct:.2f}% |",
            f"| Character Error Rate (CER) % | {self.cer_pct:.2f}% |",
        ]
        if self.auto_coverage_pct is not None:
            lines.append(f"| AUTO Coverage % | {self.auto_coverage_pct:.2f}% |")
        if self.wrong_in_auto_pct is not None:
            lines.append(f"| Wrong-in-AUTO % | {self.wrong_in_auto_pct:.2f}% |")
        return "\n".join(lines)


def evaluate_predictions(
    gts: list[str],
    preds: list[str],
    confidences: list[float] | None = None,
    auto_threshold: float = 85.0,
) -> EvaluationReport:
    """Evaluate predictions against ground truths across all standard metrics."""
    total = len(gts)
    exact_pct = compute_exact_match(gts, preds)
    char_acc_pct = compute_character_accuracy(gts, preds, mode="backend")
    cer_pct = compute_cer(gts, preds)

    auto_cov = None
    wrong_auto = None
    if confidences is not None:
        auto_stats = compute_auto_metrics(
            gts, preds, confidences, threshold=auto_threshold
        )
        auto_cov = auto_stats["auto_coverage_pct"]
        wrong_auto = auto_stats["wrong_in_auto_pct"]

    wrong_samples: list[dict[str, Any]] = []
    for i, (gt, pred) in enumerate(zip(gts, preds, strict=False)):
        if gt != pred:
            wrong_samples.append(
                {
                    "index": i,
                    "ground_truth": gt,
                    "predicted": pred,
                    "confidence": confidences[i] if confidences is not None else None,
                    "distance": levenshtein_distance(gt, pred),
                }
            )

    return EvaluationReport(
        total_samples=total,
        exact_match_pct=exact_pct,
        character_accuracy_pct=char_acc_pct,
        cer_pct=cer_pct,
        auto_coverage_pct=auto_cov,
        wrong_in_auto_pct=wrong_auto,
        wrong_samples=wrong_samples,
    )
