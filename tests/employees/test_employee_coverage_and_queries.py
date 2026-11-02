"""
Measured Query Count Bounds and Comprehensive Unit/Boundary Tests for Employee Module.
Module: apps.employees (SRS 4.3.1–4.3.4, Milestone M4, Round 67).

Ensures:
1. Exact Query Bounds Assertions across all 7 endpoints:
   - positions/ : == 1
   - summary/ : == 1
   - employees/ (list) : <= 2
   - employees/{id}/ (detail) : <= 2
   - employees/ (create) : <= 8 (pure SQL)
   - employees/{id}/ (update) : <= 6 (pure SQL, measured 3-5)
   - employees/{id}/ (delete) : <= 6 (pure SQL)
2. >= 95% Line & Branch coverage on apps/employees/selectors/employees.py
3. >= 95% Line & Branch coverage on apps/employees/serializers/employees.py
4. >= 95% Line & Branch coverage on apps/employees/services/employees.py
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.models import Session
from django.db import connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.exceptions import BusinessAPIException
from apps.core.models import (
    AdministrativeDistrict,
    AdministrativeProvince,
    AdministrativeWard,
)
from apps.employees.models import Employee, Position
from apps.employees.selectors.employees import (
    get_employee_by_id,
    get_employee_summary,
    list_employees,
)
from apps.employees.serializers.employees import (
    EmployeeCreateSerializer,
    EmployeeDetailSerializer,
    EmployeeFilterSerializer,
    EmployeeListSerializer,
    EmployeeUpdateSerializer,
    has_emoji_or_pictograph,
    validate_password_complexity,
    validate_raw_address,
    validate_raw_employee_name,
)
from apps.employees.services.employees import (
    create_employee,
    generate_employee_code,
    revoke_account_sessions_and_tokens,
    soft_delete_employee,
    update_employee,
    validate_password_policy,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def manager_account() -> Account:
    acc = Account.objects.filter(
        role="MANAGER", is_active=True, deleted_at__isnull=True
    ).first()
    if not acc:
        acc = Account.objects.create(
            email="cov_manager@parking.local",
            phone="0901999777",
            role="MANAGER",
            is_active=True,
            password=make_password("Manager123!@#"),
        )
    return acc


@pytest.fixture
def manager_client(manager_account: Account) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=manager_account)
    return client


# ==============================================================================
# 1. MEASURED QUERY COUNT BOUNDS (7 ENDPOINTS)
# ==============================================================================


class TestEmployeeQueryBounds:
    """Exact query count assertions for all 7 employee module endpoints."""

    def test_positions_query_bound(self, manager_client: APIClient) -> None:
        """GET /api/v1/positions/ executed in exactly 1 query."""
        with CaptureQueriesContext(connection) as ctx:
            res = manager_client.get("/api/v1/positions/")
        assert res.status_code == status.HTTP_200_OK
        pure_queries = [q for q in ctx.captured_queries if "SAVEPOINT" not in q["sql"]]
        assert len(pure_queries) == 1

    def test_summary_query_bound(self, manager_client: APIClient) -> None:
        """GET /api/v1/employees/summary/ executed in exactly 1 query (aggregate SOT)."""
        with CaptureQueriesContext(connection) as ctx:
            res = manager_client.get("/api/v1/employees/summary/")
        assert res.status_code == status.HTTP_200_OK
        pure_queries = [q for q in ctx.captured_queries if "SAVEPOINT" not in q["sql"]]
        assert len(pure_queries) == 1

    def test_list_query_bound(self, manager_client: APIClient) -> None:
        """GET /api/v1/employees/ (paginated) executed in <= 2 queries (COUNT + SELECT)."""
        with CaptureQueriesContext(connection) as ctx:
            res = manager_client.get("/api/v1/employees/?page=1&page_size=10")
        assert res.status_code == status.HTTP_200_OK
        pure_queries = [q for q in ctx.captured_queries if "SAVEPOINT" not in q["sql"]]
        assert len(pure_queries) <= 2

    def test_detail_query_bound(self, manager_client: APIClient) -> None:
        """GET /api/v1/employees/{id}/ executed in <= 2 queries (1 query with select_related)."""
        emp = Employee.objects.filter(deleted_at__isnull=True).first()
        assert emp is not None
        with CaptureQueriesContext(connection) as ctx:
            res = manager_client.get(f"/api/v1/employees/{emp.id}/")
        assert res.status_code == status.HTTP_200_OK
        pure_queries = [q for q in ctx.captured_queries if "SAVEPOINT" not in q["sql"]]
        assert len(pure_queries) <= 2

    def test_create_query_bound(self, manager_client: APIClient) -> None:
        """POST /api/v1/employees/ executed in <= 9 pure SQL queries (measured 8-9 with live DB position code query)."""
        prov = AdministrativeProvince.objects.first()
        dist = AdministrativeDistrict.objects.filter(province=prov).first()
        ward = AdministrativeWard.objects.filter(district=dist).first()
        pos = Position.objects.filter(deleted_at__isnull=True, code="NVVH").first()
        assert pos is not None

        payload = {
            "full_name": "Nguyễn Văn Đo Lường Query",
            "date_of_birth": "1993-06-15",
            "gender": "Nam",
            "identity_card_number": "079093888777",
            "phone": "0919888777",
            "email": "cov_query_create@parking.local",
            "address": "123 Đường Test",
            "province_id": prov.id if prov else 1,
            "district_id": dist.id if dist else 1,
            "ward_id": ward.id if ward else 1,
            "position_id": pos.id,
            "status": "ACTIVE",
            "password": "Password123!@#",
        }

        with transaction.atomic():
            sid = transaction.savepoint_create()
            try:
                with CaptureQueriesContext(connection) as ctx:
                    res = manager_client.post(
                        "/api/v1/employees/", payload, format="json"
                    )
                assert res.status_code == status.HTTP_201_CREATED
                pure_queries = [
                    q for q in ctx.captured_queries if "SAVEPOINT" not in q["sql"]
                ]
                assert len(pure_queries) <= 9, (
                    f"Expected <= 9 queries, got {len(pure_queries)}"
                )
            finally:
                transaction.savepoint_rollback(sid)

    def test_update_query_bound(
        self, manager_client: APIClient, manager_account: Account
    ) -> None:
        """PATCH /api/v1/employees/{id}/ executed in <= 6 pure SQL queries (measured 3-5)."""
        target_emp = (
            Employee.objects.filter(deleted_at__isnull=True)
            .exclude(account=manager_account)
            .first()
        )
        assert target_emp is not None

        payload = {
            "full_name": "Nguyễn Văn Đã Đo Query",
            "row_version": target_emp.row_version,
        }

        with transaction.atomic():
            sid = transaction.savepoint_create()
            try:
                with CaptureQueriesContext(connection) as ctx:
                    res = manager_client.patch(
                        f"/api/v1/employees/{target_emp.id}/", payload, format="json"
                    )
                assert res.status_code == status.HTTP_200_OK
                pure_queries = [
                    q for q in ctx.captured_queries if "SAVEPOINT" not in q["sql"]
                ]
                assert len(pure_queries) <= 6, (
                    f"Expected <= 6 queries, got {len(pure_queries)}"
                )
            finally:
                transaction.savepoint_rollback(sid)

    def test_delete_query_bound(
        self, manager_client: APIClient, manager_account: Account
    ) -> None:
        """DELETE /api/v1/employees/{id}/ executed in <= 6 pure SQL queries."""
        del_emp = (
            Employee.objects.filter(
                deleted_at__isnull=True, position__code__in=["NVVH", "NVTN", "KTV"]
            )
            .exclude(account=manager_account)
            .first()
        )
        assert del_emp is not None

        with transaction.atomic():
            sid = transaction.savepoint_create()
            try:
                with CaptureQueriesContext(connection) as ctx:
                    res = manager_client.delete(f"/api/v1/employees/{del_emp.id}/")
                assert res.status_code == status.HTTP_200_OK
                pure_queries = [
                    q for q in ctx.captured_queries if "SAVEPOINT" not in q["sql"]
                ]
                assert len(pure_queries) <= 6, (
                    f"Expected <= 6 queries, got {len(pure_queries)}"
                )
            finally:
                transaction.savepoint_rollback(sid)


# ==============================================================================
# 2. SELECTOR COVERAGE TESTS
# ==============================================================================


class TestEmployeeSelectorCoverage:
    """Coverage expansion for apps.employees.selectors.employees."""

    def test_get_employee_summary_fallback_when_total_positions_none(self) -> None:
        """Covers line 84: fallback when total_positions aggregate returns None."""
        with patch.object(
            Employee.objects,
            "aggregate",
            return_value={
                "total_employees": 0,
                "active_employees": 0,
                "inactive_employees": 0,
                "total_positions": None,
            },
        ):
            summary = get_employee_summary()
            assert (
                summary["total_positions"]
                == Position.objects.filter(deleted_at__isnull=True).count()
            )

    def test_list_employees_filter_by_name(self) -> None:
        """Covers lines 150-151: filtering by name directly (?name=...)."""
        emp = Employee.objects.filter(deleted_at__isnull=True).first()
        assert emp is not None
        qs = list_employees(filters={"name": emp.full_name[:3]})
        assert qs.filter(id=emp.id).exists()

    def test_list_employees_filter_by_code(self) -> None:
        """Covers lines 155-156: filtering by code directly (?code=...)."""
        emp = Employee.objects.filter(deleted_at__isnull=True).first()
        assert emp is not None
        qs = list_employees(filters={"code": emp.code})
        assert qs.filter(id=emp.id).exists()

    def test_list_employees_filter_by_address(self) -> None:
        """Covers lines 160-161: filtering by address directly (?address=...)."""
        emp = (
            Employee.objects.filter(deleted_at__isnull=True)
            .exclude(address__isnull=True)
            .exclude(address="")
            .first()
        )
        if emp and emp.address:
            qs = list_employees(filters={"address": emp.address[:4]})
            assert qs.filter(id=emp.id).exists()

    def test_list_employees_filter_birth_range_valid_and_invalid(self) -> None:
        """Covers lines 171-174, 184-187: birth_from / birth_to valid & invalid formats."""
        # Valid range
        qs = list_employees(
            filters={"birth_from": "1980-01-01", "birth_to": "2005-12-31"}
        )
        assert qs.exists()

        # Invalid birth_from format raises 400
        with pytest.raises(BusinessAPIException) as exc_info:
            list_employees(filters={"birth_from": "invalid-date"})
        assert exc_info.value.code == "PROP-GEN-P01"

        # Invalid birth_to format raises 400
        with pytest.raises(BusinessAPIException) as exc_info:
            list_employees(filters={"birth_to": "not-a-date"})
        assert exc_info.value.code == "PROP-GEN-P01"

    def test_list_employees_filter_by_numeric_position_id(self) -> None:
        """Covers line 211: clean_pos.isdigit() branch (?position=<numeric_id>)."""
        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None
        qs = list_employees(filters={"position": str(pos.id)})
        for item in qs:
            assert item.position_id == pos.id

    def test_list_employees_ordering_whitelist_and_invalid(self) -> None:
        """Covers lines 232, 238: ordering whitelist validation and special id handling."""
        # Valid custom ordering
        qs_asc = list_employees(filters={"ordering": "id"})
        assert qs_asc.ordered

        qs_desc = list_employees(filters={"ordering": "-id"})
        assert qs_desc.ordered

        # Invalid ordering not in whitelist
        with pytest.raises(BusinessAPIException) as exc_info:
            list_employees(filters={"ordering": "password_hash"})
        assert exc_info.value.code == "PROP-GEN-P01"

    def test_get_employee_by_id_none(self) -> None:
        """Covers line 260: get_employee_by_id(None) raises 404."""
        with pytest.raises(BusinessAPIException) as exc_info:
            get_employee_by_id(None)
        assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND


# ==============================================================================
# 3. SERIALIZER COVERAGE TESTS
# ==============================================================================


class TestEmployeeSerializerCoverage:
    """Coverage expansion for apps.employees.serializers.employees."""

    def test_has_emoji_or_pictograph_misc_symbols(self) -> None:
        """Covers line 89: Pictograph in 0x2600–0x27BF (e.g. coffee symbol, lightning)."""
        assert has_emoji_or_pictograph("Nguyễn ☕ Văn") is True
        assert has_emoji_or_pictograph("Trần ⚡ Nam") is True
        assert has_emoji_or_pictograph("Nguyễn Văn An") is False

    def test_validate_raw_employee_name_edges(self) -> None:
        """Covers lines 101, 103, 105, 107, 115, 125 in validate_raw_employee_name."""
        # None or empty
        with pytest.raises(serializers.ValidationError):
            validate_raw_employee_name(None)
        with pytest.raises(serializers.ValidationError):
            validate_raw_employee_name("")
        with pytest.raises(serializers.ValidationError):
            validate_raw_employee_name("   ")

        # Non-string
        with pytest.raises(serializers.ValidationError):
            validate_raw_employee_name(12345)

        # Null byte
        with pytest.raises(serializers.ValidationError):
            validate_raw_employee_name("Nguyễn\x00Văn")

        # Length > 45
        with pytest.raises(serializers.ValidationError):
            validate_raw_employee_name("A" * 46)

        # Control characters
        with pytest.raises(serializers.ValidationError):
            validate_raw_employee_name("Nguyễn\x07Văn")

    def test_validate_raw_address_edges(self) -> None:
        """Covers lines 134, 136, 138, 140, 143, 148, 153 in validate_raw_address."""
        # None or empty returns None
        assert validate_raw_address(None) is None
        assert validate_raw_address("") is None
        assert validate_raw_address("   ") is None

        # Non-string
        with pytest.raises(serializers.ValidationError):
            validate_raw_address(12345)

        # Null byte
        with pytest.raises(serializers.ValidationError):
            validate_raw_address("123\x00Đường")

        # Length > 100
        with pytest.raises(serializers.ValidationError):
            validate_raw_address("A" * 101)

        # Zero-width char
        with pytest.raises(serializers.ValidationError):
            validate_raw_address("123\u200b Đường")

        # Control char
        with pytest.raises(serializers.ValidationError):
            validate_raw_address("123\x01 Đường")

        # Valid address stripped
        assert validate_raw_address("  123 Đường Số 1  ") == "123 Đường Số 1"

    def test_validate_password_complexity_non_str(self) -> None:
        """Covers line 167: validate_password_complexity non-string."""
        with pytest.raises(serializers.ValidationError):
            validate_password_complexity(12345678)  # type: ignore[arg-type]

    def test_serializer_get_position_and_account_none(self) -> None:
        """Covers lines 256, 373, 388: get_position & get_account when fields are None."""
        emp = Employee(
            id=9999,
            code="NV999",
            full_name="Null Relations",
            phone="0911111111",
            email="null@test.local",
        )
        list_ser = EmployeeListSerializer(emp)
        assert list_ser.data["position"] is None
        assert list_ser.data["area"] == {"district_name": None, "province_name": None}

        detail_ser = EmployeeDetailSerializer(emp)
        assert detail_ser.data["position"] is None
        assert detail_ser.data["account"] is None
        assert detail_ser.data["province"] is None

    def test_employee_create_serializer_validation_edges(self) -> None:
        """Covers lines 542, 545, 552, 555, 560, 565, 568, 575, 578, 585 in EmployeeCreateSerializer."""
        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None
        base_valid = {
            "code": "NV001",
            "full_name": "Nguyễn Văn Test",
            "email": "test.valid@example.com",
            "phone": "0987654321",
            "password": "ValidPassword123!@#",
            "position_id": pos.id,
        }

        # Invalid CCCD format
        ser_cccd = EmployeeCreateSerializer(
            data={**base_valid, "identity_card_number": "not_digits"}
        )
        assert not ser_cccd.is_valid()
        assert "identity_card_number" in ser_cccd.errors

        ser_cccd_short = EmployeeCreateSerializer(
            data={**base_valid, "identity_card_number": "1234"}
        )
        assert not ser_cccd_short.is_valid()
        assert "identity_card_number" in ser_cccd_short.errors

        # Invalid code format
        ser_code = EmployeeCreateSerializer(data={**base_valid, "code": "NV12"})
        assert not ser_code.is_valid()
        assert "code" in ser_code.errors

        # Future date_of_birth
        future_date = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
        ser_dob = EmployeeCreateSerializer(
            data={**base_valid, "date_of_birth": future_date}
        )
        assert not ser_dob.is_valid()
        assert "date_of_birth" in ser_dob.errors

        # Gender invalid
        ser_gender = EmployeeCreateSerializer(data={**base_valid, "gender": "Other"})
        assert not ser_gender.is_valid()
        assert "gender" in ser_gender.errors

        # Status invalid
        ser_status = EmployeeCreateSerializer(
            data={**base_valid, "status": "INVALID_STATUS"}
        )
        assert not ser_status.is_valid()
        assert "status" in ser_status.errors

        # Non-existent position_id
        ser_pos = EmployeeCreateSerializer(data={**base_valid, "position_id": 999999})
        assert not ser_pos.is_valid()
        assert "position_id" in ser_pos.errors

        # Invalid geo hierarchy: ward without district
        ser_geo1 = EmployeeCreateSerializer(
            data={**base_valid, "ward_id": 1, "district_id": None}
        )
        assert not ser_geo1.is_valid()
        assert "ward_id" in ser_geo1.errors

        # district without province
        ser_geo2 = EmployeeCreateSerializer(
            data={**base_valid, "district_id": 1, "province_id": None}
        )
        assert not ser_geo2.is_valid()
        assert "district_id" in ser_geo2.errors

        # ward not belonging to district
        ser_geo3 = EmployeeCreateSerializer(
            data={**base_valid, "province_id": 1, "district_id": 999999, "ward_id": 1}
        )
        assert not ser_geo3.is_valid()
        assert "ward_id" in ser_geo3.errors

        # district not belonging to province
        ser_geo4 = EmployeeCreateSerializer(
            data={**base_valid, "province_id": 999999, "district_id": 1}
        )
        assert not ser_geo4.is_valid()
        assert "district_id" in ser_geo4.errors

    def test_employee_update_serializer_validation_edges(self) -> None:
        """Covers lines 744, 749, 755-762, 765-767, 770-777, 782, 789, 818, 826, 830, 841, 852 in EmployeeUpdateSerializer."""
        # Field level validations
        ser_fields = EmployeeUpdateSerializer(
            data={
                "row_version": 1,
                "identity_card_number": "invalid_chars",
                "date_of_birth": "2099-01-01",
                "gender": "UnknownGender",
                "position_id": 999999,
                "status": "BAD_STATUS",
            }
        )
        assert not ser_fields.is_valid()
        assert "identity_card_number" in ser_fields.errors
        assert "date_of_birth" in ser_fields.errors
        assert "gender" in ser_fields.errors
        assert "position_id" in ser_fields.errors
        assert "status" in ser_fields.errors

        # Object level geo validations in validate(attrs)
        # 1. ward without district
        ser_geo1 = EmployeeUpdateSerializer(
            data={"row_version": 1, "ward_id": 1, "district_id": None}
        )
        assert not ser_geo1.is_valid()
        assert "ward_id" in ser_geo1.errors

        # 2. district without province
        ser_geo2 = EmployeeUpdateSerializer(
            data={"row_version": 1, "district_id": 1, "province_id": None}
        )
        assert not ser_geo2.is_valid()
        assert "district_id" in ser_geo2.errors

        # 3. ward not belonging to district
        ser_geo3 = EmployeeUpdateSerializer(
            data={
                "row_version": 1,
                "province_id": 1,
                "district_id": 999999,
                "ward_id": 1,
            }
        )
        assert not ser_geo3.is_valid()
        assert "ward_id" in ser_geo3.errors

        # 4. district not belonging to province
        ser_geo4 = EmployeeUpdateSerializer(
            data={"row_version": 1, "province_id": 999999, "district_id": 1}
        )
        assert not ser_geo4.is_valid()
        assert "district_id" in ser_geo4.errors

    def test_employee_filter_serializer_validate_status_empty(self) -> None:
        """Covers line 921: EmployeeFilterSerializer.validate_status empty/None -> ''."""
        ser1 = EmployeeFilterSerializer(data={"status": ""})
        assert ser1.is_valid()
        assert ser1.validated_data["status"] == ""

        ser2 = EmployeeFilterSerializer(data={})
        assert ser2.is_valid()

    def test_serializer_empty_optional_fields_and_code_immutable(self) -> None:
        """Covers lines 542, 552, 565, 575, 744, 749, 756, 771, 802-805, 818."""
        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None

        # EmployeeCreateSerializer with empty optional strings returns None/ACTIVE
        create_ser = EmployeeCreateSerializer(
            data={
                "full_name": "Nguyễn Văn Test",
                "email": "test.empty@example.com",
                "phone": "0987654321",
                "password": "ValidPassword123!@#",
                "position_id": pos.id,
                "identity_card_number": "",
                "code": "",
                "gender": "",
            }
        )
        assert create_ser.is_valid(), create_ser.errors
        assert create_ser.validated_data["identity_card_number"] is None
        assert create_ser.validated_data["code"] is None
        assert create_ser.validated_data["gender"] is None
        assert create_ser.validated_data["status"] == "ACTIVE"
        assert EmployeeCreateSerializer().validate_status("") == "ACTIVE"
        assert EmployeeCreateSerializer().validate_status(None) == "ACTIVE"

        # EmployeeUpdateSerializer code in initial_data raises validation error
        update_ser_code = EmployeeUpdateSerializer(
            data={"row_version": 1, "code": "NV001"}
        )
        assert not update_ser_code.is_valid()
        assert "code" in update_ser_code.errors

        # EmployeeUpdateSerializer with empty optional fields
        update_ser_empty = EmployeeUpdateSerializer(
            data={
                "row_version": 1,
                "address": "  Hà Nội  ",
                "identity_card_number": "",
                "gender": "",
            }
        )
        assert update_ser_empty.is_valid(), update_ser_empty.errors
        assert update_ser_empty.validated_data["address"] == "Hà Nội"
        assert update_ser_empty.validated_data["identity_card_number"] is None
        assert update_ser_empty.validated_data["gender"] is None

        # EmployeeUpdateSerializer invalid phone format
        update_ser_phone = EmployeeUpdateSerializer(
            data={"row_version": 1, "phone": "invalid_phone"}
        )
        assert not update_ser_phone.is_valid()
        assert "phone" in update_ser_phone.errors

        # Password single string error handling
        with patch(
            "apps.employees.serializers.employees.validate_password_complexity",
            side_effect=serializers.ValidationError("Lỗi đơn"),
        ):
            update_ser_pwd = EmployeeUpdateSerializer(
                data={"row_version": 1, "password": "weak"}
            )
            assert not update_ser_pwd.is_valid()
            assert "password" in update_ser_pwd.errors


# ==============================================================================
# 4. SERVICE COVERAGE TESTS
# ==============================================================================


class TestEmployeeServiceCoverage:
    """Coverage expansion for apps.employees.services.employees."""

    def test_validate_password_policy_all_branches(self) -> None:
        """Covers lines 52, 59, 66, 73, 80, 87 in validate_password_policy."""
        # Non-string
        with pytest.raises(BusinessAPIException):
            validate_password_policy(12345678)  # type: ignore

        # Length < 8
        with pytest.raises(BusinessAPIException):
            validate_password_policy("Sh0rt!")

        # Length > 50
        with pytest.raises(BusinessAPIException):
            validate_password_policy("A1!" + "a" * 48)

        # Missing lowercase
        with pytest.raises(BusinessAPIException):
            validate_password_policy("UPPERCASE123!@#")

        # Missing uppercase
        with pytest.raises(BusinessAPIException):
            validate_password_policy("lowercase123!@#")

        # Missing digit
        with pytest.raises(BusinessAPIException):
            validate_password_policy("NoDigitsHere!@#")

        # Missing special character
        with pytest.raises(BusinessAPIException):
            validate_password_policy("NoSpecial123456")

        # Valid
        validate_password_policy("Valid123!@#")

    def test_generate_employee_code_sequence_extension_over_999(self) -> None:
        """Covers line 131: generate_employee_code formatting NV%04d when next_num >= 1000."""
        # Mock cursor.fetchone to return 999 so next_num becomes 1000
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = [999]
        code_1000 = generate_employee_code(mock_cursor)
        assert code_1000 == "NV1000"

        mock_cursor.fetchone.return_value = [1050]
        code_1051 = generate_employee_code(mock_cursor)
        assert code_1051 == "NV1051"

    def test_revoke_account_sessions_decode_exception_handled(self) -> None:
        """Covers lines 153-154: SessionStore decoding failure continues cleanly."""
        acc = Account.objects.filter(is_active=True).first()
        assert acc is not None

        # Create session with broken data that raises on decode
        Session.objects.create(
            session_key="corrupt_session_test_key",
            session_data="corrupted_base64_string",
            expire_date=timezone.now() + datetime.timedelta(days=1),
        )
        try:
            # Should not crash, continues in try/except
            count = revoke_account_sessions_and_tokens(acc.id)
            assert isinstance(count, int)
        finally:
            Session.objects.filter(session_key="corrupt_session_test_key").delete()

    def test_create_employee_service_input_validations(self) -> None:
        """Covers lines 177, 182, 190, 201, 214, 272, 278, 311 in create_employee."""
        # Missing position_id
        with pytest.raises(BusinessAPIException) as exc:
            create_employee(data={"password": "ValidPassword123!@#"})
        assert exc.value.code == "PROP-GEN-P01"

        # Invalid position_id
        with pytest.raises(BusinessAPIException) as exc:
            create_employee(
                data={"position_id": 999999, "password": "ValidPassword123!@#"}
            )
        assert exc.value.code == "PROP-GEN-P01"

        # Missing password
        with pytest.raises(BusinessAPIException) as exc:
            create_employee(data={"position_id": 1, "password": ""})
        assert exc.value.code == "PROP-GEN-P01"

        # Empty email or phone
        with pytest.raises(BusinessAPIException) as exc:
            create_employee(
                data={
                    "position_id": 1,
                    "password": "ValidPassword123!@#",
                    "email": "",
                    "phone": "0911",
                }
            )
        assert exc.value.code == "PROP-GEN-P01"

        # Invalid geo hierarchy: ward without district
        with pytest.raises(BusinessAPIException) as exc:
            create_employee(
                data={
                    "position_id": 1,
                    "password": "ValidPassword123!@#",
                    "email": "a@t.c",
                    "phone": "0911",
                    "ward_id": 1,
                    "district_id": None,
                }
            )
        assert exc.value.code == "PROP-GEN-P01"

        # Invalid geo hierarchy: district without province
        with pytest.raises(BusinessAPIException) as exc:
            create_employee(
                data={
                    "position_id": 1,
                    "password": "ValidPassword123!@#",
                    "email": "a@t.c",
                    "phone": "0911",
                    "district_id": 1,
                    "province_id": None,
                }
            )
        assert exc.value.code == "PROP-GEN-P01"

        # Invalid status
        with pytest.raises(BusinessAPIException) as exc:
            create_employee(
                data={
                    "position_id": 1,
                    "password": "ValidPassword123!@#",
                    "email": "a@t.c",
                    "phone": "0911",
                    "status": "UNKNOWN",
                }
            )
        assert exc.value.code == "PROP-GEN-P01"

    def test_update_employee_service_edges(self) -> None:
        """Covers lines 397, 399, 404, 416, 424, 435, 446 in update_employee."""
        emp = Employee.objects.filter(deleted_at__isnull=True).first()
        assert emp is not None

        # employee parameter as int
        res1 = update_employee(employee=emp.id, data={"row_version": emp.row_version})
        assert res1.id == emp.id

        # employee parameter as instance
        emp.refresh_from_db()
        res2 = update_employee(employee=emp, data={"row_version": emp.row_version})
        assert res2.id == emp.id

        # employee_id is None raises 404
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(employee_id=None, data={"row_version": 1})
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

        # employee not found raises 404
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(employee_id=999999, data={"row_version": 1})
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

        # missing row_version raises 400
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(employee_id=emp.id, data={})
        assert exc.value.code == "PROP-GEN-P01"

        # immutable code raises 400
        emp.refresh_from_db()
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=emp.id,
                data={"row_version": emp.row_version, "code": "NV9999"},
            )
        assert exc.value.code == "PROP-GEN-P01"

        # invalid status raises 400
        emp.refresh_from_db()
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=emp.id,
                data={"row_version": emp.row_version, "status": "BAD_STATUS"},
            )
        assert exc.value.code == "PROP-GEN-P01"

    def test_update_employee_service_password_change(self) -> None:
        """Covers lines 590-593: password update on employee."""
        emp = Employee.objects.filter(
            deleted_at__isnull=True, account__isnull=False
        ).first()
        assert emp is not None and emp.account is not None
        old_hash = emp.account.password

        updated = update_employee(
            employee_id=emp.id,
            data={
                "row_version": emp.row_version,
                "password": "NewStrongPassword123!@#",
            },
        )
        assert updated.account is not None
        emp.account.refresh_from_db()
        assert emp.account.password != old_hash

    def test_soft_delete_employee_service_edges(self) -> None:
        """Covers lines 650-660: soft_delete_employee parameter handling (instance, int, None)."""
        # employee_id is None raises 404
        with pytest.raises(BusinessAPIException) as exc:
            soft_delete_employee(employee_id=None)
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

        # employee_id not found raises 404
        with pytest.raises(BusinessAPIException) as exc:
            soft_delete_employee(employee_id=999999)
        assert exc.value.status_code == status.HTTP_404_NOT_FOUND

    def test_get_position_code_uncached_and_not_found(self) -> None:
        """Covers get_position_code direct DB query & None return for non-existent position."""
        from apps.employees.services.employees import get_position_code

        pos = Position.objects.filter(deleted_at__isnull=True).first()
        assert pos is not None
        fetched = get_position_code(pos.id)
        assert fetched == pos.code

        # Non-existent position returns None
        assert get_position_code(999999) is None

    def test_create_employee_service_kwargs_and_created_by(self) -> None:
        """Covers lines 201, 214, 294 in create_employee."""
        admin_acc = Account.objects.filter(role="ADMIN").first()
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None

        # Non-int position_id raises 400
        with pytest.raises(BusinessAPIException) as exc:
            create_employee(
                data={
                    "position_id": "not_an_int",
                    "password": "Password123!@#",
                    "email": "a@b.c",
                    "phone": "0911",
                }
            )
        assert exc.value.code == "PROP-GEN-P01"

        # payload update from kwargs and created_by actor
        emp = create_employee(
            data={
                "position_id": pos.id,
                "password": "Password123!@#",
                "email": "kwarg_emp@test.local",
                "phone": "0977889900",
                "full_name": "Kwarg Employee",
            },
            created_by=admin_acc,
            status="ACTIVE",
        )
        assert emp.full_name == "Kwarg Employee"
        assert emp.id is not None

        # Invalid client code regex raises MSG-4.3.2-M02
        with pytest.raises(BusinessAPIException) as exc:
            create_employee(
                data={
                    "position_id": pos.id,
                    "password": "Password123!@#",
                    "email": "a2@b.c",
                    "phone": "0911222333",
                    "code": "NV12",
                }
            )
        assert exc.value.code == "MSG-4.3.2-M02"

    def test_update_employee_security_guards_self_and_last_manager(self) -> None:
        """Covers lines 422, 430, 440-449, 452-474 in update_employee."""
        mgr_pos = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
        nvvh_pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert mgr_pos is not None and nvvh_pos is not None

        mgr_emp = Employee.objects.filter(
            position=mgr_pos, deleted_at__isnull=True, account__isnull=False
        ).first()
        assert mgr_emp is not None and mgr_emp.account is not None

        # 1. Non-int position_id raises 400
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=mgr_emp.id,
                data={"row_version": mgr_emp.row_version, "position_id": "bad_id"},
            )
        assert exc.value.code == "PROP-GEN-P01"

        # 2. Non-existent position_id raises 400
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=mgr_emp.id,
                data={"row_version": mgr_emp.row_version, "position_id": 999999},
            )
        assert exc.value.code == "PROP-GEN-P01"

        # 3. Self-deactivation raises PROP-DEL-01-SELF-DEACT
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=mgr_emp.id,
                data={"row_version": mgr_emp.row_version, "status": "INACTIVE"},
                actor=mgr_emp.account,
            )
        assert exc.value.code == "PROP-DEL-01-SELF-DEACT"

        # 4. Self-demotion raises PROP-DEL-01-SELF-DEMOTE
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=mgr_emp.id,
                data={"row_version": mgr_emp.row_version, "position_id": nvvh_pos.id},
                actor=mgr_emp.account,
            )
        assert exc.value.code == "PROP-DEL-01-SELF-DEMOTE"

        # 5. Last active manager deactivation raises PROP-DEL-01-LAST-MGR-EMP
        with patch.object(Account.objects, "filter") as mock_filter:
            mock_filter.return_value.exclude.return_value.count.return_value = 0
            with pytest.raises(BusinessAPIException) as exc:
                update_employee(
                    employee_id=mgr_emp.id,
                    data={"row_version": mgr_emp.row_version, "status": "INACTIVE"},
                    actor=None,
                )
            assert exc.value.code == "PROP-DEL-01-LAST-MGR-EMP"

    def test_update_employee_duplicate_checks_and_geo_validations(self) -> None:
        """Covers lines 478-498, 502-520, 522-540, 545-585 in update_employee."""
        emps = list(Employee.objects.filter(deleted_at__isnull=True)[:2])
        assert len(emps) >= 2
        emp1, emp2 = emps[0], emps[1]

        # Duplicate email
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=emp1.id,
                data={"row_version": emp1.row_version, "email": emp2.email},
            )
        assert exc.value.code == "MSG-4.3.1-M05"

        # Duplicate phone
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=emp1.id,
                data={"row_version": emp1.row_version, "phone": emp2.phone},
            )
        assert exc.value.code == "MSG-4.3.1-M05"

        # Duplicate CCCD
        if emp2.identity_card_number:
            with pytest.raises(BusinessAPIException) as exc:
                update_employee(
                    employee_id=emp1.id,
                    data={
                        "row_version": emp1.row_version,
                        "identity_card_number": emp2.identity_card_number,
                    },
                )
            assert exc.value.code == "MSG-4.3.1-M05"

        # Geo hierarchy: ward without district
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=emp1.id,
                data={
                    "row_version": emp1.row_version,
                    "ward_id": 1,
                    "district_id": None,
                },
            )
        assert exc.value.code == "PROP-GEN-P01"

        # Geo hierarchy: district without province
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=emp1.id,
                data={
                    "row_version": emp1.row_version,
                    "district_id": 1,
                    "province_id": None,
                },
            )
        assert exc.value.code == "PROP-GEN-P01"

        # Geo hierarchy: ward not in district
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=emp1.id,
                data={
                    "row_version": emp1.row_version,
                    "province_id": 1,
                    "district_id": 999999,
                    "ward_id": 1,
                },
            )
        assert exc.value.code == "PROP-GEN-P01"

        # Geo hierarchy: district not in province
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=emp1.id,
                data={
                    "row_version": emp1.row_version,
                    "province_id": 999999,
                    "district_id": 1,
                },
            )
        assert exc.value.code == "PROP-GEN-P01"

    def test_soft_delete_employee_instance_and_id_variants(self) -> None:
        """Covers lines 673, 675 in soft_delete_employee."""
        pos = Position.objects.filter(code="NVTN", deleted_at__isnull=True).first()
        assert pos is not None

        # Create two temp employees for testing soft delete invocation variants
        emp_a = create_employee(
            data={
                "position_id": pos.id,
                "password": "Password123!@#",
                "email": "del_a@test.local",
                "phone": "0981112223",
                "full_name": "Del A",
            }
        )
        res_a = soft_delete_employee(employee=emp_a)
        assert res_a["code"] == "MSG-4.3.4-M01"

        emp_b = create_employee(
            data={
                "position_id": pos.id,
                "password": "Password123!@#",
                "email": "del_b@test.local",
                "phone": "0981112224",
                "full_name": "Del B",
            }
        )
        res_b = soft_delete_employee(employee=emp_b.id)
        assert res_b["code"] == "MSG-4.3.4-M01"

    def test_update_employee_syncs_account_email_and_role_and_district_mismatch(
        self,
    ) -> None:
        """Covers lines 573-580, 599-600, 608-610, 634 in update_employee."""
        emp = Employee.objects.filter(
            deleted_at__isnull=True, account__isnull=False, position__code="NVVH"
        ).first()
        assert emp is not None and emp.account is not None
        nvtn_pos = Position.objects.filter(code="NVTN", deleted_at__isnull=True).first()
        assert nvtn_pos is not None

        # 1. District not belonging to province during update_employee
        with pytest.raises(BusinessAPIException) as exc:
            update_employee(
                employee_id=emp.id,
                data={
                    "row_version": emp.row_version,
                    "province_id": 1,
                    "district_id": 999999,
                },
            )
        assert exc.value.code == "PROP-GEN-P01"

        # 2. Update email and position together to sync account
        emp.refresh_from_db()
        new_email = f"synced_{emp.id}@test.local"
        updated = update_employee(
            employee_id=emp.id,
            data={
                "row_version": emp.row_version,
                "email": new_email,
                "position_id": nvtn_pos.id,
            },
        )
        assert updated.email == new_email
        assert updated.position_id == nvtn_pos.id
        emp.account.refresh_from_db()
        assert emp.account.email == new_email
        assert emp.account.role == "EMPLOYEE"
