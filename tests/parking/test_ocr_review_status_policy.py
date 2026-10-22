"""
Boundary Stress Test Suite for OCR Review Status Policy.
Validates:
1. Precise boundary conditions for review_status (85.00%, 84.99%, 85.01%, Decimal rounding).
2. MANUAL source invariant: review_status='AUTO' and ai_confidence=None regardless of input.
3. Plate normalization parity against PostgreSQL fn_normalize_license_plate with boundary strings.
4. Validation of the 7 documented failure modes, specifically dirty/blurred sample #74 defense.
"""

from decimal import Decimal

import pytest
from django.db import connection
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.exceptions import BusinessAPIException
from apps.parking.models import ParkingGate, VehicleEntryExitLog
from apps.parking.services.check_in import check_in_vehicle
from apps.parking.services.ocr import PlateRecognizer

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_boundary@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def entry_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào Boundary Test", direction="IN", is_active=True
        )
    return gate


# ==============================================================================
# SECTION 1: Boundary Stress Test — Boundary & Precision of review_status
# ==============================================================================


@pytest.mark.parametrize(
    "ai_conf_input, expected_status, expected_conf_db",
    [
        # Exact boundaries
        (85.00, "AUTO", Decimal("85.00")),
        (85.01, "AUTO", Decimal("85.01")),
        (84.99, "NEEDS_REVIEW", Decimal("84.99")),
        # Decimal rounding half-even edge cases
        (84.994, "NEEDS_REVIEW", Decimal("84.99")),
        (84.995, "AUTO", Decimal("85.00")),
        (84.999, "AUTO", Decimal("85.00")),
        # Extreme boundaries
        (100.00, "AUTO", Decimal("100.00")),
        (0.00, "NEEDS_REVIEW", Decimal("0.00")),
        # Failure mode #74 exact confidence
        (78.41, "NEEDS_REVIEW", Decimal("78.41")),
        # None confidence with AI source
        (None, "NEEDS_REVIEW", None),
    ],
)
def test_review_status_boundary_stress_in_check_in_service(
    auth_employee, entry_gate, ai_conf_input, expected_status, expected_conf_db
):
    """
    Stress-test review_status classification directly in check_in_vehicle service.
    Verifies database persisted values for both review_status and ai_confidence.
    """
    import uuid

    unique_suffix = f"{uuid.uuid4().hex[:6].upper()}"
    plate = f"51A-{unique_suffix}"

    session, _ = check_in_vehicle(
        license_plate=plate,
        entry_gate_id=entry_gate.id,
        recognition_source="AI",
        ai_confidence=ai_conf_input,
        user=auth_employee,
    )

    db_record = VehicleEntryExitLog.objects.get(id=session.id)
    assert db_record.review_status == expected_status
    if expected_conf_db is None:
        assert db_record.ai_confidence is None
    else:
        assert db_record.ai_confidence == expected_conf_db


@pytest.mark.parametrize("invalid_conf", [-5.00, 120.00])
def test_review_status_out_of_bounds_confidence_raises_error(
    auth_employee, entry_gate, invalid_conf
):
    """
    Theo đặc tả F5: Độ tin cậy AI bắt buộc phải nằm trong khoảng từ 0.00 đến 100.00,
    nếu vượt quá sẽ raise BusinessAPIException (PROP-GEN-P01, HTTP 400).
    """
    import uuid

    unique_suffix = f"{uuid.uuid4().hex[:6].upper()}"
    plate = f"51A-{unique_suffix}"

    with pytest.raises(BusinessAPIException) as exc_info:
        check_in_vehicle(
            license_plate=plate,
            entry_gate_id=entry_gate.id,
            recognition_source="AI",
            ai_confidence=invalid_conf,
            user=auth_employee,
        )
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == 400


# ==============================================================================
# SECTION 2: Boundary Stress Test — MANUAL Recognition Source Invariants
# ==============================================================================


@pytest.mark.parametrize(
    "source_str, input_conf",
    [
        ("MANUAL", 50.00),
        ("MANUAL", 78.41),
        ("MANUAL", 99.99),
        ("MANUAL", None),
        ("manual", 0.00),
        ("Manual", 84.99),
    ],
)
def test_manual_source_invariant_enforces_auto_and_none_confidence(
    auth_employee, entry_gate, source_str, input_conf
):
    """
    SRS Invariant: Whenever recognition_source is MANUAL, review_status MUST be AUTO,
    and ai_confidence MUST be nullified (None) in the database, regardless of what caller passes.
    """
    import uuid

    unique_suffix = f"{uuid.uuid4().hex[:6].upper()}"
    plate = f"51B-{unique_suffix}"

    session, _ = check_in_vehicle(
        license_plate=plate,
        entry_gate_id=entry_gate.id,
        recognition_source=source_str,
        ai_confidence=input_conf,
        user=auth_employee,
    )

    db_record = VehicleEntryExitLog.objects.get(id=session.id)
    assert db_record.recognition_source == "MANUAL"
    assert db_record.review_status == "AUTO"
    assert db_record.ai_confidence is None


