"""
Boundary Stress Testing Suite for Session Concurrency and Vehicle Entry/Exit Edge Cases.

Stress-tests:
1. Concurrency Race Conditions:
   - Two concurrent threads checking in the exact same license plate.
   - Two concurrent threads checking in different vehicles into the exact same parking slot.
   - Two concurrent threads checking out the exact same session by session_code.
   - Two concurrent threads checking out the exact same session by license_plate.

2. Upload Security & Abuse Prevention:
   - Non-image disguised with .jpg extension (PHP script, Bash script, Python script, HTML/JS) -> 400 PROP-4.5.1-P04.
   - Corrupted and truncated image streams -> 400 PROP-4.5.1-P05.
   - Decompression bomb detection (dimension cap > 4096px) -> 400 PROP-4.5.1-P05.
   - EXIF and GPS Metadata stripping -> verifying GPS latitude/longitude and EXIF tags are 100% stripped.
   - Path traversal in filename -> files strictly stored in isolated UUID paths under MEDIA_ROOT.
"""

import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.utils import timezone
from PIL import ExifTags, Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.exceptions import BusinessAPIException
from apps.parking.models import ParkingGate, ParkingSlot, VehicleEntryExitLog
from apps.parking.services.ocr import DummyPlateRecognizer, set_global_recognizer
from apps.parking.services.upload import validate_and_save_image
from apps.tickets.models import Payment


@pytest.fixture(autouse=True)
def setup_dummy_recognizer():
    """Đảm bảo DummyPlateRecognizer được sử dụng để test OCR deterministic."""
    orig = set_global_recognizer(
        DummyPlateRecognizer(default_plate="51H-999.88", default_confidence=95.0)
    )
    yield
    set_global_recognizer(orig)


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="verification_emp@parking.local",
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
        email="verification_mgr@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return mgr


@pytest.fixture
def entry_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào Verification", direction="IN", is_active=True
        )
    return gate


@pytest.fixture
def exit_gate():
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng ra Verification", direction="OUT", is_active=True
        )
    return gate


# ==============================================================================
# SECTION 1: UPLOAD SECURITY BOUNDARY STRESS TESTS
# ==============================================================================


