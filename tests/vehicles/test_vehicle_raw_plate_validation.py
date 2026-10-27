"""
Tests for raw license plate validation and tricky strings matrix (Milestone 3 / S3).

Verifies:
1. Full 21 tricky strings matrix submitted via DRF test client POST /api/v1/vehicles/.
2. caplog assertion: exactly 0 log records with "Database exception caught" across all tricky strings.
3. Lowercase plate "51k-992.14" is accepted (201 Created) and stored in DB as uppercase "51K-992.14".
4. Separator variants ("51K-992.14", "51K 992.14", "51K99214") trigger 409 Conflict (MSG-4.3.1-M05).
5. Comprehensive unit tests for validate_raw_license_plate covering all validation branches.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.vehicles.models import Vehicle
from apps.vehicles.services.vehicles import validate_raw_license_plate

pytestmark = pytest.mark.django_db

ENDPOINT_URL = "/api/v1/vehicles/"

TRICKY_STRINGS_MATRIX = [
    # STT, raw_input, expected_status, expected_code, description
    (1, "51K-992.14", status.HTTP_201_CREATED, "201_CREATED", "R64 civilian valid"),
    (2, "30A-123.45", status.HTTP_201_CREATED, "201_CREATED", "R64 civilian valid"),
    (3, "43A-999.99", status.HTTP_201_CREATED, "201_CREATED", "R64 civilian valid"),
    (
        4,
        "29LD-123.45",
        status.HTTP_201_CREATED,
        "201_CREATED",
        "R64 joint venture valid",
    ),
    (5, "A", status.HTTP_400_BAD_REQUEST, "PROP-4.5.1-P16", "R64 short string len 1"),
    (6, "000000000000", status.HTTP_400_BAD_REQUEST, "PROP-4.5.1-P16", "R64 12 digits"),
    (
        7,
        "59P1-678.90",
        status.HTTP_400_BAD_REQUEST,
        "PROP-4.5.1-P16",
        "R64 motorbike format",
    ),
    (
        8,
        "13A-123.45",
        status.HTTP_400_BAD_REQUEST,
        "PROP-4.5.1-P16",
        "R64 invalid province code 13",
    ),
    (
        9,
        "TM-12.34",
        status.HTTP_400_BAD_REQUEST,
        "PROP-4.5.1-P16",
        "R64 military format",
    ),
    (
        10,
        "51I-123.45",
        status.HTTP_400_BAD_REQUEST,
        "PROP-4.5.1-P16",
        "R64 series I not civilian car",
    ),
    (
        11,
        "50LĐ-123.45",
        status.HTTP_400_BAD_REQUEST,
        "PROP-4.5.1-P16",
        "Diacritic Đ non-ASCII",
    ),
    (
        12,
        "51K-992.14\u200b",
        status.HTTP_400_BAD_REQUEST,
        "PROP-4.5.1-P16",
        "Trailing zero-width space",
    ),
    (
        13,
        "51K-\u00a0992.14",
        status.HTTP_400_BAD_REQUEST,
        "PROP-4.5.1-P16",
        "Non-breaking space",
    ),
    (
        14,
        "５１K-９９２.１４",
        status.HTTP_400_BAD_REQUEST,
        "PROP-4.5.1-P16",
        "Full-width digits",
    ),
    (15, "51K-992.14🚗", status.HTTP_400_BAD_REQUEST, "PROP-4.5.1-P16", "Emoji car"),
    (
        16,
        "51K-\t992.14",
        status.HTTP_400_BAD_REQUEST,
        "PROP-4.5.1-P16",
        "Tab in middle",
    ),
    (
        17,
        "51K-\n992.14",
        status.HTTP_400_BAD_REQUEST,
        "PROP-4.5.1-P16",
        "Newline in middle",
    ),
    (
        18,
        "X" * 1000,
        status.HTTP_400_BAD_REQUEST,
        "PROP-GEN-P01",
        "1000 characters exceeded max length",
    ),
    (19, "51K-\x00992.14", status.HTTP_400_BAD_REQUEST, "PROP-GEN-P01", "NUL byte"),
    (
        20,
        "' OR 1=1 --",
        status.HTTP_400_BAD_REQUEST,
        "PROP-4.5.1-P16",
        "SQL injection syntax",
    ),
    (
        21,
        "51k-992.14",
        status.HTTP_201_CREATED,
        "201_CREATED",
        "Lowercase valid civilian car plate",
    ),
]


@pytest.mark.parametrize(
    "stt, raw_input, expected_status, expected_code, description",
    TRICKY_STRINGS_MATRIX,
)
def test_tricky_strings_matrix_via_api(
    manager_client: Any,
    car_type: Any,
    active_customer: Any,
    caplog: pytest.LogCaptureFixture,
    stt: int,
    raw_input: str,
    expected_status: int,
    expected_code: str,
    description: str,
) -> None:
    """
    Test each of the 21 tricky strings through POST /api/v1/vehicles/.
    Asserts expected HTTP status and response envelope code.
    Asserts zero "Database exception caught" log records on apps.core.exceptions.
    """
    caplog.set_level(logging.ERROR, logger="apps.core.exceptions")

    payload = {
        "license_plate": raw_input,
        "model_name": f"Test Vehicle {stt}",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }

    response = manager_client.post(ENDPOINT_URL, payload, format="json")

    # Assert HTTP status
    assert response.status_code == expected_status, (
        f"STT {stt} ({description}): expected {expected_status}, got {response.status_code}. Body: {response.content}"
    )

    # Assert response code
    if expected_status == status.HTTP_201_CREATED:
        data = response.json()
        assert "id" in data
        assert data["license_plate"] == raw_input.strip(" ").upper()
    else:
        data = response.json()
        assert data.get("code") == expected_code, (
            f"STT {stt} ({description}): expected code {expected_code}, got {data.get('code')}"
        )

    # Crucial assertion: 0 "Database exception caught" logs
    db_exception_logs = [
        rec.message
        for rec in caplog.records
        if "Database exception caught" in rec.message
    ]
    assert len(db_exception_logs) == 0, (
        f"STT {stt} ({description}) leaked database exception log: {db_exception_logs}"
    )


def test_lowercase_license_plate_saved_as_uppercase(
    manager_client: Any, car_type: Any, active_customer: Any
) -> None:
    """
    Test lowercase plate '51k-992.14' creates vehicle successfully (201 Created)
    and is stored in DB with uppercase '51K-992.14'.
    """
    payload = {
        "license_plate": "51k-992.14",
        "model_name": "VinFast VF8",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }

    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["license_plate"] == "51K-992.14"
    assert data["license_plate_norm"] == "51K99214"

    # Verify directly from database
    vehicle = Vehicle.objects.get(id=data["id"])
    assert vehicle.license_plate == "51K-992.14"
    assert vehicle.license_plate_norm == "51K99214"


def test_license_plate_separator_variants_conflict(
    manager_client: Any, car_type: Any, active_customer: Any
) -> None:
    """
    Test separator variants ('51K-992.14', '51K 992.14', '51K99214'):
    - First creation succeeds (201 Created).
    - Subsequent creations trigger 409 Conflict with code MSG-4.3.1-M05.
    """
    # 1. Create first vehicle with hyphen
    payload_1 = {
        "license_plate": "51K-992.14",
        "model_name": "Car Hyphen",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    resp_1 = manager_client.post(ENDPOINT_URL, payload_1, format="json")
    assert resp_1.status_code == status.HTTP_201_CREATED

    # 2. Attempt duplicate with space separator -> 409 MSG-4.3.1-M05
    payload_2 = {
        "license_plate": "51K 992.14",
        "model_name": "Car Space",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    resp_2 = manager_client.post(ENDPOINT_URL, payload_2, format="json")
    assert resp_2.status_code == status.HTTP_409_CONFLICT
    assert resp_2.json().get("code") == "MSG-4.3.1-M05"

    # 3. Attempt duplicate with no separator -> 409 MSG-4.3.1-M05
    payload_3 = {
        "license_plate": "51K99214",
        "model_name": "Car No Sep",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    resp_3 = manager_client.post(ENDPOINT_URL, payload_3, format="json")
    assert resp_3.status_code == status.HTTP_409_CONFLICT
    assert resp_3.json().get("code") == "MSG-4.3.1-M05"


# ==============================================================================
# Unit Tests for validate_raw_license_plate
# ==============================================================================


def test_validate_raw_license_plate_empty_or_none() -> None:
    """Test None, empty string, and whitespace-only raise PROP-GEN-P01."""
    with pytest.raises(BusinessAPIException) as exc_none:
        validate_raw_license_plate(None)
    assert exc_none.value.code == "PROP-GEN-P01"
    assert exc_none.value.status_code == status.HTTP_400_BAD_REQUEST

    with pytest.raises(BusinessAPIException) as exc_empty:
        validate_raw_license_plate("")
    assert exc_empty.value.code == "PROP-GEN-P01"
    assert exc_empty.value.status_code == status.HTTP_400_BAD_REQUEST

    with pytest.raises(BusinessAPIException) as exc_spaces:
        validate_raw_license_plate("     ")
    assert exc_spaces.value.code == "PROP-GEN-P01"
    assert exc_spaces.value.status_code == status.HTTP_400_BAD_REQUEST


def test_validate_raw_license_plate_length_limits() -> None:
    """Test strings shorter than 5 or longer than 20 characters raise PROP-4.5.1-P16."""
    # Shorter than 5 characters
    with pytest.raises(BusinessAPIException) as exc_short:
        validate_raw_license_plate("51K")
    assert exc_short.value.code == "PROP-4.5.1-P16"
    assert (
        exc_short.value.details.get("reason")
        == "Length must be between 5 and 20 characters."
    )

    # Longer than 20 characters
    with pytest.raises(BusinessAPIException) as exc_long:
        validate_raw_license_plate("51K-123.45-67890-ABCDE")
    assert exc_long.value.code == "PROP-4.5.1-P16"
    assert (
        exc_long.value.details.get("reason")
        == "Length must be between 5 and 20 characters."
    )


def test_validate_raw_license_plate_non_ascii() -> None:
    """Test non-ASCII characters (Vietnamese diacritics, unicode) raise PROP-4.5.1-P16."""
    with pytest.raises(BusinessAPIException) as exc_info:
        validate_raw_license_plate("50LĐ-123.45")
    assert exc_info.value.code == "PROP-4.5.1-P16"
    assert (
        exc_info.value.details.get("reason")
        == "Contains non-ASCII characters or unsupported symbols."
    )


def test_validate_raw_license_plate_invalid_syntax_positions() -> None:
    """Test leading, trailing, or invalid separator characters raise PROP-4.5.1-P16."""
    # Leading hyphen
    with pytest.raises(BusinessAPIException) as exc_lead:
        validate_raw_license_plate("-51K99214")
    assert exc_lead.value.code == "PROP-4.5.1-P16"
    assert (
        exc_lead.value.details.get("reason")
        == "Plate contains invalid characters or separator positions."
    )

    # Trailing dot
    with pytest.raises(BusinessAPIException) as exc_trail:
        validate_raw_license_plate("51K99214.")
    assert exc_trail.value.code == "PROP-4.5.1-P16"
    assert (
        exc_trail.value.details.get("reason")
        == "Plate contains invalid characters or separator positions."
    )


def test_validate_raw_license_plate_consecutive_separators() -> None:
    """Test consecutive separators raise PROP-4.5.1-P16."""
    # Consecutive hyphens
    with pytest.raises(BusinessAPIException) as exc_dash:
        validate_raw_license_plate("51K--992.14")
    assert exc_dash.value.code == "PROP-4.5.1-P16"
    assert (
        exc_dash.value.details.get("reason")
        == "Consecutive separators are not allowed."
    )

    # Consecutive dots
    with pytest.raises(BusinessAPIException) as exc_dots:
        validate_raw_license_plate("51K..992.14")
    assert exc_dots.value.code == "PROP-4.5.1-P16"
    assert (
        exc_dots.value.details.get("reason")
        == "Consecutive separators are not allowed."
    )

    # Consecutive spaces
    with pytest.raises(BusinessAPIException) as exc_spaces:
        validate_raw_license_plate("51K  992.14")
    assert exc_spaces.value.code == "PROP-4.5.1-P16"
    assert (
        exc_spaces.value.details.get("reason")
        == "Consecutive separators are not allowed."
    )


def test_validate_raw_license_plate_valid_cases() -> None:
    """Test valid license plates are correctly normalized to uppercase and ASCII trimmed."""
    # Standard civilian with dot and hyphen
    assert validate_raw_license_plate("51k-992.14") == "51K-992.14"

    # With leading/trailing spaces
    assert validate_raw_license_plate("  30A-123.45  ") == "30A-123.45"

    # Space separator
    assert validate_raw_license_plate("43A 999.99") == "43A 999.99"

    # Joint venture
    assert validate_raw_license_plate("29ld-123.45") == "29LD-123.45"
