"""
Core API functional tests for Employee Management API (apps.employees) per SRS 4.3.1–4.3.4 and Round 67 specifications.
Tests all 7 endpoints against real PostgreSQL 18.6:
- GET /api/v1/positions/
- GET /api/v1/employees/summary/
- GET /api/v1/employees/
- POST /api/v1/employees/
- GET /api/v1/employees/{id}/
- PATCH /api/v1/employees/{id}/
- DELETE /api/v1/employees/{id}/
Verifies RBAC matrix, SOT KPI metrics, query bounds (zero N+1), OCC row_version,
DEL-01 guards, atomic Account+Employee lifecycle, raw-string validation, and session revocation.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.models import Session
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account, PersistentLoginToken
from apps.core.models import (
    AdministrativeDistrict,
    AdministrativeProvince,
    AdministrativeWard,
)
from apps.employees.models import Employee, Position
from config.settings import base as base_settings

pytestmark = pytest.mark.django_db


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def manager_account() -> Account:
    """Primary active MANAGER account."""
    acc, _ = Account.objects.get_or_create(
        email="test_manager_primary@parking.local",
        defaults={
            "phone": "0901000001",
            "role": "MANAGER",
            "is_active": True,
            "password": make_password("Manager123!@#"),
        },
    )
    acc.is_active = True
    acc.role = "MANAGER"
    acc.save()
    return acc


@pytest.fixture
def secondary_manager_account() -> Account:
    """Secondary active MANAGER account (ensures system has > 1 manager when testing)."""
    acc, _ = Account.objects.get_or_create(
        email="test_manager_secondary@parking.local",
        defaults={
            "phone": "0901000002",
            "role": "MANAGER",
            "is_active": True,
            "password": make_password("Manager123!@#"),
        },
    )
    acc.is_active = True
    acc.role = "MANAGER"
    acc.save()
    return acc


@pytest.fixture
def employee_account() -> Account:
    """Active EMPLOYEE account."""
    acc, _ = Account.objects.get_or_create(
        email="test_employee_standard@parking.local",
        defaults={
            "phone": "0901000003",
            "role": "EMPLOYEE",
            "is_active": True,
            "password": make_password("Employee123!@#"),
        },
    )
    acc.is_active = True
    acc.role = "EMPLOYEE"
    acc.save()
    return acc


@pytest.fixture
def customer_account() -> Account:
    """Active CUSTOMER account."""
    acc, _ = Account.objects.get_or_create(
        email="test_customer_standard@parking.local",
        defaults={
            "phone": "0901000004",
            "role": "CUSTOMER",
            "is_active": True,
            "password": make_password("Customer123!@#"),
        },
    )
    acc.is_active = True
    acc.role = "CUSTOMER"
    acc.save()
    return acc


@pytest.fixture
def manager_client(manager_account: Account) -> APIClient:
    """APIClient authenticated as primary MANAGER."""
    client = APIClient()
    client.force_authenticate(user=manager_account)
    return client


@pytest.fixture
def employee_client(employee_account: Account) -> APIClient:
    """APIClient authenticated as EMPLOYEE."""
    client = APIClient()
    client.force_authenticate(user=employee_account)
    return client


@pytest.fixture
def customer_client(customer_account: Account) -> APIClient:
    """APIClient authenticated as CUSTOMER."""
    client = APIClient()
    client.force_authenticate(user=customer_account)
    return client


@pytest.fixture
def anonymous_client() -> APIClient:
    """Unauthenticated APIClient."""
    return APIClient()


@pytest.fixture
def admin_hierarchy() -> dict[str, Any]:
    """Returns valid 3-tier administrative hierarchy from seed data."""
    province = AdministrativeProvince.objects.order_by("id").first()
    assert province is not None, "Missing administrative province seed data"
    district = (
        AdministrativeDistrict.objects.filter(province=province).order_by("id").first()
    )
    assert district is not None, "Missing administrative district seed data"
    ward = AdministrativeWard.objects.filter(district=district).order_by("id").first()
    assert ward is not None, "Missing administrative ward seed data"
    return {
        "province_id": province.id,
        "district_id": district.id,
        "ward_id": ward.id,
    }


# ==============================================================================
# 1. RBAC MATRIX TESTS
# ==============================================================================


class TestEmployeeRBACMatrix:
    """Verify that all employee and position endpoints are strictly MANAGER-only."""

    def test_positions_rbac(
        self,
        anonymous_client: APIClient,
        customer_client: APIClient,
        employee_client: APIClient,
        manager_client: APIClient,
    ) -> None:
        url = "/api/v1/positions/"
        assert anonymous_client.get(url).status_code == status.HTTP_401_UNAUTHORIZED
        assert customer_client.get(url).status_code == status.HTTP_403_FORBIDDEN
        assert employee_client.get(url).status_code == status.HTTP_403_FORBIDDEN
        assert manager_client.get(url).status_code == status.HTTP_200_OK

    def test_summary_rbac(
        self,
        anonymous_client: APIClient,
        customer_client: APIClient,
        employee_client: APIClient,
        manager_client: APIClient,
    ) -> None:
        url = "/api/v1/employees/summary/"
        assert anonymous_client.get(url).status_code == status.HTTP_401_UNAUTHORIZED
        assert customer_client.get(url).status_code == status.HTTP_403_FORBIDDEN
        assert employee_client.get(url).status_code == status.HTTP_403_FORBIDDEN
        assert manager_client.get(url).status_code == status.HTTP_200_OK

    def test_list_rbac(
        self,
        anonymous_client: APIClient,
        customer_client: APIClient,
        employee_client: APIClient,
        manager_client: APIClient,
    ) -> None:
        url = "/api/v1/employees/"
        assert anonymous_client.get(url).status_code == status.HTTP_401_UNAUTHORIZED
        assert customer_client.get(url).status_code == status.HTTP_403_FORBIDDEN
        assert employee_client.get(url).status_code == status.HTTP_403_FORBIDDEN
        assert manager_client.get(url).status_code == status.HTTP_200_OK

    def test_detail_rbac(
        self,
        anonymous_client: APIClient,
        customer_client: APIClient,
        employee_client: APIClient,
        manager_client: APIClient,
    ) -> None:
        target = Employee.objects.filter(deleted_at__isnull=True).first()
        assert target is not None
        url = f"/api/v1/employees/{target.id}/"
        assert anonymous_client.get(url).status_code == status.HTTP_401_UNAUTHORIZED
        assert customer_client.get(url).status_code == status.HTTP_403_FORBIDDEN
        assert employee_client.get(url).status_code == status.HTTP_403_FORBIDDEN
        assert manager_client.get(url).status_code == status.HTTP_200_OK

    def test_create_rbac(
        self,
        anonymous_client: APIClient,
        customer_client: APIClient,
        employee_client: APIClient,
        manager_client: APIClient,
    ) -> None:
        url = "/api/v1/employees/"
        payload = {"full_name": "Test RBAC"}
        assert (
            anonymous_client.post(url, payload).status_code
            == status.HTTP_401_UNAUTHORIZED
        )
        assert (
            customer_client.post(url, payload).status_code == status.HTTP_403_FORBIDDEN
        )
        assert (
            employee_client.post(url, payload).status_code == status.HTTP_403_FORBIDDEN
        )
        # Manager succeeds on valid payload
        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None
        valid_payload = {
            "full_name": "RBAC Manager Create",
            "email": "rbac_mgr_ok@parking.local",
            "phone": "0911000999",
            "position_id": pos.id,
            "password": "StrongPassword123!@#",
        }
        res_mgr = manager_client.post(url, valid_payload, format="json")
        assert res_mgr.status_code == status.HTTP_201_CREATED

    def test_update_rbac(
        self,
        anonymous_client: APIClient,
        customer_client: APIClient,
        employee_client: APIClient,
        manager_client: APIClient,
    ) -> None:
        target = (
            Employee.objects.filter(status="ACTIVE", deleted_at__isnull=True)
            .exclude(code="NV001")
            .first()
        )
        assert target is not None
        url = f"/api/v1/employees/{target.id}/"
        payload = {"row_version": target.row_version, "full_name": "New Name"}
        assert (
            anonymous_client.patch(url, payload).status_code
            == status.HTTP_401_UNAUTHORIZED
        )
        assert (
            customer_client.patch(url, payload).status_code == status.HTTP_403_FORBIDDEN
        )
        assert (
            employee_client.patch(url, payload).status_code == status.HTTP_403_FORBIDDEN
        )
        # Manager succeeds
        res_mgr = manager_client.patch(url, payload, format="json")
        assert res_mgr.status_code == status.HTTP_200_OK

    def test_delete_rbac(
        self,
        anonymous_client: APIClient,
        customer_client: APIClient,
        employee_client: APIClient,
        manager_client: APIClient,
    ) -> None:
        target = Employee.objects.filter(deleted_at__isnull=True).first()
        assert target is not None
        url = f"/api/v1/employees/{target.id}/"
        assert anonymous_client.delete(url).status_code == status.HTTP_401_UNAUTHORIZED
        assert customer_client.delete(url).status_code == status.HTTP_403_FORBIDDEN
        assert employee_client.delete(url).status_code == status.HTTP_403_FORBIDDEN
        # Manager succeeds on disposable employee
        pos = Position.objects.filter(code="NVTN", deleted_at__isnull=True).first()
        assert pos is not None
        del_acc = Account.objects.create(
            email="rbac_del_ok@parking.local",
            phone="0955112233",
            role="EMPLOYEE",
            is_active=True,
            password=make_password("Pass123!@#"),
        )
        del_emp = Employee.objects.create(
            code="NV789",
            full_name="RBAC Delete Target",
            email=str(del_acc.email),
            phone=str(del_acc.phone),
            position=pos,
            account=del_acc,
            status="ACTIVE",
        )
        res_mgr = manager_client.delete(f"/api/v1/employees/{del_emp.id}/")
        assert res_mgr.status_code == status.HTTP_200_OK


# ==============================================================================
# 2. POSITIONS LIST ENDPOINT
# ==============================================================================


class TestPositionsEndpoint:
    """Verify GET /api/v1/positions/."""

    def test_list_positions_deterministic_order(
        self, manager_client: APIClient
    ) -> None:
        response = manager_client.get("/api/v1/positions/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 4

        # Verify deterministic ascending order by ID
        ids = [item["id"] for item in data]
        assert ids == sorted(ids)

        # Verify structure
        for item in data:
            assert "id" in item
            assert "code" in item
            assert "name" in item

        codes = {item["code"] for item in data}
        assert {"QL", "NVVH", "NVTN", "KTV"}.issubset(codes)

    def test_list_positions_excludes_soft_deleted(
        self, manager_client: APIClient
    ) -> None:
        # Create a temporary position and soft-delete it
        pos = Position.objects.create(
            code="TEMP_DEL",
            name="Chức vụ tạm",
            deleted_at=timezone.now(),
        )
        response = manager_client.get("/api/v1/positions/")
        assert response.status_code == status.HTTP_200_OK
        codes = [item["code"] for item in response.json()]
        assert pos.code not in codes


# ==============================================================================
# 3. EMPLOYEE SUMMARY (KPI SOT) ENDPOINT
# ==============================================================================


class TestEmployeeSummaryEndpoint:
    """Verify GET /api/v1/employees/summary/ and SOT KPI."""

    def test_summary_matches_seed_sot(self, manager_client: APIClient) -> None:
        response = manager_client.get("/api/v1/employees/summary/")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Calculate ground truth directly with independent raw SQL
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    COUNT(id) AS total_employees,
                    COUNT(id) FILTER (WHERE status = 'ACTIVE') AS active_employees,
                    COUNT(id) FILTER (WHERE status = 'INACTIVE') AS inactive_employees,
                    (SELECT COUNT(*) FROM position WHERE deleted_at IS NULL) AS total_positions
                FROM employee
                WHERE deleted_at IS NULL;
                """
            )
            row = cursor.fetchone()
            assert row is not None
            raw_total, raw_active, raw_inactive, raw_positions = row

        assert data["total_employees"] == raw_total
        assert data["active_employees"] == raw_active
        assert data["inactive_employees"] == raw_inactive
        assert data["total_positions"] == raw_positions

        # Verify exact seed numbers (8 total: 7 active, 1 inactive; 4 positions)
        assert data["total_employees"] == 8
        assert data["active_employees"] == 7
        assert data["inactive_employees"] == 1
        assert data["total_positions"] == 4

    def test_summary_query_count_bound(self, manager_client: APIClient) -> None:
        """Verify summary executes in exactly 1 query via aggregate + Subquery."""
        with CaptureQueriesContext(connection) as ctx:
            response = manager_client.get("/api/v1/employees/summary/")
        assert response.status_code == status.HTTP_200_OK
        assert len(ctx) <= 1, f"Expected <= 1 query, got {len(ctx)}"


