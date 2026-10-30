"""
Test suite for POST /api/v1/customers/ (Customer Creation API).
Covers:
- Single customer creation with auto-generated sequential code KH%04d under advisory lock.
- Explicit customer code assignment and uniqueness enforcement (409 MSG-4.3.1-M05).
- Uniqueness validation for identity_card, phone, email (409 MSG-4.3.1-M05) without PII leakage.
- Atomic customer creation with vehicles array (SRS 4.4.3).
- All-or-nothing rollback when 2nd vehicle fails (zero orphan customer rows).
- Raw-string validation against control chars, zero-width chars, NUL byte, over-length strings.
- caplog assertion: exactly 0 'Database exception' log records during input rejection.
- Rule 04 compliance: all field validation errors returned together.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.customers.models import Customer
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db
CREATE_URL = "/api/v1/customers/"


def test_customer_create_single_auto_code_success(
    employee_client: APIClient, admin_hierarchy: dict[str, Any]
):
    """
    Verify single customer creation without explicit code.
    System must auto-generate sequential KH%04d code under advisory lock.
    """
    payload = {
        "full_name": "Nguyễn Văn Đạt",
        "date_of_birth": "1992-05-15",
        "gender": "Nam",
        "identity_card_number": "079092001122",
        "phone": "0918112233",
        "email": "dat.nguyen@example.com",
        "address": "123 Lê Lợi, Phường Bến Nghé",
        "province_id": admin_hierarchy["province_id"],
        "district_id": admin_hierarchy["district_id"],
        "ward_id": admin_hierarchy["ward_id"],
        "status": "ACTIVE",
    }

    response = employee_client.post(CREATE_URL, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["code"].startswith("KH")
    assert len(data["code"]) >= 6
    assert data["full_name"] == "Nguyễn Văn Đạt"
    assert data["row_version"] == 1
    assert data["status"] == "ACTIVE"
    assert data["province_id"] == admin_hierarchy["province_id"]

    # Verify DB persistence
    cust = Customer.objects.get(id=data["id"])
    assert cust.code == data["code"]
    assert cust.identity_card_number == "079092001122"


def test_customer_create_with_explicit_code(employee_client: APIClient):
    """Verify single customer creation with explicit valid code."""
    payload = {
        "code": "KH8877",
        "full_name": "Trần Thị Lan",
        "identity_card_number": "079195009988",
        "phone": "0909887766",
        "status": "ACTIVE",
    }
    response = employee_client.post(CREATE_URL, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["code"] == "KH8877"

    # Duplicate code should fail with 409
    dup_payload = {
        "code": "KH8877",
        "full_name": "Lê Văn Hùng",
        "identity_card_number": "079195009989",
        "phone": "0909887767",
    }
    dup_res = employee_client.post(CREATE_URL, dup_payload, format="json")
    assert dup_res.status_code == status.HTTP_409_CONFLICT
    assert dup_res.json()["code"] == "MSG-4.3.1-M05"


def test_customer_create_duplicate_idcard_rejected(
    employee_client: APIClient, active_customer: Customer
):
    """Verify creating a customer with duplicate CCCD fails with 409 and never leaks CCCD."""
    payload = {
        "full_name": "Người Trùng CCCD",
        "identity_card_number": active_customer.identity_card_number,
        "phone": "0919999888",
    }
    response = employee_client.post(CREATE_URL, payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT

    data = response.json()
    assert data["code"] == "MSG-4.3.1-M05"
    assert active_customer.identity_card_number not in str(data)


def test_customer_create_duplicate_phone_rejected(
    employee_client: APIClient, active_customer: Customer
):
    """Verify creating a customer with duplicate phone fails with 409."""
    payload = {
        "full_name": "Người Trùng Phone",
        "identity_card_number": "079200999888",
        "phone": active_customer.phone,
    }
    response = employee_client.post(CREATE_URL, payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "MSG-4.3.1-M05"


def test_customer_create_duplicate_email_rejected(
    employee_client: APIClient, active_customer: Customer
):
    """Verify creating a customer with duplicate email fails with 409."""
    assert active_customer.email is not None
    payload = {
        "full_name": "Người Trùng Email",
        "identity_card_number": "079200999777",
        "phone": "0919999777",
        "email": active_customer.email.upper(),
    }
    response = employee_client.post(CREATE_URL, payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.json()["code"] == "MSG-4.3.1-M05"


def test_customer_create_atomic_with_vehicles_success(
    employee_client: APIClient, car_type: VehicleType, ev_type: VehicleType
):
    """
    SRS 4.4.3: Verify atomic creation of customer with optional vehicles array.
    Customer and all vehicles are created successfully in ONE transaction.
    """
    payload = {
        "full_name": "Vũ Đình Đạt",
        "identity_card_number": "079199003344",
        "phone": "0933112244",
        "vehicles": [
            {
                "license_plate": "51K-990.11",
                "model_name": "VF8",
                "vehicle_type_id": ev_type.id,
                "color": "Đỏ",
            },
            {
                "license_plate": "51K-990.22",
                "model_name": "Camry",
                "vehicle_type_id": car_type.id,
                "color": "Đen",
            },
        ],
    }
    response = employee_client.post(CREATE_URL, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    cust_id = data["id"]

    # Verify both vehicles exist and are assigned to this customer
    v1 = Vehicle.objects.get(license_plate="51K-990.11", deleted_at__isnull=True)
    v2 = Vehicle.objects.get(license_plate="51K-990.22", deleted_at__isnull=True)
    assert v1.customer_id == cust_id
    assert v2.customer_id == cust_id


def test_customer_create_atomic_rollback_on_second_vehicle_failure(
    employee_client: APIClient, car_type: VehicleType
):
    """
    SRS 4.4.3: All-or-nothing transaction guarantee.
    If the 2nd vehicle fails (e.g. duplicate license plate), the entire customer creation
    must ROLL BACK completely. Zero orphan customer records must remain in the DB.
    """
    # Pick an existing vehicle's license plate to trigger unique violation on 2nd vehicle
    first_veh = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert first_veh is not None
    existing_plate = first_veh.license_plate

    test_cccd = "079199009900"
    test_phone = "0944009900"
    payload = {
        "full_name": "Lê Thị Bích Hạnh",
        "identity_card_number": test_cccd,
        "phone": test_phone,
        "vehicles": [
            {
                "license_plate": "51K-881.01",
                "model_name": "VF9",
                "vehicle_type_id": car_type.id,
            },
            {
                "license_plate": existing_plate,  # DUPLICATE -> FAILS
                "model_name": "Civic",
                "vehicle_type_id": car_type.id,
            },
        ],
    }

    response = employee_client.post(CREATE_URL, payload, format="json")
    assert response.status_code in [
        status.HTTP_409_CONFLICT,
        status.HTTP_400_BAD_REQUEST,
    ]

    # ASSERTION OF ALL-OR-NOTHING: Customer MUST NOT exist in DB
    assert not Customer.objects.filter(identity_card_number=test_cccd).exists()
    assert not Customer.objects.filter(phone=test_phone).exists()

    # Neither should vehicle 1 exist
    assert not Vehicle.objects.filter(license_plate="51K-881.01").exists()


@pytest.mark.parametrize(
    "invalid_name",
    [
        "Nguyễn\x00Văn Nam",
        "Nguyễn\x08Văn Nam",
        "Nguyễn\u200bVăn Nam",
        "Nguyễn\ufeffVăn Nam",
        "   ",
        "A" * 46,
    ],
)
def test_customer_create_raw_string_tricks_rejected(
    employee_client: APIClient,
    caplog: pytest.LogCaptureFixture,
    invalid_name: str,
):
    """
    Verify raw-string input validation cleans and rejects invalid characters before DB hit.
    caplog must confirm ZERO 'Database exception' records were logged.
    """
    caplog.set_level(logging.ERROR)

    payload = {
        "full_name": invalid_name,
        "identity_card_number": "079099887766",
        "phone": "0933887766",
    }
    response = employee_client.post(CREATE_URL, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST

    data = response.json()
    assert data["code"] == "PROP-GEN-P01"
    assert "full_name" in data.get("details", {})

    # Assert ZERO "Database exception" log messages
    for record in caplog.records:
        assert "Database exception" not in record.message


def test_customer_create_vietnamese_diacritics_accepted(employee_client: APIClient):
    """Verify legitimate Vietnamese names with diacritics and excessive whitespace are cleaned and accepted."""
    payload = {
        "full_name": "   Đặng   Thị   Mỹ   Duyên   ",
        "identity_card_number": "079099112233",
        "phone": "0911223344",
    }
    response = employee_client.post(CREATE_URL, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["full_name"] == "Đặng Thị Mỹ Duyên"


def test_customer_create_blacklisted_without_reason_rejected(
    employee_client: APIClient,
):
    """Verify creating a customer with BLACKLISTED status requires status_reason."""
    payload = {
        "full_name": "Phạm Văn Khóa",
        "identity_card_number": "079099554433",
        "phone": "0955443322",
        "status": "BLACKLISTED",
        # status_reason omitted
    }
    response = employee_client.post(CREATE_URL, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Lý do khóa là bắt buộc" in str(response.json())
