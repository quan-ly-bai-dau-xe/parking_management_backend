"""
VNPAY sandbox wallet top-up orchestration: intent creation, IPN processing, and return verification.
"""

from __future__ import annotations

import logging
import re
import urllib.parse
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db import transaction
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_message
from apps.customers.models import Customer
from apps.payments.services.vnpay_client import (
    build_payment_url,
    extract_vnpay_query_params,
    generate_signed_txn_ref,
    verify_and_parse_txn_ref,
    verify_vnpay_signature,
)
from apps.wallet.models import Wallet, WalletTransaction
from apps.wallet.services.wallet import credit_wallet, ensure_wallet_for_customer

logger = logging.getLogger(__name__)

_SAFE_ALNUM_PATTERN = re.compile(r"[^A-Za-z0-9_-]+")
DEFAULT_FRONTEND_RESULT_PATH = "/wallet/vnpay-return"


def is_vnpay_enabled() -> bool:
    """Returns True iff both VNPAY_TMN_CODE and VNPAY_HASH_SECRET are configured."""
    tmn_code = str(getattr(settings, "VNPAY_TMN_CODE", "") or "").strip()
    hash_secret = str(getattr(settings, "VNPAY_HASH_SECRET", "") or "").strip()
    return bool(tmn_code and hash_secret)


def is_vnpay_sandbox() -> bool:
    """Returns True when VNPAY_PAYMENT_URL targets the VNPAY sandbox host."""
    payment_url = str(getattr(settings, "VNPAY_PAYMENT_URL", "") or "").lower()
    return "sandbox.vnpayment.vn" in payment_url


def _sanitize_token_field(value: str | None, fallback: str = "N/A") -> str:
    cleaned = _SAFE_ALNUM_PATTERN.sub("", str(value or "").strip())
    return cleaned[:32] or fallback


def _resolve_safe_frontend_result_url() -> str:
    raw_target = str(getattr(settings, "VNPAY_FRONTEND_RESULT_URL", "") or "").strip()
    if not raw_target:
        return DEFAULT_FRONTEND_RESULT_PATH
    if raw_target.startswith("/") and not raw_target.startswith("//"):
        return raw_target

    parsed = urllib.parse.urlparse(raw_target)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return DEFAULT_FRONTEND_RESULT_PATH

    allowed_hosts: set[str] = {
        str(h).strip().lower()
        for h in getattr(settings, "ALLOWED_HOSTS", [])
        if str(h).strip()
    }
    for origin in getattr(settings, "CORS_ALLOWED_ORIGINS", []):
        origin_host = urllib.parse.urlparse(str(origin)).netloc.lower()
        if origin_host:
            allowed_hosts.add(origin_host)

    target_host = parsed.netloc.lower()
    target_hostname = (parsed.hostname or "").lower()
    if (
        "*" in allowed_hosts
        or target_host in allowed_hosts
        or target_hostname in allowed_hosts
    ):
        return raw_target
    return DEFAULT_FRONTEND_RESULT_PATH