# ==============================================================================
# 4. EMPLOYEE LIST & FILTERS ENDPOINT
# ==============================================================================


class TestEmployeeListAndFilters:
    """Verify GET /api/v1/employees/ with filters, substring search, ordering, pagination."""

    def test_list_query_bounds_zero_n_plus_one(self, manager_client: APIClient) -> None:
        """Verify 2 queries: 1 count + 1 select with select_related for all 5 relations."""
        with CaptureQueriesContext(connection) as ctx:
            response = manager_client.get("/api/v1/employees/?page=1&page_size=10")
        assert response.status_code == status.HTTP_200_OK
        assert len(ctx) <= 2, f"Expected <= 2 queries, got {len(ctx)}"

    def test_list_pagination_structure(self, manager_client: APIClient) -> None:
        response = manager_client.get("/api/v1/employees/?page=1&page_size=5")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "count" in data
        assert "total_pages" in data
        assert "current_page" in data
        assert "page_size" in data
        assert "results" in data
        assert data["count"] == 8
        assert data["total_pages"] == 2
        assert len(data["results"]) == 5

        # Check item fields and absence of sensitive fields
        item = data["results"][0]
        assert "id" in item
        assert "code" in item
        assert "full_name" in item
        assert "position" in item
        assert "phone" in item
        assert "email" in item
        assert "area" in item
        assert "status" in item
        assert "status_display" in item
        assert "row_version" in item

        # Zero password/hash fields!
        assert "password" not in item
        assert "password_hash" not in item

    def test_list_q_substring_search(self, manager_client: APIClient) -> None:
        # Search by partial name
        res = manager_client.get("/api/v1/employees/?q=Khang")
        assert res.status_code == status.HTTP_200_OK
        assert res.json()["count"] >= 1
        assert any("Khang" in emp["full_name"] for emp in res.json()["results"])

        # Search by partial code
        res_code = manager_client.get("/api/v1/employees/?q=NV00")
        assert res_code.status_code == status.HTTP_200_OK
        assert res_code.json()["count"] == 8

        # Search with wildcard escaping (should not match all)
        res_wildcard = manager_client.get("/api/v1/employees/?q=%")
        assert res_wildcard.status_code == status.HTTP_200_OK
        assert res_wildcard.json()["count"] == 0

    def test_list_explicit_field_filters(self, manager_client: APIClient) -> None:
        # Filter by position code
        res_pos = manager_client.get("/api/v1/employees/?position=QL")
        assert res_pos.status_code == status.HTTP_200_OK
        for emp in res_pos.json()["results"]:
            assert emp["position"]["code"] == "QL"

        # Filter by status
        res_status = manager_client.get("/api/v1/employees/?status=INACTIVE")
        assert res_status.status_code == status.HTTP_200_OK
        assert res_status.json()["count"] == 1
        assert res_status.json()["results"][0]["status"] == "INACTIVE"

        # Invalid status returns 400
        res_invalid_st = manager_client.get("/api/v1/employees/?status=UNKNOWN")
        assert res_invalid_st.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_birth_range_filters(self, manager_client: APIClient) -> None:
        res = manager_client.get(
            "/api/v1/employees/?birth_from=1980-01-01&birth_to=2005-12-31"
        )
        assert res.status_code == status.HTTP_200_OK

        # birth_from > birth_to returns 400
        res_err = manager_client.get(
            "/api/v1/employees/?birth_from=2000-01-01&birth_to=1990-01-01"
        )
        assert res_err.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_ordering_whitelist(self, manager_client: APIClient) -> None:
        res_asc = manager_client.get("/api/v1/employees/?ordering=code")
        assert res_asc.status_code == status.HTTP_200_OK
        codes = [item["code"] for item in res_asc.json()["results"]]
        assert codes == sorted(codes)

        # Disallowed ordering returns 400
        res_disallowed = manager_client.get("/api/v1/employees/?ordering=secret_field")
        assert res_disallowed.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 5. EMPLOYEE DETAIL PROFILE ENDPOINT
