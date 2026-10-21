"""
Tests for Defect F4: Sessions Filter Validation & JSON 404 Handler.
Verifies:
1. GET /api/v1/parking/sessions/?entry_time_from=abc -> 400 PROP-GEN-P01 (not 500).
2. GET /api/v1/parking/sessions/?page_size=100000 / 0 / -5 -> 400 PROP-GEN-P01.
3. GET /api/v1/parking/sessions/?status=weird -> 400 PROP-GEN-P01.
4. GET /api/v1/parking/sessions/?review_status=weird -> 400 PROP-GEN-P01.
5. GET /api/v1/parking/sessions/?min_fee=100000&max_fee=50000 -> 400 PROP-GEN-P01.
6. GET /api/v1/parking/sessions/?entry_time_from > entry_time_to -> 400 PROP-GEN-P01.
7. GET /api/v1/parking/sessions/?exit_time_from > exit_time_to -> 400 PROP-GEN-P01.
8. GET /api/v1/parking/sessions/?valid_params -> 200 OK.
9. GET /api/v1/parking/sessions/abc/ -> 404 JSON envelope MSG-4.4.1-M01 (not HTML).
"""

import json

import pytest
from django.test import Client
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.parking.models import VehicleEntryExitLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_f4_test@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


# -----------------------------------------------------------------------------
# 1. Invalid Datetimes Validation (entry_time_from=abc -> 400 PROP-GEN-P01)
# -----------------------------------------------------------------------------
def test_sessions_filter_invalid_datetime_returns_400(auth_employee):
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # entry_time_from invalid
    resp = client.get("/api/v1/parking/sessions/?entry_time_from=abc")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "PROP-GEN-P01"
    assert "entry_time_from" in resp.data["details"]

    # entry_time_to invalid
    resp_to = client.get("/api/v1/parking/sessions/?entry_time_to=invalid_date")
    assert resp_to.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_to.data["code"] == "PROP-GEN-P01"
    assert "entry_time_to" in resp_to.data["details"]

    # exit_time_from invalid
    resp_exit = client.get("/api/v1/parking/sessions/?exit_time_from=not_a_time")
    assert resp_exit.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_exit.data["code"] == "PROP-GEN-P01"
    assert "exit_time_from" in resp_exit.data["details"]


# -----------------------------------------------------------------------------
# 2. page_size Bounds (1..100)
# -----------------------------------------------------------------------------
def test_sessions_filter_page_size_bounds_returns_400(auth_employee):
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # page_size > 100
    resp_100k = client.get("/api/v1/parking/sessions/?page_size=100000")
    assert resp_100k.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_100k.data["code"] == "PROP-GEN-P01"
    assert "page_size" in resp_100k.data["details"]

    # page_size = 0
    resp_0 = client.get("/api/v1/parking/sessions/?page_size=0")
    assert resp_0.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_0.data["code"] == "PROP-GEN-P01"
    assert "page_size" in resp_0.data["details"]

    # page_size < 0
    resp_neg = client.get("/api/v1/parking/sessions/?page_size=-5")
    assert resp_neg.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_neg.data["code"] == "PROP-GEN-P01"
    assert "page_size" in resp_neg.data["details"]


# -----------------------------------------------------------------------------
# 3. status Choice Validation
# -----------------------------------------------------------------------------
def test_sessions_filter_invalid_status_returns_400(auth_employee):
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.get("/api/v1/parking/sessions/?status=weird")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "PROP-GEN-P01"
    assert "status" in resp.data["details"]


# -----------------------------------------------------------------------------
# 4. review_status Choice Validation
# -----------------------------------------------------------------------------
def test_sessions_filter_invalid_review_status_returns_400(auth_employee):
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.get("/api/v1/parking/sessions/?review_status=weird")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "PROP-GEN-P01"
    assert "review_status" in resp.data["details"]


def test_vehicle_entry_exit_log_review_status_choices():
    assert hasattr(VehicleEntryExitLog, "ReviewStatus")
    assert VehicleEntryExitLog.ReviewStatus.AUTO == "AUTO"
    assert VehicleEntryExitLog.ReviewStatus.MATCHED == "MATCHED"
    assert VehicleEntryExitLog.ReviewStatus.NEEDS_REVIEW == "NEEDS_REVIEW"
    assert VehicleEntryExitLog.ReviewStatus.APPROVED == "APPROVED"
    assert VehicleEntryExitLog.ReviewStatus.REJECTED == "REJECTED"


# -----------------------------------------------------------------------------
# 5. min_fee <= max_fee Cross-Field Validation
# -----------------------------------------------------------------------------
def test_sessions_filter_fee_range_ordering_returns_400(auth_employee):
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.get("/api/v1/parking/sessions/?min_fee=100000&max_fee=50000")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "PROP-GEN-P01"
    assert "min_fee" in resp.data["details"]


# -----------------------------------------------------------------------------
# 6. Time Range Ordering Cross-Field Validation
# -----------------------------------------------------------------------------
def test_sessions_filter_time_range_ordering_returns_400(auth_employee):
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # entry_time_from > entry_time_to
    resp_entry = client.get(
        "/api/v1/parking/sessions/?entry_time_from=2026-10-20T00:00:00Z&entry_time_to=2026-10-10T00:00:00Z"
    )
    assert resp_entry.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_entry.data["code"] == "PROP-GEN-P01"
    assert "entry_time_from" in resp_entry.data["details"]

    # exit_time_from > exit_time_to
    resp_exit = client.get(
        "/api/v1/parking/sessions/?exit_time_from=2026-10-20T00:00:00Z&exit_time_to=2026-10-10T00:00:00Z"
    )
    assert resp_exit.status_code == status.HTTP_400_BAD_REQUEST
    assert resp_exit.data["code"] == "PROP-GEN-P01"
    assert "exit_time_from" in resp_exit.data["details"]


# -----------------------------------------------------------------------------
# 7. Valid Parameters Return 200 OK
# -----------------------------------------------------------------------------
def test_sessions_filter_valid_parameters_returns_200(auth_employee):
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.get(
        "/api/v1/parking/sessions/?page=1&page_size=50&status=open&review_status=AUTO&min_fee=0&max_fee=50000"
    )
    assert resp.status_code == status.HTTP_200_OK
    assert "results" in resp.data
    assert "count" in resp.data


# -----------------------------------------------------------------------------
# 8. GET /api/v1/parking/sessions/abc/ -> JSON 404 MSG-4.4.1-M01
# -----------------------------------------------------------------------------
def test_unmatched_url_returns_json_404_envelope(auth_employee):
    client = Client()
    client.force_login(auth_employee)

    resp = client.get("/api/v1/parking/sessions/abc/")
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.headers.get("Content-Type") == "application/json"

    data = json.loads(resp.content.decode("utf-8"))
    assert data["code"] == "MSG-4.4.1-M01"
    assert data["message"] == "Không tìm thấy dữ liệu"
    assert data["details"] == {}
