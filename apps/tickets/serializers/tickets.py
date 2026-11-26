"""
Serializers for tickets app.
Supports TicketType, Ticket listing, detail, creation, update, and renewal.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.tickets.models import Ticket, TicketRenewal, TicketType


class TicketTypeSerializer(serializers.ModelSerializer):
    """Serializer danh mục loại vé (Vé ngày, Vé tháng, Vé quý, Vé năm...)."""

    class Meta:
        model = TicketType
        fields = [
            "id",
            "code",
            "name",
            "duration_days",
            "default_price",
            "description",
        ]


class TicketListSerializer(serializers.Serializer):
    """Serializer cho từng dòng vé đỗ xe trong danh sách."""

    id = serializers.IntegerField()
    code = serializers.CharField()
    ticket_type = serializers.CharField(source="ticket_type.name", default="—")
    ticket_type_code = serializers.CharField(source="ticket_type.code", default="")
    customer_code = serializers.CharField(source="customer.code", default="—")
    customer_name = serializers.CharField(source="customer.full_name", default="—")
    customer_phone = serializers.CharField(source="customer.phone", default="—")
    license_plate = serializers.CharField(source="vehicle.license_plate", default="—")
    vehicle_type = serializers.CharField(
        source="vehicle.vehicle_type.name", default="—"
    )
    slot_location = serializers.SerializerMethodField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    effective_from = serializers.DateTimeField()
    effective_to = serializers.DateTimeField()
    status = serializers.CharField()
    status_display = serializers.SerializerMethodField()
    row_version = serializers.IntegerField()

    def get_slot_location(self, obj: Ticket) -> str:
        if obj.slot:
            floor_name = (
                getattr(obj.slot.zone.floor, "name", "") if obj.slot.zone else ""
            )
            zone_code = getattr(obj.slot.zone, "code", "") if obj.slot.zone else ""
            return f"{floor_name} - {zone_code}{obj.slot.code}".strip(" -")
        return "Chưa có vị trí"

    def get_status_display(self, obj: Ticket) -> str:
        status_map = {
            "ACTIVE": "Đang hoạt động",
            "EXPIRED": "Đã hết hạn",
            "RENEWING": "Đang gia hạn",
            "TERMINATED": "Đã chấm dứt",
        }
        return status_map.get(obj.status, obj.status)


class TicketRenewalHistorySerializer(serializers.Serializer):
    """Serializer lịch sử gia hạn vé đỗ xe."""

    id = serializers.IntegerField()
    old_slot_id = serializers.IntegerField(source="old_slot.id", allow_null=True)
    old_slot_code = serializers.SerializerMethodField()
    new_slot_id = serializers.IntegerField(source="new_slot.id", allow_null=True)
    new_slot_code = serializers.SerializerMethodField()
    old_ticket_type_id = serializers.IntegerField(
        source="old_ticket_type.id", allow_null=True
    )
    old_ticket_type_name = serializers.CharField(
        source="old_ticket_type.name", default=None, allow_null=True
    )
    new_ticket_type_id = serializers.IntegerField(
        source="new_ticket_type.id", allow_null=True
    )
    new_ticket_type_name = serializers.CharField(
        source="new_ticket_type.name", default=None, allow_null=True
    )
    old_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True
    )
    new_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, allow_null=True
    )
    old_effective_to = serializers.DateTimeField()
    new_effective_to = serializers.DateTimeField()
    additional_price = serializers.DecimalField(max_digits=12, decimal_places=2)
    notes = serializers.CharField(allow_null=True, allow_blank=True)
    renewed_by_name = serializers.SerializerMethodField()
    renewed_at = serializers.DateTimeField(source="created_at")

    def get_old_slot_code(self, obj: TicketRenewal) -> str | None:
        if obj.old_slot:
            floor = (
                getattr(obj.old_slot.zone.floor, "name", "")
                if getattr(obj.old_slot, "zone", None)
                else ""
            )
            zone = (
                getattr(obj.old_slot.zone, "code", "")
                if getattr(obj.old_slot, "zone", None)
                else ""
            )
            return f"{floor} - {zone}{obj.old_slot.code}".strip(" -")
        return None

    def get_new_slot_code(self, obj: TicketRenewal) -> str | None:
        if obj.new_slot:
            floor = (
                getattr(obj.new_slot.zone.floor, "name", "")
                if getattr(obj.new_slot, "zone", None)
                else ""
            )
            zone = (
                getattr(obj.new_slot.zone, "code", "")
                if getattr(obj.new_slot, "zone", None)
                else ""
            )
            return f"{floor} - {zone}{obj.new_slot.code}".strip(" -")
        return None

    def get_renewed_by_name(self, obj: TicketRenewal) -> str | None:
        if obj.renewed_by:
            return getattr(obj.renewed_by, "full_name", str(obj.renewed_by))
        return None


class TicketDetailSerializer(serializers.Serializer):
    """Serializer chi tiết vé đỗ xe."""

    id = serializers.IntegerField()
    code = serializers.CharField()
    ticket_type = TicketTypeSerializer()
    customer_id = serializers.IntegerField(source="customer.id")
    customer_code = serializers.CharField(source="customer.code", default="—")
    customer_name = serializers.CharField(source="customer.full_name", default="—")
    customer_phone = serializers.CharField(source="customer.phone", default="—")
    vehicle_id = serializers.IntegerField(source="vehicle.id")
    license_plate = serializers.CharField(source="vehicle.license_plate", default="—")
    vehicle_type = serializers.CharField(
        source="vehicle.vehicle_type.name", default="—"
    )
    slot_id = serializers.IntegerField(source="slot.id", allow_null=True)
    slot_location = serializers.SerializerMethodField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    effective_from = serializers.DateTimeField()
    effective_to = serializers.DateTimeField()
    status = serializers.CharField()
    status_display = serializers.SerializerMethodField()
    notes = serializers.CharField(allow_null=True, allow_blank=True)
    row_version = serializers.IntegerField()
    renewals = TicketRenewalHistorySerializer(many=True, read_only=True)

    def get_slot_location(self, obj: Ticket) -> str:
        if obj.slot:
            floor_name = (
                getattr(obj.slot.zone.floor, "name", "") if obj.slot.zone else ""
            )
            zone_code = getattr(obj.slot.zone, "code", "") if obj.slot.zone else ""
            return f"{floor_name} - {zone_code}{obj.slot.code}".strip(" -")
        return "Chưa có vị trí"

    def get_status_display(self, obj: Ticket) -> str:
        status_map = {
            "ACTIVE": "Đang hoạt động",
            "EXPIRED": "Đã hết hạn",
            "RENEWING": "Đang gia hạn",
            "TERMINATED": "Đã chấm dứt",
        }
        return status_map.get(obj.status, obj.status)


class TicketCreateSerializer(serializers.Serializer):
    """Serializer tạo mới vé đỗ xe."""

    ticket_type_id = serializers.IntegerField(required=True)
    customer_id = serializers.IntegerField(required=False, allow_null=True)
    customer_code = serializers.CharField(required=False, allow_blank=True)
    vehicle_id = serializers.IntegerField(required=False, allow_null=True)
    license_plate = serializers.CharField(required=False, allow_blank=True)
    slot_id = serializers.IntegerField(required=False, allow_null=True)
    effective_from = serializers.DateTimeField(required=False)
    effective_to = serializers.DateTimeField(required=False)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)


class TicketUpdateSerializer(serializers.Serializer):
    """
    Serializer cập nhật / sửa vé đỗ xe (SRS 4.6.3).
    Yêu cầu bắt buộc row_version để kiểm soát đồng thời lạc quan (OCC).
    """

    row_version = serializers.IntegerField(
        required=True, help_text="Phiên bản dòng dữ liệu cho kiểm soát OCC"
    )
    effective_to = serializers.DateTimeField(
        required=False, help_text="Thời điểm hết hạn mới"
    )
    ticket_type_id = serializers.IntegerField(
        required=False, allow_null=True, help_text="ID loại vé mới"
    )
    slot_id = serializers.IntegerField(
        required=False, allow_null=True, help_text="ID vị trí đỗ mới"
    )
    price = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        required=False,
        help_text="Giá vé điều chỉnh",
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Ghi chú điều chỉnh",
    )
    status = serializers.ChoiceField(
        choices=Ticket.STATUS_CHOICES, required=False, help_text="Trạng thái vé"
    )


class TicketRenewSerializer(serializers.Serializer):
    """Serializer gia hạn vé đỗ xe."""

    ticket_type_id = serializers.IntegerField(required=False, allow_null=True)
    new_slot_id = serializers.IntegerField(required=False, allow_null=True)
    additional_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    extend_days = serializers.IntegerField(required=False, default=30)
    notes = serializers.CharField(required=False, allow_blank=True)


class TicketDeleteSuccessSerializer(serializers.Serializer):
    """Envelope phản hồi khi xóa vé thành công (SRS 4.6.4)."""

    code = serializers.CharField(default="MSG-4.6.4-M01")
    message = serializers.CharField(default="Xóa thành công")
