from django.db import models
from django.db.models.functions import Upper
from django.utils import timezone

from apps.core.models import SoftDeleteModel


class ParkingLot(SoftDeleteModel):
    """
    Bãi đỗ xe (bậc cao nhất trong mô hình 4 cấp) - có xóa mềm.
    """

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)
    address = models.CharField(max_length=255, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "parking_lot"

    def __str__(self):
        return f"{self.name} ({self.code})"


class ParkingFloor(SoftDeleteModel):
    """
    Tầng bãi xe (thuộc ParkingLot) - có xóa mềm.
    """

    id = models.BigAutoField(primary_key=True)
    lot = models.ForeignKey(
        ParkingLot,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="lot_id",
        related_name="floors",
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=50)
    sort_order = models.IntegerField(default=1)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "parking_floor"

    def __str__(self):
        return f"{self.lot.code} - {self.name}"


class ParkingZone(SoftDeleteModel):
    """
    Khu vực đỗ xe (thuộc ParkingFloor) - có xóa mềm.
    """

    id = models.BigAutoField(primary_key=True)
    floor = models.ForeignKey(
        ParkingFloor,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="floor_id",
        related_name="zones",
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=50)
    description = models.TextField(null=True, blank=True)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "parking_zone"

    def __str__(self):
        return f"{self.floor.name} - Zone {self.code}"


class ParkingSlot(SoftDeleteModel):
    """
    Vị trí đỗ xe cụ thể (thuộc ParkingZone) - có xóa mềm.
    """

    KIND_CHOICES = [
        ("STANDARD", "Ô tô tiêu chuẩn"),
        ("EV_CHARGING", "Xe điện có sạc"),
        ("VIP", "Vị trí VIP"),
        ("ACCESSIBLE", "Người khuyết tật"),
    ]

    STATUS_CHOICES = [
        ("AVAILABLE", "Còn trống"),
        ("OCCUPIED", "Có xe đỗ"),
        ("RESERVED", "Đã đặt trước"),
        ("CHARGING", "Đang sạc điện"),
        ("MAINTENANCE", "Đang bảo trì"),
    ]

    id = models.BigAutoField(primary_key=True)
    zone = models.ForeignKey(
        ParkingZone,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="zone_id",
        related_name="slots",
    )
    code = models.CharField(max_length=20)
    slot_kind = models.CharField(
        max_length=20, choices=KIND_CHOICES, default="STANDARD"
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="AVAILABLE"
    )
    map_row = models.SmallIntegerField(null=True, blank=True)
    map_col = models.SmallIntegerField(null=True, blank=True)
    width = models.DecimalField(max_digits=5, decimal_places=2, default=2.50)
    length = models.DecimalField(max_digits=5, decimal_places=2, default=5.00)
    height = models.DecimalField(max_digits=5, decimal_places=2, default=2.20)
    notes = models.TextField(null=True, blank=True)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "parking_slot"

    def __str__(self):
        return f"Slot {self.code} ({self.zone.code})"


class SlotAllowedVehicleType(models.Model):
    """
    Bảng liên kết M:N loại phương tiện cho phép trên vị trí đỗ.
    Khóa chính phức hợp (slot_id, vehicle_type_id).
    """

    slot = models.ForeignKey(
        ParkingSlot,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="slot_id",
        primary_key=True,
        related_name="allowed_vehicle_types",
    )
    vehicle_type = models.ForeignKey(
        "vehicles.VehicleType",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="vehicle_type_id",
        related_name="+",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        managed = False
        db_table = "slot_allowed_vehicle_type"
        unique_together = (("slot", "vehicle_type"),)

    def __str__(self):
        return f"Slot #{self.slot_id} allows Type #{self.vehicle_type_id}"


class SlotReservation(SoftDeleteModel):
    """
    Đặt chỗ vị trí đỗ xe trước (có xóa mềm).
    """

    STATUS_CHOICES = [
        ("ACTIVE", "Có hiệu lực"),
        ("CANCELLED", "Đã hủy"),
        ("COMPLETED", "Đã hoàn tất"),
        ("EXPIRED", "Hết hạn"),
    ]

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=30, unique=True)
    slot = models.ForeignKey(
        ParkingSlot,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="slot_id",
        related_name="reservations",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="customer_id",
        null=True,
        blank=True,
        related_name="reservations",
    )
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="vehicle_id",
        null=True,
        blank=True,
        related_name="reservations",
    )
    reserved_name = models.CharField(max_length=100, null=True, blank=True)
    reserved_phone = models.CharField(max_length=15, null=True, blank=True)
    reserved_from = models.DateTimeField()
    reserved_until = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    notes = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        "employees.Employee",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="created_by",
        null=True,
        blank=True,
        related_name="created_reservations",
    )
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "slot_reservation"

    def __str__(self):
        return f"Reservation {self.code} - Slot {self.slot_id}"


