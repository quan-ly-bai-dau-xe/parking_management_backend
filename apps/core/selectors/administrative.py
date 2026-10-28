"""
Selectors for administrative boundary units (provinces, districts, wards).
Provides deterministic read-only queries for cascading dropdowns.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.core.models import (
    AdministrativeDistrict,
    AdministrativeProvince,
    AdministrativeWard,
)


def list_provinces() -> QuerySet[AdministrativeProvince]:
    """
    Retrieve all administrative provinces ordered deterministically by id ASC.
    Administrative tables are immutable reference tables without a deleted_at column.
    """
    return AdministrativeProvince.objects.all().order_by("id")


def list_districts(*, province_id: int) -> QuerySet[AdministrativeDistrict]:
    """
    Retrieve all administrative districts for a given province_id ordered by id ASC.
    Administrative tables are immutable reference tables without a deleted_at column.
    """
    return AdministrativeDistrict.objects.filter(province_id=province_id).order_by("id")


def list_wards(*, district_id: int) -> QuerySet[AdministrativeWard]:
    """
    Retrieve all administrative wards for a given district_id ordered by id ASC.
    Administrative tables are immutable reference tables without a deleted_at column.
    """
    return AdministrativeWard.objects.filter(district_id=district_id).order_by("id")
