"""
Real PostgreSQL 18.6 Concurrency and Live Session Revocation Tests for Employee Management API.
Module: apps.employees (SRS 4.3.1–4.3.4, Milestone M4, Round 67).

Test Suite Composition:
1. test_concurrent_employee_create_auto_code_advisory_lock:
   - 2 concurrent DB connections calling POST /api/v1/employees/ without 'code'.
   - Serialized under pg_advisory_xact_lock(hashtext('employee_code_sequence')).
   - Verifies 0 collisions, 2 distinct sequential NV%03d / NV%04d codes, both HTTP 201 Created.
2. test_concurrent_employee_create_duplicate_email_race:
   - 2 concurrent threads attempting to create an employee with the EXACT same email.
   - Verifies exactly one HTTP 201 Created and exactly one HTTP 409 Conflict (MSG-4.3.1-M05).
   - Verifies atomic rollback: zero orphan Account rows, no PII leakage in response.
3. test_concurrent_employee_create_duplicate_phone_race:
   - 2 concurrent threads attempting to create an employee with the EXACT same phone number.
   - Verifies exactly one HTTP 201 Created and exactly one HTTP 409 Conflict (MSG-4.3.1-M05).
   - Verifies atomic rollback: zero orphan Account rows, no PII leakage in response.
4. TestLiveSessionRevocationAndRoleDemotion:
   - test_live_session_and_token_revoked_on_deactivation:
     Live session and remember token purged on PATCH status=INACTIVE; next request 401.
   - test_live_session_revoked_and_forbidden_on_manager_role_demotion:
     Demoting manager (QL -> NVVH) purges session; old session 401, re-login receives 403 on manager-only API.
   - test_live_session_and_token_revoked_on_soft_delete:
     Soft-deleting employee purges session and remember token; next request 401.

CONCURRENCY EXECUTION SAFETY RULES:
- NO module-level `pytestmark = pytest.mark.django_db(transaction=True)` to prevent catastrophic flush truncation of seed data.
- Function-level `@pytest.mark.django_db(transaction=True)` applied strictly to multi-threaded tests.
- Every worker thread closes its DB connection via `connections.close_all()` in a mandatory finally block.
- Deterministic cleanup in test-level finally blocks restoring the database to a clean state.
"""

from __future__ import annotations

import re
import threading
from datetime import timedelta
from typing import Any

import pytest
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.models import Session
from django.db import connections
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account, PersistentLoginToken
from apps.employees.models import Employee, Position

