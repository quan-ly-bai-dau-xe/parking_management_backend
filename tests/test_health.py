"""
Tests for Health check and OpenAPI / Swagger documentation endpoints per TL-47 and TL-48.
"""

from unittest.mock import patch

import pytest
from django.db import DatabaseError
from rest_framework import status
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def test_health_check_endpoint_success():
    """Kiểm tra GET /api/health/ trả về 200 và kết nối database thành công."""
    client = APIClient()
    response = client.get("/api/health/")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {
        "status": "healthy",
        "database": "connected",
    }


def test_health_check_endpoint_database_error():
    """Kiểm tra GET /api/health/ trả về 503 khi CSDL gặp sự cố mất kết nối."""
    client = APIClient()
    with patch(
        "django.db.connection.cursor", side_effect=DatabaseError("Connection lost")
    ):
        response = client.get("/api/health/")

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["database"] == "disconnected"
    assert "Connection lost" in data["error"]


def test_openapi_schema_endpoint():
    """Kiểm tra GET /api/schema/ trả về tài liệu OpenAPI 3.0 hợp lệ."""
    client = APIClient()
    response = client.get("/api/schema/")

    assert response.status_code == status.HTTP_200_OK
    assert b"openapi: 3.0" in response.content or "openapi" in response.content.decode(
        "utf-8"
    )


def test_swagger_ui_endpoint():
    """Kiểm tra GET /api/docs/ trả về giao diện Swagger UI với sidecar offline."""
    client = APIClient()
    response = client.get("/api/docs/")

    assert response.status_code == status.HTTP_200_OK
    assert b"swagger-ui" in response.content.lower()


def test_redoc_ui_endpoint():
    """Kiểm tra GET /api/redoc/ trả về giao diện Redoc."""
    client = APIClient()
    response = client.get("/api/redoc/")

    assert response.status_code == status.HTTP_200_OK
    assert b"redoc" in response.content.lower()


@pytest.mark.parametrize(
    "method,url",
    [
        ("post", "/api/auth/login/"),
        ("get", "/api/auth/me/"),
        ("post", "/api/auth/logout/"),
        ("get", "/api/lookups/positions/"),
        ("get", "/api/lookups/vehicle-types/"),
        ("get", "/api/lookups/ticket-types/"),
        ("get", "/api/lookups/provinces/"),
        ("get", "/api/lookups/districts/"),
        ("get", "/api/lookups/wards/"),
        ("get", "/api/v1/lookups/"),
        ("get", "/api/v1/lookups/positions/"),
    ],
)
def test_removed_endpoints_return_404(method, url):
    """Xác minh tất cả các endpoint đã bị gỡ bỏ trong Round 30 (TL-48) trả về HTTP 404 Not Found."""
    client = APIClient()
    client_func = getattr(client, method)
    response = client_func(url)
    assert response.status_code == status.HTTP_404_NOT_FOUND
