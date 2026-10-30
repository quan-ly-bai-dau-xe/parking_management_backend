"""
Selectors for vehicles.
Provides zero-N+1 querysets, summary metrics, and detail retrieval with optimistic concurrency tokens.
"""

from __future__ import annotations

import datetime
from datetime import timedelta

from django.conf import settings
from django.db.models import (
    Case,
    CharField,
    Count,
    Exists,
    F,
    IntegerField,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.db.models.functions import Coalesce, Concat
from django.utils import timezone
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.parking.models import ParkingSlot, VehicleEntryExitLog
from apps.parking.selectors.search import escape_like
from apps.parking.services.ocr import PlateRecognizer
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle

ALLOWED_ORDERING_FIELDS = {
    "id",
    "-id",
    "code",
    "-code",
    "license_plate",
    "-license_plate",
    "created_at",
    "-created_at",
    "ticket_expires_at",
    "-ticket_expires_at",
}


def get_representative_ticket_subquery(
    now: datetime.datetime | None = None,
) -> QuerySet[Ticket]:
    """
    Subquery base for vehicle's unified representative ticket (TL-28.1, OQ-52).
    Two-tier priority:
      Tier 1: Active unexpired ticket (status in ['ACTIVE', 'RENEWING'] and effective_to >= now).
      Tier 2: Most recent non-deleted, non-CANCELLED ticket by effective_to DESC, id DESC.
    Returns None / empty if vehicle has no tickets or only CANCELLED tickets.
    """
    current_time = now or timezone.now()
    return (
        Ticket.objects.filter(
            vehicle_id=OuterRef("pk"),
            deleted_at__isnull=True,
        )
        .exclude(status="CANCELLED")
        .order_by(
            Case(
                When(
                    status__in=["ACTIVE", "RENEWING"],
                    effective_to__gte=current_time,
                    then=Value(0),
                ),
                default=Value(1),
                output_field=IntegerField(),
            ),
            "-effective_to",
            "-id",
        )
    )


def get_vehicles_queryset(
    code: str | None = None,
    plate: str | None = None,
    customer: str | None = None,
    vehicle_type: str | None = None,
    ticket_type: str | None = None,
    status_filter: str | None = None,
    ticket_state: str | None = None,
    ordering: str | None = None,
    now: datetime.datetime | None = None,
) -> QuerySet[Vehicle]:
    """
    Build optimized QuerySet for vehicle list view and export.
    Enforces zero-N+1 query design using select_related and SQL subqueries/annotations.
    Derived status adheres to TL-28.2 without redundant database columns.
    Unified representative ticket state adheres to TL-28.1 / TL-28.3 / OQ-52.
    """
    current_time = now or timezone.now()
    expiring_soon_days = getattr(settings, "TICKET_EXPIRING_SOON_DAYS", 7)
    expiring_soon_window = current_time + timedelta(days=expiring_soon_days)

    # Subquery base for representative ticket (SOT)
    rep_ticket_base = get_representative_ticket_subquery(now=current_time)

    rep_ticket_id = Subquery(rep_ticket_base.values("id")[:1])
    rep_ticket_effective_to = Subquery(rep_ticket_base.values("effective_to")[:1])
    rep_ticket_effective_from = Subquery(rep_ticket_base.values("effective_from")[:1])
    rep_ticket_type_code = Subquery(rep_ticket_base.values("ticket_type__code")[:1])
    rep_ticket_type_name = Subquery(rep_ticket_base.values("ticket_type__name")[:1])

    # Subquery conditions for derived status and current parking slot (TL-28.2)
    has_open_session = Exists(
        VehicleEntryExitLog.objects.filter(
            vehicle_id=OuterRef("pk"),
            exit_time__isnull=True,
        )
    )

    open_slot_label = Subquery(
        VehicleEntryExitLog.objects.filter(
            vehicle_id=OuterRef("pk"),
            exit_time__isnull=True,
            slot__isnull=False,
        )
        .annotate(
            label=Concat(
                Value("Khu "),
                F("slot__zone__code"),
                Value(" · "),
                F("slot__zone__floor__name"),
                Value(" · Slot "),
                F("slot__code"),
                output_field=CharField(),
            )
        )
        .values("label")[:1]
    )

    ticket_slot_label = Subquery(
        rep_ticket_base.filter(
            status__in=["ACTIVE", "RENEWING"],
            effective_to__gte=current_time,
            slot__isnull=False,
        )
        .annotate(
            label=Concat(
                Value("Khu "),
                F("slot__zone__code"),
                Value(" · "),
                F("slot__zone__floor__name"),
                Value(" · Slot "),
                F("slot__code"),
                output_field=CharField(),
            )
        )
        .values("label")[:1]
    )

    qs = (
        Vehicle.objects.filter(deleted_at__isnull=True)
        .select_related("customer", "vehicle_type")
        .annotate(
            has_open_session=has_open_session,
            rep_ticket_id=rep_ticket_id,
            rep_ticket_effective_to=rep_ticket_effective_to,
            rep_ticket_effective_from=rep_ticket_effective_from,
            rep_ticket_type_code=rep_ticket_type_code,
            rep_ticket_type_name=rep_ticket_type_name,
        )
        .annotate(
            rep_ticket_state=Case(
                When(rep_ticket_effective_to__isnull=True, then=Value("none")),
                When(rep_ticket_effective_to__lt=current_time, then=Value("expired")),
                When(
                    rep_ticket_effective_to__lte=expiring_soon_window,
                    then=Value("expiring_soon"),
                ),
                default=Value("valid"),
                output_field=CharField(),
            ),
        )
        .annotate(
            status_code=Case(
                When(has_open_session=True, then=Value("parked")),
                When(
                    rep_ticket_state__in=["valid", "expiring_soon"],
                    then=Value("active"),
                ),
                default=Value("left"),
                output_field=CharField(),
            ),
            status_display=Case(
                When(has_open_session=True, then=Value("Đang đỗ")),
                When(
                    rep_ticket_state__in=["valid", "expiring_soon"],
                    then=Value("Đang hoạt động"),
                ),
                default=Value("Đã rời bãi"),
                output_field=CharField(),
            ),
            current_slot=Coalesce(open_slot_label, ticket_slot_label),
        )
    )

    # 1. Multi-filter criteria
    if code and code.strip():
        qs = qs.filter(code__ilike=f"%{escape_like(code.strip())}%")

    if plate and plate.strip():
        norm_plate = PlateRecognizer.normalize_plate(plate.strip())
        qs = qs.filter(license_plate_norm__ilike=f"%{escape_like(norm_plate)}%")

    if customer and customer.strip():
        clean_cust = escape_like(customer.strip())
        qs = qs.filter(
            Q(customer__code__ilike=f"%{clean_cust}%")
            | Q(customer__full_name__ilike=f"%{clean_cust}%")
        )

    if vehicle_type and vehicle_type.strip():
        qs = qs.filter(vehicle_type__code__iexact=vehicle_type.strip())

    if ticket_type and ticket_type.strip():
        qs = qs.filter(rep_ticket_type_code__iexact=ticket_type.strip())

    # 2. Filter by runtime derived parking status (TL-28.2)
    if status_filter:
        clean_status = status_filter.strip().lower()
        if clean_status == "parked":
            qs = qs.filter(has_open_session=True)
        elif clean_status == "active":
            qs = qs.filter(
                has_open_session=False,
                rep_ticket_state__in=["valid", "expiring_soon"],
            )
        elif clean_status == "left":
            qs = qs.filter(
                has_open_session=False,
                rep_ticket_state__in=["expired", "none"],
            )

    # 3. Filter by runtime derived ticket state (Single Source of Truth)
    if ticket_state:
        clean_state = ticket_state.strip().lower()
        if clean_state in ("valid", "expiring_soon", "expired", "none"):
            qs = qs.filter(rep_ticket_state=clean_state)

    # 4. Deterministic ordering
    if ordering:
        clean_ord = ordering.strip()
        if clean_ord == "ticket_expires_at":
            qs = qs.order_by(F("rep_ticket_effective_to").asc(nulls_last=True), "-id")
        elif clean_ord == "-ticket_expires_at":
            qs = qs.order_by(F("rep_ticket_effective_to").desc(nulls_last=True), "-id")
        elif clean_ord in ALLOWED_ORDERING_FIELDS:
            qs = qs.order_by(clean_ord)
        else:
            qs = qs.order_by("-id")
    else:
        qs = qs.order_by("-id")

    return qs


def get_vehicle_by_id(vehicle_id: int, now: datetime.datetime | None = None) -> Vehicle:
    """
    Retrieve full vehicle detail by ID.
    Populates owner block (including total registered vehicles count), representative ticket block,
    current parking slot label, and row_version token for optimistic concurrency.
    Raises HTTP 404 (MSG-4.4.1-M01) if vehicle is not found or soft-deleted.
    """
    current_time = now or timezone.now()

    vehicle = (
        Vehicle.objects.filter(id=vehicle_id, deleted_at__isnull=True)
        .select_related("customer", "vehicle_type")
        .first()
    )

    if not vehicle:
        raise BusinessAPIException(
            code="MSG-4.4.1-M01",
            message="Không tìm thấy dữ liệu",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # 1. Total registered vehicles by this customer (Owner block metric)
    registered_count = Vehicle.objects.filter(
        customer_id=vehicle.customer_id,
        deleted_at__isnull=True,
    ).count()
    vehicle._registered_vehicles_count = registered_count  # type: ignore[attr-defined]

    # 2. Open parking session check for active lot presence
    open_session = (
        VehicleEntryExitLog.objects.filter(
            vehicle_id=vehicle.id,
            exit_time__isnull=True,
        )
        .select_related("slot", "slot__zone", "slot__zone__floor")
        .first()
    )

    # 3. Representative ticket matching the 2-tier priority (TL-28.1, TL-28.3, OQ-52)
    rep_ticket = (
        Ticket.objects.filter(
            vehicle_id=vehicle.id,
            deleted_at__isnull=True,
        )
        .exclude(status="CANCELLED")
        .order_by(
            Case(
                When(
                    status__in=["ACTIVE", "RENEWING"],
                    effective_to__gte=current_time,
                    then=Value(0),
                ),
                default=Value(1),
                output_field=IntegerField(),
            ),
            "-effective_to",
            "-id",
        )
        .select_related("ticket_type", "slot", "slot__zone", "slot__zone__floor")
        .first()
    )

    has_open = open_session is not None
    has_valid_tkt = (
        rep_ticket is not None
        and rep_ticket.status in ("ACTIVE", "RENEWING")
        and rep_ticket.effective_to >= current_time
    )

    if has_open:
        vehicle.status_code = "parked"  # type: ignore[attr-defined]
        vehicle.status_display = "Đang đỗ"  # type: ignore[attr-defined]
    elif has_valid_tkt:
        vehicle.status_code = "active"  # type: ignore[attr-defined]
        vehicle.status_display = "Đang hoạt động"  # type: ignore[attr-defined]
    else:
        vehicle.status_code = "left"  # type: ignore[attr-defined]
        vehicle.status_display = "Đã rời bãi"  # type: ignore[attr-defined]

    target_slot: ParkingSlot | None = None
    if open_session and open_session.slot:
        target_slot = open_session.slot
    elif rep_ticket and rep_ticket.slot and has_valid_tkt:
        target_slot = rep_ticket.slot

    if target_slot:
        slot_label = (
            f"Khu {target_slot.zone.code} · "
            f"{target_slot.zone.floor.name} · "
            f"Slot {target_slot.code}"
        )
        vehicle.current_slot = slot_label  # type: ignore[attr-defined]
    else:
        vehicle.current_slot = None  # type: ignore[attr-defined]

    vehicle._representative_ticket = rep_ticket  # type: ignore[attr-defined]
    vehicle._latest_ticket = rep_ticket  # type: ignore[attr-defined]
    return vehicle


def get_vehicles_summary(
    customer: str | None = None,
    vehicle_type: str | None = None,
    now: datetime.datetime | None = None,
) -> dict[str, int]:
    """
    Calculate the 4 KPI summary counts for the dashboard cards:
    - total_vehicles: Count of all active non-deleted vehicles matching filters.
    - active_vehicles: Count of vehicles parked in lot or having valid/expiring_soon ticket.
    - expiring_soon_tickets: Count of vehicles with representative ticket expiring within 7 days.
    - expired_tickets: Count of vehicles having an expired representative ticket.
    Directly leverages get_vehicles_queryset for 100% agreement between KPI cards and list filters.
    """
    current_time = now or timezone.now()

    base_qs = get_vehicles_queryset(
        customer=customer,
        vehicle_type=vehicle_type,
        now=current_time,
    )

    metrics = base_qs.aggregate(
        total_vehicles=Count("id"),
        active_vehicles=Count(
            "id",
            filter=Q(has_open_session=True)
            | Q(rep_ticket_state__in=["valid", "expiring_soon"]),
        ),
        expiring_soon_tickets=Count("id", filter=Q(rep_ticket_state="expiring_soon")),
        expired_tickets=Count("id", filter=Q(rep_ticket_state="expired")),
    )

    return {
        "total_vehicles": metrics["total_vehicles"] or 0,
        "active_vehicles": metrics["active_vehicles"] or 0,
        "expiring_soon_tickets": metrics["expiring_soon_tickets"] or 0,
        "expired_tickets": metrics["expired_tickets"] or 0,
    }
