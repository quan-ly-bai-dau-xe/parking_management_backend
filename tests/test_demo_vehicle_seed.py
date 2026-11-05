"""
Focused test suite for demo vehicle seed (XE0031 / 51A-897.14) and customer KH0021.

Verifies:
1. Demo vehicle existence in database after seed load (code, plate, normalized plate,
   model, brand, color, vehicle type, and fake customer details with account_id=NULL).
2. Lookup by normalized plate via get_combined_vehicle_context returning vehicle,
   owner ("Khách Hàng Demo"), is_blacklisted=False, open_session=None, active_ticket=None.
3. Plate scan API response reporting registered vehicle with owner details,
   not blacklisted, and no open session.
4. Seed idempotence: executing load_sample_data twice does not duplicate rows
   or cause errors.
"""

from __future__ import annotations

import io

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.models import ParkingGate, PlateBlacklist, VehicleEntryExitLog
from apps.parking.selectors.vehicles import get_combined_vehicle_context
from apps.parking.services.ocr import DummyPlateRecognizer, set_global_recognizer
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


def _create_jpeg_image(name: str = "demo_scan.jpg") -> SimpleUploadedFile:
    """Tạo file ảnh JPEG in-memory phục vụ kiểm thử Plate Scan API."""
    buf = io.BytesIO()
    img = Image.new("RGB", (300, 150), color="white")
    img.save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@pytest.fixture
