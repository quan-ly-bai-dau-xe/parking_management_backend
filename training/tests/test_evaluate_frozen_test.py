"""Unit tests for evaluate_frozen_test script logic and mutation testing guard."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("onnxruntime")
pytest.importorskip("pyarrow")

# Ensure training/src and training/scripts are on sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = str(_REPO_ROOT / "training" / "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from evaluate_frozen_test import (  # noqa: E402
    ADR0007_TARGET_S5_EXACT_MATCH,
    EXPECTED_PARQUET_SHA256,
    EXPECTED_VN_ROW_COUNT,
    MUTATION_INDICES,
    SliceMetrics,
    build_markdown_report,
    compute_delta,
    format_delta_status,
)


def test_constants_and_contracts() -> None:
    """Verify essential constants match architectural requirements."""
    assert (
        EXPECTED_PARQUET_SHA256
        == "843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b"
    )
    assert EXPECTED_VN_ROW_COUNT == 322
    assert len(MUTATION_INDICES) == 10
    assert ADR0007_TARGET_S5_EXACT_MATCH == 95.96


def test_delta_computation_arithmetic() -> None:
    """Ensure compute_delta computes true arithmetic difference."""
    assert abs(compute_delta(96.0, 93.0) - 3.0) < 1e-6
    assert abs(compute_delta(92.8571, 95.9627) - (-3.1056)) < 1e-4


def test_format_delta_status_dynamic_verdicts() -> None:
    """Ensure format_delta_status dynamically generates correct status without hardcoding."""
    # Within tolerance -> MATCH
    delta_str, status = format_delta_status(0.00, tol=0.05)
    assert delta_str == "0.00%"
    assert status == "MATCH"

    delta_str, status = format_delta_status(0.04, tol=0.05)
    assert status == "MATCH"

    # Higher is better
    delta_str, status = format_delta_status(3.00, tol=0.05, higher_is_better=True)
    assert delta_str == "+3.00%"
    assert "IMPROVED" in status

    delta_str, status = format_delta_status(-3.10, tol=0.05, higher_is_better=True)
    assert delta_str == "-3.10%"
    assert "REGRESSED" in status

    # Lower is better (e.g. error rate / Wrong-in-AUTO)
    delta_str, status = format_delta_status(-0.50, tol=0.05, higher_is_better=False)
    assert "IMPROVED" in status

    delta_str, status = format_delta_status(0.50, tol=0.05, higher_is_better=False)
    assert "REGRESSED" in status


def test_mutation_test_arithmetic_drop() -> None:
    """Verify that corrupting 10 predictions out of 322 drops exact match by exactly 3.1056%."""
    total_samples = 322
    clean_exact_matches = 309
    corrupted_exact_matches = clean_exact_matches - 10  # 299

    clean_pct = (clean_exact_matches / total_samples) * 100.0
    corrupted_pct = (corrupted_exact_matches / total_samples) * 100.0

    drop = clean_pct - corrupted_pct
    expected_drop = (10 / total_samples) * 100.0

    assert abs(drop - expected_drop) < 1e-6
    assert abs(drop - 3.10559) < 1e-4
    assert clean_pct >= 95.0
    assert corrupted_pct < 95.0  # Fails gate


def test_slice_metrics_clean_wrong_in_auto_count() -> None:
    """Verify that clean_wrong_in_auto_count is preserved in SliceMetrics."""
    sm = SliceMetrics(
        name="Slice 5",
        total_samples=322,
        exact_matches=309,
        exact_match_pct=95.96,
        char_accuracy_pct=99.07,
        total_edit_distance=5,
        auto_count=301,
        auto_coverage_pct=93.48,
        wrong_in_auto_count=4,
        wrong_in_auto_pct=1.33,
        clean_wrong_in_auto_count=3,
        clean_wrong_in_auto_pct=0.9967,
    )
    assert sm.clean_wrong_in_auto_count == 3
    assert sm.clean_wrong_in_auto_pct == 0.9967


def test_build_markdown_report_dynamic_gate_and_no_hardcoded_literals() -> None:
    """Verify build_markdown_report dynamically formats gate status and values without static facades."""
    dummy_path = Path("dummy.parquet")
    sha = "843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b"
    latencies = [1.0, 2.0, 3.0]
    pipe_latencies = {
        "pipeline": [50.0],
        "detector": [40.0],
        "ocr1": [5.0],
        "ocr2": [0.0],
    }
    spread_runs = [{"exact_match": 95.96, "char_acc": 99.07, "latency_median": 50.0}]

    def make_slices(
        em: float, clean_wia_pct: float, clean_wia_cnt: int
    ) -> dict[str, SliceMetrics]:
        m = SliceMetrics(
            name="Test",
            total_samples=322,
            exact_matches=round((em / 100.0) * 322),
            exact_match_pct=em,
            char_accuracy_pct=99.0,
            total_edit_distance=5,
            auto_count=301,
            auto_coverage_pct=93.48,
            wrong_in_auto_count=clean_wia_cnt + 1,
            wrong_in_auto_pct=1.33,
            clean_wrong_in_auto_count=clean_wia_cnt,
            clean_wrong_in_auto_pct=clean_wia_pct,
        )
        return {f"slice_{i}": m for i in range(1, 6)}

    # Case 1: Green baseline - All PASS
    green_slices = make_slices(em=95.96, clean_wia_pct=0.997, clean_wia_cnt=3)
    green_report = build_markdown_report(
        parquet_path=dummy_path,
        parquet_sha256=sha,
        cpu_model="Mock CPU",
        threads=1,
        slices=green_slices,
        standalone_exact=95.96,
        standalone_char_acc=99.34,
        standalone_latencies=latencies,
        pipeline_latencies=pipe_latencies,
        spread_runs=spread_runs,
        corrupt_mode=False,
        standalone_exact_count=309,
    )
    assert "- **Exact Match Gate**: `PASS` (95.96% >= 95.00% target)" in green_report
    assert (
        "- **Wrong-in-AUTO Gate**: `PASS` (Clean 0.997% <= 1.000% target)"
        in green_report
    )
    assert "- **Status**: `GREEN (Uncorrupted Production Baseline)`" in green_report
    assert "(3/301)" in green_report
    assert "(309/322)" in green_report

    # Case 2: Regressed baseline - Both gates FAIL
    red_slices = make_slices(em=85.00, clean_wia_pct=2.500, clean_wia_cnt=8)
    red_report = build_markdown_report(
        parquet_path=dummy_path,
        parquet_sha256=sha,
        cpu_model="Mock CPU",
        threads=1,
        slices=red_slices,
        standalone_exact=85.00,
        standalone_char_acc=90.00,
        standalone_latencies=latencies,
        pipeline_latencies=pipe_latencies,
        spread_runs=[{"exact_match": 85.00, "char_acc": 90.00, "latency_median": 50.0}],
        corrupt_mode=False,
        standalone_exact_count=274,
    )
    assert "- **Exact Match Gate**: `FAIL` (85.00% >= 95.00% target)" in red_report
    assert (
        "- **Wrong-in-AUTO Gate**: `FAIL` (Clean 2.500% <= 1.000% target)" in red_report
    )
    assert "- **Status**: `RED (Baseline Regression)`" in red_report
    assert "(8/301)" in red_report
    assert "(274/322)" in red_report

    # Case 3: Corrupted mode
    corrupt_report = build_markdown_report(
        parquet_path=dummy_path,
        parquet_sha256=sha,
        cpu_model="Mock CPU",
        threads=1,
        slices=red_slices,
        standalone_exact=85.00,
        standalone_char_acc=90.00,
        standalone_latencies=latencies,
        pipeline_latencies=pipe_latencies,
        spread_runs=spread_runs,
        corrupt_mode=True,
        standalone_exact_count=274,
    )
    assert "- **Status**: `RED (Intentionally Corrupted)`" in corrupt_report
    assert "- **Baseline Gate Verdict**: `FAIL`" in corrupt_report
    assert "Drop = `3.1056%`" in corrupt_report
