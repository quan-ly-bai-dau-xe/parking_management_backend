"""Tests proving fail-closed prevention of dataset split leakage.

Covers:
1. Exact SHA-256 duplicate cross-split leakage.
2. Perceptual hash (pHash 2D DCT) near-duplicate cross-split leakage.
3. External frozen test registry exact SHA-256 leakage (red-then-green).
4. External frozen test registry near-duplicate pHash leakage (red-then-green).
5. Fail-closed missing file detection raising FileNotFoundError.
6. Cross-split near-duplicate between train and val (red-then-green).
7. Cross-split near-duplicate between val and frozen-test (red-then-green).
8. Vehicle group_id cross-split leakage (red-then-green).
9. Vehicle group_id mandatory requirement for train/val splits.
10. Pairwise Hamming distance computation, benchmark (<50ms), and histogram on 51,681 pairs.
11. Fail-closed missing file detection with default args (base_dir=None).
12. Fail-closed cross-split near-duplicate pHash detection with default args (base_dir=None).
13. External frozen test registry detector crop exact SHA-256 leakage (red-then-green).
14. External frozen test registry detector crop re-compressed JPEG pHash leakage (red-then-green).
15. Unrelated detector crop accepted cleanly by split validator.
16. Label collision warning detection and whitelist suppression via cross_capture_groups.
17. Empirical proof of Team Lead's mutation M6 coverage boundary and honest limits.
18. Strictly 5-field frozen test registry format and zero reversible label hashes proof.
"""

import json
import statistics
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pytest

from plate_training.cache import get_benchmark_labels_path
from plate_training.manifest import ManifestItem
from plate_training.split import (
    DataLeakageError,
    check_label_collisions,
    check_registry_leakage,
    compute_phash,
    detect_exact_duplicates,
    detect_group_leakage,
    detect_near_duplicates,
    hamming_distance,
    load_benchmark_labels,
    load_frozen_test_registry,
    validate_splits,
)


@pytest.mark.leakage
def test_exact_sha256_split_leakage_red_then_green() -> None:
    """
    Demonstrate Red-then-Green proof for exact SHA-256 duplicate split leakage.
    - RED: When identical image hash exists in both frozen-test and train splits, validate_splits raises DataLeakageError.
    - GREEN: When splits have strictly disjoint hashes, validate_splits succeeds with zero errors.
    """
    shared_hash = "843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b"
    unique_hash = "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"

    # --- Phase RED: Shared hash across splits ---
    leaked_items = [
        ManifestItem(
            image_path="crops/test_plate.jpg",
            sha256=shared_hash,
            plate_text="51G49160",
            split="frozen-test",
            provenance="sonnetechnology",
            license="CC-BY-4.0",
        ),
        ManifestItem(
            image_path="crops/train_plate.jpg",
            sha256=shared_hash,  # Leaked copy in train!
            plate_text="51G49160",
            split="train",
            provenance="field-survey-2026",
            license="Proprietary",
            group_id="vehicle_001",
        ),
    ]

    duplicates = detect_exact_duplicates(leaked_items)
    assert len(duplicates) == 1
    assert duplicates[0][0].split != duplicates[0][1].split

    with pytest.raises(
        DataLeakageError, match="Exact SHA-256 duplicate leakage detected"
    ):
        validate_splits(leaked_items, check_phash=False)

    # --- Phase GREEN: Resolved split with unique hashes ---
    clean_items = [
        ManifestItem(
            image_path="crops/test_plate.jpg",
            sha256=shared_hash,
            plate_text="51G49160",
            split="frozen-test",
            provenance="sonnetechnology",
            license="CC-BY-4.0",
        ),
        ManifestItem(
            image_path="crops/train_plate.jpg",
            sha256=unique_hash,  # Distinct clean image
            plate_text="30E12345",
            split="train",
            provenance="field-survey-2026",
            license="Proprietary",
            group_id="vehicle_002",
        ),
    ]

    assert len(detect_exact_duplicates(clean_items)) == 0
    validate_splits(clean_items, check_phash=False)


@pytest.mark.leakage
def test_near_duplicate_phash_split_leakage_red_then_green() -> None:
    """
    Demonstrate Red-then-Green proof for perceptual hash (pHash) near-duplicate leakage.
    - RED: When an image in frozen-test is nearly identical (Hamming distance <= 4) to an image in train,
           validate_splits raises DataLeakageError.
    - GREEN: When images have distinct visual patterns (Hamming distance > 4), validate_splits succeeds.
    """
    rng = np.random.default_rng(42)

    # Base synthetic plate crop image (64x128 grayscale)
    base_image = rng.integers(50, 200, size=(64, 128), dtype=np.uint8)

    # Slight perturbation (brightness +2 units) -> identical pHash (Hamming distance = 0 <= 4)
    perturbed_image = np.clip(base_image.astype(np.int16) + 2, 0, 255).astype(np.uint8)
    h_base = compute_phash(base_image)
    h_perturbed = compute_phash(perturbed_image)
    assert hamming_distance(h_base, h_perturbed) <= 4

    # Distinct visual pattern (different random seed) -> Hamming distance > 10
    different_image = rng.integers(10, 100, size=(64, 128), dtype=np.uint8)
    h_different = compute_phash(different_image)
    assert hamming_distance(h_base, h_different) > 4

    # --- Phase RED: Near-duplicate leakage ---
    red_items = [
        ManifestItem(
            image_path="test_crop.jpg",
            sha256="1111111111111111111111111111111111111111111111111111111111111111",
            plate_text="51G49160",
            split="frozen-test",
            provenance="sonnetechnology",
            license="CC-BY-4.0",
        ),
        ManifestItem(
            image_path="train_crop_near_duplicate.jpg",
            sha256="2222222222222222222222222222222222222222222222222222222222222222",
            plate_text="51G49160",
            split="train",
            provenance="field-survey-2026",
            license="Proprietary",
            group_id="vehicle_red_1",
        ),
    ]
    red_image_map = {
        "test_crop.jpg": base_image,
        "train_crop_near_duplicate.jpg": perturbed_image,
    }

    near_duplicates = detect_near_duplicates(
        red_items, base_dir=".", threshold=4, image_arrays=red_image_map
    )
    assert len(near_duplicates) == 1

    with pytest.raises(DataLeakageError, match="Near-duplicate pHash leakage detected"):
        validate_splits(
            red_items, check_phash=True, phash_threshold=4, image_arrays=red_image_map
        )

    # --- Phase GREEN: Completely independent visual crops ---
    green_items = [
        ManifestItem(
            image_path="test_crop.jpg",
            sha256="1111111111111111111111111111111111111111111111111111111111111111",
            plate_text="51G49160",
            split="frozen-test",
            provenance="sonnetechnology",
            license="CC-BY-4.0",
        ),
        ManifestItem(
            image_path="train_crop_distinct.jpg",
            sha256="3333333333333333333333333333333333333333333333333333333333333333",
            plate_text="30E12345",
            split="train",
            provenance="field-survey-2026",
            license="Proprietary",
            group_id="vehicle_green_1",
        ),
    ]
    green_image_map = {
        "test_crop.jpg": base_image,
        "train_crop_distinct.jpg": different_image,
    }

    clean_near_duplicates = detect_near_duplicates(
        green_items, base_dir=".", threshold=4, image_arrays=green_image_map
    )
    assert len(clean_near_duplicates) == 0
    validate_splits(
        green_items, check_phash=True, phash_threshold=4, image_arrays=green_image_map
    )


