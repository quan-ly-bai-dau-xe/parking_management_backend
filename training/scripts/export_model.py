"""Export trained Keras model to production ONNX format with parity verification and mutation testing."""

# ruff: noqa: E402

import argparse
import contextlib
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

# Resolve project paths
SCRIPT_DIR = Path(__file__).resolve().parent
TRAINING_SRC = SCRIPT_DIR.parent / "src"
REPO_ROOT = SCRIPT_DIR.parent.parent
if str(TRAINING_SRC) not in sys.path:
    sys.path.insert(0, str(TRAINING_SRC))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Set backend before Keras import
os.environ.setdefault("KERAS_BACKEND", "torch")
if sys.platform == "win32":
    with contextlib.suppress(Exception):
        sys.stdout.reconfigure(encoding="utf-8")

import fast_plate_ocr.train.model.model_builders as mb
import fast_plate_ocr.train.model.model_schema as ms
import keras
import onnx
import onnxslim
from fast_plate_ocr.train.model.config import PlateConfig, load_plate_config_from_yaml
from fast_plate_ocr.train.model.layers import PatchExtractor
from onnx import numpy_helper

from plate_training.onnx_parity import check_onnx_parity

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("export_model")


def patch_patch_extractor_if_needed() -> None:
    """
    Patch PatchExtractor.call with equivalent pure reshape and transpose operations.
    The default keras.ops.image.extract_patches uses dynamic eye/conv kernels in Torch backend,
    which triggers SymbolicValueError during TorchScript ONNX tracing.
    The pure reshape/transpose approach yields mathematically identical results (max_diff == 0.0)
    and exports cleanly to ONNX with dynamic batch dimensions.
    """
    original_call = getattr(PatchExtractor, "_original_call", None)
    if original_call is not None:
        return

    PatchExtractor._original_call = PatchExtractor.call  # type: ignore[attr-defined]

    def _safe_patch_extractor_call(self: PatchExtractor, images: Any) -> Any:
        b, h, w, c = keras.ops.shape(images)
        ps = self.patch_size
        # Reshape to 6D: (B, H//ps, ps, W//ps, ps, C)
        x = keras.ops.reshape(images, (b, h // ps, ps, w // ps, ps, c))
        # Permute spatial and patch axes: (B, H//ps, W//ps, ps, ps, C)
        x = keras.ops.transpose(x, (0, 1, 3, 2, 4, 5))
        # Flatten patches: (B, (H//ps)*(W//ps), ps*ps*C)
        return keras.ops.reshape(x, (b, (h // ps) * (w // ps), ps * ps * c))

    PatchExtractor.call = _safe_patch_extractor_call  # type: ignore[assignment]


def build_or_load_keras_model(
    model_config_path: Path | str = Path("training/configs/model_cct_xs.yaml"),
    plate_config_path: Path | str = Path("training/configs/plate_config_vn.yaml"),
    keras_model_path: Path | str | None = None,
    drop_region_head: bool = False,
) -> tuple[keras.Model, PlateConfig]:
    """
    Build Keras model from YAML configs (zero fit, random/pretrained init)
    or load from an existing .keras checkpoint.
    """
    patch_patch_extractor_if_needed()

    plate_cfg = load_plate_config_from_yaml(Path(plate_config_path))

    if keras_model_path and Path(keras_model_path).is_file():
        k_path = Path(keras_model_path)
        logger.info("Loading existing Keras checkpoint from %s", k_path)
        if drop_region_head:
            model_cfg = ms.load_model_config_from_yaml(Path(model_config_path))
            model = mb.build_model(model_cfg, plate_cfg, enable_region_head=False)
            model.load_weights(str(k_path), skip_mismatch=True)
            return model, plate_cfg
        model = keras.models.load_model(str(k_path))
        return model, plate_cfg

    model_cfg_path = Path(model_config_path)
    logger.info(
        "Building CCT-XS Keras model from configs: %s and %s",
        model_cfg_path,
        plate_config_path,
    )
    model_cfg = ms.load_model_config_from_yaml(model_cfg_path)
    enable_region = False if drop_region_head else bool(plate_cfg.plate_regions)
    model = mb.build_model(model_cfg, plate_cfg, enable_region_head=enable_region)
    return model, plate_cfg


def export_keras_to_onnx(
    model: keras.Model,
    plate_cfg: PlateConfig,
    output_onnx_path: Path | str,
    simplify: bool = True,
    opset_version: int | None = None,
    drop_region_head: bool = True,
) -> Path:
    """
    Export Keras model to ONNX adhering strictly to ADR-0007 Section 4.1 artifact contract:
      - Input tensor: 'input', shape (batch, 64, 128, 3), dtype uint8 (NHWC)
      - Output tensor: 'plate', shape (batch, 10, 37), dtype float32
    Optionally optimize graph with onnxslim.
    """
    patch_patch_extractor_if_needed()

    if drop_region_head and isinstance(model.output, dict) and "plate" in model.output:
        logger.info("Slicing Keras model to 'plate' output only for production export.")
        model = keras.Model(
            inputs=model.input, outputs=model.output["plate"], name="cct_xs_plate_only"
        )

    out_path = Path(output_onnx_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    spec = [
        keras.InputSpec(
            name="input",
            shape=(
                None,
                plate_cfg.img_height,
                plate_cfg.img_width,
                plate_cfg.num_channels,
            ),
            dtype="uint8",
        )
    ]

    with tempfile.NamedTemporaryFile(suffix=".onnx", delete=False) as tmp:
        tmp_name = tmp.name

    try:
        logger.info("Exporting Keras model via Keras 3 ONNX exporter...")
        model.export(
            tmp_name,
            format="onnx",
            verbose=False,
            input_signature=spec,
            opset_version=opset_version,
        )

        proto = onnx.load(tmp_name)

        # Standardize output tensor names
        if len(proto.graph.output) == 1:
            old_out_name = proto.graph.output[0].name
            if old_out_name != "plate":
                logger.info("Renaming output tensor from '%s' to 'plate'", old_out_name)
                for node in proto.graph.node:
                    for i, out in enumerate(node.output):
                        if out == old_out_name:
                            node.output[i] = "plate"
                proto.graph.output[0].name = "plate"
        elif len(proto.graph.output) == 2:
            out0_name = proto.graph.output[0].name
            out1_name = proto.graph.output[1].name
            if out0_name != "plate":
                logger.info("Renaming output tensor 0 from '%s' to 'plate'", out0_name)
                for node in proto.graph.node:
                    for i, out in enumerate(node.output):
                        if out == out0_name:
                            node.output[i] = "plate"
                proto.graph.output[0].name = "plate"
            if out1_name != "region":
                logger.info("Renaming output tensor 1 from '%s' to 'region'", out1_name)
                for node in proto.graph.node:
                    for i, out in enumerate(node.output):
                        if out == out1_name:
                            node.output[i] = "region"
                proto.graph.output[1].name = "region"

        if simplify:
            logger.info("Optimizing ONNX graph with onnxslim...")
            proto = onnxslim.slim(proto)

        onnx.save(proto, str(out_path))
        logger.info(
            "ONNX artifact saved to %s (%d bytes)", out_path, out_path.stat().st_size
        )
    finally:
        if os.path.exists(tmp_name):
            with contextlib.suppress(OSError):
                os.remove(tmp_name)

    return out_path


def perturb_onnx_weights(onnx_path: Path | str, perturbation: float = 1.0) -> str:
    """
    Deliberately perturb a weight initializer in the ONNX model to prove
    that the parity check genuinely detects numerical deviation (mutation testing).
    """
    path = Path(onnx_path)
    proto = onnx.load(str(path))
    perturbed_name = ""

    for init in proto.graph.initializer:
        arr = numpy_helper.to_array(init)
        if arr.dtype == np.float32 and arr.size > 0:
            perturbed = arr + np.float32(perturbation)
            new_init = numpy_helper.from_array(perturbed, name=init.name)
            init.CopyFrom(new_init)
            perturbed_name = init.name
            break

    if not perturbed_name:
        raise RuntimeError(
            "No suitable float32 initializer found in ONNX graph to perturb."
        )

    onnx.save(proto, str(path))
    logger.warning(
        "MUTATION APPLIED: Perturbed initializer '%s' by %+f",
        perturbed_name,
        perturbation,
    )
    return perturbed_name


def verify_with_fast_alpr(
    onnx_path: Path | str,
    plate_cfg_path: Path | str,
    parquet_path: Path | str | None = None,
    num_samples: int = 3,
) -> dict[str, Any]:
    """
    Verify artifact contract compatibility by loading the exported ONNX model
    into FastAlprPlateRecognizer via PARKING_OCR_MODELS_DIR on sample parquet images.
    """
    import io

    import pyarrow.parquet as pq
    from PIL import Image

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
    import django

    django.setup()
    from apps.parking.services.ocr import FastAlprPlateRecognizer
    from django.conf import settings

    resolved_parquet = None
    if parquet_path and Path(parquet_path).is_file():
        resolved_parquet = Path(parquet_path)
    else:
        # Check standard Hugging Face hub cache
        candidate = (
            Path.home()
            / ".cache"
            / "huggingface"
            / "hub"
            / "datasets--sonnetechnology--license-plate-text-recognition-full"
            / "snapshots"
            / "e9eeda1872046de715d36de41d326e7a4e7d4634"
            / "data"
            / "test-00000-of-00001-a359b6560048e51f.parquet"
        )
        if candidate.is_file():
            resolved_parquet = candidate

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        # FastAlprPlateRecognizer expects cct_xs_v2_global.onnx and cct_xs_v2_global_plate_config.yaml
        shutil.copy(onnx_path, tmp_dir_path / "cct_xs_v2_global.onnx")
        shutil.copy(plate_cfg_path, tmp_dir_path / "cct_xs_v2_global_plate_config.yaml")

        prev_models_dir = getattr(settings, "PARKING_OCR_MODELS_DIR", None)
        settings.PARKING_OCR_MODELS_DIR = tmp_dir_path

        try:
            recognizer = FastAlprPlateRecognizer()
            logger.info(
                "FastAlprPlateRecognizer successfully loaded from throwaway models dir."
            )

            sample_results = []
            if resolved_parquet:
                table = pq.read_table(str(resolved_parquet), columns=["image"])
                limit = min(num_samples, table.num_rows)
                for idx in range(limit):
                    img_bytes = table.column("image")[idx].as_py()["bytes"]
                    res = recognizer.recognize(img_bytes)
                    sample_results.append(
                        {
                            "index": idx,
                            "raw_text": res.raw_text,
                            "review_status": res.review_status,
                            "cct_plate": res.cct_plate,
                            "latency_ms": res.latency_ms,
                        }
                    )
            else:
                # Synthetic dummy image (RGB 64x128)
                img = Image.fromarray(
                    np.random.randint(0, 256, (64, 128, 3), dtype=np.uint8)
                )
                buf = io.BytesIO()
                img.save(buf, format="JPEG")
                res = recognizer.recognize(buf.getvalue())
                sample_results.append(
                    {
                        "index": 0,
                        "raw_text": res.raw_text,
                        "review_status": res.review_status,
                        "cct_plate": res.cct_plate,
                    }
                )

            return {
                "verified": True,
                "samples_tested": len(sample_results),
                "sample_results": sample_results,
            }
        finally:
            if prev_models_dir is not None:
                settings.PARKING_OCR_MODELS_DIR = prev_models_dir


def export_and_verify(
    model_config_path: Path | str = Path("training/configs/model_cct_xs.yaml"),
    plate_config_path: Path | str = Path("training/configs/plate_config_vn.yaml"),
    output_onnx_path: Path | str = Path("training/artifacts/cct_xs_v2_global.onnx"),
    keras_model_path: Path | str | None = None,
    simplify: bool = True,
    atol: float = 1e-4,
    rtol: float = 1e-4,
    perturb: bool = False,
    verify_recognizer: bool = True,
    parquet_path: Path | str | None = None,
    drop_region_head: bool = True,
) -> dict[str, Any]:
    """
    Build/load Keras model, export to ONNX, run parity check,
    optionally apply mutation perturbation, and verify contract compatibility.
    """
    onnx_path = Path(output_onnx_path)
    model_cfg_p = Path(model_config_path)
    plate_cfg_p = Path(plate_config_path)

    # 1. Build or load Keras model
    keras_model, plate_cfg = build_or_load_keras_model(
        model_config_path=model_cfg_p,
        plate_config_path=plate_cfg_p,
        keras_model_path=keras_model_path,
        drop_region_head=drop_region_head,
    )

    # 2. Export Keras model to ONNX
    export_keras_to_onnx(
        model=keras_model,
        plate_cfg=plate_cfg,
        output_onnx_path=onnx_path,
        simplify=simplify,
        drop_region_head=drop_region_head,
    )

    perturbed_initializer = None
    if perturb:
        perturbed_initializer = perturb_onnx_weights(onnx_path, perturbation=1.0)

    # 3. Numerical Parity Check
    parity_dict = check_onnx_parity(
        keras_model_or_predict=keras_model,
        onnx_model_or_session=onnx_path,
        input_shape=(plate_cfg.img_height, plate_cfg.img_width, plate_cfg.num_channels),
        batch_size=4,
        atol=atol,
        rtol=rtol,
        raise_on_error=False,
    )

    max_abs_diff = parity_dict["max_abs_diff"]
    mean_abs_diff = parity_dict["mean_abs_diff"]
    passed = parity_dict["passed"]
    status_str = "PASS" if passed else "FAIL"

    logger.info(
        "PARITY CHECK RESULT: status=%s (passed=%s), max_abs_diff=%.6e, mean_abs_diff=%.6e",
        status_str,
        passed,
        max_abs_diff,
        mean_abs_diff,
    )

    recognizer_report: dict[str, Any] = {"verified": False}
    if verify_recognizer and not perturb:
        try:
            recognizer_report = verify_with_fast_alpr(
                onnx_path=onnx_path,
                plate_cfg_path=plate_cfg_p,
                parquet_path=parquet_path,
            )
            logger.info("Contract verification with FastAlprPlateRecognizer passed.")
        except Exception as exc:
            logger.warning("FastAlprPlateRecognizer verification warning: %s", exc)
            recognizer_report = {"verified": False, "error": str(exc)}

    result: dict[str, Any] = {
        "status": status_str,
        "passed": passed,
        "keras_model": str(keras_model_path) if keras_model_path else "built_from_yaml",
        "onnx_model": str(onnx_path),
        "onnx_size_bytes": onnx_path.stat().st_size if onnx_path.exists() else 0,
        "max_abs_diff": max_abs_diff,
        "mean_abs_diff": mean_abs_diff,
        "max_diff": max_abs_diff,
        "tolerance": {"atol": atol, "rtol": rtol},
        "artifact_contract": {
            "input_name": "input",
            "input_shape": [
                None,
                plate_cfg.img_height,
                plate_cfg.img_width,
                plate_cfg.num_channels,
            ],
            "input_dtype": "uint8",
            "output_tensor": "plate",
            "output_shape": [None, plate_cfg.max_plate_slots, len(plate_cfg.alphabet)],
        },
        "perturbed": perturb,
        "perturbed_initializer": perturbed_initializer,
        "recognizer_verification": recognizer_report,
    }

    metadata_path = onnx_path.with_suffix(".json")
    with open(metadata_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    logger.info("Export summary metadata saved to %s", metadata_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export Keras CCT-XS model to ONNX with parity verification and mutation test."
    )
    parser.add_argument(
        "--model-config",
        "-m",
        default="training/configs/model_cct_xs.yaml",
        help="Model architecture config YAML path.",
    )
    parser.add_argument(
        "--plate-config",
        "-p",
        default="training/configs/plate_config_vn.yaml",
        help="Plate config YAML path.",
    )
    parser.add_argument(
        "--keras-model",
        "-k",
        default=None,
        help="Input Keras checkpoint path (.keras). If not given, builds from config.",
    )
    parser.add_argument(
        "--output",
        "-o",
        default="training/artifacts/cct_xs_v2_global.onnx",
        help="Output ONNX model path.",
    )
    parser.add_argument(
        "--no-simplify", action="store_true", help="Skip ONNX simplification step."
    )
    parser.add_argument(
        "--atol", type=float, default=1e-4, help="Absolute tolerance for parity check."
    )
    parser.add_argument(
        "--rtol", type=float, default=1e-4, help="Relative tolerance for parity check."
    )
    parser.add_argument(
        "--perturb-weight",
        "--mutate",
        action="store_true",
        help="Intentionally corrupt an ONNX weight to trigger RED failure (mutation test).",
    )
    parser.add_argument(
        "--verify-recognizer",
        action="store_true",
        default=True,
        help="Verify exported ONNX by loading into FastAlprPlateRecognizer on sample images.",
    )
    parser.add_argument(
        "--no-verify-recognizer",
        dest="verify_recognizer",
        action="store_false",
        help="Skip FastAlprPlateRecognizer verification.",
    )
    parser.add_argument(
        "--parquet-path",
        default=None,
        help="Path to Parquet dataset file for contract verification images.",
    )
    parser.add_argument(
        "--keep-region-head",
        dest="drop_region_head",
        action="store_false",
        default=True,
        help="Keep region head in exported ONNX instead of slicing it off for Vietnam-only.",
    )

    args = parser.parse_args()

    result = export_and_verify(
        model_config_path=args.model_config,
        plate_config_path=args.plate_config,
        output_onnx_path=args.output,
        keras_model_path=args.keras_model,
        simplify=not args.no_simplify,
        atol=args.atol,
        rtol=args.rtol,
        perturb=args.perturb_weight,
        verify_recognizer=args.verify_recognizer,
        parquet_path=args.parquet_path,
        drop_region_head=args.drop_region_head,
    )

    # In mutation test mode, expected outcome is RED failure (exit code 1)
    if args.perturb_weight:
        if not result["passed"]:
            logger.info(
                "[RED MUTATION TEST PASSED] Parity check successfully failed on corrupted ONNX weight! (Exit code 1)"
            )
            sys.exit(1)
        else:
            logger.error(
                "[MUTATION FAILED] Parity check did not catch perturbed weight!"
            )
            sys.exit(2)
    else:
        if result["passed"]:
            logger.info(
                "[GREEN PASS] Model export and parity check passed successfully! (Exit code 0)"
            )
            sys.exit(0)
        else:
            logger.error("[EXPORT FAILED] Parity check failed on unperturbed model!")
            sys.exit(1)


if __name__ == "__main__":
    main()
