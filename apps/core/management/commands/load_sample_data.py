from __future__ import annotations

import argparse
import re
from pathlib import Path

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


def parse_sample_accounts_from_seed(seed_sql: str) -> list[tuple[str, str]]:
    """
    Extract (email, password_hash) tuples for sample accounts from seed SQL.
    Targets only the 2.6. SYSTEM ACCOUNTS block in db/02-seed.sql.
    """
    match = re.search(
        r"INSERT INTO account\s*\([^)]+\)\s*VALUES\s*(.*?)\s*ON CONFLICT",
        seed_sql,
        re.DOTALL,
    )
    if not match:
        return []
    raw_accounts = re.findall(
        r"\(\s*'([^']+@[^']+)'\s*,\s*'([0-9]+)'\s*,\s*'([^']+)'",
        match.group(1),
    )
    return [(email.lower(), pwd_hash) for email, _, pwd_hash in raw_accounts]


class Command(BaseCommand):
    help = "Loads seed data from db/02-seed.sql idempotently."

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--force-production",
            action="store_true",
            help="Force loading sample data when DEBUG=False.",
        )
        parser.add_argument(
            "--refresh-passwords",
            action="store_true",
            help="Refresh sample account passwords from seed file on an already-seeded database.",
        )

    def handle(self, *args: object, **options: object) -> None:
        is_production = not settings.DEBUG
        force_production = bool(options.get("force_production"))
        refresh_passwords = bool(options.get("refresh_passwords"))

        if is_production and not force_production:
            raise CommandError(
                "Loading sample data in production (DEBUG=False) is disallowed. "
                "Pass --force-production if you really intend to do this."
            )

        seed_path = Path(settings.BASE_DIR) / "db" / "02-seed.sql"
        if not seed_path.exists():
            raise CommandError(f"Seed file not found at: {seed_path}")

        self.stdout.write(f"Loading seed data from: {seed_path}")
        with open(seed_path, encoding="utf-8") as f:
            seed_sql = f.read()

        # Pre-validate sample accounts from seed file BEFORE executing SQL to ensure
        # production safety reset cannot be bypassed if seed parsing fails.
        sample_accounts = parse_sample_accounts_from_seed(seed_sql)
        if not sample_accounts:
            raise CommandError("No sample accounts found in seed file.")

        self.stdout.write("Executing seed SQL...")
        with connection.cursor() as cursor:
            cursor.execute(seed_sql)

        self.stdout.write(self.style.SUCCESS("Sample seed data loaded successfully."))

        if is_production:
            if refresh_passwords:
                self.stdout.write(
                    self.style.WARNING(
                        "--refresh-passwords is ignored in production mode (DEBUG=False)."
                    )
                )
            self.stdout.write(
                self.style.WARNING(
                    "Production mode detected (DEBUG=False): Resetting all sample account passwords to unusable hashes for security."
                )
            )
            reset_count = 0
            with connection.cursor() as cursor:
                for email, _ in sample_accounts:
                    cursor.execute(
                        "UPDATE account SET password_hash = %s WHERE lower(email) = %s AND deleted_at IS NULL",
                        [make_password(None), email],
                    )
                    reset_count += cursor.rowcount
            self.stdout.write(
                self.style.WARNING(
                    f"Reset {reset_count} sample account(s) to unusable password hashes."
                )
            )
        elif refresh_passwords:
            refreshed_count = 0
            with connection.cursor() as cursor:
                for email, pwd_hash in sample_accounts:
                    cursor.execute(
                        "UPDATE account SET password_hash = %s WHERE lower(email) = %s AND deleted_at IS NULL",
                        [pwd_hash, email],
                    )
                    refreshed_count += cursor.rowcount
            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully refreshed passwords for {refreshed_count} sample account(s)."
                )
            )
