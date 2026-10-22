"""
Session serializers for parking app per TL-05, TL-50, and SRS 4.5.1.
Provides request and response validation for check-in, check-out, and session listings.
"""

from decimal import Decimal
from typing import Any

from rest_framework import serializers
from rest_framework.fields import empty

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import ALL_MESSAGES
from apps.parking.models import VehicleEntryExitLog
from apps.parking.selectors.sessions import calculate_session_duration
from apps.parking.serializers.lookup import VehicleLookupResponseSerializer
from apps.parking.services.upload import validate_parking_image_path
from apps.tickets.models import Payment


class ParkingImageRelativeUrlField(serializers.CharField):
    """
    Serializer Field chuyên dụng cho entry_image_url và exit_image_url per F3.
    Chỉ chấp nhận null/omitted hoặc đường dẫn tương đối đúng chuẩn trỏ tới file có thật.
    Mọi giá trị khác bị từ chối với HTTP 400 PROP-4.5.1-P13.
    """

    DEFAULT_MAX_LENGTH = 150

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", self.DEFAULT_MAX_LENGTH)
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_null", True)
        kwargs.setdefault("allow_blank", False)
        super().__init__(**kwargs)

    def run_validation(self, data=empty):
        if data is empty or data is None:
            return None
        if not isinstance(data, str):
            raise BusinessAPIException(
                code="PROP-4.5.1-P13",
                message=ALL_MESSAGES.get(
                    "PROP-4.5.1-P13",
                    "Đường dẫn hình ảnh không hợp lệ hoặc tệp không tồn tại.",
                ),
                status_code=400,
            )
        return validate_parking_image_path(data)


class CheckInRequestSerializer(serializers.Serializer):
    """Payload yêu cầu check-in phương tiện vào bãi."""

    license_plate = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Biển số xe nhận dạng được hoặc nhập tay (vd: 51K-992.14)",
    )
    entry_gate_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID cổng vào (bắt buộc phải có direction='IN')",
    )
    slot_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID vị trí đỗ xe dự kiến gán (tùy chọn, mặc định lấy vị trí của vé active nếu có)",
    )
    recognition_source = serializers.ChoiceField(
        choices=VehicleEntryExitLog.RECOGNITION_SOURCE_CHOICES,
        default="AI",
        help_text="Nguồn thu thập biển số (AI: tự động từ camera, MANUAL: nhân viên nhập tay)",
    )
    ai_confidence = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        min_value=Decimal("0.00"),
        max_value=Decimal("100.00"),
        required=False,
        allow_null=True,
        help_text="Độ tin cậy nhận dạng từ OCR AI (0.00 - 100.00)",
    )
    entry_image_url = ParkingImageRelativeUrlField(
        help_text="Đường dẫn ảnh chụp lúc vào bãi",
    )
    override_blacklist = serializers.BooleanField(
        default=False,
        help_text="Cờ ghi đè cho phép xe thuộc danh sách đen vào bãi (chỉ có hiệu lực khi người dùng là Quản lý/MANAGER)",
    )
    notes = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Ghi chú thêm về lượt xe vào",
    )


