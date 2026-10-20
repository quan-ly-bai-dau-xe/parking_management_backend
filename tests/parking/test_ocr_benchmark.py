"""
Re-runnable benchmark & test suite for offline OCR engines (Fast-ALPR, Dummy).
Validates PlateRecognizer interface, normalization, review status rules,
and evaluates Fast-ALPR on real public dataset when PARKING_SCRATCH_DATASET_DIR is set.
"""

import hashlib
import io
import os
import re
from pathlib import Path
from typing import Any

import pytest
from PIL import Image

from apps.parking.services.ocr import (
    BoundingBox,
    DummyPlateRecognizer,
    FastAlprPlateRecognizer,
    PlateCandidate,
    PlateRecognizer,
    PlateScanResult,
)

EXPECTED_PARQUET_SHA256 = (
    "843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b"
)

EXPECTED_TOP_10_E2E_PLATES = [
    "51G-491.60",
    "51F-446.14",
    "51A-897.14",
    "51A-256.68",
    "51G-513.32",
    "51F-079.73",
    "51A-724.44",
    "51F-207.54",
    "51F-590.11",
    "51F-617.12",
]


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            ins = prev[j + 1] + 1
            deletions = curr[j] + 1
            subs = prev[j] + (c1 != c2)
            curr.append(min(ins, deletions, subs))
        prev = curr
    return prev[-1]


def _classify_review_status(
    recognition_source: str, ai_confidence: float | None
) -> str:
    """
    Classify session review status based on SRS 4.5.1 and Section 2 rules:
    - MANUAL entry -> AUTO (ai_confidence is None)
    - AI scan with confidence >= 85.00 -> AUTO
    - AI scan with confidence < 85.00 -> NEEDS_REVIEW
    """
    if recognition_source == "MANUAL":
        return "AUTO"
    if ai_confidence is not None and ai_confidence >= 85.00:
        return "AUTO"
    return "NEEDS_REVIEW"


def _locate_dataset_parquet() -> Path | None:
    """Find the verified test Parquet file in PARKING_SCRATCH_DATASET_DIR if provided."""
    env_dir = os.getenv("PARKING_SCRATCH_DATASET_DIR")
    if not env_dir:
        return None

    path_obj = Path(env_dir)
    if path_obj.is_file() and path_obj.suffix == ".parquet":
        return path_obj

    if path_obj.is_dir():
        for candidate in path_obj.rglob("*.parquet"):
            if "test" in candidate.name.lower():
                return candidate
        matches = list(path_obj.glob("*.parquet"))
        if matches:
            return matches[0]

    return None


# ---------------------------------------------------------------------------
# Unit tests: PlateRecognizer Interface & Normalization & Review Status
# ---------------------------------------------------------------------------


def test_plate_recognizer_normalize_plate_edge_cases() -> None:
    """Ensure normalize_plate removes non-alphanumeric chars and capitalizes."""
    test_cases = [
        ("51G-491.60", "51G49160"),
        ("51A 256.68", "51A25668"),
        ("51F / 20.70", "51F2070"),
        ("62P-5688", "62P5688"),
        (" 43A - 123.45 ", "43A12345"),
        ("29b_99999", "29B99999"),
        ("51k.992-14", "51K99214"),
        ("", ""),
    ]
    for raw_input, expected in test_cases:
        assert PlateRecognizer.normalize_plate(raw_input) == expected


def test_plate_recognizer_normalize_plate_none() -> None:
    """Ensure normalize_plate handles None gracefully by returning empty string."""
    # cast None as Any to verify defensive behavior against legacy data
    none_val: Any = None
    assert PlateRecognizer.normalize_plate(none_val) == ""


