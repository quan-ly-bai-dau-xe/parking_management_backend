"""
Serializers for vehicles.
Provides list, detail, write, summary, and filter query serializers.
"""

from __future__ import annotations

import math
import re
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone
from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.vehicles.models import Vehicle, VehicleType


class VehicleTypeSimpleSerializer(serializers.ModelSerializer):
    """Simple vehicle type representation for nested vehicle responses."""

    class Meta:
        model = VehicleType
        fields = ["id", "code", "name"]


class CustomerSimpleSerializer(serializers.Serializer):
    """Simple customer representation for vehicle list rows."""

    id = serializers.IntegerField()
    code = serializers.CharField()
    full_name = serializers.SerializerMethodField()
    is_anonymized = serializers.BooleanField()

    def get_full_name(self, obj: Any) -> str:
        if getattr(obj, "is_anonymized", False):
            return "Khách hàng ẩn danh"
        return getattr(obj, "full_name", "")


class TicketTypeNestedSerializer(serializers.Serializer):
    """Nested ticket type summary."""

    code = serializers.CharField()
    name = serializers.CharField()


class VehicleTicketInfoSerializer(serializers.Serializer):
    """Ticket subscription information for vehicle list row."""

    ticket_type_code = serializers.CharField()
    ticket_type_name = serializers.CharField()
    type = TicketTypeNestedSerializer()
    expires_at = serializers.DateTimeField()
    state = serializers.CharField(
        help_text="Machine state code: valid, expiring_soon, or expired"
    )
    state_display = serializers.CharField(
        help_text="Human-readable state label: Còn hạn, Sắp hết hạn, Đã hết hạn"
    )
    days_remaining = serializers.IntegerField(
        help_text="Number of remaining subscription days (ceiling per TL-28.3)"
    )


class VehicleDetailTicketSerializer(serializers.Serializer):
    """Detailed ticket subscription information for vehicle detail view."""

    ticket_type_code = serializers.CharField()
    ticket_type_name = serializers.CharField()
    type = TicketTypeNestedSerializer()
    effective_from = serializers.DateTimeField(allow_null=True)
    expires_at = serializers.DateTimeField()
    state = serializers.CharField()
    state_display = serializers.CharField()
    days_remaining = serializers.IntegerField()
    progress_pct = serializers.FloatField(
        help_text="Elapsed lifecycle percentage [0.0 - 100.0] per TL-28.3"
    )
    is_valid = serializers.BooleanField(  # type: ignore[assignment]
        help_text="True if subscription is active and unexpired"
    )
    validity_message = serializers.CharField()


class VehicleOwnerDetailSerializer(serializers.Serializer):
    """Complete owner profile representation for detail view."""

    id = serializers.IntegerField()
    code = serializers.CharField()
    full_name = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    registered_vehicles_count = serializers.SerializerMethodField()
    is_anonymized = serializers.BooleanField()

    def get_registered_vehicles_count(self, obj: Any) -> int:
        return int(self.context.get("registered_vehicles_count", 0))

    def get_full_name(self, obj: Any) -> str:
        if getattr(obj, "is_anonymized", False):
            return "Khách hàng ẩn danh"
        return getattr(obj, "full_name", "")

    def get_phone(self, obj: Any) -> str:
        if getattr(obj, "is_anonymized", False):
            return "***"
        return getattr(obj, "phone", "")

    def get_email(self, obj: Any) -> str | None:
        if getattr(obj, "is_anonymized", False):
            return "***"
        return getattr(obj, "email", None)


