"""
Pytest configuration and shared fixtures for parking_management_backend test suite.
"""

import io
import os
import re
import uuid
from typing import Any

import pytest

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings.test"

import cloudinary.uploader  # noqa: E402
from django.conf import settings  # noqa: E402
from django.core.management import call_command  # noqa: E402

from apps.parking.models import PlateBlacklist  # noqa: E402


@pytest.fixture(autouse=True)
def ensure_sample_data(db):
    """Đảm bảo dữ liệu mẫu (seed data) luôn được nạp vào test database."""
    if PlateBlacklist.all_objects.count() == 0:
        call_command("load_sample_data", force_production=True)


class FakeCloudinaryStorage:
    """In-memory deterministic fake for Cloudinary uploader APIs.

    Provides deterministic secure_url matching the regex required by
    validate_parking_image_path and ADR-0010 without making external network calls.
    """

    def __init__(self) -> None:
        self.uploaded_public_ids: list[str] = []
        self.destroyed_public_ids: list[str] = []
        self.uploaded_files: list[bytes] = []
        self.last_uploaded_bytes: bytes | None = None
        self.upload_calls: list[dict[str, Any]] = []
        self.destroy_calls: list[dict[str, Any]] = []
        self.force_upload_failure: bool | Exception | type[Exception] = False
        self.force_destroy_failure: bool | Exception | type[Exception] = False

    def upload(self, file_arg: Any, **kwargs: Any) -> dict[str, Any]:
        self.upload_calls.append({"file": file_arg, "kwargs": kwargs})

        if self.force_upload_failure:
            if isinstance(self.force_upload_failure, Exception):
                raise self.force_upload_failure
            if isinstance(self.force_upload_failure, type) and issubclass(
                self.force_upload_failure, Exception
            ):
                raise self.force_upload_failure("Forced Cloudinary upload failure")
            raise RuntimeError("Forced Cloudinary upload failure")

        if isinstance(file_arg, (io.BytesIO, io.BufferedReader)):
            file_arg.seek(0)
            raw = file_arg.read()
            self.last_uploaded_bytes = raw
            self.uploaded_files.append(raw)
        elif isinstance(file_arg, (bytes, bytearray)):
            self.last_uploaded_bytes = bytes(file_arg)
            self.uploaded_files.append(self.last_uploaded_bytes)
        elif hasattr(file_arg, "read"):
            raw = file_arg.read()
            self.last_uploaded_bytes = (
                raw if isinstance(raw, bytes) else str(raw).encode("utf-8")
            )
            self.uploaded_files.append(self.last_uploaded_bytes)

        cloud_name = (
            getattr(settings, "CLOUDINARY_CLOUD_NAME", "test-cloud") or "test-cloud"
        )
        folder = kwargs.get("folder", "parking_scans/2026/10/29")
        clean_folder = folder.strip("/") if folder else "parking_scans/2026/10/29"

        public_id = kwargs.get("public_id")
        raw_uuid = uuid.uuid4().hex if not public_id else str(public_id)

        if clean_folder and raw_uuid.startswith(clean_folder + "/"):
            leaf_id = raw_uuid[len(clean_folder) + 1 :].strip("/")
        else:
            leaf_id = raw_uuid.strip("/")

        if not re.match(r"^[0-9a-f]{32}$", leaf_id):
            uuid32 = uuid.uuid4().hex
        else:
            uuid32 = leaf_id

        full_public_id = f"{clean_folder}/{leaf_id}" if clean_folder else leaf_id
        self.uploaded_public_ids.append(full_public_id)

        timestamp = 1730178490
        secure_url = (
            f"https://res.cloudinary.com/{cloud_name}/image/upload/"
            f"v{timestamp}/{clean_folder}/{uuid32}.jpg"
        )

        return {
            "public_id": full_public_id,
            "secure_url": secure_url,
            "url": secure_url,
            "version": timestamp,
            "format": "jpg",
            "resource_type": "image",
            "created_at": "2026-10-29T12:00:00Z",
            "bytes": len(self.last_uploaded_bytes)
            if self.last_uploaded_bytes
            else 1024,
        }

    def destroy(self, public_id: Any, **options: Any) -> dict[str, Any]:
        self.destroy_calls.append({"public_id": public_id, "options": options})

        if self.force_destroy_failure:
            if isinstance(self.force_destroy_failure, Exception):
                raise self.force_destroy_failure
            if isinstance(self.force_destroy_failure, type) and issubclass(
                self.force_destroy_failure, Exception
            ):
                raise self.force_destroy_failure("Forced Cloudinary destroy failure")
            raise RuntimeError("Forced Cloudinary destroy failure")

        self.destroyed_public_ids.append(str(public_id))
        return {"result": "ok"}


@pytest.fixture(autouse=True)
def fake_cloudinary_storage(request, monkeypatch):
    """Autouse fixture replacing Cloudinary upload and destroy with an in-memory fake."""
    if request.node.get_closest_marker("network") is not None:
        yield
        return

    fake = FakeCloudinaryStorage()
    monkeypatch.setattr(cloudinary.uploader, "upload", fake.upload)
    monkeypatch.setattr(cloudinary.uploader, "destroy", fake.destroy)
    yield fake


@pytest.fixture
def fake_cloudinary(fake_cloudinary_storage):
    """Convenience alias for fake_cloudinary_storage."""
    return fake_cloudinary_storage


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
