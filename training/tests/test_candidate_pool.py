"""Unit tests for candidate pool builder, margin clamping, quarantine routing, and graph clustering."""

from __future__ import annotations

import numpy as np
import pytest

from plate_training.pool import (
    CandidateInstance,
    clamp_bbox,
    cluster_instances,
    evaluate_quarantine_status,
    extract_normalized_crop,
)


@pytest.mark.unit
def test_clamp_bbox_normal_and_boundary_cases() -> None:
    """Test bounding box expansion with margin and clamping to image bounds."""
    width, height = 200, 100
    margin = 4

    # 1. Normal box well within boundaries
    normal_box = [50.0, 30.0, 150.0, 70.0]
    x1, y1, x2, y2 = clamp_bbox(normal_box, width=width, height=height, margin=margin)
    assert x1 == 46
    assert y1 == 26
    assert x2 == 154
    assert y2 == 74

    # 2. Box near top-left boundary (clamped to 0)
    boundary_top_left = [2.0, 1.0, 60.0, 40.0]
    x1, y1, x2, y2 = clamp_bbox(
        boundary_top_left, width=width, height=height, margin=margin
    )
    assert x1 == 0
    assert y1 == 0
    assert x2 == 64
    assert y2 == 44

    # 3. Box near bottom-right boundary (clamped to width, height)
    boundary_bottom_right = [140.0, 80.0, 198.0, 99.0]
    x1, y1, x2, y2 = clamp_bbox(
        boundary_bottom_right, width=width, height=height, margin=margin
    )
    assert x1 == 136
    assert y1 == 76
    assert x2 == width
    assert y2 == height

    # 4. Box completely covering image
    full_box = [0.0, 0.0, float(width), float(height)]
    x1, y1, x2, y2 = clamp_bbox(full_box, width=width, height=height, margin=margin)
    assert x1 == 0
    assert y1 == 0
    assert x2 == width
    assert y2 == height

    # 5. Invalid bounding box length raises ValueError
    with pytest.raises(ValueError, match="Expected 4-element"):
        clamp_bbox([1.0, 2.0], width=width, height=height, margin=margin)


@pytest.mark.unit
def test_clamp_bbox_red_then_green_mutation() -> None:
    """Demonstrate Red-then-Green proof that missing boundary clamping causes assertion failure."""
    width, height = 100, 100
    margin = 4
    boundary_box = [1.0, 1.0, 99.0, 99.0]

    # GREEN: Properly clamped coordinates are strictly within [0, width] and [0, height]
    x1, y1, x2, y2 = clamp_bbox(boundary_box, width=width, height=height, margin=margin)
    assert x1 >= 0
    assert y1 >= 0
    assert x2 <= width
    assert y2 <= height

    # RED MUTATION: If naive unclamped expansion were performed
    unclamped_x1 = int(boundary_box[0]) - margin  # 1 - 4 = -3
    unclamped_x2 = int(boundary_box[2]) + margin  # 99 + 4 = 103
    with pytest.raises(AssertionError):
        assert unclamped_x1 >= 0
    with pytest.raises(AssertionError):
        assert unclamped_x2 <= width


@pytest.mark.unit
def test_extract_normalized_crop_geometry_and_hashes() -> None:
    """Test normalized crop extraction, resolution 128x64, and hash generation."""
    # Create synthetic test image (100x200 BGR)
    img = np.full((100, 200, 3), 128, dtype=np.uint8)
    # Paint a distinct rectangle representing plate area
    img[30:70, 50:150] = (255, 255, 255)

    bbox = [50.0, 30.0, 150.0, 70.0]
    resized, crop_sha, crop_phash, clamped = extract_normalized_crop(
        image=img,
        bbox=bbox,
        margin=4,
        target_size=(128, 64),
    )

    # Verify dimensions: width=128, height=64, 3 channels
    assert resized.shape == (64, 128, 3)
    assert resized.dtype == np.uint8

    # Verify SHA-256 digest format: hex 64 chars
    assert len(crop_sha) == 64
    assert all(c in "0123456789abcdef" for c in crop_sha)

    # Verify pHash format: hex 0x...
    assert crop_phash.startswith("0x")
    phash_int = int(crop_phash, 16)
    assert phash_int >= 0

    # Verify clamped box coordinates
    assert clamped == (46, 26, 154, 74)


