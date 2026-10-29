"""
Boundary Stress Test Suite for Plate Scans Lifecycle Management.

Focus Areas Tested Empirically:
1. 422 Residual Artifacts: Burst uploads across JPEG, PNG, WEBP and mid-process OCR crashes.
   Confirm zero leftover files in MEDIA_ROOT under all failure paths.
2. EXIF Orientation Transpose Matrix: Orientation tags 6 (90 CW), 8 (270 CW), 3 (180), 1 (Normal), and None.
   Confirm transposed upright dimensions (height > width) at both OCR input bytes and disk persistence,
   and confirm EXIF metadata is completely stripped on saved disk files.
3. Stream Ingestion Defense:
   - Early abort on declared size > 5MB (zero bytes read from stream).
   - Deceptive spoofed declared size with 12MB body (stream capped at max_bytes + 1).
   - Infinite byte generator stream (bounded read prevents Memory Exhaustion / OOM).
   - Exact boundary limits (5MB pass vs 5MB + 1 byte reject).
"""

import io
from pathlib import Path
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.exceptions import BusinessAPIException
from apps.parking.services.ocr import DummyPlateRecognizer, set_global_recognizer
from apps.parking.services.upload import (
    process_uploaded_image,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="verification_m2_emp@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


# ==============================================================================
# 1. BOUNDARY STRESS TEST: 422 RESIDUAL ARTIFACTS & MID-PROCESS CRASH CLEANUP
# ==============================================================================
class TestBoundaryF10ResidualArtifacts:
    """Thử nghiệm thực nghiệm đối kháng về rò rỉ tệp trong MEDIA_ROOT khi quét thất bại."""

    def test_burst_422_uploads_across_formats_leaves_zero_leftovers(
        self, auth_employee, monkeypatch
    ):
        """
        Stress test: Upload liên tiếp 15 bức ảnh không chứa biển số (5 JPEG, 5 PNG, 5 WEBP).
        Xác nhận:
        - Tất cả 15 requests đều trả về HTTP 422 PROP-4.5.1-P06.
        - Số lượng tệp phát sinh trong MEDIA_ROOT chính xác là 0.
        """
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
        set_global_recognizer(DummyPlateRecognizer(default_plate=""))

        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)
        files_before = set(media_root.rglob("*"))

        client = APIClient()
        client.force_authenticate(user=auth_employee)

        formats = [
            ("JPEG", "image/jpeg", "empty_{}.jpg"),
            ("PNG", "image/png", "empty_{}.png"),
            ("WEBP", "image/webp", "empty_{}.webp"),
        ]

        results = []
        for fmt, content_type, filename_pattern in formats:
            for i in range(5):
                buf = io.BytesIO()
                img = Image.new("RGB", (180 + i * 10, 90 + i * 5), color="gray")
                img.save(buf, format=fmt)
                file_obj = SimpleUploadedFile(
                    filename_pattern.format(i),
                    buf.getvalue(),
                    content_type=content_type,
                )

                resp = client.post(
                    "/api/v1/parking/plate-scans/",
                    {"image": file_obj},
                    format="multipart",
                )
                assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
                assert resp.data["code"] == "PROP-4.5.1-P06"
                results.append(resp.status_code)

        assert len(results) == 15
        assert all(code == 422 for code in results)

        files_after = set(media_root.rglob("*"))
        leftover_files = [f for f in (files_after - files_before) if f.is_file()]
        assert len(leftover_files) == 0, (
            f"Boundary Failure: Found {len(leftover_files)} leftover files after 15 burst 422 requests: {leftover_files}"
        )

        set_global_recognizer(None)

    def test_mid_process_crash_after_save_triggers_unlink_cleanup(
        self, auth_employee, monkeypatch
    ):
        """
        Thử nghiệm kịch bản lỗi bất thường (defensive test):
        Ảnh hợp lệ, OCR tìm thấy biển số, file ĐÃ ĐƯỢC LƯU VÀO ĐĨA,
        nhưng sau đó hệ thống gặp crash đột ngột (ví dụ cơ sở dữ liệu tra cứu bị lỗi).
        Xác nhận khối defensive exception handling trong PlateScanView lập tức unlink file rác.
        """
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
        set_global_recognizer(
            DummyPlateRecognizer(default_plate="51K-123.45", default_confidence=99.0)
        )

        media_root = Path(settings.MEDIA_ROOT)
        media_root.mkdir(parents=True, exist_ok=True)
        files_before = set(media_root.rglob("*"))

        client = APIClient()
        client.force_authenticate(user=auth_employee)

        buf = io.BytesIO()
        Image.new("RGB", (200, 100), color="green").save(buf, format="JPEG")
        file_obj = SimpleUploadedFile(
            "crash_test.jpg", buf.getvalue(), content_type="image/jpeg"
        )

        # Mô phỏng lỗi crash bất ngờ ở bước tra cứu xe vehicle_lookup_func
        with patch(
            "apps.parking.views.scans.vehicle_lookup_func",
            side_effect=RuntimeError("Database Connection Abruptly Terminated!"),
        ):
            resp = client.post(
                "/api/v1/parking/plate-scans/",
                {"image": file_obj},
                format="multipart",
            )
            assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # File đã lưu trước khi crash phải bị xóa hoàn toàn khỏi đĩa (defensive unlink)
        files_after = set(media_root.rglob("*"))
        new_files = [f for f in (files_after - files_before) if f.is_file()]
        assert len(new_files) == 0, (
            f"Boundary Failure: Defensive unlink failed! Leftover file exists: {new_files}"
        )

        set_global_recognizer(None)


