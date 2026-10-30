"""
Test suite for GET /api/v1/customers/{id}/ (Customer Detail View).
Covers:
- Successful retrieval with complete profile, 3 administrative tiers (IDs and names).
- Vehicles sub-grid using representative ticket subquery (SRS 4.4.2).
- Masking of PII fields for anonymized customers (Decree 13/2023/NĐ-CP, OQ-12).
- 404 Not Found for non-existent customer (PROP-4.4.4-P02).
- 404 Not Found for soft-deleted customer (PROP-4.4.4-P02).
- Zero N+1 query assertion.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.customers.models import Customer
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


def test_customer_detail_success(employee_client: APIClient, active_customer: Customer):
    """Verify customer detail endpoint returns full profile including administrative units and vehicle subgrid."""
    url = f"/api/v1/customers/{active_customer.id}/"
    response = employee_client.get(url)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["id"] == active_customer.id
    assert data["code"] == active_customer.code
    assert data["full_name"] == active_customer.full_name
    assert data["phone"] == active_customer.phone
    assert data["identity_card_number"] == active_customer.identity_card_number
    assert data["status"] == active_customer.status
    assert "status_display" in data
    assert "row_version" in data
    assert "vehicles" in data
    assert isinstance(data["vehicles"], list)

    # Administrative hierarchy fields
    assert "province_id" in data
    assert "district_id" in data
    assert "ward_id" in data
    assert "province_name" in data
    assert "district_name" in data
    assert "ward_name" in data


def test_customer_detail_vehicles_subgrid_matches_vehicle_table(
    employee_client: APIClient,
):
    """
    Verify the vehicles subgrid matches the actual vehicles registered to the customer in the database,
    including vehicle type and representative ticket annotations.
    """
    # Find a customer with at least one vehicle
    cust = (
        Customer.objects.filter(
            deleted_at__isnull=True,
            vehicles__deleted_at__isnull=True,
        )
        .distinct()
        .first()
    )
    assert cust is not None, "Seed data must contain a customer with vehicles"

    url = f"/api/v1/customers/{cust.id}/"
    response = employee_client.get(url)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    db_vehicles = Vehicle.objects.filter(
        customer_id=cust.id, deleted_at__isnull=True
    ).order_by("id")
    assert len(data["vehicles"]) == db_vehicles.count()

    db_plates = [v.license_plate for v in db_vehicles]
    response_plates = [v["license_plate"] for v in data["vehicles"]]
    assert response_plates == db_plates

    # Check vehicle structure
    v_item = data["vehicles"][0]
    assert "license_plate" in v_item
    assert "model_name" in v_item
    assert "vehicle_type" in v_item
    assert "ticket" in v_item


def test_customer_detail_not_found(employee_client: APIClient):
    """Verify 404 response for non-existent customer primary key."""
    non_existent_id = 9999999
    url = f"/api/v1/customers/{non_existent_id}/"
    response = employee_client.get(url)

    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["code"] == "PROP-4.4.4-P02"
    assert "Khách hàng không tồn tại" in data["message"]


def test_customer_detail_soft_deleted_returns_404(employee_client: APIClient):
    """Verify that soft-deleted customers are not accessible and return 404."""
    # Create a fresh customer with no vehicles and no tickets to satisfy trigger guards
    temp_cust = Customer.objects.create(
        code="KH9991",
        full_name="Khách Hàng Xóa Mềm",
        identity_card_number="999888777666",
        phone="0988776655",
    )
    # Soft delete the customer
    Customer.objects.filter(id=temp_cust.id).update(deleted_at=timezone.now())

    url = f"/api/v1/customers/{temp_cust.id}/"
    response = employee_client.get(url)
    assert response.status_code == status.HTTP_404_NOT_FOUND
    data = response.json()
    assert data["code"] == "PROP-4.4.4-P02"


def test_customer_detail_pii_masking_for_anonymized_profile(
    employee_client: APIClient,
):
    """
    Verify complete PII masking in Detail view when is_anonymized = True:
    full_name -> 'Khách hàng ẩn danh'
    date_of_birth -> None
    identity_card_number -> '***'
    phone -> '***'
    email -> '***'
    address -> '***'
    """
    target = Customer.objects.filter(deleted_at__isnull=True).order_by("id").first()
    assert target is not None

    Customer.objects.filter(id=target.id).update(
        is_anonymized=True,
        anonymized_at=timezone.now(),
    )

    try:
        url = f"/api/v1/customers/{target.id}/"
        response = employee_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["is_anonymized"] is True
        assert data["full_name"] == "Khách hàng ẩn danh"
        assert data["identity_card_number"] == "***"
        assert data["phone"] == "***"
        assert data["email"] == "***"
        assert data["address"] == "***"
        assert data["date_of_birth"] is None
    finally:
        Customer.objects.filter(id=target.id).update(
            is_anonymized=False,
            anonymized_at=None,
        )


def test_customer_detail_query_count_bounded(
    employee_client: APIClient, active_customer: Customer
):
    """Zero N+1 query guarantee: Detail view must execute a fixed minimal number of queries."""
    url = f"/api/v1/customers/{active_customer.id}/"
    with CaptureQueriesContext(connection) as ctx:
        response = employee_client.get(url)
        assert response.status_code == status.HTTP_200_OK

    # Detail query count: customer query (with select_related) + vehicles annotated query + auth
    assert len(ctx.captured_queries) <= 6, (
        f"Too many queries: {len(ctx.captured_queries)}"
    )
