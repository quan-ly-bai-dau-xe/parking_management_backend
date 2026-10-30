"""Benchmark dataset preparation and deterministic 322 detector crop generation."""

from __future__ import annotations

import json
import logging
import re
import urllib.request
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pyarrow.parquet as pq

from plate_training.cache import (
    EXPECTED_PARQUET_SHA256,
    OFFICIAL_PARQUET_URL,
    compute_sha256,
    ensure_cache_dir,
    get_benchmark_labels_path,
    get_crops_dir,
)
from plate_training.normalization import normalize_plate

logger = logging.getLogger("plate_training.benchmark")

VN_PLATE_REGEX = re.compile(r"^\d{2}[A-Z]")


def find_or_download_parquet(
    explicit_path: str | Path | None = None,
    cache_dir: str | Path | None = None,
) -> Path:
    """Find local Parquet file or download from official Hugging Face benchmark repository."""
    if explicit_path:
        p = Path(explicit_path).resolve()
        if p.is_file():
            return p

    # Check Hugging Face default cache
    hf_cache = (
        Path.home()
        / ".cache"
        / "huggingface"
        / "hub"
        / "datasets--sonnetechnology--license-plate-text-recognition-full"
    )
    if hf_cache.is_dir():
        matches = list(hf_cache.rglob("*.parquet"))
        for m in matches:
            try:
                if compute_sha256(m) == EXPECTED_PARQUET_SHA256:
                    return m
            except Exception:
                continue

    # Download into cache_dir
    target_dir = ensure_cache_dir(cache_dir)
    target_parquet = target_dir / "sonne_benchmark_test.parquet"

    if target_parquet.is_file():
        sha = compute_sha256(target_parquet)
        if sha == EXPECTED_PARQUET_SHA256:
            return target_parquet

    logger.info(
        "Downloading benchmark Parquet dataset from %s...", OFFICIAL_PARQUET_URL
    )
    temp_p = target_parquet.with_suffix(".tmp")
    req = urllib.request.Request(
        OFFICIAL_PARQUET_URL,
        headers={"User-Agent": "plate-training/0.1.0 (benchmark generator)"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp, open(temp_p, "wb") as f:
        while chunk := resp.read(65536):
            f.write(chunk)

    actual_sha = compute_sha256(temp_p)
    if actual_sha != EXPECTED_PARQUET_SHA256:
        temp_p.unlink(missing_ok=True)
        raise ValueError(
            f"Parquet SHA-256 mismatch: got {actual_sha}, expected {EXPECTED_PARQUET_SHA256}"
        )

    temp_p.replace(target_parquet)
    return target_parquet


def extract_benchmark_crops(
    parquet_path: str | Path | None = None,
    cache_dir: str | Path | None = None,
    force: bool = False,
) -> tuple[Path, Path]:
    """
    Extract deterministic 322 detector crops (64x128 PNG) and benchmark labels into cache.

    Returns:
        tuple[Path, Path]: (crops_dir, labels_json_path)
    """
    target_crops_dir = get_crops_dir(cache_dir)
    target_labels_path = get_benchmark_labels_path(cache_dir)

    target_crops_dir.mkdir(parents=True, exist_ok=True)
    existing_crops = sorted(target_crops_dir.glob("crop_*.png"))

    if len(existing_crops) == 322 and target_labels_path.is_file() and not force:
        logger.info(
            "322 crops and benchmark labels already prepared: %s", target_crops_dir
        )
        return target_crops_dir, target_labels_path

    p_file = find_or_download_parquet(parquet_path, cache_dir)
    table = pq.read_table(str(p_file))
    num_rows = len(table)

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

    import open_image_models

    detector: Any = open_image_models.create_detector(
        model="yolo-v9-t-384-license-plate-end2end",
        conf_thresh=0.01,
    )

    margin = 4
    labels_records = []

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

        if len(detections) > 0:
            best_det = max(
                detections, key=lambda d: d.score if hasattr(d, "score") else 0.0
            )
            bbox = best_det.bounding_box
            x1 = max(int(bbox.x1) - margin, 0)
            y1 = max(int(bbox.y1) - margin, 0)
            x2 = min(int(bbox.x2) + margin, W)
            y2 = min(int(bbox.y2) + margin, H)
        else:
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

        crop_filename = f"crop_{idx:03d}.png"
        crop_file = target_crops_dir / crop_filename
        cv2.imwrite(str(crop_file), resized)

        raw_target = str(table["target"][table_idx].as_py()[0])
        norm_label = normalize_plate(raw_target)
        labels_records.append(
            {
                "row_index": idx,
                "table_row_index": table_idx,
                "crop_filename": crop_filename,
                "plate_text": norm_label,
            }
        )

    with open(target_labels_path, "w", encoding="utf-8") as f:
        json.dump(labels_records, f, indent=2)

    logger.info(
        "Successfully generated %d crops and saved labels to %s",
        len(vn_row_indices),
        target_labels_path,
    )
    return target_crops_dir, target_labels_path