# ==============================================================================
# 2. BOUNDARY STRESS TEST: EXIF ORIENTATION TRANSPOSE MATRIX
# ==============================================================================
class TestBoundaryF10ExifOrientationMatrix:
    """Thử nghiệm thực nghiệm đối kháng về xử lý thẻ xoay EXIF Orientation."""

    @pytest.mark.parametrize(
        "orientation,orig_w,orig_h,expected_w,expected_h,should_transpose",
        [
            (6, 400, 200, 200, 400, True),  # 90 độ CW: ngang 400x200 -> dọc 200x400
            (
                8,
                500,
                250,
                250,
                500,
                True,
            ),  # 270 độ CW (90 CCW): ngang 500x250 -> dọc 250x500
            (3, 300, 150, 300, 150, False),  # 180 độ: giữ nguyên tỷ lệ kích thước
            (1, 350, 150, 350, 150, False),  # 0 độ: bình thường
            (None, 320, 160, 320, 160, False),  # Không có thẻ EXIF: bình thường
        ],
    )
    def test_exif_orientation_matrix(
        self,
        auth_employee,
        monkeypatch,
        orientation,
        orig_w,
        orig_h,
        expected_w,
        expected_h,
        should_transpose,
    ):
        """
        Kiểm tra ma trận các hướng xoay EXIF:
        - Kích thước gửi tới OCR engine phải đúng chuẩn expected (chiều cao > chiều rộng nếu orientation 6, 8).
        - Kích thước lưu trên đĩa MEDIA_ROOT phải đúng chuẩn expected.
        - EXIF metadata trên tệp lưu đĩa phải bị tước bỏ hoàn toàn (strip EXIF).
        """
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")

        captured_dimensions = []

        class DimensionCapturingRecognizer(DummyPlateRecognizer):
            def recognize(self, image_data):
                if isinstance(image_data, bytes):
                    with Image.open(io.BytesIO(image_data)) as im:
                        captured_dimensions.append(im.size)
                return super().recognize(image_data)

        set_global_recognizer(
            DimensionCapturingRecognizer(
                default_plate="51A-999.88", default_confidence=95.0
            )
        )

        exif = Image.Exif() if orientation is not None else None
        if exif is not None and orientation is not None:
            exif[0x0112] = orientation

        buf = io.BytesIO()
        img = Image.new("RGB", (orig_w, orig_h), color="yellow")
        if exif is not None:
            img.save(buf, format="JPEG", exif=exif)
        else:
            img.save(buf, format="JPEG")

        file_obj = SimpleUploadedFile(
            f"orient_{orientation}.jpg", buf.getvalue(), content_type="image/jpeg"
        )

        client = APIClient()
        client.force_authenticate(user=auth_employee)

        resp = client.post(
            "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
        )
        assert resp.status_code == status.HTTP_200_OK

        # 1. OCR nhận ảnh đúng kích thước chuẩn hóa
        assert len(captured_dimensions) == 1
        assert captured_dimensions[0] == (expected_w, expected_h)
        if should_transpose:
            assert captured_dimensions[0][1] > captured_dimensions[0][0], (
                f"Orientation {orientation} should result in height > width, got {captured_dimensions[0]}"
            )

        # 2. File lưu trên đĩa đúng kích thước và tước bỏ EXIF
        media_url = getattr(settings, "MEDIA_URL", "/media/")
        rel_url = resp.data["image_url"]
        rel_path = (
            rel_url[len(media_url) :].lstrip("/")
            if rel_url.startswith(media_url)
            else rel_url.removeprefix(media_url)
        )
        disk_path = Path(settings.MEDIA_ROOT) / rel_path
        assert disk_path.is_file()

        with Image.open(disk_path) as disk_img:
            assert disk_img.size == (expected_w, expected_h)
            # Thẻ EXIF orientation phải bị xóa hoàn toàn khỏi file lưu đĩa
            assert disk_img.getexif().get(0x0112) is None

        set_global_recognizer(None)


