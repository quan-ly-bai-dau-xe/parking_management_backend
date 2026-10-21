"""
Tests for Custom Role-Based DRF Permissions per TL-01, TL-48 and Security Baseline.
Covers permission matrix (anonymous, CUSTOMER, EMPLOYEE, MANAGER) for IsManager and IsEmployeeOrManager.
Verifies standard error envelope:
- Anonymous caller -> HTTP 401 with code 'MSG-4.1-M02'
- CUSTOMER caller -> HTTP 403 with code 'MSG-4.2-M01'
"""

from unittest.mock import MagicMock

import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework import status
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.accounts.models import Account
from apps.core.permissions import IsEmployeeOrManager, IsManager

pytestmark = pytest.mark.django_db


class DummyEmployeeOrManagerView(APIView):
    """View giả lập áp dụng IsEmployeeOrManager."""

    permission_classes = [IsEmployeeOrManager]

    def get(self, request):
        return Response({"status": "success", "message": "OK"})


class DummyManagerOnlyView(APIView):
    """View giả lập áp dụng IsManager."""

    permission_classes = [IsManager]

    def get(self, request):
        return Response({"status": "success", "message": "OK"})


def test_is_manager_permission_matrix():
    """Kiểm tra ma trận quyền của IsManager."""
    perm = IsManager()
    view = MagicMock()

    # 1. Anonymous user
    req_anon = MagicMock()
    req_anon.user = AnonymousUser()
    assert perm.has_permission(req_anon, view) is False

    # 2. None user
    req_none = MagicMock()
    req_none.user = None
    assert perm.has_permission(req_none, view) is False

    # 3. Customer role
    req_customer = MagicMock()
    req_customer.user = Account(
        email="cust@example.com", role="CUSTOMER", is_active=True
    )
    assert perm.has_permission(req_customer, view) is False

    # 4. Employee role
    req_employee = MagicMock()
    req_employee.user = Account(
        email="emp@example.com", role="EMPLOYEE", is_active=True
    )
    assert perm.has_permission(req_employee, view) is False

    # 5. Manager role (Active)
    req_manager = MagicMock()
    req_manager.user = Account(email="mgr@example.com", role="MANAGER", is_active=True)
    assert perm.has_permission(req_manager, view) is True

    # 6. Manager role (Inactive)
    req_manager_inactive = MagicMock()
    req_manager_inactive.user = Account(
        email="mgr_inact@example.com", role="MANAGER", is_active=False
    )
    assert perm.has_permission(req_manager_inactive, view) is False


def test_is_employee_or_manager_permission_matrix():
    """Kiểm tra ma trận quyền của IsEmployeeOrManager."""
    perm = IsEmployeeOrManager()
    view = MagicMock()

    # 1. Anonymous user
    req_anon = MagicMock()
    req_anon.user = AnonymousUser()
    assert perm.has_permission(req_anon, view) is False

    # 2. None user
    req_none = MagicMock()
    req_none.user = None
    assert perm.has_permission(req_none, view) is False

    # 3. Customer role
    req_customer = MagicMock()
    req_customer.user = Account(
        email="cust@example.com", role="CUSTOMER", is_active=True
    )
    assert perm.has_permission(req_customer, view) is False

    # 4. Employee role (Active)
    req_employee = MagicMock()
    req_employee.user = Account(
        email="emp@example.com", role="EMPLOYEE", is_active=True
    )
    assert perm.has_permission(req_employee, view) is True

    # 5. Manager role (Active)
    req_manager = MagicMock()
    req_manager.user = Account(email="mgr@example.com", role="MANAGER", is_active=True)
    assert perm.has_permission(req_manager, view) is True

    # 6. Employee role (Inactive)
    req_emp_inactive = MagicMock()
    req_emp_inactive.user = Account(
        email="emp_inact@example.com", role="EMPLOYEE", is_active=False
    )
    assert perm.has_permission(req_emp_inactive, view) is False


def test_api_view_enforcement_anonymous_returns_401_envelope():
    """
    Kiểm tra gọi APIView khi chưa xác thực (anonymous):
    Bị từ chối với HTTP 401 Unauthorized và envelope chuẩn có mã MSG-4.1-M02.
    """
    factory = APIRequestFactory()
    request = factory.get("/api/v1/test-parking/")
    view = DummyEmployeeOrManagerView.as_view()

    response = view(request)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"
    assert (
        response.data["message"] == "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu"
    )


def test_api_view_enforcement_customer_returns_403_envelope():
    """
    Kiểm tra gọi APIView với role CUSTOMER:
    Bị từ chối với HTTP 403 Forbidden và envelope chuẩn có mã MSG-4.2-M01.
    """
    factory = APIRequestFactory()
    request = factory.get("/api/v1/test-parking/")
    customer_user = Account.objects.create_user(
        email="customer_test@example.com",
        password="Password123!",
        role="CUSTOMER",
    )
    request.user = customer_user

    view = DummyEmployeeOrManagerView.as_view()
    response = view(request)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"
    assert response.data["message"] == "Bạn không có quyền thực hiện thao tác này."


def test_api_view_enforcement_employee_success_on_employee_view():
    """Kiểm tra gọi APIView với role EMPLOYEE thành công trên DummyEmployeeOrManagerView."""
    factory = APIRequestFactory()
    request = factory.get("/api/v1/test-parking/")
    employee_user = Account.objects.create_user(
        email="employee_test@example.com",
        password="Password123!",
        role="EMPLOYEE",
    )
    request.user = employee_user

    view = DummyEmployeeOrManagerView.as_view()
    response = view(request)

    assert response.status_code == status.HTTP_200_OK
    assert response.data["status"] == "success"


def test_api_view_enforcement_employee_rejected_on_manager_only_view():
    """Kiểm tra gọi APIView với role EMPLOYEE bị từ chối 403 trên DummyManagerOnlyView."""
    factory = APIRequestFactory()
    request = factory.get("/api/v1/test-manager/")
    employee_user = Account.objects.create_user(
        email="employee_mgr_test@example.com",
        password="Password123!",
        role="EMPLOYEE",
    )
    request.user = employee_user

    view = DummyManagerOnlyView.as_view()
    response = view(request)

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"


def test_api_view_enforcement_manager_success_on_both_views():
    """Kiểm tra role MANAGER vượt qua kiểm tra quyền trên cả 2 view."""
    factory = APIRequestFactory()
    manager_user = Account.objects.create_user(
        email="manager_test@example.com",
        password="Password123!",
        role="MANAGER",
    )

    # 1. DummyEmployeeOrManagerView
    req1 = factory.get("/api/v1/test-parking/")
    req1.user = manager_user
    resp1 = DummyEmployeeOrManagerView.as_view()(req1)
    assert resp1.status_code == status.HTTP_200_OK

    # 2. DummyManagerOnlyView
    req2 = factory.get("/api/v1/test-manager/")
    req2.user = manager_user
    resp2 = DummyManagerOnlyView.as_view()(req2)
    assert resp2.status_code == status.HTTP_200_OK
