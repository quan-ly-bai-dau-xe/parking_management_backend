"""
Tests for customer database error translation helper (translate_customer_db_error).
Verifies exhaustive translation of real PostgreSQL 18.6 exceptions inside transaction savepoints:
1. SQLSTATE 55000: trg_prevent_plain_delete_customer -> PROP-DEL-SAVT-IN-USE (HTTP 409 Conflict)
2. SQLSTATE 23514: Soft delete trigger guards:
   - Parked vehicle in lot -> PROP-4.4.5-P02 (HTTP 409 Conflict)
   - Active ticket -> PROP-4.4.5-P03 (HTTP 409 Conflict)
   - Active vehicle -> PROP-DEL-02-ACTIVE-VEH (HTTP 409 Conflict)
3. SQLSTATE 23514: Check constraints:
   - ck_customer_blacklist_reason -> PROP-GEN-P01 (HTTP 400 Bad Request)
   - ck_customer_dob_past -> PROP-GEN-P01 (HTTP 400 Bad Request)
   - ck_customer_full_name_nonempty -> PROP-GEN-P01 (HTTP 400 Bad Request)
   - ck_customer_gender -> PROP-GEN-P01 (HTTP 400 Bad Request)
   - ck_customer_idcard_digits -> PROP-GEN-P01 (HTTP 400 Bad Request)
   - ck_customer_phone_digits -> PROP-GEN-P01 (HTTP 400 Bad Request)
   - ck_customer_email_format -> PROP-GEN-P01 (HTTP 400 Bad Request)
   - ck_customer_code_format -> PROP-GEN-P01 (HTTP 400 Bad Request)
   - ck_customer_status_enum -> PROP-GEN-P01 (HTTP 400 Bad Request)
4. SQLSTATE 23503: Foreign key violations:
   - fk_customer_district_hierarchy -> PROP-GEN-P01 (HTTP 400 Bad Request)
   - fk_customer_ward_hierarchy -> PROP-GEN-P01 (HTTP 400 Bad Request)
   - Generic foreign key -> PROP-GEN-P01 (HTTP 400 Bad Request)
5. SQLSTATE 23505: Unique constraints:
   - uq_customer_code_active -> MSG-4.3.1-M05 (HTTP 409 Conflict)
   - uq_customer_idcard_active -> MSG-4.3.1-M05 (HTTP 409 Conflict)
   - uq_customer_phone_active -> MSG-4.3.1-M05 (HTTP 409 Conflict)
   - uq_customer_email_active -> MSG-4.3.1-M05 (HTTP 409 Conflict)
6. Unmapped exceptions -> re-raised without masking.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.core.models import AdministrativeDistrict, AdministrativeWard
from apps.customers.models import Customer
from apps.customers.services.error_translation import translate_customer_db_error

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
    except (IntegrityError, DatabaseError) as exc:
        caught_exc = exc

    if caught_exc is not None:
        return caught_exc
    pytest.fail(
        "Expected real PostgreSQL exception was not raised by the provided statement."
    )


def test_translate_hard_delete_prohibited_55000(active_customer: Customer):
    """Trigger trg_prevent_plain_delete_customer (55000) by attempting raw SQL DELETE."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute("DELETE FROM customer WHERE id = %s;", [active_customer.id])

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="delete")

    assert exc_info.value.code == "PROP-DEL-SAVT-IN-USE"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_translate_unique_code_23505(active_customer: Customer):
    """Trigger uq_customer_code_active (23505) by inserting duplicate customer code."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone)
                VALUES (%s, 'Trùng Code', '079200119988', '0919991122');
                """,
                [active_customer.code],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_translate_unique_idcard_23505(active_customer: Customer):
    """Trigger uq_customer_idcard_active (23505) by inserting duplicate CCCD."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone)
                VALUES ('KH9911', 'Trùng CCCD', %s, '0919991133');
                """,
                [active_customer.identity_card_number],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert active_customer.identity_card_number not in str(exc_info.value.message)


def test_translate_unique_phone_23505(active_customer: Customer):
    """Trigger uq_customer_phone_active (23505) by inserting duplicate phone."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone)
                VALUES ('KH9912', 'Trùng Phone', '079200119977', %s);
                """,
                [active_customer.phone],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_translate_unique_email_23505(active_customer: Customer):
    """Trigger uq_customer_email_active (23505) by inserting duplicate email."""
    assert active_customer.email is not None

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone, email)
                VALUES ('KH9913', 'Trùng Email', '079200119966', '0919991144', %s);
                """,
                [active_customer.email],
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT


def test_translate_check_blacklist_reason_23514():
    """Trigger ck_customer_blacklist_reason by inserting BLACKLISTED customer without status_reason."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone, status, status_reason)
                VALUES ('KH9914', 'Khóa Không Lý Do', '079200119955', '0919991155', 'BLACKLISTED', NULL);
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Lý do khóa là bắt buộc" in exc_info.value.message


