"""
Comprehensive Real-Database Test Suite for Administrative-Unit Dropdown Endpoints (Task T2).
Covers:
- Full RBAC matrix: Anonymous 401, CUSTOMER 403, EMPLOYEE 200, MANAGER 200 on all 3 endpoints.
- Exact query count assertion: exactly 1 database query per request (assertNumQueries(1)), 0 queries on 400.
- Deterministic ordering: assert list is strictly ordered by id ASC.
- Parameter validation: missing, non-integer, negative, or zero parent IDs return 400 Bad Request.
- Valid unknown parent ID returns 200 with empty list [].
- Cross-module consistency test: assert that every province_id, district_id, ward_id referenced
  in customer and employee seed data is returned by these dropdown endpoints.
- HTTP method restrictions: POST, PUT, PATCH, DELETE return 405 Method Not Allowed.
"""

from __future__ import annotations

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.models import (
    AdministrativeDistrict,
    AdministrativeProvince,
    AdministrativeWard,
)
from apps.customers.serializers.customers import CustomerCreateSerializer

pytestmark = pytest.mark.django_db


# ==============================================================================
# Fixtures
# ==============================================================================


@pytest.fixture
def auth_manager(db) -> Account:
    """Manager account fixture."""
    acc, _ = Account.objects.get_or_create(
        email="manager_admin_suite@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash_manager",
        },
    )
    return acc


@pytest.fixture
def auth_employee(db) -> Account:
    """Employee account fixture."""
    acc, _ = Account.objects.get_or_create(
        email="employee_admin_suite@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash_employee",
        },
    )
    return acc


@pytest.fixture
def auth_customer(db) -> Account:
    """Customer account fixture."""
    acc, _ = Account.objects.get_or_create(
        email="customer_admin_suite@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash_customer",
        },
    )
    return acc


@pytest.fixture
def manager_client(auth_manager: Account) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=auth_manager)
    return client


@pytest.fixture
def employee_client(auth_employee: Account) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    return client


@pytest.fixture
def customer_client(auth_customer: Account) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    return client


@pytest.fixture
def anonymous_client() -> APIClient:
    return APIClient()


@pytest.fixture
def seeded_hierarchy(db) -> dict[str, int]:
    """Provides valid seeded province, district, ward IDs."""
    province = AdministrativeProvince.objects.order_by("id").first()
    assert province is not None, "AdministrativeProvince seed data missing"
    district = (
        AdministrativeDistrict.objects.filter(province=province).order_by("id").first()
    )
    assert district is not None, "AdministrativeDistrict seed data missing"
    ward = AdministrativeWard.objects.filter(district=district).order_by("id").first()
    assert ward is not None, "AdministrativeWard seed data missing"
    return {
        "province_id": province.id,
        "district_id": district.id,
        "ward_id": ward.id,
    }


# ==============================================================================
# 1. Full RBAC Matrix Tests
# ==============================================================================


@pytest.mark.parametrize(
    "url_builder",
    [
        lambda h: "/api/v1/administrative/provinces/",
        lambda h: f"/api/v1/administrative/districts/?province_id={h['province_id']}",
        lambda h: f"/api/v1/administrative/wards/?district_id={h['district_id']}",
    ],
)
def test_administrative_endpoints_anonymous_unauthorized(
    anonymous_client: APIClient, seeded_hierarchy: dict[str, int], url_builder
):
    """Anonymous request to administrative endpoints must return 401 Unauthorized with MSG-4.1-M02."""
    url = url_builder(seeded_hierarchy)
    res = anonymous_client.get(url)
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json().get("code") == "MSG-4.1-M02"
    assert (
        res.json().get("message") == "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu"
    )


@pytest.mark.parametrize(
    "url_builder",
    [
        lambda h: "/api/v1/administrative/provinces/",
        lambda h: f"/api/v1/administrative/districts/?province_id={h['province_id']}",
        lambda h: f"/api/v1/administrative/wards/?district_id={h['district_id']}",
    ],
)
def test_administrative_endpoints_customer_forbidden(
    customer_client: APIClient, seeded_hierarchy: dict[str, int], url_builder
):
    """Customer request to administrative endpoints must return 403 Forbidden with MSG-4.2-M01."""
    url = url_builder(seeded_hierarchy)
    res = customer_client.get(url)
    assert res.status_code == status.HTTP_403_FORBIDDEN
    assert res.json().get("code") == "MSG-4.2-M01"
    assert res.json().get("message") == "Bạn không có quyền thực hiện thao tác này."


