"""
Vehicle lookup serializers for parking app.
Provides response serialization for exact normalized-plate lookup per SRS 4.5.1.
"""

from rest_framework import serializers


class VehicleDetailSerializer(serializers.Serializer):
    """Thông tin chi tiết phương tiện."""

    id = serializers.IntegerField(help_text="ID phương tiện")
    code = serializers.CharField(help_text="Mã định danh phương tiện (vd: XE0001)")
    license_plate = serializers.CharField(help_text="Biển số xe gốc (vd: 51K-992.14)")
    license_plate_norm = serializers.CharField(
        help_text="Biển số xe đã chuẩn hóa (vd: 51K99214)"
    )
    model_name = serializers.CharField(help_text="Tên dòng xe (vd: Camry 2.5Q)")
    brand = serializers.CharField(
        allow_null=True, required=False, help_text="Hãng xe (vd: Toyota)"
    )
    color = serializers.CharField(
        allow_null=True, required=False, help_text="Màu sắc (vd: Đen)"
    )
    vehicle_type = serializers.CharField(help_text="Tên loại phương tiện (vd: Ô tô)")
    vehicle_type_code = serializers.CharField(help_text="Mã loại phương tiện (vd: CAR)")


class CustomerDetailSerializer(serializers.Serializer):
    """Thông tin khách hàng sở hữu phương tiện."""

    id = serializers.IntegerField(help_text="ID khách hàng")
    code = serializers.CharField(help_text="Mã định danh khách hàng (vd: KH0001)")
    full_name = serializers.CharField(help_text="Họ và tên khách hàng")
    phone = serializers.CharField(
        allow_null=True, required=False, help_text="Số điện thoại liên hệ"
    )
    is_anonymized = serializers.BooleanField(
        help_text="Cờ bảo vệ dữ liệu cá nhân theo Nghị định 13/2023/NĐ-CP"
    )


class ParkingPositionSerializer(serializers.Serializer):
    """Thông tin vị trí đỗ xe trong bãi."""

    slot_id = serializers.IntegerField(help_text="ID vị trí đỗ")
    slot_code = serializers.CharField(help_text="Mã vị trí đỗ (vd: A-01)")
    zone_code = serializers.CharField(help_text="Mã khu vực (vd: A)")
    floor_code = serializers.CharField(help_text="Mã tầng (vd: B1)")
    floor_name = serializers.CharField(help_text="Tên tầng (vd: Tầng B1)")
    display_text = serializers.CharField(
        help_text="Chuỗi định dạng vị trí thân thiện (vd: Tầng B1 - Zone A - A-01)"
    )


class ActiveTicketSummarySerializer(serializers.Serializer):
    """Thông tin vé đỗ xe đang còn hiệu lực."""

    id = serializers.IntegerField(help_text="ID vé đỗ xe")
    code = serializers.CharField(help_text="Mã vé đỗ xe (vd: VT0001)")
    ticket_type_name = serializers.CharField(help_text="Loại vé (vd: Vé tháng)")
    price = serializers.CharField(help_text="Mức giá vé (VND)")
    effective_from = serializers.CharField(
        help_text="Thời điểm bắt đầu có hiệu lực (ISO 8601)"
    )
    effective_to = serializers.CharField(help_text="Thời điểm hết hiệu lực (ISO 8601)")
    status = serializers.CharField(help_text="Trạng thái vé (vd: ACTIVE)")


class OpenSessionSummarySerializer(serializers.Serializer):
    """Thông tin phiên đỗ xe đang mở (chưa ra khỏi bãi)."""

    id = serializers.IntegerField(help_text="ID phiên đỗ xe")
    session_code = serializers.CharField(
        help_text="Mã phiên đỗ xe (vd: #PK-20261018-001)"
    )
    entry_time = serializers.CharField(help_text="Thời gian vào bãi (ISO 8601)")
    entry_gate_name = serializers.CharField(
        allow_null=True, required=False, help_text="Tên cổng vào"
    )
    entry_image_url = serializers.CharField(
        allow_null=True, required=False, help_text="Đường dẫn ảnh chụp lúc vào"
    )
    recognition_source = serializers.CharField(
        help_text="Nguồn nhận diện (AI / MANUAL)"
    )
    ai_confidence = serializers.FloatField(
        allow_null=True, required=False, help_text="Độ tin cậy AI (0 - 100)"
    )
    review_status = serializers.CharField(
        help_text="Trạng thái duyệt (AUTO / NEEDS_REVIEW)"
    )


class VehicleLookupResponseSerializer(serializers.Serializer):
    """Payload phản hồi tra cứu thông tin xe."""

    vehicle = VehicleDetailSerializer(help_text="Chi tiết phương tiện")
    customer = CustomerDetailSerializer(help_text="Chi tiết chủ phương tiện")
    parking_position = ParkingPositionSerializer(
        allow_null=True, required=False, help_text="Vị trí đỗ hiện tại hoặc theo vé"
    )
    active_ticket = ActiveTicketSummarySerializer(
        allow_null=True, required=False, help_text="Vé đỗ xe đang có hiệu lực"
    )
    open_session = OpenSessionSummarySerializer(
        allow_null=True,
        required=False,
        help_text="Phiên đỗ xe đang mở (nếu đang đỗ trong bãi)",
    )
    is_blacklisted = serializers.BooleanField(
        help_text="Cờ cảnh báo danh sách đen (Blacklist)"
    )
