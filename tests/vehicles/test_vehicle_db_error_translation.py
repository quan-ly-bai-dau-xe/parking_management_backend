"""
Tests for vehicle database error translation helper (_translate_vehicle_db_error).
Verifies exhaustive translation of real PostgreSQL 18.6 exceptions inside transaction savepoints:
1. uq_vehicle_code_active (SQLSTATE 23505) -> MSG-4.3.1-M05 (HTTP 409 Conflict)
2. uq_vehicle_license_plate_active (SQLSTATE 23505) -> MSG-4.3.1-M05 (HTTP 409 Conflict)
3. fk_vehicle_customer (SQLSTATE 23503) -> PROP-4.4.4-P02 (HTTP 400 Bad Request)
4. fk_vehicle_type (SQLSTATE 23503) -> PROP-GEN-P01 (HTTP 400 Bad Request)
5. fk_ticket_vehicle_customer (SQLSTATE 23503) -> PROP-VEH-OWNER-CHANGE-CONFLICT (HTTP 409 Conflict)
6. ck_vehicle_license_plate_format (SQLSTATE 23514) -> PROP-4.5.1-P16 (HTTP 400 Bad Request)
7. Unknown database error (SQLSTATE 42703 / syntax) -> re-raised without masking
8. Other check constraint (ck_vehicle_row_version_positive) -> re-raised
9. Service-layer and end-to-end API integration (create_vehicle & update_vehicle exception handling)

Zero mocks: all exceptions are authentic PostgreSQL errors caught within transaction.atomic() savepoints.
"""

from collections.abc import Callable
from typing import Any

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle
from apps.vehicles.services.vehicles import (
    PROP_VEH_OWNER_CHANGE_CONFLICT_CODE,
    PROP_VEH_OWNER_CHANGE_CONFLICT_MSG,
    _translate_vehicle_db_error,
    create_vehicle,
    update_vehicle,
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
    except (IntegrityError, DatabaseError) as exc:
        caught_exc = exc

    if caught_exc is not None:
        return caught_exc
    pytest.fail(
        "Expected real PostgreSQL exception was not raised by the provided statement."
    )


# ==============================================================================
# Helper Unit Tests with Real PostgreSQL Exceptions (Savepoint-Isolated)
# ==============================================================================


def test_translate_db_error_unique_code_active(active_customer, car_type):
    """
    Trigger uq_vehicle_code_active violation (SQLSTATE 23505) by inserting an existing active code.
    Expects BusinessAPIException with code MSG-4.3.1-M05, HTTP 409 Conflict.
    """
    existing = Vehicle.objects.filter(deleted_at__isnull=True).order_by("id").first()
    assert existing is not None

    def _execute_violation():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vehicle (code, license_plate, model_name, vehicle_type_id, customer_id)
                VALUES (%s, '51K-990.01', 'Test Code Collide', %s, %s);
                """,
                [existing.code, car_type.id, active_customer.id],
            )

    exc = _trigger_real_db_exception(_execute_violation)
    assert isinstance(exc, IntegrityError)
    assert "uq_vehicle_code_active" in str(exc)

    with pytest.raises(BusinessAPIException) as exc_info:
        _translate_vehicle_db_error(exc, operation="create")

    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert (
        exc_info.value.message
        == "Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp."
    )


def test_translate_db_error_unique_license_plate_active(active_customer, car_type):
    """
    Trigger uq_vehicle_license_plate_active violation (SQLSTATE 23505) by inserting an existing
    active license plate with a new vehicle code.
    Expects BusinessAPIException with code MSG-4.3.1-M05, HTTP 409 Conflict.
    """
    existing = Vehicle.objects.filter(deleted_at__isnull=True).order_by("id").first()
    assert existing is not None

    def _execute_violation():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vehicle (code, license_plate, model_name, vehicle_type_id, customer_id)
                VALUES ('XE-UNQ-01', %s, 'Test Plate Collide', %s, %s);
                """,
                [existing.license_plate, car_type.id, active_customer.id],
            )

    exc = _trigger_real_db_exception(_execute_violation)
    assert isinstance(exc, IntegrityError)
    assert "uq_vehicle_license_plate_active" in str(exc)

    with pytest.raises(BusinessAPIException) as exc_info:
        _translate_vehicle_db_error(exc, operation="create")

    assert exc_info.value.code == "MSG-4.3.1-M05"
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert (
        exc_info.value.message
        == "Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp."
    )


