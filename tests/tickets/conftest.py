"""
Shared fixtures and test configuration for apps.tickets test suite.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.models import ParkingSlot
from apps.tickets.models import Ticket, TicketType
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def seed_tickets_baseline():
    """
    Standardize seed ticket effective dates relative to timezone.now().
    Ensures stable counts of ACTIVE, EXPIRED, and CANCELLED tickets.
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
        status="ACTIVE",
    )
    Ticket.objects.filter(code__in=expired_codes).update(
        effective_from=now - timedelta(days=60),
        effective_to=now - timedelta(days=10),
        status="EXPIRED",
    )
    Ticket.objects.filter(code__in=cancelled_codes).update(
        effective_from=now - timedelta(days=90),
        effective_to=now - timedelta(days=30),
        status="CANCELLED",
    )
    yield


@pytest.fixture
def auth_manager():
    """Manager account with full read & write privileges."""
    acc, _ = Account.objects.get_or_create(
        email="manager_ticket_suite@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash_manager",
        },
    )
    return acc


@pytest.fixture
def auth_employee():
    """Employee account with read and write privileges."""
    acc, _ = Account.objects.get_or_create(
        email="employee_ticket_suite@parking.local",
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
        email="customer_ticket_suite@parking.local",
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
def sample_customer():
    """Sample customer from seed."""
    return Customer.objects.filter(deleted_at__isnull=True).first()


@pytest.fixture
def sample_vehicle():
    """Sample vehicle from seed."""
    return Vehicle.objects.filter(deleted_at__isnull=True).first()


@pytest.fixture
def sample_slot():
    """Sample available parking slot from seed."""
    return (
        ParkingSlot.objects.filter(deleted_at__isnull=True, status="AVAILABLE")
        .exclude(tickets__status="ACTIVE")
        .first()
    )


@pytest.fixture
def daily_type():
    """TicketType DAILY."""
    return TicketType.objects.get(code="DAILY")


@pytest.fixture
def monthly_type():
    """TicketType MONTHLY."""
    return TicketType.objects.get(code="MONTHLY")