@pytest.mark.parametrize(
    "url_builder",
    [
        lambda h: "/api/v1/administrative/provinces/",
        lambda h: f"/api/v1/administrative/districts/?province_id={h['province_id']}",
        lambda h: f"/api/v1/administrative/wards/?district_id={h['district_id']}",
    ],
)
def test_administrative_endpoints_employee_allowed(
    employee_client: APIClient, seeded_hierarchy: dict[str, int], url_builder
):
    """Employee request to administrative endpoints must return 200 OK bare array."""
    url = url_builder(seeded_hierarchy)
    res = employee_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.json(), list)
    assert len(res.json()) >= 1


@pytest.mark.parametrize(
    "url_builder",
    [
        lambda h: "/api/v1/administrative/provinces/",
        lambda h: f"/api/v1/administrative/districts/?province_id={h['province_id']}",
        lambda h: f"/api/v1/administrative/wards/?district_id={h['district_id']}",
    ],
)
def test_administrative_endpoints_manager_allowed(
    manager_client: APIClient, seeded_hierarchy: dict[str, int], url_builder
):
    """Manager request to administrative endpoints must return 200 OK bare array."""
    url = url_builder(seeded_hierarchy)
    res = manager_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    assert isinstance(res.json(), list)
    assert len(res.json()) >= 1


# ==============================================================================
# 2. Query Count Assertions (assertNumQueries(1))
# ==============================================================================


def test_provinces_query_count_strictly_one(
    employee_client: APIClient, django_assert_num_queries
):
    """GET /api/v1/administrative/provinces/ must execute exactly 1 database query."""
    with django_assert_num_queries(1):
        res = employee_client.get("/api/v1/administrative/provinces/")
    assert res.status_code == status.HTTP_200_OK


def test_districts_query_count_strictly_one(
    employee_client: APIClient,
    seeded_hierarchy: dict[str, int],
    django_assert_num_queries,
):
    """GET /api/v1/administrative/districts/?province_id= must execute exactly 1 database query."""
    url = f"/api/v1/administrative/districts/?province_id={seeded_hierarchy['province_id']}"
    with django_assert_num_queries(1):
        res = employee_client.get(url)
    assert res.status_code == status.HTTP_200_OK


def test_wards_query_count_strictly_one(
    employee_client: APIClient,
    seeded_hierarchy: dict[str, int],
    django_assert_num_queries,
):
    """GET /api/v1/administrative/wards/?district_id= must execute exactly 1 database query."""
    url = f"/api/v1/administrative/wards/?district_id={seeded_hierarchy['district_id']}"
    with django_assert_num_queries(1):
        res = employee_client.get(url)
    assert res.status_code == status.HTTP_200_OK


def test_invalid_parameters_execute_zero_queries(employee_client: APIClient):
    """Parameter format validation occurs before DB access, executing 0 queries."""
    with CaptureQueriesContext(connection) as ctx:
        res = employee_client.get(
            "/api/v1/administrative/districts/?province_id=invalid_text"
        )
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    assert len(ctx.captured_queries) == 0, (
        f"Expected 0 queries on validation failure, executed {len(ctx.captured_queries)}"
    )


# ==============================================================================
# 3. Deterministic Ordering Assertions (id ASC)
# ==============================================================================


def test_provinces_deterministic_ordering_id_asc(employee_client: APIClient):
    """Assert provinces list is strictly ordered by id ASC."""
    res = employee_client.get("/api/v1/administrative/provinces/")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert len(data) >= 2
    ids = [item["id"] for item in data]
    assert ids == sorted(ids), f"Provinces list not sorted by id ASC: {ids}"


def test_districts_deterministic_ordering_id_asc(
    employee_client: APIClient, seeded_hierarchy: dict[str, int]
):
    """Assert districts list is strictly ordered by id ASC."""
    url = f"/api/v1/administrative/districts/?province_id={seeded_hierarchy['province_id']}"
    res = employee_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert len(data) >= 1
    ids = [item["id"] for item in data]
    assert ids == sorted(ids), f"Districts list not sorted by id ASC: {ids}"


