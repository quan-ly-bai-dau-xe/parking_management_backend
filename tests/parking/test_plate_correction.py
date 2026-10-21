"""
Unit tests for Vietnamese plate validation, position-aware corrections, review policy, and trigram suggestions.
"""

import pytest

from apps.parking.services.plate_correction import (
    ReviewReasonCode,
    correct_plate_characters,
    evaluate_review_policy,
    get_plate_suggestions,
    is_valid_vietnamese_plate,
)
from apps.vehicles.models import Vehicle, VehicleType


@pytest.mark.django_db
class TestPlateValidationAndCorrection:
    """Test suite for Vietnamese plate regex, position-aware rules, and review policy."""

    def test_is_valid_vietnamese_plate_standard_cars(self) -> None:
        """Kiểm tra nhận diện biển số xe ô tô tiêu chuẩn 5 số và 4 số hợp lệ."""
        assert is_valid_vietnamese_plate("51K99214") is True
        assert is_valid_vietnamese_plate("30H12345") is True
        assert is_valid_vietnamese_plate("29A5678") is True
        assert is_valid_vietnamese_plate("52Y6490") is True
        assert is_valid_vietnamese_plate("39A12345") is True
        assert is_valid_vietnamese_plate("40A12345") is True
        assert is_valid_vietnamese_plate("41A12345") is True

    def test_is_valid_vietnamese_plate_dual_letter_cars(self) -> None:
        """Kiểm tra nhận diện biển xe liên doanh, ngoại giao (2 chữ cái seri)."""
        assert is_valid_vietnamese_plate("50LD04411") is True
        assert is_valid_vietnamese_plate("29DA00123") is True
        assert is_valid_vietnamese_plate("80NG12345") is True

    def test_is_valid_vietnamese_plate_motorbikes(self) -> None:
        """Kiểm tra nhận diện biển số xe máy bị từ chối do bãi xe chỉ phục vụ ô tô (SRS v4.1)."""
        assert is_valid_vietnamese_plate("29B199988") is False
        assert is_valid_vietnamese_plate("59P212345") is False

    def test_is_valid_vietnamese_plate_invalid_cases(self) -> None:
        """Kiểm tra các biển số không hợp lệ (mã tỉnh sai, độ dài sai, ký tự sai vị trí)."""
        # Mã tỉnh không tồn tại (13, 00, 42)
        assert is_valid_vietnamese_plate("13A12345") is False
        assert is_valid_vietnamese_plate("00A12345") is False
        # Độ dài quá ngắn hoặc quá dài
        assert is_valid_vietnamese_plate("51A1") is False
        assert is_valid_vietnamese_plate("51A1234567") is False
        # Chữ sai vị trí (chữ ở mã tỉnh)
        assert is_valid_vietnamese_plate("5DZ1630") is False
        assert is_valid_vietnamese_plate("") is False

    def test_correct_plate_characters_leaves_valid_plate_unchanged(self) -> None:
        """Biển số đã hợp lệ từ đầu phải được giữ nguyên 100% (0 broken correct reads)."""
        plates = [
            "51K99214",
            "30H12345",
            "50LD04411",
            "40A12345",
            "39A12345",
            "41A12345",
        ]
        for p in plates:
            res, corrs = correct_plate_characters(p)
            assert res == p
            assert corrs == []

    def test_correct_plate_5dz1630_to_50z1630(self) -> None:
        """Quy tắc sửa vị trí 1: 5DZ1630 -> 50Z1630 (D -> 0 ở mã tỉnh)."""
        res, corrs = correct_plate_characters("5DZ1630")
        assert res == "50Z1630"
        assert len(corrs) == 1
        assert corrs[0].position == 1
        assert corrs[0].original_char == "D"
        assert corrs[0].corrected_char == "0"
        assert corrs[0].rule == "province_second_digit_fix"
        assert is_valid_vietnamese_plate(res) is True

    def test_correct_plate_series_letter_confusable(self) -> None:
        """Quy tắc sửa vị trí 2: 51599214 -> 51S99214 (5 -> S ở vị trí chữ cái sê-ri)."""
        res, corrs = correct_plate_characters("51599214")
        assert res == "51S99214"
        assert len(corrs) == 1
        assert corrs[0].position == 2
        assert corrs[0].original_char == "5"
        assert corrs[0].corrected_char == "S"
        assert corrs[0].rule == "series_letter_fix"
        assert is_valid_vietnamese_plate(res) is True

    def test_correct_plate_number_group_confusable(self) -> None:
        """Quy tắc sửa nhóm số: O/I ở vị trí số được sửa thành 0/1."""
        res, corrs = correct_plate_characters("51K9921O")
        assert res == "51K99210"
        assert len(corrs) == 1
        assert corrs[0].position == 7
        assert corrs[0].original_char == "O"
        assert corrs[0].corrected_char == "0"
        assert is_valid_vietnamese_plate(res) is True

    def test_correct_plate_protects_ld_series(self) -> None:
        """Bảo vệ sê-ri liên doanh 50LD04411 (index 3 là 'D' không bị sửa thành '0')."""
        res, corrs = correct_plate_characters("50LD04411")
        assert res == "50LD04411"
        assert corrs == []


