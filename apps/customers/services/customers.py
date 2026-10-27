"""
Services for customer management.
Handles customer creation with sequential advisory lock KH%04d generation,
atomic vehicles creation with all-or-nothing rollback,
optimistic concurrency updates (row_version), and DEL-02 soft deletion.
"""

from __future__ import annotations

from typing import Any

from django.db import connection, transaction
from django.utils import timezone
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.core.models import AdministrativeDistrict, AdministrativeWard
from apps.customers.models import Customer
from apps.customers.services.error_translation import translate_customer_db_error
from apps.vehicles.services.vehicles import create_vehicle


def create_customer(
    data: dict[str, Any],
    created_by: Any = None,
    vehicles_data: list[dict[str, Any]] | None = None,
) -> Customer:
    """
    Create a new customer profile.
    Generates sequential code KH%04d under transaction-scoped advisory lock if omitted.
    Optionally creates registered vehicles in the same atomic transaction with all-or-nothing rollback.
    """
    with transaction.atomic():
        # 1. Acquire transaction-scoped advisory lock for customer code generation
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext('customer_code_sequence'));"
            )

            # Determine customer code
            code = data.get("code")
            if code and str(code).strip():
                clean_code = str(code).strip()
                if Customer.objects.filter(
                    code=clean_code, deleted_at__isnull=True
                ).exists():
                    raise BusinessAPIException(
                        code="MSG-4.3.1-M05",
                        message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                        status_code=status.HTTP_409_CONFLICT,
                    )
            else:
                cursor.execute(
                    """
                    SELECT COALESCE(
                        MAX(
                            CASE
                                WHEN code ~ '^KH[0-9]+$' THEN SUBSTRING(code FROM 3)::INTEGER
                                ELSE 0
                            END
                        ), 0
                    )
                    FROM customer;
                    """
                )
                max_num = cursor.fetchone()[0]
                clean_code = f"KH{max_num + 1:04d}"

        # 2. Fast uniqueness checks on active non-anonymized records (defense-in-depth)
        id_card = str(data["identity_card_number"]).strip()
        if Customer.objects.filter(
            identity_card_number=id_card,
            deleted_at__isnull=True,
            is_anonymized=False,
        ).exists():
            raise BusinessAPIException(
                code="MSG-4.3.1-M05",
                message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                status_code=status.HTTP_409_CONFLICT,
            )

        phone = str(data["phone"]).strip()
        if Customer.objects.filter(
            phone=phone,
            deleted_at__isnull=True,
            is_anonymized=False,
        ).exists():
            raise BusinessAPIException(
                code="MSG-4.3.1-M05",
                message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                status_code=status.HTTP_409_CONFLICT,
            )

        email = data.get("email")
        if email and str(email).strip():
            clean_email = str(email).strip().lower()
            if Customer.objects.filter(
                email__iexact=clean_email,
                deleted_at__isnull=True,
                is_anonymized=False,
            ).exists():
                raise BusinessAPIException(
                    code="MSG-4.3.1-M05",
                    message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                    status_code=status.HTTP_409_CONFLICT,
                )
        else:
            clean_email = None

        # 3. Administrative hierarchy verification
        prov_id = data.get("province_id")
        dist_id = data.get("district_id")
        ward_id = data.get("ward_id")

        if ward_id is not None and dist_id is None:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Cơ cấu địa giới hành chính không hợp lệ.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if dist_id is not None and prov_id is None:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Cơ cấu địa giới hành chính không hợp lệ.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if (
            ward_id
            and dist_id
            and not AdministrativeWard.objects.filter(
                id=ward_id, district_id=dist_id
            ).exists()
        ):
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Phường/Xã không thuộc Quận/Huyện đã chọn.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if (
            dist_id
            and prov_id
            and not AdministrativeDistrict.objects.filter(
                id=dist_id, province_id=prov_id
            ).exists()
        ):
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Quận/Huyện không thuộc Tỉnh/Thành phố đã chọn.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # 4. Status and Blacklist reason check
        cust_status = data.get("status", "ACTIVE")
        status_reason = data.get("status_reason")
        if cust_status == "BLACKLISTED" and (
            not status_reason or not str(status_reason).strip()
        ):
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Lý do khóa là bắt buộc khi khách hàng thuộc danh sách đen.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # 5. Persist customer
        try:
            customer = Customer.objects.create(
                code=clean_code,
                full_name=data["full_name"],
                date_of_birth=data.get("date_of_birth"),
                gender=data.get("gender"),
                identity_card_number=id_card,
                phone=phone,
                email=clean_email,
                address=data.get("address"),
                province_id=prov_id,
                district_id=dist_id,
                ward_id=ward_id,
                status=cust_status,
                status_reason=status_reason,
            )
        except Exception as exc:
            translate_customer_db_error(exc, operation="create")

        # 6. Atomic creation of vehicles array if provided
        v_list = (
            vehicles_data if vehicles_data is not None else data.get("vehicles", [])
        )
        if v_list:
            actor_id = created_by.id if hasattr(created_by, "id") else created_by
            for v_item in v_list:
                create_vehicle(
                    license_plate=v_item["license_plate"],
                    model_name=v_item["model_name"],
                    vehicle_type_id=v_item["vehicle_type_id"],
                    customer_id=customer.id,
                    code=v_item.get("code"),
                    brand=v_item.get("brand"),
                    color=v_item.get("color"),
                    image_url=v_item.get("image_url"),
                    notes=v_item.get("notes"),
                    actor_id=actor_id,
                )

        return customer


