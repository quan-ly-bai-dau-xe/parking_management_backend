"""
Services for employee lifecycle management per SRS 4.3.1–4.3.4 and Round 67 specifications.
Handles atomic Employee + Account creation with sequential advisory lock NV%03d/NV%04d generation,
optimistic concurrency updates (row_version), position-to-role derivation,
DEL-01 soft delete guards, and immediate session/remember-token revocation.
"""

from __future__ import annotations

import binascii
import re
from typing import Any

from django.contrib.auth.hashers import make_password
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.sessions.exceptions import SuspiciousSession
from django.contrib.sessions.models import Session
from django.core.signing import BadSignature
from django.db import connection, transaction
from django.utils import timezone
from rest_framework import status

from apps.accounts.models import Account, PersistentLoginToken
from apps.core.exceptions import BusinessAPIException
from apps.core.models import AdministrativeDistrict, AdministrativeWard
from apps.employees.models import Employee, Position
from apps.employees.services.error_translation import translate_employee_db_error


class StaleRowVersionError(BusinessAPIException):
    """
    Ngoại lệ phát sinh khi kiểm tra OCC row_version thất bại (xung đột cập nhật đồng thời).
    Ánh xạ nguyên văn sang HTTP 409 Conflict với mã lỗi MSG-4.3.1-M03.
    """

    def __init__(
        self, message: str = "Dữ liệu hiện đang được cập nhật bởi user khác"
    ) -> None:
        super().__init__(
            code="MSG-4.3.1-M03",
            message=message,
            status_code=status.HTTP_409_CONFLICT,
        )


def validate_password_policy(password: str) -> None:
    """
    Thẩm định chính sách độ phức tạp mật khẩu per SRS 4.3.3 & Rule 07:
    - Độ dài từ 8 đến 50 ký tự.
    - Chứa ít nhất một chữ cái in thường [a-z].
    - Chứa ít nhất một chữ cái in hoa [A-Z].
    - Chứa ít nhất một chữ số [0-9].
    - Chứa ít nhất một ký tự đặc biệt [!@#$%^&*()_+-=[]{}|;:,.<>?].
    """
    if not isinstance(password, str):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Mật khẩu không hợp lệ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if len(password) < 8 or len(password) > 50:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Mật khẩu phải có độ dài từ 8 đến 50 ký tự.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not re.search(r"[a-z]", password):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Mật khẩu phải chứa ít nhất một chữ cái thường.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not re.search(r"[A-Z]", password):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Mật khẩu phải chứa ít nhất một chữ cái hoa.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not re.search(r"[0-9]", password):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Mật khẩu phải chứa ít nhất một chữ số.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not re.search(r"[!@#$%^&*()_+\-=\[\]{}|;:,.<>?]", password):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Mật khẩu phải chứa ít nhất một ký tự đặc biệt.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )


def derive_account_role_from_position(position_code: str) -> str:
    """
    Suy diễn quyền tài khoản (Account.role) từ mã chức vụ (Position.code).
    QL -> 'MANAGER'
    NVVH, NVTN, KTV và các mã khác -> 'EMPLOYEE'
    """
    if position_code == "QL":
        return "MANAGER"
    return "EMPLOYEE"


def generate_employee_code(cursor: Any) -> str:
    """
    Sinh mã nhân viên tự động tuần tự dưới khóa cố vấn giao dịch pg_advisory_xact_lock.
    Khớp định dạng ck_employee_code_format: ^NV[0-9]{3,4}$.
    - Dưới 1000: NV%03d (ví dụ: NV009, NV999).
    - Từ 1000 trở lên: NV%04d (ví dụ: NV1000, NV9999).
    """
    cursor.execute(
        """
        SELECT COALESCE(
            MAX(
                CASE
                    WHEN code ~ '^NV[0-9]{3,4}$' THEN SUBSTRING(code FROM 3)::INTEGER
                    ELSE 0
                END
            ), 0
        )
        FROM employee;
        """
    )
    row = cursor.fetchone()
    max_num = row[0] if row else 0
    next_num = max_num + 1

    if next_num <= 999:
        return f"NV{next_num:03d}"
    return f"NV{next_num:04d}"


