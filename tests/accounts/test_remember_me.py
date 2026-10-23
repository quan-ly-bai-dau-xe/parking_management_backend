"""
Persistent Remember-Me Middleware & Token Lifecycle Test Suite.
Verifies ADR-0004, TL-36, and TL-52 requirements on PostgreSQL.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import OperationalError
from django.http import HttpRequest, HttpResponse
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status

from apps.accounts.middleware import PersistentRememberMeMiddleware
from apps.accounts.models import Account, PersistentLoginToken
from apps.accounts.services.auth import create_remember_token


class RememberMe0QueryInvariantTest(TestCase):
    """
    Verifies the 0-query invariant of PersistentRememberMeMiddleware per Section 3.3.
    """

    def setUp(self) -> None:
        self.account = Account.objects.create_user(
            email="zeroquery@parking.com",
            phone="0911000111",
            password="StrongPassword123!",
            role="EMPLOYEE",
        )
        self.middleware = PersistentRememberMeMiddleware(
            get_response=lambda req: HttpResponse("OK")
        )

    def test_anonymous_request_without_cookie_executes_zero_queries(self) -> None:
        """
        Guard 1: A cookieless request must exit immediately via in-memory dict lookup
        executing exactly 0 database queries without touching request.user.
        """
        request = HttpRequest()
        request.COOKIES = {}
        request.user = AnonymousUser()

        with self.assertNumQueries(0):
            response = self.middleware(request)

        self.assertEqual(response.status_code, 200)

    def test_session_authenticated_request_executes_zero_token_queries(self) -> None:
        """
        Guard 2: When the request is already authenticated in session,
        the middleware exits immediately without querying persistent_login_token.
        """
        request = HttpRequest()
        # Even if a remember cookie is present, if already authenticated, 0 token queries occur
        request.COOKIES = {"parking_remember_token": "series123:token456"}
        request.user = self.account

        with self.assertNumQueries(0):
            response = self.middleware(request)

        self.assertEqual(response.status_code, 200)


class RememberMeReAuthenticationTest(TestCase):
    """
    Tests persistent remember-me re-authentication, rotation, grace window, and theft detection.
    """

    def setUp(self) -> None:
        self.client = Client()
        self.password = "StrongPassword123!"
        self.account = Account.objects.create_user(
            email="remember_user@parking.com",
            phone="0911223344",
            password=self.password,
            role="EMPLOYEE",
        )
        self.me_url = reverse("auth-me")

    def test_re_authentication_with_valid_cookie(self) -> None:
        """
        Anonymous client presenting a valid remember-me cookie is transparently
        authenticated, a new session is initialized, and /me/ returns 200 OK.
        """
        req = HttpRequest()
        series, raw_token = create_remember_token(self.account, req)
        cookie_val = f"{series}:{raw_token}"

        # Client has no session cookie, only remember cookie
        self.client.cookies["parking_remember_token"] = cookie_val
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["id"], self.account.id)
        self.assertEqual(data["email"], self.account.email)

        # Session cookie was created and must be a browser-session cookie (no Max-Age, no Expires per ADR-0004 and TL-53)
        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)
        session_cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertEqual(session_cookie.get("max-age"), "")
        self.assertEqual(session_cookie.get("expires"), "")

    def test_grace_window_skips_rotation_within_30_seconds(self) -> None:
        """
        When last_used_at is <= 30 seconds ago, rotation is skipped (OQ-87, ADR-0004).
        The cookie value remains unchanged.
        """
        req = HttpRequest()
        series, raw_token = create_remember_token(self.account, req)
        cookie_val = f"{series}:{raw_token}"

        token_obj = PersistentLoginToken.objects.get(series=series)
        token_obj.last_used_at = timezone.now() - timedelta(seconds=10)
        token_obj.save(update_fields=["last_used_at"])

        self.client.cookies["parking_remember_token"] = cookie_val
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Cookie should not have been rotated
        token_obj.refresh_from_db()
        self.assertNotIn(":", token_obj.token_hash)  # Still a single hash
        if "parking_remember_token" in response.cookies:
            # If set, must match the same token
            self.assertEqual(
                response.cookies["parking_remember_token"].value, cookie_val
            )

    def test_token_rotation_after_30_seconds_grace_window(self) -> None:
        """
        When last_used_at is > 30 seconds ago, token rotation occurs:
        - A new raw token is generated and returned in Set-Cookie.
        - Composite hash f"{new_hash}:{old_hash}" is stored in database.
        """
        req = HttpRequest()
        series, raw_token = create_remember_token(self.account, req)
        old_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        token_obj = PersistentLoginToken.objects.get(series=series)
        token_obj.last_used_at = timezone.now() - timedelta(seconds=35)
        token_obj.save(update_fields=["last_used_at"])

        self.client.cookies["parking_remember_token"] = f"{series}:{raw_token}"
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # New cookie was issued
        self.assertIn("parking_remember_token", response.cookies)
        new_cookie = response.cookies["parking_remember_token"].value
        new_series, new_raw_token = new_cookie.split(":", 1)
        self.assertEqual(new_series, series)
        self.assertNotEqual(new_raw_token, raw_token)

        # Database stores composite hash: new_hash:old_hash
        token_obj.refresh_from_db()
        new_hash = hashlib.sha256(new_raw_token.encode("utf-8")).hexdigest()
        expected_composite = f"{new_hash}:{old_hash}"
        self.assertEqual(token_obj.token_hash, expected_composite)

    def test_parallel_request_with_previous_hash_accepted_during_grace(self) -> None:
        """
        A concurrent request presenting the previous token within 30s of rotation
        is accepted without re-rotation or theft invalidation.
        """
        req = HttpRequest()
        series, raw_token1 = create_remember_token(self.account, req)
        hash1 = hashlib.sha256(raw_token1.encode("utf-8")).hexdigest()

        raw_token2 = secrets.token_hex(32)
        hash2 = hashlib.sha256(raw_token2.encode("utf-8")).hexdigest()

        # Simulate rotation already happened 5 seconds ago
        token_obj = PersistentLoginToken.objects.get(series=series)
        token_obj.token_hash = f"{hash2}:{hash1}"
        token_obj.last_used_at = timezone.now() - timedelta(seconds=5)
        token_obj.save(update_fields=["token_hash", "last_used_at"])

        # Second request arrives with token1 (the previous token)
        self.client.cookies["parking_remember_token"] = f"{series}:{raw_token1}"
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Token row still exists
        self.assertTrue(PersistentLoginToken.objects.filter(series=series).exists())

    def test_token_theft_hash_mismatch_revokes_all_account_tokens(self) -> None:
        """
        When series exists but presented token hash does not match, token theft is detected:
        ALL persistent tokens for the account are revoked, cookie deleted, user rejected.
        """
        req = HttpRequest()
        series1, _ = create_remember_token(self.account, req)
        series2, _ = create_remember_token(self.account, req)

        self.assertEqual(
            PersistentLoginToken.objects.filter(account=self.account).count(), 2
        )

        # Attacker presents forged token for series1
        forged_cookie = f"{series1}:forged_token_value_hex_123456"
        self.client.cookies["parking_remember_token"] = forged_cookie
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # ALL tokens for account must be deleted per TL-36
        self.assertEqual(
            PersistentLoginToken.objects.filter(account=self.account).count(), 0
        )

        # Cookie deleted on response
        self.assertEqual(response.cookies["parking_remember_token"].value, "")

    def test_stale_token_replay_outside_grace_window_triggers_theft_revocation(
        self,
    ) -> None:
        """
        Replaying an old previous token after the 30s grace window triggers token theft revocation.
        """
        req = HttpRequest()
        series, raw_token1 = create_remember_token(self.account, req)
        hash1 = hashlib.sha256(raw_token1.encode("utf-8")).hexdigest()

        raw_token2 = secrets.token_hex(32)
        hash2 = hashlib.sha256(raw_token2.encode("utf-8")).hexdigest()

        token_obj = PersistentLoginToken.objects.get(series=series)
        token_obj.token_hash = f"{hash2}:{hash1}"
        # Rotation occurred 40 seconds ago (outside 30s grace)
        token_obj.last_used_at = timezone.now() - timedelta(seconds=40)
        token_obj.save(update_fields=["token_hash", "last_used_at"])

        # Replay token1 outside grace window
        self.client.cookies["parking_remember_token"] = f"{series}:{raw_token1}"
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # All tokens for account revoked
        self.assertEqual(
            PersistentLoginToken.objects.filter(account=self.account).count(), 0
        )

    def test_expired_token_is_deleted_and_cookie_cleared(self) -> None:
        """
        Expired remember-me token (expires_at in past) is deleted, cookie cleared.
        """
        req = HttpRequest()
        series, raw_token = create_remember_token(self.account, req)

        token_obj = PersistentLoginToken.objects.get(series=series)
        now = timezone.now()
        token_obj.created_at = now - timedelta(days=35)
        token_obj.last_used_at = now - timedelta(days=35)
        token_obj.expires_at = now - timedelta(days=5)
        token_obj.save(update_fields=["created_at", "last_used_at", "expires_at"])

        self.client.cookies["parking_remember_token"] = f"{series}:{raw_token}"
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(PersistentLoginToken.objects.filter(series=series).exists())
        self.assertEqual(response.cookies["parking_remember_token"].value, "")

    def test_inactive_or_soft_deleted_account_rejects_and_purges_token(self) -> None:
        """
        Remember-me token presented for an inactive or soft-deleted account is deleted,
        cookie cleared, and authentication is rejected.
        """
        req = HttpRequest()
        series, raw_token = create_remember_token(self.account, req)

        # Deactivate account
        self.account.is_active = False
        self.account.save(update_fields=["is_active"])

        self.client.cookies["parking_remember_token"] = f"{series}:{raw_token}"
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(PersistentLoginToken.objects.filter(series=series).exists())

    def test_malformed_cookie_is_cleared_safely(self) -> None:
        """
        Malformed remember-me cookie (missing colon or empty parts) is cleared without crashing.
        """
        self.client.cookies["parking_remember_token"] = "malformed_token"
        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.cookies["parking_remember_token"].value, "")

    def test_active_token_cap_limits_to_10_per_account(self) -> None:
        """
        Issuing more than 10 remember tokens for a single account purges the oldest tokens (ADR-0004, TL-52).
        """
        req = HttpRequest()
        created_series = []
        for _ in range(12):
            s, _ = create_remember_token(self.account, req)
            created_series.append(s)

        tokens = PersistentLoginToken.objects.filter(account=self.account)
        self.assertEqual(tokens.count(), 10)

        # The first 2 created tokens must have been pruned
        self.assertFalse(
            PersistentLoginToken.objects.filter(series=created_series[0]).exists()
        )
        self.assertFalse(
            PersistentLoginToken.objects.filter(series=created_series[1]).exists()
        )
        # The latest token exists
        self.assertTrue(
            PersistentLoginToken.objects.filter(series=created_series[-1]).exists()
        )

    def test_remember_me_middleware_db_operational_error_preserves_cookie_and_row(
        self,
    ) -> None:
        """
        Kiểm tra khả năng chịu lỗi CSDL: Khi CSDL gặp OperationalError tạm thời, middleware coi request là anonymous per TL-53,
        TUYỆT ĐỐI KHÔNG xóa cookie và KHÔNG xóa bản ghi token trong CSDL.
        """
        req = HttpRequest()
        series, raw_token = create_remember_token(self.account, req)
        self.client.cookies["parking_remember_token"] = f"{series}:{raw_token}"

        with patch(
            "apps.accounts.middleware.PersistentLoginToken.objects.select_for_update",
            side_effect=OperationalError("deadlock detected"),
        ):
            response = self.client.get(reverse("auth-csrf"))
            self.assertEqual(response.status_code, status.HTTP_200_OK)

            res_cookie = response.cookies.get("parking_remember_token")
            if res_cookie:
                self.assertNotEqual(res_cookie.value, "")

            self.assertTrue(
                PersistentLoginToken.objects.filter(series=series).exists(),
                "Token row must NOT be deleted upon transient database error",
            )

    @override_settings(REMEMBER_ROTATION_GRACE_SECONDS=1)
    def test_override_rotation_grace_seconds_triggers_rotation(self) -> None:
        """
        Khẳng định middleware sử dụng setting REMEMBER_ROTATION_GRACE_SECONDS thay vì hardcode 30s per TL-53.
        Khi đặt grace=1s và đã trôi qua 2s, middleware phải xoay vòng token.
        """
        req = HttpRequest()
        series, raw_token = create_remember_token(self.account, req)
        token_obj = PersistentLoginToken.objects.get(series=series)

        past_time = timezone.now() - timedelta(seconds=2)
        token_obj.last_used_at = past_time
        token_obj.save(update_fields=["last_used_at"])

        self.client.cookies["parking_remember_token"] = f"{series}:{raw_token}"
        response = self.client.get(self.me_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIn("parking_remember_token", response.cookies)
        new_cookie_val = response.cookies["parking_remember_token"].value
        self.assertNotEqual(new_cookie_val, f"{series}:{raw_token}")

    @override_settings(REMEMBER_MAX_TOKENS_PER_ACCOUNT=3)
    def test_override_max_tokens_per_account_enforces_custom_cap(self) -> None:
        """
        Khẳng định create_remember_token sử dụng REMEMBER_MAX_TOKENS_PER_ACCOUNT thay vì hardcode 10 per TL-53.
        Khi đặt cap=3 và tạo 4 tokens, chỉ giữ lại đúng 3 tokens.
        """
        req = HttpRequest()
        for _ in range(4):
            create_remember_token(self.account, req)

        active_tokens = PersistentLoginToken.objects.filter(account=self.account)
        self.assertEqual(active_tokens.count(), 3)

    @override_settings(REMEMBER_TOKEN_LIFETIME_DAYS=1)
    def test_override_token_lifetime_days_enforces_custom_expiration(self) -> None:
        """
        Khẳng định create_remember_token và middleware sử dụng REMEMBER_TOKEN_LIFETIME_DAYS per TL-53.
        Khi đặt lifetime=1 ngày:
        - expires_at được tính đúng theo created_at + 1 ngày (không phải 30 ngày hardcode).
        - Sau 2 ngày (injected clock), token bị từ chối do hết hạn và cookie bị xóa.
        """
        req = HttpRequest()
        series, raw_token = create_remember_token(self.account, req)
        token_obj = PersistentLoginToken.objects.get(series=series)
        expected_expiry = token_obj.created_at + timedelta(days=1)
        self.assertAlmostEqual(
            token_obj.expires_at.timestamp(),
            expected_expiry.timestamp(),
            delta=2,
        )

        future_expired = timezone.now() + timedelta(days=2)
        with patch("django.utils.timezone.now", return_value=future_expired):
            client = Client()
            client.cookies["parking_remember_token"] = f"{series}:{raw_token}"
            response = client.get(self.me_url)
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertEqual(response.cookies["parking_remember_token"]["max-age"], 0)
