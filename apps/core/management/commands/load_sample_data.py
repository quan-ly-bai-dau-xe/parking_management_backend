from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Loads seed data from db/02-seed.sql idempotently."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force-production",
            action="store_true",
            help="Force loading sample data when DEBUG=False.",
        )

    def handle(self, *args, **options):
        if not settings.DEBUG and not options.get("force_production"):
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

        self.stdout.write("Executing seed SQL...")
        with connection.cursor() as cursor:
            cursor.execute(seed_sql)

        self.stdout.write(self.style.SUCCESS("Sample seed data loaded successfully."))
