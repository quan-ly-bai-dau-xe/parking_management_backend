"""CLI script to download official cct_xs_v2_global.keras weights into PLATE_TRAINING_CACHE."""

# ruff: noqa: E402

import argparse
import sys
from pathlib import Path

# Add training/src to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
TRAINING_SRC = SCRIPT_DIR.parent / "src"
if str(TRAINING_SRC) not in sys.path:
    sys.path.insert(0, str(TRAINING_SRC))

from plate_training.cache import (
    EXPECTED_WEIGHTS_SIZE_BYTES,
    OFFICIAL_WEIGHTS_URL,
    compute_sha256,
    fetch_published_weights,
    get_cache_dir,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Fetch published CCT-XS weights from official release ({OFFICIAL_WEIGHTS_URL})"
    )
    parser.add_argument(
        "--cache-dir",
        default=None,
        help="Target cache directory (defaults to PLATE_TRAINING_CACHE or OS user cache).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force re-download even if weights already exist and pass verification.",
    )
    args = parser.parse_args()

    try:
        resolved_dir = get_cache_dir(args.cache_dir)
        print(f"[INFO] Resolving weights cache in: {resolved_dir}")
        w_path = fetch_published_weights(cache_dir=args.cache_dir, force=args.force)
        sha = compute_sha256(w_path)
        size = w_path.stat().st_size
        print(f"[SUCCESS] Weights verified: {w_path}")
        print(f"  - Size: {size:,} bytes (expected: {EXPECTED_WEIGHTS_SIZE_BYTES:,})")
        print(f"  - SHA-256: {sha}")
        print(f"  - Release URL: {OFFICIAL_WEIGHTS_URL}")
    except Exception as e:
        print(f"[ERROR] Failed to fetch weights: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
