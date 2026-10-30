"""Pydantic configuration models for training hyperparameters and dataset options."""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class BaseConfigModel(BaseModel):
    """Base model forbidding unexpected extra attributes."""

    model_config = ConfigDict(extra="forbid")


class DatasetConfig(BaseConfigModel):
    """Dataset manifest and image geometry configuration."""

    train_manifest: str
    val_manifest: str
    plate_config: str
    model_config_path: str = Field(alias="model_config")
    min_height: int = 20
    min_width: int = 40


class TrainingHyperparameters(BaseConfigModel):
    """Epochs, batch size and mixed precision settings."""

    batch_size: int = 64
    epochs: int = 50
    validation_freq: int = 1
    mixed_precision_policy: str = "float32"


class OptimizerConfig(BaseConfigModel):
    """Optimizer algorithm and learning rate schedule configuration."""

    name: str = "AdamW"
    lr: float = 0.001
    final_lr_factor: float = 0.01
    warmup_fraction: float = 0.05
    weight_decay: float = 0.01
    clipnorm: float = 1.0
    use_ema: bool = True
    wd_ignore: str = "bias,layer_norm"


class LossConfig(BaseConfigModel):
    """Loss functions and label smoothing weights."""

    plate_loss: str = "cce"
    label_smoothing: float = 0.01
    plate_loss_weight: float = 1.0


class EarlyStoppingConfig(BaseConfigModel):
    """Early stopping criteria and tolerance."""

    metric: str = "val_plate_acc"
    patience: int = 15
    mode: str = "max"


class HardwareConfig(BaseConfigModel):
    """Data loading workers and multiprocessing settings."""

    workers: int = 4
    use_multiprocessing: bool = False
    max_queue_size: int = 10


class CheckpointConfig(BaseConfigModel):
    """Model checkpoint persistence settings."""

    output_dir: str = "./outputs/checkpoints"
    save_best_only: bool = True
    save_weights_only: bool = False


class TrainConfig(BaseConfigModel):
    """Full baseline training experiment configuration schema."""

    experiment_name: str
    seed: int = 42
    dataset: DatasetConfig
    training: TrainingHyperparameters
    optimizer: OptimizerConfig
    loss: LossConfig
    early_stopping: EarlyStoppingConfig
    hardware: HardwareConfig
    checkpoint: CheckpointConfig

    @classmethod
    def from_yaml(cls, path: str | Path) -> "TrainConfig":
        """Load and strictly validate training configuration from a YAML file."""
        file_path = Path(path)
        if not file_path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {file_path}")

        with open(file_path, encoding="utf-8") as f:
            raw_data: Any = yaml.safe_load(f)

        if not isinstance(raw_data, dict):
            raise ValueError(f"YAML configuration must be a mapping: {file_path}")

        return cls.model_validate(raw_data)
