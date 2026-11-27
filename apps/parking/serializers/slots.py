"""
Serializers for ParkingSlot domain per TL-27, TL-50, and SRS 4.8.1 - 4.8.5.
Fully typed, validated, and documented for DRF Spectacular OpenAPI generation.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.core.messages import get_prop_message
from apps.parking.models import ParkingSlot, ParkingZone


def format_duration_vietnamese(start_time: Any) -> str:
    """Định dạng khoảng thời gian đỗ xe thân thiện bằng tiếng Việt."""
    if not start_time:
        return ""
    now = timezone.now()
    diff = now - start_time
    total_seconds = int(diff.total_seconds())
    if total_seconds < 0:
        return "0 phút"

    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60

    if days > 0:
        return f"{days} ngày {hours} giờ"
    if hours > 0:
        return f"{hours} giờ {minutes} phút"
    return f"{max(1, minutes)} phút"


class SlotFilterSerializer(serializers.Serializer):
    """Tham số lọc cho danh sách ô đỗ xe."""

    floor = serializers.CharField(
        required=False,
        help_text="Mã hoặc ID tầng bãi đỗ (ví dụ: 'B1', '1')",
    )
    zone = serializers.CharField(
        required=False,
        help_text="Mã hoặc ID khu vực (ví dụ: 'A', '2')",
    )
    status = serializers.CharField(
        required=False,
        help_text=(
            "Trạng thái ô đỗ (AVAILABLE, OCCUPIED, RESERVED, CHARGING, MAINTENANCE) "
            "hoặc danh sách phân cách dấu phẩy, hoặc 'OVERSTAY'"
        ),
    )
    vehicle_type = serializers.CharField(
        required=False,
        help_text="Mã hoặc ID loại xe cho phép (ví dụ: 'CAR', 'EV')",
    )
    slot_kind = serializers.CharField(
        required=False,
        help_text="Loại ô đỗ: 'STANDARD', 'PRIORITY', 'EV_CHARGING'",
    )
    search = serializers.CharField(
        required=False,
        help_text="Từ khóa tìm kiếm theo mã ô đỗ hoặc ghi chú",
    )
    ordering = serializers.CharField(
        required=False,
        help_text="Sắp xếp kết quả (ví dụ: 'code', '-code', 'status')",
    )
    page = serializers.IntegerField(
        required=False,
        default=1,
        min_value=1,
        help_text="Số trang cần truy vấn",
    )
    page_size = serializers.IntegerField(
        required=False,
        default=20,
        min_value=1,
        max_value=100,
        help_text="Kích thước trang (mặc định: 20)",
    )


class SlotItemSerializer(serializers.Serializer):
    """Serializer biểu diễn ô đỗ xe trong danh sách (SRS 4.8.1)."""

    id = serializers.IntegerField(help_text="ID ô đỗ xe")
    code = serializers.CharField(help_text="Mã ô đỗ xe")
    label = serializers.SerializerMethodField(  # type: ignore[assignment]
        help_text="Nhãn hiển thị dạng Khu-Mã"
    )
    row = serializers.SerializerMethodField(help_text="Dãy đỗ (A, B, C...)")
    status = serializers.CharField(help_text="Mã trạng thái ô đỗ")
    status_display = serializers.SerializerMethodField(
        help_text="Mô tả trạng thái bằng tiếng Việt"
    )
    slot_kind = serializers.CharField(
        help_text="Loại ô đỗ (STANDARD, PRIORITY, EV_CHARGING)"
    )
    zone = serializers.SerializerMethodField(help_text="Mã khu vực")
    zone_id = serializers.IntegerField(help_text="ID khu vực")
    floor = serializers.SerializerMethodField(help_text="Mã tầng")
    floor_id = serializers.SerializerMethodField(help_text="ID tầng")
    lot_id = serializers.SerializerMethodField(help_text="ID bãi đỗ")
    vehicle_types = serializers.SerializerMethodField(
        help_text="Danh sách mã loại xe cho phép"
    )
    plate = serializers.SerializerMethodField(
        help_text="Biển số xe đang đỗ hoặc liên kết nếu có"
    )
    license_plate = serializers.SerializerMethodField(
        help_text="Biển số xe (alias cho plate)"
    )
    reserved_phone = serializers.SerializerMethodField(
        help_text="Số điện thoại người đặt trước"
    )
    notes = serializers.CharField(
        allow_blank=True, allow_null=True, required=False, help_text="Ghi chú ô đỗ"
    )
    row_version = serializers.IntegerField(help_text="Phiên bản dòng (OCC)")
    map_row = serializers.IntegerField(
        allow_null=True, required=False, help_text="Tọa độ hàng trên sơ đồ"
    )
    map_col = serializers.IntegerField(
        allow_null=True, required=False, help_text="Tọa độ cột trên sơ đồ"
    )
    width = serializers.DecimalField(
        max_digits=5, decimal_places=2, help_text="Chiều rộng (m)"
    )
    length = serializers.DecimalField(
        max_digits=5, decimal_places=2, help_text="Chiều dài (m)"
    )
    height = serializers.DecimalField(
        max_digits=5, decimal_places=2, help_text="Chiều cao (m)"
    )
    reserved_by = serializers.SerializerMethodField(
        help_text="Người đặt trước hoặc khách hàng đang sử dụng"
    )
    reserved_time = serializers.SerializerMethodField(
        help_text="Thời điểm đặt trước nếu có"
    )
    duration = serializers.SerializerMethodField(
        help_text="Thời gian xe đã đỗ trong ô nếu đang mở"
    )
    is_overstay = serializers.SerializerMethodField(help_text="Cờ cảnh báo đỗ quá 24h")
    created_at = serializers.DateTimeField(help_text="Thời điểm tạo")
    updated_at = serializers.DateTimeField(help_text="Thời điểm cập nhật cuối")

    def _get_open_session(self, obj: ParkingSlot) -> Any:
        prefetched = getattr(obj, "prefetched_open_sessions", None)
        if prefetched:
            return prefetched[0]
        return None

    def _get_active_reservation(self, obj: ParkingSlot) -> Any:
        prefetched = getattr(obj, "prefetched_active_reservations", None)
        if prefetched:
            return prefetched[0]
        return None

    def _get_active_ticket(self, obj: ParkingSlot) -> Any:
        prefetched = getattr(obj, "prefetched_active_tickets", None)
        if prefetched:
            return prefetched[0]
        return None

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

    def get_plate(self, obj: ParkingSlot) -> str | None:
        session = self._get_open_session(obj)
        if session:
            return session.license_plate
        rsv = self._get_active_reservation(obj)
        if rsv:
            if rsv.vehicle:
                return rsv.vehicle.license_plate
            if getattr(rsv, "license_plate", None):
                return rsv.license_plate
        tkt = self._get_active_ticket(obj)
        if tkt and tkt.vehicle:
            return tkt.vehicle.license_plate
        return None

    def get_license_plate(self, obj: ParkingSlot) -> str | None:
        return self.get_plate(obj)

    def get_reserved_by(self, obj: ParkingSlot) -> str | None:
        rsv = self._get_active_reservation(obj)
        if rsv:
            if rsv.reserved_name:
                return rsv.reserved_name
            if rsv.customer:
                return getattr(rsv.customer, "full_name", None)
        tkt = self._get_active_ticket(obj)
        if tkt and tkt.customer:
            return getattr(tkt.customer, "full_name", None)
        return None

    def get_reserved_phone(self, obj: ParkingSlot) -> str | None:
        rsv = self._get_active_reservation(obj)
        if rsv:
            if getattr(rsv, "reserved_phone", None):
                return rsv.reserved_phone
            if rsv.customer:
                return getattr(rsv.customer, "phone", None)
        return None

    def get_reserved_time(self, obj: ParkingSlot) -> str | None:
        rsv = self._get_active_reservation(obj)
        if rsv:
            return rsv.reserved_from.isoformat()
        tkt = self._get_active_ticket(obj)
        if tkt:
            return tkt.effective_from.isoformat()
        return None

    def get_duration(self, obj: ParkingSlot) -> str:
        session = self._get_open_session(obj)
        if session and session.entry_time:
            return format_duration_vietnamese(session.entry_time)
        return ""

    def get_is_overstay(self, obj: ParkingSlot) -> bool:
        session = self._get_open_session(obj)
        if session and session.entry_time:
            diff = timezone.now() - session.entry_time
            return diff.total_seconds() > 86400  # > 24h
        return False


class SlotDetailSerializer(SlotItemSerializer):
    """Serializer chi tiết ô đỗ xe kèm đầy đủ phiên đỗ, vé, đặt chỗ (SRS 4.8.4)."""

    open_session = serializers.SerializerMethodField(
        help_text="Thông tin phiên đỗ xe đang mở (nếu có)"
    )
    active_reservation = serializers.SerializerMethodField(
        help_text="Thông tin đặt chỗ đang có hiệu lực (nếu có)"
    )
    active_ticket = serializers.SerializerMethodField(
        help_text="Thông tin vé đỗ xe đang có hiệu lực (nếu có)"
    )
    allowed_vehicle_types = serializers.SerializerMethodField(
        help_text="Danh sách loại phương tiện được phép đỗ chi tiết"
    )

    def get_open_session(self, obj: ParkingSlot) -> dict[str, Any] | None:
        session = self._get_open_session(obj)
        if not session:
            return None

        customer_name = ""
        if session.vehicle and session.vehicle.customer:
            customer_name = getattr(session.vehicle.customer, "full_name", "")

        gate_name = ""
        if session.entry_gate:
            gate_name = getattr(session.entry_gate, "name", "")

        diff = timezone.now() - session.entry_time if session.entry_time else None
        is_overstay = bool(diff and diff.total_seconds() > 86400)

        return {
            "session_code": session.session_code,
            "entry_time": session.entry_time.isoformat()
            if session.entry_time
            else None,
            "entry_gate_name": gate_name,
            "vehicle_plate": session.license_plate,
            "customer_name": customer_name,
            "duration": format_duration_vietnamese(session.entry_time)
            if session.entry_time
            else "",
            "is_overstay": is_overstay,
        }

    def get_active_reservation(self, obj: ParkingSlot) -> dict[str, Any] | None:
        rsv = self._get_active_reservation(obj)
        if not rsv:
            return None

        plate = rsv.vehicle.license_plate if rsv.vehicle else None
        name = rsv.reserved_name
        if not name and rsv.customer:
            name = getattr(rsv.customer, "full_name", "")

        return {
            "reservation_code": rsv.code,
            "reserved_name": name,
            "reserved_phone": rsv.reserved_phone,
            "reserved_from": rsv.reserved_from.isoformat()
            if rsv.reserved_from
            else None,
            "reserved_until": rsv.reserved_until.isoformat()
            if rsv.reserved_until
            else None,
            "vehicle_plate": plate,
        }

    def get_active_ticket(self, obj: ParkingSlot) -> dict[str, Any] | None:
        tkt = self._get_active_ticket(obj)
        if not tkt:
            return None

        plate = tkt.vehicle.license_plate if tkt.vehicle else None
        customer_name = getattr(tkt.customer, "full_name", "") if tkt.customer else ""
        type_name = (
            getattr(tkt.ticket_type, "name", "")
            if hasattr(tkt, "ticket_type") and tkt.ticket_type
            else ""
        )

        return {
            "ticket_code": tkt.code,
            "ticket_type_name": type_name,
            "customer_name": customer_name,
            "vehicle_plate": plate,
            "effective_from": tkt.effective_from.isoformat()
            if tkt.effective_from
            else None,
            "effective_to": tkt.effective_to.isoformat() if tkt.effective_to else None,
        }

    def get_allowed_vehicle_types(self, obj: ParkingSlot) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        if hasattr(obj, "allowed_vehicle_types"):
            for link in obj.allowed_vehicle_types.all():
                if hasattr(link, "vehicle_type") and link.vehicle_type:
                    result.append(
                        {
                            "id": link.vehicle_type.id,
                            "code": link.vehicle_type.code,
                            "name": link.vehicle_type.name,
                        }
                    )
        return result


@extend_schema_serializer(
    examples=[],
)
class ParkingSlotCreateSerializer(serializers.Serializer):
    """Serializer nhận dữ liệu thêm mới ô đỗ xe (SRS 4.8.2)."""

    zone_id = serializers.IntegerField(
        required=True,
        help_text="ID khu vực chứa ô đỗ (ParkingZone)",
    )
    code = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Mã ô đỗ xe (ví dụ: 'A01', 'B1-02')",
    )
    slot_kind = serializers.ChoiceField(
        choices=ParkingSlot.KIND_CHOICES,
        default="STANDARD",
        help_text="Loại ô đỗ: 'STANDARD', 'PRIORITY', 'EV_CHARGING'",
    )
    status = serializers.ChoiceField(
        choices=ParkingSlot.STATUS_CHOICES,
        default="AVAILABLE",
        help_text="Trạng thái ban đầu: 'AVAILABLE', 'MAINTENANCE'",
    )
    map_row = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        help_text="Tọa độ hàng trên sơ đồ ma trận",
    )
    map_col = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        help_text="Tọa độ cột trên sơ đồ ma trận",
    )
    width = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.50"),
        min_value=Decimal("0.01"),
        help_text="Chiều rộng (m)",
    )
    length = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("5.00"),
        min_value=Decimal("0.01"),
        help_text="Chiều dài (m)",
    )
    height = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("2.20"),
        min_value=Decimal("0.01"),
        help_text="Chiều cao (m)",
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        help_text="Ghi chú về ô đỗ",
    )
    allowed_vehicle_type_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        default=list,
        help_text="Danh sách ID loại xe được phép đỗ vào ô",
    )

    def validate_code(self, value: str) -> str:
        clean = value.strip().upper()
        if not clean:
            raise serializers.ValidationError(
                get_prop_message(
                    "PROP-4.8.2-P02",
                    "Dữ liệu vị trí đỗ xe không hợp lệ, xin mời nhập lại.",
                )
            )
        if not re.match(r"^[A-Za-z0-9 .\-]+$", clean):
            raise serializers.ValidationError(
                get_prop_message(
                    "PROP-4.8.2-P02",
                    "Dữ liệu vị trí đỗ xe không hợp lệ, xin mời nhập lại.",
                )
            )
        return clean

    def validate_zone_id(self, value: int) -> int:
        if not ParkingZone.objects.filter(id=value, deleted_at__isnull=True).exists():
            raise serializers.ValidationError(
                get_prop_message(
                    "PROP-4.8.2-P02",
                    "Dữ liệu vị trí đỗ xe không hợp lệ, xin mời nhập lại.",
                )
            )
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        map_row = attrs.get("map_row")
        map_col = attrs.get("map_col")
        if (map_row is None and map_col is not None) or (
            map_row is not None and map_col is None
        ):
            raise serializers.ValidationError(
                {
                    "map_coords": get_prop_message(
                        "PROP-4.8.2-P02",
                        "Dữ liệu vị trí đỗ xe không hợp lệ, xin mời nhập lại.",
                    )
                }
            )

        status_val = attrs.get("status", "AVAILABLE")
        slot_kind = attrs.get("slot_kind", "STANDARD")
        if status_val == "CHARGING" and slot_kind != "EV_CHARGING":
            raise serializers.ValidationError(
                {
                    "status": get_prop_message(
                        "PROP-4.8.2-P02",
                        "Dữ liệu vị trí đỗ xe không hợp lệ, xin mời nhập lại.",
                    )
                }
            )

        if status_val == "OCCUPIED":
            raise serializers.ValidationError(
                {
                    "status": "Không thể chuyển vị trí sang trạng thái đang có xe khi không có phiên đỗ xe đang mở."
                }
            )

        return attrs


@extend_schema_serializer(
    examples=[],
)
class ParkingSlotUpdateSerializer(serializers.Serializer):
    """Serializer cập nhật thông tin ô đỗ xe (SRS 4.8.3). Bắt buộc row_version để kiểm soát OCC."""

    row_version = serializers.IntegerField(
        required=True,
        min_value=1,
        help_text="Phiên bản dòng hiện tại của ô đỗ trong client để kiểm tra xung đột đồng thời",
    )
    code = serializers.CharField(
        max_length=20,
        required=False,
        help_text="Mã ô đỗ xe mới",
    )
    slot_kind = serializers.ChoiceField(
        choices=ParkingSlot.KIND_CHOICES,
        required=False,
        help_text="Loại ô đỗ: 'STANDARD', 'PRIORITY', 'EV_CHARGING'",
    )
    status = serializers.ChoiceField(
        choices=ParkingSlot.STATUS_CHOICES,
        required=False,
        help_text="Trạng thái ô đỗ",
    )
    map_row = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        help_text="Tọa độ hàng",
    )
    map_col = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        help_text="Tọa độ cột",
    )
    width = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        help_text="Chiều rộng (m)",
    )
    length = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        help_text="Chiều dài (m)",
    )
    height = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        required=False,
        min_value=Decimal("0.01"),
        help_text="Chiều cao (m)",
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Ghi chú về ô đỗ",
    )
    allowed_vehicle_type_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        help_text="Danh sách ID loại xe được phép đỗ",
    )
    zone_id = serializers.IntegerField(
        required=False,
        help_text="ID khu vực mới nếu muốn chuyển khu",
    )

    def validate_code(self, value: str) -> str:
        clean = value.strip().upper()
        if not clean:
            raise serializers.ValidationError(
                get_prop_message(
                    "PROP-4.8.3-P02", "Dữ liệu cập nhật vị trí đỗ xe không hợp lệ."
                )
            )
        if not re.match(r"^[A-Za-z0-9 .\-]+$", clean):
            raise serializers.ValidationError(
                get_prop_message(
                    "PROP-4.8.3-P02", "Dữ liệu cập nhật vị trí đỗ xe không hợp lệ."
                )
            )
        return clean

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        map_row = attrs.get("map_row")
        map_col = attrs.get("map_col")
        if (map_row is None and map_col is not None) or (
            map_row is not None and map_col is None
        ):
            raise serializers.ValidationError(
                {
                    "map_coords": get_prop_message(
                        "PROP-4.8.3-P02", "Dữ liệu cập nhật vị trí đỗ xe không hợp lệ."
                    )
                }
            )
        return attrs


class SlotDeleteSuccessSerializer(serializers.Serializer):
    """Serializer phản hồi xóa mềm ô đỗ xe thành công (SRS 4.8.5)."""

    code = serializers.CharField(
        default="PROP-4.8.5-P01",
        help_text="Mã thông điệp thành công",
    )
    message = serializers.CharField(
        default="Xóa vị trí đỗ xe thành công.",
        help_text="Thông điệp mô tả kết quả thao tác",
    )


class SlotPaginatedResponseSerializer(serializers.Serializer):
    """Envelope phản hồi phân trang danh sách ô đỗ xe cho OpenAPI."""

    count = serializers.IntegerField(help_text="Tổng số ô đỗ thỏa mãn bộ lọc")
    total_pages = serializers.IntegerField(help_text="Tổng số trang")
    current_page = serializers.IntegerField(help_text="Trang hiện tại")
    page_size = serializers.IntegerField(help_text="Số phần tử trên trang")
    next = serializers.CharField(
        allow_null=True, help_text="Đường dẫn đến trang tiếp theo"
    )
    previous = serializers.CharField(
        allow_null=True, help_text="Đường dẫn đến trang trước đó"
    )
    results = SlotItemSerializer(many=True, help_text="Danh sách ô đỗ")