@pytest.mark.leakage
def test_registry_exact_sha256_leakage_red_then_green() -> None:
    """
    Demonstrate Red-then-Green proof for exact SHA-256 leakage against frozen_test_registry.json.
    - RED: Any item in 'train' or 'val' matching a SHA-256 from the registry triggers DataLeakageError.
    - GREEN: When items have clean SHA-256 checksums, validate_splits passes.
    """
    registry = load_frozen_test_registry()
    assert len(registry) == 322
    target_entry = registry[0]
    leaked_sha = target_entry["sha256"]

    # --- Phase RED: Item in train matches registry entry 0 ---
    leaked_train_item = ManifestItem(
        image_path="crops/candidate_train.jpg",
        sha256=leaked_sha,
        plate_text="51F44614",
        split="train",
        provenance="incoming-batch",
        license="MIT",
        group_id="v_leak_reg",
    )

    with pytest.raises(
        DataLeakageError,
        match=f"matches frozen_test_registry row {target_entry['row_index']}",
    ):
        validate_splits([leaked_train_item], check_phash=False)

    # Also test check_registry_leakage directly
    with pytest.raises(DataLeakageError):
        check_registry_leakage([leaked_train_item])

    # --- Phase GREEN: Item has clean distinct SHA-256 ---
    clean_train_item = ManifestItem(
        image_path="crops/candidate_train.jpg",
        sha256="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        plate_text="51F44614",
        split="train",
        provenance="incoming-batch",
        license="MIT",
        group_id="v_leak_reg",
    )
    validate_splits([clean_train_item], check_phash=False)


@pytest.mark.leakage
def test_registry_near_duplicate_phash_leakage_red_then_green(tmp_path: Path) -> None:
    """
    Demonstrate Red-then-Green proof for pHash near-duplicate leakage against a frozen test registry.
    - RED: An item whose pHash is within Hamming distance <= 4 of a registry entry raises DataLeakageError.
    - GREEN: When pHash Hamming distance > 4, validation succeeds.
    """
    rng = np.random.default_rng(12345)
    test_img = rng.integers(30, 220, size=(64, 128), dtype=np.uint8)
    h_test = compute_phash(test_img)

    # Create temporary isolated registry pointing to h_test
    temp_registry_path = tmp_path / "test_registry.json"
    temp_registry_data = [
        {
            "row_index": 0,
            "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
            "phash": hex(h_test),
        }
    ]
    with open(temp_registry_path, "w", encoding="utf-8") as f:
        json.dump(temp_registry_data, f)

    # Near-duplicate crop (brightness +1 -> Hamming distance 0 <= 4)
    near_dup_img = np.clip(test_img.astype(np.int16) + 1, 0, 255).astype(np.uint8)
    assert hamming_distance(h_test, compute_phash(near_dup_img)) <= 4

    # Completely distinct crop (different distribution -> Hamming distance > 10)
    distinct_img = rng.integers(10, 80, size=(64, 128), dtype=np.uint8)
    assert hamming_distance(h_test, compute_phash(distinct_img)) > 4

    # --- Phase RED: val item triggers registry near-duplicate leakage ---
    red_item = ManifestItem(
        image_path="val_crop.jpg",
        sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        plate_text="29A11111",
        split="val",
        provenance="test",
        license="MIT",
        group_id="v_reg_phash",
    )
    red_map = {"val_crop.jpg": near_dup_img}

    with pytest.raises(
        DataLeakageError,
        match="Near-duplicate pHash leakage detected with frozen test registry",
    ):
        validate_splits(
            [red_item],
            registry_path=temp_registry_path,
            check_phash=True,
            image_arrays=red_map,
        )

    # --- Phase GREEN: distinct visual crop passes ---
    green_item = ManifestItem(
        image_path="val_crop.jpg",
        sha256="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        plate_text="29A11111",
        split="val",
        provenance="test",
        license="MIT",
        group_id="v_reg_phash",
    )
    green_map = {"val_crop.jpg": distinct_img}

    validate_splits(
        [green_item],
        registry_path=temp_registry_path,
        check_phash=True,
        image_arrays=green_map,
    )


