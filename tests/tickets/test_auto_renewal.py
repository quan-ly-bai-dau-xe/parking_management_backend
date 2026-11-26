"""
Integration tests for automatic ticket renewal command and service (WP4 R2 & D6).
Verifies:
- MONTHLY / QUARTERLY / YEARLY tickets expiring on or before today (Asia/Ho_Chi_Minh) are auto-renewed.
- DAILY tickets are never auto-renewed.
- Idempotency on repeated runs within the same day (no double debit / duplicate renewal).
- Insufficient wallet balance -> ticket status becomes EXPIRED + single TICKET_EXPIRY notification per day.
- Timezone boundary (23:30 UTC == 06:30+07 next day in ICT).
- Wallet reconciliation invariant holds.
"""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounts.models import Account
from apps.content.models import Notification
from apps.customers.models import Customer
from apps.parking.models import ParkingSlot, ParkingZone, SlotAllowedVehicleType
from apps.tickets.models import Payment, Ticket, TicketRenewal, TicketType
from apps.tickets.services.auto_renewal import process_ticket_auto_renewals
from apps.vehicles.models import Vehicle, VehicleType
from apps.wallet.models import Wallet, WalletTransaction
from apps.wallet.services.wallet import credit_wallet

pytestmark = pytest.mark.django_db


