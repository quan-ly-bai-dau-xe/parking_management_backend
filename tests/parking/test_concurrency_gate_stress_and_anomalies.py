"""
Boundary empirical stress tests for Parking Concurrency Gate:
- Concurrency Gate: burst overload, HTTP 503, Retry-After header, envelope, zero slot leakage.
- Anomalous payloads (empty form, empty urlencoded, raw stream, json) returning 400 PROP-4.5.1-P02 without 415.
"""

import concurrent.futures
import io
import time
from typing import Any

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.concurrency import (
    OCRConcurrencyGate,
    set_ocr_concurrency_gate,
)
from apps.parking.services.ocr import (
    DummyPlateRecognizer,
    PlateScanResult,
    set_global_recognizer,
)

pytestmark = pytest.mark.django_db


def _make_dummy_jpeg(name: str = "stress_test.jpg") -> SimpleUploadedFile:
    buf = io.BytesIO()
    img = Image.new("RGB", (160, 80), color="blue")
    img.save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@pytest.fixture
def test_employee():
    user, _ = Account.objects.get_or_create(
        email="verification_emp@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return user


class DelayingPlateRecognizer(DummyPlateRecognizer):
    """Recognizer with artificial delay to simulate heavy inference in stress harness."""

    def __init__(self, delay_sec: float = 0.08, default_plate: str = "51K-992.14"):
        super().__init__(default_plate=default_plate)
        self.delay_sec = delay_sec

    def recognize(self, image_input: Any) -> PlateScanResult:
        if self.delay_sec > 0:
            time.sleep(self.delay_sec)
        return super().recognize(image_input)


# ==============================================================================
# TEST 1: BURST CONCURRENCY & HTTP 503 BACK-PRESSURE WITH RETRY-AFTER
# ==============================================================================
def test_boundary_concurrency_gate_burst_overload(test_employee, monkeypatch):
    """
    Stress-test: Gửi burst đồng thời 16 requests với gate limit=2 và queue timeout=0.03s.
    Chứng minh:
    - Các requests xếp hàng quá hạn trả về chính xác HTTP 503 Service Unavailable.
    - Header Retry-After xuất hiện với giá trị integer string (ví dụ "4").
    - Error envelope tuân thủ chuẩn PROP-4.5.1-P15 và details rỗng.
    - 0 lỗi 500, 0 kết nối treo.
    """
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    set_global_recognizer(
        DelayingPlateRecognizer(delay_sec=0.07, default_plate="51K-992.14")
    )

    gate = OCRConcurrencyGate(limit=2, timeout=0.03, retry_after=4)
    set_ocr_concurrency_gate(gate)

    def worker_request() -> tuple[int, dict[str, str], dict[str, Any]]:
        try:
            client = APIClient()
            client.force_authenticate(user=test_employee)
            f = _make_dummy_jpeg()
            resp = client.post(
                "/api/v1/parking/plate-scans/",
                {"image": f},
                format="multipart",
            )
            return resp.status_code, dict(resp.headers), resp.data
        finally:
            connection.close()

    concurrency = 16
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker_request) for _ in range(concurrency)]
        results = [fut.result(timeout=5.0) for fut in futures]

    status_codes = [r[0] for r in results]
    assert 500 not in status_codes
    assert all(
        code in (status.HTTP_200_OK, status.HTTP_503_SERVICE_UNAVAILABLE)
        for code in status_codes
    )

    # Có ít nhất 1 request bị quá tải do burst 16 requests vào limit=2
    overloaded_responses = [
        r for r in results if r[0] == status.HTTP_503_SERVICE_UNAVAILABLE
    ]
    assert len(overloaded_responses) > 0, (
        "Gate should have triggered 503 back-pressure under burst load"
    )

    for _, headers, data in overloaded_responses:
        assert headers.get("Retry-After") == "4"
        assert data.get("code") == "PROP-4.5.1-P15"
        assert "quá tải" in data.get("message", "")
        assert data.get("details") == {}

    # Reset
    set_ocr_concurrency_gate(None)
    set_global_recognizer(None)


# ==============================================================================
# TEST 2: MULTITHREADED ZERO SLOT LEAKAGE & EXCEPTION RECOVERY
# ==============================================================================
def test_boundary_concurrency_gate_zero_slot_leakage(test_employee, monkeypatch):
    """
    Stress-test: Đảm bảo sau burst nhiều luồng và sau khi gặp exception nội bộ,
    Semaphore không bao giờ rò rỉ permit (internal _value luôn hồi phục về đúng limit).
    """
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    set_global_recognizer(
        DelayingPlateRecognizer(delay_sec=0.04, default_plate="51K-992.14")
    )

    limit = 3
    gate = OCRConcurrencyGate(limit=limit, timeout=0.02, retry_after=2)
    set_ocr_concurrency_gate(gate)

    def worker_request() -> int:
        try:
            client = APIClient()
            client.force_authenticate(user=test_employee)
            f = _make_dummy_jpeg()
            resp = client.post(
                "/api/v1/parking/plate-scans/",
                {"image": f},
                format="multipart",
            )
            return resp.status_code
        finally:
            connection.close()

    # 1. Chạy 24 requests đa luồng
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        futures = [pool.submit(worker_request) for _ in range(24)]
        codes = [fut.result(timeout=5.0) for fut in futures]

    assert 500 not in codes
    # Kiểm tra semaphore value sau khi toàn bộ luồng hoàn tất
    assert gate._semaphore._value == limit, (
        f"Semaphore leaked! Expected {limit}, got {gate._semaphore._value}"
    )

    # 2. Gửi ngay request tiếp theo để chứng minh cổng phục vụ bình thường
    client = APIClient()
    client.force_authenticate(user=test_employee)
    f = _make_dummy_jpeg()
    resp_subsequent = client.post(
        "/api/v1/parking/plate-scans/",
        {"image": f},
        format="multipart",
    )
    assert resp_subsequent.status_code == status.HTTP_200_OK

    # 3. Thử nghiệm khi xảy ra ngoại lệ không mong muốn bên trong block acquire
    class FaultyRecognizer:
        def recognize(self, _):
            raise RuntimeError("Simulated crash inside inference block")

    set_global_recognizer(FaultyRecognizer())
    for _ in range(20):
        try:
            with gate.acquire():
                FaultyRecognizer().recognize(None)
        except RuntimeError:
            pass

    # Sau 20 ngoại lệ, semaphore phải bảo toàn nguyên vẹn permit
    assert gate._semaphore._value == limit, (
        f"Permit leaked after exceptions! Expected {limit}, got {gate._semaphore._value}"
    )

    # Reset
    set_ocr_concurrency_gate(None)
    set_global_recognizer(None)


