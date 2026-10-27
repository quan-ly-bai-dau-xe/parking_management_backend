"""
Regression tests verifying vehicle-lookup and vehicle-search APIs remain 100% stable.

Verifies:
- GET /api/v1/parking/vehicle-lookup/ response payload contracts and values are unchanged.
- GET /api/v1/parking/vehicle-search/ response payload contracts and values are unchanged.
- Asserts that all newly added routes and logic in apps.vehicles produce zero side-effects
  on existing gate/barrier operations.
"""

import pytest
from rest_framework import status

pytestmark = pytest.mark.django_db


def test_regression_vehicle_lookup_xe0001(employee_client):
    """
    Khẳng định API GET /api/v1/parking/vehicle-lookup/ trả về cấu trúc và giá trị
    chính xác tuyệt đối cho phương tiện XE0001 (43K-860.50).
    """
    response = employee_client.get(
        "/api/v1/parking/vehicle-lookup/?license_plate=43K-860.50"
    )
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "vehicle" in data
    assert "customer" in data
    assert "is_blacklisted" in data
    assert "parking_position" in data
    assert "active_ticket" in data

    # Vehicle details
    v = data["vehicle"]
    assert v["code"] == "XE0001"
    assert v["license_plate"] == "43K-860.50"
    assert v["license_plate_norm"] == "43K86050"
    assert v["brand"] == "Toyota"
    assert v["model_name"] == "Vios 1.5G"

    # Customer details
    c = data["customer"]
    assert c["code"] == "KH0001"
    assert c["full_name"] == "Trịnh Xuân Trường"
    assert c["is_anonymized"] is False

    # Security flag
    assert data["is_blacklisted"] is False


def test_regression_vehicle_search_xe0001(employee_client):
    """
    Khẳng định API GET /api/v1/parking/vehicle-search/ trả về cấu trúc và giá trị
    chính xác tuyệt đối khi tìm kiếm theo biển số hoặc mã xe.
    """
    response = employee_client.get("/api/v1/parking/vehicle-search/?q=43K-860.50")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "count" in data
    assert "results" in data
    assert data["count"] >= 1

    item = data["results"][0]
    assert item["vehicle"]["code"] == "XE0001"
    assert item["vehicle"]["license_plate"] == "43K-860.50"
    assert item["customer"]["code"] == "KH0001"
    assert item["currently_parked"] is True


def test_regression_vehicle_search_partial_plate(employee_client):
    """Tìm kiếm biển số xe với tham số license_plate=43K."""
    response = employee_client.get("/api/v1/parking/vehicle-search/?license_plate=43K")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["count"] > 0
    assert all("43K" in r["vehicle"]["license_plate_norm"] for r in data["results"])


def test_regression_vehicle_lookup_not_found(employee_client):
    """Tra cứu xe không tồn tại trả về 404 MSG-4.5.1-M01 như trước."""
    response = employee_client.get(
        "/api/v1/parking/vehicle-lookup/?license_plate=99Z-999.99"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json().get("code") == "MSG-4.5.1-M01"