# ==============================================================================
# 3. BOUNDARY STRESS TEST: STREAM INGESTION & BOUNDED DOS DEFENSE
# ==============================================================================
class TestBoundaryF10StreamIngestionDefense:
    """Thử nghiệm thực nghiệm đối kháng về phòng vệ stream và giới hạn bộ nhớ RAM."""

    def test_declared_large_size_aborts_without_single_stream_read(self):
        """
        Tấn công gửi payload 25MB với declared size:
        Hệ thống phát hiện size > 5MB và reject ngay lập tức mà KHÔNG gọi stream.read() dù chỉ 1 lần.
        """

        class MonitoredStream(io.BytesIO):
            def __init__(self, data, size):
                super().__init__(data)
                self.size = size
                self.read_count = 0
                self.total_bytes_read = 0

            def read(self, *args):
                self.read_count += 1
                chunk = super().read(*args)
                self.total_bytes_read += len(chunk)
                return chunk

        oversized_bytes = 25 * 1024 * 1024  # 25 MB
        stream = MonitoredStream(b"\x00" * 1024, size=oversized_bytes)

        with pytest.raises(BusinessAPIException) as exc:
            process_uploaded_image(stream)

        assert exc.value.status_code == 400
        assert exc.value.code == "PROP-4.5.1-P03"
        assert stream.read_count == 0, (
            f"Boundary Failure: stream.read() was invoked {stream.read_count} times on declared oversize file!"
        )
        assert stream.total_bytes_read == 0

    def test_spoofed_declared_size_capped_at_max_bytes_plus_one(self):
        """
        Tấn công giả mạo (Size Spoofing Attack):
        Kẻ tấn công khai báo file.size = 120 bytes, nhưng stream thực tế bơm 12MB.
        Hệ thống phải giới hạn đọc tối đa đúng max_bytes + 1 = 5,242,881 bytes,
        từ chối ngay và KHÔNG nạp toàn bộ 12MB vào RAM.
        """
        max_bytes = 5 * 1024 * 1024
        max_limit = max_bytes + 1

        class SpoofedStream(io.BytesIO):
            def __init__(self, data, spoofed_size):
                super().__init__(data)
                self.size = spoofed_size
                self.bytes_read = 0

            def read(self, *args):
                chunk = super().read(*args)
                self.bytes_read += len(chunk)
                return chunk

        large_payload = b"\xff\xd8\xff\xe0" + b"\x00" * (12 * 1024 * 1024)  # 12 MB
        spoofed = SpoofedStream(large_payload, spoofed_size=120)

        with pytest.raises(BusinessAPIException) as exc:
            process_uploaded_image(spoofed)

        assert exc.value.status_code == 400
        assert exc.value.code == "PROP-4.5.1-P03"
        assert spoofed.bytes_read == max_limit, (
            f"Boundary Failure: Expected exactly {max_limit} bytes read, but read {spoofed.bytes_read} bytes!"
        )

    def test_infinite_generator_stream_capped_and_rejected(self):
        """
        Tấn công luồng vô tận (Infinite Generator Stream DOS Attack):
        Mô phỏng socket client truyền byte liên tục không có điểm dừng.
        Hệ thống phải đọc đúng 5,242,881 bytes rồi ngắt lập tức mà không treo CPU/RAM.
        """
        max_bytes = 5 * 1024 * 1024
        max_limit = max_bytes + 1

        class InfiniteStream:
            def __init__(self):
                self.bytes_served = 0

            def read(self, size=-1):
                if size <= 0:
                    raise RuntimeError(
                        "Unbounded read requested! Vulnerable to Memory Exhaustion!"
                    )
                chunk = b"\x00" * size
                self.bytes_served += len(chunk)
                return chunk

        infinite = InfiniteStream()

        with pytest.raises(BusinessAPIException) as exc:
            process_uploaded_image(infinite)

        assert exc.value.status_code == 400
        assert exc.value.code == "PROP-4.5.1-P03"
        assert infinite.bytes_served == max_limit

    def test_boundary_limit_at_exact_5mb_vs_5mb_plus_one(self):
        """
        Kiểm tra ranh giới chính xác (Boundary Value Analysis):
        - 5MB tròn (5,242,880 bytes): Không bị lỗi kích thước PROP-4.5.1-P03.
        - 5MB + 1 byte (5,242,881 bytes): Bị chặn với lỗi PROP-4.5.1-P03.
        """
        max_bytes = 5 * 1024 * 1024  # 5,242,880 bytes

        # 1. Đúng 5MB + 1 byte -> Bị chặn với PROP-4.5.1-P03
        over_boundary = io.BytesIO(b"\x00" * (max_bytes + 1))
        with pytest.raises(BusinessAPIException) as exc_over:
            process_uploaded_image(over_boundary)
        assert exc_over.value.code == "PROP-4.5.1-P03"

        # 2. Đúng 5MB tròn -> Vượt qua kiểm tra kích thước (chỉ lỗi magic bytes vì toàn \x00)
        exact_5mb = io.BytesIO(b"\x00" * max_bytes)
        with pytest.raises(BusinessAPIException) as exc_exact:
            process_uploaded_image(exact_5mb)
        # Không được là lỗi P03 (quá dung lượng), mà là P04 (định dạng không hỗ trợ)
        assert exc_exact.value.code == "PROP-4.5.1-P04"
