"""
Unit and schema validation tests for Round 47 Swagger/OpenAPI fixes (W2, W3, W4, W5).
Verifies:
- W2: 403 response with PROP-4.1-P06 on login & logout, Retry-After header on login 429
- W3: csrfAuth apiKey security scheme (header X-CSRFToken) and step-by-step description
- W4: summary/description/503 example on health endpoints, descriptions for NullEnum & PaginatedSessionListItemList
- W5: valid CSRF_FAILURE_VIEW path in README and documentation files
"""

from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from drf_spectacular.generators import SchemaGenerator

from apps.core.messages import ALL_MESSAGES


@pytest.fixture(autouse=True)
def ensure_sample_data():
    """Bypasses database seed fixture since schema tests do not access DB."""
    return


@pytest.fixture(scope="module")
def openapi_schema():
    """Generates the OpenAPI schema once for this test module."""
    generator = SchemaGenerator()
    return generator.get_schema(public=True)


def test_w2_login_and_logout_403_prop_4_1_p06(openapi_schema):
    """
    W2: Verify POST /api/v1/auth/login/ and POST /api/v1/auth/logout/ document
    HTTP 403 response with PROP-4.1-P06 verbatim error envelope example.
    """
    paths = openapi_schema["paths"]
    expected_msg = ALL_MESSAGES["PROP-4.1-P06"]

    # Login 403
    login_responses = paths["/api/v1/auth/login/"]["post"]["responses"]
    assert "403" in login_responses, "POST /api/v1/auth/login/ must document HTTP 403"
    login_403_str = str(login_responses["403"])
    assert "PROP-4.1-P06" in login_403_str, "Login 403 must reference PROP-4.1-P06"
    assert expected_msg in login_403_str, (
        f"Login 403 must contain verbatim message '{expected_msg}'"
    )

    # Logout 403
    logout_responses = paths["/api/v1/auth/logout/"]["post"]["responses"]
    assert "403" in logout_responses, "POST /api/v1/auth/logout/ must document HTTP 403"
    logout_403_str = str(logout_responses["403"])
    assert "PROP-4.1-P06" in logout_403_str, "Logout 403 must reference PROP-4.1-P06"
    assert expected_msg in logout_403_str, (
        f"Logout 403 must contain verbatim message '{expected_msg}'"
    )


def test_w2_login_429_retry_after_header(openapi_schema):
    """
    W2: Verify POST /api/v1/auth/login/ documents Retry-After header on HTTP 429 response.
    """
    login_responses = openapi_schema["paths"]["/api/v1/auth/login/"]["post"][
        "responses"
    ]
    assert "429" in login_responses, "POST /api/v1/auth/login/ must document HTTP 429"
    resp_429 = login_responses["429"]
    assert "headers" in resp_429, "HTTP 429 response must contain 'headers' object"
    assert "Retry-After" in resp_429["headers"], (
        "HTTP 429 response headers must document 'Retry-After'"
    )


def test_w3_csrf_security_scheme_and_description(openapi_schema):
    """
    W3: Verify csrfAuth security scheme is configured in components and active in security list,
    and step-by-step instructions appear at the top of description.
    """
    components = openapi_schema.get("components", {})
    sec_schemes = components.get("securitySchemes", {})
    assert "csrfAuth" in sec_schemes, (
        "components.securitySchemes must include 'csrfAuth'"
    )

    csrf_scheme = sec_schemes["csrfAuth"]
    assert csrf_scheme.get("type") == "apiKey", "csrfAuth type must be 'apiKey'"
    assert csrf_scheme.get("name") == "X-CSRFToken", (
        "csrfAuth header name must be 'X-CSRFToken'"
    )
    assert csrf_scheme.get("in") == "header", "csrfAuth location must be 'header'"

    # Verify SECURITY list in schema
    security = openapi_schema.get("security", [])
    csrf_in_security = any("csrfAuth" in item for item in security)
    assert csrf_in_security, "Top-level security requirement must include csrfAuth"

    # Verify step-by-step instructions in info.description
    info_desc = openapi_schema.get("info", {}).get("description", "")
    assert "GET /api/v1/auth/csrf/" in info_desc, (
        "OpenAPI description must instruct calling GET /api/v1/auth/csrf/"
    )
    assert "X-CSRFToken" in info_desc, (
        "OpenAPI description must explain X-CSRFToken usage"
    )