def revoke_account_sessions_and_tokens(account_id: int | str) -> int:
    """
    Thu hồi tức thì toàn bộ token ghi nhớ (PersistentLoginToken) và phiên làm việc (Session)
    của tài khoản chỉ định mà KHÔNG cần sửa đổi bất kỳ tệp nào trong apps/accounts/**.
    Tối ưu hóa bộ nhớ RAM bằng streaming server-side cursor iterator(chunk_size=2000)
    và giải mã trực tiếp bằng SessionStore().decode() thay vì khởi tạo model instance (M5).
    """
    account_id_int = int(account_id)
    account_id_str = str(account_id_int)

    # 1. Thu hồi toàn bộ PersistentLoginToken (Remember-Me)
    PersistentLoginToken.objects.filter(account_id=account_id_int).delete()

    # 2. Quét và xóa các active sessions trong django_session qua streaming cursor
    session_keys_to_delete: list[str] = []
    store = SessionStore()
    active_sessions_qs = (
        Session.objects.filter(expire_date__gte=timezone.now())
        .values_list("session_key", "session_data")
        .iterator(chunk_size=2000)
    )
    for s_key, s_data in active_sessions_qs:
        try:
            data = store.decode(s_data)
            if str(data.get("_auth_user_id")) == account_id_str:
                session_keys_to_delete.append(s_key)
        except (
            AttributeError,
            ValueError,
            SuspiciousSession,
            BadSignature,
            binascii.Error,
        ):
            continue

    if session_keys_to_delete:
        Session.objects.filter(session_key__in=session_keys_to_delete).delete()

    return len(session_keys_to_delete)


def get_position_code(position_id: int) -> str | None:
    """
    Lấy mã chức vụ trực tiếp từ cơ sở dữ liệu nếu chức vụ chưa bị xóa mềm.
    Loại bỏ hoàn toàn bộ nhớ đệm tĩnh trong RAM per M1 & Anti-facade rule.
    """
    return (
        Position.objects.filter(id=position_id, deleted_at__isnull=True)
        .values_list("code", flat=True)
        .first()
    )


