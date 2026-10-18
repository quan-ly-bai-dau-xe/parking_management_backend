from django.db import models

from apps.core.models import SoftDeleteModel


class Position(SoftDeleteModel):
    """
    Chức vụ nhân viên (bảng danh mục có xóa mềm).
    """

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=255, null=True, blank=True)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "position"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Employee(SoftDeleteModel):
    """
    Hồ sơ nhân viên (có xóa mềm).
    """

    STATUS_CHOICES = [
        ("ACTIVE", "Đang làm việc"),
        ("ON_LEAVE", "Nghỉ phép"),
        ("TERMINATED", "Đã nghỉ việc"),
    ]

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=10, unique=True)
    full_name = models.CharField(max_length=45)
    date_of_birth = models.DateField(null=True, blank=True)
    gender = models.CharField(max_length=10, null=True, blank=True)
    identity_card_number = models.CharField(max_length=20, null=True, blank=True)
    phone = models.CharField(max_length=15)
    email = models.CharField(max_length=100)
    address = models.CharField(max_length=100, null=True, blank=True)
    province = models.ForeignKey(
        "core.AdministrativeProvince",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="province_id",
        null=True,
        blank=True,
        related_name="employees",
    )
    district = models.ForeignKey(
        "core.AdministrativeDistrict",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="district_id",
        null=True,
        blank=True,
        related_name="employees",
    )
    ward = models.ForeignKey(
        "core.AdministrativeWard",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="ward_id",
        null=True,
        blank=True,
        related_name="employees",
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="position_id",
        related_name="employees",
    )
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="account_id",
        null=True,
        blank=True,
        related_name="employee_profile",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "employee"

    def __str__(self):
        return f"{self.full_name} ({self.code})"
