"""
URL configuration for vehicles app.
Routes:
- api/v1/vehicle-types/
- api/v1/vehicles/
- api/v1/vehicles/summary/
- api/v1/vehicles/export/
- api/v1/vehicles/<int:id>/
"""

from django.urls import path

from apps.vehicles.views.types import VehicleTypeListView
from apps.vehicles.views.vehicles import (
    VehicleDetailUpdateDeleteView,
    VehicleExportView,
    VehicleListCreateView,
    VehicleSummaryView,
)

app_name = "vehicles"

urlpatterns = [
    path("vehicle-types/", VehicleTypeListView.as_view(), name="vehicle-types-list"),
    path("vehicles/summary/", VehicleSummaryView.as_view(), name="vehicle-summary"),
    path("vehicles/export/", VehicleExportView.as_view(), name="vehicle-export"),
    path("vehicles/", VehicleListCreateView.as_view(), name="vehicle-list-create"),
    path(
        "vehicles/<int:id>/",
        VehicleDetailUpdateDeleteView.as_view(),
        name="vehicle-detail",
    ),
]
