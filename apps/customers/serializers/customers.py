"""
Serializers for Customer Management API per SRS 4.4.1–4.4.5 and Round 66 specifications.
Provides list, detail, create, update, summary, filter, and sub-grid serializers.
"""

import re
from typing import Any

from django.utils import timezone
from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.core.models import (
    AdministrativeDistrict,
    AdministrativeProvince,
    AdministrativeWard,
)
from apps.customers.models import Customer
from apps.customers.selectors.customers import ALLOWED_ORDERING_FIELDS

VALID_CUSTOMER_STATUSES = {"ACTIVE", "SUSPENDED", "BLACKLISTED"}


# Control characters and zero-width characters for raw-string validation
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

STATUS_DISPLAY_MAP = {
    "ACTIVE": "Đang hoạt động",
    "SUSPENDED": "Tạm ngưng",
    "BLACKLISTED": "Danh sách đen",
}


def validate_raw_name(value: Any) -> str:
    """
    Validate and clean customer full_name raw string.
    Accepts legitimate Vietnamese names with diacritics.
    Strictly rejects control characters, zero-width characters, NUL byte,
    and over-long strings before database execution.
    """
    if value is None:
        raise serializers.ValidationError("Họ và tên khách hàng không được để trống.")
    if not isinstance(value, str):
        raise serializers.ValidationError("Họ và tên khách hàng phải là chuỗi ký tự.")
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
    trimmed = value.strip()
    if not trimmed:
        raise serializers.ValidationError("Họ và tên khách hàng không được để trống.")
    # Collapse multiple consecutive whitespace characters
    return re.sub(r"\s+", " ", trimmed)


class AdministrativeProvinceSerializer(serializers.ModelSerializer):
    """Province summary representation."""

    class Meta:
        model = AdministrativeProvince
        fields = ["id", "code", "name"]


class AdministrativeDistrictSerializer(serializers.ModelSerializer):
    """District summary representation."""

    class Meta:
        model = AdministrativeDistrict
        fields = ["id", "code", "name"]


class AdministrativeWardSerializer(serializers.ModelSerializer):
    """Ward summary representation."""

    class Meta:
        model = AdministrativeWard
        fields = ["id", "code", "name"]


class CustomerVehicleSubgridSerializer(serializers.Serializer):
    """
    Vehicle subgrid row representation in Customer Detail view (SRS 4.4.2).
    Includes vehicle specifications, type information, and representative ticket status.
    """

    id = serializers.IntegerField()
    code = serializers.CharField()
    license_plate = serializers.CharField()
    brand = serializers.CharField(allow_null=True, required=False)
    model_name = serializers.CharField()
    color = serializers.CharField(allow_null=True, required=False)
    image_url = serializers.CharField(allow_null=True, required=False)
    notes = serializers.CharField(allow_null=True, required=False)
    vehicle_type_id = serializers.IntegerField(allow_null=True, required=False)
    vehicle_type_name = serializers.CharField(allow_blank=True, required=False)
    vehicle_type = serializers.DictField(allow_null=True, required=False)
    ticket_type_name = serializers.CharField(allow_null=True, required=False)
    ticket_expires_at = serializers.DateTimeField(allow_null=True, required=False)
    ticket = serializers.DictField(allow_null=True, required=False)


class CustomerVehicleCreateSerializer(serializers.Serializer):
    """
    Serializer for creating a vehicle within atomic customer creation (SRS 4.4.3).
    """

    license_plate = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Biển số xe (vd: 51K-992.14)",
    )
    model_name = serializers.CharField(
        max_length=50,
        required=True,
        help_text="Tên dòng xe (vd: VF8, Camry)",
    )
    vehicle_type_id = serializers.IntegerField(
        required=True,
        help_text="ID loại xe (chỉ phục vụ CAR hoặc EV)",
    )
    code = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Mã xe tùy chọn (hệ thống tự sinh nếu bỏ trống)",
    )
    brand = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    color = serializers.CharField(
        max_length=30,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    image_url = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )


