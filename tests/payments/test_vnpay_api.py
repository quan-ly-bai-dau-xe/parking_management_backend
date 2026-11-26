"""
Integration, security, concurrency, and schema-guard tests for VNPAY wallet top-up APIs.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import subprocess
import sys
import threading
import urllib.parse
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.payments.services.vnpay_client import (
    generate_signed_txn_ref,
    sign_vnpay_params,
)
from apps.wallet.models import WalletTransaction

REPO_ROOT = Path(__file__).resolve().parents[2]
SYNTH_TMN = "TESTTMN1"
SYNTH_SECRET = "synthetic-vnpay-api-test-secret-key"
SYNTH_VNPAY_SETTINGS = {
    "VNPAY_TMN_CODE": SYNTH_TMN,
    "VNPAY_HASH_SECRET": SYNTH_SECRET,
    "VNPAY_PAYMENT_URL": "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html",
    "VNPAY_RETURN_URL": "https://merchant.example.test/api/v1/payments/vnpay/return/",
    "VNPAY_FRONTEND_RESULT_URL": "/wallet/vnpay-return",
    "VNPAY_TOPUP_MIN": 10000,
    "VNPAY_TOPUP_MAX": 50000000,
    "VNPAY_TIMEOUT_MINUTES": 15,
}


def _signed_ipn_params(
    *,
    txn_ref: str,
    amount_vnd: int,
    rsp_code: str = "00",
    tx_status: str = "00",
    tmn_code: str = SYNTH_TMN,
    secret: str = SYNTH_SECRET,
) -> dict[str, str]:
    params = {
        "vnp_Amount": str(amount_vnd * 100),
        "vnp_BankCode": "NCB",
        "vnp_BankTranNo": "VNP14000001",
        "vnp_CardType": "ATM",
        "vnp_OrderInfo": "Nap tien vi KHW",
        "vnp_PayDate": "20261123103000",
        "vnp_ResponseCode": rsp_code,
        "vnp_TmnCode": tmn_code,
        "vnp_TransactionNo": "14000001",
        "vnp_TransactionStatus": tx_status,
        "vnp_TxnRef": txn_ref,
    }
    params["vnp_SecureHash"] = sign_vnpay_params(params, secret)
    return params


@pytest.fixture(autouse=True)
def clear_cache_between_tests():
    cache.clear()
    yield
    cache.clear()


@pytest.mark.django_db
@override_settings(**SYNTH_VNPAY_SETTINGS)
def test_me_wallet_exposes_topup_channels_and_never_leaks_secrets(customer_client):
    resp = customer_client.get("/api/v1/me/wallet/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["topup_channels"] == {
        "vnpay_enabled": True,
        "vnpay_is_sandbox": True,
        "vnpay_topup_min": 10000,
        "vnpay_topup_max": 50000000,
        "simulated_vietqr_enabled": True,
    }
    raw_text = resp.content.decode("utf-8")
    assert SYNTH_SECRET not in raw_text
    assert SYNTH_TMN not in raw_text


@pytest.mark.django_db
@override_settings(VNPAY_TMN_CODE="", VNPAY_HASH_SECRET="")
def test_vnpay_disabled_returns_503_and_ipn_returns_99(
    customer_client, anon_client, wallet_customer_pair
):
    wallet_resp = customer_client.get("/api/v1/me/wallet/")
    assert wallet_resp.status_code == 200
    assert wallet_resp.json()["topup_channels"]["vnpay_enabled"] is False

    create_resp = customer_client.post(
        "/api/v1/me/wallet/topups/vnpay/",
        data={"amount": 50000},
        format="json",
    )
    assert create_resp.status_code == 503
    assert create_resp.json()["code"] == "PROP-VNPAY-DISABLED"

    ipn_resp = anon_client.get("/api/v1/payments/vnpay/ipn/", {"vnp_TxnRef": "bad"})
    assert ipn_resp.status_code == 200
    assert ipn_resp.json()["RspCode"] == "99"


@pytest.mark.django_db
@override_settings(**SYNTH_VNPAY_SETTINGS)
def test_vnpay_topup_create_rbac_and_amount_boundaries(
    anon_client, staff_client, manager_client, customer_client, wallet_customer_pair
):
    _, cust, wallet = wallet_customer_pair

    # RBAC checks
    assert (
        anon_client.post(
            "/api/v1/me/wallet/topups/vnpay/", data={"amount": 50000}, format="json"
        ).status_code
        == 401
    )
    assert (
        staff_client.post(
            "/api/v1/me/wallet/topups/vnpay/", data={"amount": 50000}, format="json"
        ).status_code
        == 403
    )
    assert (
        manager_client.post(
            "/api/v1/me/wallet/topups/vnpay/", data={"amount": 50000}, format="json"
        ).status_code
        == 403
    )

    # Strict integer VND boundary & malformed checks -> 400 PROP-VNPAY-AMOUNT-RANGE
    for bad_amount in [
        0,
        -10000,
        9999,
        50000001,
        10000.5,
        "10000.50",
        "1e5",
        True,
        None,
        "abc",
    ]:
        bad_resp = customer_client.post(
            "/api/v1/me/wallet/topups/vnpay/",
            data={"amount": bad_amount},
            format="json",
        )
        assert bad_resp.status_code == 400, (
            f"amount={bad_amount!r} got {bad_resp.status_code}"
        )
        assert bad_resp.json()["code"] == "PROP-VNPAY-AMOUNT-RANGE"

    # Valid min boundary
    ok_resp = customer_client.post(
        "/api/v1/me/wallet/topups/vnpay/",
        data={"amount": 10000, "locale": "vn"},
        format="json",
        REMOTE_ADDR="203.0.113.10",
    )
    assert ok_resp.status_code == 201
    body = ok_resp.json()
    assert body["is_sandbox"] is True
    assert Decimal(body["amount"]) == Decimal("10000.00")
    assert body["txn_ref"].startswith("VP1-")
    assert "vnp_IpAddr=203.0.113.10" in body["payment_url"]
    assert SYNTH_SECRET not in body["payment_url"]

    # Locked wallet -> 409 PROP-WALLET-LOCKED
    wallet.status = "LOCKED"
    wallet.save(update_fields=["status"])
    locked_resp = customer_client.post(
        "/api/v1/me/wallet/topups/vnpay/",
        data={"amount": 50000},
        format="json",
    )
    assert locked_resp.status_code == 409
    assert locked_resp.json()["code"] == "PROP-WALLET-LOCKED"

    # Suspended customer -> 403 PROP-CUSTOMER-INACTIVE
    wallet.status = "ACTIVE"
    wallet.save(update_fields=["status"])
    cust.status = "SUSPENDED"
    cust.save(update_fields=["status"])
    cust_locked = customer_client.post(
        "/api/v1/me/wallet/topups/vnpay/",
        data={"amount": 50000},
        format="json",
    )
    assert cust_locked.status_code == 403
    assert cust_locked.json()["code"] == "PROP-CUSTOMER-INACTIVE"


@pytest.mark.django_db
@override_settings(**SYNTH_VNPAY_SETTINGS, NUM_PROXIES=0)
def test_vnpay_topup_respects_num_proxies_and_rate_limit(customer_client):
    # NUM_PROXIES=0 ignores spoofed X-Forwarded-For
    r1 = customer_client.post(
        "/api/v1/me/wallet/topups/vnpay/",
        data={"amount": 20000},
        format="json",
        REMOTE_ADDR="198.51.100.2",
        HTTP_X_FORWARDED_FOR="1.2.3.4",
    )
    assert r1.status_code == 201
    assert "vnp_IpAddr=198.51.100.2" in r1.json()["payment_url"]

    with override_settings(NUM_PROXIES=1):
        r2 = customer_client.post(
            "/api/v1/me/wallet/topups/vnpay/",
            data={"amount": 20000},
            format="json",
            REMOTE_ADDR="198.51.100.2",
            HTTP_X_FORWARDED_FOR="1.2.3.4, 198.51.100.99",
        )
        assert r2.status_code == 201
        assert "vnp_IpAddr=198.51.100.99" in r2.json()["payment_url"]

    # Exhaust 10/min rate limit (2 already used) -> 11th returns 429 + Retry-After
    for _ in range(8):
        ok = customer_client.post(
            "/api/v1/me/wallet/topups/vnpay/",
            data={"amount": 20000},
            format="json",
        )
        assert ok.status_code == 201

    throttled = customer_client.post(
        "/api/v1/me/wallet/topups/vnpay/",
        data={"amount": 20000},
        format="json",
    )
    assert throttled.status_code == 429
    assert throttled.json()["code"] == "PROP-VNPAY-RATE-LIMITED"
    assert throttled.headers.get("Retry-After") == "60"


@pytest.mark.django_db
@override_settings(**SYNTH_VNPAY_SETTINGS)
def test_vnpay_ipn_signature_first_zero_db_queries_and_all_rsp_codes(
    anon_client, customer_client, other_customer_pair, wallet_customer_pair
):
    _, cust, wallet = wallet_customer_pair
    other_acc, _, _ = other_customer_pair

    create_resp = customer_client.post(
        "/api/v1/me/wallet/topups/vnpay/",
        data={"amount": 100000},
        format="json",
    )
    assert create_resp.status_code == 201
    txn_ref = create_resp.json()["txn_ref"]

    # Before IPN, status polling reports PENDING
    poll_before = customer_client.get(f"/api/v1/me/wallet/topups/vnpay/{txn_ref}/")
    assert poll_before.status_code == 200
    assert poll_before.json()["status"] == "PENDING"

    # Cross-customer status lookup -> 404 MSG-4.4.1-M01
    other_client = APIClient()
    other_client.force_authenticate(user=other_acc)
    assert (
        other_client.get(f"/api/v1/me/wallet/topups/vnpay/{txn_ref}/").status_code
        == 404
    )

    # 1. Invalid signature -> RspCode=97 with ZERO DB queries
    bad_sig_params = _signed_ipn_params(txn_ref=txn_ref, amount_vnd=100000)
    bad_sig_params["vnp_SecureHash"] = "0" * 128
    with CaptureQueriesContext(connection) as ctx:
        r_97 = anon_client.get("/api/v1/payments/vnpay/ipn/", bad_sig_params)
    assert r_97.status_code == 200
    assert r_97.json()["RspCode"] == "97"
    assert len(ctx) == 0

    # 2. Invalid TmnCode / forged txn_ref -> RspCode=01
    r_01_tmn = anon_client.get(
        "/api/v1/payments/vnpay/ipn/",
        _signed_ipn_params(txn_ref=txn_ref, amount_vnd=100000, tmn_code="WRONGTMN"),
    )
    assert r_01_tmn.status_code == 200
    assert r_01_tmn.json()["RspCode"] == "01"

    r_01_ref = anon_client.get(
        "/api/v1/payments/vnpay/ipn/",
        _signed_ipn_params(txn_ref="VP1-bad-ref", amount_vnd=100000),
    )
    assert r_01_ref.status_code == 200
    assert r_01_ref.json()["RspCode"] == "01"

    # 3. Amount mismatch -> RspCode=04
    r_04 = anon_client.get(
        "/api/v1/payments/vnpay/ipn/",
        _signed_ipn_params(txn_ref=txn_ref, amount_vnd=99999),
    )
    assert r_04.status_code == 200
    assert r_04.json()["RspCode"] == "04"

    # 4. Non-00 status (e.g. ResponseCode="00" & TransactionStatus="02", or "24") -> RspCode=00, ZERO credit
    r_partial = anon_client.get(
        "/api/v1/payments/vnpay/ipn/",
        _signed_ipn_params(
            txn_ref=txn_ref, amount_vnd=100000, rsp_code="00", tx_status="02"
        ),
    )
    assert r_partial.status_code == 200
    assert r_partial.json()["RspCode"] == "00"
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("0.00")

    # 5. Locked wallet -> RspCode=99, ZERO credit
    wallet.status = "LOCKED"
    wallet.save(update_fields=["status"])
    r_locked = anon_client.get(
        "/api/v1/payments/vnpay/ipn/",
        _signed_ipn_params(txn_ref=txn_ref, amount_vnd=100000),
    )
    assert r_locked.status_code == 200
    assert r_locked.json()["RspCode"] == "99"
    wallet.status = "ACTIVE"
    wallet.save(update_fields=["status"])

    # 6. Valid success ("00" AND "00") -> RspCode=00 and credits exactly once
    valid_params = _signed_ipn_params(txn_ref=txn_ref, amount_vnd=100000)
    r_00 = anon_client.get("/api/v1/payments/vnpay/ipn/", valid_params)
    assert r_00.status_code == 200
    assert r_00.json()["RspCode"] == "00"
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("100000.00")

    tx = WalletTransaction.objects.get(idempotency_key=f"vnpay-{txn_ref}")
    assert tx.kind == "TOPUP_VNPAY"
    assert tx.transaction_type == "CREDIT"
    assert tx.amount == Decimal("100000.00")
    assert "VNPAY" in (tx.note or "")

    # 7. Replay -> RspCode=02, no second credit
    r_02 = anon_client.get("/api/v1/payments/vnpay/ipn/", valid_params)
    assert r_02.status_code == 200
    assert r_02.json()["RspCode"] == "02"
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("100000.00")

    # Status polling now confirms CREDITED
    poll_after = customer_client.get(f"/api/v1/me/wallet/topups/vnpay/{txn_ref}/")
    assert poll_after.status_code == 200
    assert poll_after.json()["status"] == "CREDITED"
    assert Decimal(poll_after.json()["balance"]) == Decimal("100000.00")
    assert poll_after.json()["wallet_transaction_id"] == tx.id

    call_command("reconcile_wallets", fail_on_mismatch=True)


@pytest.mark.django_db
@override_settings(**SYNTH_VNPAY_SETTINGS)
def test_vnpay_return_url_never_credits_db_and_prevents_open_redirect(
    anon_client, wallet_customer_pair
):
    _, cust, wallet = wallet_customer_pair
    txn_ref = generate_signed_txn_ref(cust.id, 75000, SYNTH_SECRET)

    # Valid success signature on Return URL -> redirects to pending, ZERO credit
    params = _signed_ipn_params(txn_ref=txn_ref, amount_vnd=75000)
    r_ok = anon_client.get("/api/v1/payments/vnpay/return/", params)
    assert r_ok.status_code == 302
    parsed_loc = urllib.parse.urlparse(r_ok["Location"])
    qs = urllib.parse.parse_qs(parsed_loc.query)
    assert parsed_loc.path == "/wallet/vnpay-return"
    assert qs["status"] == ["pending"]
    assert qs["txn_ref"] == [txn_ref]
    assert qs["code"] == ["00"]
    assert "vnp_SecureHash" not in r_ok["Location"]

    wallet.refresh_from_db()
    assert wallet.balance == Decimal("0.00")
    assert (
        WalletTransaction.objects.filter(idempotency_key=f"vnpay-{txn_ref}").count()
        == 0
    )

    # Bad signature on Return URL -> invalid_signature
    bad_params = {**params, "vnp_SecureHash": "f" * 128}
    r_bad = anon_client.get("/api/v1/payments/vnpay/return/", bad_params)
    assert r_bad.status_code == 302
    assert "status=invalid_signature" in r_bad["Location"]

    # Cancelled/failed -> status=failed
    fail_params = _signed_ipn_params(
        txn_ref=txn_ref, amount_vnd=75000, rsp_code="24", tx_status="02"
    )
    r_fail = anon_client.get("/api/v1/payments/vnpay/return/", fail_params)
    assert r_fail.status_code == 302
    assert "status=failed" in r_fail["Location"]
    assert "code=24" in r_fail["Location"]

    # Open-redirect protection: external untrusted host falls back to /wallet/vnpay-return
    with override_settings(
        VNPAY_FRONTEND_RESULT_URL="https://evil.attacker.example/steal"
    ):
        r_safe = anon_client.get("/api/v1/payments/vnpay/return/", params)
        assert r_safe.status_code == 302
        assert r_safe["Location"].startswith("/wallet/vnpay-return?")


@pytest.mark.django_db(transaction=True)
@override_settings(**SYNTH_VNPAY_SETTINGS)
def test_vnpay_ipn_concurrent_double_hit_barrier_credits_exactly_once(
    wallet_customer_pair,
):
    _, cust, wallet = wallet_customer_pair
    txn_ref = generate_signed_txn_ref(cust.id, 250000, SYNTH_SECRET)
    params = _signed_ipn_params(txn_ref=txn_ref, amount_vnd=250000)

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def _worker() -> None:
        client = APIClient()
        barrier.wait(timeout=5)
        resp = client.get("/api/v1/payments/vnpay/ipn/", params)
        with lock:
            results.append(resp.json()["RspCode"])

    t1 = threading.Thread(target=_worker)
    t2 = threading.Thread(target=_worker)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert sorted(results) == ["00", "02"]
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("250000.00")
    assert (
        WalletTransaction.objects.filter(idempotency_key=f"vnpay-{txn_ref}").count()
        == 1
    )
    call_command("reconcile_wallets", fail_on_mismatch=True)


def test_production_settings_rejects_sandbox_vnpay_when_credentials_set():
    base_env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "SECRET_KEY": "x" * 50,
        "POSTGRES_DB": "x",
        "POSTGRES_USER": "x",
        "POSTGRES_PASSWORD": "x",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "DEBUG": "False",
        "ALLOWED_HOSTS": "localhost",
        "CLOUDINARY_CLOUD_NAME": "test-cloud",
        "CLOUDINARY_API_KEY": "test-key",
        "CLOUDINARY_API_SECRET": "test-secret",
        "VNPAY_TMN_CODE": SYNTH_TMN,
        "VNPAY_HASH_SECRET": SYNTH_SECRET,
        "VNPAY_PAYMENT_URL": "https://sandbox.vnpayment.vn/paymentv2/vpcpay.html",
        "VNPAY_ALLOW_SANDBOX_IN_PRODUCTION": "False",
    }
    proc_fail = subprocess.run(
        [sys.executable, "-c", "import config.settings.production"],
        cwd=REPO_ROOT,
        env=base_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc_fail.returncode != 0
    assert "ImproperlyConfigured" in proc_fail.stderr

    # Allowed when override switch is True
    proc_ok = subprocess.run(
        [sys.executable, "-c", "import config.settings.production"],
        cwd=REPO_ROOT,
        env={**base_env, "VNPAY_ALLOW_SANDBOX_IN_PRODUCTION": "True"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert proc_ok.returncode == 0, proc_ok.stderr


@pytest.mark.django_db
def test_simulated_vietqr_topup_remains_topup_vietqr(
    customer_client, wallet_customer_pair
):
    _, _, wallet = wallet_customer_pair
    resp = customer_client.post(
        "/api/v1/me/wallet/topups/",
        data={"amount": 50000, "idempotency_key": f"sim-vqr-{wallet.id}"},
        format="json",
    )
    assert resp.status_code == 201
    tx_data = resp.json()["transaction"]
    assert tx_data["kind"] == "TOPUP_VIETQR"
    tx = WalletTransaction.objects.get(id=tx_data["id"])
    assert tx.kind == "TOPUP_VIETQR"


def _independent_vnpay_sign(
    items: list[tuple[str, str]],
    secret: str,
    *,
    mode: str = "quote_plus",
) -> str:
    """
    Independent stdlib-only VNPAY v2.1.0 HMAC-SHA512 signer (D5).
    Uses only hmac/hashlib/urllib.parse; never imports vnpay_client to sign.
    """
    if mode == "php_include_empty":
        filtered = [
            (k, v)
            for k, v in items
            if k.startswith("vnp_")
            and k not in {"vnp_SecureHash", "vnp_SecureHashType"}
        ]
    else:
        filtered = [
            (k, v)
            for k, v in items
            if k.startswith("vnp_")
            and k not in {"vnp_SecureHash", "vnp_SecureHashType"}
            and v != ""
        ]
    filtered.sort(key=lambda pair: pair[0])

    if mode in {"quote_plus", "php_include_empty"}:
        hash_data = "&".join(
            f"{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(v)}"
            for k, v in filtered
        )
    elif mode == "quote":
        hash_data = "&".join(
            f"{urllib.parse.quote(k)}={urllib.parse.quote(v)}" for k, v in filtered
        )
    elif mode == "nodejs_unencoded":
        hash_data = "&".join(f"{k}={v}" for k, v in filtered)
    elif mode == "java_keep_asterisk":
        # Java URLEncoder.encode keeps '*' unencoded and encodes '~' as '%7E'.
        def _java_encode(raw: str) -> str:
            return urllib.parse.quote_plus(raw, safe="*").replace("~", "%7E")

        hash_data = "&".join(
            f"{_java_encode(k)}={_java_encode(v)}" for k, v in filtered
        )
    elif mode == "lowercase_percent":
        canonical = "&".join(
            f"{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(v)}"
            for k, v in filtered
        )
        hash_data = re.sub(r"%[0-9A-F]{2}", lambda m: m.group(0).lower(), canonical)
    else:
        raise ValueError(f"Unsupported independent sign mode: {mode}")

    return hmac.new(
        secret.encode("utf-8"),
        hash_data.encode("utf-8"),
        hashlib.sha512,
    ).hexdigest()


def _base_vnpay_items(
    *,
    txn_ref: str,
    amount_vnd: int = 100000,
    order_info: str = "Nap tien vi",
    bank_tran_no: str = "VNP14000001",
) -> list[tuple[str, str]]:
    return [
        ("vnp_Amount", str(amount_vnd * 100)),
        ("vnp_BankCode", "NCB"),
        ("vnp_BankTranNo", bank_tran_no),
        ("vnp_CardType", "ATM"),
        ("vnp_OrderInfo", order_info),
        ("vnp_PayDate", "20261124120000"),
        ("vnp_ResponseCode", "00"),
        ("vnp_TmnCode", SYNTH_TMN),
        ("vnp_TransactionNo", "14000001"),
        ("vnp_TransactionStatus", "00"),
        ("vnp_TxnRef", txn_ref),
    ]


@pytest.mark.django_db
@override_settings(**SYNTH_VNPAY_SETTINGS)
def test_vnpay_ipn_and_return_reject_duplicate_vnp_keys_hpp(
    anon_client, wallet_customer_pair
):
    _, cust, wallet = wallet_customer_pair
    txn_ref = generate_signed_txn_ref(cust.id, 100000, SYNTH_SECRET)
    base_items = _base_vnpay_items(txn_ref=txn_ref, amount_vnd=100000)
    sig = _independent_vnpay_sign(base_items, SYNTH_SECRET, mode="quote_plus")
    base_qs = urllib.parse.urlencode(base_items)

    hpp_cases = [
        ("dup_amount_same", f"vnp_Amount=10000000&{base_qs}&vnp_SecureHash={sig}"),
        ("dup_amount_diff", f"vnp_Amount=99999900&{base_qs}&vnp_SecureHash={sig}"),
        (
            "dup_order_info",
            f"vnp_OrderInfo=Spoofed&{base_qs}&vnp_SecureHash={sig}",
        ),
        (
            "dup_secure_hash",
            f"{base_qs}&vnp_SecureHash={sig}&vnp_SecureHash={sig}",
        ),
        (
            "dup_secure_hash_type",
            f"{base_qs}&vnp_SecureHashType=SHA512&vnp_SecureHashType=HMACSHA512&vnp_SecureHash={sig}",
        ),
    ]

    for label, raw_qs in hpp_cases:
        with CaptureQueriesContext(connection) as ctx:
            ipn_resp = anon_client.get(f"/api/v1/payments/vnpay/ipn/?{raw_qs}")
        assert ipn_resp.status_code == 200, label
        assert ipn_resp.json()["RspCode"] == "97", f"{label} expected 97"
        assert len(ctx) == 0, f"{label} should execute 0 DB queries"

        ret_resp = anon_client.get(f"/api/v1/payments/vnpay/return/?{raw_qs}")
        assert ret_resp.status_code == 302, label
        parsed_loc = urllib.parse.urlparse(ret_resp["Location"])
        qs_map = urllib.parse.parse_qs(parsed_loc.query)
        assert qs_map["status"] == ["invalid_signature"], label
        assert qs_map["code"] == ["97"], label
        assert "txn_ref" not in qs_map, label

    wallet.refresh_from_db()
    assert wallet.balance == Decimal("0.00")
    assert WalletTransaction.objects.filter(wallet=wallet).count() == 0


@pytest.mark.django_db
@override_settings(**SYNTH_VNPAY_SETTINGS)
def test_vnpay_ipn_and_return_reject_invalid_utf8_percent_bytes(
    anon_client, wallet_customer_pair
):
    _, cust, wallet = wallet_customer_pair
    txn_ref = generate_signed_txn_ref(cust.id, 100000, SYNTH_SECRET)
    # Sign with U+FFFD replacement chars to prove Django's QueryDict errors='replace'
    # would otherwise accept invalid %FF%FE bytes on the wire.
    items_with_replacement = _base_vnpay_items(
        txn_ref=txn_ref,
        amount_vnd=100000,
        order_info="test\ufffd\ufffd",
    )
    sig_replacement = _independent_vnpay_sign(
        items_with_replacement, SYNTH_SECRET, mode="quote_plus"
    )
    wire_items = [(k, v) for k, v in items_with_replacement if k != "vnp_OrderInfo"]
    raw_qs = (
        urllib.parse.urlencode(wire_items)
        + "&vnp_OrderInfo=test%FF%FE"
        + f"&vnp_SecureHash={sig_replacement}"
    )

    with CaptureQueriesContext(connection) as ctx:
        ipn_resp = anon_client.get(f"/api/v1/payments/vnpay/ipn/?{raw_qs}")
    assert ipn_resp.status_code == 200
    assert ipn_resp.json()["RspCode"] == "97"
    assert len(ctx) == 0

    ret_resp = anon_client.get(f"/api/v1/payments/vnpay/return/?{raw_qs}")
    assert ret_resp.status_code == 302
    qs_map = urllib.parse.parse_qs(urllib.parse.urlparse(ret_resp["Location"]).query)
    assert qs_map["status"] == ["invalid_signature"]
    assert qs_map["code"] == ["97"]
    assert "txn_ref" not in qs_map

    wallet.refresh_from_db()
    assert wallet.balance == Decimal("0.00")


@pytest.mark.django_db
@override_settings(**SYNTH_VNPAY_SETTINGS)
@pytest.mark.parametrize(
    ("case_id", "order_info", "bank_tran_no", "wire_mode", "sign_mode", "expected_rsp"),
    [
        # 1. Spaces '+' wire + canonical quote_plus sig -> 00
        (
            "d5_01_space_plus_wire",
            "Nap tien vi",
            "VNP14000001",
            "quote_plus",
            "quote_plus",
            "00",
        ),
        # 2. Spaces '%20' wire + canonical '+' sig -> 00
        (
            "d5_02_space_pct20_wire_plus_sig",
            "Nap tien vi",
            "VNP14000001",
            "quote",
            "quote_plus",
            "00",
        ),
        # 3. Spaces '%20' wire + quote() '%20' sig -> 97
        (
            "d5_03_space_quote_pct20_sig",
            "Nap tien vi",
            "VNP14000001",
            "quote",
            "quote",
            "97",
        ),
        # 4. NodeJS unencoded (encode: false) sig -> 97
        (
            "d5_04_nodejs_unencoded_sig",
            "Nap tien vi",
            "VNP14000001",
            "quote_plus",
            "nodejs_unencoded",
            "97",
        ),
        # 5. Special chars : / . - _ ~ * % canonical quote_plus -> 00
        (
            "d5_05_special_chars_canonical",
            "Order: a/b.c-d_e~f*g%",
            "VNP14000001",
            "quote_plus",
            "quote_plus",
            "00",
        ),
        # 6. quote() keeping '/' unencoded -> 97
        (
            "d5_06_quote_slash_unencoded",
            "Path/a/b",
            "VNP14000001",
            "quote_plus",
            "quote",
            "97",
        ),
        # 7. Java URLEncoder keeping '*' unencoded -> 97
        (
            "d5_07_java_asterisk_unencoded",
            "Promo*2026",
            "VNP14000001",
            "quote_plus",
            "java_keep_asterisk",
            "97",
        ),
        # 8. Non-ASCII Vietnamese UTF-8 canonical quote_plus -> 00
        (
            "d5_08_utf8_vietnamese_canonical",
            "Nạp tiền ví",
            "VNP14000001",
            "quote_plus",
            "quote_plus",
            "00",
        ),
        # 9. Non-ASCII raw unencoded UTF-8 sig -> 97
        (
            "d5_09_utf8_raw_unencoded_sig",
            "Nạp tiền ví",
            "VNP14000001",
            "quote_plus",
            "nodejs_unencoded",
            "97",
        ),
        # 10. Empty value vnp_BankTranNo= skipped (Java/C#/Python) -> 00
        (
            "d5_10_empty_value_skipped",
            "Nap tien vi",
            "",
            "quote_plus",
            "quote_plus",
            "00",
        ),
        # 11. Empty value vnp_BankTranNo= included (PHP style) -> 97
        (
            "d5_11_empty_value_php_included",
            "Nap tien vi",
            "",
            "quote_plus",
            "php_include_empty",
            "97",
        ),
        # 12. Non-alphabetical key order (vnp_TxnRef before vnp_Amount) -> 00
        (
            "d5_12_non_alpha_key_order",
            "Nap tien vi",
            "VNP14000001",
            "reverse_order",
            "quote_plus",
            "00",
        ),
        # 13. Lowercase %3a on wire + uppercase %3A canonical sig -> 00
        (
            "d5_13_lowercase_wire_uppercase_sig",
            "Don: 123",
            "VNP14000001",
            "lowercase_percent",
            "quote_plus",
            "00",
        ),
        # 14. Lowercase %3a on wire + lowercase %3a sig -> 97
        (
            "d5_14_lowercase_sig_rejected",
            "Don: 123",
            "VNP14000001",
            "lowercase_percent",
            "lowercase_percent",
            "97",
        ),
    ],
)
def test_vnpay_ipn_d5_independent_encoding_vector_matrix_over_raw_http(
    anon_client,
    wallet_customer_pair,
    case_id,
    order_info,
    bank_tran_no,
    wire_mode,
    sign_mode,
    expected_rsp,
):
    _, cust, wallet = wallet_customer_pair
    amount_vnd = 100000
    txn_ref = generate_signed_txn_ref(cust.id, amount_vnd, SYNTH_SECRET)
    items = _base_vnpay_items(
        txn_ref=txn_ref,
        amount_vnd=amount_vnd,
        order_info=order_info,
        bank_tran_no=bank_tran_no,
    )
    sig = _independent_vnpay_sign(items, SYNTH_SECRET, mode=sign_mode)

    wire_items = list(items)
    if wire_mode == "reverse_order":
        wire_items.reverse()  # Places vnp_TxnRef first and vnp_Amount last

    if wire_mode == "quote":
        raw_qs = "&".join(
            f"{urllib.parse.quote(k)}={urllib.parse.quote(v)}" for k, v in wire_items
        )
    elif wire_mode == "lowercase_percent":
        raw_qs = "&".join(
            f"{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(v)}"
            for k, v in wire_items
        )
        raw_qs = re.sub(r"%[0-9A-F]{2}", lambda m: m.group(0).lower(), raw_qs)
    else:
        raw_qs = "&".join(
            f"{urllib.parse.quote_plus(k)}={urllib.parse.quote_plus(v)}"
            for k, v in wire_items
        )

    raw_qs = f"{raw_qs}&vnp_SecureHash={sig}"

    if expected_rsp == "97":
        with CaptureQueriesContext(connection) as ctx:
            resp = anon_client.get(f"/api/v1/payments/vnpay/ipn/?{raw_qs}")
        assert resp.status_code == 200, case_id
        assert resp.json()["RspCode"] == "97", case_id
        assert len(ctx) == 0, f"{case_id} must reject with 0 DB queries"
        wallet.refresh_from_db()
        assert wallet.balance == Decimal("0.00"), case_id
    else:
        resp = anon_client.get(f"/api/v1/payments/vnpay/ipn/?{raw_qs}")
        assert resp.status_code == 200, case_id
        assert resp.json()["RspCode"] == "00", case_id
        wallet.refresh_from_db()
        assert wallet.balance == Decimal(amount_vnd), case_id
        tx = WalletTransaction.objects.get(idempotency_key=f"vnpay-{txn_ref}")
        assert tx.kind == "TOPUP_VNPAY", case_id
        call_command("reconcile_wallets", fail_on_mismatch=True)
