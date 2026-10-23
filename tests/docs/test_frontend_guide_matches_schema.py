"""
Schema-drift guard test suite for the Vietnamese Frontend API Guide (G3).

Validates that `docs/guides/01-frontend-api-guide.md`:
1. Documents only valid HTTP operations (method + path) present in the live OpenAPI schema
   or resolvable via Django URLconf for documentation endpoints (/api/docs/, /api/redoc/, /api/schema/).
2. Documents only valid /api/ paths present in the live OpenAPI schema or Django URL resolver.
3. Documents only valid error codes (PROP-* and MSG-*) defined in apps.core.messages.ALL_MESSAGES.
4. Fully covers all 14 OpenAPI schema paths without omissions.

Includes deliberate mismatch unit tests (Red-then-Green proof) verifying that the
validator accurately detects unknown endpoints, wrong methods, and invalid error codes.
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
from django.urls import Resolver404, resolve
from drf_spectacular.generators import SchemaGenerator

from apps.core.messages import ALL_MESSAGES

# URLs that serve Swagger/ReDoc UI and OpenAPI schema (not in schema['paths'] due to SERVE_INCLUDE_SCHEMA=False)
DOC_URLS: set[str] = {
    "/api/docs/",
    "/api/redoc/",
    "/api/schema/",
}

# Base prefixes and rewrite tokens that do not represent discrete API endpoints
PREFIX_OR_WILDCARD_PATHS: set[str] = {
    "/api",
    "/api/",
    "/api/v1",
    "/api/v1/",
}

# Regex to match HTTP operations: e.g. `POST /api/v1/auth/login/` or `GET /api/health/ HTTP/1.1`
OPERATION_PATTERN = re.compile(
    r"\b(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+`?(/api/[^\s`\"\'\)\],]+)",
    re.IGNORECASE,
)

# Regex to match Markdown table row operations: e.g. `| POST | /api/v1/auth/login/ |`
TABLE_OPERATION_PATTERN = re.compile(
    r"\|\s*`?(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)`?\s*\|\s*`?(/api/[^\s`\"\'\|]+)",
    re.IGNORECASE,
)

# Regex to match /api/... paths (including full URLs like http://127.0.0.1:8000/api/...)
PATH_PATTERN = re.compile(r"(?:https?://[^/\s`\"'\)]+)?(/api/[^\s`\"'\)\],;]+)")

# Regex to match PROP-* and MSG-* codes
CODE_PATTERN = re.compile(r"\b((?:PROP|MSG)-[A-Za-z0-9_.-]+)\b")


def _normalize_numeric_path_params(path: str) -> str:
    """Normalizes concrete numeric path segments (e.g. /sessions/51/) to OpenAPI {id} templates."""
    return re.sub(r"/\d+(?=/|$)", "/{id}", path)


def extract_documented_operations(markdown_text: str) -> set[tuple[str, str]]:
    """
    Extracts all (METHOD, /api/...) operations from markdown text.
    Normalizes HTTP method to uppercase and strips query strings and trailing punctuation from path.
    """
    operations: set[tuple[str, str]] = set()

    for pattern in (OPERATION_PATTERN, TABLE_OPERATION_PATTERN):
        for match in pattern.finditer(markdown_text):
            method = match.group(1).upper()
            raw_path = match.group(2).split("?")[0].rstrip(".,;:)\"'`")
            if raw_path.startswith("/api/"):
                normalized = _normalize_numeric_path_params(raw_path)
                operations.add((method, normalized))

    return operations


def extract_documented_paths(markdown_text: str) -> set[str]:
    """
    Extracts all documented /api/ endpoint paths from markdown text.
    Filters out prefix wildcards (e.g. /api/*, /api/:path*, /api/v1/*, /api/v1/parking/*)
    and base routing prefixes (/api, /api/v1).
    Ensures consistent trailing slash matching OpenAPI paths.
    """
    paths: set[str] = set()

    for match in PATH_PATTERN.finditer(markdown_text):
        raw_path = match.group(1).split("?")[0].rstrip(".,;:)\"'`")
        if "*" in raw_path or ":" in raw_path:
            continue
        normalized = raw_path if raw_path.endswith("/") else f"{raw_path}/"
        normalized = _normalize_numeric_path_params(normalized)
        if normalized in PREFIX_OR_WILDCARD_PATHS:
            continue
        paths.add(normalized)

    return paths


def extract_documented_codes(markdown_text: str) -> set[str]:
    """
    Extracts all PROP-* and MSG-* codes from markdown text.
    Ignores generic wildcards like 'PROP-*' or 'MSG-*'.
    """
    codes: set[str] = set()

    for match in CODE_PATTERN.finditer(markdown_text):
        code = match.group(1)
        if not code.endswith("-") and "*" not in code:
            codes.add(code)

    return codes


def validate_operations_against_schema(
    operations: Iterable[tuple[str, str]], schema: dict[str, Any]
) -> list[str]:
    """
    Validates that each (method, path) operation exists in the live OpenAPI schema
    or resolves via Django URLconf for documentation URLs.
    Returns a list of human-readable error messages (empty if all valid).
    """
    errors: list[str] = []
    schema_paths = schema.get("paths", {})

    for method, path in sorted(operations):
        if path in DOC_URLS:
            try:
                resolve(path)
            except Resolver404:
                errors.append(
                    f"Doc URL '{path}' could not be resolved by Django URLconf."
                )
        elif path not in schema_paths:
            errors.append(
                f"Endpoint '{path}' (operation {method} {path}) does not exist in OpenAPI schema."
            )
        elif method.lower() not in schema_paths[path]:
            allowed = [m.upper() for m in schema_paths[path]]
            errors.append(
                f"Method '{method}' is not allowed for '{path}' in OpenAPI schema (allowed: {allowed})."
            )

    return errors


def validate_paths_against_schema(
    paths: Iterable[str], schema: dict[str, Any]
) -> list[str]:
    """
    Validates that each documented API path exists in schema['paths'] or resolves as a doc URL.
    Returns a list of error messages (empty if all valid).
    """
    errors: list[str] = []
    schema_paths = schema.get("paths", {})

    for path in sorted(paths):
        if path in DOC_URLS:
            try:
                resolve(path)
            except Resolver404:
                errors.append(
                    f"Doc URL '{path}' could not be resolved by Django URLconf."
                )
        elif path not in schema_paths:
            errors.append(f"Path '{path}' does not exist in OpenAPI schema paths.")

    return errors


def validate_codes_against_messages(
    codes: Iterable[str], message_catalog: dict[str, str]
) -> list[str]:
    """
    Validates that each extracted error code exists in ALL_MESSAGES.
    Returns a list of error messages (empty if all valid).
    """
    errors: list[str] = []

    for code in sorted(codes):
        if code not in message_catalog:
            errors.append(
                f"Error code '{code}' does not exist in apps.core.messages.ALL_MESSAGES."
            )

    return errors


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def ensure_sample_data():
    """Bypasses database seed fixture since schema drift tests do not access DB."""
    return


@pytest.fixture(scope="module")
def guide_path() -> Path:
    """Returns the path to the Vietnamese Frontend API Guide."""
    repo_root = Path(__file__).resolve().parents[2]
    return repo_root / "docs" / "guides" / "01-frontend-api-guide.md"


@pytest.fixture(scope="module")
def guide_content(guide_path: Path) -> str:
    """Reads and returns the content of the Frontend API Guide."""
    assert guide_path.exists(), f"Guide file does not exist at {guide_path}"
    return guide_path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def openapi_schema() -> dict[str, Any]:
    """Generates the live OpenAPI schema using drf-spectacular."""
    generator = SchemaGenerator()
    return generator.get_schema(request=None, public=True)


# ---------------------------------------------------------------------------
# Live Guide Validation Tests
# ---------------------------------------------------------------------------


def test_guide_file_exists_and_non_empty(guide_path: Path, guide_content: str):
    """Verifies that the Frontend API Guide exists and has substantial content."""
    assert guide_path.is_file(), f"Expected guide file at {guide_path}"
    assert len(guide_content.strip()) > 1000, "Guide file content is too short"


def test_all_documented_operations_exist_in_schema(
    guide_content: str, openapi_schema: dict[str, Any]
):
    """
    Extracts all (method, path) operations from the guide and verifies they exist
    in the live OpenAPI schema or resolve via Django URLconf.
    """
    operations = extract_documented_operations(guide_content)
    assert operations, "No API operations found in guide"

    errors = validate_operations_against_schema(operations, openapi_schema)
    assert not errors, (
        "Documented operations do not match OpenAPI schema:\n"
        + "\n".join(f"  - {e}" for e in errors)
    )


def test_all_documented_paths_exist_in_schema(
    guide_content: str, openapi_schema: dict[str, Any]
):
    """
    Extracts all /api/ endpoint paths from the guide and verifies each one is
    registered in schema['paths'] or resolvable as a doc URL.
    """
    paths = extract_documented_paths(guide_content)
    assert paths, "No API paths found in guide"

    errors = validate_paths_against_schema(paths, openapi_schema)
    assert not errors, "Documented paths do not match OpenAPI schema:\n" + "\n".join(
        f"  - {e}" for e in errors
    )


def test_all_documented_codes_exist_in_all_messages(guide_content: str):
    """
    Extracts all PROP-* and MSG-* codes from the guide and asserts every code
    is defined in apps.core.messages.ALL_MESSAGES.
    """
    codes = extract_documented_codes(guide_content)
    assert codes, "No error codes found in guide"

    errors = validate_codes_against_messages(codes, ALL_MESSAGES)
    assert not errors, (
        "Documented error codes do not match ALL_MESSAGES catalog:\n"
        + "\n".join(f"  - {e}" for e in errors)
    )


def test_all_schema_paths_covered_in_guide(
    guide_content: str, openapi_schema: dict[str, Any]
):
    """
    Ensures bidirectional coverage: every path in OpenAPI schema['paths'] must
    be documented in the frontend guide.
    """
    documented_paths = extract_documented_paths(guide_content)
    schema_paths = set(openapi_schema.get("paths", {}).keys())

    missing_from_guide = schema_paths - documented_paths
    assert not missing_from_guide, (
        "OpenAPI schema paths missing from frontend guide:\n"
        + "\n".join(f"  - {p}" for p in sorted(missing_from_guide))
    )


# ---------------------------------------------------------------------------
# Deliberate Mismatch Tests (Red-then-Green Proof)
# ---------------------------------------------------------------------------


def test_validator_detects_deliberate_unknown_endpoint(
    openapi_schema: dict[str, Any],
):
    """
    Deliberate mismatch proof: verifies that the validator detects an unknown
    endpoint (e.g. POST /api/v1/fake-endpoint/) and reports an actionable error.
    """
    simulated_guide = """
    ## Hướng dẫn API giả định
    Endpoint không tồn tại trong hệ thống:
    POST /api/v1/fake-endpoint/ HTTP/1.1
    """
    operations = extract_documented_operations(simulated_guide)
    assert ("POST", "/api/v1/fake-endpoint/") in operations

    errors = validate_operations_against_schema(operations, openapi_schema)
    assert len(errors) == 1
    assert (
        "Endpoint '/api/v1/fake-endpoint/' (operation POST /api/v1/fake-endpoint/) does not exist"
        in errors[0]
    )


def test_validator_detects_deliberate_wrong_method(
    openapi_schema: dict[str, Any],
):
    """
    Deliberate mismatch proof: verifies that the validator detects a wrong HTTP
    method on an existing endpoint (e.g. DELETE /api/v1/auth/login/).
    """
    simulated_guide = """
    ## Phương thức không được hỗ trợ
    Thử nghiệm gọi DELETE vào endpoint đăng nhập:
    `DELETE /api/v1/auth/login/`
    """
    operations = extract_documented_operations(simulated_guide)
    assert ("DELETE", "/api/v1/auth/login/") in operations

    errors = validate_operations_against_schema(operations, openapi_schema)
    assert len(errors) == 1
    assert "Method 'DELETE' is not allowed for '/api/v1/auth/login/'" in errors[0]


def test_validator_detects_deliberate_unknown_prop_code():
    """
    Deliberate mismatch proof: verifies that the validator detects an unknown
    PROP-* error code (e.g. PROP-9.9-FAKE99).
    """
    simulated_guide = """
    | Mã lỗi | HTTP Status |
    | `PROP-9.9-FAKE99` | 400 | Mã lỗi giả định |
    """
    codes = extract_documented_codes(simulated_guide)
    assert "PROP-9.9-FAKE99" in codes

    errors = validate_codes_against_messages(codes, ALL_MESSAGES)
    assert len(errors) == 1
    assert (
        "Error code 'PROP-9.9-FAKE99' does not exist in apps.core.messages.ALL_MESSAGES"
        in errors[0]
    )


def test_validator_detects_deliberate_unknown_msg_code():
    """
    Deliberate mismatch proof: verifies that the validator detects an unknown
    MSG-* error code (e.g. MSG-9.9-FAKE99).
    """
    simulated_guide = """
    Thông báo lỗi giả mạo: mã `MSG-9.9-FAKE99` xuất hiện trên UI.
    """
    codes = extract_documented_codes(simulated_guide)
    assert "MSG-9.9-FAKE99" in codes

    errors = validate_codes_against_messages(codes, ALL_MESSAGES)
    assert len(errors) == 1
    assert (
        "Error code 'MSG-9.9-FAKE99' does not exist in apps.core.messages.ALL_MESSAGES"
        in errors[0]
    )


def test_validator_detects_deliberate_unknown_path(
    openapi_schema: dict[str, Any],
):
    """
    Deliberate mismatch proof: verifies that validate_paths_against_schema detects
    undocumented/non-existent API paths.
    """
    simulated_guide = """
    Truy cập đường dẫn: http://127.0.0.1:8000/api/v1/nonexistent-service/
    """
    paths = extract_documented_paths(simulated_guide)
    assert "/api/v1/nonexistent-service/" in paths

    errors = validate_paths_against_schema(paths, openapi_schema)
    assert len(errors) == 1
    assert (
        "Path '/api/v1/nonexistent-service/' does not exist in OpenAPI schema paths"
        in errors[0]
    )


def test_deliberate_combined_mismatches_all_caught(
    openapi_schema: dict[str, Any],
):
    """
    Deliberate combined mismatch proof:
    Verifies that when a guide snippet contains multiple deliberate errors
    (unknown endpoint, wrong method, fake MSG code, fake PROP code),
    the validator catches all 4 errors simultaneously.
    """
    simulated_guide = """
    Endpoint giả mạo: POST /api/v1/fake-endpoint/
    Sai phương thức: DELETE /api/v1/auth/login/
    Mã lỗi không tồn tại: PROP-9.9-FAKE99 và MSG-9.9-FAKE99
    """
    ops = extract_documented_operations(simulated_guide)
    codes = extract_documented_codes(simulated_guide)
    op_errors = validate_operations_against_schema(ops, openapi_schema)
    code_errors = validate_codes_against_messages(codes, ALL_MESSAGES)
    all_errors = op_errors + code_errors

    assert len(all_errors) == 4
    assert any("/api/v1/fake-endpoint/" in e for e in all_errors)
    assert any("DELETE" in e and "/api/v1/auth/login/" in e for e in all_errors)
    assert any("PROP-9.9-FAKE99" in e for e in all_errors)
    assert any("MSG-9.9-FAKE99" in e for e in all_errors)
