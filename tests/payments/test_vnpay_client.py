"""
Unit tests for pure stdlib VNPAY v2.1.0 client and stateless signed vnp_TxnRef codec.
Zero database dependency.
"""

from __future__ import annotations

import hashlib
import hmac
import urllib.parse
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from apps.payments.services.vnpay_client import (
    MAX_TXN_REF_LENGTH,
    build_payment_url,
    canonical_vnpay_query,
    extract_vnpay_query_params,
    generate_signed_txn_ref,
    sanitize_order_info,
    sign_vnpay_params,
    verify_and_parse_txn_ref,
    verify_vnpay_signature,
)


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """Bypass DB fixture for pure unit tests."""
    return None


SYNTHETIC_TMN = "SYNTH001"
SYNTHETIC_SECRET = "synthetic-unit-test-hash-secret-vnpay"
PAYMENT_URL = "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html"
RETURN_URL = "https://merchant.example.test/api/v1/payments/vnpay/return/"


def test_build_payment_url_canonical_quote_plus_hmac_sha512_and_no_hash_type():
    fixed_dt = datetime(2026, 11, 23, 10, 15, 30, tzinfo=ZoneInfo("Asia/Ho_Chi_Minh"))
    url, expire_dt = build_payment_url(
        tmn_code=SYNTHETIC_TMN,
        hash_secret=SYNTHETIC_SECRET,
        payment_url=PAYMENT_URL,
        return_url=RETURN_URL,
        amount_vnd=150000,
        txn_ref="VP1-1-37q8-1000-aabbccddeeff-00112233445566778899aabbccddeeff",
        order_info="Nạp tiền ví : KH0001 / test!",
        ip_addr="10.0.0.5",
        locale="vn",
        bank_code="NCB",
        timeout_minutes=15,
        now_fn=lambda: fixed_dt,
    )

    assert url.startswith(PAYMENT_URL + "?")
    assert "vnp_SecureHashType" not in url
    assert "vnp_Amount=15000000" in url
    assert "vnp_CreateDate=20261123101530" in url
    assert "vnp_ExpireDate=20261123103030" in url
    assert expire_dt.strftime("%Y%m%d%H%M%S") == "20261123103030"
    # Verify quote_plus encoding on space ('+') and ':' ('%3A') and '/' ('%2F')
    assert "vnp_OrderInfo=Nap+tien+vi+%3A+KH0001+test" in url
    assert urllib.parse.quote_plus(RETURN_URL) in url

    parsed_qs = urllib.parse.parse_qs(
        urllib.parse.urlparse(url).query, keep_blank_values=True
    )
    flat = {k: v[0] for k, v in parsed_qs.items()}
    assert len(flat["vnp_SecureHash"]) == 128
    assert flat["vnp_SecureHash"] == flat["vnp_SecureHash"].lower()

    # Cross-verify against independent stdlib HMAC-SHA512 formula
    vnp_items = sorted(
        (k, val)
        for k, val in flat.items()
        if k.startswith("vnp_") and k not in {"vnp_SecureHash", "vnp_SecureHashType"}
    )
    independent_hash_data = "&".join(
        f"{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(val)}"
        for k, val in vnp_items
    )
    independent_sig = hmac.new(
        SYNTHETIC_SECRET.encode("utf-8"),
        independent_hash_data.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()
    assert flat["vnp_SecureHash"] == independent_sig
    assert verify_vnpay_signature(flat, SYNTHETIC_SECRET) is True


def test_timezone_gmt7_midnight_month_end_and_leap_day_rollover():
    # 2024-02-29 16:55:00 UTC == 2024-02-29 23:55:00 Asia/Ho_Chi_Minh (+7) -> +15m = 2024-03-01 00:10:00
    utc_dt = datetime(2024, 2, 29, 16, 55, 0, tzinfo=ZoneInfo("UTC"))
    url, expire_dt = build_payment_url(
        tmn_code=SYNTHETIC_TMN,
        hash_secret=SYNTHETIC_SECRET,
        payment_url=PAYMENT_URL,
        return_url=RETURN_URL,
        amount_vnd=20000,
        txn_ref="VP1-1-fgg-1-aabbccddeeff-00112233445566778899aabbccddeeff",
        order_info="Leap day test",
        ip_addr="127.0.0.1",
        timeout_minutes=15,
        now_fn=lambda: utc_dt,
    )
    assert "vnp_CreateDate=20240229235500" in url
    assert "vnp_ExpireDate=20240301001000" in url
    assert expire_dt.strftime("%Y%m%d%H%M%S") == "20240301001000"


def test_verify_vnpay_signature_rejects_tamper_wrong_case_missing_extra_and_ignores_non_vnp():
    base_params = {
        "vnp_Amount": "10000000",
        "vnp_Command": "pay",
        "vnp_ResponseCode": "00",
        "vnp_TmnCode": SYNTHETIC_TMN,
        "vnp_TransactionStatus": "00",
        "vnp_TxnRef": "VP1-1-2qxc-1-aabbccddeeff-00112233445566778899aabbccddeeff",
    }
    sig = sign_vnpay_params(base_params, SYNTHETIC_SECRET)
    signed = {**base_params, "vnp_SecureHash": sig}
    assert verify_vnpay_signature(signed, SYNTHETIC_SECRET) is True

    # Non-vnp_* params ignored; vnp_SecureHashType ignored
    assert (
        verify_vnpay_signature(
            {**signed, "utm_source": "foo", "vnp_SecureHashType": "SHA512"},
            SYNTHETIC_SECRET,
        )
        is True
    )

    # 1-char tamper in param value -> False
    assert (
        verify_vnpay_signature({**signed, "vnp_Amount": "10000001"}, SYNTHETIC_SECRET)
        is False
    )
    # 1-char tamper in signature -> False
    tampered_sig = ("0" if sig[0] != "0" else "1") + sig[1:]
    assert (
        verify_vnpay_signature(
            {**signed, "vnp_SecureHash": tampered_sig}, SYNTHETIC_SECRET
        )
        is False
    )
    # Wrong case (uppercase hex) -> False
    assert (
        verify_vnpay_signature(
            {**signed, "vnp_SecureHash": sig.upper()}, SYNTHETIC_SECRET
        )
        is False
    )
    # Extra vnp_* param -> False
    assert (
        verify_vnpay_signature({**signed, "vnp_Extra": "1"}, SYNTHETIC_SECRET) is False
    )
    # Missing required vnp_* param -> False
    missing_param = {k: v for k, v in signed.items() if k != "vnp_Amount"}
    assert verify_vnpay_signature(missing_param, SYNTHETIC_SECRET) is False
    # Missing / empty / non-hex hash -> False (never raises)
    assert verify_vnpay_signature(base_params, SYNTHETIC_SECRET) is False
    assert (
        verify_vnpay_signature({**base_params, "vnp_SecureHash": ""}, SYNTHETIC_SECRET)
        is False
    )
    assert (
        verify_vnpay_signature(
            {**base_params, "vnp_SecureHash": "z" * 128}, SYNTHETIC_SECRET
        )
        is False
    )
    assert verify_vnpay_signature(signed, "") is False


def test_stateless_txn_ref_roundtrip_length_bounds_and_tamper_detection():
    txn_ref = generate_signed_txn_ref(
        customer_id=42,
        amount_vnd=50_000_000,
        hash_secret=SYNTHETIC_SECRET,
        now_ts=1_795_000_000,
    )
    assert len(txn_ref) <= MAX_TXN_REF_LENGTH
    assert len(f"vnpay-{txn_ref}") <= 100

    parsed = verify_and_parse_txn_ref(txn_ref, SYNTHETIC_SECRET)
    assert parsed is not None
    assert parsed.customer_id == 42
    assert parsed.amount_vnd == 50_000_000
    assert parsed.created_ts == 1_795_000_000

    # Tampering any character invalidates HMAC
    idx = txn_ref.find("-", 4) + 1
    flipped = "a" if txn_ref[idx] != "a" else "b"
    tampered = txn_ref[:idx] + flipped + txn_ref[idx + 1 :]
    assert verify_and_parse_txn_ref(tampered, SYNTHETIC_SECRET) is None
    assert verify_and_parse_txn_ref(txn_ref, "wrong-secret") is None
    assert (
        verify_and_parse_txn_ref("VP1-0-0-0-000000000000-" + "0" * 32, SYNTHETIC_SECRET)
        is None
    )
    assert verify_and_parse_txn_ref("not-a-txn-ref", SYNTHETIC_SECRET) is None


def test_sanitize_order_info_and_canonical_query_edge_cases():
    sanitized = sanitize_order_info("Đóng tiền gửi xe Ô tô @#$% " + "x" * 300)
    assert len(sanitized) <= 255
    assert sanitized.startswith("Dong tien gui xe O to")
    assert "@" not in sanitized
    assert sanitize_order_info("!!!") == "Nap tien vi Smart Parking"

    q = canonical_vnpay_query(
        {
            "b": "ignored",
            "vnp_Z": "2",
            "vnp_A": "1",
            "vnp_Empty": "",
            "vnp_SecureHash": "x",
        }
    )
    assert q == "vnp_A=1&vnp_Z=2"


def test_extract_vnpay_query_params_and_querydict_hpp_guard():
    from django.http import QueryDict

    # Raw query string: ignores duplicate non-vnp_ keys, decodes '+' and '%3a'
    parsed = extract_vnpay_query_params(
        "utm=1&utm=2&vnp_Amount=10000000&vnp_OrderInfo=Nap+tien%3a+1&vnp_BankTranNo="
    )
    assert parsed == {
        "vnp_Amount": "10000000",
        "vnp_OrderInfo": "Nap tien: 1",
        "vnp_BankTranNo": "",
    }

    # Rejects duplicate vnp_* keys (HPP) and invalid UTF-8 bytes
    assert extract_vnpay_query_params("vnp_Amount=100&vnp_Amount=100") is None
    assert extract_vnpay_query_params("vnp_SecureHash=a&vnp_SecureHash=b") is None
    assert extract_vnpay_query_params("vnp_OrderInfo=test%FF%FE") is None

    # Direct QueryDict caller cannot bypass HPP protection in verify_vnpay_signature
    base = {
        "vnp_Amount": "10000000",
        "vnp_TxnRef": "VP1-1-2qxc-1-aabbccddeeff-00112233445566778899aabbccddeeff",
    }
    sig = sign_vnpay_params(base, SYNTHETIC_SECRET)
    qd_ok = QueryDict(
        f"vnp_Amount={base['vnp_Amount']}&vnp_TxnRef={base['vnp_TxnRef']}&vnp_SecureHash={sig}"
    )
    assert verify_vnpay_signature(qd_ok, SYNTHETIC_SECRET) is True

    qd_hpp = QueryDict(
        f"vnp_Amount=99999900&vnp_Amount={base['vnp_Amount']}&vnp_TxnRef={base['vnp_TxnRef']}&vnp_SecureHash={sig}"
    )
    assert extract_vnpay_query_params(qd_hpp) is None
    assert verify_vnpay_signature(qd_hpp, SYNTHETIC_SECRET) is False