def test_review_status_classification_logic() -> None:
    """Verify review_status decision matrix according to 85.00 threshold."""
    assert _classify_review_status("AI", 85.00) == "AUTO"
    assert _classify_review_status("AI", 85.01) == "AUTO"
    assert _classify_review_status("AI", 99.99) == "AUTO"
    assert _classify_review_status("AI", 84.99) == "NEEDS_REVIEW"
    assert _classify_review_status("AI", 78.41) == "NEEDS_REVIEW"
    assert _classify_review_status("AI", 0.00) == "NEEDS_REVIEW"
    assert _classify_review_status("AI", None) == "NEEDS_REVIEW"
    assert _classify_review_status("MANUAL", None) == "AUTO"


def test_dummy_plate_recognizer_contract() -> None:
    """Ensure DummyPlateRecognizer conforms to PlateRecognizer interface contract."""
    recognizer = DummyPlateRecognizer(
        default_plate="51K-992.14", default_confidence=92.50
    )
    dummy_img = Image.new("RGB", (150, 60), color=(255, 255, 255))
    result: PlateScanResult = recognizer.recognize(dummy_img)

    assert result.engine_name == "dummy"
    assert len(result.candidates) == 1
    assert result.best_candidate is not None
    assert result.best_candidate.plate_text == "51K-992.14"
    assert result.best_candidate.plate_normalized == "51K99214"
    assert result.best_candidate.confidence == 92.50
    assert isinstance(result.best_candidate.bounding_box, BoundingBox)
    assert result.latency_ms > 0


def test_dummy_plate_recognizer_custom_result() -> None:
    """Ensure DummyPlateRecognizer supports custom preset PlateScanResult."""
    recognizer = DummyPlateRecognizer()
    cand = PlateCandidate(
        plate_text="30H-123.45",
        plate_normalized="30H12345",
        confidence=98.0,
        bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
    )
    custom_res = PlateScanResult(
        candidates=[cand],
        best_candidate=cand,
        engine_name="custom_dummy",
        raw_text="30H-123.45",
        latency_ms=2.5,
    )
    recognizer.set_result(custom_res)

    result = recognizer.recognize(b"arbitrary_bytes")
    assert result == custom_res
    assert result.engine_name == "custom_dummy"


def test_fast_alpr_recognizer_synthetic_image() -> None:
    """
    Ensure FastAlprPlateRecognizer runs without error on in-memory synthetic image.
    Does not require real dataset; operates on tiny Pillow-generated image.
    """
    recognizer = FastAlprPlateRecognizer()
    synthetic_img = Image.new("RGB", (200, 80), color=(240, 240, 240))
    result = recognizer.recognize(synthetic_img)

    assert result.engine_name == "fast_alpr"
    assert isinstance(result.candidates, list)
    assert result.latency_ms >= 0


# ---------------------------------------------------------------------------
# Re-runnable Benchmark Tests: Executed ONLY when PARKING_SCRATCH_DATASET_DIR is set
# ---------------------------------------------------------------------------

SCRATCH_DATASET_PATH = _locate_dataset_parquet()


