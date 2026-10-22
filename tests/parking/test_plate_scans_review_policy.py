"""
Comprehensive tests for Plate Scan Review Policy, Corrections, and Trigram Suggestions (API level).
"""

import io

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.services.ocr import (
    BoundingBox,
    DummyPlateRecognizer,
    PlateCandidate,
    PlateScanResult,
    set_global_recognizer,
)
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


def _create_jpeg_file(name: str = "scan.jpg") -> SimpleUploadedFile:
    buf = io.BytesIO()
    img = Image.new("RGB", (200, 100), color="white")
    img.save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_review_policy@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture(autouse=True)
def dummy_engine(monkeypatch):
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    yield
    set_global_recognizer(None)


class TestPlateScanReviewPolicyAPI:
    """Kiểm tra chính sách review policy, corrections và suggestions qua HTTP API."""

    def test_scan_auto_status_when_all_conditions_met(self, auth_employee) -> None:
        """
        Trường hợp AUTO hoàn hảo:
        - Đồng thuận cả 2 mô hình (model_agreement = True)
        - Độ tin cậy ký tự tối thiểu >= 85.0%
        - Biển số đúng chuẩn định dạng xe Việt Nam (51K99214)
        - Không dùng detection fallback (used_detection_fallback = False)
        -> review_status: "AUTO", review_reasons: []
        """
        client = APIClient()
        client.force_authenticate(user=auth_employee)

        cand = PlateCandidate(
            plate_text="51K-992.14",
            plate_normalized="51K99214",
            confidence=98.50,
            char_confidences=[99.0, 98.5, 99.2, 98.0, 98.5, 97.9, 98.2, 98.8],
            min_char_confidence=97.90,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
        )
        custom_result = PlateScanResult(
            candidates=[cand],
            best_candidate=cand,
            engine_name="dummy",
            raw_text="51K-992.14",
            latency_ms=2.0,
            model_agreement=True,
            used_detection_fallback=False,
            review_status="AUTO",
            review_reasons=[],
        )

        dummy = DummyPlateRecognizer(preset_result=custom_result)
        set_global_recognizer(dummy)
        try:
            file_obj = _create_jpeg_file()
            response = client.post(
                "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.data
            assert data["review_status"] == "AUTO"
            assert data["review_reasons"] == []
            assert data["corrections"] == []
            assert "suggestions" in data
            assert data["best_candidate"]["plate_normalized"] == "51K99214"
            assert data["best_candidate"]["min_char_confidence"] == 97.90
        finally:
            set_global_recognizer(None)

    def test_scan_needs_review_when_model_disagreement(self, auth_employee) -> None:
        """
        Hai mô hình bất đồng thuận (model_agreement = False)
        -> review_status: "NEEDS_REVIEW", review_reasons chứa "MODEL_DISAGREEMENT"
        """
        client = APIClient()
        client.force_authenticate(user=auth_employee)

        cand = PlateCandidate(
            plate_text="51K-992.14",
            plate_normalized="51K99214",
            confidence=95.0,
            char_confidences=[95.0] * 8,
            min_char_confidence=95.0,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
        )
        custom_result = PlateScanResult(
            candidates=[cand],
            best_candidate=cand,
            engine_name="dummy",
            raw_text="51K-992.14",
            latency_ms=2.0,
            model_agreement=False,
            used_detection_fallback=False,
            review_status="NEEDS_REVIEW",
            review_reasons=["MODEL_DISAGREEMENT"],
        )

        dummy = DummyPlateRecognizer(preset_result=custom_result)
        set_global_recognizer(dummy)
        try:
            file_obj = _create_jpeg_file()
            response = client.post(
                "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.data
            assert data["review_status"] == "NEEDS_REVIEW"
            assert "MODEL_DISAGREEMENT" in data["review_reasons"]
        finally:
            set_global_recognizer(None)

    def test_scan_needs_review_when_low_char_confidence(self, auth_employee) -> None:
        """
        Độ tin cậy ký tự < ngưỡng (70.0% < 85.0%)
        -> review_status: "NEEDS_REVIEW", review_reasons chứa "LOW_CHAR_CONFIDENCE"
        """
        client = APIClient()
        client.force_authenticate(user=auth_employee)

        cand = PlateCandidate(
            plate_text="51K-992.14",
            plate_normalized="51K99214",
            confidence=70.0,
            char_confidences=[90.0, 70.0, 90.0, 90.0, 90.0, 90.0, 90.0, 90.0],
            min_char_confidence=70.0,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
        )
        custom_result = PlateScanResult(
            candidates=[cand],
            best_candidate=cand,
            engine_name="dummy",
            raw_text="51K-992.14",
            latency_ms=2.0,
            model_agreement=True,
            used_detection_fallback=False,
            review_status="NEEDS_REVIEW",
            review_reasons=["LOW_CHAR_CONFIDENCE"],
        )

        dummy = DummyPlateRecognizer(preset_result=custom_result)
        set_global_recognizer(dummy)
        try:
            file_obj = _create_jpeg_file()
            response = client.post(
                "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.data
            assert data["review_status"] == "NEEDS_REVIEW"
            assert "LOW_CHAR_CONFIDENCE" in data["review_reasons"]
        finally:
            set_global_recognizer(None)

    def test_scan_needs_review_when_fallback_detection_used(
        self, auth_employee
    ) -> None:
        """
        Nhận diện biển số sau khi kích hoạt Detection Fallback retry
        -> review_status: "NEEDS_REVIEW", review_reasons chứa "NO_DETECTION_RETRY"
        """
        client = APIClient()
        client.force_authenticate(user=auth_employee)

        cand = PlateCandidate(
            plate_text="51K-992.14",
            plate_normalized="51K99214",
            confidence=95.0,
            char_confidences=[95.0] * 8,
            min_char_confidence=95.0,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
        )
        custom_result = PlateScanResult(
            candidates=[cand],
            best_candidate=cand,
            engine_name="dummy",
            raw_text="51K-992.14",
            latency_ms=2.0,
            model_agreement=True,
            used_detection_fallback=True,
            review_status="NEEDS_REVIEW",
            review_reasons=["NO_DETECTION_RETRY"],
        )

        dummy = DummyPlateRecognizer(preset_result=custom_result)
        set_global_recognizer(dummy)
        try:
            file_obj = _create_jpeg_file()
            response = client.post(
                "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.data
            assert data["review_status"] == "NEEDS_REVIEW"
            assert "NO_DETECTION_RETRY" in data["review_reasons"]
        finally:
            set_global_recognizer(None)

    def test_scan_applies_position_aware_corrections_and_reports(
        self, auth_employee
    ) -> None:
        """
        Biển số nhận dạng thô là 5DZ1630 (D thay vì 0 ở mã tỉnh).
        -> View tự động áp dụng rule sửa D -> 0 thành 50Z1630.
        -> Trường corrections trả về thông tin chi tiết sửa đổi.
        """
        client = APIClient()
        client.force_authenticate(user=auth_employee)

        cand = PlateCandidate(
            plate_text="5DZ-1630",
            plate_normalized="5DZ1630",
            confidence=96.0,
            char_confidences=[98.0, 90.0, 97.0, 96.0, 95.0, 96.0, 97.0],
            min_char_confidence=90.0,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
        )

        dummy = DummyPlateRecognizer(preset_candidates=[cand], default_confidence=96.0)
        set_global_recognizer(dummy)
        try:
            file_obj = _create_jpeg_file()
            response = client.post(
                "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.data
            # Kiểm tra corrections
            assert len(data["corrections"]) == 1
            corr = data["corrections"][0]
            assert corr["position"] == 1
            assert corr["original_char"] == "D"
            assert corr["corrected_char"] == "0"
            assert corr["rule"] == "province_second_digit_fix"
            # J4: Non-silent substitution forces review status to NEEDS_REVIEW
            assert data["review_status"] == "NEEDS_REVIEW"
            assert "POSITION_CORRECTED" in data["review_reasons"]
        finally:
            set_global_recognizer(None)

    def test_scan_forces_needs_review_when_position_corrected_at_max_confidence(
        self, auth_employee
    ) -> None:
        """
        Even with 100% confidence, a scan that undergoes position-aware corrections
        must be forced to NEEDS_REVIEW with POSITION_CORRECTED (non-silent substitution J4).
        """
        client = APIClient()
        client.force_authenticate(user=auth_employee)

        cand = PlateCandidate(
            plate_text="51599214",
            plate_normalized="51599214",
            confidence=100.0,
            char_confidences=[100.0] * 8,
            min_char_confidence=100.0,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
        )

        dummy = DummyPlateRecognizer(preset_candidates=[cand], default_confidence=100.0)
        set_global_recognizer(dummy)
        try:
            file_obj = _create_jpeg_file()
            response = client.post(
                "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.data
            assert data["plate_raw"] == "51599214"
            assert data["plate_final"] == "51S99214"
            assert len(data["corrections"]) == 1
            assert data["review_status"] == "NEEDS_REVIEW"
            assert "POSITION_CORRECTED" in data["review_reasons"]
        finally:
            set_global_recognizer(None)

    def test_scan_remains_auto_when_clean_plate_without_corrections(
        self, auth_employee
    ) -> None:
        """
        A clean plate scan with >= 90.0% confidence, valid format, and no corrections
        must retain AUTO review status with empty review_reasons.
        """
        client = APIClient()
        client.force_authenticate(user=auth_employee)

        cand = PlateCandidate(
            plate_text="51K-992.14",
            plate_normalized="51K99214",
            confidence=98.0,
            char_confidences=[98.0] * 8,
            min_char_confidence=98.0,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
        )

        dummy = DummyPlateRecognizer(preset_candidates=[cand], default_confidence=98.0)
        set_global_recognizer(dummy)
        try:
            file_obj = _create_jpeg_file()
            response = client.post(
                "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.data
            assert data["corrections"] == []
            assert data["review_status"] == "AUTO"
            assert data["review_reasons"] == []
            assert "POSITION_CORRECTED" not in data["review_reasons"]
        finally:
            set_global_recognizer(None)

    def test_scan_provides_suggestions_when_needs_review_or_unregistered(
        self, auth_employee
    ) -> None:
        """
        Khi review_status là NEEDS_REVIEW hoặc xe chưa đăng ký, hệ thống đề xuất tối đa 3 gợi ý tương tự.
        """
        client = APIClient()
        client.force_authenticate(user=auth_employee)

        customer = Customer.objects.first()
        if not customer:
            customer = Customer.objects.create(
                code="CUST-REV01",
                full_name="Lê Văn C",
                phone="0911223344",
                identity_card_number="112233445566",
            )
        vtype, _ = VehicleType.objects.get_or_create(
            code="CAR", defaults={"name": "Ô tô"}
        )
        Vehicle.objects.create(
            customer=customer,
            code="VEH-REV01",
            license_plate="51K-992.14",
            license_plate_norm="51K99214",
            model_name="Vios",
            vehicle_type=vtype,
        )

        # Quét ra biển số sai 1 chữ số (2 -> 7): 51K99274 với confidence thấp -> NEEDS_REVIEW và chưa đăng ký
        cand = PlateCandidate(
            plate_text="51K-992.74",
            plate_normalized="51K99274",
            confidence=72.0,
            char_confidences=[90.0, 90.0, 90.0, 90.0, 90.0, 72.0, 90.0, 90.0],
            min_char_confidence=72.0,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
        )
        dummy = DummyPlateRecognizer(preset_candidates=[cand], default_confidence=72.0)
        set_global_recognizer(dummy)
        try:
            file_obj = _create_jpeg_file()
            response = client.post(
                "/api/v1/parking/plate-scans/", {"image": file_obj}, format="multipart"
            )
            assert response.status_code == status.HTTP_200_OK
            data = response.data
            assert data["review_status"] == "NEEDS_REVIEW"
            assert "suggestions" in data
            assert len(data["suggestions"]) >= 1
            assert any("51K-992.14" in s for s in data["suggestions"])
        finally:
            set_global_recognizer(None)

    def test_api_plate_scan_respects_settings_threshold_override(
        self, auth_employee
    ) -> None:
        """
        Prove HTTP API endpoint /api/v1/parking/plate-scans/ dynamically respects
        settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD without getattr fallbacks.
        - Under 90.0%: min_char_conf=88.5% -> NEEDS_REVIEW + LOW_CHAR_CONFIDENCE
        - Under 85.0%: min_char_conf=88.5% -> AUTO
        """
        client = APIClient()
        client.force_authenticate(user=auth_employee)

        cand = PlateCandidate(
            plate_text="51F-598.81",
            plate_normalized="51F59881",
            confidence=88.50,
            char_confidences=[95.0, 95.0, 95.0, 88.5, 95.0, 95.0, 95.0, 95.0],
            min_char_confidence=88.50,
            bounding_box=BoundingBox(x1=10, y1=10, x2=100, y2=50),
        )
        # Using preset_candidates triggers real view evaluation of review policy
        dummy = DummyPlateRecognizer(
            preset_candidates=[cand],
            model_agreement=True,
        )
        set_global_recognizer(dummy)
        try:
            # 1. Under default threshold 90.0% -> NEEDS_REVIEW
            with override_settings(PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD=90.0):
                file_obj = _create_jpeg_file()
                resp_default = client.post(
                    "/api/v1/parking/plate-scans/",
                    {"image": file_obj},
                    format="multipart",
                )
                assert resp_default.status_code == status.HTTP_200_OK
                data_def = resp_default.data
                assert data_def["review_status"] == "NEEDS_REVIEW"
                assert "LOW_CHAR_CONFIDENCE" in data_def["review_reasons"]

            # 2. Under overridden threshold 85.0% -> AUTO
            with override_settings(PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD=85.0):
                file_obj = _create_jpeg_file()
                resp_override = client.post(
                    "/api/v1/parking/plate-scans/",
                    {"image": file_obj},
                    format="multipart",
                )
                assert resp_override.status_code == status.HTTP_200_OK
                data_ovr = resp_override.data
                assert data_ovr["review_status"] == "AUTO"
                assert data_ovr["review_reasons"] == []
        finally:
            set_global_recognizer(None)
