"""
Unit Tests and Zero-Training Proof for Manifest-to-Dataset Loader.

Tests:
1. Preprocessing parity on real detector crops (byte-for-byte max_abs_diff == 0).
2. Label encoding and decoding roundtrip on all 322 frozen labels (322/322 exact match).
3. ManifestItem dataclass-level group_id enforcement for train/val splits (G7).
4. Fail-closed split validation rejecting leaked manifests and missing files before batch generation.
5. Batch shapes, uint8 image dtypes, float32 one-hot target dtypes, and deterministic shuffling.
6. Zero-Training Proof: model.predict & model.evaluate execution on synthetic manifest
   without any gradient update (max weight difference == 0.0).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np
import pytest

os.environ.setdefault("KERAS_BACKEND", "torch")

# Dependencies check
pytest.importorskip("keras")
pytest.importorskip("torch")
pytest.importorskip("cv2")
pytest.importorskip("fast_plate_ocr")

from fast_plate_ocr.core.process import read_and_resize_plate_image  # noqa: E402
from fast_plate_ocr.train.model.loss import cce_loss  # noqa: E402
from fast_plate_ocr.train.model.metric import cat_acc_metric, plate_acc_metric  # noqa: E402

from plate_training.dataset import (  # noqa: E402
    DEFAULT_ALPHABET,
    DEFAULT_PAD_CHAR,
    PlateDataset,
    build_dataset,
    decode_plate_prediction,
    encode_plate_label,
    preprocess_plate_image,
)
from plate_training.manifest import ManifestItem, compute_file_sha256  # noqa: E402
from plate_training.model import load_aligned_model  # noqa: E402
from plate_training.split import DataLeakageError  # noqa: E402


@pytest.mark.parity
@pytest.mark.heavy
def test_preprocessing_parity_with_production(heavy_crops_dir: Path) -> None:
    """
    Prove byte-for-byte parity (max_abs_diff == 0) between dataset preprocessor
    and fast_plate_ocr production recognizer preprocessing across all 322 real detector crops.
    """
    crop_files = sorted(heavy_crops_dir.glob("crop_*.png"))
    assert len(crop_files) == 322, f"Expected 322 crops, found {len(crop_files)}"

    for crop_path in crop_files:
        prod_img = read_and_resize_plate_image(
            crop_path,
            img_height=64,
            img_width=128,
            image_color_mode="rgb",
            keep_aspect_ratio=False,
            interpolation_method="linear",
        )
        loader_img = preprocess_plate_image(
            crop_path,
            img_height=64,
            img_width=128,
            color_mode="rgb",
        )

        assert prod_img.shape == (64, 128, 3)
        assert loader_img.shape == (64, 128, 3)
        assert prod_img.dtype == np.uint8
        assert loader_img.dtype == np.uint8

        max_diff = int(np.max(np.abs(prod_img.astype(int) - loader_img.astype(int))))
        assert max_diff == 0, (
            f"Preprocessing difference {max_diff} > 0 on {crop_path.name}"
        )


@pytest.mark.unit
def test_label_roundtrip_all_322_frozen_labels() -> None:
    """
    Verify encode-and-decode round-trip across all 322 real Vietnamese plate labels:
    100% (322 / 322) exact match.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from evaluate_frozen_test import find_cached_parquet, load_parquet_vn_records

    try:
        parquet_path = find_cached_parquet()
        records = load_parquet_vn_records(parquet_path)
    except FileNotFoundError:
        pytest.skip("Parquet dataset not found in cache.")

    assert len(records) == 322
    matches = 0
    for r in records:
        lbl = r.gt_normalized
        one_hot = encode_plate_label(
            lbl, max_slots=10, alphabet=DEFAULT_ALPHABET, pad_char=DEFAULT_PAD_CHAR
        )
        assert one_hot.shape == (10, 37)
        assert one_hot.dtype == np.float32

        decoded = decode_plate_prediction(
            one_hot, alphabet=DEFAULT_ALPHABET, pad_char=DEFAULT_PAD_CHAR
        )
        if decoded == lbl:
            matches += 1

    assert matches == 322, f"Expected 322 / 322 roundtrip matches, got {matches}"


