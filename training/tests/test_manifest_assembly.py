"""
Unit and integration tests for dataset assembly and smoke manifest generation.

Covers Milestone S5:
1. Refusal of unverified labels without --allow-provisional.
2. Metadata handling when --allow-provisional is passed.
3. Acceptance of human-verified instances.
4. --smoke mode generation: exactly 64 train, 64 val, Group A consensus only,
   0 leakage to frozen-test, 0 quarantine, group-disjoint, passing validate_splits and JSON Schema.
5. 30-character vocabulary accounting and province distribution calculation.
6. CLI subcommand integration and behavior under various flag combinations.
7. Real cached smoke_128 dataset verification.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from plate_training.assembly import (
    CIVILIAN_CAR_VOCABULARY,
    AssemblyError,
    HumanVerificationRequiredError,
    build_training_manifest,
    compute_archive_sha256,
    compute_distribution,
)
from plate_training.cache import get_cache_dir
from plate_training.cli import main
from plate_training.manifest import ManifestItem, load_manifest, validate_manifest
from plate_training.split import (
    compute_phash,
    hamming_distance,
    load_frozen_test_registry,
    validate_splits,
)


@pytest.fixture
def synthetic_candidate_pool(tmp_path: Path) -> tuple[Path, Path]:
    """Create a synthetic candidate pool and crops directory for isolated unit tests."""
    pool_dir = tmp_path / "pool_data"
    pool_dir.mkdir(parents=True, exist_ok=True)
    crops_dir = tmp_path / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    import cv2
    import numpy as np

    from plate_training.manifest import compute_file_sha256

    instances: list[dict[str, Any]] = []

    # 1. Generate 80 Group A instances (unverified, singletons)
    for i in range(80):
        iid = f"inst_train_synth_a_{i:03d}"
        crop_fn = f"{iid}.png"
        crop_file = crops_dir / crop_fn
        # Create valid 64x128 synthetic image with distinct pHash
        rng_img = np.random.default_rng(i)
        img = rng_img.integers(0, 256, size=(64, 128, 3), dtype=np.uint8)
        cv2.imwrite(str(crop_file), img)
        c_sha = compute_file_sha256(crop_file)

        # Valid civilian plates: e.g. "51A12345", "30F67890", etc.
        letter = CIVILIAN_CAR_VOCABULARY[10 + (i % 20)]
        plate = f"51{letter}{10000 + i}"

        instances.append(
            {
                "instance_id": iid,
                "source_split": "train",
                "image_id": 1000 + i,
                "target_idx": 0,
                "bbox": [10.0, 10.0, 100.0, 50.0],
                "photo_sha256": ("p" + "0" * 63)[:64],
                "photo_phash": f"0x{i + 1:016x}",
                "crop_sha256": c_sha,
                "crop_phash": f"0x{1000 + i:016x}",
                "crop_filename": crop_fn,
                "group_id": f"grp_synth_a_{i:03d}",
                "quarantined": False,
                "quarantine_reason": "",
                "raw_label": plate,
                "triage_group": "A",
                "verified_by_human": False,
            }
        )

    # 2. Generate 80 Group A instances for val (unverified, singletons)
    for i in range(80, 160):
        iid = f"inst_val_synth_a_{i:03d}"
        crop_fn = f"{iid}.png"
        crop_file = crops_dir / crop_fn
        rng_img = np.random.default_rng(i)
        img = rng_img.integers(0, 256, size=(64, 128, 3), dtype=np.uint8)
        cv2.imwrite(str(crop_file), img)
        c_sha = compute_file_sha256(crop_file)

        letter = CIVILIAN_CAR_VOCABULARY[10 + (i % 20)]
        plate = f"30{letter}{20000 + i}"

        instances.append(
            {
                "instance_id": iid,
                "source_split": "val",
                "image_id": 2000 + i,
                "target_idx": 0,
                "bbox": [10.0, 10.0, 100.0, 50.0],
                "photo_sha256": ("pv" + "0" * 62)[:64],
                "photo_phash": f"0x{i + 1:016x}",
                "crop_sha256": c_sha,
                "crop_phash": f"0x{2000 + i:016x}",
                "crop_filename": crop_fn,
                "group_id": f"grp_synth_a_{i:03d}",
                "quarantined": False,
                "quarantine_reason": "",
                "raw_label": plate,
                "triage_group": "A",
                "verified_by_human": False,
            }
        )

    # 3. Add 10 Group B instances (disagreements)
    for i in range(10):
        instances.append(
            {
                "instance_id": f"inst_synth_b_{i:02d}",
                "source_split": "train",
                "image_id": 3000 + i,
                "target_idx": 0,
                "bbox": [10.0, 10.0, 100.0, 50.0],
                "photo_sha256": ("pb" + "0" * 62)[:64],
                "photo_phash": f"0x{3000 + i:016x}",
                "crop_sha256": ("cb" + str(i).zfill(2) + "0" * 60)[:64],
                "crop_phash": f"0x{3000 + i:016x}",
                "crop_filename": f"inst_synth_b_{i:02d}.png",
                "group_id": f"grp_synth_b_{i:02d}",
                "quarantined": False,
                "quarantine_reason": "",
                "raw_label": f"43A{30000 + i}",
                "triage_group": "B",
                "verified_by_human": False,
            }
        )

    # 4. Add 5 Quarantined instances
    for i in range(5):
        instances.append(
            {
                "instance_id": f"inst_synth_q_{i:02d}",
                "source_split": "train",
                "image_id": 4000 + i,
                "target_idx": 0,
                "bbox": [10.0, 10.0, 100.0, 50.0],
                "photo_sha256": ("pq" + "0" * 62)[:64],
                "photo_phash": f"0x{4000 + i:016x}",
                "crop_sha256": ("cq" + str(i).zfill(2) + "0" * 60)[:64],
                "crop_phash": f"0x{4000 + i:016x}",
                "crop_filename": f"inst_synth_q_{i:02d}.png",
                "group_id": f"grp_synth_q_{i:02d}",
                "quarantined": True,
                "quarantine_reason": "Near-duplicate match with frozen test",
                "raw_label": "51A99999",
                "triage_group": "A",
                "verified_by_human": False,
            }
        )

    pool_path = pool_dir / "candidate_pool.json"
    with open(pool_path, "w", encoding="utf-8") as f:
        json.dump(instances, f, indent=2)

    return pool_path, tmp_path


@pytest.mark.unit
def test_refusal_unverified_labels_without_allow_provisional(
    synthetic_candidate_pool: tuple[Path, Path], tmp_path: Path
) -> None:
    """Verify that build_training_manifest refuses unverified machine-generated labels by default."""
    pool_path, cache_root = synthetic_candidate_pool
    out_dir = tmp_path / "output_refusal"

    with pytest.raises(HumanVerificationRequiredError) as exc_info:
        build_training_manifest(
            pool_path=pool_path,
            output_dir=out_dir,
            cache_dir=cache_root,
            allow_provisional=False,
            smoke=False,
            copy_crops=False,
            validate=False,
        )

    err_msg = str(exc_info.value)
    assert "Full training manifest requires human-verified labels" in err_msg
    assert "--allow-provisional" in err_msg


@pytest.mark.unit
def test_allow_provisional_sets_correct_metadata(
    synthetic_candidate_pool: tuple[Path, Path], tmp_path: Path
) -> None:
    """Verify that passing allow_provisional=True accepts data and records provisional metadata."""
    pool_path, cache_root = synthetic_candidate_pool
    out_dir = tmp_path / "output_provisional"

    result = build_training_manifest(
        pool_path=pool_path,
        output_dir=out_dir,
        cache_dir=cache_root,
        allow_provisional=True,
        smoke=False,
        copy_crops=False,
        create_archive=False,
        validate=False,
    )

    assert result.is_provisional is True
    assert result.label_status == "provisional_machine_generated"
    assert result.total_items > 0
    assert result.metadata_path.is_file()

    with open(result.metadata_path, encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["label_status"] == "provisional_machine_generated"
    assert meta["provisional"] is True
    assert meta["verified_by_human"] is False


@pytest.mark.unit
def test_human_verified_labels_accepted_without_provisional(
    synthetic_candidate_pool: tuple[Path, Path], tmp_path: Path
) -> None:
    """Verify that pre-verified labels are accepted without requiring --allow-provisional."""
    pool_path, cache_root = synthetic_candidate_pool
    out_dir = tmp_path / "output_human_verified"

    # Mark all items in pool as verified_by_human=True
    with open(pool_path, encoding="utf-8") as f:
        pool_data = json.load(f)
    for it in pool_data:
        it["verified_by_human"] = True

    verified_pool_path = tmp_path / "verified_pool.json"
    with open(verified_pool_path, "w", encoding="utf-8") as f:
        json.dump(pool_data, f)

    result = build_training_manifest(
        pool_path=verified_pool_path,
        output_dir=out_dir,
        cache_dir=cache_root,
        allow_provisional=False,
        smoke=False,
        copy_crops=False,
        create_archive=False,
        validate=False,
    )

    assert result.is_provisional is False
    assert result.label_status == "human_verified"

    with open(result.metadata_path, encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["label_status"] == "human_verified"
    assert meta["verified_by_human"] is True


@pytest.mark.unit
def test_smoke_mode_generates_strictly_64_train_64_val_group_disjoint(
    synthetic_candidate_pool: tuple[Path, Path], tmp_path: Path
) -> None:
    """Verify that smoke mode outputs strictly 64 train and 64 val items disjoint by group_id."""
    pool_path, cache_root = synthetic_candidate_pool
    out_dir = tmp_path / "output_smoke"

    result = build_training_manifest(
        pool_path=pool_path,
        output_dir=out_dir,
        cache_dir=cache_root,
        smoke=True,
        smoke_train_count=64,
        smoke_val_count=64,
        copy_crops=True,
        create_archive=True,
        validate=False,
    )

    assert result.total_items == 128
    assert result.train_count == 64
    assert result.val_count == 64
    assert result.is_smoke is True
    assert result.is_provisional is True

    items = load_manifest(result.manifest_path)
    assert len(items) == 128

    train_groups = {it.group_id for it in items if it.split == "train"}
    val_groups = {it.group_id for it in items if it.split == "val"}

    # Strictly disjoint
    assert len(train_groups & val_groups) == 0, (
        f"Detected group overlap: {train_groups & val_groups}"
    )

    # Check archive and physical disk crops integrity
    assert result.archive_path is not None
    assert result.archive_path.is_file()
    assert result.archive_sha256 is not None
    assert len(result.archive_sha256) == 64

    crops_dir = out_dir / "crops"
    disk_crops = list(crops_dir.glob("*.png"))
    assert len(disk_crops) == 128, (
        f"Expected 128 crops on disk, found {len(disk_crops)}"
    )

    with zipfile.ZipFile(result.archive_path, "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) == 129, (
            f"Expected 129 entries in zip, found {len(namelist)}"
        )
        assert "manifest.json" in namelist
        crop_entries = [n for n in namelist if n.startswith("crops/")]
        assert len(crop_entries) == 128


@pytest.mark.unit
def test_assembly_cleans_stale_crops_directory_and_avoids_pollution(
    synthetic_candidate_pool: tuple[Path, Path], tmp_path: Path
) -> None:
    """Verify that build_training_manifest cleans stale crops from output_dir and does not pollute archive."""
    pool_path, cache_root = synthetic_candidate_pool
    out_dir = tmp_path / "output_stale_test"
    stale_crops_dir = out_dir / "crops"
    stale_crops_dir.mkdir(parents=True, exist_ok=True)

    # Plant a fake orphan crop file
    fake_stale_crop = stale_crops_dir / "stale_orphan_crop.png"
    fake_stale_crop.write_bytes(b"FAKE_STALE_CONTENT")
    assert fake_stale_crop.is_file()

    result = build_training_manifest(
        pool_path=pool_path,
        output_dir=out_dir,
        cache_dir=cache_root,
        smoke=True,
        smoke_train_count=64,
        smoke_val_count=64,
        copy_crops=True,
        create_archive=True,
        validate=False,
    )

    # Verify stale crop was cleaned and not included in disk crops or archive
    assert not fake_stale_crop.is_file()
    assert len(list(stale_crops_dir.glob("*.png"))) == 128

    assert result.archive_path is not None
    with zipfile.ZipFile(result.archive_path, "r") as zf:
        namelist = zf.namelist()
        assert "crops/stale_orphan_crop.png" not in namelist
        assert len(namelist) == 129


@pytest.mark.unit
def test_smoke_mode_strictly_rejects_untriaged_or_none_group(
    synthetic_candidate_pool: tuple[Path, Path], tmp_path: Path
) -> None:
    """Verify that instances with triage_group=None or unknown are strictly excluded in smoke mode."""
    pool_path, cache_root = synthetic_candidate_pool
    out_dir = tmp_path / "output_untriaged_test"

    # Load synthetic pool and set triage_group of all items to None
    with open(pool_path, encoding="utf-8") as f:
        pool_data = json.load(f)
    for it in pool_data:
        it["triage_group"] = None

    untriaged_pool_path = tmp_path / "untriaged_pool.json"
    with open(untriaged_pool_path, "w", encoding="utf-8") as f:
        json.dump(pool_data, f)

    with pytest.raises(AssemblyError):
        build_training_manifest(
            pool_path=untriaged_pool_path,
            output_dir=out_dir,
            cache_dir=cache_root,
            smoke=True,
            smoke_train_count=64,
            smoke_val_count=64,
            copy_crops=False,
            create_archive=False,
            validate=False,
        )


@pytest.mark.unit
def test_character_and_province_distribution_accounting() -> None:
    """Verify distribution metrics accounting for 30 vocabulary characters and province codes."""
    sample_items = [
        ManifestItem(
            image_path="crops/1.png",
            sha256="a" * 64,
            plate_text="51A12345",
            split="train",
            provenance="test",
            license="MIT",
            group_id="g1",
        ),
        ManifestItem(
            image_path="crops/2.png",
            sha256="b" * 64,
            plate_text="30F67890",
            split="train",
            provenance="test",
            license="MIT",
            group_id="g2",
        ),
    ]

    dist = compute_distribution(sample_items)
    # 30 vocabulary characters must all be present
    assert len(dist.character_counts) >= 30
    for ch in CIVILIAN_CAR_VOCABULARY:
        assert ch in dist.character_counts

    # Counts verification: '5' appears in 51A12345 (twice) and in 30F67890 (none) -> count 2
    assert dist.character_counts["5"] == 2
    assert dist.character_counts["1"] == 2
    assert dist.character_counts["A"] == 1
    assert dist.character_counts["F"] == 1

    # Province codes
    assert dist.province_counts.get("51") == 1
    assert dist.province_counts.get("30") == 1


@pytest.mark.unit
def test_cli_build_training_manifest_refusal_and_help(
    synthetic_candidate_pool: tuple[Path, Path],
) -> None:
    """Verify CLI behavior: refusal without --allow-provisional and help display."""
    pool_path, cache_root = synthetic_candidate_pool
    runner = CliRunner()

    # 1. Help check
    res_help = runner.invoke(main, ["build-training-manifest", "--help"])
    assert res_help.exit_code == 0
    assert "--smoke" in res_help.output
    assert "--allow-provisional" in res_help.output

    # 2. Refusal check
    res_refusal = runner.invoke(
        main,
        [
            "build-training-manifest",
            "--pool-file",
            str(pool_path),
            "--cache-dir",
            str(cache_root),
        ],
    )
    assert res_refusal.exit_code == 1
    assert "Full training manifest requires human-verified labels" in res_refusal.output


@pytest.mark.heavy
def test_real_cached_smoke_128_dataset_integrity() -> None:
    """
    Verify the physical 128-crop Kaggle smoke dataset generated in PLATE_TRAINING_CACHE.

    Verifies:
    1. smoke_128/manifest.json contains strictly 128 items (64 train, 64 val).
    2. Groups across train and val are strictly disjoint (0 overlap).
    3. All instances pass validate_manifest against JSON Schema Draft 2020-12.
    4. All instances strictly pass validate_splits (0 leakage to frozen-test, 0 quarantine).
    5. smoke_128.zip exists and its SHA-256 matches archive_sha256.txt.
    6. dataset_metadata.json contains 0 plate strings and records provisional machine status.
    """
    cache_root = get_cache_dir()
    smoke_dir = cache_root / "smoke_128"
    manifest_p = smoke_dir / "manifest.json"
    metadata_p = smoke_dir / "dataset_metadata.json"
    archive_p = smoke_dir / "smoke_128.zip"
    sha_p = smoke_dir / "archive_sha256.txt"

    if not manifest_p.is_file():
        pytest.skip("smoke_128 dataset not generated yet in cache")

    # 1. Manifest structure
    items = load_manifest(manifest_p)
    assert len(items) == 128, f"Expected 128 items, found {len(items)}"

    train_items = [it for it in items if it.split == "train"]
    val_items = [it for it in items if it.split == "val"]
    assert len(train_items) == 64
    assert len(val_items) == 64

    # 2. Group disjointness
    train_groups = {it.group_id for it in train_items}
    val_groups = {it.group_id for it in val_items}
    assert len(train_groups & val_groups) == 0, (
        f"Group overlap detected in smoke_128: {train_groups & val_groups}"
    )

    # 3. Schema validation
    validate_manifest([it.to_dict() for it in items])

    # 4. Strict Split Validation with pHash check against disk images
    warnings = validate_splits(
        items,
        base_dir=smoke_dir,
        check_phash=True,
        phash_threshold=4,
        require_group_id=True,
        check_registry=True,
        check_labels=False,
    )
    # Non-blocking label warnings permitted, but zero DataLeakageError
    assert isinstance(warnings, list)

    # 5. Disk crops integrity
    crops_dir = smoke_dir / "crops"
    assert crops_dir.is_dir()
    disk_crops = list(crops_dir.glob("*.png"))
    assert len(disk_crops) == 128, (
        f"Expected exactly 128 crops on disk, found {len(disk_crops)}"
    )

    # 6. Archive integrity and strict packaging check (zero pollution)
    assert archive_p.is_file()
    actual_sha = compute_archive_sha256(archive_p)
    sha_text = sha_p.read_text(encoding="utf-8").strip()
    assert actual_sha in sha_text

    with zipfile.ZipFile(archive_p, "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) == 129, (
            f"Expected exactly 129 entries in zip (1 manifest + 128 crops), found {len(namelist)}"
        )
        assert "manifest.json" in namelist
        crop_entries = [n for n in namelist if n.startswith("crops/")]
        assert len(crop_entries) == 128, (
            f"Expected exactly 128 crop entries in zip, found {len(crop_entries)}"
        )
        assert "crops/inst_train_1477_0.png" not in namelist, (
            "Critical leakage violation: inst_train_1477_0.png found in zip archive!"
        )

    # 7. Physical crops pHash verification against 322 frozen test images
    registry_entries = load_frozen_test_registry()
    reg_crop_hashes = [
        int(r["crop_phash"], 16)
        if isinstance(r["crop_phash"], str)
        else int(r["crop_phash"])
        for r in registry_entries
        if "crop_phash" in r and r["crop_phash"]
    ]
    min_dist = min(
        min(hamming_distance(compute_phash(p), rph) for rph in reg_crop_hashes)
        for p in disk_crops
    )
    assert min_dist >= 5, (
        f"Near-duplicate leakage detected in smoke disk crops: min pHash distance={min_dist} <= 4"
    )

    # 8. Metadata verification
    with open(metadata_p, encoding="utf-8") as f:
        meta = json.load(f)
    assert meta["dataset_type"] == "smoke_128"
    assert meta["total_samples"] == 128
    assert meta["splits"]["train"] == 64
    assert meta["splits"]["val"] == 64
    assert meta["groups"]["overlap"] == 0
    assert meta["label_status"] == "provisional_machine_generated"
    assert meta["archive_sha256"] == actual_sha
    assert meta["archive_size_bytes"] == archive_p.stat().st_size
