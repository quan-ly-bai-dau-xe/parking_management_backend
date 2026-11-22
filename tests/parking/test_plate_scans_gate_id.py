"""
Comprehensive Gate ID Validation and Concurrency Test Suite.

Verifies:
1. gate_id parameter validation and parsing (API integration and unit parser):
   - Rejection of invalid inputs (-1, 0, abc, 1.5, null, -999, 0.0, NaN, Infinity, SQL/XSS, etc.)
     with HTTP 400 Bad Request and PROP-GEN-P01.
   - Acceptance of valid inputs (None/omitted, "", positive integers) with HTTP 200 OK.
2. Concurrency burst:
   - 10 concurrent requests with preview=true.
   - Strictly 0 Cloudinary calls (upload or destroy).
   - Structured logging of gate_id in parking_api_request events.
   - 0 race conditions, deadlocks, or HTTP failures.
3. Mixed concurrency burst:
   - Concurrent interleaving of preview=true and authoritative (preview=false) requests.
"""

import concurrent.futures
import io
import json
import logging
from typing import Any

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.exceptions import BusinessAPIException
from apps.parking.services.ocr import (
    DummyPlateRecognizer,
    set_global_recognizer,
)
from apps.parking.views.scans import parse_gate_id
from tests.parking.contract_reference_validator import (
    validate_plate_scan_reference_contract,
)

pytestmark = pytest.mark.django_db


def _create_jpeg_file(name: str = "gate_scan.jpg") -> SimpleUploadedFile:
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 100), color="white")
    img.save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_gate_test@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


# ============================================================================
# Section 1: gate_id Parameter Validation and Parsing
# ============================================================================


class TestGateIdValidationAndParsing:
    """Fuzzing and boundary tests for gate_id parameter across API and unit parser."""

    @pytest.mark.parametrize(
        "invalid_gate_id",
        [
            "-1",
            "0",
            "abc",
            "1.5",
            "null",
            "-999999999",
            "0.0",
            "NaN",
            "Infinity",
            "-Infinity",
            "1e5",
            "<script>alert(1)</script>",
            "1; DROP TABLE parking_gates;",
            " 12.3 ",
            "undefined",
            "true",
            "false",
            "--1",
            "++1",
            "1a",
            "a1",
        ],
    )
    def test_api_rejects_invalid_gate_id_with_400_prop_gen_p01(
        self, auth_employee, fake_cloudinary_storage, invalid_gate_id
    ):
        """API must reject any malformed, negative, zero, or non-integer gate_id with HTTP 400 & PROP-GEN-P01."""
        client = APIClient()
        client.force_authenticate(user=auth_employee)
        file_obj = _create_jpeg_file()

        resp = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": file_obj, "gate_id": invalid_gate_id, "preview": "true"},
            format="multipart",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Expected HTTP 400 for gate_id={invalid_gate_id!r}, got {resp.status_code}"
        )
        assert resp.data["code"] == "PROP-GEN-P01"
        assert "gate_id" in resp.data["details"]
        # Must not call Cloudinary on invalid requests
        assert len(fake_cloudinary_storage.upload_calls) == 0

    @pytest.mark.parametrize(
        ("valid_gate_id", "expected_extracted"),
        [
            ("", None),
            ("999999999", 999999999),
            (999999999, 999999999),
            ("1", 1),
            ("42", 42),
            ("0012", 12),  # Leading zeros string
        ],
    )
    def test_api_accepts_valid_gate_id_cleanly(
        self, auth_employee, monkeypatch, valid_gate_id, expected_extracted
    ):
        """API must accept valid positive integers, empty string, or omitted gate_id."""
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
        set_global_recognizer(
            DummyPlateRecognizer(default_plate="51K-992.14", default_confidence=98.5)
        )

        client = APIClient()
        client.force_authenticate(user=auth_employee)
        file_obj = _create_jpeg_file()

        resp = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": file_obj, "gate_id": valid_gate_id, "preview": "true"},
            format="multipart",
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["plate_final"] == "51K99214"
        validate_plate_scan_reference_contract(resp.data)
        set_global_recognizer(None)

    def test_api_omitted_gate_id_passes_cleanly(self, auth_employee, monkeypatch):
        """API must pass cleanly when gate_id field is omitted entirely (gate_id=None)."""
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
        set_global_recognizer(
            DummyPlateRecognizer(default_plate="51K-992.14", default_confidence=98.5)
        )

        client = APIClient()
        client.force_authenticate(user=auth_employee)
        file_obj = _create_jpeg_file()

        resp = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": file_obj, "preview": "true"},
            format="multipart",
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["plate_final"] == "51K99214"
        validate_plate_scan_reference_contract(resp.data)
        set_global_recognizer(None)

    @pytest.mark.parametrize(
        "invalid_raw",
        [
            "-1",
            -1,
            "0",
            0,
            "abc",
            "1.5",
            1.5,
            True,
            False,
            "null",
            None if False else "None",
            "-999999999",
            -999999999,
            "0.0",
            "NaN",
            "Infinity",
            [1],
            {"id": 1},
        ],
    )
    def test_parse_gate_id_unit_invalid_inputs(self, invalid_raw):
        """Unit test: parse_gate_id must raise BusinessAPIException(PROP-GEN-P01) for invalid inputs."""
        with pytest.raises(BusinessAPIException) as exc_info:
            parse_gate_id(invalid_raw)
        assert exc_info.value.code == "PROP-GEN-P01"
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST

    @pytest.mark.parametrize(
        ("valid_raw", "expected"),
        [
            (None, None),
            ("", None),
            (1, 1),
            ("1", 1),
            (999999999, 999999999),
            ("999999999", 999999999),
            (" 42 ", 42),
        ],
    )
    def test_parse_gate_id_unit_valid_inputs(self, valid_raw, expected):
        """Unit test: parse_gate_id returns int or None for valid inputs."""
        assert parse_gate_id(valid_raw) == expected


