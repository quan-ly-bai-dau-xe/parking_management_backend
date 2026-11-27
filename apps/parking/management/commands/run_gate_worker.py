"""
Django management command to run the autonomous background gate worker process.
Adheres to ADR-0011 Section 2.1 & 2.7 (TL-66 to TL-77).

Usage:
    python manage.py run_gate_worker
    python manage.py run_gate_worker --gate IN_01
    python manage.py run_gate_worker --duration 10
"""

from __future__ import annotations

import argparse
from typing import Any

from django.core.management.base import BaseCommand

from apps.parking.gate_worker.coordinator import GateWorkerCoordinator


class Command(BaseCommand):
    help = (
        "Runs the background gate worker process for headless camera stream "
        "ingestion, license plate recognition, and autonomous barrier control."
    )

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument(
            "--gate",
            type=str,
            default=None,
            help="Filter and manage specific gate codes or IDs (comma-separated, e.g. '--gate IN_01,IN_02' or '--gate 1,2').",
        )
        parser.add_argument(
            "--duration",
            type=float,
            default=None,
            help="Run worker for N seconds and then exit cleanly (useful for bounded tests and health probes).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        gate_arg = options.get("gate")
        duration = options.get("duration")

        self.stdout.write(
            self.style.SUCCESS(
                f"Starting Gate Worker Process (gate={gate_arg or 'ALL'}, "
                f"duration={f'{duration}s' if duration else 'infinite'})..."
            )
        )

        coordinator = GateWorkerCoordinator(gate_code_filter=gate_arg)
        initialized = coordinator.initialize()
        self.stdout.write(
            self.style.SUCCESS(f"Initialized {initialized} active gate camera streams.")
        )

        coordinator.run(duration=float(duration) if duration is not None else None)
        self.stdout.write(self.style.SUCCESS("Gate Worker Process stopped cleanly."))
