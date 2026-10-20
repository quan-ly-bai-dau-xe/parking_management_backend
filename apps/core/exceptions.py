"""
Custom exception handler for Parking Management Backend per TL-47.
Standardizes all API error responses into the envelope format:
{
    "code": "MSG-...",
    "message": "...",
    "details": {}
}
"""

import logging
import re
from typing import Any

from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.db import DatabaseError, IntegrityError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    NotFound,
    ValidationError,
)
from rest_framework.exceptions import (
    PermissionDenied as DRFPermissionDenied,
)
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from apps.core.messages import ALL_MESSAGES

logger = logging.getLogger(__name__)

# SQLSTATE Mappings per TL-47
SQLSTATE_MAP: dict[str, dict[str, Any]] = {
    "23514": {
        "status": status.HTTP_400_BAD_REQUEST,
        "default_code": "PROP-GEN-P01",
        "default_message": "Dữ liệu vi phạm ràng buộc kiểm tra hợp lệ.",
    },
    "55000": {
        "status": status.HTTP_409_CONFLICT,
        "default_code": "PROP-DEL-SAVT-IN-USE",
        "default_message": "Dữ liệu đang được sử dụng hoặc không ở trạng thái hợp lệ để thao tác.",
    },
    "23503": {
        "status": status.HTTP_409_CONFLICT,
        "default_code": "MSG-4.3.1-M03",
        "default_message": "Dữ liệu tham chiếu không tồn tại hoặc đang có liên kết ràng buộc không thể xóa/sửa.",
    },
    "23505": {
        "status": status.HTTP_409_CONFLICT,
        "default_code": "MSG-4.3.1-M05",
        "default_message": "Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
    },
    "22023": {
        "status": status.HTTP_400_BAD_REQUEST,
        "default_code": "PROP-GEN-P01",
        "default_message": "Tham số dữ liệu truyền vào không hợp lệ.",
    },
}


def _extract_sqlstate_and_message(exc: Exception) -> tuple[str | None, str | None]:
    """Trích xuất mã lỗi SQLSTATE và thông điệp lỗi gốc từ ngoại lệ CSDL."""
    cause = getattr(exc, "__cause__", None) or exc
    sqlstate = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)

    # Trích xuất thông báo từ đối tượng chẩn đoán psycopg (nếu có)
    diag = getattr(cause, "diag", None)
    primary_msg = None
    if diag:
        primary_msg = getattr(diag, "message_primary", None) or getattr(
            diag, "message_detail", None
        )

    # Nếu chưa có thông điệp, đọc từ chuỗi biểu diễn ngoại lệ
    cause_str = str(cause)
    if not primary_msg:
        # Lọc bỏ các tiền tố không cần thiết nếu có
        clean_msg = cause_str.split("\n")[0]
        if clean_msg:
            primary_msg = clean_msg

    # Tìm kiếm fallback sqlstate bằng regex nếu chưa nhận diện được
    if not sqlstate:
        match = re.search(r"\b(23514|55000|23503|23505|22023)\b", cause_str)
        if match:
            sqlstate = match.group(1)

    return (str(sqlstate) if sqlstate else None, primary_msg)


def custom_exception_handler(exc: Exception, context: Any) -> Response | None:
    """
    Xử lý ngoại lệ toàn cục cho REST Framework.
    Map các lỗi CSDL (SQLSTATE) và DRF exceptions sang envelope chuẩn:
    {
        "code": "MSG-...",
        "message": "...",
        "details": {}
    }
    """
    # 1. Gọi handler mặc định của DRF
    response = drf_exception_handler(exc, context)

    # 2. Xử lý trường hợp DRF đã nhận diện (HTTP 4xx thông thường)
    if response is not None:
        envelope: dict[str, Any] = {
            "code": "MSG-4.2-M01",
            "message": "Đã xảy ra lỗi khi xử lý yêu cầu.",
            "details": response.data
            if isinstance(response.data, dict)
            else {"error": response.data},
        }

        if isinstance(exc, ValidationError):
            envelope["code"] = "PROP-GEN-P01"
            envelope["message"] = ALL_MESSAGES.get(
                "PROP-GEN-P01", "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu"
            )
        elif isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
            envelope["code"] = "MSG-4.1-M02"
            envelope["message"] = ALL_MESSAGES.get(
                "MSG-4.1-M02", "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu"
            )
            response.status_code = status.HTTP_401_UNAUTHORIZED
        elif isinstance(exc, (DRFPermissionDenied, DjangoPermissionDenied)):
            envelope["code"] = "MSG-4.2-M01"
            envelope["message"] = "Bạn không có quyền thực hiện thao tác này."
        elif isinstance(exc, (NotFound, Http404)):
            envelope["code"] = "MSG-4.4.1-M01"
            envelope["message"] = ALL_MESSAGES.get(
                "MSG-4.4.1-M01", "Không tìm thấy dữ liệu"
            )

        response.data = envelope
        return response

    # 3. Xử lý các ngoại lệ CSDL (IntegrityError / DatabaseError)
    if isinstance(exc, (IntegrityError, DatabaseError)):
        sqlstate, raw_message = _extract_sqlstate_and_message(exc)
        if sqlstate in SQLSTATE_MAP:
            config = SQLSTATE_MAP[sqlstate]
            # Ưu tiên lấy thông điệp tiếng Việt phát sinh từ trigger trong DB nếu có
            msg = raw_message or config["default_message"]
            return Response(
                {
                    "code": config["default_code"],
                    "message": msg,
                    "details": {"sqlstate": sqlstate},
                },
                status=config["status"],
            )

        logger.error(
            f"Unhandled DatabaseError with sqlstate={sqlstate}: {exc}", exc_info=True
        )
        return Response(
            {
                "code": "MSG-4.2-M01",
                "message": ALL_MESSAGES.get("MSG-4.2-M01", "Thông báo lỗi hệ thống"),
                "details": {"sqlstate": sqlstate} if sqlstate else {},
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # 4. Ngoại lệ Django PermissionDenied chưa qua DRF
    if isinstance(exc, DjangoPermissionDenied):
        return Response(
            {
                "code": "MSG-4.2-M01",
                "message": str(exc) or "Bạn không có quyền thực hiện thao tác này.",
                "details": {},
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    # 5. Các lỗi không kiểm soát khác (500)
    logger.error(
        f"Unhandled exception caught by custom_exception_handler: {exc}", exc_info=True
    )
    return Response(
        {
            "code": "MSG-4.2-M01",
            "message": ALL_MESSAGES.get("MSG-4.2-M01", "Thông báo lỗi hệ thống"),
            "details": {"error": str(exc)},
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
