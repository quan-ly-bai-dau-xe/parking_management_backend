"""Tickets views exports."""

from apps.tickets.views.tickets import (
    TicketDetailView,
    TicketListCreateView,
    TicketRenewView,
    TicketTypeListView,
)

__all__ = [
    "TicketDetailView",
    "TicketListCreateView",
    "TicketRenewView",
    "TicketTypeListView",
]
