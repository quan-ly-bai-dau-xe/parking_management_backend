"""
OpenAPI schema postprocessing hooks and schema enrichment utilities per TL-54, S1, and S2.
"""

from typing import Any


def postprocess_schema_descriptions(
    result: dict[str, Any], generator: Any, **kwargs: Any
) -> dict[str, Any]:
    """
    Enriches auto-generated OpenAPI schema descriptions and enforces accurate
    per-operation security requirements per TL-54, S1, and S2:
    - Global schema security: single AND requirement [{"cookieAuth": [], "csrfAuth": []}].
    - Public endpoints (health, csrf, docs): security = [].
    - Auth actions (login, logout): security = [{"csrfAuth": []}].
    - Protected read endpoints (GET): security = [{"cookieAuth": []}].
    - Protected mutating endpoints (POST, PUT, PATCH, DELETE): security = [{"cookieAuth": [], "csrfAuth": []}].
    - Enriches NullEnum and PaginatedSessionListItemList with clear human-readable descriptions.
    """
    # 1. Global schema security: session cookie AND CSRF token in a single requirement object
    result["security"] = [{"cookieAuth": [], "csrfAuth": []}]

    # 2. Known public and auth endpoint classifications
    public_exact_paths = {
        "/api/health/",
        "/api/v1/health/",
        "/api/v1/auth/csrf/",
    }
    csrf_only_operations = {
        ("post", "/api/v1/auth/login/"),
        ("post", "/api/v1/auth/logout/"),
    }

    # 3. Enforce per-operation security requirements across all paths
    for path, path_item in result.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            m = method.lower()
            if m not in ("get", "post", "put", "patch", "delete", "options", "head"):
                continue

            # Public paths (health, csrf, and docs paths if present)
            if (
                path in public_exact_paths
                or path.startswith("/api/docs/")
                or path.startswith("/api/schema/")
                or path.startswith("/api/redoc/")
            ):
                operation["security"] = []
            # Auth actions requiring CSRF header only
            elif (m, path) in csrf_only_operations:
                operation["security"] = [{"csrfAuth": []}]
            # Protected read operations requiring session cookie only
            elif m == "get":
                operation["security"] = [{"cookieAuth": []}]
            # Protected mutating operations requiring session cookie AND CSRF header
            else:
                operation["security"] = [{"cookieAuth": [], "csrfAuth": []}]

    # 4. Enforce descriptions on specific reusable schema components
    schemas = result.get("components", {}).get("schemas", {})
    if "NullEnum" in schemas and not schemas["NullEnum"].get("description"):
        schemas["NullEnum"]["description"] = (
            "Giá trị null đại diện cho trường hợp không có dữ liệu hoặc trường tùy chọn chưa được thiết lập."
        )
    if "PaginatedSessionListItemList" in schemas and not schemas[
        "PaginatedSessionListItemList"
    ].get("description"):
        schemas["PaginatedSessionListItemList"]["description"] = (
            "Danh sách các phiên đỗ xe (SessionListItem) được phân trang theo chuẩn StandardResultsSetPagination."
        )

    return result
