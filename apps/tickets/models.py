from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteModel


class TicketType(SoftDeleteModel):
    """
    Loại vé đỗ xe (Vé ngày, Vé tháng, Vé quý, Vé năm...) - bảng danh mục có xóa mềm.
    """

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=50)
    duration_days = models.IntegerField()
    default_price = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, null=True, blank=True)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "ticket_type"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Ticket(SoftDeleteModel):
    """
    Vé đỗ xe dài hạn / cố định gắn với khách hàng và phương tiện (có xóa mềm).
    """

    STATUS_CHOICES = [
        ("ACTIVE", "Còn hiệu lực"),
        ("EXPIRED", "Hết hạn"),
        ("RENEWING", "Đang gia hạn"),
        ("TERMINATED", "Đã chấm dứt"),
    ]

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=10, unique=True)
    vehicle = models.ForeignKey(
        "vehicles.Vehicle",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="vehicle_id",
        related_name="tickets",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="customer_id",
        related_name="tickets",
    )
    slot = models.ForeignKey(
        "parking.ParkingSlot",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="slot_id",
        related_name="tickets",
    )
    ticket_type = models.ForeignKey(
        TicketType,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="ticket_type_id",
        related_name="tickets",
    )
    issued_by = models.ForeignKey(
        "employees.Employee",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="issued_by",
        null=True,
        blank=True,
        related_name="issued_tickets",
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    effective_from = models.DateTimeField(default=timezone.now)
    effective_to = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="ACTIVE")
    notes = models.TextField(null=True, blank=True)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "ticket"

    def __str__(self):
        return f"Ticket {self.code} - {self.vehicle}"


class TicketRenewal(models.Model):
    """
    Lịch sử gia hạn vé đỗ xe (bất biến, không xóa mềm, append-only).
    """

    id = models.BigAutoField(primary_key=True)
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="ticket_id",
        related_name="renewals",
    )
    old_slot = models.ForeignKey(
        "parking.ParkingSlot",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="old_slot_id",
        related_name="+",
    )
    new_slot = models.ForeignKey(
        "parking.ParkingSlot",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="new_slot_id",
        related_name="+",
    )
    old_ticket_type = models.ForeignKey(
        TicketType,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="old_ticket_type_id",
        null=True,
        blank=True,
        related_name="+",
    )
    new_ticket_type = models.ForeignKey(
        TicketType,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="new_ticket_type_id",
        null=True,
        blank=True,
        related_name="+",
    )
    old_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    new_price = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    old_effective_to = models.DateTimeField()
    new_effective_to = models.DateTimeField()
    additional_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(null=True, blank=True)
    renewed_by = models.ForeignKey(
        "employees.Employee",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="renewed_by",
        null=True,
        blank=True,
        related_name="renewals",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "ticket_renewal"

    def __str__(self):
        return f"Renewal #{self.id} for Ticket {self.ticket_id}"


class Payment(SoftDeleteModel):
    """
    Chứng từ giao dịch thanh toán (có xóa mềm, bảo vệ chặt chẽ bởi triggers per TL-39, TL-42).
    """

    METHOD_CHOICES = [
        ("CASH", "Tiền mặt"),
        ("VIETQR", "Chuyển khoản VietQR"),
    ]

    STATUS_CHOICES = [
        ("UNPAID", "Chưa thanh toán"),
        ("PAID", "Đã thanh toán"),
        ("CANCELLED", "Đã hủy"),
        ("REFUNDED", "Đã hoàn tiền"),
    ]

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=30, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="UNPAID")
    paid_at = models.DateTimeField(null=True, blank=True)
    received_by = models.ForeignKey(
        "employees.Employee",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="received_by",
        null=True,
        blank=True,
        related_name="received_payments",
    )
    provider_ref = models.CharField(max_length=100, null=True, blank=True)
    session = models.ForeignKey(
        "parking.VehicleEntryExitLog",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="session_id",
        null=True,
        blank=True,
        related_name="payments",
    )
    ticket = models.ForeignKey(
        Ticket,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="ticket_id",
        null=True,
        blank=True,
        related_name="payments",
    )
    renewal = models.ForeignKey(
        TicketRenewal,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="renewal_id",
        null=True,
        blank=True,
        related_name="payments",
    )
    notes = models.TextField(null=True, blank=True)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "payment"

    def __str__(self):
        return f"Payment {self.code} - {self.amount} ({self.status})"
