"""
Read-only selectors for customer VNPAY top-up polling.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.conf import settings
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_message
from apps.payments.services.topup import is_vnpay_enabled
from apps.payments.services.vnpay_client import verify_and_parse_txn_ref
from apps.wallet.models import Wallet, WalletTransaction


def get_vnpay_topup_status(*, customer_id: int, txn_ref: str) -> dict[str, Any]:
    """
    Returns whether a customer-owned VNPAY txn_ref has been credited via IPN.
    Raises 404 MSG-4.4.1-M01 if txn_ref is invalid or belongs to another customer.
    """
    if not is_vnpay_enabled():
        raise BusinessAPIException(
            code="PROP-VNPAY-DISABLED",
            message=get_message("PROP-VNPAY-DISABLED"),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    hash_secret = str(settings.VNPAY_HASH_SECRET).strip()
    parsed = verify_and_parse_txn_ref(txn_ref, hash_secret)
    if parsed is None or parsed.customer_id != customer_id:
        raise BusinessAPIException(
            code="MSG-4.4.1-M01",
            message=get_message("MSG-4.4.1-M01"),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    tx = WalletTransaction.objects.filter(
        wallet__customer_id=customer_id,
        idempotency_key=f"vnpay-{txn_ref}",
    ).first()
    wallet = Wallet.objects.filter(
        customer_id=customer_id,
        deleted_at__isnull=True,
    ).first()

    return {
        "txn_ref": txn_ref,
        "status": "CREDITED" if tx is not None else "PENDING",
        "amount": Decimal(parsed.amount_vnd).quantize(Decimal("0.01")),
        "balance": (wallet.balance if wallet is not None else Decimal("0.00")).quantize(
            Decimal("0.01")
        ),
        "wallet_transaction_id": tx.id if tx is not None else None,
        "credited_at": tx.created_at if tx is not None else None,
    }
