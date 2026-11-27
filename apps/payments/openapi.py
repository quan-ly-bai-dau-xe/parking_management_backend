"""
OpenAPI postprocessing hook for public VNPAY callback endpoints (ADR-0013, TL-104).
"""

from __future__ import annotations

from typing import Any

VNPAY_PUBLIC_GET_PATHS: frozenset[str] = frozenset(
    {
        "/api/v1/payments/vnpay/ipn/",
        "/api/v1/payments/vnpay/return/",
    }
)


def postprocess_vnpay_public_security(
    result: dict[str, Any], generator: Any, **kwargs: Any
) -> dict[str, Any]:
    """
    Marks VNPAY IPN and browser Return GET endpoints as public (security = [])
    in the OpenAPI schema without modifying apps/core/openapi.py.
    """
    paths = result.get("paths", {})
    for path in VNPAY_PUBLIC_GET_PATHS:
        path_item = paths.get(path)
        if isinstance(path_item, dict) and isinstance(path_item.get("get"), dict):
            path_item["get"]["security"] = []
    return result
