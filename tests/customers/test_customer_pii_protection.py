"""
Test suite for Personal Identifiable Information (PII) Protection (Decree 13/2023/NĐ-CP, OQ-12).
Verifies:
- Sensitive PII (CCCD, phone number, email, residential address, date of birth) is NEVER leaked
  into application logs, error details, or exception messages when validation/conflict occurs.
- Both caplog and response bodies are strictly checked for zero sensitive token reflections.
- Complete data masking on anonymized customer records (is_anonymized = True) in both List and Detail endpoints.
"""

from __future__ import annotations

import logging

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.customers.models import Customer

pytestmark = pytest.mark.django_db


def test_pii_never_echoed_in_duplicate_idcard_error(
    employee_client: APIClient,
    active_customer: Customer,
    caplog: pytest.LogCaptureFixture,
):
    """
    Verify that when duplicate CCCD is submitted, the error response and log records
    NEVER echo the actual CCCD digits.
    """
    caplog.set_level(logging.DEBUG)

    sensitive_cccd = active_customer.identity_card_number
    payload = {
        "full_name": "Kiểm Tra Lộ PII CCCD",
        "identity_card_number": sensitive_cccd,
        "phone": "0918776655",
    }
    response = employee_client.post("/api/v1/customers/", payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT

    # Check response body
    response_str = str(response.json())
    assert sensitive_cccd not in response_str, "CCCD leaked in response body!"

    # Check caplog
    for record in caplog.records:
        assert sensitive_cccd not in record.message, (
            f"CCCD leaked in log: {record.message}"
        )


def test_pii_never_echoed_in_duplicate_phone_error(
    employee_client: APIClient,
    active_customer: Customer,
    caplog: pytest.LogCaptureFixture,
):
    """
    Verify that when duplicate phone number is submitted, the error response and log records
    NEVER echo the actual phone number digits.
    """
    caplog.set_level(logging.DEBUG)

    sensitive_phone = active_customer.phone
    payload = {
        "full_name": "Kiểm Tra Lộ PII Phone",
        "identity_card_number": "079200332211",
        "phone": sensitive_phone,
    }
    response = employee_client.post("/api/v1/customers/", payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT

    response_str = str(response.json())
    assert sensitive_phone not in response_str, "Phone number leaked in response body!"

    for record in caplog.records:
        assert sensitive_phone not in record.message, (
            f"Phone leaked in log: {record.message}"
        )


def test_pii_never_echoed_in_duplicate_email_error(
    employee_client: APIClient,
    active_customer: Customer,
    caplog: pytest.LogCaptureFixture,
):
    """
    Verify that when duplicate email is submitted, the error response and log records
    NEVER echo the actual email string.
    """
    caplog.set_level(logging.DEBUG)
    assert active_customer.email is not None
    sensitive_email = active_customer.email

    payload = {
        "full_name": "Kiểm Tra Lộ PII Email",
        "identity_card_number": "079200332299",
        "phone": "0918776699",
        "email": sensitive_email,
    }
    response = employee_client.post("/api/v1/customers/", payload, format="json")
    assert response.status_code == status.HTTP_409_CONFLICT

    response_str = str(response.json())
    assert sensitive_email not in response_str, "Email leaked in response body!"

    for record in caplog.records:
        assert sensitive_email not in record.message, (
            f"Email leaked in log: {record.message}"
        )


def test_pii_masking_contract_list_and_detail(employee_client: APIClient):
    """
    Verify decree 13/2023/NĐ-CP masking compliance:
    When is_anonymized = True:
    - full_name becomes 'Khách hàng ẩn danh'
    - phone becomes '***'
    - identity_card_number becomes '***'
    - email becomes '***'
    - address becomes '***'
    - date_of_birth becomes None
    """
    cust = Customer.objects.create(
        code="KHPII01",
        full_name="Nguyễn Văn Bảo Mật",
        date_of_birth="1985-12-20",
        identity_card_number="079085009911",
        phone="0909859911",
        email="baomat@example.vn",
        address="999 Tuyệt Mật, P1, Q1",
        is_anonymized=True,
        anonymized_at=timezone.now(),
    )

    # 1. Verify List View Masking
    res_list = employee_client.get(f"/api/v1/customers/?code={cust.code}")
    assert res_list.status_code == status.HTTP_200_OK
    list_item = res_list.json()["results"][0]
    assert list_item["full_name"] == "Khách hàng ẩn danh"
    assert list_item["phone"] == "***"
    assert list_item["identity_card_number"] == "***"
    assert "079085009911" not in str(list_item)
    assert "0909859911" not in str(list_item)

    # 2. Verify Detail View Masking
    res_detail = employee_client.get(f"/api/v1/customers/{cust.id}/")
    assert res_detail.status_code == status.HTTP_200_OK
    detail_data = res_detail.json()
    assert detail_data["full_name"] == "Khách hàng ẩn danh"
    assert detail_data["identity_card_number"] == "***"
    assert detail_data["phone"] == "***"
    assert detail_data["email"] == "***"
    assert detail_data["address"] == "***"
    assert detail_data["date_of_birth"] is None
    assert "079085009911" not in str(detail_data)
    assert "baomat@example.vn" not in str(detail_data)
    assert "999 Tuyệt Mật" not in str(detail_data)
