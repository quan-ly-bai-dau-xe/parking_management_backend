from django.core.validators import RegexValidator
from django.db import models

from apps.accounts.models import Account


class Position(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Business natural position code: BV (Bảo vệ), GX (Giữ xe), QL (Quản lý) (REQ-4.3.1-F04, REQ-4.3.2-F04)",
    )
    name = models.CharField(
        max_length=45,
        help_text="Display name of position (String max 45 chars per SRS) (REQ-4.3.1-F04, REQ-4.3.2-F04, REQ-4.3.3-F04)",
    )
    description = models.TextField(
        null=True,
        blank=True,
        help_text="Detailed description of responsibilities and scope (REQ-4.3.1-F04)",
    )
    row_version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="deleted_positions",
    )

    class Meta:
        db_table = "position"
        verbose_name = "Chức vụ"
        verbose_name_plural = "Chức vụ"
        indexes = [
            models.Index(
                fields=["code"],
                name="uq_position_code_active",
                condition=models.Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["name"],
                name="uq_position_name_active",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self):
        return self.name


class Employee(models.Model):
    GENDER_CHOICES = [
        ("Nam", "Nam"),
        ("Nữ", "Nữ"),
    ]

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(
        max_length=10,
        unique=True,
        validators=[RegexValidator(r"^[A-Za-z0-9-]+$")],
        help_text="Natural employee code (NV-1234 or 5-char alphanumeric), immutable upon edit (REQ-4.3.1-F01, REQ-4.3.2-F06, REQ-4.3.3-F06)",
    )
    account = models.OneToOneField(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employee_profile",
        help_text="Foreign key referencing user account credentials (REQ-4.1-F01, ADR-0004, OQ-56)",
    )
    position = models.ForeignKey(
        Position,
        on_delete=models.PROTECT,
        related_name="employees",
        help_text="Foreign key referencing employee job position (REQ-4.3.1-F04, REQ-4.3.2-F04, REQ-4.3.3-F04)",
    )
    full_name = models.CharField(
        max_length=45,
        help_text="Full name of employee (max 45 characters per SRS) (REQ-4.3.1-F02, REQ-4.3.2-F01, REQ-4.3.3-F01)",
    )
    date_of_birth = models.DateField()
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        help_text="Employee gender (Nam, Nữ per SRS 4.3.2) (REQ-4.3.1-F05, REQ-4.3.2-F07, REQ-4.3.3-F08)",
    )
    phone = models.CharField(
        max_length=15,
        validators=[RegexValidator(r"^[0-9]+$")],
        help_text="Employee contact phone number (max 15 digits) (REQ-4.3.2-F08, Rule 05, OQ-65)",
    )
    email = models.EmailField(
        max_length=45,
        help_text="Employee contact email address (REQ-4.3.1-F07, REQ-4.3.2-F05, REQ-4.3.3-F05)",
    )
    address = models.CharField(
        max_length=45,
        help_text="Detailed address string (max 45 characters per SRS) (REQ-4.3.1-F06, REQ-4.3.2-F03, REQ-4.3.3-F03, Rule 05)",
    )
    province = models.ForeignKey(
        "customers.AdministrativeProvince",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employees",
    )
    district = models.ForeignKey(
        "customers.AdministrativeDistrict",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employees",
    )
    ward = models.ForeignKey(
        "customers.AdministrativeWard",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="employees",
    )
    row_version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="deleted_employees",
    )

    class Meta:
        db_table = "employee"
        verbose_name = "Nhân viên"
        verbose_name_plural = "Nhân viên"
        indexes = [
            models.Index(
                fields=["code"],
                name="uq_employee_code_active",
                condition=models.Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["account"],
                name="uq_employee_account_active",
                condition=models.Q(deleted_at__isnull=True)
                & models.Q(account__isnull=False),
            ),
            models.Index(
                fields=["phone"],
                name="uq_employee_phone_active",
                condition=models.Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["email"],
                name="uq_employee_email_active",
                condition=models.Q(deleted_at__isnull=True),
            ),
            models.Index(fields=["position"], name="idx_employee_position"),
            models.Index(fields=["full_name"], name="idx_employee_full_name"),
        ]

    def __str__(self):
        return self.full_name

    def clean(self):
        # Validate phone contains only digits
        if self.phone and not self.phone.isdigit():
            from django.core.exceptions import ValidationError

            raise ValidationError({"phone": "Số điện thoại chỉ chứa các chữ số"})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
