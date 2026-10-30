"""Dataset manifest loading, validation, and SHA-256 integrity verification."""

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import jsonschema

from plate_training.normalization import normalize_plate


@dataclass
class ManifestItem:
    """Represents a single row in the dataset manifest."""

    image_path: str
    sha256: str
    plate_text: str
    split: str
    provenance: str
    license: str
    plate_region: str = "VN"
    aspect_ratio: float | None = None
    quality: str = "readable"
    group_id: str | None = None

    def __post_init__(self) -> None:
        """
        Enforce data integrity rules at dataclass instantiation time.

        Mandatory group_id constraint (G7 / R3):
        Any item assigned to non-frozen splits ('train' or 'val') MUST provide
        a non-empty group_id string to prevent multi-frame data leakage across splits.
        """
        if self.split in ("train", "val") and (
            self.group_id is None or not str(self.group_id).strip()
        ):
            raise ValueError(
                f"group_id is required and cannot be empty for split '{self.split}' "
                f"(item: '{self.image_path}')"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest item to serializable dictionary."""
        d = asdict(self)
        if self.aspect_ratio is None:
            d.pop("aspect_ratio", None)
        if self.group_id is None:
            d.pop("group_id", None)
        return d


def get_default_schema_path() -> Path:
    """Resolve default manifest JSON schema path."""
    # From plate_training package location: src/plate_training/ -> training/data/
    candidate = (
        Path(__file__).resolve().parent.parent.parent / "data" / "manifest.schema.json"
    )
    if candidate.exists():
        return candidate
    return Path("training/data/manifest.schema.json").resolve()


def compute_file_sha256(file_path: str | Path) -> str:
    """Compute lowercase hexadecimal SHA-256 checksum of raw image bytes."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def validate_manifest(
    manifest_data: list[dict[str, Any]], schema_path: str | Path | None = None
) -> None:
    """
    Validate manifest data dictionary against JSON Schema Draft 2020-12 / Draft 7.
    Raises jsonschema.ValidationError on schema mismatch.
    """
    path = Path(schema_path) if schema_path else get_default_schema_path()
    with open(path, encoding="utf-8") as f:
        schema = json.load(f)

    validator_cls = jsonschema.validators.validator_for(schema)
    validator = validator_cls(schema)
    validator.validate(manifest_data)


def load_manifest(
    manifest_path: str | Path, schema_path: str | Path | None = None
) -> list[ManifestItem]:
    """
    Load dataset manifest from JSON file, validate against schema,
    and return list of ManifestItem objects with normalized plate text.
    """
    path = Path(manifest_path)
    with open(path, encoding="utf-8") as f:
        raw_data = json.load(f)

    if not isinstance(raw_data, list):
        raise ValueError(
            f"Manifest at {manifest_path} must be a JSON array of objects."
        )

    validate_manifest(raw_data, schema_path=schema_path)

    items: list[ManifestItem] = []
    for row in raw_data:
        norm_text = normalize_plate(row.get("plate_text", ""))
        group_val = row.get("group_id")
        item = ManifestItem(
            image_path=str(row["image_path"]),
            sha256=str(row["sha256"]).lower(),
            plate_text=norm_text,
            split=str(row["split"]),
            provenance=str(row["provenance"]),
            license=str(row["license"]),
            plate_region=str(row.get("plate_region", "VN")),
            aspect_ratio=float(row["aspect_ratio"]) if "aspect_ratio" in row else None,
            quality=str(row.get("quality", "readable")),
            group_id=str(group_val) if group_val is not None else None,
        )
        items.append(item)

    return items


def save_manifest(items: list[ManifestItem], manifest_path: str | Path) -> None:
    """Save ManifestItem objects to a formatted JSON manifest file."""
    path = Path(manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = [item.to_dict() for item in items]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
        f.write("\n")


def verify_image_hashes(
    items: list[ManifestItem], base_dir: str | Path, fail_fast: bool = False
) -> dict[str, bool]:
    """
    Verify physical existence and SHA-256 integrity of all images in manifest.
    Returns mapping from image_path to verification result (True/False).
    Raises ValueError if fail_fast=True and any image fails verification.
    """
    root = Path(base_dir)
    results: dict[str, bool] = {}

    for item in items:
        target = root / item.image_path
        if not target.is_file():
            if fail_fast:
                raise ValueError(
                    f"Image not found at {target} for manifest row {item.image_path}"
                )
            results[item.image_path] = False
            continue

        actual_hash = compute_file_sha256(target)
        if actual_hash != item.sha256.lower():
            if fail_fast:
                raise ValueError(
                    f"SHA-256 mismatch for {item.image_path}: expected {item.sha256}, got {actual_hash}"
                )
            results[item.image_path] = False
        else:
            results[item.image_path] = True

    return results
