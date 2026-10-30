"""Tests for Keras vs ONNX inference parity checker."""

import numpy as np
import pytest

from plate_training.onnx_parity import ParityCheckError, check_onnx_parity


@pytest.mark.parity
def test_parity_check_success_within_tolerance() -> None:
    """Verify check_onnx_parity passes when predictions match within 1e-4 tolerance."""
    base_logits = np.random.randn(4, 10, 37).astype(np.float32)

    def mock_keras(x: np.ndarray, training: bool = True) -> np.ndarray:
        # Check that training=False is passed
        assert training is False
        return base_logits

    def mock_onnx(x: np.ndarray) -> np.ndarray:
        # Add micro deviation well below atol=1e-4
        return base_logits + 1e-6

    result = check_onnx_parity(
        keras_model_or_predict=mock_keras,
        onnx_model_or_session=mock_onnx,
        input_shape=(64, 128, 3),
        batch_size=4,
        atol=1e-4,
        rtol=1e-4,
    )
    assert result["passed"] is True
    assert result["status"] == "PASS"
    assert result["max_abs_diff"] < 1e-4
    assert result["mean_abs_diff"] < 1e-4
    assert result["max_diff"] < 1e-4
    assert result["tolerance"] == {"atol": 1e-4, "rtol": 1e-4}


@pytest.mark.parity
def test_parity_check_fails_when_deviation_exceeds_tolerance() -> None:
    """Verify check_onnx_parity raises ParityCheckError when deviation exceeds tolerance."""
    base_logits = np.random.randn(4, 10, 37).astype(np.float32)

    def mock_keras(x: np.ndarray, training: bool = True) -> np.ndarray:
        return base_logits

    def mock_onnx_deviant(x: np.ndarray) -> np.ndarray:
        # Add significant deviation (0.01 > 1e-4)
        return base_logits + 0.01

    with pytest.raises(ParityCheckError, match="deviate beyond tolerance"):
        check_onnx_parity(
            keras_model_or_predict=mock_keras,
            onnx_model_or_session=mock_onnx_deviant,
            input_shape=(64, 128, 3),
            batch_size=4,
            atol=1e-4,
            rtol=1e-4,
        )


@pytest.mark.parity
def test_parity_check_raise_on_error_false_returns_failure_dict() -> None:
    """Verify check_onnx_parity returns dict with passed=False when raise_on_error=False."""
    base_logits = np.random.randn(4, 10, 37).astype(np.float32)

    def mock_keras(x: np.ndarray, training: bool = True) -> np.ndarray:
        return base_logits

    def mock_onnx_deviant(x: np.ndarray) -> np.ndarray:
        return base_logits + 0.05

    result = check_onnx_parity(
        keras_model_or_predict=mock_keras,
        onnx_model_or_session=mock_onnx_deviant,
        input_shape=(64, 128, 3),
        batch_size=4,
        atol=1e-4,
        rtol=1e-4,
        raise_on_error=False,
    )
    assert result["passed"] is False
    assert result["status"] == "FAIL"
    assert result["max_abs_diff"] >= 0.049
    assert result["mean_abs_diff"] >= 0.049


@pytest.mark.parity
def test_parity_check_fails_on_shape_mismatch() -> None:
    """Verify check_onnx_parity detects tensor shape discrepancy."""

    def mock_keras(x: np.ndarray, training: bool = True) -> np.ndarray:
        return np.zeros((4, 10, 37), dtype=np.float32)

    def mock_onnx_wrong_shape(x: np.ndarray) -> np.ndarray:
        return np.zeros((4, 8, 37), dtype=np.float32)

    with pytest.raises(ParityCheckError, match="Shape mismatch"):
        check_onnx_parity(
            keras_model_or_predict=mock_keras,
            onnx_model_or_session=mock_onnx_wrong_shape,
            input_shape=(64, 128, 3),
            batch_size=4,
        )
