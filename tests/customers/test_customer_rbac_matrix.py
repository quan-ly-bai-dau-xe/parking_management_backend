"""
RBAC Matrix tests for Customer Management API per SRS 4.4.1–4.4.5 and Security Baseline.
Verifies permission enforcement across all 7 customer endpoints for:
- MANAGER: Allowed (200 / 201)
- EMPLOYEE: Allowed (200 / 201)
- CUSTOMER: Forbidden (403)
- ANONYMOUS: Unauthorized (401)
"""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.customers.models import Customer
from apps.vehicles.models import VehicleType

pytestmark = pytest.mark.django_db


def test_rbac_customer_list(
    manager_client: APIClient,
    employee_client: APIClient,
    customer_client: APIClient,
    anonymous_client: APIClient,
):
    """GET /api/v1/customers/: EMPLOYEE/MANAGER allow; CUSTOMER 403; Anonymous 401."""
    url = "/api/v1/customers/"
    assert manager_client.get(url).status_code == status.HTTP_200_OK
    assert employee_client.get(url).status_code == status.HTTP_200_OK
    assert customer_client.get(url).status_code == status.HTTP_403_FORBIDDEN
    assert anonymous_client.get(url).status_code == status.HTTP_401_UNAUTHORIZED


def test_rbac_customer_summary(
    manager_client: APIClient,
    employee_client: APIClient,
    customer_client: APIClient,
    anonymous_client: APIClient,
):
    """GET /api/v1/customers/summary/: EMPLOYEE/MANAGER allow; CUSTOMER 403; Anonymous 401."""
    url = "/api/v1/customers/summary/"
    assert manager_client.get(url).status_code == status.HTTP_200_OK
    assert employee_client.get(url).status_code == status.HTTP_200_OK
    assert customer_client.get(url).status_code == status.HTTP_403_FORBIDDEN
    assert anonymous_client.get(url).status_code == status.HTTP_401_UNAUTHORIZED


def test_rbac_customer_detail(
    manager_client: APIClient,
    employee_client: APIClient,
    customer_client: APIClient,
    anonymous_client: APIClient,
    active_customer: Customer,
):
    """GET /api/v1/customers/{id}/: EMPLOYEE/MANAGER allow; CUSTOMER 403; Anonymous 401."""
    url = f"/api/v1/customers/{active_customer.id}/"
    assert manager_client.get(url).status_code == status.HTTP_200_OK
    assert employee_client.get(url).status_code == status.HTTP_200_OK
    assert customer_client.get(url).status_code == status.HTTP_403_FORBIDDEN
    assert anonymous_client.get(url).status_code == status.HTTP_401_UNAUTHORIZED


def test_rbac_customer_create(
    manager_client: APIClient,
    employee_client: APIClient,
    customer_client: APIClient,
    anonymous_client: APIClient,
):
    """POST /api/v1/customers/: EMPLOYEE/MANAGER allow; CUSTOMER 403; Anonymous 401."""
    url = "/api/v1/customers/"

    # Anonymous -> 401
    assert (
        anonymous_client.post(
            url,
            {
                "full_name": "Test",
                "identity_card_number": "079090008811",
                "phone": "0908811001",
            },
            format="json",
        ).status_code
        == status.HTTP_401_UNAUTHORIZED
    )

    # Customer -> 403
    assert (
        customer_client.post(
            url,
            {
                "full_name": "Test",
                "identity_card_number": "079090008812",
                "phone": "0908811002",
            },
            format="json",
        ).status_code
        == status.HTTP_403_FORBIDDEN
    )

    # Employee -> 201
    res_emp = employee_client.post(
        url,
        {
            "full_name": "Test Emp",
            "identity_card_number": "079090008813",
            "phone": "0908811003",
        },
        format="json",
    )
    assert res_emp.status_code == status.HTTP_201_CREATED

    # Manager -> 201
    res_mgr = manager_client.post(
        url,
        {
            "full_name": "Test Mgr",
            "identity_card_number": "079090008814",
            "phone": "0908811004",
        },
        format="json",
    )
    assert res_mgr.status_code == status.HTTP_201_CREATED


