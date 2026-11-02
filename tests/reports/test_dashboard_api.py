"""
Integration tests for Dashboard / Reports API (Trang chủ — Smart Mobility.png).
Verifies:
- Permission matrix: anonymous -> 401, CUSTOMER -> 403, EMPLOYEE -> 200 (revenue hidden), MANAGER -> 200 (full).
- Contract verification: kpis, floors (TL-28.6), traffic_chart 24h, alerts (TL-13), recent_activities.
- Sub-endpoints: /kpis/, /floors/, /traffic/, /alerts/, /activities/.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager_account():
    mgr, _ = Account.objects.get_or_create(
        email="mgr_dashboard@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return mgr


@pytest.fixture
def employee_account():
    emp, _ = Account.objects.get_or_create(
        email="emp_dashboard@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def customer_account():
    cust, _ = Account.objects.get_or_create(
        email="cust_dashboard@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return cust


def test_dashboard_overview_anonymous_rejected():
    """Chưa đăng nhập -> 401 Unauthorized."""
    client = APIClient()
    response = client.get("/api/v1/dashboard/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_dashboard_overview_customer_forbidden(customer_account):
    """Khách hàng (CUSTOMER) bị từ chối truy cập Dashboard -> 403 Forbidden."""
    client = APIClient()
    client.force_authenticate(user=customer_account)
    response = client.get("/api/v1/dashboard/")
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_dashboard_overview_manager_full_access(manager_account):
    """Quản lý (MANAGER) truy cập thành công và thấy đầy đủ cả tài chính."""
    client = APIClient()
    client.force_authenticate(user=manager_account)
    response = client.get("/api/v1/dashboard/")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # Khẳng định 5 phần dữ liệu cốt lõi của Trang chủ
    assert "kpis" in data
    assert "floors" in data
    assert "traffic_chart" in data
    assert "alerts" in data
    assert "recent_activities" in data

    # Kiểm tra cấu trúc KPIs
    kpis = data["kpis"]
    assert "slots" in kpis
    assert "traffic" in kpis
    assert "revenue" in kpis
    assert "ai_recognition" in kpis

    # MANAGER có quyền xem số liệu doanh thu (revenue không phải None)
    assert kpis["revenue"] is not None
    assert "total_revenue" in kpis["revenue"]
    assert "cash_revenue" in kpis["revenue"]
    assert "vietqr_revenue" in kpis["revenue"]

    # Kiểm tra cấu trúc slots KPI
    slots = kpis["slots"]
    assert "total_slots" in slots
    assert "occupancy_rate_pct" in slots
    assert "status_text" in slots

    # Kiểm tra cấu trúc thanh tỷ lệ các tầng (TL-28.6)
    assert isinstance(data["floors"], list)

    # Kiểm tra cấu trúc biểu đồ 24h
    assert isinstance(data["traffic_chart"], list)

    # Kiểm tra cảnh báo và hoạt động
    assert isinstance(data["alerts"], list)
    assert isinstance(data["recent_activities"], list)


def test_dashboard_overview_employee_revenue_masked(employee_account):
    """Nhân viên (EMPLOYEE) truy cập được Dashboard nhưng revenue bị ẩn per Rule 01 Section 2."""
    client = APIClient()
    client.force_authenticate(user=employee_account)
    response = client.get("/api/v1/dashboard/")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    # revenue phải là None đối với vai trò Employee
    assert data["kpis"]["revenue"] is None

    # Các thông tin vận hành khác vẫn xem được bình thường
    assert "slots" in data["kpis"]
    assert "traffic" in data["kpis"]
    assert "ai_recognition" in data["kpis"]


def test_dashboard_kpis_endpoint(manager_account):
    """Kiểm tra endpoint /api/v1/dashboard/kpis/ độc lập."""
    client = APIClient()
    client.force_authenticate(user=manager_account)
    response = client.get("/api/v1/dashboard/kpis/")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "slots" in data
    assert "traffic" in data
    assert "revenue" in data
    assert "ai_recognition" in data


def test_dashboard_floors_endpoint(manager_account):
    """Kiểm tra endpoint /api/v1/dashboard/floors/ độc lập."""
    client = APIClient()
    client.force_authenticate(user=manager_account)
    response = client.get("/api/v1/dashboard/floors/")

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)


def test_dashboard_traffic_endpoint(manager_account):
    """Kiểm tra endpoint /api/v1/dashboard/traffic/ độc lập."""
    client = APIClient()
    client.force_authenticate(user=manager_account)
    response = client.get("/api/v1/dashboard/traffic/")

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)


def test_dashboard_alerts_endpoint(manager_account):
    """Kiểm tra endpoint /api/v1/dashboard/alerts/ độc lập."""
    client = APIClient()
    client.force_authenticate(user=manager_account)
    response = client.get("/api/v1/dashboard/alerts/")

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)


def test_dashboard_activities_endpoint(manager_account):
    """Kiểm tra endpoint /api/v1/dashboard/activities/ độc lập."""
    client = APIClient()
    client.force_authenticate(user=manager_account)
    response = client.get("/api/v1/dashboard/activities/")

    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.json(), list)

