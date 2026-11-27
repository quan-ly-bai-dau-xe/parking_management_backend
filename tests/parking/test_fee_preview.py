"""
Integration and edge-case tests for Fee Preview API (GET /api/v1/parking/sessions/fee-preview/)
and minimum hourly parking tariff calculations.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.models import (
    ParkingGate,
    ParkingSlot,
    ParkingZone,
    VehicleEntryExitLog,
)
from apps.parking.services.tariff import calculate_parking_fee
from apps.tickets.models import Ticket, TicketType
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


def unique_session_code():
    return f"#PK-TEST-PREVIEW-{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture
def auth_employee():
    emp = Account.objects.filter(role="EMPLOYEE", is_active=True).first()
    if not emp:
        emp, _ = Account.objects.get_or_create(
            email="emp_feepreview@parking.local",
            defaults={"role": "EMPLOYEE", "is_active": True, "password": "!dummy"},
        )
    return emp


@pytest.fixture
def auth_manager():
    mgr = Account.objects.filter(role="MANAGER", is_active=True).first()
    if not mgr:
        mgr, _ = Account.objects.get_or_create(
            email="mgr_feepreview@parking.local",
            defaults={"role": "MANAGER", "is_active": True, "password": "!dummy"},
        )
    return mgr


@pytest.fixture
def auth_customer():
    cust = Account.objects.filter(role="CUSTOMER", is_active=True).first()
    if not cust:
        cust, _ = Account.objects.get_or_create(
            email="cust_feepreview@parking.local",
            defaults={"role": "CUSTOMER", "is_active": True, "password": "!dummy"},
        )
    return cust


@pytest.fixture
def in_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào Test Preview", direction="IN", is_active=True
        )
    return gate


@pytest.fixture
def out_gate():
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng ra Test Preview", direction="OUT", is_active=True
        )
    return gate


@pytest.fixture
def open_transient_session(in_gate):
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-PREVIEW-01",
        license_plate="51K-992.14",
        license_plate_norm="51K99214",
        entry_time=now
        - timedelta(minutes=95),  # 1 hour 35 mins -> 2 hours = 20,000 VND
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
        ai_confidence=Decimal("95.00"),
    )
    return session


# ==============================================================================
# SECTION 1: CORE FEE PREVIEW API TESTS
# ==============================================================================


def test_fee_preview_anonymous_rejected():
    """Chưa đăng nhập -> 401."""
    client = APIClient()
    response = client.get(
        "/api/v1/parking/sessions/fee-preview/?license_plate=51K-992.14"
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_fee_preview_customer_rejected(auth_customer):
    """Tài khoản CUSTOMER -> 403 Forbidden."""
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    response = client.get(
        "/api/v1/parking/sessions/fee-preview/?license_plate=51K-992.14"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"


def test_fee_preview_missing_both_params(auth_employee):
    """Thiếu cả 2 param -> 400 Bad Request PROP-4.5.1-P11."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/sessions/fee-preview/")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P11"


def test_fee_preview_open_session_not_found(auth_employee):
    """Không có phiên mở -> 404 PROP-4.5.1-P06."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        "/api/v1/parking/sessions/fee-preview/?license_plate=99Z-999.99"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "PROP-4.5.1-P06"


def test_fee_preview_closed_session_returns_404(auth_employee, in_gate):
    """Phiên đã kết thúc (exit_time IS NOT NULL) -> 404 PROP-4.5.1-P06."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-CLOSED-01",
        license_plate="51K-111.11",
        license_plate_norm="51K11111",
        entry_time=now - timedelta(hours=2),
        exit_time=now - timedelta(hours=1),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        f"/api/v1/parking/sessions/fee-preview/?session_code={session.session_code}"
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.data["code"] == "PROP-4.5.1-P06"


