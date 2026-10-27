"""
Supplementary coverage tests for apps.customers to guarantee >= 95% line & branch coverage.
Covers:
- Model __str__ representations.
- Selectors branches: vehicle ticket remaining_days calculation, unannotated serializer fallbacks.
- Serializers validation edge cases: date_of_birth, gender, identity_card, phone, email, raw_name validators.
- Services administrative hierarchy validations (ward without district, district without province, invalid mappings).
- Error translation direct mapping branches (regex fallback, generic constraint checks).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework import serializers

from apps.core.exceptions import BusinessAPIException
from apps.core.models import (
    AdministrativeDistrict,
    AdministrativeWard,
)
from apps.customers.models import Customer
from apps.customers.selectors.customers import get_customer_by_id
from apps.customers.serializers.customers import (
    CustomerCreateSerializer,
    CustomerDetailSerializer,
    CustomerListSerializer,
    CustomerUpdateSerializer,
    validate_raw_name,
)
from apps.customers.services.customers import create_customer, update_customer
from apps.customers.services.error_translation import translate_customer_db_error
from apps.parking.models import ParkingSlot
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


def test_customer_model_str(active_customer: Customer):
    """Cover Customer.__str__ method."""
    assert (
        str(active_customer) == f"{active_customer.full_name} ({active_customer.code})"
    )


def test_validate_raw_name_edge_cases():
    """Cover validate_raw_name exception branches."""
    with pytest.raises(serializers.ValidationError, match="không được để trống"):
        validate_raw_name(None)

    with pytest.raises(serializers.ValidationError, match="phải là chuỗi ký tự"):
        validate_raw_name(12345)

    with pytest.raises(serializers.ValidationError, match="không được chứa ký tự NUL"):
        validate_raw_name("Nam\x00")

    with pytest.raises(
        serializers.ValidationError, match="không được vượt quá 45 ký tự"
    ):
        validate_raw_name("A" * 46)

    with pytest.raises(serializers.ValidationError, match="không được để trống"):
        validate_raw_name("   ")


def test_customer_list_serializer_unannotated_fallbacks(active_customer: Customer):
    """Cover CustomerListSerializer fallback methods when queryset annotations are absent."""
    serializer = CustomerListSerializer(active_customer)
    # Directly invoke serializer method fields on un-annotated instance
    assert isinstance(serializer.get_vehicles_count(active_customer), int)
    assert isinstance(serializer.get_has_active_ticket(active_customer), bool)


def test_customer_detail_serializer_null_administrative_units():
    """Cover CustomerDetailSerializer when administrative units are None."""
    cust = Customer(
        id=99991,
        code="KH99991",
        full_name="Khách Không Địa Giới",
        identity_card_number="079090009991",
        phone="0909999991",
        province=None,
        district=None,
        ward=None,
        status="ACTIVE",
        is_anonymized=False,
    )
    serializer = CustomerDetailSerializer(cust)
    assert serializer.get_province_name(cust) is None
    assert serializer.get_province(cust) is None
    assert serializer.get_district_name(cust) is None
    assert serializer.get_district(cust) is None
    assert serializer.get_ward_name(cust) is None
    assert serializer.get_ward(cust) is None


def test_customer_selector_remaining_days_calculation(car_type: VehicleType):
    """Cover remaining_days and expiration calculations in get_customer_by_id."""
    cust = Customer.objects.create(
        code="KHREM01",
        full_name="Khách Hàng Tính Ngày",
        identity_card_number="079090007771",
        phone="0907771111",
    )
    veh = Vehicle.objects.create(
        code="XE-REM01",
        license_plate="51K-666.11",
        model_name="VF5",
        vehicle_type=car_type,
        customer=cust,
    )
    now = timezone.now()
    ticket_template = Ticket.objects.filter(deleted_at__isnull=True).first()
    assert ticket_template is not None

    free_slot = (
        ParkingSlot.objects.filter(deleted_at__isnull=True)
        .exclude(
            tickets__status__in=["ACTIVE", "RENEWING"],
            tickets__deleted_at__isnull=True,
            tickets__effective_to__gt=now,
        )
        .first()
    )
    assert free_slot is not None

    Ticket.objects.create(
        code="TKT-REM01",
        customer=cust,
        vehicle=veh,
        slot=free_slot,
        ticket_type=ticket_template.ticket_type,
        price=ticket_template.price or 500000,
        effective_from=now - timedelta(days=2),
        effective_to=now + timedelta(days=5),
        status="ACTIVE",
    )

    detail_cust = get_customer_by_id(cust.id, now=now)
    assert detail_cust is not None
    annotated_vehicles = getattr(detail_cust, "annotated_vehicles", [])
    assert annotated_vehicles
    annotated_v = annotated_vehicles[0]
    assert annotated_v["ticket"] is not None
    assert annotated_v["ticket"]["remaining_days"] >= 4
    assert annotated_v["ticket"]["ticket_state"] == "expiring_soon"


def test_customer_create_serializer_validations():
    """Cover field validators in CustomerCreateSerializer."""
    # 1. Invalid date_of_birth in the future
    future_date = (timezone.now() + timezone.timedelta(days=2)).date().isoformat()
    s1 = CustomerCreateSerializer(
        data={
            "full_name": "Nguyễn Văn Test",
            "identity_card_number": "079090001122",
            "phone": "0901112233",
            "date_of_birth": future_date,
        }
    )
    assert not s1.is_valid()
    assert "date_of_birth" in s1.errors

    # 2. Invalid gender
    s2 = CustomerCreateSerializer(
        data={
            "full_name": "Nguyễn Văn Test",
            "identity_card_number": "079090001122",
            "phone": "0901112233",
            "gender": "Unknown",
        }
    )
    assert not s2.is_valid()
    assert "gender" in s2.errors

    # 3. Invalid identity_card_number (non-digits)
    s3 = CustomerCreateSerializer(
        data={
            "full_name": "Nguyễn Văn Test",
            "identity_card_number": "079090ABC122",
            "phone": "0901112233",
        }
    )
    assert not s3.is_valid()
    assert "identity_card_number" in s3.errors

    # 4. Invalid phone (too short)
    s4 = CustomerCreateSerializer(
        data={
            "full_name": "Nguyễn Văn Test",
            "identity_card_number": "079090001122",
            "phone": "09011",
        }
    )
    assert not s4.is_valid()
    assert "phone" in s4.errors

    # 5. Invalid email
    s5 = CustomerCreateSerializer(
        data={
            "full_name": "Nguyễn Văn Test",
            "identity_card_number": "079090001122",
            "phone": "0901112233",
            "email": "not-an-email",
        }
    )
    assert not s5.is_valid()
    assert "email" in s5.errors

    # 6. Invalid status enum
    s6 = CustomerCreateSerializer(
        data={
            "full_name": "Nguyễn Văn Test",
            "identity_card_number": "079090001122",
            "phone": "0901112233",
            "status": "INVALID_STATUS",
        }
    )
    assert not s6.is_valid()
    assert "status" in s6.errors


def test_customer_create_administrative_hierarchy_checks(admin_hierarchy: dict):
    """Cover service-layer administrative hierarchy validation errors in create_customer."""
    # 1. ward_id provided without district_id
    with pytest.raises(BusinessAPIException) as exc1:
        create_customer(
            {
                "full_name": "Test Hierarchy 1",
                "identity_card_number": "079090006611",
                "phone": "0906611001",
                "ward_id": admin_hierarchy["ward_id"],
                "district_id": None,
            }
        )
    assert exc1.value.code == "PROP-GEN-P01"
    assert "Cơ cấu địa giới hành chính không hợp lệ" in exc1.value.message

    # 2. district_id provided without province_id
    with pytest.raises(BusinessAPIException) as exc2:
        create_customer(
            {
                "full_name": "Test Hierarchy 2",
                "identity_card_number": "079090006612",
                "phone": "0906611002",
                "district_id": admin_hierarchy["district_id"],
                "province_id": None,
            }
        )
    assert exc2.value.code == "PROP-GEN-P01"
    assert "Cơ cấu địa giới hành chính không hợp lệ" in exc2.value.message

    # 3. ward not belonging to district
    other_ward = AdministrativeWard.objects.exclude(
        district_id=admin_hierarchy["district_id"]
    ).first()
    if other_ward:
        with pytest.raises(BusinessAPIException) as exc3:
            create_customer(
                {
                    "full_name": "Test Hierarchy 3",
                    "identity_card_number": "079090006613",
                    "phone": "0906611003",
                    "province_id": admin_hierarchy["province_id"],
                    "district_id": admin_hierarchy["district_id"],
                    "ward_id": other_ward.id,
                }
            )
        assert exc3.value.code == "PROP-GEN-P01"
        assert "Phường/Xã không thuộc Quận/Huyện" in exc3.value.message

    # 4. district not belonging to province
    other_dist = AdministrativeDistrict.objects.exclude(
        province_id=admin_hierarchy["province_id"]
    ).first()
    if other_dist:
        with pytest.raises(BusinessAPIException) as exc4:
            create_customer(
                {
                    "full_name": "Test Hierarchy 4",
                    "identity_card_number": "079090006614",
                    "phone": "0906611004",
                    "province_id": admin_hierarchy["province_id"],
                    "district_id": other_dist.id,
                }
            )
        assert exc4.value.code == "PROP-GEN-P01"
        assert "Quận/Huyện không thuộc Tỉnh/Thành phố" in exc4.value.message


def test_customer_update_administrative_hierarchy_checks(
    active_customer: Customer, admin_hierarchy: dict
):
    """Cover service-layer administrative hierarchy validation errors in update_customer."""
    # 1. ward provided but district cleared
    with pytest.raises(BusinessAPIException) as exc1:
        update_customer(
            active_customer.id,
            {
                "row_version": active_customer.row_version,
                "ward_id": admin_hierarchy["ward_id"],
                "district_id": None,
            },
        )
    assert exc1.value.code == "PROP-GEN-P01"

    # 2. district provided but province cleared
    with pytest.raises(BusinessAPIException) as exc2:
        update_customer(
            active_customer.id,
            {
                "row_version": active_customer.row_version,
                "district_id": admin_hierarchy["district_id"],
                "province_id": None,
            },
        )
    assert exc2.value.code == "PROP-GEN-P01"


def test_customer_detail_serializer_with_administrative_units(admin_hierarchy: dict):
    """Cover CustomerDetailSerializer get_district and get_ward when units exist."""
    cust = Customer(
        id=99992,
        code="KH99992",
        full_name="Khách Đủ Địa Giới",
        identity_card_number="079090009992",
        phone="0909999992",
        province=admin_hierarchy["province"],
        district=admin_hierarchy["district"],
        ward=admin_hierarchy["ward"],
        status="ACTIVE",
        is_anonymized=False,
    )
    cust_obj: Any = cust
    cust_obj.annotated_vehicles = []
    serializer = CustomerDetailSerializer(cust)
    assert serializer.get_province_name(cust) == admin_hierarchy["province"].name
    prov_dict = serializer.get_province(cust)
    assert prov_dict is not None
    assert prov_dict["id"] == admin_hierarchy["province"].id
    assert serializer.get_district_name(cust) == admin_hierarchy["district"].name
    dist_dict = serializer.get_district(cust)
    assert dist_dict is not None
    assert dist_dict["id"] == admin_hierarchy["district"].id
    assert serializer.get_ward_name(cust) == admin_hierarchy["ward"].name
    ward_dict = serializer.get_ward(cust)
    assert ward_dict is not None
    assert ward_dict["id"] == admin_hierarchy["ward"].id


def test_customer_serializers_format_validations():
    """Cover serializers format checks for code, identity card, phone, blacklist in create & update."""
    # 1. Code too long
    s_code_long = CustomerCreateSerializer(
        data={
            "code": "KH1234567890",
            "full_name": "Test",
            "identity_card_number": "079090001122",
            "phone": "0901112233",
        }
    )
    assert not s_code_long.is_valid()
    assert "code" in s_code_long.errors

    # 2. Code invalid regex format
    s_code_fmt = CustomerCreateSerializer(
        data={
            "code": "KH_123@",
            "full_name": "Test",
            "identity_card_number": "079090001122",
            "phone": "0901112233",
        }
    )
    assert not s_code_fmt.is_valid()
    assert "code" in s_code_fmt.errors

    # 3. Create: ward without district, district without province
    s_w_no_d = CustomerCreateSerializer(
        data={
            "full_name": "Test",
            "identity_card_number": "079090001122",
            "phone": "0901112233",
            "ward_id": 1,
            "district_id": None,
        }
    )
    assert not s_w_no_d.is_valid()

    s_d_no_p = CustomerCreateSerializer(
        data={
            "full_name": "Test",
            "identity_card_number": "079090001122",
            "phone": "0901112233",
            "district_id": 1,
            "province_id": None,
        }
    )
    assert not s_d_no_p.is_valid()

    # 4. Create: Blacklisted without reason
    s_bl = CustomerCreateSerializer(
        data={
            "full_name": "Test",
            "identity_card_number": "079090001122",
            "phone": "0901112233",
            "status": "BLACKLISTED",
            "status_reason": "",
        }
    )
    assert not s_bl.is_valid()

    # 5. Update serializer field validators
    future_date = (timezone.now() + timezone.timedelta(days=5)).date().isoformat()
    s_up = CustomerUpdateSerializer(
        data={
            "row_version": 1,
            "date_of_birth": future_date,
            "gender": "UnknownGender",
            "identity_card_number": "INVALID-ID",
            "phone": "123",
            "email": "invalid-email",
            "status": "BLACKLISTED",
            "status_reason": "",
            "ward_id": 1,
            "district_id": None,
        }
    )
    assert not s_up.is_valid()
    assert "date_of_birth" in s_up.errors
    assert "gender" in s_up.errors
    assert "identity_card_number" in s_up.errors
    assert "phone" in s_up.errors
    assert "email" in s_up.errors


def test_customer_serializers_and_services_remaining_branches(
    active_customer: Customer, admin_hierarchy: dict
):
    """Cover remaining validation and fallback branches in serializers and services."""
    from apps.customers.serializers.customers import CustomerFilterSerializer

    # 1. CustomerDetailSerializer.get_vehicles un-annotated fallback
    fresh_cust = Customer.objects.get(id=active_customer.id)
    detail_ser = CustomerDetailSerializer(fresh_cust)
    vehicles_list = detail_ser.get_vehicles(fresh_cust)
    assert isinstance(vehicles_list, list)

    # 2. CustomerCreateSerializer validate_code("") -> None, BLACKLISTED with reason
    s_empty_code = CustomerCreateSerializer(
        data={
            "code": "   ",
            "full_name": "Nguyễn Văn Hợp Lệ",
            "identity_card_number": "079090001122",
            "phone": "0901112233",
        }
    )
    assert s_empty_code.is_valid(), s_empty_code.errors
    assert s_empty_code.validated_data["code"] is None

    s_bl_ok = CustomerCreateSerializer(
        data={
            "full_name": "Nguyễn Văn Blacklist",
            "identity_card_number": "079090001123",
            "phone": "0901112234",
            "status": "BLACKLISTED",
            "status_reason": "Vi phạm nội quy bãi xe",
        }
    )
    assert s_bl_ok.is_valid(), s_bl_ok.errors

    # 3. CustomerCreateSerializer mismatched ward/district and district/province
    other_ward = AdministrativeWard.objects.exclude(
        district_id=admin_hierarchy["district_id"]
    ).first()
    other_dist = AdministrativeDistrict.objects.exclude(
        province_id=admin_hierarchy["province_id"]
    ).first()
    if other_ward and other_dist:
        s_mismatch = CustomerCreateSerializer(
            data={
                "full_name": "Nguyễn Văn Sai Địa Giới",
                "identity_card_number": "079090001124",
                "phone": "0901112235",
                "province_id": admin_hierarchy["province_id"],
                "district_id": other_dist.id,
                "ward_id": admin_hierarchy["ward_id"],
            }
        )
        assert not s_mismatch.is_valid()
        assert "ward_id" in s_mismatch.errors
        assert "district_id" in s_mismatch.errors

    # 4. CustomerUpdateSerializer valid past DOB, invalid status, and BLACKLISTED with reason
    s_up_valid_dob = CustomerUpdateSerializer(
        data={
            "row_version": 1,
            "date_of_birth": "1990-05-15",
            "status": "BLACKLISTED",
            "status_reason": "Khóa có lý do",
        }
    )
    assert s_up_valid_dob.is_valid(), s_up_valid_dob.errors

    s_up_bad_status = CustomerUpdateSerializer(
        data={
            "row_version": 1,
            "status": "NOT_A_VALID_STATUS",
        }
    )
    assert not s_up_bad_status.is_valid()
    assert "status" in s_up_bad_status.errors

    # 5. CustomerFilterSerializer invalid status and empty status
    f_bad = CustomerFilterSerializer(data={"status": "INVALID_STATUS"})
    assert not f_bad.is_valid()
    assert "status" in f_bad.errors

    f_empty = CustomerFilterSerializer(data={"status": "   "})
    assert f_empty.is_valid(), f_empty.errors
    assert f_empty.validated_data["status"] == ""

    # 6. update_customer mismatched district/province and unchanged CCCD/phone
    if other_dist:
        with pytest.raises(BusinessAPIException) as exc_dist:
            update_customer(
                active_customer.id,
                {
                    "row_version": active_customer.row_version,
                    "province_id": admin_hierarchy["province_id"],
                    "district_id": other_dist.id,
                    "ward_id": None,
                },
            )
        assert exc_dist.value.code == "PROP-GEN-P01"

    same_updated = update_customer(
        active_customer.id,
        {
            "row_version": active_customer.row_version,
            "identity_card_number": active_customer.identity_card_number,
            "phone": active_customer.phone,
        },
    )
    assert same_updated.id == active_customer.id


def test_customer_services_db_error_handlers_real_postgres(active_customer: Customer):
    """Exercise create_customer and update_customer except blocks with real PostgreSQL trigger exceptions."""
    from django.db import connection, transaction

    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute(
                """
                CREATE OR REPLACE FUNCTION pg_temp.raise_customer_23505()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'duplicate key value violates unique constraint "uq_customer_idcard_active"'
                        USING ERRCODE = '23505', CONSTRAINT = 'uq_customer_idcard_active';
                END;
                $$;
                CREATE TRIGGER trg_temp_customer_23505
                BEFORE INSERT OR UPDATE ON customer
                FOR EACH ROW EXECUTE FUNCTION pg_temp.raise_customer_23505();
                """
            )
        try:
            with pytest.raises(BusinessAPIException) as exc_create:
                create_customer(
                    {
                        "full_name": "Trigger Create Test",
                        "identity_card_number": "079090008811",
                        "phone": "0908811001",
                    }
                )
            assert exc_create.value.code == "MSG-4.3.1-M05"
            assert exc_create.value.status_code == 409

            with pytest.raises(BusinessAPIException) as exc_update:
                update_customer(
                    active_customer.id,
                    {
                        "row_version": active_customer.row_version,
                        "full_name": "Trigger Update Test",
                    },
                )
            assert exc_update.value.code == "MSG-4.3.1-M05"
            assert exc_update.value.status_code == 409
        finally:
            with connection.cursor() as cur:
                cur.execute(
                    "DROP TRIGGER IF EXISTS trg_temp_customer_23505 ON customer;"
                )


def test_customer_services_direct_exceptions(active_customer: Customer):
    """Cover remaining service exception branches directly."""
    # 1. create_customer with BLACKLISTED without reason
    with pytest.raises(BusinessAPIException) as exc1:
        create_customer(
            {
                "full_name": "Test Blacklist Direct",
                "identity_card_number": "079090009955",
                "phone": "0909955001",
                "status": "BLACKLISTED",
                "status_reason": "",
            }
        )
    assert exc1.value.code == "PROP-GEN-P01"

    # 2. update_customer missing row_version
    with pytest.raises(BusinessAPIException) as exc2:
        update_customer(active_customer.id, {"address": "No row version"})
    assert exc2.value.code == "PROP-GEN-P01"

    # 3. update_customer with email lower/strip
    res = update_customer(
        active_customer.id,
        {
            "row_version": active_customer.row_version,
            "email": "  UPDATED_EMAIL@EXAMPLE.COM  ",
        },
    )
    assert res.email == "updated_email@example.com"

    # 4. update_customer BLACKLISTED without reason
    with pytest.raises(BusinessAPIException) as exc3:
        update_customer(
            active_customer.id,
            {
                "row_version": res.row_version,
                "status": "BLACKLISTED",
                "status_reason": "   ",
            },
        )
    assert exc3.value.code == "PROP-GEN-P01"


def test_error_translation_additional_branches(admin_hierarchy: dict):
    """Cover remaining error translation branches using real PostgreSQL 18.6 exceptions inside savepoints."""
    from django.db import connection

    from tests.customers.test_customer_error_translation import (
        _trigger_real_db_exception,
    )

    # 1. ck_customer_ward_requires_district (real PostgreSQL 23514 check constraint)
    exc1 = _trigger_real_db_exception(
        lambda: connection.cursor().execute(
            """
            INSERT INTO customer (code, full_name, identity_card_number, phone, ward_id, district_id)
            VALUES ('KH9931', 'Ward No District', '079200117711', '0918881111', %s, NULL);
            """,
            [admin_hierarchy["ward_id"]],
        )
    )
    with pytest.raises(BusinessAPIException) as info1:
        translate_customer_db_error(exc1)
    assert info1.value.code == "PROP-GEN-P01"

    # 2. ck_customer_status_enum (real PostgreSQL 23514 check constraint)
    exc2 = _trigger_real_db_exception(
        lambda: connection.cursor().execute(
            """
            INSERT INTO customer (code, full_name, identity_card_number, phone, status)
            VALUES ('KH9932', 'Invalid Status', '079200117722', '0918881122', 'INVALID_ENUM');
            """
        )
    )
    with pytest.raises(BusinessAPIException) as info2:
        translate_customer_db_error(exc2)
    assert info2.value.code == "PROP-GEN-P01"

    # 3. Generic check constraint fallback (ck_customer_anonymized_pair, real PostgreSQL 23514)
    exc3 = _trigger_real_db_exception(
        lambda: connection.cursor().execute(
            """
            INSERT INTO customer (code, full_name, identity_card_number, phone, is_anonymized, anonymized_at)
            VALUES ('KH9933', 'Invalid Anon Pair', '079200117733', '0918881133', TRUE, NULL);
            """
        )
    )
    with pytest.raises(BusinessAPIException) as info3:
        translate_customer_db_error(exc3)
    assert info3.value.code == "PROP-GEN-P01"

    # 4. Generic foreign key constraint fallback (fk_customer_account, real PostgreSQL 23503)
    exc4 = _trigger_real_db_exception(
        lambda: connection.cursor().execute(
            """
            INSERT INTO customer (code, full_name, identity_card_number, phone, account_id)
            VALUES ('KH9934', 'Invalid Account FK', '079200117744', '0918881144', 999999);
            """
        )
    )
    with pytest.raises(BusinessAPIException) as info4:
        translate_customer_db_error(exc4)
    assert info4.value.code == "PROP-GEN-P01"
