"""
Unit and integration tests for license plate display formatting and check-in storage parity.
Validates format_display_license_plate helper and check_in_vehicle behavior for registered vs visitor plates.
"""

import uuid

import pytest
from django.db import connection

from apps.accounts.models import Account
from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer
from apps.parking.models import (
    ParkingGate,
    ParkingSlot,
    ParkingZone,
    SlotAllowedVehicleType,
    VehicleEntryExitLog,
)
from apps.parking.selectors.sessions import get_open_session_by_identifier
from apps.parking.services.check_in import check_in_vehicle
from apps.parking.services.ocr import PlateRecognizer
from apps.parking.services.plate_format import format_display_license_plate
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


# ==============================================================================
# SECTION 1: TABLE-DRIVEN TESTS FOR format_display_license_plate (TL-65)
# ==============================================================================


@pytest.mark.parametrize(
    "raw_input,vehicle_type,expected_output",
    [
        # --- 1. Ambiguous Shape A: 8 chars (^[0-9]{2}[A-Z][0-9]{5}$) ---
        # "29H11234" (Car 5-digit vs Moto 4-digit)
        ("29H11234", None, "29H11234"),
        ("29H11234", "CAR", "29H-112.34"),
        ("29H11234", "MOTORCYCLE", "29-H1 1234"),
        ("29H1 1234", None, "29H11234"),
        ("29H1 1234", "MOTORCYCLE", "29-H1 1234"),
        ("29-H1 1234", None, "29-H1 1234"),
        ("29-H1 1234", "CAR", "29-H1 1234"),  # Explicit separator preserved
        # Demo plate: "51A89714"
        ("51A89714", None, "51A89714"),
        ("51A89714", "CAR", "51A-897.14"),
        ("51A89714", "MOTORCYCLE", "51-A8 9714"),
        ("51A-897.14", None, "51A-897.14"),
        ("51A-897.14", "CAR", "51A-897.14"),
        # Clip plate: "30A61235" (Hanoi car)
        ("30A61235", None, "30A61235"),
        ("30A61235", "CAR", "30A-612.35"),
        ("30A61235", "MOTORCYCLE", "30-A6 1235"),
        ("30A-612.35", None, "30A-612.35"),
        # Other ambiguous 8-char plates
        ("30C46858", None, "30C46858"),
        ("30C46858", "CAR", "30C-468.58"),
        ("43K86050", None, "43K86050"),
        ("43K86050", "CAR", "43K-860.50"),
        ("29A99988", None, "29A99988"),
        ("29A99988", "CAR", "29A-999.88"),
        # --- 2. Ambiguous Shape B: 9 chars 2-letter (^[0-9]{2}[A-Z]{2}[0-9]{5}$) ---
        # "29MD12345" (Car 5-digit 2-letter vs Moto electric 5-digit)
        ("29MD12345", None, "29MD12345"),
        ("29MD12345", "CAR", "29MD-123.45"),
        ("29MD12345", "MOTORCYCLE", "29-MD 123.45"),
        ("50LD04411", None, "50LD04411"),
        ("50LD04411", "CAR", "50LD-044.11"),
        # --- 3. Ambiguous Shape C: 8 chars 2-letter (^[0-9]{2}[A-Z]{2}[0-9]{4}$) ---
        ("29LD1234", None, "29LD1234"),
        ("29LD1234", "CAR", "29LD-1234"),
        ("29LD1234", "MOTORCYCLE", "29-LD 1234"),
        # --- 4. Unambiguous Motorcycle: 9 chars (^[0-9]{2}[A-Z][0-9][0-9]{5}$) ---
        # Clip plate: "81B334303" (Gia Lai motorcycle)
        ("81B334303", None, "81-B3 343.03"),
        ("81-B3 343.03", None, "81-B3 343.03"),
        # Clip plate: "59T249609" (TP.HCM motorcycle)
        ("59T249609", None, "59-T2 496.09"),
        ("59-T2 496.09", None, "59-T2 496.09"),
        # "59X112345"
        ("59X112345", None, "59-X1 123.45"),
        # --- 5. Unambiguous Car 4-digit: 7 chars (^[0-9]{2}[A-Z][0-9]{4}$) ---
        ("29A1234", None, "29A-1234"),
        ("43B4096", None, "43B-4096"),
        ("52S5678", None, "52S-5678"),
        # --- 6. Lowercase / Mixed case with whitespace ---
        ("  51a89714  ", None, "51A89714"),
        ("  51a89714  ", "CAR", "51A-897.14"),
        ("30a-612.35", None, "30A-612.35"),
        ("81b334303", None, "81-B3 343.03"),
    ],
)
def test_format_display_license_plate_table_driven(
    raw_input: str, vehicle_type: str | None, expected_output: str
):
    """Kiểm tra toàn diện bảng table-driven cho cả ambiguous và unambiguous per TL-65."""
    assert format_display_license_plate(raw_input, vehicle_type) == expected_output


