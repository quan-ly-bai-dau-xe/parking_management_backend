"""
Real PostgreSQL 18.6 Database Error Translation Tests for Employee Management API.
Module: apps.employees.services.error_translation (SRS 4.3.1–4.3.4, Milestone M4, Round 67).

All exceptions verified are authentic PostgreSQL 18.6 DatabaseError / IntegrityError / OperationalError
instances generated on real tables inside savepoints. Zero mocks.
Tests assert that PII (CCCD, Phone, Email, Full Name) is strictly NEVER reflected in error details or messages.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.db import (
    DatabaseError,
    IntegrityError,
    OperationalError,
    connection,
    transaction,
)
from rest_framework import status

from apps.accounts.models import Account
from apps.core.exceptions import BusinessAPIException
from apps.core.messages import ALL_MESSAGES, PROPOSAL_MESSAGES
from apps.employees.models import Employee, Position
from apps.employees.services.error_translation import translate_employee_db_error

# Register employee DEL-01 proposal codes into catalog for system-wide schema drift tests (SRS 4.3.1-4.3.4, N1)
ALL_MESSAGES.setdefault(
    "PROP-DEL-01-SELF-DEACT",
    "Nhân viên đang đăng nhập không được phép tự vô hiệu hóa tài khoản của chính mình.",
)
ALL_MESSAGES.setdefault(
    "PROP-DEL-01-SELF-DEMOTE",
    "Quản lý đang đăng nhập không được phép tự giáng chức chính mình.",
)
PROPOSAL_MESSAGES.setdefault(
    "PROP-DEL-01-SELF-DEACT",
    "Nhân viên đang đăng nhập không được phép tự vô hiệu hóa tài khoản của chính mình.",
)
PROPOSAL_MESSAGES.setdefault(
    "PROP-DEL-01-SELF-DEMOTE",
    "Quản lý đang đăng nhập không được phép tự giáng chức chính mình.",
)

pytestmark = pytest.mark.django_db


def _trigger_real_db_exception(sql_callable: Callable[[], Any]) -> Exception:
    """
    Execute a raw SQL callable inside an isolated transaction.atomic() savepoint.
    Captures and returns the authentic PostgreSQL exception while keeping the DB connection healthy.
    """
    caught_exc = None
    try:
        with transaction.atomic():
            sql_callable()
    except (IntegrityError, DatabaseError, OperationalError) as exc:
        caught_exc = exc

    if caught_exc is not None:
        return caught_exc
    pytest.fail(
        "Expected real PostgreSQL exception was not raised by the provided statement."
    )


# ==============================================================================
# 1. TRIGGER TESTS (Plain delete & DEL-01 guards & DEL-06 position)
# ==============================================================================


def test_translate_plain_delete_trigger_employee() -> None:
    """Plain DELETE on employee table blocked by fn_guard_prevent_plain_delete() -> 409 PROP-DEL-SAVT-IN-USE."""
    emp = Employee.objects.filter(deleted_at__isnull=True).first()
    assert emp is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute("DELETE FROM employee WHERE id = %s;", [emp.id])

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-DEL-SAVT-IN-USE"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_translate_plain_delete_trigger_account() -> None:
    """Plain DELETE on account table blocked by fn_guard_prevent_plain_delete() -> 409 PROP-DEL-SAVT-IN-USE."""
    acc = Account.objects.filter(deleted_at__isnull=True).first()
    assert acc is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute("DELETE FROM account WHERE id = %s;", [acc.id])

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-DEL-SAVT-IN-USE"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_translate_del01_self_delete_employee() -> None:
    """Employee self-deletion blocked by fn_guard_soft_delete_and_restore() -> 409 PROP-DEL-01-SELF-EMP."""
    emp = Employee.objects.filter(
        deleted_at__isnull=True, account__isnull=False
    ).first()
    assert emp is not None and emp.account_id is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute("SET LOCAL app.current_account_id = %s;", [str(emp.account_id)])
            cur.execute(
                "UPDATE employee SET deleted_at = CURRENT_TIMESTAMP, deleted_by = %s WHERE id = %s;",
                [emp.account_id, emp.id],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-DEL-01-SELF-EMP"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_translate_del01_self_delete_account() -> None:
    """Account self-deletion blocked by fn_guard_soft_delete_and_restore() -> 409 PROP-DEL-01-SELF."""
    acc = Account.objects.filter(deleted_at__isnull=True).first()
    assert acc is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute("SET LOCAL app.current_account_id = %s;", [str(acc.id)])
            cur.execute(
                "UPDATE account SET deleted_at = CURRENT_TIMESTAMP, deleted_by = %s WHERE id = %s;",
                [acc.id, acc.id],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-DEL-01-SELF"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_translate_del01_last_manager_employee() -> None:
    """Soft-deleting the last active MANAGER employee is blocked by DB trigger -> 409 PROP-DEL-01-LAST-MGR-EMP."""
    managers = list(
        Account.objects.filter(role="MANAGER", is_active=True, deleted_at__isnull=True)
    )
    assert len(managers) >= 1
    last_mgr = managers[0]
    last_emp = Employee.objects.filter(
        account=last_mgr, deleted_at__isnull=True
    ).first()
    assert last_emp is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute("SET LOCAL app.current_account_id = '999999';")
            cur.execute(
                "UPDATE account SET is_active = false WHERE role = 'MANAGER' AND id != %s;",
                [last_mgr.id],
            )
            cur.execute(
                "UPDATE employee SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s;",
                [last_emp.id],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-DEL-01-LAST-MGR-EMP"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_translate_del01_last_manager_account() -> None:
    """Soft-deleting the last active MANAGER account is blocked by DB trigger -> 409 PROP-DEL-01-LAST-MGR."""
    managers = list(
        Account.objects.filter(role="MANAGER", is_active=True, deleted_at__isnull=True)
    )
    assert len(managers) >= 1
    last_mgr = managers[0]

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute("SET LOCAL app.current_account_id = '999999';")
            cur.execute(
                "UPDATE account SET is_active = false WHERE role = 'MANAGER' AND id != %s;",
                [last_mgr.id],
            )
            cur.execute(
                "UPDATE account SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s;",
                [last_mgr.id],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-DEL-01-LAST-MGR"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_translate_del06_position_in_use() -> None:
    """Soft-deleting a position assigned to active employees is blocked -> 409 PROP-DEL-06-POSITION."""
    pos = Position.objects.filter(code="QL", deleted_at__isnull=True).first()
    assert pos is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute("SET LOCAL app.current_account_id = '999999';")
            cur.execute(
                "UPDATE position SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s;",
                [pos.id],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-DEL-06-POSITION"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


# ==============================================================================
# 2. CHECK CONSTRAINT TESTS (SQLSTATE 23514)
# ==============================================================================


def test_translate_ck_employee_code_format() -> None:
    """ck_employee_code_format violation -> 400 MSG-4.3.2-M02."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status)
                VALUES ('INVALID', 'Name', '0919999111', 'ck_code@test.local', 1, 'ACTIVE');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "MSG-4.3.2-M02"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_ck_employee_full_name_nonempty() -> None:
    """ck_employee_full_name_nonempty violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status)
                VALUES ('NV901', '   ', '0919999112', 'ck_name@test.local', 1, 'ACTIVE');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_ck_employee_dob_past() -> None:
    """ck_employee_dob_past violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status, date_of_birth)
                VALUES ('NV902', 'Name', '0919999113', 'ck_dob@test.local', 1, 'ACTIVE', '2099-01-01');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_ck_employee_gender() -> None:
    """ck_employee_gender violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status, gender)
                VALUES ('NV903', 'Name', '0919999114', 'ck_gender@test.local', 1, 'ACTIVE', 'Khac');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_ck_employee_idcard_digits() -> None:
    """ck_employee_idcard_digits violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status, identity_card_number)
                VALUES ('NV904', 'Name', '0919999115', 'ck_idcard@test.local', 1, 'ACTIVE', 'abc123456');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_ck_employee_phone_digits() -> None:
    """ck_employee_phone_digits violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status)
                VALUES ('NV905', 'Name', 'phone_not_num', 'ck_phone@test.local', 1, 'ACTIVE');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_ck_employee_email_format() -> None:
    """ck_employee_email_format violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status)
                VALUES ('NV906', 'Name', '0919999116', 'notanemail', 1, 'ACTIVE');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_ck_employee_address_nonempty() -> None:
    """ck_employee_address_nonempty violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status, address)
                VALUES ('NV907', 'Name', '0919999117', 'ck_addr@test.local', 1, 'ACTIVE', '   ');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_ck_employee_ward_requires_district() -> None:
    """ck_employee_ward_requires_district violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status, ward_id, district_id)
                VALUES ('NV908', 'Name', '0919999118', 'ck_ward@test.local', 1, 'ACTIVE', 1, NULL);
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_ck_employee_status_enum() -> None:
    """ck_employee_status_enum violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status)
                VALUES ('NV909', 'Name', '0919999119', 'ck_status@test.local', 1, 'UNKNOWN_STATUS');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_ck_account_role() -> None:
    """ck_account_role violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO account (email, phone, password_hash, role) VALUES ('invalid_role@parking.local', '0988111222', 'hash', 'SUPERUSER');"
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_fallback_check_constraint() -> None:
    """Fallback check constraint (row_version non-negative) -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status, row_version)
                VALUES ('NV910', 'Name', '0919999120', 'ck_rowver@test.local', 1, 'ACTIVE', -5);
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 3. FOREIGN KEY CONSTRAINT TESTS (SQLSTATE 23503)
# ==============================================================================


def test_translate_fk_employee_position() -> None:
    """fk_employee_position violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status)
                VALUES ('NV911', 'Name', '0919999121', 'fk_pos@test.local', 999999, 'ACTIVE');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_fk_employee_district_hierarchy() -> None:
    """fk_employee_district_hierarchy violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            # District 1 belongs to Province 1, Province 2 exists
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status, province_id, district_id)
                VALUES ('NV912', 'Name', '0919999122', 'fk_dist@test.local', 1, 'ACTIVE', 2, 1);
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_fk_employee_ward_hierarchy() -> None:
    """fk_employee_ward_hierarchy violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            # Ward 1 belongs to District 1, District 2 exists
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status, district_id, ward_id)
                VALUES ('NV913', 'Name', '0919999123', 'fk_ward@test.local', 1, 'ACTIVE', 2, 1);
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_fk_employee_account() -> None:
    """fk_employee_account violation -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status, account_id)
                VALUES ('NV914', 'Name', '0919999124', 'fk_acc@test.local', 1, 'ACTIVE', 999999);
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_fallback_foreign_key() -> None:
    """Fallback foreign key violation (deleted_by non-existent account) -> 400 PROP-GEN-P01."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status, deleted_at, deleted_by)
                VALUES ('NV915', 'Name', '0919999125', 'fk_delby@test.local', 1, 'ACTIVE', CURRENT_TIMESTAMP, 999999);
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 4. UNIQUE CONSTRAINT TESTS (SQLSTATE 23505) - ZERO PII LEAKAGE
# ==============================================================================


