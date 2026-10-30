"""
Plate recognition model building, weight loading, and region head slicing.

Provides wrappers around fast_plate_ocr model builders ensuring proper alignment
with the published 18-layer, 7-TransformerBlock cct_xs_v2_global architecture
(644,215 Keras parameters / 791,700 ONNX initializers).
"""

from __future__ import annotations

import io
import logging
import os
import zipfile
from pathlib import Path
from typing import Any

import h5py
import numpy as np

# Default to torch backend for Keras 3
os.environ.setdefault("KERAS_BACKEND", "torch")

import fast_plate_ocr.train.model.layers  # Registers custom layers  # noqa: E402, F401
import fast_plate_ocr.train.model.model_builders as mb  # noqa: E402
import fast_plate_ocr.train.model.model_schema as ms  # noqa: E402
import keras  # noqa: E402
from fast_plate_ocr.train.model.config import (  # noqa: E402
    PlateConfig,
    load_plate_config_from_yaml,
)
from fast_plate_ocr.train.model.model_schema import AnyModelConfig  # noqa: E402

logger = logging.getLogger("plate_training.model")


DEFAULT_MODEL_CONFIG_PATH = Path("training/configs/model_cct_xs.yaml")
DEFAULT_PLATE_CONFIG_PATH = Path("training/configs/plate_config_vn.yaml")


def get_default_weights_path() -> Path:
    """Return default path to cached published weights."""
    from plate_training.cache import get_weights_path

    return get_weights_path()


def build_model(
    model_cfg: AnyModelConfig | None = None,
    plate_cfg: PlateConfig | None = None,
    enable_region_head: bool | None = None,
    model_config_path: Path | str | None = None,
    plate_config_path: Path | str | None = None,
) -> keras.Model:
    """
    Build Keras model with automatic region head activation when plate_regions is present.

    If enable_region_head is not explicitly passed, it defaults to bool(plate_cfg.plate_regions).
    This ensures that when 66 regions are configured, the full 18-layer, 7-TransformerBlock
    architecture (644,215 parameters) is built to match cct_xs_v2_global.keras.
    """
    if plate_cfg is None:
        p_path = Path(plate_config_path or DEFAULT_PLATE_CONFIG_PATH)
        plate_cfg = load_plate_config_from_yaml(p_path)

    if model_cfg is None:
        m_path = Path(model_config_path or DEFAULT_MODEL_CONFIG_PATH)
        model_cfg = ms.load_model_config_from_yaml(m_path)

    if enable_region_head is None:
        enable_region_head = bool(plate_cfg.plate_regions)

    logger.debug(
        "Building model: enable_region_head=%s (plate_regions=%d)",
        enable_region_head,
        len(plate_cfg.plate_regions) if plate_cfg.plate_regions else 0,
    )

    return mb.build_model(model_cfg, plate_cfg, enable_region_head=enable_region_head)


DROPPED_REGION_LAYERS: tuple[str, ...] = (
    "region_pre_pool_transformer_block_1",
    "region_seq_pool",
    "region",
)

EXPECTED_PLATE_H5_GROUPS: tuple[str, ...] = (
    "sequential",
    "mlp",
    "position_embedding",
    "token_reducer",
    "transformer_block",
    "transformer_block_1",
    "transformer_block_2",
    "transformer_block_3",
    "transformer_block_4",
    "transformer_block_5",
    "vocabulary_projection",
)


def inspect_keras_archive(weights_path: Path | str) -> dict[str, tuple[int, ...]]:
    """
    Inspect .keras zip archive and model.weights.h5 structure directly.

    Verifies that the file is a valid zip archive containing model.weights.h5,
    checks that all expected plate-path groups exist under layers/,
    and returns a dictionary mapping dataset path to shape.
    """
    w_path = Path(weights_path)
    if not w_path.is_file():
        raise FileNotFoundError(f"Weights file not found: {w_path}")

    try:
        with zipfile.ZipFile(w_path, "r") as zin:
            namelist = zin.namelist()
            if "model.weights.h5" not in namelist:
                raise ValueError(
                    f"Corrupted .keras archive at {w_path}: missing 'model.weights.h5'"
                )
            h5_bytes = zin.read("model.weights.h5")
    except zipfile.BadZipFile as e:
        raise ValueError(f"Invalid .keras zip archive at {w_path}: {e}") from e

    datasets: dict[str, tuple[int, ...]] = {}
    with h5py.File(io.BytesIO(h5_bytes), "r") as f:
        if "layers" not in f:
            raise ValueError(
                f"Corrupted model.weights.h5 in {w_path}: missing 'layers' group"
            )
        layers_grp = f["layers"]
        for expected_grp in EXPECTED_PLATE_H5_GROUPS:
            if expected_grp not in layers_grp:
                raise ValueError(
                    f"Corrupted weights archive: missing plate-path layer group "
                    f"'{expected_grp}' in model.weights.h5"
                )

        def record_dataset(name: str, obj: Any) -> None:
            if hasattr(obj, "shape"):
                datasets[name] = tuple(obj.shape)

        layers_grp.visititems(record_dataset)

    return datasets


