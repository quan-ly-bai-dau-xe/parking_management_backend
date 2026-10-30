"""
URL configuration for customers app.
Routes:
- api/v1/customers/summary/
- api/v1/customers/
- api/v1/customers/<int:id>/
- api/v1/customers/<int:customer_id>/vehicles/
"""

from django.urls import path

from apps.customers.views.customers import (
    CustomerDetailView,
    CustomerListCreateView,
    CustomerSummaryView,
    CustomerVehicleCreateAliasView,
)

app_name = "customers"

urlpatterns = [
    path(
        "customers/summary/",
        CustomerSummaryView.as_view(),
        name="customer-summary",
    ),
    path(
        "customers/",
        CustomerListCreateView.as_view(),
        name="customer-list-create",
    ),
    path(
        "customers/<int:id>/",
        CustomerDetailView.as_view(),
        name="customer-detail",
    ),
    path(
        "customers/<int:customer_id>/vehicles/",
        CustomerVehicleCreateAliasView.as_view(),
        name="customer-vehicle-create",
    ),
]