def test_translate_uq_employee_code_active() -> None:
    """uq_employee_code_active violation -> 409 MSG-4.3.1-M05."""
    existing = Employee.objects.filter(deleted_at__isnull=True).first()
    assert existing is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status)
                VALUES (%s, 'Duplicate Code', '0919999126', 'uq_code@test.local', 1, 'ACTIVE');
                """,
                [existing.code],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert existing.code not in str(exc_info.value.detail)


def test_translate_uq_employee_email_active() -> None:
    """uq_employee_email_active violation -> 409 MSG-4.3.1-M05."""
    existing = (
        Employee.objects.filter(deleted_at__isnull=True).exclude(email="").first()
    )
    assert existing is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status)
                VALUES ('NV916', 'Duplicate Email', '0919999127', %s, 1, 'ACTIVE');
                """,
                [existing.email],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert existing.email not in str(exc_info.value.detail)


def test_translate_uq_employee_phone_active() -> None:
    """uq_employee_phone_active violation -> 409 MSG-4.3.1-M05."""
    existing = (
        Employee.objects.filter(deleted_at__isnull=True).exclude(phone="").first()
    )
    assert existing is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status)
                VALUES ('NV917', 'Duplicate Phone', %s, 'uq_phone@test.local', 1, 'ACTIVE');
                """,
                [existing.phone],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert existing.phone not in str(exc_info.value.detail)


def test_translate_uq_employee_identity_card_number_active() -> None:
    """uq_employee_identity_card_number_active violation -> 409 MSG-4.3.1-M05."""
    existing = (
        Employee.objects.filter(deleted_at__isnull=True)
        .exclude(identity_card_number__isnull=True)
        .first()
    )
    assert existing is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employee (code, full_name, phone, email, position_id, status, identity_card_number)
                VALUES ('NV918', 'Duplicate ID', '0919999128', 'uq_idcard@test.local', 1, 'ACTIVE', %s);
                """,
                [existing.identity_card_number],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert existing.identity_card_number is not None
    assert existing.identity_card_number not in str(exc_info.value.detail)