@pytest.mark.parametrize(
    "edge_input,expected_output",
    [
        (None, ""),
        ("", ""),
        ("   ", ""),
        ("UNKNOWN_CODE", "UNKNOWN_CODE"),
        ("TM-12-34", "TM-12-34"),
    ],
)
def test_format_display_license_plate_edge_cases(
    edge_input: str | None, expected_output: str
):
    """Kiểm tra xử lý các giá trị biên, rỗng, None hoặc cấu trúc không quy chuẩn."""
    assert format_display_license_plate(edge_input) == expected_output


# ==============================================================================
# SECTION 2: INTEGRATION TESTS WITH CHECK-IN VEHICLE SERVICE
# ==============================================================================


@pytest.fixture
def auth_employee():
    emp = Account.objects.filter(role="EMPLOYEE", is_active=True).first()
    if not emp:
        emp = Account.objects.get(email="luong.mai.phuong@example.org")
    return emp


@pytest.fixture
def entry_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào Test Plate Format", direction="IN", is_active=True
        )
    return gate


def test_check_in_registered_vehicle_stores_registered_plate(auth_employee, entry_gate):
    """
    Xe đã đăng ký trong hệ thống có license_plate chuẩn mực.
    Khi client gửi chuỗi nhận diện OCR thô (không dấu phân cách),
    bản ghi session.license_plate phải lưu chính xác giá trị vehicle.license_plate.
    """
    vtype = VehicleType.objects.first()
    cust = Customer.objects.filter(deleted_at__isnull=True).first()
    registered_plate = "51K-888.99"
    raw_plate = "51K88899"
    Vehicle.objects.filter(license_plate_norm="51K88899").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="51K88899").delete()

    veh = Vehicle.objects.create(
        code=f"XE{uuid.uuid4().hex[:4].upper()}",
        license_plate=registered_plate,
        model_name="Honda City",
        vehicle_type=vtype,
        customer=cust,
    )

    session, _ = check_in_vehicle(
        license_plate=raw_plate,
        entry_gate_id=entry_gate.id,
        user=auth_employee,
    )

    assert session.license_plate == registered_plate
    assert session.vehicle_id == veh.id

    # Kiểm tra lookup tìm thấy cả bằng chuỗi có dấu và không dấu
    lookup_with_dash = get_open_session_by_identifier(license_plate=registered_plate)
    lookup_raw = get_open_session_by_identifier(license_plate=raw_plate)
    assert lookup_with_dash is not None and lookup_with_dash.id == session.id
    assert lookup_raw is not None and lookup_raw.id == session.id


