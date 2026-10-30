"""
Automated secret scanner guard test.
Scans repository source files, configuration templates, and documentation
to ensure zero hardcoded or committed Cloudinary credentials (API keys, secrets, or URLs)
exist in the repository, per ADR-0009 and Milestone 4 requirements.
"""

from __future__ import annotations

import re
from pathlib import Path

IGNORED_DIRECTORIES: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "node_modules",
    }
)

IGNORED_FILES: frozenset[str] = frozenset(
    {
        ".env",  # Local developer env file, git-ignored
        "test_secret_scanner.py",  # Self-referential test patterns
    }
)

ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".md",
        ".txt",
        ".json",
        ".yml",
        ".yaml",
        ".sql",
        ".sh",
        ".bat",
        ".toml",
    }
)

# Regex patterns matching Cloudinary secrets, URLs, and numeric API keys assigned to config
CLOUDINARY_SECRET_PATTERNS = [
    # Full cloudinary:// URL with embedded credentials
    re.compile(r"cloudinary://\d+:[A-Za-z0-9_\-]+@[A-Za-z0-9_\-]+"),
    # Assignment to CLOUDINARY_API_SECRET with a long literal value (quoted or not, as in .env files)
    re.compile(
        r"""CLOUDINARY_API_SECRET[ \t]*[:=][ \t]*['"]?[A-Za-z0-9_\-]{16,}['"]?"""
    ),
    # Assignment to CLOUDINARY_API_KEY with numeric literal of 12-18 digits (quoted or not)
    re.compile(r"""CLOUDINARY_API_KEY[ \t]*[:=][ \t]*['"]?\d{12,18}['"]?"""),
]


def scan_file_for_secrets(file_path: Path) -> list[str]:
    """Scans a single file for strings shaped like Cloudinary secrets or credentials."""
    findings: list[str] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return findings

    for pattern in CLOUDINARY_SECRET_PATTERNS:
        matches = pattern.findall(content)
        if matches:
            findings.extend(
                f"{file_path}: matched pattern '{pattern.pattern}' -> {m[:10]}... (redacted)"
                for m in matches
            )
    return findings


def scan_repository_for_secrets(root_dir: Path) -> list[str]:
    """Recursively scans repository files for exposed Cloudinary secrets."""
    all_findings: list[str] = []
    for path in root_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.name in IGNORED_FILES:
            continue
        if any(part in IGNORED_DIRECTORIES for part in path.parts):
            continue
        if path.suffix not in ALLOWED_EXTENSIONS and path.name != ".env.example":
            continue

        findings = scan_file_for_secrets(path)
        all_findings.extend(findings)

    return all_findings


def test_no_committed_cloudinary_secrets_across_repo():
    """Verifies that no tracked files in the repo contain committed Cloudinary secrets."""
    repo_root = Path(__file__).resolve().parents[2]
    findings = scan_repository_for_secrets(repo_root)

    assert not findings, (
        "Automated security scan failed! Exposed Cloudinary secrets found:\n"
        + "\n".join(findings)
    )


def test_scanner_detects_synthetic_secrets():
    """Unit test verifying the secret scanner correctly detects synthetic credentials."""
    synthetic_samples = [
        "cloudinary://123456789012345:mySecretKeyAbc123@mycloud",
        "CLOUDINARY_API_SECRET = 'aBcDeFgHiJkLmNoPqRsTuVwXyZ123456'",
        'CLOUDINARY_API_KEY = "123456789012345"',
        "CLOUDINARY_API_SECRET=aBcDeFgHiJkLmNoPqRsTuVwXyZ123456",
        "CLOUDINARY_API_KEY=123456789012345",
    ]
    clean_samples = [
        "CLOUDINARY_API_SECRET=",
        "CLOUDINARY_API_KEY=",
        "CLOUDINARY_API_SECRET=<your-secret>",
        "CLOUDINARY_API_SECRET=\nMAX_IMAGE_SIZE_MB=5",
        "CLOUDINARY_API_KEY=\nCLOUDINARY_API_SECRET=",
    ]
    for sample in clean_samples:
        assert not any(p.search(sample) for p in CLOUDINARY_SECRET_PATTERNS), sample
    for sample in synthetic_samples:
        matched = any(p.search(sample) for p in CLOUDINARY_SECRET_PATTERNS)
        assert matched, f"Scanner should have matched synthetic sample: {sample}"
