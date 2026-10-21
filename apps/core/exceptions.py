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
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import DatabaseError, IntegrityError
from django.http import Http404, HttpRequest, JsonResponse
from rest_framework import status
from rest_framework.exceptions import (
    APIException,
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


class BusinessAPIException(APIException):
    """
    Ngoại lệ nghiệp vụ có cấu trúc mã code, thông điệp tiếng Việt message,
    và HTTP status code tương ứng per TL-47 / TL-50.
    """

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        wait: int | float | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        self.headers = headers or {}
        self.wait = wait
        super().__init__(detail=message, code=code)


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


def _is_safe_vietnamese_message(msg: str | None) -> bool:
    """Kiểm tra xem chuỗi có phải là thông báo nghiệp vụ tiếng Việt an toàn hay là raw SQL text."""
    if not msg:
        return False
    dangerous_keywords = [
        "duplicate key",
        "violates unique constraint",
        "violates foreign key",
        "violates check constraint",
        "relation",
        "syntax error",
        "null value in column",
        "permission denied for table",
        "psycopg",
        "postgresql",
        "table",
        "column",
        "constraint",
        "key (",
    ]
    lower_msg = msg.lower()
    if any(k in lower_msg for k in dangerous_keywords):
        return False

    vietnamese_markers = [
        "không",
        "đã",
        "lỗi",
        "vị trí",
        "xe",
        "vé",
        "hệ thống",
        "thành công",
        "phương tiện",
        "khách hàng",
        "nhân viên",
    ]
    return any(marker in lower_msg for marker in vietnamese_markers)


def map_database_exception_to_business_error(
    exc: Exception,
) -> BusinessAPIException | None:
    """
    Centralized mapping of database constraint violations and trigger errors to BusinessAPIException.

    Architectural Rationale (Standard 4 DRY Justification):
    Shared exclusively between check_in_vehicle service and custom_exception_handler:
    1. Fail-Fast in Service Layer: When check_in_vehicle encounters deterministic database triggers
       (e.g., maintenance slots, vehicle-type mismatch, active open sessions), retrying across
       attempt loops is futile and wastes CPU/DB queries. Calling this helper inside the retry loop
       breaks immediately on known business domain failures.
    2. DRY Single Source of Truth: Centralizing regex/message matching here guarantees uniform error
       codes (PROP-4.5.1-P07, PROP-4.5.2-P01, etc.) without duplicating database error parsing.
    3. Global Fallback: Unhandled infrastructure errors (e.g. connection losses, deadlocks) return
       None and bubble up to custom_exception_handler for standard SQLSTATE classification.
    """
    sqlstate, raw_message = _extract_sqlstate_and_message(exc)
    cause_str = str(getattr(exc, "__cause__", None) or exc)
    search_text = f"{raw_message or ''} {cause_str}"

    if "Vị trí này đang bảo trì." in search_text:
        return BusinessAPIException(
            code="PROP-4.5.2-P01",
            message=ALL_MESSAGES.get("PROP-4.5.2-P01", "Vị trí này đang bảo trì."),
            status_code=status.HTTP_409_CONFLICT,
            details={"sqlstate": sqlstate or "23514"},
        )

    if "Vị trí này đã được đặt trước cho phương tiện khác." in search_text:
        return BusinessAPIException(
            code="PROP-4.5.2-P05",
            message=ALL_MESSAGES.get(
                "PROP-4.5.2-P05",
                "Vị trí này đã được đặt trước cho phương tiện khác.",
            ),
            status_code=status.HTTP_409_CONFLICT,
            details={"sqlstate": sqlstate or "23514"},
        )

    if (
        "Loại xe không phù hợp với cấu hình cho phép của vị trí đỗ." in search_text
        or "Loại phương tiện không tương thích" in search_text
        or "PROP-SLOT-VEHICLE-TYPE-MISMATCH" in search_text
    ):
        return BusinessAPIException(
            code="PROP-SLOT-VEHICLE-TYPE-MISMATCH",
            message=ALL_MESSAGES.get(
                "PROP-SLOT-VEHICLE-TYPE-MISMATCH",
                "Loại phương tiện không tương thích với danh sách loại xe cho phép của vị trí đỗ này.",
            ),
            status_code=status.HTTP_409_CONFLICT,
            details={"sqlstate": sqlstate or "23514"},
        )

    if "Vị trí này đã có xe đk vé và đang sử dụng" in search_text:
        return BusinessAPIException(
            code="MSG-4.5.2-M02",
            message=ALL_MESSAGES.get(
                "MSG-4.5.2-M02",
                "Vị trí này đã có xe đk vé và đang sử dụng",
            ),
            status_code=status.HTTP_409_CONFLICT,
            details={"sqlstate": sqlstate or "23514"},
        )

    if "Lỗi dữ liệu không tìm thấy đê lưu" in search_text:
        return BusinessAPIException(
            code="MSG-4.5.1-M02",
            message=ALL_MESSAGES.get(
                "MSG-4.5.1-M02",
                "Lỗi dữ liệu không tìm thấy đê lưu",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"sqlstate": sqlstate or "23514"},
        )

    if (
        "uq_log_open_session_plate" in search_text
        or "uq_log_open_session_vehicle" in search_text
    ):
        return BusinessAPIException(
            code="PROP-4.5.1-P07",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P07",
                "Biển số xe đã có phiên đỗ xe đang mở chưa hoàn thành.",
            ),
            status_code=status.HTTP_409_CONFLICT,
            details={"sqlstate": sqlstate or "23505"},
        )

    if "uq_log_open_session_slot" in search_text:
        return BusinessAPIException(
            code="PROP-4.5.2-P02",
            message=ALL_MESSAGES.get(
                "PROP-4.5.2-P02",
                "Không thể chuyển trạng thái vị trí khi đang có xe đỗ trong ô.",
            ),
            status_code=status.HTTP_409_CONFLICT,
            details={"sqlstate": sqlstate or "23505"},
        )

    return None


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

        if isinstance(exc, BusinessAPIException):
            envelope["code"] = exc.code
            envelope["message"] = exc.message
            envelope["details"] = exc.details
            response.status_code = exc.status_code
            if hasattr(exc, "headers") and exc.headers:
                for k, v in exc.headers.items():
                    response[k] = str(v)
            if hasattr(exc, "wait") and exc.wait is not None:
                response["Retry-After"] = str(int(exc.wait))
        elif isinstance(exc, (ValidationError, DjangoValidationError)):
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
        logger.error(
            f"Database exception caught by custom_exception_handler: {exc}",
            exc_info=True,
        )
        # Sử dụng hàm ánh xạ lỗi tập trung (Standard 4 DRY)
        mapped_biz_exc = map_database_exception_to_business_error(exc)
        if mapped_biz_exc:
            return Response(
                {
                    "code": mapped_biz_exc.code,
                    "message": mapped_biz_exc.message,
                    "details": mapped_biz_exc.details,
                },
                status=mapped_biz_exc.status_code,
            )

        sqlstate, raw_message = _extract_sqlstate_and_message(exc)

        if sqlstate in SQLSTATE_MAP:
            config = SQLSTATE_MAP[sqlstate]
            # TUYỆT ĐỐI KHÔNG rò rỉ raw_message nếu là raw SQL text từ DB
            msg = config["default_message"]
            if _is_safe_vietnamese_message(raw_message):
                msg = raw_message

            return Response(
                {
                    "code": config["default_code"],
                    "message": msg,
                    "details": {"sqlstate": sqlstate} if sqlstate else {},
                },
                status=config["status"],
            )

        # Unmapped IntegrityError / DatabaseError per F2:
        # Chuẩn hóa về MSG-4.5.1-M03 ("lỗi kết nối"), HTTP 500, details rỗng
        return Response(
            {
                "code": "MSG-4.5.1-M03",
                "message": ALL_MESSAGES.get("MSG-4.5.1-M03", "lỗi kết nối"),
                "details": {},
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

    # 4.1 Ngoại lệ Django ValidationError chưa qua DRF (defense-in-depth per F4)
    if isinstance(exc, DjangoValidationError):
        details: dict[str, Any] = {}
        if hasattr(exc, "message_dict"):
            details = exc.message_dict
        elif hasattr(exc, "messages"):
            details = {"error": exc.messages}
        else:
            details = {"error": [str(exc)]}
        return Response(
            {
                "code": "PROP-GEN-P01",
                "message": ALL_MESSAGES.get(
                    "PROP-GEN-P01", "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu"
                ),
                "details": details,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # 5. Các lỗi không kiểm soát khác (500)
    logger.error(
        f"Unhandled exception caught by custom_exception_handler: {exc}", exc_info=True
    )
    return Response(
        {
            "code": "MSG-4.2-M01",
            "message": ALL_MESSAGES.get("MSG-4.2-M01", "Thông báo lỗi hệ thống"),
            "details": {},
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def custom_json_404(
    request: HttpRequest, exception: Exception | None = None
) -> JsonResponse:
    """
    Handler 404 tùy chỉnh trả về JSON envelope chuẩn MSG-4.4.1-M01
    cho các URL không khớp route trên toàn hệ thống per F4.
    """
    return JsonResponse(
        {
            "code": "MSG-4.4.1-M01",
            "message": ALL_MESSAGES.get("MSG-4.4.1-M01", "Không tìm thấy dữ liệu"),
            "details": {},
        },
        status=404,
    )
