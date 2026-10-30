"""
Vehicle domain views package.
"""

from apps.vehicles.views.types import VehicleTypeListView
from apps.vehicles.views.vehicles import (
    VehicleDetailUpdateDeleteView,
    VehicleExportView,
    VehicleListCreateView,
    VehicleSummaryView,
)

__all__ = [
    "VehicleTypeListView",
    "VehicleListCreateView",
    "VehicleDetailUpdateDeleteView",
    "VehicleSummaryView",
    "VehicleExportView",
]
