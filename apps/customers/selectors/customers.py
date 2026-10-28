"""
Selectors for customers.
Provides zero-N+1 querysets, status summary KPI metrics, and detail retrieval with optimistic concurrency tokens.
"""

from __future__ import annotations

import datetime
import math
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import (
    Case,
    CharField,
    Count,
    Exists,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Value,
    When,
)
from django.utils import timezone
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer
from apps.parking.selectors.search import escape_like
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle
from apps.vehicles.selectors.vehicles import get_representative_ticket_subquery

ALLOWED_ORDERING_FIELDS = {
    "id",
    "-id",
    "code",
    "-code",
    "full_name",
    "-full_name",
    "created_at",
    "-created_at",
    "row_version",
    "-row_version",
}


def get_customers_queryset(
    filters: dict[str, Any] | None = None,
    ordering: str | None = None,
    now: datetime.datetime | None = None,
    code: str | None = None,
    name: str | None = None,
    phone: str | None = None,
    identity_card: str | None = None,
    status_filter: str | None = None,
) -> QuerySet[Customer]:
    """
    Build optimized QuerySet for customer list view.
    Enforces zero-N+1 query design using Count and Exists subqueries.
    Provides filtering by code, name, phone, identity_card, and status.
    """
    current_time = now or timezone.now()
    filters_dict = filters or {}

    # Read criteria from kwargs or filters dictionary
    code_val = code or filters_dict.get("code")
    name_val = name or filters_dict.get("name") or filters_dict.get("full_name")
    phone_val = phone or filters_dict.get("phone")
    id_card_val = (
        identity_card
        or filters_dict.get("identity_card")
        or filters_dict.get("identity_card_number")
    )
    status_val = status_filter or filters_dict.get("status")
    ordering_val = ordering or filters_dict.get("ordering")

    has_active_ticket = Exists(
        Ticket.objects.filter(
            customer_id=OuterRef("pk"),
            deleted_at__isnull=True,
            status__in=["ACTIVE", "RENEWING"],
            effective_to__gt=current_time,
        )
    )

    qs = Customer.objects.filter(deleted_at__isnull=True).annotate(
        vehicles_count=Count(
            "vehicles",
            filter=Q(vehicles__deleted_at__isnull=True),
            distinct=True,
        ),
        has_active_ticket=has_active_ticket,
    )

    # 1. Filter criteria
    if code_val and str(code_val).strip():
        clean_code = escape_like(str(code_val).strip())
        qs = qs.filter(code__ilike=f"%{clean_code}%")

    if name_val and str(name_val).strip():
        clean_name = escape_like(str(name_val).strip())
        qs = qs.filter(full_name__ilike=f"%{clean_name}%")

    if phone_val and str(phone_val).strip():
        qs = qs.filter(phone__icontains=str(phone_val).strip())

    if id_card_val and str(id_card_val).strip():
        qs = qs.filter(identity_card_number__icontains=str(id_card_val).strip())

    if status_val and str(status_val).strip():
        qs = qs.filter(status=str(status_val).strip().upper())

    # 2. Ordering
    if ordering_val and ordering_val in ALLOWED_ORDERING_FIELDS:
        qs = qs.order_by(ordering_val, "id")
    else:
        qs = qs.order_by("code", "id")

    return qs


def get_customer_status_summary(
    now: datetime.datetime | None = None,
) -> dict[str, int]:
    """
    Single Source of Truth (SOT) for the 4 KPI summary cards matching list filters 100%:
    1. total_customers: Count of all active (non-deleted) customers.
    2. active_subscriptions / active_subscribers: Count of distinct customers with unexpired subscription ticket.
    3. expiring_soon_subscriptions / expiring_soon_subscribers: Count of distinct customers with ticket expiring in 7 days.
    4. blacklisted_or_suspended: Count of customers in SUSPENDED or BLACKLISTED state.
    """
    current_time = now or timezone.now()
    expiring_soon_days = getattr(settings, "TICKET_EXPIRING_SOON_DAYS", 7)
    expiring_soon_window = current_time + timedelta(days=expiring_soon_days)

    total_customers = Customer.objects.filter(deleted_at__isnull=True).count()

    active_subscribers = (
        Customer.objects.filter(deleted_at__isnull=True)
        .filter(
            Exists(
                Ticket.objects.filter(
                    customer_id=OuterRef("pk"),
                    deleted_at__isnull=True,
                    status__in=["ACTIVE", "RENEWING"],
                    effective_to__gt=current_time,
                )
            )
        )
        .count()
    )

    expiring_soon_subscribers = (
        Customer.objects.filter(deleted_at__isnull=True)
        .filter(
            Exists(
                Ticket.objects.filter(
                    customer_id=OuterRef("pk"),
                    deleted_at__isnull=True,
                    status__in=["ACTIVE", "RENEWING"],
                    effective_to__gt=current_time,
                    effective_to__lte=expiring_soon_window,
                )
            )
        )
        .count()
    )

    blacklisted_or_suspended = Customer.objects.filter(
        deleted_at__isnull=True,
        status__in=["SUSPENDED", "BLACKLISTED"],
    ).count()

    return {
        "total_customers": total_customers,
        "active_subscriptions": active_subscribers,
        "active_subscribers": active_subscribers,
        "expiring_soon_subscriptions": expiring_soon_subscribers,
        "expiring_soon_subscribers": expiring_soon_subscribers,
        "blacklisted_or_suspended": blacklisted_or_suspended,
    }


