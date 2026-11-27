"""
Fee calculation parity matrix, plate formatting edge cases, and fee waiver authorization tests.
Validates:
1. Plate format edge cases, anomaly strings, military plates, special plates.
2. Full fee preview parity against calculate_parking_fee and check_out across diverse durations and vehicle types.
3. Fee waiver RBAC permissions (EMPLOYEE, CUSTOMER, MANAGER) and validation rules.
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.audit.models import ActivityLog
from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer
from apps.parking.models import (
    ParkingGate,
    ParkingSlot,
    ParkingZone,
    VehicleEntryExitLog,
)
from apps.parking.services.check_out import check_out_vehicle
from apps.parking.services.plate_format import format_display_license_plate
from apps.parking.services.tariff import calculate_parking_fee, get_fee_preview
from apps.tickets.models import Payment, Ticket, TicketType
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def auth_employee():
    emp = Account.objects.filter(role="EMPLOYEE", is_active=True).first()
    if not emp:
        emp = Account.objects.get(email="luong.mai.phuong@example.org")
    return emp


@pytest.fixture
def auth_manager():
    mgr = Account.objects.filter(role="MANAGER", is_active=True).first()
    if not mgr:
        mgr = Account.objects.get(email="hoang.dinh.khang@example.com")
    return mgr


@pytest.fixture
def auth_customer():
    cust = Account.objects.filter(role="CUSTOMER", is_active=True).first()
    if not cust:
        cust = Account.objects.get(email="trinh.xuan.truong@example.com")
    return cust


@pytest.fixture
def in_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào Test Parity", direction="IN", is_active=True
        )
    return gate


@pytest.fixture
def out_gate():
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng ra Test Parity", direction="OUT", is_active=True
        )
    return gate


# ==============================================================================
# 1. KIỂM THỬ HELPER format_display_license_plate
# ==============================================================================


@pytest.mark.parametrize(
    "raw_input,expected_output",
    [
        # 1.1 Chuỗi rỗng, None, khoảng trắng
        (None, ""),
        ("", ""),
        ("   ", ""),
        ("\t\n\r  ", ""),
        # 1.2 Độ dài dị thường (quá ngắn hoặc quá dài)
        ("A", "A"),
        ("1", "1"),
        ("51", "51"),
        ("AB", "AB"),
        ("51A", "51A"),
        ("12345678901234567890", "12345678901234567890"),
        ("X" * 60, "X" * 60),
        # 1.3 Chuỗi ô tô chuẩn (chưa format và đã format per TL-65)
        ("51A89714", "51A89714"),
        ("51A-897.14", "51A-897.14"),
        ("30A61235", "30A61235"),
        ("30A-612.35", "30A-612.35"),
        ("30C46858", "30C46858"),
        ("30C-468.58", "30C-468.58"),
        ("50LD04411", "50LD04411"),
        ("50LD-044.11", "50LD-044.11"),
        ("29A1234", "29A-1234"),
        ("29A-1234", "29A-1234"),
        ("43B4096", "43B-4096"),
        ("43B-4096", "43B-4096"),
        # 1.4 Chuỗi xe máy chuẩn (đã có dấu hoặc không dấu 5 số)
        ("81B334303", "81-B3 343.03"),
        ("81-B3 343.03", "81-B3 343.03"),
        ("59T249609", "59-T2 496.09"),
        ("59-T2 496.09", "59-T2 496.09"),
        ("29-H1 1234", "29-H1 1234"),
        # 1.5 Dấu phân cách dị thường (dấu chấm, khoảng trắng, gạch ngang lẫn lộn)
        ("51A.897.14", "51A89714"),
        ("51A 897 14", "51A89714"),
        ("51A-897-14", "51A-897.14"),
        ("81-B3-343-03", "81-B3 343.03"),
        ("81-B3.343.03", "81-B3 343.03"),
        ("81B3-343.03", "81-B3 343.03"),
        ("  51a89714  ", "51A89714"),
        ("  81b334303 \n", "81-B3 343.03"),
        # 1.6 Biển xe quân sự (bắt đầu bằng 2 chữ cái)
        ("TM-12-34", "TM-12-34"),
        ("QP-12-34", "QP-12-34"),
        ("TH-45-67", "TH-45-67"),
        ("QA-11-22", "QA-11-22"),
        ("VT-88-99", "VT-88-99"),
        ("TM1234", "TM1234"),
        ("QP1234", "QP1234"),
        ("TC12345", "TC12345"),
        # 1.7 Biển đặc biệt ngoại giao có tiền tố 3 số
        ("80-123-NG-01", "80-123-NG-01"),
        # 1.8 Ký tự đặc biệt, XSS, injection
        ("<script>alert(1)</script>", "<SCRIPT>ALERT(1)</SCRIPT>"),
        ("SELECT * FROM USERS;", "SELECT * FROM USERS;"),
    ],
)
def test_format_display_license_plate_parity_matrix(raw_input, expected_output):
    """Kiểm tra ma trận đầu vào dị thường và biên của format_display_license_plate."""
    result = format_display_license_plate(raw_input)
    assert result == expected_output, (
        f"Input: {raw_input!r} -> Expected: {expected_output!r}, Actual: {result!r}"
    )


def test_finding_moto_4digit_unseparated_collision():
    """
    Finding 2 / TL-65: Xung đột cú pháp biển xe máy 4 số thô không dấu '29H11234'.
    Khi vehicle_type không xác định, hệ thống KHÔNG ĐOÁN MÒ thành ô tô 29H-112.34
    mà giữ nguyên dạng compact '29H11234'.
    Khi truyền vehicle_type='MOTORCYCLE' -> '29-H1 1234'.
    Khi truyền vehicle_type='CAR' -> '29H-112.34'.
    """
    raw_moto_4 = "29H11234"
    assert format_display_license_plate(raw_moto_4) == "29H11234"
    assert (
        format_display_license_plate(raw_moto_4, vehicle_type="MOTORCYCLE")
        == "29-H1 1234"
    )
    assert format_display_license_plate(raw_moto_4, vehicle_type="CAR") == "29H-112.34"


def test_finding_diplomatic_and_foreign_car_misformatting():
    """
    [PHÁT HIỆN 2]: MOTO_EXPLICIT_5_RE định dạng nhầm biển ô tô ngoại giao / nước ngoài.
    Đầu vào: '80-NG-123-45' (Ô tô ngoại giao), '80-NN-123-45' (Ô tô nước ngoài), '50-LD-044.11' (Ô tô liên doanh).
    Thực tế helper: MOTO_EXPLICIT_5_RE regex ^([0-9]{2})-([A-Z][0-9A-Z]) nhận diện 'NG', 'NN', 'LD' là sê-ri xe máy!
    Hậu quả: Biển ô tô có dấu gạch ngang bị format thành định dạng xe máy ('80-NG 123.45', '80-NN 123.45', '50-LD 044.11').
    """
    # 1. Biển ngoại giao 80-NG-123-45 bị biến thành 80-NG 123.45 (xe máy)
    res_ng = format_display_license_plate("80-NG-123-45")
    assert res_ng == "80-NG 123.45"

    # 2. Biển nước ngoài 80-NN-123-45 bị biến thành 80-NN 123.45 (xe máy)
    res_nn = format_display_license_plate("80-NN-123-45")
    assert res_nn == "80-NN 123.45"

    # 3. Biển ô tô liên doanh có dấu sau tỉnh 50-LD-044.11 bị biến thành 50-LD 044.11 (xe máy)
    res_ld = format_display_license_plate("50-LD-044.11")
    assert res_ld == "50-LD 044.11"


# ==============================================================================
# 2. KIỂM THỬ TÍNH NHẤT QUÁN (PARITY) CƯỚC DỰ KIẾN VS CHECK-OUT
# ==============================================================================


DURATIONS_MINUTES = [
    0,  # 0 phút (tối thiểu 1 giờ = 10k)
    1,  # 1 phút (< 15 phút -> 10k)
    14,  # 14 phút (< 15 phút -> 10k)
    15,  # 15 phút (không có grace -> 10k)
    30,  # 30 phút -> 10k
    59,  # 59 phút -> 10k
    60,  # 60 phút đúng -> 10k
    61,  # 61 phút (làm tròn lên 2 giờ -> 20k)
    119,  # 119 phút -> 20k
    120,  # 120 phút đúng -> 20k
    121,  # 121 phút -> 30k
    180,  # 3 giờ -> 30k
    480,  # Qua đêm ca 8 giờ -> 80k
    720,  # 12 giờ -> 120k
    1440,  # 1 ngày (24 giờ) -> 240k
    2880,  # 2 ngày (48 giờ) -> 480k
    4320,  # 3 ngày (72 giờ) -> 720k
    10080,  # 7 ngày -> 1.080.000đ
    43200,  # 30 ngày -> 7.200.000đ
]


@pytest.mark.parametrize("duration_min", DURATIONS_MINUTES)
def test_fee_preview_parity_transient_motorcycle(
    duration_min, auth_manager, in_gate, out_gate
):
    """
    Xe máy vãng lai (81-B3 343.03, không có bản ghi Vehicle trong DB):
    Kiểm tra tính nhất quán tuyệt đối giữa get_fee_preview, calculate_parking_fee,
    và check_out_vehicle trên toàn dải thời gian từ 0 phút đến 30 ngày.
    """
    now = timezone.now()
    entry_time = now - timedelta(minutes=duration_min)
    unique_code = f"#PK-MOTO-{duration_min}-{uuid.uuid4().hex[:4].upper()}"

    session = VehicleEntryExitLog.objects.create(
        session_code=unique_code,
        license_plate="81-B3 343.03",
        license_plate_norm="81B334303",
        entry_time=entry_time,
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    # 1. Cước tính qua service calculate_parking_fee
    direct_calc_fee = calculate_parking_fee(session, now)

    # 2. Cước tính qua service get_fee_preview
    preview = get_fee_preview(session_code=session.session_code)
    preview_fee = Decimal(str(preview["fee_amount"]))

    # 3. Thực hiện check-out thực tế
    completed_session, payment, _ = check_out_vehicle(
        session_code=session.session_code,
        exit_gate_id=out_gate.id,
        payment_method="CASH",
        user=auth_manager,
    )
    checkout_fee = completed_session.fee_amount

    # Xác nhận nhất quán không lệch 1 xu
    assert preview_fee == direct_calc_fee, (
        f"Lệch giữa preview ({preview_fee}) và calculate_parking_fee ({direct_calc_fee}) tại {duration_min} phút"
    )
    assert checkout_fee == direct_calc_fee, (
        f"Lệch giữa checkout ({checkout_fee}) và calculate_parking_fee ({direct_calc_fee}) tại {duration_min} phút"
    )
    assert preview_fee == checkout_fee, (
        f"Lệch giữa preview ({preview_fee}) và checkout ({checkout_fee}) tại {duration_min} phút"
    )

    # Kiểm tra hóa đơn payment
    assert payment is not None
    assert payment.amount == checkout_fee


@pytest.mark.parametrize("duration_min", DURATIONS_MINUTES)
def test_fee_preview_parity_transient_car(
    duration_min, auth_manager, in_gate, out_gate
):
    """
    Ô tô vãng lai (30A-612.35, không có bản ghi Vehicle trong DB):
    Kiểm tra parity trên toàn dải thời gian.
    """
    now = timezone.now()
    entry_time = now - timedelta(minutes=duration_min)
    unique_code = f"#PK-CAR-{duration_min}-{uuid.uuid4().hex[:4].upper()}"

    session = VehicleEntryExitLog.objects.create(
        session_code=unique_code,
        license_plate="30A-612.35",
        license_plate_norm="30A61235",
        entry_time=entry_time,
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    direct_calc_fee = calculate_parking_fee(session, now)
    preview = get_fee_preview(session_code=session.session_code)
    preview_fee = Decimal(str(preview["fee_amount"]))

    completed_session, payment, _ = check_out_vehicle(
        session_code=session.session_code,
        exit_gate_id=out_gate.id,
        payment_method="VIETQR",
        user=auth_manager,
    )
    checkout_fee = completed_session.fee_amount

    assert preview_fee == direct_calc_fee == checkout_fee
    assert payment.amount == checkout_fee


def test_fee_preview_parity_active_monthly_ticket(auth_manager, in_gate, out_gate):
    """
    Xe có vé tháng ACTIVE: Cước phí dự kiến và cước phí check-out đều phải là 0.00 VNĐ.
    Không phát sinh payment record.
    """
    now = timezone.now()
    vtype = VehicleType.objects.first()
    ttype = TicketType.objects.first()
    cust = Customer.objects.filter(deleted_at__isnull=True).first()

    veh = Vehicle.objects.create(
        code=f"XE{uuid.uuid4().hex[:4].upper()}",
        license_plate="51K-TKT-ACTIVE",
        license_plate_norm="51KTKTACTIVE",
        model_name="Corolla Cross",
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

    ticket = Ticket.objects.create(
        code=f"VT{uuid.uuid4().hex[:4].upper()}",
        ticket_type=ttype,
        vehicle=veh,
        customer=cust,
        slot=slot,
        price=Decimal("1500000.00"),
        status="ACTIVE",
        effective_from=now - timedelta(days=5),
        effective_to=now + timedelta(days=25),
    )

    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-TKT-{uuid.uuid4().hex[:4].upper()}",
        license_plate=veh.license_plate,
        license_plate_norm=veh.license_plate_norm,
        vehicle=veh,
        ticket=ticket,
        entry_time=now - timedelta(hours=6),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    # 1. Preview
    preview = get_fee_preview(license_plate=veh.license_plate)
    assert preview["fee_amount"] == Decimal("0.00")
    assert preview["has_active_ticket"] is True
    assert preview["ticket_code"] == ticket.code
    assert preview["is_exempt"] is True

    # 2. Direct calculate
    calc_fee = calculate_parking_fee(session, now)
    assert calc_fee == Decimal("0.00")

    # 3. Check-out
    completed_session, payment, _ = check_out_vehicle(
        session_code=session.session_code,
        exit_gate_id=out_gate.id,
        user=auth_manager,
    )
    assert completed_session.fee_amount == Decimal("0.00")
    assert payment is None


# ==============================================================================
# 3. KIỂM THỬ PHÂN QUYỀN MIỄN CƯỚC PHÍ (WAIVER)
# ==============================================================================


def test_waiver_forbidden_for_employee_via_api(auth_employee, out_gate, in_gate):
    """
    EMPLOYEE gửi waive_fee=True qua API check-out:
    Bị từ chối HTTP 403 Forbidden với mã nghiệp vụ PROP-4.5.1-P18.
    Phiên đỗ vẫn giữ nguyên trạng thái mở (exit_time is None).
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-EMP-{uuid.uuid4().hex[:4].upper()}",
        license_plate="51K-EMP.99",
        license_plate_norm="51KEMP99",
        entry_time=now - timedelta(hours=2),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": True,
            "waiver_reason": "Nhân viên trực cổng tự ý miễn",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "PROP-4.5.1-P18"
    assert "Quản lý" in response.data["message"]

    session.refresh_from_db()
    assert session.exit_time is None