@transaction.atomic
def create_employee(
    *,
    data: dict[str, Any] | None = None,
    actor: Any = None,
    created_by: Any = None,
    **kwargs: Any,
) -> Employee:
    """
    Tạo mới nguyên tử cả bản ghi Account và Employee trong một transaction duy nhất.
    Tự động sinh mã NV%03d/NV%04d dưới pg_advisory_xact_lock nếu code bị bỏ trống.
    Băm mật khẩu Argon2 và suy diễn vai trò Account.role từ Position.code.
    """
    payload = dict(data) if data is not None else dict(kwargs)
    if data is not None and kwargs:
        payload.update(kwargs)

    # 1. Kiểm tra chức vụ và suy diễn quyền Account.role
    position_id = payload.get("position_id")
    if not position_id:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Chức vụ là bắt buộc.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    try:
        pos_id_int = int(position_id)
    except (ValueError, TypeError) as exc:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Chức vụ không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_400_BAD_REQUEST,
        ) from exc

    pos_code = get_position_code(pos_id_int)
    if not pos_code:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Chức vụ không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    account_role = derive_account_role_from_position(pos_code)

    # 2. Thẩm định mật khẩu và tạo hash Argon2
    raw_password = payload.get("password")
    if not raw_password:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Mật khẩu là bắt buộc khi tạo nhân viên mới.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    validate_password_policy(str(raw_password))
    password_hash = make_password(str(raw_password))

    # 3. Chuẩn hóa và thẩm định tính duy nhất của Email & SĐT (Defense-in-depth)
    clean_email = str(payload.get("email", "")).strip().lower()
    clean_phone = str(payload.get("phone", "")).strip()

    if not clean_email or not clean_phone:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Email và số điện thoại là bắt buộc.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    id_card = payload.get("identity_card_number")
    clean_id_card = str(id_card).strip() if id_card else None

    # 4. Thẩm định phân cấp địa giới hành chính
    prov_id = payload.get("province_id")
    dist_id = payload.get("district_id")
    ward_id = payload.get("ward_id")

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

    # 5. Xác định trạng thái và đồng bộ is_active
    emp_status = payload.get("status", "ACTIVE")
    if emp_status not in ("ACTIVE", "INACTIVE"):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Trạng thái nhân viên không hợp lệ (chỉ chấp nhận ACTIVE hoặc INACTIVE).",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    account_is_active = emp_status == "ACTIVE"

    # 6. Sinh mã nhân viên hoặc thẩm định mã do client cung cấp dưới advisory lock
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s));", ["employee_code_sequence"]
        )

        client_code = payload.get("code")
        if client_code and str(client_code).strip():
            clean_code = str(client_code).strip().upper()
            if not re.match(r"^NV[0-9]{3,4}$", clean_code):
                raise BusinessAPIException(
                    code="MSG-4.3.2-M02",
                    message="Mã nhân viên không đúng định dạng.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
        else:
            clean_code = generate_employee_code(cursor)

    # 7. Khởi tạo Account trước (trong transaction atomic)
    try:
        account = Account.objects.create(
            email=clean_email,
            phone=clean_phone,
            password=password_hash,
            role=account_role,
            is_active=account_is_active,
        )
    except Exception as exc:
        translate_employee_db_error(exc, operation="create_account")

    # 8. Khởi tạo Employee liên kết với Account
    try:
        employee = Employee.objects.create(
            code=clean_code,
            full_name=str(payload["full_name"]).strip(),
            date_of_birth=payload.get("date_of_birth"),
            gender=payload.get("gender"),
            identity_card_number=clean_id_card,
            phone=clean_phone,
            email=clean_email,
            address=str(payload["address"]).strip() if payload.get("address") else None,
            province_id=prov_id,
            district_id=dist_id,
            ward_id=ward_id,
            position_id=pos_id_int,
            account=account,
            status=emp_status,
        )
    except Exception as exc:
        translate_employee_db_error(exc, operation="create_employee")

    return employee


@transaction.atomic
def update_employee(
    *,
    employee_id: int | None = None,
    employee: Employee | int | None = None,
    data: dict[str, Any],
    actor: Any = None,
    updated_by: Any = None,
) -> Employee:
    """
    Cập nhật từng phần thông tin nhân viên (PATCH /api/v1/employees/{id}/).
    Bắt buộc kiểm tra OCC row_version (ném StaleRowVersionError nếu cũ).
    Bất biến trường code. Tự động đồng bộ vai trò, trạng thái, email, SĐT sang Account.
    Áp dụng các quy tắc bảo vệ DEL-01 (tự vô hiệu hóa / tự giáng chức / Quản lý cuối cùng).
    """
    emp_id: int | None
    if isinstance(employee, Employee):
        emp_id = employee.id
    elif isinstance(employee, int):
        emp_id = employee
    else:
        emp_id = employee_id

    if emp_id is None:
        raise BusinessAPIException(
            code="PROP-4.3.3-P02",
            message="Nhân viên không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    emp = (
        Employee.objects.select_for_update(of=("self",))
        .select_related("account", "position")
        .filter(id=emp_id, deleted_at__isnull=True)
        .first()
    )
    if not emp:
        raise BusinessAPIException(
            code="PROP-4.3.3-P02",
            message="Nhân viên không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    # 1. Kiểm tra bắt buộc OCC row_version
    if "row_version" not in data:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Trường row_version là bắt buộc để kiểm soát cập nhật đồng thời.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if int(data["row_version"]) != emp.row_version:
        raise StaleRowVersionError()

    # 2. Bất biến trường code
    if "code" in data and data["code"] != emp.code:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Mã nhân viên là bất biến, không được phép chỉnh sửa.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    actor_account_id = getattr(actor or updated_by, "id", actor or updated_by)

    # 3. Xử lý trạng thái và thẩm định DEL-01 Deactivation
    target_status = data.get("status", emp.status)
    if target_status not in ("ACTIVE", "INACTIVE"):
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Trạng thái nhân viên không hợp lệ (chỉ chấp nhận ACTIVE hoặc INACTIVE).",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    is_deactivating = emp.status == "ACTIVE" and target_status == "INACTIVE"

    # 4. Xử lý chức vụ và thẩm định DEL-01 Demotion
    new_position_id = data.get("position_id")
    new_pos_id_int: int | None = None
    new_pos_code: str | None = None
    is_demoting_manager = False

    if new_position_id is not None and new_position_id != emp.position_id:
        try:
            new_pos_id_int = int(new_position_id)
        except (ValueError, TypeError) as exc:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Chức vụ không tồn tại hoặc đã bị xóa.",
                status_code=status.HTTP_400_BAD_REQUEST,
            ) from exc
        new_pos_code = get_position_code(new_pos_id_int)
        if not new_pos_code:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Chức vụ không tồn tại hoặc đã bị xóa.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if emp.position.code == "QL" and new_pos_code != "QL":
            is_demoting_manager = True

    # 5. Thẩm định các chốt chặn an ninh DEL-01 trên Update
    # 5.1. Chặn tự vô hiệu hóa hoặc tự giáng chức chính mình (Truthful Proposal Messages per M4)
    if emp.account_id is not None and emp.account_id == actor_account_id:
        if is_deactivating:
            raise BusinessAPIException(
                code="PROP-DEL-01-SELF-DEACT",
                message="Nhân viên đang đăng nhập không được phép tự vô hiệu hóa tài khoản của chính mình.",
                status_code=status.HTTP_409_CONFLICT,
            )
        if is_demoting_manager:
            raise BusinessAPIException(
                code="PROP-DEL-01-SELF-DEMOTE",
                message="Quản lý đang đăng nhập không được phép tự giáng chức chính mình.",
                status_code=status.HTTP_409_CONFLICT,
            )

    # 5.2. Chặn vô hiệu hóa hoặc giáng chức Quản lý hoạt động cuối cùng
    if (
        ((is_deactivating and emp.position.code == "QL") or is_demoting_manager)
        and emp.account_id is not None
        and emp.account
        and emp.account.role == "MANAGER"
        and emp.account.is_active
        and emp.account.deleted_at is None
    ):
        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s));",
                    ["guard_last_active_manager"],
                )

        other_active_managers = (
            Account.objects.filter(
                role="MANAGER",
                is_active=True,
                deleted_at__isnull=True,
            )
            .exclude(id=emp.account_id)
            .count()
        )
        if other_active_managers == 0:
            raise BusinessAPIException(
                code="PROP-DEL-01-LAST-MGR-EMP",
                message="Không thể xóa nhân viên gắn với tài khoản Quản lý hoạt động cuối cùng.",
                status_code=status.HTTP_409_CONFLICT,
            )

    # 6. Thẩm định tính duy nhất nếu thay đổi Email, SĐT, hoặc CCCD
    if "email" in data:
        new_email = str(data["email"]).strip().lower()
        if new_email != emp.email:
            acc_email_qs = Account.objects.filter(
                email__iexact=new_email, deleted_at__isnull=True
            )
            if emp.account_id is not None:
                acc_email_qs = acc_email_qs.exclude(id=emp.account_id)

            if (
                Employee.objects.filter(
                    email__iexact=new_email, deleted_at__isnull=True
                )
                .exclude(id=emp.id)
                .exists()
                or acc_email_qs.exists()
            ):
                raise BusinessAPIException(
                    code="MSG-4.3.1-M05",
                    message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                    status_code=status.HTTP_409_CONFLICT,
                )

    if "phone" in data:
        new_phone = str(data["phone"]).strip()
        if new_phone != emp.phone:
            acc_phone_qs = Account.objects.filter(
                phone=new_phone, deleted_at__isnull=True
            )
            if emp.account_id is not None:
                acc_phone_qs = acc_phone_qs.exclude(id=emp.account_id)

            if (
                Employee.objects.filter(phone=new_phone, deleted_at__isnull=True)
                .exclude(id=emp.id)
                .exists()
                or acc_phone_qs.exists()
            ):
                raise BusinessAPIException(
                    code="MSG-4.3.1-M05",
                    message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                    status_code=status.HTTP_409_CONFLICT,
                )

    if "identity_card_number" in data:
        new_id_card = (
            str(data["identity_card_number"]).strip()
            if data["identity_card_number"]
            else None
        )
        if (
            new_id_card
            and new_id_card != emp.identity_card_number
            and Employee.objects.filter(
                identity_card_number=new_id_card, deleted_at__isnull=True
            )
            .exclude(id=emp.id)
            .exists()
        ):
            raise BusinessAPIException(
                code="MSG-4.3.1-M05",
                message="Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
                status_code=status.HTTP_409_CONFLICT,
            )

    # 7. Thẩm định phân cấp địa giới hành chính khi có thay đổi
    has_geo_change = any(k in data for k in ("province_id", "district_id", "ward_id"))
    if has_geo_change:
        prov_id = data.get("province_id", emp.province_id)
        dist_id = data.get("district_id", emp.district_id)
        ward_id = data.get("ward_id", emp.ward_id)

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

    # 8. Xử lý cập nhật mật khẩu nếu được cung cấp
    password_updated = False
    if "password" in data and data["password"]:
        raw_password = str(data["password"]).strip()
        validate_password_policy(raw_password)
        if emp.account:
            emp.account.password = make_password(raw_password)
            password_updated = True

    # 9. Đồng bộ tài khoản Account liên kết
    if emp.account:
        acc_updated = False
        if "email" in data:
            emp.account.email = str(data["email"]).strip().lower()
            acc_updated = True
        if "phone" in data:
            emp.account.phone = str(data["phone"]).strip()
            acc_updated = True
        if "status" in data:
            emp.account.is_active = target_status == "ACTIVE"
            acc_updated = True
        if new_pos_code:
            emp.account.role = derive_account_role_from_position(new_pos_code)
            acc_updated = True
        if password_updated or acc_updated:
            try:
                emp.account.save()
            except Exception as exc:
                translate_employee_db_error(exc, operation="update_account")

    # 10. Cập nhật Employee (code bất biến)
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
    ]
    for field in updatable_fields:
        if field in data:
            val = data[field]
            if field == "email" and val:
                val = str(val).strip().lower()
            elif (
                field in ("phone", "identity_card_number", "full_name", "address")
                and val
            ):
                val = str(val).strip()
            setattr(emp, field, val)

    if new_pos_id_int:
        emp.position_id = new_pos_id_int

    try:
        emp.save()
    except Exception as exc:
        translate_employee_db_error(exc, operation="update_employee")

    # 11. Thu hồi session & token tức thì nếu bị deactive hoặc đổi mật khẩu hoặc giáng chức
    if emp.account_id and (is_deactivating or password_updated or is_demoting_manager):
        revoke_account_sessions_and_tokens(emp.account_id)

    return emp