@extend_schema_serializer(component_name="CustomerListItem")
class CustomerListSerializer(serializers.Serializer):
    """
    Serializer for customer list table items (SRS 4.4.1).
    Provides PII masking if is_anonymized = True per Decree 13/2023/NĐ-CP (OQ-12).
    """

    id = serializers.IntegerField()
    code = serializers.CharField()
    full_name = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    identity_card_number = serializers.SerializerMethodField()
    status = serializers.CharField()
    status_display = serializers.SerializerMethodField()
    vehicles_count = serializers.SerializerMethodField()
    has_active_ticket = serializers.SerializerMethodField()
    row_version = serializers.IntegerField()
    is_anonymized = serializers.BooleanField()
    created_at = serializers.DateTimeField()

    def get_full_name(self, obj: Customer) -> str:
        if getattr(obj, "is_anonymized", False):
            return "Khách hàng ẩn danh"
        return getattr(obj, "full_name", "")

    def get_phone(self, obj: Customer) -> str:
        if getattr(obj, "is_anonymized", False):
            return "***"
        return getattr(obj, "phone", "")

    def get_identity_card_number(self, obj: Customer) -> str:
        if getattr(obj, "is_anonymized", False):
            return "***"
        return getattr(obj, "identity_card_number", "")

    def get_status_display(self, obj: Customer) -> str:
        status_code = getattr(obj, "status", "ACTIVE")
        return STATUS_DISPLAY_MAP.get(status_code, status_code)

    @extend_schema_field(serializers.IntegerField)
    def get_vehicles_count(self, obj: Customer) -> int:
        if hasattr(obj, "vehicles_count"):
            return int(obj.vehicles_count)
        return obj.vehicles.filter(deleted_at__isnull=True).count()

    @extend_schema_field(serializers.BooleanField)
    def get_has_active_ticket(self, obj: Customer) -> bool:
        if hasattr(obj, "has_active_ticket"):
            return bool(obj.has_active_ticket)
        return obj.tickets.filter(
            deleted_at__isnull=True,
            status__in=["ACTIVE", "RENEWING"],
            effective_to__gt=timezone.now(),
        ).exists()


