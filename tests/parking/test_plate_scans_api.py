"""
Integration tests for Plate Scan API (POST /api/v1/parking/plate-scans/).
Verifies:
- Permission matrix: anonymous -> 401, CUSTOMER -> 403, EMPLOYEE -> allowed.
- Missing image -> 400 PROP-4.5.1-P02.
- Unprocessable image / no plate detected -> 422 PROP-4.5.1-P06.
- Successful scan returns candidates, best_candidate, image_url, and vehicle_lookup.
- Blacklisted plate flagged in response.
"""

import io
from pathlib import Path

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.exceptions import BusinessAPIException
from apps.parking.models import PlateBlacklist
from apps.parking.services.ocr import (
    DummyPlateRecognizer,
    set_global_recognizer,
)
from apps.parking.services.upload import validate_and_save_image
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


def _create_jpeg_file(name: str = "scan.jpg") -> SimpleUploadedFile:
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 100), color="white")
    img.save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@pytest.fixture
def auth_employee():
    """Tạo hoặc lấy tài khoản nhân viên vận hành."""
    emp, _ = Account.objects.get_or_create(
        email="emp_scanner@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def auth_customer():
    """Tạo hoặc lấy tài khoản khách hàng."""
    cust, _ = Account.objects.get_or_create(
        email="cust_scanner@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return cust


def test_plate_scan_anonymous_rejected():
    """Người dùng chưa xác thực bị từ chối với HTTP 401 và mã MSG-4.1-M02."""
    client = APIClient()
    file_obj = _create_jpeg_file()
    response = client.post(
        "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
    )
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"


def test_plate_scan_customer_role_forbidden(auth_customer):
    """Khách hàng không có quyền truy cập API quét biển số (HTTP 403, MSG-4.2-M01)."""
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    file_obj = _create_jpeg_file()
    response = client.post(
        "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"


def test_plate_scan_missing_image(auth_employee):
    """Nhân viên không gửi file ảnh bị từ chối với HTTP 400 và mã PROP-4.5.1-P02."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post("/api/v1/parking/plate-scans/", {}, format="multipart")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P02"


def test_plate_scan_no_plate_detected_raises_422(auth_employee, monkeypatch):
    """Khi OCR không nhận dạng được biển số nào -> HTTP 422 PROP-4.5.1-P06."""
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    recognizer = DummyPlateRecognizer(default_plate="")
    set_global_recognizer(recognizer)

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    file_obj = _create_jpeg_file()
    response = client.post(
        "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.data["code"] == "PROP-4.5.1-P06"

    set_global_recognizer(None)


def test_plate_scan_success_registered_vehicle(auth_employee, monkeypatch):
    """Quét biển số xe đã đăng ký thành công, trả về vehicle_lookup đầy đủ."""
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert v is not None

    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    recognizer = DummyPlateRecognizer(
        default_plate=v.license_plate, default_confidence=98.5
    )
    set_global_recognizer(recognizer)

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    file_obj = _create_jpeg_file()
    response = client.post(
        "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.data
    assert len(data["candidates"]) == 1
    assert data["best_candidate"]["plate_normalized"] == v.license_plate_norm
    assert data["best_candidate"]["confidence"] == 98.5
    assert data["image_url"].startswith("/media/parking_scans/")
    assert data["is_blacklisted"] is False

    assert data["vehicle_lookup"] is not None
    assert (
        data["vehicle_lookup"]["vehicle"]["license_plate_norm"] == v.license_plate_norm
    )

    set_global_recognizer(None)


def test_plate_scan_blacklisted_plate_flagged(auth_employee, monkeypatch):
    """Quét biển số nằm trong danh sách đen trả về is_blacklisted = True."""
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    blacklisted_plate = "29A-888.99"
    PlateBlacklist.objects.create(
        license_plate="29A-888.99",
        license_plate_norm="29A88899",
        reason="Vi phạm quy định đỗ xe",
        is_active=True,
    )

    recognizer = DummyPlateRecognizer(
        default_plate=blacklisted_plate, default_confidence=95.0
    )
    set_global_recognizer(recognizer)

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    file_obj = _create_jpeg_file()
    response = client.post(
        "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.data["is_blacklisted"] is True

    set_global_recognizer(None)


def test_plate_scan_422_leaves_zero_files_in_media_root(auth_employee, monkeypatch):
    """
    F10(a): Khi OCR không tìm thấy biển số (HTTP 422), đảm bảo KHÔNG để lại bất kỳ
    tệp hình ảnh nào trong MEDIA_ROOT.
    """
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    set_global_recognizer(DummyPlateRecognizer(default_plate=""))

    media_root = Path(settings.MEDIA_ROOT)
    scans_dir = media_root / "parking_scans"
    files_before = set(scans_dir.rglob("*")) if scans_dir.exists() else set()

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    buf = io.BytesIO()
    Image.new("RGB", (200, 100), color="white").save(buf, format="JPEG")
    file_obj = SimpleUploadedFile(
        "empty_plate.jpg", buf.getvalue(), content_type="image/jpeg"
    )

    response = client.post(
        "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.data["code"] == "PROP-4.5.1-P06"

    files_after = set(scans_dir.rglob("*")) if scans_dir.exists() else set()
    new_files = [f for f in (files_after - files_before) if f.is_file()]
    assert len(new_files) == 0, (
        f"Defect F10(a): Found leftover files after 422 scan: {new_files}"
    )

    set_global_recognizer(None)


def test_plate_scan_exif_orientation_6_transposed_upright(auth_employee, monkeypatch):
    """
    F10(b): Tệp ảnh chụp từ điện thoại có EXIF Orientation = 6 (xoay ngang 90 độ)
    phải được tự động xoay đứng thẳng (ImageOps.exif_transpose) trước khi OCR và lưu đĩa.
    """
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")

    received_image_dims: list[tuple[int, int]] = []

    class InspectingDummyRecognizer(DummyPlateRecognizer):
        def recognize(self, image_data):
            if isinstance(image_data, bytes):
                img = Image.open(io.BytesIO(image_data))
                received_image_dims.append(img.size)
            return super().recognize(image_data)

    set_global_recognizer(InspectingDummyRecognizer(default_plate="51K-992.14"))

    # Tạo ảnh có kích thước ngang 300x150, EXIF Orientation = 6 (90 CW)
    # Kích thước sau xoay đứng thẳng phải là 150x300 (chiều cao > chiều rộng)
    exif = Image.Exif()
    exif[0x0112] = 6

    buf = io.BytesIO()
    Image.new("RGB", (300, 150), color="blue").save(buf, format="JPEG", exif=exif)
    file_obj = SimpleUploadedFile(
        "rotated_phone.jpg", buf.getvalue(), content_type="image/jpeg"
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    response = client.post(
        "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
    )
    assert response.status_code == status.HTTP_200_OK

    # OCR phải nhận được ảnh đứng thẳng 150x300
    assert len(received_image_dims) == 1
    assert received_image_dims[0] == (
        150,
        300,
    ), f"OCR received wrong dimensions: {received_image_dims[0]}"

    # File lưu trên đĩa cũng phải có kích thước 150x300 và không còn thẻ EXIF
    saved_rel_url = response.data["image_url"]
    media_url = getattr(settings, "MEDIA_URL", "/media/")
    rel_path = (
        saved_rel_url[len(media_url) :].lstrip("/")
        if saved_rel_url.startswith(media_url)
        else saved_rel_url.removeprefix(media_url)
    )
    disk_file = Path(settings.MEDIA_ROOT) / rel_path
    assert disk_file.exists(), f"Saved file {disk_file} does not exist"

    with Image.open(disk_file) as saved_img:
        assert saved_img.size == (150, 300)
        assert saved_img.getexif().get(0x0112) is None

    set_global_recognizer(None)


def test_upload_declared_oversized_rejected_before_reading():
    """
    F10(c.1): Khi file_obj có khai báo size vượt quá MAX_IMAGE_SIZE_MB (5MB),
    hệ thống từ chối ngay lập tức mà không đọc byte nào từ stream.
    """

    class StreamTracker(io.BytesIO):
        def __init__(self, data, size):
            super().__init__(data)
            self.size = size
            self.read_called = False

        def read(self, *args):
            self.read_called = True
            return super().read(*args)

    oversized = 6 * 1024 * 1024  # 6 MB
    tracker = StreamTracker(b"X" * oversized, size=oversized)

    with pytest.raises(BusinessAPIException) as exc_info:
        validate_and_save_image(tracker)

    assert exc_info.value.code == "PROP-4.5.1-P03"
    assert exc_info.value.status_code == 400
    assert not tracker.read_called, (
        "Defect F10(c.1): Stream read() was called despite declared size > 5MB!"
    )


def test_upload_stream_capped_at_max_bytes_plus_one():
    """
    F10(c.2): Khi stream upload không khai báo size, hệ thống chỉ đọc tối đa
    max_bytes + 1 (5,242,881 bytes) rồi từ chối ngay, không nạp toàn bộ file lớn vào RAM.
    """

    class ByteCountingStream(io.BytesIO):
        def __init__(self, data):
            super().__init__(data)
            self.bytes_read = 0
            self.read_args = []

        def read(self, *args):
            self.read_args.append(args)
            chunk = super().read(*args)
            self.bytes_read += len(chunk)
            return chunk

    oversized = 10 * 1024 * 1024  # 10 MB payload
    stream = ByteCountingStream(b"Y" * oversized)

    with pytest.raises(BusinessAPIException) as exc_info:
        validate_and_save_image(stream)

    assert exc_info.value.code == "PROP-4.5.1-P03"
    assert exc_info.value.status_code == 400
    max_limit = 5 * 1024 * 1024 + 1
    assert stream.bytes_read <= max_limit, (
        f"Defect F10(c.2): Read {stream.bytes_read} bytes into memory, exceeded limit {max_limit}!"
    )
    assert stream.read_args[0] == (max_limit,)


# ==============================================================================
# LEFTOVER (C) & P2 CONCURRENCY GATE & P3 SINGLE-PASS PIPELINE TESTS
# ==============================================================================


def test_plate_scan_empty_urlencoded_form_returns_400(auth_employee):
    """
    Leftover (c): Gửi form urlencoded rỗng (hoặc form POST không đính kèm file)
    trả về HTTP 400 Bad Request cùng mã lỗi PROP-4.5.1-P02 thay vì lỗi generic 415.
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/plate-scans/",
        {},
        content_type="application/x-www-form-urlencoded",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P02"
    assert response.data["message"] == "Tệp hình ảnh biển số xe không được để trống."
    assert response.data["details"] == {}


def test_plate_scan_urlencoded_with_non_file_fields_returns_400(auth_employee):
    """
    Leftover (c): Gửi form urlencoded có chứa trường dữ liệu khác nhưng thiếu file ảnh
    trả về đúng HTTP 400 cùng mã PROP-4.5.1-P02.
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/plate-scans/",
        {"gate_id": 1, "note": "camera_front"},
        content_type="application/x-www-form-urlencoded",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P02"


def test_plate_scan_unsupported_json_media_type_returns_400(auth_employee):
    """
    Leftover (c): Gửi payload application/json không hỗ trợ
    được chuẩn hóa về HTTP 400 cùng mã PROP-4.5.1-P02 thay vì 415.
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post("/api/v1/parking/plate-scans/", {}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P02"


def test_plate_scan_concurrency_gate_timeout_returns_503_and_retry_after(
    auth_employee, monkeypatch
):
    """
    P2 Back-pressure: Khi số lượng request đồng thời vượt quá giới hạn và timeout,
    hệ thống trả về HTTP 503 Service Unavailable kèm header Retry-After và phong bì PROP-4.5.1-P15.
    """
    from apps.core.concurrency import (
        OCRConcurrencyGate,
        set_ocr_concurrency_gate,
    )

    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    set_global_recognizer(DummyPlateRecognizer(default_plate="51K-992.14"))

    # Thiết lập gate với limit=1 và timeout cực ngắn 0.05s để kích hoạt quá tải
    test_gate = OCRConcurrencyGate(limit=1, timeout=0.05, retry_after=3)
    set_ocr_concurrency_gate(test_gate)

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    file_obj = _create_jpeg_file()

    # Chiếm giữ slot duy nhất
    with test_gate.acquire():
        # Gửi request thứ 2 trong lúc slot đang bận -> timeout -> 503
        resp = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": file_obj},
            format="multipart",
        )

    assert resp.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert resp.headers.get("Retry-After") == "3"
    assert resp.data["code"] == "PROP-4.5.1-P15"
    assert (
        resp.data["message"]
        == "Hệ thống nhận diện biển số xe đang quá tải, vui lòng thử lại sau."
    )
    assert resp.data["details"] == {}

    # Dọn dẹp gate
    set_ocr_concurrency_gate(None)
    set_global_recognizer(None)


def test_plate_scan_concurrency_gate_multithreaded_no_500_or_hung_connection(
    auth_employee, monkeypatch
):
    """
    P2 Concurrency: Thử nghiệm đa luồng đồng thời (8 threads) qua Concurrency Gate:
    100% request kết thúc hợp lệ (200 hoặc 503), tuyệt đối không có 500 hoặc treo kết nối.
    """
    import concurrent.futures

    from apps.core.concurrency import (
        OCRConcurrencyGate,
        set_ocr_concurrency_gate,
    )

    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    set_global_recognizer(DummyPlateRecognizer(default_plate="51K-992.14"))

    test_gate = OCRConcurrencyGate(limit=2, timeout=0.05, retry_after=2)
    set_ocr_concurrency_gate(test_gate)

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    def send_request():
        f = _create_jpeg_file()
        resp = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": f},
            format="multipart",
        )
        return resp.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(send_request) for _ in range(8)]
        status_codes = [f.result(timeout=5.0) for f in futures]

    assert all(code in (200, 503) for code in status_codes)
    assert 500 not in status_codes
    assert 415 not in status_codes

    set_ocr_concurrency_gate(None)
    set_global_recognizer(None)


def test_plate_scan_single_pass_pipeline_downscales_image_over_1280(
    auth_employee, monkeypatch
):
    """
    P3 Image Pipeline: Ảnh lớn (1600x1200) được downscale cạnh lớn nhất <= 1280 (1280x960),
    lưu file an toàn trên đĩa và OCR xử lý chuẩn xác.
    """
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    set_global_recognizer(DummyPlateRecognizer(default_plate="51K-888.99"))

    buf = io.BytesIO()
    img = Image.new("RGB", (1600, 1200), color="blue")
    img.save(buf, format="JPEG")
    file_obj = SimpleUploadedFile(
        "large_1600x1200.jpg", buf.getvalue(), content_type="image/jpeg"
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    resp = client.post(
        "/api/v1/parking/plate-scans/",
        {"image": file_obj},
        format="multipart",
    )
    assert resp.status_code == status.HTTP_200_OK

    media_url = getattr(settings, "MEDIA_URL", "/media/")
    rel_url = resp.data["image_url"]
    rel_path = (
        rel_url[len(media_url) :].lstrip("/")
        if rel_url.startswith(media_url)
        else rel_url.removeprefix(media_url)
    )
    disk_path = Path(settings.MEDIA_ROOT) / rel_path
    assert disk_path.is_file()

    with Image.open(disk_path) as saved_img:
        assert max(saved_img.size) <= 1280
        assert saved_img.size == (1280, 960)

    set_global_recognizer(None)


def test_ocr_recognizer_thread_safe_singleton_and_warmup():
    """
    P3: Kiểm tra tính sẵn sàng (is_ocr_ready) và thread-safe singleton của recognizer.
    """
    import concurrent.futures

    from apps.parking.services.ocr import (
        get_plate_recognizer,
        is_ocr_ready,
        warmup_ocr,
    )

    # Khởi động warm-up
    warmup_res = warmup_ocr()
    assert warmup_res is True
    assert is_ocr_ready() is True

    # Kiểm tra nhiều luồng đồng thời lấy singleton
    def get_instance():
        return get_plate_recognizer()

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(get_instance) for _ in range(8)]
        instances = [f.result(timeout=2.0) for f in futures]

    first_inst = instances[0]
    assert all(inst is first_inst for inst in instances)
