from decimal import Decimal

from django.core.exceptions import PermissionDenied
from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteModel


class Wallet(SoftDeleteModel):
    """
    Ví điện tử trả trước của khách hàng (1:1 với customer đang hoạt động, ADR-0012).
    """

    STATUS_CHOICES = [
        ("ACTIVE", "Đang hoạt động"),
        ("LOCKED", "Tạm khóa"),
        ("CLOSED", "Đã đóng"),
    ]

    id = models.BigAutoField(primary_key=True)
    customer = models.OneToOneField(
        "customers.Customer",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="customer_id",
        related_name="wallet",
    )
    balance = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    currency = models.CharField(max_length=3, default="VND")
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE",
    )
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "wallet"

    def __str__(self) -> str:
        return f"Wallet #{self.id} (Customer {self.customer_id}: {self.balance} {self.currency})"


class WalletTransaction(models.Model):
    """
    Sổ cái giao dịch ví bất biến (chỉ thêm mới / append-only, ADR-0012).
    Mọi thao tác UPDATE/DELETE bị chặn ở cả tầng ORM lẫn PostgreSQL trigger.
    """

    TRANSACTION_TYPE_CHOICES = [
        ("CREDIT", "Ghi có"),
        ("DEBIT", "Ghi nợ"),
    ]

    KIND_CHOICES = [
        ("TOPUP_CASH", "Nạp tiền mặt tại quầy"),
        ("TOPUP_VIETQR", "Nạp tiền qua VietQR"),
        ("TOPUP_VNPAY", "Nạp tiền qua VNPAY"),
        ("TICKET_PURCHASE", "Mua vé đỗ xe"),
        ("TICKET_RENEWAL", "Gia hạn vé đỗ xe"),
        ("PARKING_FEE", "Thanh toán phí gửi xe"),
        ("REFUND", "Hoàn tiền"),
        ("ADJUSTMENT", "Điều chỉnh số dư"),
    ]

    id = models.BigAutoField(primary_key=True)
    wallet = models.ForeignKey(
        Wallet,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="wallet_id",
        related_name="transactions",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    transaction_type = models.CharField(
        max_length=10,
        choices=TRANSACTION_TYPE_CHOICES,
    )
    kind = models.CharField(max_length=30, choices=KIND_CHOICES)
    idempotency_key = models.CharField(max_length=100, unique=True)
    reference_type = models.CharField(max_length=50, null=True, blank=True)
    reference_id = models.BigIntegerField(null=True, blank=True)
    note = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        "accounts.Account",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="created_by_id",
        null=True,
        blank=True,
        related_name="wallet_transactions_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        managed = False
        db_table = "wallet_transaction"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise PermissionDenied(
                "Sổ cái giao dịch ví là bảng chỉ ghi (append-only), không cho phép cập nhật."
            )
        return super().save(*args, **kwargs)

    def delete(self, using=None, keep_parents=False):
        raise PermissionDenied(
            "Sổ cái giao dịch ví là bảng chỉ ghi (append-only), không cho phép xóa."
        )

    def __str__(self) -> str:
        return f"WalletTx #{self.id} [{self.kind}] {self.amount} (after={self.balance_after})"