def scanner_employee():
    """Tạo hoặc lấy tài khoản nhân viên có quyền quét biển số."""
    emp, _ = Account.objects.get_or_create(
        email="demo_scanner@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


def test_demo_vehicle_exists_after_seed():
    """
    Kiểm tra phương tiện demo XE0031 tồn tại trong CSDL sau khi nạp seed:
    - Biển số hiển thị: 51A-897.14
    - Biển số chuẩn hóa: 51A89714
    - Hãng xe: Toyota, Dòng xe: Vios, Màu: Bạc, Loại: CAR
    - Chủ sở hữu: KH0021 (Khách Hàng Demo, account_id=NULL)
    - Không bị blacklist, không có active ticket, không có open session.
    """
    vehicle = (
        Vehicle.objects.filter(code="XE0031", deleted_at__isnull=True)
        .select_related("vehicle_type", "customer")
        .first()
    )
    assert vehicle is not None, "Phương tiện demo XE0031 không tồn tại trong CSDL"
    assert vehicle.license_plate == "51A-897.14"
    assert vehicle.license_plate_norm == "51A89714"
    assert vehicle.model_name == "Vios"
    assert vehicle.brand == "Toyota"
    assert vehicle.color == "Bạc"
    assert vehicle.vehicle_type.code == "CAR"

    # Thông tin chủ xe KH0021
    customer = vehicle.customer
    assert customer is not None, "Chủ phương tiện KH0021 không tồn tại"
    assert customer.code == "KH0021"
    assert customer.full_name == "Khách Hàng Demo"
    assert customer.phone == "0909897140"
    assert customer.email == "demo.khachhang@example.com"
    assert customer.identity_card_number == "048099999999"
    assert customer.status == "ACTIVE"
    # Invariant bảo toàn 20 accounts: account_id bắt buộc phải là NULL
    assert customer.account_id is None

    # Không nằm trong danh sách đen
    assert not PlateBlacklist.objects.filter(
        license_plate_norm="51A89714", is_active=True, deleted_at__isnull=True
    ).exists()

    # Không có phiên đỗ mở
    assert not VehicleEntryExitLog.objects.filter(
        vehicle_id=vehicle.id, exit_time__isnull=True
    ).exists()


def test_demo_vehicle_lookup_by_normalized_plate():
    """
    Tra cứu qua selector get_combined_vehicle_context bằng biển thô và các biến thể chuẩn hóa:
    - Các biến thể: "51A-897.14", "51A89714", "51a-897.14", "51A 897.14", "51A-89714", "  51A-897.14  ", "51A.897.14"
    - Trả về đối tượng vehicle XE0031 và customer KH0021 ("Khách Hàng Demo")
    - is_blacklisted is False
    - open_session is None
    - active_ticket is None
    """
    variations = [
        "51A-897.14",
        "51A89714",
        "51a-897.14",
        "51A 897.14",
        "51A-89714",
        "  51A-897.14  ",
        "51A.897.14",
    ]
    for query_plate in variations:
        ctx = get_combined_vehicle_context(query_plate)
        assert ctx.vehicle is not None, f"Không tìm thấy xe với query: {query_plate}"
        assert ctx.vehicle.code == "XE0031"
        assert ctx.vehicle.license_plate_norm == "51A89714"
        assert ctx.customer is not None
        assert ctx.customer.code == "KH0021"
        assert ctx.customer.full_name == "Khách Hàng Demo"
        assert ctx.is_blacklisted is False
        assert ctx.open_session is None
        assert ctx.active_ticket is None


def test_demo_vehicle_plate_scan_api_response(scanner_employee, monkeypatch):
    """
    Kiểm tra POST /api/v1/parking/plate-scans/ khi quét biển số xe demo:
    - Nhận diện đúng biển số 51A-897.14 -> 51A89714
    - Trả về payload vehicle_lookup với đầy đủ thông tin phương tiện và chủ xe
    - is_blacklisted is False
    - open_session is None
    - Bất biến Non-Mutation: Số lượng VehicleEntryExitLog trước và sau quét là không đổi (0 session được tạo)
    """
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    recognizer = DummyPlateRecognizer(
        default_plate="51A-897.14", default_confidence=98.8
    )
    set_global_recognizer(recognizer)

    try:
        client = APIClient()
        client.force_authenticate(user=scanner_employee)

        # 1. Đếm số lượng phiên đỗ trước khi quét
        log_count_before = VehicleEntryExitLog.objects.count()

        # Quét xem trước (preview=True)
        img_file = _create_jpeg_image()
        response = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": img_file, "preview": True},
            format="multipart",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.data

        # 2. Xác minh tính bất biến non-mutation: không tạo phiên đỗ nào
        log_count_after_preview = VehicleEntryExitLog.objects.count()
        assert log_count_before == log_count_after_preview, (
            "POST plate-scans (preview=True) vi phạm bất biến: đã tạo bản ghi VehicleEntryExitLog"
        )

        # Quét thực tế (preview=False)
        img_file_2 = _create_jpeg_image()
        response_real = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": img_file_2, "preview": False},
            format="multipart",
        )
        assert response_real.status_code == status.HTTP_200_OK
        log_count_after_real = VehicleEntryExitLog.objects.count()
        assert log_count_before == log_count_after_real, (
            "POST plate-scans (preview=False) vi phạm bất biến: đã tạo bản ghi VehicleEntryExitLog"
        )

        # Kiểm tra OCR fields
        assert data["plate_raw"] == "51A-897.14"
        assert data["plate_final"] == "51A89714"
        assert data["is_blacklisted"] is False
        assert data["open_session"] is None

        # Kiểm tra vehicle_lookup
        lookup = data["vehicle_lookup"]
        assert lookup is not None
        assert lookup["vehicle"]["code"] == "XE0031"
        assert lookup["vehicle"]["license_plate"] == "51A-897.14"
        assert lookup["vehicle"]["license_plate_norm"] == "51A89714"
        assert lookup["vehicle"]["brand"] == "Toyota"
        assert lookup["vehicle"]["model_name"] == "Vios"
        assert lookup["vehicle"]["color"] == "Bạc"
        assert lookup["vehicle"]["vehicle_type_code"] == "CAR"

        # Kiểm tra customer trong lookup
        cust = lookup["customer"]
        assert cust is not None
        assert cust["code"] == "KH0021"
        assert cust["full_name"] == "Khách Hàng Demo"
        assert cust["phone"] == "0909897140"
        assert cust["is_anonymized"] is False

        # Trạng thái bổ trợ
        assert lookup["active_ticket"] is None
        assert lookup["open_session"] is None
        assert lookup["is_blacklisted"] is False
    finally:
        set_global_recognizer(None)