def _setup_ticket_and_wallet(
    suffix: str,
    ticket_type_code: str,
    effective_to: datetime,
    wallet_balance: Decimal = Decimal("1000000.00"),
    create_wallet: bool = True,
):
    vtype = VehicleType.objects.first()
    assert vtype is not None
    ttype = TicketType.objects.get(code=ticket_type_code)
    acct = Account.objects.create(
        email=f"rnw_{suffix}@parking.local",
        role="CUSTOMER",
        is_active=True,
        password="!dummy_password_hash",
    )
    cust = Customer.objects.create(
        account=acct,
        code=f"KHR{suffix}",
        full_name=f"Khach Renewal {suffix}",
        phone=f"0966{suffix[-6:].zfill(6)}",
        identity_card_number=f"079098{suffix[-6:].zfill(6)}",
    )
    veh = Vehicle.objects.create(
        code=f"XER{suffix}",
        license_plate=f"51H-{suffix[-5:].zfill(5)}",
        license_plate_norm=f"51H{suffix[-5:].zfill(5)}",
        vehicle_type=vtype,
        customer=cust,
        model_name="City",
    )
    zone = ParkingZone.objects.first()
    assert zone is not None
    slot = ParkingSlot.objects.create(
        zone=zone,
        code=f"RN{suffix}",
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
        if wallet_balance > Decimal("0.00"):
            credit_wallet(
                wallet_id=wallet.id,
                amount=wallet_balance,
                kind="TOPUP_CASH",
                idempotency_key=f"init-rnw-{suffix}-{uuid.uuid4().hex[:6]}",
            )
            wallet.refresh_from_db()

    # Keep effective_from < effective_to and ensure ticket starts ACTIVE in DB
    eff_from = effective_to - timedelta(days=ttype.duration_days)
    ticket = Ticket.objects.create(
        code=f"TR{suffix[:6]}",
        vehicle=veh,
        customer=cust,
        slot=slot,
        ticket_type=ttype,
        status="ACTIVE",
        effective_from=eff_from,
        effective_to=effective_to,
        price=ttype.default_price,
    )
    return acct, cust, ticket, wallet, ttype


@pytest.mark.parametrize("code", ["MONTHLY", "QUARTERLY", "YEARLY"])
def test_auto_renewal_extends_subscription_and_debits_wallet(code):
    """MONTHLY/QUARTERLY/YEARLY ticket due today is renewed idempotently from wallet."""
    now = timezone.now()
    eff_to = now + timedelta(minutes=30)
    suffix = f"{uuid.uuid4().int % 100000:05d}"
    acct, _, ticket, wallet, ttype = _setup_ticket_and_wallet(
        suffix, code, eff_to, wallet_balance=Decimal("10000000.00")
    )
    assert ticket.status == "ACTIVE"
    assert wallet is not None

    summary = process_ticket_auto_renewals(now=now)
    assert summary["renewed"] >= 1
    assert summary["errors"] == 0

    ticket.refresh_from_db()
    wallet.refresh_from_db()
    assert ticket.status == "ACTIVE"
    assert ticket.effective_to == eff_to + timedelta(days=ttype.duration_days)
    assert wallet.balance == Decimal("10000000.00") - ttype.default_price

    renewal = TicketRenewal.objects.get(ticket=ticket)
    assert renewal.renewed_by is None
    assert renewal.additional_price == ttype.default_price
    assert renewal.new_effective_to == ticket.effective_to

    payment = Payment.objects.get(renewal=renewal)
    assert payment.method == "WALLET"
    assert payment.status == "PAID"
    assert payment.amount == ttype.default_price

    tx = WalletTransaction.objects.get(wallet=wallet, reference_type="TICKET_RENEWAL")
    assert tx.kind == "TICKET_RENEWAL"
    assert tx.transaction_type == "DEBIT"
    assert tx.amount == -ttype.default_price
    assert tx.reference_id == renewal.id

    notif = Notification.objects.get(
        recipient_account=acct, notification_type="PAYMENT"
    )
    assert ticket.code in notif.title

    # Running a second time on the same day must be idempotent (no double charge)
    summary2 = process_ticket_auto_renewals(now=now)
    assert summary2["renewed"] == 0
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("10000000.00") - ttype.default_price
    assert TicketRenewal.objects.filter(ticket=ticket).count() == 1

    call_command("reconcile_wallets", "--fail-on-mismatch")


def test_auto_renewal_skips_daily_tickets():
    """DAILY tickets must NOT be auto-renewed."""
    now = timezone.now()
    eff_to = now + timedelta(minutes=20)
    suffix = f"{uuid.uuid4().int % 100000:05d}"
    _, _, ticket, wallet, _ = _setup_ticket_and_wallet(
        suffix, "DAILY", eff_to, wallet_balance=Decimal("500000.00")
    )
    assert wallet is not None

    process_ticket_auto_renewals(now=now)
    ticket.refresh_from_db()
    wallet.refresh_from_db()
    assert ticket.effective_to == eff_to
    assert wallet.balance == Decimal("500000.00")
    assert TicketRenewal.objects.filter(ticket=ticket).count() == 0


def test_auto_renewal_insufficient_balance_marks_expired_and_single_notification():
    """Insufficient balance -> ticket status becomes EXPIRED + single TICKET_EXPIRY notification."""
    now = timezone.now()
    eff_to = now + timedelta(minutes=30)
    suffix = f"{uuid.uuid4().int % 100000:05d}"
    acct, _, ticket, wallet, _ = _setup_ticket_and_wallet(
        suffix, "MONTHLY", eff_to, wallet_balance=Decimal("100000.00")
    )
    assert wallet is not None

    summary = process_ticket_auto_renewals(now=now)
    assert summary["expired"] >= 1
    assert summary["errors"] == 0

    ticket.refresh_from_db()
    wallet.refresh_from_db()
    assert ticket.status == "EXPIRED"
    assert wallet.balance == Decimal("100000.00")
    assert TicketRenewal.objects.filter(ticket=ticket).count() == 0
    assert Payment.objects.filter(renewal__ticket=ticket).count() == 0

    notifs = Notification.objects.filter(
        recipient_account=acct, notification_type="TICKET_EXPIRY"
    )
    assert notifs.count() == 1
    assert ticket.code in notifs.first().title

    # Re-running does not spam notifications or charge wallet
    process_ticket_auto_renewals(now=now)
    assert (
        Notification.objects.filter(
            recipient_account=acct, notification_type="TICKET_EXPIRY"
        ).count()
        == 1
    )


def test_auto_renewal_asia_ho_chi_minh_boundary():
    """
    23:30 UTC == 06:30+07 next day in Asia/Ho_Chi_Minh.
    A ticket expiring at 20:00+07 on 2026-11-19 is due when cron runs at 2026-11-18T17:30Z (2026-11-19 00:30+07).
    """
    now_run = timezone.now()
    # Set ticket effective_to 25 hours from now, then simulate running at a timestamp in the same ICT day
    eff_to = now_run + timedelta(hours=25)
    suffix = f"{uuid.uuid4().int % 100000:05d}"
    _, _, ticket, wallet, ttype = _setup_ticket_and_wallet(
        suffix, "MONTHLY", eff_to, wallet_balance=Decimal("1000000.00")
    )
    assert wallet is not None

    # Compute 00:30+07 on the ICT date of eff_to (which is 17:30 UTC on the previous UTC day!)
    hcm_date = eff_to.astimezone(datetime.now(UTC).tzinfo)
    del hcm_date
    from apps.tickets.services.auto_renewal import HCM_TZ

    eff_hcm_date = eff_to.astimezone(HCM_TZ).date()
    run_at_ict_morning = datetime(
        eff_hcm_date.year, eff_hcm_date.month, eff_hcm_date.day, 0, 30, 0, tzinfo=HCM_TZ
    ).astimezone(UTC)

    summary = process_ticket_auto_renewals(now=run_at_ict_morning)
    assert summary["renewed"] >= 1
    ticket.refresh_from_db()
    assert ticket.effective_to == eff_to + timedelta(days=ttype.duration_days)


def test_management_command_dry_run_and_execute():
    """Management command `process_ticket_auto_renewals --dry-run` does not mutate DB."""
    now = timezone.now()
    eff_to = now + timedelta(minutes=15)
    suffix = f"{uuid.uuid4().int % 100000:05d}"
    _, _, ticket, wallet, _ = _setup_ticket_and_wallet(
        suffix, "MONTHLY", eff_to, wallet_balance=Decimal("1000000.00")
    )
    assert wallet is not None

    call_command("process_ticket_auto_renewals", "--dry-run")
    ticket.refresh_from_db()
    wallet.refresh_from_db()
    assert ticket.effective_to == eff_to
    assert wallet.balance == Decimal("1000000.00")

    call_command("process_ticket_auto_renewals")
    ticket.refresh_from_db()
    wallet.refresh_from_db()
    assert ticket.effective_to > eff_to
    assert wallet.balance < Decimal("1000000.00")
