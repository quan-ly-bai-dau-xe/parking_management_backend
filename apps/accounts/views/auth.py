"""
Authentication views for accounts app per SRS 4.1, ADR-0004, and TL-01.
"""

from __future__ import annotations

from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers.auth import (
    CSRFResponseSerializer,
    DetailResponseSerializer,
    LoginSerializer,
    UserResponseSerializer,
)
from apps.accounts.services.auth import (
    authenticate_account,
    login_account,
    logout_account,
)
from apps.accounts.services.throttling import LoginAttemptLimiter
from apps.core.exceptions import BusinessAPIException
from apps.core.messages import ALL_MESSAGES, get_prop_message
from apps.core.serializers.envelope import ErrorEnvelopeSerializer


class CSRFBootstrapView(APIView):
    """
    Public endpoint to ensure csrftoken cookie is issued and present.
    Essential for Single Page Application (SPA) CSRF handshake.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Khởi tạo CSRF cookie",
        description="Endpoint công khai khởi tạo và trả về cookie csrftoken phục vụ cơ chế bảo vệ CSRF hai lớp của SPA.",
        responses={
            200: OpenApiResponse(
                response=CSRFResponseSerializer,
                description="CSRF cookie đã được thiết lập thành công",
            )
        },
        auth=[],
        tags=["Authentication"],
    )
    def get(self, request: Request) -> Response:
        # Enforce evaluation and setting of csrftoken cookie
        get_token(request)
        return Response(
            {
                "detail": get_prop_message(
                    "PROP-4.1-P02", "Khởi tạo cookie CSRF thành công."
                )
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(sensitive_post_parameters("password"), name="dispatch")
class LoginView(APIView):
    """
    Endpoint xác thực đăng nhập qua Email/Số điện thoại và Mật khẩu.
    Thiết lập session cookie và cấp phát persistent token nếu người dùng chọn Ghi nhớ.
    """

    permission_classes = [AllowAny]
    limiter = LoginAttemptLimiter()

    @extend_schema(
        summary="Đăng nhập hệ thống",
        description="Xác thực thông tin tài khoản bằng Email hoặc Số điện thoại. "
        "Khi đăng nhập thành công, khởi tạo session cookie (HttpOnly, SameSite=Lax) "
        "và optional remember token bền 30 ngày nếu chọn ghi nhớ đăng nhập.",
        request=LoginSerializer,
        parameters=[
            OpenApiParameter(
                name="Retry-After",
                type=int,
                location=OpenApiParameter.HEADER,
                description="Số giây cần chờ trước khi thử đăng nhập lại khi bị giới hạn tần suất",
                response=[429],
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=UserResponseSerializer,
                description="Đăng nhập thành công, trả về thông tin tài khoản",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Thiếu hoặc để trống thông tin đăng nhập (MSG-4.1-M03)",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Thông tin đăng nhập không hợp lệ hoặc tài khoản bị khóa (MSG-4.1-M02)",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Mã CSRF không hợp lệ hoặc bị thiếu (PROP-4.1-P06)",
                examples=[
                    OpenApiExample(
                        "Lỗi CSRF Token (PROP-4.1-P06)",
                        value={
                            "code": "PROP-4.1-P06",
                            "message": ALL_MESSAGES["PROP-4.1-P06"],
                            "details": {},
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
            429: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Quá nhiều lần đăng nhập thất bại (PROP-4.1-P01)",
            ),
        },
        auth=[{"csrfAuth": []}],  # type: ignore[list-item]
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        identifier = data["identifier"]
        password = data["password"]
        remember = data.get("remember", False)

        # 1. ATOMIC RESERVE BEFORE PASSWORD VERIFICATION
        reservation = self.limiter.reserve_or_throttle(request, identifier)

        # 2. PASSWORD VERIFICATION (CPU-heavy Argon2/PBKDF2)
        try:
            account = authenticate_account(identifier, password)
        except BusinessAPIException:
            # Failed authentication: quota remains consumed per ADR-0004 and TL-53
            raise

        # 3. SUCCESSFUL AUTHENTICATION: RELEASE RESERVATION
        self.limiter.release_on_success(reservation)

        # Prepare payload and response
        user_payload = UserResponseSerializer(account).data
        response = Response(user_payload, status=status.HTTP_200_OK)

        # Initialize session, cycle key, update last_login, issue remember token
        login_account(request, account, remember=remember, response=response)

        return response


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    """
    Endpoint đăng xuất và hủy bỏ phiên làm việc của người dùng.
    Hủy session, thu hồi remember token và xóa sạch cookie xác thực.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Đăng xuất hệ thống",
        description="Hủy bỏ phiên làm việc Django session, thu hồi remember-me token tương ứng "
        "trong cơ sở dữ liệu và xóa cookies xác thực khỏi trình duyệt.",
        request=None,
        responses={
            200: OpenApiResponse(
                response=DetailResponseSerializer,
                description="Đăng xuất thành công",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Mã CSRF không hợp lệ hoặc bị thiếu (PROP-4.1-P06)",
                examples=[
                    OpenApiExample(
                        "Lỗi CSRF Token (PROP-4.1-P06)",
                        value={
                            "code": "PROP-4.1-P06",
                            "message": ALL_MESSAGES["PROP-4.1-P06"],
                            "details": {},
                        },
                        response_only=True,
                        status_codes=["403"],
                    )
                ],
            ),
        },
        auth=[{"csrfAuth": []}],  # type: ignore[list-item]
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        response = Response(
            {"detail": get_prop_message("PROP-4.1-P03", "Đăng xuất thành công.")},
            status=status.HTTP_200_OK,
        )
        logout_account(request, response=response)
        return response


class CurrentUserView(APIView):
    """
    Endpoint lấy thông tin tài khoản người dùng đang đăng nhập trong phiên làm việc.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Thông tin người dùng hiện tại",
        description="Truy vấn thông tin tài khoản đang xác thực (id, email, phone, role) "
        "từ phiên làm việc hiện tại.",
        responses={
            200: OpenApiResponse(
                response=UserResponseSerializer,
                description="Lấy thông tin tài khoản thành công",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Yêu cầu chưa được xác thực (MSG-4.1-M02)",
            ),
        },
        auth=[{"cookieAuth": []}],  # type: ignore[list-item]
        tags=["Authentication"],
    )
    def get(self, request: Request) -> Response:
        return Response(
            UserResponseSerializer(request.user).data,
            status=status.HTTP_200_OK,
        )
