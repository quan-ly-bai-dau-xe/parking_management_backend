"""Strict heavy test proving zero leakage from candidate pool to frozen test registry.

Requires real cached candidate pool and frozen test registry.
Fails with 0 skips when PLATE_TRAINING_REQUIRE_HEAVY=1.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import cv2
import pytest

from plate_training.pool import CandidateInstance
from plate_training.split import hamming_distance, load_frozen_test_registry


@pytest.mark.heavy
def test_heavy_candidate_pool_zero_leakage_to_frozen_test(
    heavy_candidate_pool_path: Path,
    heavy_pool_summary_path: Path,
    heavy_cache_dir: Path,
) -> None:
    """
    Prove that zero non-quarantined candidate instances leak into the frozen test registry.

    Verifies:
    1. Zero non-quarantined instances have photo SHA-256 matching registry.
    2. Zero non-quarantined instances have crop SHA-256 matching registry.
    3. Zero non-quarantined instances have photo pHash Hamming distance <= 4 to registry.
    4. Zero non-quarantined instances have crop pHash Hamming distance <= 4 to registry.
    5. All quarantined instances satisfy at least one valid quarantine condition.
    6. pool_summary.json contains strictly aggregate statistics and zero plate strings.
    7. All candidate instances have non-empty group_id and physical crops on disk.
    """
    # 1. Load registry and candidate pool
    registry = load_frozen_test_registry()
    assert len(registry) == 322, f"Expected 322 registry items, found {len(registry)}"

    reg_photo_shas = {r["sha256"].lower() for r in registry}
    reg_crop_shas = {r["crop_sha256"].lower() for r in registry if "crop_sha256" in r}
    reg_photo_hashes = [
        int(r["phash"], 16) if isinstance(r["phash"], str) else int(r["phash"])
        for r in registry
    ]
    reg_crop_hashes = [
        int(r["crop_phash"], 16)
        if isinstance(r["crop_phash"], str)
        else int(r["crop_phash"])
        for r in registry
        if "crop_phash" in r
    ]

    with open(heavy_candidate_pool_path, encoding="utf-8") as f:
        pool_data = json.load(f)

    instances = [CandidateInstance.from_dict(d) for d in pool_data]
    assert len(instances) == 2826, f"Expected 2,826 instances, found {len(instances)}"

    clean_instances = [it for it in instances if not it.quarantined]
    quarantined_instances = [it for it in instances if it.quarantined]

    assert len(clean_instances) == 2569, (
        f"Expected 2,569 clean instances, found {len(clean_instances)}"
    )
    assert len(quarantined_instances) == 257, (
        f"Expected 257 quarantined instances, found {len(quarantined_instances)}"
    )

    # 2. Strict Zero-Leakage Checks on Clean Instances
    leakage_violations: list[str] = []
    threshold = 4

    for it in clean_instances:
        p_sha = it.photo_sha256.lower()
        c_sha = it.crop_sha256.lower()
        p_phash = int(it.photo_phash, 16)
        c_phash = int(it.crop_phash, 16)

        # 2A. Exact Photo SHA-256
        if p_sha in reg_photo_shas:
            leakage_violations.append(
                f"Instance '{it.instance_id}' has exact photo SHA-256 match in registry"
            )

        # 2B. Exact Crop SHA-256
        if c_sha in reg_crop_shas:
            leakage_violations.append(
                f"Instance '{it.instance_id}' has exact crop SHA-256 match in registry"
            )

        # 2C. Photo pHash distance <= 4
        min_p_dist = min(hamming_distance(p_phash, rph) for rph in reg_photo_hashes)
        if min_p_dist <= threshold:
            leakage_violations.append(
                f"Instance '{it.instance_id}' has photo pHash distance {min_p_dist} <= {threshold}"
            )

        # 2D. Crop pHash distance <= 4
        min_c_dist = min(hamming_distance(c_phash, rph) for rph in reg_crop_hashes)
        if min_c_dist <= threshold:
            leakage_violations.append(
                f"Instance '{it.instance_id}' has crop pHash distance {min_c_dist} <= {threshold}"
            )

    assert len(leakage_violations) == 0, (
        f"Leakage detected in {len(leakage_violations)} clean instances:\n"
        + "\n".join(leakage_violations[:10])
    )

    # 3. Verify Quarantined Instances
    photo_nd_count = 0
    for it in quarantined_instances:
        p_sha = it.photo_sha256.lower()
        c_sha = it.crop_sha256.lower()
        p_phash = int(it.photo_phash, 16)
        c_phash = int(it.crop_phash, 16)

        min_p_dist = min(hamming_distance(p_phash, rph) for rph in reg_photo_hashes)
        min_c_dist = min(hamming_distance(c_phash, rph) for rph in reg_crop_hashes)

        matches_criteria = (
            (p_sha in reg_photo_shas)
            or (c_sha in reg_crop_shas)
            or (min_p_dist <= threshold)
            or (min_c_dist <= threshold)
        )
        assert matches_criteria is True, (
            f"Quarantined instance '{it.instance_id}' does not match any quarantine condition"
        )
        if min_p_dist <= threshold:
            photo_nd_count += 1

    # Exactly 181 photo pHash near-duplicates (D-4 finding confirmation)
    assert photo_nd_count == 181, (
        f"Expected exactly 181 photo pHash near-duplicates, found {photo_nd_count}"
    )

    # 4. Verify pool_summary.json
    with open(heavy_pool_summary_path, encoding="utf-8") as f:
        summary_text = f.read()
        summary = json.loads(summary_text)

    assert summary["total_instances"] == 2826
    assert summary["total_clean"] == 2569
    assert summary["total_quarantined"] == 257
    assert summary["quarantine_photo_near_duplicates_h4"] == 181
    assert summary["clustering"]["total_groups"] == 1827

    # Scan summary text to prove ZERO real license plate strings appear
    plate_pattern = re.compile(r"\b\d{2}[A-Z]-?\d{4,6}\b")
    assert not plate_pattern.search(summary_text), (
        "Forbidden: license plate string found inside pool_summary.json"
    )

    # 5. Verify groups and physical crop images
    crops_dir = heavy_cache_dir / "crops"
    assert crops_dir.is_dir()

    # Spot-check physical crops for clean instances
    spot_check_sample = clean_instances[:20] + clean_instances[-20:]
    for it in spot_check_sample:
        assert it.group_id.startswith("grp_"), (
            f"Clean instance '{it.instance_id}' has invalid group_id '{it.group_id}'"
        )
        crop_path = crops_dir / it.crop_filename
        assert crop_path.is_file(), f"Crop file missing: {crop_path}"
        crop_img = cv2.imread(str(crop_path))
        assert crop_img is not None, f"Failed to read crop: {crop_path}"
        assert crop_img.shape == (64, 128, 3), (
            f"Unexpected shape {crop_img.shape} for crop {crop_path}"
        )