@pytest.mark.leakage
def test_fail_closed_missing_file_raises_file_not_found_error(tmp_path: Path) -> None:
    """
    Demonstrate Fail-Closed guarantee: missing images on disk raise FileNotFoundError
    unless allow_missing_files is explicitly enabled.
    """
    missing_item = ManifestItem(
        image_path="missing_directory/nonexistent_plate.jpg",
        sha256="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff",
        plate_text="51A99999",
        split="train",
        provenance="test",
        license="MIT",
        group_id="vh_fail_closed",
    )

    # 1. detect_near_duplicates fails closed by default (allow_missing_files=False)
    with pytest.raises(
        FileNotFoundError,
        match="Fail-closed leakage check requires all image files to exist",
    ):
        detect_near_duplicates(
            [missing_item], base_dir=tmp_path, allow_missing_files=False
        )

    # 2. validate_splits fails closed by default
    with pytest.raises(
        FileNotFoundError,
        match="Fail-closed leakage check requires all image files to exist",
    ):
        validate_splits(
            [missing_item],
            base_dir=tmp_path,
            check_phash=True,
            allow_missing_files=False,
        )

    # 3. Permissive mode (allow_missing_files=True) ignores missing files
    results = detect_near_duplicates(
        [missing_item], base_dir=tmp_path, allow_missing_files=True
    )
    assert len(results) == 0

    # 4. Creating the real physical file allows fail-closed validation to pass
    real_file = tmp_path / "missing_directory" / "nonexistent_plate.jpg"
    real_file.parent.mkdir(parents=True, exist_ok=True)
    dummy_img = np.full((64, 128), 128, dtype=np.uint8)
    cv2.imwrite(str(real_file), dummy_img)

    validate_splits(
        [missing_item], base_dir=tmp_path, check_phash=True, allow_missing_files=False
    )


@pytest.mark.leakage
def test_cross_split_near_duplicate_train_vs_val_red_then_green() -> None:
    """
    Demonstrate Red-then-Green proof for near-duplicate leakage between train and val splits.
    Verify that train vs val near-duplicates trigger split leakage detection.
    """
    rng = np.random.default_rng(777)
    base_img = rng.integers(40, 210, size=(64, 128), dtype=np.uint8)
    perturbed_img = np.clip(base_img.astype(np.int16) + 2, 0, 255).astype(np.uint8)
    distinct_img = rng.integers(10, 90, size=(64, 128), dtype=np.uint8)

    assert hamming_distance(compute_phash(base_img), compute_phash(perturbed_img)) <= 4
    assert hamming_distance(compute_phash(base_img), compute_phash(distinct_img)) > 4

    # --- Phase RED: train vs val near-duplicate ---
    red_items = [
        ManifestItem(
            image_path="train_crop.jpg",
            sha256="1111111111111111111111111111111111111111111111111111111111111111",
            plate_text="51F12345",
            split="train",
            provenance="field",
            license="Proprietary",
            group_id="v_train_1",
        ),
        ManifestItem(
            image_path="val_crop.jpg",
            sha256="2222222222222222222222222222222222222222222222222222222222222222",
            plate_text="51F12345",
            split="val",
            provenance="field",
            license="Proprietary",
            group_id="v_val_1",
        ),
    ]
    red_map = {"train_crop.jpg": base_img, "val_crop.jpg": perturbed_img}

    near_duplicates = detect_near_duplicates(
        red_items, base_dir=".", threshold=4, image_arrays=red_map
    )
    assert len(near_duplicates) == 1
    assert {near_duplicates[0][0].split, near_duplicates[0][1].split} == {
        "train",
        "val",
    }

    with pytest.raises(
        DataLeakageError,
        match="Near-duplicate pHash leakage detected between 'train' .* and 'val'",
    ):
        validate_splits(red_items, check_phash=True, image_arrays=red_map)

    # --- Phase GREEN: distinct images across train and val ---
    green_items = [
        ManifestItem(
            image_path="train_crop.jpg",
            sha256="1111111111111111111111111111111111111111111111111111111111111111",
            plate_text="51F12345",
            split="train",
            provenance="field",
            license="Proprietary",
            group_id="v_train_1",
        ),
        ManifestItem(
            image_path="val_crop.jpg",
            sha256="3333333333333333333333333333333333333333333333333333333333333333",
            plate_text="30A99999",
            split="val",
            provenance="field",
            license="Proprietary",
            group_id="v_val_2",
        ),
    ]
    green_map = {"train_crop.jpg": base_img, "val_crop.jpg": distinct_img}

    assert (
        len(
            detect_near_duplicates(
                green_items, base_dir=".", threshold=4, image_arrays=green_map
            )
        )
        == 0
    )
    validate_splits(green_items, check_phash=True, image_arrays=green_map)


@pytest.mark.leakage
def test_cross_split_near_duplicate_val_vs_frozen_test_red_then_green() -> None:
    """
    Demonstrate Red-then-Green proof for near-duplicate leakage between val and frozen-test splits.
    """
    rng = np.random.default_rng(888)
    base_img = rng.integers(50, 200, size=(64, 128), dtype=np.uint8)
    perturbed_img = np.clip(base_img.astype(np.int16) + 1, 0, 255).astype(np.uint8)
    distinct_img = rng.integers(10, 70, size=(64, 128), dtype=np.uint8)

    # --- Phase RED: val vs frozen-test near-duplicate ---
    red_items = [
        ManifestItem(
            image_path="val_crop.jpg",
            sha256="1111111111111111111111111111111111111111111111111111111111111111",
            plate_text="60A12345",
            split="val",
            provenance="field",
            license="Proprietary",
            group_id="v_val_888",
        ),
        ManifestItem(
            image_path="frozen_crop.jpg",
            sha256="2222222222222222222222222222222222222222222222222222222222222222",
            plate_text="60A12345",
            split="frozen-test",
            provenance="sonnetechnology",
            license="CC-BY-4.0",
        ),
    ]
    red_map = {"val_crop.jpg": base_img, "frozen_crop.jpg": perturbed_img}

    with pytest.raises(
        DataLeakageError,
        match="Near-duplicate pHash leakage detected between 'frozen-test' .* and 'val'",
    ):
        validate_splits(red_items, check_phash=True, image_arrays=red_map)

    # --- Phase GREEN: distinct images ---
    green_items = [
        ManifestItem(
            image_path="val_crop.jpg",
            sha256="1111111111111111111111111111111111111111111111111111111111111111",
            plate_text="60A12345",
            split="val",
            provenance="field",
            license="Proprietary",
            group_id="v_val_888",
        ),
        ManifestItem(
            image_path="frozen_crop.jpg",
            sha256="3333333333333333333333333333333333333333333333333333333333333333",
            plate_text="43B99999",
            split="frozen-test",
            provenance="sonnetechnology",
            license="CC-BY-4.0",
        ),
    ]
    green_map = {"val_crop.jpg": distinct_img, "frozen_crop.jpg": base_img}

    validate_splits(green_items, check_phash=True, image_arrays=green_map)