class TestReviewPolicyEvaluation:
    """Test suite for Review Policy A2: AUTO vs NEEDS_REVIEW."""

    def test_review_policy_all_satisfied_returns_auto(self) -> None:
        """Đầy đủ 4 điều kiện -> AUTO và review_reasons rỗng."""
        status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=95.0,
            threshold=85.0,
            is_valid_format=True,
            used_detection_fallback=False,
        )
        assert status == "AUTO"
        assert reasons == []

    def test_review_policy_fractional_threshold_auto(self) -> None:
        """Hỗ trợ threshold tỷ lệ 0.85 tương đương 85.0%."""
        status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=90.0,
            threshold=0.85,
            is_valid_format=True,
            used_detection_fallback=False,
        )
        assert status == "AUTO"
        assert reasons == []

    def test_review_policy_model_disagreement(self) -> None:
        """Hai mô hình bất đồng thuận -> NEEDS_REVIEW với MODEL_DISAGREEMENT."""
        status, reasons = evaluate_review_policy(
            model_agreement=False,
            min_char_confidence=95.0,
            threshold=85.0,
            is_valid_format=True,
            used_detection_fallback=False,
        )
        assert status == "NEEDS_REVIEW"
        assert ReviewReasonCode.MODEL_DISAGREEMENT in reasons

    def test_review_policy_low_char_confidence(self) -> None:
        """Có ký tự < threshold -> NEEDS_REVIEW với LOW_CHAR_CONFIDENCE."""
        status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=75.0,
            threshold=85.0,
            is_valid_format=True,
            used_detection_fallback=False,
        )
        assert status == "NEEDS_REVIEW"
        assert ReviewReasonCode.LOW_CHAR_CONFIDENCE in reasons

    def test_review_policy_invalid_format(self) -> None:
        """Biển số sai định dạng -> NEEDS_REVIEW với INVALID_FORMAT."""
        status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=95.0,
            threshold=85.0,
            is_valid_format=False,
            used_detection_fallback=False,
        )
        assert status == "NEEDS_REVIEW"
        assert ReviewReasonCode.INVALID_FORMAT in reasons

    def test_review_policy_used_detection_fallback(self) -> None:
        """Chỉ tìm thấy qua fallback retry -> NEEDS_REVIEW với NO_DETECTION_RETRY."""
        status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=95.0,
            threshold=85.0,
            is_valid_format=True,
            used_detection_fallback=True,
        )
        assert status == "NEEDS_REVIEW"
        assert ReviewReasonCode.NO_DETECTION_RETRY in reasons

    def test_review_policy_multiple_violations(self) -> None:
        """Nhiều lỗi đồng thời -> mảng review_reasons chứa tất cả lý do."""
        status, reasons = evaluate_review_policy(
            model_agreement=False,
            min_char_confidence=60.0,
            threshold=85.0,
            is_valid_format=False,
            used_detection_fallback=True,
        )
        assert status == "NEEDS_REVIEW"
        assert len(reasons) == 4
        assert set(reasons) == {
            ReviewReasonCode.MODEL_DISAGREEMENT,
            ReviewReasonCode.LOW_CHAR_CONFIDENCE,
            ReviewReasonCode.INVALID_FORMAT,
            ReviewReasonCode.NO_DETECTION_RETRY,
        }

    def test_review_policy_unknown_plate_pattern(self) -> None:
        """Biển số có cú pháp lạ/quân sự/mã dự trữ -> UNKNOWN_PLATE_PATTERN."""
        status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=95.0,
            threshold=85.0,
            is_valid_format=True,
            used_detection_fallback=False,
            is_unknown_pattern=True,
        )
        assert status == "NEEDS_REVIEW"
        assert ReviewReasonCode.UNKNOWN_PLATE_PATTERN in reasons

    def test_review_policy_auxiliary_signals(self) -> None:
        """Các tín hiệu phụ (box confidence thấp, aspect ratio bất thường, crop mờ)."""
        status, reasons = evaluate_review_policy(
            model_agreement=True,
            min_char_confidence=95.0,
            threshold=85.0,
            is_valid_format=True,
            used_detection_fallback=False,
            detector_box_confidence=0.45,
            plate_aspect_ratio=6.5,
            crop_sharpness=12.0,
        )
        assert status == "NEEDS_REVIEW"
        assert ReviewReasonCode.LOW_DETECTION_CONFIDENCE in reasons
        assert ReviewReasonCode.IRREGULAR_ASPECT_RATIO in reasons
        assert ReviewReasonCode.LOW_IMAGE_SHARPNESS in reasons


