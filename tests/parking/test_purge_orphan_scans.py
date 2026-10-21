"""
Unit tests for purge_orphan_scans management command.
Verifies:
1. test_dry_run_preserves_orphan_files: dry-run mode detects orphans without deleting.
2. test_no_dry_run_deletes_only_orphans: --no-dry-run deletes only orphans, preserves referenced files and DB records.
3. test_recent_orphan_files_are_preserved: files newer than cutoff are not purged.
4. test_empty_directories_are_cleaned: cleans empty YYYY/MM/DD date folders, preserves parking_scans root.
5. test_negative_older_than_hours_raises_command_error: rejects negative hours with CommandError.
6. test_missing_scans_directory_handled_gracefully: does not crash when parking_scans dir does not exist.
"""

from __future__ import annotations

import io
import os
import time
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.parking.models import ParkingGate, VehicleEntryExitLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def test_media_setup(settings, tmp_path):
    """Thiết lập môi trường MEDIA_ROOT sạch trong tmp_path cho mỗi bài kiểm thử."""
    media_dir = tmp_path / "test_media"
    media_dir.mkdir(parents=True, exist_ok=True)
    settings.MEDIA_ROOT = media_dir
    settings.MEDIA_URL = "/media/"
    scans_dir = media_dir / "parking_scans"
    scans_dir.mkdir(parents=True, exist_ok=True)
    return media_dir, scans_dir


@pytest.fixture
def default_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào Purge Test", direction="IN", is_active=True
        )
    return gate


def create_dummy_scan_file(
    parent_dir: Path, rel_sub_path: str, age_hours: float = 48.0
) -> Path:
    """Tạo tệp ảnh giả lập trên đĩa và gán thời gian mtime tương ứng."""
    file_path = parent_dir / rel_sub_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(b"dummy_scan_image_content_" + rel_sub_path.encode("utf-8"))

    past_time = time.time() - (age_hours * 3600.0)
    os.utime(file_path, (past_time, past_time))
    return file_path


def test_dry_run_preserves_orphan_files(test_media_setup):
    """
    1. Kiểm chứng chế độ dry-run mặc định:
    Phát hiện đúng tệp mồ côi nhưng tuyệt đối không xóa tệp nào trên đĩa.
    """
    media_dir, scans_dir = test_media_setup
    orphan_rel = "2026/01/01/orphan_01.jpg"
    orphan_file = create_dummy_scan_file(scans_dir, orphan_rel, age_hours=48.0)

    out = io.StringIO()
    call_command("purge_orphan_scans", stdout=out, dry_run=True, older_than_hours=24.0)

    output = out.getvalue()
    assert "DRY-RUN (Mô phỏng, KHÔNG xóa tệp)" in output
    assert "Tệp mồ côi phát hiện: 1" in output
    assert "Tệp mồ côi đã xóa thực tế: 0" in output
    # Tệp vẫn còn trên đĩa
    assert orphan_file.exists()


