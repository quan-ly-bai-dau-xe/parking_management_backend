"""
Vehicle domain serializers package.
"""

from apps.vehicles.serializers.types import VehicleTypeSerializer
from apps.vehicles.serializers.vehicles import (
    VehicleCreateSerializer,
    VehicleDeleteSuccessSerializer,
    VehicleDetailSerializer,
    VehicleFilterSerializer,
    VehicleListSerializer,
    VehicleSummarySerializer,
    VehicleUpdateSerializer,
)

__all__ = [
    "VehicleTypeSerializer",
    "VehicleListSerializer",
    "VehicleDetailSerializer",
    "VehicleCreateSerializer",
    "VehicleUpdateSerializer",
    "VehicleSummarySerializer",
    "VehicleFilterSerializer",
    "VehicleDeleteSuccessSerializer",
]
