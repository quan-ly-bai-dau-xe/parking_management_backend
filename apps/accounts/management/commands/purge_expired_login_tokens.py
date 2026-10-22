"""
Management command to purge expired persistent login tokens per ADR-0004, TL-36, and D7.
Token tables are exempted from immutable table triggers per TL-36, permitting plain DELETE.
By default, runs in dry-run mode unless --no-dry-run or --force is explicitly provided.
"""

from __future__ import annotations

import argparse

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import PersistentLoginToken


class Command(BaseCommand):
    help = (
        "Purges expired persistent remember-me login tokens (plain DELETE per TL-36)."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--dry-run",
            action=argparse.BooleanOptionalAction,
            default=True,
            help="Simulate cleanup without deleting database records (default: True). Use --no-dry-run to execute.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            default=False,
            help="Bypass dry-run and permanently delete expired tokens.",
        )

    def handle(self, *args: object, **options: object) -> None:
        dry_run = bool(options.get("dry_run", True))
        if options.get("force", False):
            dry_run = False

        now = timezone.now()
        expired_qs = PersistentLoginToken.objects.filter(expires_at__lt=now)
        count = expired_qs.count()

        if dry_run:
            self.stdout.write(
                self.style.NOTICE(
                    f"DRY RUN: Found {count} expired login token(s) eligible for purging. No records were deleted."
                )
            )
            return

        deleted_count, _ = expired_qs.delete()
        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully purged {deleted_count} expired login token(s)."
            )
        )