def create_vnpay_topup_intent(
    *,
    customer: Customer,
    amount_vnd: int,
    client_ip: str,
    locale: str = "vn",
    bank_code: str | None = None,
    order_info: str | None = None,
    return_url_fallback: str | None = None,
) -> dict[str, Any]:
    """
    Creates a signed VNPAY v2.1.0 payment URL for the authenticated customer.
    """
    if not is_vnpay_enabled():
        raise BusinessAPIException(
            code="PROP-VNPAY-DISABLED",
            message=get_message("PROP-VNPAY-DISABLED"),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    if customer.status != "ACTIVE":
        raise BusinessAPIException(
            code="PROP-CUSTOMER-INACTIVE",
            message=get_message("PROP-CUSTOMER-INACTIVE"),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    min_vnd = int(getattr(settings, "VNPAY_TOPUP_MIN", 10000))
    max_vnd = int(getattr(settings, "VNPAY_TOPUP_MAX", 50000000))
    if amount_vnd < min_vnd or amount_vnd > max_vnd:
        raise BusinessAPIException(
            code="PROP-VNPAY-AMOUNT-RANGE",
            message=get_message("PROP-VNPAY-AMOUNT-RANGE"),
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"min": min_vnd, "max": max_vnd},
        )

    wallet = ensure_wallet_for_customer(customer.id)
    if wallet.status != "ACTIVE":
        raise BusinessAPIException(
            code="PROP-WALLET-LOCKED",
            message=get_message("PROP-WALLET-LOCKED"),
            status_code=status.HTTP_409_CONFLICT,
        )

    return_url = (
        str(getattr(settings, "VNPAY_RETURN_URL", "") or "").strip()
        or str(return_url_fallback or "").strip()
    )
    if not return_url:
        raise BusinessAPIException(
            code="PROP-VNPAY-DISABLED",
            message=get_message("PROP-VNPAY-DISABLED"),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )

    hash_secret = str(settings.VNPAY_HASH_SECRET).strip()
    tmn_code = str(settings.VNPAY_TMN_CODE).strip()
    txn_ref = generate_signed_txn_ref(
        customer_id=customer.id,
        amount_vnd=amount_vnd,
        hash_secret=hash_secret,
    )
    payment_url, expires_at = build_payment_url(
        tmn_code=tmn_code,
        hash_secret=hash_secret,
        payment_url=str(settings.VNPAY_PAYMENT_URL).strip(),
        return_url=return_url,
        amount_vnd=amount_vnd,
        txn_ref=txn_ref,
        order_info=order_info or f"Nap tien vi {customer.code}",
        ip_addr=client_ip,
        locale=locale,
        bank_code=bank_code,
        timeout_minutes=int(getattr(settings, "VNPAY_TIMEOUT_MINUTES", 15)),
    )
    return {
        "payment_url": payment_url,
        "txn_ref": txn_ref,
        "amount": Decimal(amount_vnd).quantize(Decimal("0.01")),
        "expires_at": expires_at,
        "is_sandbox": is_vnpay_sandbox(),
    }


def process_vnpay_ipn(query_params: str | Mapping[str, str]) -> tuple[str, str]:
    """
    Handles server-to-server VNPAY IPN GET callbacks.
    Always returns a (RspCode, Message) pair for an HTTP 200 JSON response.
    """
    # Fail closed with 0 DB queries when VNPAY is unconfigured.
    if not is_vnpay_enabled():
        return ("99", "Unknown error")

    params = extract_vnpay_query_params(query_params)
    if params is None:
        return ("97", "Invalid Checksum")

    hash_secret = str(settings.VNPAY_HASH_SECRET).strip()
    tmn_code = str(settings.VNPAY_TMN_CODE).strip()

    # Signature MUST be checked before any database read or write.
    if not verify_vnpay_signature(params, hash_secret):
        return ("97", "Invalid Checksum")

    if params.get("vnp_TmnCode", "").strip() != tmn_code:
        return ("01", "Order not found")

    txn_ref = params.get("vnp_TxnRef", "").strip()
    parsed = verify_and_parse_txn_ref(txn_ref, hash_secret)
    if parsed is None:
        return ("01", "Order not found")

    raw_amount = params.get("vnp_Amount", "").strip()
    if not (raw_amount.isascii() and raw_amount.isdigit()):
        return ("04", "Invalid amount")
    if int(raw_amount) != parsed.amount_vnd * 100:
        return ("04", "Invalid amount")

    customer_exists = Customer.objects.filter(
        id=parsed.customer_id,
        deleted_at__isnull=True,
    ).exists()
    if not customer_exists:
        return ("01", "Order not found")

    idempotency_key = f"vnpay-{txn_ref}"
    rsp_code = params.get("vnp_ResponseCode", "").strip()
    tx_status = params.get("vnp_TransactionStatus", "").strip()

    try:
        with transaction.atomic():
            wallet = ensure_wallet_for_customer(parsed.customer_id)
            locked_wallet = (
                Wallet.objects.select_for_update()
                .filter(id=wallet.id, deleted_at__isnull=True)
                .first()
            )
            if WalletTransaction.objects.filter(
                idempotency_key=idempotency_key
            ).exists():
                return ("02", "Order already confirmed")

            # Acknowledge non-00 gateway outcomes with 00 (no credit) so VNPAY stops retrying.
            if rsp_code != "00" or tx_status != "00":
                logger.info(
                    "VNPAY IPN non-success acknowledged without credit: txn_ref=%s rsp=%s tx_status=%s",
                    txn_ref,
                    _sanitize_token_field(rsp_code, "NONE"),
                    _sanitize_token_field(tx_status, "NONE"),
                )
                return ("00", "Confirm Success")

            if locked_wallet is None or locked_wallet.status != "ACTIVE":
                return ("99", "Unknown error")

            safe_tx_no = _sanitize_token_field(params.get("vnp_TransactionNo"))
            safe_bank = _sanitize_token_field(params.get("vnp_BankCode"))
            credit_wallet(
                wallet_id=locked_wallet.id,
                amount=Decimal(parsed.amount_vnd),
                kind="TOPUP_VNPAY",
                idempotency_key=idempotency_key,
                note=f"Nạp tiền ví qua VNPAY (Mã GD: {safe_tx_no}, NH: {safe_bank})",
                reference_type="VNPAY_TXN",
            )
            return ("00", "Confirm Success")
    except BusinessAPIException as exc:
        if exc.code == "PROP-WALLET-IDEMPOTENCY-CONFLICT":
            return ("02", "Order already confirmed")
        logger.warning(
            "VNPAY IPN business rejection: txn_ref=%s code=%s",
            txn_ref,
            exc.code,
        )
        return ("99", "Unknown error")
    except Exception:
        logger.exception(
            "Unexpected error during VNPAY IPN processing: txn_ref=%s", txn_ref
        )
        return ("99", "Unknown error")


def verify_vnpay_return(query_params: str | Mapping[str, str]) -> str:
    """
    Verifies browser Return URL parameters WITHOUT mutating any database state.
    Returns a safe frontend redirect URL containing only status, txn_ref, and code.
    """
    base_target = _resolve_safe_frontend_result_url()

    hash_secret = str(getattr(settings, "VNPAY_HASH_SECRET", "") or "").strip()
    tmn_code = str(getattr(settings, "VNPAY_TMN_CODE", "") or "").strip()

    params = extract_vnpay_query_params(query_params)
    if params is None:
        redirect_params = {"status": "invalid_signature", "code": "97"}
        separator = "&" if "?" in base_target else "?"
        return f"{base_target}{separator}{urllib.parse.urlencode(redirect_params)}"

    raw_txn_ref = params.get("vnp_TxnRef", "").strip()
    safe_txn_ref = (
        raw_txn_ref if re.fullmatch(r"[A-Za-z0-9_-]{1,94}", raw_txn_ref) else ""
    )

    if not is_vnpay_enabled() or not verify_vnpay_signature(params, hash_secret):
        redirect_params = {"status": "invalid_signature", "code": "97"}
        if safe_txn_ref:
            redirect_params["txn_ref"] = safe_txn_ref
    else:
        parsed = verify_and_parse_txn_ref(raw_txn_ref, hash_secret)
        if parsed is None or params.get("vnp_TmnCode", "").strip() != tmn_code:
            redirect_params = {"status": "invalid_signature", "code": "01"}
            if safe_txn_ref:
                redirect_params["txn_ref"] = safe_txn_ref
        else:
            rsp_code = params.get("vnp_ResponseCode", "").strip()
            tx_status = params.get("vnp_TransactionStatus", "").strip()
            if rsp_code == "00" and tx_status == "00":
                redirect_params = {
                    "status": "pending",
                    "txn_ref": raw_txn_ref,
                    "code": "00",
                }
            else:
                redirect_params = {
                    "status": "failed",
                    "txn_ref": raw_txn_ref,
                    "code": _sanitize_token_field(rsp_code or tx_status, "99"),
                }

    separator = "&" if "?" in base_target else "?"
    return f"{base_target}{separator}{urllib.parse.urlencode(redirect_params)}"


def format_vnpay_expiry_iso(expires_at: datetime) -> str:
    """Formats GMT+7 expiration timestamp to ISO-8601 string."""
    return expires_at.isoformat()