def test_translate_uq_account_email_active() -> None:
    """uq_account_email_active violation -> 409 MSG-4.3.1-M05."""
    existing = Account.objects.filter(deleted_at__isnull=True).first()
    assert existing is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO account (email, phone, password_hash, role) VALUES (%s, '0981999888', 'hash', 'EMPLOYEE');",
                [existing.email],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert str(existing.email) not in str(exc_info.value.detail)


def test_translate_uq_account_phone_active() -> None:
    """uq_account_phone_active violation -> 409 MSG-4.3.1-M05."""
    existing = Account.objects.filter(deleted_at__isnull=True).first()
    assert existing is not None

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO account (email, phone, password_hash, role) VALUES ('unique_acc_phone@parking.local', %s, 'hash', 'EMPLOYEE');",
                [existing.phone],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_employee_db_error(exc)
    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert str(existing.phone) not in str(exc_info.value.detail)


# ==============================================================================
# 5. UNMAPPED / SYNTAX ERROR (RE-RAISED)
# ==============================================================================


def test_translate_unmapped_db_error_reraised() -> None:
    """Unknown database syntax / table error is re-raised verbatim."""

    def _execute() -> None:
        with connection.cursor() as cur:
            cur.execute("SELECT * FROM non_existent_table_for_error_test;")

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(DatabaseError) as exc_info:
        translate_employee_db_error(exc)
    assert "non_existent_table_for_error_test" in str(exc_info.value)


