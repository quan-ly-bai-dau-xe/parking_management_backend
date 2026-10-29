"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""

from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path, re_path
from django.views.static import serve
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.views.health import HealthCheckView

urlpatterns: list = [
    path("admin/", admin.site.urls),
    # Health check endpoint
    path("api/health/", HealthCheckView.as_view(), name="health"),
    # API v1 routes
    path("api/v1/", include("apps.core.urls")),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/", include("apps.customers.urls")),
    path("api/v1/", include("apps.employees.urls")),
    path("api/v1/", include("apps.vehicles.urls")),
    path("api/v1/", include("apps.tickets.urls")),
    path("api/v1/parking/", include("apps.parking.urls")),
    path("api/v1/", include("apps.reports.urls")),
    # OpenAPI Schema and Swagger UI documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]

# Serve media files safely via django.views.static.serve when local storage is active (ADR-0009)
if getattr(settings, "IMAGE_STORAGE_BACKEND", "local") == "local":
    media_prefix = settings.MEDIA_URL.strip("/")
    urlpatterns += [
        re_path(
            rf"^{media_prefix}/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]

# Serve static files in development/DEBUG mode
if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()

handler404 = "apps.core.exceptions.custom_json_404"
