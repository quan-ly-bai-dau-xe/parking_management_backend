from django.db import models

from apps.core.models import SoftDeleteModel


class Customer(SoftDeleteModel):
    """
    Hồ sơ khách hàng (có xóa mềm).
    Tuân thủ bảo vệ dữ liệu cá nhân (Nghị định 13/2023/NĐ-CP).
    """

    STATUS_CHOICES = [
        ("ACTIVE", "Hoạt động"),
        ("SUSPENDED", "Tạm ngưng"),
        ("BLACKLISTED", "Danh sách đen"),
    ]

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=10, unique=True)
    full_name = models.CharField(max_length=45)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    identity_card_number = models.CharField(max_length=20)
    phone = models.CharField(max_length=15)
    email = models.CharField(max_length=100, null=True, blank=True)
    address = models.CharField(max_length=100, null=True, blank=True)
    province = models.ForeignKey(
        "core.AdministrativeProvince",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="province_id",
        null=True,
        blank=True,
        related_name="customers",
    )
    district = models.ForeignKey(
        "core.AdministrativeDistrict",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="district_id",
        null=True,
        blank=True,
        related_name="customers",
    )
    ward = models.ForeignKey(
        "core.AdministrativeWard",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="ward_id",
        null=True,
        blank=True,
        related_name="customers",
    )
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="account_id",
        null=True,
        blank=True,
        related_name="customer_profile",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    status_reason = models.TextField(null=True, blank=True)
    is_anonymized = models.BooleanField(default=False)
    anonymized_at = models.DateTimeField(null=True, blank=True)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "customer"

    def __str__(self):
        return f"{self.full_name} ({self.code})"


class CustomerWallet(models.Model):
    """
    Ví điện tử nội bộ cho khách hàng.
    Quản lý số dư thanh toán không tiền mặt và kiểm soát giao dịch an toàn.
    """

    id = models.BigAutoField(primary_key=True)
    customer = models.OneToOneField(
        Customer,
        on_delete=models.CASCADE,
        related_name="wallet",
        db_column="customer_id",
    )
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    status = models.CharField(max_length=20, default="ACTIVE")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        managed = False
        db_table = "customer_wallet"

    def __str__(self):
        return f"Wallet of {self.customer.full_name}: {self.balance}đ"


class CustomerWalletTransaction(models.Model):
    """
    Lịch sử biến động số dư ví (Nạp tiền, Trừ cước đỗ xe, Hoàn tiền).
    """

    TRANSACTION_TYPES = [
        ("DEPOSIT", "Nạp tiền"),
        ("DEDUCT", "Trừ cước đỗ xe"),
        ("REFUND", "Hoàn tiền"),
    ]

    id = models.BigAutoField(primary_key=True)
    wallet = models.ForeignKey(
        CustomerWallet,
        on_delete=models.CASCADE,
        related_name="transactions",
        db_column="wallet_id",
    )
    transaction_type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    balance_before = models.DecimalField(max_digits=12, decimal_places=2)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    session = models.ForeignKey(
        "parking.VehicleEntryExitLog",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="session_id",
    )
    reference_code = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        managed = False
        db_table = "customer_wallet_transaction"

    def __str__(self):
        return f"Tx {self.id} ({self.transaction_type}): {self.amount}đ"