def test_translate_db_error_fk_vehicle_customer(car_type):
    """
    Trigger fk_vehicle_customer violation (SQLSTATE 23503) by inserting a non-existent customer_id.
    Expects BusinessAPIException with code PROP-4.4.4-P02, HTTP 400 Bad Request.
    """

    def _execute_violation():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vehicle (code, license_plate, model_name, vehicle_type_id, customer_id)
                VALUES ('XE-FKC-01', '51K-990.02', 'Test FK Customer', %s, 999999999);
                """,
                [car_type.id],
            )

    exc = _trigger_real_db_exception(_execute_violation)
    assert isinstance(exc, IntegrityError)
    assert "fk_vehicle_customer" in str(exc)

    with pytest.raises(BusinessAPIException) as exc_info:
        _translate_vehicle_db_error(exc, operation="create")

    assert exc_info.value.code == "PROP-4.4.4-P02"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert exc_info.value.message == "Khách hàng không tồn tại hoặc đã bị xóa."


def test_translate_db_error_fk_vehicle_type(active_customer):
    """
    Trigger fk_vehicle_type violation (SQLSTATE 23503) by inserting a non-existent vehicle_type_id.
    Expects BusinessAPIException with code PROP-GEN-P01, HTTP 400 Bad Request.
    """

    def _execute_violation():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vehicle (code, license_plate, model_name, vehicle_type_id, customer_id)
                VALUES ('XE-FKT-01', '51K-990.03', 'Test FK Type', 999999999, %s);
                """,
                [active_customer.id],
            )

    exc = _trigger_real_db_exception(_execute_violation)
    assert isinstance(exc, IntegrityError)
    assert "fk_vehicle_type" in str(exc)

    with pytest.raises(BusinessAPIException) as exc_info:
        _translate_vehicle_db_error(exc, operation="create")

    assert exc_info.value.code == "PROP-GEN-P01"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert (
        exc_info.value.message
        == "Loại xe không hợp lệ (hệ thống chỉ phục vụ Ô tô và Xe điện)."
    )
    assert exc_info.value.code != PROP_VEH_OWNER_CHANGE_CONFLICT_CODE


def test_translate_db_error_fk_ticket_vehicle_customer():
    """
    Trigger fk_ticket_vehicle_customer violation (SQLSTATE 23503) by updating customer_id
    on a vehicle that has a linked ticket record.
    Expects BusinessAPIException with code PROP-VEH-OWNER-CHANGE-CONFLICT, HTTP 409 Conflict.
    """
    ticket = (
        Ticket.objects.filter(deleted_at__isnull=True)
        .select_related("vehicle", "customer")
        .first()
    )
    assert ticket is not None, "Seed data must contain at least one ticket"

    other_customer = (
        Customer.objects.filter(deleted_at__isnull=True)
        .exclude(id=ticket.customer_id)
        .first()
    )
    assert other_customer is not None, (
        "Need another active customer to trigger owner change violation"
    )

    def _execute_violation():
        with connection.cursor() as cur:
            cur.execute(
                "UPDATE vehicle SET customer_id = %s WHERE id = %s;",
                [other_customer.id, ticket.vehicle_id],
            )

    exc = _trigger_real_db_exception(_execute_violation)
    assert isinstance(exc, IntegrityError)
    assert "fk_ticket_vehicle_customer" in str(exc)

    with pytest.raises(BusinessAPIException) as exc_info:
        _translate_vehicle_db_error(exc, operation="update")

    assert exc_info.value.code == PROP_VEH_OWNER_CHANGE_CONFLICT_CODE
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT
    assert exc_info.value.message == PROP_VEH_OWNER_CHANGE_CONFLICT_MSG


def test_translate_db_error_check_license_plate_format(active_customer, car_type):
    """
    Trigger ck_vehicle_license_plate_format check constraint violation (SQLSTATE 23514)
    by inserting a license plate containing a non-ASCII Vietnamese character ('Đ').
    Expects BusinessAPIException with code PROP-4.5.1-P16, HTTP 400 Bad Request.
    """

    def _execute_violation():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vehicle (code, license_plate, model_name, vehicle_type_id, customer_id)
                VALUES ('XE-CKF-01', '50LĐ-123.45', 'Test CK Format', %s, %s);
                """,
                [car_type.id, active_customer.id],
            )

    exc = _trigger_real_db_exception(_execute_violation)
    assert isinstance(exc, IntegrityError)
    assert "ck_vehicle_license_plate_format" in str(exc)

    with pytest.raises(BusinessAPIException) as exc_info:
        _translate_vehicle_db_error(exc, operation="create")

    assert exc_info.value.code == "PROP-4.5.1-P16"
    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST
    assert "danh mục quy chuẩn" in exc_info.value.message
    assert exc_info.value.details.get("syntax_status") == "INVALID_FORMAT"


def test_translate_db_error_unknown_error_reraised():
    """
    Trigger an unmapped database error (undefined column, SQLSTATE 42703).
    Expects helper to re-raise the original DatabaseError without masking.
    """

    def _execute_violation():
        with connection.cursor() as cur:
            cur.execute(
                "SELECT non_existent_column_for_testing_purposes FROM vehicle LIMIT 1;"
            )

    exc = _trigger_real_db_exception(_execute_violation)
    assert isinstance(exc, DatabaseError)

    with pytest.raises(DatabaseError) as exc_info:
        _translate_vehicle_db_error(exc, operation="create")

    assert exc_info.value is exc


def test_translate_db_error_other_check_constraint_reraised(active_customer, car_type):
    """
    Trigger another check constraint on vehicle (ck_vehicle_row_version_positive with row_version = 0).
    Expects helper to re-raise the original IntegrityError because it is not ck_vehicle_license_plate_format.
    """

    def _execute_violation():
        with connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO vehicle (code, license_plate, model_name, vehicle_type_id, customer_id, row_version)
                VALUES ('XE-CKR-01', '51K-990.04', 'Test CK RowVer', %s, %s, 0);
                """,
                [car_type.id, active_customer.id],
            )

    exc = _trigger_real_db_exception(_execute_violation)
    assert isinstance(exc, IntegrityError)
    assert "ck_vehicle_row_version_positive" in str(exc)

    with pytest.raises(IntegrityError) as exc_info:
        _translate_vehicle_db_error(exc, operation="create")

    assert exc_info.value is exc


