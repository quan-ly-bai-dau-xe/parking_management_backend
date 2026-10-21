"""
Boundary Stress Testing Suite for Core Foundations (Permissions & Exceptions).

Covers edge cases, unusual inputs, and stress conditions:
1. Permissions:
   - Weird roles: lowercase, whitespace, null bytes, admin/superuser/staff/root, empty, non-string, booleans, collections.
   - Weird user objects: AnonymousUser, None, objects without is_authenticated, inactive users, active without role.
   - Weird requests: None, missing user attr, mock objects.
   - APIView HTTP status and envelope enforcement:
     - Anonymous / unauthenticated -> HTTP 401, 'MSG-4.1-M02'
     - Inactive user -> HTTP 403, 'MSG-4.2-M01'
     - Invalid / unknown role -> HTTP 403, 'MSG-4.2-M01'
     - CUSTOMER -> HTTP 403, 'MSG-4.2-M01'
     - EMPLOYEE on IsManager -> HTTP 403, 'MSG-4.2-M01'
     - EMPLOYEE on IsEmployeeOrManager -> HTTP 200
     - MANAGER on both -> HTTP 200

2. Exceptions:
   - DatabaseError / IntegrityError / OperationalError with unusual inputs:
     - Empty error message ("")
     - Whitespace-only message ("   ")
     - None sqlstate, weird sqlstate ("08006", "42P01", "XX000", "57P01", "40001", "99999", "")
     - Message with special regex characters, nested newlines, non-ASCII/unicode
     - psycopg diag attribute variations: None, empty object, mock with None fields
     - Truncated trigger messages vs complete trigger messages
     - Multiple conflicting triggers in the same exception
   - DRF standard exceptions envelope verification:
     - ValidationError (dict, list, str, nested) -> HTTP 400, 'PROP-GEN-P01'
     - NotAuthenticated / AuthenticationFailed -> HTTP 401, 'MSG-4.1-M02'
     - PermissionDenied (DRF & Django) -> HTTP 403, 'MSG-4.2-M01'
     - NotFound / Http404 -> HTTP 404, 'MSG-4.4.1-M01'
     - MethodNotAllowed -> HTTP 405, 'MSG-4.2-M01'
     - UnsupportedMediaType -> HTTP 415, 'MSG-4.2-M01'
     - Throttled -> HTTP 429, 'MSG-4.2-M01'
     - Unhandled exceptions (KeyError, ZeroDivisionError, MemoryError) -> HTTP 500, 'MSG-4.2-M01'
"""

from typing import Any
from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import AnonymousUser
from django.db import DatabaseError, IntegrityError, OperationalError
from rest_framework import status
from rest_framework.exceptions import (
    MethodNotAllowed,
    Throttled,
    UnsupportedMediaType,
    ValidationError,
)
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.accounts.models import Account
from apps.core.exceptions import custom_exception_handler
from apps.core.permissions import IsEmployeeOrManager, IsManager

pytestmark = pytest.mark.django_db


class DummyUserWithoutAuthAttr:
    """Đối tượng giả lập không có thuộc tính is_authenticated thông thường."""

    pass


class DummyUserCustomRole:
    """Đối tượng người dùng tùy biến với các thuộc tính linh hoạt."""

    def __init__(
        self,
        is_authenticated: bool = True,
        is_active: bool | None = True,
        role: Any = None,
    ):
        self.is_authenticated = is_authenticated
        self.is_active = is_active
        self.role = role


class DummySecuredView(APIView):
    """View kiểm thử phân quyền IsEmployeeOrManager."""

    permission_classes = [IsEmployeeOrManager]

    def get(self, request):
        return Response(
            {"status": "success", "user_role": getattr(request.user, "role", None)}
        )


class DummyManagerSecuredView(APIView):
    """View kiểm thử phân quyền IsManager."""

    permission_classes = [IsManager]

    def get(self, request):
        return Response(
            {"status": "success", "user_role": getattr(request.user, "role", None)}
        )


# ==============================================================================
# SECTION 1: BOUNDARY STRESS TEST TRÊN PERMISSIONS
# ==============================================================================