def test_w4_health_endpoints_summary_description_and_503(openapi_schema):
    """
    W4: Verify /api/health/ and /api/v1/health/ have summary, description mentioning both
    paths are intentionally provided, and an HTTP 503 response example.
    """
    paths = openapi_schema["paths"]
    for path in ["/api/health/", "/api/v1/health/"]:
        assert path in paths, f"{path} must be present in OpenAPI schema"
        operation = paths[path]["get"]
        assert operation.get("summary"), f"{path} must have a non-empty summary"
        desc = operation.get("description", "")
        assert "/api/health/" in desc and "/api/v1/health/" in desc, (
            f"{path} description must explicitly mention both /api/health/ and /api/v1/health/ are intentionally provided"
        )
        assert "503" in operation["responses"], (
            f"{path} must document HTTP 503 response"
        )
        resp_503 = operation["responses"]["503"]
        assert "examples" in resp_503 or "content" in resp_503, (
            f"{path} 503 response must have examples"
        )


def test_w4_schema_descriptions_null_enum_and_paginated_session(openapi_schema):
    """
    W4: Verify NullEnum and PaginatedSessionListItemList have human-readable descriptions
    and PaginatedSessionListItemList preserves its pagination properties.
    """
    schemas = openapi_schema.get("components", {}).get("schemas", {})

    assert "NullEnum" in schemas, "NullEnum must exist in components.schemas"
    assert schemas["NullEnum"].get("description"), (
        "NullEnum must carry a human-readable description"
    )

    assert "PaginatedSessionListItemList" in schemas, (
        "PaginatedSessionListItemList must exist in components.schemas"
    )
    paginated = schemas["PaginatedSessionListItemList"]
    assert paginated.get("description"), (
        "PaginatedSessionListItemList must carry a human-readable description"
    )
    assert "properties" in paginated, (
        "PaginatedSessionListItemList must preserve 'properties'"
    )
    for prop in ["count", "next", "previous", "results"]:
        assert prop in paginated["properties"], (
            f"PaginatedSessionListItemList properties must include '{prop}'"
        )


def test_w5_csrf_failure_view_paths():
    """
    W5: Verify README.md and documentation do not contain stale module path
    apps.core.exceptions.custom_csrf_failure_view.
    """
    base_dir = Path(settings.BASE_DIR)

    # README.md
    readme_text = (base_dir / "README.md").read_text(encoding="utf-8")
    assert "apps.core.exceptions.custom_csrf_failure_view" not in readme_text, (
        "README.md must not reference stale apps.core.exceptions.custom_csrf_failure_view"
    )
    assert "apps.accounts.views.csrf.custom_csrf_failure_view" in readme_text, (
        "README.md must reference correct apps.accounts.views.csrf.custom_csrf_failure_view"
    )

    # 01-decision-log.md
    decision_log_path = base_dir / "docs" / "requirements" / "01-decision-log.md"
    if decision_log_path.exists():
        decision_log = decision_log_path.read_text(encoding="utf-8")
        assert "apps.core.exceptions.custom_csrf_failure_view" not in decision_log, (
            "01-decision-log.md must not reference stale apps.core.exceptions.custom_csrf_failure_view"
        )


EXPECTED_OPERATION_SECURITY: dict[tuple[str, str], list[Any]] = {
    # Public operations: require nothing
    ("GET", "/api/health/"): [],
    ("GET", "/api/v1/health/"): [],
    ("GET", "/api/v1/auth/csrf/"): [],
    # Auth actions: require CSRF header only
    ("POST", "/api/v1/auth/login/"): [{"csrfAuth": []}],
    ("POST", "/api/v1/auth/logout/"): [{"csrfAuth": []}],
    # Protected read operations: require session cookie only
    ("GET", "/api/v1/auth/me/"): [{"cookieAuth": []}],
    ("GET", "/api/v1/parking/gates/"): [{"cookieAuth": []}],
    ("GET", "/api/v1/parking/sessions/"): [{"cookieAuth": []}],
    ("GET", "/api/v1/parking/sessions/{id}/"): [{"cookieAuth": []}],
    ("GET", "/api/v1/parking/vehicle-lookup/"): [{"cookieAuth": []}],
    ("GET", "/api/v1/parking/vehicle-search/"): [{"cookieAuth": []}],
    # Protected mutating operations: require session cookie AND CSRF header in single dict
    ("POST", "/api/v1/parking/plate-scans/"): [{"cookieAuth": [], "csrfAuth": []}],
    ("POST", "/api/v1/parking/sessions/check-in/"): [
        {"cookieAuth": [], "csrfAuth": []}
    ],
    ("POST", "/api/v1/parking/sessions/check-out/"): [
        {"cookieAuth": [], "csrfAuth": []}
    ],
}


