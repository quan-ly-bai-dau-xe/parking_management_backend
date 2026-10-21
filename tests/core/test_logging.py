"""
Unit & integration test suite for logging utilities and plate masking (J9.2).
Validates Rule 07 & Decree 13/2023/ND-CP compliance for PII protection.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest
from django.test import override_settings
from rest_framework.response import Response

from apps.core.logging import format_plate_for_log, mask_plate
from apps.parking.views.scans import (
    finalize_observability_response,
)
from apps.parking.views.scans import (
    format_plate_for_log as reexported_format_plate,
)


class TestPlateMaskingUnit:
    """Verifies that mask_plate obscures personal vehicle plate numbers while preserving audit prefix/suffix."""

    def test_formatted_plate_with_hyphen_and_dot(self) -> None:
        """Standard 5-digit formatted plate e.g. 51F-698.81 -> 51F-***.81."""
        assert mask_plate("51F-698.81") == "51F-***.81"
        assert mask_plate("29A-123.45") == "29A-***.45"
        assert mask_plate("80B-999.99") == "80B-***.99"

    def test_unpunctuated_8_digit_plate(self) -> None:
        """Unpunctuated 8-char plate e.g. 51F69881 -> 51F***81."""
        assert mask_plate("51F69881") == "51F***81"
        assert mask_plate("29A12345") == "29A***45"
        assert mask_plate("50LD04411") == "50L***11"

    def test_formatted_4_digit_plate(self) -> None:
        """Legacy 4-digit formatted plate e.g. 80B-1234 -> 80B-***34."""
        assert mask_plate("80B-1234") == "80B-***34"
        assert mask_plate("52Y-6490") == "52Y-***90"

    def test_short_or_empty_plate(self) -> None:
        """Short or empty string handling."""
        assert mask_plate("12A") == "***"
        assert mask_plate("") == ""
        assert mask_plate("   ") == ""


class TestFormatPlateForLogSettings:
    """Verifies format_plate_for_log behavior when PARKING_LOG_MASK_PLATES is toggled."""

    def test_default_is_masked(self) -> None:
        """Default behavior must be masked to protect customer PII."""
        assert format_plate_for_log("51F-698.81") == "51F-***.81"
        assert format_plate_for_log("51F69881") == "51F***81"
        assert format_plate_for_log("29A12345") == "29A***45"
        assert format_plate_for_log(None) is None
        assert format_plate_for_log("") is None

    @override_settings(PARKING_LOG_MASK_PLATES=False)
    def test_disabled_masking_via_settings(self) -> None:
        """When PARKING_LOG_MASK_PLATES=False, returns full unmasked plate."""
        assert format_plate_for_log("51F-698.81") == "51F-698.81"
        assert format_plate_for_log("51F69881") == "51F69881"
        assert format_plate_for_log(None) is None

    def test_backward_compatibility_reexport(self) -> None:
        """Import from apps.parking.views.scans must point to the identical function."""
        assert reexported_format_plate is format_plate_for_log
        assert reexported_format_plate("51F69881") == "51F***81"


class TestStructuredLoggingOutput:
    """Verifies that structured JSON request log records the masked plate."""

    def test_finalize_observability_response_logs_masked_plate(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Plate logged in JSON record must be masked."""
        request = SimpleNamespace(
            _obs_start=0.0,
            _request_id="req-test-log-001",
            _obs_stages={
                "decode": 1.0,
                "detect": 2.0,
                "ocr1": 1.0,
                "ocr2": 1.0,
                "db": 1.0,
                "write": 1.0,
            },
            _obs_review_status="AUTO",
            _obs_review_reasons=[],
            _obs_plate="51F69881",
            user=SimpleNamespace(id="staff-uuid-001"),
        )
        response = Response({"status": "ok"}, status=200)

        with caplog.at_level(logging.INFO, logger="apps.parking.views.scans"):
            finalize_observability_response(
                request, response, "/api/v1/parking/plate-scans/"
            )

        assert len(caplog.records) >= 1
        log_json = json.loads(caplog.records[-1].message)
        assert log_json["plate"] == "51F***81"
        assert "51F69881" not in caplog.records[-1].message
