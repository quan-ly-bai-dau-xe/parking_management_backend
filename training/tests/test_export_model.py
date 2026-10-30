"""Tests for Keras to ONNX model export, contract compliance, and mutation testing."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

os.environ.setdefault("KERAS_BACKEND", "torch")

pytest.importorskip("keras")
pytest.importorskip("torch")
pytest.importorskip("onnxruntime")
pytest.importorskip("fast_plate_ocr")

import numpy as np  # noqa: E402
import onnxruntime as ort  # noqa: E402

from scripts.export_model import (  # noqa: E402
    build_or_load_keras_model,
    export_and_verify,
    export_keras_to_onnx,
)


@pytest.mark.parity
def test_build_keras_model_from_yaml(tmp_path: Path) -> None:
    """Verify building CCT-XS Keras model from YAML architecture configs."""
    model_cfg = Path("training/configs/model_cct_xs.yaml")
    plate_cfg = Path("training/configs/plate_config_vn.yaml")

    model, cfg = build_or_load_keras_model(
        model_config_path=model_cfg,
        plate_config_path=plate_cfg,
    )
    assert model is not None
    assert cfg.max_plate_slots == 10
    assert len(cfg.alphabet) == 37

    dummy = np.random.randint(0, 256, (2, 64, 128, 3), dtype=np.uint8)
    out = model(dummy, training=False)
    assert "plate" in out
    plate_logits = out["plate"]
    assert plate_logits.shape == (2, 10, 37)


@pytest.mark.parity
def test_export_keras_to_onnx_and_contract(tmp_path: Path) -> None:
    """Verify exported ONNX matches ADR-0007 Section 4.1 contract."""
    model_cfg = Path("training/configs/model_cct_xs.yaml")
    plate_cfg = Path("training/configs/plate_config_vn.yaml")
    out_onnx = tmp_path / "cct_test.onnx"

    model, cfg = build_or_load_keras_model(model_cfg, plate_cfg)
    exported_path = export_keras_to_onnx(
        model=model,
        plate_cfg=cfg,
        output_onnx_path=out_onnx,
        simplify=True,
    )

    assert exported_path.is_file()
    assert exported_path.stat().st_size > 1_000_000

    sess = ort.InferenceSession(str(exported_path), providers=["CPUExecutionProvider"])
    inputs = sess.get_inputs()
    outputs = sess.get_outputs()

    assert len(inputs) == 1
    assert inputs[0].name == "input"
    assert inputs[0].type == "tensor(uint8)"
    assert inputs[0].shape[1:] == [64, 128, 3]

    assert len(outputs) == 1
    assert outputs[0].name == "plate"
    assert outputs[0].type == "tensor(float)"
    assert outputs[0].shape[-1] == 37

    # Run actual forward pass on ONNX session to verify dynamic shape (2, 10, 37)
    dummy_inp = np.zeros((2, 64, 128, 3), dtype=np.uint8)
    ort_res = sess.run(["plate"], {"input": dummy_inp})[0]
    assert ort_res.shape == (2, 10, 37)
    assert ort_res.dtype == np.float32


@pytest.mark.parity
def test_export_and_verify_parity_green(tmp_path: Path) -> None:
    """Verify export_and_verify passes numerical parity within 1e-4 tolerance (GREEN)."""
    out_onnx = tmp_path / "cct_green.onnx"
    result = export_and_verify(
        output_onnx_path=out_onnx,
        simplify=True,
        atol=1e-4,
        rtol=1e-4,
        perturb=False,
        verify_recognizer=False,
    )

    assert result["passed"] is True
    assert result["status"] == "PASS"
    assert result["max_abs_diff"] < 1e-4
    assert result["mean_abs_diff"] < 1e-4
    assert result["perturbed"] is False
    assert out_onnx.with_suffix(".json").is_file()


@pytest.mark.parity
def test_export_and_verify_mutation_red(tmp_path: Path) -> None:
    """Verify weight perturbation causes parity check to fail with status FAIL (RED)."""
    out_onnx = tmp_path / "cct_corrupted.onnx"
    result = export_and_verify(
        output_onnx_path=out_onnx,
        simplify=True,
        atol=1e-4,
        rtol=1e-4,
        perturb=True,
        verify_recognizer=False,
    )

    assert result["passed"] is False
    assert result["status"] == "FAIL"
    assert result["perturbed"] is True
    assert result["max_abs_diff"] > 1e-3
    assert result["perturbed_initializer"] is not None


@pytest.mark.parity
def test_export_model_cli_exit_codes(tmp_path: Path) -> None:
    """Verify export_model.py CLI exits with 0 on normal export (GREEN) and 1 on mutation (RED)."""
    green_onnx = tmp_path / "cli_green.onnx"
    red_onnx = tmp_path / "cli_red.onnx"

    # 1. Normal run -> Exit 0
    cmd_green = [
        sys.executable,
        "training/scripts/export_model.py",
        "--output",
        str(green_onnx),
        "--no-verify-recognizer",
    ]
    res_green = subprocess.run(cmd_green, capture_output=True, text=True)
    assert res_green.returncode == 0, (
        f"Green run failed with code {res_green.returncode}: {res_green.stderr}"
    )
    assert (
        "PARITY CHECK RESULT: status=PASS" in res_green.stdout
        or "status=PASS" in res_green.stderr
    )

    # 2. Mutation run -> Exit 1
    cmd_red = [
        sys.executable,
        "training/scripts/export_model.py",
        "--output",
        str(red_onnx),
        "--perturb-weight",
        "--no-verify-recognizer",
    ]
    res_red = subprocess.run(cmd_red, capture_output=True, text=True)
    assert res_red.returncode == 1, (
        f"Red run expected returncode 1, got {res_red.returncode}: {res_red.stdout}"
    )
    assert (
        "RED MUTATION TEST PASSED" in res_red.stdout
        or "RED MUTATION TEST PASSED" in res_red.stderr
    )
