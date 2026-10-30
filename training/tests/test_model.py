"""
Tests for CCT-XS Model Architecture Realignment, Weight Loading,
Equivalence Proof on 322 Real Detector Crops, Mutation Testing, and Export Parity.
"""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("KERAS_BACKEND", "torch")

pytest.importorskip("keras")
pytest.importorskip("torch")
pytest.importorskip("fast_plate_ocr")
pytest.importorskip("onnx")
pytest.importorskip("onnxruntime")
pytest.importorskip("cv2")

import cv2  # noqa: E402
import keras  # noqa: E402
import onnx  # noqa: E402
import onnxruntime as ort  # noqa: E402
from onnx import numpy_helper  # noqa: E402

from plate_training.model import (  # noqa: E402
    build_model,
    count_model_parameters,
    inspect_model_topology,
    load_aligned_model,
    slice_plate_model,
)
from scripts.export_model import export_keras_to_onnx, patch_patch_extractor_if_needed  # noqa: E402

ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"
PAD_CHAR = "_"

CACHED_ONNX_PATH = (
    Path.home()
    / ".cache"
    / "fast-plate-ocr"
    / "cct-xs-v2-global-model"
    / "cct_xs_v2_global.onnx"
)


def decode_prediction_logits(logits: np.ndarray) -> list[str]:
    """Decode raw (B, 10, 37) plate logits to plate strings."""
    preds = np.argmax(logits, axis=-1)
    decoded: list[str] = []
    for row in preds:
        s = "".join(ALPHABET[idx] for idx in row).rstrip(PAD_CHAR)
        decoded.append(s)
    return decoded


def load_322_detector_crops(crops_dir: Path) -> np.ndarray:
    """Load all 322 real detector crops as uint8 RGB (322, 64, 128, 3)."""
    assert crops_dir.is_dir(), f"Crops directory missing: {crops_dir}"
    crop_files = sorted(
        crops_dir.glob("crop_*.png"),
        key=lambda p: int(p.stem.split("_")[1]),
    )
    assert len(crop_files) == 322, f"Expected 322 crops, found {len(crop_files)}"

    crops = [cv2.cvtColor(cv2.imread(str(f)), cv2.COLOR_BGR2RGB) for f in crop_files]
    crops_np = np.stack(crops, axis=0)
    assert crops_np.shape == (322, 64, 128, 3)
    assert crops_np.dtype == np.uint8
    return crops_np


@pytest.mark.parity
def test_model_topology_and_parameter_counts() -> None:
    """
    Verify aligned Keras model topology (18 layers, 7 TransformerBlocks, 2 outputs)
    and parameter count matches published cct_xs_v2_global:
      - Keras total: 644,215 (643,351 trainable + 864 non-trainable)
      - ONNX initializers: 791,700
    """
    keras.backend.clear_session()
    model = build_model()

    assert model is not None
    param_counts = count_model_parameters(model)
    assert param_counts["total"] == 644_215
    assert param_counts["trainable"] == 643_351
    assert param_counts["non_trainable"] == 864

    topology = inspect_model_topology(model)
    assert topology["config_layers_count"] == 18
    assert topology["transformer_blocks_count"] == 7
    assert "plate" in topology["output_names"]
    assert "region" in topology["output_names"]

    # Verify official ONNX initializer count
    if CACHED_ONNX_PATH.is_file():
        proto = onnx.load(str(CACHED_ONNX_PATH))
        total_onnx_params = sum(
            numpy_helper.to_array(init).size for init in proto.graph.initializer
        )
        assert total_onnx_params == 791_700


@pytest.mark.parity
@pytest.mark.heavy
def test_load_published_weights_full_and_forward_pass(heavy_weights_path: Path) -> None:
    """
    Verify loading published weights into the aligned 18-layer model
    and running forward pass on both 'plate' and 'region' outputs.
    """
    model = load_aligned_model(weights_path=heavy_weights_path, drop_region_head=False)
    assert model.count_params() == 644_215

    dummy = np.random.randint(0, 256, size=(2, 64, 128, 3), dtype=np.uint8)
    outputs = model(dummy, training=False)

    assert isinstance(outputs, dict)
    assert "plate" in outputs
    assert "region" in outputs
    assert outputs["plate"].shape == (2, 10, 37)
    assert outputs["region"].shape == (2, 66)


