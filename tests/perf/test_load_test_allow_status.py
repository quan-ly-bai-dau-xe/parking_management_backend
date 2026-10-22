"""
Unit tests for load_test.py --allow-status CLI argument and fatal error counting logic.
Ensures parser handles exact HTTP codes and wildcard patterns (2xx, 5xx),
and verifies count_fatal_errors correctly distinguishes allowed vs fatal codes without server.
"""

from __future__ import annotations

from tests.perf.load_test import (
    ScenarioStats,
    count_fatal_errors,
    is_status_allowed,
    parse_allow_status,
)


def test_parse_allow_status_default():
    """Verifies default parse_allow_status matches '2xx,503'."""
    parsed = parse_allow_status("2xx,503")
    assert "2xx" in parsed
    assert 503 in parsed
    assert len(parsed) == 2


def test_parse_allow_status_custom_tokens():
    """Verifies parsing comma-separated exact codes, wildcards, and trimming."""
    parsed = parse_allow_status(" 200, 201, 400 , 404, 5xx , 503 ")
    assert 200 in parsed
    assert 201 in parsed
    assert 400 in parsed
    assert 404 in parsed
    assert "5xx" in parsed
    assert 503 in parsed


def test_is_status_allowed_wildcard_and_exact():
    """Verifies is_status_allowed matches exact integers and xx wildcards."""
    allowed = {"2xx", 503, 404}
    assert is_status_allowed(200, allowed) is True
    assert is_status_allowed(201, allowed) is True
    assert is_status_allowed(204, allowed) is True
    assert is_status_allowed(503, allowed) is True
    assert is_status_allowed(404, allowed) is True
    assert is_status_allowed(400, allowed) is False
    assert is_status_allowed(500, allowed) is False
    assert is_status_allowed(301, allowed) is False


def test_count_fatal_errors_default():
    """Verifies count_fatal_errors treats non-2xx and non-503 as fatal by default."""
    stats = ScenarioStats(
        scenario_name="test",
        concurrency=1,
        duration_s=1.0,
        total_requests=21,
        successful_requests=15,
        rps=21.0,
        p50_ms=10.0,
        p95_ms=20.0,
        p99_ms=25.0,
        max_ms=30.0,
        status_counts={
            "200": 10,
            "201": 5,
            "503": 2,
            "400": 3,
            "500": 1,
            "ERR": 1,
        },
    )
    # 400 (3) + 500 (1) + ERR (1) = 5 fatal errors
    fatal = count_fatal_errors([stats])
    assert fatal == 5


def test_count_fatal_errors_custom_allow_status():
    """Verifies count_fatal_errors respects custom allowed status set."""
    stats = ScenarioStats(
        scenario_name="negative_test",
        concurrency=4,
        duration_s=2.0,
        total_requests=68,
        successful_requests=50,
        rps=34.0,
        p50_ms=12.0,
        p95_ms=22.0,
        p99_ms=28.0,
        max_ms=35.0,
        status_counts={
            "200": 50,
            "400": 10,
            "404": 5,
            "503": 2,
            "500": 1,
        },
    )
    # Allow 2xx, 400, 404, 503
    custom_allow = parse_allow_status("2xx,400,404,503")
    fatal = count_fatal_errors([stats], allow_status=custom_allow)
    # Only 500 is fatal (1)
    assert fatal == 1
