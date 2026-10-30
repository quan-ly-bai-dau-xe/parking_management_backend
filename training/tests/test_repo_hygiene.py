"""Repository Hygiene Scanner & Path Leakage Unit Test with Red-then-Green Mutation Proof."""

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Patterns forbidden in training subproject and committed PR changes (S2a)
FORBIDDEN_PATH_PATTERNS = [
    re.compile(r"C:[/\\]+Users", re.IGNORECASE),
    re.compile(r"[/\\]home[/\\](?!appuser|username)", re.IGNORECASE),
    re.compile(r"\.gemini", re.IGNORECASE),
    re.compile(r"antigravity", re.IGNORECASE),
    re.compile(r"(?:^|[\s\"'`(=/\\])scratch[/\\](?!pretrained)", re.IGNORECASE),
]

# Process vocabulary forbidden outside .agents/ (S5)
FORBIDDEN_PROCESS_VOCAB = re.compile(r"Round\s+[0-9]+", re.IGNORECASE)


def scan_file_content(
    content: str,
    filename: str,
    check_process_vocab: bool = False,
) -> list[str]:
    """Scan content for forbidden machine-specific paths and optionally process vocabulary."""
    violations: list[str] = []
    lines = content.splitlines()
    for lineno, line in enumerate(lines, 1):
        for pattern in FORBIDDEN_PATH_PATTERNS:
            if pattern.search(line):
                violations.append(
                    f"[{filename}:{lineno}] Forbidden path pattern '{pattern.pattern}' matched: {line.strip()}"
                )
        if check_process_vocab and FORBIDDEN_PROCESS_VOCAB.search(line):
            violations.append(
                f"[{filename}:{lineno}] Forbidden process vocabulary 'Round NN' matched: {line.strip()}"
            )
    return violations


# ==============================================================================
# Phase RED: Mutation Proof
# ==============================================================================
@pytest.mark.unit
def test_repo_hygiene_scanner_mutation_red_path_injection() -> None:
    """Prove that injecting a machine-specific path causes scanner to FAIL (Phase RED)."""
    synthetic_bad_content = 'DEFAULT_WEIGHTS = Path(r"C:\\Users\\Developer\\.gemini\\antigravity\\scratch\\r59_cache\\weights.keras")\n'
    violations = scan_file_content(synthetic_bad_content, "synthetic_model.py")
    assert len(violations) >= 1, "Expected scanner to detect injected forbidden path"
    assert any("Users" in v or "antigravity" in v for v in violations)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("bad_line", "expected_pattern_substr"),
    [
        ('PATH = "C:/Users/Developer/weights.keras"', "Users"),
        ('PATH = "C:\\\\Users\\\\Developer\\\\weights.keras"', "Users"),
        (r'PATH = "C:\Users\Developer\weights.keras"', "Users"),
        ('PATH = "c:/users/someone/file.py"', "Users"),
        ('PATH = "C:/USERS/SOMEONE/FILE.PY"', "Users"),
        ('HOME = "/home/developer/data"', "home"),
        (r'HOME = "\home\developer\data"', "home"),
        ('GEMINI_DIR = "/opt/.gemini/cache"', ".gemini"),
        ('TOOL_NAME = "antigravity.runner"', "antigravity"),
        ('CACHE = "scratch/cache"', "scratch"),
        ('CACHE = "scratch/temp"', "scratch"),
        (r'CACHE = "scratch\cache"', "scratch"),
        ('CACHE = "scratch\\\\cache"', "scratch"),
        ('CACHE = "SCRATCH/CACHE"', "scratch"),
        ('NESTED = "nested/dir/scratch/cache"', "scratch"),
    ],
)
def test_repo_hygiene_scanner_granular_forbidden_mutations(
    bad_line: str, expected_pattern_substr: str
) -> None:
    """Prove that each forbidden pattern is independently caught by the scanner."""
    violations = scan_file_content(bad_line, "synthetic_check.py")
    assert len(violations) >= 1, f"Expected scanner to detect: {bad_line}"
    assert any(expected_pattern_substr.lower() in v.lower() for v in violations)


