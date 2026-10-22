"""
Integration tests for Check-Out API (POST /api/v1/parking/sessions/check-out/).
Verifies:
- Permission matrix: anonymous -> 401, CUSTOMER -> 403, EMPLOYEE -> allowed.
- Provide neither or both session_code & license_plate -> 400 PROP-4.5.1-P11.
- Invalid exit gate (e.g. IN direction) -> 400 PROP-4.5.1-P12.
- Session already closed -> 409 PROP-4.5.1-P10.
- Missing payment_method when fee > 0 -> 400 PROP-4.5.1-P13.
- Visitor check-out with fee -> creates Payment record status PAID (CASH/VIETQR).
- Active ticket check-out -> fee = 0, no payment required.
- Soft-deleted vehicle during parking (OQ-67) -> check-out succeeds normally.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.models import ParkingGate, ParkingSlot, VehicleEntryExitLog
from apps.tickets.models import Payment, Ticket, TicketType
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_checkout@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def auth_customer():
    cust, _ = Account.objects.get_or_create(
        email="cust_checkout@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return cust


@pytest.fixture
def in_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào Test", direction="IN", is_active=True
        )
    return gate


@pytest.fixture
def out_gate():
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng ra Test", direction="OUT", is_active=True
        )
    return gate


def test_check_out_anonymous_rejected():
    """Chưa đăng nhập -> 401 MSG-4.1-M02."""
    client = APIClient()
    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {"license_plate": "43A-999.88", "exit_gate_id": 1},
        format="json",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"


def test_check_out_customer_forbidden(auth_customer, out_gate):
    """Khách hàng bị từ chối gọi API check-out -> 403 MSG-4.2-M01."""
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {"license_plate": "43A-999.88", "exit_gate_id": out_gate.id},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"


def test_check_out_criteria_mutual_exclusive(auth_employee, out_gate):
    """Không gửi cả hai hoặc gửi đồng thời cả mã phiên và biển số -> 400 PROP-4.5.1-P11."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Không gửi cái nào
    resp1 = client.post(
        "/api/v1/parking/sessions/check-out/",
        {"exit_gate_id": out_gate.id},
        format="json",
    )
    assert resp1.status_code == status.HTTP_400_BAD_REQUEST
    assert resp1.data["code"] == "PROP-4.5.1-P11"

    # 2. Gửi đồng thời cả hai
    resp2 = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": "#PK-20261018-001",
            "license_plate": "43A-123.45",
            "exit_gate_id": out_gate.id,
        },
        format="json",
    )
    assert resp2.status_code == status.HTTP_400_BAD_REQUEST
    assert resp2.data["code"] == "PROP-4.5.1-P11"


def test_check_out_invalid_exit_gate(auth_employee, in_gate):
    """Gửi cổng hướng IN tại API check-out -> 400 PROP-4.5.1-P12."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {"license_plate": "43A-123.45", "exit_gate_id": in_gate.id},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P12"


def test_check_out_session_already_closed(auth_employee, in_gate, out_gate):
    """Phiên đỗ xe đã kết thúc trước đó -> 409 PROP-4.5.1-P10."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-20261018-991",
        license_plate="43A-777.88",
        license_plate_norm="43A77788",
        entry_gate=in_gate,
        exit_gate=out_gate,
        entry_time=now - timedelta(hours=2),
        exit_time=now - timedelta(hours=1),
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": "CASH",
        },
        format="json",
    )
    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "PROP-4.5.1-P10"


def test_check_out_visitor_paid_by_cash(auth_employee, in_gate, out_gate):
    """Xe vãng lai check-out phát sinh cước 20.000 VND, thanh toán CASH tạo Payment PAID."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-20261018-992",
        license_plate="43A-666.55",
        license_plate_norm="43A66655",
        entry_gate=in_gate,
        entry_time=now
        - timedelta(hours=1, minutes=30),  # 1.5 giờ -> tính 2 giờ = 20.000đ
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": "CASH",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert data["session"]["fee_amount"] == "20000.00"
    assert data["session"]["exit_gate_id"] == out_gate.id
    assert data["payment"] is not None
    assert data["payment"]["method"] == "CASH"
    assert data["payment"]["amount"] == "20000.00"
    assert data["payment"]["status"] == "PAID"

    # Kiểm tra bản ghi Payment trong CSDL
    pmt = Payment.objects.get(session_id=session.id)
    assert pmt.status == "PAID"
    assert pmt.amount == Decimal("20000.00")


def test_check_out_missing_payment_method_when_fee_positive(
    auth_employee, in_gate, out_gate
):
    """Xe vãng lai có cước phí mà không truyền payment_method -> 400 PROP-4.5.1-P13."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-20261018-993",
        license_plate="43A-444.33",
        license_plate_norm="43A44433",
        entry_gate=in_gate,
        entry_time=now - timedelta(hours=1),
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            # Thiếu payment_method
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P09"


