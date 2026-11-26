"""
Tests for Ticket List & Ticket Types API (GET /api/v1/tickets/ and GET /api/v1/ticket-types/).
Covers:
- Pagination, status filter, ticket_type filter, search keyword.
- Zero N+1 query assertion via django_assert_num_queries.
- RBAC permissions (Anonymous -> 401, Customer -> 403, Employee/Manager -> 200).
- TicketType catalog endpoint.
"""

from __future__ import annotations

import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db

TICKETS_URL = "/api/v1/tickets/"
TICKET_TYPES_URL = "/api/v1/ticket-types/"


def test_ticket_types_list(employee_client):
    """GET /api/v1/ticket-types/ trả về danh mục 4 loại vé chuẩn."""
    response = employee_client.get(TICKET_TYPES_URL)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert isinstance(data, list)
    codes = [item["code"] for item in data]
    assert "DAILY" in codes
    assert "MONTHLY" in codes
    assert "QUARTERLY" in codes
    assert "YEARLY" in codes


def test_ticket_list_pagination(employee_client):
    """GET /api/v1/tickets/ trả về phong bì phân trang chuẩn {count, next, previous, results}."""
    response = employee_client.get(f"{TICKETS_URL}?page=1&page_size=5")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "count" in data
    assert "results" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) <= 5

    # Kiểm tra các trường dữ liệu bắt buộc của 1 ticket
    if data["results"]:
        first = data["results"][0]
        assert "id" in first
        assert "code" in first
        assert "customer_name" in first
        assert "license_plate" in first
        assert "ticket_type" in first
        assert "effective_from" in first
        assert "effective_to" in first
        assert "status" in first
        assert "row_version" in first


def test_ticket_list_filter_status(employee_client):
    """Lọc danh sách vé theo status=ACTIVE hoặc status=EXPIRED."""
    res_active = employee_client.get(f"{TICKETS_URL}?status=ACTIVE")
    assert res_active.status_code == status.HTTP_200_OK
    for t in res_active.json()["results"]:
        assert t["status"] == "ACTIVE"

    res_expired = employee_client.get(f"{TICKETS_URL}?status=EXPIRED")
    assert res_expired.status_code == status.HTTP_200_OK
    for t in res_expired.json()["results"]:
        assert t["status"] == "EXPIRED"


def test_ticket_list_filter_ticket_type(employee_client):
    """Lọc danh sách vé theo loại vé: DAILY hoặc MONTHLY."""
    res_daily = employee_client.get(f"{TICKETS_URL}?ticket_type=DAILY")
    assert res_daily.status_code == status.HTTP_200_OK
    for t in res_daily.json()["results"]:
        assert t["ticket_type_code"] == "DAILY"

    res_monthly = employee_client.get(f"{TICKETS_URL}?ticket_type=MONTHLY")
    assert res_monthly.status_code == status.HTTP_200_OK
    for t in res_monthly.json()["results"]:
        assert t["ticket_type_code"] == "MONTHLY"


def test_ticket_list_search_license_plate(employee_client):
    """Tìm kiếm vé theo biển số xe hoặc mã vé."""
    # Tìm kiếm theo biển số xe
    res_search = employee_client.get(f"{TICKETS_URL}?q=43P-163.22")
    assert res_search.status_code == status.HTTP_200_OK
    results = res_search.json()["results"]
    assert len(results) >= 1
    assert any("43P-163.22" in t["license_plate"] for t in results)

    # Tìm kiếm theo mã vé
    res_code = employee_client.get(f"{TICKETS_URL}?q=VT0022")
    assert res_code.status_code == status.HTTP_200_OK
    results_code = res_code.json()["results"]
    assert len(results_code) >= 1
    assert any(t["code"] == "VT0022" for t in results_code)


def test_ticket_list_zero_n_plus_one_queries(
    employee_client, django_assert_num_queries
):
    """
    Khẳng định Zero N+1 queries:
    Truy vấn lấy 5 vé hay 20 vé đều không làm tăng số câu lệnh SQL theo số bản ghi.
    Bao gồm select_related và prefetch_related cho renewals.
    """
    # Làm ấm kết nối và cache
    employee_client.get(f"{TICKETS_URL}?page=1&page_size=5")

    # Đo số truy vấn khi lấy 5 bản ghi vs 15 bản ghi
    # Với selector tối ưu: 1 count query + 1 ticket query (select_related) + 1 renewals prefetch query = 3 queries cố định (hoặc kèm session/user auth)
    with django_assert_num_queries(3):
        res = employee_client.get(f"{TICKETS_URL}?page=1&page_size=10")
        assert res.status_code == status.HTTP_200_OK


def test_ticket_list_permissions(
    anonymous_client, customer_client, employee_client, manager_client
):
    """
    Phân quyền truy cập Ticket List:
    - Anonymous -> 401 Unauthorized
    - Customer -> 403 Forbidden
    - Employee -> 200 OK
    - Manager -> 200 OK
    """
    assert anonymous_client.get(TICKETS_URL).status_code == status.HTTP_401_UNAUTHORIZED
    assert customer_client.get(TICKETS_URL).status_code == status.HTTP_403_FORBIDDEN
    assert employee_client.get(TICKETS_URL).status_code == status.HTTP_200_OK
    assert manager_client.get(TICKETS_URL).status_code == status.HTTP_200_OK