class VehicleListSerializer(serializers.ModelSerializer):
    """
    Serializer for paginated vehicle list table rows.
    Adheres strictly to the 11 columns of the frontend mockup.
    """

    stt = serializers.SerializerMethodField(help_text="Row sequence number")
    customer = CustomerSimpleSerializer(read_only=True)
    vehicle_type = VehicleTypeSimpleSerializer(read_only=True)
    ticket = serializers.SerializerMethodField(
        help_text="Active ticket subscription info or null"
    )
    status = serializers.SerializerMethodField(
        help_text="Derived status code: parked, active, left"
    )
    status_display = serializers.SerializerMethodField(
        help_text="Vietnamese status label: Đang đỗ, Đang hoạt động, Đã rời bãi"
    )
    current_slot = serializers.CharField(
        read_only=True,
        allow_null=True,
        help_text="Current parking slot label when parked or ticket-assigned",
    )

    class Meta:
        model = Vehicle
        fields = [
            "stt",
            "id",
            "code",
            "license_plate",
            "image_url",
            "customer",
            "vehicle_type",
            "ticket",
            "current_slot",
            "status",
            "status_display",
            "row_version",
            "created_at",
        ]

    def get_stt(self, obj: Vehicle) -> int:
        request = self.context.get("request")
        page = 1
        page_size = 20
        if request:
            try:
                page = int(request.query_params.get("page", 1))
                page_size = int(request.query_params.get("page_size", 20))
            except ValueError, TypeError:
                pass
        idx = getattr(obj, "_row_index", 0)
        return (page - 1) * page_size + idx + 1

    def get_status(self, obj: Vehicle) -> str:
        return getattr(obj, "status_code", "left")

    def get_status_display(self, obj: Vehicle) -> str:
        return getattr(obj, "status_display", "Đã rời bãi")

    def get_ticket(self, obj: Vehicle) -> dict[str, Any] | None:
        rep_state = getattr(obj, "rep_ticket_state", None)
        if rep_state is not None:
            if rep_state == "none":
                return None
            type_code = getattr(obj, "rep_ticket_type_code", None)
            type_name = getattr(obj, "rep_ticket_type_name", None)
            expires_at = getattr(obj, "rep_ticket_effective_to", None)
            if not expires_at or not type_code:
                return None
            state = rep_state
        else:
            ticket_type = getattr(obj, "ticket_type", None)
            expires_at = getattr(obj, "ticket_expires_at", None)
            if not ticket_type or not expires_at:
                return None
            type_code = ticket_type.code
            type_name = ticket_type.name
            now = timezone.now()
            expiring_days = getattr(settings, "TICKET_EXPIRING_SOON_DAYS", 7)
            expiring_window = now + timedelta(days=expiring_days)
            if expires_at < now:
                state = "expired"
            elif expires_at <= expiring_window:
                state = "expiring_soon"
            else:
                state = "valid"

        now = timezone.now()
        diff_sec = (expires_at - now).total_seconds()
        days_rem = max(0, int(math.ceil(diff_sec / 86400.0)))
        state_display_map = {
            "valid": "Còn hạn",
            "expiring_soon": "Sắp hết hạn",
            "expired": "Đã hết hạn",
        }
        state_display = state_display_map.get(state, "")

        return {
            "ticket_type_code": type_code,
            "ticket_type_name": type_name,
            "type": {
                "code": type_code,
                "name": type_name,
            },
            "expires_at": expires_at,
            "state": state,
            "state_display": state_display,
            "days_remaining": days_rem,
        }


@extend_schema_serializer(component_name="VehicleManagementDetail")
class VehicleDetailSerializer(serializers.ModelSerializer):
    """
    Serializer for detailed vehicle specifications and related blocks.
    Serves the 3 detail panels: Chi tiết xe, Thông tin chủ xe, Trạng thái vé.
    """

    vehicle_type = VehicleTypeSimpleSerializer(read_only=True)
    customer = serializers.SerializerMethodField(help_text="Vehicle owner profile")
    owner = serializers.SerializerMethodField(help_text="Vehicle owner profile alias")
    ticket = serializers.SerializerMethodField(
        help_text="Detailed ticket subscription status"
    )
    status = serializers.SerializerMethodField()
    status_display = serializers.SerializerMethodField()
    current_slot = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = Vehicle
        fields = [
            "id",
            "code",
            "license_plate",
            "license_plate_norm",
            "brand",
            "model_name",
            "color",
            "image_url",
            "notes",
            "created_at",
            "updated_at",
            "row_version",
            "vehicle_type",
            "customer",
            "owner",
            "ticket",
            "current_slot",
            "status",
            "status_display",
        ]

    def get_status(self, obj: Vehicle) -> str:
        return getattr(obj, "status_code", "left")

    def get_status_display(self, obj: Vehicle) -> str:
        return getattr(obj, "status_display", "Đã rời bãi")

    def get_customer(self, obj: Vehicle) -> dict[str, Any] | None:
        cust = getattr(obj, "customer", None)
        if not cust:
            return None
        reg_count = getattr(obj, "_registered_vehicles_count", 1)
        serializer = VehicleOwnerDetailSerializer(
            cust,
            context={"registered_vehicles_count": reg_count},
        )
        data = serializer.data
        data["registered_vehicles_count"] = reg_count
        return data

    def get_owner(self, obj: Vehicle) -> dict[str, Any] | None:
        return self.get_customer(obj)

    def get_ticket(self, obj: Vehicle) -> dict[str, Any] | None:
        rep_ticket = getattr(obj, "_representative_ticket", None)
        if rep_ticket is None:
            rep_ticket = getattr(obj, "_latest_ticket", None)

        if not rep_ticket:
            return None

        ticket_type = rep_ticket.ticket_type
        expires_at = rep_ticket.effective_to
        effective_from = rep_ticket.effective_from

        if not ticket_type or not expires_at:
            return None

        now = timezone.now()
        expiring_days = getattr(settings, "TICKET_EXPIRING_SOON_DAYS", 7)
        expiring_window = now + timedelta(days=expiring_days)

        diff_sec = (expires_at - now).total_seconds()
        days_rem = max(0, int(math.ceil(diff_sec / 86400.0)))

        if expires_at < now:
            state = "expired"
            state_display = "Đã hết hạn"
            is_valid = False
            validity_message = "Vé đã hết hạn."
        elif expires_at <= expiring_window:
            state = "expiring_soon"
            state_display = "Sắp hết hạn"
            is_valid = True
            validity_message = "Vé sắp hết hạn."
        else:
            state = "valid"
            state_display = "Còn hạn"
            is_valid = True
            validity_message = "Vé còn hiệu lực."

        # Compute consumed percentage per TL-28.3
        progress_pct = 0.0
        if effective_from and expires_at > effective_from:
            total_duration = (expires_at - effective_from).total_seconds()
            elapsed = (min(expires_at, now) - effective_from).total_seconds()
            if total_duration > 0:
                progress_pct = round(
                    min(100.0, max(0.0, (elapsed / total_duration) * 100.0)), 1
                )

        return {
            "ticket_type_code": ticket_type.code,
            "ticket_type_name": ticket_type.name,
            "type": {
                "code": ticket_type.code,
                "name": ticket_type.name,
            },
            "effective_from": effective_from,
            "expires_at": expires_at,
            "state": state,
            "state_display": state_display,
            "days_remaining": days_rem,
            "progress_pct": progress_pct,
            "is_valid": is_valid,
            "validity_message": validity_message,
        }


