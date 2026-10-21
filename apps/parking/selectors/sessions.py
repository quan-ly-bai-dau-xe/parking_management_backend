"""
Session selectors for parking app.
Provides filtering, details, duration calculation, and zero N+1 queries per TL-05, TL-50.
"""

import contextlib
from decimal import Decimal, InvalidOperation
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from apps.parking.models import VehicleEntryExitLog
from apps.parking.services.ocr import PlateRecognizer


def format_duration_text(duration_seconds: int) -> str:
    """
    Chuyển đổi thời lượng đỗ xe (giây) sang chuỗi văn bản tiếng Việt thân thiện:
    - Dưới 1 phút: "X giây"
    - Dưới 1 giờ: "X phút"
    - Dưới 1 ngày: "X giờ Y phút"
    - Trên 1 ngày: "X ngày Y giờ Z phút"
    """
    if duration_seconds < 0:
        duration_seconds = 0

    days = duration_seconds // 86400
    rem = duration_seconds % 86400
    hours = rem // 3600
    rem = rem % 3600
    minutes = rem // 60
    seconds = rem % 60

    if days > 0:
        if minutes > 0:
            return f"{days} ngày {hours} giờ {minutes} phút"
        return f"{days} ngày {hours} giờ"
    if hours > 0:
        if minutes > 0:
            return f"{hours} giờ {minutes} phút"
        return f"{hours} giờ"
    if minutes > 0:
        return f"{minutes} phút"
    return f"{seconds} giây"


def calculate_session_duration(session: VehicleEntryExitLog) -> tuple[int, str]:
    """
    Tính toán thời lượng đỗ xe:
    - Nếu đã check-out: duration = exit_time - entry_time
    - Nếu chưa check-out: duration = now - entry_time
    Trả về (duration_seconds, human_duration_text).
    """
    end_time = session.exit_time or timezone.now()
    duration_seconds = max(0, int((end_time - session.entry_time).total_seconds()))
    return duration_seconds, format_duration_text(duration_seconds)


def list_sessions(
    filters: dict[str, Any] | None = None,
) -> QuerySet[VehicleEntryExitLog]:
    """
    Truy vấn danh sách các lượt đỗ xe (VehicleEntryExitLog) với bộ lọc đa dạng,
    sắp xếp giảm dần theo entry_time, nạp trước quan hệ tránh N+1.
    """
    # Optimized for SessionListItemSerializer (H5): Only join relations actually consumed
    # by the list serializer, eliminating 7 heavy unused LEFT JOINs.
    qs = VehicleEntryExitLog.objects.select_related(
        "vehicle",
        "vehicle__customer",
        "slot",
        "entry_gate",
        "exit_gate",
    ).order_by("-entry_time")

    if not filters:
        return qs

    # 1. Lọc theo mã phiên đỗ xe
    session_code = filters.get("session_code")
    if session_code and str(session_code).strip():
        qs = qs.filter(session_code__icontains=str(session_code).strip())

    # 2. Lọc theo biển số xe (chuẩn hóa hoặc chuỗi gốc)
    plate = filters.get("license_plate")
    if plate and str(plate).strip():
        clean_plate = str(plate).strip()
        norm_filter = PlateRecognizer.normalize_plate(clean_plate)
        if norm_filter:
            qs = qs.filter(license_plate_norm__icontains=norm_filter)
        else:
            qs = qs.filter(license_plate__icontains=clean_plate)

    # 3. Lọc theo khoảng thời gian vào (entry_time)
    entry_from = filters.get("entry_time_from")
    if entry_from:
        qs = qs.filter(entry_time__gte=entry_from)
    entry_to = filters.get("entry_time_to")
    if entry_to:
        qs = qs.filter(entry_time__lte=entry_to)

    # 4. Lọc theo khoảng thời gian ra (exit_time)
    exit_from = filters.get("exit_time_from")
    if exit_from:
        qs = qs.filter(exit_time__gte=exit_from)
    exit_to = filters.get("exit_time_to")
    if exit_to:
        qs = qs.filter(exit_time__lte=exit_to)

    # 5. Lọc theo trạng thái phiên đỗ (status: open | closed)
    status_filter = filters.get("status")
    if status_filter:
        status_val = str(status_filter).strip().lower()
        if status_val == "open":
            qs = qs.filter(exit_time__isnull=True)
        elif status_val == "closed":
            qs = qs.filter(exit_time__isnull=False)

    # 6. Lọc theo trạng thái kiểm duyệt (review_status)
    review_status = filters.get("review_status")
    if review_status and str(review_status).strip():
        qs = qs.filter(review_status=str(review_status).strip())

    # 7. Lọc theo khoảng cước phí (min_fee / max_fee)
    min_fee = filters.get("min_fee")
    if min_fee is not None:
        with contextlib.suppress(InvalidOperation, ValueError):
            qs = qs.filter(fee_amount__gte=Decimal(str(min_fee)))

    max_fee = filters.get("max_fee")
    if max_fee is not None:
        with contextlib.suppress(InvalidOperation, ValueError):
            qs = qs.filter(fee_amount__lte=Decimal(str(max_fee)))

    return qs


def get_session_by_id(session_id: int) -> VehicleEntryExitLog | None:
    """Truy vấn thông tin chi tiết một phiên đỗ xe theo id."""
    return (
        VehicleEntryExitLog.objects.select_related(
            "vehicle",
            "vehicle__vehicle_type",
            "vehicle__customer",
            "slot",
            "slot__zone",
            "slot__zone__floor",
            "ticket",
            "ticket__ticket_type",
            "entry_gate",
            "exit_gate",
            "entry_handled_by",
            "exit_handled_by",
        )
        .filter(id=session_id)
        .first()
    )


def get_open_session_by_identifier(
    license_plate: str | None = None, session_code: str | None = None
) -> VehicleEntryExitLog | None:
    """
    Truy vấn phiên đỗ đang mở (exit_time IS NULL) theo biển số HOẶC mã phiên.
    """
    qs = VehicleEntryExitLog.objects.select_related(
        "vehicle",
        "vehicle__vehicle_type",
        "vehicle__customer",
        "slot",
        "slot__zone",
        "slot__zone__floor",
        "ticket",
        "entry_gate",
    ).filter(exit_time__isnull=True)

    if session_code and session_code.strip():
        return qs.filter(session_code=session_code.strip()).first()

    if license_plate and license_plate.strip():
        norm_plate = PlateRecognizer.normalize_plate(license_plate)
        return qs.filter(license_plate_norm=norm_plate).first()

    return None