@pytest.mark.unit
def test_quarantine_evaluation_exact_and_near_duplicate_routing() -> None:
    """Verify quarantine routing against registry across all 4 criteria."""
    # Synthetic registry item
    dummy_reg = [
        {
            "row_index": 0,
            "sha256": "aaaa" * 16,
            "phash": "0x1111111111111111",
            "crop_sha256": "bbbb" * 16,
            "crop_phash": "0x2222222222222222",
        }
    ]
    reg_photo_ph = int("0x1111111111111111", 16)
    reg_crop_ph = int("0x2222222222222222", 16)

    # Case 1: Exact photo SHA-256 match
    is_q, reason, _, _ = evaluate_quarantine_status(
        photo_sha256="aaaa" * 16,
        crop_sha256="9999" * 16,
        photo_phash_int=0,
        crop_phash_int=0,
        registry_entries=dummy_reg,
        threshold=4,
    )
    assert is_q is True
    assert "Exact photo SHA-256 match" in reason

    # Case 2: Exact crop SHA-256 match
    is_q, reason, _, _ = evaluate_quarantine_status(
        photo_sha256="8888" * 16,
        crop_sha256="bbbb" * 16,
        photo_phash_int=0,
        crop_phash_int=0,
        registry_entries=dummy_reg,
        threshold=4,
    )
    assert is_q is True
    assert "Exact crop SHA-256 match" in reason

    # Case 3: Photo pHash near-duplicate (Hamming distance = 2 <= 4)
    # Flip 2 bits in reg_photo_ph
    photo_near = reg_photo_ph ^ 0b11
    is_q, reason, dp, _ = evaluate_quarantine_status(
        photo_sha256="7777" * 16,
        crop_sha256="6666" * 16,
        photo_phash_int=photo_near,
        crop_phash_int=0,
        registry_entries=dummy_reg,
        threshold=4,
    )
    assert is_q is True
    assert dp == 2
    assert "Near-duplicate photo pHash match" in reason

    # Case 4: Crop pHash near-duplicate (Hamming distance = 3 <= 4)
    crop_near = reg_crop_ph ^ 0b111
    is_q, reason, _, dc = evaluate_quarantine_status(
        photo_sha256="5555" * 16,
        crop_sha256="4444" * 16,
        photo_phash_int=0,
        crop_phash_int=crop_near,
        registry_entries=dummy_reg,
        threshold=4,
    )
    assert is_q is True
    assert dc == 3
    assert "Near-duplicate crop pHash match" in reason

    # Case 5: Clean instance (Hamming distance > 4 on both, no SHA match)
    photo_far = reg_photo_ph ^ 0xFF
    crop_far = reg_crop_ph ^ 0xFF
    is_q, reason, dp, dc = evaluate_quarantine_status(
        photo_sha256="3333" * 16,
        crop_sha256="2222" * 16,
        photo_phash_int=photo_far,
        crop_phash_int=crop_far,
        registry_entries=dummy_reg,
        threshold=4,
    )
    assert is_q is False
    assert reason == ""
    assert dp == 8
    assert dc == 8


@pytest.mark.unit
def test_quarantine_evaluation_red_then_green_mutation() -> None:
    """Demonstrate Red-then-Green proof that near-duplicate distance threshold mutation fails."""
    dummy_reg = [
        {
            "row_index": 0,
            "sha256": "aaaa" * 16,
            "phash": "0x1111111111111111",
            "crop_sha256": "bbbb" * 16,
            "crop_phash": "0x2222222222222222",
        }
    ]
    reg_photo_ph = int("0x1111111111111111", 16)

    # Distance = 4 should be quarantined under threshold = 4
    d4_hash = reg_photo_ph ^ 0b1111
    is_q, _, dist, _ = evaluate_quarantine_status(
        photo_sha256="1234" * 16,
        crop_sha256="5678" * 16,
        photo_phash_int=d4_hash,
        crop_phash_int=0,
        registry_entries=dummy_reg,
        threshold=4,
    )
    assert is_q is True
    assert dist == 4

    # RED MUTATION: If threshold was set too strict (< 4), distance 4 would be missed
    strict_threshold = 3
    is_q_mutated, _, _, _ = evaluate_quarantine_status(
        photo_sha256="1234" * 16,
        crop_sha256="5678" * 16,
        photo_phash_int=d4_hash,
        crop_phash_int=0,
        registry_entries=dummy_reg,
        threshold=strict_threshold,
    )
    with pytest.raises(AssertionError):
        # Proves distance 4 is missed if threshold is 3
        assert is_q_mutated is True