@extend_schema_serializer(component_name="CustomerManagementDetail")
class CustomerDetailSerializer(serializers.Serializer):
    """
    Serializer for comprehensive customer profile detail (SRS 4.4.2).
    Includes administrative units, OCC token, and vehicle subgrid with representative tickets.
    """

    id = serializers.IntegerField()
    code = serializers.CharField()
    full_name = serializers.SerializerMethodField()
    date_of_birth = serializers.SerializerMethodField()
    gender = serializers.CharField(allow_null=True)
    identity_card_number = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    address = serializers.SerializerMethodField()
    province_id = serializers.IntegerField(allow_null=True)
    province_name = serializers.SerializerMethodField()
    province = serializers.SerializerMethodField()
    district_id = serializers.IntegerField(allow_null=True)
    district_name = serializers.SerializerMethodField()
    district = serializers.SerializerMethodField()
    ward_id = serializers.IntegerField(allow_null=True)
    ward_name = serializers.SerializerMethodField()
    ward = serializers.SerializerMethodField()
    status = serializers.CharField()
    status_display = serializers.SerializerMethodField()
    status_reason = serializers.CharField(allow_null=True)
    is_anonymized = serializers.BooleanField()
    anonymized_at = serializers.DateTimeField(allow_null=True)
    row_version = serializers.IntegerField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    vehicles = serializers.SerializerMethodField()

    def get_full_name(self, obj: Customer) -> str:
        if getattr(obj, "is_anonymized", False):
            return "Khách hàng ẩn danh"
        return getattr(obj, "full_name", "")

    def get_date_of_birth(self, obj: Customer) -> Any:
        if getattr(obj, "is_anonymized", False):
            return None
        return getattr(obj, "date_of_birth", None)

    def get_identity_card_number(self, obj: Customer) -> str:
        if getattr(obj, "is_anonymized", False):
            return "***"
        return getattr(obj, "identity_card_number", "")

    def get_phone(self, obj: Customer) -> str:
        if getattr(obj, "is_anonymized", False):
            return "***"
        return getattr(obj, "phone", "")

    def get_email(self, obj: Customer) -> str | None:
        if getattr(obj, "is_anonymized", False):
            return "***"
        return getattr(obj, "email", None)

    def get_address(self, obj: Customer) -> str | None:
        if getattr(obj, "is_anonymized", False):
            return "***"
        return getattr(obj, "address", None)

    def get_province_name(self, obj: Customer) -> str | None:
        prov = getattr(obj, "province", None)
        return prov.name if prov else None

    def get_province(self, obj: Customer) -> dict[str, Any] | None:
        prov = getattr(obj, "province", None)
        return AdministrativeProvinceSerializer(prov).data if prov else None

    def get_district_name(self, obj: Customer) -> str | None:
        dist = getattr(obj, "district", None)
        return dist.name if dist else None

    def get_district(self, obj: Customer) -> dict[str, Any] | None:
        dist = getattr(obj, "district", None)
        return AdministrativeDistrictSerializer(dist).data if dist else None

    def get_ward_name(self, obj: Customer) -> str | None:
        ward = getattr(obj, "ward", None)
        return ward.name if ward else None

    def get_ward(self, obj: Customer) -> dict[str, Any] | None:
        ward = getattr(obj, "ward", None)
        return AdministrativeWardSerializer(ward).data if ward else None

    def get_status_display(self, obj: Customer) -> str:
        status_code = getattr(obj, "status", "ACTIVE")
        return STATUS_DISPLAY_MAP.get(status_code, status_code)

    def get_vehicles(self, obj: Customer) -> list[dict[str, Any]]:
        annotated = getattr(obj, "annotated_vehicles", None)
        if annotated is None:
            from apps.customers.selectors.customers import get_customer_by_id

            hydrated = get_customer_by_id(obj.id)
            annotated = getattr(hydrated, "annotated_vehicles", [])
        return list(CustomerVehicleSubgridSerializer(annotated, many=True).data)


