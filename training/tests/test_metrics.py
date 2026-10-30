"""Tests for benchmark metrics: Levenshtein distance, Exact Match, Char Acc, CER, and Review Policy."""

import pytest

from plate_training.metrics import (
    compute_auto_metrics,
    compute_cer,
    compute_character_accuracy,
    compute_exact_match,
    evaluate_predictions,
    levenshtein_distance,
)


@pytest.mark.unit
def test_levenshtein_distance() -> None:
    """Verify Levenshtein distance edge cases and typical plate edits."""
    assert levenshtein_distance("", "") == 0
    assert levenshtein_distance("51G49160", "51G49160") == 0
    assert levenshtein_distance("51G49160", "51G4916") == 1  # deletion
    assert levenshtein_distance("51G49160", "51G491600") == 1  # insertion
    assert (
        levenshtein_distance("51G49160", "51G49180") == 1
    )  # substitution ('6' -> '8')
    assert levenshtein_distance("ABC", "DEF") == 3


@pytest.mark.unit
def test_compute_exact_match() -> None:
    """Verify exact match percentage calculation."""
    gts = ["51G49160", "30E12345", "43B99999", "60C11111"]
    preds_all_correct = ["51G49160", "30E12345", "43B99999", "60C11111"]
    preds_half_correct = ["51G49160", "30E12345", "43B88888", "60C22222"]
    preds_none_correct = ["XXXXX", "YYYYY", "ZZZZZ", "WWWWW"]

    assert compute_exact_match(gts, preds_all_correct) == 100.0
    assert compute_exact_match(gts, preds_half_correct) == 50.0
    assert compute_exact_match(gts, preds_none_correct) == 0.0
    assert compute_exact_match([], []) == 0.0


@pytest.mark.unit
def test_compute_character_accuracy_and_cer() -> None:
    """Verify character accuracy and CER against ADR-0007 definitions."""
    gts = ["51G49160", "30E12345"]  # 8 + 8 = 16 characters
    preds = [
        "51G49180",
        "30E12345",
    ]  # 1 substitution in first plate -> edit distance = 1

    # Backend mode: denominator is sum(max(len(gt), len(pred))) = 16
    char_acc = compute_character_accuracy(gts, preds, mode="backend")
    expected_acc = (1.0 - (1.0 / 16.0)) * 100.0  # 93.75%
    assert abs(char_acc - expected_acc) < 1e-4

    # CER: 1 / 16 = 6.25%
    cer = compute_cer(gts, preds)
    assert abs(cer - 6.25) < 1e-4


@pytest.mark.unit
def test_compute_auto_metrics() -> None:
    """Verify review policy classification (AUTO Coverage and Wrong-in-AUTO)."""
    gts = ["51G49160", "30E12345", "43B99999", "60C11111"]
    preds = ["51G49160", "30E12345", "43B88888", "60C11111"]  # plate 3 is wrong
    confidences = [
        95.0,
        90.0,
        92.0,
        80.0,
    ]  # first 3 >= 85.0 (AUTO), 4th < 85.0 (NEEDS_REVIEW)

    auto_stats = compute_auto_metrics(gts, preds, confidences, threshold=85.0)

    # 3 out of 4 routed to AUTO -> 75% coverage
    assert auto_stats["auto_coverage_pct"] == 75.0
    assert auto_stats["auto_count"] == 3.0

    # Of the 3 AUTO samples, 1 is wrong -> 1/3 = 33.3333% Wrong-in-AUTO
    assert abs(auto_stats["wrong_in_auto_pct"] - 33.3333) < 0.01
    assert auto_stats["wrong_in_auto_count"] == 1.0


@pytest.mark.unit
def test_evaluation_report_markdown() -> None:
    """Verify that EvaluationReport formats a compliant Markdown table."""
    gts = ["51G49160", "30E12345"]
    preds = ["51G49160", "30E12345"]
    confs = [95.0, 96.0]

    report = evaluate_predictions(gts, preds, confidences=confs, auto_threshold=85.0)
    assert report.exact_match_pct == 100.0
    assert report.character_accuracy_pct == 100.0
    assert report.cer_pct == 0.0
    assert report.auto_coverage_pct == 100.0
    assert report.wrong_in_auto_pct == 0.0

    md = report.to_markdown_table()
    assert "| Metric | Value |" in md
    assert "| Total Samples | 2 |" in md
    assert "| Exact Match % | 100.00% |" in md