def test_check_in_unregistered_visitor_ambiguous_unknown_type_keeps_compact(
    auth_employee, entry_gate
):
    """
    Finding 2 / TL-65: Khách vãng lai gửi chuỗi thô ambiguous '30A61235' (không có xe trong DB,
    không gán slot_id, không truyền vehicle_type).
    Hệ thống KHÔNG ĐOÁN MÒ, giữ nguyên chuỗi compact '30A61235'.
    """
    plate_raw = "30A61235"
    Vehicle.objects.filter(license_plate_norm="30A61235").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="30A61235").delete()

    session, _ = check_in_vehicle(
        license_plate=plate_raw,
        entry_gate_id=entry_gate.id,
        user=auth_employee,
    )

    assert session.license_plate == "30A61235"
    assert session.vehicle_id is None

    # Tra cứu qua PostgreSQL generated column license_plate_norm vẫn tìm thấy
    lookup = get_open_session_by_identifier(license_plate="30A61235")
    assert lookup is not None and lookup.id == session.id


def test_check_in_visitor_ambiguous_with_vehicle_type_param(auth_employee, entry_gate):
    """
    Finding 2 / TL-65: Khách vãng lai gửi chuỗi thô ambiguous '30A61235',
    nhưng caller truyền trực tiếp vehicle_type='CAR'.
    Hệ thống format chuẩn xác sang '30A-612.35'.
    """
    plate_raw = "30A61235"
    Vehicle.objects.filter(license_plate_norm="30A61235").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="30A61235").delete()

    session, _ = check_in_vehicle(
        license_plate=plate_raw,
        entry_gate_id=entry_gate.id,
        user=auth_employee,
        vehicle_type="CAR",
    )

    assert session.license_plate == "30A-612.35"
    assert session.vehicle_id is None


def test_check_in_visitor_ambiguous_with_car_slot_inferred(auth_employee, entry_gate):
    """
    Finding 2 / TL-65: Khách vãng lai gửi chuỗi thô ambiguous '30A61235',
    gán slot đỗ dành cho xe CAR (qua slot_allowed_vehicle_type).
    Hệ thống suy luận vehicle_type='CAR' và format sang '30A-612.35'.
    """
    vtype_car = VehicleType.objects.filter(code="CAR").first()
    if not vtype_car:
        vtype_car = VehicleType.objects.first()

    plate_raw = "30A61235"
    Vehicle.objects.filter(license_plate_norm="30A61235").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="30A61235").delete()

    slot = ParkingSlot.objects.filter(status="AVAILABLE").first()
    if not slot:
        from apps.parking.models import ParkingZone

        zone = ParkingZone.objects.first()
        slot = ParkingSlot.objects.create(
            code=f"TSLOT_{uuid.uuid4().hex[:4].upper()}",
            zone=zone,
            slot_kind="STANDARD",
            status="AVAILABLE",
        )
    SlotAllowedVehicleType.objects.get_or_create(slot=slot, vehicle_type=vtype_car)

    session, _ = check_in_vehicle(
        license_plate=plate_raw,
        entry_gate_id=entry_gate.id,
        slot_id=slot.id,
        user=auth_employee,
    )

    assert session.license_plate == "30A-612.35"
    assert session.slot_id == slot.id


def test_check_in_visitor_motorcycle_formats_display_plate(auth_employee, entry_gate):
    """
    Xe máy vãng lai gửi chuỗi OCR thô '81B334303' (dạng unambiguous xe máy 5 số).
    Hệ thống format thành '81-B3 343.03' ngay cả khi vehicle_type là None.
    """
    plate_raw = "81B334303"
    Vehicle.objects.filter(license_plate_norm="81B334303").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="81B334303").delete()

    session, _ = check_in_vehicle(
        license_plate=plate_raw,
        entry_gate_id=entry_gate.id,
        user=auth_employee,
    )

    assert session.license_plate == "81-B3 343.03"
    assert session.vehicle_id is None

    lookup = get_open_session_by_identifier(license_plate="81-B3 343.03")
    assert lookup is not None and lookup.id == session.id


# ==============================================================================
# SECTION 3: ADVERSARIAL EMPIRICAL TESTS FOR CHECK-IN FLOW & DB INTEGRITY
# ==============================================================================


