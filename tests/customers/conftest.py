"""
Shared fixtures and test configuration for apps.customers test suite.
Provides authenticated clients for MANAGER, EMPLOYEE, CUSTOMER, and ANONYMOUS users,
along with database reference instances for administrative units and vehicle types.
"""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.models import (
    AdministrativeDistrict,
    AdministrativeProvince,
    AdministrativeWard,
)
from apps.customers.models import Customer
from apps.vehicles.models import VehicleType

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_manager() -> Account:
    """Manager account with full read & write privileges."""
    acc, _ = Account.objects.get_or_create(
        email="manager_customer_suite@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash_manager",
        },
    )
    return acc


@pytest.fixture
def auth_employee() -> Account:
    """Employee account with read and write privileges."""
    acc, _ = Account.objects.get_or_create(
        email="employee_customer_suite@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash_employee",
        },
    )
    return acc


@pytest.fixture
def auth_customer() -> Account:
    """Customer account without backend staff privileges."""
    acc, _ = Account.objects.get_or_create(
        email="customer_customer_suite@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash_customer",
        },
    )
    return acc


@pytest.fixture
def manager_client(auth_manager: Account) -> APIClient:
    """APIClient authenticated as MANAGER."""
    client = APIClient()
    client.force_authenticate(user=auth_manager)
    return client


@pytest.fixture
def employee_client(auth_employee: Account) -> APIClient:
    """APIClient authenticated as EMPLOYEE."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    return client


@pytest.fixture
def customer_client(auth_customer: Account) -> APIClient:
    """APIClient authenticated as CUSTOMER (should receive 403 on staff endpoints)."""
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    return client


@pytest.fixture
def anonymous_client() -> APIClient:
    """Unauthenticated APIClient (should receive 401 on protected endpoints)."""
    return APIClient()


@pytest.fixture
def admin_hierarchy() -> dict[str, Any]:
    """
    Returns valid 3-tier administrative hierarchy matching database constraints.
    Province -> District -> Ward.
    """
    province = AdministrativeProvince.objects.order_by("id").first()
    assert province is not None, "AdministrativeProvince seed data missing"

    district = (
        AdministrativeDistrict.objects.filter(province=province).order_by("id").first()
    )
    assert district is not None, "AdministrativeDistrict seed data missing"

    ward = AdministrativeWard.objects.filter(district=district).order_by("id").first()
    assert ward is not None, "AdministrativeWard seed data missing"

    return {
        "province": province,
        "district": district,
        "ward": ward,
        "province_id": province.id,
        "district_id": district.id,
        "ward_id": ward.id,
    }


@pytest.fixture
def car_type() -> VehicleType:
    """VehicleType CAR instance from seed."""
    return VehicleType.objects.get(code="CAR", deleted_at__isnull=True)


@pytest.fixture
def ev_type() -> VehicleType:
    """VehicleType EV instance from seed."""
    return VehicleType.objects.get(code="EV", deleted_at__isnull=True)


@pytest.fixture
def active_customer() -> Customer:
    """Active non-deleted Customer instance from seed."""
    customer = (
        Customer.objects.filter(deleted_at__isnull=True, is_anonymized=False)
        .order_by("id")
        .first()
    )
    assert customer is not None, "Seed customer data missing"
    return customer
