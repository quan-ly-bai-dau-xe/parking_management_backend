"""
Tests for Parking Slot endpoints and Parking Session PATCH slot assignment.
- GET /api/v1/parking/slots/
- GET /api/v1/parking/slots/<int:pk>/
- PATCH /api/v1/parking/slots/<int:pk>/
- PATCH /api/v1/parking/sessions/<int:pk>/
"""

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.parking.models import (
    ParkingFloor,
    ParkingLot,
    ParkingSlot,
    ParkingZone,
    VehicleEntryExitLog,
)


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def operator_account(db):
    account, _ = Account.objects.get_or_create(
        email="operator_test@parking.local",
        defaults={
            "phone": "0987654321",
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return account


@pytest.fixture
def parking_setup(db):
    lot = ParkingLot.objects.create(code="LOT_01", name="Smart Mobility Parking")
    floor = ParkingFloor.objects.create(lot=lot, code="B1", name="Tầng B1", sort_order=1)
    zone = ParkingZone.objects.create(floor=floor, code="A", name="Khu A")
    slot1 = ParkingSlot.objects.create(
        zone=zone, code="A-01", slot_kind="STANDARD", status="AVAILABLE"
    )
    slot2 = ParkingSlot.objects.create(
        zone=zone, code="A-02", slot_kind="STANDARD", status="AVAILABLE"
    )
    return {
        "lot": lot,
        "floor": floor,
        "zone": zone,
        "slot1": slot1,
        "slot2": slot2,
    }


@pytest.mark.django_db
def test_get_slots_list(api_client, operator_account, parking_setup):
    api_client.force_authenticate(user=operator_account)
    response = api_client.get("/api/v1/parking/slots/")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) >= 2
    codes = [item["code"] for item in data]
    assert "A-01" in codes
    assert "A-02" in codes


@pytest.mark.django_db
def test_filter_slots_by_floor_and_status(api_client, operator_account, parking_setup):
    api_client.force_authenticate(user=operator_account)
    slot1 = parking_setup["slot1"]
    slot1.status = "MAINTENANCE"
    slot1.save()

    response = api_client.get(f"/api/v1/parking/slots/?floor=B1&status=MAINTENANCE&search={slot1.code}")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data) == 1
    assert data[0]["code"] == slot1.code
    assert data[0]["status"] == "MAINTENANCE"


@pytest.mark.django_db
def test_update_slot_status(api_client, operator_account, parking_setup):
    api_client.force_authenticate(user=operator_account)
    slot1 = parking_setup["slot1"]

    response = api_client.patch(
        f"/api/v1/parking/slots/{slot1.id}/",
        data={"status": "MAINTENANCE", "notes": "Đang bảo dưỡng đèn"},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "MAINTENANCE"
    assert data["notes"] == "Đang bảo dưỡng đèn"

    slot1.refresh_from_db()
    assert slot1.status == "MAINTENANCE"


@pytest.mark.django_db
def test_patch_session_slot_assignment(api_client, operator_account, parking_setup):
    api_client.force_authenticate(user=operator_account)
    slot1 = parking_setup["slot1"]
    slot2 = parking_setup["slot2"]

    session = VehicleEntryExitLog.objects.create(
        session_code="PK-TEST-001",
        license_plate="51K-123.45",
        slot=slot1,
    )
    slot1.status = "OCCUPIED"
    slot1.save()

    # Re-assign slot to slot2
    response = api_client.patch(
        f"/api/v1/parking/sessions/{session.id}/",
        data={"slot_id": slot2.id},
        format="json",
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["slot_id"] == slot2.id

    session.refresh_from_db()
    slot1.refresh_from_db()
    slot2.refresh_from_db()

    assert session.slot_id == slot2.id
    # slot1 should be released back to AVAILABLE
    assert slot1.status == "AVAILABLE"
    # slot2 should be OCCUPIED
    assert slot2.status == "OCCUPIED"
