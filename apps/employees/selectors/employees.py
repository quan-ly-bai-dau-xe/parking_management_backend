"""
Selectors for Employee Management API.
Provides optimized querysets, Single Source of Truth (SOT) KPI metrics,
and deterministic detail retrieval with Zero N+1 guarantees.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.db.models import Count, IntegerField, Max, Q, QuerySet, Subquery, Value
from rest_framework import status as rest_status

from apps.core.exceptions import BusinessAPIException
from apps.employees.models import Employee, Position
from apps.parking.selectors.search import escape_like

ALLOWED_ORDERING_FIELDS: set[str] = {
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


def list_positions() -> QuerySet[Position]:
    """
    Retrieve all active positions ordered deterministically by id ASC.
    Excludes soft-deleted positions (deleted_at IS NOT NULL).
    """
    return Position.objects.filter(deleted_at__isnull=True).order_by("id")


def get_employee_summary() -> dict[str, int]:
    """
    Single Source of Truth (SOT) for the 4 dashboard KPI cards matching list filters 100%:
    1. total_employees: Count of all active (non-soft-deleted) employees.
    2. active_employees: Count of active employees with status='ACTIVE'.
    3. inactive_employees: Count of active employees with status='INACTIVE'.
    4. total_positions: Count of active (non-soft-deleted) positions.

    Executes in a single SQL query via aggregate() with a Subquery, with fallback
    for empty tables.
    """
    pos_sq = Subquery(
        Position.objects.filter(deleted_at__isnull=True)
        .annotate(dummy=Value(1))
        .values("dummy")
        .annotate(c=Count("id"))
        .values("c")[:1],
        output_field=IntegerField(),
    )

    metrics = Employee.objects.filter(deleted_at__isnull=True).aggregate(
        total_employees=Count("id"),
        active_employees=Count("id", filter=Q(status="ACTIVE")),
        inactive_employees=Count("id", filter=Q(status="INACTIVE")),
        total_positions=Max(pos_sq),
    )

    total_positions = metrics["total_positions"]
    if total_positions is None:
        total_positions = Position.objects.filter(deleted_at__isnull=True).count()

    return {
        "total_employees": metrics["total_employees"] or 0,
        "active_employees": metrics["active_employees"] or 0,
        "inactive_employees": metrics["inactive_employees"] or 0,
        "total_positions": total_positions or 0,
    }


def list_employees(
    *,
    q: str | None = None,
    name: str | None = None,
    code: str | None = None,
    address: str | None = None,
    birth_from: datetime.date | str | None = None,
    birth_to: datetime.date | str | None = None,
    position: int | str | None = None,
    status: str | None = None,
    ordering: str | None = None,
    filters: dict[str, Any] | None = None,
) -> QuerySet[Employee]:
    """
    Build optimized QuerySet for employee list view.
    Enforces zero-N+1 query design using select_related across all foreign relationships.
    Provides substring search with DirectILike & escape_like, explicit field filters,
    and whitelisted deterministic ordering.
    """
    filters_dict = filters or {}

    q_val = q if q is not None else filters_dict.get("q")
    name_val = (
        name
        if name is not None
        else (filters_dict.get("name") or filters_dict.get("full_name"))
    )
    code_val = code if code is not None else filters_dict.get("code")
    address_val = address if address is not None else filters_dict.get("address")
    birth_from_val = (
        birth_from if birth_from is not None else filters_dict.get("birth_from")
    )
    birth_to_val = birth_to if birth_to is not None else filters_dict.get("birth_to")
    pos_val = position if position is not None else filters_dict.get("position")
    status_val = status if status is not None else filters_dict.get("status")
    ordering_val = ordering if ordering is not None else filters_dict.get("ordering")

    qs = Employee.objects.filter(deleted_at__isnull=True).select_related(
        "position",
        "province",
        "district",
        "ward",
        "account",
    )

    # 1. q substring search across full_name, code, email
    if q_val is not None and str(q_val).strip():
        clean_q = escape_like(str(q_val).strip())
        qs = qs.filter(
            Q(full_name__ilike=f"%{clean_q}%")
            | Q(code__ilike=f"%{clean_q}%")
            | Q(email__ilike=f"%{clean_q}%")
        )

    # 2. Case-insensitive substring for full_name
    if name_val is not None and str(name_val).strip():
        clean_name = escape_like(str(name_val).strip())
        qs = qs.filter(full_name__ilike=f"%{clean_name}%")

    # 3. Case-insensitive substring for code
    if code_val is not None and str(code_val).strip():
        clean_code = escape_like(str(code_val).strip())
        qs = qs.filter(code__ilike=f"%{clean_code}%")

    # 4. Case-insensitive substring for address and administrative area
    if address_val is not None and str(address_val).strip():
        clean_addr = escape_like(str(address_val).strip())
        qs = qs.filter(
            Q(address__ilike=f"%{clean_addr}%")
            | Q(province__name__ilike=f"%{clean_addr}%")
            | Q(district__name__ilike=f"%{clean_addr}%")
            | Q(ward__name__ilike=f"%{clean_addr}%")
        )

    # 5. Date of birth range validation & filtering
    birth_from_date: datetime.date | None = None
    if isinstance(birth_from_val, str) and birth_from_val.strip():
        try:
            birth_from_date = datetime.date.fromisoformat(birth_from_val.strip())
        except ValueError as exc:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Định dạng birth_from không hợp lệ (yêu cầu YYYY-MM-DD).",
                status_code=rest_status.HTTP_400_BAD_REQUEST,
            ) from exc
    elif isinstance(birth_from_val, datetime.date):
        birth_from_date = birth_from_val

    birth_to_date: datetime.date | None = None
    if isinstance(birth_to_val, str) and birth_to_val.strip():
        try:
            birth_to_date = datetime.date.fromisoformat(birth_to_val.strip())
        except ValueError as exc:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Định dạng birth_to không hợp lệ (yêu cầu YYYY-MM-DD).",
                status_code=rest_status.HTTP_400_BAD_REQUEST,
            ) from exc
    elif isinstance(birth_to_val, datetime.date):
        birth_to_date = birth_to_val

    if birth_from_date and birth_to_date and birth_from_date > birth_to_date:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Khoảng thời gian ngày sinh không hợp lệ: birth_from không được lớn hơn birth_to.",
            status_code=rest_status.HTTP_400_BAD_REQUEST,
        )

    if birth_from_date:
        qs = qs.filter(date_of_birth__gte=birth_from_date)
    if birth_to_date:
        qs = qs.filter(date_of_birth__lte=birth_to_date)

    # 6. Exact match for position (code or id)
    if pos_val is not None and str(pos_val).strip():
        clean_pos = str(pos_val).strip()
        if clean_pos.isdigit():
            qs = qs.filter(
                Q(position_id=int(clean_pos)) | Q(position__code__iexact=clean_pos)
            )
        else:
            qs = qs.filter(position__code__iexact=clean_pos)

    # 7. Exact match for status (ACTIVE / INACTIVE)
    if status_val is not None and str(status_val).strip():
        clean_status = str(status_val).strip().upper()
        if clean_status not in ("ACTIVE", "INACTIVE"):
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message=f"Trạng thái '{status_val}' không hợp lệ. Chỉ chấp nhận ACTIVE hoặc INACTIVE.",
                status_code=rest_status.HTTP_400_BAD_REQUEST,
            )
        qs = qs.filter(status=clean_status)

    # 8. Whitelisted deterministic ordering
    if ordering_val and str(ordering_val).strip():
        clean_ordering = str(ordering_val).strip()
        if clean_ordering not in ALLOWED_ORDERING_FIELDS:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message=f"Trường sắp xếp '{ordering_val}' không hợp lệ.",
                status_code=rest_status.HTTP_400_BAD_REQUEST,
            )
        if clean_ordering in ("id", "-id"):
            qs = qs.order_by(clean_ordering)
        else:
            qs = qs.order_by(clean_ordering, "id")
    else:
        qs = qs.order_by("-created_at", "id")

    return qs


def get_employee_by_id(
    employee_id: int | None = None, *, id: int | None = None
) -> Employee:
    """
    Retrieve single employee by primary key with all relations hydrated.
    Raises 404 BusinessAPIException if record is unknown or soft-deleted.
    """
    target_id = employee_id if employee_id is not None else id
    if target_id is None:
        raise BusinessAPIException(
            code="PROP-4.3.3-P02",
            message="Nhân viên không tồn tại hoặc đã bị xóa.",
            status_code=rest_status.HTTP_404_NOT_FOUND,
        )

    employee = (
        Employee.objects.filter(id=target_id, deleted_at__isnull=True)
        .select_related("position", "province", "district", "ward", "account")
        .first()
    )
    if not employee:
        raise BusinessAPIException(
            code="PROP-4.3.3-P02",
            message="Nhân viên không tồn tại hoặc đã bị xóa.",
            status_code=rest_status.HTTP_404_NOT_FOUND,
        )
    return employee
