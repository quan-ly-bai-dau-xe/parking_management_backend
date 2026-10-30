"""Unit tests for checkpoint discovery pure function."""

from pathlib import Path

import pytest

from plate_training.checkpoint import find_latest_checkpoint


@pytest.mark.unit
def test_find_latest_checkpoint_nonexistent_dir(tmp_path: Path) -> None:
    """Non-existent directory should return (None, 0)."""
    non_existent = tmp_path / "does_not_exist"
    path, epoch = find_latest_checkpoint(non_existent)
    assert path is None
    assert epoch == 0


@pytest.mark.unit
def test_find_latest_checkpoint_file_as_dir(tmp_path: Path) -> None:
    """When a file is passed instead of a directory, return (None, 0)."""
    fake_dir = tmp_path / "a_file.txt"
    fake_dir.write_text("hello", encoding="utf-8")
    path, epoch = find_latest_checkpoint(fake_dir)
    assert path is None
    assert epoch == 0


@pytest.mark.unit
def test_find_latest_checkpoint_empty_dir(tmp_path: Path) -> None:
    """Empty directory should return (None, 0)."""
    empty_dir = tmp_path / "empty_checkpoints"
    empty_dir.mkdir()
    path, epoch = find_latest_checkpoint(empty_dir)
    assert path is None
    assert epoch == 0


@pytest.mark.unit
def test_find_latest_checkpoint_zero_byte_file(tmp_path: Path) -> None:
    """0-byte .keras files should be ignored."""
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    (ckpt_dir / "cct_xs_epoch_010.keras").touch()  # 0 bytes
    path, epoch = find_latest_checkpoint(ckpt_dir)
    assert path is None
    assert epoch == 0


@pytest.mark.unit
def test_find_latest_checkpoint_invalid_filename(tmp_path: Path) -> None:
    """Files not matching pattern .*_epoch_(\\d+)\\.keras should be ignored."""
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    (ckpt_dir / "cct_xs_best.keras").write_bytes(b"dummy")
    (ckpt_dir / "model_epoch_abc.keras").write_bytes(b"dummy")
    (ckpt_dir / "checkpoint.onnx").write_bytes(b"dummy")
    path, epoch = find_latest_checkpoint(ckpt_dir)
    assert path is None
    assert epoch == 0


@pytest.mark.unit
def test_find_latest_checkpoint_single_valid(tmp_path: Path) -> None:
    """Single valid checkpoint should return its path and extracted epoch."""
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    valid_file = ckpt_dir / "cct_xs_epoch_005.keras"
    valid_file.write_bytes(b"non-empty model weights")
    path, epoch = find_latest_checkpoint(ckpt_dir)
    assert path == valid_file
    assert epoch == 5


@pytest.mark.unit
def test_find_latest_checkpoint_multiple_epochs_highest_selected(
    tmp_path: Path,
) -> None:
    """Multiple checkpoints should correctly identify the one with the maximum epoch."""
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    (ckpt_dir / "cct_xs_epoch_002.keras").write_bytes(b"e2")
    (ckpt_dir / "cct_xs_epoch_015.keras").write_bytes(b"e15")
    (ckpt_dir / "cct_xs_epoch_007.keras").write_bytes(b"e7")
    (ckpt_dir / "cct_xs_epoch_010.keras").write_bytes(b"e10")

    path, epoch = find_latest_checkpoint(ckpt_dir)
    assert path == ckpt_dir / "cct_xs_epoch_015.keras"
    assert epoch == 15


@pytest.mark.unit
def test_find_latest_checkpoint_ignores_zero_byte_even_if_higher_epoch(
    tmp_path: Path,
) -> None:
    """A zero-byte file with a higher epoch should be ignored in favor of a valid non-empty checkpoint."""
    ckpt_dir = tmp_path / "checkpoints"
    ckpt_dir.mkdir()
    (ckpt_dir / "cct_xs_epoch_012.keras").write_bytes(b"e12 valid weights")
    (ckpt_dir / "cct_xs_epoch_025.keras").touch()  # 0-byte corrupted file

    path, epoch = find_latest_checkpoint(ckpt_dir)
    assert path == ckpt_dir / "cct_xs_epoch_012.keras"
    assert epoch == 12