def test_wards_deterministic_ordering_id_asc(
    employee_client: APIClient, seeded_hierarchy: dict[str, int]
):
    """Assert wards list is strictly ordered by id ASC."""
    url = f"/api/v1/administrative/wards/?district_id={seeded_hierarchy['district_id']}"
    res = employee_client.get(url)
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert len(data) >= 1
    ids = [item["id"] for item in data]
    assert ids == sorted(ids), f"Wards list not sorted by id ASC: {ids}"


# ==============================================================================
# 4. Parameter Validation & Error Envelope Tests
# ==============================================================================


@pytest.mark.parametrize(
    "invalid_query",
    [
        "",  # Missing province_id parameter
        "?province_id=",  # Empty string
        "?province_id=abc",  # Alphabetic string
        "?province_id=1.5",  # Floating point
        "?province_id=-1",  # Negative integer
        "?province_id=0",  # Zero
        "?province_id=null",  # Literal null
    ],
)
def test_districts_parameter_validation_rejects_with_400(
    employee_client: APIClient, invalid_query: str
):
    """Missing, empty, non-integer, or <= 0 province_id must return 400 Bad Request."""
    url = f"/api/v1/administrative/districts/{invalid_query}"
    res = employee_client.get(url)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    data = res.json()
    assert data.get("code") == "PROP-GEN-P01"
    assert data.get("message") == "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu"


@pytest.mark.parametrize(
    "invalid_query",
    [
        "",  # Missing district_id parameter
        "?district_id=",  # Empty string
        "?district_id=xyz",  # Alphabetic string
        "?district_id=3.14",  # Floating point
        "?district_id=-5",  # Negative integer
        "?district_id=0",  # Zero
        "?district_id=undefined",  # Literal undefined
    ],
)
def test_wards_parameter_validation_rejects_with_400(
    employee_client: APIClient, invalid_query: str
):
    """Missing, empty, non-integer, or <= 0 district_id must return 400 Bad Request."""
    url = f"/api/v1/administrative/wards/{invalid_query}"
    res = employee_client.get(url)
    assert res.status_code == status.HTTP_400_BAD_REQUEST
    data = res.json()
    assert data.get("code") == "PROP-GEN-P01"
    assert data.get("message") == "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu"


def test_districts_unknown_valid_province_id_returns_empty_list(
    employee_client: APIClient,
):
    """A valid positive integer province_id with no matching districts returns 200 with empty list."""
    res = employee_client.get("/api/v1/administrative/districts/?province_id=999999999")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == []


def test_wards_unknown_valid_district_id_returns_empty_list(
    employee_client: APIClient,
):
    """A valid positive integer district_id with no matching wards returns 200 with empty list."""
    res = employee_client.get("/api/v1/administrative/wards/?district_id=999999999")
    assert res.status_code == status.HTTP_200_OK
    assert res.json() == []


# ==============================================================================
# 5. Response Format & Field Projection Tests
# ==============================================================================


def test_administrative_response_schema_exact_fields(employee_client: APIClient):
    """Response items must strictly project id, code, name without leaking timestamps or internal FKs."""
    res = employee_client.get("/api/v1/administrative/provinces/")
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert isinstance(data, list)
    for item in data:
        assert set(item.keys()) == {"id", "code", "name"}
        assert isinstance(item["id"], int)
        assert isinstance(item["code"], str)
        assert isinstance(item["name"], str)
        assert item["name"].strip() != ""


@pytest.mark.parametrize(
    "method",
    ["post", "put", "patch", "delete"],
)
def test_administrative_endpoints_method_not_allowed(
    employee_client: APIClient, seeded_hierarchy: dict[str, int], method: str
):
    """Administrative endpoints are strictly read-only; write methods return 405 Method Not Allowed."""
    client_func = getattr(employee_client, method)
    for url in [
        "/api/v1/administrative/provinces/",
        f"/api/v1/administrative/districts/?province_id={seeded_hierarchy['province_id']}",
        f"/api/v1/administrative/wards/?district_id={seeded_hierarchy['district_id']}",
    ]:
        res = client_func(url, data={})
        assert res.status_code == status.HTTP_405_METHOD_NOT_ALLOWED


# ==============================================================================
# 6. Cross-Module Consistency Tests
# ==============================================================================


