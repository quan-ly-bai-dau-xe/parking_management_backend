"""Tests for configuration YAML schemas without invoking training or fit()."""

from pathlib import Path

import pytest
import yaml


def get_config_dir() -> Path:
    """Resolve config directory path."""
    return Path(__file__).resolve().parent.parent / "configs"


@pytest.mark.unit
def test_plate_config_vn_schema() -> None:
    """Verify plate_config_vn.yaml adheres strictly to fast-plate-ocr PlateConfig."""
    config_path = get_config_dir() / "plate_config_vn.yaml"
    assert config_path.is_file(), f"Missing config file at {config_path}"

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # 1. Structural assertions
    assert cfg["max_plate_slots"] == 10
    assert cfg["alphabet"] == "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"
    assert len(cfg["alphabet"]) == 37
    assert cfg["pad_char"] == "_"
    assert cfg["img_height"] == 64
    assert cfg["img_width"] == 128
    assert cfg["keep_aspect_ratio"] is False
    assert cfg["interpolation"] == "linear"
    assert cfg["image_color_mode"] == "rgb"

    # 2. Pydantic PlateConfig model validation
    pytest.importorskip("fast_plate_ocr")
    from fast_plate_ocr.train.model.config import PlateConfig

    plate_cfg = PlateConfig(**cfg)
    assert plate_cfg.max_plate_slots == 10
    assert plate_cfg.pad_char == "_"


@pytest.mark.unit
def test_model_cct_xs_architecture_schema() -> None:
    """Verify model_cct_xs.yaml architecture definition."""
    config_path = get_config_dir() / "model_cct_xs.yaml"
    assert config_path.is_file()

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    assert cfg["model"] == "cct"
    assert "tokenizer" in cfg
    assert len(cfg["tokenizer"]["blocks"]) == 7
    assert cfg["transformer_encoder"]["layers"] == 3
    assert cfg["transformer_encoder"]["heads"] == 2
    assert cfg["transformer_encoder"]["projection_dim"] == 96
    assert cfg["transformer_encoder"]["normalization"] == "dyt"


@pytest.mark.unit
def test_train_cct_xs_baseline_hyperparameters() -> None:
    """Verify baseline training experiment hyperparameters."""
    config_path = get_config_dir() / "train_cct_xs_baseline.yaml"
    assert config_path.is_file()

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    assert cfg["seed"] == 42
    assert cfg["optimizer"]["name"] == "AdamW"
    assert cfg["optimizer"]["lr"] == 0.001
    assert cfg["training"]["batch_size"] == 64
    assert cfg["training"]["epochs"] == 50
    assert cfg["early_stopping"]["metric"] == "val_plate_acc"
    assert cfg["early_stopping"]["patience"] == 15
