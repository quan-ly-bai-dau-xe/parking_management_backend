import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.employees.models import Employee, Position
from apps.wallet.models import Wallet
from apps.wallet.services.wallet import ensure_wallet_for_customer


@pytest.fixture
def staff_employee(db):
    pos = Position.objects.first()
    if pos is None:
        pos = Position.objects.create(code="NVVH_W", name="Nhân viên vận hành")
    suffix = uuid.uuid4().hex[:6]
    acc = Account.objects.create_user(
        email=f"staff_wallet_{suffix}@example.com",
        password="TestPassword123!",
        role="EMPLOYEE",
    )
    emp = Employee.objects.create(
        code=f"NV{uuid.uuid4().int % 9000 + 1000}",
        full_name="Nhân Viên Ví",
        identity_card_number=f"079{uuid.uuid4().int % 10**9:09d}",
        phone=f"09{uuid.uuid4().int % 10**8:08d}",
        email=acc.email,
        position=pos,
        account=acc,
        status="ACTIVE",
    )
    return acc, emp


@pytest.fixture
def manager_account(db):
    suffix = uuid.uuid4().hex[:6]
    return Account.objects.create_user(
        email=f"mgr_wallet_{suffix}@example.com",
        password="TestPassword123!",
        role="MANAGER",
    )


@pytest.fixture
def wallet_customer_pair(db):
    suffix = uuid.uuid4().hex[:6]
    acc = Account.objects.create_user(
        email=f"cust_wallet_{suffix}@example.com",
        password="TestPassword123!",
        role="CUSTOMER",
    )
    cust = Customer.objects.create(
        code=f"KHW{suffix[:4].upper()}",
        full_name="Nguyễn Văn Ví",
        identity_card_number=f"079{uuid.uuid4().int % 10**9:09d}",
        phone=f"08{uuid.uuid4().int % 10**8:08d}",
        email=acc.email,
        account=acc,
        status="ACTIVE",
    )
    wallet = ensure_wallet_for_customer(cust.id)
    return acc, cust, wallet


@pytest.fixture
def other_customer_pair(db):
    suffix = uuid.uuid4().hex[:6]
    acc = Account.objects.create_user(
        email=f"other_wallet_{suffix}@example.com",
        password="TestPassword123!",
        role="CUSTOMER",
    )
    cust = Customer.objects.create(
        code=f"KHO{suffix[:4].upper()}",
        full_name="Trần Thị Khác",
        identity_card_number=f"079{uuid.uuid4().int % 10**9:09d}",
        phone=f"07{uuid.uuid4().int % 10**8:08d}",
        email=acc.email,
        account=acc,
        status="ACTIVE",
    )
    wallet = ensure_wallet_for_customer(cust.id)
    return acc, cust, wallet


@pytest.fixture
def customer_client(wallet_customer_pair):
    acc, _, _ = wallet_customer_pair
    client = APIClient()
    client.force_authenticate(user=acc)
    return client


@pytest.fixture
def staff_client(staff_employee):
    acc, _ = staff_employee
    client = APIClient()
    client.force_authenticate(user=acc)
    return client


@pytest.fixture
def manager_client(manager_account):
    client = APIClient()
    client.force_authenticate(user=manager_account)
    return client


@pytest.fixture
def anon_client():
    return APIClient()


def get_fresh_wallet(wallet_id: int) -> Wallet:
    return Wallet.objects.get(id=wallet_id)


def assert_wallet_balance(wallet_id: int, expected: Decimal) -> None:
    w = Wallet.objects.get(id=wallet_id)
    assert w.balance == expected