@transaction.atomic
def soft_delete_employee(
    *,
    employee_id: int | None = None,
    employee: Employee | int | None = None,
    actor: Any = None,
    deleted_by: Any = None,
) -> dict[str, str]:
    """
    Xóa mềm nguyên tử cả Employee và Account liên kết (DEL-01, SRS 4.3.4).
    Đồng bộ đặt deleted_at = now, deleted_by = actor, Account.is_active = False.
    Thu hồi tức thì toàn bộ Session và RememberToken của tài khoản bị xóa.
    Đón bắt trigger fn_guard_soft_delete_and_restore và trả về 409 Conflict.
    """
    emp_id: int | None
    if isinstance(employee, Employee):
        emp_id = employee.id
    elif isinstance(employee, int):
        emp_id = employee
    else:
        emp_id = employee_id

    if emp_id is None:
        raise BusinessAPIException(
            code="PROP-4.3.3-P02",
            message="Nhân viên không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    emp = (
        Employee.objects.select_for_update(of=("self",))
        .select_related("position")
        .filter(id=emp_id, deleted_at__isnull=True)
        .first()
    )
    if not emp:
        raise BusinessAPIException(
            code="PROP-4.3.3-P02",
            message="Nhân viên không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    actor_account_id = getattr(actor or deleted_by, "id", actor or deleted_by)
    now = timezone.now()

    if emp.position and emp.position.code == "QL" and connection.vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s));",
                ["guard_last_active_manager"],
            )

    emp.deleted_at = now
    emp.deleted_by_id = actor_account_id
    account_to_revoke_id = emp.account_id

    try:
        emp.save(update_fields=["deleted_at", "deleted_by"])

        if emp.account_id:
            account = (
                Account.objects.select_for_update()
                .filter(id=emp.account_id, deleted_at__isnull=True)
                .first()
            )
            if account:
                account.deleted_at = now
                account.deleted_by_id = actor_account_id
                account.is_active = False
                account.save(update_fields=["deleted_at", "deleted_by", "is_active"])
    except Exception as exc:
        translate_employee_db_error(exc, operation="delete_employee")

    if account_to_revoke_id:
        revoke_account_sessions_and_tokens(account_to_revoke_id)

    return {
        "code": "MSG-4.3.4-M01",
        "message": "Xóa thành công",
    }
