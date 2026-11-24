"""
Serializers for ParkingSlot models per SRS 4.5.2.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.parking.models import ParkingSlot


class ParkingSlotSerializer(serializers.ModelSerializer):
    """
    Serializer hiển thị danh sách và chi tiết ô đỗ xe.
    Cung cấp thông tin phẳng và tương thích cả frontend lẫn specs.
    """

    floor = serializers.CharField(source="zone.floor.code", read_only=True)
    floor_name = serializers.CharField(source="zone.floor.name", read_only=True)
    zone = serializers.CharField(source="zone.code", read_only=True)
    zone_name = serializers.CharField(source="zone.name", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    slot_kind_display = serializers.CharField(source="get_slot_kind_display", read_only=True)
    is_occupied = serializers.SerializerMethodField()
    display = serializers.SerializerMethodField()
    license_plate = serializers.SerializerMethodField()

    class Meta:
        model = ParkingSlot
        fields = [
            "id",
            "code",
            "zone",
            "zone_name",
            "floor",
            "floor_name",
            "slot_kind",
            "slot_kind_display",
            "status",
            "status_display",
            "is_occupied",
            "map_row",
            "map_col",
            "width",
            "length",
            "height",
            "notes",
            "display",
            "license_plate",
        ]

    def get_is_occupied(self, obj: ParkingSlot) -> bool:
        return obj.status == "OCCUPIED"

    def get_display(self, obj: ParkingSlot) -> str:
        floor_code = obj.zone.floor.code if obj.zone and obj.zone.floor else ""
        zone_code = obj.zone.code if obj.zone else ""
        return f"{floor_code} · {zone_code} · Slot {obj.code}".strip(" ·")

    def get_license_plate(self, obj: ParkingSlot) -> str | None:
        """Nếu ô đỗ có xe đang đỗ (phiên mở), lấy biển số xe."""
        active_log = (
            obj.entry_exit_logs.filter(exit_time__isnull=True)
            .order_by("-entry_time")
            .first()
        )
        return active_log.license_plate if active_log else None


class ParkingSlotUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer cập nhật trạng thái hoặc ghi chú của ô đỗ xe.
    """

    class Meta:
        model = ParkingSlot
        fields = ["status", "notes"]

    def validate_status(self, value: str) -> str:
        allowed_statuses = [choice[0] for choice in ParkingSlot.STATUS_CHOICES]
        if value not in allowed_statuses:
            raise serializers.ValidationError(
                f"Trạng thái '{value}' không hợp lệ. Cho phép: {allowed_statuses}"
            )
        return value
