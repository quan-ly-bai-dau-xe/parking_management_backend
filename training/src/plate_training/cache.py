"""Cache directory resolution and asset management for heavy training inputs."""

from __future__ import annotations

import hashlib
import logging
import os
import sys
import urllib.request
from pathlib import Path

logger = logging.getLogger("plate_training.cache")

OFFICIAL_WEIGHTS_URL = "https://github.com/ankandrew/fast-plate-ocr/releases/download/arg-plates/cct_xs_v2_global.keras"
EXPECTED_WEIGHTS_SHA256 = (
    "0716717772b1f8d25b3c227e1e65e7f42e63900ec017059b4a32155488735ffd"
)
EXPECTED_WEIGHTS_SIZE_BYTES = 10_865_307

OFFICIAL_PARQUET_URL = "https://huggingface.co/datasets/sonnetechnology/license-plate-text-recognition-full/resolve/main/data/test-00000-of-00001-a359b6560048e51f.parquet"
EXPECTED_PARQUET_SHA256 = (
    "843233e51036adeef7796205b70d6ae4c30537b03f358323f2ab396ff26bb31b"
)


def get_repo_root() -> Path:
    """Resolve repository root directory."""
    return Path(__file__).resolve().parents[3]


def get_cache_dir(override: str | Path | None = None) -> Path:
    """
    Resolve cache directory for heavy training inputs.

    Resolution order:
    1. Explicit override argument.
    2. PLATE_TRAINING_CACHE environment variable.
    3. Default OS user cache directory outside repository:
       - Windows: %LOCALAPPDATA%/plate_training/cache (or ~/.cache/plate_training)
       - Linux/macOS: $XDG_CACHE_HOME/plate_training (or ~/.cache/plate_training)

    Enforces that cache directory MUST NOT reside inside the repository.
    """
    if override:
        resolved = Path(override).expanduser().resolve()
    elif os.environ.get("PLATE_TRAINING_CACHE"):
        resolved = Path(os.environ["PLATE_TRAINING_CACHE"]).expanduser().resolve()
    else:
        if sys.platform == "win32":
            local_appdata = os.environ.get("LOCALAPPDATA")
            if local_appdata:
                resolved = Path(local_appdata).resolve() / "plate_training" / "cache"
            else:
                resolved = Path.home() / ".cache" / "plate_training"
        else:
            xdg_cache = os.environ.get("XDG_CACHE_HOME")
            base = Path(xdg_cache).resolve() if xdg_cache else (Path.home() / ".cache")
            resolved = base / "plate_training"

    repo_root = get_repo_root()
    try:
        if resolved == repo_root or resolved.is_relative_to(repo_root):
            raise ValueError(
                f"PLATE_TRAINING_CACHE ({resolved}) must not reside inside repository ({repo_root})"
            )
    except AttributeError:
        # Fallback for Python versions without Path.is_relative_to
        if str(resolved).startswith(str(repo_root)):
            raise ValueError(
                f"PLATE_TRAINING_CACHE ({resolved}) must not reside inside repository ({repo_root})"
            ) from None

    return resolved


def ensure_cache_dir(override: str | Path | None = None) -> Path:
    """Ensure cache directory exists on disk and return its Path."""
    d = get_cache_dir(override)
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_weights_path(cache_dir: str | Path | None = None) -> Path:
    """Return Path to cached published weights file."""
    return get_cache_dir(cache_dir) / "cct_xs_v2_global.keras"


def get_crops_dir(cache_dir: str | Path | None = None) -> Path:
    """Return Path to cached 322 detector crops directory."""
    return get_cache_dir(cache_dir) / "crops_322"


def get_benchmark_labels_path(cache_dir: str | Path | None = None) -> Path:
    """Return Path to cached local benchmark labels file."""
    return get_cache_dir(cache_dir) / "benchmark_322_labels.json"


def compute_sha256(file_path: Path | str, chunk_size: int = 65536) -> str:
    """Compute hex SHA-256 digest of file."""
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def fetch_published_weights(
    cache_dir: str | Path | None = None,
    force: bool = False,
) -> Path:
    """
    Download and verify official cct_xs_v2_global.keras weights into cache directory.

    Verifies exact SHA-256 (0716717772b1f8d25b3c227e1e65e7f42e63900ec017059b4a32155488735ffd)
    and exact size (10,865,307 bytes).
    """
    target_dir = ensure_cache_dir(cache_dir)
    target_file = target_dir / "cct_xs_v2_global.keras"

    if target_file.is_file() and not force:
        sha = compute_sha256(target_file)
        size = target_file.stat().st_size
        if sha == EXPECTED_WEIGHTS_SHA256 and size == EXPECTED_WEIGHTS_SIZE_BYTES:
            logger.info("Weights file already cached and verified: %s", target_file)
            return target_file

    logger.info("Fetching published weights from %s...", OFFICIAL_WEIGHTS_URL)
    temp_file = target_file.with_suffix(".tmp")
    req = urllib.request.Request(
        OFFICIAL_WEIGHTS_URL,
        headers={"User-Agent": "plate-training/0.1.0 (reproducible benchmark)"},
    )

    with urllib.request.urlopen(req, timeout=120) as resp, open(temp_file, "wb") as f:
        while chunk := resp.read(65536):
            f.write(chunk)

    actual_sha = compute_sha256(temp_file)
    actual_size = temp_file.stat().st_size

    if actual_sha != EXPECTED_WEIGHTS_SHA256:
        temp_file.unlink(missing_ok=True)
        raise ValueError(
            f"Weights SHA-256 mismatch: got {actual_sha}, expected {EXPECTED_WEIGHTS_SHA256}"
        )
    if actual_size != EXPECTED_WEIGHTS_SIZE_BYTES:
        temp_file.unlink(missing_ok=True)
        raise ValueError(
            f"Weights size mismatch: got {actual_size}, expected {EXPECTED_WEIGHTS_SIZE_BYTES}"
        )

    temp_file.replace(target_file)
    logger.info("Successfully cached weights: %s (SHA-256 verified)", target_file)
    return target_file
