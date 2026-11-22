"""
Serializers for tickets app.
Supports TicketType, Ticket listing, detail, creation, and renewal.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.tickets.models import Ticket, TicketType


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


class TicketRenewSerializer(serializers.Serializer):
    """Serializer gia hạn vé đỗ xe."""

    ticket_type_id = serializers.IntegerField(required=False, allow_null=True)
    new_slot_id = serializers.IntegerField(required=False, allow_null=True)
    additional_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0")
    )
    extend_days = serializers.IntegerField(required=False, default=30)
    notes = serializers.CharField(required=False, allow_blank=True)