@pytest.fixture
def car_slot():
    zone = ParkingZone.objects.first()
    slot = ParkingSlot.objects.create(
        code=f"SLOT-C-{uuid.uuid4().hex[:4].upper()}",
        zone=zone,
        slot_kind="STANDARD",
        status="AVAILABLE",
    )
    vtype_car = VehicleType.objects.filter(code="CAR").first()
    if not vtype_car:
        vtype_car = VehicleType.objects.create(name="Ô tô", code="CAR")
    SlotAllowedVehicleType.objects.create(slot=slot, vehicle_type=vtype_car)
    return slot


@pytest.fixture
def mixed_slot():
    zone = ParkingZone.objects.first()
    slot = ParkingSlot.objects.create(
        code=f"SLOT-M-{uuid.uuid4().hex[:4].upper()}",
        zone=zone,
        slot_kind="STANDARD",
        status="AVAILABLE",
    )
    vtype_car = VehicleType.objects.filter(code="CAR").first()
    vtype_moto, _ = VehicleType.objects.get_or_create(
        code="MOTORCYCLE", defaults={"name": "Xe máy"}
    )
    if not vtype_car:
        vtype_car = VehicleType.objects.create(name="Ô tô", code="CAR")
    SlotAllowedVehicleType.objects.create(slot=slot, vehicle_type=vtype_car)
    SlotAllowedVehicleType.objects.create(slot=slot, vehicle_type=vtype_moto)
    return slot


def test_registered_vehicle_formatting_various_inputs(auth_employee, entry_gate):
    """
    Khi xe đã đăng ký có biển số '51A-897.14' và '29-H1 1234':
    - Dù đầu vào là compact '51A89714', display '51A-897.14', hay có khoảng trắng,
      session.license_plate luôn lưu chính xác biển số đã đăng ký của vehicle.
    """
    vtype_car = VehicleType.objects.filter(code="CAR").first()
    vtype_moto, _ = VehicleType.objects.get_or_create(
        code="MOTORCYCLE", defaults={"name": "Xe máy"}
    )
    cust = Customer.objects.filter(deleted_at__isnull=True).first()

    # Tạo xe ô tô đăng ký 51A-897.14
    Vehicle.objects.filter(license_plate_norm="51A89714").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="51A89714").delete()
    car_veh = Vehicle.objects.create(
        code=f"CAR-{uuid.uuid4().hex[:4].upper()}",
        license_plate="51A-897.14",
        model_name="Toyota Vios",
        vehicle_type=vtype_car,
        customer=cust,
    )

    # Check-in với compact input '51A89714'
    session1, _ = check_in_vehicle(
        license_plate="51A89714",
        entry_gate_id=entry_gate.id,
        user=auth_employee,
    )
    assert session1.license_plate == "51A-897.14"
    assert session1.vehicle_id == car_veh.id

    # Đóng session1
    session1.exit_time = session1.entry_time
    session1.save(update_fields=["exit_time"])

    # Check-in với display input '51A-897.14'
    session2, _ = check_in_vehicle(
        license_plate="51A-897.14",
        entry_gate_id=entry_gate.id,
        user=auth_employee,
    )
    assert session2.license_plate == "51A-897.14"
    assert session2.vehicle_id == car_veh.id
    session2.exit_time = session2.entry_time
    session2.save(update_fields=["exit_time"])

    # Tạo xe máy đăng ký 29-H1 1234
    Vehicle.objects.filter(license_plate_norm="29H11234").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="29H11234").delete()
    moto_veh = Vehicle.objects.create(
        code=f"MOT-{uuid.uuid4().hex[:4].upper()}",
        license_plate="29-H1 1234",
        model_name="Honda Wave",
        vehicle_type=vtype_moto,
        customer=cust,
    )

    # Check-in với compact input '29H11234'
    session3, _ = check_in_vehicle(
        license_plate="29H11234",
        entry_gate_id=entry_gate.id,
        user=auth_employee,
    )
    assert session3.license_plate == "29-H1 1234"
    assert session3.vehicle_id == moto_veh.id