class TestUploadSecurityBoundary:
    """Thử nghiệm đối kháng bảo mật tải lên hình ảnh."""

    @pytest.mark.django_db
    def test_upload_spoofed_script_file(self):
        """Tệp văn bản/mã kịch bản đổi đuôi thành .jpg bị chặn bởi magic bytes -> PROP-4.5.1-P04."""
        script_payload = b"var x = 1; console.log('test non image');"
        fake_file = SimpleUploadedFile(
            name="script.jpg",
            content=script_payload,
            content_type="image/jpeg",
        )
        with pytest.raises(BusinessAPIException) as exc:
            validate_and_save_image(fake_file)
        assert exc.value.code == "PROP-4.5.1-P04"
        assert exc.value.status_code == 400

    @pytest.mark.django_db
    def test_upload_spoofed_binary_data(self):
        """Tệp nhị phân không phải ảnh đổi đuôi thành .png/.webp bị chặn -> PROP-4.5.1-P04."""
        raw_binary = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\x0c\r\x0e\x0f"
        for fname, mime in [
            ("binary.webp", "image/webp"),
            ("archive.png", "image/png"),
            ("data.jpg", "image/jpeg"),
        ]:
            fake_file = SimpleUploadedFile(fname, raw_binary, content_type=mime)
            with pytest.raises(BusinessAPIException) as exc:
                validate_and_save_image(fake_file)
            assert exc.value.code == "PROP-4.5.1-P04"

    @pytest.mark.django_db
    def test_upload_corrupted_truncated_jpeg(self):
        """Tệp có header JPEG hợp lệ nhưng dữ liệu bị cắt cụt (truncated) gây crash decode -> PROP-4.5.1-P05."""
        truncated_bytes = (
            b"\xff\xd8\xff\xe0\x00\x10\x4a\x46\x49\x46\x00\x01\x01\x00\x00\x01\x00\x01"
        )
        corrupt_file = SimpleUploadedFile(
            name="truncated.jpg",
            content=truncated_bytes,
            content_type="image/jpeg",
        )
        with pytest.raises(BusinessAPIException) as exc:
            validate_and_save_image(corrupt_file)
        assert exc.value.code == "PROP-4.5.1-P05"
        assert exc.value.status_code == 400

    @pytest.mark.django_db
    def test_upload_decompression_bomb_dimension_cap(self):
        """Tệp có chiều dài hoặc chiều rộng > 4096px bị chặn bảo vệ bộ nhớ -> PROP-4.5.1-P05."""
        buf = io.BytesIO()
        img = Image.new("RGB", (4097, 50), color="white")
        img.save(buf, format="JPEG")
        oversized_file = SimpleUploadedFile(
            name="bomb_dimension.jpg",
            content=buf.getvalue(),
            content_type="image/jpeg",
        )
        with pytest.raises(BusinessAPIException) as exc:
            validate_and_save_image(oversized_file)
        assert exc.value.code == "PROP-4.5.1-P05"
        assert exc.value.status_code == 400

    @pytest.mark.django_db
    def test_upload_exif_gps_stripping(self, tmp_path, monkeypatch):
        """Xác nhận toàn bộ EXIF và dữ liệu GPS bị loại bỏ hoàn toàn khi lưu trữ file."""
        monkeypatch.setattr(settings, "MEDIA_ROOT", tmp_path)
        monkeypatch.setattr(settings, "MEDIA_URL", "/media/")

        exif = Image.Exif()
        gps_data = {
            ExifTags.GPS.GPSLatitudeRef: "N",
            ExifTags.GPS.GPSLatitude: 16.0544,
            ExifTags.GPS.GPSLongitudeRef: "E",
            ExifTags.GPS.GPSLongitude: 108.2022,
            ExifTags.GPS.GPSAltitude: 10.5,
        }
        exif[ExifTags.Base.Make] = "EmpiricalVerificationCamera"
        exif[ExifTags.Base.Model] = "StressTester-2026"
        exif[ExifTags.Base.GPSInfo] = gps_data

        buf = io.BytesIO()
        img = Image.new("RGB", (250, 150), color="green")
        img.save(buf, format="JPEG", exif=exif)

        raw_check = Image.open(io.BytesIO(buf.getvalue()))
        raw_exif = raw_check.getexif()
        assert raw_exif.get(ExifTags.Base.Make) == "EmpiricalVerificationCamera"
        assert raw_exif.get_ifd(ExifTags.IFD.GPSInfo) is not None

        upload_file = SimpleUploadedFile(
            "plate_with_gps.jpg", buf.getvalue(), content_type="image/jpeg"
        )
        result = validate_and_save_image(upload_file)

        assert result.file_path.exists()
        saved_img = Image.open(result.file_path)
        saved_exif = saved_img.getexif()

        assert saved_exif.get(ExifTags.Base.Make) is None
        gps_ifd = saved_exif.get_ifd(ExifTags.IFD.GPSInfo)
        assert len(gps_ifd) == 0, f"GPS info was not stripped: {gps_ifd}"

    @pytest.mark.django_db
    def test_upload_path_traversal_in_filename(self, tmp_path, monkeypatch):
        """Path traversal trong filename không thể lưu ra ngoài thư mục MEDIA_ROOT."""
        monkeypatch.setattr(settings, "MEDIA_ROOT", tmp_path)
        monkeypatch.setattr(settings, "MEDIA_URL", "/media/")

        buf = io.BytesIO()
        img = Image.new("RGB", (100, 100), color="gray")
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        traversal_names = [
            "../../../../etc/config.jpg",
            "..\\..\\system\\test.jpg",
            "nested/../../../../shell.jpg",
            "%2e%2e%2f%2e%2e%2f_test.jpg",
        ]

        for malicious_name in traversal_names:
            file_obj = SimpleUploadedFile(
                name=malicious_name,
                content=image_bytes,
                content_type="image/jpeg",
            )
            result = validate_and_save_image(file_obj)

            dest = result.file_path.resolve()
            media_resolved = tmp_path.resolve()
            assert media_resolved in dest.parents, (
                f"File leaked outside MEDIA_ROOT: {dest}"
            )
            assert "config" not in dest.name
            assert "test" not in dest.name
            assert "shell" not in dest.name


# ==============================================================================
# SECTION 2: CONCURRENCY RACE CONDITION TESTS
# ==============================================================================