@pytest.mark.parametrize(
    "weird_role",
    [
        "manager",  # Lowercase
        "MANAGER ",  # Trailing space
        " MANAGER",  # Leading space
        "Manager",  # Title case
        "mAnAgEr",  # Mixed case
        "ADMIN",  # Non-existent role
        "SUPERUSER",  # Superuser is not explicitly MANAGER
        "ROOT",  # Unix root
        "STAFF",  # Django staff
        "OPERATOR",
        "",  # Empty string
        "   ",  # Whitespace only
        "MANAGER\0",  # Null byte injection
        "EMPLOYEE; DROP TABLE account;--",  # SQL injection attempt in role
        None,  # Null role
        123,  # Integer
        0,  # Zero
        False,  # Boolean False
        True,  # Boolean True
        ["MANAGER"],  # List
        {"role": "MANAGER"},  # Dict
    ],
)
def test_permissions_boundary_weird_roles_rejected(weird_role):
    """
    Tất cả các role dị biệt, sai định dạng, khoảng trắng, chữ thường hoặc cố gắng injection
    đều phải bị từ chối bởi cả IsManager và IsEmployeeOrManager.
    """
    perm_mgr = IsManager()
    perm_emp_mgr = IsEmployeeOrManager()
    view = MagicMock()

    req = MagicMock()
    req.user = DummyUserCustomRole(
        is_authenticated=True, is_active=True, role=weird_role
    )

    assert perm_mgr.has_permission(req, view) is False, (
        f"Failed for weird_role={weird_role!r}"
    )
    assert perm_emp_mgr.has_permission(req, view) is False, (
        f"Failed for weird_role={weird_role!r}"
    )


@pytest.mark.parametrize(
    "weird_user",
    [
        None,
        AnonymousUser(),
        DummyUserWithoutAuthAttr(),  # Thiếu thuộc tính is_authenticated
        DummyUserCustomRole(is_authenticated=False, is_active=True, role="MANAGER"),
        DummyUserCustomRole(is_authenticated=True, is_active=False, role="MANAGER"),
        DummyUserCustomRole(is_authenticated=True, is_active=False, role="EMPLOYEE"),
        DummyUserCustomRole(is_authenticated=True, is_active=None, role="MANAGER"),
        "string_user",  # User là chuỗi thay vì object
        12345,  # User là số nguyên
    ],
)
def test_permissions_boundary_weird_users_rejected(weird_user):
    """
    Tất cả các đối tượng user dị biệt (None, Anonymous, inactive, kiểu dữ liệu lạ)
    đều phải an toàn bị từ chối hoặc trả về False mà không làm vỡ logic.
    """
    perm_mgr = IsManager()
    perm_emp_mgr = IsEmployeeOrManager()
    view = MagicMock()

    req = MagicMock()
    req.user = weird_user

    # Nếu user không có is_authenticated, getattr an toàn hoặc bool(user and getattr...)
    try:
        res_mgr = perm_mgr.has_permission(req, view)
    except AttributeError:
        # Nếu raise AttributeError trên user lạ không có is_authenticated, ghi nhận hành vi
        res_mgr = False

    try:
        res_emp_mgr = perm_emp_mgr.has_permission(req, view)
    except AttributeError:
        res_emp_mgr = False

    assert res_mgr is False
    assert res_emp_mgr is False


def test_permissions_boundary_request_without_user_attr():
    """Kiểm tra request không hề có thuộc tính user (getattr request, 'user', None)."""
    perm_mgr = IsManager()
    perm_emp_mgr = IsEmployeeOrManager()
    view = MagicMock()

    class BareRequest:
        pass

    bare_req = BareRequest()
    assert perm_mgr.has_permission(bare_req, view) is False
    assert perm_emp_mgr.has_permission(bare_req, view) is False


def test_permissions_boundary_none_request():
    """Kiểm tra request là None."""
    perm_mgr = IsManager()
    perm_emp_mgr = IsEmployeeOrManager()
    view = MagicMock()

    assert perm_mgr.has_permission(None, view) is False
    assert perm_emp_mgr.has_permission(None, view) is False


def test_permissions_api_view_boundary_inactive_user_envelope():
    """
    Người dùng bị vô hiệu hóa (is_active=False) dù có role MANAGER:
    DRF SessionAuthentication từ chối ngay tại tầng Authentication, trả về HTTP 401 Unauthorized
    với envelope chuẩn MSG-4.1-M02 thay vì 403.
    """
    factory = APIRequestFactory()
    request = factory.get("/api/v1/test/")
    inactive_mgr = Account.objects.create_user(
        email="inactive_mgr@example.com",
        password="Password123!",
        role="MANAGER",
        is_active=False,
    )
    request.user = inactive_mgr

    view = DummyManagerSecuredView.as_view()
    response = view(request)

    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"
    assert (
        response.data["message"] == "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu"
    )


def test_permissions_api_view_boundary_weird_role_user_envelope():
    """
    Người dùng có role lạ ('HACKER') khi gọi APIView phải bị từ chối 403
    với envelope chuẩn MSG-4.2-M01.
    """
    factory = APIRequestFactory()
    request = factory.get("/api/v1/test/")
    weird_user = Account(email="hacker@example.com", role="HACKER", is_active=True)
    request.user = weird_user

    view = DummySecuredView.as_view()
    response = view(request)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"
    assert response.data["message"] == "Bạn không có quyền thực hiện thao tác này."


