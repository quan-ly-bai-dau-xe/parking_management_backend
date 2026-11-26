from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer, CustomerWallet, CustomerWalletTransaction


def get_or_create_customer_wallet(customer: Customer) -> CustomerWallet:
    """Lấy ví hoặc tự động khởi tạo ví cho khách hàng nếu chưa tồn tại."""
    wallet, _ = CustomerWallet.objects.get_or_create(
        customer=customer,
        defaults={"balance": Decimal("0.00"), "status": "ACTIVE"},
    )
    return wallet


@transaction.atomic
def deposit_to_wallet(
    customer_id: int,
    amount: Decimal | float | int | str,
    description: str | None = None,
    reference_code: str | None = None,
) -> dict[str, Any]:
    """Nạp tiền vào ví khách hàng."""
    dec_amount = Decimal(str(amount))
    if dec_amount <= 0:
        raise BusinessAPIException(
            code="PROP-WALLET-AMOUNT-INVALID",
            message="Số tiền nạp vào ví phải lớn hơn 0.",
            status_code=400,
        )

    customer = (
        Customer.objects.select_for_update()
        .filter(id=customer_id, deleted_at__isnull=True)
        .first()
    )
    if not customer:
        raise BusinessAPIException(
            code="PROP-CUSTOMER-NOT-FOUND",
            message="Không tìm thấy khách hàng.",
            status_code=404,
        )

    wallet = get_or_create_customer_wallet(customer)
    balance_before = wallet.balance
    balance_after = balance_before + dec_amount

    wallet.balance = balance_after
    wallet.updated_at = timezone.now()
    wallet.save()

    tx = CustomerWalletTransaction.objects.create(
        wallet=wallet,
        transaction_type="DEPOSIT",
        amount=dec_amount,
        balance_before=balance_before,
        balance_after=balance_after,
        reference_code=reference_code,
        description=description or f"Nạp tiền vào ví Smart Parking ({dec_amount:,.0f}đ)",
    )

    return {
        "wallet_id": wallet.id,
        "customer_id": customer.id,
        "customer_name": customer.full_name,
        "balance": wallet.balance,
        "transaction_id": tx.id,
        "amount": tx.amount,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "message": f"Nạp thành công {dec_amount:,.0f}đ vào ví khách hàng {customer.full_name}.",
    }


@transaction.atomic
def deduct_from_wallet(
    customer_id: int,
    amount: Decimal | float | int | str,
    session_id: int | None = None,
    description: str | None = None,
    reference_code: str | None = None,
) -> dict[str, Any]:
    """Trừ tiền từ ví khách hàng khi thanh toán cước đỗ xe."""
    dec_amount = Decimal(str(amount))
    if dec_amount <= 0:
        raise BusinessAPIException(
            code="PROP-WALLET-AMOUNT-INVALID",
            message="Số tiền trừ ví phải lớn hơn 0.",
            status_code=400,
        )

    customer = (
        Customer.objects.select_for_update()
        .filter(id=customer_id, deleted_at__isnull=True)
        .first()
    )
    if not customer:
        raise BusinessAPIException(
            code="PROP-CUSTOMER-NOT-FOUND",
            message="Không tìm thấy khách hàng.",
            status_code=404,
        )

    wallet = get_or_create_customer_wallet(customer)
    balance_before = wallet.balance

    if balance_before < dec_amount:
        shortfall = dec_amount - balance_before
        raise BusinessAPIException(
            code="PROP-WALLET-INSUFFICIENT-FUNDS",
            message=(
                f"Số dư ví không đủ (Hiện có: {balance_before:,.0f}đ, "
                f"Cần thanh toán: {dec_amount:,.0f}đ, Thiếu: {shortfall:,.0f}đ)."
            ),
            status_code=400,
        )

    balance_after = balance_before - dec_amount
    wallet.balance = balance_after
    wallet.updated_at = timezone.now()
    wallet.save()

    tx = CustomerWalletTransaction.objects.create(
        wallet=wallet,
        transaction_type="DEDUCT",
        amount=dec_amount,
        balance_before=balance_before,
        balance_after=balance_after,
        session_id=session_id,
        reference_code=reference_code,
        description=description or f"Thanh toán cước đỗ xe qua ví ({dec_amount:,.0f}đ)",
    )

    return {
        "wallet_id": wallet.id,
        "customer_id": customer.id,
        "customer_name": customer.full_name,
        "balance": wallet.balance,
        "transaction_id": tx.id,
        "amount": tx.amount,
        "balance_before": balance_before,
        "balance_after": balance_after,
        "message": f"Đã trừ {dec_amount:,.0f}đ từ ví khách hàng {customer.full_name}.",
    }