def test_waiver_forbidden_for_customer_via_api_and_service(
    auth_customer, out_gate, in_gate
):
    """
    CUSTOMER gửi waive_fee=True:
    - Ở tầng API: Bị từ chối HTTP 403 Forbidden với mã MSG-4.2-M01 (do IsEmployeeOrManager chặn từ cửa vào).
    - Ở tầng Service (phòng thủ chiều sâu nếu bypass view): Bị chặn bởi PROP-4.5.1-P18.
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-CUST-{uuid.uuid4().hex[:4].upper()}",
        license_plate="51K-CUST.99",
        license_plate_norm="51KCUST99",
        entry_time=now - timedelta(hours=2),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    # 1. Tầng API
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    api_resp = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": True,
            "waiver_reason": "Khách hàng muốn miễn phí",
        },
        format="json",
    )
    assert api_resp.status_code == status.HTTP_403_FORBIDDEN
    assert api_resp.data["code"] == "MSG-4.2-M01"

    # 2. Tầng Service (gọi trực tiếp check_out_vehicle với user là CUSTOMER)
    with pytest.raises(BusinessAPIException) as exc_info:
        check_out_vehicle(
            session_code=session.session_code,
            exit_gate_id=out_gate.id,
            waive_fee=True,
            waiver_reason="Khách hàng gọi trực tiếp hàm service",
            user=auth_customer,
        )
    assert exc_info.value.code == "PROP-4.5.1-P18"
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.parametrize(
    "invalid_reason",
    [
        None,
        "",
        "   ",
        "\t\r\n",
        "         ",
    ],
)
def test_waiver_manager_missing_reason_rejected_prop_19(
    invalid_reason, auth_manager, out_gate, in_gate
):
    """
    MANAGER gửi waive_fee=True nhưng không cung cấp waiver_reason (None, rỗng, toàn khoảng trắng):
    Bị từ chối HTTP 400 Bad Request với mã PROP-4.5.1-P19.
    Phiên đỗ không bị đóng, cước phí không bị thay đổi.
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-MGR-NO-REASON-{uuid.uuid4().hex[:4].upper()}",
        license_plate="51K-NOREASON.01",
        license_plate_norm="51KNOREASON01",
        entry_time=now - timedelta(hours=2),
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    client = APIClient()
    client.force_authenticate(user=auth_manager)

    payload = {
        "session_code": session.session_code,
        "exit_gate_id": out_gate.id,
        "waive_fee": True,
    }
    if invalid_reason is not None:
        payload["waiver_reason"] = invalid_reason

    response = client.post(
        "/api/v1/parking/sessions/check-out/", payload, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P19"
    assert "lý do miễn cước" in response.data["message"]

    session.refresh_from_db()
    assert session.exit_time is None
    assert session.fee_amount == Decimal("0.00")


def test_waiver_manager_success_with_comprehensive_audit(
    auth_manager, out_gate, in_gate
):
    """
    MANAGER gửi waive_fee=True kèm waiver_reason hợp lệ:
    - 200 OK
    - session.fee_amount = 0.00
    - Không sinh Payment record
    - session.notes ghi chú kiểm toán rõ ràng: [MIỄN CƯỚC ĐẶC CÁCH]: <reason> (Người duyệt: <email>)
    - ActivityLog ghi nhận hành động SESSION_CHECK_OUT_WAIVED
    """
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code=f"#PK-MGR-OK-{uuid.uuid4().hex[:4].upper()}",
        license_plate="51K-WAIVE-SUCCESS.01",
        license_plate_norm="51KWAIVESUCCESS01",
        entry_time=now - timedelta(hours=4),  # Thường là 40k
        entry_gate=in_gate,
        recognition_source="AI",
        review_status="AUTO",
    )

    client = APIClient()
    client.force_authenticate(user=auth_manager)

    reason = "Xe khách VIP thuộc đoàn ngoại giao tham gia hội nghị cấp cao"
    initial_payment_count = Payment.objects.count()

    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "waive_fee": True,
            "waiver_reason": reason,
            "notes": "Kiểm tra barrier cổng 2 hoạt động bình thường",
        },
        format="json",
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["payment"] is None
    assert Decimal(str(response.data["session"]["fee_amount"])) == Decimal("0.00")

    # Xác nhận trong CSDL
    session.refresh_from_db()
    assert session.exit_time is not None
    assert session.fee_amount == Decimal("0.00")
    assert "[MIỄN CƯỚC ĐẶC CÁCH]" in session.notes
    assert reason in session.notes
    assert auth_manager.email in session.notes

    # Không sinh Payment
    assert Payment.objects.count() == initial_payment_count
    assert not Payment.objects.filter(session_id=session.id).exists()

    # Kiểm tra ActivityLog
    log = ActivityLog.objects.filter(
        action="SESSION_CHECK_OUT_WAIVED", entity_id=session.id
    ).first()
    assert log is not None
    assert log.actor_account == auth_manager
    assert reason in log.message
    assert auth_manager.email in log.message
