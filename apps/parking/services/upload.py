"""
Image upload security service for Parking Management Backend.
Validates file size, content magic bytes, Pillow integrity, decompression bomb caps,
strips EXIF/GPS metadata, and stores with randomized UUID names under MEDIA_ROOT.
"""

import io
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from django.utils import timezone
from PIL import Image, ImageOps

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import ALL_MESSAGES

# Prevent decompression bomb DOS attacks
Image.MAX_IMAGE_PIXELS = 16_000_000
MAX_IMAGE_DIMENSION = 4096


TARGET_MAX_SIDE = 1280
JPEG_SAVE_QUALITY = 85


class ProcessedImage:
    """Kết quả xác thực và tiền xử lý hình ảnh an toàn trong bộ nhớ (chưa lưu đĩa)."""

    def __init__(
        self,
        pil_image: Image.Image,
        width: int,
        height: int,
        format: str,
        ext: str,
        scale_factor: float = 1.0,
        original_size: tuple[int, int] | None = None,
        image_bytes: bytes | None = None,
    ) -> None:
        self.pil_image = pil_image
        self.width = width
        self.height = height
        self.format = format
        self.ext = ext
        self.scale_factor = scale_factor
        self.original_size = original_size or (width, height)
        self._image_bytes = image_bytes

    @property
    def image_bytes(self) -> bytes:
        if self._image_bytes is None:
            clean_buffer = io.BytesIO()
            if self.format == "JPEG":
                self.pil_image.save(
                    clean_buffer, format="JPEG", quality=JPEG_SAVE_QUALITY
                )
            elif self.format == "PNG":
                self.pil_image.save(clean_buffer, format="PNG")
            else:  # WEBP
                self.pil_image.save(clean_buffer, format="WEBP")
            self._image_bytes = clean_buffer.getvalue()
        return self._image_bytes


@dataclass(frozen=True)
class UploadResult:
    """Kết quả xác thực và lưu trữ hình ảnh tải lên an toàn."""

    file_path: Path
    relative_url: str
    image_bytes: bytes
    width: int
    height: int
    format: str


def _check_magic_bytes(content: bytes) -> str | None:
    """
    Xác định định dạng ảnh dựa trên magic bytes của nội dung.
    Hỗ trợ: JPEG, PNG, WEBP.
    """
    if len(content) < 12:
        return None
    if content.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "WEBP"
    return None


