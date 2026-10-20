"""
URL configuration for core app.
"""

from django.urls import path

from apps.core.views.health import HealthCheckView

urlpatterns: list = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
]
