"""
Selectors for customer wallet and self-service endpoints.
Enforces zero-N+1 query design with select_related and subqueries.
"""

from __future__ import annotations

from django.db.models import QuerySet
from rest_framework import status

from apps.content.models import Notification
from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_message
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle
from apps.vehicles.selectors.vehicles import get_vehicles_queryset
from apps.wallet.models import Wallet, WalletTransaction


def get_wallet_by_customer_id(customer_id: int) -> Wallet:
    """Retrieve active wallet for a customer or raise 404."""
    wallet = (
        Wallet.objects.select_related("customer")
        .filter(
            customer_id=customer_id,
            deleted_at__isnull=True,
            customer__deleted_at__isnull=True,
        )
        .first()
    )
    if not wallet:
        raise BusinessAPIException(
            code="PROP-WALLET-NOT-FOUND",
            message=get_message("PROP-WALLET-NOT-FOUND"),
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return wallet


def get_wallet_transactions_queryset(
    wallet_id: int,
    kind: str | None = None,
    direction: str | None = None,
) -> QuerySet[WalletTransaction]:
    """
    Build zero-N+1 QuerySet for wallet ledger transactions ordered newest-first.
    Supports filtering by kind and direction ('CREDIT'/'deposit' vs 'DEBIT'/'payment').
    """
    qs = (
        WalletTransaction.objects.filter(wallet_id=wallet_id)
        .select_related("created_by")
        .order_by("-created_at", "-id")
    )

    if kind and str(kind).strip():
        qs = qs.filter(kind=str(kind).strip().upper())

    if direction and str(direction).strip():
        dir_norm = str(direction).strip().upper()
        if dir_norm in ("CREDIT", "DEPOSIT"):
            qs = qs.filter(transaction_type="CREDIT")
        elif dir_norm in ("DEBIT", "PAYMENT"):
            qs = qs.filter(transaction_type="DEBIT")

    return qs


def get_me_vehicles_queryset(customer_id: int) -> QuerySet[Vehicle]:
    """Retrieve vehicles owned strictly by the authenticated customer with zero N+1."""
    return get_vehicles_queryset().filter(customer_id=customer_id)


def get_me_tickets_queryset(
    customer_id: int,
    status_filter: str | None = None,
) -> QuerySet[Ticket]:
    """Retrieve tickets owned strictly by the authenticated customer with zero N+1."""
    qs = (
        Ticket.objects.filter(customer_id=customer_id, deleted_at__isnull=True)
        .select_related(
            "ticket_type",
            "vehicle",
            "vehicle__vehicle_type",
            "slot",
            "slot__zone",
            "slot__zone__floor",
        )
        .order_by("-created_at", "-id")
    )

    if status_filter and str(status_filter).strip():
        st = str(status_filter).strip().upper()
        if st != "ALL":
            qs = qs.filter(status=st)

    return qs


def get_me_notifications_queryset(
    account_id: int,
    is_read: bool | None = None,
    notification_type: str | None = None,
) -> QuerySet[Notification]:
    """Retrieve non-deleted notifications owned by the authenticated account (zero N+1)."""
    qs = (
        Notification.objects.filter(
            recipient_account_id=account_id,
            deleted_at__isnull=True,
        )
        .only(
            "id",
            "recipient_account_id",
            "title",
            "content",
            "notification_type",
            "is_read",
            "read_at",
            "created_at",
        )
        .order_by("-created_at", "-id")
    )
    if is_read is not None:
        qs = qs.filter(is_read=is_read)
    if notification_type and str(notification_type).strip():
        qs = qs.filter(notification_type=str(notification_type).strip().upper())
    return qs


def get_me_unread_notifications_count(account_id: int) -> int:
    """Count unread non-deleted notifications for the authenticated account."""
    return Notification.objects.filter(
        recipient_account_id=account_id,
        deleted_at__isnull=True,
        is_read=False,
    ).count()
