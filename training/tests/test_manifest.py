"""Tests for manifest loading, schema validation, and SHA-256 image verification."""

import tempfile
from pathlib import Path

import jsonschema
import pytest

from plate_training.manifest import (
    ManifestItem,
    compute_file_sha256,
    load_manifest,
    save_manifest,
    validate_manifest,
    verify_image_hashes,
)


@pytest.fixture
def valid_manifest_data() -> list[dict]:
    """Provide valid synthetic manifest rows."""
    return [
        {
            "image_path": "crops/51G49160.jpg",
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            "plate_text": "51G49160",
            "split": "train",
            "provenance": "field-survey-2026",
            "license": "Proprietary",
            "plate_region": "VN",
            "quality": "readable",
            "group_id": "vehicle_001",
        },
        {
            "image_path": "crops/30E12345.jpg",
            "sha256": "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
            "plate_text": "30E12345",
            "split": "val",
            "provenance": "field-survey-2026",
            "license": "Proprietary",
            "plate_region": "VN",
            "quality": "readable",
            "group_id": "vehicle_002",
        },
        {
            "image_path": "crops/43B99999.jpg",
            "sha256": "843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b",
            "plate_text": "43B99999",
            "split": "frozen-test",
            "provenance": "sonnetechnology",
            "license": "CC-BY-4.0",
            "plate_region": "VN",
            "quality": "readable",
        },
    ]


@pytest.mark.unit
def test_valid_manifest_passes_validation(valid_manifest_data: list[dict]) -> None:
    """Verify that a compliant manifest passes JSON schema validation."""
    validate_manifest(valid_manifest_data)


@pytest.mark.unit
def test_missing_required_field_raises_validation_error(
    valid_manifest_data: list[dict],
) -> None:
    """Verify that omitting a mandatory field raises ValidationError."""
    invalid_data = [valid_manifest_data[0].copy()]
    del invalid_data[0]["sha256"]
    with pytest.raises(jsonschema.ValidationError):
        validate_manifest(invalid_data)


@pytest.mark.unit
def test_invalid_sha256_format_raises_validation_error(
    valid_manifest_data: list[dict],
) -> None:
    """Verify that a malformed SHA-256 hash raises ValidationError."""
    invalid_data = [valid_manifest_data[0].copy()]
    invalid_data[0]["sha256"] = "invalid_hash_too_short"
    with pytest.raises(jsonschema.ValidationError):
        validate_manifest(invalid_data)


@pytest.mark.unit
def test_invalid_split_value_raises_validation_error(
    valid_manifest_data: list[dict],
) -> None:
    """Verify that an illegal split name outside enum raises ValidationError."""
    invalid_data = [valid_manifest_data[0].copy()]
    invalid_data[0]["split"] = "unsupported_split_name"
    with pytest.raises(jsonschema.ValidationError):
        validate_manifest(invalid_data)


@pytest.mark.unit
def test_invalid_plate_characters_raises_validation_error(
    valid_manifest_data: list[dict],
) -> None:
    """Verify that lowercase or special characters in plate_text violate schema."""
    invalid_data = [valid_manifest_data[0].copy()]
    invalid_data[0]["plate_text"] = "51g-491.60"  # unnormalized
    with pytest.raises(jsonschema.ValidationError):
        validate_manifest(invalid_data)


@pytest.mark.unit
def test_save_and_load_manifest_roundtrip(valid_manifest_data: list[dict]) -> None:
    """Verify save_manifest and load_manifest preserve data and normalize text."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_file = Path(tmpdir) / "manifest.json"
        items = [
            ManifestItem(
                image_path=d["image_path"],
                sha256=d["sha256"],
                plate_text=d["plate_text"],
                split=d["split"],
                provenance=d["provenance"],
                license=d["license"],
                group_id=d.get("group_id"),
            )
            for d in valid_manifest_data
        ]
        save_manifest(items, manifest_file)
        loaded = load_manifest(manifest_file)
        assert len(loaded) == len(items)
        assert loaded[0].plate_text == "51G49160"
        assert loaded[0].group_id == "vehicle_001"
        assert loaded[1].group_id == "vehicle_002"
        assert loaded[2].split == "frozen-test"
        assert loaded[2].group_id is None


@pytest.mark.unit
def test_missing_group_id_for_train_or_val_raises_validation_error(
    valid_manifest_data: list[dict],
) -> None:
    """Verify that omitting group_id for train or val splits raises ValidationError."""
    invalid_train = [valid_manifest_data[0].copy()]  # train split
    invalid_train[0].pop("group_id", None)
    with pytest.raises(
        jsonschema.ValidationError, match="'group_id' is a required property"
    ):
        validate_manifest(invalid_train)

    invalid_val = [valid_manifest_data[1].copy()]  # val split
    invalid_val[0].pop("group_id", None)
    with pytest.raises(
        jsonschema.ValidationError, match="'group_id' is a required property"
    ):
        validate_manifest(invalid_val)


@pytest.mark.unit
def test_frozen_test_without_group_id_passes_validation(
    valid_manifest_data: list[dict],
) -> None:
    """Verify that frozen-test split does not require group_id."""
    frozen_data = [valid_manifest_data[2].copy()]  # frozen-test split
    assert "group_id" not in frozen_data[0]
    validate_manifest(frozen_data)


@pytest.mark.unit
def test_verify_image_hashes_integrity() -> None:
    """Verify that file modification is detected by verify_image_hashes."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        crop_file = root / "crop1.jpg"
        content = b"fake_jpeg_image_bytes_12345"
        crop_file.write_bytes(content)

        actual_sha = compute_file_sha256(crop_file)
        item = ManifestItem(
            image_path="crop1.jpg",
            sha256=actual_sha,
            plate_text="51G49160",
            split="train",
            provenance="test",
            license="MIT",
            group_id="vehicle_test_001",
        )

        # 1. Unmodified file passes
        results = verify_image_hashes([item], base_dir=root)
        assert results["crop1.jpg"] is True

        # 2. Mutate file -> hash mismatch detected
        crop_file.write_bytes(content + b"_mutated")
        results_mutated = verify_image_hashes([item], base_dir=root)
        assert results_mutated["crop1.jpg"] is False

        # 3. fail_fast raises ValueError
        with pytest.raises(ValueError, match="SHA-256 mismatch"):
            verify_image_hashes([item], base_dir=root, fail_fast=True)
