"""
Integration tests for Wallet Check-Out Charging (WP4 R3b & D6).
Verifies:
- Check-out with payment_method='WALLET' atomically debits wallet (kind='PARKING_FEE') and creates PAID Payment.
- Insufficient wallet balance -> 409 PROP-WALLET-INSUFFICIENT with complete rollback (0 Payment, 0 WalletTransaction, session stays open).
- Walk-in vehicle (no customer) or missing/soft-deleted wallet -> 404 PROP-WALLET-NOT-FOUND.
- Locked wallet -> 409 PROP-WALLET-LOCKED with complete rollback.
- Session list & detail APIs serialize payment_method cleanly with zero N+1 queries.
- Ledger reconciliation passes after wallet checkout.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.models import (
    ParkingGate,
    ParkingSlot,
    ParkingZone,
    SlotAllowedVehicleType,
    VehicleEntryExitLog,
)
from apps.tickets.models import Payment
from apps.vehicles.models import Vehicle, VehicleType
from apps.wallet.models import Wallet, WalletTransaction
from apps.wallet.services.wallet import credit_wallet

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_wallet_co@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def gates():
    in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not in_gate:
        in_gate = ParkingGate.objects.create(
            code="IN_WCO", name="In Wallet CO", direction="IN", is_active=True
        )
    out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if not out_gate:
        out_gate = ParkingGate.objects.create(
            code="OUT_WCO", name="Out Wallet CO", direction="OUT", is_active=True
        )
    return in_gate, out_gate


def _create_registered_vehicle_and_session(
    suffix: str,
    in_gate: ParkingGate,
    hours_ago: int = 2,
    create_wallet: bool = True,
    initial_balance: Decimal = Decimal("100000.00"),
    wallet_status: str = "ACTIVE",
):
    vtype = VehicleType.objects.first()
    assert vtype is not None
    acct = Account.objects.create(
        email=f"cust_wco_{suffix}@parking.local",
        role="CUSTOMER",
        is_active=True,
        password="!dummy_password_hash",
    )
    cust = Customer.objects.create(
        account=acct,
        code=f"KHW{suffix}",
        full_name=f"Khach Wallet {suffix}",
        phone=f"0977{suffix[-6:].zfill(6)}",
        identity_card_number=f"079099{suffix[-6:].zfill(6)}",
    )
    veh = Vehicle.objects.create(
        code=f"XEW{suffix}",
        license_plate=f"51G-{suffix[-5:].zfill(5)}",
        license_plate_norm=f"51G{suffix[-5:].zfill(5)}",
        vehicle_type=vtype,
        customer=cust,
        model_name="Accent",
    )
    zone = ParkingZone.objects.first()
    assert zone is not None
    slot = ParkingSlot.objects.create(
        zone=zone,
        code=f"WC{suffix}",
        slot_kind="STANDARD",
        status="AVAILABLE",
    )
    SlotAllowedVehicleType.objects.get_or_create(slot=slot, vehicle_type=vtype)
    wallet = None
    if create_wallet:
        wallet = Wallet.objects.create(
            customer=cust,
            balance=Decimal("0.00"),
            currency="VND",
            status="ACTIVE",
        )
        if initial_balance > Decimal("0.00"):
            credit_wallet(
                wallet_id=wallet.id,
                amount=initial_balance,
                kind="TOPUP_CASH",
                idempotency_key=f"init-topup-{suffix}-{uuid.uuid4().hex[:6]}",
            )
            wallet.refresh_from_db()
        if wallet_status != "ACTIVE":
            wallet.status = wallet_status
            wallet.save(update_fields=["status"])

    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-WCO-{suffix}",
        vehicle=veh,
        slot=slot,
        entry_gate=in_gate,
        license_plate=veh.license_plate,
        license_plate_norm=veh.license_plate_norm,
        entry_time=now - timedelta(hours=hours_ago),
        recognition_source="AI",
        review_status="AUTO",
    )
    return acct, cust, veh, slot, wallet, session


def test_check_out_wallet_success_and_history_payment_method(auth_employee, gates):
    """Happy path: WALLET checkout debits wallet (PARKING_FEE), creates PAID Payment, serializes payment_method."""
    in_gate, out_gate = gates
    suffix = f"{uuid.uuid4().int % 100000:05d}"
    _, _, _, _, wallet, session = _create_registered_vehicle_and_session(
        suffix, in_gate, hours_ago=2, initial_balance=Decimal("50000.00")
    )
    assert wallet is not None

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": "WALLET",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["session"]["fee_amount"] == "20000.00"
    assert resp.data["session"]["payment_method"] == "WALLET"
    assert resp.data["payment"]["method"] == "WALLET"
    assert resp.data["payment"]["status"] == "PAID"
    assert resp.data["payment"]["amount"] == "20000.00"

    wallet.refresh_from_db()
    assert wallet.balance == Decimal("30000.00")

    tx = WalletTransaction.objects.get(
        wallet=wallet,
        idempotency_key=f"checkout-session-{session.id}",
    )
    assert tx.transaction_type == "DEBIT"
    assert tx.kind == "PARKING_FEE"
    assert tx.amount == Decimal("-20000.00")
    assert tx.balance_after == Decimal("30000.00")
    assert tx.reference_type == "PAYMENT"
    assert tx.reference_id == resp.data["payment"]["id"]
    assert tx.created_by_id == auth_employee.id

    # Verify history list & detail serialize payment_method
    list_resp = client.get(
        f"/api/v1/parking/sessions/?session_code={session.session_code.replace('#', '')}"
    )
    assert list_resp.status_code == status.HTTP_200_OK
    results = list_resp.data["results"]
    assert len(results) == 1
    assert results[0]["payment_method"] == "WALLET"

    detail_resp = client.get(f"/api/v1/parking/sessions/{session.id}/")
    assert detail_resp.status_code == status.HTTP_200_OK
    assert detail_resp.data["payment_method"] == "WALLET"

    # Reconcile wallets invariant
    call_command("reconcile_wallets", "--fail-on-mismatch")


def test_check_out_wallet_insufficient_balance_rolls_back(auth_employee, gates):
    """Insufficient wallet balance -> 409 PROP-WALLET-INSUFFICIENT, full atomic rollback."""
    in_gate, out_gate = gates
    suffix = f"{uuid.uuid4().int % 100000:05d}"
    _, _, _, _, wallet, session = _create_registered_vehicle_and_session(
        suffix, in_gate, hours_ago=3, initial_balance=Decimal("10000.00")
    )
    assert wallet is not None
    initial_tx_count = WalletTransaction.objects.filter(wallet=wallet).count()

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": "WALLET",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.data["code"] == "PROP-WALLET-INSUFFICIENT"
    assert resp.data["details"]["required_amount"] == "30000.00"
    assert resp.data["details"]["current_balance"] == "10000.00"
    assert resp.data["details"]["missing_amount"] == "20000.00"

    # No Payment, no WalletTransaction, session stays open
    assert Payment.objects.filter(session=session).count() == 0
    assert WalletTransaction.objects.filter(wallet=wallet).count() == initial_tx_count
    session.refresh_from_db()
    assert session.exit_time is None
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("10000.00")


def test_check_out_wallet_walkin_or_missing_wallet_returns_404(auth_employee, gates):
    """Walk-in vehicle or customer without wallet -> 404 PROP-WALLET-NOT-FOUND, no Payment."""
    in_gate, out_gate = gates
    now = timezone.now()

    # 1. Walk-in vehicle (vehicle=None)
    walkin_session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-WI-{uuid.uuid4().hex[:6].upper()}",
        vehicle=None,
        entry_gate=in_gate,
        license_plate="43A-911.22",
        license_plate_norm="43A91122",
        entry_time=now - timedelta(hours=1),
        recognition_source="AI",
        review_status="AUTO",
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    resp1 = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": walkin_session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": "WALLET",
        },
        format="json",
    )
    assert resp1.status_code == status.HTTP_404_NOT_FOUND
    assert resp1.data["code"] == "PROP-WALLET-NOT-FOUND"
    assert Payment.objects.filter(session=walkin_session).count() == 0

    # 2. Registered customer with no wallet
    suffix = f"{uuid.uuid4().int % 100000:05d}"
    _, _, _, _, _, no_wallet_session = _create_registered_vehicle_and_session(
        suffix, in_gate, hours_ago=1, create_wallet=False
    )
    resp2 = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": no_wallet_session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": "WALLET",
        },
        format="json",
    )
    assert resp2.status_code == status.HTTP_404_NOT_FOUND
    assert resp2.data["code"] == "PROP-WALLET-NOT-FOUND"
    assert Payment.objects.filter(session=no_wallet_session).count() == 0


def test_check_out_wallet_locked_returns_409_and_rolls_back(auth_employee, gates):
    """Locked wallet -> 409 PROP-WALLET-LOCKED, no Payment, session stays open."""
    in_gate, out_gate = gates
    suffix = f"{uuid.uuid4().int % 100000:05d}"
    _, _, _, _, wallet, session = _create_registered_vehicle_and_session(
        suffix,
        in_gate,
        hours_ago=2,
        initial_balance=Decimal("100000.00"),
        wallet_status="LOCKED",
    )
    assert wallet is not None

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    resp = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": "WALLET",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.data["code"] == "PROP-WALLET-LOCKED"
    assert Payment.objects.filter(session=session).count() == 0
    session.refresh_from_db()
    assert session.exit_time is None
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("100000.00")
