import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import IntegrityError, connection, transaction
from rest_framework import status

from apps.audit.models import ActivityLog
from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_message
from apps.customers.models import Customer
from apps.wallet.models import Wallet, WalletTransaction

CREDIT_KINDS = {"TOPUP_CASH", "TOPUP_VIETQR", "TOPUP_VNPAY", "REFUND", "ADJUSTMENT"}
DEBIT_KINDS = {"TICKET_PURCHASE", "TICKET_RENEWAL", "PARKING_FEE", "ADJUSTMENT"}

MIN_SIMULATED_TOPUP_VND = Decimal("10000.00")
MAX_SIMULATED_TOPUP_VND = Decimal("50000000.00")


class InsufficientWalletBalanceError(BusinessAPIException):
    """Raised when attempting to debit more than the current wallet balance."""

    def __init__(
        self,
        required_amount: Decimal,
        current_balance: Decimal,
        message: str | None = None,
    ) -> None:
        missing = (required_amount - current_balance).quantize(Decimal("0.01"))
        super().__init__(
            code="PROP-WALLET-INSUFFICIENT",
            message=message or get_message("PROP-WALLET-INSUFFICIENT"),
            status_code=status.HTTP_409_CONFLICT,
            details={
                "required_amount": f"{required_amount:.2f}",
                "current_balance": f"{current_balance:.2f}",
                "missing_amount": f"{missing:.2f}",
            },
        )


def _validate_positive_decimal(raw_amount: object) -> Decimal:
    """Validate and quantize monetary input to positive Decimal(0.01)."""
    if isinstance(raw_amount, bool) or raw_amount is None:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Số tiền giao dịch không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    try:
        dec = Decimal(str(raw_amount))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Số tiền giao dịch không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if not dec.is_finite() or dec <= Decimal("0.00"):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Số tiền giao dịch phải lớn hơn 0.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    quantized = dec.quantize(Decimal("0.01"))
    if quantized <= Decimal("0.00"):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Số tiền giao dịch phải lớn hơn 0.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return quantized


def _validate_idempotency_key(idempotency_key: object) -> str:
    """Validate non-empty idempotency key within VARCHAR(100) limit."""
    if not isinstance(idempotency_key, str):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Khóa chống trùng lặp (idempotency_key) không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    clean_key = idempotency_key.strip()
    if not clean_key or len(clean_key) > 100:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Khóa chống trùng lặp (idempotency_key) phải từ 1 đến 100 ký tự.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return clean_key