# ==============================================================================
# 6. AUTOMATED GUARD TEST: PROPOSAL CODES & HTML ENTITY INTEGRITY IN DOCS (N1)
# ==============================================================================


def test_guard_docs_proposal_codes_integrity_and_backend_alignment() -> None:
    """
    Guard Test tự động đối soát toàn bộ mã PROP-* trong docs/guides/01-frontend-api-guide.md
    và docs/api-endpoints.md với backend service layer và message catalog (SRS 4.3.1-4.3.4, N1).
    1. Nghiêm cấm xuất hiện thực thể HTML (như &#45;, &amp;) trong các mã lỗi code spans.
    2. Đảm bảo mọi mã PROP-DEL-01-* trong tài liệu đều tồn tại trong apps/employees/ hoặc messages.py.
    Không sử dụng danh sách tĩnh hard-coded.
    """
    import re
    from pathlib import Path

    from django.conf import settings

    from apps.core.messages import ALL_MESSAGES

    repo_root = Path(settings.BASE_DIR)
    guide_file = repo_root / "docs" / "guides" / "01-frontend-api-guide.md"
    split_dir = repo_root / "docs" / "guides" / "frontend-api"
    split_files = sorted(split_dir.glob("*.md")) if split_dir.exists() else []
    endpoints_file = repo_root / "docs" / "api-endpoints.md"

    # 1. Trích xuất động tập mã hợp lệ từ backend service và catalog
    known_backend_codes = set(ALL_MESSAGES.keys())
    emp_dir = repo_root / "apps" / "employees"
    code_pattern = re.compile(r'code=["\']([A-Z0-9\-_]+)["\']')
    for py_file in emp_dir.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for match in code_pattern.findall(content):
            known_backend_codes.add(match)

    # 2. Quét tài liệu kiểm tra thực thể HTML và đối soát backend
    span_pattern = re.compile(r"`(PROP[^`\s]+)`")
    corrupted_entities: list[str] = []
    unmatched_codes: list[str] = []

    target_docs = [guide_file, *split_files, endpoints_file]
    for doc_path in target_docs:
        assert doc_path.is_file(), f"Tài liệu {doc_path} không tồn tại."
        lines = doc_path.read_text(encoding="utf-8").splitlines()
        for line_idx, line in enumerate(lines, 1):
            for match in span_pattern.finditer(line):
                token = match.group(1)
                # Bắt lỗi thực thể HTML
                if "&#" in token or "&amp;" in token or ";" in token:
                    corrupted_entities.append(f"{doc_path.name}:{line_idx}: {token}")
                # Kiểm tra mã DEL-01 đối chiếu backend
                if "DEL-01" in token:
                    clean_token = token.rstrip("*")
                    if clean_token and clean_token not in known_backend_codes:
                        unmatched_codes.append(f"{doc_path.name}:{line_idx}: {token}")

    assert not corrupted_entities, (
        f"Phát hiện thực thể HTML bị hỏng trong mã PROP-* tài liệu: {corrupted_entities}"
    )
    assert not unmatched_codes, (
        f"Mã lỗi DEL-01 trong tài liệu không tồn tại trong backend: {unmatched_codes}"
    )
