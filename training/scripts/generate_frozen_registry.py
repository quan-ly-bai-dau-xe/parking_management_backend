"""Generate frozen test registry (strictly 5 image and crop hash digests) for the 322 Vietnamese license plate images.

Public Benchmark Hash Digest Contract (strictly 5 fields):
- row_index: int (0..321)
- sha256: full photo SHA-256 (hex 64)
- phash: full photo 64-bit DCT pHash (hex 0x...)
- crop_sha256: production detector 64x128 plate crop SHA-256 (hex 64)
- crop_phash: production detector 64x128 plate crop 64-bit DCT pHash (hex 0x...)

Zero reversible label hashes committed to git; benchmark plate strings reside in cache/fixtures.
"""

# ruff: noqa: E402

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import pyarrow.parquet as pq

# Ensure plate_training is importable
SCRIPT_DIR = Path(__file__).resolve().parent
TRAINING_SRC = SCRIPT_DIR.parent / "src"
if str(TRAINING_SRC) not in sys.path:
    sys.path.insert(0, str(TRAINING_SRC))

from plate_training.cache import get_crops_dir
from plate_training.split import compute_phash

EXPECTED_PARQUET_SHA256 = (
    "843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b"
)
VN_PLATE_REGEX = re.compile(r"^\d{2}[A-Z]")


def find_default_parquet() -> Path:
    """Find default Hugging Face parquet cache path."""
    cache_root = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / "datasets--sonnetechnology--license-plate-text-recognition-full"
    )
    matches = list(cache_root.rglob("*.parquet"))
    if not matches:
        raise FileNotFoundError(f"No parquet dataset found under {cache_root}")
    return matches[0]


def extract_crops_from_detector(
    table: pq.Table,
    vn_row_indices: list[int],
    margin: int = 4,
    detector_model_path: Path | str | None = None,
) -> list[np.ndarray]:
    """
    Extract 64x128 uint8 RGB crops from full vehicle images using production detector.
    Fallback to ground-truth bbox if detection confidence is below threshold.
    """
    import open_image_models

    models_dir = Path("models/ocr")
    det_path = (
        Path(detector_model_path)
        if detector_model_path
        else (models_dir / "yolo-v9-t-384-license-plates-end2end.onnx")
    )
    if not det_path.is_file():
        cache_det = (
            Path.home()
            / ".cache"
            / "open-image-models"
            / "yolo-v9-t-384-license-plate-end2end"
            / "yolo-v9-t-384-license-plates-end2end.onnx"
        )
        if cache_det.is_file():
            det_path = cache_det

    detector = open_image_models.create_detector(
        model=str(det_path)
        if det_path.is_file()
        else "yolo-v9-t-384-license-plate-end2end",
        conf_thresh=0.01,  # Low threshold to capture all plates including edge cases
    )

    crops: list[np.ndarray] = []
    for idx, table_idx in enumerate(vn_row_indices):
        raw_img = table["image"][table_idx].as_py()
        img_bytes = raw_img["bytes"]
        img_bgr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
        if img_bgr is None:
            raise RuntimeError(f"Failed to decode image at index {idx}")

        H, W = img_bgr.shape[:2]
        detections = (
            detector.predict(img_bgr)
            if hasattr(detector, "predict")
            else detector(img_bgr)
        )

        # Disambiguate or fallback
        if len(detections) > 0:
            # Pick highest confidence detection
            best_det = max(
                detections, key=lambda d: d.score if hasattr(d, "score") else 0.0
            )
            bbox = best_det.bounding_box
            x1 = max(int(bbox.x1) - margin, 0)
            y1 = max(int(bbox.y1) - margin, 0)
            x2 = min(int(bbox.x2) + margin, W)
            y2 = min(int(bbox.y2) + margin, H)
        else:
            # Fallback to parquet bbox
            raw_bbox = table["bbox"][table_idx].as_py()
            if raw_bbox and len(raw_bbox) > 0 and len(raw_bbox[0]) == 4:
                b = raw_bbox[0]
                x1 = max(int(b[0]) - margin, 0)
                y1 = max(int(b[1]) - margin, 0)
                x2 = min(int(b[2]) + margin, W)
                y2 = min(int(b[3]) + margin, H)
            else:
                x1, y1, x2, y2 = 0, 0, W, H

        cropped = img_bgr[y1:y2, x1:x2]
        resized = cv2.resize(cropped, (128, 64), interpolation=cv2.INTER_LINEAR)
        crops.append(resized)

    return crops


