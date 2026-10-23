"""
Brute-Force Rate Limiting Test Suite per SRS 4.1, ADR-0004, and Threat Model T1.
Verifies dual-key throttling (identifier and IP) on real PostgreSQL.
"""

from __future__ import annotations

import concurrent.futures
import threading
import uuid
from typing import Any

from django.core.cache import cache
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from rest_framework import status

from apps.accounts.models import Account


class LoginThrottlingTest(TestCase):
    """
    Tests identifier rate limiter (5 failed attempts / 15m) and IP rate limiter (30 attempts / 15m).
    """

    def setUp(self) -> None:
        cache.clear()
        # enforce_csrf_checks=False is explicitly justified here to isolate rate limiting quotas
        # and sliding window counter verification from CSRF validation.
        self.client = Client(enforce_csrf_checks=False)
        self.login_url = reverse("auth-login")
        self.password = "ValidSecret123!"
        self.account = Account.objects.create_user(
            email="victim@parking.com",
            phone="0911223344",
            password=self.password,
            role="EMPLOYEE",
        )

    def tearDown(self) -> None:
        cache.clear()

    def test_identifier_throttling_blocks_on_6th_failed_attempt(self) -> None:
        """
        Five consecutive failed logins with the same identifier return 401 MSG-4.1-M02.
        The 6th attempt returns 429 Too Many Requests with PROP-4.1-P01 and Retry-After.
        """
        payload = {
            "identifier": "victim@parking.com",
            "password": "WrongPassword!",
            "remember": False,
        }

        # Attempts 1 to 5: Return 401 Unauthorized
        for i in range(5):
            response = self.client.post(
                self.login_url,
                data=payload,
                content_type="application/json",
            )
            self.assertEqual(
                response.status_code,
                status.HTTP_401_UNAUTHORIZED,
                f"Attempt {i + 1} should be 401",
            )
            self.assertEqual(response.json()["code"], "MSG-4.1-M02")

        # 6th attempt: Must be blocked with 429 Too Many Requests
        response6 = self.client.post(
            self.login_url,
            data=payload,
            content_type="application/json",
        )
        self.assertEqual(response6.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        data = response6.json()
        self.assertEqual(data["code"], "PROP-4.1-P01")
        self.assertIn("Quá nhiều lần đăng nhập không thành công", data["message"])
        self.assertIn("Retry-After", response6.headers)
        retry_after = int(response6.headers["Retry-After"])
        self.assertGreater(retry_after, 0)
        self.assertLessEqual(retry_after, 900)

    def test_identifier_throttling_normalizes_case_and_phone_separators(self) -> None:
        """
        Mixed casing for email and formatting separators for phone share the same quota.
        """
        # Test case-insensitive email: 3 attempts with uppercase, 2 with mixed case
        variants = [
            "VICTIM@PARKING.COM",
            "Victim@Parking.Com",
            "victim@PARKING.com",
            "VICTIM@parking.com",
            "victim@parking.COM",
        ]
        for email_var in variants:
            res = self.client.post(
                self.login_url,
                data={"identifier": email_var, "password": "Bad", "remember": False},
                content_type="application/json",
            )
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # 6th attempt with standard lowercase email is throttled
        res6 = self.client.post(
            self.login_url,
            data={
                "identifier": "victim@parking.com",
                "password": "Bad",
                "remember": False,
            },
            content_type="application/json",
        )
        self.assertEqual(res6.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(res6.json()["code"], "PROP-4.1-P01")

        # Test phone number formatting separators normalization
        cache.clear()
        phone_variants = [
            "0911 22 33 44",
            "0911.22.33.44",
            "0911-22-33-44",
            "0911223344",
            " 0911 223344 ",
        ]
        for phone_var in phone_variants:
            res = self.client.post(
                self.login_url,
                data={"identifier": phone_var, "password": "Bad", "remember": False},
                content_type="application/json",
            )
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # 6th attempt with clean phone is throttled
        res6_phone = self.client.post(
            self.login_url,
            data={
                "identifier": "0911223344",
                "password": "Bad",
                "remember": False,
            },
            content_type="application/json",
        )
        self.assertEqual(res6_phone.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_successful_login_resets_identifier_failed_attempts(self) -> None:
        """
        A successful login resets the failed attempts counter for that identifier.
        """
        # 3 failed attempts
        for _ in range(3):
            self.client.post(
                self.login_url,
                data={
                    "identifier": "victim@parking.com",
                    "password": "Wrong",
                    "remember": False,
                },
                content_type="application/json",
            )

        # Successful login resets the counter
        success_res = self.client.post(
            self.login_url,
            data={
                "identifier": "victim@parking.com",
                "password": self.password,
                "remember": False,
            },
            content_type="application/json",
        )
        self.assertEqual(success_res.status_code, status.HTTP_200_OK)

        # User can now make up to 5 more failed attempts without being throttled
        for i in range(5):
            res = self.client.post(
                self.login_url,
                data={
                    "identifier": "victim@parking.com",
                    "password": "WrongAgain",
                    "remember": False,
                },
                content_type="application/json",
            )
            self.assertEqual(
                res.status_code,
                status.HTTP_401_UNAUTHORIZED,
                f"Attempt {i + 1} after reset should be 401",
            )

        # 6th attempt after reset is blocked
        blocked_res = self.client.post(
            self.login_url,
            data={
                "identifier": "victim@parking.com",
                "password": "WrongAgain",
                "remember": False,
            },
            content_type="application/json",
        )
        self.assertEqual(blocked_res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_nonexistent_account_throttling_prevents_enumeration(self) -> None:
        """
        Non-existent accounts are throttled in the exact same manner as existing accounts,
        preventing account enumeration via rate-limiting behavior (Threat T2).
        """
        fake_id = "nonexistent_target@parking.com"
        for _ in range(5):
            res = self.client.post(
                self.login_url,
                data={"identifier": fake_id, "password": "Wrong", "remember": False},
                content_type="application/json",
            )
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertEqual(res.json()["code"], "MSG-4.1-M02")

        # 6th attempt is throttled
        res6 = self.client.post(
            self.login_url,
            data={"identifier": fake_id, "password": "Wrong", "remember": False},
            content_type="application/json",
        )
        self.assertEqual(res6.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(res6.json()["code"], "PROP-4.1-P01")

    def test_ip_throttling_blocks_on_31st_attempt(self) -> None:
        """
        Thirty login attempts from the same IP address succeed or fail normally.
        The 31st attempt returns 429 Too Many Requests (ADR-0004, TL-52).
        """
        client_ip = "192.168.1.100"

        # 30 attempts with different identifiers from the same IP
        for i in range(30):
            res = self.client.post(
                self.login_url,
                data={
                    "identifier": f"user_{i}@parking.com",
                    "password": "Password!",
                    "remember": False,
                },
                content_type="application/json",
                REMOTE_ADDR=client_ip,
            )
            self.assertIn(
                res.status_code,
                [status.HTTP_401_UNAUTHORIZED, status.HTTP_200_OK],
                f"Attempt {i + 1} from IP should not be 429",
            )

        # 31st attempt from the same IP must be throttled
        res31 = self.client.post(
            self.login_url,
            data={
                "identifier": "another_user@parking.com",
                "password": "Password!",
                "remember": False,
            },
            content_type="application/json",
            REMOTE_ADDR=client_ip,
        )
        self.assertEqual(res31.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(res31.json()["code"], "PROP-4.1-P01")
        self.assertIn("Retry-After", res31.headers)

    def test_31_successful_logins_from_one_ip_never_produce_429(self) -> None:
        """
        31 successful logins from one IP must never produce 429.
        Successful logins only verify credentials and must not consume failed attempts quota.
        """
        client_ip = "192.168.10.50"
        for i in range(31):
            res = self.client.post(
                self.login_url,
                data={
                    "identifier": self.account.email,
                    "password": self.password,
                    "remember": False,
                },
                content_type="application/json",
                REMOTE_ADDR=client_ip,
            )
            self.assertEqual(
                res.status_code,
                status.HTTP_200_OK,
                f"Attempt {i + 1} from IP should be 200 OK, got {res.status_code}",
            )

    def test_successful_login_does_not_reset_another_pair_counter(self) -> None:
        """
        Đăng nhập thành công của một tài khoản/IP không được xóa biến đếm thất bại của cặp khác per TL-53.
        """
        pair_a_ip = "192.168.1.10"
        for _ in range(5):
            self.client.post(
                self.login_url,
                data={
                    "identifier": "victim@parking.com",
                    "password": "Wrong",
                    "remember": False,
                },
                content_type="application/json",
                REMOTE_ADDR=pair_a_ip,
            )
        res_blocked = self.client.post(
            self.login_url,
            data={
                "identifier": "victim@parking.com",
                "password": "Wrong",
                "remember": False,
            },
            content_type="application/json",
            REMOTE_ADDR=pair_a_ip,
        )
        self.assertEqual(res_blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

        # Cặp 2: Đăng nhập thành công từ IP khác
        other_account = Account.objects.create_user(
            email="other_pair_user@parking.com",
            password=self.password,
            role="EMPLOYEE",
        )
        res_other = self.client.post(
            self.login_url,
            data={
                "identifier": other_account.email,
                "password": self.password,
                "remember": False,
            },
            content_type="application/json",
            REMOTE_ADDR="192.168.1.20",
        )
        self.assertEqual(res_other.status_code, status.HTTP_200_OK)

        # Cặp 1 vẫn tiếp tục bị khóa 429
        res_still_blocked = self.client.post(
            self.login_url,
            data={
                "identifier": "victim@parking.com",
                "password": "Wrong",
                "remember": False,
            },
            content_type="application/json",
            REMOTE_ADDR=pair_a_ip,
        )
        self.assertEqual(
            res_still_blocked.status_code, status.HTTP_429_TOO_MANY_REQUESTS
        )

    def test_identifier_ceiling_blocks_after_20_attempts_across_different_ips(
        self,
    ) -> None:
        """
        20 failed attempts against the same identifier from 20 different IPs hit the identifier ceiling.
        The 21st attempt from a 21st IP is throttled with 429.
        """
        target_email = "target_ceiling@parking.com"
        for i in range(20):
            res = self.client.post(
                self.login_url,
                data={
                    "identifier": target_email,
                    "password": "Wrong",
                    "remember": False,
                },
                content_type="application/json",
                REMOTE_ADDR=f"10.0.0.{i + 1}",
            )
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        res21 = self.client.post(
            self.login_url,
            data={"identifier": target_email, "password": "Wrong", "remember": False},
            content_type="application/json",
            REMOTE_ADDR="10.0.0.21",
        )
        self.assertEqual(res21.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(res21.json()["code"], "PROP-4.1-P01")

    def test_num_proxies_header_parsing(self) -> None:
        """
        Honors NUM_PROXIES setting when extracting client IP per TL-53 and ADR-0004.
        """
        from django.test import RequestFactory

        from apps.accounts.services.throttling import get_client_ip

        rf = RequestFactory()

        # Default NUM_PROXIES = 0 -> uses REMOTE_ADDR
        with self.settings(NUM_PROXIES=0):
            req = rf.get(
                "/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8"
            )
            self.assertEqual(get_client_ip(req), "127.0.0.1")

        # NUM_PROXIES = 1 -> uses last proxy client address
        with self.settings(NUM_PROXIES=1):
            req = rf.get(
                "/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8"
            )
            self.assertEqual(get_client_ip(req), "5.6.7.8")

        # NUM_PROXIES = 2 -> uses second-to-last proxy client address
        with self.settings(NUM_PROXIES=2):
            req = rf.get(
                "/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4, 5.6.7.8"
            )
            self.assertEqual(get_client_ip(req), "1.2.3.4")

        # Empty X-Forwarded-For falls back to REMOTE_ADDR
        with self.settings(NUM_PROXIES=1):
            req = rf.get("/", REMOTE_ADDR="127.0.0.1", HTTP_X_FORWARDED_FOR="   ")
            self.assertEqual(get_client_ip(req), "127.0.0.1")

    def test_limiter_direct_methods_and_edge_cases(self) -> None:
        """
        Direct unit tests for LoginAttemptLimiter methods and branches.
        """
        from apps.accounts.services.throttling import (
            LimiterReservation,
            LoginAttemptLimiter,
        )

        limiter = LoginAttemptLimiter()
        # reset without IP and with IP
        limiter.reset("some_user@parking.com")
        limiter.reset("some_user@parking.com", client_ip="1.2.3.4")

        # atomic_decr when key does not exist or <= 0
        limiter._atomic_decr("nonexistent_throttle_key")

        # release_on_success
        res = LimiterReservation(
            pair_key="k_pair", id_key="k_id", ip_key="k_ip", window=900
        )
        cache.set("k_pair", 1)
        cache.set("k_id", 1)
        cache.set("k_ip", 1)
        limiter.release_on_success(res)
        self.assertIsNone(cache.get("k_pair"))
        self.assertIsNone(cache.get("k_id"))
        self.assertIsNone(cache.get("k_ip"))

    def test_limiter_mocked_incr_decr_exceptions(self) -> None:
        """Covers ValueError branches in _atomic_incr and _atomic_decr."""
        from unittest.mock import MagicMock

        from apps.accounts.services.throttling import LoginAttemptLimiter

        mock_cache = MagicMock()
        mock_cache.incr.side_effect = [ValueError("Key not found"), 2]
        mock_cache.add.side_effect = [False, True]
        limiter = LoginAttemptLimiter(cache_backend=mock_cache)
        count = limiter._atomic_incr("some_key", 900)
        self.assertEqual(count, 1)

        mock_cache_decr = MagicMock()
        mock_cache_decr.decr.side_effect = ValueError("Key not found")
        limiter_decr = LoginAttemptLimiter(cache_backend=mock_cache_decr)
        limiter_decr._atomic_decr("some_key")

    def test_client_ip_headers_fallback(self) -> None:
        """Covers request.headers fallback for x-forwarded-for."""
        from apps.accounts.services.throttling import get_client_ip

        class DummyRequest:
            META = {"REMOTE_ADDR": "127.0.0.1"}
            headers = {"x-forwarded-for": "10.10.10.10"}

        with self.settings(NUM_PROXIES=1):
            ip = get_client_ip(DummyRequest())  # type: ignore
            self.assertEqual(ip, "10.10.10.10")

            class DummyEmptyRequest:
                META = {"REMOTE_ADDR": "127.0.0.1"}
                headers: dict[str, str] = {}

            ip_empty = get_client_ip(DummyEmptyRequest())  # type: ignore
            self.assertEqual(ip_empty, "127.0.0.1")


class ParallelLoginThrottleConcurrencyTest(TransactionTestCase):
    """
    Verifies that atomic reserve-then-verify prevents parallel brute-force bypass per TL-53 and ADR-0004.
    Must run on real PostgreSQL with transaction=True.
    """

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        from django.db import connections

        for conn in connections.all():
            conn.settings_dict["CONN_MAX_AGE"] = 0

    def setUp(self) -> None:
        cache.clear()
        self.login_url = reverse("auth-login")
        self.unique_id = uuid.uuid4().hex[:6]
        self.email = f"victim_conc_{self.unique_id}@parking.local"
        self.password = "ValidSecret123!"
        Account.objects.filter(email=self.email).delete()
        self.account = Account.objects.create_user(
            email=self.email,
            phone=f"091{uuid.uuid4().int % 10000000:07d}",
            password=self.password,
            role="EMPLOYEE",
        )

    def tearDown(self) -> None:
        from django.db import connections

        Account.objects.filter(email=self.email).delete()
        connections.close_all()
        cache.clear()

    @classmethod
    def tearDownClass(cls) -> None:
        from django.db import connections

        connections.close_all()
        super().tearDownClass()

    def test_25_parallel_wrong_passwords_strictly_throttled_to_max_5_failures(
        self,
    ) -> None:
        """
        25 concurrent threads attempting wrong passwords for the same (identifier, IP) pair.
        Atomic reserve-then-verify ensures at most 5 return 401 and the rest return 429.
        Executes for 20 consecutive iterations ("run it 20 times") per TL-53 specification.
        """
        total_iterations = 20
        concurrency_passes = 0

        for iteration in range(total_iterations):
            cache.clear()
            barrier = threading.Barrier(25)
            payload = {
                "identifier": self.email,
                "password": "WrongPassword!",
                "remember": False,
            }

            def worker_attempt(
                _barrier: threading.Barrier = barrier,
                _data: dict[str, Any] = payload,
            ) -> int:
                from django.db import connections

                try:
                    # enforce_csrf_checks=False is explicitly justified here to isolate parallel throttle
                    # concurrency race verification from CSRF validation; end-to-end CSRF compliance
                    # is tested independently in tests/accounts/test_core_auth.py.
                    client = Client(enforce_csrf_checks=False)
                    _barrier.wait(timeout=10)
                    response = client.post(
                        self.login_url,
                        data=_data,
                        content_type="application/json",
                    )
                    return response.status_code
                finally:
                    connections.close_all()

            with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
                futures = [executor.submit(worker_attempt) for _ in range(25)]
                results = [f.result() for f in futures]

            count_401 = results.count(status.HTTP_401_UNAUTHORIZED)
            count_429 = results.count(status.HTTP_429_TOO_MANY_REQUESTS)

            self.assertEqual(len(results), 25)
            self.assertLessEqual(
                count_401,
                5,
                f"Iteration {iteration + 1}: Expected at most 5 failures of 401, got {count_401}",
            )
            self.assertGreaterEqual(
                count_429,
                20,
                f"Iteration {iteration + 1}: Expected at least 20 throttled 429, got {count_429}",
            )
            self.assertEqual(count_401 + count_429, 25)
            concurrency_passes += 1

        self.assertEqual(
            concurrency_passes,
            total_iterations,
            f"Expected {total_iterations} passed iterations, got {concurrency_passes}",
        )
