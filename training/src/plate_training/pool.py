"""Candidate pool builder, bounding box extraction, quarantine enforcement, and pHash group clustering."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pyarrow.parquet as pq

from plate_training.cache import ensure_cache_dir
from plate_training.split import (
    compute_phash,
    hamming_distance,
    load_frozen_test_registry,
)

logger = logging.getLogger("plate_training.pool")

VN_PLATE_REGEX = re.compile(r"^\d{2}[A-Z]")


@dataclass
class CandidateInstance:
    """Represents a single extracted plate candidate instance."""

    instance_id: str
    source_split: str
    image_id: int
    target_idx: int
    bbox: list[float]
    photo_sha256: str
    photo_phash: str
    crop_sha256: str
    crop_phash: str
    crop_filename: str
    group_id: str = ""
    quarantined: bool = False
    quarantine_reason: str = ""
    raw_label: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CandidateInstance:
        """Construct CandidateInstance from dictionary."""
        return cls(
            instance_id=str(data["instance_id"]),
            source_split=str(data["source_split"]),
            image_id=int(data["image_id"]),
            target_idx=int(data.get("target_idx", 0)),
            bbox=[float(x) for x in data["bbox"]],
            photo_sha256=str(data["photo_sha256"]).lower(),
            photo_phash=str(data["photo_phash"]),
            crop_sha256=str(data["crop_sha256"]).lower(),
            crop_phash=str(data["crop_phash"]),
            crop_filename=str(data.get("crop_filename", f"{data['instance_id']}.png")),
            group_id=str(data.get("group_id", "")),
            quarantined=bool(data.get("quarantined", False)),
            quarantine_reason=str(data.get("quarantine_reason", "")),
            raw_label=str(data.get("raw_label", "")),
        )


def clamp_bbox(
    bbox: Sequence[float],
    width: int,
    height: int,
    margin: int = 4,
) -> tuple[int, int, int, int]:
    """
    Expand bounding box by margin pixels and clamp to image boundaries [0, W] and [0, H].

    Follows production convention [x1, y1, x2, y2]:
    x1 = max(int(b0) - margin, 0)
    y1 = max(int(b1) - margin, 0)
    x2 = min(int(b2) + margin, width)
    y2 = min(int(b3) + margin, height)
    """
    if len(bbox) != 4:
        raise ValueError(
            f"Expected 4-element bounding box [x1, y1, x2, y2], got {bbox}"
        )

    b0, b1, b2, b3 = bbox
    x1 = max(int(b0) - margin, 0)
    y1 = max(int(b1) - margin, 0)
    x2 = min(int(b2) + margin, width)
    y2 = min(int(b3) + margin, height)

    if x2 <= x1:
        x1 = max(0, min(int(b0), max(width - 1, 0)))
        x2 = min(width, max(x1 + 1, int(b2)))
    if y2 <= y1:
        y1 = max(0, min(int(b1), max(height - 1, 0)))
        y2 = min(height, max(y1 + 1, int(b3)))

    return x1, y1, x2, y2


def extract_normalized_crop(
    image: np.ndarray,
    bbox: Sequence[float],
    margin: int = 4,
    target_size: tuple[int, int] = (128, 64),
) -> tuple[np.ndarray, str, str, tuple[int, int, int, int]]:
    """
    Extract plate crop with margin padding, clamp to image bounds, and resize to target_size.

    Returns:
        (resized_crop_bgr, crop_sha256_hex, crop_phash_hex, clamped_box_coords)
    """
    h, w = image.shape[:2]
    x1, y1, x2, y2 = clamp_bbox(bbox, width=w, height=h, margin=margin)

    cropped = image[y1:y2, x1:x2]
    if cropped.size == 0:
        cropped = image

    resized = cv2.resize(cropped, target_size, interpolation=cv2.INTER_LINEAR)
    success, buf = cv2.imencode(".png", resized)
    if not success:
        raise RuntimeError("Failed to encode crop to PNG format")

    crop_bytes = buf.tobytes()
    crop_sha256 = hashlib.sha256(crop_bytes).hexdigest().lower()
    crop_phash_int = compute_phash(resized)
    crop_phash_hex = f"0x{crop_phash_int:016x}"

    return resized, crop_sha256, crop_phash_hex, (x1, y1, x2, y2)


def evaluate_quarantine_status(
    photo_sha256: str,
    crop_sha256: str,
    photo_phash_int: int,
    crop_phash_int: int,
    registry_entries: Sequence[dict[str, Any]],
    threshold: int = 4,
) -> tuple[bool, str, int, int]:
    """
    Evaluate instance hashes against frozen test registry.

    Quarantine triggered if:
    1. photo_sha256 matches any registry photo sha256.
    2. crop_sha256 matches any registry crop_sha256.
    3. photo pHash Hamming distance <= threshold.
    4. crop pHash Hamming distance <= threshold.

    Returns:
        (is_quarantined, quarantine_reason, min_photo_dist, min_crop_dist)
    """
    norm_photo_sha = photo_sha256.lower()
    norm_crop_sha = crop_sha256.lower()

    min_photo_d = 64
    min_crop_d = 64
    reasons: list[str] = []

    for reg in registry_entries:
        reg_row = reg["row_index"]
        reg_photo_sha = str(reg.get("sha256", "")).lower()
        reg_crop_sha = str(reg.get("crop_sha256", "")).lower()

        reg_photo_phash = reg["phash"]
        if isinstance(reg_photo_phash, str):
            reg_photo_phash = int(reg_photo_phash, 16)

        reg_crop_phash = reg.get("crop_phash")
        if isinstance(reg_crop_phash, str):
            reg_crop_phash = int(reg_crop_phash, 16)

        # 1. Exact Photo SHA-256
        if norm_photo_sha and norm_photo_sha == reg_photo_sha:
            reasons.append(f"Exact photo SHA-256 match with registry row {reg_row}")

        # 2. Exact Crop SHA-256
        if norm_crop_sha and norm_crop_sha == reg_crop_sha:
            reasons.append(f"Exact crop SHA-256 match with registry row {reg_row}")

        # 3. Photo pHash distance
        dp = hamming_distance(photo_phash_int, reg_photo_phash)
        if dp < min_photo_d:
            min_photo_d = dp

        # 4. Crop pHash distance
        if reg_crop_phash is not None:
            dc = hamming_distance(crop_phash_int, reg_crop_phash)
            if dc < min_crop_d:
                min_crop_d = dc

    if min_photo_d <= threshold:
        reasons.append(
            f"Near-duplicate photo pHash match (Hamming distance {min_photo_d} <= {threshold})"
        )
    if min_crop_d <= threshold:
        reasons.append(
            f"Near-duplicate crop pHash match (Hamming distance {min_crop_d} <= {threshold})"
        )

    is_quarantined = len(reasons) > 0
    reason_str = "; ".join(reasons)
    return is_quarantined, reason_str, min_photo_d, min_crop_d


def cluster_instances(
    instances: list[CandidateInstance],
    threshold: int = 4,
) -> list[CandidateInstance]:
    """
    Perform connected-components clustering using 64-bit DCT pHash on non-quarantined instances.

    Each connected component receives a deterministic group_id: f"grp_{min_sha[:16]}"
    where min_sha is the lexicographically smallest photo_sha256 in the component.
    Quarantined instances receive group_id = f"quarantine_{photo_sha256[:16]}".
    """
    clean_indices = [idx for idx, it in enumerate(instances) if not it.quarantined]
    n_clean = len(clean_indices)

    if n_clean == 0:
        for it in instances:
            if it.quarantined:
                it.group_id = f"quarantine_{it.photo_sha256[:16]}"
        return instances

    parsed_hashes: list[int] = [
        int(instances[orig_idx].photo_phash, 16)
        if isinstance(instances[orig_idx].photo_phash, str)
        else int(instances[orig_idx].photo_phash)
        for orig_idx in clean_indices
    ]

    adj: dict[int, list[int]] = defaultdict(list)
    for i in range(n_clean):
        hi = parsed_hashes[i]
        orig_i = clean_indices[i]
        img_id_i = instances[orig_i].image_id
        for j in range(i + 1, n_clean):
            orig_j = clean_indices[j]
            # Same image instances share an edge
            if (
                img_id_i == instances[orig_j].image_id
                or (hi ^ parsed_hashes[j]).bit_count() <= threshold
            ):
                adj[i].append(j)
                adj[j].append(i)

    visited = [False] * n_clean
    for i in range(n_clean):
        if not visited[i]:
            component_nodes: list[int] = []
            queue = deque([i])
            visited[i] = True
            while queue:
                curr = queue.popleft()
                component_nodes.append(curr)
                for neighbor in adj[curr]:
                    if not visited[neighbor]:
                        visited[neighbor] = True
                        queue.append(neighbor)

            comp_instances = [
                instances[clean_indices[node_idx]] for node_idx in component_nodes
            ]
            min_sha = min(it.photo_sha256 for it in comp_instances)
            gid = f"grp_{min_sha[:16]}"
            for it in comp_instances:
                it.group_id = gid

    for it in instances:
        if it.quarantined:
            it.group_id = f"quarantine_{it.photo_sha256[:16]}"

    return instances


def find_parquet_split(cache_dir: Path, split_name: str) -> Path:
    """Find Parquet file for a given split name in cache directory."""
    matches = list(cache_dir.glob(f"{split_name}-*.parquet"))
    if matches:
        return sorted(matches)[0]
    candidate = cache_dir / f"{split_name}.parquet"
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"Parquet file for split '{split_name}' not found in {cache_dir}"
    )


def build_candidate_pool(
    cache_dir: Path | str | None = None,
    registry_path: Path | str | None = None,
    margin: int = 4,
    phash_threshold: int = 4,
    output_pool_path: Path | str | None = None,
    output_summary_path: Path | str | None = None,
    crops_dir: Path | str | None = None,
    splits: Sequence[str] = ("train", "validation"),
    force: bool = False,
    save_crops: bool = True,
) -> tuple[list[CandidateInstance], dict[str, Any]]:
    """
    Build candidate pool from cached Parquet splits with quarantine and group clustering.

    Extracts all Vietnamese plate bounding boxes (matching ^\\d{2}[A-Z]),
    normalizes to 64x128 RGB crops, evaluates quarantine against frozen_test_registry.json,
    clusters non-quarantined instances into deterministic group_id components,
    and writes candidate_pool.json and pool_summary.json.
    """
    resolved_cache = ensure_cache_dir(cache_dir)
    target_pool_path = (
        Path(output_pool_path)
        if output_pool_path
        else (resolved_cache / "candidate_pool.json")
    )
    target_summary_path = (
        Path(output_summary_path)
        if output_summary_path
        else (resolved_cache / "pool_summary.json")
    )
    target_crops_dir = Path(crops_dir) if crops_dir else (resolved_cache / "crops")

    if save_crops:
        target_crops_dir.mkdir(parents=True, exist_ok=True)

    # Check if already generated and non-force
    if (
        not force
        and target_pool_path.is_file()
        and target_summary_path.is_file()
        and target_pool_path.stat().st_size > 0
    ):
        logger.info(
            "Loading existing candidate pool from %s and summary from %s",
            target_pool_path,
            target_summary_path,
        )
        with open(target_pool_path, encoding="utf-8") as f:
            raw_pool = json.load(f)
        with open(target_summary_path, encoding="utf-8") as f:
            cached_summary = json.load(f)
        loaded_instances = [CandidateInstance.from_dict(d) for d in raw_pool]
        return loaded_instances, cached_summary

    registry_entries = load_frozen_test_registry(registry_path)
    logger.info("Loaded %d frozen test registry items", len(registry_entries))

    instances: list[CandidateInstance] = []
    split_stats: dict[str, dict[str, int]] = {}

    for split_name in splits:
        parquet_file = find_parquet_split(resolved_cache, split_name)
        logger.info("Processing split '%s' from %s...", split_name, parquet_file.name)
        table = pq.read_table(str(parquet_file))
        n_rows = len(table)

        split_total_instances = 0
        split_quarantined = 0
        split_photo_nd = 0

        for row_idx in range(n_rows):
            targets = table["target"][row_idx].as_py() or []
            bbox_list = table["bbox"][row_idx].as_py() or []
            image_id = int(table["image_id"][row_idx].as_py())

            # Find matching VN targets
            matching_pairs: list[tuple[int, str, list[float]]] = []
            for t_idx, (t_val, bbox) in enumerate(
                zip(targets, bbox_list, strict=False)
            ):
                t_str = str(t_val).strip() if t_val is not None else ""
                if VN_PLATE_REGEX.match(t_str) and len(bbox) == 4:
                    matching_pairs.append((t_idx, t_str, bbox))

            if not matching_pairs:
                continue

            raw_bytes = table["image"][row_idx].as_py()["bytes"]
            photo_sha256 = hashlib.sha256(raw_bytes).hexdigest().lower()
            arr = np.frombuffer(raw_bytes, np.uint8)
            img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img_bgr is None:
                raise RuntimeError(
                    f"Failed to decode image at split '{split_name}', row {row_idx}"
                )

            img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
            photo_phash_int = compute_phash(img_gray)
            photo_phash_hex = f"0x{photo_phash_int:016x}"

            for t_idx, raw_label, bbox in matching_pairs:
                split_total_instances += 1
                instance_id = f"inst_{split_name}_{image_id}_{t_idx}"
                crop_filename = f"{instance_id}.png"

                resized_bgr, crop_sha256, crop_phash_hex, _clamped = (
                    extract_normalized_crop(
                        img_bgr, bbox, margin=margin, target_size=(128, 64)
                    )
                )

                if save_crops:
                    crop_dest = target_crops_dir / crop_filename
                    if force or not crop_dest.is_file():
                        cv2.imwrite(str(crop_dest), resized_bgr)

                crop_phash_int = int(crop_phash_hex, 16)
                is_q, q_reason, min_p, _min_c = evaluate_quarantine_status(
                    photo_sha256=photo_sha256,
                    crop_sha256=crop_sha256,
                    photo_phash_int=photo_phash_int,
                    crop_phash_int=crop_phash_int,
                    registry_entries=registry_entries,
                    threshold=phash_threshold,
                )

                if is_q:
                    split_quarantined += 1
                if min_p <= phash_threshold:
                    split_photo_nd += 1

                inst = CandidateInstance(
                    instance_id=instance_id,
                    source_split=split_name,
                    image_id=image_id,
                    target_idx=t_idx,
                    bbox=[float(x) for x in bbox],
                    photo_sha256=photo_sha256,
                    photo_phash=photo_phash_hex,
                    crop_sha256=crop_sha256,
                    crop_phash=crop_phash_hex,
                    crop_filename=crop_filename,
                    group_id="",
                    quarantined=is_q,
                    quarantine_reason=q_reason,
                    raw_label=raw_label,
                )
                instances.append(inst)

        split_stats[split_name] = {
            "total_instances": split_total_instances,
            "quarantined": split_quarantined,
            "clean": split_total_instances - split_quarantined,
            "quarantine_photo_near_duplicates_h4": split_photo_nd,
        }

    # Connected-components group clustering
    instances = cluster_instances(instances, threshold=phash_threshold)

    # Compute aggregate summary statistics (0 plate strings)
    total_inst = len(instances)
    total_quarantined = sum(1 for it in instances if it.quarantined)
    total_clean = total_inst - total_quarantined

    photo_nd_total = sum(
        stats["quarantine_photo_near_duplicates_h4"] for stats in split_stats.values()
    )

    clean_groups = {it.group_id for it in instances if not it.quarantined}
    group_sizes: dict[str, int] = defaultdict(int)
    for it in instances:
        if not it.quarantined:
            group_sizes[it.group_id] += 1

    singletons = sum(1 for sz in group_sizes.values() if sz == 1)
    multi_instance_groups = sum(1 for sz in group_sizes.values() if sz > 1)

    crop_nd_count = sum(
        1
        for it in instances
        if it.quarantined and "crop pHash match" in it.quarantine_reason
    )
    photo_sha_matches = sum(
        1
        for it in instances
        if it.quarantined and "photo SHA-256 match" in it.quarantine_reason
    )
    crop_sha_matches = sum(
        1
        for it in instances
        if it.quarantined and "crop SHA-256 match" in it.quarantine_reason
    )

    summary: dict[str, Any] = {
        "total_instances": total_inst,
        "total_quarantined": total_quarantined,
        "total_clean": total_clean,
        "quarantine_photo_near_duplicates_h4": photo_nd_total,
        "quarantine_breakdown": {
            "photo_phash_near_duplicates_h4": photo_nd_total,
            "crop_phash_near_duplicates_h4": crop_nd_count,
            "photo_sha256_exact_matches": photo_sha_matches,
            "crop_sha256_exact_matches": crop_sha_matches,
        },
        "splits": split_stats,
        "clustering": {
            "phash_threshold": phash_threshold,
            "total_groups": len(clean_groups),
            "singleton_groups": singletons,
            "multi_instance_groups": multi_instance_groups,
        },
        "margin_px": margin,
        "target_resolution": [128, 64],
    }

    # Save to disk
    target_pool_path.parent.mkdir(parents=True, exist_ok=True)
    with open(target_pool_path, "w", encoding="utf-8") as f:
        json.dump([it.to_dict() for it in instances], f, indent=2)

    with open(target_summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    logger.info(
        "Candidate pool successfully built: %d instances (%d clean, %d quarantined). "
        "Saved to %s and %s",
        total_inst,
        total_clean,
        total_quarantined,
        target_pool_path,
        target_summary_path,
    )

    return instances, summary
