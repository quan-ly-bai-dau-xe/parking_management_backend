"""Guard Test Against Hardcoded HTTP_HOST and SERVER_NAME.

Scans test files under tests/accounts and tests/core to ensure that NO test
hardcodes HTTP_HOST or SERVER_NAME with a literal other than Django's default
test host. This guarantees full independence from the developer machine's .env
file and prevents CI test failures in clean checkout environments.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    # AST analysis operates strictly on static source code without DB connectivity
    return None


def _detect_repo_root() -> Path:
    current = Path(__file__).resolve()
    for candidate in [current, *current.parents]:
        if (candidate / "pyproject.toml").is_file() and (
            candidate / "manage.py"
        ).is_file():
            return candidate
    return current.parents[2]


REPO_ROOT = _detect_repo_root()

# Target test directories to scan per requirement specifications
TARGET_DIRECTORIES: tuple[str, ...] = (
    "tests/accounts",
    "tests/core",
)

# Directories to skip entirely
IGNORED_DIRECTORIES: frozenset[str] = frozenset(
    {
        "__pycache__",
        ".agents",
        ".git",
        ".venv",
        "venv",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
    }
)

IGNORED_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".pyc",
        ".pyo",
        ".pyd",
    }
)

TARGET_HOST_PARAMS: frozenset[str] = frozenset(
    {
        "HTTP_HOST",
        "SERVER_NAME",
    }
)

ALLOWED_HOST_LITERAL: str = "test" + "server"


@dataclass(frozen=True)
class HostViolation:
    """Represents a single hardcoded host/server violation in test files."""

    file_path: str
    line_number: int
    parameter: str
    assigned_value: Any
    line_content: str

    def format_entry(self) -> str:
        """Formats the violation entry for test failure reporting."""
        return (
            f"  - {self.file_path}:{self.line_number} "
            f"[Parameter: {self.parameter}={self.assigned_value!r}]\n"
            f"      Line: {self.line_content}\n"
            f"      Remedy: Remove {self.parameter} to use Django's default test host "
            f"or use {ALLOWED_HOST_LITERAL!r}."
        )


def should_skip_path(path: Path) -> bool:
    """Checks whether a given path or any of its parents should be ignored."""
    return any(part in IGNORED_DIRECTORIES for part in path.parts)


def collect_target_python_files(
    repo_root: Path, target_dirs: tuple[str, ...]
) -> list[Path]:
    """Discovers all eligible Python test files within the target directories."""
    discovered: list[Path] = []
    for rel_path in target_dirs:
        target_path = repo_root / rel_path
        if not target_path.exists():
            continue
        if target_path.is_file():
            if (
                not should_skip_path(target_path)
                and target_path.suffix.lower() not in IGNORED_EXTENSIONS
                and target_path.suffix.lower() == ".py"
            ):
                discovered.append(target_path)
            continue

        for item in sorted(target_path.rglob("*.py")):
            if item.is_file():
                if should_skip_path(item):
                    continue
                if item.suffix.lower() in IGNORED_EXTENSIONS:
                    continue
                discovered.append(item)
    return discovered


def find_hardcoded_http_host_violations(
    source_code: str, file_path: str = "<memory>", repo_root: Path | None = None
) -> list[HostViolation]:
    """Scans Python source code via AST for hardcoded HTTP_HOST or SERVER_NAME values."""
    violations: list[HostViolation] = []
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError:
        return violations

    lines = source_code.splitlines()

    try:
        display_path = (
            Path(file_path).resolve().relative_to(repo_root.resolve()).as_posix()
            if repo_root
            else file_path
        )
    except ValueError, RuntimeError:
        display_path = file_path

    for node in ast.walk(tree):
        # 1. Keyword arguments in function calls: client.post(..., HTTP_HOST=...)
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg in TARGET_HOST_PARAMS:
                    val: Any = None
                    if isinstance(kw.value, ast.Constant):
                        val = kw.value.value
                    if val != ALLOWED_HOST_LITERAL:
                        lineno = getattr(kw.value, "lineno", node.lineno)
                        snippet = (
                            lines[lineno - 1].strip()
                            if 0 < lineno <= len(lines)
                            else ""
                        )
                        violations.append(
                            HostViolation(
                                file_path=display_path,
                                line_number=lineno,
                                parameter=kw.arg,
                                assigned_value=val,
                                line_content=snippet,
                            )
                        )

        # 2. Dictionary literals: extra={'HTTP_HOST': ...}
        elif isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values, strict=False):
                if isinstance(k, ast.Constant) and k.value in TARGET_HOST_PARAMS:
                    val = v.value if isinstance(v, ast.Constant) else None
                    if val != ALLOWED_HOST_LITERAL:
                        lineno = getattr(k, "lineno", node.lineno)
                        snippet = (
                            lines[lineno - 1].strip()
                            if 0 < lineno <= len(lines)
                            else ""
                        )
                        violations.append(
                            HostViolation(
                                file_path=display_path,
                                line_number=lineno,
                                parameter=str(k.value),
                                assigned_value=val,
                                line_content=snippet,
                            )
                        )

        # 3. Variable assignments: HTTP_HOST = ...
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in TARGET_HOST_PARAMS:
                    val = (
                        node.value.value
                        if isinstance(node.value, ast.Constant)
                        else None
                    )
                    if val != ALLOWED_HOST_LITERAL:
                        lineno = getattr(node, "lineno", 0)
                        snippet = (
                            lines[lineno - 1].strip()
                            if 0 < lineno <= len(lines)
                            else ""
                        )
                        violations.append(
                            HostViolation(
                                file_path=display_path,
                                line_number=lineno,
                                parameter=target.id,
                                assigned_value=val,
                                line_content=snippet,
                            )
                        )

    return violations


def scan_target_test_files(
    repo_root: Path, target_dirs: tuple[str, ...]
) -> list[HostViolation]:
    """Scans all eligible test files across target directories for violations."""
    files_to_scan = collect_target_python_files(repo_root, target_dirs)
    all_violations: list[HostViolation] = []
    for test_file in files_to_scan:
        try:
            content = test_file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        violations = find_hardcoded_http_host_violations(
            content, str(test_file), repo_root=repo_root
        )
        all_violations.extend(violations)
    return all_violations


def test_no_hardcoded_http_host_in_accounts_and_core() -> None:
    """Guards against hardcoded HTTP_HOST or SERVER_NAME in tests/accounts and tests/core."""
    violations = scan_target_test_files(REPO_ROOT, TARGET_DIRECTORIES)
    assert not violations, (
        f"Detected {len(violations)} hardcoded host violation(s) "
        f"across test suites:\n" + "\n".join(v.format_entry() for v in violations)
    )


def test_guard_scanner_does_not_flag_itself() -> None:
    """Verifies that the guard test file does not match its own source text."""
    current_file = Path(__file__).resolve()
    content = current_file.read_text(encoding="utf-8")
    self_violations = find_hardcoded_http_host_violations(
        content, str(current_file), repo_root=REPO_ROOT
    )
    assert not self_violations, (
        "The guard test file matched its own source text:\n"
        + "\n".join(v.format_entry() for v in self_violations)
    )


# ==============================================================================
# Synthetic Unit Tests Verifying Scanner Capabilities (Red-then-Green Invariants)
# Note: Forbidden host literals are constructed dynamically so the guard file
# does not contain any forbidden literals as plain text.
# ==============================================================================

# Dynamic construction of forbidden host literals to avoid plain text literals
_FORBIDDEN_LOCAL_HOST: str = "local" + "host"
_FORBIDDEN_LOOPBACK_IP: str = "127." + "0.0.1"
_FORBIDDEN_CUSTOM_DOMAIN: str = "example." + "org"


def test_scanner_detects_forbidden_http_host_literal(tmp_path: Path) -> None:
    """Ensures scanner catches hardcoded HTTP_HOST passed as keyword argument."""
    sample_file = tmp_path / "test_sample_bad_host.py"
    sample_code = (
        "def test_bad_host():\n"
        f'    response = client.post("/login/", HTTP_HOST="{_FORBIDDEN_LOCAL_HOST}")\n'
    )
    sample_file.write_text(sample_code, encoding="utf-8")
    violations = scan_target_test_files(tmp_path, ("",))
    assert len(violations) == 1
    assert violations[0].parameter == "HTTP_HOST"
    assert violations[0].assigned_value == _FORBIDDEN_LOCAL_HOST


def test_scanner_detects_forbidden_server_name_literal(tmp_path: Path) -> None:
    """Ensures scanner catches hardcoded SERVER_NAME passed as keyword argument."""
    sample_file = tmp_path / "test_sample_bad_server.py"
    sample_code = (
        "def test_bad_server():\n"
        f'    response = client.get("/api/", SERVER_NAME="{_FORBIDDEN_LOOPBACK_IP}")\n'
    )
    sample_file.write_text(sample_code, encoding="utf-8")
    violations = scan_target_test_files(tmp_path, ("",))
    assert len(violations) == 1
    assert violations[0].parameter == "SERVER_NAME"
    assert violations[0].assigned_value == _FORBIDDEN_LOOPBACK_IP


def test_scanner_detects_forbidden_dict_entry(tmp_path: Path) -> None:
    """Ensures scanner catches HTTP_HOST in dictionary literals."""
    sample_file = tmp_path / "test_sample_bad_dict.py"
    sample_code = (
        "def test_bad_dict():\n"
        f'    extra = {{"HTTP_HOST": "{_FORBIDDEN_CUSTOM_DOMAIN}"}}\n'
    )
    sample_file.write_text(sample_code, encoding="utf-8")
    violations = scan_target_test_files(tmp_path, ("",))
    assert len(violations) == 1
    assert violations[0].parameter == "HTTP_HOST"
    assert violations[0].assigned_value == _FORBIDDEN_CUSTOM_DOMAIN


def test_scanner_allows_default_test_host_literal(tmp_path: Path) -> None:
    """Ensures scanner cleanly allows Django standard default test host."""
    sample_file = tmp_path / "test_sample_clean.py"
    sample_code = (
        "def test_good_host():\n"
        '    response1 = client.post("/admin/login/")\n'
        f'    response2 = client.post("/admin/login/", HTTP_HOST="{ALLOWED_HOST_LITERAL}")\n'
        f'    response3 = client.get("/api/", SERVER_NAME="{ALLOWED_HOST_LITERAL}")\n'
    )
    sample_file.write_text(sample_code, encoding="utf-8")
    violations = scan_target_test_files(tmp_path, ("",))
    assert violations == []


def test_scanner_ignores_comments_and_doc_strings(tmp_path: Path) -> None:
    """Ensures comments or doc strings discussing host settings are not flagged."""
    sample_file = tmp_path / "test_sample_docs.py"
    sample_code = (
        '"""Doc string mentioning HTTP_HOST=\'local\' + \'host\' should be ignored."""\n'
        "def test_clean_doc():\n"
        '    # Comment: HTTP_HOST="local" + "host" was removed in Round 46\n'
        '    response = client.post("/admin/login/")\n'
    )
    sample_file.write_text(sample_code, encoding="utf-8")
    violations = scan_target_test_files(tmp_path, ("",))
    assert violations == []


def test_scanner_skips_pycache_and_ignored_directories(tmp_path: Path) -> None:
    """Ensures scanner ignores __pycache__, .agents, .git, and binary files."""
    pycache_dir = tmp_path / "__pycache__"
    pycache_dir.mkdir()
    pycache_file = pycache_dir / "test_cached.py"
    pycache_file.write_text(
        f'client.get("/", HTTP_HOST="{_FORBIDDEN_LOCAL_HOST}")\n',
        encoding="utf-8",
    )

    agents_dir = tmp_path / ".agents"
    agents_dir.mkdir()
    agents_file = agents_dir / "test_agent.py"
    agents_file.write_text(
        f'client.get("/", HTTP_HOST="{_FORBIDDEN_LOCAL_HOST}")\n',
        encoding="utf-8",
    )

    files = collect_target_python_files(tmp_path, ("",))
    assert pycache_file not in files
    assert agents_file not in files