# ============================================================================
# Section 2: Concurrency Burst & Cloudinary Call Suppression
# ============================================================================


class TestGateIdConcurrencyAndObservability:
    """Stress test: burst of 10 concurrent preview=true requests verifying 0 Cloudinary calls and structured logs."""

    def test_concurrency_burst_preview_true_zero_cloudinary_calls(
        self, auth_employee, monkeypatch, fake_cloudinary_storage, caplog
    ):
        """
        Concurrency burst:
        10 concurrent threads simultaneously send POST /api/v1/parking/plate-scans/ with preview=true.
        Assert:
        - 10/10 requests return HTTP 200 OK
        - All 10 responses have image_url is None
        - Exactly 0 Cloudinary upload calls
        - Exactly 0 Cloudinary destroy calls
        - No race conditions, deadlocks, or 500 errors
        - Structured logs record gate_id in parking_api_request events
        """
        caplog.set_level(logging.INFO)
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
        set_global_recognizer(
            DummyPlateRecognizer(default_plate="51K-992.14", default_confidence=98.5)
        )

        initial_upload_count = len(fake_cloudinary_storage.upload_calls)
        initial_destroy_count = len(fake_cloudinary_storage.destroyed_public_ids)

        def make_preview_request(req_idx: int) -> tuple[int, dict[str, Any]]:
            try:
                # Each thread needs its own client instance to simulate independent HTTP clients
                client = APIClient()
                client.force_authenticate(user=auth_employee)
                file_obj = _create_jpeg_file(f"burst_{req_idx}.jpg")
                response = client.post(
                    "/api/v1/parking/plate-scans/",
                    {"image": file_obj, "preview": "true", "gate_id": req_idx + 1},
                    format="multipart",
                    HTTP_X_REQUEST_ID=f"burst-test-req-{req_idx:02d}",
                )
                return response.status_code, response.data
            finally:
                from django.db import connections

                connections.close_all()

        # Launch 10 concurrent requests simultaneously
        concurrency_level = 10
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=concurrency_level
        ) as executor:
            futures = [
                executor.submit(make_preview_request, i)
                for i in range(concurrency_level)
            ]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        # 1. Verify all 10 responses succeeded
        assert len(results) == concurrency_level
        for status_code, data in results:
            assert status_code == status.HTTP_200_OK
            assert data["image_url"] is None, "preview=true must return image_url=None"
            assert data["plate_final"] == "51K99214"
            validate_plate_scan_reference_contract(data)

        # 2. Verify Cloudinary call suppression (strictly 0 calls)
        assert len(fake_cloudinary_storage.upload_calls) == initial_upload_count, (
            f"Expected 0 Cloudinary uploads during preview burst, got {len(fake_cloudinary_storage.upload_calls)}"
        )
        assert (
            len(fake_cloudinary_storage.destroyed_public_ids) == initial_destroy_count
        ), (
            f"Expected 0 Cloudinary destroys during preview burst, got {len(fake_cloudinary_storage.destroyed_public_ids)}"
        )

        # 3. Inspect structured observability logs
        scan_logs = []
        for rec in caplog.records:
            try:
                log_data = json.loads(rec.getMessage())
                if log_data.get("event") == "parking_api_request":
                    scan_logs.append(log_data)
            except Exception:
                pass
        assert len(scan_logs) == concurrency_level, (
            f"Expected {concurrency_level} structured scan log entries, found {len(scan_logs)}"
        )
        gate_ids_logged = {log_entry["gate_id"] for log_entry in scan_logs}
        assert gate_ids_logged == set(range(1, concurrency_level + 1))
        for log_entry in scan_logs:
            assert log_entry["status"] == 200
            assert log_entry["review_status"] == "AUTO"

        set_global_recognizer(None)

    def test_concurrency_burst_mixed_preview_and_authoritative(
        self, auth_employee, monkeypatch, fake_cloudinary_storage
    ):
        """
        Mixed concurrency burst:
        5 requests with preview=true and 5 requests with preview=false interleaved concurrently.
        Assert:
        - Exactly 5 Cloudinary uploads occurred (corresponding to preview=false only)
        - The 5 preview=true requests have image_url=None
        - The 5 preview=false requests have valid https image_url
        - No race conditions between concurrent requests
        """
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
        set_global_recognizer(
            DummyPlateRecognizer(default_plate="51K-992.14", default_confidence=98.5)
        )

        initial_upload_count = len(fake_cloudinary_storage.upload_calls)

        def make_request(req_idx: int) -> tuple[int, bool, dict[str, Any]]:
            try:
                is_preview = req_idx % 2 == 0
                client = APIClient()
                client.force_authenticate(user=auth_employee)
                file_obj = _create_jpeg_file(f"mixed_{req_idx}.jpg")
                response = client.post(
                    "/api/v1/parking/plate-scans/",
                    {
                        "image": file_obj,
                        "preview": "true" if is_preview else "false",
                        "gate_id": req_idx + 1,
                    },
                    format="multipart",
                    HTTP_X_REQUEST_ID=f"mixed-test-req-{req_idx:02d}",
                )
                return response.status_code, is_preview, response.data
            finally:
                from django.db import connections

                connections.close_all()

        total_requests = 10
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=total_requests
        ) as executor:
            futures = [executor.submit(make_request, i) for i in range(total_requests)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]

        assert len(results) == total_requests
        preview_count = 0
        authoritative_count = 0

        for status_code, is_preview, data in results:
            assert status_code == status.HTTP_200_OK
            if is_preview:
                preview_count += 1
                assert data["image_url"] is None
            else:
                authoritative_count += 1
                assert data["image_url"] is not None
                assert data["image_url"].startswith("https://res.cloudinary.com/")

        assert preview_count == 5
        assert authoritative_count == 5

        # Cloudinary uploads must be exactly 5 (only from authoritative requests)
        assert len(fake_cloudinary_storage.upload_calls) == initial_upload_count + 5

        set_global_recognizer(None)