class CustomerCreateSerializer(serializers.Serializer):
    """
    Serializer for creating a customer with optional vehicles array (SRS 4.4.3).
    Implements raw-string validation, administrative hierarchy consistency,
    and returns all validation errors consolidated together per Rule 04.
    """

    code = serializers.CharField(
        max_length=10,
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Mã khách hàng tự chọn. Hệ thống tự động sinh KH%04d nếu bỏ trống.",
    )
    full_name = serializers.CharField(
        max_length=45,
        required=True,
        help_text="Họ và tên khách hàng (chấp nhận tiếng Việt có dấu)",
    )
    date_of_birth = serializers.DateField(
        required=False,
        allow_null=True,
        help_text="Ngày sinh (phải là ngày trong quá khứ)",
    )
    gender = serializers.ChoiceField(
        choices=["Nam", "Nữ"],
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    identity_card_number = serializers.CharField(
        max_length=20,
        required=True,
        help_text="Số CCCD/CMND (9-20 chữ số)",
    )
    phone = serializers.CharField(
        max_length=15,
        required=True,
        help_text="Số điện thoại (9-15 chữ số)",
    )
    email = serializers.EmailField(
        max_length=100,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    address = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    province_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    district_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    ward_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    status = serializers.CharField(
        max_length=20,
        default="ACTIVE",
        required=False,
        help_text="Trạng thái khách hàng: ACTIVE, SUSPENDED, BLACKLISTED",
    )
    status_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Lý do khóa (bắt buộc khi status = BLACKLISTED)",
    )
    vehicles = CustomerVehicleCreateSerializer(
        many=True,
        required=False,
        allow_empty=True,
        help_text="Mảng phương tiện đăng ký kèm theo",
    )

    def validate_full_name(self, value: str) -> str:
        return validate_raw_name(value)

    def validate_code(self, value: str | None) -> str | None:
        if value and value.strip():
            clean = value.strip()
            if not re.match(r"^[A-Za-z0-9-]+$", clean):
                raise serializers.ValidationError(
                    "Mã khách hàng không đúng định dạng (chỉ chấp nhận chữ cái, số và dấu gạch ngang)."
                )
            return clean
        return None

    def validate_phone(self, value: str) -> str:
        clean = (value or "").strip()
        if not re.match(r"^[0-9]{9,15}$", clean):
            raise serializers.ValidationError(
                "Số điện thoại phải là dãy số từ 9 đến 15 chữ số."
            )
        return clean

    def validate_identity_card_number(self, value: str) -> str:
        clean = (value or "").strip()
        if not re.match(r"^[0-9]{9,20}$", clean):
            raise serializers.ValidationError(
                "Số CCCD/CMND phải là dãy số từ 9 đến 20 chữ số."
            )
        return clean

    def validate_date_of_birth(self, value: Any) -> Any:
        if value and value >= timezone.localdate():
            raise serializers.ValidationError("Ngày sinh phải là ngày trong quá khứ.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        errors: dict[str, list[str]] = {}

        # 1. Status enum check
        if "status" in attrs and attrs["status"]:
            clean_status = str(attrs["status"]).strip().upper()
            if clean_status not in VALID_CUSTOMER_STATUSES:
                errors.setdefault("status", []).append(
                    "Trạng thái khách hàng không hợp lệ."
                )
            else:
                attrs["status"] = clean_status

        # 2. Blacklist reason requirement
        if attrs.get("status") == "BLACKLISTED":
            reason = attrs.get("status_reason")
            if not reason or not str(reason).strip():
                errors.setdefault("status_reason", []).append(
                    "Lý do khóa là bắt buộc khi khách hàng thuộc danh sách đen."
                )

        # 3. Administrative hierarchy checks
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


class CustomerUpdateSerializer(serializers.Serializer):
    """
    Serializer for partial customer update (PATCH /api/v1/customers/{id}/, SRS 4.4.4).
    Mandates row_version for optimistic concurrency control.
    Code is immutable per REQ-4.4.4-F01.
    """

    row_version = serializers.IntegerField(
        required=True,
        help_text="Token kiểm soát cập nhật đồng thời (Optimistic Concurrency Control)",
    )
    code = serializers.CharField(
        read_only=True,
        help_text="Mã khách hàng là bất biến, không được phép chỉnh sửa.",
    )
    full_name = serializers.CharField(
        max_length=45,
        required=False,
    )
    date_of_birth = serializers.DateField(
        required=False,
        allow_null=True,
    )
    gender = serializers.ChoiceField(
        choices=["Nam", "Nữ"],
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    identity_card_number = serializers.CharField(
        max_length=20,
        required=False,
    )
    phone = serializers.CharField(
        max_length=15,
        required=False,
    )
    email = serializers.EmailField(
        max_length=100,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    address = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    province_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    district_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    ward_id = serializers.IntegerField(
        required=False,
        allow_null=True,
    )
    status = serializers.CharField(
        max_length=20,
        required=False,
        help_text="Trạng thái khách hàng: ACTIVE, SUSPENDED, BLACKLISTED",
    )
    status_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    def validate_full_name(self, value: str) -> str:
        return validate_raw_name(value)

    def validate_phone(self, value: str) -> str:
        clean = (value or "").strip()
        if not re.match(r"^[0-9]{9,15}$", clean):
            raise serializers.ValidationError(
                "Số điện thoại phải là dãy số từ 9 đến 15 chữ số."
            )
        return clean

    def validate_identity_card_number(self, value: str) -> str:
        clean = (value or "").strip()
        if not re.match(r"^[0-9]{9,20}$", clean):
            raise serializers.ValidationError(
                "Số CCCD/CMND phải là dãy số từ 9 đến 20 chữ số."
            )
        return clean

    def validate_date_of_birth(self, value: Any) -> Any:
        if value and value >= timezone.localdate():
            raise serializers.ValidationError("Ngày sinh phải là ngày trong quá khứ.")
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        errors: dict[str, list[str]] = {}

        if "status" in attrs and attrs["status"]:
            clean_status = str(attrs["status"]).strip().upper()
            if clean_status not in VALID_CUSTOMER_STATUSES:
                errors.setdefault("status", []).append(
                    "Trạng thái khách hàng không hợp lệ."
                )
            else:
                attrs["status"] = clean_status

        if attrs.get("status") == "BLACKLISTED":
            reason = attrs.get("status_reason")
            if not reason or not str(reason).strip():
                errors.setdefault("status_reason", []).append(
                    "Lý do khóa là bắt buộc khi khách hàng thuộc danh sách đen."
                )

        if errors:
            raise serializers.ValidationError(errors)

        return attrs


class CustomerFilterSerializer(serializers.Serializer):
    """
    Serializer for validating query parameters in customer list view.
    """

    code = serializers.CharField(required=False, allow_blank=True)
    name = serializers.CharField(required=False, allow_blank=True)
    full_name = serializers.CharField(required=False, allow_blank=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    identity_card = serializers.CharField(required=False, allow_blank=True)
    identity_card_number = serializers.CharField(required=False, allow_blank=True)
    status = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Lọc theo trạng thái: ACTIVE, SUSPENDED, BLACKLISTED",
    )
    ordering = serializers.ChoiceField(
        choices=list(ALLOWED_ORDERING_FIELDS),
        required=False,
        allow_blank=True,
    )
    page = serializers.IntegerField(min_value=1, required=False)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False)

    def validate_status(self, value: str) -> str:
        if value and value.strip():
            clean_status = value.strip().upper()
            if clean_status not in VALID_CUSTOMER_STATUSES:
                raise serializers.ValidationError(
                    "Trạng thái khách hàng không hợp lệ (chỉ chấp nhận ACTIVE, SUSPENDED, BLACKLISTED)."
                )
            return clean_status
        return ""


@extend_schema_serializer(component_name="CustomerSummary")
class CustomerSummarySerializer(serializers.Serializer):
    """
    Serializer for the 4 KPI summary cards at the top of the Khách hàng screen.
    Guarantees compatibility with both active_subscriptions and active_subscribers aliases.
    """

    total_customers = serializers.IntegerField(
        help_text="Tổng số khách hàng chưa bị xóa mềm trong hệ thống",
    )
    active_subscriptions = serializers.IntegerField(
        help_text="Số khách hàng có thuê bao kích hoạt",
    )
    active_subscribers = serializers.IntegerField(
        help_text="Bí danh của active_subscriptions",
    )
    expiring_soon_subscriptions = serializers.IntegerField(
        help_text="Số khách hàng có thuê bao sắp hết hạn trong vòng 7 ngày",
    )
    expiring_soon_subscribers = serializers.IntegerField(
        help_text="Bí danh của expiring_soon_subscriptions",
    )
    blacklisted_or_suspended = serializers.IntegerField(
        help_text="Số khách hàng ở trạng thái SUSPENDED hoặc BLACKLISTED",
    )


class CustomerDeleteSuccessSerializer(serializers.Serializer):
    """Serializer for successful soft deletion response envelope (DEL-02)."""

    code = serializers.CharField(default="MSG-4.4.5-M01")
    message = serializers.CharField(default="Xóa thành công")
    details = serializers.DictField(default=dict)