def test_visitor_with_car_slot_infers_car_format(auth_employee, entry_gate, car_slot):
    """
    Khách vãng lai khi được gán ô đỗ ô tô (car_slot):
    - Biển ambiguous '30A61235' được format thành '30A-612.35'.
    - Biển ambiguous '29H11234' được format thành '29H-112.34'.
    - Biển unambiguous car '29A1234' được format thành '29A-1234'.
    """
    # 1. Ambiguous 30A61235
    Vehicle.objects.filter(license_plate_norm="30A61235").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="30A61235").delete()

    s1, _ = check_in_vehicle(
        license_plate="30A61235",
        entry_gate_id=entry_gate.id,
        slot_id=car_slot.id,
        user=auth_employee,
    )
    assert s1.license_plate == "30A-612.35"
    assert s1.vehicle_id is None
    s1.exit_time = s1.entry_time
    s1.save(update_fields=["exit_time"])

    # 2. Ambiguous 29H11234
    Vehicle.objects.filter(license_plate_norm="29H11234").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="29H11234").delete()

    s2, _ = check_in_vehicle(
        license_plate="29H11234",
        entry_gate_id=entry_gate.id,
        slot_id=car_slot.id,
        user=auth_employee,
    )
    assert s2.license_plate == "29H-112.34"
    assert s2.vehicle_id is None


def test_visitor_without_slot_unknown_type_keeps_compact_or_unambiguous(
    auth_employee, entry_gate
):
    """
    Khách vãng lai không gán ô đỗ (slot_id=None, vehicle_type=None):
    - Dạng ambiguous ('30A61235', '29H11234', '29MD12345', '29LD1234'): KHÔNG ĐOÁN MÒ, giữ nguyên compact sạch.
    - Dạng unambiguous xe máy ('81B334303', '59T249609'): Tự động format chuẩn.
    - Dạng unambiguous ô tô ('29A1234'): Tự động format chuẩn.
    """
    cases = [
        ("30A61235", "30A61235"),
        ("29H11234", "29H11234"),
        ("29MD12345", "29MD12345"),
        ("29LD1234", "29LD1234"),
        ("81B334303", "81-B3 343.03"),
        ("59T249609", "59-T2 496.09"),
        ("29A1234", "29A-1234"),
    ]

    for raw, expected in cases:
        norm = PlateRecognizer.normalize_plate(raw)
        Vehicle.objects.filter(license_plate_norm=norm).delete()
        VehicleEntryExitLog.objects.filter(license_plate_norm=norm).delete()

        session, _ = check_in_vehicle(
            license_plate=raw,
            entry_gate_id=entry_gate.id,
            slot_id=None,
            user=auth_employee,
        )
        assert session.license_plate == expected
        assert session.vehicle_id is None
        session.exit_time = session.entry_time
        session.save(update_fields=["exit_time"])


def test_registered_vehicle_anomalous_vehicle_type(auth_employee, entry_gate):
    """
    Thử nghiệm xe đăng ký nhưng vehicle_type mang giá trị lạ ('OTHER'):
    - Khi vehicle_type có code lạ ('OTHER'): stored_plate vẫn ưu tiên vehicle.license_plate ('29C-999.88').
    - Khi caller truyền trực tiếp vehicle_type lạ ('UNKNOWN_TYPE'):
      nếu biển ambiguous, hệ thống không đoán mò và giữ nguyên compact.
    """
    cust = Customer.objects.filter(deleted_at__isnull=True).first()

    # 1. Xe đăng ký có vehicle_type lạ 'OTHER'
    Vehicle.objects.filter(license_plate_norm="29C99988").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="29C99988").delete()

    vtype_other, _ = VehicleType.objects.get_or_create(
        code="OTHER", defaults={"name": "Loại xe khác"}
    )
    veh_other = Vehicle.objects.create(
        code=f"OTH-{uuid.uuid4().hex[:4].upper()}",
        license_plate="29C-999.88",
        model_name="Custom Vehicle",
        vehicle_type=vtype_other,
        customer=cust,
    )

    s1, _ = check_in_vehicle(
        license_plate="29C99988",
        entry_gate_id=entry_gate.id,
        user=auth_employee,
    )
    assert s1.license_plate == "29C-999.88"
    assert s1.vehicle_id == veh_other.id
    s1.exit_time = s1.entry_time
    s1.save(update_fields=["exit_time"])

    # 2. Caller truyền vehicle_type lạ 'UNKNOWN_TYPE' với khách vãng lai biển ambiguous
    Vehicle.objects.filter(license_plate_norm="30A99988").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="30A99988").delete()

    s2, _ = check_in_vehicle(
        license_plate="30A99988",
        entry_gate_id=entry_gate.id,
        vehicle_type="UNKNOWN_TYPE",
        user=auth_employee,
    )
    assert s2.license_plate == "30A99988"
    assert s2.vehicle_id is None


