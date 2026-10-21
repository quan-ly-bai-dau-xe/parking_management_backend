"""
Plate scan serializers for parking app.
Provides request and response validation for POST /api/v1/parking/plate-scans/.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.parking.enums import ReviewReasonCode, ReviewStatus
from apps.parking.serializers.lookup import (
    OpenSessionSummarySerializer,
    VehicleLookupResponseSerializer,
)


@extend_schema_field(OpenApiTypes.BINARY)
class PlateScanImageField(serializers.FileField):
    """Trường file nhị phân cho ảnh upload quét biển số xe."""


class PlateScanRequestSerializer(serializers.Serializer):
    """Payload yêu cầu quét biển số xe từ hình ảnh."""

    image = PlateScanImageField(
        required=True,
        help_text="Tệp hình ảnh chứa biển số xe (định dạng JPEG, PNG, hoặc WebP, dung lượng tối đa 5MB)",
    )
    gate_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID cổng barrier nơi đặt camera quét biển số (tùy chọn)",
    )


class BoundingBoxSerializer(serializers.Serializer):
    """Tọa độ hộp bao biển số xe (pixel)."""

    x1 = serializers.IntegerField(help_text="Tọa độ góc trên bên trái trục X")
    y1 = serializers.IntegerField(help_text="Tọa độ góc trên bên trái trục Y")
    x2 = serializers.IntegerField(help_text="Tọa độ góc dưới bên phải trục X")
    y2 = serializers.IntegerField(help_text="Tọa độ góc dưới bên phải trục Y")


class PlateCorrectionItemSerializer(serializers.Serializer):
    """Chi tiết một ký tự được sửa đổi theo quy tắc ngữ cảnh vị trí (A3, H6)."""

    position = serializers.IntegerField(
        help_text="Chỉ số vị trí ký tự trong biển số xe (0-indexed, từ trái sang phải)"
    )
    original_char = serializers.CharField(
        max_length=1,
        help_text="Ký tự thô ban đầu do mô hình OCR nhận diện",
    )
    corrected_char = serializers.CharField(
        max_length=1,
        help_text="Ký tự đã được sửa đổi dựa trên cấu trúc vị trí bắt buộc",
    )
    rule = serializers.CharField(
        help_text="Tên quy tắc vị trí được áp dụng",
    )
    reason = serializers.CharField(
        required=False,
        default="",
        help_text="Lý do chi tiết áp dụng quy tắc sửa đổi",
    )
    locals()["from"] = serializers.CharField(
        source="original_char",
        required=False,
        help_text="Ký tự thô ban đầu (H6 contract: 'from')",
    )
    locals()["to"] = serializers.CharField(
        source="corrected_char",
        required=False,
        help_text="Ký tự đã được sửa đổi (H6 contract: 'to')",
    )


class PlateCandidateSerializer(serializers.Serializer):
    """Ứng viên biển số nhận dạng được."""

    plate_text = serializers.CharField(
        help_text="Ký tự biển số xe thô (vd: 51K-992.14)"
    )
    plate_normalized = serializers.CharField(
        help_text="Ký tự biển số đã chuẩn hóa (vd: 51K99214)"
    )
    confidence = serializers.FloatField(
        help_text="Độ tin cậy nhận dạng (0.00 - 100.00)"
    )
    char_confidences = serializers.ListField(
        child=serializers.FloatField(),
        required=False,
        allow_null=True,
        help_text="Danh sách độ tin cậy của từng ký tự trong biển số xe (thang điểm 0.00 - 100.00)",
    )
    min_char_confidence = serializers.FloatField(
        required=False,
        allow_null=True,
        help_text="Độ tin cậy của ký tự thấp nhất trong biển số xe (thang điểm 0.00 - 100.00)",
    )
    bounding_box = BoundingBoxSerializer(
        allow_null=True, required=False, help_text="Tọa độ hộp bao trên ảnh"
    )


class PlateScanResponseSerializer(serializers.Serializer):
    """Payload phản hồi kết quả quét nhận diện biển số xe (chuẩn hóa Milestone 3, H6)."""

    plate_raw = serializers.CharField(
        help_text="Ký tự biển số xe thô do mô hình OCR nhận diện trực tiếp"
    )
    plate_final = serializers.CharField(
        help_text="Ký tự biển số xe đề xuất sau khi áp dụng các quy tắc sửa đổi vị trí chuẩn"
    )
    candidates = PlateCandidateSerializer(
        many=True, help_text="Danh sách tất cả các ứng viên biển số phát hiện được"
    )
    best_candidate = PlateCandidateSerializer(
        allow_null=True,
        required=False,
        help_text="Ứng viên có độ tin cậy cao nhất (giữ nguyên để tương thích ngược, plate_normalized đồng bộ với plate_final)",
    )
    image_url = serializers.CharField(
        help_text="Đường dẫn truy cập tệp ảnh đã lưu an toàn trên máy chủ"
    )
    vehicle_lookup = VehicleLookupResponseSerializer(
        allow_null=True,
        required=False,
        help_text="Thông tin tra cứu phương tiện tự động tương ứng với plate_final (nếu có trong hệ thống)",
    )
    is_blacklisted = serializers.BooleanField(
        help_text="Cờ cảnh báo biển số thuộc danh sách đen (Blacklist)"
    )
    open_session = OpenSessionSummarySerializer(
        allow_null=True,
        required=False,
        help_text="Thông tin phiên đỗ xe đang mở chưa hoàn tất của biển số này (nếu có)",
    )
    engine_name = serializers.CharField(
        help_text="Tên engine OCR đã thực thi nhận dạng (vd: dual_ensemble)"
    )
    latency_ms = serializers.FloatField(
        help_text="Thời gian xử lý nhận dạng OCR (mili-giây)"
    )
    review_status = serializers.ChoiceField(
        choices=ReviewStatus.CHOICES,
        default=ReviewStatus.AUTO,
        help_text="Trạng thái duyệt nhận diện: 'AUTO' hoặc 'NEEDS_REVIEW'",
    )
    review_reasons = serializers.ListField(
        child=serializers.ChoiceField(choices=ReviewReasonCode.CHOICES),
        default=list,
        help_text="Danh sách lý do cần duyệt thủ công khi review_status là 'NEEDS_REVIEW'",
    )
    corrections = PlateCorrectionItemSerializer(
        many=True,
        default=list,
        help_text="Danh sách các sửa đổi ký tự dựa trên ngữ cảnh vị trí (Position-Aware Corrections) đã được áp dụng",
    )
    suggestions = serializers.ListField(
        child=serializers.CharField(),
        default=list,
        help_text="Danh sách tối đa 3 biển số xe gợi ý gần giống (edit distance <= 1) trong hệ thống xe đã đăng ký hoặc danh sách đen",
    )
