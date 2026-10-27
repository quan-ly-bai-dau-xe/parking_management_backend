"""
Concurrency tests for Vehicle Management API (create_vehicle / POST /api/v1/vehicles/).
Verifies race condition safety:
1. N concurrent threads creating vehicles with distinct license plates:
   - All N succeed (HTTP 201 Created)
   - All N receive distinct auto-generated XE%04d codes (no collision on uq_vehicle_code_active).
2. Concurrent threads attempting to create vehicles with the identical license plate:
   - Exactly one thread succeeds (HTTP 201 Created)
   - Remaining threads receive HTTP 409 Conflict with code MSG-4.3.1-M05.
"""

import threading

import pytest
from django.db import connections
from rest_framework import status
from rest_framework.test import APIClient

from apps.vehicles.models import Vehicle

ENDPOINT_URL = "/api/v1/vehicles/"


@pytest.mark.django_db(transaction=True)
def test_concurrent_vehicle_create_distinct_codes(
    auth_manager, car_type, active_customer
):
    """
    N parallel threads creating vehicles with distinct valid plates.
    Without advisory lock, threads collide on max_num + 1 code generation (uq_vehicle_code_active).
    With pg_advisory_xact_lock, all N succeed with sequential distinct codes.
    """
    num_threads = 4
    barrier = threading.Barrier(num_threads)
    results = [None] * num_threads
    errors = [None] * num_threads

    plates = [f"51K-881.{i:02d}" for i in range(10, 10 + num_threads)]

    def worker(idx: int):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        try:
            barrier.wait()
            payload = {
                "license_plate": plates[idx],
                "model_name": f"Concurrent Model {idx}",
                "vehicle_type_id": car_type.id,
                "customer_id": active_customer.id,
            }
            res = client.post(ENDPOINT_URL, payload, format="json")
            results[idx] = res
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
        assert all(err is None for err in errors), f"Thread exceptions: {errors}"
        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes == [status.HTTP_201_CREATED] * num_threads, (
            f"Status codes: {status_codes}, bodies: {[r.json() for r in results if r is not None]}"
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
def test_concurrent_vehicle_create_identical_plate_race(
    auth_manager, car_type, active_customer
):
    """
    N parallel threads attempting to create a vehicle with the EXACT same license plate.
    Under concurrency, exactly one must receive 201 Created and others 409 Conflict (MSG-4.3.1-M05).
    """
    num_threads = 3
    barrier = threading.Barrier(num_threads)
    results = [None] * num_threads
    errors = [None] * num_threads
    target_plate = "51K-882.99"

    def worker(idx: int):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        try:
            barrier.wait()
            payload = {
                "license_plate": target_plate,
                "model_name": f"Race Car {idx}",
                "vehicle_type_id": car_type.id,
                "customer_id": active_customer.id,
            }
            res = client.post(ENDPOINT_URL, payload, format="json")
            results[idx] = res
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
        assert all(err is None for err in errors), f"Thread exceptions: {errors}"
        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes.count(status.HTTP_201_CREATED) == 1, (
            f"Expected exactly one 201: {status_codes}, bodies: {[r.json() for r in results if r is not None]}"
        )
        assert status_codes.count(status.HTTP_409_CONFLICT) == num_threads - 1, (
            f"Expected {num_threads - 1} 409s: {status_codes}"
        )

        # Verify 409 response codes are MSG-4.3.1-M05
        for r in results:
            if r is not None and r.status_code == status.HTTP_409_CONFLICT:
                assert r.json().get("code") == "MSG-4.3.1-M05", (
                    f"Unexpected error body: {r.json()}"
                )
    finally:
        Vehicle.objects.filter(license_plate=target_plate).delete()