def test_mixed_vehicle_types_slot_infers_unknown_for_ambiguous(
    auth_employee, entry_gate, mixed_slot
):
    """
    Thử nghiệm ô đỗ có nhiều loại xe hỗn hợp (CAR + MOTORCYCLE):
    - Vì slot cho phép cả 2 loại nên không thể chắc chắn loại xe của khách vãng lai.
    - Với biển ambiguous '29H11234', check_in suy luận inferred_vehicle_type = None,
      hệ thống KHÔNG ĐOÁN MÒ và lưu compact sạch '29H11234'.
    - Với biển unambiguous xe máy '81B334303', hệ thống format chuẩn '81-B3 343.03'.
    """
    # 1. Ambiguous 29H11234 vào mixed_slot
    Vehicle.objects.filter(license_plate_norm="29H11234").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="29H11234").delete()

    s1, _ = check_in_vehicle(
        license_plate="29H11234",
        entry_gate_id=entry_gate.id,
        slot_id=mixed_slot.id,
        user=auth_employee,
    )
    assert s1.license_plate == "29H11234"
    assert s1.slot_id == mixed_slot.id
    s1.exit_time = s1.entry_time
    s1.save(update_fields=["exit_time"])

    # 2. Unambiguous 81B334303 vào mixed_slot
    Vehicle.objects.filter(license_plate_norm="81B334303").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="81B334303").delete()

    s2, _ = check_in_vehicle(
        license_plate="81B334303",
        entry_gate_id=entry_gate.id,
        slot_id=mixed_slot.id,
        user=auth_employee,
    )
    assert s2.license_plate == "81-B3 343.03"
    assert s2.slot_id == mixed_slot.id


@pytest.mark.parametrize(
    "invalid_plate",
    [
        "29H-112.34Đ",  # Ký tự có dấu tiếng Việt 'Đ'
        "30A-612.35é",  # Ký tự có dấu 'é'
        "51A-897.14🚗",  # Ký tự Emoji
        "29H\t11234",  # Ký tự Tab
        "29H\n11234",  # Ký tự Newline
        "29H\u00a011234",  # Non-breaking space
        "",  # Rỗng
        "   ",  # Toàn khoảng trắng
        "29H@1234",  # Ký tự đặc biệt '@'
        "29H#1234",  # Ký tự đặc biệt '#'
    ],
)
def test_unicode_and_special_character_rejection(
    invalid_plate, auth_employee, entry_gate
):
    """
    Biển số mang ký tự Unicode tiếng Việt, emoji, tab, newline, non-breaking space
    hoặc ký tự ngoài bảng mã [A-Za-z0-9 .-] phải bị check_in_vehicle từ chối ngay lập tức
    với BusinessAPIException mã PROP-4.5.1-P01 (HTTP 400).
    """
    with pytest.raises(BusinessAPIException) as exc_info:
        check_in_vehicle(
            license_plate=invalid_plate,
            entry_gate_id=entry_gate.id,
            user=auth_employee,
        )
    assert exc_info.value.code == "PROP-4.5.1-P01"
    assert exc_info.value.status_code == 400