@pytest.mark.parity
@pytest.mark.heavy
def test_dropped_region_model_and_slicing_equivalence(heavy_weights_path: Path) -> None:
    """
    Verify dropping or slicing the region head produces identical plate logits (max diff == 0.0).
    Proves mathematical independence of the plate branch from the 62,757 region head parameters.
    """
    # Full model
    full_model = load_aligned_model(
        weights_path=heavy_weights_path, drop_region_head=False
    )

    # Dropped region model
    no_region_model = load_aligned_model(
        weights_path=heavy_weights_path, drop_region_head=True
    )
    assert no_region_model.count_params() == 581_458
    assert 644_215 - 581_458 == 62_757  # Exactly 62,757 region params dropped

    # Functional slicing of full model
    sliced_model = slice_plate_model(full_model)

    dummy = np.random.randint(0, 256, size=(4, 64, 128, 3), dtype=np.uint8)

    full_plate = full_model(dummy, training=False)["plate"].detach().cpu().numpy()
    no_reg_plate = (
        no_region_model(dummy, training=False)["plate"].detach().cpu().numpy()
    )
    sliced_plate = sliced_model(dummy, training=False).detach().cpu().numpy()

    diff_no_reg = float(np.max(np.abs(full_plate - no_reg_plate)))
    diff_sliced = float(np.max(np.abs(full_plate - sliced_plate)))

    assert diff_no_reg == 0.0, f"Expected 0.0 max diff, got {diff_no_reg}"
    assert diff_sliced == 0.0, f"Expected 0.0 max diff, got {diff_sliced}"


@pytest.mark.parity
@pytest.mark.heavy
def test_equivalence_proof_on_all_322_real_detector_crops(
    heavy_weights_path: Path, heavy_crops_dir: Path
) -> None:
    """
    Equivalence Proof on all 322 real detector crops:
      - max_abs_diff < 1e-4
      - mean_abs_diff < 1e-6
      - 322 / 322 decoded strings match production ONNX (100% identical)
    """
    if not CACHED_ONNX_PATH.is_file():
        pytest.skip("Required ONNX checkpoint not found.")

    crops_np = load_322_detector_crops(heavy_crops_dir)

    # 1. Keras model prediction
    model = load_aligned_model(weights_path=heavy_weights_path, drop_region_head=False)
    k_out = model(crops_np, training=False)
    k_logits = k_out["plate"].detach().cpu().numpy().astype(np.float32)

    # 2. Production ONNX prediction
    session_opts = ort.SessionOptions()
    session_opts.inter_op_num_threads = 1
    session_opts.intra_op_num_threads = 1
    ort_sess = ort.InferenceSession(
        str(CACHED_ONNX_PATH), session_opts, providers=["CPUExecutionProvider"]
    )
    o_logits = ort_sess.run(["plate"], {"input": crops_np})[0].astype(np.float32)

    # 3. Numerical diff
    diff = np.abs(k_logits - o_logits)
    max_abs_diff = float(np.max(diff))
    mean_abs_diff = float(np.mean(diff))

    assert max_abs_diff < 1e-4, (
        f"max_abs_diff {max_abs_diff:.6e} exceeded 1e-4 tolerance"
    )
    assert mean_abs_diff < 1e-6, (
        f"mean_abs_diff {mean_abs_diff:.6e} exceeded 1e-6 tolerance"
    )

    # 4. Decoded string equivalence across all 322 crops
    k_strings = decode_prediction_logits(k_logits)
    o_strings = decode_prediction_logits(o_logits)

    matches = sum(1 for k, o in zip(k_strings, o_strings, strict=True) if k == o)
    assert matches == 322, f"Expected 322 matching strings, got {matches} / 322"


