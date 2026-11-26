"""
URL configuration for tickets app.
Exposes endpoints for TicketType listing, Ticket CRUD, and Ticket Renewal.
"""

from django.urls import path

from apps.tickets.views.tickets import (
    TicketDetailUpdateDeleteView,
    TicketListCreateView,
    TicketRenewView,
    TicketTypeListView,
)

urlpatterns = [
    path("ticket-types/", TicketTypeListView.as_view(), name="ticket-type-list"),
    path("tickets/", TicketListCreateView.as_view(), name="ticket-list-create"),
    path(
        "tickets/<str:lookup>/",
        TicketDetailUpdateDeleteView.as_view(),
        name="ticket-detail-update-delete",
    ),
    path(
        "tickets/<str:lookup>/renew/",
        TicketRenewView.as_view(),
        name="ticket-renew",
    ),
]