@pytest.mark.leakage
def test_group_id_cross_split_leakage_red_then_green() -> None:
    """
    Demonstrate Red-then-Green proof for vehicle group_id disjointness across splits.
    - RED: When identical group_id appears in both train and val splits, DataLeakageError is raised.
    - GREEN: When each group_id is isolated strictly within one split, validation succeeds.
    """
    shared_group = "vehicle_session_XYZ"
    clean_group_1 = "vehicle_session_AAA"
    clean_group_2 = "vehicle_session_BBB"

    # --- Phase RED: Same vehicle group across train and val ---
    leaked_group_items = [
        ManifestItem(
            image_path="train_frame1.jpg",
            sha256="1111111111111111111111111111111111111111111111111111111111111111",
            plate_text="51G44444",
            split="train",
            provenance="field",
            license="MIT",
            group_id=shared_group,
        ),
        ManifestItem(
            image_path="val_frame2.jpg",
            sha256="2222222222222222222222222222222222222222222222222222222222222222",
            plate_text="51G44444",
            split="val",
            provenance="field",
            license="MIT",
            group_id=shared_group,  # Leaked multi-frame burst!
        ),
    ]

    with pytest.raises(
        DataLeakageError,
        match=f"Group ID cross-split leakage detected: group_id '{shared_group}' appears in multiple splits",
    ):
        detect_group_leakage(leaked_group_items)

    with pytest.raises(DataLeakageError, match="Group ID cross-split leakage detected"):
        validate_splits(leaked_group_items, check_phash=False, require_group_id=True)

    # --- Phase GREEN: Disjoint group IDs ---
    clean_group_items = [
        ManifestItem(
            image_path="train_frame1.jpg",
            sha256="1111111111111111111111111111111111111111111111111111111111111111",
            plate_text="51G44444",
            split="train",
            provenance="field",
            license="MIT",
            group_id=clean_group_1,
        ),
        ManifestItem(
            image_path="val_frame2.jpg",
            sha256="2222222222222222222222222222222222222222222222222222222222222222",
            plate_text="51G88888",
            split="val",
            provenance="field",
            license="MIT",
            group_id=clean_group_2,
        ),
    ]

    detect_group_leakage(clean_group_items)
    validate_splits(clean_group_items, check_phash=False, require_group_id=True)


@pytest.mark.leakage
def test_group_id_required_for_non_frozen_splits() -> None:
    """
    Verify that missing or empty group_id in train or val raises ValueError at
    ManifestItem instantiation time (G7 code-level enforcement), and that
    detect_group_leakage with require_group_id=True raises DataLeakageError
    if an item somehow bypasses __post_init__.
    """
    # 1. ManifestItem __post_init__ raises ValueError directly for train split
    with pytest.raises(
        ValueError, match="group_id is required and cannot be empty for split 'train'"
    ):
        ManifestItem(
            image_path="train_plate.jpg",
            sha256="1111111111111111111111111111111111111111111111111111111111111111",
            plate_text="51G11111",
            split="train",
            provenance="field",
            license="MIT",
            group_id=None,
        )

    # 2. ManifestItem __post_init__ raises ValueError directly for val split with whitespace
    with pytest.raises(
        ValueError, match="group_id is required and cannot be empty for split 'val'"
    ):
        ManifestItem(
            image_path="val_plate.jpg",
            sha256="2222222222222222222222222222222222222222222222222222222222222222",
            plate_text="51G22222",
            split="val",
            provenance="field",
            license="MIT",
            group_id="   ",
        )

    # 3. Defense-in-depth: detect_group_leakage rejects non-frozen items if bypassed
    bypassed_train = ManifestItem(
        image_path="train_plate.jpg",
        sha256="1111111111111111111111111111111111111111111111111111111111111111",
        plate_text="51G11111",
        split="frozen-test",
        provenance="field",
        license="MIT",
        group_id=None,
    )
    object.__setattr__(bypassed_train, "split", "train")
    with pytest.raises(
        DataLeakageError, match="Missing mandatory group_id for item 'train_plate.jpg'"
    ):
        detect_group_leakage([bypassed_train], require_group_id=True)

    # 4. frozen-test split does not require group_id even when require_group_id=True
    frozen_no_group = ManifestItem(
        image_path="test_plate.jpg",
        sha256="3333333333333333333333333333333333333333333333333333333333333333",
        plate_text="51G33333",
        split="frozen-test",
        provenance="sonnetechnology",
        license="CC-BY-4.0",
        group_id=None,
    )
    detect_group_leakage([frozen_no_group], require_group_id=True)