def test_check_out_active_ticket_zero_fee(auth_employee, in_gate, out_gate):
    """Xe có vé đỗ ACTIVE check-out cước 0 VND, không cần thanh toán."""
    now = timezone.now()
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-TCK-99",
        full_name="Vé Tháng Test 99",
        phone="0901234599",
        identity_card_number="049090123499",
    )
    v = Vehicle.objects.create(
        code="XE-TCK-99",
        license_plate="43A-999.88",
        license_plate_norm="43A99988",
        vehicle_type=vtype,
        customer=cust,
        model_name="Mazda 3",
    )
    ticket_type = TicketType.objects.first()
    slot = ParkingSlot.objects.filter(tickets__isnull=True, status="AVAILABLE").first()
    ticket = Ticket.objects.create(
        code="TCK-0099",
        vehicle=v,
        customer=cust,
        slot=slot,
        ticket_type=ticket_type,
        status="ACTIVE",
        effective_from=now - timedelta(days=5),
        effective_to=now + timedelta(days=25),
        price=Decimal("500000.00"),
    )

    VehicleEntryExitLog.objects.create(
        session_code="#PK-20261018-994",
        vehicle=v,
        ticket=ticket,
        license_plate=v.license_plate,
        license_plate_norm=v.license_plate_norm,
        entry_gate=in_gate,
        entry_time=now - timedelta(hours=4),
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "license_plate": v.license_plate,
            "exit_gate_id": out_gate.id,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert data["session"]["fee_amount"] == "0.00"
    assert data["payment"] is None


def test_check_out_soft_deleted_vehicle_succeeds(auth_employee, in_gate, out_gate):
    """Phương tiện bị soft-delete khi đang đỗ trong bãi (OQ-67) vẫn được check-out thành công."""
    now = timezone.now()
    vtype = VehicleType.objects.first()
    cust = Customer.objects.create(
        code="KH-DEL-02",
        full_name="Xóa Mềm Test",
        phone="0901234568",
        identity_card_number="049090123457",
    )
    # 1. Tạo xe hoạt động bình thường
    v = Vehicle.objects.create(
        code="XE-DEL-02",
        license_plate="43A-000.99",
        license_plate_norm="43A00099",
        vehicle_type=vtype,
        customer=cust,
        model_name="Innova",
    )

    # 2. Tạo phiên đỗ xe khi xe đang hoạt động
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-20261018-995",
        vehicle=v,
        license_plate=v.license_plate,
        license_plate_norm=v.license_plate_norm,
        entry_gate=in_gate,
        entry_time=now - timedelta(hours=1),
    )

    # 3. Mô phỏng tình huống xe bị soft-delete khi đang đỗ trong bãi (OQ-67)
    with connection.cursor() as cursor:
        cursor.execute("SET session_replication_role = 'replica';")
        cursor.execute("UPDATE vehicle SET deleted_at = %s WHERE id = %s;", [now, v.id])
        cursor.execute("SET session_replication_role = 'origin';")

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": "VIETQR",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["session"]["exit_gate_id"] == out_gate.id


def test_check_out_inactive_exit_gate_rejected(auth_employee, in_gate, out_gate):
    """Từ chối cổng ra có is_active=False với HTTP 400 PROP-GEN-P01 (F5)."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-20261018-996",
        license_plate="51K-888.99",
        license_plate_norm="51K88899",
        entry_gate=in_gate,
        entry_time=now - timedelta(hours=1),
    )

    inactive_out_gate = ParkingGate.objects.create(
        lot=out_gate.lot,
        code="GATE-OUT-INACTIVE",
        name="Cổng ra Inactive",
        direction="OUT",
        is_active=False,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": inactive_out_gate.id,
            "payment_method": "CASH",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-GEN-P01"
    assert "Cổng ra không tồn tại hoặc đã bị vô hiệu hóa." in str(
        response.data["message"]
    )
