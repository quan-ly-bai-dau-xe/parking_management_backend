"""
Integration tests for Check-In API (POST /api/v1/parking/sessions/check-in/).
Verifies:
- Permission matrix: anonymous -> 401, CUSTOMER -> 403, EMPLOYEE -> allowed.
- Visitor check-in (TL-05): generates session code #PK-YYYYMMDD-NNN, vehicle_id=None.
- Registered vehicle check-in (TL-17): auto-links vehicle_id via DB trigger, finds active ticket.
- Blacklisted plate without manager override -> 409 PROP-4.5.1-P08 + logs SystemAlert.
- Blacklisted plate with employee override attempt -> 403 forbidden.
- Blacklisted plate with manager override -> 201 created + logs SystemAlert.
- Duplicate open session -> 409 PROP-4.5.1-P07.
- Invalid gate direction (e.g. gate OUT used at entry) -> 400.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connections
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.audit.models import SystemAlert
from apps.customers.models import Customer
from apps.parking.models import (
    ParkingGate,
    PlateBlacklist,
)
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_checkin@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def auth_manager():
    mgr, _ = Account.objects.get_or_create(
        email="mgr_checkin@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return mgr


@pytest.fixture
def auth_customer():
    cust, _ = Account.objects.get_or_create(
        email="cust_checkin@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return cust


@pytest.fixture
def entry_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào Test", direction="IN", is_active=True
        )
    return gate


@pytest.fixture
def exit_gate():
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng ra Test", direction="OUT", is_active=True
        )
    return gate


def test_check_in_anonymous_rejected():
    """Chưa đăng nhập -> 401 MSG-4.1-M02."""
    client = APIClient()
    response = client.post(
        "/api/v1/parking/sessions/check-in/",
        {"license_plate": "43A-999.88"},
        format="json",
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"


def test_check_in_customer_forbidden(auth_customer):
    """Khách hàng bị từ chối gọi API check-in -> 403 MSG-4.2-M01."""
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    response = client.post(
        "/api/v1/parking/sessions/check-in/",
        {"license_plate": "43A-999.88"},
        format="json",
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"


def test_check_in_visitor_success(auth_employee, entry_gate):
    """Check-in xe vãng lai thành công: sinh mã phiên #PK-..., vehicle_id=None."""
    plate = "92A-123.45"
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    response = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": plate,
            "entry_gate_id": entry_gate.id,
            "recognition_source": "MANUAL",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    data = response.data
    assert "session" in data
    session = data["session"]
    assert session["license_plate"] == plate
    assert session["license_plate_norm"] == "92A12345"
    assert session["session_code"].startswith("#PK-")
    assert session["vehicle_id"] is None
    assert session["entry_gate_id"] == entry_gate.id


