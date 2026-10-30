"""Unit tests for Pydantic TrainConfig validation schema."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from plate_training.config import TrainConfig


def get_baseline_yaml_path() -> Path:
    """Resolve training baseline config path."""
    return (
        Path(__file__).resolve().parent.parent
        / "configs"
        / "train_cct_xs_baseline.yaml"
    )


@pytest.mark.unit
def test_train_config_loads_baseline_yaml() -> None:
    """Verify that train_cct_xs_baseline.yaml validates cleanly against TrainConfig."""
    yaml_path = get_baseline_yaml_path()
    assert yaml_path.is_file(), f"Missing config file at {yaml_path}"

    cfg = TrainConfig.from_yaml(yaml_path)

    assert cfg.experiment_name == "exp01_cct_xs_vietnamese_baseline"
    assert cfg.seed == 42
    assert cfg.dataset.train_manifest == "data/manifest_train.json"
    assert cfg.dataset.val_manifest == "data/manifest_val.json"
    assert cfg.dataset.model_config_path == "configs/model_cct_xs.yaml"
    assert cfg.training.batch_size == 64
    assert cfg.training.epochs == 50
    assert cfg.training.mixed_precision_policy == "float32"
    assert cfg.optimizer.name == "AdamW"
    assert cfg.optimizer.lr == 0.001
    assert cfg.optimizer.use_ema is True
    assert cfg.loss.plate_loss == "cce"
    assert cfg.loss.label_smoothing == 0.01
    assert cfg.early_stopping.metric == "val_plate_acc"
    assert cfg.early_stopping.patience == 15
    assert cfg.hardware.workers == 4
    assert cfg.checkpoint.output_dir == "./outputs/checkpoints"
    assert cfg.checkpoint.save_best_only is True


@pytest.mark.unit
def test_train_config_extra_field_forbid(tmp_path: Path) -> None:
    """Extra unexpected fields should trigger ValidationError due to extra='forbid'."""
    invalid_yaml = tmp_path / "invalid_extra.yaml"
    invalid_yaml.write_text(
        """
experiment_name: "test_extra"
seed: 42
unexpected_root_key: "forbidden"
dataset:
  train_manifest: "train.json"
  val_manifest: "val.json"
  plate_config: "plate.yaml"
  model_config: "model.yaml"
  min_height: 20
  min_width: 40
training:
  batch_size: 32
  epochs: 10
  validation_freq: 1
  mixed_precision_policy: "float32"
optimizer:
  name: "AdamW"
  lr: 0.001
  final_lr_factor: 0.01
  warmup_fraction: 0.05
  weight_decay: 0.01
  clipnorm: 1.0
  use_ema: true
  wd_ignore: "bias"
loss:
  plate_loss: "cce"
  label_smoothing: 0.0
  plate_loss_weight: 1.0
early_stopping:
  metric: "val_plate_acc"
  patience: 5
  mode: "max"
hardware:
  workers: 2
  use_multiprocessing: false
  max_queue_size: 5
checkpoint:
  output_dir: "./checkpoints"
  save_best_only: true
  save_weights_only: false
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError) as exc_info:
        TrainConfig.from_yaml(invalid_yaml)
    assert "unexpected_root_key" in str(exc_info.value)


@pytest.mark.unit
def test_train_config_missing_field_raises(tmp_path: Path) -> None:
    """Missing required fields should trigger ValidationError."""
    missing_yaml = tmp_path / "missing_field.yaml"
    missing_yaml.write_text(
        """
experiment_name: "test_missing"
# Missing seed and sub-configs
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        TrainConfig.from_yaml(missing_yaml)


@pytest.mark.unit
def test_train_config_file_not_found(tmp_path: Path) -> None:
    """Non-existent file should raise FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        TrainConfig.from_yaml(tmp_path / "non_existent.yaml")


@pytest.mark.unit
def test_train_config_invalid_yaml_content(tmp_path: Path) -> None:
    """Non-dictionary YAML content should raise ValueError."""
    list_yaml = tmp_path / "list_config.yaml"
    list_yaml.write_text("- item1\n- item2\n", encoding="utf-8")

    with pytest.raises(ValueError, match="YAML configuration must be a mapping"):
        TrainConfig.from_yaml(list_yaml)


@pytest.mark.unit
def test_train_config_invalid_types(tmp_path: Path) -> None:
    """Invalid data type for an integer field should raise ValidationError."""
    bad_type_yaml = tmp_path / "bad_type.yaml"
    bad_type_yaml.write_text(
        """
experiment_name: "bad_type"
seed: "not-an-int"
dataset:
  train_manifest: "train.json"
  val_manifest: "val.json"
  plate_config: "plate.yaml"
  model_config: "model.yaml"
training:
  batch_size: 32
  epochs: 10
optimizer:
  name: "AdamW"
  lr: 0.001
loss:
  plate_loss: "cce"
early_stopping:
  metric: "val_plate_acc"
hardware:
  workers: 2
checkpoint:
  output_dir: "./checkpoints"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError):
        TrainConfig.from_yaml(bad_type_yaml)