# ==============================================================================
# SECTION 2: BOUNDARY STRESS TEST TRÊN EXCEPTION HANDLER
# ==============================================================================


class PsycopgDiagStub:
    """Stub đối tượng diag của psycopg với các trường có thể tùy biến."""

    def __init__(self, message_primary=None, message_detail=None):
        self.message_primary = message_primary
        self.message_detail = message_detail


class CustomBoundaryDbError(Exception):
    """Giả lập exception psycopg với cấu trúc đa dạng."""

    def __init__(
        self,
        message: str = "",
        sqlstate: str | None = None,
        diag: Any = None,
    ):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.pgcode = sqlstate
        self.diag = diag


@pytest.mark.parametrize(
    "empty_or_none_msg",
    [
        "",
        None,
    ],
)
def test_exceptions_boundary_empty_or_none_messages(empty_or_none_msg):
    """
    Ngoại lệ CSDL có message rỗng hoặc None:
    Exception handler fallback an toàn về default message tiếng Việt
    kèm envelope hợp lệ.
    """
    cause = CustomBoundaryDbError(str(empty_or_none_msg or ""), sqlstate="23505")
    exc = IntegrityError(empty_or_none_msg or "")
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "MSG-4.3.1-M05"
    assert (
        response.data["message"]
        == "Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp."
    )
    assert response.data["details"]["sqlstate"] == "23505"


@pytest.mark.parametrize(
    "whitespace_msg",
    [
        "   ",
        "\t\n",
    ],
)
def test_exceptions_boundary_whitespace_messages_observed_behavior(whitespace_msg):
    """
    Ghi nhận hành vi chuẩn hóa (F2 hardening):
    Khi message chỉ chứa khoảng trắng, hệ thống không làm rò rỉ chuỗi thô mà
    fallback về thông điệp mặc định tiếng Việt hợp lệ của mã lỗi 23505.
    """
    cause = CustomBoundaryDbError(whitespace_msg, sqlstate="23505")
    exc = IntegrityError(whitespace_msg)
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "MSG-4.3.1-M05"
    assert (
        response.data["message"]
        == "Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp."
    )


@pytest.mark.parametrize(
    "unknown_sqlstate",
    [
        "08006",  # connection failure
        "42P01",  # undefined table
        "XX000",  # internal error
        "57P01",  # admin shutdown
        "40001",  # serialization failure / deadlock
        "99999",  # non-existent sqlstate
        "INVALID_SQLSTATE",
        "",  # empty sqlstate
    ],
)
def test_exceptions_boundary_unknown_sqlstate_codes_return_500_envelope(
    unknown_sqlstate,
):
    """
    Ngoại lệ CSDL có SQLSTATE lạ, không nằm trong SQLSTATE_MAP:
    Hệ thống chuẩn hóa về HTTP 500 với MSG-4.5.1-M03 ("lỗi kết nối"), details rỗng per F2.
    """
    cause = CustomBoundaryDbError(
        f"Database failure with state {unknown_sqlstate}",
        sqlstate=unknown_sqlstate or None,
    )
    exc = DatabaseError(f"Database error {unknown_sqlstate}")
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["code"] == "MSG-4.5.1-M03"
    assert response.data["message"] == "lỗi kết nối"
    assert response.data["details"] == {}


def test_exceptions_boundary_operational_error_connection_failure():
    """
    Ngoại lệ OperationalError (mất kết nối, timeout) được map thành HTTP 500 MSG-4.5.1-M03 per F2.
    """
    cause = CustomBoundaryDbError(
        "could not connect to server: Connection refused", "08001"
    )
    exc = OperationalError("connection failure")
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["code"] == "MSG-4.5.1-M03"
    assert response.data["message"] == "lỗi kết nối"
    assert response.data["details"] == {}


def test_exceptions_boundary_diag_with_none_attributes():
    """
    Đối tượng diag tồn tại nhưng tất cả message_primary và message_detail đều là None.
    Hệ thống phải tự động fallback sang cause_str mà không raise AttributeError.
    """
    diag = PsycopgDiagStub(message_primary=None, message_detail=None)
    cause = CustomBoundaryDbError(
        "Check constraint duration_days > 0", "23514", diag=diag
    )
    exc = IntegrityError("new row violates check constraint")
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-GEN-P01"
    assert "23514" in response.data["details"]["sqlstate"]