# ==============================================================================
# TEST 3: LEFTOVER (C) ANOMALOUS & MALFORMED PAYLOADS MUST RETURN 400 (NOT 415/500)
# ==============================================================================
def test_boundary_leftover_c_all_anomalous_payloads(test_employee):
    """
    Thách thức Leftover (c):
    Gửi các dạng payload dị thường:
    - multipart rỗng không có field
    - multipart có field khác nhưng không có file image
    - form-urlencoded rỗng
    - form-urlencoded có data không có file
    - json rỗng
    - json có fields
    - raw stream hỏng / byte rác
    - raw octet-stream
    Chứng minh: Tất cả đều trả về HTTP 400 với mã PROP-4.5.1-P02 (không có 415, không có 500).
    """
    client = APIClient()
    client.force_authenticate(user=test_employee)

    anomalous_test_cases = [
        ("empty_urlencoded", "application/x-www-form-urlencoded", b""),
        (
            "data_urlencoded_no_file",
            "application/x-www-form-urlencoded",
            b"gate_id=1&plate_text=51K12345",
        ),
        ("empty_json", "application/json", b"{}"),
        (
            "data_json_no_file",
            "application/json",
            b'{"image": "invalid.jpg", "gate_id": 1}',
        ),
        ("raw_text_stream", "text/plain", b"CORRUPTED_RAW_STREAM_DATA_ABCXYZ"),
        (
            "raw_octet_stream",
            "application/octet-stream",
            b"\x00\x01\x02\x03\xff\xd8\xff\xe0\x00\x10JFIF",
        ),
        (
            "empty_multipart",
            "multipart/form-data; boundary=----WebKitFormBoundaryDummy123",
            b"------WebKitFormBoundaryDummy123--\r\n",
        ),
        (
            "multipart_without_image_field",
            "multipart/form-data; boundary=----WebKitFormBoundaryDummy123",
            (
                b"------WebKitFormBoundaryDummy123\r\n"
                b'Content-Disposition: form-data; name="gate_id"\r\n\r\n'
                b"1\r\n"
                b"------WebKitFormBoundaryDummy123--\r\n"
            ),
        ),
    ]

    for case_name, content_type, raw_body in anomalous_test_cases:
        resp = client.post(
            "/api/v1/parking/plate-scans/",
            data=raw_body,
            content_type=content_type,
        )
        assert resp.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Case '{case_name}' failed: expected HTTP 400, got HTTP {resp.status_code} "
            f"with body: {resp.content.decode('utf-8', errors='replace')}"
        )
        assert resp.data.get("code") == "PROP-4.5.1-P02", (
            f"Case '{case_name}' failed: expected code PROP-4.5.1-P02, got {resp.data.get('code')}"
        )
        assert "không được để trống" in resp.data.get("message", ""), (
            f"Case '{case_name}' message mismatch: {resp.data.get('message')}"
        )
        assert resp.status_code != status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
        assert resp.status_code != status.HTTP_500_INTERNAL_SERVER_ERROR


# ==============================================================================
# TEST 4: HIGH-CONCURRENCY TORTURE (32 THREADS x 3 CYCLES)
# ==============================================================================
def test_boundary_high_concurrency_torture(test_employee, monkeypatch):
    """
    Stress-test áp lực cao: 32 threads x 3 đợt = 96 requests đồng thời.
    Chứng minh:
    - Hệ thống hoạt động trơn tru.
    - 0 kết nối treo (tất cả hoàn tất trong 5 giây).
    - 0 lỗi 500.
    - Không có deadlock.
    """
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    set_global_recognizer(
        DelayingPlateRecognizer(delay_sec=0.03, default_plate="51K-992.14")
    )

    gate = OCRConcurrencyGate(limit=4, timeout=0.04, retry_after=2)
    set_ocr_concurrency_gate(gate)

    def hit_endpoint() -> int:
        try:
            client = APIClient()
            client.force_authenticate(user=test_employee)
            f = _make_dummy_jpeg()
            resp = client.post(
                "/api/v1/parking/plate-scans/",
                {"image": f},
                format="multipart",
            )
            return resp.status_code
        finally:
            connection.close()

    for cycle in range(3):
        with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
            futures = [pool.submit(hit_endpoint) for _ in range(32)]
            codes = [fut.result(timeout=6.0) for fut in futures]

        assert 500 not in codes, f"Cycle {cycle} returned HTTP 500!"
        assert all(c in (200, 503) for c in codes), (
            f"Cycle {cycle} unexpected status codes: {set(codes)}"
        )

    assert gate._semaphore._value == 4, (
        f"Final semaphore state invalid: {gate._semaphore._value}"
    )

    set_ocr_concurrency_gate(None)
    set_global_recognizer(None)
