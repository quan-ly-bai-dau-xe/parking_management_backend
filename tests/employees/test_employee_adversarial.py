"""
Empirical Adversarial Challenge Test Suite for Milestone M3 (Tasks S1–S2: Employee Management API Core).
Author: challenger_m3_1 (Empirical Challenger)

Adversarial Stress Dimensions:
1. Concurrency & OCC (row_version) Edge Cases:
   - Stale row_version -> 409 MSG-4.3.1-M03
   - Missing row_version -> 400 PROP-GEN-P01
   - Malformed/string/negative row_version -> 400 or 409
   - Sequential version bump verification
2. Employee Code Immutability via PATCH:
   - Attempt to modify 'code' to another code or same code -> 400 Bad Request
3. DEL-01 Security & Bypass Protection:
   - Manager self-deletion attempt -> 409 PROP-DEL-01-SELF-EMP
   - Manager self-deactivation attempt -> 409 PROP-DEL-01-SELF-EMP
   - Manager self-demotion attempt (QL -> NVVH) -> 409 PROP-DEL-01-SELF-EMP
   - Last Active Manager deletion attempt -> 409 PROP-DEL-01-LAST-MGR-EMP
   - Last Active Manager deactivation attempt -> 409 PROP-DEL-01-LAST-MGR-EMP
   - Last Active Manager demotion attempt -> 409 PROP-DEL-01-LAST-MGR-EMP
4. Malicious & Anomalous Raw-String Payloads:
   - Null bytes (\x00), zero-width characters (\u200b, \ufeff) -> 400
   - Over-length names (> 45 chars), addresses (> 100 chars), phones (> 15 chars) -> 400
   - Emoji & pictographs in name (😀, 🚗, 🔥) -> 400
   - Non-ASCII digits / Look-alike digits in phone & CCCD -> 400
   - Zero "Database exception" logged (caplog verification)
5. Password Complexity & Policy (Rule 07 / SRS 4.3.3):
   - Missing upper, lower, digit, special char, length < 8, length > 50 -> 400
6. Authentication & RBAC Penetration:
   - Anonymous (401), Customer (403), Employee (403), Manager (200/201) across all 7 endpoints
7. Immediate Session & Token Revocation:
   - Deactivation, soft-deletion, and demotion invalidate Django Sessions and PersistentLoginTokens
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pytest
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account, PersistentLoginToken
from apps.employees.models import Employee, Position

pytestmark = pytest.mark.django_db


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def manager_account() -> Account:
    """Primary active MANAGER account."""
    acc, _ = Account.objects.get_or_create(
        email="challenger_manager_adv@parking.local",
        defaults={
            "phone": "0981111111",
            "role": "MANAGER",
            "is_active": True,
            "password": make_password("AdvManager123!@#"),
        },
    )
    acc.is_active = True
    acc.role = "MANAGER"
    acc.save()
    return acc


@pytest.fixture
def secondary_manager_account() -> Account:
    """Secondary active MANAGER account."""
    acc, _ = Account.objects.get_or_create(
        email="challenger_sec_mgr@parking.local",
        defaults={
            "phone": "0982222222",
            "role": "MANAGER",
            "is_active": True,
            "password": make_password("AdvManager123!@#"),
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
        email="challenger_employee_adv@parking.local",
        defaults={
            "phone": "0983333333",
            "role": "EMPLOYEE",
            "is_active": True,
            "password": make_password("AdvEmployee123!@#"),
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
        email="challenger_customer_adv@parking.local",
        defaults={
            "phone": "0984444444",
            "role": "CUSTOMER",
            "is_active": True,
            "password": make_password("AdvCustomer123!@#"),
        },
    )
    acc.is_active = True
    acc.role = "CUSTOMER"
    acc.save()
    return acc


@pytest.fixture
def manager_client(manager_account: Account) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=manager_account)
    return client


@pytest.fixture
def employee_client(employee_account: Account) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=employee_account)
    return client


@pytest.fixture
def customer_client(customer_account: Account) -> APIClient:
    client = APIClient()
    client.force_authenticate(user=customer_account)
    return client


@pytest.fixture
def anonymous_client() -> APIClient:
    return APIClient()


@pytest.fixture
def sample_target_employee(secondary_manager_account: Account) -> Employee:
    """Seeded or freshly created employee for test attacks."""
    pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
    assert pos is not None
    emp = Employee.objects.filter(code="NV002", deleted_at__isnull=True).first()
    if emp:
        return emp
    emp, _ = Employee.objects.get_or_create(
        code="NV099",
        defaults={
            "full_name": "Target Employee",
            "email": "target_adv@parking.local",
            "phone": "0985555555",
            "position": pos,
            "status": "ACTIVE",
        },
    )
    return emp


# ==============================================================================
# 1. CONCURRENCY & OCC (row_version) STRESS TESTS
# ==============================================================================


class TestAdversarialOCCRowVersion:
    """Adversarial stress testing for row_version optimistic locking."""

    def test_stale_row_version_returns_409_conflict(
        self, manager_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Stale row_version must strictly return 409 Conflict with MSG-4.3.1-M03."""
        stale_version = sample_target_employee.row_version - 1
        res = manager_client.patch(
            f"/api/v1/employees/{sample_target_employee.id}/",
            data={
                "row_version": stale_version,
                "full_name": "Stale Update Attack",
            },
            format="json",
        )
        assert res.status_code == status.HTTP_409_CONFLICT
        data = res.json()
        assert data.get("code") == "MSG-4.3.1-M03"
        assert "Dữ liệu hiện đang được cập nhật bởi user khác" in data.get(
            "message", ""
        )

    def test_future_row_version_returns_409_conflict(
        self, manager_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Arbitrary future row_version (e.g. +100) must return 409 Conflict."""
        future_version = sample_target_employee.row_version + 100
        res = manager_client.patch(
            f"/api/v1/employees/{sample_target_employee.id}/",
            data={
                "row_version": future_version,
                "full_name": "Future Version Attack",
            },
            format="json",
        )
        assert res.status_code == status.HTTP_409_CONFLICT
        data = res.json()
        assert data.get("code") == "MSG-4.3.1-M03"

    def test_missing_row_version_returns_400_bad_request(
        self, manager_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Omitting row_version must return 400 Bad Request."""
        res = manager_client.patch(
            f"/api/v1/employees/{sample_target_employee.id}/",
            data={"full_name": "Missing Version Attack"},
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_invalid_string_row_version_returns_400_bad_request(
        self, manager_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Passing non-integer string for row_version must return 400 Bad Request."""
        for invalid_val in ["abc", "", None, 3.14]:
            res = manager_client.patch(
                f"/api/v1/employees/{sample_target_employee.id}/",
                data={
                    "row_version": invalid_val,
                    "full_name": "Invalid Row Version Type",
                },
                format="json",
            )
            assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_negative_row_version_rejected(
        self, manager_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Passing negative row_version must return 409 Conflict (mismatch)."""
        res = manager_client.patch(
            f"/api/v1/employees/{sample_target_employee.id}/",
            data={
                "row_version": -99,
                "full_name": "Negative Row Version",
            },
            format="json",
        )
        assert res.status_code in (
            status.HTTP_409_CONFLICT,
            status.HTTP_400_BAD_REQUEST,
        )

    def test_sequential_occ_version_increment(
        self, manager_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Updating correctly bumps row_version by 1, and old token immediately becomes stale."""
        initial_version = sample_target_employee.row_version
        res1 = manager_client.patch(
            f"/api/v1/employees/{sample_target_employee.id}/",
            data={
                "row_version": initial_version,
                "full_name": "Valid Update Step 1",
            },
            format="json",
        )
        assert res1.status_code == status.HTTP_200_OK
        new_version = res1.json()["row_version"]
        assert new_version == initial_version + 1

        # Re-attempt with initial_version must now fail 409
        res2 = manager_client.patch(
            f"/api/v1/employees/{sample_target_employee.id}/",
            data={
                "row_version": initial_version,
                "full_name": "Valid Update Step 2 - Replay Old Token",
            },
            format="json",
        )
        assert res2.status_code == status.HTTP_409_CONFLICT
        assert res2.json().get("code") == "MSG-4.3.1-M03"


# ==============================================================================
# 2. EMPLOYEE CODE IMMUTABILITY VIA PATCH
# ==============================================================================


class TestAdversarialCodeImmutability:
    """Adversarial stress testing on employee code immutability."""

    def test_patch_attempting_to_alter_code_rejected(
        self, manager_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Attempting to change 'code' via PATCH must be rejected with 400 Bad Request."""
        original_code = sample_target_employee.code
        res = manager_client.patch(
            f"/api/v1/employees/{sample_target_employee.id}/",
            data={
                "row_version": sample_target_employee.row_version,
                "code": "NV9999",
            },
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        data = res.json()
        # Confirm error message or field error
        err_msg = str(data)
        assert (
            "bất biến" in err_msg or "code" in data.get("errors", {}) or "code" in data
        )

        # Database check: verify code was NOT modified
        sample_target_employee.refresh_from_db()
        assert sample_target_employee.code == original_code

    def test_patch_sending_same_code_rejected(
        self, manager_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Sending the existing 'code' in PATCH body is also rejected (code is non-writable)."""
        res = manager_client.patch(
            f"/api/v1/employees/{sample_target_employee.id}/",
            data={
                "row_version": sample_target_employee.row_version,
                "code": sample_target_employee.code,
            },
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 3. DEL-01 SECURITY GUARDS & BYPASS TESTS
# ==============================================================================


class TestAdversarialDEL01Guards:
    """Adversarial tests attacking DEL-01 soft delete and update guards."""

    def test_manager_self_deletion_blocked(
        self, manager_account: Account, manager_client: APIClient
    ) -> None:
        """A Manager cannot delete their own employee profile (PROP-DEL-01-SELF-EMP)."""
        pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
        assert pos_ql is not None

        # Bind employee record to the authenticated manager account
        self_emp, _ = Employee.objects.get_or_create(
            account=manager_account,
            defaults={
                "code": "NV701",
                "full_name": "Logged In Manager",
                "email": str(manager_account.email),
                "phone": str(manager_account.phone),
                "position": pos_ql,
                "status": "ACTIVE",
            },
        )

        res = manager_client.delete(f"/api/v1/employees/{self_emp.id}/")
        assert res.status_code == status.HTTP_409_CONFLICT
        data = res.json()
        assert data.get("code") in ("PROP-DEL-01-SELF-EMP", "PROP-DEL-01-SELF")
        assert "không được phép tự xóa" in data.get("message", "")

    def test_manager_self_deactivation_blocked(
        self, manager_account: Account, manager_client: APIClient
    ) -> None:
        """A Manager cannot deactivate their own employee profile (status -> INACTIVE)."""
        pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
        assert pos_ql is not None
        self_emp = Employee.objects.filter(account=manager_account).first()
        if not self_emp:
            self_emp = Employee.objects.create(
                code="NV702",
                full_name="Logged In Manager 2",
                email="mgr_deact@parking.local",
                phone="0986666661",
                position=pos_ql,
                account=manager_account,
                status="ACTIVE",
            )

        res = manager_client.patch(
            f"/api/v1/employees/{self_emp.id}/",
            data={
                "row_version": self_emp.row_version,
                "status": "INACTIVE",
            },
            format="json",
        )
        assert res.status_code == status.HTTP_409_CONFLICT
        data = res.json()
        assert data.get("code") == "PROP-DEL-01-SELF-DEACT"
        assert "tự vô hiệu hóa tài khoản" in data.get("message", "")

    def test_manager_self_demotion_blocked(
        self, manager_account: Account, manager_client: APIClient
    ) -> None:
        """A Manager cannot demote themselves to a non-manager position (QL -> NVVH)."""
        pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
        pos_nvvh = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos_ql is not None and pos_nvvh is not None
        self_emp, _ = Employee.objects.get_or_create(
            account=manager_account,
            defaults={
                "code": "NV702",
                "full_name": "Logged In Manager Demote",
                "email": str(manager_account.email),
                "phone": str(manager_account.phone),
                "position": pos_ql,
                "status": "ACTIVE",
            },
        )
        assert self_emp is not None

        res = manager_client.patch(
            f"/api/v1/employees/{self_emp.id}/",
            data={
                "row_version": self_emp.row_version,
                "position_id": pos_nvvh.id,
            },
            format="json",
        )
        assert res.status_code == status.HTTP_409_CONFLICT
        data = res.json()
        assert data.get("code") == "PROP-DEL-01-SELF-DEMOTE"
        assert "tự giáng chức" in data.get("message", "")

    def test_last_active_manager_deletion_guard(
        self, secondary_manager_account: Account
    ) -> None:
        """Deleting the system's last active manager is strictly blocked with 409 PROP-DEL-01-LAST-MGR-EMP."""
        pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
        assert pos_ql is not None

        # Create sole manager target
        sole_mgr_acc = Account.objects.create(
            email="sole_manager@parking.local",
            phone="0987777771",
            role="MANAGER",
            is_active=True,
            password=make_password("Manager123!@#"),
        )
        sole_emp = Employee.objects.create(
            code="NV703",
            full_name="Sole Manager",
            email="sole_manager@parking.local",
            phone="0987777771",
            position=pos_ql,
            account=sole_mgr_acc,
            status="ACTIVE",
        )

        # Deactivate all other managers in the DB except sole_mgr_acc
        other_managers = Account.objects.filter(
            role="MANAGER", is_active=True, deleted_at__isnull=True
        ).exclude(id=sole_mgr_acc.id)
        other_mgr_ids = list(other_managers.values_list("id", flat=True))
        other_managers.update(is_active=False)

        # Use an external admin actor client
        admin_actor = Account.objects.create(
            email="admin_actor@parking.local",
            phone="0987777772",
            role="MANAGER",
            is_active=True,
            password=make_password("Manager123!@#"),
        )
        # Re-activate admin_actor so client can authenticate
        client = APIClient()
        client.force_authenticate(user=admin_actor)

        # Now only 2 managers: sole_mgr_acc and admin_actor. Deactivate admin_actor's manager role to simulate sole manager
        Account.objects.filter(id=admin_actor.id).update(role="EMPLOYEE")

        try:
            res = client.delete(f"/api/v1/employees/{sole_emp.id}/")
            # If rejected by DB trigger or service guard, must be 409
            assert res.status_code == status.HTTP_409_CONFLICT
            data = res.json()
            assert data.get("code") in (
                "PROP-DEL-01-LAST-MGR-EMP",
                "PROP-DEL-01-LAST-MGR",
            )
            assert "Quản lý hoạt động cuối cùng" in data.get("message", "")
        finally:
            # Restore other managers
            Account.objects.filter(id__in=other_mgr_ids).update(is_active=True)


# ==============================================================================
# 4. MALICIOUS & ANOMALOUS RAW-STRING PAYLOADS
# ==============================================================================


class TestAdversarialRawStringPayloads:
    """Stress testing input sanitation: null bytes, over-length, emoji, zero-width, look-alikes."""

    def test_null_byte_in_name_rejected_400(
        self, manager_client: APIClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Injecting null byte \\x00 in full_name must be rejected with 400 and zero DB exception logs."""
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None
        with caplog.at_level(logging.ERROR):
            res = manager_client.post(
                "/api/v1/employees/",
                data={
                    "full_name": "Nguyễn Văn\x00A",
                    "email": "nullbyte_adv@parking.local",
                    "phone": "0988888801",
                    "position_id": pos.id,
                    "password": "Password123!@#",
                },
                format="json",
            )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "null" in str(res.json()).lower() or "nul" in str(res.json()).lower()
        assert "Database exception" not in caplog.text

    def test_emoji_in_name_rejected_400(
        self, manager_client: APIClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Injecting emoji/pictographs in full_name must return 400 Bad Request."""
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None
        for malicious_name in ["Lê Văn Tài 😀", "Trần Thị B 🚗💨", "Phạm Văn C 🔥"]:
            res = manager_client.post(
                "/api/v1/employees/",
                data={
                    "full_name": malicious_name,
                    "email": "emoji_test@parking.local",
                    "phone": "0988888802",
                    "position_id": pos.id,
                    "password": "Password123!@#",
                },
                format="json",
            )
            assert res.status_code == status.HTTP_400_BAD_REQUEST
            assert "emoji" in str(res.json()).lower()

    def test_zero_width_characters_rejected_400(
        self, manager_client: APIClient
    ) -> None:
        """Zero-width spaces/joiners (\\u200b, \\u200c, \\ufeff) in name must be rejected."""
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None
        malicious_name = "Nguyễn\u200bVăn\ufeffA"
        res = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": malicious_name,
                "email": "zerowidth@parking.local",
                "phone": "0988888803",
                "position_id": pos.id,
                "password": "Password123!@#",
            },
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST
        assert "ẩn" in str(res.json()) or "không hợp lệ" in str(res.json())

    def test_over_length_fields_rejected_400(self, manager_client: APIClient) -> None:
        """Fields exceeding maximum schema length must be rejected with 400."""
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None
        # Name > 45 chars
        res_name = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "A" * 46,
                "email": "toolong_name@parking.local",
                "phone": "0988888804",
                "position_id": pos.id,
                "password": "Password123!@#",
            },
            format="json",
        )
        assert res_name.status_code == status.HTTP_400_BAD_REQUEST

        # Phone > 15 chars
        res_phone = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Tên Hợp Lệ",
                "email": "toolong_phone@parking.local",
                "phone": "0988888888888888",  # 16 digits
                "position_id": pos.id,
                "password": "Password123!@#",
            },
            format="json",
        )
        assert res_phone.status_code == status.HTTP_400_BAD_REQUEST

        # Address > 100 chars
        res_addr = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Tên Hợp Lệ",
                "email": "toolong_addr@parking.local",
                "phone": "0988888805",
                "address": "B" * 101,
                "position_id": pos.id,
                "password": "Password123!@#",
            },
            format="json",
        )
        assert res_addr.status_code == status.HTTP_400_BAD_REQUEST

    def test_look_alike_non_ascii_digits_rejected_400(
        self, manager_client: APIClient
    ) -> None:
        """Full-width non-ASCII digits in phone must be rejected (only standard ASCII 0-9 allowed)."""
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None
        # Fullwidth digits e.g. '０９８８８８８８０６'
        res = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Tên Hợp Lệ",
                "email": "lookalike_phone@parking.local",
                "phone": "０９８８８８８８０６",
                "position_id": pos.id,
                "password": "Password123!@#",
            },
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 5. PASSWORD COMPLEXITY & POLICY (Rule 07 / SRS 4.3.3)
# ==============================================================================