@pytest.mark.leakage
def test_manifest_item_enforces_group_id_for_train_val() -> None:
    """
    Verify that ManifestItem dataclass enforces non-empty group_id for train and val splits (G7).
    """
    # 1. train split missing group_id raises ValueError
    with pytest.raises(ValueError, match="group_id is required"):
        ManifestItem(
            image_path="crops/c1.png",
            sha256="a" * 64,
            plate_text="51G12345",
            split="train",
            provenance="test",
            license="MIT",
            group_id=None,
        )

    # 2. val split with whitespace group_id raises ValueError
    with pytest.raises(ValueError, match="group_id is required"):
        ManifestItem(
            image_path="crops/c2.png",
            sha256="b" * 64,
            plate_text="51G12345",
            split="val",
            provenance="test",
            license="MIT",
            group_id="   ",
        )

    # 3. frozen-test split without group_id is accepted
    item_test = ManifestItem(
        image_path="crops/c3.png",
        sha256="c" * 64,
        plate_text="51G12345",
        split="frozen-test",
        provenance="test",
        license="MIT",
        group_id=None,
    )
    assert item_test.group_id is None

    # 4. train split with valid group_id is accepted
    item_train = ManifestItem(
        image_path="crops/c4.png",
        sha256="d" * 64,
        plate_text="51G12345",
        split="train",
        provenance="test",
        license="MIT",
        group_id="vehicle_999",
    )
    assert item_train.group_id == "vehicle_999"


@pytest.mark.leakage
def test_dataset_refuses_manifest_with_leakage_and_missing_files() -> None:
    """
    Verify fail-closed split validation: loader refuses any manifest failing validate_splits.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        crop_file = root / "crop_leak.png"
        img = np.zeros((64, 128, 3), dtype=np.uint8)
        cv2.imwrite(str(crop_file), img)
        sha = compute_file_sha256(crop_file)

        # Create manifest with cross-split duplicate group_id
        item1 = ManifestItem(
            image_path="crop_leak.png",
            sha256=sha,
            plate_text="51G11111",
            split="train",
            provenance="test",
            license="MIT",
            group_id="shared_vehicle_id",
        )
        item2 = ManifestItem(
            image_path="crop_leak.png",
            sha256=sha,
            plate_text="51G11111",
            split="val",
            provenance="test",
            license="MIT",
            group_id="shared_vehicle_id",
        )

        with pytest.raises(DataLeakageError):
            PlateDataset(
                items=[item1, item2],
                base_dir=root,
                validate_split=True,
            )

        # Also test FileNotFoundError on missing file
        missing_item = ManifestItem(
            image_path="nonexistent_crop.png",
            sha256="e" * 64,
            plate_text="51G22222",
            split="train",
            provenance="test",
            license="MIT",
            group_id="vehicle_missing",
        )
        with pytest.raises(FileNotFoundError):
            PlateDataset(
                items=[missing_item],
                base_dir=root,
                validate_split=True,
            )


@pytest.mark.unit
def test_dataset_batch_shapes_dtypes_and_shuffling() -> None:
    """
    Verify batch dimensions, uint8/float32 dtypes, and deterministic shuffling reproducibility.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        items = []
        for i in range(6):
            c_path = root / f"crop_{i}.png"
            c_img = np.full((64, 128, 3), fill_value=i * 20, dtype=np.uint8)
            cv2.imwrite(str(c_path), c_img)
            sha = compute_file_sha256(c_path)
            items.append(
                ManifestItem(
                    image_path=f"crop_{i}.png",
                    sha256=sha,
                    plate_text=f"29A0000{i}",
                    split="train",
                    provenance="test",
                    license="MIT",
                    group_id=f"veh_{i}",
                )
            )

        # 1. Deterministic shuffling check
        ds1 = PlateDataset(
            items=items,
            batch_size=2,
            shuffle=True,
            seed=42,
            base_dir=root,
            validate_split=False,
        )
        ds2 = PlateDataset(
            items=items,
            batch_size=2,
            shuffle=True,
            seed=42,
            base_dir=root,
            validate_split=False,
        )
        ds3 = PlateDataset(
            items=items,
            batch_size=2,
            shuffle=True,
            seed=99,
            base_dir=root,
            validate_split=False,
        )

        assert np.array_equal(ds1.indices, ds2.indices), (
            "Identical seed must yield identical indices"
        )
        assert not np.array_equal(ds1.indices, ds3.indices), (
            "Different seed should yield different indices"
        )

        # 2. Batch shapes & dtypes
        assert len(ds1) == 3
        batch_x, batch_y = ds1[0]
        assert batch_x.shape == (2, 64, 128, 3)
        assert batch_x.dtype == np.uint8
        assert "plate" in batch_y
        assert batch_y["plate"].shape == (2, 10, 37)
        assert batch_y["plate"].dtype == np.float32

        # 3. Epoch progression
        idx_epoch_0 = np.copy(ds1.indices)
        ds1.on_epoch_end()
        assert not np.array_equal(ds1.indices, idx_epoch_0), (
            "on_epoch_end must permute indices"
        )


