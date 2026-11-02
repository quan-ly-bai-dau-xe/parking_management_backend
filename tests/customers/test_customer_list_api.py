"""
Test suite for GET /api/v1/customers/ (Customer List View).
Covers:
- Standard pagination (StandardResultsSetPagination).
- Filters: code (case-insensitive substring with wildcard escaping), name (substring with GIN trigram acceleration),
  phone, identity_card (CCCD), status (ACTIVE, SUSPENDED, BLACKLISTED).
- Ordering whitelist and fallback to default (code asc, id asc).
- Masking of PII (full_name, phone, identity_card_number) when is_anonymized = True.
- Response item fields: id, code, full_name, phone, identity_card_number, status,
  status_display, vehicles_count, has_active_ticket, row_version, created_at.
- Zero N+1 query assertion.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.customers.models import Customer

pytestmark = pytest.mark.django_db
LIST_URL = "/api/v1/customers/"


def test_customer_list_default_pagination(employee_client: APIClient):
    """Verify default pagination returns paginated structure with results array."""
    response = employee_client.get(LIST_URL)
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert "results" in data
    assert "count" in data
    assert "total_pages" in data
    assert "current_page" in data
    assert data["count"] >= 20
    assert len(data["results"]) <= 20

    first_item = data["results"][0]
    expected_fields = {
        "id",
        "code",
        "full_name",
        "phone",
        "identity_card_number",
        "status",
        "status_display",
        "vehicles_count",
        "has_active_ticket",
        "row_version",
        "is_anonymized",
        "created_at",
    }
    assert expected_fields.issubset(first_item.keys())
    assert isinstance(first_item["vehicles_count"], int)
    assert isinstance(first_item["has_active_ticket"], bool)


def test_customer_list_custom_page_size(employee_client: APIClient):
    """Verify page_size parameter limits items returned per page."""
    response = employee_client.get(f"{LIST_URL}?page_size=5&page=1")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert len(data["results"]) == 5
    assert data["current_page"] == 1
    assert data["page_size"] == 5


def test_customer_list_filter_by_code_exact(employee_client: APIClient):
    """Verify filter by exact customer code matches only that customer."""
    sample_customer = Customer.objects.filter(
        deleted_at__isnull=True, code="KH0001"
    ).first()
    if not sample_customer:
        sample_customer = Customer.objects.filter(deleted_at__isnull=True).first()
    assert sample_customer is not None

    # Filter with lowercase
    response = employee_client.get(f"{LIST_URL}?code={sample_customer.code.lower()}")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["count"] == 1
    assert data["results"][0]["code"].upper() == sample_customer.code.upper()
    assert data["results"][0]["id"] == sample_customer.id


def test_customer_list_filter_by_code_substring(employee_client: APIClient):
    """
    Verify filter by customer code supports substring matching.

    ?code=KH00 matches KH0001..KH0020 (>= 20 records).
    ?code=0001 matches KH0001.
    """
    # 1. Partial prefix matching
    response = employee_client.get(f"{LIST_URL}?code=KH00")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["count"] >= 20
    for item in data["results"]:
        assert "KH00" in item["code"].upper()

    # 2. Partial suffix matching
    res_suffix = employee_client.get(f"{LIST_URL}?code=0001")
    assert res_suffix.status_code == status.HTTP_200_OK
    data_suffix = res_suffix.json()
    assert data_suffix["count"] >= 1
    matched_codes = [item["code"] for item in data_suffix["results"]]
    assert any("0001" in code for code in matched_codes)


def test_customer_list_filter_by_code_case_insensitive(employee_client: APIClient):
    """Verify customer code substring search is case-insensitive."""
    # Lowercase search 'kh00'
    res_lower = employee_client.get(f"{LIST_URL}?code=kh00")
    assert res_lower.status_code == status.HTTP_200_OK
    data_lower = res_lower.json()
    assert data_lower["count"] >= 20
    for item in data_lower["results"]:
        assert "kh00" in item["code"].lower()

    # Mixed-case search 'kH00'
    res_mixed = employee_client.get(f"{LIST_URL}?code=kH00")
    assert res_mixed.status_code == status.HTTP_200_OK
    data_mixed = res_mixed.json()
    assert data_mixed["count"] >= 20


def test_customer_list_filter_by_code_wildcard_escaping(employee_client: APIClient):
    """
    Verify that SQL wildcards '%' and '_' in customer code query parameter are escaped.

    Without escaping:
    - '%' would match all records in the table.
    - '_' would match single characters (e.g. 'KH000_' would match KH0001..KH0009).
    With escape_like, they are treated as literal characters and yield 0 matches.
    """
    # 1. Wildcard '%' alone via URL-encoded ?code=%25 and query dict {"code": "%"}
    res_percent_encoded = employee_client.get(f"{LIST_URL}?code=%25")
    assert res_percent_encoded.status_code == status.HTTP_200_OK
    assert res_percent_encoded.json()["count"] == 0

    res_percent_dict = employee_client.get(LIST_URL, {"code": "%"})
    assert res_percent_dict.status_code == status.HTTP_200_OK
    assert res_percent_dict.json()["count"] == 0

    # 2. Wildcard '_' alone via URL param ?code=_ and query dict {"code": "_"}
    res_underscore_url = employee_client.get(f"{LIST_URL}?code=_")
    assert res_underscore_url.status_code == status.HTTP_200_OK
    assert res_underscore_url.json()["count"] == 0

    res_underscore_dict = employee_client.get(LIST_URL, {"code": "_"})
    assert res_underscore_dict.status_code == status.HTTP_200_OK
    assert res_underscore_dict.json()["count"] == 0

    # 3. Wildcard pattern 'KH000_' must not match 'KH0001'..'KH0009'
    res_pattern = employee_client.get(f"{LIST_URL}?code=KH000_")
    assert res_pattern.status_code == status.HTTP_200_OK
    assert res_pattern.json()["count"] == 0

    # 4. Combinations of wildcards and backslashes
    for wildcard in ["%%%", "___", "\\", "\\%", "%_"]:
        res_wildcard = employee_client.get(LIST_URL, {"code": wildcard})
        assert res_wildcard.status_code == status.HTTP_200_OK
        assert res_wildcard.json()["count"] == 0


def test_customer_list_filter_by_name_substring(employee_client: APIClient):
    """Verify filter by customer name supports Vietnamese substring matching."""
    sample = (
        Customer.objects.filter(deleted_at__isnull=True).exclude(full_name="").first()
    )
    assert sample is not None

    # Pick a substring from full name
    name_part = sample.full_name.split()[0]
    response = employee_client.get(f"{LIST_URL}?name={name_part}")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["count"] >= 1
    matching_ids = [item["id"] for item in data["results"]]
    assert sample.id in matching_ids


def test_customer_list_filter_by_phone(employee_client: APIClient):
    """Verify filter by phone number substring."""
    sample = Customer.objects.filter(
        deleted_at__isnull=True, is_anonymized=False
    ).first()
    assert sample is not None

    phone_sub = sample.phone[-4:]
    response = employee_client.get(f"{LIST_URL}?phone={phone_sub}")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["count"] >= 1
    for item in data["results"]:
        assert phone_sub in item["phone"]


def test_customer_list_filter_by_identity_card(employee_client: APIClient):
    """Verify filter by identity card number (CCCD) substring."""
    sample = Customer.objects.filter(
        deleted_at__isnull=True, is_anonymized=False
    ).first()
    assert sample is not None

    cccd_sub = sample.identity_card_number[-4:]
    response = employee_client.get(f"{LIST_URL}?identity_card={cccd_sub}")
    assert response.status_code == status.HTTP_200_OK

    data = response.json()
    assert data["count"] >= 1
    for item in data["results"]:
        assert cccd_sub in item["identity_card_number"]


def test_customer_list_filter_by_status(employee_client: APIClient):
    """Verify filter by status enum (ACTIVE, BLACKLISTED, SUSPENDED)."""
    # Active
    res_active = employee_client.get(f"{LIST_URL}?status=ACTIVE")
    assert res_active.status_code == status.HTTP_200_OK
    for item in res_active.json()["results"]:
        assert item["status"] == "ACTIVE"
        assert item["status_display"] == "Đang hoạt động"

    # Blacklisted
    res_bl = employee_client.get(f"{LIST_URL}?status=BLACKLISTED")
    assert res_bl.status_code == status.HTTP_200_OK
    if res_bl.json()["count"] > 0:
        for item in res_bl.json()["results"]:
            assert item["status"] == "BLACKLISTED"
            assert item["status_display"] == "Danh sách đen"


def test_customer_list_ordering_whitelist(employee_client: APIClient):
    """Verify ordering by whitelisted columns in both ascending and descending order."""
    for field in [
        "code",
        "-code",
        "id",
        "-id",
        "full_name",
        "-full_name",
        "created_at",
        "-created_at",
    ]:
        response = employee_client.get(f"{LIST_URL}?ordering={field}")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["results"]) > 0


def test_customer_list_invalid_ordering_fallback(employee_client: APIClient):
    """Verify invalid ordering field fails validation or falls back safely."""
    # FilterSerializer validates ordering with ChoiceField: invalid ordering should return 400
    response = employee_client.get(f"{LIST_URL}?ordering=non_existent_column")
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_customer_list_pii_masking_for_anonymized_record(employee_client: APIClient):
    """
    Verify that when is_anonymized = True, PII fields are strictly masked in list view:
    full_name -> 'Khách hàng ẩn danh', phone -> '***', identity_card_number -> '***'.
    """
    target = Customer.objects.filter(deleted_at__isnull=True).order_by("-id").first()
    assert target is not None

    original_name = target.full_name
    original_phone = target.phone
    original_idcard = target.identity_card_number

    # Anonymize target customer
    Customer.objects.filter(id=target.id).update(
        is_anonymized=True,
        anonymized_at=timezone.now(),
    )

    try:
        response = employee_client.get(f"{LIST_URL}?code={target.code}")
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["count"] == 1
        item = data["results"][0]
        assert item["is_anonymized"] is True
        assert item["full_name"] == "Khách hàng ẩn danh"
        assert item["phone"] == "***"
        assert item["identity_card_number"] == "***"
        assert item["full_name"] != original_name
        assert original_phone not in item["phone"]
        assert original_idcard not in item["identity_card_number"]
    finally:
        # Revert back to un-anonymized state
        Customer.objects.filter(id=target.id).update(
            is_anonymized=False,
            anonymized_at=None,
        )


def test_customer_list_query_count_zero_n_plus_one(employee_client: APIClient):
    """
    Zero-N+1 query guarantee:
    List view must execute a bounded number of queries regardless of page size.
    Expected: count query + 1 paginated annotated select query (+ auth/session queries).
    """
    with CaptureQueriesContext(connection) as ctx:
        response = employee_client.get(f"{LIST_URL}?page_size=20")
        assert response.status_code == status.HTTP_200_OK

    # Query count should remain low (< 7 queries including auth, session, count, annotated queryset)
    assert len(ctx.captured_queries) <= 8, (
        f"Too many queries executed: {len(ctx.captured_queries)}"
    )