class VehicleCreateSerializer(serializers.Serializer):
    """
    Serializer for creating a new vehicle (POST /api/v1/vehicles/).
    Restricted to Employee or Manager role with CSRF validation.
    """

    code = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Optional custom vehicle code. Server generates XE%04d if omitted.",
    )
    license_plate = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Vehicle license plate (e.g., '51K-992.14')",
    )
    model_name = serializers.CharField(
        max_length=50,
        required=True,
        help_text="Vehicle model name (e.g., 'VF8', 'Camry')",
    )
    vehicle_type_id = serializers.IntegerField(
        required=True,
        help_text="Foreign key identifier for VehicleType (must be CAR or EV)",
    )
    customer_id = serializers.IntegerField(
        required=True,
        help_text="Foreign key identifier for Customer owner",
    )
    brand = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Vehicle manufacturer brand",
    )
    color = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Exterior color",
    )
    image_url = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Static media URI for vehicle photo",
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Operator system notes",
    )

    def validate_code(self, value: str | None) -> str | None:
        if value and value.strip():
            clean = value.strip()
            if not re.match(r"^[A-Za-z0-9-]+$", clean):
                raise serializers.ValidationError(
                    "Mã xe chỉ được chứa chữ cái, số và dấu gạch ngang."
                )
            return clean
        return None

    def validate_license_plate(self, value: str) -> str:
        clean = (value or "").strip()
        if not clean:
            raise serializers.ValidationError("Biển số xe không được để trống.")
        return clean

    def validate_model_name(self, value: str) -> str:
        clean = (value or "").strip()
        if not clean:
            raise serializers.ValidationError("Tên mẫu xe không được để trống.")
        return clean


class VehicleUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating vehicle information (PATCH /api/v1/vehicles/{id}/).
    Enforces optimistic concurrency control via required row_version.
    """

    row_version = serializers.IntegerField(
        required=True,
        help_text="Current row_version token for optimistic concurrency control (OCC)",
    )
    model_name = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=False,
        help_text="Updated model name",
    )
    brand = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    color = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    image_url = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    customer_id = serializers.IntegerField(
        required=False,
        help_text="Update owner reference to another customer",
    )
    vehicle_type_id = serializers.IntegerField(
        required=False,
        help_text="Update vehicle classification (must be CAR or EV)",
    )


class VehicleSummarySerializer(serializers.Serializer):
    """KPI summary cards serializer."""

    total_vehicles = serializers.IntegerField(
        help_text="Total active non-deleted vehicles"
    )
    active_vehicles = serializers.IntegerField(
        help_text="Vehicles currently parked or with active subscription"
    )
    expiring_soon_tickets = serializers.IntegerField(
        help_text="Vehicles with ticket expiring within 7 days"
    )
    expired_tickets = serializers.IntegerField(help_text="Vehicles with expired ticket")


class VehicleFilterSerializer(serializers.Serializer):
    """Validation serializer for list and export query parameters."""

    code = serializers.CharField(required=False, allow_blank=True)
    plate = serializers.CharField(required=False, allow_blank=True)
    customer = serializers.CharField(required=False, allow_blank=True)
    vehicle_type = serializers.ChoiceField(
        choices=["CAR", "EV"],
        required=False,
        allow_blank=True,
    )
    ticket_type = serializers.CharField(required=False, allow_blank=True)
    status = serializers.ChoiceField(
        choices=["parked", "active", "left"],
        required=False,
        allow_blank=True,
    )
    ticket_state = serializers.ChoiceField(
        choices=["valid", "expiring_soon", "expired", "none"],
        required=False,
        allow_blank=True,
    )
    ordering = serializers.CharField(required=False, allow_blank=True)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(
        required=False, min_value=1, max_value=100, default=20
    )


class VehicleDeleteSuccessSerializer(serializers.Serializer):
    """Response serializer for successful vehicle deletion."""

    code = serializers.CharField(default="MSG-4.3.1-M01")
    message = serializers.CharField(default="Xóa thành công")
