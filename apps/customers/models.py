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
