from django.conf import settings
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.employees.models import Employee
from apps.parking.models import ParkingSlot
from apps.vehicles.models import TicketType, Vehicle


class Ticket(models.Model):
    STATUS_CHOICES = [
        ("ACTIVE", "פעיל"),
        ("EXPIRED", "פג תוקף"),
        ("RENEWED", "הוחלף"),
        ("CANCELLED", "בוטל"),
    ]

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(
        max_length=20,
        unique=True,
        validators=[RegexValidator(r"^[A-Za-z0-9-]+$")],
        help_text="Natural ticket code (VE-01, VE-02) (REQ-4.6.1-F01, REQ-4.6.2-F01, REQ-4.6.3-F01)",
    )
    ticket_type = models.ForeignKey(
        TicketType,
        on_delete=models.PROTECT,
        related_name="tickets",
        help_text="Foreign key referencing ticket tariff tier (REQ-4.6.1-F08, REQ-4.6.2-F07, REQ-4.6.3-F04)",
    )
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="tickets",
        help_text="Customer identifier verified via composite FK fk_ticket_vehicle_customer (OQ-61, REQ-4.6.1-F03)",
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        related_name="tickets",
        help_text="Vehicle identifier verified via composite FK fk_ticket_vehicle_customer (OQ-61, REQ-4.6.1-F02)",
    )
    slot = models.ForeignKey(
        ParkingSlot,
        on_delete=models.PROTECT,
        related_name="tickets",
        help_text="Foreign key referencing assigned parking slot with anti-overlap exclusion (REQ-4.6.1-F10, REQ-4.6.2-F06, REQ-4.6.3-F05)",
    )
    effective_from = models.DateTimeField(
        help_text="Ticket validity start datetime TGBD (REQ-4.6.1-F06, REQ-4.6.2-F04, REQ-4.5.1-F13)"
    )
    effective_to = models.DateTimeField(
        help_text="Ticket validity end datetime TGKT (REQ-4.6.1-F07, REQ-4.6.2-F05, REQ-4.5.1-F14)"
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        help_text="Ticket price billed in VND (NUMERIC(12, 2) per Rule 05) (REQ-4.6.1-F09, REQ-4.6.2-F08)",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="ACTIVE",
        help_text="Ticket lifecycle status: ACTIVE, EXPIRED, RENEWED, CANCELLED (REQ-4.6.1, REQ-4.6.4, OQ-63)",
    )
    issued_by = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="issued_tickets",
        help_text="Foreign key referencing staff member issuing the ticket (REQ-4.6.1, REQ-4.6.2, SRS 3.1)",
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
        related_name="deleted_tickets",
    )

    class Meta:
        db_table = "ticket"
        verbose_name = "כרטיס חניה"
        verbose_name_plural = "כרטיסי חניה"
        indexes = [
            models.Index(
                fields=["code"],
                name="uq_ticket_code_active",
                condition=models.Q(deleted_at__isnull=True),
            ),
            models.Index(fields=["customer"], name="idx_ticket_customer"),
            models.Index(fields=["vehicle"], name="idx_ticket_vehicle"),
            models.Index(fields=["slot"], name="idx_ticket_slot"),
            models.Index(
                fields=["effective_from", "effective_to"],
                name="idx_ticket_effective_period",
            ),
            models.Index(fields=["status"], name="idx_ticket_status"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(code__regex=r"^[A-Za-z0-9-]+$"),
                name="ck_ticket_code_format",
            ),
            models.CheckConstraint(
                condition=models.Q(effective_to__gt=models.F("effective_from")),
                name="ck_ticket_time_order",
            ),
            models.CheckConstraint(
                condition=models.Q(price__gte=0), name="ck_ticket_price_nonnegative"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["ACTIVE", "EXPIRED", "RENEWED", "CANCELLED"]
                ),
                name="ck_ticket_status_enum",
            ),
            models.CheckConstraint(
                condition=models.Q(deleted_at__isnull=True)
                | models.Q(effective_to__lte=models.F("deleted_at")),
                name="ck_ticket_delete_only_expired",
            ),
        ]
        if settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql":
            constraints.append(
                models.ExclusionConstraint(
                    name="excl_ticket_slot_time_overlap",
                    expressions=[
                        ("slot", models.RangeOperators.EQUAL),
                        (
                            models.Func(
                                models.F("effective_from"),
                                models.F("effective_to"),
                                function="TSTZRANGE",
                            ),
                            models.RangeOperators.OVERLAP,
                        ),
                    ],
                    condition=models.Q(deleted_at__isnull=True),
                )
            )

    def __str__(self):
        return self.code

    def clean(self):
        # Additional validation beyond database constraints
        if (
            self.effective_from
            and self.effective_to
            and self.effective_to <= self.effective_from
        ):
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {"effective_to": "תוקף סיום חייב להיות אחרי תוקף התחלה"}
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class TicketRenewal(models.Model):
    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(
        Ticket, on_delete=models.PROTECT, related_name="renewals"
    )
    previous_effective_to = models.DateTimeField(
        help_text="Previous ticket expiration datetime before renewal (REQ-4.6.3-F02)"
    )
    new_effective_to = models.DateTimeField(
        help_text="New ticket expiration datetime, strictly greater than previous (REQ-4.6.3-F03)"
    )
    old_slot = models.ForeignKey(
        ParkingSlot,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="renewals_as_old_slot",
    )
    new_slot = models.ForeignKey(
        ParkingSlot,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="renewals_as_new_slot",
    )
    old_ticket_type = models.ForeignKey(
        TicketType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="renewals_as_old_type",
    )
    new_ticket_type = models.ForeignKey(
        TicketType,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="renewals_as_new_type",
    )
    old_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Historical ticket price before renewal (NUMERIC(12, 2) per Rule 05) (OQ-58)",
    )
    new_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="New ticket price applied upon renewal (NUMERIC(12, 2) per Rule 05) (OQ-58)",
    )
    additional_price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)],
        help_text="Additional surcharge billed for renewal in VND (REQ-4.6.3-F06, Rule 05)",
    )
    renewed_by = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="processed_renewals",
    )
    renewal_date = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when renewal transaction was finalized (REQ-4.6.3-F03, OQ-11)",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ticket_renewal"
        verbose_name = "החלפת כרטיס"
        verbose_name_plural = "החלפות כרטיס"
        indexes = [
            models.Index(fields=["ticket"], name="idx_ticket_renewal_ticket"),
            models.Index(fields=["renewal_date"], name="idx_ticket_renewal_date"),
            models.Index(
                fields=["old_ticket_type"], name="idx_ticket_renewal_old_type"
            ),
            models.Index(
                fields=["new_ticket_type"], name="idx_ticket_renewal_new_type"
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    new_effective_to__gt=models.F("previous_effective_to")
                ),
                name="ck_renewal_date_extension",
            ),
            models.CheckConstraint(
                condition=models.Q(additional_price__gte=0),
                name="ck_renewal_price_nonnegative",
            ),
        ]

    def __str__(self):
        return (
            f"Renewal of {self.ticket.code} on {self.renewal_date.strftime('%Y-%m-%d')}"
        )

    def clean(self):
        if (
            self.new_effective_to
            and self.previous_effective_to
            and self.new_effective_to <= self.previous_effective_to
        ):
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {"new_effective_to": "תוקף סיום חדש חייב להיות אחרי תוקף סיום קודם"}
            )
        if self.old_price is not None and self.old_price < 0:
            from django.core.exceptions import ValidationError

            raise ValidationError({"old_price": "מחיר הישן לא יכול להיות שלילי"})
        if self.new_price is not None and self.new_price < 0:
            from django.core.exceptions import ValidationError

            raise ValidationError({"new_price": "המחיר החדש לא יכול להיות שלילי"})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
