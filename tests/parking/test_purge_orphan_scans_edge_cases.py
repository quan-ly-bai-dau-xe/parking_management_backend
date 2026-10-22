"""
Boundary empirical tests for purge_orphan_scans management command.

Stress-tests:
1. Matrix test: Old orphans (>48h) purged, recent orphans (<1h) preserved,
   referenced files preserved, empty nested folders cleaned, root preserved.
2. Invariance test: --dry-run guarantees zero disk modifications.
3. Edge case tests: Negative hours raise CommandError, missing dir handled safely,
   scans path as file handled safely, chunk-size streaming iteration.
4. Concurrency race protection: Recent files under 1 hour never deleted.
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
def media_env(settings, tmp_path):
    """Set up an isolated MEDIA_ROOT directory structure for empirical testing."""
    root_media = tmp_path / "media_root"
    root_media.mkdir(parents=True, exist_ok=True)
    settings.MEDIA_ROOT = root_media
    settings.MEDIA_URL = "/media/"
    scans_dir = root_media / "parking_scans"
    scans_dir.mkdir(parents=True, exist_ok=True)
    return root_media, scans_dir


@pytest.fixture
def active_gate():
    """Retrieve or create an active parking gate for test logs."""
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng đối kháng Purge", direction="IN", is_active=True
        )
    return gate


def forge_disk_file(parent_dir: Path, sub_rel: str, hours_ago: float) -> Path:
    """Create a file on disk with custom content and modified timestamp."""
    full_path = parent_dir / sub_rel
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(f"payload_data_{sub_rel}".encode())
    target_time = time.time() - (hours_ago * 3600.0)
    os.utime(full_path, (target_time, target_time))
    return full_path


class TestPurgeOrphanScansBoundaryMatrix:
    """Comprehensive multi-file category matrix testing for purge_orphan_scans."""

    def test_comprehensive_matrix_under_no_dry_run(self, media_env, active_gate):
        """
        Verify real purge execution (--no-dry-run):
        - Old orphans (>48h) must be deleted from disk.
        - Recent orphans (<1h) must be protected against race condition.
        - Referenced files (entry and exit) must never be purged regardless of age.
        - Empty nested folders must be removed while root parking_scans is kept.
        - Folders with surviving files must not be deleted.
        - Database log records must stay intact.
        """
        root_media, scans_dir = media_env

        # 1. Create old orphan files (> 48h)
        old_orphans = [
            forge_disk_file(scans_dir, "2025/10/01/old_orphan_1.jpg", 72.0),
            forge_disk_file(scans_dir, "2025/11/15/old_orphan_2.png", 55.0),
            forge_disk_file(scans_dir, "2025/12/30/nested/sub/old_orphan_3.webp", 96.0),
            forge_disk_file(scans_dir, "root_level_old_orphan.jpg", 60.0),
        ]

        # 2. Create recent orphan files (< 1h) to test race condition defense
        recent_orphans = [
            forge_disk_file(scans_dir, "2026/10/19/recent_orphan_1.jpg", 0.2),
            forge_disk_file(scans_dir, "2026/10/19/recent_orphan_2.png", 0.5),
            forge_disk_file(scans_dir, "2026/10/19/recent_orphan_3.webp", 0.9),
        ]

        # 3. Create referenced files (> 72h old)
        ref_entry_file = forge_disk_file(scans_dir, "2025/08/10/ref_entry.jpg", 80.0)
        ref_exit_file = forge_disk_file(scans_dir, "2025/08/10/ref_exit.jpg", 80.0)
        ref_full_url_file = forge_disk_file(scans_dir, "2025/09/01/ref_full.jpg", 90.0)

        # 4. Create co-located directory: 1 old orphan + 1 referenced file
        shared_dir_orphan = forge_disk_file(
            scans_dir, "2025/07/20/mixed_orphan.jpg", 70.0
        )
        shared_dir_ref = forge_disk_file(
            scans_dir, "2025/07/20/mixed_referenced.jpg", 70.0
        )
        old_orphans.append(shared_dir_orphan)

        # 5. Create empty nested directories without any files
        empty_leaf = scans_dir / "2024" / "01" / "empty_day" / "deep_folder"
        empty_leaf.mkdir(parents=True, exist_ok=True)
        assert empty_leaf.exists()

        # 6. Create database records in VehicleEntryExitLog referencing files
        log_1 = VehicleEntryExitLog.objects.create(
            session_code="PK-ADV-001",
            license_plate="30A-999.99",
            entry_time=timezone.now(),
            entry_gate=active_gate,
            entry_image_url="/media/parking_scans/2025/08/10/ref_entry.jpg",
            exit_image_url="/media/parking_scans/2025/08/10/ref_exit.jpg",
        )
        log_2 = VehicleEntryExitLog.objects.create(
            session_code="PK-ADV-002",
            license_plate="29B-888.88",
            entry_time=timezone.now(),
            entry_gate=active_gate,
            entry_image_url="http://testserver/media/parking_scans/2025/09/01/ref_full.jpg",
            exit_image_url="/media/parking_scans/2025/07/20/mixed_referenced.jpg",
        )

        # 7. Unrelated file outside parking_scans (must never be touched)
        outside_file = forge_disk_file(root_media, "other_uploads/keep_me.txt", 100.0)

        # Run command with --no-dry-run and --older-than-hours 48.0
        out_buf = io.StringIO()
        call_command(
            "purge_orphan_scans",
            stdout=out_buf,
            dry_run=False,
            older_than_hours=48.0,
            verbosity=2,
        )
        output = out_buf.getvalue()

        # Assertion A: All 5 old orphans must be deleted from disk
        for orphan in old_orphans:
            assert not orphan.exists(), f"Old orphan was not deleted: {orphan}"

        # Assertion B: All 3 recent orphans (< 1h) must remain on disk
        for recent in recent_orphans:
            assert recent.exists(), f"Recent orphan was incorrectly deleted: {recent}"

        # Assertion C: All referenced files must remain on disk
        assert ref_entry_file.exists(), "Referenced entry file was deleted!"
        assert ref_exit_file.exists(), "Referenced exit file was deleted!"
        assert ref_full_url_file.exists(), "Referenced full URL file was deleted!"
        assert shared_dir_ref.exists(), "Referenced shared file was deleted!"

        # Assertion D: Unrelated file outside parking_scans untouched
        assert outside_file.exists(), "File outside parking_scans was touched!"

        # Assertion E: Empty nested directories cleaned, but root and non-empty kept
        assert not empty_leaf.exists(), "Empty leaf folder was not cleaned!"
        assert not (scans_dir / "2024" / "01" / "empty_day").exists()
        assert not (scans_dir / "2024" / "01").exists()
        assert not (scans_dir / "2024").exists()
        assert scans_dir.exists(), "Root parking_scans directory was deleted!"
        assert (scans_dir / "2025" / "07" / "20").exists(), "Shared folder deleted!"
        assert (scans_dir / "2026" / "10" / "19").exists(), "Recent folder deleted!"

        # Assertion F: Database records intact
        log_1.refresh_from_db()
        assert log_1.entry_image_url == "/media/parking_scans/2025/08/10/ref_entry.jpg"
        assert log_1.exit_image_url == "/media/parking_scans/2025/08/10/ref_exit.jpg"
        log_2.refresh_from_db()
        assert (
            log_2.entry_image_url
            == "http://testserver/media/parking_scans/2025/09/01/ref_full.jpg"
        )
        assert (
            log_2.exit_image_url
            == "/media/parking_scans/2025/07/20/mixed_referenced.jpg"
        )

        # Assertion G: Verification of output metrics
        assert "Tệp mồ côi đã xóa thực tế: 5" in output
        assert "Tệp còn mới (< 48.0h, bảo lưu): 3" in output
        assert "Tệp đang được CSDL tham chiếu (bảo lưu): 4" in output


class TestPurgeOrphanScansDryRunInvariance:
    """Verify that --dry-run produces zero disk mutations under stress."""

    def test_dry_run_absolute_disk_invariance(self, media_env, active_gate):
        """Dry-run must report orphans accurately while leaving disk 100% unchanged."""
        root_media, scans_dir = media_env

        # Create mixture of old orphans, recent orphans, and referenced files
        created_paths: list[Path] = []
        for i in range(6):
            created_paths.append(
                forge_disk_file(scans_dir, f"2025/03/0{i + 1}/orphan_{i}.jpg", 60.0)
            )
        for i in range(3):
            created_paths.append(
                forge_disk_file(scans_dir, f"2026/10/19/fresh_{i}.jpg", 0.4)
            )

        ref_file = forge_disk_file(scans_dir, "2025/03/99/active_ref.jpg", 60.0)
        created_paths.append(ref_file)

        VehicleEntryExitLog.objects.create(
            session_code="PK-DRY-001",
            license_plate="51F-123.45",
            entry_time=timezone.now(),
            entry_gate=active_gate,
            entry_image_url="/media/parking_scans/2025/03/99/active_ref.jpg",
        )

        # Snapshot entire tree state before execution
        tree_snapshot_before = {
            p.relative_to(root_media).as_posix(): p.stat().st_mtime
            for p in root_media.rglob("*")
            if p.is_file()
        }

        out_buf = io.StringIO()
        call_command(
            "purge_orphan_scans",
            stdout=out_buf,
            dry_run=True,
            older_than_hours=24.0,
            verbosity=2,
        )
        output = out_buf.getvalue()

        # Snapshot entire tree state after execution
        tree_snapshot_after = {
            p.relative_to(root_media).as_posix(): p.stat().st_mtime
            for p in root_media.rglob("*")
            if p.is_file()
        }

        # Assert zero mutations on file paths and mtimes
        assert tree_snapshot_before == tree_snapshot_after
        assert "DRY-RUN (Mô phỏng, KHÔNG xóa tệp)" in output
        assert "Tệp mồ côi phát hiện: 6" in output
        assert "Tệp mồ côi đã xóa thực tế: 0" in output


class TestPurgeOrphanScansEdgeCasesAndAnomalies:
    """Stress tests on parameter anomalies, boundary conditions, and file layouts."""

    def test_negative_older_than_hours_raises_command_error(self, media_env):
        """Negative hour arguments must raise CommandError with descriptive text."""
        for bad_val in [-5.0, -0.001, -100.0]:
            with pytest.raises(
                CommandError, match="Tham số --older-than-hours không được âm"
            ):
                call_command("purge_orphan_scans", older_than_hours=bad_val)

    def test_zero_older_than_hours_boundary(self, media_env):
        """Zero hour threshold purges all unreferenced files older than current time."""
        root_media, scans_dir = media_env
        orphan = forge_disk_file(scans_dir, "2026/10/19/zero_hour_orphan.jpg", 0.05)

        out_buf = io.StringIO()
        call_command(
            "purge_orphan_scans", stdout=out_buf, dry_run=False, older_than_hours=0.0
        )
        output = out_buf.getvalue()

        assert not orphan.exists()
        assert "Tệp mồ côi đã xóa thực tế: 1" in output

    def test_missing_scans_directory_handled_gracefully(self, settings, tmp_path):
        """When parking_scans directory does not exist, command exits safely without crashing."""
        settings.MEDIA_ROOT = tmp_path / "non_existent_folder"
        out_buf = io.StringIO()
        call_command("purge_orphan_scans", stdout=out_buf)
        output = out_buf.getvalue()
        assert "không tồn tại hoặc không phải là thư mục" in output

    def test_scans_directory_is_regular_file(self, settings, tmp_path):
        """When parking_scans is a regular file instead of directory, handle safely."""
        media_dir = tmp_path / "media_file_case"
        media_dir.mkdir(parents=True, exist_ok=True)
        settings.MEDIA_ROOT = media_dir
        dummy_file = media_dir / "parking_scans"
        dummy_file.write_text("I am a file, not a directory!")

        out_buf = io.StringIO()
        call_command("purge_orphan_scans", stdout=out_buf)
        output = out_buf.getvalue()
        assert "không tồn tại hoặc không phải là thư mục" in output
        assert dummy_file.exists()

    def test_chunked_streaming_pagination(self, media_env, active_gate):
        """Verify iterator chunking logic across small batch size (chunk_size=2)."""
        root_media, scans_dir = media_env

        # Create 5 referenced files and 2 orphan files
        for idx in range(5):
            sub_name = f"2025/04/chunk_ref_{idx}.jpg"
            forge_disk_file(scans_dir, sub_name, 50.0)
            VehicleEntryExitLog.objects.create(
                session_code=f"PK-CHK-{idx:03d}",
                license_plate=f"51A-{idx:03d}.11",
                entry_time=timezone.now(),
                entry_gate=active_gate,
                entry_image_url=f"/media/parking_scans/{sub_name}",
            )

        orphan_a = forge_disk_file(scans_dir, "2025/04/chunk_orphan_a.jpg", 50.0)
        orphan_b = forge_disk_file(scans_dir, "2025/04/chunk_orphan_b.jpg", 50.0)

        out_buf = io.StringIO()
        call_command(
            "purge_orphan_scans",
            stdout=out_buf,
            dry_run=False,
            older_than_hours=24.0,
            chunk_size=2,
        )
        output = out_buf.getvalue()

        assert not orphan_a.exists()
        assert not orphan_b.exists()
        assert "Tệp mồ côi đã xóa thực tế: 2" in output
        assert "Tệp đang được CSDL tham chiếu (bảo lưu): 5" in output

    def test_special_characters_in_filenames(self, media_env):
        """Orphan files containing spaces and symbols are purged cleanly."""
        root_media, scans_dir = media_env
        special_orphan = forge_disk_file(
            scans_dir, "2025/06/scan [gate-01] test #1.jpg", 60.0
        )
        assert special_orphan.exists()

        out_buf = io.StringIO()
        call_command(
            "purge_orphan_scans", stdout=out_buf, dry_run=False, older_than_hours=24.0
        )

        assert not special_orphan.exists()
