"""
Unit tests for Image Storage settings and fail-fast startup validation.
Ensures zero secret leakage and verifies environment configuration behavior
per ADR-0009 and Milestone 4 requirements.
"""

from pathlib import Path
from unittest.mock import patch

import environ
import pytest
from django.core.exceptions import ImproperlyConfigured


def _eval_storage_settings(env_dict: dict[str, str]) -> dict[str, str]:
    """Helper to evaluate image storage settings logic in isolation."""
    env = environ.Env()
    with patch.dict("os.environ", env_dict, clear=True):
        backend = env.str("IMAGE_STORAGE_BACKEND", default="local").strip().lower()
        allowed_backends = ("local", "cloudinary")
        if backend not in allowed_backends:
            raise ImproperlyConfigured(
                f"Invalid IMAGE_STORAGE_BACKEND: '{backend}'. "
                f"Permitted values are: {', '.join(allowed_backends)}."
            )

        cloud_name = env.str("CLOUDINARY_CLOUD_NAME", default="").strip()
        api_key = env.str("CLOUDINARY_API_KEY", default="").strip()
        api_secret = env.str("CLOUDINARY_API_SECRET", default="").strip()

        if backend == "cloudinary":
            missing_vars: list[str] = []
            if not cloud_name:
                missing_vars.append("CLOUDINARY_CLOUD_NAME")
            if not api_key:
                missing_vars.append("CLOUDINARY_API_KEY")
            if not api_secret:
                missing_vars.append("CLOUDINARY_API_SECRET")
            if missing_vars:
                raise ImproperlyConfigured(
                    f"IMAGE_STORAGE_BACKEND='cloudinary' requires environment variables. "
                    f"Missing: {', '.join(missing_vars)}."
                )

        return {
            "IMAGE_STORAGE_BACKEND": backend,
            "CLOUDINARY_CLOUD_NAME": cloud_name,
            "CLOUDINARY_API_KEY": api_key,
            "CLOUDINARY_API_SECRET": api_secret,
        }


def test_storage_settings_default_local():
    """Default backend must be 'local' when environment is empty."""
    res = _eval_storage_settings({})
    assert res["IMAGE_STORAGE_BACKEND"] == "local"


def test_storage_settings_invalid_backend_raises():
    """Invalid storage backend raises ImproperlyConfigured with permitted values."""
    with pytest.raises(ImproperlyConfigured) as exc_info:
        _eval_storage_settings({"IMAGE_STORAGE_BACKEND": "aws_s3"})
    msg = str(exc_info.value)
    assert "Invalid IMAGE_STORAGE_BACKEND: 'aws_s3'" in msg
    assert "local, cloudinary" in msg


def test_storage_settings_cloudinary_missing_all_raises():
    """Cloudinary backend with missing credentials raises and lists all missing vars."""
    with pytest.raises(ImproperlyConfigured) as exc_info:
        _eval_storage_settings({"IMAGE_STORAGE_BACKEND": "cloudinary"})
    msg = str(exc_info.value)
    assert "CLOUDINARY_CLOUD_NAME" in msg
    assert "CLOUDINARY_API_KEY" in msg
    assert "CLOUDINARY_API_SECRET" in msg


def test_storage_settings_cloudinary_partial_missing_raises_without_leaking():
    """Cloudinary backend with partial missing vars reports only missing and leaks no secrets."""
    secret_val = "SUPER_SECRET_VALUE_DO_NOT_LEAK"
    key_val = "123456789012345"
    with pytest.raises(ImproperlyConfigured) as exc_info:
        _eval_storage_settings(
            {
                "IMAGE_STORAGE_BACKEND": "cloudinary",
                "CLOUDINARY_API_KEY": key_val,
                "CLOUDINARY_API_SECRET": secret_val,
            }
        )
    msg = str(exc_info.value)
    assert "CLOUDINARY_CLOUD_NAME" in msg
    assert secret_val not in msg
    assert key_val not in msg


def test_storage_settings_cloudinary_valid():
    """Cloudinary backend succeeds when all credentials are provided."""
    res = _eval_storage_settings(
        {
            "IMAGE_STORAGE_BACKEND": "cloudinary",
            "CLOUDINARY_CLOUD_NAME": "test-cloud",
            "CLOUDINARY_API_KEY": "111222333",
            "CLOUDINARY_API_SECRET": "abcdef123456",
        }
    )
    assert res["IMAGE_STORAGE_BACKEND"] == "cloudinary"
    assert res["CLOUDINARY_CLOUD_NAME"] == "test-cloud"


def test_env_example_contains_empty_cloudinary_vars():
    """Verifies .env.example declares variables with strictly empty values (zero secrets)."""
    env_example_path = Path(__file__).resolve().parents[2] / ".env.example"
    assert env_example_path.exists(), ".env.example file must exist."

    content = env_example_path.read_text(encoding="utf-8")
    assert "IMAGE_STORAGE_BACKEND=local" in content
    assert "CLOUDINARY_CLOUD_NAME=" in content
    assert "CLOUDINARY_API_KEY=" in content
    assert "CLOUDINARY_API_SECRET=" in content

    # Ensure no values are attached to the Cloudinary credentials in .env.example
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("CLOUDINARY_"):
            key, val = line.split("=", 1)
            assert val == "", (
                f"{key} in .env.example must have an empty value, found: {val}"
            )