@pytest.mark.django_db
class TestTrigramSuggestions:
    """Test suite for Trigram Similarity Suggestions (A5)."""

    def test_suggestions_finds_similar_vehicle_plates(self) -> None:
        """Tra cứu biển số gần giống trong bảng vehicle với edit distance <= 1."""
        from apps.customers.models import Customer

        customer = Customer.objects.first()
        if not customer:
            customer = Customer.objects.create(
                code="CUST-001",
                full_name="Nguyễn Văn A",
                phone="0901234567",
                identity_card_number="123456789012",
            )
        vtype, _ = VehicleType.objects.get_or_create(
            code="CAR", defaults={"name": "Ô tô"}
        )
        Vehicle.objects.create(
            customer=customer,
            code="VEH-001",
            license_plate="51K-992.14",
            license_plate_norm="51K99214",
            model_name="Sedan",
            vehicle_type=vtype,
        )
        Vehicle.objects.create(
            customer=customer,
            code="VEH-002",
            license_plate="51K-992.15",
            license_plate_norm="51K99215",
            model_name="Sedan",
            vehicle_type=vtype,
        )
        # Biển sai 1 ký tự cuối: 51K9921A
        suggs = get_plate_suggestions("51K9921A", limit=3)
        assert len(suggs) >= 1
        assert any("51K-992.14" in s or "51K-992.15" in s for s in suggs)

    def test_suggestions_never_includes_exact_query_plate(self) -> None:
        """Gợi ý không bao giờ chứa chính chuỗi truy vấn."""
        from apps.customers.models import Customer

        customer = Customer.objects.first()
        if not customer:
            customer = Customer.objects.create(
                code="CUST-002",
                full_name="Trần Thị B",
                phone="0909876543",
                identity_card_number="987654321098",
            )
        vtype, _ = VehicleType.objects.get_or_create(
            code="CAR", defaults={"name": "Ô tô"}
        )
        Vehicle.objects.create(
            customer=customer,
            code="VEH-003",
            license_plate="30H-123.45",
            license_plate_norm="30H12345",
            model_name="Sedan",
            vehicle_type=vtype,
        )
        suggs = get_plate_suggestions("30H12345", limit=3)
        assert "30H-123.45" not in suggs
        assert "30H12345" not in suggs

    def test_suggestions_empty_for_empty_input(self) -> None:
        assert get_plate_suggestions("", limit=3) == []

    def test_suggestions_orm_fallback_when_pg_trgm_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Kiểm tra nhánh fallback ORM + Levenshtein khi truy vấn pg_trgm gặp lỗi."""
        from django.db import connection

        from apps.customers.models import Customer

        customer = Customer.objects.first()
        if not customer:
            customer = Customer.objects.create(
                code="CUST-003",
                full_name="Lê Văn C",
                phone="0901122334",
                identity_card_number="112233445566",
            )
        vtype, _ = VehicleType.objects.get_or_create(
            code="CAR", defaults={"name": "Ô tô"}
        )
        Vehicle.objects.create(
            customer=customer,
            code="VEH-004",
            license_plate="51F-207.54",
            license_plate_norm="51F20754",
            model_name="Sedan",
            vehicle_type=vtype,
        )
        monkeypatch.setattr(connection, "vendor", "sqlite")
        suggs = get_plate_suggestions("51F20755", limit=3)
        assert "51F-207.54" in suggs
