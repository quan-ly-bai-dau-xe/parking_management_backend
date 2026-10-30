"""
Exhaustive Role-Based Access Control (RBAC) Permissions Matrix Tests.

Covers all 8 endpoints across 4 principal roles:
- ANONYMOUS (unauthenticated): 401 Unauthorized (MSG-4.1-M02)
- CUSTOMER: 403 Forbidden (MSG-4.2-M01)
- EMPLOYEE: 200/201 OK on all operations (reads and writes per Task V0)
- MANAGER: 200/201 OK on all operations
"""

import pytest
from rest_framework import status

from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture
def test_vehicle(car_type, active_customer):
    """Creates a dedicated unblocked vehicle for permissions testing."""
    return Vehicle.objects.create(
        code="XE-PERM-01",
        license_plate="51K-777.77",
        license_plate_norm="51K77777",
        model_name="VF6",
        brand="VinFast",
        color="Bạc",
        vehicle_type=car_type,
        customer=active_customer,
    )


READ_ENDPOINTS = [
    ("GET", "/api/v1/vehicle-types/"),
    ("GET", "/api/v1/vehicles/"),
    ("GET", "/api/v1/vehicles/summary/"),
    ("GET", "/api/v1/vehicles/export/"),
]


@pytest.mark.parametrize("http_method,url", READ_ENDPOINTS)
def test_read_endpoints_anonymous_unauthorized(anonymous_client, http_method, url):
    """Người dùng chưa đăng nhập gọi endpoint đọc -> 401 Unauthorized."""
    response = anonymous_client.get(url)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json().get("code") == "MSG-4.1-M02"


@pytest.mark.parametrize("http_method,url", READ_ENDPOINTS)
def test_read_endpoints_customer_forbidden(customer_client, http_method, url):
    """Khách hàng gọi endpoint đọc -> 403 Forbidden."""
    response = customer_client.get(url)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json().get("code") == "MSG-4.2-M01"


@pytest.mark.parametrize("http_method,url", READ_ENDPOINTS)
def test_read_endpoints_employee_allowed(employee_client, http_method, url):
    """Nhân viên gọi endpoint đọc -> 200 OK."""
    response = employee_client.get(url)
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.parametrize("http_method,url", READ_ENDPOINTS)
def test_read_endpoints_manager_allowed(manager_client, http_method, url):
    """Quản lý gọi endpoint đọc -> 200 OK."""
    response = manager_client.get(url)
    assert response.status_code == status.HTTP_200_OK


def test_detail_endpoint_permissions_matrix(
    anonymous_client, customer_client, employee_client, manager_client, test_vehicle
):
    """Ma trận phân quyền trên GET /api/v1/vehicles/{id}/."""
    url = f"/api/v1/vehicles/{test_vehicle.id}/"

    # Anonymous -> 401
    assert anonymous_client.get(url).status_code == status.HTTP_401_UNAUTHORIZED
    # Customer -> 403
    assert customer_client.get(url).status_code == status.HTTP_403_FORBIDDEN
    # Employee -> 200
    assert employee_client.get(url).status_code == status.HTTP_200_OK
    # Manager -> 200
    assert manager_client.get(url).status_code == status.HTTP_200_OK


def test_create_endpoint_permissions_matrix(
    anonymous_client,
    customer_client,
    employee_client,
    manager_client,
    car_type,
    active_customer,
):
    """Ma trận phân quyền trên POST /api/v1/vehicles/."""
    url = "/api/v1/vehicles/"
    payload_employee = {
        "license_plate": "51K-888.88",
        "model_name": "VF7",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    payload_manager = {
        "license_plate": "51K-888.89",
        "model_name": "VF7",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }

    # Anonymous -> 401
    assert (
        anonymous_client.post(url, payload_employee, format="json").status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    # Customer -> 403
    assert (
        customer_client.post(url, payload_employee, format="json").status_code
        == status.HTTP_403_FORBIDDEN
    )
    # Employee -> 201 Created (Task V0: Employee được phép tạo xe)
    assert (
        employee_client.post(url, payload_employee, format="json").status_code
        == status.HTTP_201_CREATED
    )
    # Manager -> 201 Created (dùng payload riêng để tránh trùng lặp biển số)
    assert (
        manager_client.post(url, payload_manager, format="json").status_code
        == status.HTTP_201_CREATED
    )


def test_update_endpoint_permissions_matrix(
    anonymous_client, customer_client, employee_client, manager_client, test_vehicle
):
    """Ma trận phân quyền trên PATCH /api/v1/vehicles/{id}/."""
    url = f"/api/v1/vehicles/{test_vehicle.id}/"
    payload = {
        "row_version": test_vehicle.row_version,
        "color": "Tím than",
    }

    # Anonymous -> 401
    assert (
        anonymous_client.patch(url, payload, format="json").status_code
        == status.HTTP_401_UNAUTHORIZED
    )
    # Customer -> 403
    assert (
        customer_client.patch(url, payload, format="json").status_code
        == status.HTTP_403_FORBIDDEN
    )
    # Employee -> 200 OK (Task V0: Employee được phép cập nhật)
    assert (
        employee_client.patch(url, payload, format="json").status_code
        == status.HTTP_200_OK
    )
    # OCC: Khi Employee patch thành công, row_version tăng từ 1 -> 2
    # Cần refresh_from_db để Manager không bị 409 Conflict do stale row_version
    test_vehicle.refresh_from_db()
    payload["row_version"] = test_vehicle.row_version
    payload["color"] = "Xanh lục"

    # Manager -> 200 OK
    assert (
        manager_client.patch(url, payload, format="json").status_code
        == status.HTTP_200_OK
    )


def test_delete_endpoint_permissions_matrix(
    anonymous_client,
    customer_client,
    employee_client,
    manager_client,
    car_type,
    active_customer,
):
    """Ma trận phân quyền trên DELETE /api/v1/vehicles/{id}/."""
    # Tạo 2 xe riêng để tránh xung đột đã bị xóa (404) khi Employee và Manager cùng test
    v_emp = Vehicle.objects.create(
        code="XE-DEL-P01",
        license_plate="51K-666.66",
        license_plate_norm="51K66666",
        model_name="VF5",
        vehicle_type=car_type,
        customer=active_customer,
    )
    v_mgr = Vehicle.objects.create(
        code="XE-DEL-P02",
        license_plate="51K-666.67",
        license_plate_norm="51K66667",
        model_name="VF5",
        vehicle_type=car_type,
        customer=active_customer,
    )
    url_emp = f"/api/v1/vehicles/{v_emp.id}/"
    url_mgr = f"/api/v1/vehicles/{v_mgr.id}/"

    # Anonymous -> 401
    assert anonymous_client.delete(url_emp).status_code == status.HTTP_401_UNAUTHORIZED
    # Customer -> 403
    assert customer_client.delete(url_emp).status_code == status.HTTP_403_FORBIDDEN
    # Employee -> 200 OK (Task V0: Employee được phép xóa)
    assert employee_client.delete(url_emp).status_code == status.HTTP_200_OK
    # Manager -> 200 OK (xóa trên xe riêng v_mgr)
    assert manager_client.delete(url_mgr).status_code == status.HTTP_200_OK
