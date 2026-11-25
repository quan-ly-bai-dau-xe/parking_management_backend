"""
Gate worker process package (ADR-0011, TL-66 to TL-77).
Provides autonomous background stream ingestion, motion pre-filtering,
temporal plate voting, advisory locks, and barrier auto-apply coordination.
"""

from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
from apps.parking.gate_worker.filter import MotionFilter
from apps.parking.gate_worker.locks import GateAdvisoryLock
from apps.parking.gate_worker.reader import StreamReader
from apps.parking.gate_worker.voter import PlateVoter

__all__ = [
    "GateAdvisoryLock",
    "GateWorkerCoordinator",
    "MotionFilter",
    "PlateVoter",
    "StreamReader",
]
