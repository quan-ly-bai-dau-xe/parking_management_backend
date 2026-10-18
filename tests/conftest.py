"""
Pytest configuration and shared fixtures for parking_management_backend test suite.
"""

import pytest
from django.core.management import call_command

from apps.parking.models import PlateBlacklist


@pytest.fixture(autouse=True)
def ensure_sample_data(db):
    """Đảm bảo dữ liệu mẫu (seed data) luôn được nạp vào test database."""
    if PlateBlacklist.all_objects.count() == 0:
        call_command("load_sample_data", force_production=True)
