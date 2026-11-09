"""
URL configuration for tickets app.
Routes:
- api/v1/ticket-types/
- api/v1/tickets/
- api/v1/tickets/<int:id>/
- api/v1/tickets/<int:id>/renew/
"""

from django.urls import path

from apps.tickets.views.tickets import (
    TicketDetailView,
    TicketListCreateView,
    TicketRenewView,
    TicketTypeListView,
)

app_name = "tickets"

urlpatterns = [
    path("ticket-types/", TicketTypeListView.as_view(), name="ticket-types-list"),
    path("tickets/", TicketListCreateView.as_view(), name="ticket-list-create"),
    path("tickets/<int:id>/", TicketDetailView.as_view(), name="ticket-detail"),
    path("tickets/<int:id>/renew/", TicketRenewView.as_view(), name="ticket-renew"),
]