ENDPOINT_URL = "/api/v1/employees/"


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def manager_account() -> Account:
    """Primary active MANAGER account for concurrency test authentication."""
    acc, _ = Account.objects.get_or_create(
        email="conc_manager_primary@parking.local",
        defaults={
            "phone": "0901999881",
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
    """Secondary active MANAGER account ensuring > 1 manager exists for DEL-01 guards."""
    acc, _ = Account.objects.get_or_create(
        email="conc_manager_secondary@parking.local",
        defaults={
            "phone": "0901999882",
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
def manager_client(manager_account: Account) -> APIClient:
    """APIClient authenticated as primary MANAGER."""
    client = APIClient()
    client.force_authenticate(user=manager_account)
    return client


# ==============================================================================
# 1. CONCURRENCY 1: SEQUENTIAL AUTO-CODE GENERATION UNDER ADVISORY LOCK
# ==============================================================================


@pytest.mark.django_db(transaction=True)
def test_concurrent_employee_create_auto_code_advisory_lock(
    manager_account: Account, secondary_manager_account: Account
) -> None:
    """
    Two concurrent database connections creating employees simultaneously without client-supplied code.
    Verifies that pg_advisory_xact_lock(hashtext('employee_code_sequence')) serializes auto-code generation:
    1. Both connections succeed (HTTP 201 Created).
    2. Zero code collisions or IntegrityError crashes on uq_employee_code_active.
    3. Codes are strictly distinct and strictly sequential (NV%03d / NV%04d).
    """
    num_threads = 2
    barrier = threading.Barrier(num_threads)
    results: list[Any] = [None] * num_threads
    errors: list[Exception | None] = [None] * num_threads

    pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
    assert pos is not None, "Position NVVH must exist in seed data"

    emails = [f"conc_auto_code_{i}@parking.local" for i in range(num_threads)]
    phones = [f"091211100{i}" for i in range(num_threads)]
    id_cards = [f"07920011100{i}" for i in range(num_threads)]

    payloads = [
        {
            "full_name": f"Concurrent AutoCode {i}",
            "email": emails[i],
            "phone": phones[i],
            "identity_card_number": id_cards[i],
            "position_id": pos.id,
            "password": "ValidPassword123!@#",
            "status": "ACTIVE",
        }
        for i in range(num_threads)
    ]

    def worker(idx: int) -> None:
        client = APIClient()
        client.force_authenticate(user=manager_account)
        try:
            barrier.wait()
            res = client.post(ENDPOINT_URL, payloads[idx], format="json")
            results[idx] = res
        except Exception as exc:
            errors[idx] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert all(err is None for err in errors), f"Thread execution failed: {errors}"

        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes == [status.HTTP_201_CREATED] * num_threads, (
            f"Unexpected statuses: {status_codes}, bodies: {[r.json() for r in results if r is not None]}"
        )

        codes = [r.json()["code"] for r in results if r is not None]
        assert len(set(codes)) == num_threads, f"Duplicate codes generated: {codes}"

        for code in codes:
            assert re.match(r"^NV[0-9]{3,4}$", code), f"Invalid code format: {code}"

        # Verify strictly sequential difference of exactly 1
        num_0 = int(codes[0][2:])
        num_1 = int(codes[1][2:])
        assert abs(num_0 - num_1) == 1, (
            f"Codes {codes[0]} and {codes[1]} are not sequential integers!"
        )
    finally:
        # Clean up created records to avoid polluting the database
        Employee.objects.filter(email__in=emails).delete()
        Account.objects.filter(email__in=emails).delete()


# ==============================================================================
# 2. CONCURRENCY 2: DUPLICATE EMAIL AND PHONE RACE CONDITIONS
# ==============================================================================


@pytest.mark.django_db(transaction=True)
def test_concurrent_employee_create_duplicate_email_race(
    manager_account: Account, secondary_manager_account: Account
) -> None:
    """
    Two concurrent threads attempting to create an employee with the EXACT same email.
    Verifies race-condition handling:
    1. Exactly one thread receives HTTP 201 Created.
    2. Exactly one thread receives HTTP 409 Conflict with code MSG-4.3.1-M05.
    3. The 409 response never leaks raw PII (the contested email).
    4. Atomic transaction rollback guarantees zero orphan Account records in DB.
    """
    num_threads = 2
    barrier = threading.Barrier(num_threads)
    results: list[Any] = [None] * num_threads
    errors: list[Exception | None] = [None] * num_threads

    pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
    assert pos is not None, "Position NVVH must exist in seed data"

    contested_email = "conc_race_email@parking.local"
    phones = ["0913111001", "0913111002"]
    id_cards = ["079200222001", "079200222002"]

    payloads = [
        {
            "full_name": f"Race Email Worker {i}",
            "email": contested_email,
            "phone": phones[i],
            "identity_card_number": id_cards[i],
            "position_id": pos.id,
            "password": "ValidPassword123!@#",
            "status": "ACTIVE",
        }
        for i in range(num_threads)
    ]

    def worker(idx: int) -> None:
        client = APIClient()
        client.force_authenticate(user=manager_account)
        try:
            barrier.wait()
            res = client.post(ENDPOINT_URL, payloads[idx], format="json")
            results[idx] = res
        except Exception as exc:
            errors[idx] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert all(err is None for err in errors), f"Thread execution failed: {errors}"

        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes.count(status.HTTP_201_CREATED) == 1, (
            f"Expected exactly one 201: {status_codes}, bodies: {[r.json() for r in results if r is not None]}"
        )
        assert status_codes.count(status.HTTP_409_CONFLICT) == 1, (
            f"Expected exactly one 409: {status_codes}, bodies: {[r.json() for r in results if r is not None]}"
        )

        for r in results:
            if r is not None and r.status_code == status.HTTP_409_CONFLICT:
                body = r.json()
                assert body.get("code") == "MSG-4.3.1-M05", (
                    f"Unexpected error code: {body}"
                )
                assert contested_email not in str(body), (
                    "Contested email leaked in 409 body!"
                )

        # Assert no orphan account created
        assert Account.objects.filter(email=contested_email).count() == 1
        assert Employee.objects.filter(email=contested_email).count() == 1
    finally:
        Employee.objects.filter(email=contested_email).delete()
        Account.objects.filter(email=contested_email).delete()


@pytest.mark.django_db(transaction=True)
def test_concurrent_employee_create_duplicate_phone_race(
    manager_account: Account, secondary_manager_account: Account
) -> None:
    """
    Two concurrent threads attempting to create an employee with the EXACT same phone number.
    Verifies race-condition handling:
    1. Exactly one thread receives HTTP 201 Created.
    2. Exactly one thread receives HTTP 409 Conflict with code MSG-4.3.1-M05.
    3. The 409 response never leaks raw PII (the contested phone).
    4. Atomic rollback guarantees zero orphan Account records.
    """
    num_threads = 2
    barrier = threading.Barrier(num_threads)
    results: list[Any] = [None] * num_threads
    errors: list[Exception | None] = [None] * num_threads

    pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
    assert pos is not None, "Position NVVH must exist in seed data"

    contested_phone = "0914111222"
    emails = ["conc_phone_race_1@parking.local", "conc_phone_race_2@parking.local"]
    id_cards = ["079200333001", "079200333002"]

    payloads = [
        {
            "full_name": f"Race Phone Worker {i}",
            "email": emails[i],
            "phone": contested_phone,
            "identity_card_number": id_cards[i],
            "position_id": pos.id,
            "password": "ValidPassword123!@#",
            "status": "ACTIVE",
        }
        for i in range(num_threads)
    ]

    def worker(idx: int) -> None:
        client = APIClient()
        client.force_authenticate(user=manager_account)
        try:
            barrier.wait()
            res = client.post(ENDPOINT_URL, payloads[idx], format="json")
            results[idx] = res
        except Exception as exc:
            errors[idx] = exc
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    try:
        assert all(err is None for err in errors), f"Thread execution failed: {errors}"

        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes.count(status.HTTP_201_CREATED) == 1, (
            f"Expected exactly one 201: {status_codes}, bodies: {[r.json() for r in results if r is not None]}"
        )
        assert status_codes.count(status.HTTP_409_CONFLICT) == 1, (
            f"Expected exactly one 409: {status_codes}, bodies: {[r.json() for r in results if r is not None]}"
        )

        for r in results:
            if r is not None and r.status_code == status.HTTP_409_CONFLICT:
                body = r.json()
                assert body.get("code") == "MSG-4.3.1-M05", (
                    f"Unexpected error code: {body}"
                )
                assert contested_phone not in str(body), (
                    "Contested phone leaked in 409 body!"
                )

        # Assert no orphan account created
        assert Account.objects.filter(phone=contested_phone).count() == 1
        assert Employee.objects.filter(phone=contested_phone).count() == 1
    finally:
        Employee.objects.filter(phone=contested_phone).delete()
        Account.objects.filter(phone=contested_phone).delete()


# ==============================================================================
# 3. LIVE SESSION REVOCATION & ROLE DEMOTION TESTS
# ==============================================================================


@pytest.mark.django_db
class TestLiveSessionRevocationAndRoleDemotion:
    """
    Live real-session and remember-token revocation tests across employee lifecycle operations:
    1. PATCH status=INACTIVE (Deactivation):
       - Active Django session in django_session and PersistentLoginToken are purged immediately.
       - Next request using old session cookie is rejected with HTTP 401 UNAUTHORIZED.
       - Next request presenting old remember-me cookie is rejected with HTTP 401 UNAUTHORIZED.
    2. PATCH position_id (Role Demotion: QL -> NVVH):
       - Manager demoted to employee has Account.role changed from MANAGER to EMPLOYEE.
       - Existing sessions are immediately purged.
       - Next request with old session receives HTTP 401 UNAUTHORIZED.
       - Re-authenticated session with demoted EMPLOYEE role receives HTTP 403 FORBIDDEN on manager APIs.
    3. DELETE /api/v1/employees/{id}/ (Soft Delete):
       - Active session and remember-token rows are purged immediately in the same transaction.
       - Next request with old session cookie receives HTTP 401 UNAUTHORIZED.
    """

    def test_live_session_and_token_revoked_on_deactivation(
        self, manager_client: APIClient, secondary_manager_account: Account
    ) -> None:
        """
        Deactivating an employee immediately purges active Session and PersistentLoginToken rows.
        The next request presenting the previous session cookie is rejected with 401 Unauthorized.
        """
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None

        acc = Account.objects.create(
            email="live_deact_test@parking.local",
            phone="0915111001",
            role="EMPLOYEE",
            is_active=True,
            password=make_password("ValidPassword123!@#"),
        )
        emp = Employee.objects.create(
            code="NV711",
            full_name="Live Deactivate Target",
            email=str(acc.email),
            phone=str(acc.phone),
            position=pos,
            account=acc,
            status="ACTIVE",
        )

        emp_client = APIClient()
        emp_client.force_login(acc)
        session_key = emp_client.cookies["sessionid"].value

        token = PersistentLoginToken.objects.create(
            account=acc,
            series="live_series_deact",
            token_hash="dummy_token_hash_deact",
            expires_at=timezone.now() + timedelta(days=30),
        )

        assert Session.objects.filter(session_key=session_key).exists()
        assert PersistentLoginToken.objects.filter(id=token.id).exists()

        # Manager performs deactivation via PATCH
        res_patch = manager_client.patch(
            f"/api/v1/employees/{emp.id}/",
            data={"row_version": emp.row_version, "status": "INACTIVE"},
            format="json",
        )
        assert res_patch.status_code == status.HTTP_200_OK

        # DB State Assertions: sessions and remember tokens are purged immediately
        assert not Session.objects.filter(session_key=session_key).exists()
        assert not PersistentLoginToken.objects.filter(id=token.id).exists()
        acc.refresh_from_db()
        assert acc.is_active is False

        # Live request assertion 1: Old session is rejected with HTTP 401
        res_after = emp_client.get("/api/v1/auth/me/")
        assert res_after.status_code == status.HTTP_401_UNAUTHORIZED

        # Live request assertion 2: Remember-me cookie is rejected and purged
        remember_client = APIClient()
        remember_client.cookies[settings.REMEMBER_COOKIE_NAME] = (
            "live_series_deact:dummy_token_raw"
        )
        res_remember = remember_client.get("/api/v1/auth/me/")
        assert res_remember.status_code == status.HTTP_401_UNAUTHORIZED

    def test_live_session_revoked_and_forbidden_on_manager_role_demotion(
        self, manager_client: APIClient, secondary_manager_account: Account
    ) -> None:
        """
        Demoting an employee from MANAGER (QL) to EMPLOYEE (NVVH) immediately revokes active sessions.
        Subsequent request with old session receives 401 Unauthorized.
        Re-authenticating with the now-demoted account yields 403 Forbidden on MANAGER-only endpoints.
        """
        pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
        pos_nvvh = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos_ql is not None and pos_nvvh is not None

        mgr_acc = Account.objects.create(
            email="demoted_mgr@parking.local",
            phone="0915111002",
            role="MANAGER",
            is_active=True,
            password=make_password("ValidPassword123!@#"),
        )
        mgr_emp = Employee.objects.create(
            code="NV712",
            full_name="Demotion Target",
            email=str(mgr_acc.email),
            phone=str(mgr_acc.phone),
            position=pos_ql,
            account=mgr_acc,
            status="ACTIVE",
        )

        target_client = APIClient()
        target_client.force_login(mgr_acc)
        session_key = target_client.cookies["sessionid"].value

        # Pre-demotion verification: Target is an active MANAGER, can access employee list
        res_pre = target_client.get(ENDPOINT_URL)
        assert res_pre.status_code == status.HTTP_200_OK

        # Primary manager demotes target employee from QL to NVVH via PATCH
        res_patch = manager_client.patch(
            f"/api/v1/employees/{mgr_emp.id}/",
            data={
                "row_version": mgr_emp.row_version,
                "position_id": pos_nvvh.id,
            },
            format="json",
        )
        assert res_patch.status_code == status.HTTP_200_OK

        # DB State Assertions: role is changed to EMPLOYEE and session is revoked
        mgr_acc.refresh_from_db()
        assert mgr_acc.role == "EMPLOYEE"
        assert not Session.objects.filter(session_key=session_key).exists()

        # Live request assertion 1: Request with old session cookie receives 401
        res_old_sess = target_client.get(ENDPOINT_URL)
        assert res_old_sess.status_code == status.HTTP_401_UNAUTHORIZED

        # Live request assertion 2: If user logs back in with demoted EMPLOYEE role,
        # accessing MANAGER-only endpoint results in 403 Forbidden
        reauth_client = APIClient()
        reauth_client.force_login(mgr_acc)
        res_reauth = reauth_client.get(ENDPOINT_URL)
        assert res_reauth.status_code == status.HTTP_403_FORBIDDEN

    def test_live_session_and_token_revoked_on_soft_delete(
        self, manager_client: APIClient, secondary_manager_account: Account
    ) -> None:
        """
        Soft-deleting an employee immediately purges active Sessions and RememberTokens in DB.
        The next request using the old session is rejected with HTTP 401 Unauthorized.
        """
        pos = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
        assert pos is not None

        acc = Account.objects.create(
            email="live_del_test@parking.local",
            phone="0915111003",
            role="EMPLOYEE",
            is_active=True,
            password=make_password("ValidPassword123!@#"),
        )
        emp = Employee.objects.create(
            code="NV713",
            full_name="Live Delete Target",
            email=str(acc.email),
            phone=str(acc.phone),
            position=pos,
            account=acc,
            status="ACTIVE",
        )

        emp_client = APIClient()
        emp_client.force_login(acc)
        session_key = emp_client.cookies["sessionid"].value

        token = PersistentLoginToken.objects.create(
            account=acc,
            series="live_series_delete",
            token_hash="dummy_token_hash_delete",
            expires_at=timezone.now() + timedelta(days=30),
        )

        # Manager soft-deletes the employee
        res_del = manager_client.delete(f"/api/v1/employees/{emp.id}/")
        assert res_del.status_code == status.HTTP_200_OK

        # DB State Assertions
        assert not Session.objects.filter(session_key=session_key).exists()
        assert not PersistentLoginToken.objects.filter(id=token.id).exists()
        emp.refresh_from_db()
        assert emp.deleted_at is not None
        acc.refresh_from_db()
        assert acc.deleted_at is not None
        assert acc.is_active is False

        # Live request assertion: Old session is rejected with HTTP 401
        res_after = emp_client.get("/api/v1/auth/me/")
        assert res_after.status_code == status.HTTP_401_UNAUTHORIZED

    def test_revoke_account_sessions_isolation(self) -> None:
        """
        M5 Verification: Proves that revoke_account_sessions_and_tokens cleanly revokes
        all sessions and remember tokens belonging to the target account while 100%
        preserving active sessions belonging to other accounts (Session Isolation).
        """
        from django.contrib.sessions.backends.db import SessionStore

        from apps.employees.services.employees import revoke_account_sessions_and_tokens

        acc_target = Account.objects.create(
            email="target_isolation@parking.local",
            phone="0919111222",
            role="EMPLOYEE",
            is_active=True,
            password=make_password("ValidPassword123!@#"),
        )
        acc_other = Account.objects.create(
            email="other_isolation@parking.local",
            phone="0919111333",
            role="EMPLOYEE",
            is_active=True,
            password=make_password("ValidPassword123!@#"),
        )

        target_keys: list[str] = []
        for i in range(5):
            s = SessionStore()
            s["_auth_user_id"] = str(acc_target.id)
            s["custom_field"] = f"target_data_{i}"
            s.save()
            assert s.session_key is not None
            target_keys.append(s.session_key)

        other_keys: list[str] = []
        for i in range(10):
            s = SessionStore()
            s["_auth_user_id"] = str(acc_other.id)
            s["custom_field"] = f"other_data_{i}"
            s.save()
            assert s.session_key is not None
            other_keys.append(s.session_key)

        # Assert initial state
        assert Session.objects.filter(session_key__in=target_keys).count() == 5
        assert Session.objects.filter(session_key__in=other_keys).count() == 10

        # Execute revocation on target account only
        revoked_count = revoke_account_sessions_and_tokens(acc_target.id)
        assert revoked_count == 5

        # Assert complete purging of target sessions
        assert Session.objects.filter(session_key__in=target_keys).count() == 0

        # Assert strict 100% preservation of other accounts' sessions
        assert Session.objects.filter(session_key__in=other_keys).count() == 10
        for key in other_keys:
            stored_session = Session.objects.get(session_key=key)
            decoded = SessionStore().decode(stored_session.session_data)
            assert str(decoded.get("_auth_user_id")) == str(acc_other.id)

    def test_revoke_account_sessions_corrupted_data_and_narrow_exception(
        self,
    ) -> None:
        """
        Kiểm thử thu hồi session khi tồn tại bản ghi session_data bị hỏng/undecodable (N4, R5).
        - 1 bản ghi session hỏng (payload dị thường không decode được).
        - 1 bản ghi session hợp lệ của tài khoản mục tiêu (acc_target).
        - 1 bản ghi session hợp lệ của tài khoản khác (acc_other).
        Khẳng định:
        1. Session hợp lệ của mục tiêu bị thu hồi thành công.
        2. Bản ghi session hỏng được bỏ qua an toàn, không gây crash hoặc ném exception chưa bắt.
        3. Bản ghi session của tài khoản khác được bảo tồn nguyên vẹn 100%.
        4. Tuyệt đối không rò rỉ PII hay nội dung session payload.
        """
        from apps.employees.services.employees import (
            revoke_account_sessions_and_tokens,
        )

        acc_target = Account.objects.create(
            email="test_corrupt_target@parking.local",
            phone="0919998877",
            role="EMPLOYEE",
            is_active=True,
            password=make_password("ValidPassword123!@#"),
        )
        acc_other = Account.objects.create(
            email="test_corrupt_other@parking.local",
            phone="0919998866",
            role="EMPLOYEE",
            is_active=True,
            password=make_password("ValidPassword123!@#"),
        )

        expire = timezone.now() + timedelta(days=1)
        key_corrupt = "test_corrupted_key_001"
        key_valid_target = "test_valid_target_key_002"
        key_valid_other = "test_valid_other_key_003"

        Session.objects.filter(
            session_key__in=[key_corrupt, key_valid_target, key_valid_other]
        ).delete()

        try:
            # 1. Tạo session hỏng (chuỗi không hợp lệ gây lỗi giải mã)
            Session.objects.create(
                session_key=key_corrupt,
                session_data="!@#$%^&*()_CORRUPTED_NON_BASE64_PAYLOAD",
                expire_date=expire,
            )

            # 2. Tạo session hợp lệ của mục tiêu
            s_target = SessionStore()
            valid_target_data = s_target.encode(
                {
                    "_auth_user_id": str(acc_target.id),
                    "secret_token": "target_secret_token",
                }
            )
            Session.objects.create(
                session_key=key_valid_target,
                session_data=valid_target_data,
                expire_date=expire,
            )

            # 3. Tạo session hợp lệ của user khác
            s_other = SessionStore()
            valid_other_data = s_other.encode(
                {
                    "_auth_user_id": str(acc_other.id),
                    "secret_token": "other_secret_token",
                }
            )
            Session.objects.create(
                session_key=key_valid_other,
                session_data=valid_other_data,
                expire_date=expire,
            )

            # Thực thi thu hồi
            revoked_count = revoke_account_sessions_and_tokens(acc_target.id)
            assert revoked_count == 1

            # Assert session của mục tiêu bị xóa
            assert not Session.objects.filter(session_key=key_valid_target).exists()

            # Assert session hỏng vẫn tồn tại (bỏ qua an toàn)
            assert Session.objects.filter(session_key=key_corrupt).exists()

            # Assert session của user khác còn nguyên vẹn
            assert Session.objects.filter(session_key=key_valid_other).exists()
            stored_other = Session.objects.get(session_key=key_valid_other)
            decoded_other = SessionStore().decode(stored_other.session_data)
            assert str(decoded_other.get("_auth_user_id")) == str(acc_other.id)
        finally:
            Session.objects.filter(
                session_key__in=[key_corrupt, key_valid_target, key_valid_other]
            ).delete()
            acc_target.delete()
            acc_other.delete()


# ==============================================================================
# 5. CONCURRENCY: RACE-FREE LAST ACTIVE MANAGER GUARD (M3)
# ==============================================================================


@pytest.mark.django_db(transaction=True)
def test_concurrent_last_active_manager_deactivation_race() -> None:
    """
    M3 Concurrency Test: Two concurrent database connections attempting to deactivate
    each other simultaneously when only two active managers remain in the system.
    Under pg_advisory_xact_lock(hashtext('guard_last_active_manager')):
    1. Exactly one request succeeds with HTTP 200 OK.
    2. Exactly one request fails cleanly with HTTP 409 Conflict and code PROP-DEL-01-LAST-MGR-EMP.
    3. Zero deadlocks, zero 500 Internal Server Errors.
    4. Database strictly preserves exactly 1 active manager.
    """
    pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
    assert pos_ql is not None

    acc_a = Account.objects.create(
        email="conc_m3_deact_a@parking.local",
        phone="0918111901",
        role="MANAGER",
        is_active=True,
        password=make_password("Manager123!@#"),
    )
    emp_a = Employee.objects.create(
        code="NV881",
        full_name="Manager Race Deact A",
        email=str(acc_a.email),
        phone=str(acc_a.phone),
        position=pos_ql,
        account=acc_a,
        status="ACTIVE",
    )

    acc_b = Account.objects.create(
        email="conc_m3_deact_b@parking.local",
        phone="0918111902",
        role="MANAGER",
        is_active=True,
        password=make_password("Manager123!@#"),
    )
    emp_b = Employee.objects.create(
        code="NV882",
        full_name="Manager Race Deact B",
        email=str(acc_b.email),
        phone=str(acc_b.phone),
        position=pos_ql,
        account=acc_b,
        status="ACTIVE",
    )

    other_mgr_ids = list(
        Account.objects.filter(role="MANAGER", is_active=True, deleted_at__isnull=True)
        .exclude(id__in=[acc_a.id, acc_b.id])
        .values_list("id", flat=True)
    )
    Account.objects.filter(id__in=other_mgr_ids).update(is_active=False)

    num_threads = 2
    barrier = threading.Barrier(num_threads)
    results: list[Any] = [None] * num_threads
    errors: list[Exception | None] = [None] * num_threads

    def worker_a() -> None:
        client = APIClient()
        client.force_authenticate(user=acc_a)
        try:
            barrier.wait()
            res = client.patch(
                f"/api/v1/employees/{emp_b.id}/",
                data={"row_version": emp_b.row_version, "status": "INACTIVE"},
                format="json",
            )
            results[0] = res
        except Exception as exc:
            errors[0] = exc
        finally:
            connections.close_all()

    def worker_b() -> None:
        client = APIClient()
        client.force_authenticate(user=acc_b)
        try:
            barrier.wait()
            res = client.patch(
                f"/api/v1/employees/{emp_a.id}/",
                data={"row_version": emp_a.row_version, "status": "INACTIVE"},
                format="json",
            )
            results[1] = res
        except Exception as exc:
            errors[1] = exc
        finally:
            connections.close_all()

    try:
        t1 = threading.Thread(target=worker_a)
        t2 = threading.Thread(target=worker_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert all(err is None for err in errors), f"Thread execution error: {errors}"

        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes.count(status.HTTP_200_OK) == 1, (
            f"Expected exactly one 200 OK, got: {status_codes}"
        )
        assert status_codes.count(status.HTTP_409_CONFLICT) == 1, (
            f"Expected exactly one 409 Conflict, got: {status_codes}"
        )

        losing_res = next(
            r for r in results if r.status_code == status.HTTP_409_CONFLICT
        )
        assert losing_res.json().get("code") == "PROP-DEL-01-LAST-MGR-EMP"

        active_count = Account.objects.filter(
            role="MANAGER", is_active=True, deleted_at__isnull=True
        ).count()
        assert active_count == 1, (
            f"Expected strictly 1 active manager remaining, found {active_count}"
        )
    finally:
        Account.objects.filter(id__in=other_mgr_ids).update(is_active=True)
        Employee.objects.filter(id__in=[emp_a.id, emp_b.id]).delete()
        Account.objects.filter(id__in=[acc_a.id, acc_b.id]).delete()
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_concurrent_last_active_manager_demotion_race() -> None:
    """
    M3 Concurrency Test: Two concurrent database connections attempting to demote
    each other simultaneously from QL to NVVH when only two active managers remain.
    Verifies that under pg_advisory_xact_lock:
    1. Exactly one request succeeds with HTTP 200 OK.
    2. Exactly one request fails cleanly with HTTP 409 Conflict (PROP-DEL-01-LAST-MGR-EMP).
    3. Exactly 1 active manager remains in the system.
    """
    pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
    pos_nvvh = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
    assert pos_ql is not None and pos_nvvh is not None

    acc_a = Account.objects.create(
        email="conc_m3_demote_a@parking.local",
        phone="0918111903",
        role="MANAGER",
        is_active=True,
        password=make_password("Manager123!@#"),
    )
    emp_a = Employee.objects.create(
        code="NV883",
        full_name="Manager Race Demote A",
        email=str(acc_a.email),
        phone=str(acc_a.phone),
        position=pos_ql,
        account=acc_a,
        status="ACTIVE",
    )

    acc_b = Account.objects.create(
        email="conc_m3_demote_b@parking.local",
        phone="0918111904",
        role="MANAGER",
        is_active=True,
        password=make_password("Manager123!@#"),
    )
    emp_b = Employee.objects.create(
        code="NV884",
        full_name="Manager Race Demote B",
        email=str(acc_b.email),
        phone=str(acc_b.phone),
        position=pos_ql,
        account=acc_b,
        status="ACTIVE",
    )

    other_mgr_ids = list(
        Account.objects.filter(role="MANAGER", is_active=True, deleted_at__isnull=True)
        .exclude(id__in=[acc_a.id, acc_b.id])
        .values_list("id", flat=True)
    )
    Account.objects.filter(id__in=other_mgr_ids).update(is_active=False)

    num_threads = 2
    barrier = threading.Barrier(num_threads)
    results: list[Any] = [None] * num_threads
    errors: list[Exception | None] = [None] * num_threads

    def worker_a() -> None:
        client = APIClient()
        client.force_authenticate(user=acc_a)
        try:
            barrier.wait()
            res = client.patch(
                f"/api/v1/employees/{emp_b.id}/",
                data={"row_version": emp_b.row_version, "position_id": pos_nvvh.id},
                format="json",
            )
            results[0] = res
        except Exception as exc:
            errors[0] = exc
        finally:
            connections.close_all()

    def worker_b() -> None:
        client = APIClient()
        client.force_authenticate(user=acc_b)
        try:
            barrier.wait()
            res = client.patch(
                f"/api/v1/employees/{emp_a.id}/",
                data={"row_version": emp_a.row_version, "position_id": pos_nvvh.id},
                format="json",
            )
            results[1] = res
        except Exception as exc:
            errors[1] = exc
        finally:
            connections.close_all()

    try:
        t1 = threading.Thread(target=worker_a)
        t2 = threading.Thread(target=worker_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert all(err is None for err in errors), f"Thread execution error: {errors}"

        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes.count(status.HTTP_200_OK) == 1, (
            f"Expected exactly one 200 OK, got: {status_codes}"
        )
        assert status_codes.count(status.HTTP_409_CONFLICT) == 1, (
            f"Expected exactly one 409 Conflict, got: {status_codes}"
        )

        losing_res = next(
            r for r in results if r.status_code == status.HTTP_409_CONFLICT
        )
        assert losing_res.json().get("code") == "PROP-DEL-01-LAST-MGR-EMP"

        active_count = Account.objects.filter(
            role="MANAGER", is_active=True, deleted_at__isnull=True
        ).count()
        assert active_count == 1, (
            f"Expected strictly 1 active manager remaining, found {active_count}"
        )
    finally:
        Account.objects.filter(id__in=other_mgr_ids).update(is_active=True)
        Employee.objects.filter(id__in=[emp_a.id, emp_b.id]).delete()
        Account.objects.filter(id__in=[acc_a.id, acc_b.id]).delete()
        connections.close_all()


# ==============================================================================
# 5. COMMITTED LAST-MANAGER DELETE-PATH CONCURRENCY TESTS (N2)
# ==============================================================================


def _run_single_delete_delete_race(iteration: int, pos_ql: Position) -> None:
    """Thực thi một vòng race condition delete / delete giữa 2 Quản lý duy nhất."""
    code_a = f"NV81{iteration:02d}"
    code_b = f"NV82{iteration:02d}"
    acc_a = Account.objects.create(
        email=f"del_del_a_{iteration}@parking.local",
        phone=f"091801{iteration:04d}",
        role="MANAGER",
        is_active=True,
        password=make_password("Manager123!@#"),
    )
    emp_a = Employee.objects.create(
        code=code_a,
        full_name=f"Manager DelDel A {iteration}",
        email=str(acc_a.email),
        phone=str(acc_a.phone),
        position=pos_ql,
        account=acc_a,
        status="ACTIVE",
    )

    acc_b = Account.objects.create(
        email=f"del_del_b_{iteration}@parking.local",
        phone=f"091802{iteration:04d}",
        role="MANAGER",
        is_active=True,
        password=make_password("Manager123!@#"),
    )
    emp_b = Employee.objects.create(
        code=code_b,
        full_name=f"Manager DelDel B {iteration}",
        email=str(acc_b.email),
        phone=str(acc_b.phone),
        position=pos_ql,
        account=acc_b,
        status="ACTIVE",
    )

    other_mgr_ids = list(
        Account.objects.filter(role="MANAGER", is_active=True, deleted_at__isnull=True)
        .exclude(id__in=[acc_a.id, acc_b.id])
        .values_list("id", flat=True)
    )
    Account.objects.filter(id__in=other_mgr_ids).update(is_active=False)

    num_threads = 2
    barrier = threading.Barrier(num_threads)
    results: list[Any] = [None] * num_threads
    errors: list[Exception | None] = [None] * num_threads

    def worker_a() -> None:
        client = APIClient()
        client.force_authenticate(user=acc_a)
        try:
            barrier.wait()
            res = client.delete(f"/api/v1/employees/{emp_b.id}/")
            results[0] = res
        except Exception as exc:
            errors[0] = exc
        finally:
            connections.close_all()

    def worker_b() -> None:
        client = APIClient()
        client.force_authenticate(user=acc_b)
        try:
            barrier.wait()
            res = client.delete(f"/api/v1/employees/{emp_a.id}/")
            results[1] = res
        except Exception as exc:
            errors[1] = exc
        finally:
            connections.close_all()

    try:
        t1 = threading.Thread(target=worker_a)
        t2 = threading.Thread(target=worker_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert all(err is None for err in errors), (
            f"[Iteration {iteration}] Thread error: {errors}"
        )
        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes.count(status.HTTP_200_OK) == 1, (
            f"[Iteration {iteration}] Expected 1 200 OK, got: {status_codes}"
        )
        assert status_codes.count(status.HTTP_409_CONFLICT) == 1, (
            f"[Iteration {iteration}] Expected 1 409 Conflict, got: {status_codes}"
        )

        losing_res = next(
            r for r in results if r.status_code == status.HTTP_409_CONFLICT
        )
        assert losing_res.json().get("code") == "PROP-DEL-01-LAST-MGR-EMP", (
            f"[Iteration {iteration}] Wrong error code: {losing_res.json()}"
        )

        active_count = Account.objects.filter(
            role="MANAGER", is_active=True, deleted_at__isnull=True
        ).count()
        assert active_count == 1, (
            f"[Iteration {iteration}] Expected strictly 1 active manager, got: {active_count}"
        )
    finally:
        Account.objects.filter(id__in=other_mgr_ids).update(is_active=True)
        Employee.objects.filter(id__in=[emp_a.id, emp_b.id]).delete()
        Account.objects.filter(id__in=[acc_a.id, acc_b.id]).delete()
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_concurrent_last_active_manager_delete_delete_race() -> None:
    """
    Kịch bản (a): delete / delete race condition (N2, Milestone M2).
    Hai kết nối CSDL đồng thời gọi DELETE /api/v1/employees/{id}/ lẫn nhau khi hệ thống
    chỉ còn chính xác 2 Quản lý đang hoạt động.
    Lặp lại 5 lần để đảm bảo tính bất biến và triệt tiêu flakiness:
    - Đúng 1 request trả về HTTP 200 OK (xóa thành công).
    - Đúng 1 request trả về HTTP 409 Conflict với mã PROP-DEL-01-LAST-MGR-EMP.
    - Cơ sở dữ liệu luôn còn lại chính xác đúng 1 Quản lý hoạt động.
    """
    pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
    assert pos_ql is not None, "Position QL must exist in seed data"

    for iteration in range(5):
        _run_single_delete_delete_race(iteration, pos_ql)


def _run_single_deactivate_delete_race(iteration: int, pos_ql: Position) -> None:
    """Thực thi một vòng race condition deactivate / delete giữa 2 Quản lý."""
    code_a = f"NV83{iteration:02d}"
    code_b = f"NV84{iteration:02d}"
    acc_a = Account.objects.create(
        email=f"deact_del_a_{iteration}@parking.local",
        phone=f"091811{iteration:04d}",
        role="MANAGER",
        is_active=True,
        password=make_password("Manager123!@#"),
    )
    emp_a = Employee.objects.create(
        code=code_a,
        full_name=f"Manager DeactDel A {iteration}",
        email=str(acc_a.email),
        phone=str(acc_a.phone),
        position=pos_ql,
        account=acc_a,
        status="ACTIVE",
    )

    acc_b = Account.objects.create(
        email=f"deact_del_b_{iteration}@parking.local",
        phone=f"091812{iteration:04d}",
        role="MANAGER",
        is_active=True,
        password=make_password("Manager123!@#"),
    )
    emp_b = Employee.objects.create(
        code=code_b,
        full_name=f"Manager DeactDel B {iteration}",
        email=str(acc_b.email),
        phone=str(acc_b.phone),
        position=pos_ql,
        account=acc_b,
        status="ACTIVE",
    )

    other_mgr_ids = list(
        Account.objects.filter(role="MANAGER", is_active=True, deleted_at__isnull=True)
        .exclude(id__in=[acc_a.id, acc_b.id])
        .values_list("id", flat=True)
    )
    Account.objects.filter(id__in=other_mgr_ids).update(is_active=False)

    num_threads = 2
    barrier = threading.Barrier(num_threads)
    results: list[Any] = [None] * num_threads
    errors: list[Exception | None] = [None] * num_threads

    def worker_a() -> None:
        client = APIClient()
        client.force_authenticate(user=acc_a)
        try:
            barrier.wait()
            res = client.patch(
                f"/api/v1/employees/{emp_b.id}/",
                data={"row_version": emp_b.row_version, "status": "INACTIVE"},
                format="json",
            )
            results[0] = res
        except Exception as exc:
            errors[0] = exc
        finally:
            connections.close_all()

    def worker_b() -> None:
        client = APIClient()
        client.force_authenticate(user=acc_b)
        try:
            barrier.wait()
            res = client.delete(f"/api/v1/employees/{emp_a.id}/")
            results[1] = res
        except Exception as exc:
            errors[1] = exc
        finally:
            connections.close_all()

    try:
        t1 = threading.Thread(target=worker_a)
        t2 = threading.Thread(target=worker_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert all(err is None for err in errors), (
            f"[Iteration {iteration}] Thread error: {errors}"
        )
        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes.count(status.HTTP_200_OK) == 1, (
            f"[Iteration {iteration}] Expected 1 200 OK, got: {status_codes}"
        )
        assert status_codes.count(status.HTTP_409_CONFLICT) == 1, (
            f"[Iteration {iteration}] Expected 1 409 Conflict, got: {status_codes}"
        )

        losing_res = next(
            r for r in results if r.status_code == status.HTTP_409_CONFLICT
        )
        assert losing_res.json().get("code") == "PROP-DEL-01-LAST-MGR-EMP", (
            f"[Iteration {iteration}] Wrong error code: {losing_res.json()}"
        )

        active_count = Account.objects.filter(
            role="MANAGER", is_active=True, deleted_at__isnull=True
        ).count()
        assert active_count == 1, (
            f"[Iteration {iteration}] Expected strictly 1 active manager, got: {active_count}"
        )
    finally:
        Account.objects.filter(id__in=other_mgr_ids).update(is_active=True)
        Employee.objects.filter(id__in=[emp_a.id, emp_b.id]).delete()
        Account.objects.filter(id__in=[acc_a.id, acc_b.id]).delete()
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_concurrent_last_active_manager_deactivate_delete_race() -> None:
    """
    Kịch bản (b): deactivate / delete race condition (N2, Milestone M2).
    Một kết nối gọi PATCH status='INACTIVE' đối với Quản lý B, đồng thời kết nối kia gọi
    DELETE đối với Quản lý A khi hệ thống chỉ còn đúng 2 Quản lý.
    Lặp lại 5 lần để đảm bảo tính ổn định:
    - Đúng 1 request thành công 200 OK.
    - Đúng 1 request bị chặn 409 Conflict với mã PROP-DEL-01-LAST-MGR-EMP.
    - Cơ sở dữ liệu luôn còn lại chính xác đúng 1 Quản lý hoạt động.
    """
    pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
    assert pos_ql is not None, "Position QL must exist in seed data"

    for iteration in range(5):
        _run_single_deactivate_delete_race(iteration, pos_ql)


def _run_single_demote_delete_race(
    iteration: int, pos_ql: Position, pos_nvvh: Position
) -> None:
    """Thực thi một vòng race condition demote / delete giữa 2 Quản lý."""
    code_a = f"NV85{iteration:02d}"
    code_b = f"NV86{iteration:02d}"
    acc_a = Account.objects.create(
        email=f"demote_del_a_{iteration}@parking.local",
        phone=f"091821{iteration:04d}",
        role="MANAGER",
        is_active=True,
        password=make_password("Manager123!@#"),
    )
    emp_a = Employee.objects.create(
        code=code_a,
        full_name=f"Manager DemoteDel A {iteration}",
        email=str(acc_a.email),
        phone=str(acc_a.phone),
        position=pos_ql,
        account=acc_a,
        status="ACTIVE",
    )

    acc_b = Account.objects.create(
        email=f"demote_del_b_{iteration}@parking.local",
        phone=f"091822{iteration:04d}",
        role="MANAGER",
        is_active=True,
        password=make_password("Manager123!@#"),
    )
    emp_b = Employee.objects.create(
        code=code_b,
        full_name=f"Manager DemoteDel B {iteration}",
        email=str(acc_b.email),
        phone=str(acc_b.phone),
        position=pos_ql,
        account=acc_b,
        status="ACTIVE",
    )

    other_mgr_ids = list(
        Account.objects.filter(role="MANAGER", is_active=True, deleted_at__isnull=True)
        .exclude(id__in=[acc_a.id, acc_b.id])
        .values_list("id", flat=True)
    )
    Account.objects.filter(id__in=other_mgr_ids).update(is_active=False)

    num_threads = 2
    barrier = threading.Barrier(num_threads)
    results: list[Any] = [None] * num_threads
    errors: list[Exception | None] = [None] * num_threads

    def worker_a() -> None:
        client = APIClient()
        client.force_authenticate(user=acc_a)
        try:
            barrier.wait()
            res = client.patch(
                f"/api/v1/employees/{emp_b.id}/",
                data={"row_version": emp_b.row_version, "position_id": pos_nvvh.id},
                format="json",
            )
            results[0] = res
        except Exception as exc:
            errors[0] = exc
        finally:
            connections.close_all()

    def worker_b() -> None:
        client = APIClient()
        client.force_authenticate(user=acc_b)
        try:
            barrier.wait()
            res = client.delete(f"/api/v1/employees/{emp_a.id}/")
            results[1] = res
        except Exception as exc:
            errors[1] = exc
        finally:
            connections.close_all()

    try:
        t1 = threading.Thread(target=worker_a)
        t2 = threading.Thread(target=worker_b)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert all(err is None for err in errors), (
            f"[Iteration {iteration}] Thread error: {errors}"
        )
        status_codes = [r.status_code for r in results if r is not None]
        assert status_codes.count(status.HTTP_200_OK) == 1, (
            f"[Iteration {iteration}] Expected 1 200 OK, got: {status_codes}"
        )
        assert status_codes.count(status.HTTP_409_CONFLICT) == 1, (
            f"[Iteration {iteration}] Expected 1 409 Conflict, got: {status_codes}"
        )

        losing_res = next(
            r for r in results if r.status_code == status.HTTP_409_CONFLICT
        )
        assert losing_res.json().get("code") == "PROP-DEL-01-LAST-MGR-EMP", (
            f"[Iteration {iteration}] Wrong error code: {losing_res.json()}"
        )

        active_count = Account.objects.filter(
            role="MANAGER", is_active=True, deleted_at__isnull=True
        ).count()
        assert active_count == 1, (
            f"[Iteration {iteration}] Expected strictly 1 active manager, got: {active_count}"
        )
    finally:
        Account.objects.filter(id__in=other_mgr_ids).update(is_active=True)
        Employee.objects.filter(id__in=[emp_a.id, emp_b.id]).delete()
        Account.objects.filter(id__in=[acc_a.id, acc_b.id]).delete()
        connections.close_all()


@pytest.mark.django_db(transaction=True)
def test_concurrent_last_active_manager_demote_delete_race() -> None:
    """
    Kịch bản (c): demote / delete race condition (N2, Milestone M2).
    Một kết nối gọi PATCH giáng chức Quản lý B xuống NVVH, đồng thời kết nối kia gọi
    DELETE đối với Quản lý A khi hệ thống chỉ còn đúng 2 Quản lý.
    Lặp lại 5 lần để đảm bảo tính ổn định:
    - Đúng 1 request thành công 200 OK.
    - Đúng 1 request bị chặn 409 Conflict với mã PROP-DEL-01-LAST-MGR-EMP.
    - Cơ sở dữ liệu luôn còn lại chính xác đúng 1 Quản lý hoạt động.
    """
    pos_ql = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
    pos_nvvh = Position.objects.filter(code="NVVH", deleted_at__isnull=True).first()
    assert pos_ql is not None and pos_nvvh is not None, (
        "Positions QL and NVVH must exist"
    )

    for iteration in range(5):
        _run_single_demote_delete_race(iteration, pos_ql, pos_nvvh)
