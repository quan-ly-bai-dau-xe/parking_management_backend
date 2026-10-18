from django.db import models
from django.db.models.functions import Upper

from apps.core.models import SoftDeleteModel


class VehicleType(SoftDeleteModel):
    """
    Loại phương tiện (Ô tô xăng/dầu, Xe điện...) - bảng danh mục có xóa mềm.
    """

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=50)
    description = models.CharField(max_length=255, null=True, blank=True)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "vehicle_type"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Vehicle(SoftDeleteModel):
    """
    Phương tiện khách hàng đăng ký (có xóa mềm).
    Cột license_plate_norm được CSDL tự động chuẩn hóa qua hàm fn_normalize_license_plate().
    """

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=10, unique=True)
    license_plate = models.CharField(max_length=20)
    license_plate_norm = models.GeneratedField(
        expression=Upper("license_plate"),
        output_field=models.CharField(max_length=20),
        db_persist=True,
    )
    model_name = models.CharField(max_length=50)
    brand = models.CharField(max_length=50, null=True, blank=True)
    color = models.CharField(max_length=30, null=True, blank=True)
    image_url = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    vehicle_type = models.ForeignKey(
        VehicleType,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="vehicle_type_id",
        related_name="vehicles",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="customer_id",
        related_name="vehicles",
    )
    ticket_type = models.ForeignKey(
        "tickets.TicketType",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="ticket_type_id",
        null=True,
        blank=True,
        related_name="vehicles",
    )
    ticket_expires_at = models.DateTimeField(null=True, blank=True)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "vehicle"

    def __str__(self):
        return f"{self.license_plate} - {self.model_name}"
