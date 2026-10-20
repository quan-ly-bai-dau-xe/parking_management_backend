"""
Pytest configuration and shared fixtures for parking_management_backend test suite.
"""

import os

import pytest

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"

from django.core.management import call_command  # noqa: E402

from apps.parking.models import PlateBlacklist  # noqa: E402


@pytest.fixture(autouse=True)
def ensure_sample_data(db):
    """Đảm bảo dữ liệu mẫu (seed data) luôn được nạp vào test database."""
    if PlateBlacklist.all_objects.count() == 0:
        call_command("load_sample_data", force_production=True)


@pytest.fixture(autouse=True)
def redirect_media_root_to_tmp(settings, tmp_path):
    """
    Chuyển hướng settings.MEDIA_ROOT về tmp_path cho toàn bộ test suite.
    Đảm bảo pytest không bao giờ tạo hay để lại tệp rác trong media/ ở root repo.
    """
    test_media = tmp_path / "media"
    test_media.mkdir(parents=True, exist_ok=True)
    settings.MEDIA_ROOT = test_media
    return test_media


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """
    Tự động bỏ qua mọi test có gắn marker @pytest.mark.perf
    trừ khi biến môi trường RUN_PERF_TESTS='1' được thiết lập rõ ràng.
    """
    if os.getenv("RUN_PERF_TESTS") != "1":
        skip_perf = pytest.mark.skip(
            reason="Performance test skipped by default. Set RUN_PERF_TESTS=1 to run."
        )
        for item in items:
            if item.get_closest_marker("perf") is not None:
                item.add_marker(skip_perf)
