"""
Test suite for sample account shared development password, loader idempotency,
and production safety net for sample accounts.
"""

from __future__ import annotations

import io
import re
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.hashers import (
    check_password,
    is_password_usable,
    make_password,
)
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from rest_framework import status

from apps.accounts.models import Account
from apps.core.management.commands.load_sample_data import (
    parse_sample_accounts_from_seed,
)

# Named test constant for the public shared development password
SHARED_DEV_PASSWORD = "Parking@Dev2026"


class SampleAccountSeedHashVerificationTest(TestCase):
    """
    Verifies that all 20 sample accounts in db/02-seed.sql use valid
    Argon2id hashes matching SHARED_DEV_PASSWORD and preserve all attributes.
    """

    def setUp(self) -> None:
        seed_path = Path(settings.BASE_DIR) / "db" / "02-seed.sql"
        self.assertTrue(seed_path.exists(), f"Seed file not found at {seed_path}")
        self.seed_content = seed_path.read_text(encoding="utf-8")
        self.sample_accounts = parse_sample_accounts_from_seed(self.seed_content)

    def test_seed_contains_exactly_20_sample_accounts(self) -> None:
        """db/02-seed.sql must contain exactly 20 sample accounts."""
        self.assertEqual(
            len(self.sample_accounts),
            20,
            f"Expected exactly 20 sample accounts in seed, found {len(self.sample_accounts)}",
        )

    def test_every_seed_account_hash_verifies_against_dev_password(self) -> None:
        """Every sample account hash verifies against SHARED_DEV_PASSWORD via check_password."""
        for email, pwd_hash in self.sample_accounts:
            with self.subTest(email=email):
                self.assertTrue(
                    pwd_hash.startswith("argon2$argon2id$"),
                    f"Hash for {email} is not Argon2id: {pwd_hash[:30]}...",
                )
                self.assertTrue(
                    check_password(SHARED_DEV_PASSWORD, pwd_hash),
                    f"Hash for {email} failed verification against dev password.",
                )
                self.assertTrue(
                    is_password_usable(pwd_hash),
                    f"Hash for {email} is marked unusable.",
                )
                self.assertFalse(
                    check_password("WrongDevPassword123!", pwd_hash),
                    f"Hash for {email} unexpectedly matched an invalid password.",
                )

    def test_seed_preserves_inactive_sample_account_status(self) -> None:
        """Account #4 (truong.ngoc.bich@example.com) must have is_active=FALSE in seed SQL."""
        email_pattern = re.escape("truong.ngoc.bich@example.com")
        match = re.search(
            rf"\(\s*'{email_pattern}'\s*,\s*'0374179898'\s*,\s*'[^']+'\s*,\s*'EMPLOYEE'\s*,\s*(FALSE)\s*,",
            self.seed_content,
        )
        self.assertIsNotNone(
            match,
            "Inactive sample account truong.ngoc.bich@example.com with is_active=FALSE not found in seed SQL.",
        )