def test_demo_vehicle_seed_idempotence():
    """
    Kiểm tra tính lũy đẳng (idempotence): nạp lại seed bằng load_sample_data:
    - Không làm trùng lặp bản ghi XE0031 hay KH0021
    - Số lượng xe và khách hàng trước và sau nạp lần 2 hoàn toàn không đổi
    - Không gây ra bất kỳ lỗi ràng buộc CSDL nào
    """
    vehicles_before = Vehicle.all_objects.count()
    customers_before = Customer.all_objects.count()
    accounts_before = Account.all_objects.count()

    assert vehicles_before >= 31
    assert customers_before >= 21

    # Nạp seed lần thứ 2
    call_command("load_sample_data", force_production=True)

    vehicles_after = Vehicle.all_objects.count()
    customers_after = Customer.all_objects.count()
    accounts_after = Account.all_objects.count()

    assert vehicles_before == vehicles_after, (
        "Số lượng xe bị thay đổi sau khi nạp seed lần 2"
    )
    assert customers_before == customers_after, (
        "Số lượng khách hàng bị thay đổi sau khi nạp seed lần 2"
    )
    assert accounts_before == accounts_after, (
        "Số lượng tài khoản bị thay đổi sau khi nạp seed lần 2"
    )

    # Kiểm tra bản ghi duy nhất của XE0031 và KH0021
    assert Vehicle.all_objects.filter(code="XE0031").count() == 1
    assert Customer.all_objects.filter(code="KH0021").count() == 1


def test_demo_vehicle_session_lifecycle_contrast(scanner_employee, monkeypatch):
    """
    Thực nghiệm đối chứng vòng đời phiên đỗ xe demo (Milestone 1 Empirical Challenge):
    1. Quét plate-scan: Không sinh session (VehicleEntryExitLog count không đổi, open_session is None).
    2. Check-in xe demo: POST /api/v1/parking/sessions/check-in/ -> HTTP 201, sinh session, link XE0031.
    3. Quét lại plate-scan: open_session bây giờ KHÔNG None (chính là session vừa tạo).
    4. Check-out xe demo: POST /api/v1/parking/sessions/check-out/ -> HTTP 200, đóng session.
    5. Quét lại plate-scan lần 3: open_session trở về None.
    -> Chứng minh tính bất biến: Quét camera là read-only, chỉ check-in mới tạo session và để lại lịch sử!
    """
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    recognizer = DummyPlateRecognizer(
        default_plate="51A-897.14", default_confidence=98.8
    )
    set_global_recognizer(recognizer)

    try:
        client = APIClient()
        client.force_authenticate(user=scanner_employee)

        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        out_gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        if not in_gate:
            in_gate = ParkingGate.objects.create(
                name="Cổng Vào Demo", direction="IN", is_active=True
            )
        if not out_gate:
            out_gate = ParkingGate.objects.create(
                name="Cổng Ra Demo", direction="OUT", is_active=True
            )

        # Bước 1: Quét trước check-in
        count_init = VehicleEntryExitLog.objects.count()
        scan1 = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": _create_jpeg_image(), "preview": True},
            format="multipart",
        )
        assert scan1.status_code == status.HTTP_200_OK
        assert scan1.data["open_session"] is None
        assert VehicleEntryExitLog.objects.count() == count_init

        # Bước 2: Check-in tạo phiên
        ci_resp = client.post(
            "/api/v1/parking/sessions/check-in/",
            {
                "license_plate": "51A-897.14",
                "entry_gate_id": in_gate.id,
                "recognition_source": "AI",
            },
            format="json",
        )
        assert ci_resp.status_code == status.HTTP_201_CREATED, (
            f"Check-in failed: {ci_resp.status_code} - {getattr(ci_resp, 'data', ci_resp.content)}"
        )
        session_data = ci_resp.data["session"]
        session_code = session_data["session_code"]
        assert session_data["license_plate_norm"] == "51A89714"
        assert session_data["vehicle_id"] is not None
        assert VehicleEntryExitLog.objects.count() == count_init + 1

        # Bước 3: Quét lại sau check-in
        scan2 = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": _create_jpeg_image(), "preview": True},
            format="multipart",
        )
        assert scan2.status_code == status.HTTP_200_OK
        assert scan2.data["open_session"] is not None
        assert scan2.data["open_session"]["session_code"] == session_code
        assert VehicleEntryExitLog.objects.count() == count_init + 1

        # Bước 4: Check-out kết thúc phiên
        co_resp = client.post(
            "/api/v1/parking/sessions/check-out/",
            {
                "session_code": session_code,
                "exit_gate_id": out_gate.id,
                "payment_method": "CASH",
            },
            format="json",
        )
        assert co_resp.status_code == status.HTTP_200_OK

        # Bước 5: Quét lại sau check-out
        scan3 = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": _create_jpeg_image(), "preview": True},
            format="multipart",
        )
        assert scan3.status_code == status.HTTP_200_OK
        assert scan3.data["open_session"] is None
    finally:
        set_global_recognizer(None)
