"""
Host Independence Guard Test Suite.

Scans all test files under tests/ to ensure that NO test in the default test suite
depends on the developer's host machine, specific operating system commands,
PowerShell cmdlets, Docker volume counts, or hardcoded Windows drive letters.
Tests requiring host-specific tools MUST be explicitly decorated with `@pytest.mark.host`.
"""

# cspell:words childitem

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TESTS_DIR = REPO_ROOT / "tests"


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    # AST analysis operates strictly on static source code without DB connectivity
    return None


FORBIDDEN_STRING_PATTERNS: dict[str, str] = {
    "powershell": "PowerShell CLI invocation",
    "docker volume": "Docker volume host invariant assertion",
    "get-childitem": "Get-ChildItem PowerShell cmdlet",
}

# Negative lookbehind and lookahead prevent false positives on HTTP/HTTPS/file URLs
DRIVE_LETTER_PATTERN = re.compile(r"(?<![a-zA-Z0-9])[a-zA-Z]:[\\/](?!/)")


def _is_host_expr(expr: ast.AST) -> bool:
    if isinstance(expr, ast.Attribute) and expr.attr == "host":
        return True
    if isinstance(expr, ast.Name) and expr.id == "host":
        return True
    if isinstance(expr, ast.Call):
        func = expr.func
        if isinstance(func, ast.Attribute) and func.attr == "host":
            return True
        if isinstance(func, ast.Name) and func.id == "host":
            return True
    return False


def _has_host_marker(node: ast.AST) -> bool:
    decorators = getattr(node, "decorator_list", [])
    if isinstance(decorators, list):
        for decorator in decorators:
            if isinstance(decorator, ast.AST) and _is_host_expr(decorator):
                return True
    return False


def _is_module_host_marked(tree: ast.Module) -> bool:
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytestmark":
                    val = node.value
                    if _is_host_expr(val):
                        return True
                    if isinstance(val, (ast.List, ast.Tuple)):
                        for elt in val.elts:
                            if _is_host_expr(elt):
                                return True
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "pytestmark"
            and node.value is not None
        ):
            if _is_host_expr(node.value):
                return True
            if isinstance(node.value, (ast.List, ast.Tuple)):
                for elt in node.value.elts:
                    if _is_host_expr(elt):
                        return True
    return False


def find_host_dependence_violations(
    source_code: str, file_path: str = "<memory>"
) -> list[dict[str, Any]]:
    violations: list[dict[str, Any]] = []
    try:
        tree = ast.parse(source_code, filename=file_path)
    except SyntaxError:
        return violations

    if _is_module_host_marked(tree):
        return []

    host_exempt_scopes: set[ast.AST] = set()
    for n in ast.walk(tree):
        if isinstance(
            n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ) and _has_host_marker(n):
            host_exempt_scopes.add(n)
            # Exemption cascades to all nested child nodes inside the marked block
            for sub in ast.walk(n):
                host_exempt_scopes.add(sub)

    lines = source_code.splitlines()

    for node in ast.walk(tree):
        if node in host_exempt_scopes:
            continue

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            val_lower = node.value.lower()
            lineno = getattr(node, "lineno", 0)
            snippet = lines[lineno - 1].strip() if 0 < lineno <= len(lines) else ""

            for pattern, reason in FORBIDDEN_STRING_PATTERNS.items():
                if pattern in val_lower:
                    violations.append(
                        {
                            "file": file_path,
                            "line": lineno,
                            "violation": f"{reason} ({pattern!r})",
                            "snippet": snippet,
                        }
                    )

            if DRIVE_LETTER_PATTERN.search(node.value):
                violations.append(
                    {
                        "file": file_path,
                        "line": lineno,
                        "violation": f"Windows drive letter path literal in {node.value!r}",
                        "snippet": snippet,
                    }
                )

    return violations


def test_host_independence_guard_scans_all_tests_clean() -> None:
    """Ensure NO test in the default suite contains unmarked host-dependent checks."""
    all_violations: list[dict[str, Any]] = []
    test_files = sorted(
        set(TESTS_DIR.rglob("test_*.py"))
        | set(TESTS_DIR.rglob("*_test.py"))
        | set(TESTS_DIR.rglob("tests.py"))
    )

    assert len(test_files) > 0, "No test files discovered under tests/!"

    for test_file in test_files:
        if test_file.name == "test_host_independence_guard.py":
            continue

        content = test_file.read_text(encoding="utf-8", errors="ignore")
        file_violations = find_host_dependence_violations(
            content, str(test_file.relative_to(REPO_ROOT))
        )
        all_violations.extend(file_violations)

    assert all_violations == [], (
        "Found host-dependence violations in default test suite:\n"
        + "\n".join(
            f"  - {v['file']}:{v['line']} -> {v['violation']} (code: `{v['snippet']}`)"
            for v in all_violations
        )
    )


# ==============================================================================
# Synthetic Unit Tests Verifying the Guard Itself
# ==============================================================================


def test_guard_detects_powershell_invocation() -> None:
    code = """
def test_bad_powershell():
    cmd = ["powershell", "-Command", "ls"]
"""
    v = find_host_dependence_violations(code, "test_synth.py")
    assert len(v) == 1
    assert "PowerShell CLI invocation" in v[0]["violation"]


def test_guard_detects_docker_volume_command() -> None:
    code = """
def test_bad_docker_volume():
    msg = "docker volume ls -q"
"""
    v = find_host_dependence_violations(code, "test_synth.py")
    assert len(v) == 1
    assert "Docker volume host invariant" in v[0]["violation"]


def test_guard_detects_get_childitem() -> None:
    code = """
def test_bad_gci():
    script = "Get-ChildItem -Force"
"""
    v = find_host_dependence_violations(code, "test_synth.py")
    assert len(v) == 1
    assert "Get-ChildItem" in v[0]["violation"]


def test_guard_detects_windows_drive_letter() -> None:
    code = """
def test_bad_drive():
    p = "C:\\\\Users\\\\AppData"
"""
    v = find_host_dependence_violations(code, "test_synth.py")
    assert len(v) == 1
    assert "Windows drive letter" in v[0]["violation"]


def test_guard_allows_marked_host_function() -> None:
    code = """
@pytest.mark.host
def test_allowed_host_function():
    cmd = ["powershell", "Get-ChildItem"]
    vol = "docker volume inspect"
    path = "D:\\\\data"
"""
    assert len(find_host_dependence_violations(code, "test_synth.py")) == 0


def test_guard_allows_marked_host_class() -> None:
    code = """
@pytest.mark.host
class TestAllowedHostSuite:
    def test_one(self):
        cmd = ["powershell"]
    def test_two(self):
        vol = "docker volume ls"
"""
    assert len(find_host_dependence_violations(code, "test_synth.py")) == 0


def test_guard_allows_module_level_host_mark() -> None:
    code = """
pytestmark = pytest.mark.host

def test_module_allowed():
    cmd = ["powershell"]
"""
    assert len(find_host_dependence_violations(code, "test_synth.py")) == 0


def test_guard_allows_standard_urls_not_flagged_as_drive_letter() -> None:
    code = """
def test_urls():
    u1 = "https://example.com/api"
    u2 = "http://localhost:8000"
    u3 = "file:///workspace/data"
"""
    assert len(find_host_dependence_violations(code, "test_synth.py")) == 0