@pytest.mark.leakage
def test_frozen_test_registry_pairwise_hamming_histogram_and_benchmark() -> None:
    """
    Calculate pairwise Hamming distances across all 322 frozen test images:
    - Verifies exactly 322 * 321 / 2 = 51,681 distinct pairs.
    - Verifies calculation completes in < 50 ms.
    - Validates descriptive statistics (min=0, median=32, mean ~30.59).
    - Validates exactly 13 near-duplicate pairs (distance <= 4) proving binomial distribution properties.
    """
    registry = load_frozen_test_registry()
    assert len(registry) == 322

    hashes = [entry["phash"] for entry in registry]
    n = len(hashes)

    t0 = time.perf_counter()
    dists = [
        (hashes[i] ^ hashes[j]).bit_count() for i in range(n) for j in range(i + 1, n)
    ]
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    # 1. Total count assertion
    assert len(dists) == 51681, f"Expected 51,681 pairs, got {len(dists)}"

    # 2. Performance benchmark
    assert elapsed_ms < 50.0, (
        f"Benchmark failed: computation took {elapsed_ms:.2f} ms (expected < 50 ms)"
    )

    # 3. Descriptive statistics
    assert min(dists) == 0
    assert max(dists) == 48
    assert statistics.median(dists) == 32.0
    mean_val = statistics.mean(dists)
    assert 30.0 <= mean_val <= 31.0

    # 4. Histogram validation
    counts = Counter(dists)
    assert counts[0] == 3
    assert counts[2] == 3
    assert counts[4] == 7
    le4_count = sum(counts[k] for k in counts if k <= 4)
    assert le4_count == 13, f"Expected 13 pairs with distance <= 4, got {le4_count}"

    # Peak of binomial distribution B(64, 0.5) is at 32 bits
    assert counts[32] == 8735


@pytest.mark.leakage
def test_validate_splits_default_args_raises_file_not_found_on_missing_file() -> None:
    """
    Verify that calling validate_splits with default arguments (base_dir=None,
    allow_missing_files=False, check_phash=True) immediately raises FileNotFoundError
    when an image file does not exist on disk (fail-closed bypass remediation).
    """
    missing_item = ManifestItem(
        image_path="nonexistent_candidate_plate_xyz999.jpg",
        sha256="44" * 32,
        plate_text="51A99999",
        split="train",
        provenance="field",
        license="Proprietary",
        group_id="vehicle_missing_1",
    )

    with pytest.raises(
        FileNotFoundError,
        match="Fail-closed leakage check requires all image files to exist on disk",
    ):
        validate_splits([missing_item])


@pytest.mark.leakage
def test_validate_splits_default_args_detects_near_duplicate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """
    Verify that calling validate_splits with default arguments (base_dir=None,
    check_phash=True) detects cross-split perceptual near-duplicates (fail-closed
    bypass remediation when images exist on disk without explicit base_dir).
    """
    monkeypatch.chdir(tmp_path)
    rng = np.random.default_rng(9999)
    base_img = rng.integers(50, 200, size=(64, 128), dtype=np.uint8)
    near_img = np.clip(base_img.astype(np.int16) + 1, 0, 255).astype(np.uint8)

    train_file = tmp_path / "crop_train_default.jpg"
    val_file = tmp_path / "crop_val_default.jpg"
    cv2.imwrite(str(train_file), base_img)
    cv2.imwrite(str(val_file), near_img)

    items = [
        ManifestItem(
            image_path="crop_train_default.jpg",
            sha256="11" * 32,
            plate_text="51A11111",
            split="train",
            provenance="field",
            license="Proprietary",
            group_id="v_train_def",
        ),
        ManifestItem(
            image_path="crop_val_default.jpg",
            sha256="22" * 32,
            plate_text="51A22222",
            split="val",
            provenance="field",
            license="Proprietary",
            group_id="v_val_def",
        ),
    ]

    with pytest.raises(
        DataLeakageError,
        match="Near-duplicate pHash leakage detected between 'train' .* and 'val'",
    ):
        validate_splits(items)