@pytest.mark.parity
@pytest.mark.heavy
def test_zero_training_proof_predict_and_evaluate(heavy_weights_path: Path) -> None:
    """
    Zero-Training Proof:
      - Construct tiny synthetic manifest (4 plate-like crops, 0 real plates).
      - Build PlateDataset via build_dataset factory.
      - Load published weights into aligned Keras model.
      - Compile with cce_loss and accuracy metrics.
      - Execute model.predict and model.evaluate without any weight updates.
      - Verify max_abs_diff on model weights before and after evaluation is exactly 0.0.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        manifest_file = root / "synthetic_manifest.json"

        # 1. Generate 4 synthetic crops
        rng = np.random.default_rng(42)
        items = []
        for i, text in enumerate(["29A12345", "51F99999", "43B88888", "30E77777"]):
            c_path = root / f"synth_crop_{i}.png"
            noise = rng.integers(50, 200, size=(64, 128, 3), dtype=np.uint8)
            cv2.imwrite(str(c_path), noise)
            sha = hashlib.sha256(c_path.read_bytes()).hexdigest()

            items.append(
                ManifestItem(
                    image_path=f"synth_crop_{i}.png",
                    sha256=sha,
                    plate_text=text,
                    split="train",
                    provenance="synthetic-zero-training",
                    license="MIT",
                    group_id=f"synth_veh_{i:03d}",
                )
            )

        serializable = [it.to_dict() for it in items]
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)

        # 2. Build dataset via factory function
        dataset = build_dataset(
            manifest_path=manifest_file,
            batch_size=2,
            shuffle=False,
            base_dir=root,
            drop_region_head=True,
            validate_split=False,
        )
        assert len(dataset) == 2

        # 3. Load aligned model (drop_region_head=True -> 581,458 parameters)
        model = load_aligned_model(
            weights_path=heavy_weights_path, drop_region_head=True
        )
        cce = cce_loss(vocabulary_size=37, label_smoothing=0.01)
        p_acc = plate_acc_metric(max_plate_slots=10, vocabulary_size=37)
        c_acc = cat_acc_metric(max_plate_slots=10, vocabulary_size=37)
        model.compile(loss={"plate": cce}, metrics={"plate": [p_acc, c_acc]})

        # 4. Record weights before evaluation
        w_before = [np.copy(w.numpy()) for w in model.weights]

        # 5. Run predict
        preds = model.predict(dataset, verbose=0)
        plate_preds = preds["plate"] if isinstance(preds, dict) else preds
        assert plate_preds.shape == (4, 10, 37)

        # 6. Run evaluate
        eval_metrics = model.evaluate(dataset, verbose=0)
        loss_val = float(eval_metrics[0])
        plate_acc_val = float(eval_metrics[1])
        char_acc_val = float(eval_metrics[2])

        assert np.isfinite(loss_val)
        assert 0.0 <= plate_acc_val <= 1.0
        assert 0.0 <= char_acc_val <= 1.0

        print(f"\n[Zero-Training Proof] Loss: {loss_val:.6f}")
        print(f"[Zero-Training Proof] Plate Acc: {plate_acc_val:.6f}")
        print(f"[Zero-Training Proof] Char Acc: {char_acc_val:.6f}")

        # 7. Prove ZERO weight updates (0 gradient updates, weights strictly unchanged)
        w_after = [w.numpy() for w in model.weights]
        max_w_diff = max(
            float(np.max(np.abs(b - a))) for b, a in zip(w_before, w_after, strict=True)
        )
        assert max_w_diff == 0.0, (
            f"Model weights changed during evaluation! max_diff={max_w_diff}"
        )