def test_cross_module_seed_data_exhaustive_consistency(employee_client: APIClient):
    """
    Prove that every province_id, district_id, ward_id referenced in customer
    and employee seed data is returned by these dropdown endpoints.
    """
    with connection.cursor() as cursor:
        # Collect all non-null province IDs from customer and employee tables
        cursor.execute(
            """
            SELECT DISTINCT province_id FROM customer WHERE province_id IS NOT NULL
            UNION
            SELECT DISTINCT province_id FROM employee WHERE province_id IS NOT NULL
            """
        )
        used_province_ids = {row[0] for row in cursor.fetchall()}

        # Collect all non-null (province_id, district_id) pairs
        cursor.execute(
            """
            SELECT DISTINCT province_id, district_id FROM customer WHERE province_id IS NOT NULL AND district_id IS NOT NULL
            UNION
            SELECT DISTINCT province_id, district_id FROM employee WHERE province_id IS NOT NULL AND district_id IS NOT NULL
            """
        )
        used_district_pairs = set(cursor.fetchall())

        # Collect all non-null (district_id, ward_id) pairs
        cursor.execute(
            """
            SELECT DISTINCT district_id, ward_id FROM customer WHERE district_id IS NOT NULL AND ward_id IS NOT NULL
            UNION
            SELECT DISTINCT district_id, ward_id FROM employee WHERE district_id IS NOT NULL AND ward_id IS NOT NULL
            """
        )
        used_ward_pairs = set(cursor.fetchall())

    # 1. Verify provinces
    res_prov = employee_client.get("/api/v1/administrative/provinces/")
    assert res_prov.status_code == status.HTTP_200_OK
    returned_prov_ids = {p["id"] for p in res_prov.json()}
    for prov_id in used_province_ids:
        assert prov_id in returned_prov_ids, (
            f"province_id {prov_id} from seed is missing in dropdown endpoint"
        )

    # 2. Verify districts per province
    for prov_id, dist_id in used_district_pairs:
        res_dist = employee_client.get(
            f"/api/v1/administrative/districts/?province_id={prov_id}"
        )
        assert res_dist.status_code == status.HTTP_200_OK
        returned_dist_ids = {d["id"] for d in res_dist.json()}
        assert dist_id in returned_dist_ids, (
            f"district_id {dist_id} for province {prov_id} is missing in dropdown endpoint"
        )

    # 3. Verify wards per district
    for dist_id, ward_id in used_ward_pairs:
        res_ward = employee_client.get(
            f"/api/v1/administrative/wards/?district_id={dist_id}"
        )
        assert res_ward.status_code == status.HTTP_200_OK
        returned_ward_ids = {w["id"] for w in res_ward.json()}
        assert ward_id in returned_ward_ids, (
            f"ward_id {ward_id} for district {dist_id} is missing in dropdown endpoint"
        )


def test_cross_module_customer_creation_contract(employee_client: APIClient):
    """
    Prove that administrative IDs fetched from the dropdown endpoints
    are valid and accepted by CustomerCreateSerializer without hierarchy errors.
    """
    # 1. Fetch first province
    res_p = employee_client.get("/api/v1/administrative/provinces/")
    assert res_p.status_code == status.HTTP_200_OK
    province = res_p.json()[0]

    # 2. Fetch first district under this province
    res_d = employee_client.get(
        f"/api/v1/administrative/districts/?province_id={province['id']}"
    )
    assert res_d.status_code == status.HTTP_200_OK
    assert len(res_d.json()) > 0
    district = res_d.json()[0]

    # 3. Fetch first ward under this district
    res_w = employee_client.get(
        f"/api/v1/administrative/wards/?district_id={district['id']}"
    )
    assert res_w.status_code == status.HTTP_200_OK
    assert len(res_w.json()) > 0
    ward = res_w.json()[0]

    # 4. Pass IDs into CustomerCreateSerializer
    payload = {
        "full_name": "Phan Đình Giót",
        "identity_card_number": "048099001234",
        "phone": "0987111222",
        "province_id": province["id"],
        "district_id": district["id"],
        "ward_id": ward["id"],
    }
    serializer = CustomerCreateSerializer(data=payload)
    assert serializer.is_valid(), (
        f"Serializer validation failed on dropdown IDs: {serializer.errors}"
    )
    assert serializer.validated_data["province_id"] == province["id"]
    assert serializer.validated_data["district_id"] == district["id"]
    assert serializer.validated_data["ward_id"] == ward["id"]