class ParkingGate(SoftDeleteModel):
    """
    Cổng barrier kiểm soát xe vào/ra (có xóa mềm).
    """

    DIRECTION_CHOICES = [
        ("IN", "Cổng vào"),
        ("OUT", "Cổng ra"),
    ]

    CAMERA_STATUS_CHOICES = [
        ("ONLINE", "Trực tuyến"),
        ("OFFLINE", "Ngoại tuyến"),
        ("ERROR", "Lỗi kết nối"),
    ]

    id = models.BigAutoField(primary_key=True)
    lot = models.ForeignKey(
        ParkingLot,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="lot_id",
        related_name="gates",
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=50)
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    camera_status = models.CharField(
        max_length=20, choices=CAMERA_STATUS_CHOICES, default="ONLINE"
    )
    is_auto_scan = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "parking_gate"

    def __str__(self):
        return f"{self.name} ({self.direction})"


class VehicleEntryExitLog(models.Model):
    """
    Nhật ký phiên xe ra vào bãi đỗ (bất biến, không xóa mềm, append-only).
    Cột license_plate_norm được sinh tự động bởi PostgreSQL.
    """

    RECOGNITION_SOURCE_CHOICES = [
        ("AI", "Tự động nhận diện AI"),
        ("MANUAL", "Nhân viên nhập tay"),
    ]

    REVIEW_STATUS_CHOICES = [
        ("AUTO", "Tự động duyệt"),
        ("VERIFIED", "Nhân viên đã xác nhận"),
        ("DISCREPANCY", "Có sai lệch biển số"),
    ]

    id = models.BigAutoField(primary_key=True)
    session_code = models.CharField(max_length=30, unique=True)
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="vehicle_id",
        null=True,
        blank=True,
        related_name="entry_exit_logs",
    )
    slot = models.ForeignKey(
        ParkingSlot,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="slot_id",
        null=True,
        blank=True,
        related_name="entry_exit_logs",
    )
    ticket = models.ForeignKey(
        "tickets.Ticket",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="ticket_id",
        null=True,
        blank=True,
        related_name="entry_exit_logs",
    )
    entry_gate = models.ForeignKey(
        ParkingGate,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="entry_gate_id",
        null=True,
        blank=True,
        related_name="entries",
    )
    exit_gate = models.ForeignKey(
        ParkingGate,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="exit_gate_id",
        null=True,
        blank=True,
        related_name="exits",
    )
    license_plate = models.CharField(max_length=20)
    license_plate_norm = models.GeneratedField(
        expression=Upper("license_plate"),
        output_field=models.CharField(max_length=20),
        db_persist=True,
    )
    ai_confidence = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )
    recognition_source = models.CharField(
        max_length=20, choices=RECOGNITION_SOURCE_CHOICES, default="AI"
    )
    review_status = models.CharField(
        max_length=20, choices=REVIEW_STATUS_CHOICES, default="AUTO"
    )
    fee_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    entry_time = models.DateTimeField(default=timezone.now)
    exit_time = models.DateTimeField(null=True, blank=True)
    entry_image_url = models.TextField(null=True, blank=True)
    exit_image_url = models.TextField(null=True, blank=True)
    entry_handled_by = models.ForeignKey(
        "employees.Employee",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="entry_handled_by",
        null=True,
        blank=True,
        related_name="handled_entries",
    )
    exit_handled_by = models.ForeignKey(
        "employees.Employee",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="exit_handled_by",
        null=True,
        blank=True,
        related_name="handled_exits",
    )
    notes = models.TextField(null=True, blank=True)
    row_version = models.IntegerField(default=1, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        managed = False
        db_table = "vehicle_entry_exit_log"

    def __str__(self):
        return f"Session {self.session_code} - {self.license_plate}"


class PlateBlacklist(SoftDeleteModel):
    """
    Danh sách đen biển số xe (có xóa mềm).
    """

    id = models.BigAutoField(primary_key=True)
    license_plate = models.CharField(max_length=20)
    license_plate_norm = models.GeneratedField(
        expression=Upper("license_plate"),
        output_field=models.CharField(max_length=20),
        db_persist=True,
    )
    reason = models.TextField()
    unpaid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)
    added_by = models.ForeignKey(
        "employees.Employee",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="added_by",
        null=True,
        blank=True,
        related_name="blacklisted_plates",
    )
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "plate_blacklist"

    def __str__(self):
        return f"Blacklist {self.license_plate}: {self.reason[:30]}"
