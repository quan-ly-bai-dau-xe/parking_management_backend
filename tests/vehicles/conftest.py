"""
Shared fixtures and test configuration for apps.vehicles test suite.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.tickets.models import Ticket
from apps.vehicles.models import VehicleType

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def seed_vehicle_ticket_baseline():
    """
    Shared fixture anchoring the 25 seeded tickets relative to timezone.now()
    inside each test transaction. Guarantees 100% stable baseline distribution:
      - 31 vehicles total
      - 10 valid tickets (VT0001..VT0005, VT0007..VT0010, VT0012)
      - 0 expiring soon tickets
      - 12 expired tickets (VT0006, VT0011, VT0013..VT0022)
      - 9 without active ticket (VT0023..VT0025 CANCELLED + 6 unassigned vehicles)
      - 15 active vehicles (10 valid + 5 parked without valid ticket: XE0006, XE0018..XE0021)
    """
    now = timezone.now()
    valid_codes = [
        "VT0001",
        "VT0002",
        "VT0003",
        "VT0004",
        "VT0005",
        "VT0007",
        "VT0008",
        "VT0009",
        "VT0010",
        "VT0012",
    ]
    expired_codes = [
        "VT0006",
        "VT0011",
        "VT0013",
        "VT0014",
        "VT0015",
        "VT0016",
        "VT0017",
        "VT0018",
        "VT0019",
        "VT0020",
        "VT0021",
        "VT0022",
    ]
    cancelled_codes = ["VT0023", "VT0024", "VT0025"]

    Ticket.objects.filter(code__in=valid_codes).update(
        effective_from=now - timedelta(days=30),
        effective_to=now + timedelta(days=60),
    )
    Ticket.objects.filter(code__in=expired_codes).update(
        effective_from=now - timedelta(days=60),
        effective_to=now - timedelta(days=10),
    )
    Ticket.objects.filter(code__in=cancelled_codes).update(
        effective_from=now - timedelta(days=90),
        effective_to=now - timedelta(days=30),
    )
    yield


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
    """Employee account with read and write privileges (Task V0: IsEmployeeOrManager)."""
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