def test_rbac_customer_update(
    manager_client: APIClient,
    employee_client: APIClient,
    customer_client: APIClient,
    anonymous_client: APIClient,
    active_customer: Customer,
):
    """PATCH /api/v1/customers/{id}/: EMPLOYEE/MANAGER allow; CUSTOMER 403; Anonymous 401."""
    url = f"/api/v1/customers/{active_customer.id}/"
    payload = {"row_version": active_customer.row_version, "address": "Địa chỉ mới"}

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

    # Employee -> 200
    res_emp = employee_client.patch(url, payload, format="json")
    assert res_emp.status_code == status.HTTP_200_OK

    # Manager -> 200 (using new row_version)
    new_version = res_emp.json()["row_version"]
    res_mgr = manager_client.patch(
        url, {"row_version": new_version, "address": "Địa chỉ quản lý"}, format="json"
    )
    assert res_mgr.status_code == status.HTTP_200_OK


def test_rbac_customer_delete(
    manager_client: APIClient,
    employee_client: APIClient,
    customer_client: APIClient,
    anonymous_client: APIClient,
):
    """DELETE /api/v1/customers/{id}/: EMPLOYEE/MANAGER allow; CUSTOMER 403; Anonymous 401."""
    # Create two isolated customers with no vehicles or tickets
    cust1 = Customer.objects.create(
        code="KHRBAC01",
        full_name="Khách Hàng RBAC 1",
        identity_card_number="079090008821",
        phone="0908822001",
    )
    cust2 = Customer.objects.create(
        code="KHRBAC02",
        full_name="Khách Hàng RBAC 2",
        identity_card_number="079090008822",
        phone="0908822002",
    )

    url1 = f"/api/v1/customers/{cust1.id}/"
    url2 = f"/api/v1/customers/{cust2.id}/"

    # Anonymous -> 401
    assert anonymous_client.delete(url1).status_code == status.HTTP_401_UNAUTHORIZED

    # Customer -> 403
    assert customer_client.delete(url1).status_code == status.HTTP_403_FORBIDDEN

    # Employee -> 200
    assert employee_client.delete(url1).status_code == status.HTTP_200_OK

    # Manager -> 200
    assert manager_client.delete(url2).status_code == status.HTTP_200_OK


def test_rbac_customer_vehicle_alias(
    manager_client: APIClient,
    employee_client: APIClient,
    customer_client: APIClient,
    anonymous_client: APIClient,
    active_customer: Customer,
    car_type: VehicleType,
):
    """POST /api/v1/customers/{customer_id}/vehicles/: EMPLOYEE/MANAGER allow; CUSTOMER 403; Anonymous 401."""
    url = f"/api/v1/customers/{active_customer.id}/vehicles/"

    # Anonymous -> 401
    assert (
        anonymous_client.post(
            url,
            {
                "license_plate": "51K-777.01",
                "model_name": "Vios",
                "vehicle_type_id": car_type.id,
            },
            format="json",
        ).status_code
        == status.HTTP_401_UNAUTHORIZED
    )

    # Customer -> 403
    assert (
        customer_client.post(
            url,
            {
                "license_plate": "51K-777.02",
                "model_name": "Vios",
                "vehicle_type_id": car_type.id,
            },
            format="json",
        ).status_code
        == status.HTTP_403_FORBIDDEN
    )

    # Employee -> 201
    res_emp = employee_client.post(
        url,
        {
            "license_plate": "51K-777.03",
            "model_name": "Vios",
            "vehicle_type_id": car_type.id,
        },
        format="json",
    )
    assert res_emp.status_code == status.HTTP_201_CREATED

    # Manager -> 201
    res_mgr = manager_client.post(
        url,
        {
            "license_plate": "51K-777.04",
            "model_name": "Camry",
            "vehicle_type_id": car_type.id,
        },
        format="json",
    )
    assert res_mgr.status_code == status.HTTP_201_CREATED