class SessionDetailSerializer(serializers.ModelSerializer):
    """Serializer chi tiết đầy đủ của một phiên đỗ xe."""

    entry_gate_name = serializers.SerializerMethodField(help_text="Tên cổng vào")
    exit_gate_name = serializers.SerializerMethodField(help_text="Tên cổng ra")
    entry_handled_by_name = serializers.SerializerMethodField(
        help_text="Họ tên nhân viên phụ trách cổng vào"
    )
    exit_handled_by_name = serializers.SerializerMethodField(
        help_text="Họ tên nhân viên phụ trách cổng ra"
    )
    duration_seconds = serializers.SerializerMethodField(
        help_text="Tổng thời gian đỗ xe tính bằng giây"
    )
    duration_text = serializers.SerializerMethodField(
        help_text="Chuỗi thời gian đỗ hiển thị thân thiện tiếng Việt"
    )
    slot_display = serializers.SerializerMethodField(
        help_text="Mã hoặc vị trí đỗ hiển thị"
    )

    class Meta:
        model = VehicleEntryExitLog
        fields = [
            "id",
            "session_code",
            "vehicle_id",
            "slot_id",
            "slot_display",
            "ticket_id",
            "entry_gate_id",
            "entry_gate_name",
            "exit_gate_id",
            "exit_gate_name",
            "license_plate",
            "license_plate_norm",
            "ai_confidence",
            "recognition_source",
            "review_status",
            "fee_amount",
            "entry_time",
            "exit_time",
            "duration_seconds",
            "duration_text",
            "entry_image_url",
            "exit_image_url",
            "entry_handled_by",
            "entry_handled_by_name",
            "exit_handled_by",
            "exit_handled_by_name",
            "notes",
            "created_at",
        ]

    def get_entry_gate_name(self, obj: VehicleEntryExitLog) -> str | None:
        return obj.entry_gate.name if obj.entry_gate else None

    def get_exit_gate_name(self, obj: VehicleEntryExitLog) -> str | None:
        return obj.exit_gate.name if obj.exit_gate else None

    def get_entry_handled_by_name(self, obj: VehicleEntryExitLog) -> str | None:
        return obj.entry_handled_by.full_name if obj.entry_handled_by else None

    def get_exit_handled_by_name(self, obj: VehicleEntryExitLog) -> str | None:
        return obj.exit_handled_by.full_name if obj.exit_handled_by else None

    def get_duration_seconds(self, obj: VehicleEntryExitLog) -> int:
        seconds, _ = calculate_session_duration(obj)
        return seconds

    def get_duration_text(self, obj: VehicleEntryExitLog) -> str:
        _, text = calculate_session_duration(obj)
        return text

    def get_slot_display(self, obj: VehicleEntryExitLog) -> str | None:
        if obj.slot:
            return f"{obj.slot.zone.floor.name} - Zone {obj.slot.zone.code} - {obj.slot.code}"
        return None


class CheckInResponseSerializer(serializers.Serializer):
    """Payload phản hồi kết quả check-in thành công."""

    session = SessionDetailSerializer(help_text="Thông tin phiên đỗ xe vừa khởi tạo")
    vehicle_lookup = VehicleLookupResponseSerializer(
        allow_null=True,
        required=False,
        help_text="Thông tin tra cứu phương tiện và khách hàng liên kết",
    )


class CheckOutRequestSerializer(serializers.Serializer):
    """Payload yêu cầu check-out kết thúc phiên đỗ xe."""

    license_plate = serializers.CharField(
        max_length=20,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Biển số xe cần check-out (cung cấp chính xác 1 trong 2: biển số HOẶC mã phiên)",
    )
    session_code = serializers.CharField(
        max_length=30,
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Mã phiên đỗ xe cần check-out (cung cấp chính xác 1 trong 2: biển số HOẶC mã phiên)",
    )
    exit_gate_id = serializers.IntegerField(
        required=True,
        help_text="ID cổng ra (bắt buộc phải có direction='OUT')",
    )
    payment_method = serializers.ChoiceField(
        choices=["CASH", "VIETQR"],
        required=False,
        allow_null=True,
        help_text="Phương thức thanh toán cước phí (bắt buộc khi fee_amount > 0: 'CASH' hoặc 'VIETQR')",
    )
    exit_image_url = ParkingImageRelativeUrlField(
        help_text="Đường dẫn ảnh chụp lúc ra khỏi bãi",
    )
    notes = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        help_text="Ghi chú thêm về phiên ra",
    )


class PaymentSummarySerializer(serializers.ModelSerializer):
    """Thông tin hóa đơn thanh toán cước phí đỗ xe."""

    class Meta:
        model = Payment
        fields = [
            "id",
            "code",
            "amount",
            "method",
            "status",
            "paid_at",
        ]


