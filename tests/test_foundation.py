"""
Foundation test suite for Parking Management Backend per TL-48.
Covers core components: Pagination, Messages catalog, Soft-delete ORM hierarchy,
Account authentication model & manager, and load_sample_data management command.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models.lookups import IsNull
from django.db.models.sql.where import WhereNode
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from apps.accounts.models import Account, PasswordResetToken, PersistentLoginToken
from apps.core.messages import (
    ALL_MESSAGES,
    get_message,
    get_prop_message,
    get_srs_message,
)
from apps.core.models import (
    AdministrativeDistrict,
    AdministrativeProvince,
    AdministrativeWard,
    _has_deleted_at_lookup,
    _transform_deleted_at_where,
)
from apps.core.pagination import StandardResultsSetPagination

pytestmark = pytest.mark.django_db


# ==============================================================================
# 1. Tests for apps/core/pagination.py
# ==============================================================================


def test_standard_results_set_pagination_default():
    """Kiểm tra phân trang mặc định (page_size=20) và cấu trúc envelope trả về."""
    factory = APIRequestFactory()
    wsgi_request = factory.get("/api/test-items/")
    request = Request(wsgi_request)
    paginator = StandardResultsSetPagination()

    data_set = list(range(1, 55))  # 54 phần tử
    page = paginator.paginate_queryset(data_set, request)
    assert page is not None
    assert len(page) == 20

    response = paginator.get_paginated_response(page)
    payload = response.data

    assert payload["count"] == 54
    assert payload["total_pages"] == 3
    assert payload["current_page"] == 1
    assert payload["page_size"] == 20
    assert payload["next"] is not None
    assert payload["previous"] is None
    assert payload["results"] == list(range(1, 21))


def test_standard_results_set_pagination_custom_page_size():
    """Kiểm tra tùy chỉnh kích thước trang qua tham số truy vấn page_size."""
    factory = APIRequestFactory()
    wsgi_request = factory.get("/api/test-items/?page_size=10&page=2")
    request = Request(wsgi_request)
    paginator = StandardResultsSetPagination()

    data_set = list(range(1, 35))
    page = paginator.paginate_queryset(data_set, request)
    assert page is not None
    assert len(page) == 10

    response = paginator.get_paginated_response(page)
    payload = response.data

    assert payload["count"] == 34
    assert payload["total_pages"] == 4
    assert payload["current_page"] == 2
    assert payload["page_size"] == 10
    assert payload["next"] is not None
    assert payload["previous"] is not None
    assert payload["results"] == list(range(11, 21))


def test_standard_results_set_pagination_max_page_size_cap():
    """Kiểm tra max_page_size giới hạn tối đa ở mức 100 khi client yêu cầu vượt ngưỡng."""
    factory = APIRequestFactory()
    wsgi_request = factory.get("/api/test-items/?page_size=500")
    request = Request(wsgi_request)
    paginator = StandardResultsSetPagination()

    data_set = list(range(1, 150))
    page = paginator.paginate_queryset(data_set, request)
    assert page is not None
    assert len(page) == 100  # Bị giới hạn ở 100

    response = paginator.get_paginated_response(page)
    assert response.data["page_size"] == 100


# ==============================================================================
# 2. Tests for apps/core/messages.py
# ==============================================================================


def test_messages_catalog_helpers():
    """Kiểm tra các hàm tiện ích truy vấn chuỗi thông báo tập trung."""
    # 1. get_srs_message
    srs_msg = get_srs_message("MSG-4.1-M02")
    assert srs_msg == "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu"
    assert get_srs_message("NON_EXISTENT", default="Default text") == "Default text"

    # 2. get_prop_message
    prop_msg = get_prop_message("PROP-GEN-P01")
    assert prop_msg == "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu"
    assert get_prop_message("NON_EXISTENT", default="Fallback") == "Fallback"

    # 3. get_message có định dạng tham số kwargs
    with_format = get_message("MSG-4.3.3-M01", item="email")
    assert "email" in with_format

    # Xử lý an toàn khi format lỗi
    malformed = get_message("MSG-4.3.3-M01", wrong_param=123)
    assert "{item}" in malformed

    # 4. get_message tìm kiếm trong ALL_MESSAGES
    assert get_message("MSG-4.1-M02") == srs_msg
    assert get_message("PROP-GEN-P01") == prop_msg
    assert get_message("NON_EXISTENT", default="Safe") == "Safe"

    with pytest.raises(KeyError):
        get_message("INVALID_CODE")

    # Kiểm tra ALL_MESSAGES không rỗng
    assert len(ALL_MESSAGES) >= 100


# ==============================================================================
# 3. Tests for apps/core/models.py (Soft-Delete & Administrative Models)
# ==============================================================================


def test_soft_delete_ast_where_tree_transforms():
    """Kiểm tra các hàm biến đổi cây điều kiện SQL WHERE của Django ORM."""
    mock_field = MagicMock()
    mock_field.target.name = "deleted_at"
    lookup = IsNull(mock_field, True)

    where = WhereNode([lookup])
    assert _has_deleted_at_lookup(where) is True

    # Biến đổi sang only_deleted: IsNull(deleted_at, False)
    transformed_only = _transform_deleted_at_where(where, mode="only_deleted")
    assert len(transformed_only.children) == 1
    assert transformed_only.children[0].rhs is False

    # Biến đổi sang with_deleted: xóa bỏ node IsNull
    transformed_with = _transform_deleted_at_where(where, mode="with_deleted")
    assert len(transformed_with.children) == 0

    # Cây WHERE không chứa deleted_at
    mock_other_field = MagicMock()
    mock_other_field.target.name = "name"
    other_lookup = IsNull(mock_other_field, True)
    where_other = WhereNode([other_lookup])
    assert _has_deleted_at_lookup(where_other) is False


def test_soft_delete_ban_hard_delete():
    """Kiểm tra lệnh xóa cứng (hard_delete) bị nghiêm cấm trên cả QuerySet và Model instance."""
    user = Account.objects.create_user(
        email="soft_del_test@example.com",
        password="Password123!",
    )

    # Cấm xóa cứng trên model instance
    with pytest.raises(PermissionDenied) as exc_info:
        user.hard_delete()
    assert "Hard delete bị nghiêm cấm per ADR-0003" in str(exc_info.value)

    # Cấm xóa cứng trên QuerySet
    qs = Account.objects.filter(id=user.id)
    with pytest.raises(PermissionDenied) as qs_exc_info:
        qs.hard_delete()
    assert "Thao tác xóa cứng trên thực thể nghiệp vụ bị nghiêm cấm" in str(
        qs_exc_info.value
    )


def test_soft_delete_manager_and_queryset_operations():
    """Kiểm tra toàn bộ vòng đời soft_delete, with_deleted, only_deleted và restore."""
    operator = Account.objects.create_user(
        email="operator_sd@example.com",
        password="Password123!",
        role="MANAGER",
    )
    target = Account.objects.create_user(
        email="target_sd@example.com",
        password="Password123!",
        role="EMPLOYEE",
    )

    # 1. Soft delete bằng model method có truyền operator
    target.soft_delete(user=operator)
    target.refresh_from_db()
    assert target.deleted_at is not None
    assert target.deleted_by_id == operator.id

    # Không xuất hiện trong default objects manager
    assert Account.objects.filter(id=target.id).count() == 0

    # Xuất hiện trong with_deleted và only_deleted
    assert Account.objects.with_deleted().filter(id=target.id).count() == 1
    assert Account.objects.only_deleted().filter(id=target.id).count() == 1

    # 2. Restore bằng model method
    target.restore()
    target.refresh_from_db()
    assert target.deleted_at is None
    assert target.deleted_by is None
    assert Account.objects.filter(id=target.id).count() == 1

    # 3. Soft delete bằng QuerySet method
    Account.objects.filter(id=target.id).soft_delete(user=operator)
    assert Account.objects.filter(id=target.id).count() == 0
    assert Account.objects.only_deleted().filter(id=target.id).count() == 1

    # 4. Restore bằng Manager/QuerySet method
    Account.objects.filter(id=target.id).restore()
    assert Account.objects.filter(id=target.id).count() == 1

    # 5. Model delete() gọi soft_delete()
    target.delete()
    target.refresh_from_db()
    assert target.deleted_at is not None
    assert Account.objects.filter(id=target.id).count() == 0


def test_administrative_models_string_representation():
    """Kiểm tra phương thức __str__ của các thực thể địa giới hành chính unmanaged."""
    province = AdministrativeProvince(code="01", name="Thành phố Hà Nội")
    assert str(province) == "Thành phố Hà Nội"

    district = AdministrativeDistrict(
        province=province, code="001", name="Quận Ba Đình"
    )
    assert str(district) == "Quận Ba Đình, Thành phố Hà Nội"

    ward = AdministrativeWard(district=district, code="00001", name="Phường Phúc Xá")
    assert str(ward) == "Phường Phúc Xá, Quận Ba Đình"


# ==============================================================================
# 4. Tests for apps/accounts/models.py
# ==============================================================================


def test_account_creation_validation():
    """Kiểm tra AccountManager quăng ValueError khi thiếu cả email và số điện thoại."""
    with pytest.raises(ValueError) as exc:
        Account.objects.create_user(email=None, phone=None, password="Password123!")
    assert "Bắt buộc phải cung cấp Email hoặc Số điện thoại" in str(exc.value)


def test_account_properties_and_permissions():
    """Kiểm tra các thuộc tính phân quyền is_staff, is_superuser, has_perm theo vai trò."""
    manager = Account(email="mgr@example.com", role="MANAGER")
    assert manager.is_staff is True
    assert manager.is_superuser is True
    assert manager.has_perm("any_perm") is True
    assert manager.has_module_perms("any_module") is True

    employee = Account(email="emp@example.com", role="EMPLOYEE")
    assert employee.is_staff is False
    assert employee.is_superuser is False
    assert employee.has_perm("any_perm") is False
    assert employee.has_module_perms("any_module") is False

    customer = Account(phone="0911223344", role="CUSTOMER")
    assert customer.is_staff is False
    assert customer.is_superuser is False


def test_account_and_tokens_string_representations():
    """Kiểm tra định dạng chuỗi hiển thị (__str__) của Account và các mô hình Token."""
    # 1. Account có email
    acc_email = Account(id=10, email="user@example.com")
    assert str(acc_email) == "user@example.com"

    # 2. Account chỉ có phone
    acc_phone = Account(id=11, phone="0988776655")
    assert str(acc_phone) == "0988776655"

    # 3. Account không có cả hai (fallback)
    acc_none = Account(id=12)
    assert str(acc_none) == "Account #12"

    # 4. PersistentLoginToken
    token = PersistentLoginToken(id=1, series="SERIES123", account_id=10)
    assert str(token) == "Token series SERIES123 for Account #10"

    # 5. PasswordResetToken
    reset_token = PasswordResetToken(id=5, account_id=10)
    assert str(reset_token) == "ResetToken #5 for Account #10"


# ==============================================================================
# 5. Tests for apps/core/management/commands/load_sample_data.py
# ==============================================================================


def test_load_sample_data_production_guard():
    """Kiểm tra lệnh load_sample_data bị chặn trong môi trường production (DEBUG=False)."""
    with patch("apps.core.management.commands.load_sample_data.settings.DEBUG", False):
        with pytest.raises(CommandError) as exc:
            call_command("load_sample_data")
        assert "Loading sample data in production (DEBUG=False) is disallowed" in str(
            exc.value
        )


def test_load_sample_data_missing_seed_file():
    """Kiểm tra lệnh load_sample_data quăng CommandError nếu file db/02-seed.sql không tồn tại."""
    with patch("pathlib.Path.exists", return_value=False):
        with pytest.raises(CommandError) as exc:
            call_command("load_sample_data", force_production=True)
        assert "Seed file not found at" in str(exc.value)
