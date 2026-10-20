"""
Vehicle search serializers for parking app.
Provides request query validation, result serialization with currently_parked flag,
and paginated response envelope for OpenAPI documentation per SRS 4.5.1 and Task 9.
"""

from typing import Any

from rest_framework import serializers

from apps.parking.serializers.lookup import VehicleLookupResponseSerializer


class VehicleSearchItemSerializer(VehicleLookupResponseSerializer):
    """
    Serializer kết quả từng phương tiện trong Modal tìm xe.
    Kế thừa đầy đủ cấu trúc tra cứu xe và bổ sung cờ boolean currently_parked.
    """

    currently_parked = serializers.BooleanField(
        help_text="Cờ boolean xác định phương tiện hiện có đang đỗ trong bãi hay không (True nếu có phiên đỗ mở)"
    )


# Alias tương thích tài liệu đặc tả OpenAPI
VehicleSearchResultSerializer = VehicleSearchItemSerializer


class VehicleSearchListResponseSerializer(serializers.Serializer):
    """
    Envelope phản hồi danh sách phân trang chuẩn cho Modal tìm xe per Task 9.
    """

    count = serializers.IntegerField(
        help_text="Tổng số phương tiện tìm thấy khớp với điều kiện tìm kiếm"
    )
    total_pages = serializers.IntegerField(
        required=False, help_text="Tổng số trang kết quả"
    )
    current_page = serializers.IntegerField(
        required=False, help_text="Số thứ tự trang hiện tại"
    )
    page_size = serializers.IntegerField(
        required=False, help_text="Số lượng bản ghi trên một trang"
    )
    next = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Đường dẫn đến trang kết quả tiếp theo (null nếu là trang cuối)",
    )
    previous = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Đường dẫn đến trang kết quả trước đó (null nếu là trang đầu)",
    )
    results = VehicleSearchItemSerializer(
        many=True,
        help_text="Danh sách các phương tiện tìm thấy khớp điều kiện tìm kiếm",
    )
    message = serializers.CharField(
        allow_null=True,
        required=False,
        help_text="Thông điệp phản hồi (trả về 'Không tìm thấy dữ liệu trùng khớp' khi results rỗng)",
    )


# Alias tương thích OpenAPI schema generator
PaginatedVehicleSearchResponseSerializer = VehicleSearchListResponseSerializer


class VehicleSearchQuerySerializer(serializers.Serializer):
    """Serializer xác thực query parameters cho API tìm kiếm xe (Task 9)."""

    q = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Từ khóa tìm kiếm hợp nhất (khớp họ tên khách hàng, số điện thoại hoặc biển số xe)",
    )
    customer_name = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Tìm kiếm theo họ tên khách hàng (khớp ILIKE với chỉ mục Trigram GIN)",
    )
    phone = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Tìm kiếm theo số điện thoại khách hàng (hỗ trợ quy đổi đầu số +84 và 0)",
    )
    license_plate = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Tìm kiếm theo biển số xe (chuẩn hóa loại bỏ khoảng trắng, dấu gạch, dấu chấm)",
    )
    page = serializers.IntegerField(
        required=False,
        min_value=1,
        default=1,
        help_text="Số thứ tự trang cần xem (mặc định: 1)",
    )
    page_size = serializers.IntegerField(
        required=False,
        min_value=1,
        max_value=50,
        default=20,
        help_text="Số lượng bản ghi trên một trang (mặc định: 20, tối đa: 50)",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        search_fields = ["q", "customer_name", "phone", "license_plate"]
        has_search_term = False

        for field in search_fields:
            val = attrs.get(field)
            if val is not None:
                cleaned_val = str(val).strip()
                if cleaned_val:
                    if len(cleaned_val) < 2:
                        raise serializers.ValidationError(
                            {
                                field: "Từ khóa tìm kiếm phải có độ dài tối thiểu 2 ký tự sau khi loại bỏ khoảng trắng."
                            }
                        )
                    attrs[field] = cleaned_val
                    has_search_term = True
                else:
                    attrs[field] = None

        if not has_search_term:
            raise serializers.ValidationError(
                {
                    "non_field_errors": [
                        "Yêu cầu cung cấp ít nhất một tiêu chí tìm kiếm hợp lệ (q, customer_name, phone, license_plate)."
                    ]
                }
            )

        return attrs


class ErrorEnvelopeSerializer(serializers.Serializer):
    """Envelope phản hồi lỗi chuẩn của hệ thống per TL-47."""

    code = serializers.CharField(help_text="Mã định danh lỗi (MSG-... hoặc PROP-...)")
    message = serializers.CharField(
        help_text="Thông điệp mô tả lỗi chi tiết bằng tiếng Việt"
    )
    details = serializers.DictField(
        required=False,
        help_text="Chi tiết bổ sung các lỗi theo từng trường dữ liệu",
    )
