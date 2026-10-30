"""Checkpoint discovery and epoch extraction pure utilities."""

import re
from pathlib import Path

CHECKPOINT_REGEX = re.compile(r"^.*_epoch_(\d+)\.keras$")


def find_latest_checkpoint(checkpoint_dir: str | Path) -> tuple[Path | None, int]:
    """
    Scan checkpoint directory for valid non-empty .keras files,
    extract the highest epoch number, and return (latest_checkpoint_path, initial_epoch).

    Returns (None, 0) if the directory does not exist or contains no valid checkpoints.
    """
    p = Path(checkpoint_dir)
    if not p.is_dir():
        return None, 0

    best_epoch = -1
    best_path: Path | None = None

    for item in p.iterdir():
        if not item.is_file() or item.suffix != ".keras":
            continue
        try:
            if item.stat().st_size == 0:
                continue
        except OSError:
            continue

        match = CHECKPOINT_REGEX.match(item.name)
        if match:
            epoch = int(match.group(1))
            if epoch > best_epoch or (
                epoch == best_epoch
                and (best_path is None or item.name > best_path.name)
            ):
                best_epoch = epoch
                best_path = item

    if best_path is None or best_epoch < 0:
        return None, 0

    return best_path, best_epoch