@pytest.mark.parity
@pytest.mark.heavy
def test_red_then_green_weight_shuffle_mutation(
    heavy_weights_path: Path, heavy_crops_dir: Path
) -> None:
    """
    Red-then-Green Weight Shuffle Mutation Test:
      - RED phase: shuffle the weights of the 'plate' output layer, assert max_abs_diff > 0.5
        and string matches collapse.
      - GREEN phase: restore original weights, assert max_abs_diff == 0.0 and 322/322 matches.
    """
    crops_np = load_322_detector_crops(heavy_crops_dir)
    model = load_aligned_model(weights_path=heavy_weights_path, drop_region_head=False)

    baseline_logits = (
        model(crops_np, training=False)["plate"]
        .detach()
        .cpu()
        .numpy()
        .astype(np.float32)
    )
    baseline_strings = decode_prediction_logits(baseline_logits)

    # Locate 'plate' layer
    plate_layer = model.get_layer("plate")
    original_weights = [w.copy() for w in plate_layer.get_weights()]

    # Apply shuffle mutation (RED)
    rng = np.random.default_rng(2026)
    shuffled_weights = []
    for w in original_weights:
        w_flat = w.flatten().copy()
        rng.shuffle(w_flat)
        shuffled_weights.append(w_flat.reshape(w.shape))

    plate_layer.set_weights(shuffled_weights)
    mutated_logits = (
        model(crops_np, training=False)["plate"]
        .detach()
        .cpu()
        .numpy()
        .astype(np.float32)
    )

    red_diff = float(np.max(np.abs(mutated_logits - baseline_logits)))
    mutated_strings = decode_prediction_logits(mutated_logits)
    red_matches = sum(
        1 for m, b in zip(mutated_strings, baseline_strings, strict=True) if m == b
    )

    assert red_diff > 0.5, f"Expected mutation diff > 0.5, got {red_diff}"
    assert red_matches < 30, (
        f"Expected string accuracy to collapse, got {red_matches}/322"
    )

    # Restore original weights (GREEN)
    plate_layer.set_weights(original_weights)
    restored_logits = (
        model(crops_np, training=False)["plate"]
        .detach()
        .cpu()
        .numpy()
        .astype(np.float32)
    )

    green_diff = float(np.max(np.abs(restored_logits - baseline_logits)))
    restored_strings = decode_prediction_logits(restored_logits)
    green_matches = sum(
        1 for r, b in zip(restored_strings, baseline_strings, strict=True) if r == b
    )

    assert green_diff == 0.0, f"Expected 0.0 diff after restoration, got {green_diff}"
    assert green_matches == 322, (
        f"Expected 322 matches after restoration, got {green_matches}"
    )


@pytest.mark.parity
@pytest.mark.heavy
def test_export_model_onnx_parity_on_322_crops(
    heavy_weights_path: Path, heavy_crops_dir: Path, tmp_path: Path
) -> None:
    """
    Verify exported ONNX from export_model.py matches production ONNX on all 322 real crops.
    """
    if not CACHED_ONNX_PATH.is_file():
        pytest.skip("Required production ONNX checkpoint not found.")

    patch_patch_extractor_if_needed()
    crops_np = load_322_detector_crops(heavy_crops_dir)

    # Load model and export
    model = load_aligned_model(weights_path=heavy_weights_path, drop_region_head=True)
    from fast_plate_ocr.train.model.config import load_plate_config_from_yaml

    plate_cfg = load_plate_config_from_yaml(
        Path("training/configs/plate_config_vn.yaml")
    )

    exported_onnx_path = tmp_path / "cct_xs_exported_parity.onnx"
    export_keras_to_onnx(
        model=model,
        plate_cfg=plate_cfg,
        output_onnx_path=exported_onnx_path,
        simplify=True,
        drop_region_head=True,
    )

    assert exported_onnx_path.is_file()

    # Run inference on exported ONNX
    sess_exp = ort.InferenceSession(
        str(exported_onnx_path), providers=["CPUExecutionProvider"]
    )
    exp_logits = sess_exp.run(["plate"], {"input": crops_np})[0].astype(np.float32)

    # Run inference on production ONNX
    sess_prod = ort.InferenceSession(
        str(CACHED_ONNX_PATH), providers=["CPUExecutionProvider"]
    )
    prod_logits = sess_prod.run(["plate"], {"input": crops_np})[0].astype(np.float32)

    diff = np.abs(exp_logits - prod_logits)
    max_diff = float(np.max(diff))
    mean_diff = float(np.mean(diff))

    assert max_diff < 1e-4, f"max_diff {max_diff} exceeded 1e-4 tolerance"
    assert mean_diff < 1e-6, f"mean_diff {mean_diff} exceeded 1e-6 tolerance"

    exp_strings = decode_prediction_logits(exp_logits)
    prod_strings = decode_prediction_logits(prod_logits)
    matches = sum(1 for e, p in zip(exp_strings, prod_strings, strict=True) if e == p)
    assert matches == 322, f"Expected 322 matching strings, got {matches} / 322"


