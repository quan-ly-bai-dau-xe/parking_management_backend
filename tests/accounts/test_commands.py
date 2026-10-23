"""
Management Commands Test Suite per TL-36 and TL-52.
Tests set_account_password and purge_expired_login_tokens.
"""

from __future__ import annotations

import io
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Account, PersistentLoginToken


class SetAccountPasswordCommandTest(TestCase):
    """
    Tests the set_account_password management command per TL-52.
    """

    def setUp(self) -> None:
        self.account = Account.objects.create_user(
            email="command_user@parking.com",
            phone="0988776655",
            password="InitialPassword123!",
            role="EMPLOYEE",
        )

    def test_set_password_via_environment_variable(self) -> None:
        """
        Sets password using the ACCOUNT_PASSWORD environment variable without prompting.
        """
        new_password = "EnvPassword456!@"
        out = io.StringIO()

        with patch.dict("os.environ", {"ACCOUNT_PASSWORD": new_password}):
            call_command(
                "set_account_password",
                identifier="command_user@parking.com",
                stdout=out,
            )

        output = out.getvalue()
        self.assertIn("Successfully updated password", output)
        self.assertNotIn(new_password, output)  # Plaintext password must never leak!

        self.account.refresh_from_db()
        self.assertTrue(self.account.check_password(new_password))

    def test_set_password_via_interactive_prompt(self) -> None:
        """
        Sets password interactively using getpass when env var is not set.
        """
        new_password = "PromptPassword789!#"
        out = io.StringIO()

        with (
            patch.dict("os.environ", {}, clear=True),
            patch("getpass.getpass", side_effect=[new_password, new_password]),
        ):
            call_command(
                "set_account_password",
                identifier="0988776655",
                stdout=out,
            )

        output = out.getvalue()
        self.assertIn("Successfully updated password", output)
        self.assertNotIn(new_password, output)

        self.account.refresh_from_db()
        self.assertTrue(self.account.check_password(new_password))

    def test_set_password_fails_for_unknown_account(self) -> None:
        """
        Raises CommandError when target account does not exist.
        """
        out = io.StringIO()
        with (
            patch.dict("os.environ", {"ACCOUNT_PASSWORD": "NewPassword123!"}),
            self.assertRaises(CommandError) as ctx,
        ):
            call_command(
                "set_account_password",
                identifier="nonexistent@parking.com",
                stdout=out,
            )

        self.assertIn("not found", str(ctx.exception))

    def test_set_password_fails_when_passwords_do_not_match(self) -> None:
        """
        Raises CommandError when interactive confirmation password does not match.
        """
        out = io.StringIO()
        with (
            patch.dict("os.environ", {}, clear=True),
            patch("getpass.getpass", side_effect=["PasswordA123!", "PasswordB456!"]),
            self.assertRaises(CommandError) as ctx,
        ):
            call_command(
                "set_account_password",
                identifier="command_user@parking.com",
                stdout=out,
            )

        self.assertIn("do not match", str(ctx.exception))

    def test_set_password_fails_for_empty_password(self) -> None:
        """
        Raises CommandError when empty password is provided via environment variable.
        """
        out = io.StringIO()
        with (
            patch.dict("os.environ", {"ACCOUNT_PASSWORD": "   "}),
            self.assertRaises(CommandError) as ctx,
        ):
            call_command(
                "set_account_password",
                identifier="command_user@parking.com",
                stdout=out,
            )

        self.assertIn("cannot be empty", str(ctx.exception))


class PurgeExpiredLoginTokensCommandTest(TestCase):
    """
    Tests the purge_expired_login_tokens management command per TL-36 and TL-52.
    """

    def setUp(self) -> None:
        self.account = Account.objects.create_user(
            email="purge_user@parking.com",
            phone="0977665544",
            password="Password123!",
            role="CUSTOMER",
        )
        now = timezone.now()

        # Create 2 expired tokens
        self.expired_token1 = PersistentLoginToken.objects.create(
            series="exp_series_1",
            token_hash="hash1",
            account=self.account,
            created_at=now - timedelta(days=35),
            last_used_at=now - timedelta(days=35),
            expires_at=now - timedelta(days=5),
        )
        self.expired_token2 = PersistentLoginToken.objects.create(
            series="exp_series_2",
            token_hash="hash2",
            account=self.account,
            created_at=now - timedelta(days=40),
            last_used_at=now - timedelta(days=40),
            expires_at=now - timedelta(days=10),
        )

        # Create 1 active token
        self.active_token = PersistentLoginToken.objects.create(
            series="active_series",
            token_hash="hash_active",
            account=self.account,
            created_at=now,
            last_used_at=now,
            expires_at=now + timedelta(days=30),
        )

    def test_purge_dry_run_does_not_delete_records(self) -> None:
        """
        Default dry-run mode reports eligible expired tokens without deleting them.
        """
        out = io.StringIO()
        call_command("purge_expired_login_tokens", stdout=out)

        output = out.getvalue()
        self.assertIn("DRY RUN", output)
        self.assertIn("Found 2 expired login token(s)", output)

        # Records must still exist in database
        self.assertTrue(
            PersistentLoginToken.objects.filter(series="exp_series_1").exists()
        )
        self.assertTrue(
            PersistentLoginToken.objects.filter(series="exp_series_2").exists()
        )
        self.assertTrue(
            PersistentLoginToken.objects.filter(series="active_series").exists()
        )

    def test_purge_no_dry_run_deletes_expired_tokens_and_preserves_active(self) -> None:
        """
        Running with --no-dry-run deletes expired tokens while preserving active tokens.
        """
        out = io.StringIO()
        call_command("purge_expired_login_tokens", dry_run=False, stdout=out)

        output = out.getvalue()
        self.assertIn("Successfully purged 2 expired login token(s)", output)

        # Expired tokens must be deleted
        self.assertFalse(
            PersistentLoginToken.objects.filter(series="exp_series_1").exists()
        )
        self.assertFalse(
            PersistentLoginToken.objects.filter(series="exp_series_2").exists()
        )

        # Active token must remain intact
        self.assertTrue(
            PersistentLoginToken.objects.filter(series="active_series").exists()
        )

    def test_purge_force_flag_deletes_expired_tokens(self) -> None:
        """
        Running with --force bypasses dry-run and executes deletion.
        """
        out = io.StringIO()
        call_command("purge_expired_login_tokens", force=True, stdout=out)

        output = out.getvalue()
        self.assertIn("Successfully purged 2 expired login token(s)", output)
        self.assertEqual(
            PersistentLoginToken.objects.filter(account=self.account).count(), 1
        )
