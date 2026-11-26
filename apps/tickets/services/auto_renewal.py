"""
Automatic subscription ticket renewal service (WP4 R2 & D6).
Processes MONTHLY, QUARTERLY, and YEARLY tickets expiring on or before today
in Asia/Ho_Chi_Minh timezone, debiting the customer's wallet idempotently.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.content.models import Notification
from apps.core.exceptions import BusinessAPIException
from apps.tickets.models import Payment, Ticket, TicketRenewal
from apps.wallet.models import Wallet, WalletTransaction
from apps.wallet.services.wallet import InsufficientWalletBalanceError, debit_wallet

logger = logging.getLogger(__name__)

HCM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
AUTO_RENEWAL_TICKET_CODES = ("MONTHLY", "QUARTERLY", "YEARLY")


class _UnavailableWalletError(Exception):
    """Internal marker when customer has no active wallet for auto-renewal."""


def process_ticket_auto_renewals(
    now: datetime | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """
    Scan and auto-renew eligible subscription tickets expiring in Asia/Ho_Chi_Minh.
    Returns summary counters: checked, renewed, expired, skipped, errors.
    """
    now_utc = now or timezone.now()
    if timezone.is_naive(now_utc):
        now_utc = timezone.make_aware(now_utc, HCM_TZ)

    today_hcm = now_utc.astimezone(HCM_TZ).date()
    start_of_today_hcm = datetime.combine(today_hcm, time.min, tzinfo=HCM_TZ)
    cutoff_hcm = datetime.combine(
        today_hcm + timedelta(days=1), time.min, tzinfo=HCM_TZ
    )

    candidate_ids = list(
        Ticket.objects.filter(
            deleted_at__isnull=True,
            ticket_type__code__in=AUTO_RENEWAL_TICKET_CODES,
            ticket_type__deleted_at__isnull=True,
            status__in=("ACTIVE", "RENEWING"),
            effective_to__lt=cutoff_hcm,
        )
        .order_by("id")
        .values_list("id", flat=True)
    )

    summary = {
        "checked": len(candidate_ids),
        "renewed": 0,
        "expired": 0,
        "skipped": 0,
        "errors": 0,
    }
    if dry_run or not candidate_ids:
        return summary

    for ticket_id in candidate_ids:
        idempotency_key = f"ticket_renewal_{ticket_id}_{today_hcm.isoformat()}"
        insufficient = False

        try:
            with transaction.atomic():
                ticket = (
                    Ticket.objects.select_for_update()
                    .select_related("ticket_type", "customer", "slot", "vehicle")
                    .filter(id=ticket_id, deleted_at__isnull=True)
                    .first()
                )
                if (
                    not ticket
                    or ticket.status not in ("ACTIVE", "RENEWING")
                    or ticket.effective_to >= cutoff_hcm
                    or ticket.ticket_type.code not in AUTO_RENEWAL_TICKET_CODES
                    or ticket.customer.deleted_at is not None
                ):
                    summary["skipped"] += 1
                    continue

                if WalletTransaction.objects.filter(
                    idempotency_key=idempotency_key
                ).exists():
                    summary["skipped"] += 1
                    continue

                wallet = Wallet.objects.filter(
                    customer_id=ticket.customer_id, deleted_at__isnull=True
                ).first()
                if not wallet or wallet.status != "ACTIVE":
                    raise _UnavailableWalletError()

                renewal_price = ticket.ticket_type.default_price
                old_effective_to = ticket.effective_to
                base_dt = max(old_effective_to, now_utc)
                new_effective_to = base_dt + timedelta(
                    days=ticket.ticket_type.duration_days
                )

                renewal = TicketRenewal.objects.create(
                    ticket=ticket,
                    old_slot=ticket.slot,
                    new_slot=ticket.slot,
                    old_ticket_type=ticket.ticket_type,
                    new_ticket_type=ticket.ticket_type,
                    old_price=ticket.price,
                    new_price=renewal_price,
                    old_effective_to=old_effective_to,
                    new_effective_to=new_effective_to,
                    additional_price=renewal_price,
                    notes=(
                        f"Tự động gia hạn {ticket.ticket_type.name} "
                        f"({ticket.code}) ngày {today_hcm.isoformat()}"
                    ),
                    renewed_by=None,
                )

                Payment.objects.create(
                    code=f"PAY-RNW-{renewal.id}",
                    amount=renewal_price,
                    method="WALLET",
                    status="PAID",
                    paid_at=now_utc,
                    received_by=None,
                    session=None,
                    ticket=None,
                    renewal=renewal,
                    notes=f"Thanh toán tự động gia hạn vé {ticket.code}",
                )

                debit_wallet(
                    wallet_id=wallet.id,
                    amount=renewal_price,
                    kind="TICKET_RENEWAL",
                    idempotency_key=idempotency_key,
                    reference_type="TICKET_RENEWAL",
                    reference_id=renewal.id,
                    note=f"Tự động gia hạn vé {ticket.code} ({ticket.ticket_type.name})",
                    actor_id=None,
                )

                ticket.effective_to = new_effective_to
                ticket.price = renewal_price
                ticket.status = "ACTIVE"
                ticket.save(update_fields=["effective_to", "price", "status"])

                account_id = ticket.customer.account_id
                if account_id is not None:
                    new_exp_local = new_effective_to.astimezone(HCM_TZ).strftime(
                        "%d/%m/%Y %H:%M"
                    )
                    Notification.objects.create(
                        recipient_account_id=account_id,
                        title=f"Gia hạn vé {ticket.code} thành công"[:200],
                        content=(
                            f"Vé {ticket.code} ({ticket.ticket_type.name}) đã được tự động gia hạn "
                            f"đến {new_exp_local}. Số tiền đã trừ từ ví: {renewal_price:,.0f} VND."
                        ),
                        notification_type="PAYMENT",
                    )

                summary["renewed"] += 1
        except InsufficientWalletBalanceError, _UnavailableWalletError:
            insufficient = True
        except BusinessAPIException as exc:
            if exc.code in ("PROP-WALLET-LOCKED", "PROP-WALLET-NOT-FOUND"):
                insufficient = True
            else:
                summary["errors"] += 1
                logger.exception(
                    "Business error during auto-renewal for ticket_id=%s: %s",
                    ticket_id,
                    exc.code,
                )
        except Exception:
            summary["errors"] += 1
            logger.exception(
                "Unexpected error during auto-renewal for ticket_id=%s", ticket_id
            )

        if insufficient:
            try:
                with transaction.atomic():
                    ticket = (
                        Ticket.objects.select_for_update()
                        .select_related("customer", "ticket_type")
                        .filter(id=ticket_id, deleted_at__isnull=True)
                        .first()
                    )
                    if not ticket or ticket.status not in ("ACTIVE", "RENEWING"):
                        summary["skipped"] += 1
                        continue

                    ticket.status = "EXPIRED"
                    ticket.save(update_fields=["status"])

                    account_id = ticket.customer.account_id
                    if account_id is not None:
                        already_notified = Notification.objects.filter(
                            recipient_account_id=account_id,
                            notification_type="TICKET_EXPIRY",
                            title__contains=ticket.code,
                            created_at__gte=start_of_today_hcm,
                            deleted_at__isnull=True,
                        ).exists()
                        if not already_notified:
                            Notification.objects.create(
                                recipient_account_id=account_id,
                                title=(
                                    f"Vé {ticket.code} đã hết hạn do ví không đủ số dư"
                                )[:200],
                                content=(
                                    f"Không thể tự động gia hạn vé {ticket.code} "
                                    f"({ticket.ticket_type.name}) do số dư ví không đủ hoặc ví chưa sẵn sàng. "
                                    "Vui lòng nạp thêm tiền vào ví và mua hoặc gia hạn lại vé."
                                ),
                                notification_type="TICKET_EXPIRY",
                            )

                    summary["expired"] += 1
            except Exception:
                summary["errors"] += 1
                logger.exception(
                    "Failed to mark expired ticket_id=%s after insufficient balance",
                    ticket_id,
                )

    return summary
