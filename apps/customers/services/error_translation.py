"""
PostgreSQL database error translation for Customer Management API.
Translates SQLSTATE 23505, 23514, 23503, 55000 into structured BusinessAPIException.
Strictly protects personal identifiable information (PII) by never echoing CCCD, phone, email, or address.
"""

from __future__ import annotations

from typing import NoReturn

from rest_framework import status

from apps.core.exceptions import BusinessAPIException


def translate_customer_db_error(
    exc: Exception,
    operation: str = "customer",
) -> NoReturn:
    """
    Translate raw PostgreSQL 18.6 database exceptions (IntegrityError, DatabaseError)
    into structured BusinessAPIException for customer operations per SRS 4.4.1–4.4.5.
    Under NO circumstances are raw PII values (CCCD, phone, email, address, DOB)
    reflected into exception messages, details, or logs.
    """
    err_str = str(exc)
    cause = getattr(exc, "__cause__", None) or exc
    sqlstate = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
    sqlstate_str = str(sqlstate) if sqlstate else ""
    diag = getattr(cause, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None) or ""

    # 1. Hard delete prohibited trigger (SQLSTATE 55000)
    if (
        sqlstate_str == "55000"
        or "55000" in err_str
        or "trg_prevent_plain_delete_customer" in err_str
        or "ADR-0003" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-DEL-SAVT-IN-USE",
            message="Dữ liệu đang được sử dụng hoặc không ở trạng thái hợp lệ để thao tác.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    # 2. Check constraint violations & soft delete triggers (SQLSTATE 23514)
    # Check trigger guards on soft deletion (DEL-02, TL-25)
    if (
        "Khách hàng đang có phương tiện trong bãi" in err_str
        or "PROP-4.4.5-P02" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-4.4.5-P02",
            message="Khách hàng đang có phương tiện trong bãi, không được phép xóa.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    if (
        "Khách hàng đang có vé xe còn hiệu lực" in err_str
        or "PROP-4.4.5-P03" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-4.4.5-P03",
            message="Khách hàng đang có vé xe còn hiệu lực, không được phép xóa.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    if (
        "Khách hàng đang có phương tiện hoạt động trong hệ thống" in err_str
        or "PROP-DEL-02-ACTIVE-VEH" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-DEL-02-ACTIVE-VEH",
            message="Khách hàng đang có phương tiện hoạt động trong hệ thống, không được phép xóa.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    # Blacklist reason required check constraint
    if (
        "ck_customer_blacklist_reason" in constraint_name
        or "ck_customer_blacklist_reason" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Lý do khóa là bắt buộc khi khách hàng thuộc danh sách đen.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Date of birth in past check constraint
    if "ck_customer_dob_past" in constraint_name or "ck_customer_dob_past" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Ngày sinh phải là ngày trong quá khứ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Full name non-empty check constraint
    if (
        "ck_customer_full_name_nonempty" in constraint_name
        or "ck_customer_full_name_nonempty" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Họ và tên khách hàng không được để trống.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Gender enum check constraint
    if "ck_customer_gender" in constraint_name or "ck_customer_gender" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Giới tính không hợp lệ (chỉ chấp nhận 'Nam' hoặc 'Nữ').",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Identity card digits check constraint
    if (
        "ck_customer_idcard_digits" in constraint_name
        or "ck_customer_idcard_digits" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Số CCCD/CMND phải là dãy số từ 9 đến 20 chữ số.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Phone digits check constraint
    if (
        "ck_customer_phone_digits" in constraint_name
        or "ck_customer_phone_digits" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Số điện thoại phải là dãy số từ 9 đến 15 chữ số.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Email format check constraint
    if (
        "ck_customer_email_format" in constraint_name
        or "ck_customer_email_format" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Định dạng email không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Code format check constraint
    if (
        "ck_customer_code_format" in constraint_name
        or "ck_customer_code_format" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Mã khách hàng không đúng định dạng.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Administrative ward requires district
    if (
        "ck_customer_ward_requires_district" in constraint_name
        or "ck_customer_ward_requires_district" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Cơ cấu địa giới hành chính không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Customer status enum
    if (
        "ck_customer_status_enum" in constraint_name
        or "ck_customer_status_enum" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Trạng thái khách hàng không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # 3. Foreign key violation (SQLSTATE 23503)
    if (
        "fk_customer_district_hierarchy" in constraint_name
        or "fk_customer_district_hierarchy" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Quận/Huyện không thuộc Tỉnh/Thành phố đã chọn.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if (
        "fk_customer_ward_hierarchy" in constraint_name
        or "fk_customer_ward_hierarchy" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Phường/Xã không thuộc Quận/Huyện đã chọn.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if sqlstate_str == "23503" or "foreign key constraint" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Dữ liệu tham chiếu không tồn tại hoặc không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # 4. Unique constraint / index violations (SQLSTATE 23505)
    # Strictly NEVER echo PII (CCCD, phone, email, name)
    if (
        sqlstate_str == "23505"
        or "23505" in err_str
        or "uq_customer" in constraint_name
        or "uq_customer" in err_str
        or "uq_vehicle" in err_str
        or "unique constraint" in err_str
    ):
        raise BusinessAPIException(
            code="MSG-4.3.1-M05",
            message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    if sqlstate_str == "23514" or "check constraint" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Dữ liệu vi phạm ràng buộc kiểm tra hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # If unmapped, re-raise to let DRF / custom_exception_handler handle it
    raise exc
