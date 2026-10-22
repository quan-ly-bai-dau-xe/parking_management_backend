"""
Multi-threaded concurrency verification for authentication on PostgreSQL.
Verifies:
1. 20x Concurrency Pass Count for Remember-Me Grace Window (20 concurrent threads x 20 iterations = 100% pass).
2. Concurrent Login & Remember-Me Verification (Deadlock Prevention RSK-09, zero SQLSTATE 40P01).
3. Concurrent Token Theft Revocation (10 valid + 2 tampered threads, TL-36 account tokens purged).
4. Concurrent parallel requests with previous hash accepted during grace window.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db import OperationalError, connections
from django.http import HttpRequest
from django.test import Client, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import Account, PersistentLoginToken
from apps.accounts.services.auth import create_remember_token

logger = logging.getLogger(__name__)


class RememberMeConcurrencyTransactionTest(TransactionTestCase):
    """
    Multi-threaded Concurrency Test Suite executing against real PostgreSQL.
    Inherits from TransactionTestCase with reset_sequences=True to ensure real
    commit visibility, row locking, and multi-connection concurrency isolation.
    """

    reset_sequences = True

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        for conn in connections.all():
            conn.settings_dict["CONN_MAX_AGE"] = 0

    def setUp(self) -> None:
        cache.clear()
        self.me_url = reverse("auth-me")
        self.login_url = reverse("auth-login")

    def tearDown(self) -> None:
        connections.close_all()
        cache.clear()

    @classmethod
    def tearDownClass(cls) -> None:
        connections.close_all()
        super().tearDownClass()

    def test_20x_concurrency_pass_count_remember_me_grace_window(self) -> None:
        """
        Verify that 20 concurrent threads presenting the same remember-me token
        within the 30-second rotation grace window all succeed (HTTP 200).
        Executes for 20 consecutive iterations to prove a 20/20 (100%) pass count
        without race condition false theft alerts or database deadlocks.
        """
        total_iterations = 20
        workers_count = 20
        concurrency_passes = 0
        iteration_summaries: list[str] = []

        for iteration in range(total_iterations):
            email = f"grace_conc_{iteration}_{uuid.uuid4().hex[:6]}@parking.local"
            phone = f"093{iteration:02d}{uuid.uuid4().int % 100000:05d}"
            password = "TestPassword123!"

            account = Account.objects.create_user(
                email=email,
                phone=phone,
                password=password,
                role="EMPLOYEE",
            )

            req = HttpRequest()
            series, raw_token = create_remember_token(account, req)
            cookie_val = f"{series}:{raw_token}"

            # Ensure last_used_at is fresh to guarantee within 30s grace window
            token_obj = PersistentLoginToken.objects.get(series=series)
            token_obj.last_used_at = timezone.now()
            token_obj.save(update_fields=["last_used_at"])

            barrier = threading.Barrier(workers_count)
            iteration_results: list[tuple[int, dict[str, Any]]] = []
            deadlock_errors: list[str] = []

            def worker_grace(
                worker_id: int,
                _cookie: str = cookie_val,
                _b: threading.Barrier = barrier,
                _it: int = iteration,
                _deadlocks: list[str] = deadlock_errors,
            ) -> tuple[int, dict[str, Any]]:
                try:
                    client = Client()
                    client.cookies["parking_remember_token"] = _cookie
                    _b.wait(timeout=10)
                    response = client.get(
                        self.me_url,
                        REMOTE_ADDR=f"10.10.{_it}.{worker_id}",
                    )
                    return response.status_code, response.json()
                except OperationalError as exc:
                    _deadlocks.append(str(exc))
                    raise
                finally:
                    connections.close_all()

            with ThreadPoolExecutor(max_workers=workers_count) as executor:
                futures = [
                    executor.submit(worker_grace, i) for i in range(workers_count)
                ]
                for f in futures:
                    iteration_results.append(f.result())

            # 1. All 20 threads must return HTTP 200 OK
            status_codes = [res[0] for res in iteration_results]
            self.assertEqual(
                status_codes,
                [status.HTTP_200_OK] * workers_count,
                f"Iteration {iteration + 1}: Not all 20 threads returned HTTP 200: {status_codes}",
            )

            # 2. All responses return correct account identity
            for _, body in iteration_results:
                self.assertEqual(body["id"], account.id)
                self.assertEqual(body["email"], email)

            # 3. Zero deadlock errors detected
            self.assertEqual(
                len(deadlock_errors),
                0,
                f"Iteration {iteration + 1}: Deadlock occurred: {deadlock_errors}",
            )

            # 4. Token row in DB must remain valid with 0 false-positive theft revocations
            token_in_db = PersistentLoginToken.objects.filter(
                series=series, account=account
            ).first()
            self.assertIsNotNone(
                token_in_db,
                f"Iteration {iteration + 1}: Token was erroneously revoked by grace window!",
            )
            assert token_in_db is not None
            self.assertNotIn(
                ":",
                token_in_db.token_hash,
                f"Iteration {iteration + 1}: Token should not have rotated within grace window",
            )

            concurrency_passes += 1
            summary_line = (
                f"Iteration {concurrency_passes:02d}/{total_iterations}: "
                f"PASSED ({workers_count}/{workers_count} threads HTTP 200, 0 deadlocks)"
            )
            iteration_summaries.append(summary_line)

        # Confirm 20/20 (100%) concurrency pass count
        self.assertEqual(
            concurrency_passes,
            total_iterations,
            f"Expected {total_iterations} passed iterations, got {concurrency_passes}",
        )
        self.assertEqual(len(iteration_summaries), 20)

    def test_concurrent_login_and_remember_me_deadlock_prevention_rsk_09(self) -> None:
        """
        Verify deadlock prevention (RSK-09) when executing 10 login requests and
        10 remember-me re-authentication requests concurrently across 20 parallel threads
        targeting the same account.
        Asserts zero OperationalError with SQLSTATE 40P01 and correct transaction isolation.
        """
        email = f"deadlock_conc_{uuid.uuid4().hex[:6]}@parking.local"
        phone = f"092{uuid.uuid4().int % 10000000:07d}"
        password = "StrongPassword123!"

        account = Account.objects.create_user(
            email=email,
            phone=phone,
            password=password,
            role="EMPLOYEE",
        )

        req = HttpRequest()
        series, raw_token = create_remember_token(account, req)
        cookie_val = f"{series}:{raw_token}"

        # Ensure token is active and within grace window
        token_obj = PersistentLoginToken.objects.get(series=series)
        token_obj.last_used_at = timezone.now()
        token_obj.save(update_fields=["last_used_at"])

        total_threads = 20
        barrier = threading.Barrier(total_threads)
        all_results: list[tuple[str, int, dict[str, Any]]] = []
        deadlock_errors: list[str] = []

        def worker_login(idx: int) -> tuple[str, int, dict[str, Any]]:
            try:
                client = Client()
                barrier.wait(timeout=10)
                response = client.post(
                    self.login_url,
                    {"identifier": email, "password": password, "remember": True},
                    content_type="application/json",
                    REMOTE_ADDR=f"10.20.1.{idx}",
                )
                return ("login", response.status_code, response.json())
            except OperationalError as exc:
                deadlock_errors.append(f"Login thread {idx}: {exc}")
                raise
            finally:
                connections.close_all()

        def worker_remember(idx: int) -> tuple[str, int, dict[str, Any]]:
            try:
                client = Client()
                client.cookies["parking_remember_token"] = cookie_val
                barrier.wait(timeout=10)
                response = client.get(
                    self.me_url,
                    REMOTE_ADDR=f"10.20.2.{idx}",
                )
                return ("remember", response.status_code, response.json())
            except OperationalError as exc:
                deadlock_errors.append(f"Remember thread {idx}: {exc}")
                raise
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=total_threads) as executor:
            login_futures = [executor.submit(worker_login, i) for i in range(10)]
            remember_futures = [executor.submit(worker_remember, i) for i in range(10)]
            for f in login_futures + remember_futures:
                all_results.append(f.result())

        # 1. Zero deadlock errors (SQLSTATE 40P01)
        self.assertEqual(
            len(deadlock_errors),
            0,
            f"PostgreSQL deadlock detected during concurrent login & remember-me: {deadlock_errors}",
        )

        login_results = [r for r in all_results if r[0] == "login"]
        remember_results = [r for r in all_results if r[0] == "remember"]

        self.assertEqual(len(login_results), 10)
        self.assertEqual(len(remember_results), 10)

        # 2. All 10 login requests succeeded with HTTP 200
        for _, status_code, body in login_results:
            self.assertEqual(status_code, status.HTTP_200_OK)
            self.assertEqual(body["id"], account.id)

        # 3. All 10 remember-me requests succeeded with HTTP 200
        for _, status_code, body in remember_results:
            self.assertEqual(status_code, status.HTTP_200_OK)
            self.assertEqual(body["id"], account.id)

        # 4. Account row version incremented and last_login updated cleanly
        account.refresh_from_db()
        self.assertTrue(account.is_active)
        self.assertIsNotNone(account.last_login)
        self.assertGreater(account.row_version, 1)

    def test_concurrent_token_theft_revocation_purges_all_account_tokens(self) -> None:
        """
        Verify concurrent token theft detection:
        10 threads present valid token, while 2 threads present tampered token
        (matching series but invalid hash).
        Asserts that token theft is detected, plain DELETE per TL-36 purges ALL tokens
        for the account, and zero unhandled concurrency exceptions or deadlocks occur.
        """
        email = f"theft_conc_{uuid.uuid4().hex[:6]}@parking.local"
        phone = f"091{uuid.uuid4().int % 10000000:07d}"
        password = "ValidPassword123!"

        account = Account.objects.create_user(
            email=email,
            phone=phone,
            password=password,
            role="EMPLOYEE",
        )

        req = HttpRequest()
        series1, raw_token1 = create_remember_token(account, req)
        series2, _ = create_remember_token(account, req)

        self.assertEqual(
            PersistentLoginToken.objects.filter(account=account).count(), 2
        )

        valid_cookie = f"{series1}:{raw_token1}"
        tampered_cookie = f"{series1}:tampered_bad_token_hash_value"

        total_threads = 12
        barrier = threading.Barrier(total_threads)
        theft_results: list[tuple[bool, int, dict[str, Any]]] = []
        deadlock_errors: list[str] = []

        def worker_theft(
            is_tampered: bool, idx: int
        ) -> tuple[bool, int, dict[str, Any]]:
            try:
                client = Client()
                client.cookies["parking_remember_token"] = (
                    tampered_cookie if is_tampered else valid_cookie
                )
                barrier.wait(timeout=10)
                response = client.get(
                    self.me_url,
                    REMOTE_ADDR=f"10.30.{1 if is_tampered else 2}.{idx}",
                )
                return (is_tampered, response.status_code, response.json())
            except OperationalError as exc:
                deadlock_errors.append(f"Theft thread {idx}: {exc}")
                raise
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=total_threads) as executor:
            valid_futures = [executor.submit(worker_theft, False, i) for i in range(10)]
            tampered_futures = [
                executor.submit(worker_theft, True, i) for i in range(2)
            ]
            for f in valid_futures + tampered_futures:
                theft_results.append(f.result())

        # 1. Zero deadlock errors
        self.assertEqual(
            len(deadlock_errors),
            0,
            f"Deadlock detected during concurrent token theft test: {deadlock_errors}",
        )

        # 2. Tampered requests must receive HTTP 401 Unauthorized
        tampered_responses = [r for r in theft_results if r[0] is True]
        self.assertEqual(len(tampered_responses), 2)
        for _, status_code, _ in tampered_responses:
            self.assertEqual(status_code, status.HTTP_401_UNAUTHORIZED)

        # 3. Valid requests must return either 200 (if run before revocation) or 401 (if run after)
        valid_responses = [r for r in theft_results if r[0] is False]
        self.assertEqual(len(valid_responses), 10)
        for _, status_code, _ in valid_responses:
            self.assertIn(
                status_code,
                (status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED),
            )

        # 4. Plain DELETE per TL-36 must have purged ALL tokens for the account
        remaining_tokens_count = PersistentLoginToken.objects.filter(
            account=account
        ).count()
        self.assertEqual(
            remaining_tokens_count,
            0,
            "All persistent tokens for account must be purged upon token theft",
        )

    def test_concurrent_parallel_requests_with_previous_hash_during_grace_window(
        self,
    ) -> None:
        """
        Verify that 10 concurrent requests presenting the previous rotated token
        within the 30-second grace window are all accepted (HTTP 200) without
        triggering false token theft revocation.
        """
        email = f"prev_conc_{uuid.uuid4().hex[:6]}@parking.local"
        phone = f"090{uuid.uuid4().int % 10000000:07d}"
        password = "ValidPassword123!"

        account = Account.objects.create_user(
            email=email,
            phone=phone,
            password=password,
            role="EMPLOYEE",
        )

        req = HttpRequest()
        series, raw_token1 = create_remember_token(account, req)
        hash1 = hashlib.sha256(raw_token1.encode("utf-8")).hexdigest()

        raw_token2 = secrets.token_hex(32)
        hash2 = hashlib.sha256(raw_token2.encode("utf-8")).hexdigest()

        # Simulate rotation happened 5 seconds ago: composite hash new:old
        token_obj = PersistentLoginToken.objects.get(series=series)
        token_obj.token_hash = f"{hash2}:{hash1}"
        token_obj.last_used_at = timezone.now() - timedelta(seconds=5)
        token_obj.save(update_fields=["token_hash", "last_used_at"])

        workers_count = 10
        barrier = threading.Barrier(workers_count)
        results: list[tuple[int, dict[str, Any]]] = []

        def worker_prev(worker_id: int) -> tuple[int, dict[str, Any]]:
            try:
                client = Client()
                client.cookies["parking_remember_token"] = f"{series}:{raw_token1}"
                barrier.wait(timeout=10)
                response = client.get(
                    self.me_url,
                    REMOTE_ADDR=f"10.40.1.{worker_id}",
                )
                return response.status_code, response.json()
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=workers_count) as executor:
            futures = [executor.submit(worker_prev, i) for i in range(workers_count)]
            for f in futures:
                results.append(f.result())

        status_codes = [r[0] for r in results]
        self.assertEqual(
            status_codes,
            [status.HTTP_200_OK] * workers_count,
            f"Expected all threads to succeed with HTTP 200, got: {status_codes}",
        )

        # Token still exists
        self.assertTrue(
            PersistentLoginToken.objects.filter(series=series, account=account).exists()
        )
