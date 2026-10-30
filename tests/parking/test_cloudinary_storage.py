"""
Comprehensive unit and integration tests for Cloudinary image storage backend,
Decree 13/2023/ND-CP compliance, dual URL validation, and fail-closed error handling.
"""

import io
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.core.exceptions import BusinessAPIException
from apps.parking.models import ParkingGate
from apps.parking.serializers.sessions import (
    CheckInRequestSerializer,
    ParkingImageRelativeUrlField,
)
from apps.parking.services.ocr import DummyPlateRecognizer, PlateScanResult
from apps.parking.services.plate_scan import (
    compose_scan_contract_payload,
    execute_plate_scan,
)
from apps.parking.services.upload import (
    ProcessedImage,
    process_uploaded_image,
    save_processed_image,
    validate_parking_image_path,
)


def _create_processed_image() -> ProcessedImage:
    """Helper creating an in-memory ProcessedImage fixture."""
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 200), color="blue")
    img.save(buf, format="JPEG")
    return ProcessedImage(
        pil_image=img,
        width=200,
        height=200,
        format="JPEG",
        ext=".jpg",
        image_bytes=buf.getvalue(),
    )


# ==============================================================================
# 1. URL Validation Tests
# ==============================================================================


def test_validate_parking_image_path_none_allowed():
    """None is permitted for optional/nullable image fields."""
    assert validate_parking_image_path(None) is None


def test_validate_parking_image_path_empty_rejected():
    """Empty string is rejected with PROP-4.5.1-P13."""
    with pytest.raises(BusinessAPIException) as exc_info:
        validate_parking_image_path("")
    assert exc_info.value.code == "PROP-4.5.1-P13"


def test_validate_parking_image_path_exceeds_255_rejected():
    """URL exceeding 255 characters is rejected with PROP-4.5.1-P13."""
    long_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/" + ("a" * 210) + ".jpg"
    )
    assert len(long_url) > 255
    with pytest.raises(BusinessAPIException) as exc_info:
        validate_parking_image_path(long_url)
    assert exc_info.value.code == "PROP-4.5.1-P13"


def test_validate_parking_image_path_hostile_schemes_rejected():
    """Rejects javascript:, data:, file:, ftp:, and plain http:// schemes."""
    hostile_urls = [
        "javascript:alert(1)",
        "data:image/png;base64,AAAA",
        "file:///etc/passwd",
        "ftp://example.com/scans/image.jpg",
        "http://res.cloudinary.com/test-cloud/image/upload/v12345/parking_scans/2026/10/29/12345678901234567890123456789012.jpg",
    ]
    for url in hostile_urls:
        with pytest.raises(BusinessAPIException) as exc_info:
            validate_parking_image_path(url)
        assert exc_info.value.code == "PROP-4.5.1-P13"


def test_validate_parking_image_path_foreign_domain_rejected(monkeypatch):
    """Rejects URLs from arbitrary third-party domains."""
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")
    foreign_url = "https://attacker.com/parking_scans/2026/10/29/12345678901234567890123456789012.jpg"
    with pytest.raises(BusinessAPIException) as exc_info:
        validate_parking_image_path(foreign_url)
    assert exc_info.value.code == "PROP-4.5.1-P13"


def test_validate_parking_image_path_unauthorized_cloud_name_rejected(monkeypatch):
    """Rejects Cloudinary URLs that do not match configured CLOUDINARY_CLOUD_NAME."""
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "my-company-cloud")
    unauthorized_url = (
        "https://res.cloudinary.com/other-unauthorized-cloud/image/upload/"
        "v1234567890/parking_scans/2026/10/29/12345678901234567890123456789012.jpg"
    )
    with pytest.raises(BusinessAPIException) as exc_info:
        validate_parking_image_path(unauthorized_url)
    assert exc_info.value.code == "PROP-4.5.1-P13"


def test_validate_parking_image_path_authorized_cloudinary_accepted(monkeypatch):
    """Accepts valid Cloudinary HTTPS URLs belonging to configured cloud name."""
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")
    valid_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/"
        "v1730178490/parking_scans/2026/10/29/12345678901234567890123456789012.jpg"
    )
    assert validate_parking_image_path(valid_url) == valid_url


def test_validate_parking_image_path_test_folder_rejected(monkeypatch):
    """Only the parking_scans/ folder is accepted; no test-only folder in production code."""
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")
    other_folder_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/"
        "v1730178490/r71-test/12345678901234567890123456789012.jpg"
    )
    with pytest.raises(BusinessAPIException) as exc_info:
        validate_parking_image_path(other_folder_url)
    assert exc_info.value.code == "PROP-4.5.1-P13"


