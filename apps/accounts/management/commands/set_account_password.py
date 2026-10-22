"""
Management command to safely set an account password for local development or seeded accounts.
Per TL-52, passwords are never accepted via CLI arguments to prevent shell history leakage,
and passwords are never printed to stdout/stderr.
"""

from __future__ import annotations

import argparse
import getpass
import os

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.selectors.auth import get_active_account_by_identifier


class Command(BaseCommand):
    help = "Safely sets a password for an active account using an environment variable or interactive prompt."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--identifier",
            type=str,
            required=True,
            help="Email or phone number of the target account.",
        )

    def handle(self, *args: object, **options: object) -> None:
        identifier = str(options.get("identifier") or "").strip()
        if not identifier:
            raise CommandError("Identifier cannot be empty.")

        account = get_active_account_by_identifier(identifier)
        if account is None:
            raise CommandError(
                f"Active account with identifier '{identifier}' not found."
            )

        # Check environment variable first per TL-52
        password = os.environ.get("ACCOUNT_PASSWORD")
        if password is not None:
            if not password.strip():
                raise CommandError(
                    "ACCOUNT_PASSWORD environment variable cannot be empty."
                )
            target_password = password
        else:
            # Prompt interactively without echoing
            p1 = getpass.getpass("Enter password: ")
            p2 = getpass.getpass("Confirm password: ")
            if p1 != p2:
                raise CommandError("Passwords do not match.")
            if not p1.strip():
                raise CommandError("Password cannot be empty.")
            target_password = p1

        account.set_password(target_password)
        account.save(update_fields=["password"])

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully updated password for account #{account.id} ({identifier})."
            )
        )
