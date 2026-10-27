"""
Empirical Adversarial Challenge Test Suite for Milestone 3 (R3 - S3).
Author: challenger_r3 (Senior Empirical Challenger)

Adversarial Stress Dimensions:
1. Concurrency Stress:
   - 8-thread parallel vehicle creation with distinct valid civilian plates.
   - 6-thread race condition on identical vehicle plate across representation variants (casing, hyphens, spaces).
   - Race condition on duplicate custom code creation.
2. Plate Validation Stress:
   - Comprehensive rejection of motorbike formats (e.g. 59P1-678.90, 29-B1 123.45, 43A1-999.99).
   - Single character and boundary length attacks (A, 000000000000, 51, 51A, 51A12).
   - Statutory unassigned/reserved province codes per Circular 51/2025/TT-BCA (13, 42, 44, 45, 46, 87, 91, 96, 00).
   - Military plate series (TM-12.34, QA-12.34, TH-99.99).
   - Invalid civilian series letters (I, J, O, Q, R, W).
   - Full acceptance of diverse valid civilian car plates across provinces.
3. Owner Change Conflict & OCC Safety:
   - Blocked when vehicle has tickets -> 409 PROP-VEH-OWNER-CHANGE-CONFLICT (never MSG-4.3.1-M03).
   - Blocked when vehicle has open parking session without tickets -> 409 PROP-VEH-OWNER-CHANGE-CONFLICT.
   - Blocked when vehicle has active slot reservation without tickets -> 409 PROP-VEH-OWNER-CHANGE-CONFLICT.
   - Allowed when vehicle has completed/closed session and cancelled reservation -> 200 OK.
   - Stale row_version strictly returns MSG-4.3.1-M03 (OCC guard).
   - Defensive mapping of SQLSTATE 23503 / 23505.
"""

from __future__ import annotations

import threading
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import IntegrityError, connections
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer
from apps.parking.models import SlotReservation, VehicleEntryExitLog
from apps.vehicles.models import Vehicle
from apps.vehicles.services.vehicles import update_vehicle

ENDPOINT_URL = "/api/v1/vehicles/"


# =============================================================================
# 1. CONCURRENCY ADVERSARIAL STRESS TESTS
# =============================================================================


@pytest.mark.django_db(transaction=True)
def test_adversarial_concurrency_8_threads_distinct_plates(
    auth_manager, car_type, active_customer
):
    """
    Stress-test high concurrency with 8 parallel worker threads creating vehicles with distinct valid plates.
    Verifies that advisory locking serializes XE%04d code generation with zero collisions.
    """
    num_threads = 8
    barrier = threading.Barrier(num_threads)
    results = [None] * num_threads
    errors = [None] * num_threads

    plates = [f"51K-771.{i:02d}" for i in range(10, 10 + num_threads)]

    def worker(idx: int):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        try:
            barrier.wait()
            payload = {
                "license_plate": plates[idx],
                "model_name": f"Stress Model {idx}",
                "vehicle_type_id": car_type.id,
                "customer_id": active_customer.id,
            }
            results[idx] = client.post(ENDPOINT_URL, payload, format="json")
        except Exception as exc:
            errors[idx] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    created_ids = []
    try:
        assert all(err is None for err in errors), f"Thread execution errors: {errors}"
        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes == [status.HTTP_201_CREATED] * num_threads, (
            f"Expected all 201 Created: {status_codes}"
        )

        codes = [r.json()["code"] for r in results if r is not None]
        assert len(set(codes)) == num_threads, f"Duplicate codes generated: {codes}"
        for r in results:
            if r is not None and "id" in r.json():
                created_ids.append(r.json()["id"])
    finally:
        if created_ids:
            Vehicle.objects.filter(id__in=created_ids).delete()
        Vehicle.objects.filter(license_plate__in=plates).delete()


