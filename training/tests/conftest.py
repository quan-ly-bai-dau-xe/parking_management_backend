"""Pytest fixtures and strict heavy test requirement enforcement."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from plate_training.cache import (
    get_benchmark_labels_path,
    get_cache_dir,
    get_crops_dir,
    get_weights_path,
)


def is_heavy_required() -> bool:
    """Return True if PLATE_TRAINING_REQUIRE_HEAVY environment variable is set to 1."""
    return os.environ.get("PLATE_TRAINING_REQUIRE_HEAVY", "0").lower() in (
        "1",
        "true",
        "yes",
    )


@pytest.fixture(scope="session")
def heavy_cache_dir() -> Path:
    """Resolve active PLATE_TRAINING_CACHE directory."""
    return get_cache_dir()


@pytest.fixture(scope="session")
def heavy_weights_path(heavy_cache_dir: Path) -> Path:
    """
    Resolve published cct_xs_v2_global.keras weights path.

    Fails with pytest.fail if PLATE_TRAINING_REQUIRE_HEAVY=1 and file missing.
    Skips if PLATE_TRAINING_REQUIRE_HEAVY is unset and file missing.
    """
    w_path = get_weights_path(heavy_cache_dir)
    if not w_path.is_file():
        msg = (
            f"Missing heavy input: Published weights file not found at {w_path}. "
            "Run 'python -m plate_training.cli prepare-heavy-inputs' to prepare cache."
        )
        if is_heavy_required():
            pytest.fail(msg)
        else:
            pytest.skip(msg)
    return w_path


@pytest.fixture(scope="session")
def heavy_crops_dir(heavy_cache_dir: Path) -> Path:
    """
    Resolve 322 detector benchmark crops directory.

    Fails with pytest.fail if PLATE_TRAINING_REQUIRE_HEAVY=1 and crops missing.
    Skips if PLATE_TRAINING_REQUIRE_HEAVY is unset and crops missing.
    """
    c_dir = get_crops_dir(heavy_cache_dir)
    crop_files = list(c_dir.glob("crop_*.png")) if c_dir.is_dir() else []
    if len(crop_files) != 322:
        msg = (
            f"Missing heavy input: Expected 322 detector crops in {c_dir}, found {len(crop_files)}. "
            "Run 'python -m plate_training.cli prepare-heavy-inputs' to prepare cache."
        )
        if is_heavy_required():
            pytest.fail(msg)
        else:
            pytest.skip(msg)
    return c_dir


@pytest.fixture(scope="session")
def heavy_labels_path(heavy_cache_dir: Path) -> Path:
    """
    Resolve benchmark 322 plate strings labels path.

    Fails with pytest.fail if PLATE_TRAINING_REQUIRE_HEAVY=1 and labels missing.
    Skips if PLATE_TRAINING_REQUIRE_HEAVY is unset and labels missing.
    """
    l_path = get_benchmark_labels_path(heavy_cache_dir)
    if not l_path.is_file():
        msg = (
            f"Missing heavy input: Benchmark labels not found at {l_path}. "
            "Run 'python -m plate_training.cli prepare-heavy-inputs' to prepare cache."
        )
        if is_heavy_required():
            pytest.fail(msg)
        else:
            pytest.skip(msg)
    return l_path


@pytest.fixture(scope="session")
def heavy_candidate_pool_path(heavy_cache_dir: Path) -> Path:
    """
    Resolve cached candidate_pool.json path.

    Fails with pytest.fail if PLATE_TRAINING_REQUIRE_HEAVY=1 and file missing.
    Skips if PLATE_TRAINING_REQUIRE_HEAVY is unset and file missing.
    """
    pool_path = heavy_cache_dir / "candidate_pool.json"
    if not pool_path.is_file():
        msg = (
            f"Missing heavy input: Candidate pool not found at {pool_path}. "
            "Run 'python -m plate_training.cli build-candidate-pool' to prepare cache."
        )
        if is_heavy_required():
            pytest.fail(msg)
        else:
            pytest.skip(msg)
    return pool_path


@pytest.fixture(scope="session")
def heavy_pool_summary_path(heavy_cache_dir: Path) -> Path:
    """
    Resolve cached pool_summary.json path.

    Fails with pytest.fail if PLATE_TRAINING_REQUIRE_HEAVY=1 and file missing.
    Skips if PLATE_TRAINING_REQUIRE_HEAVY is unset and file missing.
    """
    summary_path = heavy_cache_dir / "pool_summary.json"
    if not summary_path.is_file():
        msg = (
            f"Missing heavy input: Pool summary not found at {summary_path}. "
            "Run 'python -m plate_training.cli build-candidate-pool' to prepare cache."
        )
        if is_heavy_required():
            pytest.fail(msg)
        else:
            pytest.skip(msg)
    return summary_path
