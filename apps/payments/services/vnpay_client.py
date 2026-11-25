"""
Pure stdlib VNPAY v2.1.0 gateway client and stateless signed vnp_TxnRef codec.
Zero third-party dependencies, zero global mutable state, zero secret logging.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
import unicodedata
import urllib.parse
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable
from zoneinfo import ZoneInfo

VNPAY_VERSION = "2.1.0"
VNPAY_COMMAND_PAY = "pay"
VNPAY_CURR_CODE_VND = "VND"
VNPAY_DEFAULT_ORDER_TYPE = "other"
VIETNAM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

MAX_TXN_REF_LENGTH = 94  # Guarantees f"vnpay-{txn_ref}" <= 100 chars (VARCHAR(100))
_BASE36_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyz"
_TXN_REF_PATTERN = re.compile(
    r"^VP1-([0-9a-z]+)-([0-9a-z]+)-([0-9a-z]+)-([0-9a-f]{12})-([0-9a-f]{32})$"
)
_LOWER_HEX_128_PATTERN = re.compile(r"^[0-9a-f]{128}$")
_SAFE_ORDER_INFO_CHAR_PATTERN = re.compile(r"[^A-Za-z0-9 .:-]+")
_WHITESPACE_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class ParsedTxnRef:
    """Decoded payload extracted from a verified stateless vnp_TxnRef token."""

    customer_id: int
    amount_vnd: int
    created_ts: int
    nonce: str


def _int_to_base36(value: int) -> str:
    if value < 0:
        raise ValueError("Value must be non-negative.")
    if value == 0:
        return "0"
    digits: list[str] = []
    num = value
    while num > 0:
        num, rem = divmod(num, 36)
        digits.append(_BASE36_ALPHABET[rem])
    return "".join(reversed(digits))


def _base36_to_int(raw: str) -> int | None:
    if not raw or any(ch not in _BASE36_ALPHABET for ch in raw):
        return None
    val = int(raw, 36)
    if _int_to_base36(val) != raw:
        return None
    return val


def _derive_txn_ref_key(hash_secret: str) -> bytes:
    # Domain-separate txn_ref MAC key from raw VNPAY_HASH_SECRET used for vnp_SecureHash.
    return hmac.new(
        hash_secret.encode("utf-8"),
        b"parking:vnpay:txnref:v1",
        hashlib.sha256,
    ).digest()


def generate_signed_txn_ref(
    customer_id: int,
    amount_vnd: int,
    hash_secret: str,
    now_ts: int | None = None,
    nonce: str | None = None,
) -> str:
    """
    Generates a stateless HMAC-authenticated vnp_TxnRef token (<= 94 chars).
    Format: VP1-<customer_b36>-<amount_b36>-<ts_b36>-<nonce12>-<hmac32>.
    """
    if not hash_secret:
        raise ValueError("hash_secret must not be empty.")
    if customer_id <= 0 or amount_vnd <= 0:
        raise ValueError("customer_id and amount_vnd must be positive integers.")

    ts = int(time.time()) if now_ts is None else int(now_ts)
    if ts < 0:
        raise ValueError("now_ts must be non-negative.")

    if nonce is None:
        nonce_str = secrets.token_hex(6)
    else:
        nonce_str = str(nonce).lower()
        if not re.fullmatch(r"[0-9a-f]{12}", nonce_str):
            raise ValueError("nonce must be 12 lowercase hex characters.")

    payload = (
        f"VP1-{_int_to_base36(customer_id)}-{_int_to_base36(amount_vnd)}"
        f"-{_int_to_base36(ts)}-{nonce_str}"
    )
    tag = hmac.new(
        _derive_txn_ref_key(hash_secret),
        payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()[:32]
    txn_ref = f"{payload}-{tag}"
    if len(txn_ref) > MAX_TXN_REF_LENGTH:
        raise ValueError("Generated vnp_TxnRef exceeds maximum allowed length.")
    return txn_ref


def verify_and_parse_txn_ref(txn_ref: str, hash_secret: str) -> ParsedTxnRef | None:
    """
    Verifies HMAC signature and structural validity of a stateless vnp_TxnRef.
    Returns ParsedTxnRef if authentic, otherwise None.
    """
    if (
        not isinstance(txn_ref, str)
        or not hash_secret
        or len(txn_ref) > MAX_TXN_REF_LENGTH
    ):
        return None

    match = _TXN_REF_PATTERN.fullmatch(txn_ref)
    if match is None:
        return None

    cust_raw, amt_raw, ts_raw, nonce_str, tag_hex = match.groups()
    payload = f"VP1-{cust_raw}-{amt_raw}-{ts_raw}-{nonce_str}"
    expected_tag = hmac.new(
        _derive_txn_ref_key(hash_secret),
        payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()[:32]

    if not hmac.compare_digest(tag_hex, expected_tag):
        return None

    customer_id = _base36_to_int(cust_raw)
    amount_vnd = _base36_to_int(amt_raw)
    created_ts = _base36_to_int(ts_raw)
    if (
        customer_id is None
        or customer_id <= 0
        or amount_vnd is None
        or amount_vnd <= 0
        or created_ts is None
    ):
        return None

    return ParsedTxnRef(
        customer_id=customer_id,
        amount_vnd=amount_vnd,
        created_ts=created_ts,
        nonce=nonce_str,
    )


def sanitize_order_info(raw_text: str) -> str:
    """
    Normalizes Vietnamese order descriptions to ASCII without diacritics or unsafe
    punctuation, clamped to VNPAY's 255-character vnp_OrderInfo limit.
    """
    text = (raw_text or "").replace("đ", "d").replace("Đ", "D")
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = _SAFE_ORDER_INFO_CHAR_PATTERN.sub(" ", ascii_only)
    collapsed = _WHITESPACE_PATTERN.sub(" ", cleaned).strip()
    if not collapsed:
        return "Nap tien vi Smart Parking"
    return collapsed[:255].strip() or "Nap tien vi Smart Parking"


def canonical_vnpay_query(params: Mapping[str, str | int]) -> str:
    """
    Builds the VNPAY v2.1.0 canonical sorted query string using quote_plus
    on both parameter keys and values, excluding vnp_SecureHash and vnp_SecureHashType.
    """
    filtered_items: list[tuple[str, str]] = []
    for raw_key, raw_val in params.items():
        key = str(raw_key)
        if not key.startswith("vnp_"):
            continue
        if key in {"vnp_SecureHash", "vnp_SecureHashType"}:
            continue
        if raw_val is None:
            continue
        val_str = str(raw_val)
        if val_str == "":
            continue
        filtered_items.append((key, val_str))

    filtered_items.sort(key=lambda pair: pair[0])
    return "&".join(
        f"{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(v)}"
        for k, v in filtered_items
    )


def sign_vnpay_params(params: Mapping[str, str | int], hash_secret: str) -> str:
    """Computes VNPAY v2.1.0 HMAC-SHA512 lowercase hex digest over canonical query."""
    if not hash_secret:
        raise ValueError("hash_secret must not be empty.")
    hash_data = canonical_vnpay_query(params)
    return hmac.new(
        hash_secret.encode("utf-8"),
        hash_data.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()


@runtime_checkable
class _MultiValueMapping(Protocol):
    def lists(self) -> Iterable[tuple[str, list[str]]]: ...


def extract_vnpay_query_params(
    query_source: str | Mapping[str, str],
) -> dict[str, str] | None:
    """
    Strictly extracts single-valued vnp_* parameters from a raw QUERY_STRING or mapping.
    Returns None (fail closed) on invalid UTF-8 percent-encoding or any duplicate vnp_* key
    (HTTP Parameter Pollution protection, including vnp_SecureHash/vnp_SecureHashType).
    Non-vnp_* keys are ignored.
    """
    extracted: dict[str, str] = {}
    if isinstance(query_source, str):
        try:
            pairs = urllib.parse.parse_qsl(
                query_source,
                keep_blank_values=True,
                encoding="utf-8",
                errors="strict",
            )
        except UnicodeDecodeError:
            return None

        for raw_key, raw_val in pairs:
            if not raw_key.startswith("vnp_"):
                continue
            if raw_key in extracted:
                return None
            extracted[raw_key] = raw_val
        return extracted

    if isinstance(query_source, _MultiValueMapping):
        for raw_key, values in query_source.lists():
            key = str(raw_key)
            if not key.startswith("vnp_"):
                continue
            if len(values) != 1:
                return None
            extracted[key] = str(values[0])
        return extracted

    for raw_key, raw_val in query_source.items():
        key = str(raw_key)
        if key.startswith("vnp_"):
            extracted[key] = str(raw_val)
    return extracted


def verify_vnpay_signature(params: Mapping[str, str], hash_secret: str) -> bool:
    """
    Verifies VNPAY v2.1.0 vnp_SecureHash strictly in constant time.
    Requires exact 128-character lowercase hex digest; rejects multi-value QueryDict HPP;
    never raises on missing/bad input.
    """
    if not hash_secret:
        return False
    if isinstance(params, _MultiValueMapping):
        normalized = extract_vnpay_query_params(params)
        if normalized is None:
            return False
        params = normalized
    received = params.get("vnp_SecureHash")
    if not isinstance(received, str) or not _LOWER_HEX_128_PATTERN.fullmatch(received):
        return False
    expected = sign_vnpay_params(params, hash_secret)
    return hmac.compare_digest(received, expected)


def build_payment_url(
    *,
    tmn_code: str,
    hash_secret: str,
    payment_url: str,
    return_url: str,
    amount_vnd: int,
    txn_ref: str,
    order_info: str,
    ip_addr: str,
    locale: str = "vn",
    order_type: str = VNPAY_DEFAULT_ORDER_TYPE,
    bank_code: str | None = None,
    timeout_minutes: int = 15,
    now_fn: Callable[[], datetime] | None = None,
) -> tuple[str, datetime]:
    """
    Constructs a signed VNPAY v2.1.0 payment URL (without vnp_SecureHashType)
    using Asia/Ho_Chi_Minh (GMT+7) timestamps for vnp_CreateDate and vnp_ExpireDate.
    """
    if not tmn_code or not hash_secret:
        raise ValueError("tmn_code and hash_secret are required.")
    if not payment_url or not return_url:
        raise ValueError("payment_url and return_url are required.")
    if (
        not isinstance(amount_vnd, int)
        or isinstance(amount_vnd, bool)
        or amount_vnd <= 0
    ):
        raise ValueError("amount_vnd must be a positive integer.")
    if not txn_ref or len(txn_ref) > 100:
        raise ValueError("txn_ref must be between 1 and 100 characters.")
    if timeout_minutes <= 0:
        raise ValueError("timeout_minutes must be positive.")

    raw_now = now_fn() if now_fn is not None else datetime.now(tz=VIETNAM_TZ)
    now_gmt7 = (
        raw_now.replace(tzinfo=VIETNAM_TZ)
        if raw_now.tzinfo is None
        else raw_now.astimezone(VIETNAM_TZ)
    )
    expire_gmt7 = now_gmt7 + timedelta(minutes=timeout_minutes)

    clean_locale = "en" if str(locale).strip().lower() == "en" else "vn"
    clean_ip = (ip_addr or "127.0.0.1").strip()[:45] or "127.0.0.1"

    params: dict[str, str | int] = {
        "vnp_Version": VNPAY_VERSION,
        "vnp_Command": VNPAY_COMMAND_PAY,
        "vnp_TmnCode": str(tmn_code).strip(),
        "vnp_Amount": str(amount_vnd * 100),
        "vnp_CurrCode": VNPAY_CURR_CODE_VND,
        "vnp_TxnRef": txn_ref,
        "vnp_OrderInfo": sanitize_order_info(order_info),
        "vnp_OrderType": (order_type or VNPAY_DEFAULT_ORDER_TYPE).strip()[:100],
        "vnp_Locale": clean_locale,
        "vnp_ReturnUrl": str(return_url).strip(),
        "vnp_IpAddr": clean_ip,
        "vnp_CreateDate": now_gmt7.strftime("%Y%m%d%H%M%S"),
        "vnp_ExpireDate": expire_gmt7.strftime("%Y%m%d%H%M%S"),
    }
    if bank_code and str(bank_code).strip():
        params["vnp_BankCode"] = str(bank_code).strip().upper()[:20]

    query = canonical_vnpay_query(params)
    secure_hash = sign_vnpay_params(params, hash_secret)
    separator = "&" if "?" in payment_url else "?"
    full_url = f"{payment_url}{separator}{query}&vnp_SecureHash={secure_hash}"
    return full_url, expire_gmt7