@pytest.mark.skipif(
    SCRATCH_DATASET_PATH is None,
    reason="Real dataset benchmark skipped: PARKING_SCRATCH_DATASET_DIR not set",
)
def test_real_dataset_integrity_and_sha256() -> None:
    """Verify SHA-256 hash of external real dataset Parquet file matches expected value."""
    assert SCRATCH_DATASET_PATH is not None
    hasher = hashlib.sha256()
    with open(SCRATCH_DATASET_PATH, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    actual_hash = hasher.hexdigest()
    assert actual_hash == EXPECTED_PARQUET_SHA256, (
        f"Parquet hash mismatch: expected {EXPECTED_PARQUET_SHA256}, got {actual_hash}"
    )


@pytest.mark.skipif(
    SCRATCH_DATASET_PATH is None,
    reason="Real dataset benchmark skipped: PARKING_SCRATCH_DATASET_DIR not set",
)
def test_fast_alpr_real_dataset_benchmark_100_images() -> None:
    """
    Benchmark Fast-ALPR on 100 real Vietnamese car plate images from external dataset.
    Verifies:
    - Exact match accuracy >= 90.00% (measured: 93.00%)
    - Character-level accuracy >= 95.00% (measured: 98.12%)
    - High-confidence (>= 85%) precision >= 90.00% (measured: 94.90%)
    """
    import pyarrow.parquet as pq

    assert SCRATCH_DATASET_PATH is not None
    table = pq.read_table(str(SCRATCH_DATASET_PATH))

    # Filter Vietnamese plates matching 2-digit province code + series letter
    vn_indices: list[int] = []
    for i in range(len(table)):
        target_val = table["target"][i].as_py()
        if (
            target_val
            and len(target_val) > 0
            and re.match(r"^\d{2}[A-Z]", target_val[0])
        ):
            vn_indices.append(i)
        if len(vn_indices) >= 100:
            break

    assert len(vn_indices) == 100, f"Expected 100 VN plates, found {len(vn_indices)}"

    recognizer = FastAlprPlateRecognizer()
    exact_match_count = 0
    total_edit_distance = 0
    total_characters = 0
    high_conf_total = 0
    high_conf_correct = 0

    for row_idx in vn_indices:
        gt_raw = table["target"][row_idx].as_py()[0]
        gt_norm = PlateRecognizer.normalize_plate(gt_raw)
        img_bytes = table["image"][row_idx].as_py()["bytes"]

        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        scan_res = recognizer.recognize(img)

        best = scan_res.best_candidate
        pred_norm = best.plate_normalized if best else ""
        conf = best.confidence if best else 0.0

        is_exact = pred_norm == gt_norm
        if is_exact:
            exact_match_count += 1

        dist = _levenshtein_distance(gt_norm, pred_norm)
        total_edit_distance += dist
        total_characters += max(len(gt_norm), len(pred_norm))

        if conf >= 85.00:
            high_conf_total += 1
            if is_exact:
                high_conf_correct += 1

    exact_match_rate = (exact_match_count / 100.0) * 100.0
    char_accuracy = (1.0 - (total_edit_distance / total_characters)) * 100.0
    high_conf_precision = (
        (high_conf_correct / high_conf_total) * 100.0 if high_conf_total else 0.0
    )

    assert exact_match_rate >= 90.0, (
        f"Exact match rate {exact_match_rate:.2f}% below required 90.00%"
    )
    assert char_accuracy >= 95.0, (
        f"Character accuracy {char_accuracy:.2f}% below required 95.00%"
    )
    assert high_conf_precision >= 90.0, (
        f"High confidence precision {high_conf_precision:.2f}% below required 90.00%"
    )


@pytest.mark.skipif(
    SCRATCH_DATASET_PATH is None,
    reason="Real dataset benchmark skipped: PARKING_SCRATCH_DATASET_DIR not set",
)
def test_top_10_e2e_dataset_plates_recognition() -> None:
    """Verify that all 10 plates designated for Docker E2E are correctly recognized."""
    import pyarrow.parquet as pq

    assert SCRATCH_DATASET_PATH is not None
    table = pq.read_table(str(SCRATCH_DATASET_PATH))
    recognizer = FastAlprPlateRecognizer()

    plate_to_row: dict[str, int] = {}
    for i in range(len(table)):
        target_val = table["target"][i].as_py()
        if target_val:
            norm_target = PlateRecognizer.normalize_plate(target_val[0])
            if norm_target not in plate_to_row:
                plate_to_row[norm_target] = i

    for expected_plate in EXPECTED_TOP_10_E2E_PLATES:
        expected_norm = PlateRecognizer.normalize_plate(expected_plate)
        assert expected_norm in plate_to_row, (
            f"Plate {expected_plate} (norm {expected_norm}) not found in Parquet dataset"
        )
        row_idx = plate_to_row[expected_norm]
        img_bytes = table["image"][row_idx].as_py()["bytes"]
        img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
        res = recognizer.recognize(img)

        assert res.best_candidate is not None, f"No candidate for {expected_plate}"
        assert res.best_candidate.plate_normalized == expected_norm
        assert res.best_candidate.confidence >= 85.00
