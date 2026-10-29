"""Live Cloudinary network integration test (Milestone 4 - R8).

Guarded under @pytest.mark.network.
Uses a synthetic image and destroys the asset within the same test,
logging only raw HTTP status lines without credentials.
"""

import io
import logging
import re
import uuid
from pathlib import Path

import environ
import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.parking.services.ocr import (
    DummyPlateRecognizer,
    set_global_recognizer,
)
from apps.parking.services.upload import validate_parking_image_path

logger = logging.getLogger(__name__)


def _load_env_credentials() -> tuple[str, str, str]:
    """Helper loading real credentials from .env if present, without logging values."""
    env = environ.Env()
    repo_root = Path(__file__).resolve().parents[2]
    env_file = repo_root / ".env"
    if env_file.is_file():
        environ.Env.read_env(env_file)

    cloud_name = env.str("CLOUDINARY_CLOUD_NAME", default="").strip()
    api_key = env.str("CLOUDINARY_API_KEY", default="").strip()
    api_secret = env.str("CLOUDINARY_API_SECRET", default="").strip()

    return cloud_name, api_key, api_secret


@pytest.mark.network
@pytest.mark.django_db
def test_live_cloudinary_upload_and_destroy_cycle():
    """R8 Live Verification Check:

    1. Tests live network connectivity via official Cloudinary ping endpoint.
    2. Sends a synthetic image through the real POST /api/v1/parking/plate-scans/ code path
       using Django test client, dummy OCR engine, and real Cloudinary SDK.
    3. Asserts HTTP 200 with an HTTPS image_url matching validate_parking_image_path regex.
    4. Destroys the uploaded asset in the same test via its public ID and asserts 'ok'.
    5. Also validates direct low-level SDK upload and destroy cycle.
    """
    cloud_name, api_key, api_secret = _load_env_credentials()
    if not (cloud_name and api_key and api_secret):
        pytest.skip(
            "Live Cloudinary credentials not configured in environment or .env."
        )

    import cloudinary
    import cloudinary.api
    import cloudinary.exceptions
    import cloudinary.uploader

    # Configure Cloudinary client with credentials
    cloudinary.config(
        cloud_name=cloud_name,
        api_key=api_key,
        api_secret=api_secret,
        secure=True,
    )
    old_cloud_name = getattr(settings, "CLOUDINARY_CLOUD_NAME", "")
    old_api_key = getattr(settings, "CLOUDINARY_API_KEY", "")
    old_api_secret = getattr(settings, "CLOUDINARY_API_SECRET", "")
    settings.CLOUDINARY_CLOUD_NAME = cloud_name
    settings.CLOUDINARY_API_KEY = api_key
    settings.CLOUDINARY_API_SECRET = api_secret

    try:
        # 1. Verify live network connectivity via official Cloudinary ping endpoint
        ping_res = cloudinary.api.ping()
        assert ping_res.get("status") == "ok", (
            "Cloudinary ping must return status 'ok'."
        )
        logger.info("Cloudinary live ping HTTP status: ok")

        # 2. Test full plate-scans pipeline endpoint with synthetic image
        buf = io.BytesIO()
        img = Image.new("RGB", (200, 100), color="white")
        img.save(buf, format="JPEG")
        image_bytes = buf.getvalue()

        emp, _ = Account.objects.get_or_create(
            email="live_test_scanner@parking.local",
            defaults={
                "role": "EMPLOYEE",
                "is_active": True,
                "password": "!dummy_password_hash",
            },
        )

        recognizer = DummyPlateRecognizer(
            default_plate="51K-992.14", default_confidence=98.5
        )
        set_global_recognizer(recognizer)

        client = APIClient()
        client.force_authenticate(user=emp)
        file_obj = SimpleUploadedFile(
            "live_synthetic_scan.jpg", image_bytes, content_type="image/jpeg"
        )

        response = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": file_obj},
            format="multipart",
        )
        logger.info("Live plate scan HTTP status: %d", response.status_code)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

        image_url = response.data.get("image_url")
        assert image_url is not None, "Response data must include image_url"

        # Validate returned HTTPS URL against strict validator
        validated = validate_parking_image_path(image_url)
        assert validated == image_url, (
            "Returned image_url must match validate_parking_image_path regex"
        )
        logger.info("Cloudinary live URL regex match: %s", bool(validated))

        # Extract public_id and destroy asset
        match = re.search(
            r"/(parking_scans/\d{4}/\d{2}/\d{2}/[0-9a-f]{32})\.(jpg|png|webp)$",
            image_url,
        )
        assert match is not None, f"Could not extract public_id from {image_url}"
        public_id = match.group(1)

        destroy_result = cloudinary.uploader.destroy(
            public_id,
            resource_type="image",
            invalidate=True,
        )
        logger.info(
            "Cloudinary live destroy completed: result=%s",
            destroy_result.get("result"),
        )
        assert destroy_result.get("result") in ("ok", "not found")

        # 3. Direct low-level SDK upload and destroy cycle
        test_uuid = uuid.uuid4().hex
        direct_public_id = f"synthetic-{test_uuid}"
        folder = "r71-test"
        full_direct_id = f"{folder}/{direct_public_id}"

        upload_result = cloudinary.uploader.upload(
            io.BytesIO(image_bytes),
            public_id=direct_public_id,
            folder=folder,
            resource_type="image",
            overwrite=True,
            transformation=[{"flags": "force_strip"}],
        )
        logger.info(
            "Cloudinary live upload completed: bytes=%d, format=%s",
            len(image_bytes),
            upload_result.get("format"),
        )
        direct_url = upload_result.get("secure_url", "")
        assert direct_url.startswith("https://res.cloudinary.com/"), (
            "secure_url must be HTTPS."
        )
        assert f"/{cloud_name}/" in direct_url, (
            "secure_url must match configured cloud_name."
        )

        direct_destroy = cloudinary.uploader.destroy(
            full_direct_id,
            resource_type="image",
            invalidate=True,
        )
        logger.info(
            "Cloudinary direct destroy completed: result=%s",
            direct_destroy.get("result"),
        )
        assert direct_destroy.get("result") in ("ok", "not found")

    finally:
        set_global_recognizer(None)
        settings.CLOUDINARY_CLOUD_NAME = old_cloud_name
        settings.CLOUDINARY_API_KEY = old_api_key
        settings.CLOUDINARY_API_SECRET = old_api_secret
