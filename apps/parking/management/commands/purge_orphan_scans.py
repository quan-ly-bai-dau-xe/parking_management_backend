"""
Management command to purge unreferenced (orphan) parking scan images from MEDIA_ROOT.

Task: Round 34 P5 (L5 - Orphan Scans Cleanup Command).
Deletes only unreferenced files under MEDIA_ROOT/parking_scans that do not match
any VehicleEntryExitLog.entry_image_url or exit_image_url.
Never touches referenced files or database records.
Safely cleans up empty YYYY/MM/DD date directories.
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.parking.models import VehicleEntryExitLog


def normalize_db_url_to_rel_path(url: str | None, media_url_prefix: str) -> str | None:
    """
    Chuẩn hóa URL ảnh từ CSDL thành đường dẫn tương đối (POSIX path) so với MEDIA_ROOT.
    """
    if not url:
        return None
    url = url.strip()
    if not url:
        return None

    parsed = urlparse(url)
    path = parsed.path if parsed.path else url

    clean_prefix = "/" + media_url_prefix.strip("/") + "/"
    if path.startswith(clean_prefix):
        rel = path[len(clean_prefix) :]
    elif path.startswith("parking_scans/"):
        rel = path
    elif path.startswith("/parking_scans/"):
        rel = path.lstrip("/")
    else:
        rel = path.lstrip("/")

    return Path(rel).as_posix()


def fetch_referenced_scan_paths(chunk_size: int = 10000) -> set[str]:
    """
    Truy vấn tập hợp các relative paths của ảnh scan đang được tham chiếu trong CSDL.
    Sử dụng values_list và iterator(chunk_size) để streaming, không nạp toàn bộ model vào RAM.
    """
    media_url = settings.MEDIA_URL
    referenced: set[str] = set()

    # Quét entry_image_url
    entry_qs = (
        VehicleEntryExitLog.objects.exclude(entry_image_url__isnull=True)
        .exclude(entry_image_url="")
        .values_list("entry_image_url", flat=True)
        .iterator(chunk_size=chunk_size)
    )
    for url in entry_qs:
        rel = normalize_db_url_to_rel_path(url, media_url)
        if rel:
            referenced.add(rel)

    # Quét exit_image_url
    exit_qs = (
        VehicleEntryExitLog.objects.exclude(exit_image_url__isnull=True)
        .exclude(exit_image_url="")
        .values_list("exit_image_url", flat=True)
        .iterator(chunk_size=chunk_size)
    )
    for url in exit_qs:
        rel = normalize_db_url_to_rel_path(url, media_url)
        if rel:
            referenced.add(rel)

    return referenced


def format_bytes(bytes_count: int) -> str:
    """Chuyển đổi số bytes thành chuỗi dung lượng dễ đọc."""
    units = ["B", "KB", "MB", "GB"]
    size = float(bytes_count)
    for unit in units:
        if size < 1024.0 or unit == "GB":
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{bytes_count} B"


class Command(BaseCommand):
    help = (
        "Purges orphan scan images under MEDIA_ROOT/parking_scans that are not referenced "
        "by any VehicleEntryExitLog.entry_image_url or exit_image_url."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Chạy ở chế độ mô phỏng an toàn (mặc định: True). Sử dụng --no-dry-run để xóa thật.",
        )
        parser.add_argument(
            "--older-than-hours",
            type=float,
            default=24.0,
            help="Chỉ xét các tệp có mtime cũ hơn số giờ này (mặc định: 24.0). Ngăn xóa ảnh đang upload dở dang.",
        )
        parser.add_argument(
            "--chunk-size",
            type=int,
            default=10000,
            help="Kích thước chunk truy vấn CSDL (mặc định: 10000).",
        )

    def handle(self, *args: object, **options: object) -> None:
        dry_run = bool(options.get("dry_run", True))
        older_than_hours = float(str(options.get("older_than_hours", 24.0)))
        chunk_size = int(str(options.get("chunk_size", 10000)))
        verbosity = int(str(options.get("verbosity", 1)))

        if older_than_hours < 0:
            raise CommandError("Tham số --older-than-hours không được âm.")

        media_root = Path(settings.MEDIA_ROOT).resolve()
        scans_dir = media_root / "parking_scans"

        self.stdout.write(
            self.style.NOTICE(
                "=== BẮT ĐẦU DỌN DẸP ẢNH QUÉT MỒ CÔI (PURGE ORPHAN SCANS) ===\n"
                f"- Chế độ: {'DRY-RUN (Mô phỏng, KHÔNG xóa tệp)' if dry_run else 'THỰC THI (XÓA TỆP VĨNH VIỄN)'}\n"
                f"- Thư mục quét: {scans_dir}\n"
                f"- Ngưỡng thời gian sửa đổi (mtime): cũ hơn {older_than_hours} giờ\n"
                f"- Kích thước chunk CSDL: {chunk_size}\n"
            )
        )

        if not scans_dir.exists() or not scans_dir.is_dir():
            self.stdout.write(
                self.style.WARNING(
                    f"Thư mục '{scans_dir}' không tồn tại hoặc không phải là thư mục. Không có tệp nào cần xử lý."
                )
            )
            return

        # 1. Truy vấn các tệp đang được CSDL tham chiếu
        self.stdout.write("Đang truy vấn các tệp ảnh được tham chiếu trong CSDL...")
        start_db_query = time.perf_counter()
        referenced_paths = fetch_referenced_scan_paths(chunk_size=chunk_size)
        db_query_time = time.perf_counter() - start_db_query
        self.stdout.write(
            f"-> Đã tìm thấy {len(referenced_paths):,} đường dẫn ảnh đang được CSDL tham chiếu ({db_query_time:.2f}s)."
        )

        # 2. Quét filesystem
        now_ts = time.time()
        cutoff_ts = now_ts - (older_than_hours * 3600.0)

        total_files = 0
        referenced_files = 0
        recent_files = 0
        orphan_files: list[Path] = []
        orphan_bytes = 0

        self.stdout.write("Đang quét thư mục parking_scans...")
        for root, _, files in os.walk(scans_dir):
            for file_name in files:
                total_files += 1
                file_path = Path(root) / file_name

                try:
                    stat = file_path.stat()
                except OSError as e:
                    if verbosity >= 1:
                        self.stderr.write(f"Lỗi đọc stat tệp '{file_path}': {e}")
                    continue

                if stat.st_mtime > cutoff_ts:
                    recent_files += 1
                    continue

                try:
                    rel_path = file_path.relative_to(media_root).as_posix()
                except ValueError:
                    rel_path = file_path.as_posix()

                if rel_path in referenced_paths:
                    referenced_files += 1
                else:
                    orphan_files.append(file_path)
                    orphan_bytes += stat.st_size
                    if verbosity >= 2:
                        self.stdout.write(
                            f"[ORPHAN] Phát hiện tệp mồ côi: {rel_path} ({stat.st_size} bytes)"
                        )

        # 3. Tiến hành xóa tệp mồ côi
        deleted_count = 0
        deleted_bytes = 0
        failed_deletions = 0

        for orphan_path in orphan_files:
            if dry_run:
                if verbosity >= 2:
                    self.stdout.write(f"[DRY-RUN] Sẽ xóa: {orphan_path}")
            else:
                try:
                    size = orphan_path.stat().st_size
                    orphan_path.unlink()
                    deleted_count += 1
                    deleted_bytes += size
                    if verbosity >= 2:
                        self.stdout.write(f"[DELETED] Đã xóa: {orphan_path}")
                except OSError as e:
                    failed_deletions += 1
                    self.stderr.write(
                        self.style.ERROR(f"Không thể xóa tệp '{orphan_path}': {e}")
                    )

        # 4. Dọn dẹp các thư mục con rỗng YYYY/MM/DD
        empty_dirs_found = 0
        empty_dirs_cleaned = 0

        for root, _, _ in os.walk(scans_dir, topdown=False):
            dir_path = Path(root)
            if dir_path == scans_dir:
                continue

            try:
                if not any(os.scandir(dir_path)):
                    empty_dirs_found += 1
                    if dry_run:
                        if verbosity >= 2:
                            self.stdout.write(
                                f"[DRY-RUN] Sẽ xóa thư mục rỗng: {dir_path}"
                            )
                    else:
                        os.rmdir(dir_path)
                        empty_dirs_cleaned += 1
                        if verbosity >= 2:
                            self.stdout.write(
                                f"[CLEANED DIR] Đã xóa thư mục rỗng: {dir_path}"
                            )
            except OSError as e:
                if verbosity >= 1:
                    self.stderr.write(f"Không thể xóa thư mục rỗng '{dir_path}': {e}")

        # 5. In bảng tổng kết
        self.stdout.write(
            self.style.SUCCESS(
                f"\n=== TỔNG KẾT DỌN DẸP ẢNH QUÉT MỒ CÔI ===\n"
                f"- Tổng số tệp đã quét: {total_files:,}\n"
                f"- Tệp đang được CSDL tham chiếu (bảo lưu): {referenced_files:,}\n"
                f"- Tệp còn mới (< {older_than_hours}h, bảo lưu): {recent_files:,}\n"
                f"- Tệp mồ côi phát hiện: {len(orphan_files):,} ({format_bytes(orphan_bytes)})\n"
                f"- Tệp mồ côi đã xóa thực tế: {deleted_count:,} ({format_bytes(deleted_bytes)})\n"
                f"- Thất bại khi xóa tệp: {failed_deletions:,}\n"
                f"- Thư mục rỗng phát hiện / đã dọn dẹp: {empty_dirs_found:,} / {empty_dirs_cleaned:,}\n"
                f"- Trạng thái: {'HOÀN TẤT MÔ PHỎNG (Chạy với cờ --no-dry-run để xóa thật)' if dry_run else 'HOÀN TẤT XÓA THẬT THÀNH CÔNG'}"
            )
        )
