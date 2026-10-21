"""
Message catalog immutability and verbatim string pinning tests (MSG-4.5.1-M01..M03, PROP-4.5.1-P01..P12).
"""

import hashlib
from types import MappingProxyType

import pytest

from apps.core.messages import (
    PROPOSAL_MESSAGES,
    SRS_MESSAGES,
)


class TestVerbatimPinningM01M03:
    """Kiểm tra ghim chuỗi nguyên văn không thể sai lệch."""

    def test_m01_verbatim_text_and_hash(self):
        """MSG-4.5.1-M01: 'Không tìm thấy dữ liệu trùng khớp'."""
        expected = "Không tìm thấy dữ liệu trùng khớp"
        actual = SRS_MESSAGES["MSG-4.5.1-M01"]
        assert actual == expected
        assert len(actual) == 33
        # Đảm bảo không có trailing space hay dấu chấm cuối (OQ-46)
        assert not actual.endswith(".")
        assert actual == actual.strip()
        # Ghim SHA-256 hash của chuỗi UTF-8
        expected_hash = hashlib.sha256(expected.encode("utf-8")).hexdigest()
        actual_hash = hashlib.sha256(actual.encode("utf-8")).hexdigest()
        assert actual_hash == expected_hash

    def test_m02_verbatim_text_and_typo_preservation(self):
        """
        MSG-4.5.1-M02: 'Lỗi dữ liệu không tìm thấy đê lưu'
        Bảo toàn nguyên văn lỗi chính tả 'đê lưu' từ SRS v4.1 gốc (OQ-46).
        """
        expected = "Lỗi dữ liệu không tìm thấy đê lưu"
        actual = SRS_MESSAGES["MSG-4.5.1-M02"]
        assert actual == expected
        assert "đê lưu" in actual
        assert not actual.endswith(".")
        assert actual == actual.strip()
        expected_hash = hashlib.sha256(expected.encode("utf-8")).hexdigest()
        actual_hash = hashlib.sha256(actual.encode("utf-8")).hexdigest()
        assert actual_hash == expected_hash

    def test_m03_verbatim_lowercase_fix(self):
        """
        MSG-4.5.1-M03: 'lỗi kết nối'
        Chữ 'l' phải viết thường theo SRS v4.1 (Mục 4.5.1, ACT-4.5.1-A02) và 00-srs-catalog.md dòng 326.
        Khắc phục hoàn toàn lỗi lặp lại văn bản của M02 ban đầu.
        """
        expected = "lỗi kết nối"
        actual = SRS_MESSAGES["MSG-4.5.1-M03"]
        assert actual == expected
        assert actual[0] == "l", "Chữ đầu tiên phải là chữ thường 'l'"
        assert actual != SRS_MESSAGES["MSG-4.5.1-M02"], "M03 không được trùng với M02"
        assert not actual.endswith(".")
        assert actual == actual.strip()
        expected_hash = hashlib.sha256(expected.encode("utf-8")).hexdigest()
        actual_hash = hashlib.sha256(actual.encode("utf-8")).hexdigest()
        assert actual_hash == expected_hash

    def test_proposals_p01_to_p12_verbatim_period_termination(self):
        """
        Toàn bộ PROP-4.5.1-P01 đến PROP-4.5.1-P12 bắt buộc kết thúc bằng dấu chấm (.) theo OQ-46.
        """
        for i in range(1, 13):
            code = f"PROP-4.5.1-P{i:02d}"
            assert code in PROPOSAL_MESSAGES, (
                f"{code} chưa được đăng ký trong PROPOSAL_MESSAGES"
            )
            msg = PROPOSAL_MESSAGES[code]
            assert msg.endswith("."), f"{code}: '{msg}' phải kết thúc bằng dấu chấm (.)"
            assert msg == msg.strip(), f"{code} có khoảng trắng thừa"


class TestCatalogImmutabilityChallenge:
    """Thử thách tính bất biến của Message Catalog đối với các hành vi sửa đổi runtime."""

    def test_catalog_runtime_mutation_vulnerability_demonstration(self):
        """
        Thực nghiệm kiểm chứng (Empirical Finding):
        SRS_MESSAGES và ALL_MESSAGES hiện tại là kiểu dict Python thông thường,
        do đó CÓ THỂ bị gán đè tại runtime nếu không có cơ chế bảo vệ.
        """
        # Lưu lại giá trị gốc
        original_m03 = SRS_MESSAGES["MSG-4.5.1-M03"]
        try:
            # Mô phỏng một đoạn code bất cẩn sửa đổi catalog
            SRS_MESSAGES["MSG-4.5.1-M03"] = "lỗi kết nối bị ghi đè"
            assert SRS_MESSAGES["MSG-4.5.1-M03"] == "lỗi kết nối bị ghi đè"
        finally:
            # Khôi phục nguyên trạng để không ảnh hưởng test suite
            SRS_MESSAGES["MSG-4.5.1-M03"] = original_m03

        assert SRS_MESSAGES["MSG-4.5.1-M03"] == "lỗi kết nối"

    def test_catalog_protection_via_mapping_proxy_recommendation(self):
        """
        Kiểm chứng giải pháp kiến trúc đề xuất (Defense-in-depth):
        Sử dụng MappingProxyType để ngăn chặn hoàn toàn việc mutation tại runtime.
        """
        immutable_catalog = MappingProxyType(SRS_MESSAGES)
        with pytest.raises(TypeError):
            immutable_catalog["MSG-4.5.1-M03"] = "cố tình thay đổi"