def verify_loaded_weights(
    target_model: keras.Model,
    weights_path: Path | str,
    drop_region_head: bool = False,
    model_config_path: Path | str | None = None,
    plate_config_path: Path | str | None = None,
) -> dict[str, Any]:
    """
    Post-load tensor verification for CCT-XS model weights.

    1. Inspects the .keras archive and verifies plate-path groups in model.weights.h5.
    2. Loads a reference 18-layer model with skip_mismatch=False.
    3. Compares every single plate-path weight tensor between target_model and reference model.
    4. Raises ValueError or RuntimeError if any plate-path layer/tensor is missing,
       has a mismatched shape, or differs in value.
    5. Returns a dict reporting exact count of compared tensors and list of skipped region head layers.
    """
    # 1. Direct inspection of .keras archive and model.weights.h5
    inspect_keras_archive(weights_path)

    # 2. Reference model loading with skip_mismatch=False
    p_path = Path(plate_config_path or DEFAULT_PLATE_CONFIG_PATH)
    m_path = Path(model_config_path or DEFAULT_MODEL_CONFIG_PATH)
    plate_cfg = load_plate_config_from_yaml(p_path)
    model_cfg = ms.load_model_config_from_yaml(m_path)

    ref_model = mb.build_model(model_cfg, plate_cfg, enable_region_head=True)
    try:
        ref_model.load_weights(str(weights_path), skip_mismatch=False)
    except Exception as e:
        raise ValueError(
            f"Reference weight loading failed with skip_mismatch=False: {e}"
        ) from e

    # 3. Filter reference weights for plate path vs region head
    ref_plate_weights = [
        w
        for w in ref_model.weights
        if not any(
            w.path.startswith(layer_name + "/") for layer_name in DROPPED_REGION_LAYERS
        )
    ]

    expected_count = 137 if drop_region_head else 159
    if drop_region_head:
        if len(ref_plate_weights) != 137:
            raise ValueError(
                f"Expected 137 reference plate-path weights, found {len(ref_plate_weights)}"
            )
        if len(target_model.weights) != 137:
            raise ValueError(
                f"Target single-head model has {len(target_model.weights)} weights, expected 137"
            )
        ref_weights_to_compare = ref_plate_weights
    else:
        if len(ref_model.weights) != 159:
            raise ValueError(
                f"Expected 159 reference model weights, found {len(ref_model.weights)}"
            )
        if len(target_model.weights) != 159:
            raise ValueError(
                f"Target full model has {len(target_model.weights)} weights, expected 159"
            )
        ref_weights_to_compare = ref_model.weights

    # 4. Compare every weight tensor
    compared_count = 0
    max_diff = 0.0
    for rw, tw in zip(ref_weights_to_compare, target_model.weights, strict=True):
        if rw.shape != tw.shape:
            raise ValueError(
                f"Shape mismatch for weight '{rw.path}': reference {rw.shape} vs target {tw.shape}"
            )
        r_np = rw.numpy()
        t_np = tw.numpy()
        diff = float(np.max(np.abs(r_np - t_np)))
        if diff > 1e-6:
            raise ValueError(
                f"Weight value mismatch for '{rw.path}': max diff = {diff} > 1e-6"
            )
        max_diff = max(max_diff, diff)
        compared_count += 1

    if compared_count != expected_count:
        raise ValueError(
            f"Compared tensor count mismatch: {compared_count} != expected {expected_count}"
        )

    skipped_layers = list(DROPPED_REGION_LAYERS) if drop_region_head else []

    logger.info(
        "Post-load tensor verification passed: %d tensors verified (max diff=%.6e), "
        "skipped region layers: %s",
        compared_count,
        max_diff,
        skipped_layers,
    )

    return {
        "compared_tensors_count": compared_count,
        "skipped_region_head_layers": skipped_layers,
        "max_weight_diff": max_diff,
        "verified": True,
    }