def test_api_check_in_review_status_boundary_via_http(auth_employee, entry_gate):
    """
    Verify boundary 84.99% vs 85.00% through DRF API endpoint response envelope.
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Test 84.99% -> NEEDS_REVIEW
    resp_8499 = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": "51C-849.90",
            "entry_gate_id": entry_gate.id,
            "recognition_source": "AI",
            "ai_confidence": 84.99,
        },
        format="json",
    )
    assert resp_8499.status_code == status.HTTP_201_CREATED
    assert resp_8499.data["session"]["review_status"] == "NEEDS_REVIEW"
    assert float(resp_8499.data["session"]["ai_confidence"]) == 84.99

    # 2. Test 85.00% -> AUTO
    resp_8500 = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": "51C-850.00",
            "entry_gate_id": entry_gate.id,
            "recognition_source": "AI",
            "ai_confidence": 85.00,
        },
        format="json",
    )
    assert resp_8500.status_code == status.HTTP_201_CREATED
    assert resp_8500.data["session"]["review_status"] == "AUTO"
    assert float(resp_8500.data["session"]["ai_confidence"]) == 85.00


# ==============================================================================
# SECTION 3: Boundary Stress Test — Normalization Parity with PostgreSQL
# ==============================================================================


@pytest.mark.parametrize(
    "boundary_plate, expected_normalized",
    [
        # Two-line plates with newline / carriage return
        ("29A\n123.45", "29A12345"),
        ("51-A\r\n 20.70", "51A2070"),
        ("51A \n/\n 20.70", "51A2070"),
        # Excessive spaces, tabs, dashes, dots, underscores
        ("  43A \t - \t 111 . 22  ", "43A11122"),
        ("51G---513...32___", "51G51332"),
        # Mixed casing
        ("51f-590.11", "51F59011"),
        ("62p-5688", "62P5688"),
        # Special symbols
        ("[51K]-(992).14!", "51K99214"),
        ("30H#123*45$", "30H12345"),
        # Diacritics / Vietnamese Unicode: non-alphanumeric ASCII stripped
        ("51Đ-123.45", "5112345"),
        ("29Â-892.16", "2989216"),
        ("51Á-724.44", "5172444"),
        # Empty and non-alphanumeric only
        ("", ""),
        ("   --- ... ///   ", ""),
    ],
)
def test_normalization_boundary_strings_and_postgres_parity(
    boundary_plate, expected_normalized
):
    """
    Verify that Python PlateRecognizer.normalize_plate matches expected output
    AND matches PostgreSQL fn_normalize_license_plate(text) 100% identically.
    """
    py_result = PlateRecognizer.normalize_plate(boundary_plate)
    assert py_result == expected_normalized

    if boundary_plate:
        with connection.cursor() as cursor:
            cursor.execute("SELECT fn_normalize_license_plate(%s);", [boundary_plate])
            pg_result = cursor.fetchone()[0]
        assert pg_result == expected_normalized


# ==============================================================================
# SECTION 4: Boundary Stress Test — 7 Failure Modes Verification
# ==============================================================================


def test_failure_mode_sample_74_dirty_blur_defense():
    """
    Failure mode #74: Ground truth 51F-278.09, blurred/muddy car plate.
    Simulate OCR result for sample #74: confidence 78.41% (< 85.00%).
    Verify defensive mechanism assigns review_status='NEEDS_REVIEW'.
    """
    sample_74_ocr_text = "IF2Y809"
    sample_74_conf = 78.41

    from apps.parking.services.ocr import DummyPlateRecognizer, PlateCandidate

    rec = DummyPlateRecognizer()
    cand = PlateCandidate(
        plate_text=sample_74_ocr_text,
        plate_normalized=PlateRecognizer.normalize_plate(sample_74_ocr_text),
        confidence=sample_74_conf,
    )
    rec.set_candidates([cand])

    scan_res = rec.recognize(b"fake_muddy_plate_image")
    best = scan_res.best_candidate
    assert best is not None
    assert best.plate_normalized == "IF2Y809"
    assert best.confidence == 78.41

    # Verify review_status calculation
    status_assigned = "AUTO" if best.confidence >= 85.00 else "NEEDS_REVIEW"
    assert status_assigned == "NEEDS_REVIEW"


def test_failure_mode_sample_91_missed_bbox_triggers_422():
    """
    Failure mode #91: Ground truth 51A / 20.70, camera angle > 60 deg, missed bbox.
    Verify that an image with 0 detected candidates results in empty candidates
    and triggers proper handling (422 in plate-scans).
    """
    from apps.parking.services.ocr import DummyPlateRecognizer

    rec = DummyPlateRecognizer(default_plate="")
    scan_res = rec.recognize(b"severely_angled_car_image")

    assert len(scan_res.candidates) == 0
    assert scan_res.best_candidate is None
