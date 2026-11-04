"""
Authentication serializers for accounts app per SRS 4.1, ADR-0004, and TL-01.
"""

import re
from typing import Any, NoReturn

from drf_spectacular.utils import OpenApiExample, extend_schema_serializer
from rest_framework import serializers, status
from rest_framework.fields import empty

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_prop_message, get_srs_message


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


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Forgot Password Request",
            value={"email": "employee@parking.com"},
            request_only=True,
        )
    ]
)
class ForgotPasswordSerializer(serializers.Serializer):
    """Payload yêu cầu đặt lại mật khẩu per REQ-4.1-F04 và TL-52."""

    email = serializers.EmailField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        help_text="Địa chỉ email đã đăng ký của tài khoản cần đặt lại mật khẩu",
    )

    def validate_email(self, value: str) -> str:
        cleaned = value.strip().lower()
        if not cleaned:
            raise serializers.ValidationError("Email không được để trống.")
        return cleaned


@extend_schema_serializer(
    examples=[
        OpenApiExample(
            "Reset Password Confirm Request",
            value={
                "token": "dGhpcy1pcy1hLXNhbXBsZS10b2tlbg...",
                "new_password": "NewSecurePassword123!",
                "confirm_password": "NewSecurePassword123!",
            },
            request_only=True,
        )
    ]
)
class ResetPasswordConfirmSerializer(serializers.Serializer):
    """Payload xác nhận đặt lại mật khẩu per REQ-4.1-F04 và SRS 4.3.3."""

    token = serializers.CharField(
        required=True,
        allow_blank=False,
        trim_whitespace=True,
        help_text="Mã token đặt lại mật khẩu một lần nhận được qua email",
    )
    new_password = serializers.CharField(
        required=True,
        allow_blank=False,
        write_only=True,
        min_length=8,
        max_length=50,
        style={"input_type": "password"},
        help_text="Mật khẩu mới (8-50 ký tự, gồm chữ hoa, chữ thường, số và ký tự đặc biệt)",
    )
    confirm_password = serializers.CharField(
        required=True,
        allow_blank=False,
        write_only=True,
        min_length=8,
        max_length=50,
        style={"input_type": "password"},
        help_text="Nhập lại mật khẩu mới để xác nhận",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        new_pwd = attrs.get("new_password")
        confirm_pwd = attrs.get("confirm_password")

        errors: dict[str, list[str]] = {}

        if new_pwd != confirm_pwd:
            errors.setdefault("confirm_password", []).append(
                get_prop_message("PROP-4.1-P09", "Mật khẩu xác nhận không khớp.")
            )

        if new_pwd:
            special_characters = r"!@#$%^&*()_+-=[]{}|;:,.<>?"
            if len(new_pwd) < 8 or len(new_pwd) > 50:
                errors.setdefault("new_password", []).append(
                    "Mật khẩu phải có độ dài từ 8 đến 50 ký tự."
                )
            if not re.search(r"[a-z]", new_pwd):
                errors.setdefault("new_password", []).append(
                    "Mật khẩu phải chứa ít nhất 1 chữ cái viết thường."
                )
            if not re.search(r"[A-Z]", new_pwd):
                errors.setdefault("new_password", []).append(
                    "Mật khẩu phải chứa ít nhất 1 chữ cái viết hoa."
                )
            if not re.search(r"[0-9]", new_pwd):
                errors.setdefault("new_password", []).append(
                    "Mật khẩu phải chứa ít nhất 1 chữ số."
                )
            if not any(ch in special_characters for ch in new_pwd):
                errors.setdefault("new_password", []).append(
                    "Mật khẩu phải chứa ít nhất 1 ký tự đặc biệt."
                )

        if errors:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message=get_prop_message(
                    "PROP-GEN-P01", "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu"
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
                details=errors,
            )

        return attrs
