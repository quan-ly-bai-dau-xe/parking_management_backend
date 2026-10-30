"""Split validation, data leakage detection (Exact SHA-256, pHash DCT), and label collision checking."""

import json
from collections import defaultdict
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from plate_training.cache import get_benchmark_labels_path
from plate_training.manifest import ManifestItem
from plate_training.normalization import normalize_plate


class DataLeakageError(ValueError):
    """Raised when data leakage between dataset splits is detected."""


def compute_phash(image_input: str | Path | np.ndarray) -> int:
    """
    Compute 64-bit Discrete Cosine Transform perceptual hash (pHash).

    Resizes to 32x32 grayscale, computes 2D DCT via OpenCV, takes top-left 8x8 block,
    and generates a 64-bit integer based on median thresholding.
    """
    if isinstance(image_input, (str, Path)):
        path_str = str(image_input)
        img = cv2.imread(path_str, cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise FileNotFoundError(f"Cannot read image at {path_str}")
    elif isinstance(image_input, np.ndarray):
        if len(image_input.shape) == 3:
            img = cv2.cvtColor(image_input, cv2.COLOR_RGB2GRAY)
        elif len(image_input.shape) == 2:
            img = image_input
        else:
            raise ValueError(f"Invalid array shape for image: {image_input.shape}")
    else:
        raise TypeError(f"Unsupported image input type: {type(image_input)}")

    resized = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(np.float32(resized))
    dct_low = dct[:8, :8]
    med = float(np.median(dct_low))
    bits = (dct_low > med).flatten()
    h = 0
    for b in bits:
        h = (h << 1) | int(b)
    return h


def hamming_distance(hash1: int, hash2: int) -> int:
    """Calculate bitwise Hamming distance between two 64-bit hashes."""
    return (hash1 ^ hash2).bit_count()


def detect_exact_duplicates(
    items: list[ManifestItem],
) -> list[tuple[ManifestItem, ManifestItem]]:
    """
    Detect exact SHA-256 duplicate images across different splits.
    Returns list of duplicate pairs across different splits.
    """
    sha_map: dict[str, list[ManifestItem]] = defaultdict(list)
    for item in items:
        sha_map[item.sha256.lower()].append(item)

    cross_split_duplicates: list[tuple[ManifestItem, ManifestItem]] = []
    for _sha, group in sha_map.items():
        splits = {item.split for item in group}
        if len(splits) > 1:
            for i in range(len(group)):
                for j in range(i + 1, len(group)):
                    if group[i].split != group[j].split:
                        cross_split_duplicates.append((group[i], group[j]))

    return cross_split_duplicates


def get_default_registry_path() -> Path:
    """Resolve path to default frozen test registry JSON file."""
    candidate = (
        Path(__file__).resolve().parent.parent.parent
        / "data"
        / "frozen_test_registry.json"
    )
    if candidate.is_file():
        return candidate
    return Path("training/data/frozen_test_registry.json").resolve()


def load_frozen_test_registry(
    registry_path: Path | str | None = None,
) -> list[dict[str, Any]]:
    """
    Load frozen test registry JSON file.
    Returns list of entries with strictly 5 image and crop fields:
      - row_index: int
      - sha256: str hex 64 (full photo)
      - phash: int (full photo 64-bit DCT pHash)
      - crop_sha256: str hex 64 (detector plate crop)
      - crop_phash: int (detector plate crop 64-bit DCT pHash)
    """
    path = Path(registry_path) if registry_path else get_default_registry_path()
    if not path.is_file():
        raise FileNotFoundError(f"Frozen test registry not found at {path}")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    parsed: list[dict[str, Any]] = []
    for entry in data:
        phash_val = entry["phash"]
        phash_int = int(phash_val, 16) if isinstance(phash_val, str) else int(phash_val)
        parsed_entry: dict[str, Any] = {
            "row_index": int(entry["row_index"]),
            "sha256": str(entry["sha256"]).lower(),
            "phash": phash_int,
        }

        # Detector crop extensions (strictly hash-only, 0 plate strings, 0 image bytes)
        if "crop_sha256" in entry and entry["crop_sha256"] is not None:
            parsed_entry["crop_sha256"] = str(entry["crop_sha256"]).lower()

        if "crop_phash" in entry and entry["crop_phash"] is not None:
            c_phash = entry["crop_phash"]
            parsed_entry["crop_phash"] = (
                int(c_phash, 16) if isinstance(c_phash, str) else int(c_phash)
            )

        parsed.append(parsed_entry)
    return parsed


def load_benchmark_labels(
    benchmark_labels_path: Path | str | None = None,
) -> dict[str, list[int]]:
    """
    Load benchmark reference plate strings from local cache or explicit path.

    Reads benchmark_322_labels.json (prepared by prepare-heavy-inputs in PLATE_TRAINING_CACHE).
    Returns mapping from normalized plate text to list of benchmark row_indices.
    Returns empty dict if no benchmark labels file is found.
    """
    path = (
        Path(benchmark_labels_path)
        if benchmark_labels_path
        else get_benchmark_labels_path()
    )
    if not path.is_file():
        return {}

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    mapping: dict[str, list[int]] = defaultdict(list)
    if isinstance(data, list):
        for idx, entry in enumerate(data):
            if isinstance(entry, dict):
                p_text = entry.get("plate_text", "")
                r_idx = entry.get("row_index", idx)
            elif isinstance(entry, str):
                p_text = entry
                r_idx = idx
            else:
                continue
            norm = normalize_plate(str(p_text))
            if norm:
                mapping[norm].append(int(r_idx))
    elif isinstance(data, dict):
        for k, v in data.items():
            norm = normalize_plate(str(k))
            if norm:
                if isinstance(v, list):
                    mapping[norm].extend(int(x) for x in v)
                elif isinstance(v, int):
                    mapping[norm].append(v)
                else:
                    mapping[norm].append(0)
    return dict(mapping)


def check_label_collisions(
    items: list[ManifestItem],
    benchmark_labels_path: Path | str | None = None,
    benchmark_labels: dict[str, list[int]] | None = None,
    cross_capture_groups: Sequence[str] | set[str] | None = None,
    registry_path: Path | str | None = None,
    registry_entries: list[dict[str, Any]] | None = None,
) -> list[str]:
    """
    Check for plate label collisions between non-frozen items and benchmark reference plates.

    Reads the 322 reference plate strings from local-only benchmark_322_labels.json
    in git-ignored PLATE_TRAINING_CACHE (or explicit path / dictionary) rather than storing
    reversible label hashes in the committed frozen test registry.

    If a match is found and the item's group_id is NOT in cross_capture_groups:
    Records a warning string into label_collision_warnings.

    NOTE: This is strictly a WARNING check, NOT a hard error (never raises DataLeakageError).
    Legitimate public vehicles or cross-session captures may share plate numbers.

    Args:
        items: List of ManifestItem objects to validate.
        benchmark_labels_path: Optional path to benchmark labels JSON file.
        benchmark_labels: Optional pre-loaded mapping of normalized plate string -> row indices.
        cross_capture_groups: Whitelist of vehicle group_ids permitted to have cross-capture collisions.
        registry_path: Deprecated argument kept for backward compatibility.
        registry_entries: Deprecated argument kept for backward compatibility.

    Returns:
        List of human-readable warning strings for manual review.
    """
    if benchmark_labels is None:
        benchmark_labels = load_benchmark_labels(benchmark_labels_path)

    if not benchmark_labels:
        return []

    allowed_groups = set(cross_capture_groups) if cross_capture_groups else set()
    warnings: list[str] = []

    non_test_items = [it for it in items if it.split != "frozen-test"]
    for it in non_test_items:
        norm_text = normalize_plate(it.plate_text)
        if not norm_text:
            continue
        if norm_text in benchmark_labels:
            gid = str(it.group_id).strip() if it.group_id else ""
            if gid not in allowed_groups:
                matched_rows = benchmark_labels[norm_text]
                row_str = (
                    f"row {matched_rows[0]}"
                    if len(matched_rows) == 1
                    else f"rows {matched_rows}"
                )
                warning_msg = (
                    f"Label collision warning: item '{it.image_path}' in split '{it.split}' "
                    f"(group_id='{it.group_id}') has normalized plate label matching "
                    f"frozen_test_registry / benchmark reference {row_str} ('{norm_text}'). "
                    f"Requires manual review (not in declared cross_capture_groups)."
                )
                warnings.append(warning_msg)

    return warnings


def check_registry_leakage(
    items: list[ManifestItem],
    registry_path: Path | str | None = None,
    threshold: int = 4,
    image_hashes: dict[str, int] | None = None,
    crop_hashes: dict[str, int] | None = None,
    check_labels: bool = False,
    cross_capture_groups: Sequence[str] | set[str] | None = None,
    benchmark_labels_path: Path | str | None = None,
) -> list[str]:
    """
    Reject any manifest entry (in any split other than 'frozen-test') whose:
    1. sha256 matches full photo sha256 in frozen_test_registry.json.
    2. sha256 matches crop_sha256 in frozen_test_registry.json.
    3. perceptual hash (phash) is within Hamming threshold of any full photo phash in registry.
    4. perceptual hash (phash or crop_phash) is within Hamming threshold of any crop_phash in registry.

    Optionally runs label collision checks if check_labels=True.

    Raises DataLeakageError if leakage is detected.
    Returns label_collision_warnings (list[str]).
    """
    registry_entries = load_frozen_test_registry(registry_path)

    # 1. Exact SHA-256 lookup tables
    photo_shas: dict[str, int] = {
        entry["sha256"]: entry["row_index"]
        for entry in registry_entries
        if "sha256" in entry
    }
    crop_shas: dict[str, int] = {
        entry["crop_sha256"]: entry["row_index"]
        for entry in registry_entries
        if "crop_sha256" in entry and entry["crop_sha256"]
    }

    non_test_items = [it for it in items if it.split != "frozen-test"]

    # 1A. Exact SHA-256 match against full photo
    for it in non_test_items:
        it_sha = it.sha256.lower()
        if it_sha in photo_shas:
            reg_row = photo_shas[it_sha]
            raise DataLeakageError(
                f"Exact SHA-256 duplicate leakage detected: item '{it.image_path}' "
                f"in split '{it.split}' matches frozen_test_registry row {reg_row} "
                f"(SHA-256: {it_sha})"
            )

    # 1B. Exact SHA-256 match against detector crop
    for it in non_test_items:
        it_sha = it.sha256.lower()
        if it_sha in crop_shas:
            reg_row = crop_shas[it_sha]
            raise DataLeakageError(
                f"Exact crop SHA-256 duplicate leakage detected: item '{it.image_path}' "
                f"in split '{it.split}' matches frozen_test_registry row {reg_row} "
                f"crop SHA-256: {it_sha}"
            )

    # 2. Near-duplicate pHash against registry (if image_hashes provided)
    if image_hashes:
        for it in non_test_items:
            if it.image_path in image_hashes:
                it_phash = image_hashes[it.image_path]

                # 2A. Near-duplicate check against full photo pHash
                for entry in registry_entries:
                    dist = hamming_distance(it_phash, entry["phash"])
                    if dist <= threshold:
                        raise DataLeakageError(
                            f"Near-duplicate pHash leakage detected with frozen test registry: item '{it.image_path}' "
                            f"in split '{it.split}' matches registry row {entry['row_index']} "
                            f"with Hamming distance {dist} <= {threshold}"
                        )

                # 2B. Near-duplicate check against detector crop pHash
                for entry in registry_entries:
                    crop_ph = entry.get("crop_phash")
                    if crop_ph is not None:
                        dist_crop = hamming_distance(it_phash, crop_ph)
                        if dist_crop <= threshold:
                            raise DataLeakageError(
                                f"Near-duplicate crop pHash leakage detected with frozen test registry: item '{it.image_path}' "
                                f"in split '{it.split}' matches registry row {entry['row_index']} "
                                f"crop with Hamming distance {dist_crop} <= {threshold}"
                            )

    # 2C. Explicit crop_hashes if provided separately
    if crop_hashes:
        for it in non_test_items:
            if it.image_path in crop_hashes:
                it_crop_phash = crop_hashes[it.image_path]
                for entry in registry_entries:
                    crop_ph = entry.get("crop_phash")
                    if crop_ph is not None:
                        dist_crop = hamming_distance(it_crop_phash, crop_ph)
                        if dist_crop <= threshold:
                            raise DataLeakageError(
                                f"Near-duplicate crop pHash leakage detected with frozen test registry: item '{it.image_path}' "
                                f"in split '{it.split}' matches registry row {entry['row_index']} "
                                f"crop with Hamming distance {dist_crop} <= {threshold}"
                            )

    # 3. Label collision check (warning only, if enabled)
    warnings: list[str] = []
    if check_labels:
        warnings = check_label_collisions(
            items=items,
            benchmark_labels_path=benchmark_labels_path,
            cross_capture_groups=cross_capture_groups,
        )

    return warnings


def detect_group_leakage(
    items: list[ManifestItem],
    require_group_id: bool = True,
) -> None:
    """
    Verify vehicle group_id disjointness across splits.
    - If require_group_id is True, raises DataLeakageError if any item in 'train' or 'val' lacks group_id.
    - Raises DataLeakageError if the same group_id appears in more than one distinct split.
    """
    group_to_splits: dict[str, set[str]] = defaultdict(set)
    group_to_paths: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for it in items:
        if (
            require_group_id
            and it.split in ("train", "val")
            and (not it.group_id or not str(it.group_id).strip())
        ):
            raise DataLeakageError(
                f"Missing mandatory group_id for item '{it.image_path}' in split '{it.split}'. "
                "All train and val items must specify a group_id."
            )
        if it.group_id and str(it.group_id).strip():
            gid = str(it.group_id).strip()
            group_to_splits[gid].add(it.split)
            group_to_paths[gid].append((it.split, it.image_path))

    for gid, splits in group_to_splits.items():
        if len(splits) > 1:
            examples = group_to_paths[gid][:4]
            ex_str = ", ".join(f"'{s}': {p}" for s, p in examples)
            raise DataLeakageError(
                f"Group ID cross-split leakage detected: group_id '{gid}' appears in multiple splits "
                f"{sorted(splits)} ({ex_str})"
            )


def detect_near_duplicates(
    items: list[ManifestItem],
    base_dir: str | Path | None = None,
    threshold: int = 4,
    image_arrays: dict[str, np.ndarray] | None = None,
    allow_missing_files: bool = False,
) -> list[tuple[ManifestItem, ManifestItem, int]]:
    """
    Detect perceptual near-duplicate images across ALL distinct split pairs
    (train vs val, train vs frozen-test, val vs frozen-test) using 2D DCT pHash.

    If allow_missing_files is False (default, fail-closed) and an image file is not found
    on disk nor in image_arrays, raises FileNotFoundError.
    """
    root = Path(base_dir) if base_dir else Path(".")
    hashes: dict[str, int] = {}

    for item in items:
        if image_arrays and item.image_path in image_arrays:
            hashes[item.image_path] = compute_phash(image_arrays[item.image_path])
        else:
            img_path = root / item.image_path
            if img_path.is_file():
                hashes[item.image_path] = compute_phash(img_path)
            elif not allow_missing_files:
                raise FileNotFoundError(
                    f"Image not found at {img_path}. Fail-closed leakage check "
                    "requires all image files to exist on disk."
                )

    # Group items by split
    items_by_split: dict[str, list[ManifestItem]] = defaultdict(list)
    for it in items:
        if it.image_path in hashes:
            items_by_split[it.split].append(it)

    splits = sorted(items_by_split.keys())
    near_duplicates: list[tuple[ManifestItem, ManifestItem, int]] = []

    # Compare across all distinct split pairs (splits[i] vs splits[j], i < j)
    for i in range(len(splits)):
        for j in range(i + 1, len(splits)):
            split_a = splits[i]
            split_b = splits[j]
            for item_a in items_by_split[split_a]:
                hash_a = hashes[item_a.image_path]
                for item_b in items_by_split[split_b]:
                    hash_b = hashes[item_b.image_path]
                    dist = hamming_distance(hash_a, hash_b)
                    if dist <= threshold:
                        near_duplicates.append((item_a, item_b, dist))

    return near_duplicates


def validate_splits(
    items: list[ManifestItem],
    base_dir: str | Path | None = None,
    check_phash: bool = True,
    phash_threshold: int = 4,
    image_arrays: dict[str, np.ndarray] | None = None,
    registry_path: str | Path | None = None,
    allow_missing_files: bool = False,
    require_group_id: bool = True,
    check_registry: bool = True,
    check_labels: bool = True,
    cross_capture_groups: Sequence[str] | set[str] | None = None,
    benchmark_labels_path: str | Path | None = None,
) -> list[str]:
    """
    Validate dataset splits for zero leakage under fail-closed guarantees.

    Pipeline order:
    1. Internal exact SHA-256 duplicates across distinct splits.
    2. Group ID cross-split disjointness and mandatory field check.
    3. Frozen test registry external leakage check (photo SHA-256, crop SHA-256, photo pHash, crop pHash).
    4. Cross-split perceptual near-duplicate check across all distinct split pairs.
    5. External label collision warning check (non-blocking quality inspection).

    Returns:
        List of label collision warning strings (empty list if none detected).
    """
    # Step 1: Internal exact SHA-256 duplicates across splits
    exact_duplicates = detect_exact_duplicates(items)
    if exact_duplicates:
        first = exact_duplicates[0]
        msg = (
            f"Exact SHA-256 duplicate leakage detected between splits '{first[0].split}' "
            f"and '{first[1].split}' (SHA-256: {first[0].sha256}, "
            f"paths: {first[0].image_path} <-> {first[1].image_path})"
        )
        raise DataLeakageError(msg)

    # Step 2: Group ID cross-split leakage
    detect_group_leakage(items, require_group_id=require_group_id)

    # Compute image hashes if checking pHash or checking registry pHash
    computed_hashes: dict[str, int] = {}
    if check_phash or (
        check_registry and (base_dir is not None or image_arrays is not None)
    ):
        root = Path(base_dir) if base_dir else Path(".")
        for item in items:
            if image_arrays and item.image_path in image_arrays:
                computed_hashes[item.image_path] = compute_phash(
                    image_arrays[item.image_path]
                )
            else:
                img_path = root / item.image_path
                if img_path.is_file():
                    computed_hashes[item.image_path] = compute_phash(img_path)
                elif not allow_missing_files:
                    raise FileNotFoundError(
                        f"Image not found at {img_path}. Fail-closed leakage check "
                        "requires all image files to exist on disk."
                    )

    # Step 3: External frozen test registry leakage check (Hard error on match)
    if check_registry:
        check_registry_leakage(
            items,
            registry_path=registry_path,
            threshold=phash_threshold,
            image_hashes=computed_hashes if computed_hashes else None,
            check_labels=False,  # Checked explicitly in Step 5
        )

    # Step 4: Cross-split near-duplicate pHash check (Hard error on match)
    if check_phash:
        near_duplicates = detect_near_duplicates(
            items,
            base_dir=base_dir,
            threshold=phash_threshold,
            image_arrays=image_arrays,
            allow_missing_files=allow_missing_files,
        )
        if near_duplicates:
            first_near = near_duplicates[0]
            msg = (
                f"Near-duplicate pHash leakage detected between '{first_near[0].split}' ('{first_near[0].image_path}') "
                f"and '{first_near[1].split}' ('{first_near[1].image_path}') with Hamming distance {first_near[2]} "
                f"(threshold: {phash_threshold})"
            )
            raise DataLeakageError(msg)

    # Step 5: External label collision check (Warning only, non-blocking)
    warnings: list[str] = []
    if check_registry and check_labels:
        warnings = check_label_collisions(
            items,
            benchmark_labels_path=benchmark_labels_path,
            cross_capture_groups=cross_capture_groups,
        )

    return warnings
