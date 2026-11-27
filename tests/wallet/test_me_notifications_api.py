"""
WP3 (K3): Integration tests for Customer Self-Service Notifications API
(/api/v1/me/notifications/, /read/, /read-all/).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.content.models import Notification
from apps.customers.models import Customer

pytestmark = pytest.mark.django_db


def _create_customer_client(prefix: str) -> tuple[Account, Customer, APIClient]:
    suffix = uuid.uuid4().hex[:6].upper()
    acc = Account.objects.create_user(
        email=f"{prefix}_{suffix}@parking.local",
        phone=f"09{int(uuid.uuid4().int % 100000000):08d}",
        password="TestPassword123!",
        role="CUSTOMER",
        is_active=True,
    )
    cust = Customer.objects.create(
        account=acc,
        code=f"KN{suffix}"[:10],
        full_name=f"Khach Notif {suffix}",
        phone=acc.phone,
        identity_card_number=f"079{int(uuid.uuid4().int % 1000000000):09d}",
        status="ACTIVE",
    )
    client = APIClient()
    client.force_authenticate(user=acc)
    return acc, cust, client


def test_me_notifications_list_and_permission_matrix(
    anon_client, customer_client, staff_client, manager_client, wallet_customer_pair
):
    acc, _, _ = wallet_customer_pair

    notif = Notification.objects.create(
        recipient_account_id=acc.id,
        title="Số dư ví không đủ tại cổng ra (Cổng ra 1)",
        content=(
            "Xe 51A-897.** cần thanh toán 20,000 VND nhưng số dư ví hiện tại là 5,000 VND "
            "(còn thiếu 15,000 VND). Vui lòng nạp thêm tối thiểu 15,000 VND vào ví hoặc thanh toán tại quầy."
        ),
        notification_type="PAYMENT",
        is_read=False,
        read_at=None,
    )

    # Role matrix
    assert anon_client.get("/api/v1/me/notifications/").status_code == 401
    assert staff_client.get("/api/v1/me/notifications/").status_code == 403
    assert manager_client.get("/api/v1/me/notifications/").status_code == 403

    orphan_acc = Account.objects.create_user(
        email=f"orphan_notif_{uuid.uuid4().hex[:6]}@example.com",
        password="TestPassword123!",
        role="CUSTOMER",
    )
    orphan_client = APIClient()
    orphan_client.force_authenticate(user=orphan_acc)
    assert orphan_client.get("/api/v1/me/notifications/").status_code == 403

    # Authenticated customer -> 200 with zero N+1 (<= 4 queries)
    with CaptureQueriesContext(connection) as ctx:
        resp = customer_client.get("/api/v1/me/notifications/")
    assert resp.status_code == 200
    assert len(ctx) <= 4

    data = resp.json()
    assert data["unread_count"] == 1
    assert data["count"] == 1
    assert len(data["results"]) == 1
    item = data["results"][0]
    assert item["id"] == notif.id
    assert item["notification_type"] == "PAYMENT"
    assert item["is_read"] is False
    assert item["read_at"] is None
    assert "15,000" in item["content"]
    assert Decimal(item["missing_amount"]) == Decimal("15000.00")


def test_me_notifications_filters_isolation_and_mark_read_pair_constraint(
    customer_client, wallet_customer_pair
):
    acc_a, _, _ = wallet_customer_pair
    acc_b, _, client_b = _create_customer_client("notif_b")

    n1 = Notification.objects.create(
        recipient_account_id=acc_a.id,
        title="Thiếu số dư",
        content="Xe 51A-897.** cần thanh toán 20,000 VND nhưng số dư ví hiện tại là 5,000 VND (còn thiếu 15,000 VND).",
        notification_type="PAYMENT",
        is_read=False,
        read_at=None,
    )
    n2 = Notification.objects.create(
        recipient_account_id=acc_a.id,
        title="Thông báo hệ thống",
        content="Bảo trì định kỳ.",
        notification_type="SYSTEM",
        is_read=True,
        read_at=timezone.now(),
    )
    other_n = Notification.objects.create(
        recipient_account_id=acc_b.id,
        title="Riêng tư B",
        content="Thông báo của B",
        notification_type="PAYMENT",
        is_read=False,
        read_at=None,
    )

    # Filters: is_read & notification_type
    r_unread = customer_client.get("/api/v1/me/notifications/?is_read=false")
    assert r_unread.status_code == 200
    assert [row["id"] for row in r_unread.json()["results"]] == [n1.id]

    r_sys = customer_client.get("/api/v1/me/notifications/?notification_type=SYSTEM")
    assert r_sys.status_code == 200
    assert [row["id"] for row in r_sys.json()["results"]] == [n2.id]

    # Invalid filter value -> 400 PROP-GEN-P01
    r_bad = customer_client.get("/api/v1/me/notifications/?is_read=maybe")
    assert r_bad.status_code == 400
    assert r_bad.json()["code"] == "PROP-GEN-P01"

    # Cross-customer isolation: Customer A cannot read/mark-read Customer B's notification -> 404 MSG-4.4.1-M01
    r_cross = customer_client.post(f"/api/v1/me/notifications/{other_n.id}/read/")
    assert r_cross.status_code == 404
    assert r_cross.json()["code"] == "MSG-4.4.1-M01"

    # Customer A marks n1 read -> sets both is_read=True and read_at != None (ck_notification_read_pair)
    r_read = customer_client.post(f"/api/v1/me/notifications/{n1.id}/read/")
    assert r_read.status_code == 200
    assert r_read.json()["unread_count"] == 0
    assert r_read.json()["notification"]["is_read"] is True
    assert r_read.json()["notification"]["read_at"] is not None

    n1.refresh_from_db()
    assert n1.is_read is True
    assert n1.read_at is not None

    # Customer B has 1 unread, tests read-all
    r_b_all = client_b.post("/api/v1/me/notifications/read-all/")
    assert r_b_all.status_code == 200
    assert r_b_all.json()["updated_count"] == 1
    assert r_b_all.json()["unread_count"] == 0
    other_n.refresh_from_db()
    assert other_n.is_read is True
    assert other_n.read_at is not None


def test_extract_missing_amount_handles_decimal_dot_zero_zero_and_thousands_separators():
    from apps.wallet.serializers.me import _extract_missing_amount

    assert (
        _extract_missing_amount(
            "Xe 51A-897.** cần thanh toán 20,000 VND (còn thiếu 15,000 VND)."
        )
        == "15000.00"
    )
    assert (
        _extract_missing_amount("Vui lòng nạp thêm tối thiểu 15,000.00 VND vào ví.")
        == "15000.00"
    )
    assert (
        _extract_missing_amount("Vui lòng nạp thêm tối thiểu 15000.00 VND vào ví.")
        == "15000.00"
    )
    assert (
        _extract_missing_amount("Còn thiếu 1,250,000.50 VND khi qua cổng.")
        == "1250000.50"
    )
    assert _extract_missing_amount("Còn thiếu 15.000 VND khi qua cổng.") == "15000.00"
    assert _extract_missing_amount("Còn thiếu 0.00 VND.") is None
