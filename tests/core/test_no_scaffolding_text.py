# cspell:ignore IHDR ilestone ound
"""Guard Test Against Residual Scaffolding and Prompt Artifacts.

Ensures that code under production and test paths contains no residual iteration
labels, prompt task numbers, or temporary testing flags.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


def _detect_repo_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "manage.py"
        ).is_file():
            return candidate
    return current.parents[2]


REPO_ROOT = _detect_repo_root()

# Target locations to scan per requirement specifications
TARGET_LOCATIONS: tuple[str, ...] = (
    "apps/accounts",
    "tests/accounts",
    "config/settings",
    ".env.example",
)

# Binary and cache extensions to skip during file scanning
IGNORED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pyc",
        ".pyo",
        ".pyd",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".svg",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".zip",
        ".tar",
        ".gz",
        ".db",
        ".sqlite3",
    }
)

# Directories to skip entirely
IGNORED_DIRECTORIES: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".agents",
        ".git",
        ".venv",
        "venv",
    }
)

# Forbidden regex patterns constructed via dynamic string concatenation
# so the scanner does not match its own source text.
FORBIDDEN_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile("R" + r"ound \d+"), "R" + "ound <digits>"),
    (re.compile("M" + r"ilestone"), "M" + "ilestone"),
    (re.compile("R" + r"ed Test"), "R" + "ed Test"),
    (re.compile(r"\b" + "p" + r"er D\d+\b"), "per D" + "<digits>"),
    (re.compile(r"\b" + "Q" + r"\d\b"), "Q" + "<digit>"),
    (re.compile(r"\b" + "L" + r"\d\b"), "L" + "<digit>"),
)


@dataclass(frozen=True)
class ScaffoldingViolation:
    """Represents a single detected scaffolding text violation."""

    file_path: str
    line_number: int
    matched_rule: str
    line_content: str

    def format_entry(self) -> str:
        """Formats the violation entry for test failure reporting."""
        return (
            f"  - {self.file_path}:{self.line_number} "
            f"[{self.matched_rule}]\n"
            f"      Line: {self.line_content}"
        )


def should_skip_path(path: Path) -> bool:
    """Checks whether a given path or any of its parents should be ignored."""
    return any(part in IGNORED_DIRECTORIES for part in path.parts)


def collect_scan_files(target_roots: Sequence[Path]) -> list[Path]:
    """Collects all eligible text files within the specified target paths."""
    discovered: list[Path] = []
    for root in target_roots:
        if not root.exists():
            continue
        if root.is_file():
            if (
                not should_skip_path(root)
                and root.suffix.lower() not in IGNORED_EXTENSIONS
            ):
                discovered.append(root)
            continue

        for item in sorted(root.rglob("*")):
            if item.is_file():
                if should_skip_path(item):
                    continue
                if item.suffix.lower() in IGNORED_EXTENSIONS:
                    continue
                discovered.append(item)
    return discovered


def scan_file_content(file_path: Path, repo_root: Path) -> list[ScaffoldingViolation]:
    """Scans an individual file line by line for forbidden scaffolding patterns."""
    violations: list[ScaffoldingViolation] = []
    try:
        with open(file_path, encoding="utf-8") as stream:
            for line_no, raw_line in enumerate(stream, 1):
                clean_line = raw_line.strip()
                for pattern, rule_label in FORBIDDEN_RULES:
                    if pattern.search(clean_line):
                        try:
                            relative_display = (
                                file_path.resolve()
                                .relative_to(repo_root.resolve())
                                .as_posix()
                            )
                        except ValueError:
                            relative_display = file_path.as_posix()
                        violations.append(
                            ScaffoldingViolation(
                                file_path=relative_display,
                                line_number=line_no,
                                matched_rule=rule_label,
                                line_content=clean_line,
                            )
                        )
                        break  # Report once per line
    except UnicodeDecodeError:
        # Gracefully skip binary files that cannot be decoded as UTF-8
        return []
    return violations


def scan_targets(
    repo_root: Path, target_paths: Sequence[str]
) -> list[ScaffoldingViolation]:
    """Scans all specified target relative paths for scaffolding text violations."""
    target_roots = [repo_root / rel_path for rel_path in target_paths]
    files_to_scan = collect_scan_files(target_roots)
    all_violations: list[ScaffoldingViolation] = []
    for file_path in files_to_scan:
        all_violations.extend(scan_file_content(file_path, repo_root))
    return all_violations


def test_no_residual_scaffolding_text() -> None:
    """Guards against residual scaffolding, iteration tags, and prompt labels."""
    violations = scan_targets(REPO_ROOT, TARGET_LOCATIONS)
    assert not violations, (
        f"Detected {len(violations)} scaffolding text violation(s) "
        f"across target locations:\n" + "\n".join(v.format_entry() for v in violations)
    )


def test_guard_scanner_does_not_flag_itself() -> None:
    """Verifies that the guard test file does not match its own source text."""
    current_file = Path(__file__).resolve()
    self_violations = scan_file_content(current_file, REPO_ROOT)
    assert not self_violations, (
        "The guard test file matched its own source text:\n"
        + "\n".join(v.format_entry() for v in self_violations)
    )


# ==============================================================================
# Synthetic Unit Tests Verifying Scanner Capabilities
# ==============================================================================


def test_scanner_detects_forbidden_patterns(tmp_path: Path) -> None:
    """Ensures scanner catches all forbidden patterns when present in text."""
    test_file = tmp_path / "sample_violation.py"
    # Construct test strings dynamically so this test function does not flag itself
    lines = [
        "# Valid header per ADR-0004",
        "# Sample text with " + "R" + "ound " + "44 banner",
        "# Another note with " + "M" + "ilestone marker",
        "# Docstring with " + "R" + "ed " + "Test label",
        "# Parameter comment " + "p" + "er " + "D" + "6 specification",
        "# Security rule " + "Q" + "3 rate limiter",
        "# Cache layer " + "L" + "2 cache entry",
        "# Clean durable citation: TL-52 and TL-53",
    ]
    test_file.write_text("\n".join(lines), encoding="utf-8")

    violations = scan_file_content(test_file, tmp_path)
    # Lines 2, 3, 4, 5, 6, 7 should be flagged (6 violations)
    assert len(violations) == 6
    matched_rules = [v.matched_rule for v in violations]
    assert ("R" + "ound <digits>") in matched_rules
    assert ("M" + "ilestone") in matched_rules
    assert ("R" + "ed Test") in matched_rules
    assert ("per D" + "<digits>") in matched_rules
    assert ("Q" + "<digit>") in matched_rules
    assert ("L" + "<digit>") in matched_rules


def test_scanner_allows_clean_durable_ids(tmp_path: Path) -> None:
    """Ensures scanner passes cleanly on approved durable architecture IDs."""
    test_file = tmp_path / "clean_sample.py"
    lines = [
        "# Protected per TL-52 and TL-53",
        "# Grace window per OQ-87 and ADR-0004",
        "# Token purge per TL-36",
        "# Requirement trace: REQ-AUTH-01 and SRS 4.1",
        "# Message catalogs: MSG-4.1-M02 and PROP-4.1-P06",
    ]
    test_file.write_text("\n".join(lines), encoding="utf-8")

    violations = scan_file_content(test_file, tmp_path)
    assert violations == []


def test_scanner_skips_binary_and_pycache(tmp_path: Path) -> None:
    """Ensures scanner ignores binary files and pycache directories."""
    pycache_dir = tmp_path / "__pycache__"
    pycache_dir.mkdir()
    pycache_file = pycache_dir / "bad.py"
    pycache_file.write_text("R" + "ound " + "44", encoding="utf-8")

    binary_file = tmp_path / "image.png"
    binary_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"R" + b"ound 44")

    files = collect_scan_files([tmp_path])
    assert pycache_file not in files
    assert binary_file not in files