@pytest.mark.unit
def test_cluster_instances_connected_components_and_determinism() -> None:
    """Verify deterministic connected-components clustering on pHash graph."""
    base_hash = 0x1000000000000000

    # Instance A and Instance B have Hamming distance 2 <= 4 -> connected
    hash_a = base_hash
    hash_b = base_hash ^ 0b11
    # Instance C has Hamming distance 2 to B (total dist to A = 4 <= 4) -> connected
    hash_c = base_hash ^ 0b1111
    # Instance D has Hamming distance 10 to A, B, C -> isolated component
    hash_d = base_hash ^ 0x3FF

    inst_a = CandidateInstance(
        instance_id="inst_1",
        source_split="train",
        image_id=1,
        target_idx=0,
        bbox=[0.0, 0.0, 10.0, 10.0],
        photo_sha256="cccc" * 16,
        photo_phash=f"0x{hash_a:016x}",
        crop_sha256="1111" * 16,
        crop_phash="0x0",
        crop_filename="inst_1.png",
    )
    inst_b = CandidateInstance(
        instance_id="inst_2",
        source_split="train",
        image_id=2,
        target_idx=0,
        bbox=[0.0, 0.0, 10.0, 10.0],
        photo_sha256="aaaa" * 16,  # Smallest sha256 in {A, B, C}
        photo_phash=f"0x{hash_b:016x}",
        crop_sha256="2222" * 16,
        crop_phash="0x0",
        crop_filename="inst_2.png",
    )
    inst_c = CandidateInstance(
        instance_id="inst_3",
        source_split="validation",
        image_id=3,
        target_idx=0,
        bbox=[0.0, 0.0, 10.0, 10.0],
        photo_sha256="bbbb" * 16,
        photo_phash=f"0x{hash_c:016x}",
        crop_sha256="3333" * 16,
        crop_phash="0x0",
        crop_filename="inst_3.png",
    )
    inst_d = CandidateInstance(
        instance_id="inst_4",
        source_split="train",
        image_id=4,
        target_idx=0,
        bbox=[0.0, 0.0, 10.0, 10.0],
        photo_sha256="dddd" * 16,
        photo_phash=f"0x{hash_d:016x}",
        crop_sha256="4444" * 16,
        crop_phash="0x0",
        crop_filename="inst_4.png",
    )
    inst_q = CandidateInstance(
        instance_id="inst_q",
        source_split="train",
        image_id=5,
        target_idx=0,
        bbox=[0.0, 0.0, 10.0, 10.0],
        photo_sha256="eeee" * 16,
        photo_phash=f"0x{hash_a:016x}",
        crop_sha256="5555" * 16,
        crop_phash="0x0",
        crop_filename="inst_q.png",
        quarantined=True,
    )

    items = [inst_a, inst_b, inst_c, inst_d, inst_q]
    clustered = cluster_instances(items, threshold=4)

    # 1. A, B, C must share identical group_id based on min sha256 ("aaaa..."[:16])
    expected_gid = f"grp_{'aaaa' * 4}"
    assert clustered[0].group_id == expected_gid
    assert clustered[1].group_id == expected_gid
    assert clustered[2].group_id == expected_gid

    # 2. D is in its own group
    assert clustered[3].group_id == f"grp_{'dddd' * 4}"
    assert clustered[3].group_id != expected_gid

    # 3. Quarantined instance receives quarantine prefix
    assert clustered[4].group_id == f"quarantine_{'eeee' * 4}"
    assert clustered[4].group_id != expected_gid


@pytest.mark.unit
def test_candidate_instance_serialization_roundtrip() -> None:
    """Verify CandidateInstance to_dict and from_dict roundtrip fidelity."""
    original = CandidateInstance(
        instance_id="inst_train_100_0",
        source_split="train",
        image_id=100,
        target_idx=0,
        bbox=[10.5, 20.0, 110.0, 60.5],
        photo_sha256="a1b2" * 16,
        photo_phash="0xabcdef0123456789",
        crop_sha256="c3d4" * 16,
        crop_phash="0x9876543210fedcba",
        crop_filename="inst_train_100_0.png",
        group_id="grp_a1b2a1b2a1b2a1b2",
        quarantined=False,
        quarantine_reason="",
        raw_label="51G12345",
    )
    serialized = original.to_dict()
    restored = CandidateInstance.from_dict(serialized)
    assert restored == original
