from django.core.validators import RegexValidator
from django.db import models

from apps.accounts.models import Account


class AdministrativeProvince(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'administrative_province'
        verbose_name = 'Tỉnh/Thành phố'
        verbose_name_plural = 'Tỉnh/Thành phố'
        indexes = [
            models.Index(fields=['code'], name='uq_admin_province_code'),
            models.Index(fields=['name'], name='idx_admin_province_name'),
        ]

    def __str__(self):
        return self.name


class AdministrativeDistrict(models.Model):
    id = models.BigAutoField(primary_key=True)
    province = models.ForeignKey(
        AdministrativeProvince,
        on_delete=models.PROTECT,
        related_name='districts'
    )
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'administrative_district'
        verbose_name = 'Quận/Huyện/Thị xã'
        verbose_name_plural = 'Quận/Huyện/Thị xã'
        indexes = [
            models.Index(fields=['code'], name='uq_admin_district_code'),
            models.Index(fields=['province'], name='idx_admin_district_province'),
        ]

    def __str__(self):
        return self.name


class AdministrativeWard(models.Model):
    id = models.BigAutoField(primary_key=True)
    district = models.ForeignKey(
        AdministrativeDistrict,
        on_delete=models.PROTECT,
        related_name='wards'
    )
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'administrative_ward'
        verbose_name = 'Phường/Xã'
        verbose_name_plural = 'Phường/Xã'
        indexes = [
            models.Index(fields=['code'], name='uq_admin_ward_code'),
            models.Index(fields=['district'], name='idx_admin_ward_district'),
        ]

    def __str__(self):
        return self.name


class Customer(models.Model):
    GENDER_CHOICES = [
        ('Nam', 'Nam'),
        ('Nữ', 'Nữ'),
    ]

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(
        max_length=10,
        unique=True,
        validators=[RegexValidator(r'^[A-Za-z0-9-]+$')],
        help_text='Natural customer code (KH-1234 or 5-char alphanumeric), immutable upon edit (REQ-4.4.1-F01, REQ-4.4.4-F01)'
    )
    account = models.OneToOneField(
        Account,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='customer_profile',
        help_text='Foreign key referencing portal account [PROPOSAL OQ-55] (SRS 3.1, ADR-0004)'
    )
    full_name = models.CharField(
        max_length=45,
        help_text='Full name of customer (max 45 characters per SRS) (REQ-4.4.1-F02, REQ-4.4.3-F01, REQ-4.4.4-F02)'
    )
    date_of_birth = models.DateField()
    gender = models.CharField(
        max_length=10,
        choices=GENDER_CHOICES,
        help_text='Customer gender (Nam, Nữ per SRS 4.4.1/4.4.3) (REQ-4.4.1-F07, REQ-4.4.3-F03, REQ-4.4.4-F02)'
    )
    identity_card_number = models.CharField(
        max_length=20,
        validators=[RegexValidator(r'^[0-9]+$')],
        help_text='National ID / Citizen card number, digits-only string up to 20 characters (REQ-4.4.1-F04, REQ-4.4.3-F07, REQ-4.4.4-F02, ck_customer_idcard_digits)'
    )
    phone = models.CharField(
        max_length=11,
        validators=[RegexValidator(r'^[0-9]+$')],
        help_text='Customer telephone number (max 11 digits per SRS) (REQ-4.4.1-F05, REQ-4.4.3-F06, REQ-4.4.4-F02, Rule 05)'
    )
    email = models.EmailField(
        max_length=45,
        help_text='Customer contact email address (REQ-4.4.1-F06, REQ-4.4.3-F05, REQ-4.4.4-F02)'
    )
    address = models.CharField(
        max_length=45,
        help_text='Detailed address string (max 45 characters per SRS) (REQ-4.4.1, REQ-4.4.3-F04, REQ-4.4.4-F02, Rule 05)'
    )
    province = models.ForeignKey(
        AdministrativeProvince,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='customers'
    )
    district = models.ForeignKey(
        AdministrativeDistrict,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='customers'
    )
    ward = models.ForeignKey(
        AdministrativeWard,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='customers'
    )
    is_anonymized = models.BooleanField(
        default=False,
        help_text='Flag marking PII anonymization under Decree 13/2023/ND-CP (OQ-12, ADR-0003)'
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
        related_name='deleted_customers'
    )

    class Meta:
        db_table = 'customer'
        verbose_name = 'Khách hàng'
        verbose_name_plural = 'Khách hàng'
        indexes = [
            models.Index(fields=['code'], name='uq_customer_code_active', condition=models.Q(deleted_at__isnull=True)),
            models.Index(fields=['identity_card_number'], name='uq_customer_idcard_active', condition=models.Q(deleted_at__isnull=True)),
            models.Index(fields=['phone'], name='uq_customer_phone_active', condition=models.Q(deleted_at__isnull=True)),
            models.Index(fields=['full_name'], name='idx_customer_full_name'),
        ]

    def __str__(self):
        return self.full_name

    def clean(self):
        # Validate phone contains only digits and max 11 characters
        if self.phone and (not self.phone.isdigit() or len(self.phone) > 11):
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'phone': 'Số điện thoại chỉ chứa các chữ số và tối đa 11 chữ số'
            })

        # Validate ID card contains only digits
        if self.identity_card_number and not self.identity_card_number.isdigit():
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'identity_card_number': 'Số chứng minh thư chỉ chứa các chữ số'
            })

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