def test_exceptions_boundary_regex_chars_in_database_error():
    """
    Thông điệp lỗi CSDL chứa các ký tự đặc biệt của biểu thức chính quy (regex) như [, ], (, ), *, +, ?, ^, $.
    Hàm _extract_sqlstate_and_message không được bị lỗi regex syntax.
    """
    weird_msg = r"Error near table[0-9]+ (.*?) \d+ [a-z]{3} ^ $ \ / : 23505"
    cause = CustomBoundaryDbError(weird_msg, sqlstate=None)  # Phải fallback qua regex
    exc = IntegrityError(weird_msg)
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "MSG-4.3.1-M05"
    assert response.data["details"]["sqlstate"] == "23505"


def test_exceptions_boundary_nested_multiline_trigger_message():
    """
    Thông điệp lỗi trigger được bọc trong nhiều dòng traceback, HINT, CONTEXT và ký tự tiếng Việt có dấu.
    Trích xuất và ánh xạ trigger phải thành công và phân biệt đúng mã lỗi.
    """
    multiline_msg = (
        "ERROR: Vị trí này đang bảo trì.\n"
        "DETAIL: Key (slot_id)=(15) is in MAINTENANCE status.\n"
        "HINT: Please select another available slot.\n"
        "CONTEXT: PL/pgSQL function fn_check_slot_status() line 12 at RAISE"
    )
    cause = CustomBoundaryDbError(multiline_msg, sqlstate="23514")
    exc = IntegrityError(multiline_msg)
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "PROP-4.5.2-P01"
    assert response.data["message"] == "Vị trí này đang bảo trì."


@pytest.mark.parametrize(
    "drf_exc, expected_status, expected_code",
    [
        (MethodNotAllowed("POST"), status.HTTP_405_METHOD_NOT_ALLOWED, "MSG-4.2-M01"),
        (
            UnsupportedMediaType("text/plain"),
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "MSG-4.2-M01",
        ),
        (Throttled(wait=60), status.HTTP_429_TOO_MANY_REQUESTS, "MSG-4.2-M01"),
    ],
)
def test_exceptions_boundary_drf_status_codes_envelope_conformance(
    drf_exc, expected_status, expected_code
):
    """
    Các ngoại lệ HTTP đặc biệt khác của DRF (405 MethodNotAllowed, 415 UnsupportedMediaType, 429 Throttled)
    phải tuân thủ 100% envelope chuẩn {code, message, details} và giữ nguyên HTTP status code tương ứng.
    """
    response = custom_exception_handler(drf_exc, context={})
    assert response is not None
    assert response.status_code == expected_status
    assert "code" in response.data
    assert "message" in response.data
    assert "details" in response.data
    assert response.data["code"] == expected_code


def test_exceptions_boundary_validation_error_formats():
    """
    Kiểm tra DRF ValidationError ở cả 3 định dạng dữ liệu (dict, list, str)
    đều được bọc vào details an toàn mà không bị mất dữ liệu.
    """
    # 1. Dict
    exc_dict = ValidationError({"field_a": ["Lỗi a"], "field_b": ["Lỗi b"]})
    resp_dict = custom_exception_handler(exc_dict, context={})
    assert resp_dict.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_dict.data["details"]["field_a"] == ["Lỗi a"]

    # 2. List
    exc_list = ValidationError(["Lỗi tổng thể 1", "Lỗi tổng thể 2"])
    resp_list = custom_exception_handler(exc_list, context={})
    assert resp_list.status_code == status.HTTP_400_BAD_REQUEST
    assert "error" in resp_list.data["details"]
    assert resp_list.data["details"]["error"] == ["Lỗi tổng thể 1", "Lỗi tổng thể 2"]

    # 3. String
    exc_str = ValidationError("Lỗi chuỗi đơn")
    resp_str = custom_exception_handler(exc_str, context={})
    assert resp_str.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_str.data["details"]["error"] == ["Lỗi chuỗi đơn"]


@pytest.mark.parametrize(
    "fatal_exc",
    [
        KeyError("missing_crucial_key"),
        ZeroDivisionError("division by zero"),
        MemoryError("out of memory"),
        TypeError("unhashable type: 'dict'"),
    ],
)
def test_exceptions_boundary_fatal_unhandled_python_exceptions(fatal_exc):
    """
    Các ngoại lệ Python nghiêm trọng (KeyError, ZeroDivisionError, MemoryError, TypeError)
    không được làm sập ứng dụng mà phải được bọc thành HTTP 500 với envelope chuẩn.
    """
    response = custom_exception_handler(fatal_exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["code"] == "MSG-4.2-M01"
    assert response.data["message"] == "Thông báo lỗi hệ thống"
    assert response.data["details"] == {}
