"""Build dataset manifest JSON from image directory and annotation metadata."""

import argparse
import random
from pathlib import Path

from plate_training.manifest import ManifestItem, compute_file_sha256, save_manifest
from plate_training.normalization import normalize_plate
from plate_training.split import validate_splits


def build_manifest_from_directory(
    image_dir: str | Path,
    output_path: str | Path,
    provenance: str = "field-survey-2026",
    license_str: str = "Proprietary",
    val_ratio: float = 0.2,
    seed: int = 42,
) -> list[ManifestItem]:
    """
    Scan image directory, compute SHA-256 hashes, assign train/val splits,
    validate for zero split leakage, and save manifest JSON.
    """
    root = Path(image_dir)
    image_paths = sorted(
        [
            p
            for p in root.glob("**/*")
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and p.is_file()
        ]
    )

    if not image_paths:
        raise FileNotFoundError(f"No valid image files found in {image_dir}")

    random.seed(seed)
    items: list[ManifestItem] = []

    for path in image_paths:
        rel_path = str(path.relative_to(root)).replace("\\", "/")
        sha = compute_file_sha256(path)
        # Parse ground truth plate text from filename (stem before separator)
        raw_name = path.stem.split("_")[0]
        norm_text = normalize_plate(raw_name)

        # Split assignment (preserving reproducibility)
        split = "val" if random.random() < val_ratio else "train"

        item = ManifestItem(
            image_path=rel_path,
            sha256=sha,
            plate_text=norm_text,
            split=split,
            provenance=provenance,
            license=license_str,
            plate_region="VN",
            quality="readable",
        )
        items.append(item)

    # Validate split integrity
    validate_splits(items, base_dir=root, check_phash=True, phash_threshold=4)

    # Save manifest
    save_manifest(items, output_path)
    return items


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build dataset manifest from image crop folder."
    )
    parser.add_argument(
        "--image-dir", "-i", required=True, help="Input images directory."
    )
    parser.add_argument(
        "--output",
        "-o",
        default="data/manifest.json",
        help="Output manifest JSON path.",
    )
    parser.add_argument(
        "--provenance", default="field-survey-2026", help="Data source provenance."
    )
    parser.add_argument(
        "--license", default="Proprietary", help="Data license identifier."
    )
    parser.add_argument(
        "--val-ratio", type=float, default=0.2, help="Validation set split ratio."
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for split assignment."
    )

    args = parser.parse_args()
    items = build_manifest_from_directory(
        image_dir=args.image_dir,
        output_path=args.output,
        provenance=args.provenance,
        license_str=args.license,
        val_ratio=args.val_ratio,
        seed=args.seed,
    )
    print(f"Built manifest with {len(items)} samples -> {args.output}")


if __name__ == "__main__":
    main()
