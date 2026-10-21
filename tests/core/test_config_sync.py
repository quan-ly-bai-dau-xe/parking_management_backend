"""
Automated Configuration Synchronization & Drift Prevention Test Suite.
Verifies that docker-compose.yml, .env.example, docker/gunicorn.conf.py,
config/settings/base.py, apps/core/concurrency.py, README.md, and ADR-0007
never drift apart (J2 Single Source of Truth).
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def ensure_sample_data():
    """Bypasses database seed fixture since config sync tests are strictly on-disk."""
    return


def parse_env_file(filepath: Path) -> dict[str, str]:
    """Parses key-value pairs from .env or .env.example."""
    data: dict[str, str] = {}
    if not filepath.is_file():
        return data
    for raw_line in filepath.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            val = v.split("#")[0].strip().strip('"').strip("'")
            data[k.strip()] = val
    return data


def parse_compose_defaults(filepath: Path) -> dict[str, str]:
    """Extracts default fallback values from docker-compose.yml ${VAR:-default} syntax."""
    text = filepath.read_text(encoding="utf-8")
    matches = re.findall(r"([A-Z0-9_]+):\s*\$\{[A-Z0-9_]+:-([^}]+)\}", text)
    return {k: v.strip().strip('"').strip("'") for k, v in matches}


def load_gunicorn_conf(filepath: Path):
    """Imports docker/gunicorn.conf.py as a dynamic module."""
    spec = importlib.util.spec_from_file_location("gunicorn_conf_sync", filepath)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_j2_single_source_of_truth_and_drift_prevention():
    """
    J2 Acceptance Criteria:
    Asserts exact synchronization across:
    1. docker-compose.yml
    2. .env.example
    3. docker/gunicorn.conf.py
    4. config/settings/base.py (via Django settings)
    5. apps/core/concurrency.py (fallback defaults)
    6. README.md
    7. docs/adr/0007-backend-service-in-docker-compose-and-plate-ocr-engine.md
    """
    repo_root = Path(settings.BASE_DIR)
    compose_path = repo_root / "docker-compose.yml"
    env_example_path = repo_root / ".env.example"
    gunicorn_conf_path = repo_root / "docker" / "gunicorn.conf.py"
    concurrency_path = repo_root / "apps" / "core" / "concurrency.py"
    readme_path = repo_root / "README.md"
    adr_path = (
        repo_root
        / "docs"
        / "adr"
        / "0007-backend-service-in-docker-compose-and-plate-ocr-engine.md"
    )

    compose_defs = parse_compose_defaults(compose_path)
    env_example_defs = parse_env_file(env_example_path)
    gunicorn_mod = load_gunicorn_conf(gunicorn_conf_path)
    concurrency_text = concurrency_path.read_text(encoding="utf-8")
    readme_text = readme_path.read_text(encoding="utf-8")
    adr_text = adr_path.read_text(encoding="utf-8")

    # 1. Expected Single-Source-Of-Truth Target Values
    expected_workers = 4
    expected_threads = 6
    expected_gate = 4
    expected_timeout = 2.0

    # 2. Extract Values
    # docker-compose.yml
    compose_workers = int(compose_defs.get("GUNICORN_WORKERS", 0))
    compose_threads = int(compose_defs.get("GUNICORN_THREADS", 0))
    compose_gate = int(compose_defs.get("PARKING_OCR_CONCURRENCY_LIMIT", 0))
    compose_timeout = float(compose_defs.get("PARKING_OCR_QUEUE_TIMEOUT", 0.0))

    # .env.example
    env_workers = int(env_example_defs.get("GUNICORN_WORKERS", 0))
    env_threads = int(env_example_defs.get("GUNICORN_THREADS", 0))
    env_gate = int(env_example_defs.get("PARKING_OCR_CONCURRENCY_LIMIT", 0))
    env_timeout = float(env_example_defs.get("PARKING_OCR_QUEUE_TIMEOUT", 0.0))

    # docker/gunicorn.conf.py
    gunicorn_workers = int(getattr(gunicorn_mod, "workers", 0))
    gunicorn_threads = int(getattr(gunicorn_mod, "threads", 0))

    # Django settings (config/settings/base.py)
    settings_gate = int(getattr(settings, "PARKING_OCR_CONCURRENCY_LIMIT", 0))
    settings_timeout = float(getattr(settings, "PARKING_OCR_QUEUE_TIMEOUT", 0.0))

    # 3. Synchronized Equality Assertions
    assert compose_workers == env_workers == gunicorn_workers == expected_workers, (
        f"GUNICORN_WORKERS mismatch: compose={compose_workers}, env={env_workers}, gunicorn={gunicorn_workers}"
    )
    assert compose_threads == env_threads == gunicorn_threads == expected_threads, (
        f"GUNICORN_THREADS mismatch: compose={compose_threads}, env={env_threads}, gunicorn={gunicorn_threads}"
    )
    assert compose_gate == env_gate == settings_gate == expected_gate, (
        f"PARKING_OCR_CONCURRENCY_LIMIT mismatch: compose={compose_gate}, env={env_gate}, settings={settings_gate}"
    )
    assert compose_timeout == env_timeout == settings_timeout == expected_timeout, (
        f"PARKING_OCR_QUEUE_TIMEOUT mismatch: compose={compose_timeout}, env={env_timeout}, settings={settings_timeout}"
    )

    # apps/core/concurrency.py fallback timeout assertion
    assert (
        'default_timeout = float(os.getenv("PARKING_OCR_QUEUE_TIMEOUT", "2.0"))'
        in concurrency_text
    ), "apps/core/concurrency.py does not define default_timeout fallback as '2.0'"

    # 4. Strict Back-Pressure Invariant Proof: Threads MUST strictly exceed Concurrency Gate
    assert gunicorn_threads > settings_gate, (
        f"CRITICAL BACK-PRESSURE FLAW: GUNICORN_THREADS ({gunicorn_threads}) must be strictly greater than "
        f"PARKING_OCR_CONCURRENCY_LIMIT ({settings_gate}) to allow worker threads to queue at Semaphore!"
    )

    # 5. Database Connection Ceiling Guarantee
    assert gunicorn_workers * gunicorn_threads <= 32 < 40, (
        f"DB Connection ceiling exceeded: {gunicorn_workers} * {gunicorn_threads} = "
        f"{gunicorn_workers * gunicorn_threads} > 32"
    )

    # 6. Documentation Regex Assertions
    # README.md check
    assert re.search(
        r"GUNICORN_THREADS.*`" + str(expected_threads) + r"`", readme_text
    ), f"README.md does not document GUNICORN_THREADS as `{expected_threads}`"
    assert re.search(
        r"PARKING_OCR_QUEUE_TIMEOUT.*`" + str(expected_timeout) + r"`", readme_text
    ), f"README.md does not document PARKING_OCR_QUEUE_TIMEOUT as `{expected_timeout}`"

    # ADR-0007 check
    assert re.search(r"threads\s*=\s*" + str(expected_threads), adr_text), (
        f"ADR-0007 does not document threads = {expected_threads}"
    )


def test_j6_explicit_settings_sync():
    """
    J6 Acceptance Criteria:
    Verifies that all newly declared OCR, review policy, storage, and retry tunables
    match between docker-compose.yml, .env.example, and Django settings.
    """
    repo_root = Path(settings.BASE_DIR)
    compose_path = repo_root / "docker-compose.yml"
    env_example_path = repo_root / ".env.example"

    compose_defs = parse_compose_defaults(compose_path)
    env_example_defs = parse_env_file(env_example_path)

    # 1. OCR Accuracy Tunables
    assert (
        float(compose_defs["PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD"])
        == float(env_example_defs["PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD"])
        == float(settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD)
        == 90.0
    )
    assert (
        float(compose_defs["PARKING_OCR_ADAPTIVE_THRESHOLD"])
        == float(env_example_defs["PARKING_OCR_ADAPTIVE_THRESHOLD"])
        == float(settings.PARKING_OCR_ADAPTIVE_THRESHOLD)
        == 94.0
    )
    assert (
        float(compose_defs["PARKING_OCR_LEADING_CHAR_THRESHOLD"])
        == float(env_example_defs["PARKING_OCR_LEADING_CHAR_THRESHOLD"])
        == float(settings.PARKING_OCR_LEADING_CHAR_THRESHOLD)
        == 99.2
    )
    assert (
        float(compose_defs["PARKING_OCR_ADAPTIVE_AVG_THRESHOLD"])
        == float(env_example_defs["PARKING_OCR_ADAPTIVE_AVG_THRESHOLD"])
        == float(settings.PARKING_OCR_ADAPTIVE_AVG_THRESHOLD)
        == 96.0
    )
    assert (
        int(compose_defs["PARKING_OCR_CROP_MARGIN"])
        == int(env_example_defs["PARKING_OCR_CROP_MARGIN"])
        == int(settings.PARKING_OCR_CROP_MARGIN)
        == 4
    )
    assert (
        int(compose_defs["PARKING_OCR_RETRY_AFTER"])
        == int(env_example_defs["PARKING_OCR_RETRY_AFTER"])
        == int(settings.PARKING_OCR_RETRY_AFTER)
        == 3
    )

    # 2. Review Policy Secondary Signal Thresholds
    assert (
        float(compose_defs["PARKING_REVIEW_DETECTOR_CONF_THRESHOLD"])
        == float(env_example_defs["PARKING_REVIEW_DETECTOR_CONF_THRESHOLD"])
        == float(settings.PARKING_REVIEW_DETECTOR_CONF_THRESHOLD)
        == 80.0
    )
    assert (
        float(compose_defs["PARKING_REVIEW_MIN_ASPECT_RATIO"])
        == float(env_example_defs["PARKING_REVIEW_MIN_ASPECT_RATIO"])
        == float(settings.PARKING_REVIEW_MIN_ASPECT_RATIO)
        == 1.3
    )
    assert (
        float(compose_defs["PARKING_REVIEW_MAX_ASPECT_RATIO"])
        == float(env_example_defs["PARKING_REVIEW_MAX_ASPECT_RATIO"])
        == float(settings.PARKING_REVIEW_MAX_ASPECT_RATIO)
        == 6.0
    )
    assert (
        float(compose_defs["PARKING_REVIEW_MIN_SHARPNESS"])
        == float(env_example_defs["PARKING_REVIEW_MIN_SHARPNESS"])
        == float(settings.PARKING_REVIEW_MIN_SHARPNESS)
        == 30.0
    )

    # 3. Upload & Storage Limits
    assert (
        int(compose_defs["MAX_IMAGE_SIZE_MB"])
        == int(env_example_defs["MAX_IMAGE_SIZE_MB"])
        == int(settings.MAX_IMAGE_SIZE_MB)
        == 5
    )


def test_fail_fast_invalid_setting_type_in_subprocess():
    """
    J6 Fail-Fast Verification:
    Passing a malformed value to a typed django-environ tunable must immediately fail at startup.
    """
    cmd = [
        sys.executable,
        "-c",
        (
            "import os; "
            "os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.test'; "
            "os.environ['PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD'] = 'invalid_float_val'; "
            "import django; django.setup()"
        ),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode != 0
    assert (
        "ValueError" in proc.stderr
        or "could not convert string to float" in proc.stderr
    )


def test_subprocess_env_override_runtime():
    """
    J6 Subprocess Runtime Override:
    Proves that environment variables properly propagate through django-environ into Django settings.
    """
    cmd = [
        sys.executable,
        "-c",
        (
            "import os; "
            "os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings.test'; "
            "os.environ['PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD'] = '85.5'; "
            "os.environ['PARKING_OCR_CROP_MARGIN'] = '8'; "
            "import django; django.setup(); "
            "from django.conf import settings; "
            "assert settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD == 85.5; "
            "assert settings.PARKING_OCR_CROP_MARGIN == 8; "
            "print('OVERRIDE_OK')"
        ),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    assert proc.returncode == 0
    assert "OVERRIDE_OK" in proc.stdout
