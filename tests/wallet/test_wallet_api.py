import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext

from apps.accounts.models import Account
from apps.audit.models import ActivityLog


@pytest.mark.django_db
def test_me_wallet_permission_matrix(
    anon_client, customer_client, staff_client, manager_client, wallet_customer_pair
):
    _, cust, _ = wallet_customer_pair

    # Anonymous -> 401
    assert anon_client.get("/api/v1/me/wallet/").status_code == 401

    # Employee / Manager -> 403 on /me/
    assert staff_client.get("/api/v1/me/wallet/").status_code == 403
    assert manager_client.get("/api/v1/me/wallet/").status_code == 403

    # CUSTOMER account without Customer record -> 403
    orphan_acc = Account.objects.create_user(
        email=f"orphan_{uuid.uuid4().hex[:6]}@example.com",
        password="TestPassword123!",
        role="CUSTOMER",
    )
    from rest_framework.test import APIClient

    orphan_client = APIClient()
    orphan_client.force_authenticate(user=orphan_acc)
    assert orphan_client.get("/api/v1/me/wallet/").status_code == 403

    # Valid customer -> 200
    resp = customer_client.get("/api/v1/me/wallet/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["customer_id"] == cust.id
    assert data["currency"] == "VND"
    assert data["status"] == "ACTIVE"
    assert Decimal(data["balance"]) == Decimal("0.00")


@pytest.mark.django_db
def test_me_wallet_topups_and_transactions_flow(customer_client, wallet_customer_pair):
    _, _, wallet = wallet_customer_pair
    idem_key = f"vqr-{uuid.uuid4().hex}"

    # Topup 200,000 VND via simulated VietQR
    resp = customer_client.post(
        "/api/v1/me/wallet/topups/",
        data={"amount": 200000, "idempotency_key": idem_key},
        format="json",
    )
    assert resp.status_code == 201
    body = resp.json()
    assert Decimal(body["wallet"]["balance"]) == Decimal("200000.00")
    assert body["transaction"]["kind"] == "TOPUP_VIETQR"
    assert body["transaction"]["transaction_type"] == "CREDIT"
    assert body["replayed"] is False
    assert body["simulated_qr"]["is_simulated"] is True

    # Idempotent retry -> 200 with replayed=True and no double credit
    replay = customer_client.post(
        "/api/v1/me/wallet/topups/",
        data={"amount": 200000, "idempotency_key": idem_key},
        format="json",
    )
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert Decimal(replay.json()["wallet"]["balance"]) == Decimal("200000.00")

    # Query transactions with direction filter + bounded queries
    with CaptureQueriesContext(connection) as ctx:
        tx_resp = customer_client.get(
            "/api/v1/me/wallet/transactions/?direction=deposit"
        )
    assert tx_resp.status_code == 200
    assert len(ctx) <= 8
    results = tx_resp.json()["results"]
    assert len(results) == 1
    assert Decimal(results[0]["amount"]) == Decimal("200000.00")

    # Payment filter should be empty
    pay_resp = customer_client.get("/api/v1/me/wallet/transactions/?direction=payment")
    assert pay_resp.status_code == 200
    assert pay_resp.json()["count"] == 0


@pytest.mark.django_db
@override_settings(WALLET_SIMULATED_TOPUP_ENABLED=False)
def test_me_wallet_topup_rejected_when_simulated_disabled(customer_client):
    resp = customer_client.post(
        "/api/v1/me/wallet/topups/",
        data={"amount": 50000, "idempotency_key": f"dis-{uuid.uuid4().hex}"},
        format="json",
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "PROP-WALLET-SIMULATED-DISABLED"


@pytest.mark.django_db
def test_me_wallet_topup_validation_errors(customer_client):
    resp = customer_client.post(
        "/api/v1/me/wallet/topups/",
        data={"amount": -5000, "idempotency_key": f"neg-{uuid.uuid4().hex}"},
        format="json",
    )
    assert resp.status_code == 400


@pytest.mark.django_db
def test_staff_customer_wallet_endpoints_and_audit(
    anon_client, customer_client, staff_client, manager_client, wallet_customer_pair
):
    _, cust, wallet = wallet_customer_pair

    # Unauthorized roles
    assert anon_client.get(f"/api/v1/customers/{cust.id}/wallet/").status_code == 401
    assert (
        customer_client.get(f"/api/v1/customers/{cust.id}/wallet/").status_code == 403
    )
    assert (
        customer_client.post(
            f"/api/v1/customers/{cust.id}/wallet/topup/",
            data={"amount": 50000},
            format="json",
        ).status_code
        == 403
    )

    # Staff cash top-up -> 201
    topup_key = f"cash-{uuid.uuid4().hex}"
    r1 = staff_client.post(
        f"/api/v1/customers/{cust.id}/wallet/topup/",
        data={
            "amount": 300000,
            "payment_method": "CASH",
            "idempotency_key": topup_key,
            "note": "Thu tiền mặt tại quầy",
        },
        format="json",
    )
    assert r1.status_code == 201
    assert Decimal(r1.json()["wallet"]["balance"]) == Decimal("300000.00")
    assert r1.json()["transaction"]["kind"] == "TOPUP_CASH"

    # Manager retrieves wallet & transactions
    r_get = manager_client.get(f"/api/v1/customers/{cust.id}/wallet/")
    assert r_get.status_code == 200
    assert Decimal(r_get.json()["balance"]) == Decimal("300000.00")

    r_tx = manager_client.get(f"/api/v1/customers/{cust.id}/wallet/transactions/")
    assert r_tx.status_code == 200
    assert r_tx.json()["count"] == 1

    # Customer detail endpoint exposes wallet_balance
    r_detail = staff_client.get(f"/api/v1/customers/{cust.id}/")
    assert r_detail.status_code == 200
    assert Decimal(r_detail.json()["wallet_balance"]) == Decimal("300000.00")

    assert (
        ActivityLog.objects.filter(
            action="WALLET_STAFF_TOPUP", entity_id=wallet.id
        ).count()
        == 1
    )
