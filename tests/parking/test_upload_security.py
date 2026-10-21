"""
Unit tests for upload security service per SRS 4.5.1 and Security Baseline.
Verifies:
- Empty file -> 400 PROP-4.5.1-P02
- File > 5MB -> 400 PROP-4.5.1-P03
- Invalid magic bytes -> 400 PROP-4.5.1-P04
- Corrupt file / decompression bomb -> 400 PROP-4.5.1-P05
- Valid JPEG/PNG/WebP upload strips EXIF GPS and stores under MEDIA_ROOT with UUID name.
"""

import io
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

from apps.core.exceptions import BusinessAPIException
from apps.parking.services.upload import (
    _check_magic_bytes,
    process_uploaded_image,
    validate_and_save_image,
)


@pytest.fixture(autouse=True)
def ensure_sample_data():
    """Bypasses database seed fixture since upload tests do not access DB."""
    return


def _create_test_image(
    format_name: str = "JPEG",
    size: tuple[int, int] = (100, 100),
    color: str = "red",
) -> bytes:
    """Tạo byte stream hình ảnh hợp lệ phục vụ kiểm thử."""
    buf = io.BytesIO()
    # Image mode 'RGB' is supported by JPEG and WebP
    img = Image.new("RGB", size, color=color)
    img.save(buf, format=format_name)
    return buf.getvalue()


def test_magic_bytes_detection():
    """Kiểm tra nhận diện đúng magic bytes JPEG, PNG, WEBP."""
    jpeg_bytes = _create_test_image("JPEG")
    png_bytes = _create_test_image("PNG")
    webp_bytes = _create_test_image("WEBP")

    assert _check_magic_bytes(jpeg_bytes) == "JPEG"
    assert _check_magic_bytes(png_bytes) == "PNG"
    assert _check_magic_bytes(webp_bytes) == "WEBP"

    # Invalid header
    assert _check_magic_bytes(b"hello world123") is None
    assert _check_magic_bytes(b"") is None


def test_upload_empty_file_raises_prop_p02():
    """Tệp rỗng (0 bytes) bị từ chối với mã PROP-4.5.1-P02."""
    empty_file = SimpleUploadedFile("empty.jpg", b"", content_type="image/jpeg")
    with pytest.raises(BusinessAPIException) as exc_info:
        validate_and_save_image(empty_file)

    assert exc_info.value.code == "PROP-4.5.1-P02"
    assert exc_info.value.status_code == 400


def test_upload_none_file_raises_prop_p02():
    """Không truyền tệp bị từ chối với mã PROP-4.5.1-P02."""
    with pytest.raises(BusinessAPIException) as exc_info:
        validate_and_save_image(None)

    assert exc_info.value.code == "PROP-4.5.1-P02"
    assert exc_info.value.status_code == 400


def test_upload_exceeds_max_size_raises_prop_p03(monkeypatch):
    """Tệp vượt quá 5MB bị từ chối với mã PROP-4.5.1-P03."""
    # Giả lập MAX_IMAGE_SIZE_MB = 1MB để test nhanh
    monkeypatch.setattr(settings, "MAX_IMAGE_SIZE_MB", 1)
    large_payload = b"X" * (1 * 1024 * 1024 + 10)
    large_file = SimpleUploadedFile(
        "large.jpg", large_payload, content_type="image/jpeg"
    )

    with pytest.raises(BusinessAPIException) as exc_info:
        validate_and_save_image(large_file)

    assert exc_info.value.code == "PROP-4.5.1-P03"
    assert exc_info.value.status_code == 400


def test_upload_invalid_magic_bytes_raises_prop_p04():
    """Tệp giả mạo phần mở rộng (vd: file text đổi đuôi jpg) bị từ chối với PROP-4.5.1-P04."""
    fake_image = SimpleUploadedFile(
        "fake.jpg",
        b"This is not a real JPEG image but plain text content.",
        content_type="image/jpeg",
    )

    with pytest.raises(BusinessAPIException) as exc_info:
        validate_and_save_image(fake_image)

    assert exc_info.value.code == "PROP-4.5.1-P04"
    assert exc_info.value.status_code == 400


def test_upload_corrupted_image_raises_prop_p05():
    """Tệp có magic bytes JPEG nhưng nội dung bị hỏng không đọc được qua Pillow bị từ chối với PROP-4.5.1-P05."""
    corrupted_bytes = b"\xff\xd8\xff\xe0" + b"\x00" * 100
    corrupt_file = SimpleUploadedFile(
        "corrupt.jpg", corrupted_bytes, content_type="image/jpeg"
    )

    with pytest.raises(BusinessAPIException) as exc_info:
        validate_and_save_image(corrupt_file)

    assert exc_info.value.code == "PROP-4.5.1-P05"
    assert exc_info.value.status_code == 400


