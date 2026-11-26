"""
Selectors for tickets app.
Provides optimized querysets with zero N+1 queries and flexible lookups.
"""

from __future__ import annotations

from typing import Any

from django.db.models import Prefetch, Q, QuerySet

from apps.tickets.models import Ticket, TicketRenewal


def get_tickets_base_queryset() -> QuerySet[Ticket]:
    """
    Returns base queryset for tickets with eager loading on all related models.
    Guarantees O(1) query complexity (Zero N+1 queries) when serializing.
    """
    renewals_prefetch = Prefetch(
        "renewals",
        queryset=TicketRenewal.objects.select_related(
            "old_slot",
            "old_slot__zone",
            "old_slot__zone__floor",
            "new_slot",
            "new_slot__zone",
            "new_slot__zone__floor",
            "old_ticket_type",
            "new_ticket_type",
            "renewed_by",
        ).order_by("-id"),
    )

    return (
        Ticket.objects.filter(deleted_at__isnull=True)
        .select_related(
            "ticket_type",
            "customer",
            "vehicle",
            "vehicle__vehicle_type",
            "slot",
            "slot__zone",
            "slot__zone__floor",
            "issued_by",
        )
        .prefetch_related(renewals_prefetch)
    )


def get_tickets_queryset(
    *,
    search: str | None = None,
    status: str | None = None,
    ticket_type: str | int | None = None,
    date_from: Any = None,
    date_to: Any = None,
    ordering: str = "-id",
) -> QuerySet[Ticket]:
    """
    Filter tickets based on search keyword, status, ticket_type, date range, and ordering.
    """
    qs = get_tickets_base_queryset()

    if search:
        search_val = search.strip()
        qs = qs.filter(
            Q(code__icontains=search_val)
            | Q(vehicle__license_plate__icontains=search_val)
            | Q(customer__full_name__icontains=search_val)
            | Q(customer__phone__icontains=search_val)
            | Q(customer__code__icontains=search_val)
        )

    if status and str(status).strip().upper() != "ALL":
        qs = qs.filter(status=str(status).strip().upper())

    if ticket_type and str(ticket_type).strip().upper() != "ALL":
        val_str = str(ticket_type).strip()
        if val_str.isdigit():
            qs = qs.filter(ticket_type_id=int(val_str))
        else:
            qs = qs.filter(ticket_type__code=val_str.upper())

    if date_from:
        qs = qs.filter(effective_from__gte=date_from)

    if date_to:
        qs = qs.filter(effective_to__lte=date_to)

    return qs.order_by(ordering)


def get_ticket_by_id(ticket_id: int) -> Ticket | None:
    """Look up an active ticket by its integer ID."""
    return get_tickets_base_queryset().filter(id=ticket_id).first()


def get_ticket_by_code(code: str) -> Ticket | None:
    """Look up an active ticket by its business code (e.g. VT0001, TK-2026-0001)."""
    return get_tickets_base_queryset().filter(code__iexact=code.strip()).first()


def get_ticket_by_lookup(lookup: str | int) -> Ticket | None:
    """
    Flexible lookup: if string is all digits or int, lookup by id;
    otherwise lookup by business code.
    """
    lookup_str = str(lookup).strip()
    if lookup_str.isdigit():
        ticket = get_ticket_by_id(int(lookup_str))
        if ticket:
            return ticket
    return get_ticket_by_code(lookup_str)
