"""
Selectors for vehicle types.
Provides queries for active car-only vehicle types (CAR, EV).
"""

from django.db.models import QuerySet

from apps.vehicles.models import VehicleType

CAR_ONLY_CODES = ("CAR", "EV")


def get_vehicle_types() -> QuerySet[VehicleType]:
    """
    Retrieve all active vehicle types strictly filtered to Car-only fleet (CAR, EV).
    Motorbikes are explicitly excluded per SRS v4.1, TL-09, TL-20, TL-35, OQ-49.
    """
    return VehicleType.objects.filter(
        deleted_at__isnull=True,
        code__in=CAR_ONLY_CODES,
    ).order_by("id")