def test_fee_preview_transient_by_plate_success(auth_employee, open_transient_session):
    """Xem trước phí xe vãng lai theo biển số: 95 phút = 2 giờ = 20,000 VND."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        f"/api/v1/parking/sessions/fee-preview/?license_plate={open_transient_session.license_plate}"
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert data["session_id"] == open_transient_session.id
    assert data["session_code"] == open_transient_session.session_code
    assert data["license_plate"] == open_transient_session.license_plate
    assert data["duration_minutes"] >= 95
    assert "1 giờ" in data["duration_text"]
    assert Decimal(str(data["fee_amount"])) == Decimal("20000.00")
    assert data["has_active_ticket"] is False
    assert data["ticket_code"] is None
    assert data["is_exempt"] is False
    assert Decimal(str(data["hourly_rate"])) == Decimal("10000.00")


def test_fee_preview_transient_by_code_success(auth_manager, open_transient_session):
    """Quản lý xem trước phí theo mã phiên."""
    client = APIClient()
    client.force_authenticate(user=auth_manager)
    response = client.get(
        f"/api/v1/parking/sessions/fee-preview/?session_code={open_transient_session.session_code}"
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert data["session_code"] == open_transient_session.session_code
    assert Decimal(str(data["fee_amount"])) == Decimal("20000.00")


def test_fee_preview_active_ticket_exempt(auth_employee):
    """Xe có vé tháng ACTIVE còn hạn -> fee_amount = 0.00, is_exempt = True, has_active_ticket = True."""
    session = VehicleEntryExitLog.objects.filter(
        session_code="#PK-20261017-037", exit_time__isnull=True
    ).first()
    assert session is not None, (
        "Yêu cầu phiên mở #PK-20261017-037 tồn tại trong seed data"
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(
        f"/api/v1/parking/sessions/fee-preview/?license_plate={session.license_plate}"
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert Decimal(str(data["fee_amount"])) == Decimal("0.00")
    assert data["has_active_ticket"] is True
    assert data["ticket_code"] == session.ticket.code
    assert data["is_exempt"] is True


# ==============================================================================
# SECTION 2: DEFENSIVE EDGE CASES & NORMALIZATION
# ==============================================================================


def test_fee_preview_no_15min_grace_rule(auth_employee, in_gate):
    """
    Khách vãng lai đỗ 10 phút (< 15 phút).
    Backend Single Source of Truth: Không có quy tắc miễn phí 15 phút.
    Cước phí phải là 10.000 VNĐ (tối thiểu 1 giờ).
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-PREVIEW-10MIN",
        license_plate="51K-100.10",
        license_plate_norm="51K10010",
        entry_time=now - timedelta(minutes=10),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    resp = client.get(
        f"/api/v1/parking/sessions/fee-preview/?license_plate={session.license_plate}"
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.data
    assert Decimal(str(data["fee_amount"])) == Decimal("10000.00")
    assert data["is_exempt"] is False
    assert data["duration_minutes"] == 10


def test_fee_preview_hourly_boundaries(auth_employee, in_gate):
    """
    Kiểm tra ranh giới làm tròn thời gian tính cước:
    - 60 phút: đúng 1 giờ = 10.000 VNĐ
    - 61 phút: làm tròn lên 2 giờ = 20.000 VNĐ
    """
    now = timezone.now()
    s60 = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-PREVIEW-60MIN",
        license_plate="51K-060.00",
        license_plate_norm="51K06000",
        entry_time=now - timedelta(minutes=60),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    s61 = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-PREVIEW-61MIN",
        license_plate="51K-061.00",
        license_plate_norm="51K06100",
        entry_time=now - timedelta(minutes=61),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp60 = client.get(
        f"/api/v1/parking/sessions/fee-preview/?session_code={s60.session_code}"
    )
    assert resp60.status_code == status.HTTP_200_OK
    assert Decimal(str(resp60.data["fee_amount"])) == Decimal("10000.00")

    resp61 = client.get(
        f"/api/v1/parking/sessions/fee-preview/?session_code={s61.session_code}"
    )
    assert resp61.status_code == status.HTTP_200_OK
    assert Decimal(str(resp61.data["fee_amount"])) == Decimal("20000.00")


def test_fee_preview_unregistered_transient_no_vehicle_fk(auth_employee, in_gate):
    """
    Xe vãng lai hoàn toàn không có bản ghi Vehicle trong DB (vehicle_id=None).
    Endpoint hoạt động bình thường, không sinh lỗi.
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-PREVIEW-TRANSIENT",
        license_plate="29A-999.88",
        license_plate_norm="29A99988",
        vehicle=None,
        ticket=None,
        entry_time=now - timedelta(hours=2),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    resp = client.get(
        f"/api/v1/parking/sessions/fee-preview/?license_plate={session.license_plate}"
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["has_active_ticket"] is False
    assert resp.data["ticket_code"] is None
    assert Decimal(str(resp.data["fee_amount"])) == Decimal("20000.00")


def test_fee_preview_expired_ticket_charges_normal_fee(auth_employee, in_gate):
    """
    Xe có vé tháng nhưng vé tháng ĐÃ HẾT HẠN (effective_to < now).
    Cước phí phải được tính như xe bình thường, không được miễn phí.
    """
    now = timezone.now()
    vtype = VehicleType.objects.first()
    ttype = TicketType.objects.first()
    cust = Customer.objects.filter(deleted_at__isnull=True).first()
    veh = Vehicle.objects.create(
        code=f"XE{uuid.uuid4().hex[:4].upper()}",
        license_plate="51K-EXPIRED",
        model_name="Vios",
        vehicle_type=vtype,
        customer=cust,
    )
    slot = ParkingSlot.objects.first()
    expired_ticket = Ticket.objects.create(
        code=f"VT{uuid.uuid4().hex[:4].upper()}",
        ticket_type=ttype,
        vehicle=veh,
        customer=cust,
        slot=slot,
        price=Decimal("500000.00"),
        status="ACTIVE",
        effective_from=now - timedelta(days=60),
        effective_to=now - timedelta(days=1),  # Hết hạn hôm qua
    )
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-PREVIEW-EXPTICKET",
        license_plate="51K-EXPIRED",
        license_plate_norm="51KEXPIRED",
        vehicle=veh,
        ticket=expired_ticket,
        entry_time=now - timedelta(hours=3),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    resp = client.get(
        f"/api/v1/parking/sessions/fee-preview/?license_plate={session.license_plate}"
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.data
    assert data["has_active_ticket"] is False
    assert data["ticket_code"] is None
    assert data["is_exempt"] is False
    assert Decimal(str(data["fee_amount"])) == Decimal("30000.00")


def test_fee_preview_multiple_closed_sessions_no_open_session(
    auth_employee, in_gate, out_gate
):
    """
    Biển số đã từng vào ra nhiều lần trong quá khứ (tất cả exit_time đều NOT NULL),
    nhưng hiện tại KHÔNG có phiên đỗ nào đang mở.
    Kỳ vọng: 404 NOT FOUND (PROP-4.5.1-P06), không được nhầm lẫn phiên cũ.
    """
    now = timezone.now()
    plate = "51H-MULTI-OLD"
    norm = "51HMULTIOLD"
    for i in range(3):
        VehicleEntryExitLog.objects.create(
            session_code=f"#PK-TEST-PREVIEW-OLD-{i}",
            license_plate=plate,
            license_plate_norm=norm,
            entry_time=now - timedelta(days=i + 2),
            exit_time=now - timedelta(days=i + 1),
            entry_gate=in_gate,
            exit_gate=out_gate,
            recognition_source="AI",
            review_status="AUTO",
        )
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    resp = client.get(f"/api/v1/parking/sessions/fee-preview/?license_plate={plate}")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.data["code"] == "PROP-4.5.1-P06"


def test_fee_preview_both_params_matching_and_conflicting(auth_employee, in_gate):
    """
    1. Cung cấp cả license_plate và session_code của cùng 1 phiên -> 200 OK.
    2. Cung cấp cả hai nhưng thuộc 2 phiên khác nhau -> theo logic get_open_session_by_identifier,
       session_code được ưu tiên.
    """
    now = timezone.now()
    s1 = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-PREVIEW-PAIR-1",
        license_plate="51K-PAIR-01",
        license_plate_norm="51KPAIR01",
        entry_time=now - timedelta(hours=1),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    s2 = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-PREVIEW-PAIR-2",
        license_plate="51K-PAIR-02",
        license_plate_norm="51KPAIR02",
        entry_time=now - timedelta(hours=2),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # Cả hai tham số khớp cùng phiên
    resp_match = client.get(
        f"/api/v1/parking/sessions/fee-preview/?license_plate={s1.license_plate}&session_code={s1.session_code}"
    )
    assert resp_match.status_code == status.HTTP_200_OK
    assert resp_match.data["session_code"] == s1.session_code

    # Cả hai tham số nhưng khác phiên -> session_code được ưu tiên
    resp_conflict = client.get(
        f"/api/v1/parking/sessions/fee-preview/?license_plate={s2.license_plate}&session_code={s1.session_code}"
    )
    assert resp_conflict.status_code == status.HTTP_200_OK
    assert resp_conflict.data["session_code"] == s1.session_code


def test_fee_preview_whitespace_and_normalization(auth_employee, in_gate):
    """
    Biển số nhập chữ thường '51k-norm.99', có khoảng trắng hai đầu '  51K-NORM.99  '.
    Hệ thống tự động chuẩn hóa và tìm ra phiên đỗ đang mở.
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-TEST-PREVIEW-NORM",
        license_plate="51K-NORM.99",
        license_plate_norm="51KNORM99",
        entry_time=now - timedelta(hours=1),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # Chữ thường
    resp_lower = client.get(
        "/api/v1/parking/sessions/fee-preview/?license_plate=51k-norm.99"
    )
    assert resp_lower.status_code == status.HTTP_200_OK
    assert resp_lower.data["session_id"] == session.id

    # Khoảng trắng xung quanh
    resp_spaces = client.get(
        "/api/v1/parking/sessions/fee-preview/?license_plate=%20%2051K-NORM.99%20%20"
    )
    assert resp_spaces.status_code == status.HTTP_200_OK
    assert resp_spaces.data["session_id"] == session.id


def test_fee_preview_all_whitespace_rejected_400(auth_employee):
    """
    Truyền license_plate="   " và session_code="   " -> 400 Bad Request PROP-4.5.1-P11.
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    resp = client.get(
        "/api/v1/parking/sessions/fee-preview/?license_plate=%20%20%20&session_code=%20%20"
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "PROP-4.5.1-P11"


# ==============================================================================
# SECTION 3: TARIFF FORMULA AND TIME BOUNDARIES
# ==============================================================================


def test_tariff_duration_zero_seconds():
    """0 giây đỗ: tính 1 giờ = 10.000 VNĐ."""
    now = timezone.now()
    session = VehicleEntryExitLog(
        session_code=unique_session_code(),
        license_plate="51K-000.00",
        license_plate_norm="51K00000",
        entry_time=now,
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("10000.00")


def test_tariff_duration_under_15_minutes_no_free_grace():
    """Đỗ 14 phút (dưới 15 phút): không có quy tắc miễn phí, vẫn tính 10.000 VNĐ."""
    now = timezone.now()
    session = VehicleEntryExitLog(
        session_code=unique_session_code(),
        license_plate="51K-014.00",
        license_plate_norm="51K01400",
        entry_time=now - timedelta(minutes=14),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("10000.00")


def test_tariff_duration_exact_one_hour():
    """Đỗ đúng 3600 giây: tính đúng 1 giờ = 10.000 VNĐ."""
    now = timezone.now()
    session = VehicleEntryExitLog(
        session_code=unique_session_code(),
        license_plate="51K-060.00",
        license_plate_norm="51K06000",
        entry_time=now - timedelta(seconds=3600),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("10000.00")


def test_tariff_duration_one_second_over_one_hour():
    """Đỗ 3601 giây (1 giờ 1 giây): làm tròn lên 2 giờ = 20.000 VNĐ."""
    now = timezone.now()
    session = VehicleEntryExitLog(
        session_code=unique_session_code(),
        license_plate="51K-060.01",
        license_plate_norm="51K06001",
        entry_time=now - timedelta(seconds=3601),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("20000.00")


def test_tariff_duration_one_second_over_two_hours():
    """Đỗ 7201 giây (2 giờ 1 giây): làm tròn lên 3 giờ = 30.000 VNĐ."""
    now = timezone.now()
    session = VehicleEntryExitLog(
        session_code=unique_session_code(),
        license_plate="51K-120.01",
        license_plate_norm="51K12001",
        entry_time=now - timedelta(seconds=7201),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("30000.00")


# ==============================================================================
# SECTION 4: THIN CONTROLLER AST INSPECTION & CHECKOUT PARITY VERIFICATION
# ==============================================================================


def test_fee_preview_view_is_thin_controller():
    """
    AST introspection proves that FeePreviewView.get is a thin controller (< 30 lines)
    and strictly delegates business logic to get_fee_preview without leaking inline
    database queries or tariff calculations.
    """
    import inspect

    from apps.parking.views.sessions import FeePreviewView

    source = inspect.getsource(FeePreviewView.get)
    def_index = source.find("def get(")
    body_source = source[def_index:] if def_index != -1 else source
    lines = [
        line.strip()
        for line in body_source.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]

    assert len(lines) <= 30, f"FeePreviewView.get is too long: {len(lines)} lines"
    assert "get_fee_preview" in source, "View must delegate to get_fee_preview service"
    assert "Ticket.objects" not in source, (
        "View must not contain direct Ticket database queries"
    )
    assert "calculate_parking_fee" not in source, (
        "Tariff computation must reside in service layer"
    )


def test_fee_preview_matches_checkout_fee_transient(auth_manager, in_gate, out_gate):
    """
    Chứng minh cước phí dự kiến từ fee-preview hoàn toàn nhất quán (100% parity)
    với cước phí thực tế khi check-out cho xe vãng lai.
    """
    from apps.parking.services.check_out import check_out_vehicle

    now = timezone.now()
    session_code = f"#PK-PAR-{uuid.uuid4().hex[:6].upper()}"
    session = VehicleEntryExitLog.objects.create(
        session_code=session_code,
        license_plate="51K-PARITY.01",
        license_plate_norm="51KPARITY01",
        entry_time=now
        - timedelta(minutes=125),  # 2 hours 5 mins -> 3 hours = 30,000 VND
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    client = APIClient()
    client.force_authenticate(user=auth_manager)
    resp = client.get(
        f"/api/v1/parking/sessions/fee-preview/?session_code={session.session_code}"
    )
    assert resp.status_code == status.HTTP_200_OK
    preview_fee = Decimal(str(resp.data["fee_amount"]))
    assert preview_fee == Decimal("30000.00")

    # Check-out cùng một phiên đỗ
    completed_session, payment, _ = check_out_vehicle(
        session_code=session.session_code,
        exit_gate_id=out_gate.id,
        payment_method="CASH",
        user=auth_manager,
    )

    assert completed_session.fee_amount == Decimal("30000.00")
    assert payment is not None
    assert payment.amount == Decimal("30000.00")
    assert preview_fee == completed_session.fee_amount


def test_fee_preview_matches_checkout_fee_with_active_ticket(
    auth_manager, in_gate, out_gate
):
    """
    Chứng minh cước phí dự kiến từ fee-preview hoàn toàn nhất quán (0.00 VND)
    với cước phí thực tế khi check-out cho xe có vé tháng ACTIVE.
    """
    from apps.parking.services.check_out import check_out_vehicle

    now = timezone.now()
    vtype = VehicleType.objects.first()
    ttype = TicketType.objects.first()
    cust = Customer.objects.filter(deleted_at__isnull=True).first()
    veh = Vehicle.objects.create(
        code=f"XE{uuid.uuid4().hex[:4].upper()}",
        license_plate="51K-TICKET-PARITY",
        model_name="Camry",
        vehicle_type=vtype,
        customer=cust,
    )
    ticket_slot_ids = Ticket.objects.filter(deleted_at__isnull=True).values_list(
        "slot_id", flat=True
    )
    slot = (
        ParkingSlot.objects.filter(status="AVAILABLE")
        .exclude(id__in=ticket_slot_ids)
        .first()
    )
    if not slot:
        zone = ParkingZone.objects.first()
        slot = ParkingSlot.objects.create(
            zone=zone,
            code=f"S{uuid.uuid4().hex[:4].upper()}",
            slot_kind="STANDARD",
            status="AVAILABLE",
        )
    active_ticket = Ticket.objects.create(
        code=f"VT{uuid.uuid4().hex[:4].upper()}",
        ticket_type=ttype,
        vehicle=veh,
        customer=cust,
        slot=slot,
        price=Decimal("1200000.00"),
        status="ACTIVE",
        effective_from=now - timedelta(days=10),
        effective_to=now + timedelta(days=20),
    )
    session_code = f"#PK-PAR-{uuid.uuid4().hex[:6].upper()}"
    session = VehicleEntryExitLog.objects.create(
        session_code=session_code,
        license_plate=veh.license_plate,
        license_plate_norm="51KTICKETPARITY",
        vehicle=veh,
        ticket=active_ticket,
        entry_time=now - timedelta(hours=4),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    client = APIClient()
    client.force_authenticate(user=auth_manager)
    resp = client.get(
        f"/api/v1/parking/sessions/fee-preview/?license_plate={veh.license_plate}"
    )
    assert resp.status_code == status.HTTP_200_OK
    preview_fee = Decimal(str(resp.data["fee_amount"]))
    assert preview_fee == Decimal("0.00")
    assert resp.data["has_active_ticket"] is True
    assert resp.data["ticket_code"] == active_ticket.code
    assert resp.data["is_exempt"] is True

    # Check-out phiên này
    completed_session, payment, _ = check_out_vehicle(
        session_code=session.session_code,
        exit_gate_id=out_gate.id,
        user=auth_manager,
    )

    assert completed_session.fee_amount == Decimal("0.00")
    assert payment is None
    assert preview_fee == completed_session.fee_amount
