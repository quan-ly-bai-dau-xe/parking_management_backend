"""
URL configuration for core app.
"""

from django.urls import path

from apps.core.views.administrative import (
    DistrictListView,
    ProvinceListView,
    WardListView,
)
from apps.core.views.health import HealthCheckView

urlpatterns: list = [
    path("health/", HealthCheckView.as_view(), name="health-check"),
    path(
        "administrative/provinces/",
        ProvinceListView.as_view(),
        name="administrative-provinces-list",
    ),
    path(
        "administrative/districts/",
        DistrictListView.as_view(),
        name="administrative-districts-list",
    ),
    path(
        "administrative/wards/",
        WardListView.as_view(),
        name="administrative-wards-list",
    ),
]
