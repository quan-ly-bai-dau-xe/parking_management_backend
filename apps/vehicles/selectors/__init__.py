"""
Vehicle domain selectors package.
"""

from apps.vehicles.selectors.types import get_vehicle_types
from apps.vehicles.selectors.vehicles import (
    get_vehicle_by_id,
    get_vehicles_queryset,
    get_vehicles_summary,
)

__all__ = [
    "get_vehicle_types",
    "get_vehicles_queryset",
    "get_vehicle_by_id",
    "get_vehicles_summary",
]
