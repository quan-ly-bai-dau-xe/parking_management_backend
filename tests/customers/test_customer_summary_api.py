"""
Test suite for GET /api/v1/customers/summary/ (Customer Status Summary KPI API).
Covers:
- 4 KPI cards: total_customers, active_subscriptions, expiring_soon_subscriptions, blacklisted_or_suspended.
- Independent verification against raw PostgreSQL SQL queries.
- Comparison with database view v_customer_status_summary.
- Property testing: iterating through all seed customers and ensuring summary KPI numbers
  match list endpoint filters and single-source-of-truth calculations 100%.
- Verification of 7-day expiration window per TL-28.5 (TICKET_EXPIRING_SOON_DAYS).
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.customers.models import Customer
from apps.customers.selectors.customers import get_customer_status_summary
from apps.tickets.models import Ticket

pytestmark = pytest.mark.django_db
SUMMARY_URL = "/api/v1/customers/summary/"
LIST_URL = "/api/v1/customers/"


def test_customer_summary_api_success(employee_client: APIClient):
    """Verify customer summary endpoint returns 200 OK with all required KPI fields."""
    response = employee_client.get(SUMMARY_URL)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    expected_keys = {
        "total_customers",
        "active_subscriptions",
        "expiring_soon_subscriptions",
        "blacklisted_or_suspended",
    }
    assert expected_keys.issubset(data.keys())
    assert isinstance(data["total_customers"], int)
    assert isinstance(data["active_subscriptions"], int)
    assert isinstance(data["expiring_soon_subscriptions"], int)
    assert isinstance(data["blacklisted_or_suspended"], int)


def test_customer_summary_matches_independent_sql(employee_client: APIClient):
    """
    Independent SQL Verification:
    Directly execute raw PostgreSQL SQL queries to count each KPI and assert 100% agreement.
    """
    now = timezone.now()
    expiring_soon_days = getattr(settings, "TICKET_EXPIRING_SOON_DAYS", 7)
    expiring_soon_window = now + timedelta(days=expiring_soon_days)

    with connection.cursor() as cursor:
        # Total customers
        cursor.execute("SELECT COUNT(*) FROM customer WHERE deleted_at IS NULL;")
        expected_total = cursor.fetchone()[0]

        # Active subscribers (distinct customers having at least one active, unexpired ticket)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT c.id)
            FROM customer c
            INNER JOIN ticket t ON t.customer_id = c.id
            WHERE c.deleted_at IS NULL
              AND t.deleted_at IS NULL
              AND t.status IN ('ACTIVE', 'RENEWING')
              AND t.effective_to > %s;
            """,
            [now],
        )
        expected_active_subscribers = cursor.fetchone()[0]

        # Expiring soon subscribers (distinct customers having at least one ticket expiring in <= 7 days)
        cursor.execute(
            """
            SELECT COUNT(DISTINCT c.id)
            FROM customer c
            INNER JOIN ticket t ON t.customer_id = c.id
            WHERE c.deleted_at IS NULL
              AND t.deleted_at IS NULL
              AND t.status IN ('ACTIVE', 'RENEWING')
              AND t.effective_to > %s
              AND t.effective_to <= %s;
            """,
            [now, expiring_soon_window],
        )
        expected_expiring_soon = cursor.fetchone()[0]

        # Blacklisted or suspended customers
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM customer
            WHERE deleted_at IS NULL
              AND status IN ('SUSPENDED', 'BLACKLISTED');
            """
        )
        expected_blacklisted_or_suspended = cursor.fetchone()[0]

    response = employee_client.get(SUMMARY_URL)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["total_customers"] == expected_total
    assert data["active_subscriptions"] == expected_active_subscribers
    assert data["expiring_soon_subscriptions"] == expected_expiring_soon
    assert data["blacklisted_or_suspended"] == expected_blacklisted_or_suspended


def test_customer_summary_matches_database_view(employee_client: APIClient):
    """
    Compare summary numbers with PostgreSQL view v_customer_status_summary.
    Total customers and (suspended + blacklisted) must align exactly with the view.
    """
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT total_customers, suspended_customers, blacklisted_customers
            FROM v_customer_status_summary;
            """
        )
        row = cursor.fetchone()
        assert row is not None
        v_total, v_suspended, v_blacklisted = row

    response = employee_client.get(SUMMARY_URL)
    assert response.status_code == status.HTTP_200_OK
    data = response.json()

    assert data["total_customers"] == v_total
    assert data["blacklisted_or_suspended"] == (v_suspended + v_blacklisted)


def test_customer_summary_property_all_seed_customers(employee_client: APIClient):
    """
    Property test across all seed customers:
    For every customer in the database, calculate whether they contribute to each KPI card,
    sum them up, and verify that the API summary returns the exact same aggregated counts.
    """
    now = timezone.now()
    expiring_soon_days = getattr(settings, "TICKET_EXPIRING_SOON_DAYS", 7)
    expiring_soon_window = now + timedelta(days=expiring_soon_days)

    customers = Customer.objects.filter(deleted_at__isnull=True)
    prop_total = 0
    prop_active_subs = 0
    prop_expiring_soon = 0
    prop_bl_or_susp = 0

    for cust in customers:
        prop_total += 1

        if cust.status in ["SUSPENDED", "BLACKLISTED"]:
            prop_bl_or_susp += 1

        active_tickets = Ticket.objects.filter(
            customer_id=cust.id,
            deleted_at__isnull=True,
            status__in=["ACTIVE", "RENEWING"],
            effective_to__gt=now,
        )
        if active_tickets.exists():
            prop_active_subs += 1

        expiring_tickets = active_tickets.filter(effective_to__lte=expiring_soon_window)
        if expiring_tickets.exists():
            prop_expiring_soon += 1

    summary_result = get_customer_status_summary(now=now)

    assert summary_result["total_customers"] == prop_total
    assert summary_result["active_subscriptions"] == prop_active_subs
    assert summary_result["expiring_soon_subscriptions"] == prop_expiring_soon
    assert summary_result["blacklisted_or_suspended"] == prop_bl_or_susp

    # Also check against the HTTP API
    response = employee_client.get(SUMMARY_URL)
    assert response.status_code == status.HTTP_200_OK
    api_data = response.json()
    assert api_data["total_customers"] == prop_total
    assert api_data["blacklisted_or_suspended"] == prop_bl_or_susp


def test_customer_summary_matches_list_filters(employee_client: APIClient):
    """
    Verify that list filtering by status aligns with the summary's count.
    Total customers in list equals total_customers in summary.
    List filtered by status=SUSPENDED + status=BLACKLISTED equals blacklisted_or_suspended.
    """
    summary_resp = employee_client.get(SUMMARY_URL)
    assert summary_resp.status_code == status.HTTP_200_OK
    summary_data = summary_resp.json()

    # Total from list
    list_total_resp = employee_client.get(LIST_URL)
    assert list_total_resp.status_code == status.HTTP_200_OK
    assert list_total_resp.json()["count"] == summary_data["total_customers"]

    # Suspended from list
    list_susp_resp = employee_client.get(f"{LIST_URL}?status=SUSPENDED")
    susp_count = list_susp_resp.json()["count"]

    # Blacklisted from list
    list_bl_resp = employee_client.get(f"{LIST_URL}?status=BLACKLISTED")
    bl_count = list_bl_resp.json()["count"]

    assert (susp_count + bl_count) == summary_data["blacklisted_or_suspended"]