@pytest.mark.django_db(transaction=True)
def test_adversarial_concurrency_6_threads_identical_plate_representation_race(
    auth_manager, car_type, active_customer
):
    """
    Stress-test race condition where 6 concurrent threads attempt to register the exact same plate
    using disparate formatting representations: lowercase, hyphenated, space-separated, no separators, padded.
    Verifies that normalization under advisory lock ensures EXACTLY ONE 201 Created and FIVE 409 Conflicts (MSG-4.3.1-M05).
    """
    plate_variants = [
        "51K-883.77",
        "51k-883.77",
        "51K 883.77",
        "  51K-883.77  ",
        "51K88377",
        "51k883.77",
    ]
    num_threads = len(plate_variants)
    barrier = threading.Barrier(num_threads)
    results = [None] * num_threads
    errors = [None] * num_threads

    def worker(idx: int):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        try:
            barrier.wait()
            payload = {
                "license_plate": plate_variants[idx],
                "model_name": f"Race Variant {idx}",
                "vehicle_type_id": car_type.id,
                "customer_id": active_customer.id,
            }
            results[idx] = client.post(ENDPOINT_URL, payload, format="json")
        except Exception as exc:
            errors[idx] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert all(err is None for err in errors), f"Thread errors: {errors}"
        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes.count(status.HTTP_201_CREATED) == 1, (
            f"Expected exactly 1 201 Created, got: {status_codes}"
        )
        assert status_codes.count(status.HTTP_409_CONFLICT) == num_threads - 1, (
            f"Expected {num_threads - 1} 409 Conflicts, got: {status_codes}"
        )

        for r in results:
            if r is not None and r.status_code == status.HTTP_409_CONFLICT:
                assert r.json().get("code") == "MSG-4.3.1-M05"
    finally:
        Vehicle.objects.filter(license_plate_norm="51K88377").delete()


@pytest.mark.django_db(transaction=True)
def test_adversarial_concurrency_duplicate_custom_code_race(
    auth_manager, car_type, active_customer
):
    """
    Stress-test race condition where 3 threads attempt to create vehicles with the SAME custom code.
    Verifies that exactly one thread succeeds with 201 and others receive 409 MSG-4.3.1-M05.
    """
    target_code = "XE-RACE-01"
    num_threads = 3
    barrier = threading.Barrier(num_threads)
    results = [None] * num_threads
    errors = [None] * num_threads
    plates = [f"51K-772.{i:02d}" for i in range(num_threads)]

    def worker(idx: int):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        try:
            barrier.wait()
            payload = {
                "code": target_code,
                "license_plate": plates[idx],
                "model_name": f"Custom Code Car {idx}",
                "vehicle_type_id": car_type.id,
                "customer_id": active_customer.id,
            }
            results[idx] = client.post(ENDPOINT_URL, payload, format="json")
        except Exception as exc:
            errors[idx] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert all(err is None for err in errors), f"Thread errors: {errors}"
        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes.count(status.HTTP_201_CREATED) == 1
        assert status_codes.count(status.HTTP_409_CONFLICT) == num_threads - 1
        for r in results:
            if r is not None and r.status_code == status.HTTP_409_CONFLICT:
                assert r.json().get("code") == "MSG-4.3.1-M05"
    finally:
        Vehicle.objects.filter(code=target_code).delete()
        Vehicle.objects.filter(license_plate__in=plates).delete()


# =============================================================================
# 2. PLATE VALIDATION ADVERSARIAL STRESS TESTS
# =============================================================================