@pytest.mark.parity
@pytest.mark.heavy
def test_load_aligned_model_tensor_verification_red_then_green(
    heavy_weights_path: Path, tmp_path: Path
) -> None:
    """
    Red-then-Green test for post-load tensor verification in load_aligned_model:
      - RED Phase 1: Corrupted weights file with missing plate-path layer -> raises ValueError.
      - RED Phase 2: Corrupted weights file with mismatched tensor shape -> raises ValueError.
      - GREEN Phase: Valid published weights -> passes with 137 tensors verified on single-head,
        159 tensors on full model, exactly matching 0.0 diff.
    """
    import io
    import zipfile

    import h5py

    # 1. RED Phase 1: Missing plate-path layer in weights archive
    with zipfile.ZipFile(heavy_weights_path, "r") as zin:
        h5_bytes = zin.read("model.weights.h5")
        cfg_bytes = zin.read("config.json")
        meta_bytes = zin.read("metadata.json")

    bio_missing = io.BytesIO()
    with (
        h5py.File(io.BytesIO(h5_bytes), "r") as fin,
        h5py.File(bio_missing, "w") as f_out,
    ):
        for k in fin:
            if k != "layers":
                fin.copy(k, f_out)
            else:
                layers_grp = f_out.create_group("layers")
                for lk in fin["layers"]:
                    if lk != "vocabulary_projection":
                        fin["layers"].copy(lk, layers_grp)

    corrupted_missing_layer = tmp_path / "corrupted_missing_layer.keras"
    with zipfile.ZipFile(corrupted_missing_layer, "w") as z_out:
        z_out.writestr("metadata.json", meta_bytes)
        z_out.writestr("config.json", cfg_bytes)
        z_out.writestr("model.weights.h5", bio_missing.getvalue())

    with pytest.raises(
        (ValueError, RuntimeError),
        match="Corrupted weights archive|vocabulary_projection|Reference weight loading",
    ):
        load_aligned_model(
            weights_path=corrupted_missing_layer,
            drop_region_head=True,
            verify_tensors=True,
        )

    # 2. RED Phase 2: Mismatched tensor shape in weights archive
    bio_shape = io.BytesIO()
    with (
        h5py.File(io.BytesIO(h5_bytes), "r") as fin,
        h5py.File(bio_shape, "w") as f_out,
    ):
        for k in fin:
            if k != "layers":
                fin.copy(k, f_out)
            else:
                layers_grp = f_out.create_group("layers")
                for lk in fin["layers"]:
                    if lk != "vocabulary_projection":
                        fin["layers"].copy(lk, layers_grp)
                    else:
                        vp = layers_grp.create_group("vocabulary_projection")
                        clf = vp.create_group("classifier")
                        vars_grp = clf.create_group("vars")
                        # Inject bad shape (96, 30) instead of (96, 37)
                        vars_grp.create_dataset(
                            "0", data=np.zeros((96, 30), dtype=np.float32)
                        )
                        vars_grp.create_dataset(
                            "1", data=np.zeros((30,), dtype=np.float32)
                        )

    corrupted_bad_shape = tmp_path / "corrupted_bad_shape.keras"
    with zipfile.ZipFile(corrupted_bad_shape, "w") as z_out:
        z_out.writestr("metadata.json", meta_bytes)
        z_out.writestr("config.json", cfg_bytes)
        z_out.writestr("model.weights.h5", bio_shape.getvalue())

    with pytest.raises((ValueError, RuntimeError)):
        load_aligned_model(
            weights_path=corrupted_bad_shape,
            drop_region_head=True,
            verify_tensors=True,
        )

    # 3. GREEN Phase: Real cct_xs_v2_global.keras weights pass cleanly
    model_single, v_info_single = load_aligned_model(
        weights_path=heavy_weights_path,
        drop_region_head=True,
        verify_tensors=True,
        return_verification_info=True,
    )
    assert model_single is not None
    assert v_info_single["verified"] is True
    assert v_info_single["compared_tensors_count"] == 137
    assert v_info_single["max_weight_diff"] == 0.0
    assert v_info_single["skipped_region_head_layers"] == [
        "region_pre_pool_transformer_block_1",
        "region_seq_pool",
        "region",
    ]

    model_full, v_info_full = load_aligned_model(
        weights_path=heavy_weights_path,
        drop_region_head=False,
        verify_tensors=True,
        return_verification_info=True,
    )
    assert model_full is not None
    assert v_info_full["verified"] is True
    assert v_info_full["compared_tensors_count"] == 159
    assert v_info_full["max_weight_diff"] == 0.0
    assert v_info_full["skipped_region_head_layers"] == []