# ==============================================================================
# Service Layer & End-to-End API Integration Tests (create_vehicle & update_vehicle)
# ==============================================================================


def test_create_vehicle_service_and_api_db_exception_caught(
    manager_client, active_customer, car_type
):
    """
    Verify that when PostgreSQL raises an IntegrityError (SQLSTATE 23505 on uq_vehicle_code_active)
    during INSERT inside create_vehicle, the try-except block catches it and translates it via
    _translate_vehicle_db_error into HTTP 409 MSG-4.3.1-M05 both at service level and via POST API.
    """
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(
                """
                CREATE OR REPLACE FUNCTION pg_temp.fn_force_vehicle_insert_uq()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'duplicate key value violates unique constraint "uq_vehicle_code_active"'
                        USING ERRCODE = '23505', CONSTRAINT = 'uq_vehicle_code_active';
                END;
                $$;
                CREATE TRIGGER trg_force_vehicle_insert_uq
                    BEFORE INSERT ON vehicle
                    FOR EACH ROW EXECUTE FUNCTION pg_temp.fn_force_vehicle_insert_uq();
                """
            )

        with pytest.raises(BusinessAPIException) as exc_info:
            create_vehicle(
                license_plate="51K-888.11",
                model_name="VinFast Test",
                vehicle_type_id=car_type.id,
                customer_id=active_customer.id,
            )

        assert exc_info.value.code == "MSG-4.3.1-M05"
        assert exc_info.value.status_code == status.HTTP_409_CONFLICT

        resp = manager_client.post(
            "/api/v1/vehicles/",
            {
                "license_plate": "51K-888.22",
                "model_name": "VinFast E2E",
                "vehicle_type_id": car_type.id,
                "customer_id": active_customer.id,
            },
            format="json",
        )
        assert resp.status_code == status.HTTP_409_CONFLICT
        assert resp.json()["code"] == "MSG-4.3.1-M05"

        with connection.cursor() as cur:
            cur.execute("DROP TRIGGER trg_force_vehicle_insert_uq ON vehicle;")


def test_update_vehicle_service_and_api_db_exception_caught(manager_client):
    """
    Verify that when a vehicle has only soft-deleted tickets (bypassing the active tickets.exists()
    pre-check) and has no open session or active reservation, updating customer_id hits PostgreSQL's
    table-level foreign key constraint fk_ticket_vehicle_customer (SQLSTATE 23503) at save() time,
    which update_vehicle catches and translates into HTTP 409 PROP-VEH-OWNER-CHANGE-CONFLICT both
    at service level and via PATCH /api/v1/vehicles/{id}/.
    """
    ticket = (
        Ticket.objects.filter(
            status="EXPIRED",
            deleted_at__isnull=True,
        )
        .select_related("vehicle", "customer")
        .first()
    )
    assert ticket is not None, "Seed data must contain at least one EXPIRED ticket"

    vehicle = ticket.vehicle
    # Close any open sessions and cancel active reservations first (DEL-04 guard), then soft-delete tickets
    vehicle.entry_exit_logs.filter(exit_time__isnull=True).update(
        exit_time=timezone.now(),
    )
    vehicle.reservations.filter(status="ACTIVE", deleted_at__isnull=True).update(
        status="CANCELLED"
    )
    Ticket.objects.filter(vehicle=vehicle).update(deleted_at=timezone.now())

    other_customer = (
        Customer.objects.filter(deleted_at__isnull=True)
        .exclude(id=vehicle.customer_id)
        .first()
    )
    assert other_customer is not None

    with pytest.raises(BusinessAPIException) as exc_info:
        update_vehicle(
            vehicle=vehicle,
            data={
                "row_version": vehicle.row_version,
                "customer_id": other_customer.id,
            },
        )

    assert exc_info.value.code == PROP_VEH_OWNER_CHANGE_CONFLICT_CODE
    assert exc_info.value.status_code == status.HTTP_409_CONFLICT

    vehicle.refresh_from_db()
    resp = manager_client.patch(
        f"/api/v1/vehicles/{vehicle.id}/",
        {
            "row_version": vehicle.row_version,
            "customer_id": other_customer.id,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.json()["code"] == PROP_VEH_OWNER_CHANGE_CONFLICT_CODE
