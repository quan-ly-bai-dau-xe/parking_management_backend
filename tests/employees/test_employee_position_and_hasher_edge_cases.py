"""
Adversarial Edge Cases Test Suite for Employee Position Authorization and Password Hasher.
Covers SRS 4.3.1–4.3.4 (Milestone M1 & M2, Round 68).

Validates database-driven position authorization invariants, dynamic role derivation,
Argon2id password hasher production parameters, and zero plaintext leakage.

M1: Database-Driven Position Authorization:
- Test dynamic role mapping when position code is renamed at runtime in live PostgreSQL.
- Test high Position ID (>4) with code 'QL' deriving MANAGER role.
- Test rejection of soft-deleted and non-existent positions on create and update (HTTP 400 PROP-GEN-P01).
- Adversarial fuzzing of position_id: negative, zero, float, non-digit string, SQL injection string, huge int, null.

M2: Production Password Hasher Verification:
- Test Argon2id password hash generation under base_settings.PASSWORD_HASHERS (RFC 9106 format).
- Test extreme password diversity: 64-char length, special characters, Vietnamese Unicode.
- Exhaustive Zero Leakage Scan across all Employee and Account fields, and API response payloads.
- Test password update flow under base_settings.PASSWORD_HASHERS with Zero Leakage.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth.hashers import make_password
from django.db import connection
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.employees.models import Employee, Position
from config.settings import base as base_settings

pytestmark = pytest.mark.django_db


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def active_manager_account() -> Account:
    """Fixture ensuring an active MANAGER exists for authenticated requests."""
    acc, _ = Account.objects.get_or_create(
        email="challenger_manager@parking.local",
        defaults={
            "phone": "0901999888",
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
def manager_client(active_manager_account: Account) -> APIClient:
    """APIClient authenticated as an active MANAGER."""
    client = APIClient()
    client.force_authenticate(user=active_manager_account)
    return client


# ==============================================================================
# M1 ADVERSARIAL TESTS: DATABASE-DRIVEN POSITION AUTHORIZATION
# ==============================================================================


class TestM1DatabaseDrivenPositionAuthorizationAdversarial:
    """
    Adversarial challenge for Milestone M1:
    Verifies that authorization is strictly database-driven without in-memory caching or hardcoded IDs.
    """

    def test_m1_1_runtime_role_derivation_on_position_code_mutation(
        self, manager_client: APIClient
    ) -> None:
        """
        Adversarial test: Mutate position codes in PostgreSQL at runtime.
        1. Rename Position 1 ('QL') -> 'TEST_POS'
        2. Rename Position 2 ('NVVH') -> 'QL'
        Assert:
        - Employee created with Position 1 derives role 'EMPLOYEE' (NOT 'MANAGER').
        - Employee created with Position 2 derives role 'MANAGER' (NOT 'EMPLOYEE').
        - Updating an existing employee to Position 1 updates role to 'EMPLOYEE'.
        - Updating an existing employee to Position 2 updates role to 'MANAGER'.
        """
        pos1 = Position.objects.get(id=1)
        orig_code_1 = pos1.code
        pos2 = Position.objects.get(id=2)
        orig_code_2 = pos2.code

        try:
            # Step 1: Mutate Position 1 -> TEST_POS
            Position.objects.filter(id=1).update(code="TEST_POS")

            # Step 2: Mutate Position 2 -> QL
            Position.objects.filter(id=2).update(code="QL")

            # Verify CSDL state
            assert Position.objects.get(id=1).code == "TEST_POS"
            assert Position.objects.get(id=2).code == "QL"

            # Create employee with Position 1 (code TEST_POS)
            res1 = manager_client.post(
                "/api/v1/employees/",
                data={
                    "full_name": "Nhân viên Test Mutate Pos 1",
                    "email": "adv_m1_pos1@parking.local",
                    "phone": "0917001001",
                    "password": "Password123!@#",
                    "position_id": 1,
                },
                format="json",
            )
            assert res1.status_code == status.HTTP_201_CREATED, res1.content.decode()
            acc1 = Account.objects.get(id=res1.json()["account"]["id"])
            assert acc1.role == "EMPLOYEE", (
                f"Expected role 'EMPLOYEE' for position code 'TEST_POS', got '{acc1.role}'"
            )

            # Create employee with Position 2 (code QL)
            res2 = manager_client.post(
                "/api/v1/employees/",
                data={
                    "full_name": "Quản lý Test Mutate Pos 2",
                    "email": "adv_m1_pos2@parking.local",
                    "phone": "0917001002",
                    "password": "Password123!@#",
                    "position_id": 2,
                },
                format="json",
            )
            assert res2.status_code == status.HTTP_201_CREATED, res2.content.decode()
            acc2 = Account.objects.get(id=res2.json()["account"]["id"])
            assert acc2.role == "MANAGER", (
                f"Expected role 'MANAGER' for position code 'QL', got '{acc2.role}'"
            )

            # Update employee 1 to Position 2 -> Should promote to MANAGER
            emp1 = Employee.objects.get(account=acc1)
            res_up1 = manager_client.patch(
                f"/api/v1/employees/{emp1.id}/",
                data={
                    "row_version": emp1.row_version,
                    "position_id": 2,
                },
                format="json",
            )
            assert res_up1.status_code == status.HTTP_200_OK, res_up1.content.decode()
            acc1.refresh_from_db()
            assert acc1.role == "MANAGER", (
                f"Expected promoted role 'MANAGER', got '{acc1.role}'"
            )

            # Update employee 2 to Position 1 -> Should demote to EMPLOYEE
            emp2 = Employee.objects.get(account=acc2)
            res_up2 = manager_client.patch(
                f"/api/v1/employees/{emp2.id}/",
                data={
                    "row_version": emp2.row_version,
                    "position_id": 1,
                },
                format="json",
            )
            assert res_up2.status_code == status.HTTP_200_OK, res_up2.content.decode()
            acc2.refresh_from_db()
            assert acc2.role == "EMPLOYEE", (
                f"Expected demoted role 'EMPLOYEE', got '{acc2.role}'"
            )

        finally:
            # Restore original codes respecting uniqueness
            Position.objects.filter(id=2).update(code=orig_code_2)
            Position.objects.filter(id=1).update(code=orig_code_1)

            # Cleanup test records
            with connection.cursor() as cur:
                cur.execute("ALTER TABLE employee DISABLE TRIGGER ALL;")
                cur.execute(
                    "DELETE FROM employee WHERE email IN (%s, %s);",
                    ["adv_m1_pos1@parking.local", "adv_m1_pos2@parking.local"],
                )
                cur.execute("ALTER TABLE employee ENABLE TRIGGER ALL;")
                cur.execute("ALTER TABLE account DISABLE TRIGGER ALL;")
                cur.execute(
                    "DELETE FROM account WHERE email IN (%s, %s);",
                    ["adv_m1_pos1@parking.local", "adv_m1_pos2@parking.local"],
                )
                cur.execute("ALTER TABLE account ENABLE TRIGGER ALL;")

    def test_m1_2_high_position_ids_with_ql_derives_manager(
        self, manager_client: APIClient
    ) -> None:
        """
        Adversarial test: Create positions with high IDs (999, 5000) and code 'QL'.
        Proves that role derivation does NOT depend on ID <= 4 or ID == 1.
        """
        pos1 = Position.objects.get(id=1)
        orig_code_1 = pos1.code

        try:
            Position.objects.filter(id=1).update(code="QL_TEMP_HOLD")

            # Create high ID positions
            high_pos_999 = Position.objects.create(
                id=999, code="QL", name="Quản lý ID 999"
            )
            assert high_pos_999.id == 999

            res = manager_client.post(
                "/api/v1/employees/",
                data={
                    "full_name": "Quản lý ID Cao 999",
                    "email": "adv_m1_high999@parking.local",
                    "phone": "0917002001",
                    "password": "Password123!@#",
                    "position_id": high_pos_999.id,
                },
                format="json",
            )
            assert res.status_code == status.HTTP_201_CREATED, res.content.decode()
            acc = Account.objects.get(id=res.json()["account"]["id"])
            assert acc.role == "MANAGER", (
                f"Expected role 'MANAGER' for high position id 999 with code 'QL', got '{acc.role}'"
            )

            # Test update to another high position ID (5000)
            Position.objects.filter(id=999).update(code="QL_999_MUTATED")
            high_pos_5000 = Position.objects.create(
                id=5000, code="QL", name="Quản lý ID 5000"
            )

            emp = Employee.objects.get(account=acc)
            res_patch = manager_client.patch(
                f"/api/v1/employees/{emp.id}/",
                data={
                    "row_version": emp.row_version,
                    "position_id": high_pos_5000.id,
                },
                format="json",
            )
            assert res_patch.status_code == status.HTTP_200_OK, (
                res_patch.content.decode()
            )
            acc.refresh_from_db()
            assert acc.role == "MANAGER"

        finally:
            with connection.cursor() as cur:
                cur.execute("ALTER TABLE employee DISABLE TRIGGER ALL;")
                cur.execute(
                    "DELETE FROM employee WHERE email = %s;",
                    ["adv_m1_high999@parking.local"],
                )
                cur.execute("ALTER TABLE employee ENABLE TRIGGER ALL;")
                cur.execute("ALTER TABLE account DISABLE TRIGGER ALL;")
                cur.execute(
                    "DELETE FROM account WHERE email = %s;",
                    ["adv_m1_high999@parking.local"],
                )
                cur.execute("ALTER TABLE account ENABLE TRIGGER ALL;")
                cur.execute("ALTER TABLE position DISABLE TRIGGER ALL;")
                cur.execute("DELETE FROM position WHERE id IN (999, 5000);")
                cur.execute(
                    "UPDATE position SET code = %s WHERE id = 1;", [orig_code_1]
                )
                cur.execute("ALTER TABLE position ENABLE TRIGGER ALL;")

    def test_m1_3_soft_deleted_and_nonexistent_positions_rejected(
        self, manager_client: APIClient
    ) -> None:
        """
        Adversarial test: Explicitly try creating and updating employees with:
        - Soft-deleted position (deleted_at IS NOT NULL)
        - Non-existent position ID (e.g. 999999)
        Assert: Must be rejected with HTTP 400 Bad Request and code PROP-GEN-P01.
        """
        soft_pos = Position.objects.create(
            code="SOFT_DEL_TEST",
            name="Chức vụ Xóa Mềm Đối Kháng",
            deleted_at=timezone.now(),
        )

        existing_emp = Employee.objects.filter(deleted_at__isnull=True).first()
        assert existing_emp is not None

        # 1. Soft-deleted on create
        res_create_soft = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Test Soft Del Create",
                "email": "soft_del_create@parking.local",
                "phone": "0917003001",
                "password": "Password123!@#",
                "position_id": soft_pos.id,
            },
            format="json",
        )
        assert res_create_soft.status_code == status.HTTP_400_BAD_REQUEST
        assert res_create_soft.json()["code"] == "PROP-GEN-P01"

        # 2. Soft-deleted on update
        res_update_soft = manager_client.patch(
            f"/api/v1/employees/{existing_emp.id}/",
            data={
                "row_version": existing_emp.row_version,
                "position_id": soft_pos.id,
            },
            format="json",
        )
        assert res_update_soft.status_code == status.HTTP_400_BAD_REQUEST
        assert res_update_soft.json()["code"] == "PROP-GEN-P01"

        # 3. Non-existent ID on create
        res_create_nonexistent = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Test Nonexistent Create",
                "email": "nonexistent_create@parking.local",
                "phone": "0917003002",
                "password": "Password123!@#",
                "position_id": 999999,
            },
            format="json",
        )
        assert res_create_nonexistent.status_code == status.HTTP_400_BAD_REQUEST
        assert res_create_nonexistent.json()["code"] == "PROP-GEN-P01"

        # 4. Non-existent ID on update
        res_update_nonexistent = manager_client.patch(
            f"/api/v1/employees/{existing_emp.id}/",
            data={
                "row_version": existing_emp.row_version,
                "position_id": 999999,
            },
            format="json",
        )
        assert res_update_nonexistent.status_code == status.HTTP_400_BAD_REQUEST
        assert res_update_nonexistent.json()["code"] == "PROP-GEN-P01"

    @pytest.mark.parametrize(
        "anomalous_id",
        [
            -1,
            0,
            -9999,
            1.5,
            "abc",
            "1; DROP TABLE position;",
            "   ",
            999999999999999999999999999999999999999,
            None,
        ],
    )
    def test_m1_4_anomalous_position_id_fuzzing(
        self, manager_client: APIClient, anomalous_id: Any
    ) -> None:
        """
        Adversarial fuzzing on position_id:
        Negative, zero, float, non-digit string, SQL injection string, huge int, None.
        Assert: Always rejected cleanly with HTTP 400 Bad Request; NO HTTP 500 or DB crash.
        """
        existing_emp = Employee.objects.filter(deleted_at__isnull=True).first()
        assert existing_emp is not None

        # Test on create
        payload_create = {
            "full_name": "Fuzzing Position ID",
            "email": "fuzz_pos@parking.local",
            "phone": "0917004001",
            "password": "Password123!@#",
            "position_id": anomalous_id,
        }
        res_create = manager_client.post(
            "/api/v1/employees/", data=payload_create, format="json"
        )
        assert res_create.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Expected HTTP 400 for create with position_id={anomalous_id!r}, got {res_create.status_code}: {res_create.content.decode()}"
        )

        # Test on update
        payload_update = {
            "row_version": existing_emp.row_version,
            "position_id": anomalous_id,
        }
        res_update = manager_client.patch(
            f"/api/v1/employees/{existing_emp.id}/",
            data=payload_update,
            format="json",
        )
        assert res_update.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Expected HTTP 400 for update with position_id={anomalous_id!r}, got {res_update.status_code}: {res_update.content.decode()}"
        )


# ==============================================================================
# M2 ADVERSARIAL TESTS: PRODUCTION PASSWORD HASHER VERIFICATION
# ==============================================================================


class TestM2ProductionPasswordHasherAdversarial:
    """
    Adversarial challenge for Milestone M2:
    Verifies that under base_settings.PASSWORD_HASHERS:
    - Argon2id RFC 9106 format is strictly used for all employee password creations/updates.
    - Password diversity (64 chars, special chars, Vietnamese Unicode) is properly hashed and validated.
    - Zero plaintext password leakage across all DB columns, objects, and API response payloads.
    """

    @override_settings(PASSWORD_HASHERS=base_settings.PASSWORD_HASHERS)
    def test_m2_1_argon2id_format_and_verification(
        self, manager_client: APIClient
    ) -> None:
        """
        Adversarial test: Verify standard RFC 9106 Argon2id hash structure.
        Django Argon2 format: argon2$argon2id$v=19$m=102400,t=2,p=8$...
        """
        assert (
            base_settings.PASSWORD_HASHERS[0]
            == "django.contrib.auth.hashers.Argon2PasswordHasher"
        )

        raw_pwd = "P@ssw0rd_RFC9106_Argon2id_Verified!"
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None

        res = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Nguyễn Văn Argon2 RFC",
                "email": "argon2_rfc_test@parking.local",
                "phone": "0917005001",
                "password": raw_pwd,
                "position_id": pos.id,
            },
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED, res.content.decode()

        acc_id = res.json()["account"]["id"]
        account = Account.objects.get(id=acc_id)

        # RFC 9106 structure inspection
        pwd_hash = account.password
        assert pwd_hash.startswith("argon2$argon2id$v=19$m=102400,t=2,p=8$"), (
            f"Password hash does not match expected RFC 9106 Argon2id params: {pwd_hash[:45]}"
        )

        # Successful password check
        assert account.check_password(raw_pwd) is True
        # Negative password check
        assert account.check_password(raw_pwd + "_wrong") is False
        assert account.check_password("TotallyWrongPassword123!") is False

    @override_settings(PASSWORD_HASHERS=base_settings.PASSWORD_HASHERS)
    def test_m2_2a_excessive_length_64_chars_rejected_by_api_password_policy(
        self, manager_client: APIClient
    ) -> None:
        """
        Adversarial test: Attempting to submit a 64-character password via API.
        Per SRS Rule 07 / 4.3.3, password length is strictly bounded to [8, 50].
        Assert: Rejected cleanly with HTTP 400 Bad Request (PROP-GEN-P01).
        """
        pos = Position.objects.filter(code="NVTN", deleted_at__isnull=True).first()
        assert pos is not None

        pwd_64 = (
            "A1@b2#C3$d4%E5^F6&g7*H8(i9)J0_k1-L2+M3=N4{o5}P6[q7]R8:s9;T0'u1,V2.w3?X4"[
                :64
            ]
        )
        assert len(pwd_64) == 64

        res = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Test Excessive Length Password 64",
                "email": "adv_pwd_64_excessive@parking.local",
                "phone": "0917006064",
                "password": pwd_64,
                "position_id": pos.id,
            },
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        res_data = res.json()
        assert res_data["code"] == "PROP-GEN-P01"
        assert "password" in res_data.get("details", {})

    @override_settings(PASSWORD_HASHERS=base_settings.PASSWORD_HASHERS)
    @pytest.mark.parametrize(
        "test_password,case_name",
        [
            (
                "P@ssw0rd_50Chars_Max_Boundary_Key_Complex_Valid_01",  # Exactly 50 chars
                "max_valid_length_50_chars",
            ),
            (
                "P@ss!#$%&*+-=?^_`{|}~1A",
                "extreme_special_symbols",
            ),
            (
                "MậtKhẩu@BảoMật#ĐỗThànhCông_TiếngViệt2026!",
                "vietnamese_unicode_accented",
            ),
            (
                "Aa1!Aa1!Aa1!Aa1!Aa1!Aa1!Aa1!Aa1!",
                "repetitive_complex_pattern",
            ),
        ],
    )
    def test_m2_2b_password_diversity_stress_under_argon2(
        self,
        manager_client: APIClient,
        test_password: str,
        case_name: str,
    ) -> None:
        """
        Adversarial test: Test extreme password diversity under Argon2 through API:
        - 50-character boundary password (valid max length per Rule 07)
        - Extreme special characters
        - Accented Vietnamese Unicode characters
        - Repetitive complex pattern
        Assert:
        - Created successfully (HTTP 201)
        - Hashed with Argon2id ('argon2$' prefix)
        - Authenticates correctly with check_password
        - Raw password never matches hash string
        """
        pos = Position.objects.filter(code="NVTN", deleted_at__isnull=True).first()
        assert pos is not None

        email = f"adv_pwd_{case_name}@parking.local"
        res = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": f"Test Diversity {case_name}",
                "email": email,
                "phone": "091700600" + str(len(case_name))[:1],
                "password": test_password,
                "position_id": pos.id,
            },
            format="json",
        )
        assert res.status_code == status.HTTP_201_CREATED, (
            f"Failed on case {case_name}: {res.content.decode()}"
        )

        acc = Account.objects.get(email=email)
        assert acc.password.startswith("argon2$")
        assert acc.password != test_password
        assert test_password not in acc.password
        assert acc.check_password(test_password) is True

    @override_settings(PASSWORD_HASHERS=base_settings.PASSWORD_HASHERS)
    def test_m2_2c_argon2_engine_handles_64_and_128_chars_without_truncation(
        self,
    ) -> None:
        """
        Adversarial test: Verify Argon2id engine handles 64-char and 128-char passwords.
        Unlike bcrypt which truncates passwords at 72 bytes, Argon2id handles arbitrary length.
        """
        from django.contrib.auth.hashers import check_password, make_password

        pwd_64 = (
            "A1@b2#C3$d4%E5^F6&g7*H8(i9)J0_k1-L2+M3=N4{o5}P6[q7]R8:s9;T0'u1,V2.w3?X4"[
                :64
            ]
        )
        pwd_128 = pwd_64 + pwd_64

        assert len(pwd_64) == 64
        assert len(pwd_128) == 128

        hash_64 = make_password(pwd_64)
        hash_128 = make_password(pwd_128)

        assert hash_64.startswith("argon2$argon2id$")
        assert hash_128.startswith("argon2$argon2id$")
        assert check_password(pwd_64, hash_64) is True
        assert check_password(pwd_64 + "X", hash_64) is False
        assert check_password(pwd_128, hash_128) is True
        assert check_password(pwd_128 + "X", hash_128) is False

    @override_settings(PASSWORD_HASHERS=base_settings.PASSWORD_HASHERS)
    def test_m2_3_exhaustive_zero_plaintext_leakage_scan(
        self, manager_client: APIClient
    ) -> None:
        """
        Adversarial test: Exhaustive Zero Plaintext Leakage Scan.
        Verifies:
        1. On employee creation:
           - Scan all DB columns in Employee and Account
           - Scan HTTP response body JSON and raw response content
           - Assert raw password is never found anywhere.
        2. On employee password update (PATCH):
           - Update password to a new secret under base_settings.PASSWORD_HASHERS
           - Assert new password is hashed with Argon2id
           - Scan all DB columns and HTTP response to verify zero leakage.
        """
        secret_create_pwd = "Create_Secret_P@ssw0rd_2026_ZeroLeak!"
        pos = Position.objects.filter(code="KTV", deleted_at__isnull=True).first()
        assert pos is not None

        # 1. Test creation flow
        res_create = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Nguyễn Zero Leakage",
                "email": "zero_leak_scan@parking.local",
                "phone": "0917007001",
                "password": secret_create_pwd,
                "position_id": pos.id,
            },
            format="json",
        )
        assert res_create.status_code == status.HTTP_201_CREATED

        acc_id = res_create.json()["account"]["id"]
        account = Account.objects.get(id=acc_id)
        employee = Employee.objects.get(account=account)

        # Scan all Employee attributes
        for field in Employee._meta.get_fields():
            if hasattr(employee, field.name):
                val = getattr(employee, field.name)
                assert secret_create_pwd not in str(val), (
                    f"Raw create password leaked in Employee.{field.name} = {val!r}"
                )

        # Scan all Account attributes
        for field in Account._meta.get_fields():
            if hasattr(account, field.name):
                val = getattr(account, field.name)
                assert secret_create_pwd not in str(val), (
                    f"Raw create password leaked in Account.{field.name} = {val!r}"
                )

        # Scan API response
        res_json = res_create.json()
        assert "password" not in res_json
        assert "password" not in res_json.get("account", {})
        assert secret_create_pwd not in res_create.content.decode("utf-8")

        # 2. Test password update flow via PATCH
        secret_update_pwd = "Update_Secret_P@ssw0rd_2026_Argon2New!"
        res_update = manager_client.patch(
            f"/api/v1/employees/{employee.id}/",
            data={
                "row_version": employee.row_version,
                "password": secret_update_pwd,
            },
            format="json",
        )
        assert res_update.status_code == status.HTTP_200_OK, res_update.content.decode()

        account.refresh_from_db()
        employee.refresh_from_db()

        # Assert new password hashed with Argon2
        assert account.password.startswith("argon2$"), (
            f"Updated password not hashed with Argon2: {account.password[:25]}"
        )
        assert account.check_password(secret_update_pwd) is True
        assert account.check_password(secret_create_pwd) is False

        # Scan DB attributes after update
        for field in Employee._meta.get_fields():
            if hasattr(employee, field.name):
                val = getattr(employee, field.name)
                assert secret_update_pwd not in str(val), (
                    f"Raw update password leaked in Employee.{field.name}"
                )

        for field in Account._meta.get_fields():
            if hasattr(account, field.name):
                val = getattr(account, field.name)
                assert secret_update_pwd not in str(val), (
                    f"Raw update password leaked in Account.{field.name}"
                )

        # Scan API update response
        up_json = res_update.json()
        assert "password" not in up_json
        assert "password" not in up_json.get("account", {})
        assert secret_update_pwd not in res_update.content.decode("utf-8")