def process_uploaded_image(file_obj: Any) -> ProcessedImage:
    """
    Xác thực bảo mật và tiền xử lý hình ảnh biển số xe (Single-Pass, chưa lưu đĩa):
    1. Kiểm tra sự tồn tại của tệp (PROP-4.5.1-P02).
    2. Kiểm tra sớm dung lượng qua declared file.size nếu có (PROP-4.5.1-P03).
    3. Đọc từ stream có chặn tối đa max_bytes + 1 ngăn ngừa Buffer DOS (PROP-4.5.1-P03).
    4. Xác thực định dạng qua magic bytes (PROP-4.5.1-P04).
    5. Single-pass Pillow open và draft mode giải mã nhanh (PROP-4.5.1-P05).
    6. Tự động xoay ảnh đứng thẳng theo EXIF Orientation (ImageOps.exif_transpose).
    7. Downscale cạnh lớn nhất <= 1280px bằng BILINEAR resampling (tối ưu OCR).
    8. Giữ ảnh in-memory (PIL.Image) truyền trực tiếp cho OCR mà không encode trung gian.
    """
    if file_obj is None:
        raise BusinessAPIException(
            code="PROP-4.5.1-P02",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P02", "Tệp hình ảnh biển số xe không được để trống."
            ),
            status_code=400,
        )

    max_mb = settings.MAX_IMAGE_SIZE_MB
    max_bytes = max_mb * 1024 * 1024

    # (c.1) Kiểm tra kích thước sớm qua declared size nếu có
    declared_size = getattr(file_obj, "size", None)
    if (
        declared_size is not None
        and isinstance(declared_size, int)
        and declared_size > max_bytes
    ):
        raise BusinessAPIException(
            code="PROP-4.5.1-P03",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P03",
                "Kích thước tệp hình ảnh vượt quá giới hạn cho phép.",
            ),
            status_code=400,
        )

    # (c.2) Đọc nhị phân từ stream có chặn tối đa max_bytes + 1
    if hasattr(file_obj, "read"):
        raw_bytes = file_obj.read(max_bytes + 1)
    elif isinstance(file_obj, (bytes, bytearray)):
        raw_bytes = bytes(file_obj)
    else:
        raise BusinessAPIException(
            code="PROP-4.5.1-P02",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P02", "Tệp hình ảnh biển số xe không được để trống."
            ),
            status_code=400,
        )

    if not raw_bytes or len(raw_bytes) == 0:
        raise BusinessAPIException(
            code="PROP-4.5.1-P02",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P02", "Tệp hình ảnh biển số xe không được để trống."
            ),
            status_code=400,
        )

    if len(raw_bytes) > max_bytes:
        raise BusinessAPIException(
            code="PROP-4.5.1-P03",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P03",
                "Kích thước tệp hình ảnh vượt quá giới hạn cho phép.",
            ),
            status_code=400,
        )

    # Xác thực magic bytes
    detected_format = _check_magic_bytes(raw_bytes)
    if not detected_format:
        raise BusinessAPIException(
            code="PROP-4.5.1-P04",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P04", "Định dạng tệp hình ảnh không được hỗ trợ."
            ),
            status_code=400,
        )

    # Single-pass Pillow open và giải mã an toàn
    try:
        img: Image.Image = Image.open(io.BytesIO(raw_bytes))
        orig_w, orig_h = img.size
        if (
            orig_w <= 0
            or orig_h <= 0
            or orig_w > MAX_IMAGE_DIMENSION
            or orig_h > MAX_IMAGE_DIMENSION
        ):
            raise BusinessAPIException(
                code="PROP-4.5.1-P05",
                message=ALL_MESSAGES.get(
                    "PROP-4.5.1-P05",
                    "Tệp hình ảnh bị hỏng hoặc không thể xử lý an toàn.",
                ),
                status_code=400,
            )

        # (b) Kiểm tra thẻ EXIF Orientation (0x0112) trước khi giải mã
        exif_data = img.getexif()
        exif_orientation = exif_data.get(0x0112)
        cur_w, cur_h = (
            (orig_h, orig_w) if exif_orientation in (5, 6, 7, 8) else (orig_w, orig_h)
        )
        if (
            cur_w <= 0
            or cur_h <= 0
            or cur_w > MAX_IMAGE_DIMENSION
            or cur_h > MAX_IMAGE_DIMENSION
        ):
            raise BusinessAPIException(
                code="PROP-4.5.1-P05",
                message=ALL_MESSAGES.get(
                    "PROP-4.5.1-P05",
                    "Tệp hình ảnh bị hỏng hoặc không thể xử lý an toàn.",
                ),
                status_code=400,
            )

        max_dim = max(cur_w, cur_h)
        scale = 1.0
        new_w, new_h = cur_w, cur_h
        if max_dim > TARGET_MAX_SIDE:
            scale = TARGET_MAX_SIDE / float(max_dim)
            new_w = max(1, int(round(cur_w * scale)))
            new_h = max(1, int(round(cur_h * scale)))

        if exif_orientation is not None and exif_orientation != 1:
            raw_draft_size = (
                (new_h, new_w) if exif_orientation in (5, 6, 7, 8) else (new_w, new_h)
            )
        else:
            raw_draft_size = (new_w, new_h)

        # Call draft before exif_transpose so libjpeg decodes via DCT subsampling (2000x1500 for 12MP)
        # instead of uncompressed 36MB raster, preventing memory spikes and eliminating upscaling.
        if detected_format == "JPEG" and max_dim > TARGET_MAX_SIDE:
            img.draft("RGB", raw_draft_size)

        if exif_orientation is not None and exif_orientation != 1:
            transposed_img = ImageOps.exif_transpose(img)
            if transposed_img is not None:
                img = transposed_img

        img.load()

        if max_dim > TARGET_MAX_SIDE and img.size != (new_w, new_h):
            img = img.resize((new_w, new_h), Image.Resampling.BILINEAR)

        if img.mode != "RGB":
            img = img.convert("RGB")

        final_w, final_h = img.size
        ext = (
            ".jpg"
            if detected_format == "JPEG"
            else (".png" if detected_format == "PNG" else ".webp")
        )

        return ProcessedImage(
            pil_image=img,
            width=final_w,
            height=final_h,
            format=detected_format,
            ext=ext,
            scale_factor=scale,
            original_size=(orig_w, orig_h),
        )
    except BusinessAPIException:
        raise
    except Exception as exc:
        raise BusinessAPIException(
            code="PROP-4.5.1-P05",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P05",
                "Tệp hình ảnh bị hỏng hoặc không thể xử lý an toàn.",
            ),
            status_code=400,
        ) from exc