def update_customer(
    customer_id: int,
    data: dict[str, Any],
    updated_by: Any = None,
) -> Customer:
    """
    Partial update for customer profile (PATCH /api/v1/customers/{id}/).
    Enforces optimistic concurrency control (OCC via row_version),
    code immutability, administrative hierarchy consistency,
    and blacklist reason validation.
    """
    with transaction.atomic():
        customer = (
            Customer.objects.select_for_update()
            .filter(id=customer_id, deleted_at__isnull=True)
            .first()
        )
        if not customer:
            raise BusinessAPIException(
                code="PROP-4.4.4-P02",
                message="Khách hàng không tồn tại hoặc đã bị xóa.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # 1. OCC Token Check (row_version)
        if "row_version" not in data:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Trường row_version là bắt buộc để kiểm soát cập nhật đồng thời.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if int(data["row_version"]) != customer.row_version:
            raise BusinessAPIException(
                code="MSG-4.3.1-M03",
                message="Dữ liệu hiện đang được cập nhật bởi user khác",
                status_code=status.HTTP_409_CONFLICT,
            )

        # 2. Administrative hierarchy verification (merged with current values)
        prov_id = data.get("province_id", customer.province_id)
        dist_id = data.get("district_id", customer.district_id)
        ward_id = data.get("ward_id", customer.ward_id)

        if ward_id is not None and dist_id is None:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Cơ cấu địa giới hành chính không hợp lệ.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if dist_id is not None and prov_id is None:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Cơ cấu địa giới hành chính không hợp lệ.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if (
            ward_id
            and dist_id
            and not AdministrativeWard.objects.filter(
                id=ward_id, district_id=dist_id
            ).exists()
        ):
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Phường/Xã không thuộc Quận/Huyện đã chọn.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if (
            dist_id
            and prov_id
            and not AdministrativeDistrict.objects.filter(
                id=dist_id, province_id=prov_id
            ).exists()
        ):
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Quận/Huyện không thuộc Tỉnh/Thành phố đã chọn.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # 3. Uniqueness checks on updated identity card, phone, or email
        if "identity_card_number" in data:
            new_id_card = str(data["identity_card_number"]).strip()
            if (
                new_id_card != customer.identity_card_number
                and Customer.objects.filter(
                    identity_card_number=new_id_card,
                    deleted_at__isnull=True,
                    is_anonymized=False,
                )
                .exclude(id=customer.id)
                .exists()
            ):
                raise BusinessAPIException(
                    code="MSG-4.3.1-M05",
                    message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                    status_code=status.HTTP_409_CONFLICT,
                )

        if "phone" in data:
            new_phone = str(data["phone"]).strip()
            if (
                new_phone != customer.phone
                and Customer.objects.filter(
                    phone=new_phone,
                    deleted_at__isnull=True,
                    is_anonymized=False,
                )
                .exclude(id=customer.id)
                .exists()
            ):
                raise BusinessAPIException(
                    code="MSG-4.3.1-M05",
                    message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                    status_code=status.HTTP_409_CONFLICT,
                )

        if "email" in data:
            raw_email = data.get("email")
            new_email = str(raw_email).strip().lower() if raw_email else None
            curr_email = customer.email.lower() if customer.email else None
            if (
                new_email
                and new_email != curr_email
                and Customer.objects.filter(
                    email__iexact=new_email,
                    deleted_at__isnull=True,
                    is_anonymized=False,
                )
                .exclude(id=customer.id)
                .exists()
            ):
                raise BusinessAPIException(
                    code="MSG-4.3.1-M05",
                    message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                    status_code=status.HTTP_409_CONFLICT,
                )

        # 4. Status and Blacklist reason check
        new_status = data.get("status", customer.status)
        new_reason = data.get("status_reason", customer.status_reason)
        if new_status == "BLACKLISTED" and (
            not new_reason or not str(new_reason).strip()
        ):
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Lý do khóa là bắt buộc khi khách hàng thuộc danh sách đen.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # 5. Apply updates (code is immutable per REQ-4.4.4-F01)
        updatable_fields = [
            "full_name",
            "date_of_birth",
            "gender",
            "identity_card_number",
            "phone",
            "email",
            "address",
            "province_id",
            "district_id",
            "ward_id",
            "status",
            "status_reason",
        ]
        for field in updatable_fields:
            if field in data:
                val = data[field]
                if field == "email" and val:
                    val = str(val).strip().lower()
                setattr(customer, field, val)

        try:
            customer.save()
        except Exception as exc:
            translate_customer_db_error(exc, operation="update")

        customer.refresh_from_db()
        return customer


def delete_customer(
    customer_id: int,
    deleted_by: Any = None,
) -> dict[str, str]:
    """
    Soft-delete a customer per DEL-02.
    Evaluates 3 database trigger guards in strict order:
      1. Parked vehicles in lot -> 409 PROP-4.4.5-P02
      2. Active subscription ticket -> 409 PROP-4.4.5-P03
      3. Active vehicles exist -> 409 PROP-DEL-02-ACTIVE-VEH
    Returns MSG-4.4.5-M01 on success.
    """
    with transaction.atomic():
        customer = (
            Customer.objects.select_for_update()
            .filter(id=customer_id, deleted_at__isnull=True)
            .first()
        )
        if not customer:
            raise BusinessAPIException(
                code="PROP-4.4.5-P01",
                message="Khách hàng không tồn tại hoặc đã bị xóa.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        actor_id = deleted_by.id if hasattr(deleted_by, "id") else deleted_by
        customer.deleted_at = timezone.now()
        customer.deleted_by_id = actor_id

        try:
            customer.save(update_fields=["deleted_at", "deleted_by_id"])
        except Exception as exc:
            translate_customer_db_error(exc, operation="delete")

    return {
        "code": "MSG-4.4.5-M01",
        "message": "Xóa thành công",
    }