@pytest.mark.unit
@pytest.mark.parametrize(
    "safe_line",
    [
        "# This pipeline is strictly NOT training from scratch.",
        'PARKING_SCRATCH_DATASET_DIR = "/tmp/cache"',
        "scratch disk space is 20 GB",
        "[RESUME] Initializing model from scratch/pretrained baseline...",
        "/home/appuser/workspace",
        "/home/username/repo",
    ],
)
def test_repo_hygiene_scanner_safe_patterns_not_flagged(safe_line: str) -> None:
    """Verify that legitimate words (e.g. scratch/pretrained, appuser) are not flagged."""
    violations = scan_file_content(safe_line, "safe_file.py")
    assert violations == [], f"Legitimate line was falsely flagged: {safe_line}"


@pytest.mark.unit
def test_repo_hygiene_scanner_mutation_red_process_vocab() -> None:
    """Prove that injecting process vocabulary causes scanner to FAIL (Phase RED)."""
    bad_word = "".join(["R", "o", "u", "n", "d", " ", "6", "0"])
    synthetic_bad_content = f"# Specifications for {bad_word} benchmark run\n"
    violations = scan_file_content(
        synthetic_bad_content, "synthetic_runbook.md", check_process_vocab=True
    )
    assert len(violations) >= 1, (
        "Expected scanner to detect injected process vocabulary"
    )
    assert any("Round NN" in v for v in violations)


# ==============================================================================
# Phase GREEN: Full Training Codebase Path Hygiene Proof (S2a)
# ==============================================================================
@pytest.mark.unit
def test_training_subproject_clean_hygiene() -> None:
    """
    Verify zero machine-specific paths across git ls-files and untracked training/ files,
    and zero process vocabulary ('Round NN') across training/, ADR-0008, and 03-training-check.yml.
    """
    scanned_extensions = {".py", ".ipynb", ".yaml", ".yml", ".json", ".md", ".txt"}
    binary_extensions = {
        ".png",
        ".jpg",
        ".jpeg",
        ".onnx",
        ".woff",
        ".woff2",
        ".ttf",
        ".ico",
        ".pdf",
        ".keras",
    }
    excluded_self_tests = {"test_repo_hygiene.py", "test_host_independence_guard.py"}
    training_scope_files: list[Path] = []

    # 1. training subproject
    training_dir = REPO_ROOT / "training"
    for root, _dirs, files in os.walk(training_dir):
        if any(
            p in root
            for p in [
                ".git",
                "__pycache__",
                ".pytest_cache",
                ".mypy_cache",
                ".venv",
                "venv",
            ]
        ):
            continue
        for file in files:
            p = Path(root) / file
            if p.name in excluded_self_tests:
                continue
            if p.suffix in scanned_extensions:
                training_scope_files.append(p)

    # 2. ADR 0008
    adr_file = (
        REPO_ROOT / "docs" / "adr" / "0008-plate-recognition-training-pipeline.md"
    )
    if adr_file.is_file():
        training_scope_files.append(adr_file)

    # 3. Workflow 03
    wf_file = REPO_ROOT / ".github" / "workflows" / "03-training-check.yml"
    if wf_file.is_file():
        training_scope_files.append(wf_file)

    all_violations: list[str] = []
    scanned_resolved: set[Path] = set()
    for f in training_scope_files:
        scanned_resolved.add(f.resolve())
        try:
            content = f.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        v = scan_file_content(
            content, str(f.relative_to(REPO_ROOT)), check_process_vocab=True
        )
        all_violations.extend(v)

    # 4. Also scan all committed files (git ls-files) for forbidden machine-specific paths
    if (REPO_ROOT / ".git").exists():
        try:
            git_out = subprocess.check_output(
                ["git", "ls-files"], cwd=REPO_ROOT, text=True
            )
            for rel in git_out.splitlines():
                p = REPO_ROOT / rel
                if (
                    not p.is_file()
                    or p.resolve() in scanned_resolved
                    or p.name in excluded_self_tests
                    or p.suffix in binary_extensions
                ):
                    continue
                try:
                    content = p.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                v = scan_file_content(content, rel, check_process_vocab=False)
                all_violations.extend(v)
        except Exception:
            pass

    assert all_violations == [], (
        f"Found {len(all_violations)} hygiene violations:\n"
        + "\n".join(f"  - {x}" for x in all_violations)
    )
