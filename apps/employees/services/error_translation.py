"""
PostgreSQL database error translation for Employee Management API.
Translates SQLSTATE 23505, 23514, 23503, 55000 into structured BusinessAPIException.
Strictly protects personal identifiable information (PII) by never echoing CCCD, phone, email, or name.
"""

from __future__ import annotations

from typing import NoReturn

from rest_framework import status

from apps.core.exceptions import BusinessAPIException


def translate_employee_db_error(
    exc: Exception,
    operation: str = "employee",
) -> NoReturn:
    """
    Translate PostgreSQL 18.6 database exceptions (IntegrityError, DatabaseError)
    into structured BusinessAPIException for employee operations per SRS 4.3.1–4.3.4.
    Strictly never reflects PII data (CCCD, Phone, Email, Full Name) in exception details or logs.
    """
    cause = getattr(exc, "__cause__", None) or exc
    sqlstate = getattr(cause, "sqlstate", None) or getattr(cause, "pgcode", None)
    sqlstate_str = str(sqlstate) if sqlstate else ""
    diag = getattr(cause, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None) or ""
    message_primary = getattr(diag, "message_primary", None) or ""
    message_detail = getattr(diag, "message_detail", None) or ""

    err_str = f"{exc} {cause} {message_primary} {message_detail} {constraint_name}"

    # 1. Triggers preventing plain DELETE (SQLSTATE 55000 per ADR-0003)
    if (
        sqlstate_str == "55000"
        or "55000" in err_str
        or "trg_prevent_plain_delete_employee" in err_str
        or "trg_prevent_plain_delete_account" in err_str
        or "ADR-0003" in err_str
        or "fn_guard_prevent_plain_delete" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-DEL-SAVT-IN-USE",
            message="Dữ liệu đang được sử dụng hoặc không ở trạng thái hợp lệ để thao tác.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    # 2. Check Constraint Violations & Soft Delete Triggers DEL-01 (SQLSTATE 23514)
    # 2.1. Trigger DEL-01 Guards (OQ-10, TL-25)
    if (
        "Nhân viên đang đăng nhập không được phép tự xóa hồ sơ của chính mình"
        in err_str
        or "PROP-DEL-01-SELF-EMP" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-DEL-01-SELF-EMP",
            message="Nhân viên đang đăng nhập không được phép tự xóa hồ sơ của chính mình.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    if (
        "Tài khoản đang đăng nhập không được phép tự xóa chính mình" in err_str
        or "PROP-DEL-01-SELF" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-DEL-01-SELF",
            message="Tài khoản đang đăng nhập không được phép tự xóa chính mình.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    if (
        "Không thể xóa nhân viên gắn với tài khoản Quản lý hoạt động cuối cùng"
        in err_str
        or "PROP-DEL-01-LAST-MGR-EMP" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-DEL-01-LAST-MGR-EMP",
            message="Không thể xóa nhân viên gắn với tài khoản Quản lý hoạt động cuối cùng.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    if (
        "Không thể xóa tài khoản Quản lý hoạt động cuối cùng trong hệ thống" in err_str
        or "PROP-DEL-01-LAST-MGR" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-DEL-01-LAST-MGR",
            message="Không thể xóa tài khoản Quản lý hoạt động cuối cùng trong hệ thống.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    if (
        "Chức vụ đang được phân công cho nhân viên đang hoạt động" in err_str
        or "PROP-DEL-06-POSITION" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-DEL-06-POSITION",
            message="Chức vụ đang được phân công cho nhân viên đang hoạt động, không được phép xóa.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    # 2.2. Check Constraints on employee & account tables
    if (
        "ck_employee_code_format" in constraint_name
        or "ck_employee_code_format" in err_str
    ):
        raise BusinessAPIException(
            code="MSG-4.3.2-M02",
            message="Mã nhân viên không đúng định dạng.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if (
        "ck_employee_full_name_nonempty" in constraint_name
        or "ck_employee_full_name_nonempty" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Họ và tên nhân viên không được để trống.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if "ck_employee_dob_past" in constraint_name or "ck_employee_dob_past" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Ngày sinh phải là ngày trong quá khứ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if "ck_employee_gender" in constraint_name or "ck_employee_gender" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Giới tính không hợp lệ (chỉ chấp nhận 'Nam' hoặc 'Nữ').",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if (
        "ck_employee_idcard_digits" in constraint_name
        or "ck_employee_idcard_digits" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Số CCCD/CMND phải là dãy số từ 9 đến 20 chữ số.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if (
        "ck_employee_phone_digits" in constraint_name
        or "ck_employee_phone_digits" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Số điện thoại phải là dãy số từ 9 đến 15 chữ số.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if (
        "ck_employee_email_format" in constraint_name
        or "ck_employee_email_format" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Định dạng email không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if (
        "ck_employee_address_nonempty" in constraint_name
        or "ck_employee_address_nonempty" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Địa chỉ không được để trống.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if (
        "ck_employee_ward_requires_district" in constraint_name
        or "ck_employee_ward_requires_district" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Cơ cấu địa giới hành chính không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if (
        "ck_employee_status_enum" in constraint_name
        or "ck_employee_status_enum" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Trạng thái nhân viên không hợp lệ (chỉ chấp nhận ACTIVE hoặc INACTIVE).",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if "ck_account_role" in constraint_name or "ck_account_role" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Vai trò tài khoản không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # 3. Foreign Key Violations (SQLSTATE 23503)
    if "fk_employee_position" in constraint_name or "fk_employee_position" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Chức vụ không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if (
        "fk_employee_district_hierarchy" in constraint_name
        or "fk_employee_district_hierarchy" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Quận/Huyện không thuộc Tỉnh/Thành phố đã chọn.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if (
        "fk_employee_ward_hierarchy" in constraint_name
        or "fk_employee_ward_hierarchy" in err_str
    ):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Phường/Xã không thuộc Quận/Huyện đã chọn.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if "fk_employee_account" in constraint_name or "fk_employee_account" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Tài khoản liên kết không hợp lệ hoặc không tồn tại.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    if sqlstate_str == "23503" or "foreign key constraint" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Dữ liệu tham chiếu không tồn tại hoặc không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # 4. Unique Constraint / Index Violations (SQLSTATE 23505)
    # Strictly zero PII in details or message!
    if (
        sqlstate_str == "23505"
        or "23505" in err_str
        or "uq_employee" in constraint_name
        or "uq_employee" in err_str
        or "uq_account" in constraint_name
        or "uq_account" in err_str
        or "unique constraint" in err_str
    ):
        raise BusinessAPIException(
            code="MSG-4.3.1-M05",
            message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc

    # Fallback for remaining check constraint violations
    if sqlstate_str == "23514" or "check constraint" in err_str:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Dữ liệu vi phạm ràng buộc kiểm tra hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    # Re-raise unmapped exceptions
    raise exc
