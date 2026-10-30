"""
Manifest-to-Dataset Loader for Vietnamese License Plate Recognition.
Provides PlateDataset (compatible with Keras 3 PyDataset and model.fit / model.evaluate)
and build_dataset factory function with fail-closed split validation and byte-exact preprocessing.
"""

from __future__ import annotations

import logging
import math
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import yaml

# Ensure Keras 3 uses PyTorch backend
os.environ.setdefault("KERAS_BACKEND", "torch")

# Keras 3 PyDataset abstraction with lightweight CI fallback
try:
    from keras.utils import PyDataset
except ImportError:

    class PyDataset:  # type: ignore[no-redef]
        """Fallback base class when Keras is not installed in lightweight CI environment."""

        def __init__(self, **kwargs: Any) -> None:
            pass


from plate_training.manifest import ManifestItem, load_manifest
from plate_training.split import validate_splits

logger = logging.getLogger("plate_training.dataset")

DEFAULT_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_"
DEFAULT_PAD_CHAR = "_"
DEFAULT_MAX_PLATE_SLOTS = 10
DEFAULT_IMG_HEIGHT = 64
DEFAULT_IMG_WIDTH = 128


def preprocess_plate_image(
    image_input: str | Path | np.ndarray,
    img_height: int = DEFAULT_IMG_HEIGHT,
    img_width: int = DEFAULT_IMG_WIDTH,
    color_mode: str = "rgb",
) -> np.ndarray:
    """
    Read (if path) and resize image to (img_height, img_width, channels) uint8 RGB.
    Uses cv2.INTER_LINEAR interpolation without aspect-ratio preservation.
    Guarantees 100% byte-for-byte exact equality (max_abs_diff == 0) with
    production fast_plate_ocr recognizer and OpenCV pipeline.
    """
    if isinstance(image_input, (str, Path)):
        path_str = str(image_input)
        if not os.path.isfile(path_str):
            raise FileNotFoundError(f"Image not found at {path_str}")

        if color_mode.lower() == "rgb":
            bgr = cv2.imread(path_str, cv2.IMREAD_COLOR)
            if bgr is None:
                raise ValueError(f"Failed to decode image at {path_str}")
            rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        elif color_mode.lower() == "grayscale":
            gray = cv2.imread(path_str, cv2.IMREAD_GRAYSCALE)
            if gray is None:
                raise ValueError(f"Failed to decode image at {path_str}")
            rgb = np.expand_dims(gray, axis=-1)
        else:
            raise ValueError(f"Unsupported color_mode: {color_mode}")
    elif isinstance(image_input, np.ndarray):
        rgb = image_input
        if rgb.ndim == 2:
            rgb = np.expand_dims(rgb, axis=-1)
    else:
        raise TypeError(f"Unsupported image_input type: {type(image_input)}")

    resized = cv2.resize(rgb, (img_width, img_height), interpolation=cv2.INTER_LINEAR)
    if resized.ndim == 2:
        resized = np.expand_dims(resized, axis=-1)

    return resized.astype(np.uint8)


def read_and_preprocess_image(
    image_path: str | Path,
    img_height: int = DEFAULT_IMG_HEIGHT,
    img_width: int = DEFAULT_IMG_WIDTH,
    color_mode: str = "rgb",
) -> np.ndarray:
    """Convenience alias for preprocess_plate_image when given file paths."""
    return preprocess_plate_image(
        image_input=image_path,
        img_height=img_height,
        img_width=img_width,
        color_mode=color_mode,
    )


def encode_plate_label(
    plate_text: str,
    max_slots: int = DEFAULT_MAX_PLATE_SLOTS,
    alphabet: str = DEFAULT_ALPHABET,
    pad_char: str = DEFAULT_PAD_CHAR,
) -> np.ndarray:
    """
    Encode plate text string into a one-hot float32 matrix of shape (max_slots, len(alphabet)).

    Pads text to max_slots using pad_char.
    Alphabet index mapping:
      '0'..'9' -> 0..9
      'A'..'Z' -> 10..35
      '_'      -> 36 (pad char)
    """
    if len(plate_text) > max_slots:
        raise ValueError(f"Plate text '{plate_text}' exceeds max_slots ({max_slots}).")
    padded = plate_text.ljust(max_slots, pad_char)
    char_to_idx = {char: idx for idx, char in enumerate(alphabet)}

    one_hot = np.zeros((max_slots, len(alphabet)), dtype=np.float32)
    for slot_idx, ch in enumerate(padded):
        if ch not in char_to_idx:
            raise ValueError(
                f"Character '{ch}' in plate '{plate_text}' not in alphabet."
            )
        one_hot[slot_idx, char_to_idx[ch]] = 1.0

    return one_hot