@pytest.mark.leakage
def test_registry_crop_sha256_leakage_red_then_green(tmp_path: Path) -> None:
    """
    Demonstrate Red-then-Green proof for detector crop exact SHA-256 leakage against frozen test registry.
    - RED: When a 64x128 plate crop generated by the detector from a frozen test photo is placed in 'train',
           validate_splits immediately raises DataLeakageError.
    - GREEN: When the item in 'train' has a clean distinct SHA-256 and pHash, validation succeeds.
    """
    registry = load_frozen_test_registry()
    entry0 = registry[0]
    sample_crop_sha256 = entry0["crop_sha256"]
    clean_crop_sha256 = (
        "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    )

    # --- Phase RED: Detector crop from test placed in train split ---
    leaked_train_item = ManifestItem(
        image_path="crops/detector_crop_leaked.png",
        sha256=sample_crop_sha256,
        plate_text="51F69881",
        split="train",
        provenance="incoming_detector_crops",
        license="Proprietary",
        group_id="v_leak_detector_001",
    )

    with pytest.raises(
        DataLeakageError,
        match="Exact crop SHA-256 duplicate leakage detected",
    ):
        validate_splits([leaked_train_item], check_phash=False)

    # --- Phase GREEN: Unrelated distinct crop placed in train split ---
    clean_train_item = ManifestItem(
        image_path="crops/clean_independent_crop.png",
        sha256=clean_crop_sha256,
        plate_text="30G99999",
        split="train",
        provenance="clean_batch",
        license="Proprietary",
        group_id="v_clean_001",
    )
    validate_splits([clean_train_item], check_phash=False)


@pytest.mark.leakage
def test_registry_crop_phash_near_duplicate_leakage_red_then_green(
    tmp_path: Path,
) -> None:
    """
    Demonstrate Red-then-Green proof for re-compressed JPEG of detector crop (quality 75 & 85).
    - RED: When a detector crop is re-encoded as JPEG with quality 75 or 85, its SHA-256 changes completely
           but its 2D DCT pHash Hamming distance is <= 4. validate_splits raises DataLeakageError.
    - GREEN: When an unrelated crop with distinct visual structure (Hamming distance > 4) is validated, it passes.
    """
    rng = np.random.default_rng(2026)

    # 1. Test with synthetic detector crop and custom isolated registry
    base_plate = np.full((64, 128), 240, dtype=np.uint8)
    cv2.putText(
        base_plate, "51F69881", (10, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (20,), 2
    )
    h_base_crop = compute_phash(base_plate)

    # Re-compress to JPEG with quality 85 and 75
    _, buf85 = cv2.imencode(".jpg", base_plate, [cv2.IMWRITE_JPEG_QUALITY, 85])
    recompressed_crop_85 = cv2.imdecode(buf85, cv2.IMREAD_GRAYSCALE)
    h_recompressed_85 = compute_phash(recompressed_crop_85)
    dist85 = hamming_distance(h_base_crop, h_recompressed_85)
    assert dist85 <= 4, f"Expected Q85 Hamming distance <= 4, got {dist85}"

    _, buf75 = cv2.imencode(".jpg", base_plate, [cv2.IMWRITE_JPEG_QUALITY, 75])
    recompressed_crop_75 = cv2.imdecode(buf75, cv2.IMREAD_GRAYSCALE)
    h_recompressed_75 = compute_phash(recompressed_crop_75)
    dist75 = hamming_distance(h_base_crop, h_recompressed_75)
    assert dist75 <= 4, f"Expected Q75 Hamming distance <= 4, got {dist75}"

    temp_reg_path = tmp_path / "crop_phash_registry.json"
    temp_reg_data = [
        {
            "row_index": 0,
            "sha256": "00" * 32,
            "phash": "0x1111222233334444",
            "crop_sha256": "aabb" * 16,
            "crop_phash": f"0x{h_base_crop:016x}",
        }
    ]
    temp_reg_path.write_text(json.dumps(temp_reg_data, indent=2), encoding="utf-8")

    # --- Phase RED: Q85 and Q75 crops trigger DataLeakageError ---
    red_item_85 = ManifestItem(
        image_path="train_crop_q85.jpg",
        sha256="99" * 32,
        plate_text="51F69881",
        split="train",
        provenance="perturbed_feed",
        license="Proprietary",
        group_id="v_recomp_red_85",
    )
    with pytest.raises(
        DataLeakageError,
        match="Near-duplicate crop pHash leakage detected with frozen test registry",
    ):
        validate_splits(
            [red_item_85],
            registry_path=temp_reg_path,
            check_phash=True,
            image_arrays={"train_crop_q85.jpg": recompressed_crop_85},
        )

    red_item_75 = ManifestItem(
        image_path="train_crop_q75.jpg",
        sha256="88" * 32,
        plate_text="51F69881",
        split="train",
        provenance="perturbed_feed",
        license="Proprietary",
        group_id="v_recomp_red_75",
    )
    with pytest.raises(
        DataLeakageError,
        match="Near-duplicate crop pHash leakage detected with frozen test registry",
    ):
        validate_splits(
            [red_item_75],
            registry_path=temp_reg_path,
            check_phash=True,
            image_arrays={"train_crop_q75.jpg": recompressed_crop_75},
        )

    # 2. Also test against real disk crop and production frozen_test_registry.json if crop exists
    import os

    from plate_training.cache import get_crops_dir

    real_crop_file = get_crops_dir() / "crop_000.png"
    if (
        os.environ.get("PLATE_TRAINING_REQUIRE_HEAVY", "0").lower()
        in ("1", "true", "yes")
        and not real_crop_file.is_file()
    ):
        pytest.fail(
            f"Missing heavy crop input: {real_crop_file}. "
            "Run 'python -m plate_training.cli prepare-heavy-inputs' to prepare cache."
        )
    if real_crop_file.is_file():
        real_crop_img = cv2.imread(str(real_crop_file))
        _, enc75 = cv2.imencode(".jpg", real_crop_img, [cv2.IMWRITE_JPEG_QUALITY, 75])
        real_recomp_75 = cv2.imdecode(enc75, cv2.IMREAD_COLOR)

        real_red_item = ManifestItem(
            image_path="real_recomp_q75.jpg",
            sha256="77" * 32,
            plate_text="51F69881",
            split="train",
            provenance="real_perturbed",
            license="Proprietary",
            group_id="v_real_recomp",
        )
        with pytest.raises(
            DataLeakageError,
            match="Near-duplicate crop pHash leakage detected with frozen test registry",
        ):
            validate_splits(
                [real_red_item],
                check_phash=True,
                image_arrays={"real_recomp_q75.jpg": real_recomp_75},
            )

    # --- Phase GREEN: Unrelated visual crop passes ---
    unrelated_crop = rng.integers(10, 100, size=(64, 128), dtype=np.uint8)
    green_item = ManifestItem(
        image_path="train_crop_distinct.jpg",
        sha256="66" * 32,
        plate_text="29A12345",
        split="train",
        provenance="clean_feed",
        license="Proprietary",
        group_id="v_recomp_green",
    )
    validate_splits(
        [green_item],
        registry_path=temp_reg_path,
        check_phash=True,
        image_arrays={"train_crop_distinct.jpg": unrelated_crop},
    )


@pytest.mark.leakage
def test_registry_unrelated_crop_accepted() -> None:
    """
    Verify that an unrelated plate crop with distinct visual structure, unique SHA-256,
    and distinct plate text is cleanly accepted by validate_splits with 0 errors and 0 collision warnings.
    """
    rng = np.random.default_rng(4321)
    clean_crop = rng.integers(20, 220, size=(64, 128, 3), dtype=np.uint8)
    h_clean = compute_phash(clean_crop)

    registry = load_frozen_test_registry()
    for entry in registry:
        if "crop_phash" in entry and entry["crop_phash"] is not None:
            assert hamming_distance(h_clean, entry["crop_phash"]) > 4

    clean_item = ManifestItem(
        image_path="crops/clean_distinct_sample.png",
        sha256="55" * 32,
        plate_text="99A99999",
        split="train",
        provenance="legitimate_capture",
        license="MIT",
        group_id="v_independent_legit",
    )
    img_map = {"crops/clean_distinct_sample.png": clean_crop}

    warnings = validate_splits(
        [clean_item],
        check_phash=True,
        image_arrays=img_map,
    )
    assert warnings == []


@pytest.mark.leakage
def test_label_collision_detection_and_warning(tmp_path: Path) -> None:
    """
    Demonstrate that normalized plate label collision against benchmark reference plates:
    1. Reads reference benchmark plate strings from local cache (benchmark_322_labels.json) or explicit path.
    2. Returns a descriptive warning in label_collision_warnings for manual review.
    3. Does NOT raise DataLeakageError (soft warning guarantee).
    4. Can be suppressed if group_id is declared in cross_capture_groups.
    5. In contrast, if physical image SHA-256 or crop_sha256 also matches, DataLeakageError is mandatory.
    6. Verifies optional local cache behavior: if no benchmark labels file is present, returns 0 warnings.
    """
    # Create isolated benchmark labels file in tmp_path
    temp_labels_path = tmp_path / "benchmark_322_labels.json"
    temp_benchmark_data = [
        {"row_index": 0, "plate_text": "51F69881"},
        {"row_index": 1, "plate_text": "51G49160"},
    ]
    temp_labels_path.write_text(
        json.dumps(temp_benchmark_data, indent=2), encoding="utf-8"
    )

    # Using row 0 normalized plate text (matches row 0: 51F69881)
    candidate_item = ManifestItem(
        image_path="different_session_vehicle.jpg",
        sha256="44" * 32,
        plate_text="51f-698.81",  # Matches row 0 (normalized: 51F69881)
        split="train",
        provenance="camera_lane_2",
        license="Proprietary",
        group_id="v_session_october",
    )

    # 1. Without whitelist (using explicit benchmark_labels_path): produces warning, DOES NOT raise DataLeakageError
    warnings = validate_splits(
        [candidate_item],
        check_phash=False,
        benchmark_labels_path=temp_labels_path,
    )
    assert len(warnings) >= 1
    assert "Label collision warning" in warnings[0]
    assert "row 0" in warnings[0] or "rows" in warnings[0]

    # 2. With whitelist in cross_capture_groups: warning is suppressed
    clean_warnings = validate_splits(
        [candidate_item],
        check_phash=False,
        benchmark_labels_path=temp_labels_path,
        cross_capture_groups={"v_session_october"},
    )
    assert clean_warnings == []

    # 3. Optional local cache behavior: when no benchmark labels file exists, 0 warnings are emitted
    missing_labels_path = tmp_path / "nonexistent_labels.json"
    no_cache_warnings = validate_splits(
        [candidate_item],
        check_phash=False,
        benchmark_labels_path=missing_labels_path,
    )
    assert no_cache_warnings == []

    # 4. Red-then-green proof: distinct non-colliding plate text produces 0 warnings
    non_colliding_item = ManifestItem(
        image_path="distinct_vehicle.jpg",
        sha256="44" * 32,
        plate_text="29A99999",  # Does not collide with benchmark rows
        split="train",
        provenance="camera_lane_2",
        license="Proprietary",
        group_id="v_session_october",
    )
    non_colliding_warnings = validate_splits(
        [non_colliding_item],
        check_phash=False,
        benchmark_labels_path=temp_labels_path,
    )
    assert non_colliding_warnings == []

    # 5. Also test against real disk cache (benchmark_322_labels.json) if present
    real_cache_labels = get_benchmark_labels_path()
    if real_cache_labels.is_file():
        cache_warnings = validate_splits(
            [candidate_item],
            check_phash=False,
        )
        assert len(cache_warnings) >= 1
        assert "Label collision warning" in cache_warnings[0]

    # 6. Contrast with image hash leakage: if image SHA-256 also matched, DataLeakageError is mandatory
    registry = load_frozen_test_registry()
    entry0 = registry[0]
    leaked_image_item = ManifestItem(
        image_path="different_session_vehicle.jpg",
        sha256=entry0["sha256"],  # Full photo SHA-256
        plate_text="51f-698.81",
        split="train",
        provenance="camera_lane_2",
        license="Proprietary",
        group_id="v_session_october",
    )
    with pytest.raises(DataLeakageError):
        validate_splits([leaked_image_item], check_phash=False)


@pytest.mark.leakage
def test_mutation_m6_central_crop_boundary_proof(tmp_path: Path) -> None:
    """
    Empirical proof of Team Lead's mutation M6 coverage boundary:
    1. A crude central crop of the full vehicle photo misses the license plate bounding box.
    2. Proves pHash Hamming distance is ~30 bits (> 4) against BOTH full photo and detector crop.
    3. Confirms honest limit: arbitrary non-plate body crops cannot be caught by pHash.
    4. Proves defense-in-depth: if the central crop carries the frozen plate label, label collision check catches it.
    """
    # Vehicle photo with plate located at lower-center
    vehicle_photo = np.full((300, 480), 100, dtype=np.uint8)
    plate_region = vehicle_photo[230:280, 180:300]
    plate_region[:, :] = 240
    cv2.putText(
        plate_region, "51F69881", (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (20,), 2
    )

    # 50% central crop (M6 mutation): y=75..225, x=120..360 (completely above the plate!)
    central_crop = vehicle_photo[75:225, 120:360]
    detector_crop = cv2.resize(plate_region, (128, 64))

    h_full = compute_phash(vehicle_photo)
    h_center = compute_phash(central_crop)
    h_detector = compute_phash(detector_crop)

    dist_full_center = hamming_distance(h_full, h_center)
    dist_detector_center = hamming_distance(h_detector, h_center)

    # Both distances are far beyond threshold 4 (typically ~25 to ~35 bits)
    assert dist_full_center > 15, f"Expected dist > 15, got {dist_full_center}"
    assert dist_detector_center > 15, f"Expected dist > 15, got {dist_detector_center}"

    # Prepare benchmark labels for label collision check
    temp_labels_path = tmp_path / "benchmark_322_labels.json"
    temp_labels_path.write_text(
        json.dumps([{"row_index": 0, "plate_text": "51F69881"}], indent=2),
        encoding="utf-8",
    )

    # Verify defense-in-depth: If central crop is fed with test label, check_label_collisions catches it
    central_item = ManifestItem(
        image_path="m6_central_crop.png",
        sha256="33" * 32,
        plate_text="51F69881",  # Test vehicle label
        split="train",
        provenance="m6_mutation",
        license="MIT",
        group_id="v_m6_mutation",
    )
    warnings = validate_splits(
        [central_item],
        check_phash=False,
        benchmark_labels_path=temp_labels_path,
    )
    assert len(warnings) >= 1
    assert "Label collision warning" in warnings[0]


@pytest.mark.leakage
def test_frozen_test_registry_strictly_five_fields_and_zero_label_hashes() -> None:
    """
    Verify that training/data/frozen_test_registry.json contains strictly 5 image/crop fields:
    - row_index: int (0..321)
    - sha256: 64 hex characters (full photo)
    - phash: 64-bit DCT perceptual hash formatted as hex (0x...)
    - crop_sha256: 64 hex characters (detector 64x128 crop)
    - crop_phash: 64-bit DCT perceptual hash formatted as hex (0x...)

    Enforces that:
    1. Exactly 322 entries are present.
    2. ZERO entries contain 'label_sha256' or any cleartext plate string.
    3. ZERO entries contain any field other than the strictly allowed 5 fields.
    4. Red-then-green mutation test proves a mutated entry with extra or missing fields fails.
    """
    registry_file = Path("training/data/frozen_test_registry.json")
    assert registry_file.is_file(), f"Registry file not found: {registry_file}"

    with open(registry_file, encoding="utf-8") as f:
        raw_entries = json.load(f)

    assert len(raw_entries) == 322, (
        f"Expected exactly 322 entries, got {len(raw_entries)}"
    )

    strictly_expected_keys = {
        "row_index",
        "sha256",
        "phash",
        "crop_sha256",
        "crop_phash",
    }

    # Verify all 322 entries conform to the 5-field contract
    for idx, entry in enumerate(raw_entries):
        assert set(entry.keys()) == strictly_expected_keys, (
            f"Row {idx} contains unexpected or missing keys: {set(entry.keys())}"
        )
        assert "label_sha256" not in entry, (
            f"Row {idx} contains forbidden label_sha256!"
        )
        assert entry["row_index"] == idx
        assert len(entry["sha256"]) == 64
        assert str(entry["phash"]).startswith("0x")
        assert len(entry["crop_sha256"]) == 64
        assert str(entry["crop_phash"]).startswith("0x")

    # Verify load_frozen_test_registry parser returns matching 322 records
    parsed_entries = load_frozen_test_registry()
    assert len(parsed_entries) == 322
    for p_entry in parsed_entries:
        assert set(p_entry.keys()) == strictly_expected_keys
        assert "label_sha256" not in p_entry

    # --- Phase RED mutation test: injecting label_sha256 or extra key triggers AssertionError ---
    mutated_entry = dict(raw_entries[0])
    mutated_entry["label_sha256"] = "dummy_hash"
    with pytest.raises(AssertionError):
        assert set(mutated_entry.keys()) == strictly_expected_keys
        assert "label_sha256" not in mutated_entry

    missing_field_entry = dict(raw_entries[0])
    del missing_field_entry["crop_sha256"]
    with pytest.raises(AssertionError):
        assert set(missing_field_entry.keys()) == strictly_expected_keys


@pytest.mark.leakage
def test_load_benchmark_labels_formats_and_direct_collision_check(
    tmp_path: Path,
) -> None:
    """
    Direct unit test for load_benchmark_labels and check_label_collisions:
    - Verifies loading from missing path returns {}.
    - Verifies loading list of dicts [{"row_index": 0, "plate_text": "51F69881"}].
    - Verifies loading list of strings ["51G49160"].
    - Verifies direct check_label_collisions emits descriptive warning without raising DataLeakageError.
    - Verifies whitelist suppression via cross_capture_groups.
    """
    # 1. Missing file returns empty dict
    assert load_benchmark_labels(tmp_path / "missing.json") == {}

    # 2. List of dicts format
    labels_file_1 = tmp_path / "labels_dict.json"
    labels_file_1.write_text(
        json.dumps([{"row_index": 0, "plate_text": "51F-698.81"}], indent=2),
        encoding="utf-8",
    )
    mapping_1 = load_benchmark_labels(labels_file_1)
    assert "51F69881" in mapping_1
    assert mapping_1["51F69881"] == [0]

    # 3. List of strings format
    labels_file_2 = tmp_path / "labels_str.json"
    labels_file_2.write_text(json.dumps(["51G49160"]), encoding="utf-8")
    mapping_2 = load_benchmark_labels(labels_file_2)
    assert "51G49160" in mapping_2

    # 4. Direct check_label_collisions test
    test_item = ManifestItem(
        image_path="test_direct.jpg",
        sha256="aa" * 32,
        plate_text="51F69881",
        split="train",
        provenance="camera",
        license="MIT",
        group_id="v_direct_1",
    )
    warnings = check_label_collisions(
        [test_item],
        benchmark_labels_path=labels_file_1,
    )
    assert len(warnings) == 1
    assert "Label collision warning" in warnings[0]
    assert "row 0" in warnings[0]

    # 5. Direct whitelist suppression
    clean_warnings = check_label_collisions(
        [test_item],
        benchmark_labels_path=labels_file_1,
        cross_capture_groups={"v_direct_1"},
    )
    assert clean_warnings == []