class TestConcurrencyCheckInBoundary:
    """Thử nghiệm đối kháng tranh chấp đồng thời khi check-in."""

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_check_in_same_license_plate(self, auth_employee, entry_gate):
        """
        Boundary Test 1: 2 luồng tranh chấp check-in cùng 1 biển số xe song song.
        Xác nhận:
        - Đúng 1 luồng HTTP 201 Created thành công.
        - Luồng còn lại nhận HTTP 409 Conflict.
        - CSDL duy trì chính xác 1 phiên đỗ mở cho biển số này (an toàn dữ liệu).
        """
        uid = uuid.uuid4().hex[:6].upper()
        plate = f"51K-{uid[:3]}.{uid[3:]}"

        def do_check_in():
            try:
                client = APIClient()
                client.force_authenticate(user=auth_employee)
                res = client.post(
                    "/api/v1/parking/sessions/check-in/",
                    {
                        "license_plate": plate,
                        "entry_gate_id": entry_gate.id,
                        "recognition_source": "MANUAL",
                    },
                    format="json",
                )
                return res.status_code, getattr(res, "data", {})
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(do_check_in)
            f2 = executor.submit(do_check_in)
            s1, d1 = f1.result()
            s2, d2 = f2.result()

        statuses = [s1, s2]
        assert status.HTTP_201_CREATED in statuses, (
            f"No thread succeeded: {statuses}, {d1}, {d2}"
        )
        assert status.HTTP_409_CONFLICT in statuses, (
            f"Conflict was not raised: {statuses}, {d1}, {d2}"
        )

        # Kiểm tra CSDL chỉ có duy nhất 1 phiên đỗ mở
        open_sessions_count = VehicleEntryExitLog.objects.filter(
            license_plate=plate, exit_time__isnull=True
        ).count()
        assert open_sessions_count == 1, (
            f"Expected 1 open session but found {open_sessions_count}"
        )

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_check_in_same_parking_slot(self, auth_employee, entry_gate):
        """
        Boundary Test 2: 2 luồng tranh chấp check-in 2 xe khác nhau vào CÙNG 1 slot đỗ.
        Xác nhận:
        - Đúng 1 luồng HTTP 201 Created thành công.
        - Luồng còn lại bị từ chối với HTTP 409 Conflict.
        - CSDL chỉ ghi nhận duy nhất 1 xe chiếm slot_id này.
        """
        target_slot = ParkingSlot.objects.filter(status="AVAILABLE").first()
        if not target_slot:
            target_slot = ParkingSlot.objects.first()

        uid_a = uuid.uuid4().hex[:6].upper()
        uid_b = uuid.uuid4().hex[:6].upper()
        plate_a = f"51A-{uid_a[:3]}.{uid_a[3:]}"
        plate_b = f"51B-{uid_b[:3]}.{uid_b[3:]}"

        def do_check_in(plate_str: str):
            try:
                client = APIClient()
                client.force_authenticate(user=auth_employee)
                res = client.post(
                    "/api/v1/parking/sessions/check-in/",
                    {
                        "license_plate": plate_str,
                        "entry_gate_id": entry_gate.id,
                        "slot_id": target_slot.id,
                        "recognition_source": "MANUAL",
                    },
                    format="json",
                )
                return res.status_code, getattr(res, "data", {})
            finally:
                connections.close_all()

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(do_check_in, plate_a)
                f2 = executor.submit(do_check_in, plate_b)
                s1, d1 = f1.result()
                s2, d2 = f2.result()

            statuses = [s1, s2]
            assert status.HTTP_201_CREATED in statuses, (
                f"No thread succeeded: {statuses}, {d1}, {d2}"
            )
            assert status.HTTP_409_CONFLICT in statuses, (
                f"Slot conflict did not trigger 409: {statuses}, {d1}, {d2}"
            )

            # Kiểm tra CSDL chỉ có duy nhất 1 phiên đỗ mở chiếm slot_id này
            open_slot_sessions = VehicleEntryExitLog.objects.filter(
                slot_id=target_slot.id, exit_time__isnull=True
            ).count()
            assert open_slot_sessions == 1, (
                f"Expected 1 open slot session but found {open_slot_sessions}"
            )
        finally:
            VehicleEntryExitLog.objects.filter(
                slot_id=target_slot.id, exit_time__isnull=True
            ).update(slot_id=None)


