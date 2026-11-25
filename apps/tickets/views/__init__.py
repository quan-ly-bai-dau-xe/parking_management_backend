"""Tickets views exports."""

from apps.tickets.views.tickets import (
    TicketDetailUpdateDeleteView,
    TicketListCreateView,
    TicketRenewView,
    TicketTypeListView,
)

# Alias for backward compatibility
TicketDetailView = TicketDetailUpdateDeleteView

__all__ = [
    "TicketDetailUpdateDeleteView",
    "TicketDetailView",
    "TicketListCreateView",
    "TicketRenewView",
    "TicketTypeListView",
]
