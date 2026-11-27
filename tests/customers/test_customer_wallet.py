"""
Test suite for Customer Wallet (Ví điện tử khách hàng & An toàn tài chính).
Covers strictly 4 test cases per user requirement:
1. Test nạp tiền: Nạp 500.000đ cho khách hàng KH0020
2. Test trừ tiền thành công: Trừ 20.000đ cho cước xe
3. Test chặn rút quá số dư: Trừ 999.999.999đ (Báo lỗi không đủ số dư)
4. balance: Kiểu NUMERIC(12, 2) có ràng buộc CHECK (balance >= 0) — ngăn chặn tuyệt đối việc số dư bị âm
"""

from __future__ import annotations

from decimal import Decimal
import pytest
from django.db import IntegrityError, connection

from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer, CustomerWallet
from apps.customers.services.wallet import (
    deduct_from_wallet,
    deposit_to_wallet,
    get_or_create_customer_wallet,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def target_customer() -> Customer:
    """Fixture lấy khách hàng KH0020 (hoặc tạo mẫu nếu chưa tồn tại)."""
    cust = Customer.objects.filter(code="KH0020", deleted_at__isnull=True).first()
    if not cust:
        cust = Customer.objects.filter(deleted_at__isnull=True).first()
    if not cust:
        cust = Customer.objects.create(
            code="KH0020",
            full_name="Sơn Thị Bích Hợp",
            identity_card_number="079099001234",
            phone="0901234567",
            status="ACTIVE",
        )
    return cust


def test_deposit_500k_success(target_customer: Customer):
    """Test nạp tiền: Nạp 500.000đ cho khách hàng KH0020."""
    initial_wallet = get_or_create_customer_wallet(target_customer)
    initial_balance = initial_wallet.balance

    deposit_amount = Decimal("500000.00")
    result = deposit_to_wallet(
        customer_id=target_customer.id,
        amount=deposit_amount,
        description="Nạp 500.000đ cho khách hàng KH0020",
    )

    assert result["balance"] == initial_balance + deposit_amount
    assert result["customer_id"] == target_customer.id

    # Đối soát trực tiếp từ database
    refreshed_wallet = CustomerWallet.objects.get(id=initial_wallet.id)
    assert refreshed_wallet.balance == initial_balance + deposit_amount


def test_deduct_20k_success(target_customer: Customer):
    """Test trừ tiền thành công: Trừ 20.000đ cho cước xe."""
    wallet = get_or_create_customer_wallet(target_customer)
    # Đảm bảo số dư có đủ để trừ 20.000đ
    if wallet.balance < Decimal("20000.00"):
        deposit_to_wallet(target_customer.id, Decimal("50000.00"))
        wallet.refresh_from_db()
    balance_before = wallet.balance
    deduct_amount = Decimal("20000.00")
    result = deduct_from_wallet(
        customer_id=target_customer.id,
        amount=deduct_amount,
        description="Trừ 20.000đ cho cước xe",
    )
    assert result["balance"] == balance_before - deduct_amount
    assert result["amount"] == deduct_amount
    # Đối soát trực tiếp từ database
    wallet.refresh_from_db()
    assert wallet.balance == balance_before - deduct_amount


def test_reject_overdraft_insufficient_funds(target_customer: Customer):
    """Test chặn rút quá số dư: Trừ 999.999.999đ."""
    wallet = get_or_create_customer_wallet(target_customer)
    overdraft_amount = Decimal("999999999.00")
    with pytest.raises(BusinessAPIException) as exc_info:
        deduct_from_wallet(
            customer_id=target_customer.id,
            amount=overdraft_amount,
            description="Cố tình rút vượt quá số dư ví",
        )
    assert exc_info.value.code == "PROP-WALLET-INSUFFICIENT-FUNDS"
    assert "Số dư ví không đủ" in exc_info.value.message


def test_database_check_constraint_balance_nonnegative(target_customer: Customer):
    """balance: Kiểu NUMERIC(12, 2) có ràng buộc CHECK (balance >= 0) — ngăn chặn tuyệt đối việc số dư bị âm."""
    wallet = get_or_create_customer_wallet(target_customer)
    # Cố tình thực thi câu lệnh SQL UPDATE ép số dư âm nhằm kiểm tra DB CHECK CONSTRAINT
    with pytest.raises(IntegrityError):
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE customer_wallet SET balance = -1000.00 WHERE id = %s",
                [wallet.id],
            )
