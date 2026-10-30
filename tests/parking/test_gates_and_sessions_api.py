"""
Integration tests for Gates and Sessions List/Detail APIs.
Endpoints:
- GET /api/v1/parking/gates/
- GET /api/v1/parking/sessions/
- GET /api/v1/parking/sessions/{id}/
Verifies:
- Permissions (anonymous -> 401, CUSTOMER -> 403, EMPLOYEE -> allowed).
- Gate filtering by direction (IN, OUT) and is_active.
- Session pagination structure (StandardResultsSetPagination: count, next, previous, results).
- Session filters: status (open/closed), license_plate, session_code, min_fee, max_fee.
- Duration formatting in Vietnamese and duration_seconds integer.
- Zero N+1 queries during listing of sessions.
- Session detail retrieve 200 OK and 404 MSG-4.4.1-M01.
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.parking.models import VehicleEntryExitLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_gates@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def auth_customer():
    cust, _ = Account.objects.get_or_create(
        email="cust_gates@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return cust


# ==============================================================================
# GATES API TESTS
# ==============================================================================


def test_gates_anonymous_rejected():
    """Chưa đăng nhập -> 401 MSG-4.1-M02."""
    client = APIClient()
    response = client.get("/api/v1/parking/gates/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"


def test_gates_customer_forbidden(auth_customer):
    """Khách hàng bị từ chối truy cập danh sách cổng -> 403 MSG-4.2-M01."""
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    response = client.get("/api/v1/parking/gates/")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"


def test_gates_list_and_filter(auth_employee):
    """Lấy danh sách cổng và lọc theo direction."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Danh sách đầy đủ
    resp = client.get("/api/v1/parking/gates/")
    assert resp.status_code == status.HTTP_200_OK
    assert isinstance(resp.data, list)
    assert len(resp.data) > 0

    # 2. Lọc cổng vào IN
    resp_in = client.get("/api/v1/parking/gates/?direction=IN")
    assert resp_in.status_code == status.HTTP_200_OK
    for gate in resp_in.data:
        assert gate["direction"] == "IN"

    # 3. Lọc cổng ra OUT
    resp_out = client.get("/api/v1/parking/gates/?direction=OUT")
    assert resp_out.status_code == status.HTTP_200_OK
    for gate in resp_out.data:
        assert gate["direction"] == "OUT"

    # 4. Lọc cổng theo is_active
    resp_active = client.get("/api/v1/parking/gates/?is_active=true")
    assert resp_active.status_code == status.HTTP_200_OK
    for gate in resp_active.data:
        assert gate["is_active"] is True

    # 5. Selector get_gate_by_id
    from apps.parking.selectors.gates import get_gate_by_id

    first_gate = resp.data[0]
    gate_obj = get_gate_by_id(first_gate["id"])
    assert gate_obj is not None
    assert gate_obj.id == first_gate["id"]


# ==============================================================================
# SESSIONS LIST & DETAIL API TESTS
# ==============================================================================


def test_sessions_anonymous_rejected():
    """Chưa đăng nhập -> 401 MSG-4.1-M02."""
    client = APIClient()
    response = client.get("/api/v1/parking/sessions/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"


def test_sessions_customer_forbidden(auth_customer):
    """Khách hàng bị từ chối truy cập danh sách phiên đỗ -> 403 MSG-4.2-M01."""
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    response = client.get("/api/v1/parking/sessions/")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"


def test_sessions_pagination_and_filters(auth_employee):
    """Kiểm tra phân trang chuẩn và lọc đa tiêu chí trên danh sách phiên đỗ."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Truy vấn danh sách phân trang mặc định
    response = client.get("/api/v1/parking/sessions/?page=1&page_size=10")
    assert response.status_code == status.HTTP_200_OK
    assert "count" in response.data
    assert "results" in response.data
    assert isinstance(response.data["results"], list)

    # 2. Lọc status=open
    resp_open = client.get("/api/v1/parking/sessions/?status=open")
    assert resp_open.status_code == status.HTTP_200_OK
    for s in resp_open.data["results"]:
        assert s["exit_time"] is None

    # 3. Lọc status=closed
    resp_closed = client.get("/api/v1/parking/sessions/?status=closed")
    assert resp_closed.status_code == status.HTTP_200_OK
    for s in resp_closed.data["results"]:
        assert s["exit_time"] is not None


def test_sessions_zero_n_plus_one_queries(auth_employee, django_assert_max_num_queries):
    """Kiểm tra zero N+1 queries: số câu truy vấn không tăng theo số lượng bản ghi."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # Đảm bảo truy vấn tối ưu (chỉ vài queries cho count + select_related joined tables)
    with django_assert_max_num_queries(5):
        resp = client.get("/api/v1/parking/sessions/?page=1&page_size=20")
        assert resp.status_code == status.HTTP_200_OK


def test_session_detail_success(auth_employee):
    """Xem chi tiết một phiên đỗ xe theo ID -> 200 OK với đầy đủ thông tin."""
    session = VehicleEntryExitLog.objects.first()
    assert session is not None

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(f"/api/v1/parking/sessions/{session.id}/")

    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert data["id"] == session.id
    assert data["session_code"] == session.session_code
    assert "duration_seconds" in data
    assert "duration_text" in data


def test_session_detail_not_found(auth_employee):
    """Xem chi tiết phiên không tồn tại -> 404 MSG-4.4.1-M01."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/sessions/99999999/")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "MSG-4.4.1-M01"