def save_processed_image(processed: ProcessedImage) -> tuple[Path, str]:
    """
    Lưu trữ tệp hình ảnh đã qua xử lý an toàn vào MEDIA_ROOT với UUID ngẫu nhiên.
    Trả về: (đường dẫn tệp cục bộ Path, đường dẫn URL tương đối str).
    """
    now = timezone.now()
    media_root = Path(settings.MEDIA_ROOT)
    sub_dir = Path("parking_scans") / now.strftime("%Y/%m/%d")
    target_dir = media_root / sub_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    random_filename = f"{uuid.uuid4().hex}{processed.ext}"
    dest_path = target_dir / random_filename
    dest_path.write_bytes(processed.image_bytes)

    media_url = settings.MEDIA_URL.rstrip("/")
    rel_path_str = (sub_dir / random_filename).as_posix()
    relative_url = f"{media_url}/{rel_path_str}"

    return dest_path, relative_url


def validate_and_save_image(file_obj: Any) -> UploadResult:
    """
    Hàm tiện ích tương thích ngược: vừa xác thực tiền xử lý, vừa lưu tệp đĩa.
    """
    processed = process_uploaded_image(file_obj)
    dest_path, relative_url = save_processed_image(processed)

    return UploadResult(
        file_path=dest_path,
        relative_url=relative_url,
        image_bytes=processed.image_bytes,
        width=processed.width,
        height=processed.height,
        format=processed.format,
    )


def validate_parking_image_path(url: str | None) -> str | None:
    """
    Xác thực đường dẫn ảnh quét phương tiện (entry_image_url / exit_image_url):
    1. Chấp nhận None (hoặc omitted).
    2. Từ chối chuỗi rỗng hoặc vượt quá max_length 150 ký tự.
    3. Kiểm tra định dạng URL tương đối nghiêm ngặt:
       MEDIA_URL + parking_scans/YYYY/MM/DD/<32 lowercase hex>.(jpg|png|webp)
    4. Chống Path Traversal và kiểm tra tệp thực tế tồn tại trong MEDIA_ROOT.
    5. Trả về HTTP 400 và PROP-4.5.1-P13 nếu không hợp lệ.
    """
    if url is None:
        return None
    url = str(url).strip()
    if not url:
        raise BusinessAPIException(
            code="PROP-4.5.1-P13",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P13",
                "Đường dẫn hình ảnh không hợp lệ hoặc tệp không tồn tại.",
            ),
            status_code=400,
        )

    if len(url) > 150:
        raise BusinessAPIException(
            code="PROP-4.5.1-P13",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P13",
                "Đường dẫn hình ảnh không hợp lệ hoặc tệp không tồn tại.",
            ),
            status_code=400,
        )

    media_url = settings.MEDIA_URL.rstrip("/")
    escaped_prefix = re.escape(media_url)
    pattern = rf"^{escaped_prefix}/parking_scans/\d{{4}}/(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01])/[0-9a-f]{{32}}\.(?:jpg|png|webp)$"
    if not re.match(pattern, url):
        raise BusinessAPIException(
            code="PROP-4.5.1-P13",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P13",
                "Đường dẫn hình ảnh không hợp lệ hoặc tệp không tồn tại.",
            ),
            status_code=400,
        )

    media_root = Path(settings.MEDIA_ROOT).resolve()
    rel_path_str = url[len(media_url) :].lstrip("/")
    target_file = (media_root / rel_path_str).resolve()

    if not target_file.is_relative_to(media_root) or not target_file.is_file():
        raise BusinessAPIException(
            code="PROP-4.5.1-P13",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P13",
                "Đường dẫn hình ảnh không hợp lệ hoặc tệp không tồn tại.",
            ),
            status_code=400,
        )

    return url