def test_no_dry_run_deletes_only_orphans(test_media_setup, default_gate):
    """
    2. Kiểm chứng chế độ --no-dry-run:
    Xóa tệp mồ côi cũ, bảo lưu 100% các tệp được tham chiếu bởi entry_image_url và exit_image_url.
    Bản ghi CSDL hoàn toàn nguyên vẹn.
    """
    media_dir, scans_dir = test_media_setup

    # Tạo tệp được tham chiếu bởi entry_image_url
    ref_entry_rel = "2026/01/02/ref_entry.jpg"
    ref_entry_file = create_dummy_scan_file(scans_dir, ref_entry_rel, age_hours=48.0)

    # Tạo tệp được tham chiếu bởi exit_image_url
    ref_exit_rel = "2026/01/02/ref_exit.jpg"
    ref_exit_file = create_dummy_scan_file(scans_dir, ref_exit_rel, age_hours=48.0)

    # Tạo tệp mồ côi
    orphan_rel = "2026/01/02/orphan_to_delete.jpg"
    orphan_file = create_dummy_scan_file(scans_dir, orphan_rel, age_hours=48.0)

    # Tạo bản ghi log trong CSDL tham chiếu 2 tệp trên
    log = VehicleEntryExitLog.objects.create(
        session_code="PK-PURGE-001",
        license_plate="51K-111.11",
        entry_time=timezone.now(),
        entry_gate=default_gate,
        entry_image_url=f"/media/parking_scans/{ref_entry_rel}",
        exit_image_url=f"/media/parking_scans/{ref_exit_rel}",
    )

    out = io.StringIO()
    call_command("purge_orphan_scans", stdout=out, dry_run=False, older_than_hours=24.0)

    output = out.getvalue()
    assert "THỰC THI (XÓA TỆP VĨNH VIỄN)" in output
    assert "Tệp mồ côi phát hiện: 1" in output
    assert "Tệp mồ côi đã xóa thực tế: 1" in output

    # Tệp mồ côi đã bị xóa
    assert not orphan_file.exists()

    # Tệp được tham chiếu vẫn còn nguyên vẹn
    assert ref_entry_file.exists()
    assert ref_exit_file.exists()

    # Bản ghi CSDL không bị thay đổi
    log.refresh_from_db()
    assert log.entry_image_url == f"/media/parking_scans/{ref_entry_rel}"
    assert log.exit_image_url == f"/media/parking_scans/{ref_exit_rel}"


def test_recent_orphan_files_are_preserved(test_media_setup):
    """
    3. Kiểm chứng các tệp mồ côi mới (< older_than_hours) không bị xóa để tránh race conditions.
    """
    media_dir, scans_dir = test_media_setup
    recent_rel = "2026/01/03/recent_orphan.jpg"
    # Tạo tệp mới 2 giờ trước
    recent_file = create_dummy_scan_file(scans_dir, recent_rel, age_hours=2.0)

    out = io.StringIO()
    call_command("purge_orphan_scans", stdout=out, dry_run=False, older_than_hours=24.0)

    output = out.getvalue()
    assert "Tệp còn mới (< 24.0h, bảo lưu): 1" in output
    assert "Tệp mồ côi phát hiện: 0" in output
    assert "Tệp mồ côi đã xóa thực tế: 0" in output
    assert recent_file.exists()


def test_empty_directories_are_cleaned(test_media_setup):
    """
    4. Kiểm chứng các thư mục ngày tháng rỗng (YYYY/MM/DD) được dọn dẹp sạch sẽ,
    nhưng thư mục gốc parking_scans được bảo lưu.
    """
    media_dir, scans_dir = test_media_setup
    orphan_rel = "2026/05/10/single_orphan.jpg"
    orphan_file = create_dummy_scan_file(scans_dir, orphan_rel, age_hours=48.0)
    leaf_dir = orphan_file.parent

    assert leaf_dir.exists()

    out = io.StringIO()
    call_command("purge_orphan_scans", stdout=out, dry_run=False, older_than_hours=24.0)

    # Tệp đã bị xóa
    assert not orphan_file.exists()
    # Thư mục lá ngày 2026/05/10 đã bị xóa
    assert not leaf_dir.exists()
    # Thư mục tháng 2026/05 và năm 2026 cũng đã bị xóa do rỗng
    assert not (scans_dir / "2026" / "05").exists()
    assert not (scans_dir / "2026").exists()
    # Thư mục gốc parking_scans vẫn tồn tại
    assert scans_dir.exists()


def test_negative_older_than_hours_raises_command_error(test_media_setup):
    """
    5. Kiểm chứng bắt lỗi tham số --older-than-hours âm.
    """
    with pytest.raises(CommandError, match="Tham số --older-than-hours không được âm"):
        call_command("purge_orphan_scans", older_than_hours=-5.0)


def test_missing_scans_directory_handled_gracefully(settings, tmp_path):
    """
    6. Kiểm chứng xử lý êm ái khi thư mục parking_scans chưa tồn tại.
    """
    empty_media = tmp_path / "empty_media_without_scans"
    settings.MEDIA_ROOT = empty_media

    out = io.StringIO()
    # Không tạo thư mục parking_scans
    call_command("purge_orphan_scans", stdout=out)
    output = out.getvalue()

    assert "không tồn tại hoặc không phải là thư mục" in output