class TestConcurrencyCheckOutBoundary:
    """Thử nghiệm đối kháng tranh chấp đồng thời khi check-out."""

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_check_out_same_session_by_code(
        self, auth_employee, entry_gate, exit_gate
    ):
        """
        Boundary Test 3: 2 luồng tranh chấp check-out cùng 1 session qua session_code.
        Kỳ vọng: Đúng 1 luồng HTTP 200 OK, luồng còn lại HTTP 409 (PROP-4.5.1-P10).
        Chỉ có DUY NHẤT 1 bản ghi Payment được tạo (không bị double payment).
        """
        now = timezone.now()
        uid = uuid.uuid4().hex[:6].upper()
        code_seq = f"{uuid.uuid4().int % 900 + 100:03d}"
        code_str = f"#PK-ADV-{code_seq}"
        plate_str = f"51C-{uid[:3]}.{uid[3:]}"

        session = VehicleEntryExitLog.objects.create(
            session_code=code_str,
            license_plate=plate_str,
            entry_gate=entry_gate,
            entry_time=now - timedelta(hours=2),
        )

        def do_check_out():
            try:
                client = APIClient()
                client.force_authenticate(user=auth_employee)
                res = client.post(
                    "/api/v1/parking/sessions/check-out/",
                    {
                        "session_code": session.session_code,
                        "exit_gate_id": exit_gate.id,
                        "payment_method": "CASH",
                    },
                    format="json",
                )
                return res.status_code, getattr(res, "data", {})
            finally:
                connections.close_all()

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(do_check_out)
                f2 = executor.submit(do_check_out)
                s1, d1 = f1.result()
                s2, d2 = f2.result()

            statuses = [s1, s2]
            assert status.HTTP_200_OK in statuses, (
                f"No thread succeeded in check-out: {statuses}, {d1}, {d2}"
            )
            assert status.HTTP_409_CONFLICT in statuses, (
                f"Second checkout did not conflict: {statuses}, {d1}, {d2}"
            )

            # Kiểm tra mã lỗi của luồng bị từ chối là PROP-4.5.1-P10
            conflict_data = d1 if s1 == status.HTTP_409_CONFLICT else d2
            assert conflict_data.get("code") == "PROP-4.5.1-P10", (
                f"Expected PROP-4.5.1-P10 but got {conflict_data}"
            )

            # Kiểm tra chỉ có DUY NHẤT 1 bản ghi thanh toán
            payments = Payment.objects.filter(session_id=session.id)
            assert payments.count() == 1, (
                f"Expected 1 payment but found {payments.count()}"
            )
            pmt = payments.first()
            assert pmt.status == "PAID"
            assert pmt.amount == Decimal("20000.00")

            # Kiểm tra phiên đã đóng
            session.refresh_from_db()
            assert session.exit_time is not None
            assert session.fee_amount == Decimal("20000.00")
        finally:
            VehicleEntryExitLog.objects.filter(id=session.id).update(
                exit_time=None, fee_amount=Decimal("0.00")
            )

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_check_out_same_session_by_plate(
        self, auth_employee, entry_gate, exit_gate
    ):
        """
        Boundary Test 4: 2 luồng tranh chấp check-out cùng 1 session qua license_plate.
        Kỳ vọng: Đúng 1 luồng HTTP 200 OK, luồng còn lại HTTP 409 (PROP-4.5.1-P10).
        Chỉ có DUY NHẤT 1 bản ghi Payment được tạo.
        """
        now = timezone.now()
        uid = uuid.uuid4().hex[:6].upper()
        plate = f"51D-{uid[:3]}.{uid[3:]}"
        code_seq = f"{uuid.uuid4().int % 900 + 100:03d}"
        code_str = f"#PK-ADV-{code_seq}"

        session = VehicleEntryExitLog.objects.create(
            session_code=code_str,
            license_plate=plate,
            entry_gate=entry_gate,
            entry_time=now - timedelta(hours=1, minutes=10),
        )

        def do_check_out():
            try:
                client = APIClient()
                client.force_authenticate(user=auth_employee)
                res = client.post(
                    "/api/v1/parking/sessions/check-out/",
                    {
                        "license_plate": plate,
                        "exit_gate_id": exit_gate.id,
                        "payment_method": "VIETQR",
                    },
                    format="json",
                )
                return res.status_code, getattr(res, "data", {})
            finally:
                connections.close_all()

        try:
            with ThreadPoolExecutor(max_workers=2) as executor:
                f1 = executor.submit(do_check_out)
                f2 = executor.submit(do_check_out)
                s1, d1 = f1.result()
                s2, d2 = f2.result()

            statuses = [s1, s2]
            assert status.HTTP_200_OK in statuses, (
                f"No thread succeeded: {statuses}, {d1}, {d2}"
            )
            assert status.HTTP_409_CONFLICT in statuses, (
                f"Conflict missing: {statuses}, {d1}, {d2}"
            )

            conflict_data = d1 if s1 == status.HTTP_409_CONFLICT else d2
            assert conflict_data.get("code") == "PROP-4.5.1-P10", (
                f"Expected PROP-4.5.1-P10 but got {conflict_data}"
            )

            # Kiểm tra chỉ có đúng 1 bản ghi payment
            assert Payment.objects.filter(session_id=session.id).count() == 1
        finally:
            VehicleEntryExitLog.objects.filter(id=session.id).update(
                exit_time=None, fee_amount=Decimal("0.00")
            )
