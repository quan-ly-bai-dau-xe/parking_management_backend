"""
PostgreSQL Advisory Locks and Concurrency Stress Testing Suite.

Verifies:
1. Zero deadlocks (PostgreSQL error 40P01) under barrier-synchronized concurrency bursts.
2. 100% unique session codes generated under pg_advisory_xact_lock(20555, YYYYMMDD).
3. Strict transaction isolation: racing checkout on same session allows exactly 1 winner, N-1 409 conflicts.
4. Deterministic repeatability with dynamic license plates (zero residual open sessions).
"""

from __future__ import annotations

import datetime
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from django.apps import apps
from django.db import connections
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient


@pytest.mark.django_db(transaction=True)
class TestAdvisoryLocksConcurrencyStress:
    """
    Concurrency Stress Testing for PostgreSQL Advisory Locks and select_for_update.
    Proves:
    1. Zero deadlocks (PostgreSQL error 40P01) under barrier-synchronized concurrency bursts.
    2. 100% unique session codes generated under pg_advisory_xact_lock(20555, YYYYMMDD).
    3. Strict transaction isolation: racing checkout on same session allows exactly 1 winner, N-1 409 conflicts.
    4. Deterministic repeatability with dynamic license plates (zero residual open sessions).
    """

    @pytest.fixture
    def test_environment(self) -> dict[str, Any]:
        from apps.accounts.models import Account
        from apps.parking.models import ParkingGate, ParkingLot

        emp, _ = Account.objects.get_or_create(
            email="adv_stress_emp@parking.local",
            defaults={"role": "EMPLOYEE", "is_active": True, "password": "!dummy"},
        )
        lot = ParkingLot.objects.first()
        if not lot:
            lot = ParkingLot.objects.create(code="LOT-ADV", name="Adversarial Lot")
        in_g = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        if not in_g:
            in_g = ParkingGate.objects.create(
                lot=lot,
                code="GATE-IN",
                name="Adv Gate IN",
                direction="IN",
                is_active=True,
            )
        out_g = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
        if not out_g:
            out_g = ParkingGate.objects.create(
                lot=lot,
                code="GATE-OUT",
                name="Adv Gate OUT",
                direction="OUT",
                is_active=True,
            )

        return {"user": emp, "in_gate": in_g, "out_gate": out_g}

    def test_advisory_lock_burst_concurrency_with_dynamic_plates(
        self, test_environment: dict[str, Any]
    ) -> None:
        """
        Stress test: 3 bursts of 20 concurrent threads (60 check-ins total)
        calling check-in under transactional advisory lock.
        Proves: 60/60 return 201, 60/60 session codes unique, 0 lock contention deadlocks.
        """
        EntryExitLog = apps.get_model("parking", "VehicleEntryExitLog")
        emp = test_environment["user"]
        in_gate = test_environment["in_gate"]

        threads_per_burst = 20
        bursts = 3
        all_codes: list[str] = []
        created_session_codes: list[str] = []

        try:
            for burst_idx in range(bursts):
                barrier = threading.Barrier(threads_per_burst)
                burst_results: list[tuple[int, dict[str, Any]]] = []

                def worker_checkin(
                    plate_str: str, b: threading.Barrier = barrier
                ) -> tuple[int, dict[str, Any]]:
                    try:
                        c = APIClient()
                        c.force_authenticate(user=emp)
                        b.wait()
                        resp = c.post(
                            "/api/v1/parking/sessions/check-in/",
                            {
                                "license_plate": plate_str,
                                "entry_gate_id": in_gate.id,
                                "recognition_source": "MANUAL",
                            },
                            format="json",
                        )
                        return resp.status_code, getattr(resp, "data", {})
                    finally:
                        connections.close_all()

                run_seed = uuid.uuid4().hex[:6].upper()
                plates = [
                    f"51B-{run_seed}-{burst_idx:02d}{i:02d}.99"
                    for i in range(threads_per_burst)
                ]

                with ThreadPoolExecutor(max_workers=threads_per_burst) as executor:
                    futures = [executor.submit(worker_checkin, p) for p in plates]
                    for f in futures:
                        burst_results.append(f.result())

                statuses = [r[0] for r in burst_results]
                assert statuses.count(status.HTTP_201_CREATED) == threads_per_burst, (
                    f"Burst {burst_idx} had non-201 check-ins: {burst_results}"
                )

                for _, data in burst_results:
                    code = data["session"]["session_code"]
                    assert code.startswith("#PK-")
                    all_codes.append(code)
                    created_session_codes.append(code)

            # Uniqueness verification
            assert len(all_codes) == bursts * threads_per_burst
            assert len(set(all_codes)) == len(all_codes), (
                "Session codes must be 100% unique!"
            )
        finally:
            # Defensive hygiene: close all open sessions so no residual unclosed sessions remain
            EntryExitLog.objects.filter(session_code__in=created_session_codes).update(
                exit_time=timezone.now()
            )

    def test_racing_checkout_under_20_threads(
        self, test_environment: dict[str, Any]
    ) -> None:
        """
        Adversarial test: 20 threads simultaneously race to checkout the EXACT SAME session.
        Proves:
        - 0 Deadlocks (PostgreSQL error 40P01).
        - Exactly 1 thread succeeds (200 OK).
        - Exactly 19 threads receive 409 Conflict with code PROP-4.5.1-P10.
        - Exactly 1 Payment record created.
        """
        EntryExitLog = apps.get_model("parking", "VehicleEntryExitLog")
        Payment = apps.get_model("tickets", "Payment")
        emp = test_environment["user"]
        in_gate = test_environment["in_gate"]
        out_gate = test_environment["out_gate"]

        # 1. Create a session to race on
        client = APIClient()
        client.force_authenticate(user=emp)
        racing_plate = f"65A-{uuid.uuid4().hex[:6].upper()}.77"

        res_in = client.post(
            "/api/v1/parking/sessions/check-in/",
            {
                "license_plate": racing_plate,
                "entry_gate_id": in_gate.id,
                "recognition_source": "MANUAL",
            },
            format="json",
        )
        assert res_in.status_code == status.HTTP_201_CREATED
        session_code = res_in.data["session"]["session_code"]

        # Backdate entry time to accrue a fee
        EntryExitLog.objects.filter(session_code=session_code).update(
            entry_time=timezone.now() - datetime.timedelta(hours=2)
        )

        num_threads = 20
        barrier = threading.Barrier(num_threads)
        results: list[tuple[int, dict[str, Any]]] = []

        def worker_checkout() -> tuple[int, dict[str, Any]]:
            try:
                t_client = APIClient()
                t_client.force_authenticate(user=emp)
                barrier.wait()
                resp = t_client.post(
                    "/api/v1/parking/sessions/check-out/",
                    {
                        "session_code": session_code,
                        "exit_gate_id": out_gate.id,
                        "payment_method": "CASH",
                    },
                    format="json",
                )
                return resp.status_code, getattr(resp, "data", {})
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_checkout) for _ in range(num_threads)]
            for f in futures:
                results.append(f.result())

        statuses = [r[0] for r in results]
        status_200_count = statuses.count(status.HTTP_200_OK)
        status_409_count = statuses.count(status.HTTP_409_CONFLICT)

        assert status_200_count == 1, (
            f"Expected exactly 1 200 OK, got {status_200_count}. Statuses: {statuses}"
        )
        assert status_409_count == num_threads - 1, (
            f"Expected {num_threads - 1} 409 Conflict, got {status_409_count}. Statuses: {statuses}"
        )

        for s_code, data in results:
            if s_code == status.HTTP_409_CONFLICT:
                assert data.get("code") == "PROP-4.5.1-P10"

        # Database verification: exactly 1 session closed and exactly 1 payment
        ses = EntryExitLog.objects.get(session_code=session_code)
        assert ses.exit_time is not None
        assert Payment.objects.filter(session=ses).count() == 1

    def test_consecutive_multi_repeat_stability(
        self, test_environment: dict[str, Any]
    ) -> None:
        """
        Stress test: 5 consecutive iterations of 12-thread racing checkout.
        Proves zero flakiness, zero deadlocks, and 100% deterministic isolation across consecutive runs.
        """
        for _cycle in range(5):
            self.test_racing_checkout_under_20_threads(test_environment)
