"""
Standard error envelope serializer per TL-47 and SRS 4.5.1.
Enables drf-spectacular to render error response schemas and verbatim examples.
"""

from rest_framework import serializers


class ErrorEnvelopeSerializer(serializers.Serializer):
    """Envelope phản hồi lỗi chuẩn của hệ thống per TL-47."""

    code = serializers.CharField(
        help_text="Mã định danh lỗi chuẩn của hệ thống (MSG-... hoặc PROP-...)"
    )
    message = serializers.CharField(
        help_text="Thông điệp mô tả lỗi chi tiết bằng tiếng Việt"
    )
    details = serializers.DictField(
        required=False,
        help_text="Chi tiết bổ sung các lỗi theo từng trường dữ liệu hoặc cờ nghiệp vụ",
    )
