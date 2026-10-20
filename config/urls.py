"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
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

# Serve media files in local development/DEBUG mode only (ADR-0007)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "apps.core.exceptions.custom_json_404"