def generate_registry(
    parquet_path: Path | str,
    output_path: Path | str = Path("training/data/frozen_test_registry.json"),
    crops_dir: Path | str | None = None,
) -> list[dict[str, int | str]]:
    """
    Extract 322 Vietnamese plate records, compute SHA-256 and pHash for both
    full photos and 64x128 detector crops, and save registry JSON containing strictly
    5 image/crop hash fields (row_index, sha256, phash, crop_sha256, crop_phash).
    """
    p_path = Path(parquet_path)
    if not p_path.is_file():
        raise FileNotFoundError(f"Parquet file not found: {p_path}")

    # Verify parquet integrity
    file_bytes = p_path.read_bytes()
    parquet_sha = hashlib.sha256(file_bytes).hexdigest()
    if parquet_sha != EXPECTED_PARQUET_SHA256:
        raise ValueError(
            f"Parquet SHA-256 mismatch: got {parquet_sha}, expected {EXPECTED_PARQUET_SHA256}"
        )

    table = pq.read_table(p_path)
    num_rows = len(table)
    print(
        f"[INFO] Parquet loaded: {num_rows} total rows. Verifying SHA-256: {parquet_sha}"
    )

    # Filter VN plate rows
    vn_row_indices = []
    for i in range(num_rows):
        target_val = table["target"][i].as_py()
        if (
            target_val
            and len(target_val) > 0
            and target_val[0]
            and VN_PLATE_REGEX.match(str(target_val[0]))
        ):
            vn_row_indices.append(i)

    if len(vn_row_indices) != 322:
        raise ValueError(f"Expected 322 Vietnamese plates, found {len(vn_row_indices)}")

    # Check crops directory cache
    resolved_crops_dir: Path | None = None
    if crops_dir:
        candidate = Path(crops_dir)
        if candidate.is_dir():
            resolved_crops_dir = candidate
    else:
        cached_default = get_crops_dir()
        if cached_default.is_dir():
            resolved_crops_dir = cached_default

    crop_files: list[Path] = []
    if resolved_crops_dir:
        crop_files = sorted(
            resolved_crops_dir.glob("crop_*.png"),
            key=lambda p: int(p.stem.split("_")[1]) if "_" in p.stem else 0,
        )

    use_cached_crops = len(crop_files) == 322
    if use_cached_crops:
        print(
            f"[INFO] Using {len(crop_files)} cached detector crops from {resolved_crops_dir}"
        )
    else:
        print("[INFO] Extracting 322 crops via production detector pipeline...")
        extracted_crops = extract_crops_from_detector(table, vn_row_indices)

    registry_entries = []
    sha_set = set()
    phash_set = set()
    crop_sha_set = set()
    crop_phash_set = set()

    print("[INFO] Computing hashes for 322 frozen test items...")
    for idx, table_idx in enumerate(vn_row_indices):
        # 1. Full photo hashes
        raw_img = table["image"][table_idx].as_py()
        img_bytes = raw_img["bytes"]

        img_sha256 = hashlib.sha256(img_bytes).hexdigest().lower()
        sha_set.add(img_sha256)

        img_gray = cv2.imdecode(
            np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_GRAYSCALE
        )
        if img_gray is None:
            raise RuntimeError(
                f"Failed to decode image at index {idx} (table row {table_idx})"
            )

        phash_int = compute_phash(img_gray)
        phash_hex = f"0x{phash_int:016x}"
        phash_set.add(phash_hex)

        # 2. Crop hashes
        if use_cached_crops:
            crop_file = crop_files[idx]
            c_bytes = crop_file.read_bytes()
            crop_img = cv2.imread(str(crop_file))
        else:
            crop_img = extracted_crops[idx]
            _, buf = cv2.imencode(".png", crop_img)
            c_bytes = buf.tobytes()

        crop_sha256 = hashlib.sha256(c_bytes).hexdigest().lower()
        crop_sha_set.add(crop_sha256)

        crop_phash_int = compute_phash(crop_img)
        crop_phash_hex = f"0x{crop_phash_int:016x}"
        crop_phash_set.add(crop_phash_hex)

        registry_entries.append(
            {
                "row_index": idx,
                "sha256": img_sha256,
                "phash": phash_hex,
                "crop_sha256": crop_sha256,
                "crop_phash": crop_phash_hex,
            }
        )

    # Invariant assertions
    assert len(registry_entries) == 322, (
        f"Expected 322 entries, got {len(registry_entries)}"
    )
    assert len(sha_set) == 322, f"Expected 322 unique SHA-256, got {len(sha_set)}"
    assert len(phash_set) == 319, f"Expected 319 unique pHash, got {len(phash_set)}"
    assert len(crop_sha_set) == 322, (
        f"Expected 322 unique crop SHA-256, got {len(crop_sha_set)}"
    )
    assert len(crop_phash_set) == 321, (
        f"Expected 321 unique crop pHash, got {len(crop_phash_set)}"
    )

    # Strictly 5 image/crop fields check & format validation
    expected_fields = {"row_index", "sha256", "phash", "crop_sha256", "crop_phash"}
    sha_regex = re.compile(r"^[0-9a-f]{64}$")
    phash_regex = re.compile(r"^0x[0-9a-f]{16}$")
    for entry in registry_entries:
        assert set(entry.keys()) == expected_fields, (
            f"Entry does not contain strictly 5 fields: {set(entry.keys())}"
        )
        assert sha_regex.match(str(entry["sha256"]))
        assert phash_regex.match(str(entry["phash"]))
        assert sha_regex.match(str(entry["crop_sha256"]))
        assert phash_regex.match(str(entry["crop_phash"]))

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(registry_entries, f, indent=2)

    print(
        f"[INFO] Successfully generated {out_file} with {len(registry_entries)} entries "
        f"({len(sha_set)} unique photo SHA, {len(phash_set)} unique photo pHash, "
        f"{len(crop_sha_set)} unique crop SHA, {len(crop_phash_set)} unique crop pHash). "
        "Strictly 5 image/crop fields, 0 label hashes, and 0 image bytes stored."
    )
    return registry_entries


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate frozen test registry with strictly 5 image and detector crop hashes for 322 images."
    )
    parser.add_argument(
        "--parquet",
        "-p",
        default=None,
        help="Path to full dataset parquet file. Defaults to HF cache.",
    )
    parser.add_argument(
        "--crops-dir",
        "-c",
        default=None,
        help="Path to directory containing 322 detector crop PNGs.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="training/data/frozen_test_registry.json",
        help="Output JSON path.",
    )
    args = parser.parse_args()

    parquet_path = Path(args.parquet) if args.parquet else find_default_parquet()
    generate_registry(
        parquet_path=parquet_path,
        output_path=args.output,
        crops_dir=args.crops_dir,
    )


if __name__ == "__main__":
    main()
