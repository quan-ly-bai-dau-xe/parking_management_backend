"""
Pytest configuration and shared fixtures for accounts test suite.
"""

from collections.abc import Generator

import pytest
from django.core.cache import cache
from django.db import connections


@pytest.fixture(autouse=True)
def force_db_conn_max_age_zero() -> None:
    """
    Ensure all database connections have CONN_MAX_AGE = 0 during accounts tests,
    preventing persistent connections from blocking DROP DATABASE or leaking sockets.
    Conforms to Option (a) without touching config/settings/test.py.
    """
    for conn in connections.all():
        conn.settings_dict["CONN_MAX_AGE"] = 0


@pytest.fixture(scope="session", autouse=True)
def close_connections_at_session_end() -> Generator[None]:
    """Close all database connections at the end of the accounts test session."""
    try:
        yield
    finally:
        connections.close_all()


@pytest.fixture(autouse=True)
def clear_cache_between_tests() -> Generator[None]:
    """
    Autouse fixture that clears the default Django cache before and after each test.
    Ensures tests do not leak cache state or depend on execution order per TL-52.
    """
    cache.clear()
    try:
        yield
    finally:
        cache.clear()
