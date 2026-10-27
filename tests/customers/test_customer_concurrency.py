"""
Concurrency tests for Customer Management API (POST /api/v1/customers/).
Verifies race condition safety across concurrent PostgreSQL database transactions:
1. N concurrent threads creating customers with distinct identities:
   - All N succeed (HTTP 201 Created).
   - Advisory lock pg_advisory_xact_lock(hashtext('customer_code_sequence')) prevents collision
     on max_num + 1 code generation (uq_customer_code_active).
   - All N receive distinct sequential KH%04d codes.
2. Concurrent threads attempting to create customers with identical CCCD (identity_card_number):
   - Exactly one thread succeeds (HTTP 201 Created).
   - Remaining threads receive HTTP 409 Conflict with code MSG-4.3.1-M05.
   - PII (CCCD) is never echoed in error response.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from django.db import connections
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account

ENDPOINT_URL = "/api/v1/customers/"


@pytest.mark.django_db(transaction=True)
def test_concurrent_customer_create_distinct_codes(auth_manager: Account):
    """
    N parallel threads creating customers with distinct valid CCCD and phone.
    Without advisory lock, threads collide on max_num + 1 code generation (uq_customer_code_active).
    With pg_advisory_xact_lock, all N succeed with sequential distinct codes.
    """
    num_threads = 4
    barrier = threading.Barrier(num_threads)
    results: list[Any] = [None] * num_threads
    errors: list[Exception | None] = [None] * num_threads

    cccds = [f"0792008811{i:02d}" for i in range(num_threads)]
    phones = [f"09188811{i:02d}" for i in range(num_threads)]

    def worker(idx: int):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        try:
            barrier.wait()
            payload = {
                "full_name": f"Concurrent Customer {idx}",
                "identity_card_number": cccds[idx],
                "phone": phones[idx],
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

    assert all(err is None for err in errors), f"Thread exceptions: {errors}"
    status_codes = [r.status_code for r in results if r is not None]
    assert status_codes == [status.HTTP_201_CREATED] * num_threads, (
        f"Status codes: {status_codes}, bodies: {[r.json() for r in results if r is not None]}"
    )

    codes = [r.json()["code"] for r in results if r is not None]
    assert len(set(codes)) == num_threads, f"Duplicate codes generated: {codes}"
    for c in codes:
        assert c.startswith("KH"), f"Invalid code format: {c}"


@pytest.mark.django_db(transaction=True)
def test_concurrent_customer_create_identical_cccd_race(auth_manager: Account):
    """
    N parallel threads attempting to create a customer with the EXACT same CCCD.
    Under concurrency, exactly one must receive 201 Created and others 409 Conflict (MSG-4.3.1-M05).
    """
    num_threads = 3
    barrier = threading.Barrier(num_threads)
    results: list[Any] = [None] * num_threads
    errors: list[Exception | None] = [None] * num_threads
    target_cccd = "079200994433"

    def worker(idx: int):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        try:
            barrier.wait()
            payload = {
                "full_name": f"Race Customer {idx}",
                "identity_card_number": target_cccd,
                "phone": f"09177722{idx:02d}",
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

    assert all(err is None for err in errors), f"Thread exceptions: {errors}"
    status_codes = [r.status_code for r in results if r is not None]
    assert status_codes.count(status.HTTP_201_CREATED) == 1, (
        f"Expected exactly one 201: {status_codes}, bodies: {[r.json() for r in results if r is not None]}"
    )
    assert status_codes.count(status.HTTP_409_CONFLICT) == num_threads - 1, (
        f"Expected {num_threads - 1} 409s: {status_codes}"
    )

    for r in results:
        if r is not None and r.status_code == status.HTTP_409_CONFLICT:
            assert r.json().get("code") == "MSG-4.3.1-M05"
            assert target_cccd not in str(r.json())