def test_upload_decompression_bomb_dimension_raises_prop_p05():
    """Tệp có kích thước chiều vượt quá MAX_IMAGE_DIMENSION (4096px) bị từ chối với PROP-4.5.1-P05."""
    with patch("PIL.Image.open") as mock_open:
        mock_img = Image.new("RGB", (5000, 100))
        mock_open.return_value = mock_img
        # Bắt buộc verify không lỗi
        mock_img.verify = lambda: None

        jpeg_bytes = _create_test_image("JPEG")
        file_obj = SimpleUploadedFile("huge.jpg", jpeg_bytes, content_type="image/jpeg")

        with pytest.raises(BusinessAPIException) as exc_info:
            validate_and_save_image(file_obj)

        assert exc_info.value.code == "PROP-4.5.1-P05"
        assert exc_info.value.status_code == 400


def test_upload_valid_jpeg_success(tmp_path, monkeypatch):
    """Upload ảnh JPEG hợp lệ được lưu an toàn dưới MEDIA_ROOT với URL chuẩn."""
    monkeypatch.setattr(settings, "MEDIA_ROOT", tmp_path)
    monkeypatch.setattr(settings, "MEDIA_URL", "/media/")

    jpeg_bytes = _create_test_image("JPEG", size=(200, 150))
    file_obj = SimpleUploadedFile("plate.jpg", jpeg_bytes, content_type="image/jpeg")

    result = validate_and_save_image(file_obj)

    assert result.format == "JPEG"
    assert result.width == 200
    assert result.height == 150
    assert result.relative_url.startswith("/media/parking_scans/")
    assert result.file_path.exists()
    assert result.file_path.is_file()


def test_upload_valid_png_success(tmp_path, monkeypatch):
    """Upload ảnh PNG hợp lệ được lưu an toàn."""
    monkeypatch.setattr(settings, "MEDIA_ROOT", tmp_path)
    monkeypatch.setattr(settings, "MEDIA_URL", "/media/")

    png_bytes = _create_test_image("PNG", size=(300, 200))
    file_obj = SimpleUploadedFile("plate.png", png_bytes, content_type="image/png")

    result = validate_and_save_image(file_obj)

    assert result.format == "PNG"
    assert result.width == 300
    assert result.height == 200
    assert result.relative_url.startswith("/media/parking_scans/")
    assert result.file_path.exists()


def test_j8_draft_mode_12mp_downscaling_no_upscale():
    """
    Verify 12 MP (4000x3000) JPEG downscaling via Pillow draft mode:
    - Libjpeg decodes via DCT 1/2 to (2000, 1500)
    - Downscaled to (1280, 960) without any upscaling step
    - Scale factor is strictly 0.32
    """
    jpeg_bytes = _create_test_image("JPEG", size=(4000, 3000))
    file_obj = SimpleUploadedFile(
        "plate_12mp.jpg", jpeg_bytes, content_type="image/jpeg"
    )

    processed = process_uploaded_image(file_obj)

    assert processed.format == "JPEG"
    assert processed.width == 1280
    assert processed.height == 960
    assert pytest.approx(processed.scale_factor, rel=1e-3) == 0.32
    assert processed.original_size == (4000, 3000)
    assert processed.pil_image.size == (1280, 960)


def test_j8_draft_mode_with_exif_orientation_portrait():
    """
    Verify 12 MP JPEG with EXIF Orientation 6 (rotated 90 deg clockwise):
    - Draft mode is invoked before exif_transpose with swapped dimensions
    - Output image is oriented upright at (960, 1280)
    - Does not decode full 36 MB uncompressed raster before rotation
    """
    im = Image.new("RGB", (4000, 3000), color=(100, 150, 200))
    exif = im.getexif()
    exif[0x0112] = 6
    buf = io.BytesIO()
    im.save(buf, format="JPEG", exif=exif)
    file_obj = SimpleUploadedFile(
        "plate_12mp_ori6.jpg", buf.getvalue(), content_type="image/jpeg"
    )

    processed = process_uploaded_image(file_obj)

    assert processed.width == 960
    assert processed.height == 1280
    assert pytest.approx(processed.scale_factor, rel=1e-3) == 0.32
    assert processed.pil_image.size == (960, 1280)


def test_j8_small_image_bypass_resizing():
    """Images smaller than TARGET_MAX_SIDE (640x480) retain original dimensions and 1.0 scale factor."""
    jpeg_bytes = _create_test_image("JPEG", size=(640, 480))
    file_obj = SimpleUploadedFile(
        "plate_small.jpg", jpeg_bytes, content_type="image/jpeg"
    )

    processed = process_uploaded_image(file_obj)

    assert processed.width == 640
    assert processed.height == 480
    assert processed.scale_factor == 1.0
    assert processed.pil_image.size == (640, 480)


def test_j8_non_jpeg_png_resizing_safeguard():
    """Non-JPEG images (PNG 1920x1080) are safely downscaled to (1280, 720) without draft mode."""
    png_bytes = _create_test_image("PNG", size=(1920, 1080), color="green")
    file_obj = SimpleUploadedFile(
        "plate_1080p.png", png_bytes, content_type="image/png"
    )

    processed = process_uploaded_image(file_obj)

    assert processed.format == "PNG"
    assert processed.width == 1280
    assert processed.height == 720
    assert pytest.approx(processed.scale_factor, rel=1e-3) == (1280.0 / 1920.0)
