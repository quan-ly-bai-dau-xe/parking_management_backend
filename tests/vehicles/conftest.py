"""
Shared fixtures and test configuration for apps.vehicles test suite.
"""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.vehicles.models import VehicleType

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_manager():
    """Manager account with full read & write privileges."""
    acc, _ = Account.objects.get_or_create(
        email="manager_vehicle_suite@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash_manager",
        },
    )
    return acc


@pytest.fixture
def auth_employee():
    """Employee account with read-only privileges."""
    acc, _ = Account.objects.get_or_create(
        email="employee_vehicle_suite@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash_employee",
        },
    )
    return acc


@pytest.fixture
def auth_customer():
    """Customer account without backend staff privileges."""
    acc, _ = Account.objects.get_or_create(
        email="customer_vehicle_suite@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash_customer",
        },
    )
    return acc


@pytest.fixture
def manager_client(auth_manager):
    """APIClient authenticated as MANAGER."""
    client = APIClient()
    client.force_authenticate(user=auth_manager)
    return client


@pytest.fixture
def employee_client(auth_employee):
    """APIClient authenticated as EMPLOYEE."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    return client


@pytest.fixture
def customer_client(auth_customer):
    """APIClient authenticated as CUSTOMER."""
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    return client


@pytest.fixture
def anonymous_client():
    """Unauthenticated APIClient."""
    return APIClient()


@pytest.fixture
def car_type():
    """VehicleType CAR instance from seed."""
    return VehicleType.objects.get(code="CAR", deleted_at__isnull=True)


@pytest.fixture
def ev_type():
    """VehicleType EV instance from seed."""
    return VehicleType.objects.get(code="EV", deleted_at__isnull=True)


@pytest.fixture
def active_customer():
    """Active non-deleted Customer instance from seed."""
    return Customer.objects.filter(deleted_at__isnull=True).order_by("id").first()