def ensure_wallet_for_customer(customer_id: int) -> Wallet:
    """
    Idempotently retrieve or create the active wallet for a customer inside a transaction.
    Uses a transaction-scoped PostgreSQL advisory lock to prevent concurrent duplicate inserts.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s));",
                [f"wallet_ensure_{customer_id}"],
            )
        wallet = Wallet.objects.filter(
            customer_id=customer_id,
            deleted_at__isnull=True,
        ).first()
        if wallet is not None:
            return wallet

        customer_exists = Customer.objects.filter(
            id=customer_id,
            deleted_at__isnull=True,
        ).exists()
        if not customer_exists:
            raise BusinessAPIException(
                code="PROP-4.4.4-P02",
                message=get_message("PROP-4.4.4-P02"),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        return Wallet.objects.create(
            customer_id=customer_id,
            balance=Decimal("0.00"),
            currency="VND",
            status="ACTIVE",
        )


def credit_wallet(
    wallet_id: int,
    amount: Decimal | int | str,
    kind: str,
    idempotency_key: str,
    note: str | None = None,
    reference_id: int | None = None,
    actor_id: int | None = None,
    reference_type: str | None = None,
) -> WalletTransaction:
    """
    Atomically credit a wallet under row-level lock (select_for_update) with idempotency.
    """
    clean_amount = _validate_positive_decimal(amount)
    clean_key = _validate_idempotency_key(idempotency_key)
    clean_kind = str(kind).strip().upper()
    if clean_kind not in CREDIT_KINDS:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message=f"Loại giao dịch ghi có '{clean_kind}' không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    clean_ref_type = (
        reference_type.strip().upper()
        if reference_type and str(reference_type).strip()
        else None
    )

    with transaction.atomic():
        wallet = (
            Wallet.objects.select_for_update()
            .filter(id=wallet_id, deleted_at__isnull=True)
            .first()
        )
        if not wallet:
            raise BusinessAPIException(
                code="PROP-WALLET-NOT-FOUND",
                message=get_message("PROP-WALLET-NOT-FOUND"),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if wallet.status != "ACTIVE":
            raise BusinessAPIException(
                code="PROP-WALLET-LOCKED",
                message=get_message("PROP-WALLET-LOCKED"),
                status_code=status.HTTP_409_CONFLICT,
            )

        existing = WalletTransaction.objects.filter(idempotency_key=clean_key).first()
        if existing is not None:
            if (
                existing.wallet_id != wallet.id
                or existing.transaction_type != "CREDIT"
                or existing.kind != clean_kind
                or existing.amount != clean_amount
            ):
                raise BusinessAPIException(
                    code="PROP-WALLET-IDEMPOTENCY-CONFLICT",
                    message=get_message("PROP-WALLET-IDEMPOTENCY-CONFLICT"),
                    status_code=status.HTTP_409_CONFLICT,
                )
            return existing

        # Wrap balance update + ledger insert in a savepoint so a global idempotency_key
        # race across two different wallets rolls back cleanly and translates to HTTP 409.
        try:
            with transaction.atomic():
                new_balance = (wallet.balance + clean_amount).quantize(Decimal("0.01"))
                wallet.balance = new_balance
                wallet.save(update_fields=["balance"])

                return WalletTransaction.objects.create(
                    wallet=wallet,
                    amount=clean_amount,
                    balance_after=new_balance,
                    transaction_type="CREDIT",
                    kind=clean_kind,
                    idempotency_key=clean_key,
                    reference_type=clean_ref_type,
                    reference_id=reference_id,
                    note=note.strip()
                    if isinstance(note, str) and note.strip()
                    else None,
                    created_by_id=actor_id,
                )
        except IntegrityError as exc:
            err_msg = str(exc)
            if (
                "uq_wallet_tx_idempotency_key" not in err_msg
                and "idempotency_key" not in err_msg
            ):
                raise
            existing_after = WalletTransaction.objects.filter(
                idempotency_key=clean_key
            ).first()
            if (
                existing_after is not None
                and existing_after.wallet_id == wallet.id
                and existing_after.transaction_type == "CREDIT"
                and existing_after.kind == clean_kind
                and existing_after.amount == clean_amount
            ):
                return existing_after
            raise BusinessAPIException(
                code="PROP-WALLET-IDEMPOTENCY-CONFLICT",
                message=get_message("PROP-WALLET-IDEMPOTENCY-CONFLICT"),
                status_code=status.HTTP_409_CONFLICT,
            ) from exc


def debit_wallet(
    wallet_id: int,
    amount: Decimal | int | str,
    kind: str,
    idempotency_key: str,
    note: str | None = None,
    reference_id: int | None = None,
    actor_id: int | None = None,
    reference_type: str | None = None,
) -> WalletTransaction:
    """
    Atomically debit a wallet under row-level lock (select_for_update) with idempotency.
    Checks idempotency BEFORE balance check so retries never cause false insufficient errors.
    """
    clean_amount = _validate_positive_decimal(amount)
    clean_key = _validate_idempotency_key(idempotency_key)
    clean_kind = str(kind).strip().upper()
    if clean_kind not in DEBIT_KINDS:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message=f"Loại giao dịch ghi nợ '{clean_kind}' không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    clean_ref_type = (
        reference_type.strip().upper()
        if reference_type and str(reference_type).strip()
        else None
    )

    with transaction.atomic():
        wallet = (
            Wallet.objects.select_for_update()
            .filter(id=wallet_id, deleted_at__isnull=True)
            .first()
        )
        if not wallet:
            raise BusinessAPIException(
                code="PROP-WALLET-NOT-FOUND",
                message=get_message("PROP-WALLET-NOT-FOUND"),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if wallet.status != "ACTIVE":
            raise BusinessAPIException(
                code="PROP-WALLET-LOCKED",
                message=get_message("PROP-WALLET-LOCKED"),
                status_code=status.HTTP_409_CONFLICT,
            )

        existing = WalletTransaction.objects.filter(idempotency_key=clean_key).first()
        if existing is not None:
            if (
                existing.wallet_id != wallet.id
                or existing.transaction_type != "DEBIT"
                or existing.kind != clean_kind
                or existing.amount != -clean_amount
            ):
                raise BusinessAPIException(
                    code="PROP-WALLET-IDEMPOTENCY-CONFLICT",
                    message=get_message("PROP-WALLET-IDEMPOTENCY-CONFLICT"),
                    status_code=status.HTTP_409_CONFLICT,
                )
            return existing

        if wallet.balance < clean_amount:
            raise InsufficientWalletBalanceError(
                required_amount=clean_amount,
                current_balance=wallet.balance,
            )

        # Wrap balance update + ledger insert in a savepoint so a global idempotency_key
        # race across two different wallets rolls back cleanly and translates to HTTP 409.
        try:
            with transaction.atomic():
                new_balance = (wallet.balance - clean_amount).quantize(Decimal("0.01"))
                wallet.balance = new_balance
                wallet.save(update_fields=["balance"])

                return WalletTransaction.objects.create(
                    wallet=wallet,
                    amount=-clean_amount,
                    balance_after=new_balance,
                    transaction_type="DEBIT",
                    kind=clean_kind,
                    idempotency_key=clean_key,
                    reference_type=clean_ref_type,
                    reference_id=reference_id,
                    note=note.strip()
                    if isinstance(note, str) and note.strip()
                    else None,
                    created_by_id=actor_id,
                )
        except IntegrityError as exc:
            err_msg = str(exc)
            if (
                "uq_wallet_tx_idempotency_key" not in err_msg
                and "idempotency_key" not in err_msg
            ):
                raise
            existing_after = WalletTransaction.objects.filter(
                idempotency_key=clean_key
            ).first()
            if (
                existing_after is not None
                and existing_after.wallet_id == wallet.id
                and existing_after.transaction_type == "DEBIT"
                and existing_after.kind == clean_kind
                and existing_after.amount == -clean_amount
            ):
                return existing_after
            raise BusinessAPIException(
                code="PROP-WALLET-IDEMPOTENCY-CONFLICT",
                message=get_message("PROP-WALLET-IDEMPOTENCY-CONFLICT"),
                status_code=status.HTTP_409_CONFLICT,
            ) from exc


def staff_topup_wallet(
    customer_id: int,
    amount: Decimal | int | str,
    note: str | None = None,
    actor_id: int | None = None,
    idempotency_key: str | None = None,
    payment_method: str = "CASH",
) -> tuple[Wallet, WalletTransaction, bool]:
    """
    Staff-assisted counter cash top-up into a customer's wallet.
    Records an audit ActivityLog entry once per non-replayed top-up (no PII logged).
    """
    if str(payment_method).strip().upper() != "CASH":
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Nạp tiền tại quầy chỉ hỗ trợ phương thức tiền mặt (CASH).",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    clean_amount = _validate_positive_decimal(amount)
    clean_key = (
        _validate_idempotency_key(idempotency_key)
        if idempotency_key is not None
        else f"staff-topup-{customer_id}-{uuid.uuid4().hex}"
    )

    with transaction.atomic():
        customer = Customer.objects.filter(
            id=customer_id,
            deleted_at__isnull=True,
        ).first()
        if not customer:
            raise BusinessAPIException(
                code="PROP-4.4.4-P02",
                message=get_message("PROP-4.4.4-P02"),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        wallet = ensure_wallet_for_customer(customer.id)
        already_exists = WalletTransaction.objects.filter(
            idempotency_key=clean_key
        ).exists()

        tx = credit_wallet(
            wallet_id=wallet.id,
            amount=clean_amount,
            kind="TOPUP_CASH",
            idempotency_key=clean_key,
            note=note or f"Nạp tiền mặt tại quầy cho khách hàng {customer.code}.",
            reference_type="CUSTOMER",
            reference_id=customer.id,
            actor_id=actor_id,
        )

        created = not already_exists
        if created:
            ActivityLog.objects.create(
                actor_account_id=actor_id,
                action="WALLET_STAFF_TOPUP",
                entity_type="wallet",
                entity_id=wallet.id,
                message=(
                    f"Nhân viên nạp {clean_amount:,.0f} VND (CASH) vào ví khách hàng {customer.code}."
                ),
            )

        wallet.refresh_from_db()
        return wallet, tx, created


def simulated_vietqr_topup(
    customer_id: int,
    amount: Decimal | int | str,
    idempotency_key: str,
    actor_id: int | None = None,
    note: str | None = None,
) -> tuple[Wallet, WalletTransaction, bool]:
    """
    Simulated customer self-top-up via VietQR placeholder gated by WALLET_SIMULATED_TOPUP_ENABLED.
    """
    if not getattr(settings, "WALLET_SIMULATED_TOPUP_ENABLED", False):
        raise BusinessAPIException(
            code="PROP-WALLET-SIMULATED-DISABLED",
            message=get_message("PROP-WALLET-SIMULATED-DISABLED"),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    clean_amount = _validate_positive_decimal(amount)
    if clean_amount < MIN_SIMULATED_TOPUP_VND or clean_amount > MAX_SIMULATED_TOPUP_VND:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message=(
                f"Số tiền nạp qua VietQR giả lập phải từ "
                f"{MIN_SIMULATED_TOPUP_VND:,.0f}đ đến {MAX_SIMULATED_TOPUP_VND:,.0f}đ."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    clean_key = _validate_idempotency_key(idempotency_key)

    with transaction.atomic():
        wallet = ensure_wallet_for_customer(customer_id)
        already_exists = WalletTransaction.objects.filter(
            idempotency_key=clean_key
        ).exists()

        tx = credit_wallet(
            wallet_id=wallet.id,
            amount=clean_amount,
            kind="TOPUP_VIETQR",
            idempotency_key=clean_key,
            note=note or "Nạp tiền ví qua VietQR giả lập",
            reference_type="CUSTOMER",
            reference_id=customer_id,
            actor_id=actor_id,
        )
        wallet.refresh_from_db()
        return wallet, tx, (not already_exists)
