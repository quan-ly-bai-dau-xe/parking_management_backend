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
    ForgotPasswordSerializer,
    LoginSerializer,
    ResetPasswordConfirmSerializer,
    UserResponseSerializer,
)
from apps.accounts.services.auth import (
    authenticate_account,
    confirm_password_reset,
    login_account,
    logout_account,
    request_password_reset,
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


@method_decorator(csrf_protect, name="dispatch")
class ForgotPasswordView(APIView):
    """
    Endpoint yêu cầu đặt lại mật khẩu qua email per REQ-4.1-F04, OQ-84, TL-36.
    Phát hành token một lần gửi qua email kèm cơ chế rate limit và anti-enumeration.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Yêu cầu đặt lại mật khẩu",
        description="Gửi email chứa mã token đặt lại mật khẩu đến địa chỉ email đã đăng ký. "
        "Áp dụng cơ chế anti-enumeration (luôn trả về 200 bất kể email có tồn tại hay không) "
        "và giới hạn tần suất 3 yêu cầu/giờ theo email, 10 yêu cầu/giờ theo IP per OQ-84.",
        request=ForgotPasswordSerializer,
        parameters=[
            OpenApiParameter(
                name="Retry-After",
                type=int,
                location=OpenApiParameter.HEADER,
                description="Số giây cần chờ trước khi gửi lại yêu cầu khi bị giới hạn tần suất",
                response=[429],
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=DetailResponseSerializer,
                description="Yêu cầu đã được tiếp nhận thành công",
                examples=[
                    OpenApiExample(
                        "Success Response",
                        value={
                            "detail": get_prop_message(
                                "PROP-4.1-P04",
                                "Nếu email tồn tại trong hệ thống, hướng dẫn đặt lại mật khẩu đã được gửi.",
                            )
                        },
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Định dạng email không hợp lệ hoặc để trống",
            ),
            429: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Vượt quá giới hạn tần suất yêu cầu đặt lại mật khẩu (OQ-84)",
            ),
        },
        auth=[],
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        request_password_reset(request, email)

        return Response(
            {
                "detail": get_prop_message(
                    "PROP-4.1-P04",
                    "Nếu email tồn tại trong hệ thống, hướng dẫn đặt lại mật khẩu đã được gửi.",
                )
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_protect, name="dispatch")
@method_decorator(
    sensitive_post_parameters("new_password", "confirm_password"), name="dispatch"
)
class ResetPasswordConfirmView(APIView):
    """
    Endpoint xác nhận đặt lại mật khẩu bằng token một lần per REQ-4.1-F04 và TL-36.
    Kiểm tra tính hợp lệ của token, cập nhật mật khẩu băm Argon2 và thu hồi remember tokens.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Xác nhận đặt lại mật khẩu",
        description="Xác thực mã token một lần và thiết lập mật khẩu mới cho tài khoản. "
        "Mật khẩu mới phải tuân thủ chính sách mật khẩu (8-50 ký tự, gồm chữ hoa, chữ thường, "
        "chữ số và ký tự đặc biệt). Sau khi đặt lại thành công, mọi phiên ghi nhớ đăng nhập cũ sẽ bị thu hồi.",
        request=ResetPasswordConfirmSerializer,
        responses={
            200: OpenApiResponse(
                response=DetailResponseSerializer,
                description="Mật khẩu đã được đặt lại thành công",
                examples=[
                    OpenApiExample(
                        "Success Response",
                        value={
                            "detail": get_prop_message(
                                "PROP-4.1-P05",
                                "Đặt lại mật khẩu thành công. Vui lòng đăng nhập bằng mật khẩu mới.",
                            )
                        },
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Token không hợp lệ/hết hạn hoặc mật khẩu không tuân thủ chính sách độ phức tạp",
            ),
        },
        auth=[],
        tags=["Authentication"],
    )
    def post(self, request: Request) -> Response:
        serializer = ResetPasswordConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data["token"]
        new_password = serializer.validated_data["new_password"]

        confirm_password_reset(token, new_password)

        return Response(
            {
                "detail": get_prop_message(
                    "PROP-4.1-P05",
                    "Đặt lại mật khẩu thành công. Vui lòng đăng nhập bằng mật khẩu mới.",
                )
            },
            status=status.HTTP_200_OK,
        )