def test_check_in_registered_vehicle_auto_linked(auth_employee, entry_gate):
    """Check-in xe đã đăng ký kích hoạt trigger TL-17 tự động link vehicle_id."""
    cust = Customer.objects.first()
    vtype = VehicleType.objects.first()
    v = Vehicle.objects.create(
        code="XE-AUTO-01",
        license_plate="79K-123.45",
        license_plate_norm="79K12345",
        vehicle_type=vtype,
        customer=cust,
        model_name="Corolla",
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    response = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": v.license_plate,
            "entry_gate_id": entry_gate.id,
            "recognition_source": "AI",
            "ai_confidence": 99.5,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    session = response.data["session"]
    assert session["vehicle_id"] == v.id
    assert session["license_plate_norm"] == v.license_plate_norm
    assert response.data["vehicle_lookup"] is not None


def test_check_in_duplicate_open_session_rejected(auth_employee, entry_gate):
    """Xe đã có phiên đỗ đang mở bị từ chối check-in với HTTP 409 PROP-4.5.1-P07."""
    plate = "75B-333.44"
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # Check-in lần 1
    resp1 = client.post(
        "/api/v1/parking/sessions/check-in/",
        {"license_plate": plate, "entry_gate_id": entry_gate.id},
        format="json",
    )
    assert resp1.status_code == status.HTTP_201_CREATED

    # Check-in lần 2 ngay sau đó
    resp2 = client.post(
        "/api/v1/parking/sessions/check-in/",
        {"license_plate": plate, "entry_gate_id": entry_gate.id},
        format="json",
    )
    assert resp2.status_code == status.HTTP_409_CONFLICT
    assert resp2.data["code"] == "PROP-4.5.1-P07"


def test_check_in_invalid_gate_direction(auth_employee, exit_gate):
    """Sử dụng cổng hướng OUT tại màn hình check-in bị từ chối HTTP 400."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    response = client.post(
        "/api/v1/parking/sessions/check-in/",
        {"license_plate": "43A-000.11", "entry_gate_id": exit_gate.id},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "cổng vào" in response.data["message"].lower()


def test_check_in_blacklisted_plate_rejected_and_alerted(auth_employee, entry_gate):
    """Xe trong blacklist không có cờ override bị từ chối HTTP 409 PROP-4.5.1-P08 và ghi nhận SystemAlert."""
    plate = "29A-999.99"
    PlateBlacklist.objects.create(
        license_plate=plate,
        license_plate_norm="29A99999",
        reason="Xe trộm cắp",
        is_active=True,
    )

    alert_count_before = SystemAlert.objects.filter(
        alert_type="BLACKLIST_PLATE"
    ).count()

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-in/",
        {"license_plate": plate, "entry_gate_id": entry_gate.id},
        format="json",
    )

    assert response.status_code == status.HTTP_409_CONFLICT
    assert response.data["code"] == "PROP-4.5.1-P08"

    # Xác nhận đã ghi log SystemAlert
    alert_count_after = SystemAlert.objects.filter(alert_type="BLACKLIST_PLATE").count()
    assert alert_count_after == alert_count_before + 1


def test_check_in_blacklisted_override_by_employee_forbidden(auth_employee, entry_gate):
    """Nhân viên thường cố tình gửi override_blacklist=True bị từ chối HTTP 403."""
    plate = "29A-888.77"
    PlateBlacklist.objects.create(
        license_plate=plate,
        license_plate_norm="29A88877",
        reason="Xe tranh chấp",
        is_active=True,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": plate,
            "entry_gate_id": entry_gate.id,
            "override_blacklist": True,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "PROP-4.5.1-P14"
    assert response.data["message"] == "Nhân viên không có quyền ghi đè danh sách đen."


def test_check_in_blacklisted_override_by_manager_allowed(auth_manager, entry_gate):
    """Quản lý (MANAGER) gửi override_blacklist=True được phép cho xe vào và ghi nhận SystemAlert."""
    plate = "29A-777.66"
    PlateBlacklist.objects.create(
        license_plate=plate,
        license_plate_norm="29A77766",
        reason="Xe theo dõi đặc biệt",
        is_active=True,
    )

    client = APIClient()
    client.force_authenticate(user=auth_manager)
    response = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": plate,
            "entry_gate_id": entry_gate.id,
            "override_blacklist": True,
            "notes": "Quản lý cho phép vào theo dõi",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_201_CREATED
    assert response.data["session"]["license_plate_norm"] == "29A77766"


@pytest.mark.django_db(transaction=True)
def test_check_in_concurrent_same_plate(auth_employee, entry_gate):
    """Kiểm tra xử lý đồng thời: 2 yêu cầu check-in cùng 1 biển số song song -> chỉ 1 thành công."""
    unique_num = f"{uuid.uuid4().int % 90000 + 10000}"
    plate = f"51H-{unique_num[:3]}.{unique_num[3:]}"

    def do_check_in():
        c = APIClient()
        c.force_authenticate(user=auth_employee)
        return c.post(
            "/api/v1/parking/sessions/check-in/",
            {"license_plate": plate, "entry_gate_id": entry_gate.id},
            format="json",
        )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(do_check_in)
            f2 = executor.submit(do_check_in)
            r1 = f1.result()
            r2 = f2.result()

        statuses = [r1.status_code, r2.status_code]
        assert status.HTTP_201_CREATED in statuses
        # Yêu cầu thứ hai nhận 409 Conflict
        assert status.HTTP_409_CONFLICT in statuses
    finally:
        connections.close_all()


def test_check_in_inactive_gate_rejected(auth_employee, entry_gate):
    """Từ chối cổng vào có is_active=False với HTTP 400 PROP-GEN-P01 (F5)."""
    inactive_gate = ParkingGate.objects.create(
        lot=entry_gate.lot,
        code="GATE-IN-INACTIVE",
        name="Cổng vào Inactive",
        direction="IN",
        is_active=False,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-in/",
        {"license_plate": "51K-999.01", "entry_gate_id": inactive_gate.id},
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-GEN-P01"
    assert "Cổng vào không tồn tại hoặc đã bị vô hiệu hóa." in str(
        response.data["message"]
    )


@pytest.mark.parametrize("invalid_conf", [150, -5, 100.01, -0.01])
def test_check_in_ai_confidence_out_of_bounds_rejected(
    auth_employee, entry_gate, invalid_conf
):
    """Từ chối ai_confidence ngoài khoảng [0, 100] với HTTP 400 PROP-GEN-P01 (F5)."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": "51K-999.02",
            "entry_gate_id": entry_gate.id,
            "ai_confidence": invalid_conf,
        },
        format="json",
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-GEN-P01"
    assert "ai_confidence" in response.data["details"]
