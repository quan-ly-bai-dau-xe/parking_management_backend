from django.db import models
from django.core.validators import RegexValidator
from apps.customers.models import Customer


class VehicleType(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text='Vehicle type business code (CAR_4, CAR_7, CAR_12, MOTO) (REQ-4.8.2-F05, OQ-49)'
    )
    name = models.CharField(
        max_length=50,
        help_text='Display name of vehicle type (REQ-4.8.2-F05, REQ-4.4.2-F03, OQ-49)'
    )
    description = models.TextField(
        null=True,
        blank=True,
        help_text='Technical specification and vehicle dimensions description (REQ-4.8.2-F05)'
    )
    row_version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        'accounts.Account',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='deleted_vehicle_types'
    )

    class Meta:
        db_table = 'vehicle_type'
        verbose_name = 'Loại xe'
        verbose_name_plural = 'Loại xe'
        indexes = [
            models.Index(fields=['code'], name='uq_vehicle_type_code_active', condition=models.Q(deleted_at__isnull=True)),
            models.Index(fields=['name'], name='uq_vehicle_type_name_active', condition=models.Q(deleted_at__isnull=True)),
        ]

    def __str__(self):
        return self.name


class TicketType(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text='Ticket type business code: YEARLY, MONTHLY, DAILY (REQ-4.6.1-F08, OQ-06)'
    )
    name = models.CharField(
        max_length=50,
        help_text='Display name of ticket type (REQ-4.6.1-F08, REQ-4.6.2-F07, REQ-4.6.3-F04)'
    )
    duration_days = models.PositiveIntegerField(
        help_text='Validity duration in days (365, 30, 1) (REQ-4.6.1-F06, REQ-4.6.1-F07, OQ-06)'
    )
    default_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text='Standard tariff price in VND (NUMERIC(12, 2) per Rule 05) (REQ-4.6.1-F09, REQ-4.6.2-F08, REQ-4.6.3-F06)'
    )
    description = models.TextField(
        null=True,
        blank=True,
        help_text='Detailed description and terms of ticket type (REQ-4.6.1-F08)'
    )
    row_version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        'accounts.Account',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='deleted_ticket_types'
    )

    class Meta:
        db_table = 'ticket_type'
        verbose_name = 'Loại vé'
        verbose_name_plural = 'Loại vé'
        indexes = [
            models.Index(fields=['code'], name='uq_ticket_type_code_active', condition=models.Q(deleted_at__isnull=True)),
            models.Index(fields=['name'], name='uq_ticket_type_name_active', condition=models.Q(deleted_at__isnull=True)),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(duration_days__gt=0),
                name='ck_ticket_type_duration_positive'
            ),
            models.CheckConstraint(
                condition=models.Q(default_price__gte=0),
                name='ck_ticket_type_price_nonnegative'
            ),
        ]

    def __str__(self):
        return self.name


class Vehicle(models.Model):
    id = models.BigAutoField(primary_key=True)
    code = models.CharField(
        max_length=10,
        unique=True,
        validators=[RegexValidator(r'^[A-Za-z0-9-]+$')],
        help_text='Natural vehicle identifier (Xe-001, Xe-002), immutable upon edit (REQ-4.4.2-F02, REQ-4.4.3-F08, REQ-4.4.4-F03)'
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name='vehicles',
        help_text='Foreign key referencing vehicle owner (ON DELETE RESTRICT) (REQ-4.4.2-F01, DEL-03)'
    )
    vehicle_type = models.ForeignKey(
        VehicleType,
        on_delete=models.PROTECT,
        related_name='vehicles',
        help_text='Foreign key referencing vehicle type (REQ-4.4.2-F03, REQ-4.5.1-F08, REQ-4.8.2-F05)'
    )
    license_plate = models.CharField(
        max_length=20,
        unique=True,
        help_text='Vehicle license plate number, unique among active records (REQ-4.4.2-F06, REQ-4.5.1-F05, REQ-4.6.1-F02)'
    )
    brand = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        help_text='Vehicle manufacturer brand (Kia, Toyota, Honda), nullable per wireframe 4.4.3/4.4.4 (OQ-53, REQ-4.5.1-F07, REQ-4.8.4-F01)'
    )
    model_name = models.CharField(
        max_length=50,
        help_text='Vehicle model name (Cerato, Morning, SH) (REQ-4.4.2-F04, REQ-4.5.1-F06, REQ-4.8.4-F01)'
    )
    ticket_type = models.ForeignKey(
        TicketType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='vehicles',
        help_text='Foreign key storing ticket type registered directly during customer vehicle onboarding flow 4.4.3/4.4.4 (OQ-52)'
    )
    ticket_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Expiration timestamp of ticket registered during vehicle onboarding flow 4.4.3/4.4.4 (OQ-52)'
    )
    row_version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        'accounts.Account',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='deleted_vehicles'
    )

    class Meta:
        db_table = 'vehicle'
        verbose_name = 'Xe'
        verbose_name_plural = 'Xe'
        indexes = [
            models.Index(fields=['code'], name='uq_vehicle_code_active', condition=models.Q(deleted_at__isnull=True)),
            models.Index(fields=['license_plate'], name='uq_veh_lic_plate', condition=models.Q(deleted_at__isnull=True)),
            models.Index(fields=['customer'], name='idx_vehicle_customer'),
            models.Index(fields=['vehicle_type'], name='idx_vehicle_type'),
            models.Index(fields=['ticket_type'], name='idx_vehicle_ticket_type'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(code__regex=r'^[A-Za-z0-9-]+$'),
                name='ck_vehicle_code_format'
            ),
            models.CheckConstraint(
                condition=models.Q(
                    models.Q(ticket_type__isnull=True, ticket_expires_at__isnull=True) |
                    models.Q(ticket_type__isnull=False, ticket_expires_at__isnull=False)
                ),
                name='ck_vehicle_ticket_pref_pair'
            ),
            models.UniqueConstraint(
                fields=['license_plate'],
                condition=models.Q(deleted_at__isnull=True),
                name='uniq_active_vehicle_license_plate'
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.license_plate}"

    def clean(self):
        # Validate license plate format (basic validation)
        if self.license_plate and len(self.license_plate) > 20:
            from django.core.exceptions import ValidationError
            raise ValidationError({
                'license_plate': 'Biển số xe không được vượt quá 20 ký tự'
            })

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)