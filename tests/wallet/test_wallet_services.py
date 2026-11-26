import threading
import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction

from apps.accounts.models import Account
from apps.audit.models import ActivityLog
from apps.core.exceptions import BusinessAPIException
from apps.customers.services.customers import create_customer
from apps.wallet.models import Wallet, WalletTransaction
from apps.wallet.services.wallet import (
    InsufficientWalletBalanceError,
    credit_wallet,
    debit_wallet,
    ensure_wallet_for_customer,
    staff_topup_wallet,
)


@pytest.mark.django_db
def test_credit_and_debit_wallet_precision_and_row_version(wallet_customer_pair):
    acc, cust, wallet = wallet_customer_pair
    assert wallet.balance == Decimal("0.00")
    assert wallet.row_version == 1

    tx1 = credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("250000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"credit-1-{uuid.uuid4().hex}",
        note="Nạp tiền lần 1",
        actor_id=acc.id,
    )
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("250000.00")
    assert wallet.row_version == 2
    assert tx1.transaction_type == "CREDIT"
    assert tx1.amount == Decimal("250000.00")
    assert tx1.balance_after == Decimal("250000.00")

    tx2 = debit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("50000.00"),
        kind="TICKET_PURCHASE",
        idempotency_key=f"debit-1-{uuid.uuid4().hex}",
        note="Mua vé ngày",
        reference_type="TICKET",
        reference_id=101,
        actor_id=acc.id,
    )
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("200000.00")
    assert wallet.row_version == 3
    assert tx2.transaction_type == "DEBIT"
    assert tx2.amount == Decimal("-50000.00")
    assert tx2.balance_after == Decimal("200000.00")


@pytest.mark.django_db
def test_credit_and_debit_idempotency_replay_and_conflict(wallet_customer_pair):
    acc, _, wallet = wallet_customer_pair
    c_key = f"idem-c-{uuid.uuid4().hex}"
    tx1 = credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("100000.00"),
        kind="TOPUP_VIETQR",
        idempotency_key=c_key,
    )
    tx1_replay = credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("100000.00"),
        kind="TOPUP_VIETQR",
        idempotency_key=c_key,
    )
    assert tx1.id == tx1_replay.id
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("100000.00")

    # Conflicting amount with same key must raise 409
    with pytest.raises(BusinessAPIException) as exc_info:
        credit_wallet(
            wallet_id=wallet.id,
            amount=Decimal("200000.00"),
            kind="TOPUP_VIETQR",
            idempotency_key=c_key,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "PROP-WALLET-IDEMPOTENCY-CONFLICT"

    # Debit 80,000 leaving 20,000; then replay same debit key (even though 20,000 < 80,000!)
    d_key = f"idem-d-{uuid.uuid4().hex}"
    d_tx1 = debit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("80000.00"),
        kind="PARKING_FEE",
        idempotency_key=d_key,
    )
    d_tx_replay = debit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("80000.00"),
        kind="PARKING_FEE",
        idempotency_key=d_key,
    )
    assert d_tx1.id == d_tx_replay.id
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("20000.00")


@pytest.mark.django_db
def test_debit_insufficient_balance_never_goes_negative(wallet_customer_pair):
    _, _, wallet = wallet_customer_pair
    credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("30000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"seed-bal-{uuid.uuid4().hex}",
    )
    tx_before = WalletTransaction.objects.filter(wallet_id=wallet.id).count()
    wallet.refresh_from_db()
    ver_before = wallet.row_version

    with pytest.raises(InsufficientWalletBalanceError) as exc_info:
        debit_wallet(
            wallet_id=wallet.id,
            amount=Decimal("50000.00"),
            kind="TICKET_PURCHASE",
            idempotency_key=f"overdebit-{uuid.uuid4().hex}",
        )

    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "PROP-WALLET-INSUFFICIENT"
    assert exc_info.value.details["missing_amount"] == "20000.00"

    wallet.refresh_from_db()
    assert wallet.balance == Decimal("30000.00")
    assert wallet.row_version == ver_before
    assert WalletTransaction.objects.filter(wallet_id=wallet.id).count() == tx_before


