"""
Unit tests for OCR service & PlateRecognizer interface.
Verifies:
- License plate normalization parity with PostgreSQL fn_normalize_license_plate.
- DummyPlateRecognizer custom preset candidates & bounding box.
- get_plate_recognizer factory behavior based on PARKING_OCR_ENGINE setting.
- Candidate sorting by confidence.
"""

import pytest
from django.conf import settings
from PIL import Image

from apps.parking.services.ocr import (
    BoundingBox,
    DummyPlateRecognizer,
    PlateCandidate,
    PlateRecognizer,
    get_plate_recognizer,
    set_global_recognizer,
)


def test_normalize_plate_parity():
    """Kiểm tra logic chuẩn hóa biển số xe: loại bỏ ký tự phân cách, hoa thường, dấu."""
    assert PlateRecognizer.normalize_plate("51K-992.14") == "51K99214"
    assert PlateRecognizer.normalize_plate(" 43A - 123.45 ") == "43A12345"
    assert PlateRecognizer.normalize_plate("29b_99999") == "29B99999"
    assert PlateRecognizer.normalize_plate("") == ""
    assert PlateRecognizer.normalize_plate(None) == ""


def test_dummy_plate_recognizer_default():
    """DummyPlateRecognizer mặc định trả về biển số 51K-992.14 với confidence 98.5%."""
    recognizer = DummyPlateRecognizer()
    img = Image.new("RGB", (100, 100))
    result = recognizer.recognize(img)

    assert result.engine_name == "dummy"
    assert len(result.candidates) == 1
    assert result.best_candidate is not None
    assert result.best_candidate.plate_text == "51K-992.14"
    assert result.best_candidate.plate_normalized == "51K99214"
    assert result.best_candidate.confidence == 95.5
    assert result.best_candidate.bounding_box == BoundingBox(
        x1=50, y1=50, x2=350, y2=150
    )


def test_dummy_plate_recognizer_custom_candidates():
    """DummyPlateRecognizer có thể gán danh sách candidates tùy chỉnh cho test."""
    recognizer = DummyPlateRecognizer()
    cand1 = PlateCandidate("43A-111.11", "43A11111", 99.0)
    cand2 = PlateCandidate("43A-111.12", "43A11112", 85.0)
    recognizer.set_candidates([cand1, cand2])

    result = recognizer.recognize(b"fake-bytes")
    assert len(result.candidates) == 2
    assert result.best_candidate == cand1


def test_dummy_plate_recognizer_empty_candidates():
    """DummyPlateRecognizer trả về rỗng khi không có biển số nào được tìm thấy."""
    recognizer = DummyPlateRecognizer(default_plate="")
    result = recognizer.recognize(b"fake-bytes")
    assert len(result.candidates) == 0
    assert result.best_candidate is None


def test_get_plate_recognizer_factory(monkeypatch):
    """get_plate_recognizer trả về singleton theo cấu hình settings."""
    set_global_recognizer(None)

    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.test")
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    rec1 = get_plate_recognizer()
    assert isinstance(rec1, DummyPlateRecognizer)

    rec2 = get_plate_recognizer()
    assert rec1 is rec2

    # Reset
    set_global_recognizer(None)


def test_get_plate_recognizer_unsupported_engine(monkeypatch):
    """get_plate_recognizer ném ValueError khi engine cấu hình không hợp lệ."""
    set_global_recognizer(None)
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "unknown_engine")

    with pytest.raises(ValueError) as exc_info:
        get_plate_recognizer()

    assert "Unsupported PARKING_OCR_ENGINE" in str(exc_info.value)
    set_global_recognizer(None)


def test_dummy_engine_rejected_outside_test_settings(monkeypatch):
    """F7: PARKING_OCR_ENGINE='dummy' must raise ImproperlyConfigured outside config.settings.test."""
    from django.core.exceptions import ImproperlyConfigured

    set_global_recognizer(None)
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")

    for forbidden_module in [
        "config.settings.production",
        "config.settings.local",
        "",
    ]:
        monkeypatch.setenv("DJANGO_SETTINGS_MODULE", forbidden_module)
        with pytest.raises(ImproperlyConfigured) as exc_info:
            get_plate_recognizer()
        assert "only permitted" in str(exc_info.value)
        set_global_recognizer(None)


def test_dummy_engine_allowed_in_test_settings(monkeypatch):
    """F7: PARKING_OCR_ENGINE='dummy' is permitted in config.settings.test."""
    set_global_recognizer(None)
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.test")
    recognizer = get_plate_recognizer()
    assert isinstance(recognizer, DummyPlateRecognizer)
    set_global_recognizer(None)