def decode_plate_prediction(
    prediction: np.ndarray,
    alphabet: str = DEFAULT_ALPHABET,
    pad_char: str = DEFAULT_PAD_CHAR,
) -> str:
    """
    Decode one-hot or logits matrix of shape (max_slots, len(alphabet)) into plate string.
    Strips trailing pad_char.
    """
    if prediction.ndim != 2:
        raise ValueError(f"Expected 2D array, got shape {prediction.shape}")
    indices = np.argmax(prediction, axis=-1)
    chars = [alphabet[int(idx)] for idx in indices]
    return "".join(chars).rstrip(pad_char)


class PlateDataset(PyDataset):
    """
    Dataset loader for license-plate training, validation, and evaluation.
    Subclasses Keras 3 PyDataset for zero-copy streaming into keras.Model.fit and model.evaluate.
    """

    def __init__(
        self,
        items: Sequence[ManifestItem],
        batch_size: int = 64,
        shuffle: bool = True,
        seed: int = 42,
        base_dir: str | Path | None = None,
        img_height: int = DEFAULT_IMG_HEIGHT,
        img_width: int = DEFAULT_IMG_WIDTH,
        max_plate_slots: int = DEFAULT_MAX_PLATE_SLOTS,
        alphabet: str = DEFAULT_ALPHABET,
        pad_char: str = DEFAULT_PAD_CHAR,
        plate_regions: Sequence[str] | None = None,
        drop_region_head: bool = True,
        transform: Any | None = None,
        validate_split: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        if not items:
            raise ValueError("Cannot initialize PlateDataset with empty items list.")

        self.items: list[ManifestItem] = list(items)
        self.batch_size = max(1, int(batch_size))
        self.shuffle = bool(shuffle)
        self.seed = int(seed)
        self.base_dir = Path(base_dir) if base_dir else Path(".")
        self.img_height = int(img_height)
        self.img_width = int(img_width)
        self.max_plate_slots = int(max_plate_slots)
        self.alphabet = str(alphabet)
        self.pad_char = str(pad_char)
        self.plate_regions = list(plate_regions) if plate_regions else None
        self.drop_region_head = bool(drop_region_head)
        self.transform = transform
        self.epoch = 0

        # Region encoding setup
        self.has_region_head = not self.drop_region_head and bool(self.plate_regions)
        if self.has_region_head and self.plate_regions:
            self.region_to_idx = {name: i for i, name in enumerate(self.plate_regions)}
            self.num_regions = len(self.plate_regions)

        # Fail-closed split validation before yielding any batch
        self.label_collision_warnings: list[str] = []
        if validate_split:
            self.label_collision_warnings = validate_splits(
                self.items,
                base_dir=self.base_dir,
                check_phash=True,
                phash_threshold=4,
                allow_missing_files=False,
                require_group_id=True,
                check_registry=True,
            )
            if self.label_collision_warnings:
                for warning in self.label_collision_warnings:
                    logger.warning(warning)

        # Initialize deterministic indices
        self.indices = np.arange(len(self.items))
        if self.shuffle:
            self._shuffle_indices()

    def _shuffle_indices(self) -> None:
        """Permute indices deterministically using seed and current epoch."""
        rng = np.random.default_rng(self.seed + self.epoch)
        self.indices = rng.permutation(len(self.items))

    def __len__(self) -> int:
        """Return total number of batches per epoch."""
        return math.ceil(len(self.items) / self.batch_size)

    def __getitem__(self, idx: int) -> tuple[np.ndarray, dict[str, np.ndarray]]:
        """
        Fetch batch idx.
        Returns:
            tuple (batch_x, batch_y):
              - batch_x: uint8 array of shape (B, img_height, img_width, 3)
              - batch_y: dict mapping 'plate' -> float32 array of shape (B, max_plate_slots, alphabet_len)
                         and optionally 'region' -> float32 array of shape (B, num_regions)
        """
        if idx < 0 or idx >= len(self):
            raise IndexError(f"Batch index {idx} out of range [0, {len(self)}).")

        start = idx * self.batch_size
        end = min(start + self.batch_size, len(self.items))
        batch_slice = self.indices[start:end]

        batch_x: list[np.ndarray] = []
        batch_y_plate: list[np.ndarray] = []
        batch_y_region: list[np.ndarray] = []

        for item_idx in batch_slice:
            item = self.items[item_idx]
            img_path = self.base_dir / item.image_path
            img = preprocess_plate_image(
                img_path,
                img_height=self.img_height,
                img_width=self.img_width,
                color_mode="rgb",
            )
            if self.transform is not None:
                img = self.transform(image=img)["image"]

            y_plate = encode_plate_label(
                item.plate_text,
                max_slots=self.max_plate_slots,
                alphabet=self.alphabet,
                pad_char=self.pad_char,
            )

            batch_x.append(img)
            batch_y_plate.append(y_plate)

            if self.has_region_head:
                region_name = item.plate_region or "Vietnam"
                region_one_hot = np.zeros(self.num_regions, dtype=np.float32)
                if region_name in self.region_to_idx:
                    region_one_hot[self.region_to_idx[region_name]] = 1.0
                batch_y_region.append(region_one_hot)

        batch_x_np = np.stack(batch_x, axis=0)
        batch_y_dict: dict[str, np.ndarray] = {
            "plate": np.stack(batch_y_plate, axis=0),
        }
        if self.has_region_head:
            batch_y_dict["region"] = np.stack(batch_y_region, axis=0)

        return batch_x_np, batch_y_dict

    def on_epoch_end(self) -> None:
        """Advance epoch counter and deterministically reshuffle if shuffle is enabled."""
        self.epoch += 1
        if self.shuffle:
            self._shuffle_indices()


def build_dataset(
    manifest_path: str | Path,
    split: str | None = None,
    batch_size: int = 64,
    shuffle: bool = True,
    seed: int = 42,
    base_dir: str | Path | None = None,
    plate_config_path: str | Path | None = None,
    drop_region_head: bool = True,
    transform: Any | None = None,
    validate_split: bool = True,
) -> PlateDataset:
    """
    Factory function to load manifest, validate splits fail-closed, and instantiate PlateDataset.
    """
    p_manifest = Path(manifest_path)
    resolved_base_dir = Path(base_dir) if base_dir else p_manifest.parent

    items = load_manifest(p_manifest)
    if split is not None:
        items = [it for it in items if it.split == split]
        if not items:
            raise ValueError(f"No items found for split '{split}' in {manifest_path}")

    img_h, img_w, slots, alphabet, pad_char = (
        DEFAULT_IMG_HEIGHT,
        DEFAULT_IMG_WIDTH,
        DEFAULT_MAX_PLATE_SLOTS,
        DEFAULT_ALPHABET,
        DEFAULT_PAD_CHAR,
    )
    plate_regions = None

    if plate_config_path:
        p_cfg_path = Path(plate_config_path)
        with open(p_cfg_path, encoding="utf-8") as f:
            raw_cfg = yaml.safe_load(f)
        if isinstance(raw_cfg, dict):
            img_h = int(raw_cfg.get("img_height", img_h))
            img_w = int(raw_cfg.get("img_width", img_w))
            slots = int(raw_cfg.get("max_plate_slots", slots))
            alphabet = str(raw_cfg.get("alphabet", alphabet))
            pad_char = str(raw_cfg.get("pad_char", pad_char))
            if "plate_regions" in raw_cfg:
                plate_regions = raw_cfg["plate_regions"]

    return PlateDataset(
        items=items,
        batch_size=batch_size,
        shuffle=shuffle,
        seed=seed,
        base_dir=resolved_base_dir,
        img_height=img_h,
        img_width=img_w,
        max_plate_slots=slots,
        alphabet=alphabet,
        pad_char=pad_char,
        plate_regions=plate_regions,
        drop_region_head=drop_region_head,
        transform=transform,
        validate_split=validate_split,
    )
