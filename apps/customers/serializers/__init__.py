"""
Serializers package for customers app.
"""

from apps.customers.serializers.customers import (
    AdministrativeDistrictSerializer,
    AdministrativeProvinceSerializer,
    AdministrativeWardSerializer,
    CustomerCreateSerializer,
    CustomerDeleteSuccessSerializer,
    CustomerDetailSerializer,
    CustomerFilterSerializer,
    CustomerListSerializer,
    CustomerSummarySerializer,
    CustomerUpdateSerializer,
    CustomerVehicleCreateSerializer,
    CustomerVehicleSubgridSerializer,
)

__all__ = [
    "AdministrativeDistrictSerializer",
    "AdministrativeProvinceSerializer",
    "AdministrativeWardSerializer",
    "CustomerCreateSerializer",
    "CustomerDeleteSuccessSerializer",
    "CustomerDetailSerializer",
    "CustomerFilterSerializer",
    "CustomerListSerializer",
    "CustomerSummarySerializer",
    "CustomerUpdateSerializer",
    "CustomerVehicleCreateSerializer",
    "CustomerVehicleSubgridSerializer",
]