class SampleAccountAuthIntegrationTest(TransactionTestCase):
    """
    Verifies real HTTP authentication via login endpoint with CSRF flow
    for sample accounts loaded under development conditions (DEBUG=True / --refresh-passwords).
    """

    def setUp(self) -> None:
        # Load sample data and refresh passwords under development settings
        with override_settings(DEBUG=True):
            call_command("load_sample_data", refresh_passwords=True)

        self.client = Client(enforce_csrf_checks=True)
        self.csrf_url = reverse("auth-csrf")
        self.login_url = reverse("auth-login")

    def _get_csrf_token(self) -> str:
        resp = self.client.get(self.csrf_url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        csrf_cookie = resp.cookies.get("csrftoken")
        self.assertIsNotNone(csrf_cookie, "CSRF cookie not set by auth-csrf endpoint")
        assert csrf_cookie is not None
        return str(csrf_cookie.value)

    def test_manager_login_success_by_email_with_csrf_flow(self) -> None:
        """MANAGER sample account logs in successfully via email with dev password and CSRF token."""
        csrf_token = self._get_csrf_token()
        payload = {
            "identifier": "hoang.dinh.khang@example.com",
            "password": SHARED_DEV_PASSWORD,
            "remember": False,
        }
        response = self.client.post(
            self.login_url,
            payload,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data.get("email"), "hoang.dinh.khang@example.com")
        self.assertEqual(data.get("role"), "MANAGER")
        self.assertIn(settings.SESSION_COOKIE_NAME, response.cookies)

    def test_manager_login_success_by_phone_identifier(self) -> None:
        """MANAGER sample account logs in successfully using phone number identifier with dev password."""
        csrf_token = self._get_csrf_token()
        payload = {
            "identifier": "0880721788",
            "password": SHARED_DEV_PASSWORD,
            "remember": False,
        }
        response = self.client.post(
            self.login_url,
            payload,
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data.get("email"), "hoang.dinh.khang@example.com")
        self.assertEqual(data.get("phone"), "0880721788")
        self.assertEqual(data.get("role"), "MANAGER")

    def test_employee_and_customer_sample_accounts_login_success(self) -> None:
        """EMPLOYEE and CUSTOMER sample accounts log in successfully with dev password."""
        csrf_token = self._get_csrf_token()

        # Test EMPLOYEE account (account #2)
        emp_response = self.client.post(
            self.login_url,
            {
                "identifier": "luong.mai.phuong@example.org",
                "password": SHARED_DEV_PASSWORD,
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(emp_response.status_code, status.HTTP_200_OK)
        self.assertEqual(emp_response.json().get("role"), "EMPLOYEE")

        self.client.logout()
        csrf_token = self._get_csrf_token()

        # Test CUSTOMER account (account #9)
        cust_response = self.client.post(
            self.login_url,
            {
                "identifier": "trinh.xuan.truong@example.com",
                "password": SHARED_DEV_PASSWORD,
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(cust_response.status_code, status.HTTP_200_OK)
        self.assertEqual(cust_response.json().get("role"), "CUSTOMER")

    def test_inactive_sample_account_cannot_login(self) -> None:
        """Inactive sample account (#4: truong.ngoc.bich@example.com) receives HTTP 401."""
        csrf_token = self._get_csrf_token()

        # Attempt by email
        response_email = self.client.post(
            self.login_url,
            {
                "identifier": "truong.ngoc.bich@example.com",
                "password": SHARED_DEV_PASSWORD,
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response_email.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response_email.json().get("code"), "MSG-4.1-M02")

        # Attempt by phone
        response_phone = self.client.post(
            self.login_url,
            {"identifier": "0374179898", "password": SHARED_DEV_PASSWORD},
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response_phone.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response_phone.json().get("code"), "MSG-4.1-M02")

    def test_wrong_password_fails_authentication(self) -> None:
        """Providing an incorrect password for a sample account returns HTTP 401."""
        csrf_token = self._get_csrf_token()
        response = self.client.post(
            self.login_url,
            {
                "identifier": "hoang.dinh.khang@example.com",
                "password": "IncorrectPassword2026!",
            },
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json().get("code"), "MSG-4.1-M02")


class ProductionSafetyNetTest(TransactionTestCase):
    """
    Verifies that load_sample_data under DEBUG=False and --force-production
    immediately resets all sample accounts' passwords to unusable hashes.
    """

    def test_load_sample_data_in_production_resets_passwords_to_unusable(
        self,
    ) -> None:
        """Under DEBUG=False with --force-production, all sample accounts receive unusable hashes."""
        out = io.StringIO()
        err = io.StringIO()
        with override_settings(DEBUG=False):
            call_command(
                "load_sample_data", force_production=True, stdout=out, stderr=err
            )

        output = out.getvalue()
        self.assertIn("Production mode detected (DEBUG=False)", output)
        self.assertIn(
            "Resetting all sample account passwords to unusable hashes", output
        )
        self.assertIn("Reset 20 sample account(s) to unusable password hashes.", output)

        seed_path = Path(settings.BASE_DIR) / "db" / "02-seed.sql"
        sample_accounts = parse_sample_accounts_from_seed(
            seed_path.read_text(encoding="utf-8")
        )
        sample_emails = [email for email, _ in sample_accounts]

        db_accounts = Account.objects.filter(email__in=sample_emails)
        self.assertEqual(db_accounts.count(), 20)

        for account in db_accounts:
            with self.subTest(account=account.email):
                self.assertFalse(
                    is_password_usable(account.password),
                    f"Account {account.email} has a usable password in production: {account.password}",
                )
                self.assertTrue(
                    account.password.startswith("!"),
                    f"Account {account.email} password does not use unusable prefix '!': {account.password}",
                )
                self.assertFalse(
                    check_password(SHARED_DEV_PASSWORD, account.password),
                    f"Account {account.email} password verified against dev password in production!",
                )

        # Confirm HTTP login fails for all sample accounts in production
        client = Client(enforce_csrf_checks=False)
        login_resp = client.post(
            reverse("auth-login"),
            {
                "identifier": "hoang.dinh.khang@example.com",
                "password": SHARED_DEV_PASSWORD,
            },
            content_type="application/json",
        )
        self.assertEqual(login_resp.status_code, status.HTTP_401_UNAUTHORIZED)


class LoaderIdempotencyAndRefreshTest(TransactionTestCase):
    """
    Verifies --refresh-passwords functionality on an already-seeded database,
    protecting non-sample accounts and testing boundary conditions.
    """

    def test_refresh_passwords_updates_sample_accounts_without_affecting_non_sample(
        self,
    ) -> None:
        """
        --refresh-passwords updates existing sample accounts to the seed hash
        while leaving custom non-sample user accounts completely unaffected.
        """
        # 1. Create a non-sample user account
        custom_email = "custom_staff_member@external-domain.org"
        custom_password = "StaffCustomPassword2026!"
        non_sample = Account.objects.create_user(
            email=custom_email,
            phone="0919998887",
            password=custom_password,
            role="EMPLOYEE",
        )

        # 2. Corrupt/set sample accounts to unusable passwords
        Account.objects.filter(email="hoang.dinh.khang@example.com").update(
            password=make_password(None)
        )
        tampered_mgr = Account.objects.get(email="hoang.dinh.khang@example.com")
        self.assertFalse(is_password_usable(tampered_mgr.password))

        # 3. Run load_sample_data with --refresh-passwords in dev mode
        out = io.StringIO()
        with override_settings(DEBUG=True):
            call_command("load_sample_data", refresh_passwords=True, stdout=out)

        self.assertIn(
            "Successfully refreshed passwords for 20 sample account(s).",
            out.getvalue(),
        )

        # 4. Confirm sample account password was refreshed and is now usable
        mgr = Account.objects.get(email="hoang.dinh.khang@example.com")
        self.assertTrue(is_password_usable(mgr.password))
        self.assertTrue(check_password(SHARED_DEV_PASSWORD, mgr.password))

        # 5. Confirm non-sample account was NOT touched and still uses custom password
        non_sample.refresh_from_db()
        self.assertTrue(check_password(custom_password, non_sample.password))
        self.assertFalse(check_password(SHARED_DEV_PASSWORD, non_sample.password))

    def test_refresh_passwords_ignored_in_production_mode(self) -> None:
        """When DEBUG=False, passing --refresh-passwords emits a warning and resets passwords to unusable."""
        out = io.StringIO()
        with override_settings(DEBUG=False):
            call_command(
                "load_sample_data",
                force_production=True,
                refresh_passwords=True,
                stdout=out,
            )

        output = out.getvalue()
        self.assertIn(
            "--refresh-passwords is ignored in production mode (DEBUG=False).", output
        )
        self.assertIn(
            "Resetting all sample account passwords to unusable hashes", output
        )

        mgr = Account.objects.get(email="hoang.dinh.khang@example.com")
        self.assertFalse(is_password_usable(mgr.password))

    def test_production_guard_blocks_without_force_flag(self) -> None:
        """Calling load_sample_data with DEBUG=False without --force-production raises CommandError."""
        with (
            override_settings(DEBUG=False),
            self.assertRaises(CommandError) as ctx,
        ):
            call_command("load_sample_data")
        self.assertIn(
            "Loading sample data in production (DEBUG=False) is disallowed",
            str(ctx.exception),
        )

    def test_missing_seed_file_raises_command_error(self) -> None:
        """CommandError raised if db/02-seed.sql does not exist."""
        with (
            patch("pathlib.Path.exists", return_value=False),
            override_settings(DEBUG=True),
            self.assertRaises(CommandError) as ctx,
        ):
            call_command("load_sample_data")
        self.assertIn("Seed file not found at", str(ctx.exception))

    def test_missing_sample_accounts_block_raises_command_error(self) -> None:
        """CommandError raised if seed file does not contain sample accounts block."""
        with (
            patch(
                "apps.core.management.commands.load_sample_data.parse_sample_accounts_from_seed",
                return_value=[],
            ),
            override_settings(DEBUG=True),
            self.assertRaises(CommandError) as ctx,
        ):
            call_command("load_sample_data")
        self.assertIn("No sample accounts found in seed file.", str(ctx.exception))

    def test_missing_sample_accounts_block_prevents_sql_execution(self) -> None:
        """Pre-validation ensures cursor.execute is NEVER called if sample_accounts parsing fails."""
        with (
            patch(
                "apps.core.management.commands.load_sample_data.parse_sample_accounts_from_seed",
                return_value=[],
            ),
            patch("django.db.connection.cursor") as mock_cursor,
            override_settings(DEBUG=False),
            self.assertRaises(CommandError),
        ):
            call_command("load_sample_data", force_production=True)
        mock_cursor.assert_not_called()
