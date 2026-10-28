"""
Serializers for Employee Management API per SRS 4.3.1–4.3.4 and Round 67 specifications.
Provides list, detail, create, update, summary, filter, and position serializers.
Strictly zero password or password-hash leakage in response representations.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.core.models import (
    AdministrativeDistrict,
    AdministrativeWard,
)
from apps.employees.models import Employee, Position

# Trạng thái nhân viên hợp lệ theo check constraint ck_employee_status_enum
VALID_EMPLOYEE_STATUSES = {"ACTIVE", "INACTIVE"}

# Bảng ánh xạ hiển thị trạng thái chuẩn Mockup Quản lý nhân viên
STATUS_DISPLAY_MAP = {
    "ACTIVE": "Đang hoạt động",
    "INACTIVE": "Không hoạt động",
}

# Các trường sắp xếp được phép (Whitelist Ordering)
ALLOWED_EMPLOYEE_ORDERING = {
    "id",
    "-id",
    "code",
    "-code",
    "full_name",
    "-full_name",
    "created_at",
    "-created_at",
    "updated_at",
    "-updated_at",
    "date_of_birth",
    "-date_of_birth",
    "status",
    "-status",
    "position",
    "-position",
    "position__name",
    "-position__name",
    "row_version",
    "-row_version",
}

# Bộ ký tự điều khiển ASCII và ký tự ẩn zero-width
DISALLOWED_CONTROL_CHARS = set(range(0, 32)) | {127}
ZERO_WIDTH_CHARS = {
    "\u200b",  # zero-width space
    "\u200c",  # zero-width non-joiner
    "\u200d",  # zero-width joiner
    "\ufeff",  # zero-width no-break space / BOM
    "\u00a0",  # non-breaking space
    "\u200e",  # left-to-right mark
    "\u200f",  # right-to-left mark
}

# Regex kiểm tra mật khẩu mạnh (SRS 4.3.3 / Rule 07)
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 50
SPECIAL_CHARACTERS = set("!@#$%^&*()_+-=[]{}|;:,.<>?")


def has_emoji_or_pictograph(text: str) -> bool:
    """
    Kiểm tra xem chuỗi có chứa emoji hoặc ký hiệu pictograph không.
    Sử dụng danh mục Unicode (So, Sk) và các dải mã emoji phổ biến.
    """
    for ch in text:
        cat = unicodedata.category(ch)
        if cat in ("So", "Sk"):
            return True
        code = ord(ch)
        if (
            (0x1F300 <= code <= 0x1F9FF)
            or (0x1FA00 <= code <= 0x1FAFF)
            or (0x2600 <= code <= 0x27BF)
        ):
            return True
    return False


def validate_raw_employee_name(value: Any) -> str:
    """
    Thẩm định và làm sạch chuỗi thô họ và tên nhân viên (full_name).
    Chấp nhận tiếng Việt có dấu hợp lệ.
    Từ chối ký tự điều khiển, byte NUL, ký tự zero-width, emoji/pictographs,
    và chuỗi vượt quá 45 ký tự trước khi đến tầng CSDL.
    """
    if value is None:
        raise serializers.ValidationError("Họ và tên nhân viên không được để trống.")
    if not isinstance(value, str):
        raise serializers.ValidationError("Họ và tên nhân viên phải là chuỗi ký tự.")
    if "\x00" in value:
        raise serializers.ValidationError("Họ và tên không được chứa ký tự NUL.")
    if len(value) > 45:
        raise serializers.ValidationError("Họ và tên không được vượt quá 45 ký tự.")
    for zw in ZERO_WIDTH_CHARS:
        if zw in value:
            raise serializers.ValidationError(
                "Họ và tên chứa ký tự ẩn hoặc không hợp lệ."
            )
    for ch in value:
        if ord(ch) in DISALLOWED_CONTROL_CHARS:
            raise serializers.ValidationError(
                "Họ và tên không được chứa ký tự điều khiển."
            )
    if has_emoji_or_pictograph(value):
        raise serializers.ValidationError(
            "Họ và tên không được chứa biểu tượng hoặc ký tự emoji."
        )

    trimmed = value.strip()
    if not trimmed:
        raise serializers.ValidationError("Họ và tên nhân viên không được để trống.")
    return re.sub(r"\s+", " ", trimmed)


def validate_raw_address(value: Any) -> str | None:
    """
    Thẩm định chuỗi thô địa chỉ chi tiết (address).
    """
    if value is None:
        return None
    if not isinstance(value, str):
        raise serializers.ValidationError("Địa chỉ phải là chuỗi ký tự.")
    if "\x00" in value:
        raise serializers.ValidationError("Địa chỉ không được chứa ký tự NUL.")
    if len(value) > 100:
        raise serializers.ValidationError("Địa chỉ không được vượt quá 100 ký tự.")
    for zw in ZERO_WIDTH_CHARS:
        if zw in value:
            raise serializers.ValidationError(
                "Địa chỉ chứa ký tự ẩn hoặc không hợp lệ."
            )
    for ch in value:
        if ord(ch) in DISALLOWED_CONTROL_CHARS:
            raise serializers.ValidationError(
                "Địa chỉ không được chứa ký tự điều khiển."
            )
    trimmed = value.strip()
    if not trimmed:
        return None
    return re.sub(r"\s+", " ", trimmed)


def validate_password_complexity(password: str) -> None:
    """
    Xác thực độ phức tạp mật khẩu theo SRS 4.3.3 và Rule 07 Security Baseline:
    - Độ dài từ 8 đến 50 ký tự.
    - Chứa ít nhất một chữ cái in thường [a-z].
    - Chứa ít nhất một chữ cái in hoa [A-Z].
    - Chứa ít nhất một chữ số [0-9].
    - Chứa ít nhất một ký tự đặc biệt trong tập !@#$%^&*()_+-=[]{}|;:,.<>?
    """
    if not isinstance(password, str):
        raise serializers.ValidationError("Mật khẩu phải là chuỗi ký tự.")
    if len(password) < PASSWORD_MIN_LENGTH or len(password) > PASSWORD_MAX_LENGTH:
        raise serializers.ValidationError(
            f"Mật khẩu phải có độ dài từ {PASSWORD_MIN_LENGTH} đến {PASSWORD_MAX_LENGTH} ký tự."
        )
    if not re.search(r"[a-z]", password):
        raise serializers.ValidationError(
            "Mật khẩu phải chứa ít nhất một chữ cái in thường."
        )
    if not re.search(r"[A-Z]", password):
        raise serializers.ValidationError(
            "Mật khẩu phải chứa ít nhất một chữ cái in hoa."
        )
    if not re.search(r"[0-9]", password):
        raise serializers.ValidationError("Mật khẩu phải chứa ít nhất một chữ số.")
    if not any(ch in SPECIAL_CHARACTERS for ch in password):
        raise serializers.ValidationError(
            "Mật khẩu phải chứa ít nhất một ký tự đặc biệt (!@#$%^&*()_+-=[]{}|;:,.<>?)."
        )


# ==============================================================================
# 1. POSITION SERIALIZER
# ==============================================================================


@extend_schema_serializer(component_name="PositionItem")
class PositionSerializer(serializers.ModelSerializer):
    """Serializer danh mục chức vụ nhân viên phục vụ dropdown và hiển thị."""

    class Meta:
        model = Position
        fields = ["id", "code", "name"]


# ==============================================================================
# 2. ADMINISTRATIVE HELPER SERIALIZERS
# ==============================================================================


class AdministrativeUnitItemSerializer(serializers.Serializer):
    """Cấu trúc tóm tắt đơn vị hành chính."""

    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()


# ==============================================================================
# 3. EMPLOYEE LIST SERIALIZER
# ==============================================================================


@extend_schema_serializer(component_name="EmployeeListItem")
class EmployeeListSerializer(serializers.Serializer):
    """
    Serializer cho từng dòng danh sách nhân viên trên bảng quản trị (SRS 4.3.1).
    Phù hợp 100% với các cột trên Mockup Quản lý nhân viên - Smart mobility.png:
    - NHÂN VIÊN: full_name, email
    - MÃ NV: code
    - CHỨC VỤ: position {id, code, name}
    - LIÊN HỆ: phone
    - KHU VỰC: area {district_name, province_name} (per TL-30)
    - TRẠNG THÁI: status, status_display
    - THAO TÁC: row_version phục vụ OCC
    Tuyệt đối không rò rỉ bất kỳ trường mật khẩu hoặc hash nào.
    """

    id = serializers.IntegerField(help_text="ID định danh nhân viên")
    code = serializers.CharField(help_text="Mã nhân viên (NVxxx / NVxxxx)")
    full_name = serializers.CharField(help_text="Họ và tên nhân viên")
    position = serializers.SerializerMethodField(help_text="Thông tin chức vụ")
    phone = serializers.CharField(help_text="Số điện thoại liên hệ")
    email = serializers.CharField(help_text="Địa chỉ email nhân viên")
    area = serializers.SerializerMethodField(
        help_text="Khu vực hành chính (quận/huyện và tỉnh/thành)"
    )
    status = serializers.CharField(help_text="Trạng thái mã: ACTIVE hoặc INACTIVE")
    status_display = serializers.SerializerMethodField(
        help_text="Tên trạng thái hiển thị tiếng Việt"
    )
    row_version = serializers.IntegerField(
        help_text="Token phiên bản kiểm soát tương tranh lạc quan"
    )

    @extend_schema_field(PositionSerializer)
    def get_position(self, obj: Employee) -> dict[str, Any] | None:
        pos = getattr(obj, "position", None)
        if not pos:
            return None
        return {
            "id": pos.id,
            "code": pos.code,
            "name": pos.name,
        }

    @extend_schema_field(
        serializers.DictField(
            child=serializers.CharField(allow_null=True),
            help_text="Khu vực hành chính gồm district_name và province_name",
        )
    )
    def get_area(self, obj: Employee) -> dict[str, str | None]:
        district = getattr(obj, "district", None)
        province = getattr(obj, "province", None)
        return {
            "district_name": district.name if district else None,
            "province_name": province.name if province else None,
        }

    @extend_schema_field(serializers.CharField)
    def get_status_display(self, obj: Employee) -> str:
        st = getattr(obj, "status", "ACTIVE")
        return STATUS_DISPLAY_MAP.get(st, st)


# ==============================================================================
# 4. EMPLOYEE DETAIL SERIALIZER
# ==============================================================================


@extend_schema_serializer(component_name="EmployeeDetail")
class EmployeeDetailSerializer(serializers.Serializer):
    """
    Serializer hồ sơ chi tiết toàn diện của nhân viên (SRS 4.3.1 & 4.3.3).
    Bao gồm thông tin cá nhân, 3 cấp hành chính (ID và tên), chức vụ,
    metadata tài khoản liên kết (id, role, is_active), và timestamps.
    Tuyệt đối ZERO trường mật khẩu, hash hay token bí mật!
    """

    id = serializers.IntegerField(help_text="ID định danh nhân viên")
    code = serializers.CharField(help_text="Mã nhân viên bất biến")
    full_name = serializers.CharField(help_text="Họ và tên nhân viên")
    date_of_birth = serializers.DateField(
        allow_null=True, help_text="Ngày sinh (trong quá khứ)"
    )
    gender = serializers.CharField(
        allow_null=True, help_text="Giới tính ('Nam' hoặc 'Nữ')"
    )
    identity_card_number = serializers.CharField(
        allow_null=True, help_text="Số CCCD/CMND"
    )
    phone = serializers.CharField(help_text="Số điện thoại")
    email = serializers.CharField(help_text="Email công việc")
    address = serializers.CharField(allow_null=True, help_text="Địa chỉ chi tiết")

    province_id = serializers.IntegerField(
        allow_null=True, help_text="ID Tỉnh/Thành phố"
    )
    province_name = serializers.SerializerMethodField(help_text="Tên Tỉnh/Thành phố")
    province = serializers.SerializerMethodField(help_text="Chi tiết Tỉnh/Thành phố")

    district_id = serializers.IntegerField(allow_null=True, help_text="ID Quận/Huyện")
    district_name = serializers.SerializerMethodField(help_text="Tên Quận/Huyện")
    district = serializers.SerializerMethodField(help_text="Chi tiết Quận/Huyện")

    ward_id = serializers.IntegerField(allow_null=True, help_text="ID Phường/Xã")
    ward_name = serializers.SerializerMethodField(help_text="Tên Phường/Xã")
    ward = serializers.SerializerMethodField(help_text="Chi tiết Phường/Xã")

    position = serializers.SerializerMethodField(help_text="Chức vụ công việc")
    account = serializers.SerializerMethodField(
        help_text="Metadata tài khoản (id, role, is_active)"
    )

    status = serializers.CharField(help_text="Mã trạng thái: ACTIVE, INACTIVE")
    status_display = serializers.SerializerMethodField(
        help_text="Tên trạng thái hiển thị tiếng Việt"
    )
    row_version = serializers.IntegerField(help_text="Token phiên bản OCC")
    created_at = serializers.DateTimeField(help_text="Thời điểm tạo hồ sơ")
    updated_at = serializers.DateTimeField(
        help_text="Thời điểm cập nhật hồ sơ gần nhất"
    )

    def get_province_name(self, obj: Employee) -> str | None:
        prov = getattr(obj, "province", None)
        return prov.name if prov else None

    @extend_schema_field(AdministrativeUnitItemSerializer)
    def get_province(self, obj: Employee) -> dict[str, Any] | None:
        prov = getattr(obj, "province", None)
        return {"id": prov.id, "code": prov.code, "name": prov.name} if prov else None

    def get_district_name(self, obj: Employee) -> str | None:
        dist = getattr(obj, "district", None)
        return dist.name if dist else None

    @extend_schema_field(AdministrativeUnitItemSerializer)
    def get_district(self, obj: Employee) -> dict[str, Any] | None:
        dist = getattr(obj, "district", None)
        return {"id": dist.id, "code": dist.code, "name": dist.name} if dist else None

    def get_ward_name(self, obj: Employee) -> str | None:
        w = getattr(obj, "ward", None)
        return w.name if w else None

    @extend_schema_field(AdministrativeUnitItemSerializer)
    def get_ward(self, obj: Employee) -> dict[str, Any] | None:
        w = getattr(obj, "ward", None)
        return {"id": w.id, "code": w.code, "name": w.name} if w else None

    @extend_schema_field(PositionSerializer)
    def get_position(self, obj: Employee) -> dict[str, Any] | None:
        pos = getattr(obj, "position", None)
        if not pos:
            return None
        return {
            "id": pos.id,
            "code": pos.code,
            "name": pos.name,
        }

    @extend_schema_field(
        serializers.DictField(
            help_text="Metadata tài khoản liên kết (id, role, is_active) - Zero password/hash"
        )
    )
    def get_account(self, obj: Employee) -> dict[str, Any] | None:
        acc = getattr(obj, "account", None)
        if not acc:
            return None
        return {
            "id": acc.id,
            "role": acc.role,
            "is_active": acc.is_active,
        }

    @extend_schema_field(serializers.CharField)
    def get_status_display(self, obj: Employee) -> str:
        st = getattr(obj, "status", "ACTIVE")
        return STATUS_DISPLAY_MAP.get(st, st)


# ==============================================================================
# 5. EMPLOYEE SUMMARY SERIALIZER (KPI SOT)
# ==============================================================================


@extend_schema_serializer(component_name="EmployeeSummary")
class EmployeeSummarySerializer(serializers.Serializer):
    """
    Serializer cho 4 thẻ chỉ số KPI ở đầu trang Quản lý nhân viên (SRS 4.3.1).
    Tính toán từ cùng nguồn dữ liệu SOT (Single Source of Truth):
    1. total_employees: Tổng nhân viên chưa xóa mềm
    2. active_employees: Nhân viên đang hoạt động (status = 'ACTIVE')
    3. inactive_employees: Nhân viên không hoạt động (status = 'INACTIVE')
    4. total_positions: Tổng số chức vụ đang hoạt động
    """

    total_employees = serializers.IntegerField(
        help_text="Tổng số nhân viên chưa bị xóa mềm trong hệ thống",
    )
    active_employees = serializers.IntegerField(
        help_text="Số nhân viên đang làm việc (ACTIVE)",
    )
    inactive_employees = serializers.IntegerField(
        help_text="Số nhân viên tạm ngưng hoặc không hoạt động (INACTIVE)",
    )
    total_positions = serializers.IntegerField(
        help_text="Tổng số chức vụ công việc chưa bị xóa mềm",
    )


# ==============================================================================
# 6. EMPLOYEE CREATE SERIALIZER
# ==============================================================================


@extend_schema_serializer(component_name="EmployeeCreateRequest")
class EmployeeCreateSerializer(serializers.Serializer):
    """
    Serializer thêm mới nhân viên và tài khoản nguyên tử (SRS 4.3.2).
    Xác thực chuỗi thô (raw-string), định dạng chuẩn, và độ phức tạp mật khẩu.
    Gom toàn bộ lỗi validation của mọi trường cùng lúc theo Rule 04.
    """

    full_name = serializers.CharField(
        max_length=45,
        required=True,
        help_text="Họ và tên nhân viên (tối đa 45 ký tự, hỗ trợ tiếng Việt có dấu)",
    )
    email = serializers.EmailField(
        max_length=100,
        required=True,
        help_text="Địa chỉ email công việc (tối đa 100 ký tự, chuẩn RFC)",
    )
    phone = serializers.CharField(
        max_length=15,
        required=True,
        help_text="Số điện thoại nhân viên (9-15 chữ số)",
    )
    position_id = serializers.IntegerField(
        required=True,
        help_text="ID chức vụ công việc (bắt buộc, tham chiếu position.id)",
    )
    password = serializers.CharField(
        max_length=PASSWORD_MAX_LENGTH,
        required=True,
        write_only=True,
        style={"input_type": "password"},
        help_text="Mật khẩu khởi tạo (8-50 ký tự, ít nhất 1 hoa, 1 thường, 1 số, 1 ký tự đặc biệt)",
    )
    code = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Mã nhân viên tùy chọn (định dạng ^NV[0-9]{3,4}$; nếu bỏ trống hệ thống tự sinh có khóa cố vấn)",
    )
    date_of_birth = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Ngày sinh (bắt buộc phải trong quá khứ)",
    )
    gender = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Giới tính ('Nam' hoặc 'Nữ')",
    )
    identity_card_number = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Số CCCD/CMND (9-20 chữ số)",
    )
    address = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Địa chỉ cư trú chi tiết (tối đa 100 ký tự)",
    )
    province_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID Tỉnh/Thành phố",
    )
    district_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID Quận/Huyện",
    )
    ward_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID Phường/Xã",
    )
    status = serializers.CharField(
        max_length=20,
        required=False,
        default="ACTIVE",
        help_text="Trạng thái khởi tạo: ACTIVE hoặc INACTIVE (mặc định ACTIVE)",
    )

    def validate_full_name(self, value: Any) -> str:
        return validate_raw_employee_name(value)

    def validate_address(self, value: Any) -> str | None:
        return validate_raw_address(value)

    def validate_phone(self, value: str) -> str:
        clean = (value or "").strip()
        # Chặn đứng các chữ số look-alike phi ASCII
        if not all("0" <= c <= "9" for c in clean) or not (9 <= len(clean) <= 15):
            raise serializers.ValidationError(
                "Số điện thoại phải là dãy số từ 9 đến 15 chữ số."
            )
        return clean

    def validate_identity_card_number(self, value: str | None) -> str | None:
        if not value or not str(value).strip():
            return None
        clean = str(value).strip()
        if not all("0" <= c <= "9" for c in clean) or not (9 <= len(clean) <= 20):
            raise serializers.ValidationError(
                "Số CCCD/CMND phải là dãy số từ 9 đến 20 chữ số."
            )
        return clean

    def validate_code(self, value: str | None) -> str | None:
        if not value or not str(value).strip():
            return None
        clean = str(value).strip().upper()
        if not re.match(r"^NV[0-9]{3,4}$", clean):
            raise serializers.ValidationError("Mã nhân viên không đúng định dạng.")
        return clean

    def validate_date_of_birth(self, value: Any) -> Any:
        if value and value >= timezone.localdate():
            raise serializers.ValidationError("Ngày sinh phải là ngày trong quá khứ.")
        return value

    def validate_gender(self, value: str | None) -> str | None:
        if not value or not str(value).strip():
            return None
        clean = str(value).strip()
        if clean not in ("Nam", "Nữ"):
            raise serializers.ValidationError(
                "Giới tính không hợp lệ (chỉ chấp nhận 'Nam' hoặc 'Nữ')."
            )
        return clean

    def validate_status(self, value: str | None) -> str:
        if not value or not str(value).strip():
            return "ACTIVE"
        clean = str(value).strip().upper()
        if clean not in VALID_EMPLOYEE_STATUSES:
            raise serializers.ValidationError(
                "Trạng thái nhân viên không hợp lệ (chỉ chấp nhận ACTIVE hoặc INACTIVE)."
            )
        return clean

    def validate_position_id(self, value: int) -> int:
        if not Position.objects.filter(id=value, deleted_at__isnull=True).exists():
            raise serializers.ValidationError("Chức vụ không tồn tại hoặc đã bị xóa.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """
        Xác thực tổng hợp toàn diện và gom toàn bộ lỗi validation theo Rule 04.
        """
        errors: dict[str, list[str]] = {}

        # 1. Thẩm định độ phức tạp mật khẩu
        pwd = attrs.get("password")
        if pwd:
            try:
                validate_password_complexity(pwd)
            except serializers.ValidationError as exc:
                if isinstance(exc.detail, list):
                    errors.setdefault("password", []).extend(
                        [str(item) for item in exc.detail]
                    )
                else:
                    errors.setdefault("password", []).append(str(exc.detail))

        # 2. Thẩm định phân cấp địa giới hành chính
        ward_id = attrs.get("ward_id")
        dist_id = attrs.get("district_id")
        prov_id = attrs.get("province_id")

        if ward_id is not None and dist_id is None:
            errors.setdefault("ward_id", []).append(
                "Cơ cấu địa giới hành chính không hợp lệ (Phường/Xã cần đi kèm Quận/Huyện)."
            )
        if dist_id is not None and prov_id is None:
            errors.setdefault("district_id", []).append(
                "Cơ cấu địa giới hành chính không hợp lệ (Quận/Huyện cần đi kèm Tỉnh/Thành phố)."
            )

        if (
            ward_id
            and dist_id
            and not AdministrativeWard.objects.filter(
                id=ward_id, district_id=dist_id
            ).exists()
        ):
            errors.setdefault("ward_id", []).append(
                "Phường/Xã không thuộc Quận/Huyện đã chọn."
            )

        if (
            dist_id
            and prov_id
            and not AdministrativeDistrict.objects.filter(
                id=dist_id, province_id=prov_id
            ).exists()
        ):
            errors.setdefault("district_id", []).append(
                "Quận/Huyện không thuộc Tỉnh/Thành phố đã chọn."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs


# ==============================================================================
# 7. EMPLOYEE UPDATE SERIALIZER
# ==============================================================================


@extend_schema_serializer(component_name="EmployeeUpdateRequest")
class EmployeeUpdateSerializer(serializers.Serializer):
    """
    Serializer cập nhật thông tin nhân viên (PATCH /api/v1/employees/{id}/, SRS 4.3.3).
    Bắt buộc trường row_version để kiểm soát tương tranh lạc quan OCC.
    Mã nhân viên (code) là bất biến - cấm chỉnh sửa.
    Mật khẩu là tùy chọn, nếu truyền lên sẽ cập nhật mật khẩu mới và xác thực độ phức tạp.
    """

    row_version = serializers.IntegerField(
        required=True,
        help_text="Token phiên bản OCC hiện tại (bắt buộc)",
    )
    full_name = serializers.CharField(
        max_length=45,
        required=False,
        help_text="Họ và tên nhân viên mới",
    )
    email = serializers.EmailField(
        max_length=100,
        required=False,
        help_text="Email mới",
    )
    phone = serializers.CharField(
        max_length=15,
        required=False,
        help_text="Số điện thoại mới",
    )
    position_id = serializers.IntegerField(
        required=False,
        help_text="ID chức vụ mới (suy diễn lại Account.role)",
    )
    password = serializers.CharField(
        max_length=PASSWORD_MAX_LENGTH,
        required=False,
        write_only=True,
        style={"input_type": "password"},
        help_text="Mật khẩu mới (tùy chọn)",
    )
    date_of_birth = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Ngày sinh mới",
    )
    gender = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Giới tính mới",
    )
    identity_card_number = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Số CCCD/CMND mới",
    )
    address = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Địa chỉ mới",
    )
    province_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID Tỉnh/Thành phố mới",
    )
    district_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID Quận/Huyện mới",
    )
    ward_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="ID Phường/Xã mới",
    )
    status = serializers.CharField(
        max_length=20,
        required=False,
        help_text="Trạng thái mới: ACTIVE hoặc INACTIVE (đồng bộ Account.is_active và thu hồi session)",
    )

    def validate_full_name(self, value: Any) -> str:
        return validate_raw_employee_name(value)

    def validate_address(self, value: Any) -> str | None:
        return validate_raw_address(value)

    def validate_phone(self, value: str) -> str:
        clean = (value or "").strip()
        if not all("0" <= c <= "9" for c in clean) or not (9 <= len(clean) <= 15):
            raise serializers.ValidationError(
                "Số điện thoại phải là dãy số từ 9 đến 15 chữ số."
            )
        return clean

    def validate_identity_card_number(self, value: str | None) -> str | None:
        if not value or not str(value).strip():
            return None
        clean = str(value).strip()
        if not all("0" <= c <= "9" for c in clean) or not (9 <= len(clean) <= 20):
            raise serializers.ValidationError(
                "Số CCCD/CMND phải là dãy số từ 9 đến 20 chữ số."
            )
        return clean

    def validate_date_of_birth(self, value: Any) -> Any:
        if value and value >= timezone.localdate():
            raise serializers.ValidationError("Ngày sinh phải là ngày trong quá khứ.")
        return value

    def validate_gender(self, value: str | None) -> str | None:
        if not value or not str(value).strip():
            return None
        clean = str(value).strip()
        if clean not in ("Nam", "Nữ"):
            raise serializers.ValidationError(
                "Giới tính không hợp lệ (chỉ chấp nhận 'Nam' hoặc 'Nữ')."
            )
        return clean

    def validate_status(self, value: str) -> str:
        clean = (value or "").strip().upper()
        if clean not in VALID_EMPLOYEE_STATUSES:
            raise serializers.ValidationError(
                "Trạng thái nhân viên không hợp lệ (chỉ chấp nhận ACTIVE hoặc INACTIVE)."
            )
        return clean

    def validate_position_id(self, value: int) -> int:
        if not Position.objects.filter(id=value, deleted_at__isnull=True).exists():
            raise serializers.ValidationError("Chức vụ không tồn tại hoặc đã bị xóa.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """
        Kiểm tra tính toàn vẹn khi cập nhật:
        - Bất biến trường code (nếu client truyền code trong payload, báo lỗi).
        - Kiểm tra độ phức tạp mật khẩu nếu có truyền password.
        - Kiểm tra tính nhất quán địa giới hành chính.
        """
        errors: dict[str, list[str]] = {}

        # 1. Chặn đứng sửa đổi mã nhân viên
        if hasattr(self, "initial_data") and "code" in self.initial_data:
            errors.setdefault("code", []).append(
                "Mã nhân viên là bất biến, không được phép chỉnh sửa."
            )

        # 2. Thẩm định mật khẩu nếu có cập nhật
        pwd = attrs.get("password")
        if pwd:
            try:
                validate_password_complexity(pwd)
            except serializers.ValidationError as exc:
                if isinstance(exc.detail, list):
                    errors.setdefault("password", []).extend(
                        [str(item) for item in exc.detail]
                    )
                else:
                    errors.setdefault("password", []).append(str(exc.detail))

        # 3. Thẩm định địa giới hành chính nếu có cập nhật
        ward_id = attrs.get("ward_id")
        dist_id = attrs.get("district_id")
        prov_id = attrs.get("province_id")

        if ward_id is not None and dist_id is None and "district_id" in attrs:
            errors.setdefault("ward_id", []).append(
                "Cơ cấu địa giới hành chính không hợp lệ (Phường/Xã cần đi kèm Quận/Huyện)."
            )
        if dist_id is not None and prov_id is None and "province_id" in attrs:
            errors.setdefault("district_id", []).append(
                "Cơ cấu địa giới hành chính không hợp lệ (Quận/Huyện cần đi kèm Tỉnh/Thành phố)."
            )

        if (
            ward_id
            and dist_id
            and not AdministrativeWard.objects.filter(
                id=ward_id, district_id=dist_id
            ).exists()
        ):
            errors.setdefault("ward_id", []).append(
                "Phường/Xã không thuộc Quận/Huyện đã chọn."
            )

        if (
            dist_id
            and prov_id
            and not AdministrativeDistrict.objects.filter(
                id=dist_id, province_id=prov_id
            ).exists()
        ):
            errors.setdefault("district_id", []).append(
                "Quận/Huyện không thuộc Tỉnh/Thành phố đã chọn."
            )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs


# ==============================================================================
# 8. EMPLOYEE FILTER SERIALIZER
# ==============================================================================


class EmployeeFilterSerializer(serializers.Serializer):
    """
    Serializer thẩm định các query parameters tìm kiếm/lọc danh sách nhân viên (SRS 4.3.1).
    """

    q = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Tìm kiếm chuỗi con trên tên, mã, email",
    )
    name = serializers.CharField(
        required=False, allow_blank=True, help_text="Tìm kiếm họ và tên"
    )
    code = serializers.CharField(
        required=False, allow_blank=True, help_text="Tìm kiếm mã nhân viên"
    )
    address = serializers.CharField(
        required=False, allow_blank=True, help_text="Tìm kiếm theo địa chỉ"
    )
    birth_from = serializers.DateField(
        required=False, allow_null=True, help_text="Ngày sinh từ ngày"
    )
    birth_to = serializers.DateField(
        required=False, allow_null=True, help_text="Ngày sinh đến ngày"
    )
    position = serializers.CharField(
        required=False, allow_blank=True, help_text="Lọc theo mã hoặc ID chức vụ"
    )
    status = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Lọc theo trạng thái: ACTIVE, INACTIVE",
    )
    ordering = serializers.ChoiceField(
        choices=list(ALLOWED_EMPLOYEE_ORDERING),
        required=False,
        allow_blank=True,
        help_text="Trường sắp xếp trong whitelist",
    )
    page = serializers.IntegerField(
        min_value=1, required=False, help_text="Số trang kết quả"
    )
    page_size = serializers.IntegerField(
        min_value=1, max_value=100, required=False, help_text="Số bản ghi mỗi trang"
    )

    def validate_status(self, value: str) -> str:
        if value and value.strip():
            clean = value.strip().upper()
            if clean not in VALID_EMPLOYEE_STATUSES:
                raise serializers.ValidationError(
                    "Trạng thái lọc không hợp lệ (chỉ chấp nhận ACTIVE hoặc INACTIVE)."
                )
            return clean
        return ""

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        birth_from = attrs.get("birth_from")
        birth_to = attrs.get("birth_to")
        if birth_from and birth_to and birth_from > birth_to:
            raise serializers.ValidationError(
                {
                    "birth_from": [
                        "Khoảng thời gian ngày sinh không hợp lệ (Từ ngày phải nhỏ hơn hoặc bằng Đến ngày)."
                    ]
                }
            )
        return attrs


# ==============================================================================
# 9. EMPLOYEE DELETE SUCCESS SERIALIZER
# ==============================================================================


@extend_schema_serializer(component_name="EmployeeDeleteSuccess")
class EmployeeDeleteSuccessSerializer(serializers.Serializer):
    """Serializer phản hồi xóa mềm thành công per SRS 4.3.4 (MSG-4.3.4-M01)."""

    code = serializers.CharField(
        default="MSG-4.3.4-M01", help_text="Mã thông báo kết quả"
    )
    message = serializers.CharField(
        default="Xóa thành công", help_text="Thông điệp thành công"
    )
    details = serializers.DictField(default=dict, help_text="Chi tiết bổ sung nếu có")
