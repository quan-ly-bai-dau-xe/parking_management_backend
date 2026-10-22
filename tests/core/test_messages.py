"""
Tests for Centralized Message Catalog and Verbatim SRS Pinning.
Pins MSG-4.5.1-M01, MSG-4.5.1-M02, MSG-4.5.1-M03 and verifies PROP-4.5.1-P01..P12 registration.
"""

import pytest

from apps.core.messages import (
    ALL_MESSAGES,
    PROPOSAL_MESSAGES,
    SRS_MESSAGES,
    get_message,
    get_prop_message,
    get_srs_message,
)

pytestmark = pytest.mark.django_db


def test_verbatim_srs_messages_pinning_task8():
    """
    Ghim chặt (pin) nguyên văn các thông điệp SRS 4.5.1 theo Quan ly bai dau xe oto_SRS_v4.1.docx:
    - MSG-4.5.1-M01: 'Không tìm thấy dữ liệu trùng khớp'
    - MSG-4.5.1-M02: 'Lỗi dữ liệu không tìm thấy đê lưu'
    - MSG-4.5.1-M03: 'lỗi kết nối' (sửa lỗi copy lặp lại M02)
    """
    assert SRS_MESSAGES["MSG-4.5.1-M01"] == "Không tìm thấy dữ liệu trùng khớp"
    assert SRS_MESSAGES["MSG-4.5.1-M02"] == "Lỗi dữ liệu không tìm thấy đê lưu"
    assert SRS_MESSAGES["MSG-4.5.1-M03"] == "lỗi kết nối"

    # Xác nhận qua hàm helper get_srs_message và get_message
    assert get_srs_message("MSG-4.5.1-M01") == "Không tìm thấy dữ liệu trùng khớp"
    assert get_srs_message("MSG-4.5.1-M02") == "Lỗi dữ liệu không tìm thấy đê lưu"
    assert get_srs_message("MSG-4.5.1-M03") == "lỗi kết nối"

    assert get_message("MSG-4.5.1-M01") == "Không tìm thấy dữ liệu trùng khớp"
    assert get_message("MSG-4.5.1-M02") == "Lỗi dữ liệu không tìm thấy đê lưu"
    assert get_message("MSG-4.5.1-M03") == "lỗi kết nối"


def test_registration_of_task8_proposed_messages():
    """
    Kiểm tra đăng ký đầy đủ các mã lỗi đề xuất PROP-4.5.1-P01 đến PROP-4.5.1-P12 trong catalog.
    """
    expected_proposals = {
        "PROP-4.5.1-P01": "Định dạng biển số xe không hợp lệ.",
        "PROP-4.5.1-P02": "Tệp hình ảnh biển số xe không được để trống.",
        "PROP-4.5.1-P03": "Kích thước tệp hình ảnh vượt quá giới hạn cho phép.",
        "PROP-4.5.1-P04": "Định dạng tệp hình ảnh không được hỗ trợ.",
        "PROP-4.5.1-P05": "Tệp hình ảnh bị hỏng hoặc không thể xử lý an toàn.",
        "PROP-4.5.1-P06": "Không nhận diện được biển số xe từ hình ảnh đã cung cấp.",
        "PROP-4.5.1-P07": "Biển số xe đã có phiên đỗ xe đang mở chưa hoàn thành.",
        "PROP-4.5.1-P08": "Biển số xe nằm trong danh sách đen, không được phép vào bãi.",
        "PROP-4.5.1-P09": "Yêu cầu chọn phương thức thanh toán hợp lệ khi cước phí đỗ xe lớn hơn 0.",
        "PROP-4.5.1-P10": "Phiên đỗ xe này đã được kết thúc trước đó.",
        "PROP-4.5.1-P11": "Yêu cầu cung cấp chính xác một trong hai tiêu chí: mã phiên đỗ xe hoặc biển số xe.",
        "PROP-4.5.1-P12": "Cổng ra không hợp lệ hoặc không phải cổng có hướng ra (OUT).",
        "PROP-4.5.1-P13": "Đường dẫn hình ảnh không hợp lệ hoặc tệp không tồn tại.",
        "PROP-4.5.1-P14": "Nhân viên không có quyền ghi đè danh sách đen.",
    }

    for code, text in expected_proposals.items():
        assert code in PROPOSAL_MESSAGES
        assert PROPOSAL_MESSAGES[code] == text
        assert get_prop_message(code) == text
        assert get_message(code) == text


def test_all_messages_integrity_and_uniqueness():
    """Kiểm tra ALL_MESSAGES chứa hợp nhất của SRS_MESSAGES và PROPOSAL_MESSAGES."""
    assert len(ALL_MESSAGES) == len(SRS_MESSAGES) + len(PROPOSAL_MESSAGES)
    for code in SRS_MESSAGES:
        assert code in ALL_MESSAGES
    for code in PROPOSAL_MESSAGES:
        assert code in ALL_MESSAGES


def test_dockerignore_excludes_secrets_and_preserves_example():
    """Verify .dockerignore excludes .env and .env.* while preserving .env.example (Defect F1)."""
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent
    dockerignore_path = repo_root / ".dockerignore"
    assert dockerignore_path.exists(), ".dockerignore must exist in repository root"

    raw_lines = [line.strip() for line in dockerignore_path.read_text().splitlines()]
    rules = [line for line in raw_lines if line and not line.startswith("#")]

    # Must explicitly exclude .env and .env.*
    assert ".env" in rules, ".dockerignore must explicitly exclude .env"
    assert ".env.*" in rules, ".dockerignore must explicitly exclude .env.*"

    # Must preserve .env.example with ! negation pattern
    assert "!.env.example" in rules, (
        ".dockerignore must preserve .env.example via !.env.example"
    )

    # Ordering: !.env.example must come after .env.*
    assert rules.index("!.env.example") > rules.index(".env.*"), (
        "!.env.example negation rule must follow .env.* rule"
    )

    # Must exclude metadata, media, and test caches
    assert any(r in rules for r in [".agents", ".agents/"]), (
        ".dockerignore must exclude .agents"
    )
    assert any(r in rules for r in ["media", "media/", "media/*"]), (
        ".dockerignore must exclude media"
    )
    assert any(r in rules for r in [".pytest_cache", ".pytest_cache/"]), (
        ".dockerignore must exclude pytest cache"
    )
    assert any(r in rules for r in [".mypy_cache", ".mypy_cache/"]), (
        ".dockerignore must exclude mypy cache"
    )
    assert any(r in rules for r in [".ruff_cache", ".ruff_cache/"]), (
        ".dockerignore must exclude ruff cache"
    )
