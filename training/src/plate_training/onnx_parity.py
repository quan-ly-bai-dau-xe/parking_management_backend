"""Inference parity verification between Keras and ONNX Runtime sessions."""

from pathlib import Path
from typing import Any

import numpy as np


class ParityCheckError(RuntimeError):
    """Raised when numerical deviation between Keras and ONNX exceeds tolerance."""


def check_onnx_parity(
    keras_model_or_predict: Any,
    onnx_model_or_session: Any,
    input_shape: tuple[int, int, int] = (64, 128, 3),
    batch_size: int = 4,
    atol: float = 1e-4,
    rtol: float = 1e-4,
    seed: int = 42,
    synthetic_input: np.ndarray | None = None,
    raise_on_error: bool = True,
) -> dict[str, Any]:
    """
    Verify forward-pass output equivalence between Keras model and ONNX Runtime session
    on synthetic uint8 random tensors within specified numerical tolerances (default atol=1e-4, rtol=1e-4).
    Dynamically computes max_abs_diff, mean_abs_diff, and passed status (training=False).
    """
    rng = np.random.default_rng(seed)
    if synthetic_input is not None:
        x = synthetic_input
    else:
        h, w, c = input_shape
        x = rng.integers(0, 256, size=(batch_size, h, w, c), dtype=np.uint8)

    # 1. Run Keras prediction with deterministic evaluation (training=False)
    if callable(keras_model_or_predict):
        try:
            keras_raw = keras_model_or_predict(x, training=False)
        except TypeError:
            keras_raw = keras_model_or_predict(x)
    elif hasattr(keras_model_or_predict, "predict"):
        keras_raw = keras_model_or_predict.predict(x, verbose=0)
    else:
        raise TypeError(f"Unsupported Keras model type: {type(keras_model_or_predict)}")

    if isinstance(keras_raw, dict):
        keras_out = keras_raw.get("plate", list(keras_raw.values())[0])
    elif isinstance(keras_raw, (list, tuple)):
        keras_out = keras_raw[0]
    else:
        keras_out = keras_raw

    # 2. Run ONNX prediction
    if callable(onnx_model_or_session):
        onnx_raw = onnx_model_or_session(x)
    elif hasattr(onnx_model_or_session, "run"):
        # onnxruntime.InferenceSession
        session = onnx_model_or_session
        input_name = session.get_inputs()[0].name
        output_names = [out.name for out in session.get_outputs()]
        outputs = session.run(output_names, {input_name: x})
        onnx_raw = dict(zip(output_names, outputs, strict=False))
    elif isinstance(onnx_model_or_session, (str, Path)):
        import onnxruntime as ort

        session = ort.InferenceSession(
            str(onnx_model_or_session), providers=["CPUExecutionProvider"]
        )
        input_name = session.get_inputs()[0].name
        output_names = [out.name for out in session.get_outputs()]
        outputs = session.run(output_names, {input_name: x})
        onnx_raw = dict(zip(output_names, outputs, strict=False))
    else:
        raise TypeError(f"Unsupported ONNX model type: {type(onnx_model_or_session)}")

    if isinstance(onnx_raw, dict):
        onnx_out = onnx_raw.get("plate", list(onnx_raw.values())[0])
    elif isinstance(onnx_raw, (list, tuple)):
        onnx_out = onnx_raw[0]
    else:
        onnx_out = onnx_raw

    if hasattr(keras_out, "detach"):
        keras_arr = keras_out.detach().cpu().numpy().astype(np.float32)
    else:
        keras_arr = np.asarray(keras_out, dtype=np.float32)

    if hasattr(onnx_out, "detach"):
        onnx_arr = onnx_out.detach().cpu().numpy().astype(np.float32)
    else:
        onnx_arr = np.asarray(onnx_out, dtype=np.float32)

    if keras_arr.shape != onnx_arr.shape:
        raise ParityCheckError(
            f"Shape mismatch: Keras output shape {keras_arr.shape} vs ONNX output shape {onnx_arr.shape}"
        )

    abs_diff = np.abs(keras_arr - onnx_arr)
    max_abs_diff = float(np.max(abs_diff))
    mean_abs_diff = float(np.mean(abs_diff))
    is_close = bool(np.allclose(keras_arr, onnx_arr, rtol=rtol, atol=atol))
    passed = is_close
    status_str = "PASS" if passed else "FAIL"

    if not passed and raise_on_error:
        raise ParityCheckError(
            f"Keras and ONNX outputs deviate beyond tolerance! Max absolute diff: {max_abs_diff:.6e}, "
            f"Mean absolute diff: {mean_abs_diff:.6e} (threshold atol={atol}, rtol={rtol})"
        )

    return {
        "passed": passed,
        "status": status_str,
        "max_abs_diff": max_abs_diff,
        "mean_abs_diff": mean_abs_diff,
        "max_diff": max_abs_diff,
        "atol": atol,
        "rtol": rtol,
        "tolerance": {"atol": atol, "rtol": rtol},
        "shape": list(keras_arr.shape),
    }