# ==============================================================================


class TestEmployeeDetailEndpoint:
    """Verify GET /api/v1/employees/{id}/."""

    def test_detail_success_profile(self, manager_client: APIClient) -> None:
        emp = Employee.objects.filter(status="ACTIVE", deleted_at__isnull=True).first()
        assert emp is not None

        with CaptureQueriesContext(connection) as ctx:
            response = manager_client.get(f"/api/v1/employees/{emp.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert len(ctx) <= 1, f"Expected 1 query, got {len(ctx)}"

        data = response.json()
        assert data["id"] == emp.id
        assert data["code"] == emp.code
        assert data["full_name"] == emp.full_name
        assert data["email"] == emp.email
        assert data["phone"] == emp.phone
        assert "position" in data
        assert "account" in data
        assert data["account"]["role"] in ("MANAGER", "EMPLOYEE")
        assert emp.account is not None
        assert data["account"]["is_active"] == emp.account.is_active

        # Zero password/hash fields!
        assert "password" not in data
        assert "password_hash" not in data
        assert "password" not in data["account"]
        assert "password_hash" not in data["account"]

    def test_detail_unknown_404(self, manager_client: APIClient) -> None:
        response = manager_client.get("/api/v1/employees/999999/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "PROP-4.3.3-P02"

    def test_detail_soft_deleted_404(self, manager_client: APIClient) -> None:
        # Create an employee and soft delete
        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None
        emp = Employee.objects.create(
            code="NV999",
            full_name="Đã Xóa",
            email="daxoa@parking.local",
            phone="0999999999",
            position=pos,
            deleted_at=timezone.now(),
        )
        response = manager_client.get(f"/api/v1/employees/{emp.id}/")
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert response.json()["code"] == "PROP-4.3.3-P02"


# ==============================================================================
# 6. EMPLOYEE CREATE (POST) ENDPOINT
# ==============================================================================


class TestEmployeeCreateEndpoint:
    """Verify POST /api/v1/employees/ (SRS 4.3.2)."""

    def test_create_employee_success_atomic(
        self,
        manager_client: APIClient,
        admin_hierarchy: dict[str, Any],
    ) -> None:
        pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
        assert pos_ql is not None

        payload = {
            "full_name": "Nguyễn Văn Test Tạo Mới",
            "email": "test_create_atomic@parking.local",
            "phone": "0987654321",
            "position_id": pos_ql.id,
            "password": "StrongPassword123!@#",
            "date_of_birth": "1992-05-15",
            "gender": "Nam",
            "identity_card_number": "079092001234",
            "address": "123 Đường Test",
            "province_id": admin_hierarchy["province_id"],
            "district_id": admin_hierarchy["district_id"],
            "ward_id": admin_hierarchy["ward_id"],
            "status": "ACTIVE",
        }
        response = manager_client.post("/api/v1/employees/", payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()

        # Verify auto-generated code
        assert data["code"].startswith("NV")
        assert data["full_name"] == payload["full_name"]

        # Verify role derivation QL -> MANAGER
        assert data["account"]["role"] == "MANAGER"
        assert data["account"]["is_active"] is True

        # Verify DB records
        emp = Employee.objects.get(id=data["id"])
        assert emp.account is not None
        assert emp.account.role == "MANAGER"
        assert emp.account.is_active is True
        assert emp.account.email == "test_create_atomic@parking.local"

    def test_create_employee_role_derivation_employee(
        self,
        manager_client: APIClient,
    ) -> None:
        pos_nv = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos_nv is not None

        payload = {
            "full_name": "Trần Thị Thu Ngân",
            "email": "test_role_nv@parking.local",
            "phone": "0987654322",
            "position_id": pos_nv.id,
            "password": "StrongPassword123!@#",
            "status": "ACTIVE",
        }
        response = manager_client.post("/api/v1/employees/", payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["account"]["role"] == "EMPLOYEE"

    def test_create_employee_advisory_lock_executed(
        self,
        manager_client: APIClient,
    ) -> None:
        """Verify pg_advisory_xact_lock is executed during automatic code generation."""
        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None
        payload = {
            "full_name": "Test Lock Employee",
            "email": "test_lock@parking.local",
            "phone": "0988776655",
            "position_id": pos.id,
            "password": "Password123!@#",
        }
        with CaptureQueriesContext(connection) as ctx:
            res = manager_client.post("/api/v1/employees/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        lock_queries = [
            q for q in ctx.captured_queries if "pg_advisory_xact_lock" in q["sql"]
        ]
        assert len(lock_queries) == 1, (
            f"Expected 1 advisory lock query, got {len(lock_queries)}"
        )

    def test_create_employee_custom_valid_code(
        self,
        manager_client: APIClient,
    ) -> None:
        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None

        payload = {
            "code": "NV500",
            "full_name": "Custom Code Employee",
            "email": "test_custom_code@parking.local",
            "phone": "0987654323",
            "position_id": pos.id,
            "password": "StrongPassword123!@#",
        }
        response = manager_client.post("/api/v1/employees/", payload, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.json()["code"] == "NV500"

    def test_create_employee_invalid_code_format(
        self,
        manager_client: APIClient,
    ) -> None:
        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None

        payload = {
            "code": "INVALID_CODE",
            "full_name": "Invalid Code",
            "email": "test_inv_code@parking.local",
            "phone": "0987654324",
            "position_id": pos.id,
            "password": "StrongPassword123!@#",
        }
        response = manager_client.post("/api/v1/employees/", payload, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_employee_weak_password_rejected(
        self,
        manager_client: APIClient,
    ) -> None:
        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None

        base = {
            "full_name": "Weak Pwd Test",
            "email": "weak_pwd@parking.local",
            "phone": "0987654325",
            "position_id": pos.id,
        }

        # Too short
        res1 = manager_client.post(
            "/api/v1/employees/", {**base, "password": "Ab1!"}, format="json"
        )
        assert res1.status_code == status.HTTP_400_BAD_REQUEST

        # Missing uppercase
        res2 = manager_client.post(
            "/api/v1/employees/",
            {**base, "password": "lowercase123!@#"},
            format="json",
        )
        assert res2.status_code == status.HTTP_400_BAD_REQUEST

        # Missing digit
        res3 = manager_client.post(
            "/api/v1/employees/", {**base, "password": "NoDigits!@#$"}, format="json"
        )
        assert res3.status_code == status.HTTP_400_BAD_REQUEST

        # Missing special char
        res4 = manager_client.post(
            "/api/v1/employees/",
            {**base, "password": "NoSpecialChar123"},
            format="json",
        )
        assert res4.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_employee_unique_conflicts_409(
        self,
        manager_client: APIClient,
    ) -> None:
        existing = Employee.objects.filter(deleted_at__isnull=True).first()
        assert existing is not None
        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None

        # Duplicate email
        payload = {
            "full_name": "Trùng Email",
            "email": existing.email,
            "phone": "0911223344",
            "position_id": pos.id,
            "password": "StrongPassword123!@#",
        }
        response = manager_client.post("/api/v1/employees/", payload, format="json")
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "MSG-4.3.1-M05"

    def test_create_employee_raw_string_adversarial_rejected(
        self,
        manager_client: APIClient,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None

        # Name with emoji
        caplog.clear()
        payload_emoji = {
            "full_name": "Nguyễn Văn 😀 Test",
            "email": "emoji@parking.local",
            "phone": "0911223355",
            "position_id": pos.id,
            "password": "StrongPassword123!@#",
        }
        with caplog.at_level(logging.ERROR):
            res_emoji = manager_client.post(
                "/api/v1/employees/", payload_emoji, format="json"
            )
        assert res_emoji.status_code == status.HTTP_400_BAD_REQUEST
        assert "Database exception" not in caplog.text

        # Name with NUL byte
        caplog.clear()
        payload_nul = {
            "full_name": "Nguyễn Văn \x00 Test",
            "email": "nul@parking.local",
            "phone": "0911223356",
            "position_id": pos.id,
            "password": "StrongPassword123!@#",
        }
        with caplog.at_level(logging.ERROR):
            res_nul = manager_client.post(
                "/api/v1/employees/", payload_nul, format="json"
            )
        assert res_nul.status_code == status.HTTP_400_BAD_REQUEST
        assert "Database exception" not in caplog.text

    def test_create_employee_atomic_rollback(
        self,
        manager_client: APIClient,
    ) -> None:
        """
        Verify that when employee insert fails after account creation,
        the created Account is rolled back atomically (zero orphan account).
        """
        from unittest.mock import patch

        from django.db import DatabaseError

        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None

        orphan_email = "orphan_check@parking.local"
        payload = {
            "code": "NV555",
            "full_name": "Orphan Test",
            "email": orphan_email,
            "phone": "0911223399",
            "position_id": pos.id,
            "password": "StrongPassword123!@#",
        }

        def fail_employee_create(*args: Any, **kwargs: Any) -> None:
            # Genuine check: Assert Account actually exists in DB before rollback occurs!
            assert Account.objects.filter(email=orphan_email).exists()
            raise DatabaseError("Simulated DB failure during Employee creation")

        with patch.object(Employee.objects, "create", side_effect=fail_employee_create):
            res = manager_client.post("/api/v1/employees/", payload, format="json")
            assert res.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

        # Verify Account was rolled back cleanly by @transaction.atomic (no orphan)
        assert not Account.objects.filter(email=orphan_email).exists()
        assert not Employee.objects.filter(email=orphan_email).exists()

    def test_create_employee_client_role_cannot_override_position(
        self, manager_client: APIClient
    ) -> None:
        """Verify client cannot supply a 'role' parameter to override position-derived role (Privilege Escalation protection)."""
        pos_nv = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos_nv is not None

        payload = {
            "full_name": "Tamper Role Employee",
            "email": "tamper_role@parking.local",
            "phone": "0987654329",
            "position_id": pos_nv.id,
            "password": "StrongPassword123!@#",
            "role": "MANAGER",  # Attempt privilege escalation
        }
        res = manager_client.post("/api/v1/employees/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        assert res.json()["account"]["role"] == "EMPLOYEE"
        emp = Employee.objects.get(id=res.json()["id"])
        assert emp.account is not None
        assert emp.account.role == "EMPLOYEE"


# ==============================================================================
# 7. EMPLOYEE UPDATE (PATCH) ENDPOINT
# ==============================================================================


class TestEmployeeUpdateEndpoint:
    """Verify PATCH /api/v1/employees/{id}/ (SRS 4.3.3)."""

    def test_update_employee_success(self, manager_client: APIClient) -> None:
        emp = (
            Employee.objects.filter(status="ACTIVE", deleted_at__isnull=True)
            .exclude(code="NV001")
            .first()
        )
        assert emp is not None

        payload = {
            "row_version": emp.row_version,
            "full_name": "Họ Tên Đã Cập Nhật",
            "phone": "0988888888",
        }
        response = manager_client.patch(
            f"/api/v1/employees/{emp.id}/", payload, format="json"
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["full_name"] == "Họ Tên Đã Cập Nhật"
        assert data["phone"] == "0988888888"
        assert data["row_version"] == emp.row_version + 1

    def test_update_employee_stale_row_version_409(
        self, manager_client: APIClient
    ) -> None:
        emp = Employee.objects.filter(deleted_at__isnull=True).first()
        assert emp is not None

        payload = {
            "row_version": emp.row_version + 99,  # Stale row version
            "full_name": "Stale Attempt",
        }
        response = manager_client.patch(
            f"/api/v1/employees/{emp.id}/", payload, format="json"
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "MSG-4.3.1-M03"

    def test_update_employee_missing_row_version_400(
        self, manager_client: APIClient
    ) -> None:
        emp = Employee.objects.filter(deleted_at__isnull=True).first()
        assert emp is not None

        payload = {"full_name": "Missing row_version"}
        response = manager_client.patch(
            f"/api/v1/employees/{emp.id}/", payload, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_employee_immutable_code(self, manager_client: APIClient) -> None:
        emp = Employee.objects.filter(deleted_at__isnull=True).first()
        assert emp is not None

        payload = {
            "row_version": emp.row_version,
            "code": "NV999",  # Immutable code cannot be changed
        }
        response = manager_client.patch(
            f"/api/v1/employees/{emp.id}/", payload, format="json"
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_employee_del01_self_deactivation_guard(
        self,
        manager_account: Account,
        manager_client: APIClient,
    ) -> None:
        """Manager cannot deactivate their own profile."""
        # Create an employee attached to the logged in manager
        pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
        assert pos_ql is not None
        self_emp = Employee.objects.create(
            code="NV777",
            full_name="Self Manager",
            email="self_manager@parking.local",
            phone="0977777777",
            position=pos_ql,
            account=manager_account,
            status="ACTIVE",
        )
        payload = {
            "row_version": self_emp.row_version,
            "status": "INACTIVE",
        }
        response = manager_client.patch(
            f"/api/v1/employees/{self_emp.id}/", payload, format="json"
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "PROP-DEL-01-SELF-DEACT"
        assert "tự vô hiệu hóa tài khoản" in response.json()["message"]

    def test_update_employee_del01_self_demotion_guard(
        self,
        manager_client: APIClient,
        manager_account: Account,
    ) -> None:
        """Logged-in manager cannot demote themselves to non-manager (409 PROP-DEL-01-SELF-DEMOTE)."""
        pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
        pos_nvvh = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos_ql is not None and pos_nvvh is not None

        self_emp, _ = Employee.objects.get_or_create(
            account=manager_account,
            defaults={
                "code": "NV789",
                "full_name": "Self Demote Manager",
                "email": "self_demote@parking.local",
                "phone": "0977777778",
                "position": pos_ql,
                "status": "ACTIVE",
            },
        )
        payload = {
            "row_version": self_emp.row_version,
            "position_id": pos_nvvh.id,
        }
        response = manager_client.patch(
            f"/api/v1/employees/{self_emp.id}/", payload, format="json"
        )
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] == "PROP-DEL-01-SELF-DEMOTE"
        assert "tự giáng chức" in response.json()["message"]

    def test_update_employee_del01_last_manager_guard(
        self,
        manager_client: APIClient,
    ) -> None:
        """Cannot deactivate the only active manager in the system via HTTP PATCH."""
        pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
        assert pos_ql is not None

        # Create sole active manager target
        sole_mgr = Account.objects.create(
            email="sole_mgr_patch@parking.local",
            phone="0977888801",
            role="MANAGER",
            is_active=True,
            password=make_password("Manager123!@#"),
        )
        emp_mgr = Employee.objects.create(
            code="NV778",
            full_name="Sole Manager Emp",
            email=str(sole_mgr.email),
            phone=str(sole_mgr.phone),
            position=pos_ql,
            account=sole_mgr,
            status="ACTIVE",
        )

        # Deactivate all other managers in DB
        other_mgr_ids = list(
            Account.objects.filter(
                role="MANAGER", is_active=True, deleted_at__isnull=True
            )
            .exclude(id=sole_mgr.id)
            .values_list("id", flat=True)
        )
        Account.objects.filter(id__in=other_mgr_ids).update(is_active=False)

        # Create calling manager actor and authenticate in-memory
        caller_mgr = Account.objects.create(
            email="caller_mgr_patch@parking.local",
            phone="0977888802",
            role="MANAGER",
            is_active=True,
            password=make_password("Manager123!@#"),
        )
        client = APIClient()
        client.force_authenticate(user=caller_mgr)

        # In DB, demote caller_mgr so sole_mgr is the sole active manager in DB
        Account.objects.filter(id=caller_mgr.id).update(role="EMPLOYEE")

        try:
            payload = {
                "row_version": emp_mgr.row_version,
                "status": "INACTIVE",
            }
            res = client.patch(
                f"/api/v1/employees/{emp_mgr.id}/", payload, format="json"
            )
            assert res.status_code == status.HTTP_409_CONFLICT
            assert res.json()["code"] == "PROP-DEL-01-LAST-MGR-EMP"
        finally:
            Account.objects.filter(id__in=other_mgr_ids).update(is_active=True)

    def test_update_employee_status_toggle_syncs_account_is_active(
        self, manager_client: APIClient
    ) -> None:
        """Verify updating employee status to INACTIVE immediately updates Account.is_active to False."""
        emp = (
            Employee.objects.filter(status="ACTIVE", deleted_at__isnull=True)
            .exclude(code="NV001")
            .first()
        )
        assert emp is not None and emp.account is not None
        assert emp.account.is_active is True

        payload = {"row_version": emp.row_version, "status": "INACTIVE"}
        res = manager_client.patch(
            f"/api/v1/employees/{emp.id}/", payload, format="json"
        )
        assert res.status_code == status.HTTP_200_OK
        assert res.json()["account"]["is_active"] is False

        emp.account.refresh_from_db()
        assert emp.account.is_active is False


# ==============================================================================
# 8. EMPLOYEE DELETE (DELETE) & SESSION REVOCATION ENDPOINT
# ==============================================================================


class TestEmployeeDeleteAndRevocation:
    """Verify DELETE /api/v1/employees/{id}/ and immediate session revocation."""

    def test_soft_delete_employee_success(
        self,
        manager_client: APIClient,
        secondary_manager_account: Account,
    ) -> None:
        pos = Position.objects.filter(code="NVTN", deleted_at__isnull=True).first()
        assert pos is not None
        acc = Account.objects.create(
            email="to_delete@parking.local",
            phone="0955555555",
            role="EMPLOYEE",
            is_active=True,
            password=make_password("Pass123!@#"),
        )
        emp = Employee.objects.create(
            code="NV779",
            full_name="Nhân viên để xóa",
            email=str(acc.email),
            phone=str(acc.phone),
            position=pos,
            account=acc,
            status="ACTIVE",
        )

        response = manager_client.delete(f"/api/v1/employees/{emp.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["code"] == "MSG-4.3.4-M01"
        assert response.json()["message"] == "Xóa thành công"

        # Verify DB soft deletion
        emp.refresh_from_db()
        assert emp.deleted_at is not None
        acc.refresh_from_db()
        assert acc.deleted_at is not None
        assert acc.is_active is False

        # Verify disappearance from detail
        res_detail = manager_client.get(f"/api/v1/employees/{emp.id}/")
        assert res_detail.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_employee_del01_self_delete_guard(
        self,
        manager_account: Account,
        manager_client: APIClient,
    ) -> None:
        """Manager cannot delete their own employee profile."""
        pos = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
        assert pos is not None
        self_emp, _ = Employee.objects.get_or_create(
            account=manager_account,
            defaults={
                "code": "NV780",
                "full_name": "Self Delete Test",
                "email": manager_account.email or "self_del@parking.local",
                "phone": manager_account.phone or "0977889900",
                "position": pos,
                "status": "ACTIVE",
            },
        )
        response = manager_client.delete(f"/api/v1/employees/{self_emp.id}/")
        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.json()["code"] in ("PROP-DEL-01-SELF-EMP", "PROP-DEL-01-SELF")

    def test_deactivated_employee_session_revoked(
        self,
        manager_client: APIClient,
    ) -> None:
        """
        Verify live session & remember-token revocation:
        An employee logs in, gets deactivated, and next request is immediately 401.
        """
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None

        emp_pwd = "StrongEmpPassword123!@#"
        acc = Account.objects.create(
            email="session_revoke_target@parking.local",
            phone="0966666666",
            role="EMPLOYEE",
            is_active=True,
            password=make_password(emp_pwd),
        )
        emp = Employee.objects.create(
            code="NV781",
            full_name="Target For Revoke",
            email=str(acc.email),
            phone=str(acc.phone),
            position=pos,
            account=acc,
            status="ACTIVE",
        )

        # Create active Django session for this employee
        existing_sess = Session.objects.filter(expire_date__gte=timezone.now()).first()
        init_data = existing_sess.session_data if existing_sess is not None else ""
        emp_session = Session.objects.create(
            session_key="test_session_key_emp_123",
            session_data=init_data,
            expire_date=timezone.now() + timedelta(days=1),
        )
        # Store auth user id in decoded dict format
        session_store_class = emp_session.get_session_store_class()
        assert session_store_class is not None
        session_store = session_store_class(session_key="test_session_key_emp_123")
        session_store["_auth_user_id"] = str(acc.id)
        session_store.save()

        # Create remember-me token for this account
        PersistentLoginToken.objects.create(
            account=acc,
            series="test_series_12345",
            token_hash="dummy_token_hash",
            expires_at=timezone.now() + timedelta(days=30),
        )
        assert PersistentLoginToken.objects.filter(account=acc).exists()

        # Manager deactivates employee
        payload = {
            "row_version": emp.row_version,
            "status": "INACTIVE",
        }
        res_deact = manager_client.patch(
            f"/api/v1/employees/{emp.id}/", payload, format="json"
        )
        assert res_deact.status_code == status.HTTP_200_OK

        # Verify session and remember token are physically deleted from DB!
        assert not Session.objects.filter(
            session_key="test_session_key_emp_123"
        ).exists()
        assert not PersistentLoginToken.objects.filter(account=acc).exists()

        # Verify client with this deactivated user is rejected with 401/403
        emp_api_client = APIClient()
        emp_api_client.cookies["sessionid"] = "test_session_key_emp_123"
        res_next = emp_api_client.get("/api/v1/auth/me/")
        assert res_next.status_code == status.HTTP_401_UNAUTHORIZED


def test_position_code_renamed_in_db_derives_correct_role(
    manager_client: APIClient,
) -> None:
    """
    M1 Red-Then-Green: Verify that modifying Position.code in the database directly
    influences the derived Account.role without being masked by static memory caches.
    - If Position 1 is renamed to 'QL_TEST', created account must receive role 'EMPLOYEE'.
    - If Position 2 is renamed to 'QL', created account must receive role 'MANAGER'.
    """
    pos1 = Position.objects.get(id=1)
    orig_code_1 = pos1.code
    pos2 = Position.objects.get(id=2)
    orig_code_2 = pos2.code

    try:
        # Case A: Rename Position 1 from QL to QL_TEST
        Position.objects.filter(id=1).update(code="QL_TEST")
        res1 = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Nhân viên Test Đổi Mã Chức Vụ 1",
                "email": "m1_pos1_rename@parking.local",
                "phone": "0918999111",
                "password": "Password123!@#",
                "position_id": 1,
            },
            format="json",
        )
        assert res1.status_code == status.HTTP_201_CREATED
        account_id_1 = res1.json()["account"]["id"]
        acc_1 = Account.objects.get(id=account_id_1)
        assert acc_1.role == "EMPLOYEE", (
            f"Expected role 'EMPLOYEE' for position code 'QL_TEST', got '{acc_1.role}'"
        )

        # Case B: Rename Position 2 from NVVH to QL (Position 1 is currently QL_TEST)
        Position.objects.filter(id=2).update(code="QL")
        res2 = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Nhân viên Test Đổi Mã Chức Vụ 2",
                "email": "m1_pos2_rename@parking.local",
                "phone": "0918999222",
                "password": "Password123!@#",
                "position_id": 2,
            },
            format="json",
        )
        assert res2.status_code == status.HTTP_201_CREATED
        account_id_2 = res2.json()["account"]["id"]
        acc_2 = Account.objects.get(id=account_id_2)
        assert acc_2.role == "MANAGER", (
            f"Expected role 'MANAGER' for position code 'QL', got '{acc_2.role}'"
        )
    finally:
        # Must restore Position 2 before Position 1 to respect uq_position_code_active unique constraint
        Position.objects.filter(id=2).update(code=orig_code_2)
        Position.objects.filter(id=1).update(code=orig_code_1)


def test_high_position_id_with_ql_derives_manager_role(
    manager_client: APIClient,
) -> None:
    """
    M1 Red-Then-Green: High Position ID (>4) with code 'QL' dynamically derives Account.role = 'MANAGER'.
    Temporarily renames Position 1 to allow code 'QL' on high ID position.
    """
    pos1 = Position.objects.get(id=1)
    orig_code_1 = pos1.code

    try:
        Position.objects.filter(id=1).update(code="QL_ORIG_TEMP")
        high_pos = Position.objects.create(
            id=999,
            code="QL",
            name="Quản lý Vùng Mở Rộng",
        )
        assert high_pos.id > 4

        res = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Quản lý ID Cao M1",
                "email": "m1_high_pos@parking.local",
                "phone": "0918999333",
                "password": "Password123!@#",
                "position_id": high_pos.id,
            },
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED
        account_id = res.json()["account"]["id"]
        acc = Account.objects.get(id=account_id)
        assert acc.role == "MANAGER"
    finally:
        with connection.cursor() as cur:
            cur.execute("ALTER TABLE employee DISABLE TRIGGER ALL;")
            cur.execute(
                "DELETE FROM employee WHERE email = %s;", ["m1_high_pos@parking.local"]
            )
            cur.execute("ALTER TABLE employee ENABLE TRIGGER ALL;")
            cur.execute("ALTER TABLE account DISABLE TRIGGER ALL;")
            cur.execute(
                "DELETE FROM account WHERE email = %s;", ["m1_high_pos@parking.local"]
            )
            cur.execute("ALTER TABLE account ENABLE TRIGGER ALL;")
            cur.execute("ALTER TABLE position DISABLE TRIGGER ALL;")
            cur.execute("DELETE FROM position WHERE id = 999;")
            cur.execute("UPDATE position SET code = %s WHERE id = 1;", [orig_code_1])
            cur.execute("ALTER TABLE position ENABLE TRIGGER ALL;")


def test_soft_deleted_position_rejected_on_create_and_update(
    manager_client: APIClient,
) -> None:
    """
    M1 Red-Then-Green: Employee creation and position update strictly reject
    soft-deleted positions with HTTP 400 Bad Request (PROP-GEN-P01).
    """
    soft_pos = Position.objects.create(
        code="TEST_DEL",
        name="Chức vụ Thử Nghiệm Xóa Mềm",
        deleted_at=timezone.now(),
    )

    # 1. Reject on creation
    res_create = manager_client.post(
        "/api/v1/employees/",
        data={
            "full_name": "Nhân viên Gắn Chức Vụ Xóa",
            "email": "m1_soft_pos_create@parking.local",
            "phone": "0918999444",
            "password": "Password123!@#",
            "position_id": soft_pos.id,
        },
        format="json",
    )
    assert res_create.status_code == status.HTTP_400_BAD_REQUEST
    assert res_create.json()["code"] == "PROP-GEN-P01"

    # 2. Reject on update
    target_emp = Employee.objects.filter(deleted_at__isnull=True).first()
    assert target_emp is not None
    res_update = manager_client.patch(
        f"/api/v1/employees/{target_emp.id}/",
        data={
            "row_version": target_emp.row_version,
            "position_id": soft_pos.id,
        },
        format="json",
    )
    assert res_update.status_code == status.HTTP_400_BAD_REQUEST
    assert res_update.json()["code"] == "PROP-GEN-P01"


@override_settings(PASSWORD_HASHERS=base_settings.PASSWORD_HASHERS)
def test_create_employee_uses_argon2_under_base_settings_and_zero_leakage(
    manager_client: APIClient,
) -> None:
    """
    M2 Verification: Proves that under production base settings:
    1. base_settings.PASSWORD_HASHERS[0] is Argon2PasswordHasher.
    2. Employee creation produces an Argon2 password hash with 'argon2$' prefix.
    3. account.check_password(raw_password) validates successfully.
    4. Zero leakage: raw password is never stored plaintext or leaked into any field
       of Employee or Account, nor returned in the API response JSON or content.
    """
    # 1. Base settings verification
    assert (
        base_settings.PASSWORD_HASHERS[0]
        == "django.contrib.auth.hashers.Argon2PasswordHasher"
    )

    raw_pwd = "Password123Production!"
    pos_nvvh = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
    assert pos_nvvh is not None

    payload = {
        "full_name": "Nguyễn Văn Argon2 Prod",
        "email": "argon2_prod_test@parking.local",
        "phone": "0918777999",
        "password": raw_pwd,
        "position_id": pos_nvvh.id,
    }

    res = manager_client.post("/api/v1/employees/", data=payload, format="json")
    assert res.status_code == status.HTTP_201_CREATED

    account_id = res.json()["account"]["id"]
    account = Account.objects.get(id=account_id)
    emp = Employee.objects.get(account=account)

    # 2. Assert Argon2 prefix and verification
    assert account.password.startswith("argon2$"), (
        f"Expected password hash to start with 'argon2$', got: '{account.password[:20]}...'"
    )
    assert account.check_password(raw_pwd) is True

    # 3. Assert raw password is never stored plaintext
    assert account.password != raw_pwd
    assert raw_pwd not in account.password

    # 4. Assert zero leakage across all Employee and Account fields
    for field_name in [
        "code",
        "full_name",
        "email",
        "phone",
        "identity_card_number",
        "address",
    ]:
        val = getattr(emp, field_name, None)
        if val is not None:
            assert raw_pwd not in str(val), (
                f"Raw password leaked in Employee.{field_name}"
            )

    for field_name in ["email", "phone"]:
        val = getattr(account, field_name, None)
        if val is not None:
            assert raw_pwd not in str(val), (
                f"Raw password leaked in Account.{field_name}"
            )

    # 5. Assert zero leakage in API response
    res_data = res.json()
    assert "password" not in res_data
    assert "password" not in res_data.get("account", {})
    assert raw_pwd not in res.content.decode("utf-8")
