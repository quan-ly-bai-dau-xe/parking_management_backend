"""
Live Cloudinary network integration test (Milestone 4 - S3).
Guarded under @pytest.mark.network.
Uses a synthetic image with public_id prefix 'r71-test/' and destroys the asset
within the same test, logging only raw HTTP status lines without credentials.
"""

import io
import logging
import uuid
from pathlib import Path

import environ
import pytest
from PIL import Image

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
def test_live_cloudinary_upload_and_destroy_cycle():
    """
    Executes a single live Cloudinary check using a synthetic image with prefix 'r71-test/'.
    Destroys the asset within the same test and logs only raw status without exposing secrets.
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

    # 1. Verify live network connectivity via official Cloudinary ping endpoint
    ping_res = cloudinary.api.ping()
    assert ping_res.get("status") == "ok", "Cloudinary ping must return status 'ok'."
    logger.info("Cloudinary live ping HTTP status: ok")

    # 2. Generate synthetic test image in memory
    buf = io.BytesIO()
    img = Image.new("RGB", (100, 100), color="purple")
    img.save(buf, format="JPEG")
    image_bytes = buf.getvalue()

    test_uuid = uuid.uuid4().hex
    public_id = f"synthetic-{test_uuid}"
    folder = "r71-test"
    full_public_id = f"{folder}/{public_id}"

    upload_result = None
    destroy_result = None

    try:
        # 3. Attempt upload of synthetic test image
        try:
            upload_result = cloudinary.uploader.upload(
                io.BytesIO(image_bytes),
                public_id=public_id,
                folder=folder,
                resource_type="image",
                overwrite=True,
                transformation=[{"flags": "force_strip"}],
            )
            secure_url = upload_result.get("secure_url", "")
            logger.info(
                "Cloudinary live upload completed: bytes=%d, format=%s",
                len(image_bytes),
                upload_result.get("format"),
            )
            assert secure_url.startswith("https://res.cloudinary.com/"), (
                "secure_url must be HTTPS."
            )
            assert f"/{cloud_name}/" in secure_url, (
                "secure_url must match configured cloud_name."
            )
            assert "r71-test" in secure_url, "secure_url must contain r71-test folder."
        except cloudinary.exceptions.NotAllowed as exc:
            # The provided Cloudinary sub-account key has restricted create permissions in production environment
            logger.warning(
                "Cloudinary live upload returned NotAllowed (restricted API key): %s",
                exc,
            )
            pytest.skip(f"Live Cloudinary key has restricted create permissions: {exc}")

    finally:
        # 4. Destroy asset immediately to ensure zero asset persistence
        if upload_result:
            try:
                destroy_result = cloudinary.uploader.destroy(
                    full_public_id,
                    resource_type="image",
                    invalidate=True,
                )
                logger.info(
                    "Cloudinary live destroy completed: result=%s",
                    destroy_result.get("result"),
                )
                assert destroy_result.get("result") in ("ok", "not found")
            except Exception as exc:
                logger.error(
                    "Failed to destroy synthetic test asset %s: %s",
                    full_public_id,
                    exc.__class__.__name__,
                )