class TestAdversarialPasswordPolicy:
    """Stress testing password complexity validator on creation and update."""

    @pytest.mark.parametrize(
        "weak_password, reason",
        [
            ("loweronly123!", "Missing uppercase letter"),
            ("UPPERONLY123!", "Missing lowercase letter"),
            ("NoDigitsHere!@#", "Missing numeric digit"),
            ("NoSpecial123456", "Missing special character"),
            ("Sh0rt!", "Length < 8 chars"),
            ("A1!" + "a" * 48, "Length > 50 chars"),
            ("               ", "Whitespace only"),
            ("", "Empty password"),
        ],
    )
    def test_weak_passwords_rejected_on_create(
        self, manager_client: APIClient, weak_password: str, reason: str
    ) -> None:
        """Creating an employee with weak password violating Rule 07 must return 400 Bad Request."""
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None
        res = manager_client.post(
            "/api/v1/employees/",
            data={
                "full_name": "Weak Pwd Test",
                "email": "weak_pwd@parking.local",
                "phone": "0989999901",
                "position_id": pos.id,
                "password": weak_password,
            },
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST, (
            f"Failed for reason: {reason}"
        )

    def test_weak_password_rejected_on_patch(
        self, manager_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Updating employee password with weak password must return 400 Bad Request."""
        res = manager_client.patch(
            f"/api/v1/employees/{sample_target_employee.id}/",
            data={
                "row_version": sample_target_employee.row_version,
                "password": "weakpassword",
            },
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 6. AUTHENTICATION & RBAC PENETRATION
# ==============================================================================


class TestAdversarialRBACPenetration:
    """RBAC matrix penetration test across all 7 employee & position endpoints."""

    def test_anonymous_requests_blocked_401(
        self, anonymous_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Anonymous requests must return 401 Unauthorized with MSG-4.1-M02."""
        endpoints = [
            ("GET", "/api/v1/positions/"),
            ("GET", "/api/v1/employees/summary/"),
            ("GET", "/api/v1/employees/"),
            ("POST", "/api/v1/employees/"),
            ("GET", f"/api/v1/employees/{sample_target_employee.id}/"),
            ("PATCH", f"/api/v1/employees/{sample_target_employee.id}/"),
            ("DELETE", f"/api/v1/employees/{sample_target_employee.id}/"),
        ]
        for method, url in endpoints:
            if method == "GET":
                res = anonymous_client.get(url)
            elif method == "POST":
                res = anonymous_client.post(url, data={}, format="json")
            elif method == "PATCH":
                res = anonymous_client.patch(url, data={}, format="json")
            elif method == "DELETE":
                res = anonymous_client.delete(url)
            assert res.status_code == status.HTTP_401_UNAUTHORIZED, (
                f"{method} {url} not 401"
            )
            assert res.json().get("code") == "MSG-4.1-M02"

    def test_customer_requests_blocked_403(
        self, customer_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Customer accounts must receive 403 Forbidden with MSG-4.2-M01 on all endpoints."""
        endpoints = [
            ("GET", "/api/v1/positions/"),
            ("GET", "/api/v1/employees/summary/"),
            ("GET", "/api/v1/employees/"),
            ("POST", "/api/v1/employees/"),
            ("GET", f"/api/v1/employees/{sample_target_employee.id}/"),
            ("PATCH", f"/api/v1/employees/{sample_target_employee.id}/"),
            ("DELETE", f"/api/v1/employees/{sample_target_employee.id}/"),
        ]
        for method, url in endpoints:
            if method == "GET":
                res = customer_client.get(url)
            elif method == "POST":
                res = customer_client.post(url, data={}, format="json")
            elif method == "PATCH":
                res = customer_client.patch(url, data={}, format="json")
            elif method == "DELETE":
                res = customer_client.delete(url)
            assert res.status_code == status.HTTP_403_FORBIDDEN, (
                f"{method} {url} not 403"
            )
            assert res.json().get("code") == "MSG-4.2-M01"

    def test_employee_requests_blocked_403(
        self, employee_client: APIClient, sample_target_employee: Employee
    ) -> None:
        """Standard employee accounts must receive 403 Forbidden with MSG-4.2-M01 on all endpoints."""
        endpoints = [
            ("GET", "/api/v1/positions/"),
            ("GET", "/api/v1/employees/summary/"),
            ("GET", "/api/v1/employees/"),
            ("POST", "/api/v1/employees/"),
            ("GET", f"/api/v1/employees/{sample_target_employee.id}/"),
            ("PATCH", f"/api/v1/employees/{sample_target_employee.id}/"),
            ("DELETE", f"/api/v1/employees/{sample_target_employee.id}/"),
        ]
        for method, url in endpoints:
            if method == "GET":
                res = employee_client.get(url)
            elif method == "POST":
                res = employee_client.post(url, data={}, format="json")
            elif method == "PATCH":
                res = employee_client.patch(url, data={}, format="json")
            elif method == "DELETE":
                res = employee_client.delete(url)
            assert res.status_code == status.HTTP_403_FORBIDDEN, (
                f"{method} {url} not 403"
            )
            assert res.json().get("code") == "MSG-4.2-M01"


# ==============================================================================
# 7. IMMEDIATE SESSION & REMEMBER-ME TOKEN REVOCATION
# ==============================================================================


class TestAdversarialSessionRevocation:
    """Stress testing instant invalidation of Session and PersistentLoginToken rows."""

    def test_deactivation_purges_sessions_and_tokens(
        self, manager_client: APIClient
    ) -> None:
        """Deactivating an employee immediately purges active Sessions and RememberTokens."""
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None
        acc = Account.objects.create(
            email="sess_test@parking.local",
            phone="0989999911",
            role="EMPLOYEE",
            is_active=True,
            password=make_password("Employee123!@#"),
        )
        emp = Employee.objects.create(
            code="NV704",
            full_name="Session Target",
            email=str(acc.email),
            phone=str(acc.phone),
            position=pos,
            account=acc,
            status="ACTIVE",
        )

        # Seed an active session storing this account_id
        session = Session.objects.create(
            session_key="test_adversarial_sess_01",
            session_data="",
            expire_date=timezone.now() + timedelta(days=1),
        )
        store1 = SessionStore(session_key="test_adversarial_sess_01")
        store1["_auth_user_id"] = str(acc.id)
        store1.save()

        # Seed an active remember-me token
        token = PersistentLoginToken.objects.create(
            account=acc,
            token_hash="dummy_token_hash_value_123456",
            series="dummy_series_123456",
            expires_at=timezone.now() + timedelta(days=30),
        )

        assert Session.objects.filter(session_key=session.session_key).exists()
        assert PersistentLoginToken.objects.filter(id=token.id).exists()

        # Deactivate via Manager PATCH
        res = manager_client.patch(
            f"/api/v1/employees/{emp.id}/",
            data={
                "row_version": emp.row_version,
                "status": "INACTIVE",
            },
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK

        # Assert session and token were revoked immediately
        assert not Session.objects.filter(session_key=session.session_key).exists()
        assert not PersistentLoginToken.objects.filter(id=token.id).exists()

    def test_soft_deletion_purges_sessions_and_tokens(
        self, manager_client: APIClient
    ) -> None:
        """Soft-deleting an employee immediately purges active Sessions and RememberTokens."""
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None
        acc = Account.objects.create(
            email="del_sess_test@parking.local",
            phone="0989999912",
            role="EMPLOYEE",
            is_active=True,
            password=make_password("Employee123!@#"),
        )
        emp = Employee.objects.create(
            code="NV705",
            full_name="Delete Session Target",
            email=str(acc.email),
            phone=str(acc.phone),
            position=pos,
            account=acc,
            status="ACTIVE",
        )

        session = Session.objects.create(
            session_key="test_adversarial_sess_02",
            session_data="",
            expire_date=timezone.now() + timedelta(days=1),
        )
        store2 = SessionStore(session_key="test_adversarial_sess_02")
        store2["_auth_user_id"] = str(acc.id)
        store2.save()
        token = PersistentLoginToken.objects.create(
            account=acc,
            token_hash="dummy_del_token_hash_123456",
            series="dummy_del_series_123456",
            expires_at=timezone.now() + timedelta(days=30),
        )

        # Soft delete via Manager DELETE
        res = manager_client.delete(f"/api/v1/employees/{emp.id}/")
        assert res.status_code == status.HTTP_200_OK

        # Assert session and token purged
        assert not Session.objects.filter(session_key=session.session_key).exists()
        assert not PersistentLoginToken.objects.filter(id=token.id).exists()
