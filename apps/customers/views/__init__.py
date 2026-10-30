"""
Views package for customers app.
"""

from apps.customers.views.customers import (
    CustomerDetailView,
    CustomerListCreateView,
    CustomerSummaryView,
    CustomerVehicleCreateAliasView,
)

__all__ = [
    "CustomerDetailView",
    "CustomerListCreateView",
    "CustomerSummaryView",
    "CustomerVehicleCreateAliasView",
]