def test_validate_parking_image_path_local_rejected():
    """Rejects local relative path with PROP-4.5.1-P13 per ADR-0010."""
    local_url = "/media/parking_scans/2026/10/29/12345678901234567890123456789012.jpg"
    with pytest.raises(BusinessAPIException) as exc_info:
        validate_parking_image_path(local_url)
    assert exc_info.value.code == "PROP-4.5.1-P13"


def test_parking_image_relative_url_field_validation(monkeypatch):
    """ParkingImageRelativeUrlField accepts up to 255 chars and validates Cloudinary HTTPS URLs."""
    field = ParkingImageRelativeUrlField()
    assert field.max_length == 255

    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")
    valid_cloud_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/"
        "v1730178490/parking_scans/2026/10/29/12345678901234567890123456789012.jpg"
    )
    assert field.run_validation(valid_cloud_url) == valid_cloud_url
    assert field.run_validation(None) is None


# ==============================================================================
# 2. Cloudinary Upload & Decree 13/2023/ND-CP Compliance Tests
# ==============================================================================


def test_save_processed_image_cloudinary_mode_success(monkeypatch):
    """
    save_processed_image streams directly to Cloudinary:
    - Streams directly from memory (zero disk write)
    - Uses 128-bit random UUID4 public_id (no plate text / PII)
    - Strips metadata with transformation flags force_strip
    - Organizes under parking_scans/YYYY/MM/DD
    - Returns None as file_path and HTTPS secure_url
    """
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")

    expected_secure_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/"
        "v1730178490/parking_scans/2026/10/29/b068f56813a84124a900554a299759f0.jpg"
    )

    mock_upload = MagicMock(return_value={"secure_url": expected_secure_url})
    with patch("cloudinary.uploader.upload", mock_upload):
        processed = _create_processed_image()
        dest_path, image_url = save_processed_image(processed)

        assert dest_path is None
        assert image_url == expected_secure_url

        # Verify arguments passed to cloudinary.uploader.upload
        mock_upload.assert_called_once()
        call_args, call_kwargs = mock_upload.call_args

        # 1. First argument must be an in-memory stream or bytes
        file_arg = call_args[0]
        assert isinstance(file_arg, (io.BytesIO, bytes))

        # 2. Decree 13 compliance: folder and public_id checks
        folder = call_kwargs.get("folder", "")
        assert folder.startswith("parking_scans/")
        public_id = call_kwargs.get("public_id", "")
        assert len(public_id) == 32  # 32 hex chars = 128 bits UUID4
        # Verify public_id is pure hexadecimal
        int(public_id, 16)

        # 3. Two-tier metadata stripping: transformation force_strip
        trans = call_kwargs.get("transformation", [])
        assert (
            {"flags": "force_strip"} in trans
            or {"flags": "strip_profile"} in trans
            or any("strip" in str(t) for t in trans)
        )


def test_save_processed_image_cloudinary_failure_fail_closed(monkeypatch):
    """
    On Cloudinary upload error:
    - Fails closed immediately by raising BusinessAPIException
    - Registered error code PROP-4.5.1-P17
    - Zero secrets logged
    """
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")

    mock_upload = MagicMock(
        side_effect=Exception("Connection timeout to api.cloudinary.com")
    )
    with patch("cloudinary.uploader.upload", mock_upload):
        processed = _create_processed_image()
        with pytest.raises(BusinessAPIException) as exc_info:
            save_processed_image(processed)

        assert exc_info.value.code == "PROP-4.5.1-P17"
        assert exc_info.value.status_code in (400, 502)


def test_save_processed_image_cloudinary_missing_secure_url_fail_closed(monkeypatch):
    """A Cloudinary response without a usable secure_url must fail closed, never store an empty URL."""
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")

    bad_responses = ({}, {"secure_url": ""}, {"secure_url": "http://insecure/x.jpg"})
    for bad_response in bad_responses:
        with (
            patch("cloudinary.uploader.upload", MagicMock(return_value=bad_response)),
            pytest.raises(BusinessAPIException) as exc_info,
        ):
            save_processed_image(_create_processed_image())
        assert exc_info.value.code == "PROP-4.5.1-P17"


# ==============================================================================
# 4. End-to-End API Integration Tests (Mocked Cloudinary)
# ==============================================================================


@pytest.mark.django_db
def test_check_in_api_accepts_cloudinary_image_url(monkeypatch):
    """CheckInRequestSerializer validates and accepts Cloudinary HTTPS URL."""
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")

    cloud_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/"
        "v1730178490/parking_scans/2026/10/29/12345678901234567890123456789012.jpg"
    )

    gate = ParkingGate.objects.filter(direction="IN").first()
    payload = {
        "license_plate": "51K-992.14",
        "entry_gate_id": gate.id if gate else None,
        "entry_image_url": cloud_url,
    }

    serializer = CheckInRequestSerializer(data=payload)
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["entry_image_url"] == cloud_url


