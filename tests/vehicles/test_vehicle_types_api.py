"""
Tests for Vehicle Types API (GET /api/v1/vehicle-types/).

Verifies:
- Car-only fleet scope: returns strictly 'CAR' and 'EV' (OQ-49, TL-20, TL-35).
- Motorbike exclusion (TRC-FE-04-04): confirms absence of motorbike types.
- Payload schema: id, code, name, description.
- Permission matrix: Anonymous -> 401, Customer -> 403, Employee -> 200, Manager -> 200.
- HTTP method restrictions: POST/PUT/PATCH/DELETE -> 405 Method Not Allowed.
"""

import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db

ENDPOINT_URL = "/api/v1/vehicle-types/"


def test_vehicle_types_list_car_and_ev_only(employee_client):
    """
    GET /api/v1/vehicle-types/ returns strictly CAR and EV types.
    Confirms zero motorbike support per TL-09, TL-20, TL-35, and TRC-FE-04-04.
    """
    response = employee_client.get(ENDPOINT_URL)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 2

    codes = [item["code"] for item in data]
    assert sorted(codes) == ["CAR", "EV"]

    # Verify no motorbike code or name exists
    for item in data:
        assert item["code"] not in ("MOTO", "MOTORBIKE", "XE_MAY", "BIKE")
        assert "xe máy" not in item["name"].lower()
        assert "mô tô" not in item["name"].lower()
        assert set(item.keys()) == {"id", "code", "name", "description"}
        assert isinstance(item["id"], int)
        assert len(item["code"]) > 0
        assert len(item["name"]) > 0


def test_vehicle_types_manager_can_access(manager_client):
    """Quản lý (MANAGER) có quyền truy cập danh mục loại xe -> 200 OK."""
    response = manager_client.get(ENDPOINT_URL)
    assert response.status_code == status.HTTP_200_OK
    assert len(response.json()) == 2


def test_vehicle_types_anonymous_rejected(anonymous_client):
    """Người dùng chưa đăng nhập gọi API -> 401 Unauthorized (MSG-4.1-M02)."""
    response = anonymous_client.get(ENDPOINT_URL)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.json().get("code") == "MSG-4.1-M02"


def test_vehicle_types_customer_forbidden(customer_client):
    """Khách hàng (CUSTOMER) bị từ chối truy cập -> 403 Forbidden (MSG-4.2-M01)."""
    response = customer_client.get(ENDPOINT_URL)
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.json().get("code") == "MSG-4.2-M01"


@pytest.mark.parametrize("method", ["post", "put", "patch", "delete"])
def test_vehicle_types_disallowed_methods(manager_client, method):
    """Các phương thức ghi bị chặn trên endpoint loại xe -> 405 Method Not Allowed."""
    client_method = getattr(manager_client, method)
    response = client_method(ENDPOINT_URL, {})
    assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED
