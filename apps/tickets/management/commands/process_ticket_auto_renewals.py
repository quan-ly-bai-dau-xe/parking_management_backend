"""
Management command to process automatic subscription ticket renewals (WP4 R2 & D6).
Usage:
    python manage.py process_ticket_auto_renewals
    python manage.py process_ticket_auto_renewals --dry-run
"""

from typing import Any

from django.core.management.base import BaseCommand

from apps.tickets.services.auto_renewal import process_ticket_auto_renewals


class Command(BaseCommand):
    help = (
        "Quét và tự động gia hạn các vé tháng/quý/năm đến hạn trong ngày "
        "(Asia/Ho_Chi_Minh) bằng số dư ví khách hàng."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Chỉ kiểm tra số lượng vé đến hạn mà không ghi dữ liệu.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        dry_run = bool(options.get("dry_run", False))
        summary = process_ticket_auto_renewals(dry_run=dry_run)
        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}process_ticket_auto_renewals completed: "
                f"checked={summary['checked']}, "
                f"renewed={summary['renewed']}, "
                f"expired={summary['expired']}, "
                f"skipped={summary['skipped']}, "
                f"errors={summary['errors']}"
            )
        )
