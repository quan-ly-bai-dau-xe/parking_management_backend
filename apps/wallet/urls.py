"""
URL configuration for wallet & customer self-service endpoints.
"""

from django.urls import path

from apps.parking.views.reservations import (
    MeParkingSlotsView,
    MeParkingStructureView,
)
from apps.wallet.views import (
    MeNotificationListView,
    MeNotificationMarkAllReadView,
    MeNotificationMarkReadView,
    MeProfileView,
    MeTicketCancelView,
    MeTicketListCreateView,
    MeTicketTypeListView,
    MeVehicleDetailView,
    MeVehicleListCreateView,
    MeVehicleTypeListView,
    MeWalletDetailView,
    MeWalletTopupView,
    MeWalletTransactionListView,
    StaffCustomerWalletDetailView,
    StaffCustomerWalletTopupView,
    StaffCustomerWalletTransactionListView,
)

app_name = "wallet"

urlpatterns = [
    # Customer Self-Service (/api/v1/me/*)
    path("me/wallet/", MeWalletDetailView.as_view(), name="me-wallet-detail"),
    path(
        "me/wallet/transactions/",
        MeWalletTransactionListView.as_view(),
        name="me-wallet-transactions",
    ),
    path("me/wallet/topups/", MeWalletTopupView.as_view(), name="me-wallet-topups"),
    path(
        "me/notifications/",
        MeNotificationListView.as_view(),
        name="me-notifications",
    ),
    path(
        "me/notifications/read-all/",
        MeNotificationMarkAllReadView.as_view(),
        name="me-notifications-read-all",
    ),
    path(
        "me/notifications/<int:id>/read/",
        MeNotificationMarkReadView.as_view(),
        name="me-notification-read",
    ),
    path("me/profile/", MeProfileView.as_view(), name="me-profile"),
    path("me/vehicles/", MeVehicleListCreateView.as_view(), name="me-vehicles"),
    path(
        "me/vehicles/<str:lookup>/",
        MeVehicleDetailView.as_view(),
        name="me-vehicle-detail",
    ),
    path("me/tickets/", MeTicketListCreateView.as_view(), name="me-tickets"),
    path(
        "me/tickets/<str:lookup>/cancel/",
        MeTicketCancelView.as_view(),
        name="me-ticket-cancel",
    ),
    path("me/ticket-types/", MeTicketTypeListView.as_view(), name="me-ticket-types"),
    path("me/vehicle-types/", MeVehicleTypeListView.as_view(), name="me-vehicle-types"),
    path(
        "me/parking-structure/",
        MeParkingStructureView.as_view(),
        name="me-parking-structure",
    ),
    path(
        "me/parking-slots/",
        MeParkingSlotsView.as_view(),
        name="me-parking-slots",
    ),
    # Staff / Manager Customer Wallet Management (/api/v1/customers/<id>/wallet/*)
    path(
        "customers/<int:id>/wallet/",
        StaffCustomerWalletDetailView.as_view(),
        name="customer-wallet-detail",
    ),
    path(
        "customers/<int:id>/wallet/transactions/",
        StaffCustomerWalletTransactionListView.as_view(),
        name="customer-wallet-transactions",
    ),
    path(
        "customers/<int:id>/wallet/topup/",
        StaffCustomerWalletTopupView.as_view(),
        name="customer-wallet-topup",
    ),
]