@pytest.mark.parametrize(
    "invalid_plate,expected_syntax_status",
    [
        # Motorbike formats (2 digits + letter + digit + 5 digits)
        ("59P1-678.90", "INVALID_FORMAT"),
        ("29-B1 123.45", "INVALID_FORMAT"),
        ("43A1-999.99", "INVALID_FORMAT"),
        ("60-F2 888.88", "INVALID_FORMAT"),
        # Single char / length boundaries
        ("A", "INVALID_FORMAT"),
        ("Z", "INVALID_FORMAT"),
        ("1", "INVALID_FORMAT"),
        ("51", "INVALID_FORMAT"),
        ("51A", "INVALID_FORMAT"),
        ("51A-1", "INVALID_FORMAT"),
        ("51A-12", "INVALID_FORMAT"),
        ("000000000000", "INVALID_FORMAT"),
        ("51A-123456789", "INVALID_FORMAT"),
        ("---", "INVALID_FORMAT"),
        ("......", "INVALID_FORMAT"),
        # Statutory unassigned / reserved province codes (Circular 51/2025/TT-BCA)
        ("13A-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("42A-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("44A-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("45A-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("46A-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("87A-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("91A-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("96A-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("00A-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("05A-123.45", "UNKNOWN_PLATE_PATTERN"),
        # Military series (2 letters + digits)
        ("TM-12.34", "UNKNOWN_PLATE_PATTERN"),
        ("QA-12.34", "UNKNOWN_PLATE_PATTERN"),
        ("TH-99.99", "UNKNOWN_PLATE_PATTERN"),
        # Invalid civilian series letters (I, J, O, Q, R, W)
        ("51I-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("51J-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("51O-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("51Q-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("51R-123.45", "UNKNOWN_PLATE_PATTERN"),
        ("51W-123.45", "UNKNOWN_PLATE_PATTERN"),
    ],
)
def test_adversarial_plate_validation_rejections(
    manager_client, car_type, active_customer, invalid_plate, expected_syntax_status
):
    """
    Adversarial verification: all weak, motorbike, reserved province, military, and non-car series plates
    MUST be rejected with HTTP 400 Bad Request and PROP-4.5.1-P16.
    """
    payload = {
        "license_plate": invalid_plate,
        "model_name": "Adversarial Probe Car",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST, (
        f"Failed for plate '{invalid_plate}': expected 400, got {response.status_code} ({response.content})"
    )
    body = response.json()
    assert body.get("code") == "PROP-4.5.1-P16"
    assert "chưa được định nghĩa trong danh mục quy chuẩn" in body.get("message", "")
    assert body.get("details", {}).get("syntax_status") == expected_syntax_status


def test_adversarial_plate_validation_empty_and_whitespace(
    manager_client, car_type, active_customer
):
    """Empty and pure whitespace plates must return 400 with PROP-GEN-P01."""
    for empty_input in ["", "   ", "\t\n"]:
        payload = {
            "license_plate": empty_input,
            "model_name": "Empty Plate Car",
            "vehicle_type_id": car_type.id,
            "customer_id": active_customer.id,
        }
        res = manager_client.post(ENDPOINT_URL, payload, format="json")
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert res.json().get("code") == "PROP-GEN-P01"


@pytest.mark.parametrize(
    "valid_plate",
    [
        "51K-888.88",  # TP.HCM modern 5-digit civilian car
        "30H-123.45",  # Hà Nội modern 5-digit civilian car
        "43A-1234",  # Đà Nẵng legacy 4-digit civilian car
        "29A-999.99",  # Hà Nội 5-digit civilian car
        "60A-123.45",  # Đồng Nai 5-digit civilian car
        "50LD-123.45",  # Joint venture dual-letter series
        "80NG-123.45",  # Diplomatic dual-letter series
    ],
)
def test_adversarial_plate_validation_accepts_valid_civilian_cars(
    manager_client, car_type, active_customer, valid_plate
):
    """
    Adversarial verification: all statutory valid civilian car plates
    MUST be accepted and return HTTP 201 Created.
    """
    payload = {
        "license_plate": valid_plate,
        "model_name": "Valid Civilian Car",
        "vehicle_type_id": car_type.id,
        "customer_id": active_customer.id,
    }
    response = manager_client.post(ENDPOINT_URL, payload, format="json")
    try:
        assert response.status_code == status.HTTP_201_CREATED, (
            f"Valid plate '{valid_plate}' was unexpectedly rejected: {response.content}"
        )
        assert response.json()["license_plate"] == valid_plate
    finally:
        Vehicle.objects.filter(license_plate=valid_plate).delete()


# =============================================================================
# 3. OWNER CHANGE CONFLICT & OCC SAFETY ADVERSARIAL TESTS
# =============================================================================


def test_adversarial_owner_change_blocked_by_tickets(manager_client):
    """
    K4: Vehicle with existing tickets cannot change owner (customer_id).
    Must return 409 Conflict with PROP-VEH-OWNER-CHANGE-CONFLICT (never MSG-4.3.1-M03).
    """
    v = Vehicle.objects.filter(deleted_at__isnull=True, tickets__isnull=False).first()
    assert v is not None, "Need seed vehicle with tickets"

    new_cust = Customer.objects.create(
        code="KH-ADV-01",
        full_name="Chủ Mới Probe 1",
        phone="0918001122",
        identity_card_number="049090999001",
    )

    try:
        payload = {"row_version": v.row_version, "customer_id": new_cust.id}
        res = manager_client.patch(f"{ENDPOINT_URL}{v.id}/", payload, format="json")
        assert res.status_code == status.HTTP_409_CONFLICT
        body = res.json()
        assert body.get("code") == "PROP-VEH-OWNER-CHANGE-CONFLICT"
        assert body.get("code") != "MSG-4.3.1-M03"
        assert "Không thể thay đổi chủ sở hữu" in body.get("message", "")
        assert body.get("details", {}).get("has_tickets") is True
    finally:
        new_cust.delete()


def test_adversarial_owner_change_blocked_by_open_session_without_tickets(
    manager_client, car_type, active_customer
):
    """
    K4: Vehicle with an OPEN parking session (no tickets) cannot change owner.
    Must return 409 Conflict with PROP-VEH-OWNER-CHANGE-CONFLICT (never MSG-4.3.1-M03).
    """
    from apps.vehicles.services.vehicles import create_vehicle

    v = create_vehicle(
        license_plate="51K-773.01",
        model_name="Session Probe Car",
        vehicle_type_id=car_type.id,
        customer_id=active_customer.id,
    )
    assert v.tickets.count() == 0

    VehicleEntryExitLog.objects.create(
        session_code="SES-ADV-01",
        vehicle=v,
        license_plate=v.license_plate,
        entry_time=timezone.now() - timedelta(hours=1),
        exit_time=None,  # Open session
    )

    new_cust = Customer.objects.create(
        code="KH-ADV-02",
        full_name="Chủ Mới Probe 2",
        phone="0918001133",
        identity_card_number="049090999002",
    )

    payload = {"row_version": v.row_version, "customer_id": new_cust.id}
    res = manager_client.patch(f"{ENDPOINT_URL}{v.id}/", payload, format="json")
    assert res.status_code == status.HTTP_409_CONFLICT
    body = res.json()
    assert body.get("code") == "PROP-VEH-OWNER-CHANGE-CONFLICT"
    assert body.get("code") != "MSG-4.3.1-M03"
    assert body.get("details", {}).get("has_open_session") is True


def test_adversarial_owner_change_blocked_by_active_reservation_without_tickets(
    manager_client, active_customer
):
    """
    K4: Vehicle with an ACTIVE slot reservation (no tickets) cannot change owner.
    Must return 409 Conflict with PROP-VEH-OWNER-CHANGE-CONFLICT (never MSG-4.3.1-M03).
    """
    # XE0026 is an active vehicle with 0 tickets in seed
    v = Vehicle.objects.get(code="XE0026")
    assert v.tickets.count() == 0

    # Attach RSV-2026-0003 to XE0026 as ACTIVE reservation
    rsv = SlotReservation.objects.get(code="RSV-2026-0003")
    rsv.vehicle = v
    rsv.status = "ACTIVE"
    rsv.reserved_until = timezone.now() + timedelta(hours=4)
    rsv.save(update_fields=["vehicle", "status", "reserved_until"])

    new_cust = Customer.objects.create(
        code="KH-ADV-03",
        full_name="Chủ Mới Probe 3",
        phone="0918001144",
        identity_card_number="049090999003",
    )

    payload = {"row_version": v.row_version, "customer_id": new_cust.id}
    res = manager_client.patch(f"{ENDPOINT_URL}{v.id}/", payload, format="json")
    assert res.status_code == status.HTTP_409_CONFLICT
    body = res.json()
    assert body.get("code") == "PROP-VEH-OWNER-CHANGE-CONFLICT"
    assert body.get("code") != "MSG-4.3.1-M03"
    assert body.get("details", {}).get("has_active_reservation") is True


def test_adversarial_owner_change_allowed_when_session_closed_and_reservation_cancelled(
    manager_client, car_type, active_customer
):
    """
    K4: Vehicle with CLOSED parking session and CANCELLED reservation (no active tickets)
    CAN safely change owner -> 200 OK.
    """
    from apps.vehicles.services.vehicles import create_vehicle

    v = create_vehicle(
        license_plate="51K-773.03",
        model_name="Completed Probe Car",
        vehicle_type_id=car_type.id,
        customer_id=active_customer.id,
    )

    # Completed session
    VehicleEntryExitLog.objects.create(
        session_code="SES-ADV-02",
        vehicle=v,
        license_plate=v.license_plate,
        entry_time=timezone.now() - timedelta(hours=5),
        exit_time=timezone.now() - timedelta(hours=2),
    )

    # Cancelled reservation (attach to RSV-2026-0005 which is CANCELLED in seed)
    rsv = SlotReservation.objects.get(code="RSV-2026-0005")
    rsv.vehicle = v
    rsv.status = "CANCELLED"
    rsv.save(update_fields=["vehicle", "status"])

    new_cust = Customer.objects.create(
        code="KH-ADV-04",
        full_name="Chủ Mới Hợp Lệ 4",
        phone="0918001155",
        identity_card_number="049090999004",
    )

    payload = {"row_version": v.row_version, "customer_id": new_cust.id}
    res = manager_client.patch(f"{ENDPOINT_URL}{v.id}/", payload, format="json")
    assert res.status_code == status.HTTP_200_OK
    assert res.json()["customer"]["id"] == new_cust.id

    v.refresh_from_db()
    assert v.customer_id == new_cust.id


def test_adversarial_stale_row_version_strictly_returns_m03(manager_client):
    """
    OCC Safety: A mismatch in row_version must strictly return MSG-4.3.1-M03
    and NEVER return PROP-VEH-OWNER-CHANGE-CONFLICT.
    """
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    payload = {
        "row_version": v.row_version + 99,  # Stale version
        "color": "Tím Than",
    }
    res = manager_client.patch(f"{ENDPOINT_URL}{v.id}/", payload, format="json")
    assert res.status_code == status.HTTP_409_CONFLICT
    body = res.json()
    assert body.get("code") == "MSG-4.3.1-M03"
    assert "Dữ liệu hiện đang được cập nhật bởi user khác" in body.get("message", "")
    assert body.get("code") != "PROP-VEH-OWNER-CHANGE-CONFLICT"


def test_adversarial_defensive_db_exception_mapping_23503(active_customer):
    """
    Defensive DB Exception Mapping:
    Verifies that if PostgreSQL raises SQLSTATE 23503 on fk_ticket_vehicle_customer during save(),
    update_vehicle() cleanly maps it to 409 PROP-VEH-OWNER-CHANGE-CONFLICT instead of MSG-4.3.1-M03.
    """
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()

    fake_db_error = IntegrityError(
        'update on table "vehicle" violates foreign key constraint "fk_ticket_vehicle_customer" on table "ticket"'
    )

    with patch.object(Vehicle, "save", side_effect=fake_db_error):
        with pytest.raises(BusinessAPIException) as exc_info:
            update_vehicle(
                vehicle=v,
                data={"row_version": v.row_version, "customer_id": active_customer.id},
            )
        assert exc_info.value.code == "PROP-VEH-OWNER-CHANGE-CONFLICT"
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert exc_info.value.code != "MSG-4.3.1-M03"
