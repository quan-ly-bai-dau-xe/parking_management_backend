"""
Services for vehicle management.
Handles vehicle creation, optimistic concurrency updates, DEL-03 soft deletion, and streaming CSV export.
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Generator
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import QuerySet
from django.utils import timezone
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer
from apps.parking.data.vn_plate_rules import (
    classify_plate_syntax,
    is_valid_vietnamese_car_plate,
)
from apps.parking.services.ocr import PlateRecognizer
from apps.vehicles.models import Vehicle, VehicleType

MAX_EXPORT_ROWS = 5000
CAR_ONLY_CODES = ("CAR", "EV")
DANGEROUS_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
PROP_VEH_OWNER_CHANGE_CONFLICT_CODE = "PROP-VEH-OWNER-CHANGE-CONFLICT"
PROP_VEH_OWNER_CHANGE_CONFLICT_MSG = (
    "Không thể thay đổi chủ sở hữu khi phương tiện đang có vé đỗ xe, "
    "phiên đỗ đang mở hoặc đặt chỗ còn hiệu lực."
)
RAW_PLATE_ASCII_REGEX = re.compile(r"^[A-Z0-9][A-Z0-9 .\-]{3,18}[A-Z0-9]$")
CONSECUTIVE_SEPARATORS_REGEX = re.compile(r"[ .\-]{2,}")


def _sanitize_csv_cell(value: Any) -> Any:
    """
    Neutralize CSV / Excel formula injection per OWASP guidelines.
    Prefixes any cell starting with '=', '+', '-', '@', '\t', or '\r' with a single quote.
    """
    if value is None:
        return ""
    str_val = str(value)
    if str_val and str_val.startswith(DANGEROUS_FORMULA_PREFIXES):
        return f"'{str_val}"
    return str_val


def _translate_vehicle_db_error(exc: Exception, operation: str = "create") -> None:
    """
    Translate raw PostgreSQL 18.6 / psycopg database exceptions (IntegrityError, DatabaseError)
    into structured BusinessAPIException for vehicle operations per R2.2.

    Re-raises unmapped exceptions to allow custom_exception_handler to produce controlled HTTP 500.
    """
    err_str = str(exc)
    cause = getattr(exc, "__cause__", None) or exc
    sqlstate = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
    sqlstate_str = str(sqlstate) if sqlstate else ""
    diag = getattr(cause, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None) or ""

    # 1. Unique constraint / index violations (SQLSTATE 23505)
    if (
        sqlstate_str == "23505"
        or "23505" in err_str
        or "uq_vehicle_code_active" in constraint_name
        or "uq_vehicle_license_plate_active" in constraint_name
        or "uq_vehicle" in err_str
        or "unique constraint" in err_str
    ):
        raise BusinessAPIException(
            code="MSG-4.3.1-M05",
            message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    # 2. Check constraint violations (SQLSTATE 23514)
    if (
        "ck_vehicle_license_plate_format" in constraint_name
        or "ck_vehicle_license_plate_format" in err_str
        or (sqlstate_str == "23514" and "ck_vehicle_license_plate_format" in err_str)
    ):
        raise BusinessAPIException(
            code="PROP-4.5.1-P16",
            message=(
                "Biển số xe có định dạng chưa được định nghĩa trong danh mục quy chuẩn "
                "hoặc thuộc nhóm cần xác minh thủ công."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            details={
                "syntax_status": "INVALID_FORMAT",
                "reason": "Biển số xe không đúng định dạng quy chuẩn.",
            },
        ) from exc

    # 3. Foreign key constraint violations (SQLSTATE 23503)
    if "fk_vehicle_customer" in constraint_name or "fk_vehicle_customer" in err_str:
        raise BusinessAPIException(
            code="PROP-4.4.4-P02",
            message="Khách hàng không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if "fk_vehicle_type" in constraint_name or "fk_vehicle_type" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Loại xe không hợp lệ (hệ thống chỉ phục vụ Ô tô và Xe điện).",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if (
        "fk_ticket_vehicle_customer" in constraint_name
        or "fk_ticket_vehicle_customer" in err_str
    ):
        raise BusinessAPIException(
            code=PROP_VEH_OWNER_CHANGE_CONFLICT_CODE,
            message=PROP_VEH_OWNER_CHANGE_CONFLICT_MSG,
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    # 4. Unknown / unmapped database error -> re-raise for custom_exception_handler
    raise exc


def validate_raw_license_plate(raw_plate: str | None) -> str:
    r"""
    Validate raw license plate string before normalization.
    Ensures 100% compliance with database check constraint ck_vehicle_license_plate_format.

    Rules:
    1. Mandatory non-empty (empty/None -> 400 PROP-GEN-P01).
    2. Strip only ASCII spaces (' '). Do not strip tab, newline, non-breaking space.
    3. Basic length check 5 <= len <= 20 (violation -> 400 PROP-4.5.1-P16, details:
       {"syntax_status": "INVALID_FORMAT", "reason": "Length must be between 5 and 20 characters."}).
    4. Must be pure ASCII (violation -> 400 PROP-4.5.1-P16, details:
       {"syntax_status": "INVALID_FORMAT", "reason": "Contains non-ASCII characters or unsupported symbols."}).
    5. Convert to uppercase ASCII (.upper()).
    6. Match syntax regex ^[A-Z0-9][A-Z0-9 .\-]{3,18}[A-Z0-9]$ (violation -> 400 PROP-4.5.1-P16, details:
       {"syntax_status": "INVALID_FORMAT", "reason": "Plate contains invalid characters or separator positions."}).
    7. Forbid consecutive separators [ .\-]{2,} (violation -> 400 PROP-4.5.1-P16, details:
       {"syntax_status": "INVALID_FORMAT", "reason": "Consecutive separators are not allowed."}).
    8. Return validated and uppercased license plate string.
    """
    if not raw_plate:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Biển số xe không được để trống.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 1. Strip only standard ASCII space characters (' ')
    trimmed = raw_plate.strip(" ")
    if not trimmed:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Biển số xe không được để trống.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 2. Check length between 5 and 20 characters
    if len(trimmed) < 5 or len(trimmed) > 20:
        raise BusinessAPIException(
            code="PROP-4.5.1-P16",
            message=(
                "Biển số xe có định dạng chưa được định nghĩa trong danh mục quy chuẩn "
                "hoặc thuộc nhóm cần xác minh thủ công."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            details={
                "syntax_status": "INVALID_FORMAT",
                "reason": "Length must be between 5 and 20 characters.",
            },
        )

    # 3. Check ASCII-only characters
    if not trimmed.isascii():
        raise BusinessAPIException(
            code="PROP-4.5.1-P16",
            message=(
                "Biển số xe có định dạng chưa được định nghĩa trong danh mục quy chuẩn "
                "hoặc thuộc nhóm cần xác minh thủ công."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            details={
                "syntax_status": "INVALID_FORMAT",
                "reason": "Contains non-ASCII characters or unsupported symbols.",
            },
        )

    # 4. Uppercase ASCII conversion
    uppercased = trimmed.upper()

    # 5. Regex syntax check: start/end with alnum, allowed characters inside
    if not RAW_PLATE_ASCII_REGEX.match(uppercased):
        raise BusinessAPIException(
            code="PROP-4.5.1-P16",
            message=(
                "Biển số xe có định dạng chưa được định nghĩa trong danh mục quy chuẩn "
                "hoặc thuộc nhóm cần xác minh thủ công."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            details={
                "syntax_status": "INVALID_FORMAT",
                "reason": "Plate contains invalid characters or separator positions.",
            },
        )

    # 6. Forbid consecutive separators
    if CONSECUTIVE_SEPARATORS_REGEX.search(uppercased):
        raise BusinessAPIException(
            code="PROP-4.5.1-P16",
            message=(
                "Biển số xe có định dạng chưa được định nghĩa trong danh mục quy chuẩn "
                "hoặc thuộc nhóm cần xác minh thủ công."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
            details={
                "syntax_status": "INVALID_FORMAT",
                "reason": "Consecutive separators are not allowed.",
            },
        )

    return uppercased


def create_vehicle(
    license_plate: str,
    model_name: str,
    vehicle_type_id: int,
    customer_id: int,
    code: str | None = None,
    brand: str | None = None,
    color: str | None = None,
    image_url: str | None = None,
    notes: str | None = None,
    actor_id: int | None = None,
) -> Vehicle:
    """
    Create a new vehicle record.
    Restricted to Employee or Manager role with CSRF validation.
    Normalizes license plate, validates active uniqueness, checks FKs, and generates code if omitted.
    """
    clean_plate = validate_raw_license_plate(license_plate)

    norm_plate = PlateRecognizer.normalize_plate(clean_plate)

    # Validate plate against Vietnamese civilian car standards
    if not is_valid_vietnamese_car_plate(norm_plate):
        syntax_status, syntax_reason = classify_plate_syntax(norm_plate)
        raise BusinessAPIException(
            code="PROP-4.5.1-P16",
            message="Biển số xe có định dạng chưa được định nghĩa trong danh mục quy chuẩn hoặc thuộc nhóm cần xác minh thủ công.",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"syntax_status": syntax_status, "reason": syntax_reason},
        )

    clean_model = (model_name or "").strip()
    if not clean_model:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Tên mẫu xe không được để trống.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 1. Validate active vehicle uniqueness by normalized plate (fast-path check)
    if Vehicle.objects.filter(
        license_plate_norm=norm_plate,
        deleted_at__isnull=True,
    ).exists():
        raise BusinessAPIException(
            code="MSG-4.3.1-M05",
            message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
            status_code=status.HTTP_409_CONFLICT,
        )

    # 2. Validate VehicleType exists, active, and strictly car-only (CAR, EV)
    vtype = VehicleType.objects.filter(
        id=vehicle_type_id,
        deleted_at__isnull=True,
    ).first()
    if not vtype or vtype.code not in CAR_ONLY_CODES:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Loại xe không hợp lệ (hệ thống chỉ phục vụ Ô tô và Xe điện).",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    # 3. Validate Customer exists and is active (not soft-deleted)
    cust = Customer.objects.filter(
        id=customer_id,
        deleted_at__isnull=True,
    ).first()
    if not cust:
        raise BusinessAPIException(
            code="PROP-4.4.4-P02",
            message="Khách hàng không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    with transaction.atomic():
        # PostgreSQL transaction-scoped advisory lock for serialized vehicle creation (K4)
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext('vehicle_create'));")

        # Double-checked lock: re-verify license plate uniqueness under lock
        if Vehicle.objects.filter(
            license_plate_norm=norm_plate,
            deleted_at__isnull=True,
        ).exists():
            raise BusinessAPIException(
                code="MSG-4.3.1-M05",
                message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                status_code=status.HTTP_409_CONFLICT,
            )

        # 4. Handle vehicle code generation or validation
        if code and code.strip():
            clean_code = code.strip()
            if not re.match(r"^[A-Za-z0-9-]+$", clean_code) or len(clean_code) > 10:
                raise BusinessAPIException(
                    code="PROP-GEN-P01",
                    message="Mã xe không đúng định dạng.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            if Vehicle.objects.filter(
                code=clean_code,
                deleted_at__isnull=True,
            ).exists():
                raise BusinessAPIException(
                    code="MSG-4.3.1-M05",
                    message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                    status_code=status.HTTP_409_CONFLICT,
                )
        else:
            # Auto-generate XE%04d sequence atomically under advisory lock
            existing_codes = list(
                Vehicle.objects.filter(code__startswith="XE").values_list(
                    "code", flat=True
                )
            )
            max_num = 0
            for c in existing_codes:
                match = re.match(r"^XE(\d+)$", c)
                if match:
                    num = int(match.group(1))
                    if num > max_num:
                        max_num = num
            next_num = max_num + 1
            clean_code = f"XE{next_num:04d}"

        try:
            vehicle = Vehicle.objects.create(
                code=clean_code,
                license_plate=clean_plate,
                model_name=clean_model,
                brand=brand.strip() if brand else None,
                color=color.strip() if color else None,
                image_url=image_url.strip() if image_url else None,
                notes=notes.strip() if notes else None,
                vehicle_type_id=vtype.id,
                customer_id=cust.id,
                row_version=1,
                deleted_at=None,
                deleted_by=None,
            )
        except (IntegrityError, DatabaseError) as exc:
            _translate_vehicle_db_error(exc, operation="create")

    return vehicle


def update_vehicle(
    vehicle: Vehicle,
    data: dict[str, Any],
    actor_id: int | None = None,
) -> Vehicle:
    """
    Update vehicle specifications with optimistic concurrency control (OCC).
    Verifies data['row_version'] against current database record with select_for_update.
    Raises HTTP 409 Conflict (MSG-4.3.1-M03) if stale.
    """
    if "row_version" not in data or data["row_version"] is None:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Trường row_version là bắt buộc.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    expected_version = data["row_version"]

    with transaction.atomic():
        current_vehicle = (
            Vehicle.objects.select_for_update()
            .filter(id=vehicle.id, deleted_at__isnull=True)
            .first()
        )
        if not current_vehicle:
            raise BusinessAPIException(
                code="MSG-4.4.1-M01",
                message="Không tìm thấy dữ liệu",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if current_vehicle.row_version != expected_version:
            raise BusinessAPIException(
                code="MSG-4.3.1-M03",
                message="Dữ liệu hiện đang được cập nhật bởi user khác",
                status_code=status.HTTP_409_CONFLICT,
            )

        # Update permitted fields
        if "model_name" in data and data["model_name"]:
            current_vehicle.model_name = data["model_name"].strip()

        if "brand" in data:
            current_vehicle.brand = data["brand"].strip() if data["brand"] else None

        if "color" in data:
            current_vehicle.color = data["color"].strip() if data["color"] else None

        if "image_url" in data:
            current_vehicle.image_url = (
                data["image_url"].strip() if data["image_url"] else None
            )

        if "notes" in data:
            current_vehicle.notes = data["notes"].strip() if data["notes"] else None

        if "vehicle_type_id" in data and data["vehicle_type_id"]:
            vtype = VehicleType.objects.filter(
                id=data["vehicle_type_id"],
                deleted_at__isnull=True,
            ).first()
            if not vtype or vtype.code not in CAR_ONLY_CODES:
                raise BusinessAPIException(
                    code="PROP-GEN-P01",
                    message="Loại xe không hợp lệ (hệ thống chỉ phục vụ Ô tô và Xe điện).",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            current_vehicle.vehicle_type_id = vtype.id

        if "customer_id" in data and data["customer_id"]:
            new_cust_id = data["customer_id"]
            if new_cust_id != current_vehicle.customer_id:
                cust = Customer.objects.filter(
                    id=new_cust_id,
                    deleted_at__isnull=True,
                ).first()
                if not cust:
                    raise BusinessAPIException(
                        code="PROP-4.4.4-P02",
                        message="Khách hàng không tồn tại hoặc đã bị xóa.",
                        status_code=status.HTTP_400_BAD_REQUEST,
                    )

                # Guard: cannot reassign owner if vehicle is linked to tickets, open sessions, or active reservations (K4)
                has_tickets = current_vehicle.tickets.exists()
                has_open_session = current_vehicle.entry_exit_logs.filter(
                    exit_time__isnull=True
                ).exists()
                has_active_rsv = current_vehicle.reservations.filter(
                    status="ACTIVE", deleted_at__isnull=True
                ).exists()
                if has_tickets or has_open_session or has_active_rsv:
                    raise BusinessAPIException(
                        code=PROP_VEH_OWNER_CHANGE_CONFLICT_CODE,
                        message=PROP_VEH_OWNER_CHANGE_CONFLICT_MSG,
                        status_code=status.HTTP_409_CONFLICT,
                        details={
                            "has_tickets": has_tickets,
                            "has_open_session": has_open_session,
                            "has_active_reservation": has_active_rsv,
                        },
                    )

                current_vehicle.customer_id = cust.id

        try:
            current_vehicle.save()
            current_vehicle.refresh_from_db()
        except (IntegrityError, DatabaseError) as exc:
            _translate_vehicle_db_error(exc, operation="update")

    return current_vehicle


def delete_vehicle(
    vehicle: Vehicle,
    actor_id: int | None = None,
) -> dict[str, str]:
    """
    Soft-delete a vehicle with DEL-03 database trigger guards.
    Evaluates in strict order:
      1. Open session guard -> PROP-DEL-03-OPEN-SES (HTTP 409)
      2. Active ticket guard -> PROP-DEL-03-ACTIVE-TKT (HTTP 409)
      3. Active reservation guard -> PROP-DEL-03-ACTIVE-RSV (HTTP 409)
    """
    with transaction.atomic():
        current_vehicle = (
            Vehicle.objects.select_for_update()
            .filter(id=vehicle.id, deleted_at__isnull=True)
            .first()
        )
        if not current_vehicle:
            raise BusinessAPIException(
                code="MSG-4.4.1-M01",
                message="Không tìm thấy dữ liệu",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        try:
            current_vehicle.deleted_at = timezone.now()
            current_vehicle.deleted_by_id = actor_id
            current_vehicle.save(update_fields=["deleted_at", "deleted_by_id"])
        except (IntegrityError, DatabaseError) as exc:
            err_str = str(exc)
            if (
                "Phương tiện đang đỗ trong bãi xe" in err_str
                or "PROP-DEL-03-OPEN-SES" in err_str
            ):
                raise BusinessAPIException(
                    code="PROP-DEL-03-OPEN-SES",
                    message="Phương tiện đang đỗ trong bãi xe (có phiên đỗ đang mở), không được phép xóa.",
                    status_code=status.HTTP_409_CONFLICT,
                ) from exc
            if (
                "Phương tiện đang có vé đỗ xe còn hiệu lực" in err_str
                or "PROP-DEL-03-ACTIVE-TKT" in err_str
            ):
                raise BusinessAPIException(
                    code="PROP-DEL-03-ACTIVE-TKT",
                    message="Phương tiện đang có vé đỗ xe còn hiệu lực, không được phép xóa.",
                    status_code=status.HTTP_409_CONFLICT,
                ) from exc
            if (
                "Phương tiện đang có đặt trước vị trí đỗ xe còn hiệu lực" in err_str
                or "PROP-DEL-03-ACTIVE-RSV" in err_str
            ):
                raise BusinessAPIException(
                    code="PROP-DEL-03-ACTIVE-RSV",
                    message="Phương tiện đang có đặt trước vị trí đỗ xe còn hiệu lực, không được phép xóa.",
                    status_code=status.HTTP_409_CONFLICT,
                ) from exc
            raise

    return {
        "code": "MSG-4.3.1-M01",
        "message": "Xóa thành công",
    }


def export_vehicles_csv(
    queryset: QuerySet[Vehicle],
) -> Generator[str]:
    """
    Stream RFC 4180 compliant CSV lines for vehicle list.
    Prepends UTF-8 BOM (\ufeff) for seamless Microsoft Excel compatibility.
    Sanitizes formula injection (=, +, -, @, \t, \r) on every text cell.
    Caps output at hard limit of MAX_EXPORT_ROWS (5,000 records).
    """
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\r\n")

    # 1. Yield UTF-8 BOM
    yield "\ufeff"

    # 2. Yield CSV Header row
    headers = [
        "STT",
        "Mã xe",
        "Biển số xe",
        "Chủ xe",
        "Mã khách hàng",
        "Loại xe",
        "Loại vé",
        "Ngày hết hạn vé",
        "Tình trạng vé",
        "Vị trí đỗ",
        "Trạng thái",
    ]
    writer.writerow([_sanitize_csv_cell(h) for h in headers])
    yield output.getvalue()
    output.seek(0)
    output.truncate(0)

    # 3. Stream row records up to hard limit
    now = timezone.now()
    expiring_days = getattr(settings, "TICKET_EXPIRING_SOON_DAYS", 7)
    expiring_window = now + timedelta(days=expiring_days)

    sliced_qs = queryset[:MAX_EXPORT_ROWS]

    for idx, v in enumerate(sliced_qs, start=1):
        cust_name = ""
        cust_code = ""
        cust = getattr(v, "customer", None)
        if cust:
            cust_code = cust.code
            cust_name = "Khách hàng ẩn danh" if cust.is_anonymized else cust.full_name

        vtype = getattr(v, "vehicle_type", None)
        vtype_name = vtype.name if vtype else ""
        # Representative ticket fields from annotated queryset or fallback
        rep_state = getattr(v, "rep_ticket_state", None)
        if rep_state is not None:
            rep_type_name = getattr(v, "rep_ticket_type_name", "") or ""
            rep_expires_at = getattr(v, "rep_ticket_effective_to", None)
            ticket_type_name = rep_type_name if rep_state != "none" else ""
            expires_str = ""
            ticket_state_display = ""
            if rep_expires_at and rep_state != "none":
                expires_str = rep_expires_at.strftime("%d/%m/%Y")
                state_display_map = {
                    "valid": "Còn hạn",
                    "expiring_soon": "Sắp hết hạn",
                    "expired": "Đã hết hạn",
                }
                ticket_state_display = state_display_map.get(rep_state, "")
        else:
            ttype = getattr(v, "ticket_type", None)
            ticket_type_name = ttype.name if ttype else ""
            expires_str = ""
            ticket_state_display = ""
            if v.ticket_expires_at:
                expires_str = v.ticket_expires_at.strftime("%d/%m/%Y")
                if v.ticket_expires_at < now:
                    ticket_state_display = "Đã hết hạn"
                elif v.ticket_expires_at <= expiring_window:
                    ticket_state_display = "Sắp hết hạn"
                else:
                    ticket_state_display = "Còn hạn"

        current_slot = getattr(v, "current_slot", "") or ""
        status_disp = getattr(v, "status_display", "") or "Đã rời bãi"

        row = [
            idx,
            v.code,
            v.license_plate,
            cust_name,
            cust_code,
            vtype_name,
            ticket_type_name,
            expires_str,
            ticket_state_display,
            current_slot,
            status_disp,
        ]

        writer.writerow([_sanitize_csv_cell(cell) for cell in row])
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)