def get_customer_by_id(
    customer_id: int,
    now: datetime.datetime | None = None,
) -> Customer:
    """
    Retrieve single customer profile by primary key with administrative units
    and vehicle subgrid with representative tickets, guaranteeing zero N+1 queries.
    """
    customer = (
        Customer.objects.select_related("province", "district", "ward")
        .filter(id=customer_id, deleted_at__isnull=True)
        .first()
    )
    if not customer:
        raise BusinessAPIException(
            code="PROP-4.4.4-P02",
            message="Khách hàng không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    current_time = now or timezone.now()
    expiring_soon_days = getattr(settings, "TICKET_EXPIRING_SOON_DAYS", 7)
    expiring_soon_window = current_time + timedelta(days=expiring_soon_days)

    rep_ticket_base = get_representative_ticket_subquery(now=current_time)

    vehicles_qs = (
        Vehicle.objects.filter(customer_id=customer.id, deleted_at__isnull=True)
        .select_related("vehicle_type")
        .annotate(
            rep_ticket_id=Subquery(rep_ticket_base.values("id")[:1]),
            rep_ticket_code=Subquery(rep_ticket_base.values("code")[:1]),
            rep_ticket_type_code=Subquery(
                rep_ticket_base.values("ticket_type__code")[:1]
            ),
            rep_ticket_type_name=Subquery(
                rep_ticket_base.values("ticket_type__name")[:1]
            ),
            rep_ticket_effective_from=Subquery(
                rep_ticket_base.values("effective_from")[:1]
            ),
            rep_ticket_effective_to=Subquery(
                rep_ticket_base.values("effective_to")[:1]
            ),
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
            fe_display_status=Case(
                When(rep_ticket_effective_to__isnull=True, then=Value("Chưa có vé")),
                When(
                    rep_ticket_effective_to__lt=current_time, then=Value("Đã hết hạn")
                ),
                When(
                    rep_ticket_effective_to__lte=expiring_soon_window,
                    then=Value("Sắp hết hạn"),
                ),
                default=Value("Còn hạn"),
                output_field=CharField(),
            ),
        )
        .order_by("id")
    )

    annotated_vehicles = []
    for v in vehicles_qs:
        ticket_data = None
        if v.rep_ticket_id:
            days_rem = 0
            if v.rep_ticket_effective_to:
                diff_sec = (v.rep_ticket_effective_to - current_time).total_seconds()
                days_rem = max(0, int(math.ceil(diff_sec / 86400.0)))

            ticket_data = {
                "id": v.rep_ticket_id,
                "code": v.rep_ticket_code,
                "ticket_type": v.rep_ticket_type_name,
                "ticket_type_code": v.rep_ticket_type_code,
                "ticket_type_name": v.rep_ticket_type_name,
                "effective_from": v.rep_ticket_effective_from,
                "expires_at": v.rep_ticket_effective_to,
                "ticket_state": v.rep_ticket_state,
                "fe_display_status": v.fe_display_status,
                "remaining_days": days_rem,
                "days_remaining": days_rem,
            }

        v_type_data = None
        if v.vehicle_type:
            v_type_data = {
                "id": v.vehicle_type.id,
                "code": v.vehicle_type.code,
                "name": v.vehicle_type.name,
            }

        annotated_vehicles.append(
            {
                "id": v.id,
                "code": v.code,
                "license_plate": v.license_plate,
                "brand": v.brand,
                "model_name": v.model_name,
                "color": v.color,
                "image_url": v.image_url,
                "notes": v.notes,
                "vehicle_type": v_type_data,
                "vehicle_type_id": v.vehicle_type_id,
                "vehicle_type_name": v.vehicle_type.name if v.vehicle_type else "",
                "ticket_type_name": v.rep_ticket_type_name,
                "ticket_expires_at": v.rep_ticket_effective_to,
                "ticket": ticket_data,
            }
        )

    customer.annotated_vehicles = annotated_vehicles  # type: ignore[attr-defined]
    return customer
