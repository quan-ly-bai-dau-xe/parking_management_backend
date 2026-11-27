"""
Management command to verify wallet balance == SUM(wallet_transaction.amount) across all wallets.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from apps.wallet.models import Wallet


class Command(BaseCommand):
    help = "Reconcile wallet.balance against SUM(wallet_transaction.amount) for every wallet."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--fail-on-mismatch",
            action="store_true",
            help="Exit with CommandError if any wallet balance mismatches its ledger sum.",
        )

    def handle(self, *args, **options) -> None:
        wallets = Wallet.all_objects.annotate(
            ledger_sum=Sum("transactions__amount")
        ).order_by("id")

        mismatches = []
        total_checked = 0
        for w in wallets:
            total_checked += 1
            ledger_total = w.ledger_sum if w.ledger_sum is not None else Decimal("0.00")
            if w.balance != ledger_total:
                mismatches.append((w.id, w.customer_id, w.balance, ledger_total))

        if mismatches:
            for wid, cid, bal, lsum in mismatches:
                self.stderr.write(
                    self.style.ERROR(
                        f"MISMATCH wallet_id={wid} customer_id={cid}: balance={bal} ledger_sum={lsum}"
                    )
                )
            if options.get("fail_on_mismatch"):
                raise CommandError(
                    f"Detected {len(mismatches)} wallet reconciliation mismatch(es) out of {total_checked} wallet(s)."
                )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Reconciliation passed: {total_checked} wallet(s) checked, 0 mismatches."
                )
            )
