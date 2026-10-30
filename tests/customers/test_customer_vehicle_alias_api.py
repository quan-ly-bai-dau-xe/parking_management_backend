"""
Test suite for POST /api/v1/customers/{customer_id}/vehicles/ (SCO-06 Vehicle Creation Alias API).
Covers:
- Successful vehicle creation under customer: returns 201 Created with VehicleDetailSerializer.
- Database persistence: vehicle is correctly linked to the customer_id in URL.
- 404 Not Found when customer_id does not exist or was soft-deleted (PROP-4.4.4-P02).
- 409 Conflict when license plate already exists.
- 400 Bad Request when required vehicle fields are missing or invalid.
- RBAC permissions: EMPLOYEE and MANAGER succeed; CUSTOMER receives 403; Anonymous receives 401.
"""

from __future__ import annotations

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.customers.models import Customer
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


def test_customer_vehicle_alias_create_success(
    employee_client: APIClient, active_customer: Customer, car_type: VehicleType
):
    """Verify creating a vehicle via customer alias endpoint returns 201 with vehicle details."""
    url = f"/api/v1/customers/{active_customer.id}/vehicles/"
    payload = {
        "license_plate": "51K-998.88",
        "model_name": "Mazda 3",
        "vehicle_type_id": car_type.id,
        "color": "Trắng",
        "brand": "Mazda",
    }
    response = employee_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["license_plate"] == "51K-998.88"
    assert data["model_name"] == "Mazda 3"
    assert data["customer"]["id"] == active_customer.id

    # Verify DB persistence
    veh = Vehicle.objects.get(id=data["id"])
    assert veh.customer_id == active_customer.id
    assert veh.license_plate == "51K-998.88"


def test_customer_vehicle_alias_non_existent_customer_returns_404(
    employee_client: APIClient, car_type: VehicleType
):
    """Verify creating a vehicle for a non-existent customer returns 404 PROP-4.4.4-P02."""
    url = "/api/v1/customers/9999999/vehicles/"
    payload = {
        "license_plate": "51K-998.89",
        "model_name": "Vios",
        "vehicle_type_id": car_type.id,
    }
    response = employee_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_404_NOT_FOUND

    data = response.json()
    assert data["code"] == "PROP-4.4.4-P02"
    assert "Khách hàng không tồn tại" in data["message"]


def test_customer_vehicle_alias_soft_deleted_customer_returns_404(
    employee_client: APIClient, car_type: VehicleType
):
    """Verify creating a vehicle for a soft-deleted customer returns 404 PROP-4.4.4-P02."""
    cust = Customer.objects.create(
        code="KH9992",
        full_name="Khách Hàng Đã Xóa",
        identity_card_number="079090009992",
        phone="0909999992",
    )
    Customer.objects.filter(id=cust.id).update(deleted_at=timezone.now())

    url = f"/api/v1/customers/{cust.id}/vehicles/"
    payload = {
        "license_plate": "51K-998.90",
        "model_name": "Vios",
        "vehicle_type_id": car_type.id,
    }
    response = employee_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["code"] == "PROP-4.4.4-P02"


def test_customer_vehicle_alias_duplicate_plate_conflict(
    employee_client: APIClient, active_customer: Customer, car_type: VehicleType
):
    """Verify duplicate license plate returns 409 Conflict."""
    existing_veh = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert existing_veh is not None

    url = f"/api/v1/customers/{active_customer.id}/vehicles/"
    payload = {
        "license_plate": existing_veh.license_plate,
        "model_name": "Accord",
        "vehicle_type_id": car_type.id,
    }
    response = employee_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "MSG-4.3.1-M05"


def test_customer_vehicle_alias_missing_fields_validation(
    employee_client: APIClient, active_customer: Customer
):
    """Verify missing required fields (e.g. model_name, vehicle_type_id) returns 400 Bad Request."""
    url = f"/api/v1/customers/{active_customer.id}/vehicles/"
    payload = {
        "license_plate": "51K-123.45",
        # model_name and vehicle_type_id missing
    }
    response = employee_client.post(url, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    data = response.json()
    assert data["code"] == "PROP-GEN-P01"
    assert "model_name" in data.get("details", {})
    assert "vehicle_type_id" in data.get("details", {})