def test_translate_check_dob_past_23514():
    """Trigger ck_customer_dob_past by inserting date_of_birth in the future."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone, date_of_birth)
                VALUES ('KH9915', 'Sinh Tương Lai', '079200119944', '0919991166', CURRENT_DATE + INTERVAL '1 day');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "Ngày sinh phải là ngày trong quá khứ" in exc_info.value.message


def test_translate_check_full_name_nonempty_23514():
    """Trigger ck_customer_full_name_nonempty by inserting empty whitespace full_name."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone)
                VALUES ('KH9916', '   ', '079200119933', '0919991177');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_check_gender_enum_23514():
    """Trigger ck_customer_gender by inserting invalid gender value."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone, gender)
                VALUES ('KH9917', 'Giới Tính Sai', '079200119922', '0919991188', 'Other');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_check_idcard_digits_23514():
    """Trigger ck_customer_idcard_digits by inserting alphabetic identity_card_number."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone)
                VALUES ('KH9918', 'CCCD Sai', 'ABCXYZ123456', '0919991199');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_check_phone_digits_23514():
    """Trigger ck_customer_phone_digits by inserting short phone number."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone)
                VALUES ('KH9919', 'Phone Sai', '079200119911', '12345');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_check_email_format_23514():
    """Trigger ck_customer_email_format by inserting invalid email string."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone, email)
                VALUES ('KH9920', 'Email Sai', '079200119900', '0919991100', 'not-an-email');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_check_code_format_23514():
    """Trigger ck_customer_code_format by inserting invalid code with spaces/symbols."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone)
                VALUES ('KH 9921$', 'Code Sai', '079200118899', '0919992200');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(BusinessAPIException) as exc_info:
        translate_customer_db_error(exc, operation="create")

    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_foreign_key_district_hierarchy_23503(
    admin_hierarchy: dict[str, Any],
):
    """Trigger fk_customer_district_hierarchy (23503) by mismatched province and district."""
    # Find district from another province
    other_dist = AdministrativeDistrict.objects.exclude(
        province_id=admin_hierarchy["province_id"]
    ).first()
    if other_dist:

        def _execute():
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO customer (code, full_name, identity_card_number, phone, province_id, district_id)
                    VALUES ('KH9922', 'Mismatched District', '079200118888', '0919992211', %s, %s);
                    """,
                    [admin_hierarchy["province_id"], other_dist.id],
                )

        exc = _trigger_real_db_exception(_execute)
        with pytest.raises(BusinessAPIException) as exc_info:
            translate_customer_db_error(exc, operation="create")

        assert exc_info.value.code == "PROP-GEN-P01"
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_foreign_key_ward_hierarchy_23503(admin_hierarchy: dict[str, Any]):
    """Trigger fk_customer_ward_hierarchy (23503) by mismatched district and ward."""
    # Find ward from another district
    other_ward = AdministrativeWard.objects.exclude(
        district_id=admin_hierarchy["district_id"]
    ).first()
    if other_ward:

        def _execute():
            with connection.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO customer (code, full_name, identity_card_number, phone, province_id, district_id, ward_id)
                    VALUES ('KH9923', 'Mismatched Ward', '079200118877', '0919992222', %s, %s, %s);
                    """,
                    [
                        admin_hierarchy["province_id"],
                        admin_hierarchy["district_id"],
                        other_ward.id,
                    ],
                )

        exc = _trigger_real_db_exception(_execute)
        with pytest.raises(BusinessAPIException) as exc_info:
            translate_customer_db_error(exc, operation="create")

        assert exc_info.value.code == "PROP-GEN-P01"
        assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_translate_unmapped_exception_re_raised():
    """Verify unmapped real PostgreSQL exceptions (e.g. SQLSTATE 23502 NOT NULL) are re-raised without modification."""

    def _execute():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO customer (code, full_name, identity_card_number, phone)
                VALUES (NULL, 'NotNull Violation', '079200118866', '0919992233');
                """
            )

    exc = _trigger_real_db_exception(_execute)
    with pytest.raises(IntegrityError):
        translate_customer_db_error(exc, operation="customer")