@pytest.mark.django_db
def test_locked_wallet_blocks_mutations(wallet_customer_pair):
    _, _, wallet = wallet_customer_pair
    Wallet.objects.filter(id=wallet.id).update(status="LOCKED")

    with pytest.raises(BusinessAPIException) as exc_c:
        credit_wallet(
            wallet_id=wallet.id,
            amount=Decimal("10000.00"),
            kind="TOPUP_CASH",
            idempotency_key=f"locked-c-{uuid.uuid4().hex}",
        )
    assert exc_c.value.status_code == 409
    assert exc_c.value.code == "PROP-WALLET-LOCKED"

    with pytest.raises(BusinessAPIException) as exc_d:
        debit_wallet(
            wallet_id=wallet.id,
            amount=Decimal("10000.00"),
            kind="PARKING_FEE",
            idempotency_key=f"locked-d-{uuid.uuid4().hex}",
        )
    assert exc_d.value.status_code == 409
    assert exc_d.value.code == "PROP-WALLET-LOCKED"


@pytest.mark.django_db(transaction=True)
def test_concurrent_double_debit_exactly_one_succeeds():
    """
    Concurrency test: 2 threads simultaneously debit 60,000 VND from a 100,000 VND wallet
    with distinct idempotency keys. Exactly 1 must succeed and 1 must raise InsufficientWalletBalanceError.
    """
    suffix = uuid.uuid4().hex[:6]
    cust = create_customer(
        {
            "full_name": "Concurrency Customer",
            "identity_card_number": f"079{uuid.uuid4().int % 10**9:09d}",
            "phone": f"09{uuid.uuid4().int % 10**8:08d}",
            "email": f"conc_{suffix}@example.com",
        }
    )
    wallet = ensure_wallet_for_customer(cust.id)
    credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("100000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"conc-init-{suffix}",
    )

    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def worker(idx: int) -> None:
        connection.close()
        try:
            barrier.wait(timeout=5)
            debit_wallet(
                wallet_id=wallet.id,
                amount=Decimal("60000.00"),
                kind="PARKING_FEE",
                idempotency_key=f"conc-debit-{suffix}-{idx}",
            )
            with lock:
                results.append("OK")
        except InsufficientWalletBalanceError:
            with lock:
                results.append("INSUFFICIENT")
        finally:
            connection.close()

    t1 = threading.Thread(target=worker, args=(1,))
    t2 = threading.Thread(target=worker, args=(2,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert sorted(results) == ["INSUFFICIENT", "OK"]
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("40000.00")


@pytest.mark.django_db
def test_wallet_transaction_append_only_immutability(wallet_customer_pair):
    _, _, wallet = wallet_customer_pair
    tx = credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("50000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"imm-{uuid.uuid4().hex}",
    )

    # Python ORM layer defense-in-depth
    with pytest.raises(PermissionDenied):
        tx.note = "tampered"
        tx.save()

    with pytest.raises(PermissionDenied):
        tx.delete()

    # PostgreSQL trigger defense
    with pytest.raises(DatabaseError), connection.cursor() as cursor:
        cursor.execute(
            "UPDATE wallet_transaction SET note = 'sql_tamper' WHERE id = %s",
            [tx.id],
        )

    with pytest.raises(DatabaseError), connection.cursor() as cursor:
        cursor.execute("DELETE FROM wallet_transaction WHERE id = %s", [tx.id])


@pytest.mark.django_db
def test_wallet_soft_delete_blocked_when_balance_positive(wallet_customer_pair):
    acc, _, wallet = wallet_customer_pair
    credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("10000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"sd-{uuid.uuid4().hex}",
    )
    wallet.refresh_from_db()

    with pytest.raises(DatabaseError), transaction.atomic():
        wallet.soft_delete(user=acc)

    # Drain balance to 0 -> soft delete succeeds
    debit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("10000.00"),
        kind="ADJUSTMENT",
        idempotency_key=f"sd-drain-{uuid.uuid4().hex}",
    )
    wallet.refresh_from_db()
    wallet.soft_delete(user=acc)
    assert Wallet.objects.filter(id=wallet.id).exists() is False


@pytest.mark.django_db
def test_staff_topup_logs_activity_once_on_idempotent_replay(
    wallet_customer_pair, staff_employee
):
    _, cust, wallet = wallet_customer_pair
    staff_acc, _ = staff_employee
    key = f"staff-idem-{uuid.uuid4().hex}"

    w1, tx1, created1 = staff_topup_wallet(
        customer_id=cust.id,
        amount=Decimal("150000.00"),
        actor_id=staff_acc.id,
        idempotency_key=key,
    )
    assert created1 is True
    assert w1.balance == Decimal("150000.00")

    w2, tx2, created2 = staff_topup_wallet(
        customer_id=cust.id,
        amount=Decimal("150000.00"),
        actor_id=staff_acc.id,
        idempotency_key=key,
    )
    assert created2 is False
    assert tx2.id == tx1.id
    assert w2.balance == Decimal("150000.00")

    logs = ActivityLog.objects.filter(
        action="WALLET_STAFF_TOPUP",
        entity_type="wallet",
        entity_id=wallet.id,
    )
    assert logs.count() == 1


@pytest.mark.django_db
def test_reconcile_wallets_command_passes():
    call_command("reconcile_wallets", "--fail-on-mismatch")


@pytest.mark.django_db
def test_create_customer_automatically_provisions_wallet():
    suffix = uuid.uuid4().hex[:6]
    cust = create_customer(
        {
            "full_name": "Auto Wallet Customer",
            "identity_card_number": f"079{uuid.uuid4().int % 10**9:09d}",
            "phone": f"09{uuid.uuid4().int % 10**8:08d}",
            "email": f"autow_{suffix}@example.com",
        }
    )
    wallet = Wallet.objects.filter(customer_id=cust.id, deleted_at__isnull=True).first()
    assert wallet is not None
    assert wallet.balance == Decimal("0.00")
    assert wallet.status == "ACTIVE"
    # Ensure Account import wasn't unused
    assert Account.objects.exists()


@pytest.mark.django_db(transaction=True)
def test_cross_wallet_concurrent_idempotency_key_raises_409_conflict():
    """
    Concurrency test: two distinct wallets concurrently using the same idempotency_key
    must not leak raw IntegrityError; one succeeds and the other raises 409 PROP-WALLET-IDEMPOTENCY-CONFLICT
    with its balance rolled back cleanly.
    """
    s1 = uuid.uuid4().hex[:6]
    s2 = uuid.uuid4().hex[:6]
    cust_a = create_customer(
        {
            "full_name": "Cross Collision A",
            "identity_card_number": f"079{uuid.uuid4().int % 10**9:09d}",
            "phone": f"09{uuid.uuid4().int % 10**8:08d}",
            "email": f"cca_{s1}@example.com",
        }
    )
    cust_b = create_customer(
        {
            "full_name": "Cross Collision B",
            "identity_card_number": f"079{uuid.uuid4().int % 10**9:09d}",
            "phone": f"08{uuid.uuid4().int % 10**8:08d}",
            "email": f"ccb_{s2}@example.com",
        }
    )
    wallet_a = ensure_wallet_for_customer(cust_a.id)
    wallet_b = ensure_wallet_for_customer(cust_b.id)

    credit_wallet(
        wallet_id=wallet_a.id,
        amount=Decimal("100000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"init-a-{s1}",
    )
    credit_wallet(
        wallet_id=wallet_b.id,
        amount=Decimal("100000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"init-b-{s2}",
    )

    # Test concurrent credit collision
    shared_credit_key = f"shared-credit-{uuid.uuid4().hex}"
    barrier_c = threading.Barrier(2)
    credit_outcomes: list[tuple[str, object]] = []
    lock = threading.Lock()

    def credit_worker(w_id: int) -> None:
        connection.close()
        try:
            barrier_c.wait(timeout=5)
            tx = credit_wallet(
                wallet_id=w_id,
                amount=Decimal("50000.00"),
                kind="TOPUP_VIETQR",
                idempotency_key=shared_credit_key,
            )
            with lock:
                credit_outcomes.append(("OK", tx.wallet_id))
        except BusinessAPIException as exc:
            with lock:
                credit_outcomes.append(("CONFLICT", (exc.status_code, exc.code)))
        finally:
            connection.close()

    t1 = threading.Thread(target=credit_worker, args=(wallet_a.id,))
    t2 = threading.Thread(target=credit_worker, args=(wallet_b.id,))
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert sorted(o[0] for o in credit_outcomes) == ["CONFLICT", "OK"]
    conflict_payload = [o[1] for o in credit_outcomes if o[0] == "CONFLICT"][0]
    assert conflict_payload == (409, "PROP-WALLET-IDEMPOTENCY-CONFLICT")
    winner_wallet_id = [o[1] for o in credit_outcomes if o[0] == "OK"][0]

    wallet_a.refresh_from_db()
    wallet_b.refresh_from_db()
    if winner_wallet_id == wallet_a.id:
        assert wallet_a.balance == Decimal("150000.00")
        assert wallet_b.balance == Decimal("100000.00")
    else:
        assert wallet_b.balance == Decimal("150000.00")
        assert wallet_a.balance == Decimal("100000.00")

    # Test concurrent debit collision
    shared_debit_key = f"shared-debit-{uuid.uuid4().hex}"
    barrier_d = threading.Barrier(2)
    debit_outcomes: list[tuple[str, object]] = []

    def debit_worker(w_id: int) -> None:
        connection.close()
        try:
            barrier_d.wait(timeout=5)
            tx = debit_wallet(
                wallet_id=w_id,
                amount=Decimal("30000.00"),
                kind="PARKING_FEE",
                idempotency_key=shared_debit_key,
            )
            with lock:
                debit_outcomes.append(("OK", tx.wallet_id))
        except BusinessAPIException as exc:
            with lock:
                debit_outcomes.append(("CONFLICT", (exc.status_code, exc.code)))
        finally:
            connection.close()

    d1 = threading.Thread(target=debit_worker, args=(wallet_a.id,))
    d2 = threading.Thread(target=debit_worker, args=(wallet_b.id,))
    d1.start()
    d2.start()
    d1.join(timeout=10)
    d2.join(timeout=10)

    assert sorted(o[0] for o in debit_outcomes) == ["CONFLICT", "OK"]
    debit_conflict = [o[1] for o in debit_outcomes if o[0] == "CONFLICT"][0]
    assert debit_conflict == (409, "PROP-WALLET-IDEMPOTENCY-CONFLICT")


@pytest.mark.django_db
def test_credit_wallet_topup_vnpay_kind_and_display(wallet_customer_pair):
    from apps.wallet.serializers.wallet import WalletTransactionSerializer

    _, _, wallet = wallet_customer_pair
    tx = credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("150000.00"),
        kind="TOPUP_VNPAY",
        idempotency_key=f"vnpay-svc-{uuid.uuid4().hex}",
        note="Nạp tiền ví qua VNPAY",
        reference_type="VNPAY_TXN",
    )
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("150000.00")
    assert tx.kind == "TOPUP_VNPAY"
    assert tx.get_kind_display() == "Nạp tiền qua VNPAY"
    serialized = WalletTransactionSerializer(tx).data
    assert serialized["kind"] == "TOPUP_VNPAY"
    assert serialized["kind_display"] == "Nạp tiền qua VNPAY"
    call_command("reconcile_wallets", fail_on_mismatch=True)
