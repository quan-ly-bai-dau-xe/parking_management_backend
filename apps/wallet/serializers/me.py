"""
Serializers for Customer Self-Service endpoints (/api/v1/me/).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.content.models import Notification
from apps.customers.models import Customer
from apps.customers.serializers.customers import (
    STATUS_DISPLAY_MAP,
    AdministrativeDistrictSerializer,
    AdministrativeProvinceSerializer,
    AdministrativeWardSerializer,
    validate_raw_name,
)
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle
from apps.vehicles.serializers.vehicles import VehicleListSerializer
from apps.wallet.serializers.wallet import WalletTransactionSerializer


@extend_schema_serializer(component_name="MeProfile")
class MeProfileSerializer(serializers.Serializer):
    """Authenticated customer self-service profile with live wallet balance."""

    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    date_of_birth = serializers.DateField(allow_null=True, read_only=True)
    gender = serializers.CharField(allow_null=True, read_only=True)
    identity_card_number = serializers.CharField(read_only=True)
    phone = serializers.CharField(read_only=True)
    email = serializers.EmailField(allow_null=True, read_only=True)
    address = serializers.CharField(allow_null=True, read_only=True)
    province_id = serializers.IntegerField(allow_null=True, read_only=True)
    province_name = serializers.SerializerMethodField()
    province = serializers.SerializerMethodField()
    district_id = serializers.IntegerField(allow_null=True, read_only=True)
    district_name = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    ward_id = serializers.IntegerField(allow_null=True, read_only=True)
    ward_name = serializers.SerializerMethodField()
    ward = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)
    status_display = serializers.SerializerMethodField()
    row_version = serializers.IntegerField(read_only=True)
    wallet_balance = serializers.SerializerMethodField()
    wallet_currency = serializers.SerializerMethodField()
    wallet_status = serializers.SerializerMethodField()
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)

    def get_province_name(self, obj: Customer) -> str | None:
        return obj.province.name if obj.province else None

    def get_province(self, obj: Customer) -> dict[str, Any] | None:
        return (
            AdministrativeProvinceSerializer(obj.province).data
            if obj.province
            else None
        )

    def get_district_name(self, obj: Customer) -> str | None:
        return obj.district.name if obj.district else None

    def get_district(self, obj: Customer) -> dict[str, Any] | None:
        return (
            AdministrativeDistrictSerializer(obj.district).data
            if obj.district
            else None
        )

    def get_ward_name(self, obj: Customer) -> str | None:
        return obj.ward.name if obj.ward else None

    def get_ward(self, obj: Customer) -> dict[str, Any] | None:
        return AdministrativeWardSerializer(obj.ward).data if obj.ward else None

    def get_status_display(self, obj: Customer) -> str:
        return STATUS_DISPLAY_MAP.get(obj.status, obj.status)

    def get_wallet_balance(self, obj: Customer) -> str:
        wallet = self.context.get("wallet")
        return f"{wallet.balance:.2f}" if wallet is not None else "0.00"

    def get_wallet_currency(self, obj: Customer) -> str:
        wallet = self.context.get("wallet")
        return wallet.currency if wallet is not None else "VND"

    def get_wallet_status(self, obj: Customer) -> str:
        wallet = self.context.get("wallet")
        return wallet.status if wallet is not None else "ACTIVE"


@extend_schema_serializer(component_name="MeProfileUpdate")
class MeProfileUpdateSerializer(serializers.Serializer):
    """Allowed self-service profile update fields with OCC row_version."""

    row_version = serializers.IntegerField(min_value=1, required=True)
    full_name = serializers.CharField(max_length=45, required=False)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=["Nam", "Nữ"],
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    identity_card_number = serializers.CharField(
        max_length=12,
        required=False,
        allow_blank=False,
    )
    email = serializers.EmailField(
        max_length=100, required=False, allow_null=True, allow_blank=True
    )
    address = serializers.CharField(
        max_length=100, required=False, allow_null=True, allow_blank=True
    )
    province_id = serializers.IntegerField(required=False, allow_null=True)
    district_id = serializers.IntegerField(required=False, allow_null=True)
    ward_id = serializers.IntegerField(required=False, allow_null=True)

    def validate_full_name(self, value: Any) -> str:
        return validate_raw_name(value)

    def validate_identity_card_number(self, value: str) -> str:
        clean = str(value).strip()
        if not (clean.isdigit() and len(clean) in (9, 12)):
            raise serializers.ValidationError("Số CCCD/CMND phải gồm 9 hoặc 12 chữ số.")
        return clean


@extend_schema_serializer(component_name="MeVehicleListItem")
class MeVehicleListSerializer(VehicleListSerializer):
    """Customer self-service vehicle list item including editable attributes."""

    vehicle_type_id = serializers.IntegerField(read_only=True)
    vehicle_type_name = serializers.SerializerMethodField()

    class Meta(VehicleListSerializer.Meta):
        fields = [
            *VehicleListSerializer.Meta.fields,
            "brand",
            "model_name",
            "color",
            "notes",
            "vehicle_type_id",
            "vehicle_type_name",
        ]

    def get_vehicle_type_name(self, obj: Vehicle) -> str | None:
        vtype = getattr(obj, "vehicle_type", None)
        return vtype.name if vtype else None


@extend_schema_serializer(component_name="MeVehicleCreate")
class MeVehicleCreateSerializer(serializers.Serializer):
    """Customer self-service vehicle registration serializer."""

    license_plate = serializers.CharField(max_length=20, required=True)
    model_name = serializers.CharField(max_length=50, required=True)
    vehicle_type_id = serializers.IntegerField(required=True)
    brand = serializers.CharField(
        max_length=50, required=False, allow_blank=True, allow_null=True
    )
    color = serializers.CharField(
        max_length=30, required=False, allow_blank=True, allow_null=True
    )
    image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_license_plate(self, value: Any) -> str:
        clean = (str(value) if value is not None else "").strip(" \t")
        if not clean:
            raise serializers.ValidationError("Biển số xe không được để trống.")
        # Collapse customer spacing/tabs/repeated separators [ .\-]+ only for pure ASCII input
        # without disallowed control chars so POST /api/v1/me/vehicles/ aligns with license_plate_norm
        # while staff validate_raw_license_plate remains strict.
        if clean.isascii() and not any(ord(ch) < 32 and ch != "\t" for ch in clean):
            clean = re.sub(
                r"[ \t.\-]+",
                lambda m: (
                    "-" if "-" in m.group(0) else ("." if "." in m.group(0) else " ")
                ),
                clean,
            ).upper()
        return clean

    def validate_model_name(self, value: str) -> str:
        trimmed = str(value).strip()
        if not trimmed:
            raise serializers.ValidationError("Tên dòng xe không được để trống.")
        return trimmed


@extend_schema_serializer(component_name="MeVehicleUpdate")
class MeVehicleUpdateSerializer(serializers.Serializer):
    """Customer self-service vehicle partial update serializer (OCC row_version required)."""

    row_version = serializers.IntegerField(min_value=1, required=True)
    model_name = serializers.CharField(max_length=50, required=False)
    vehicle_type_id = serializers.IntegerField(required=False)
    brand = serializers.CharField(
        max_length=50, required=False, allow_blank=True, allow_null=True
    )
    color = serializers.CharField(
        max_length=30, required=False, allow_blank=True, allow_null=True
    )
    image_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, allow_null=True)


@extend_schema_serializer(component_name="MeTicket")
class MeTicketSerializer(serializers.Serializer):
    """Customer self-service ticket representation."""

    id = serializers.IntegerField(read_only=True)
    code = serializers.CharField(read_only=True)
    ticket_type_id = serializers.IntegerField(read_only=True)
    ticket_type_code = serializers.CharField(source="ticket_type.code", read_only=True)
    ticket_type_name = serializers.CharField(source="ticket_type.name", read_only=True)
    duration_days = serializers.IntegerField(
        source="ticket_type.duration_days", read_only=True
    )
    vehicle_id = serializers.IntegerField(read_only=True)
    vehicle_code = serializers.CharField(source="vehicle.code", read_only=True)
    license_plate = serializers.CharField(
        source="vehicle.license_plate", read_only=True
    )
    vehicle_type_code = serializers.CharField(
        source="vehicle.vehicle_type.code", read_only=True
    )
    vehicle_type_name = serializers.CharField(
        source="vehicle.vehicle_type.name", read_only=True
    )
    slot_id = serializers.IntegerField(read_only=True)
    slot_code = serializers.CharField(source="slot.code", read_only=True)
    zone_name = serializers.CharField(source="slot.zone.name", read_only=True)
    floor_name = serializers.CharField(source="slot.zone.floor.name", read_only=True)
    slot_location = serializers.SerializerMethodField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    effective_from = serializers.DateTimeField(read_only=True)
    effective_to = serializers.DateTimeField(read_only=True)
    status = serializers.CharField(read_only=True)
    notes = serializers.CharField(allow_null=True, read_only=True)
    row_version = serializers.IntegerField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)

    def get_slot_location(self, obj: Ticket) -> str:
        slot = getattr(obj, "slot", None)
        if not slot:
            return ""
        zone = getattr(slot, "zone", None)
        floor = getattr(zone, "floor", None) if zone else None
        parts = [
            p
            for p in (
                floor.name if floor else None,
                zone.name if zone else None,
                slot.code,
            )
            if p
        ]
        return " - ".join(parts)


@extend_schema_serializer(component_name="MeTicketPurchaseRequest")
class MeTicketPurchaseSerializer(serializers.Serializer):
    """Request serializer for buying a ticket directly from customer wallet."""

    vehicle_id = serializers.IntegerField(required=False, allow_null=True)
    vehicle_code = serializers.CharField(
        max_length=20, required=False, allow_blank=True
    )
    ticket_type_id = serializers.IntegerField(required=False, allow_null=True)
    ticket_type_code = serializers.CharField(
        max_length=20, required=False, allow_blank=True
    )
    slot_id = serializers.IntegerField(required=False, allow_null=True)
    effective_from = serializers.DateTimeField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(
        max_length=100, required=True, allow_blank=False
    )
    payment_method = serializers.ChoiceField(
        choices=[("WALLET", "Ví khách hàng")],
        default="WALLET",
        required=False,
    )
    notes = serializers.CharField(
        max_length=500, required=False, allow_blank=True, allow_null=True
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if (
            not attrs.get("vehicle_id")
            and not (attrs.get("vehicle_code") or "").strip()
        ):
            raise serializers.ValidationError(
                {"vehicle": "Bắt buộc cung cấp vehicle_id hoặc vehicle_code."}
            )
        if (
            not attrs.get("ticket_type_id")
            and not (attrs.get("ticket_type_code") or "").strip()
        ):
            raise serializers.ValidationError(
                {
                    "ticket_type": "Bắt buộc cung cấp ticket_type_id hoặc ticket_type_code."
                }
            )
        return attrs


@extend_schema_serializer(component_name="MeTicketPurchaseResponse")
class MeTicketPurchaseResponseSerializer(serializers.Serializer):
    """Response serializer after purchasing a ticket from customer wallet."""

    ticket = MeTicketSerializer()
    transaction = WalletTransactionSerializer()
    replayed = serializers.BooleanField()


@extend_schema_serializer(component_name="MeTicketCancelResponse")
class MeTicketCancelResponseSerializer(serializers.Serializer):
    """Response serializer after cancelling an eligible unpaid ticket."""

    ticket = MeTicketSerializer()
    message = serializers.CharField()


_MISSING_AMOUNT_RE = re.compile(
    r"(?:còn thiếu|nạp thêm tối thiểu)\s+([\d.,]+)\s*VND",
    re.IGNORECASE,
)


def _extract_missing_amount(content: str | None) -> str | None:
    if not content:
        return None
    match = _MISSING_AMOUNT_RE.search(content)
    if not match:
        return None
    raw_token = match.group(1).strip()
    if not raw_token:
        return None
    # Preserve trailing .X/.XX fractional part while stripping thousand separators
    decimal_match = re.fullmatch(r"(.+)\.(\d{1,2})", raw_token)
    if decimal_match:
        integer_part = re.sub(r"[,.]", "", decimal_match.group(1))
        normalized = f"{integer_part}.{decimal_match.group(2)}"
    else:
        normalized = re.sub(r"[,.]", "", raw_token)
    if not normalized or normalized == ".":
        return None
    try:
        val = Decimal(normalized).quantize(Decimal("0.01"))
    except InvalidOperation, ValueError:
        return None
    if val <= Decimal("0.00"):
        return None
    return f"{val:.2f}"


@extend_schema_serializer(component_name="MeNotification")
class MeNotificationSerializer(serializers.Serializer):
    """Customer self-service notification item."""

    id = serializers.IntegerField(read_only=True)
    title = serializers.CharField(read_only=True)
    content = serializers.CharField(read_only=True)
    notification_type = serializers.CharField(read_only=True)
    is_read = serializers.BooleanField(read_only=True)
    read_at = serializers.DateTimeField(allow_null=True, read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    missing_amount = serializers.SerializerMethodField()

    def get_missing_amount(self, obj: Notification) -> str | None:
        return _extract_missing_amount(getattr(obj, "content", None))


@extend_schema_serializer(component_name="MeNotificationListResponse")
class MeNotificationListResponseSerializer(serializers.Serializer):
    """Paginated notification list envelope including total unread_count."""

    count = serializers.IntegerField()
    total_pages = serializers.IntegerField()
    current_page = serializers.IntegerField()
    page_size = serializers.IntegerField()
    next = serializers.CharField(allow_null=True)
    previous = serializers.CharField(allow_null=True)
    unread_count = serializers.IntegerField()
    results = MeNotificationSerializer(many=True)


@extend_schema_serializer(component_name="MeNotificationMarkReadResponse")
class MeNotificationMarkReadResponseSerializer(serializers.Serializer):
    """Response after marking a single notification as read."""

    notification = MeNotificationSerializer()
    unread_count = serializers.IntegerField()


@extend_schema_serializer(component_name="MeNotificationMarkAllReadResponse")
class MeNotificationMarkAllReadResponseSerializer(serializers.Serializer):
    """Response after marking all unread notifications as read."""

    updated_count = serializers.IntegerField()
    unread_count = serializers.IntegerField()
