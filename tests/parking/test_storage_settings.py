"""
Tests for the Cloudinary-only storage configuration (ADR-0010).

They call the real settings helpers and start the real runtime settings modules in a
subprocess, so a change in config/settings/ is what makes them fail.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from config.settings.base import (
    configure_cloudinary_sdk,
    validate_cloudinary_credentials,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_validate_cloudinary_credentials_missing_all_names_every_variable():
    with pytest.raises(ImproperlyConfigured) as exc_info:
        validate_cloudinary_credentials("", "", "")
    msg = str(exc_info.value)
    for name in (
        "CLOUDINARY_CLOUD_NAME",
        "CLOUDINARY_API_KEY",
        "CLOUDINARY_API_SECRET",
    ):
        assert name in msg


def test_validate_cloudinary_credentials_partial_missing_never_leaks_values():
    secret_val = "SUPER_SECRET_VALUE_DO_NOT_LEAK"
    key_val = "123456789012345"
    with pytest.raises(ImproperlyConfigured) as exc_info:
        validate_cloudinary_credentials("", key_val, secret_val)
    msg = str(exc_info.value)
    assert "CLOUDINARY_CLOUD_NAME" in msg
    assert "CLOUDINARY_API_KEY" not in msg
    assert "CLOUDINARY_API_SECRET" not in msg
    assert secret_val not in msg
    assert key_val not in msg


def test_validate_cloudinary_credentials_accepts_complete_set():
    validate_cloudinary_credentials("test-cloud", "test-key", "test-secret")


def test_configure_cloudinary_sdk_sets_https_config():
    import cloudinary

    configure_cloudinary_sdk("test-cloud", "test-key", "test-secret")
    cfg = cloudinary.config()
    assert cfg.cloud_name == "test-cloud"
    assert cfg.secure is True


def _import_settings(module: str, cloudinary_env: dict[str, str]):
    """Import a runtime settings module in a clean interpreter (no real credential)."""
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "SECRET_KEY": "x" * 50,
        "POSTGRES_DB": "x",
        "POSTGRES_USER": "x",
        "POSTGRES_PASSWORD": "x",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_PORT": "5432",
        "DEBUG": "False",
        "ALLOWED_HOSTS": "localhost",
        # Empty values win over a developer's local .env (read_env never overrides).
        "CLOUDINARY_CLOUD_NAME": "",
        "CLOUDINARY_API_KEY": "",
        "CLOUDINARY_API_SECRET": "",
        **cloudinary_env,
    }
    return subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.mark.parametrize(
    "module", ["config.settings.local", "config.settings.production"]
)
def test_runtime_settings_refuse_to_start_without_cloudinary_variables(module):
    result = _import_settings(module, {})
    assert result.returncode != 0
    assert "Missing required Cloudinary environment variables" in result.stderr
    assert "CLOUDINARY_API_SECRET" in result.stderr


@pytest.mark.parametrize(
    "module", ["config.settings.local", "config.settings.production"]
)
def test_runtime_settings_start_with_cloudinary_variables(module):
    result = _import_settings(
        module,
        {
            "CLOUDINARY_CLOUD_NAME": "test-cloud",
            "CLOUDINARY_API_KEY": "test-key",
            "CLOUDINARY_API_SECRET": "test-secret",
        },
    )
    assert result.returncode == 0, result.stderr[-400:]


def test_env_example_contains_empty_cloudinary_vars():
    """Verifies .env.example declares variables with strictly empty values (zero secrets)."""
    env_example_path = Path(__file__).resolve().parents[2] / ".env.example"
    assert env_example_path.exists(), ".env.example file must exist."

    content = env_example_path.read_text(encoding="utf-8")
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
