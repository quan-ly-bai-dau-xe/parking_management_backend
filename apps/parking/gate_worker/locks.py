"""
PostgreSQL session-level advisory lock manager for gate worker process serialization.
Adheres to ADR-0011 Section 2.6 (TL-70, TL-72).
Serializes gate ownership across multiple worker replicas:
SELECT pg_try_advisory_lock(1195463749, gate_id);
1195463749 is 'GATE' in ASCII.
Dedicated raw connection ensures locks persist across Django transactions and release on disconnect.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from typing import Any

from django.db import connection

logger = logging.getLogger(__name__)

# ASCII code for 'GATE' (0x47415445 = 1195463749) per ADR-0011 Section 2.6
DEFAULT_GATE_LOCK_NAMESPACE = 1195463749

# In-memory lock fallback registry for non-PostgreSQL databases (e.g., SQLite in unit tests)
_MOCK_LOCK_REGISTRY: set[tuple[int, int]] = set()
_MOCK_LOCK_MUTEX = threading.Lock()


def get_active_gate_worker_lock_ids() -> set[int]:
    """
    Query active advisory locks held by gate worker processes.

    In PostgreSQL, inspects the pg_locks system catalog:
    SELECT l.objid FROM pg_locks l
    JOIN pg_database d ON l.database = d.oid
    WHERE d.datname = current_database()
      AND l.locktype = 'advisory'
      AND l.classid = %s
      AND l.objsubid IN (1, 2)
      AND l.granted = true;
    with classid = DEFAULT_GATE_LOCK_NAMESPACE (1195463749).
    Note: objsubid is 2 for two-key 32-bit session-level advisory locks (pg_try_advisory_lock(int4, int4)),
    and 1 for single 64-bit session-level locks.

    In non-PostgreSQL environments (e.g. SQLite during unit tests),
    falls back to reading _MOCK_LOCK_REGISTRY.

    Returns:
        set of gate_ids that are currently locked by an active worker.
    """
    if connection.vendor == "postgresql":
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT l.objid FROM pg_locks l "
                    "JOIN pg_database d ON l.database = d.oid "
                    "WHERE d.datname = current_database() "
                    "AND l.locktype = 'advisory' "
                    "AND l.classid = %s "
                    "AND l.objsubid IN (1, 2) "
                    "AND l.granted = true;",
                    (DEFAULT_GATE_LOCK_NAMESPACE,),
                )
                rows = cursor.fetchall()
                return {int(row[0]) for row in rows}
        except Exception as exc:
            logger.error(
                "Failed to query pg_locks for active gate worker locks: %s", exc
            )
            return set()
    else:
        with _MOCK_LOCK_MUTEX:
            return {
                gate_id
                for ns, gate_id in _MOCK_LOCK_REGISTRY
                if ns == DEFAULT_GATE_LOCK_NAMESPACE
            }


def clear_mock_lock_registry() -> None:
    """Clear all mock advisory locks (primarily for unit test isolation)."""
    with _MOCK_LOCK_MUTEX:
        _MOCK_LOCK_REGISTRY.clear()


class GateAdvisoryLock:
    """
    Manages a PostgreSQL session-level advisory lock on a specific gate.
    Uses an independent, dedicated raw database connection to ensure the lock
    remains held for the worker's entire lifecycle and does not get recycled by conn_max_age.
    """

    def __init__(
        self,
        gate_id: int,
        lock_namespace: int = DEFAULT_GATE_LOCK_NAMESPACE,
    ) -> None:
        self.gate_id = int(gate_id)
        self.lock_namespace = int(lock_namespace)
        self._raw_conn: Any = None
        self._is_locked: bool = False

    @property
    def is_locked(self) -> bool:
        """True if the lock was successfully acquired and is currently held."""
        return self._is_locked

    def acquire(self) -> bool:
        """
        Attempt to acquire the advisory lock non-blockingly.

        Returns:
            True if lock was acquired, False if another worker currently owns this gate.
        """
        if self._is_locked:
            return True

        if connection.vendor == "postgresql":
            try:
                # Open an independent dedicated raw psycopg connection
                conn_params = connection.get_connection_params()
                self._raw_conn = connection.get_new_connection(conn_params)
                # Ensure autocommit mode so session lock is not bound to a transaction block
                if hasattr(self._raw_conn, "autocommit"):
                    self._raw_conn.autocommit = True

                with self._raw_conn.cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_try_advisory_lock(%s, %s);",
                        (self.lock_namespace, self.gate_id),
                    )
                    row = cursor.fetchone()
                    acquired = bool(row[0]) if row else False

                if acquired:
                    self._is_locked = True
                    logger.info(
                        "Acquired PostgreSQL advisory lock for gate #%d (namespace %d)",
                        self.gate_id,
                        self.lock_namespace,
                    )
                    return True

                # Failed to acquire lock - another worker replica owns the gate
                logger.info(
                    "Gate #%d is already owned by another worker replica, skipping.",
                    self.gate_id,
                )
                self.release()
                return False

            except Exception as exc:
                logger.error(
                    "Failed to acquire advisory lock for gate #%d: %s",
                    self.gate_id,
                    exc,
                )
                self.release()
                return False
        else:
            # Fallback for non-PostgreSQL (SQLite/Mock)
            with _MOCK_LOCK_MUTEX:
                key = (self.lock_namespace, self.gate_id)
                if key in _MOCK_LOCK_REGISTRY:
                    logger.info(
                        "Gate #%d is locked in mock registry, skipping.",
                        self.gate_id,
                    )
                    return False
                _MOCK_LOCK_REGISTRY.add(key)
                self._is_locked = True
                return True

    def release(self) -> None:
        """
        Release the advisory lock and close the dedicated raw database connection.
        """
        if connection.vendor == "postgresql":
            if self._raw_conn is not None:
                try:
                    if self._is_locked:
                        with self._raw_conn.cursor() as cursor:
                            cursor.execute(
                                "SELECT pg_advisory_unlock(%s, %s);",
                                (self.lock_namespace, self.gate_id),
                            )
                except Exception as exc:
                    logger.debug(
                        "Advisory unlock notice for gate #%d: %s",
                        self.gate_id,
                        exc,
                    )
                finally:
                    with contextlib.suppress(Exception):
                        self._raw_conn.close()
                    self._raw_conn = None
        else:
            with _MOCK_LOCK_MUTEX:
                key = (self.lock_namespace, self.gate_id)
                _MOCK_LOCK_REGISTRY.discard(key)

        self._is_locked = False

    def __enter__(self) -> GateAdvisoryLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.release()