class CheckOutResponseSerializer(serializers.Serializer):
    """Payload phản hồi kết quả check-out thành công."""

    session = SessionDetailSerializer(help_text="Thông tin phiên đỗ xe đã đóng")
    payment = PaymentSummarySerializer(
        allow_null=True,
        required=False,
        help_text="Hóa đơn thanh toán cước phí (tạo tự động nếu fee_amount > 0)",
    )
    vehicle_lookup = VehicleLookupResponseSerializer(
        allow_null=True,
        required=False,
        help_text="Thông tin phương tiện và chủ xe cập nhật",
    )


class SessionListItemSerializer(serializers.ModelSerializer):
    """Serializer rút gọn cho danh sách lịch sử ra/vào (tránh N+1 queries)."""

    entry_gate_name = serializers.SerializerMethodField(help_text="Tên cổng vào")
    exit_gate_name = serializers.SerializerMethodField(help_text="Tên cổng ra")
    duration_seconds = serializers.SerializerMethodField(
        help_text="Thời lượng đỗ (giây)"
    )
    duration_text = serializers.SerializerMethodField(
        help_text="Thời lượng đỗ (chuỗi hiển thị)"
    )
    vehicle_model = serializers.SerializerMethodField(help_text="Dòng xe")
    vehicle_brand = serializers.SerializerMethodField(help_text="Hãng xe")
    customer_name = serializers.SerializerMethodField(
        help_text="Họ tên chủ xe (đã ẩn danh nếu cần)"
    )
    customer_phone = serializers.SerializerMethodField(
        help_text="Số điện thoại chủ xe (đã ẩn danh nếu cần)"
    )
    slot_code = serializers.SerializerMethodField(help_text="Mã vị trí đỗ")

    class Meta:
        model = VehicleEntryExitLog
        fields = [
            "id",
            "session_code",
            "license_plate",
            "license_plate_norm",
            "entry_time",
            "exit_time",
            "duration_seconds",
            "duration_text",
            "fee_amount",
            "entry_image_url",
            "exit_image_url",
            "entry_gate_name",
            "exit_gate_name",
            "ai_confidence",
            "recognition_source",
            "review_status",
            "vehicle_model",
            "vehicle_brand",
            "customer_name",
            "customer_phone",
            "slot_code",
        ]

    def get_entry_gate_name(self, obj: VehicleEntryExitLog) -> str | None:
        return obj.entry_gate.name if obj.entry_gate else None

    def get_exit_gate_name(self, obj: VehicleEntryExitLog) -> str | None:
        return obj.exit_gate.name if obj.exit_gate else None

    def get_duration_seconds(self, obj: VehicleEntryExitLog) -> int:
        seconds, _ = calculate_session_duration(obj)
        return seconds

    def get_duration_text(self, obj: VehicleEntryExitLog) -> str:
        _, text = calculate_session_duration(obj)
        return text

    def get_vehicle_model(self, obj: VehicleEntryExitLog) -> str | None:
        return obj.vehicle.model_name if obj.vehicle else None

    def get_vehicle_brand(self, obj: VehicleEntryExitLog) -> str | None:
        return obj.vehicle.brand if obj.vehicle else None

    def get_customer_name(self, obj: VehicleEntryExitLog) -> str | None:
        if obj.vehicle and obj.vehicle.customer:
            cust = obj.vehicle.customer
            return "Khách hàng ẩn danh" if cust.is_anonymized else cust.full_name
        return None

    def get_customer_phone(self, obj: VehicleEntryExitLog) -> str | None:
        if obj.vehicle and obj.vehicle.customer:
            cust = obj.vehicle.customer
            return None if cust.is_anonymized else cust.phone
        return None

    def get_slot_code(self, obj: VehicleEntryExitLog) -> str | None:
        return obj.slot.code if obj.slot else None