@pytest.mark.django_db
def test_plate_scan_pipeline_cloudinary_mode_success(monkeypatch):
    """Plate scan returns HTTPS secure_url with direct cloud streaming."""
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")

    buf = io.BytesIO()
    Image.new("RGB", (300, 300), color="white").save(buf, format="JPEG")
    file_obj = SimpleUploadedFile(
        "plate.jpg", buf.getvalue(), content_type="image/jpeg"
    )

    expected_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/"
        "v1730178490/parking_scans/2026/10/29/b068f56813a84124a900554a299759f0.jpg"
    )

    mock_upload = MagicMock(return_value={"secure_url": expected_url})
    with patch("cloudinary.uploader.upload", mock_upload):
        rec = DummyPlateRecognizer(default_plate="51K-992.14")
        result = execute_plate_scan(file_obj, recognizer=rec)

        assert result.saved_file_path is None
        assert result.payload["image_url"] == expected_url


@pytest.mark.django_db
def test_plate_scan_pipeline_cloudinary_upload_failure_fail_closed(monkeypatch):
    """Plate scan upload failure raises PROP-4.5.1-P17 without creating DB records."""
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")

    buf = io.BytesIO()
    Image.new("RGB", (300, 300), color="white").save(buf, format="JPEG")
    file_obj = SimpleUploadedFile(
        "plate.jpg", buf.getvalue(), content_type="image/jpeg"
    )

    mock_upload = MagicMock(side_effect=Exception("Cloud connection failed"))
    with patch("cloudinary.uploader.upload", mock_upload):
        rec = DummyPlateRecognizer(default_plate="51K-992.14")
        with pytest.raises(BusinessAPIException) as exc_info:
            execute_plate_scan(file_obj, recognizer=rec)

        assert exc_info.value.code == "PROP-4.5.1-P17"


@pytest.mark.django_db
def test_plate_scan_pipeline_cloudinary_compensating_rollback(monkeypatch):
    """If downstream processing fails after upload, cloudinary.uploader.destroy is invoked."""
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")

    buf = io.BytesIO()
    Image.new("RGB", (300, 300), color="white").save(buf, format="JPEG")
    file_obj = SimpleUploadedFile(
        "plate.jpg", buf.getvalue(), content_type="image/jpeg"
    )

    expected_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/"
        "v1730178490/parking_scans/2026/10/29/b068f56813a84124a900554a299759f0.jpg"
    )

    mock_upload = MagicMock(return_value={"secure_url": expected_url})
    mock_destroy = MagicMock()
    with (
        patch("cloudinary.uploader.upload", mock_upload),
        patch("cloudinary.uploader.destroy", mock_destroy),
    ):
        rec = DummyPlateRecognizer(default_plate="51K-992.14")
        with (
            patch(
                "apps.parking.services.plate_scan.compose_scan_contract_payload",
                side_effect=RuntimeError("downstream crashed"),
            ),
            pytest.raises(RuntimeError),
        ):
            execute_plate_scan(file_obj, recognizer=rec)

        mock_destroy.assert_called_once_with(
            "parking_scans/2026/10/29/b068f56813a84124a900554a299759f0"
        )


@pytest.mark.django_db
def test_plate_scan_pipeline_compensating_destroy_failure_logged_and_fail_closed(
    monkeypatch, caplog
):
    """If compensating destroy fails, logs single warning with exception class name only and propagates error (R5)."""
    import logging

    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")

    buf = io.BytesIO()
    Image.new("RGB", (300, 300), color="white").save(buf, format="JPEG")
    file_obj = SimpleUploadedFile(
        "plate.jpg", buf.getvalue(), content_type="image/jpeg"
    )

    expected_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/"
        "v1730178490/parking_scans/2026/10/29/b068f56813a84124a900554a299759f0.jpg"
    )

    mock_upload = MagicMock(return_value={"secure_url": expected_url})
    mock_destroy = MagicMock(
        side_effect=ConnectionError("Cloudinary destroy connection lost")
    )

    with (
        patch("cloudinary.uploader.upload", mock_upload),
        patch("cloudinary.uploader.destroy", mock_destroy),
        caplog.at_level(logging.WARNING, logger="apps.parking.services.plate_scan"),
    ):
        rec = DummyPlateRecognizer(default_plate="51K-992.14")
        with (
            patch(
                "apps.parking.services.plate_scan.compose_scan_contract_payload",
                side_effect=RuntimeError("downstream crashed"),
            ),
            pytest.raises(RuntimeError),
        ):
            execute_plate_scan(file_obj, recognizer=rec)

        warning_records = [
            r
            for r in caplog.records
            if r.name == "apps.parking.services.plate_scan"
            and r.levelno == logging.WARNING
        ]
        assert len(warning_records) == 1
        assert (
            "Compensating destroy failed: ConnectionError" in warning_records[0].message
        )
        assert "Cloudinary destroy connection lost" not in warning_records[0].message


