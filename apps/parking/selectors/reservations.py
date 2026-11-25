"""
Selectors for SlotReservation domain (SRS 4.5.2).
Guarantees O(1) query scaling (zero N+1) via select_related.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.parking.models import SlotReservation


def get_reservations_queryset(
    customer_id: int | None = None,
    slot_id: int | None = None,
    status_filter: str | None = None,
) -> QuerySet[SlotReservation]:
    """Return active (non-deleted) SlotReservation queryset with related objects."""
    qs = SlotReservation.objects.filter(deleted_at__isnull=True).select_related(
        "slot",
        "slot__zone",
        "slot__zone__floor",
        "vehicle",
        "vehicle__vehicle_type",
        "customer",
    )

    if customer_id is not None:
        qs = qs.filter(customer_id=customer_id)

    if slot_id is not None:
        qs = qs.filter(slot_id=slot_id)

    if status_filter:
        statuses = [
            s.strip().upper() for s in str(status_filter).split(",") if s.strip()
        ]
        if statuses:
            qs = qs.filter(status__in=statuses)

    return qs.order_by("-created_at", "-id")


def get_reservation_by_id(reservation_id: int) -> SlotReservation | None:
    """Retrieve a single SlotReservation with hydrated relations."""
    return get_reservations_queryset().filter(id=reservation_id).first()
