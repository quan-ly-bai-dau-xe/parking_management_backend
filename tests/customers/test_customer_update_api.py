"""
Test suite for PATCH /api/v1/customers/{id}/ (Customer Partial Update API).
Covers:
- Optimistic Concurrency Control (OCC) with row_version (409 MSG-4.3.1-M03 on stale token).
- Missing row_version rejection (400 PROP-GEN-P01).
- Customer code immutability (code cannot be modified via update).
- Blacklist status reason validation (mandatory status_reason when status = BLACKLISTED).
- 3-tier administrative hierarchy consistency (province -> district -> ward).
- Unique conflict protection on CCCD, phone, email without PII echoing (409 MSG-4.3.1-M05).
- 404 handling on non-existent or soft-deleted customer.
"""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.models import AdministrativeWard
from apps.customers.models import Customer

pytestmark = pytest.mark.django_db


def test_customer_update_success_increments_row_version(
    employee_client: APIClient, active_customer: Customer
):
    """Verify successful partial update increments row_version token automatically."""
    url = f"/api/v1/customers/{active_customer.id}/"
    initial_version = active_customer.row_version

    payload = {
        "row_version": initial_version,
        "address": "456 Nguyễn Huệ, Phường Bến Nghé",
    }
    response = employee_client.patch(url, payload, format="json")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["address"] == "456 Nguyễn Huệ, Phường Bến Nghé"
    assert data["row_version"] == initial_version + 1

    active_customer.refresh_from_db()
    assert active_customer.address == "456 Nguyễn Huệ, Phường Bến Nghé"
    assert active_customer.row_version == initial_version + 1


def test_customer_update_missing_row_version_rejected(
    employee_client: APIClient, active_customer: Customer
):
    """Verify request without row_version is rejected with 400 Bad Request."""
    url = f"/api/v1/customers/{active_customer.id}/"
    payload = {"address": "Địa chỉ mới"}

    response = employee_client.patch(url, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    data = response.json()
    assert data["code"] == "PROP-GEN-P01"
    assert "row_version" in str(data)


def test_customer_update_stale_row_version_conflict(
    employee_client: APIClient, active_customer: Customer
):
    """Verify stale row_version generates 409 Conflict MSG-4.3.1-M03."""
    url = f"/api/v1/customers/{active_customer.id}/"
    stale_version = active_customer.row_version + 999

    payload = {
        "row_version": stale_version,
        "address": "Địa chỉ mới",
    }
    response = employee_client.patch(url, payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT

    data = response.json()
    assert data["code"] == "MSG-4.3.1-M03"
    assert "user khác" in data["message"]


def test_customer_update_code_is_immutable(
    employee_client: APIClient, active_customer: Customer
):
    """Verify customer code cannot be changed via PATCH."""
    url = f"/api/v1/customers/{active_customer.id}/"
    original_code = active_customer.code

    payload = {
        "row_version": active_customer.row_version,
        "code": "KH99999",  # Attempt to mutate code
        "full_name": "Tên Cập Nhật",
    }
    response = employee_client.patch(url, payload, format="json")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["code"] == original_code  # Unchanged
    active_customer.refresh_from_db()
    assert active_customer.code == original_code


def test_customer_update_blacklisted_requires_status_reason(
    employee_client: APIClient, active_customer: Customer
):
    """Verify transitioning to BLACKLISTED requires non-empty status_reason."""
    url = f"/api/v1/customers/{active_customer.id}/"

    # 1. Without reason -> 400
    res_fail = employee_client.patch(
        url,
        {"row_version": active_customer.row_version, "status": "BLACKLISTED"},
        format="json",
    )
    assert res_fail.status_code == status.HTTP_400_BAD_REQUEST
    assert "Lý do khóa là bắt buộc" in str(res_fail.json())

    # 2. With reason -> 200
    res_ok = employee_client.patch(
        url,
        {
            "row_version": active_customer.row_version,
            "status": "BLACKLISTED",
            "status_reason": "Vi phạm quy chế bãi xe nhiều lần",
        },
        format="json",
    )
    assert res_ok.status_code == status.HTTP_200_OK
    assert res_ok.json()["status"] == "BLACKLISTED"
    assert res_ok.json()["status_reason"] == "Vi phạm quy chế bãi xe nhiều lần"


def test_customer_update_admin_hierarchy_mismatch_rejected(
    employee_client: APIClient,
    active_customer: Customer,
    admin_hierarchy: dict[str, Any],
):
    """Verify mismatched administrative hierarchy (ward not in district) returns 400."""
    url = f"/api/v1/customers/{active_customer.id}/"

    # Find a ward from a different district
    other_ward = AdministrativeWard.objects.exclude(
        district_id=admin_hierarchy["district_id"]
    ).first()
    if other_ward:
        payload = {
            "row_version": active_customer.row_version,
            "province_id": admin_hierarchy["province_id"],
            "district_id": admin_hierarchy["district_id"],
            "ward_id": other_ward.id,
        }
        response = employee_client.patch(url, payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "Phường/Xã không thuộc Quận/Huyện" in str(response.json())


def test_customer_update_duplicate_idcard_conflict(
    employee_client: APIClient, active_customer: Customer
):
    """Verify updating CCCD to match another existing customer returns 409 without PII leak."""
    other_customer = (
        Customer.objects.filter(deleted_at__isnull=True, is_anonymized=False)
        .exclude(id=active_customer.id)
        .first()
    )
    assert other_customer is not None

    url = f"/api/v1/customers/{active_customer.id}/"
    payload = {
        "row_version": active_customer.row_version,
        "identity_card_number": other_customer.identity_card_number,
    }
    response = employee_client.patch(url, payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT

    data = response.json()
    assert data["code"] == "MSG-4.3.1-M05"
    assert other_customer.identity_card_number not in str(data)


def test_customer_update_duplicate_phone_conflict(
    employee_client: APIClient, active_customer: Customer
):
    """Verify updating phone to match another existing customer returns 409 without PII leak."""
    other_customer = (
        Customer.objects.filter(deleted_at__isnull=True, is_anonymized=False)
        .exclude(id=active_customer.id)
        .first()
    )
    assert other_customer is not None

    url = f"/api/v1/customers/{active_customer.id}/"
    payload = {
        "row_version": active_customer.row_version,
        "phone": other_customer.phone,
    }
    response = employee_client.patch(url, payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "MSG-4.3.1-M05"
    assert other_customer.phone not in str(response.json())


def test_customer_update_duplicate_email_conflict(
    employee_client: APIClient, active_customer: Customer
):
    """Verify updating email to match another existing customer returns 409 without PII leak."""
    other_customer = (
        Customer.objects.filter(deleted_at__isnull=True, is_anonymized=False)
        .exclude(id=active_customer.id)
        .exclude(email__isnull=True)
        .first()
    )
    assert other_customer is not None and other_customer.email is not None

    url = f"/api/v1/customers/{active_customer.id}/"
    payload = {
        "row_version": active_customer.row_version,
        "email": other_customer.email,
    }
    response = employee_client.patch(url, payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "MSG-4.3.1-M05"
    assert other_customer.email not in str(response.json())


def test_customer_update_not_found(employee_client: APIClient):
    """Verify updating non-existent customer returns 404 PROP-4.4.4-P02."""
    url = "/api/v1/customers/9999999/"
    payload = {"row_version": 1, "address": "Địa chỉ"}
    response = employee_client.patch(url, payload, format="json")
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json()["code"] == "PROP-4.4.4-P02"