def test_s1_per_operation_security_requirements(openapi_schema):
    """
    S1: Verify all operations in generated OpenAPI schema strictly match their required
    security scheme specifications without inheriting inaccurate global OR pairs.
    """
    # 1. Verify global schema security: single AND requirement object
    assert openapi_schema.get("security") == [{"cookieAuth": [], "csrfAuth": []}], (
        "Root OpenAPI security must be a single requirement object with both cookieAuth and csrfAuth (AND)"
    )

    # 2. Collect all operations in paths
    actual_operations = {}
    for path, path_item in openapi_schema.get("paths", {}).items():
        for method in ["get", "post", "put", "patch", "delete", "options", "head"]:
            if method in path_item:
                actual_operations[(method.upper(), path)] = path_item[method].get(
                    "security", []
                )

    # 3. Verify exact operation coverage
    assert set(actual_operations.keys()) == set(EXPECTED_OPERATION_SECURITY.keys()), (
        f"Mismatch between schema operations and expected table: "
        f"extra={set(actual_operations.keys()) - set(EXPECTED_OPERATION_SECURITY.keys())}, "
        f"missing={set(EXPECTED_OPERATION_SECURITY.keys()) - set(actual_operations.keys())}"
    )

    # 4. Verify each operation's security matches expected requirement
    mismatches = []
    for op_key, expected_sec in EXPECTED_OPERATION_SECURITY.items():
        actual_sec = actual_operations.get(op_key)
        if actual_sec != expected_sec:
            mismatches.append(
                f"{op_key[0]} {op_key[1]}: expected {expected_sec}, got {actual_sec}"
            )

    assert not mismatches, "OpenAPI operation security mismatches:\n" + "\n".join(
        mismatches
    )


def test_s2_postprocess_hook_relocation():
    """
    S2: Verify postprocess_schema_descriptions is importable from apps.core.openapi
    and no longer exists on apps.core.views.health, and POSTPROCESSING_HOOKS is updated.
    """
    # 1. Hook is importable from apps.core.openapi
    from apps.core.openapi import postprocess_schema_descriptions

    assert callable(postprocess_schema_descriptions), (
        "postprocess_schema_descriptions must be a callable"
    )
    assert postprocess_schema_descriptions.__doc__, (
        "postprocess_schema_descriptions must have a clear docstring"
    )

    # 2. Hook no longer exists on apps.core.views.health
    import apps.core.views.health as health_views

    assert not hasattr(health_views, "postprocess_schema_descriptions"), (
        "postprocess_schema_descriptions must not exist on apps.core.views.health"
    )

    # 3. HealthCheckResponseSerializer and HealthCheckView remain on apps.core.views.health
    assert hasattr(health_views, "HealthCheckResponseSerializer")
    assert hasattr(health_views, "HealthCheckView")

    # 4. Settings hook path updated
    assert (
        "apps.core.openapi.postprocess_schema_descriptions"
        in settings.SPECTACULAR_SETTINGS["POSTPROCESSING_HOOKS"]
    ), (
        "SPECTACULAR_SETTINGS['POSTPROCESSING_HOOKS'] must reference apps.core.openapi.postprocess_schema_descriptions"
    )
    assert (
        "apps.core.views.health.postprocess_schema_descriptions"
        not in settings.SPECTACULAR_SETTINGS["POSTPROCESSING_HOOKS"]
    ), (
        "SPECTACULAR_SETTINGS['POSTPROCESSING_HOOKS'] must not reference apps.core.views.health"
    )
