"""
Tests for Custom Exception Handler and SQLSTATE Error Mapping per TL-47.
"""

import pytest
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

from apps.core.exceptions import custom_exception_handler

pytestmark = pytest.mark.django_db


class FakePsycopgError(Exception):
    """Giả lập lỗi psycopg có thuộc tính sqlstate hoặc pgcode."""

    def __init__(self, message: str, sqlstate: str):
        super().__init__(message)
        self.sqlstate = sqlstate
        self.pgcode = sqlstate


def test_exception_handler_sqlstate_23514_check_violation():
    """Kiểm tra ngoại lệ Check violation (23514) được map thành HTTP 400 Bad Request."""
    cause = FakePsycopgError("Check constraint failed: duration_days > 0", "23514")
    exc = IntegrityError("new row violates check constraint")
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    data = response.data
    assert data["code"] == "PROP-GEN-P01"
    assert "23514" in data["details"]["sqlstate"]


def test_exception_handler_sqlstate_55000_object_in_use():
    """Kiểm tra ngoại lệ Object in use / trigger guard (55000) được map thành HTTP 409 Conflict."""
    cause = FakePsycopgError(
        "Không thể xóa vị trí đỗ xe đang có phương tiện đỗ (trạng thái OCCUPIED).",
        "55000",
    )
    exc = IntegrityError("Object not in prerequisite state")
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_409_CONFLICT

    data = response.data
    assert data["code"] == "PROP-DEL-SAVT-IN-USE"
    assert "Không thể xóa vị trí đỗ xe" in data["message"]
    assert data["details"]["sqlstate"] == "55000"


def test_exception_handler_sqlstate_23503_foreign_key_violation():
    """Kiểm tra ngoại lệ Foreign key violation (23503) được map thành HTTP 409 Conflict."""
    cause = FakePsycopgError(
        "update or delete on table violates foreign key constraint", "23503"
    )
    exc = IntegrityError("Foreign key violation")
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_409_CONFLICT

    data = response.data
    assert data["code"] == "MSG-4.3.1-M03"
    assert data["details"]["sqlstate"] == "23503"


def test_exception_handler_sqlstate_23505_unique_violation():
    """Kiểm tra ngoại lệ Unique violation (23505) được map thành HTTP 409 Conflict."""
    cause = FakePsycopgError("duplicate key value violates unique constraint", "23505")
    exc = IntegrityError("Unique violation")
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_409_CONFLICT

    data = response.data
    assert data["code"] == "MSG-4.3.1-M05"
    assert data["details"]["sqlstate"] == "23505"


def test_exception_handler_sqlstate_22023_invalid_parameter():
    """Kiểm tra ngoại lệ Invalid parameter value (22023) được map thành HTTP 400 Bad Request."""
    cause = FakePsycopgError("invalid parameter value for function", "22023")
    exc = DatabaseError("Invalid parameter")
    exc.__cause__ = cause

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    data = response.data
    assert data["code"] == "PROP-GEN-P01"
    assert data["details"]["sqlstate"] == "22023"


def test_exception_handler_unhandled_database_error():
    """Kiểm tra ngoại lệ CSDL không xác định được map thành HTTP 500 Internal Server Error."""
    exc = DatabaseError("Fatal database corruption")

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["code"] == "MSG-4.2-M01"


def test_exception_handler_validation_error():
    """Kiểm tra DRF ValidationError được đóng gói vào envelope chuẩn."""
    exc = ValidationError({"email": ["Email không hợp lệ."]})

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    data = response.data
    assert data["code"] == "PROP-GEN-P01"
    assert "email" in data["details"]


def test_exception_handler_not_authenticated():
    """Kiểm tra lỗi chưa đăng nhập được đóng gói thành HTTP 401 với mã MSG-4.1-M02."""
    exc = NotAuthenticated()

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"


def test_exception_handler_authentication_failed():
    """Kiểm tra lỗi xác thực thất bại được đóng gói thành HTTP 401."""
    exc = AuthenticationFailed()

    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"


def test_exception_handler_permission_denied():
    """Kiểm tra lỗi không có quyền (DRF và Django) được map thành HTTP 403 với mã MSG-4.2-M01."""
    exc_drf = DRFPermissionDenied()
    resp_drf = custom_exception_handler(exc_drf, context={})
    assert resp_drf is not None
    assert resp_drf.status_code == status.HTTP_403_FORBIDDEN
    assert resp_drf.data["code"] == "MSG-4.2-M01"

    exc_dj = DjangoPermissionDenied("Cấm truy cập")
    resp_dj = custom_exception_handler(exc_dj, context={})
    assert resp_dj is not None
    assert resp_dj.status_code == status.HTTP_403_FORBIDDEN
    assert resp_dj.data["code"] == "MSG-4.2-M01"


def test_exception_handler_not_found():
    """Kiểm tra lỗi không tìm thấy tài nguyên (404) với mã MSG-4.4.1-M01."""
    exc_drf = NotFound()
    resp_drf = custom_exception_handler(exc_drf, context={})
    assert resp_drf is not None
    assert resp_drf.status_code == status.HTTP_404_NOT_FOUND
    assert resp_drf.data["code"] == "MSG-4.4.1-M01"

    exc_dj = Http404()
    resp_dj = custom_exception_handler(exc_dj, context={})
    assert resp_dj is not None
    assert resp_dj.status_code == status.HTTP_404_NOT_FOUND
    assert resp_dj.data["code"] == "MSG-4.4.1-M01"


def test_exception_handler_generic_unhandled_exception():
    """Kiểm tra ngoại lệ chung chưa được xử lý trả về HTTP 500 với envelope chuẩn."""
    exc = RuntimeError("Unexpected runtime failure")
    response = custom_exception_handler(exc, context={})
    assert response is not None
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    assert response.data["code"] == "MSG-4.2-M01"
    assert "Unexpected runtime failure" in response.data["details"]["error"]
