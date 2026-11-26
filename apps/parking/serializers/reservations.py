"""
Serializers for SlotReservation and Customer Parking Map endpoints (SRS 4.5.2).
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.parking.models import ParkingSlot, SlotReservation


class SlotReservationCreateSerializer(serializers.Serializer):
    """Input payload for creating a slot reservation."""

    vehicle_id = serializers.IntegerField(required=False, allow_null=True)
    license_plate = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=20
    )
    reserved_from = serializers.DateTimeField(required=True)
    reserved_until = serializers.DateTimeField(required=True)
    reserved_name = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=100
    )
    reserved_phone = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, max_length=15
    )
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        vehicle_id = attrs.get("vehicle_id")
        license_plate = (attrs.get("license_plate") or "").strip()
        if vehicle_id is None and not license_plate:
            raise serializers.ValidationError(
                "Vui lòng chọn phương tiện hoặc nhập biển số xe để đặt chỗ."
            )

        reserved_from = attrs["reserved_from"]
        reserved_until = attrs["reserved_until"]
        if reserved_until <= reserved_from:
            raise serializers.ValidationError(
                {"reserved_until": "Thời gian kết thúc phải lớn hơn thời gian bắt đầu."}
            )
        return attrs


class SlotReservationSerializer(serializers.Serializer):
    """Output representation of a SlotReservation."""

    id = serializers.IntegerField()
    code = serializers.CharField()
    slot_id = serializers.IntegerField()
    slot_code = serializers.SerializerMethodField()
    zone_code = serializers.SerializerMethodField()
    floor_code = serializers.SerializerMethodField()
    vehicle_id = serializers.IntegerField(allow_null=True)
    license_plate = serializers.SerializerMethodField()
    vehicle_type_code = serializers.SerializerMethodField()
    customer_id = serializers.IntegerField(allow_null=True)
    customer_name = serializers.SerializerMethodField()
    reserved_name = serializers.CharField(allow_null=True)
    reserved_phone = serializers.CharField(allow_null=True)
    reserved_from = serializers.DateTimeField()
    reserved_until = serializers.DateTimeField()
    status = serializers.CharField()
    notes = serializers.CharField(allow_null=True)
    row_version = serializers.IntegerField()
    created_at = serializers.DateTimeField()

    def get_slot_code(self, obj: SlotReservation) -> str:
        return obj.slot.code if obj.slot else ""

    def get_zone_code(self, obj: SlotReservation) -> str:
        if obj.slot and obj.slot.zone:
            return obj.slot.zone.code
        return ""

    def get_floor_code(self, obj: SlotReservation) -> str:
        if obj.slot and obj.slot.zone and obj.slot.zone.floor:
            return obj.slot.zone.floor.code
        return ""

    def get_license_plate(self, obj: SlotReservation) -> str | None:
        return obj.vehicle.license_plate if obj.vehicle else None

    def get_vehicle_type_code(self, obj: SlotReservation) -> str | None:
        if obj.vehicle and obj.vehicle.vehicle_type:
            return obj.vehicle.vehicle_type.code
        return None

    def get_customer_name(self, obj: SlotReservation) -> str | None:
        if obj.customer:
            return obj.customer.full_name
        return obj.reserved_name


class CustomerSlotItemSerializer(serializers.Serializer):
    """
    Privacy-safe parking slot serializer for CUSTOMER parking map (/api/v1/me/parking-slots/).
    Strictly strips other customers' license plates, names, and session PII.
    """

    id = serializers.IntegerField()
    code = serializers.CharField()
    label = serializers.SerializerMethodField()  # type: ignore[assignment]
    row = serializers.SerializerMethodField()
    status = serializers.CharField()
    status_display = serializers.SerializerMethodField()
    slot_kind = serializers.CharField()
    zone = serializers.SerializerMethodField()
    zone_id = serializers.IntegerField()
    floor = serializers.SerializerMethodField()
    floor_id = serializers.SerializerMethodField()
    lot_id = serializers.SerializerMethodField()
    vehicle_types = serializers.SerializerMethodField()
    map_row = serializers.IntegerField(allow_null=True, required=False)
    map_col = serializers.IntegerField(allow_null=True, required=False)
    width = serializers.DecimalField(max_digits=5, decimal_places=2)
    length = serializers.DecimalField(max_digits=5, decimal_places=2)
    height = serializers.DecimalField(max_digits=5, decimal_places=2)
    is_my_reservation = serializers.SerializerMethodField()
    plate = serializers.SerializerMethodField()
    license_plate = serializers.SerializerMethodField()
    reserved_by = serializers.SerializerMethodField()
    reserved_time = serializers.SerializerMethodField()
    row_version = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()

    def _current_customer_id(self) -> int | None:
        return self.context.get("customer_id")

    def _get_open_session(self, obj: ParkingSlot) -> Any:
        prefetched = getattr(obj, "prefetched_open_sessions", None)
        return prefetched[0] if prefetched else None

    def _get_active_reservation(self, obj: ParkingSlot) -> Any:
        prefetched = getattr(obj, "prefetched_active_reservations", None)
        return prefetched[0] if prefetched else None

    def _get_active_ticket(self, obj: ParkingSlot) -> Any:
        prefetched = getattr(obj, "prefetched_active_tickets", None)
        return prefetched[0] if prefetched else None

    def _is_owned_by_customer(self, obj: ParkingSlot) -> bool:
        cid = self._current_customer_id()
        if cid is None:
            return False
        rsv = self._get_active_reservation(obj)
        if rsv and rsv.customer_id == cid:
            return True
        tkt = self._get_active_ticket(obj)
        if tkt and tkt.customer_id == cid:
            return True
        session = self._get_open_session(obj)
        return bool(session and session.vehicle and session.vehicle.customer_id == cid)

    def get_label(self, obj: ParkingSlot) -> str:
        zone_code = getattr(obj.zone, "code", "") if hasattr(obj, "zone") else ""
        if zone_code and not obj.code.startswith(f"{zone_code}-"):
            return f"{zone_code}-{obj.code}"
        return obj.code

    def get_row(self, obj: ParkingSlot) -> str:
        if obj.map_row:
            return str(obj.map_row)
        if obj.code and obj.code[0].isalpha():
            return obj.code[0].upper()
        return "A"

    def get_status_display(self, obj: ParkingSlot) -> str:
        return (
            obj.get_status_display()
            if hasattr(obj, "get_status_display")
            else obj.status
        )

    def get_zone(self, obj: ParkingSlot) -> str:
        return getattr(obj.zone, "code", "") if hasattr(obj, "zone") else ""

    def get_floor(self, obj: ParkingSlot) -> str:
        if hasattr(obj, "zone") and hasattr(obj.zone, "floor"):
            return getattr(obj.zone.floor, "code", "")
        return ""

    def get_floor_id(self, obj: ParkingSlot) -> int:
        if hasattr(obj, "zone") and obj.zone:
            return obj.zone.floor_id
        return 0

    def get_lot_id(self, obj: ParkingSlot) -> int:
        if (
            hasattr(obj, "zone")
            and obj.zone
            and hasattr(obj.zone, "floor")
            and obj.zone.floor
        ):
            return obj.zone.floor.lot_id
        return 0

    def get_vehicle_types(self, obj: ParkingSlot) -> list[str]:
        types: list[str] = []
        if hasattr(obj, "allowed_vehicle_types"):
            for link in obj.allowed_vehicle_types.all():
                if hasattr(link, "vehicle_type") and link.vehicle_type:
                    types.append(link.vehicle_type.code)
        return types

    def get_is_my_reservation(self, obj: ParkingSlot) -> bool:
        cid = self._current_customer_id()
        if cid is None:
            return False
        rsv = self._get_active_reservation(obj)
        return bool(rsv and rsv.customer_id == cid)

    def get_plate(self, obj: ParkingSlot) -> str | None:
        if not self._is_owned_by_customer(obj):
            return None
        session = self._get_open_session(obj)
        if session:
            return session.license_plate
        rsv = self._get_active_reservation(obj)
        if rsv and rsv.vehicle:
            return rsv.vehicle.license_plate
        tkt = self._get_active_ticket(obj)
        if tkt and tkt.vehicle:
            return tkt.vehicle.license_plate
        return None

    def get_license_plate(self, obj: ParkingSlot) -> str | None:
        return self.get_plate(obj)

    def get_reserved_by(self, obj: ParkingSlot) -> str | None:
        cid = self._current_customer_id()
        if cid is None:
            return None
        rsv = self._get_active_reservation(obj)
        if rsv and rsv.customer_id == cid:
            return rsv.reserved_name or (
                rsv.customer.full_name if rsv.customer else None
            )
        tkt = self._get_active_ticket(obj)
        if tkt and tkt.customer_id == cid:
            return tkt.customer.full_name if tkt.customer else None
        return None

    def get_reserved_time(self, obj: ParkingSlot) -> str | None:
        cid = self._current_customer_id()
        if cid is None:
            return None
        rsv = self._get_active_reservation(obj)
        if rsv and rsv.customer_id == cid:
            return rsv.reserved_from.isoformat()
        tkt = self._get_active_ticket(obj)
        if tkt and tkt.customer_id == cid:
            return tkt.effective_from.isoformat()
        return None