def test_db_generated_column_license_plate_norm_integrity(auth_employee, entry_gate):
    """
    Kiểm tra cột generated column license_plate_norm trong PostgreSQL:
    1. Khi lưu compact '30A61235', CSDL tự động tính license_plate_norm = '30A61235'.
    2. Khi lưu display '30A-612.35', CSDL tự động tính license_plate_norm = '30A61235'.
    3. Kiểm tra bằng raw SQL query trực tiếp trên PostgreSQL để loại trừ can thiệp của ORM.
    """
    Vehicle.objects.filter(license_plate_norm="30A61235").delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm="30A61235").delete()

    # 1. Lưu compact '30A61235'
    s1, _ = check_in_vehicle(
        license_plate="30A61235",
        entry_gate_id=entry_gate.id,
        user=auth_employee,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT license_plate, license_plate_norm FROM vehicle_entry_exit_log WHERE id = %s;",
            [s1.id],
        )
        row1 = cursor.fetchone()
        assert row1[0] == "30A61235"
        assert row1[1] == "30A61235"

    s1.exit_time = s1.entry_time
    s1.save(update_fields=["exit_time"])

    # 2. Lưu display '30A-612.35'
    s2, _ = check_in_vehicle(
        license_plate="30A-612.35",
        entry_gate_id=entry_gate.id,
        user=auth_employee,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT license_plate, license_plate_norm FROM vehicle_entry_exit_log WHERE id = %s;",
            [s2.id],
        )
        row2 = cursor.fetchone()
        assert row2[0] == "30A-612.35"
        assert row2[1] == "30A61235"


def test_lookup_and_postgres_index_scan_display_vs_compact(auth_employee, entry_gate):
    """
    Kiểm tra tìm kiếm (lookup) biển số theo format hiển thị vs compact:
    1. Khi bản ghi lưu là compact '30A61235':
       - Lookup bằng '30A61235' (compact) -> Tìm thấy.
       - Lookup bằng '30A-612.35' (display) -> Tìm thấy.
       - Lookup bằng ' 30a-612.35 ' (lowercase, whitespace) -> Tìm thấy.
    2. Kiểm tra PostgreSQL EXPLAIN query plan:
       - Truy vấn theo license_plate_norm với exit_time IS NULL phải sử dụng
         index (Index Scan / Bitmap Index Scan trên uq_log_open_session_plate hoặc idx_log_license_plate),
         hoàn toàn không dùng Seq Scan!
    """
    norm_val = "30A61235"
    Vehicle.objects.filter(license_plate_norm=norm_val).delete()
    VehicleEntryExitLog.objects.filter(license_plate_norm=norm_val).delete()

    session, _ = check_in_vehicle(
        license_plate="30A61235",
        entry_gate_id=entry_gate.id,
        user=auth_employee,
    )

    # 1. Functional lookups qua selector
    found_compact = get_open_session_by_identifier(license_plate="30A61235")
    assert found_compact is not None and found_compact.id == session.id

    found_display = get_open_session_by_identifier(license_plate="30A-612.35")
    assert found_display is not None and found_display.id == session.id

    found_mixed = get_open_session_by_identifier(license_plate="  30a-612.35  ")
    assert found_mixed is not None and found_mixed.id == session.id

    # 2. PostgreSQL Index Scan Verification via EXPLAIN
    if connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute("SET enable_seqscan = off;")
            cursor.execute(
                """
                EXPLAIN
                SELECT id FROM vehicle_entry_exit_log
                WHERE license_plate_norm = %s AND exit_time IS NULL
                LIMIT 1;
                """,
                [norm_val],
            )
            raw_lines = [r[0] for r in cursor.fetchall()]
            cursor.execute("RESET enable_seqscan;")
            has_index_scan = any(
                "uq_log_open_session_plate" in line or "idx_log_license_plate" in line
                for line in raw_lines
            )
            assert has_index_scan, f"PostgreSQL plan did not use index: {raw_lines}"