class ParkingSessionFilterSerializer(serializers.Serializer):
    """
    Serializer xác thực các tham số truy vấn (query parameters) cho API danh sách phiên đỗ xe:
    GET /api/v1/parking/sessions/ per TL-05, TL-50, and SRS 4.5.1.
    """

    session_code = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=50,
        error_messages={
            "max_length": "Mã phiên đỗ xe không được vượt quá 50 ký tự.",
        },
    )
    license_plate = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=20,
        error_messages={
            "max_length": "Biển số xe tìm kiếm không được vượt quá 20 ký tự.",
        },
    )
    entry_time_from = serializers.DateTimeField(
        required=False,
        error_messages={
            "invalid": "Thời gian vào từ không đúng định dạng ngày giờ hợp lệ.",
        },
    )
    entry_time_to = serializers.DateTimeField(
        required=False,
        error_messages={
            "invalid": "Thời gian vào đến không đúng định dạng ngày giờ hợp lệ.",
        },
    )
    exit_time_from = serializers.DateTimeField(
        required=False,
        error_messages={
            "invalid": "Thời gian ra từ không đúng định dạng ngày giờ hợp lệ.",
        },
    )
    exit_time_to = serializers.DateTimeField(
        required=False,
        error_messages={
            "invalid": "Thời gian ra đến không đúng định dạng ngày giờ hợp lệ.",
        },
    )
    status = serializers.ChoiceField(
        choices=["open", "closed"],
        required=False,
        error_messages={
            "invalid_choice": "Trạng thái phiên đỗ xe phải là 'open' (đang đỗ) hoặc 'closed' (đã rời bãi).",
        },
    )
    review_status = serializers.ChoiceField(
        choices=VehicleEntryExitLog.ReviewStatus.values,
        required=False,
        error_messages={
            "invalid_choice": (
                "Trạng thái kiểm duyệt không hợp lệ. "
                "Các giá trị hợp lệ: AUTO, MATCHED, NEEDS_REVIEW, APPROVED, REJECTED."
            ),
        },
    )
    min_fee = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        error_messages={
            "invalid": "Mức cước phí tối thiểu không đúng định dạng số hợp lệ.",
            "min_value": "Mức cước phí tối thiểu không được nhỏ hơn 0.",
            "max_digits": "Mức cước phí tối thiểu vượt quá giới hạn chữ số cho phép.",
        },
    )
    max_fee = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        error_messages={
            "invalid": "Mức cước phí tối đa không đúng định dạng số hợp lệ.",
            "min_value": "Mức cước phí tối đa không được nhỏ hơn 0.",
            "max_digits": "Mức cước phí tối đa vượt quá giới hạn chữ số cho phép.",
        },
    )
    page = serializers.IntegerField(
        min_value=1,
        required=False,
        default=1,
        error_messages={
            "invalid": "Số trang phải là một số nguyên hợp lệ.",
            "min_value": "Số trang phải lớn hơn hoặc bằng 1.",
        },
    )
    page_size = serializers.IntegerField(
        min_value=1,
        max_value=100,
        required=False,
        default=20,
        error_messages={
            "invalid": "Kích thước trang phải là một số nguyên hợp lệ.",
            "min_value": "Kích thước trang phải từ 1 đến 100 bản ghi.",
            "max_value": "Kích thước trang không được vượt quá 100 bản ghi.",
        },
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Xác thực ràng buộc giữa các trường (cross-field validation)."""
        errors: dict[str, list[str]] = {}

        entry_from = attrs.get("entry_time_from")
        entry_to = attrs.get("entry_time_to")
        if entry_from and entry_to and entry_from > entry_to:
            errors.setdefault("entry_time_from", []).append(
                "Thời gian vào bắt đầu không được lớn hơn thời gian vào kết thúc."
            )

        exit_from = attrs.get("exit_time_from")
        exit_to = attrs.get("exit_time_to")
        if exit_from and exit_to and exit_from > exit_to:
            errors.setdefault("exit_time_from", []).append(
                "Thời gian ra bắt đầu không được lớn hơn thời gian ra kết thúc."
            )

        min_fee = attrs.get("min_fee")
        max_fee = attrs.get("max_fee")
        if min_fee is not None and max_fee is not None and min_fee > max_fee:
            errors.setdefault("min_fee", []).append(
                "Mức cước phí tối thiểu không được lớn hơn mức cước phí tối đa."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs
