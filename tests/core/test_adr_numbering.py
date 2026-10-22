"""ADR Numbering and Convention Guard Tests.

Guards the architectural decision records repository against duplicate numbering
prefixes and ensures all filenames strictly adhere to the project convention
'NNNN-<slug>.md'.
"""

import re
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ADR_DIR = REPO_ROOT / "docs" / "adr"
ADR_FILENAME_PATTERN = re.compile(r"^(\d{4})-(.+)\.md$")


def find_duplicate_adr_prefixes(adr_dir: Path) -> dict[str, list[str]]:
    """Scans the ADR directory and groups files by their 4-digit prefix.

    Returns a mapping of prefix -> list of filenames for any prefix with > 1 file.
    """
    prefix_map: dict[str, list[str]] = defaultdict(list)
    for path in adr_dir.glob("*.md"):
        if path.is_file():
            match = ADR_FILENAME_PATTERN.match(path.name)
            if match:
                prefix = match.group(1)
                prefix_map[prefix].append(path.name)

    return {
        prefix: sorted(files) for prefix, files in prefix_map.items() if len(files) > 1
    }


def test_adr_directory_exists() -> None:
    """Verifies docs/adr/ exists and is a directory."""
    assert ADR_DIR.exists(), f"ADR directory not found at {ADR_DIR}"
    assert ADR_DIR.is_dir(), f"ADR path is not a directory: {ADR_DIR}"


def test_no_duplicate_adr_prefixes() -> None:
    """Guards against duplicate 4-digit ADR prefixes in docs/adr/."""
    duplicates = find_duplicate_adr_prefixes(ADR_DIR)
    assert not duplicates, (
        f"Duplicate ADR number prefixes detected in {ADR_DIR}:\n"
        + "\n".join(
            f"  Prefix '{prefix}': {', '.join(files)}"
            for prefix, files in sorted(duplicates.items())
        )
    )


def test_all_adr_filenames_follow_convention() -> None:
    """Ensures all markdown files in docs/adr/ match the 4-digit prefix format."""
    invalid_files: list[str] = []
    for path in ADR_DIR.glob("*.md"):
        if path.is_file() and not ADR_FILENAME_PATTERN.match(path.name):
            invalid_files.append(path.name)

    assert not invalid_files, (
        f"Non-compliant ADR filenames found in {ADR_DIR} (must match 'NNNN-<slug>.md'):\n"
        + "\n".join(f"  {f}" for f in sorted(invalid_files))
    )