def load_aligned_model(
    weights_path: Path | str | None = None,
    model_config_path: Path | str | None = None,
    plate_config_path: Path | str | None = None,
    drop_region_head: bool = False,
    enable_region_head: bool | None = None,
    verify_tensors: bool = True,
    return_verification_info: bool = False,
) -> keras.Model | tuple[keras.Model, dict[str, Any]]:
    """
    Build aligned CCT-XS model, load published checkpoint weights, and verify tensors.

    Parameters
    ----------
    weights_path : Path | str | None
        Path to .keras weights checkpoint (defaults to cached cct_xs_v2_global.keras).
    model_config_path : Path | str | None
        Path to model YAML config (defaults to training/configs/model_cct_xs.yaml).
    plate_config_path : Path | str | None
        Path to plate YAML config (defaults to training/configs/plate_config_vn.yaml).
    drop_region_head : bool
        If True, builds a Vietnam-only model without the region classification head
        (581,458 parameters, 14 top-level layers) and loads weights with skip_mismatch=True.
        The resulting model has identical logits on the 'plate' output as the full model.
    enable_region_head : bool | None
        Explicit override for region head activation. If drop_region_head is True,
        enable_region_head is forced to False.
    verify_tensors : bool
        If True (default), verifies all loaded plate-path weight tensors against the
        reference weights in the .keras file.
    return_verification_info : bool
        If True, returns tuple (model, verification_info_dict). Default False returns model.

    Returns
    -------
    keras.Model | tuple[keras.Model, dict[str, Any]]
        Keras model with weights loaded and verified (or tuple with verification report).
    """
    w_path = Path(weights_path) if weights_path else get_default_weights_path()
    p_path = Path(plate_config_path or DEFAULT_PLATE_CONFIG_PATH)
    m_path = Path(model_config_path or DEFAULT_MODEL_CONFIG_PATH)

    plate_cfg = load_plate_config_from_yaml(p_path)
    model_cfg = ms.load_model_config_from_yaml(m_path)

    if drop_region_head:
        resolved_enable_region = False
    elif enable_region_head is not None:
        resolved_enable_region = enable_region_head
    else:
        resolved_enable_region = bool(plate_cfg.plate_regions)

    keras.backend.clear_session()
    model = mb.build_model(
        model_cfg, plate_cfg, enable_region_head=resolved_enable_region
    )

    v_info: dict[str, Any] | None = None
    if w_path.is_file():
        logger.info(
            "Loading weights from %s (drop_region_head=%s)", w_path, drop_region_head
        )
        model.load_weights(str(w_path), skip_mismatch=drop_region_head)
        if verify_tensors:
            v_info = verify_loaded_weights(
                target_model=model,
                weights_path=w_path,
                drop_region_head=drop_region_head,
                model_config_path=m_path,
                plate_config_path=p_path,
            )
            model._verification_info = v_info
    else:
        if verify_tensors and weights_path is not None:
            raise FileNotFoundError(
                f"Weights file not found for verification: {w_path}"
            )
        logger.warning(
            "Weights file %s not found. Returning model with initialized weights.",
            w_path,
        )

    if return_verification_info:
        return model, (v_info or {})
    return model


def slice_plate_model(model: keras.Model) -> keras.Model:
    """
    Slice a multi-output model to keep only the 'plate' classification head.

    Extracts submodel: keras.Model(inputs=model.input, outputs=model.output['plate']).
    Preserves all learned weights for the plate branch while removing region head tensors.
    """
    if isinstance(model.output, dict) and "plate" in model.output:
        return keras.Model(
            inputs=model.input, outputs=model.output["plate"], name="cct_xs_plate_only"
        )
    return model


def count_model_parameters(model: keras.Model) -> dict[str, int]:
    """
    Count total, trainable, and non-trainable parameters in a Keras model.

    Returns
    -------
    dict[str, int]
        {'total': int, 'trainable': int, 'non_trainable': int}
    """
    total = int(model.count_params())
    trainable = int(sum(keras.ops.size(w) for w in model.trainable_weights))
    non_trainable = int(sum(keras.ops.size(w) for w in model.non_trainable_weights))
    return {
        "total": total,
        "trainable": trainable,
        "non_trainable": non_trainable,
    }


def inspect_model_topology(model: keras.Model) -> dict[str, Any]:
    """
    Inspect the top-level layers and TransformerBlocks in a Keras functional model.

    Returns
    -------
    dict[str, Any]
        Dictionary with layer counts, transformer blocks count, and output names.
    """
    cfg = model.get_config()
    layers = cfg.get("layers", [])
    layer_names = [layer_dict["name"] for layer_dict in layers]
    tblocks = [
        layer_dict["name"]
        for layer_dict in layers
        if "TransformerBlock" in layer_dict.get("class_name", "")
    ]

    output_names = list(model.output_names) if hasattr(model, "output_names") else []

    return {
        "config_layers_count": len(layers),
        "runtime_layers_count": len(model.layers),
        "transformer_blocks_count": len(tblocks),
        "transformer_block_names": tblocks,
        "output_names": output_names,
        "layer_names": layer_names,
    }
