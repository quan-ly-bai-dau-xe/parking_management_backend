"""
Flow reproduction and regression test suite for Milestone 2 & Requirement 2.

Verifies the complete parking session lifecycle for demo vehicle 51A-897.14:
1. Plate scan API is strictly non-mutating (read-only for database records).
2. Plate scan of demo vehicle 51A-897.14 identifies registered vehicle XE0031,
   customer KH0021 ("Khách Hàng Demo"), blacklist=False, open_session=None.
3. Check-in (POST /api/v1/parking/sessions/check-in/) creates an active session
   linked to XE0031.
4. Active session appears immediately in session history list (GET /api/v1/parking/sessions/).
5. Check-out (POST /api/v1/parking/sessions/check-out/) closes the session cleanly
   and restores the open_session=None invariant.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.models import ParkingGate, ParkingLot, VehicleEntryExitLog
from apps.parking.services.ocr import DummyPlateRecognizer, set_global_recognizer
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


def _create_jpeg_file(name: str = "demo_scan.jpg") -> SimpleUploadedFile:
    """Create in-memory JPEG image to satisfy multipart upload requirements."""
    buf = io.BytesIO()
    img = Image.new("RGB", (320, 180), color="white")
    img.save(buf, format="JPEG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/jpeg")


@pytest.fixture
def auth_employee() -> Account:
    """Provide authenticated employee account for operator endpoint calls."""
    emp, _ = Account.objects.get_or_create(
        email="operator_reproduction@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def parking_facility() -> ParkingLot:
    """Ensure baseline parking facility exists for gate relationships."""
    lot, _ = ParkingLot.objects.get_or_create(
        code="SMART_MOBILITY",
        defaults={
            "name": "Bãi xe Smart Mobility",
            "is_active": True,
        },
    )
    return lot


@pytest.fixture
def entry_gate(parking_facility: ParkingLot) -> ParkingGate:
    """
    Ensure gate with ID=1 exists and direction is IN per R2 / M2 specification.
    Preserves existing gate 1 if already seeded by db/02-seed.sql.
    """
    gate = ParkingGate.objects.filter(id=1).first()
    if gate is not None:
        if gate.direction != "IN" or not gate.is_active:
            gate.direction = "IN"
            gate.is_active = True
            gate.save(update_fields=["direction", "is_active"])
        return gate

    return ParkingGate.objects.create(
        id=1,
        lot=parking_facility,
        code="IN_01",
        name="Cổng vào 1",
        direction="IN",
        camera_status="ONLINE",
        is_auto_scan=True,
        is_active=True,
    )


@pytest.fixture
def exit_gate(parking_facility: ParkingLot) -> ParkingGate:
    """Ensure an active OUT gate exists for check-out testing."""
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if gate is not None:
        return gate

    return ParkingGate.objects.create(
        lot=parking_facility,
        code="OUT_01",
        name="Cổng ra 1",
        direction="OUT",
        camera_status="ONLINE",
        is_auto_scan=True,
        is_active=True,
    )


@pytest.fixture
def demo_vehicle() -> Vehicle:
    """
    Ensure demo vehicle XE0031 with plate 51A-897.14 and customer KH0021 exist.
    Normal seed loading provides both; fallback ensures test independence.
    """
    car_type, _ = VehicleType.objects.get_or_create(
        code="CAR",
        defaults={"name": "Ô tô", "description": "Standard passenger automobile"},
    )
    customer, _ = Customer.objects.get_or_create(
        code="KH0021",
        defaults={
            "full_name": "Khách Hàng Demo",
            "phone": "0909897140",
            "email": "demo.khachhang@example.com",
            "identity_card_number": "048099999999",
            "status": "ACTIVE",
            "account_id": None,
        },
    )
    vehicle, _ = Vehicle.objects.get_or_create(
        code="XE0031",
        defaults={
            "license_plate": "51A-897.14",
            "model_name": "Vios",
            "brand": "Toyota",
            "color": "Bạc",
            "vehicle_type": car_type,
            "customer": customer,
        },
    )
    return vehicle


@pytest.fixture(autouse=True)
def configure_ocr_engine(monkeypatch: pytest.MonkeyPatch):
    """Bypass external OCR and cloud calls using dummy recognizer for test isolation."""
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    recognizer = DummyPlateRecognizer(
        default_plate="51A-897.14", default_confidence=98.5
    )
    set_global_recognizer(recognizer)
    yield
    set_global_recognizer(None)


def test_plate_scan_demo_vehicle_lookup_and_non_mutation(
    auth_employee: Account,
    demo_vehicle: Vehicle,
    entry_gate: ParkingGate,
):
    """
    Objective 2.a & 2.b:
    Scan demo vehicle 51A-897.14 and verify:
    - Registered vehicle XE0031 details returned
    - Owner KH0021 ("Khách Hàng Demo") returned
    - blacklist=False, open_session=None
    - Strict non-mutation: VehicleEntryExitLog count remains identical.
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    count_before = VehicleEntryExitLog.objects.count()

    response = client.post(
        "/api/v1/parking/plate-scans/",
        {
            "image": _create_jpeg_file(),
            "gate_id": entry_gate.id,
            "preview": True,
        },
        format="multipart",
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.data

    # Verify non-mutation invariant
    assert VehicleEntryExitLog.objects.count() == count_before

    # Verify normalized plate & root fields
    assert data["plate_raw"] == "51A-897.14"
    assert data["plate_final"] == "51A89714"
    assert data["is_blacklisted"] is False
    assert data["open_session"] is None

    # Verify vehicle lookup details
    lookup: dict[str, Any] = data["vehicle_lookup"]
    assert lookup is not None
    assert lookup["vehicle"]["code"] == "XE0031"
    assert lookup["vehicle"]["license_plate"] == "51A-897.14"
    assert lookup["vehicle"]["license_plate_norm"] == "51A89714"
    assert lookup["vehicle"]["brand"] == "Toyota"
    assert lookup["vehicle"]["model_name"] == "Vios"
    assert lookup["vehicle"]["color"] == "Bạc"
    assert lookup["vehicle"]["vehicle_type_code"] == "CAR"

    # Verify owner details
    assert lookup["customer"]["code"] == "KH0021"
    assert lookup["customer"]["full_name"] == "Khách Hàng Demo"
    assert lookup["customer"]["is_anonymized"] is False

    # Verify auxiliary state
    assert lookup["is_blacklisted"] is False
    assert lookup["open_session"] is None


def test_full_history_reproduction_flow(
    auth_employee: Account,
    demo_vehicle: Vehicle,
    entry_gate: ParkingGate,
    exit_gate: ParkingGate,
):
    """
    Objective 2.a through 2.e:
    Execute the entire camera scan -> check-in -> list sessions -> check-out lifecycle:
    1. Plate scan detects plate without creating any session record.
    2. POST /api/v1/parking/sessions/check-in/ creates an active session.
    3. GET /api/v1/parking/sessions/ returns the newly created session.
    4. POST /api/v1/parking/sessions/check-out/ closes the session properly.
    5. Plate scan confirms open_session is reset to None.
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # -------------------------------------------------------------------------
    # Step 1: Plate scan of 51A-897.14 (Read-only verification)
    # -------------------------------------------------------------------------
    count_init = VehicleEntryExitLog.objects.count()

    scan_res = client.post(
        "/api/v1/parking/plate-scans/",
        {
            "image": _create_jpeg_file(),
            "gate_id": entry_gate.id,
            "preview": False,
        },
        format="multipart",
    )
    assert scan_res.status_code == status.HTTP_200_OK
    scan_data = scan_res.data

    assert scan_data["plate_final"] == "51A89714"
    assert scan_data["open_session"] is None
    assert scan_data["is_blacklisted"] is False
    assert scan_data["vehicle_lookup"]["vehicle"]["code"] == "XE0031"
    assert scan_data["vehicle_lookup"]["customer"]["code"] == "KH0021"

    # Invariant: scan creates zero session records
    assert VehicleEntryExitLog.objects.count() == count_init

    # -------------------------------------------------------------------------
    # Step 2: Check-in vehicle via POST /api/v1/parking/sessions/check-in/
    # -------------------------------------------------------------------------
    check_in_payload = {
        "license_plate": "51A-897.14",
        "entry_gate_id": entry_gate.id,
        "recognition_source": "AI",
        "ai_confidence": 98.5,
    }
    check_in_res = client.post(
        "/api/v1/parking/sessions/check-in/",
        check_in_payload,
        format="json",
    )
    assert check_in_res.status_code == status.HTTP_201_CREATED
    ci_data = check_in_res.data["session"]
    session_code: str = ci_data["session_code"]

    assert session_code.startswith("#PK-")
    assert ci_data["license_plate"] == "51A-897.14"
    assert ci_data["license_plate_norm"] == "51A89714"
    assert ci_data["recognition_source"] == "AI"
    assert float(ci_data["ai_confidence"]) == 98.50
    assert ci_data["review_status"] == "AUTO"
    assert ci_data["exit_time"] is None

    # Exactly one new session record committed to DB
    assert VehicleEntryExitLog.objects.count() == count_init + 1
    db_session = VehicleEntryExitLog.objects.get(session_code=session_code)
    assert db_session.vehicle_id == demo_vehicle.id
    assert db_session.entry_gate_id == entry_gate.id

    # -------------------------------------------------------------------------
    # Step 3: Verify session is visible in GET /api/v1/parking/sessions/
    # -------------------------------------------------------------------------
    list_res = client.get(
        "/api/v1/parking/sessions/",
        {"license_plate": "51A89714", "status": "open"},
    )
    assert list_res.status_code == status.HTTP_200_OK
    list_data = list_res.data

    matched_sessions = [
        s for s in list_data["results"] if s["session_code"] == session_code
    ]
    assert len(matched_sessions) == 1
    item = matched_sessions[0]
    assert item["license_plate"] == "51A-897.14"
    assert item["exit_time"] is None
    assert item["customer_name"] == "Khách Hàng Demo"
    assert item["vehicle_model"] == "Vios"
    assert item["vehicle_brand"] == "Toyota"
    assert item["entry_gate_name"] == entry_gate.name

    # Intermediate verification: Plate scan now reports active open_session
    scan_open_res = client.post(
        "/api/v1/parking/plate-scans/",
        {
            "image": _create_jpeg_file(),
            "gate_id": entry_gate.id,
            "preview": True,
        },
        format="multipart",
    )
    assert scan_open_res.status_code == status.HTTP_200_OK
    assert scan_open_res.data["open_session"] is not None
    assert scan_open_res.data["open_session"]["session_code"] == session_code

    # -------------------------------------------------------------------------
    # Step 4: Check-out vehicle via POST /api/v1/parking/sessions/check-out/
    # -------------------------------------------------------------------------
    check_out_payload = {
        "session_code": session_code,
        "exit_gate_id": exit_gate.id,
        "payment_method": "CASH",
        "notes": "Check-out hoàn tất cho xe demo",
    }
    check_out_res = client.post(
        "/api/v1/parking/sessions/check-out/",
        check_out_payload,
        format="json",
    )
    assert check_out_res.status_code == status.HTTP_200_OK
    co_data = check_out_res.data["session"]

    assert co_data["session_code"] == session_code
    assert co_data["exit_time"] is not None
    assert co_data["exit_gate_name"] == exit_gate.name

    # -------------------------------------------------------------------------
    # Step 5: Verify session is closed in listing and open_session is reset
    # -------------------------------------------------------------------------
    db_session.refresh_from_db()
    assert db_session.exit_time is not None
    assert db_session.exit_gate_id == exit_gate.id

    # Verify no open session exists for this plate in DB
    assert not VehicleEntryExitLog.objects.filter(
        license_plate_norm="51A89714", exit_time__isnull=True
    ).exists()

    # Plate scan now reports open_session=None again
    scan_after_res = client.post(
        "/api/v1/parking/plate-scans/",
        {
            "image": _create_jpeg_file(),
            "gate_id": entry_gate.id,
            "preview": True,
        },
        format="multipart",
    )
    assert scan_after_res.status_code == status.HTTP_200_OK
    assert scan_after_res.data["open_session"] is None