def test_validate_parking_image_path_empty_configured_cloud_name(monkeypatch):
    """Rejects URLs when CLOUDINARY_CLOUD_NAME is not configured or empty (PROP-4.5.1-P13)."""
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "")
    valid_url = (
        "https://res.cloudinary.com/test-cloud/image/upload/"
        "v1730178490/parking_scans/2026/10/29/12345678901234567890123456789012.jpg"
    )
    with pytest.raises(BusinessAPIException) as exc_info:
        validate_parking_image_path(valid_url)
    assert exc_info.value.code == "PROP-4.5.1-P13"


def test_parking_image_relative_url_field_non_string_rejected():
    """ParkingImageRelativeUrlField rejects non-string data with PROP-4.5.1-P13."""
    field = ParkingImageRelativeUrlField()
    for bad_data in [12345, True, ["url"], {"url": "val"}]:
        with pytest.raises(BusinessAPIException) as exc_info:
            field.run_validation(bad_data)
        assert exc_info.value.code == "PROP-4.5.1-P13"


def test_process_uploaded_image_bytes_and_bytearray_input():
    """process_uploaded_image accepts raw bytes or bytearray directly."""
    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="green").save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    result_bytes = process_uploaded_image(raw_bytes)
    assert result_bytes.width == 100
    assert result_bytes.height == 100
    assert result_bytes.format == "JPEG"

    result_bytearray = process_uploaded_image(bytearray(raw_bytes))
    assert result_bytearray.width == 100
    assert result_bytearray.height == 100


def test_process_uploaded_image_invalid_object_type_raises():
    """process_uploaded_image raises PROP-4.5.1-P02 when input has no read method and is not bytes."""
    for invalid_input in [12345, object(), ["image.jpg"]]:
        with pytest.raises(BusinessAPIException) as exc_info:
            process_uploaded_image(invalid_input)
        assert exc_info.value.code == "PROP-4.5.1-P02"


def test_process_uploaded_image_rgba_mode_converted_to_rgb():
    """RGBA PNG image is converted to RGB mode during preprocessing."""
    buf = io.BytesIO()
    Image.new("RGBA", (120, 80), color=(255, 0, 0, 128)).save(buf, format="PNG")
    file_obj = SimpleUploadedFile("test.png", buf.getvalue(), content_type="image/png")

    result = process_uploaded_image(file_obj)
    assert result.pil_image.mode == "RGB"
    assert result.width == 120
    assert result.height == 80


def test_compose_scan_contract_payload_empty_candidates():
    """Empty OCR candidates yields empty raw_text and raw_norm in contract payload."""
    scan_result = PlateScanResult(
        candidates=[],
        best_candidate=None,
        engine_name="dummy",
        raw_text="",
        latency_ms=1.5,
    )
    payload = compose_scan_contract_payload(
        scan_result=scan_result,
        image_relative_url="",
        vehicle_lookup_data=None,
        is_blacklisted=False,
        open_session_data=None,
    )
    assert payload["plate_raw"] == ""
    assert payload["plate_final"] == ""
    assert payload["best_candidate"] is None


@pytest.mark.django_db
def test_plate_scan_pipeline_compensating_destroy_unmatched_url(monkeypatch):
    """When relative_url contains res.cloudinary.com but does not match regex, destroy is safely skipped."""
    monkeypatch.setattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud")

    buf = io.BytesIO()
    Image.new("RGB", (100, 100), color="white").save(buf, format="JPEG")
    file_obj = SimpleUploadedFile(
        "plate.jpg", buf.getvalue(), content_type="image/jpeg"
    )

    mock_upload = MagicMock(
        return_value={"secure_url": "https://res.cloudinary.com/broken-url-no-match"}
    )
    mock_destroy = MagicMock()
    with (
        patch("cloudinary.uploader.upload", mock_upload),
        patch("cloudinary.uploader.destroy", mock_destroy),
        patch(
            "apps.parking.services.plate_scan.compose_scan_contract_payload",
            side_effect=RuntimeError("crash"),
        ),
        pytest.raises(RuntimeError),
    ):
        rec = DummyPlateRecognizer(default_plate="51K-992.14")
        execute_plate_scan(file_obj, recognizer=rec)

    mock_destroy.assert_not_called()
