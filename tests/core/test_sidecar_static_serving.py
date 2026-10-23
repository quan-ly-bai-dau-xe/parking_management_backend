"""
Unit tests for W1: Sidecar static assets serving in DEBUG mode.
Verifies that Swagger UI, ReDoc, and drf-spectacular-sidecar static assets
return HTTP 200 in DEBUG mode, preventing blank documentation pages.
"""

import importlib

import pytest
from django.test import Client
from django.urls import clear_url_caches


@pytest.fixture(autouse=True)
def reset_urls_after_test():
    """Ensure URL caches and config.urls module are restored after each test."""
    yield
    clear_url_caches()
    import config.urls

    importlib.reload(config.urls)
    clear_url_caches()


@pytest.fixture(autouse=True)
def ensure_sample_data():
    """Bypasses database seed fixture since static assets serving tests do not access DB."""
    return


SIDECAR_STATIC_URLS = [
    "/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui.css",
    "/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-bundle.js",
    "/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-standalone-preset.js",
    "/static/drf_spectacular_sidecar/swagger-ui-dist/favicon-32x32.png",
    "/static/drf_spectacular_sidecar/redoc/bundles/redoc.standalone.js",
]

DOCS_PAGE_URLS = [
    "/api/docs/",
    "/api/redoc/",
    "/api/schema/",
]


def test_sidecar_static_assets_return_200_in_debug(settings):
    """
    W1: Swagger UI / ReDoc static assets from drf-spectacular-sidecar
    must return HTTP 200 under DEBUG=True.
    """
    settings.DEBUG = True
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

    import config.urls

    importlib.reload(config.urls)
    clear_url_caches()

    client = Client()

    # Documentation entry pages must return 200
    for page_url in DOCS_PAGE_URLS:
        response = client.get(page_url)
        assert response.status_code == 200, (
            f"Expected 200 for {page_url}, got {response.status_code}"
        )

    # Sidecar static assets must return 200
    for asset_url in SIDECAR_STATIC_URLS:
        response = client.get(asset_url)
        assert response.status_code == 200, (
            f"Expected 200 for {asset_url}, got {response.status_code}"
        )


def test_sidecar_static_assets_content_type_in_debug(settings):
    """
    W1: Sidecar static assets must be served with appropriate MIME types.
    """
    settings.DEBUG = True
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

    import config.urls

    importlib.reload(config.urls)
    clear_url_caches()

    client = Client()

    css_resp = client.get(
        "/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui.css"
    )
    assert css_resp.status_code == 200
    assert "text/css" in css_resp.headers.get("Content-Type", "")

    js_resp = client.get(
        "/static/drf_spectacular_sidecar/swagger-ui-dist/swagger-ui-bundle.js"
    )
    assert js_resp.status_code == 200
    assert "javascript" in js_resp.headers.get("Content-Type", "")


def test_sidecar_static_assets_not_served_in_production(settings):
    """
    W1: In production (DEBUG=False), staticfiles_urlpatterns is not attached,
    so static assets are not served by Django's WSGI application.
    """
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = ["localhost", "127.0.0.1", "testserver"]

    import config.urls

    importlib.reload(config.urls)
    clear_url_caches()

    client = Client()

    for asset_url in SIDECAR_STATIC_URLS:
        response = client.get(asset_url)
        assert response.status_code == 404, (
            f"Expected 404 for {asset_url} in DEBUG=False, got {response.status_code}"
        )
