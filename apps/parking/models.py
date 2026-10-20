from django.core.validators import MinValueValidator, RegexValidator
from django.db import models

from apps.accounts.models import Account


class ParkingSlot(models.Model):
    STATUS_CHOICES = [
        ("AVAILABLE", "Có السيارات"),
        ("OCCUPIED", "בעל הרכב"),
        ("RESERVED", "מוזמן"),
        ("MAINTENANCE", "תחזוקה"),
    ]

    id = models.BigAutoField(primary_key=True)
    floor_number = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Facility floor number derived from SRS data type Number(2): 1..99 (OQ-54, REQ-4.5.2-F02, REQ-4.8.1-F01)",
    )
    slot_number = models.PositiveIntegerField(
        validators=[MinValueValidator(1)],
        help_text="Sequential slot number per floor derived from SRS data type Number(3): 1..999 (OQ-54, REQ-4.5.2, REQ-4.8.2-F02)",
    )
    code = models.CharField(
        max_length=20,
        validators=[RegexValidator(r"^[A-Za-z0-9-]+$")],
        help_text="Natural slot display code (e.g. A-1, A-2), unique per floor (REQ-4.8.1-F02, REQ-4.8.3-F01, OQ-59)",
    )
    map_row = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Floor map 2D grid row coordinate, 1-based positive integer (SRS 4.5.2, image14, [PROPOSAL OQ-69])",
    )
    map_col = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1)],
        help_text="Floor map 2D grid column coordinate, 1-based positive integer (SRS 4.5.2, image14, [PROPOSAL OQ-69])",
    )
    width = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0.1)],
        help_text="Slot width in meters (REQ-4.5.2-F03, REQ-4.8.2-F03, REQ-4.8.3-F02)",
    )
    length = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0.1)],
        help_text="Slot length in meters (REQ-4.5.2-F03, REQ-4.8.2-F04, REQ-4.8.3-F02)",
    )
    height = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        validators=[MinValueValidator(0.1)],
        help_text="Slot height clearance in meters (REQ-4.5.2-F03, REQ-4.8.2-F06, REQ-4.8.3-F02)",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="AVAILABLE",
        help_text="Slot operational status: AVAILABLE, OCCUPIED, RESERVED, MAINTENANCE (REQ-4.5.2, REQ-4.8.1, OQ-63)",
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
        related_name="deleted_parking_slots",
    )

    class Meta:
        db_table = "parking_slot"
        verbose_name = "מקום חניה"
        verbose_name_plural = "מקומות חניה"
        indexes = [
            models.Index(
                fields=["floor_number", "slot_number"],
                name="uq_ps_floor_slot",
                condition=models.Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["floor_number", "code"],
                name="uq_ps_floor_code",
                condition=models.Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["floor_number", "map_row", "map_col"],
                name="uq_ps_floor_map",
                condition=models.Q(deleted_at__isnull=True)
                & models.Q(map_row__isnull=False)
                & models.Q(map_col__isnull=False),
            ),
            models.Index(
                fields=["floor_number", "status"],
                name="idx_ps_floor_status",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(floor_number__gte=1, floor_number__lte=99),
                name="ck_slot_floor_range",
            ),
            models.CheckConstraint(
                condition=models.Q(slot_number__gte=1, slot_number__lte=999),
                name="ck_slot_number_range",
            ),
            models.CheckConstraint(
                condition=models.Q(width__gt=0), name="ck_slot_width_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(length__gt=0), name="ck_slot_length_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(height__gt=0), name="ck_slot_height_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    models.Q(map_row__isnull=True, map_col__isnull=True)
                    | models.Q(
                        map_row__isnull=False,
                        map_col__isnull=False,
                        map_row__gt=0,
                        map_col__gt=0,
                    )
                ),
                name="ck_slot_map_coords_pair",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=["AVAILABLE", "OCCUPIED", "RESERVED", "MAINTENANCE"]
                ),
                name="ck_slot_status_enum",
            ),
        ]

    def __str__(self):
        return f"Floor {self.floor_number}-Slot {self.slot_number} ({self.code})"


class SlotAllowedVehicleType(models.Model):
    id = models.BigAutoField(primary_key=True)
    slot = models.ForeignKey(
        ParkingSlot, on_delete=models.PROTECT, related_name="allowed_vehicle_types"
    )
    vehicle_type = models.ForeignKey(
        "vehicles.VehicleType", on_delete=models.PROTECT, related_name="allowed_slots"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "slot_allowed_vehicle_type"
        verbose_name = "סוג רכב מותר למקום"
        verbose_name_plural = "סוגי רכב מורשים למקומות"
        constraints = [
            models.UniqueConstraint(
                fields=["slot", "vehicle_type"], name="uq_slot_allowed_vehicle_type"
            ),
        ]
        indexes = [
            models.Index(fields=["vehicle_type"], name="idx_slot_allowed_vehicle_type"),
        ]

    def __str__(self):
        return f"{self.slot.code} - {self.vehicle_type.name}"
