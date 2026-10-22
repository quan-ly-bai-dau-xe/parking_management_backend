"""
Authentication serializers for accounts app per SRS 4.1, ADR-0004, and TL-01.
"""

from typing import Any, NoReturn

from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers, status
from rest_framework.fields import empty

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_srs_message


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Login with Email",
            value={
                "identifier": "employee@parking.com",
                "password": "SecurePassword123!",
                "remember": True,
            },
            request_only=True,
        ),
        OpenApiExample(
            "Login with Phone",
            value={
                "identifier": "0912345678",
                "password": "SecurePassword123!",
                "remember": False,
            },
            request_only=True,
        ),
    ]
)
class LoginSerializer(serializers.Serializer):
    """
    Payload yêu cầu đăng nhập hệ thống (REQ-4.1-F01, F02, F03).
    Hỗ trợ định danh linh hoạt bằng email hoặc số điện thoại.
    """

    identifier = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        help_text="Email (không phân biệt hoa thường) hoặc Số điện thoại (9-15 chữ số)",
    )
    password = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=False,
        write_only=True,
        style={"input_type": "password"},
        help_text="Mật khẩu đăng nhập",
    )
    remember = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Ghi nhớ đăng nhập (phát hành token bền 30 ngày theo ADR-0004)",
    )

    def run_validation(self, data: Any = empty) -> dict[str, Any]:
        """
        Validate input format, raising uniform MSG-4.1-M03 on empty,
        missing, or invalid type payloads per TL-52 and SRS 4.1.
        """

        def _raise_missing(exc: Exception | None = None) -> NoReturn:
            raise BusinessAPIException(
                code="MSG-4.1-M03",
                message=get_srs_message(
                    "MSG-4.1-M03",
                    "Xin nhập đầy đủ Tên đăng nhập và Mật khẩu",
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            ) from exc

        if data is empty or not isinstance(data, dict):
            _raise_missing()

        raw_identifier = data.get("identifier")
        raw_password = data.get("password")

        # Explicit check for missing, non-string, empty string, or whitespace-only
        if (
            raw_identifier is None
            or not isinstance(raw_identifier, str)
            or not raw_identifier.strip()
            or raw_password is None
            or not isinstance(raw_password, str)
            or not raw_password.strip()
        ):
            _raise_missing()

        try:
            validated: dict[str, Any] = super().run_validation(data)
        except serializers.ValidationError as exc:
            # Map serializer validation failure directly to MSG-4.1-M03
            _raise_missing(exc)

        return validated


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "User Profile Response",
            value={
                "id": 1,
                "email": "employee@parking.com",
                "phone": "0912345678",
                "role": "EMPLOYEE",
            },
            response_only=True,
        )
    ]
)
class UserResponseSerializer(serializers.Serializer):
    """Payload phản hồi thông tin tài khoản người dùng per TL-52 và SRS 4.1."""

    id = serializers.IntegerField(
        help_text="ID định danh tài khoản",
        read_only=True,
    )
    email = serializers.CharField(
        allow_null=True,
        help_text="Địa chỉ email đã đăng ký",
        read_only=True,
    )
    phone = serializers.CharField(
        allow_null=True,
        help_text="Số điện thoại đã đăng ký",
        read_only=True,
    )
    role = serializers.CharField(
        help_text="Vai trò hệ thống (MANAGER, EMPLOYEE, CUSTOMER)",
        read_only=True,
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "CSRF Response",
            value={"detail": "CSRF cookie set"},
            response_only=True,
        )
    ]
)
class CSRFResponseSerializer(serializers.Serializer):
    """Payload phản hồi xác nhận khởi tạo CSRF cookie per TL-52 và ADR-0004."""

    detail = serializers.CharField(
        help_text="Thông báo xác nhận CSRF cookie đã được thiết lập"
    )


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Detail Response",
            value={"detail": "Successfully logged out"},
            response_only=True,
        )
    ]
)
class DetailResponseSerializer(serializers.Serializer):
    """Payload phản hồi thông điệp chi tiết thao tác per TL-52 và SRS 4.1."""

    detail = serializers.CharField(help_text="Thông báo kết quả thao tác")
