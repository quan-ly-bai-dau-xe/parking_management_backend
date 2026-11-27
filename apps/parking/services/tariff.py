"""
Parking tariff calculation and fee preview service per OQ-85, TL-50, TL-57, and WP4 (D6, R3d).
Computes fee based on parking duration, interval-merged package ticket coverage,
1-hour rounded-up overage blocks, and hourly rate.
"""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import ALL_MESSAGES
from apps.parking.models import VehicleEntryExitLog
from apps.tickets.models import Ticket

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ONE_HOUR_US = 3_600 * 1_000_000


def _ensure_aware(dt: datetime) -> datetime:
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, VN_TZ)
    return dt


def _timedelta_to_us(td: timedelta) -> int:
    return (td.days * 86_400 + td.seconds) * 1_000_000 + td.microseconds


def _ceil_hours_from_seconds(seconds: int) -> int:
    if seconds <= 0:
        return 0
    return (seconds + 3599) // 3600


def _get_hourly_rate(session: VehicleEntryExitLog) -> Decimal:
    rate_map = getattr(settings, "PARKING_HOURLY_RATE_BY_VEHICLE_TYPE", None)
    if isinstance(rate_map, dict) and getattr(session, "vehicle_id", None):
        vtype = getattr(session.vehicle, "vehicle_type", None)
        vtype_code = getattr(vtype, "code", None)
        if vtype_code and vtype_code in rate_map:
            return Decimal(str(rate_map[vtype_code])).quantize(Decimal("0.01"))

    hourly_rate = getattr(settings, "PARKING_HOURLY_RATE_VND", Decimal("10000.00"))
    if not isinstance(hourly_rate, Decimal):
        hourly_rate = Decimal(str(hourly_rate))
    return hourly_rate.quantize(Decimal("0.01"))


def get_session_active_ticket(
    session: VehicleEntryExitLog, at_time: datetime | None = None
) -> Ticket | None:
    """
    Xác định và trả về vé (Ticket) ACTIVE có hiệu lực phủ phiên đỗ xe tại thời điểm at_time.
    Single Source of Truth cho ticket coverage logic (TL-50, TL-57).
    """
    if at_time is None:
        at_time = timezone.now()
    at_dt = _ensure_aware(at_time)

    # 1. Kiểm tra vé gắn trực tiếp trên phiên đỗ xe
    if session.ticket_id:
        fields_cache = getattr(getattr(session, "_state", None), "fields_cache", {})
        if "ticket" in fields_cache:
            t = session.ticket
            if (
                t
                and t.status == "ACTIVE"
                and t.deleted_at is None
                and _ensure_aware(t.effective_from)
                <= at_dt
                < _ensure_aware(t.effective_to)
            ):
                return t

        ticket = (
            Ticket.objects.filter(
                id=session.ticket_id,
                status="ACTIVE",
                deleted_at__isnull=True,
                effective_from__lte=at_dt,
                effective_to__gt=at_dt,
            )
            .select_related("ticket_type")
            .only("id", "code", "effective_from", "effective_to", "ticket_type_id")
            .first()
        )
        if ticket:
            return ticket

    # 2. Nếu chưa gắn vé trực tiếp nhưng xe là phương tiện đã đăng ký trong hệ thống
    if session.vehicle_id:
        ticket = (
            Ticket.objects.filter(
                vehicle_id=session.vehicle_id,
                status="ACTIVE",
                deleted_at__isnull=True,
                effective_from__lte=at_dt,
                effective_to__gt=at_dt,
            )
            .select_related("ticket_type")
            .only("id", "code", "effective_from", "effective_to", "ticket_type_id")
            .first()
        )
        if ticket:
            return ticket

    return None


def _get_candidate_tickets(
    session: VehicleEntryExitLog,
    entry_time: datetime,
    exit_time: datetime,
) -> list[Ticket]:
    """
    Retrieve all valid non-cancelled, non-deleted package tickets overlapping [entry_time, exit_time).
    Includes ACTIVE, EXPIRED, and RENEWING so coverage before effective_to is preserved
    even after DB triggers or auto-renewal mark a ticket EXPIRED.
    """
    filters = (
        Q(deleted_at__isnull=True)
        & Q(status__in=("ACTIVE", "EXPIRED", "RENEWING"))
        & Q(effective_from__lt=exit_time)
        & Q(effective_to__gt=entry_time)
    )

    owner_q = Q()
    if getattr(session, "ticket_id", None):
        owner_q |= Q(id=session.ticket_id)
    if getattr(session, "vehicle_id", None):
        owner_q |= Q(vehicle_id=session.vehicle_id)

    if not owner_q:
        t = getattr(session, "ticket", None)
        if (
            t is not None
            and t.deleted_at is None
            and t.status in ("ACTIVE", "EXPIRED", "RENEWING")
            and _ensure_aware(t.effective_from) < exit_time
            and _ensure_aware(t.effective_to) > entry_time
        ):
            return [t]
        return []

    tickets = list(
        Ticket.objects.filter(filters & owner_q)
        .select_related("ticket_type")
        .order_by("effective_from", "id")
    )
    t = session.ticket
    if (
        not tickets
        and t is not None
        and t.deleted_at is None
        and t.status in ("ACTIVE", "EXPIRED", "RENEWING")
        and _ensure_aware(t.effective_from) < exit_time
        and _ensure_aware(t.effective_to) > entry_time
    ):
        return [t]
    return tickets


def calculate_parking_fee_breakdown(
    session: VehicleEntryExitLog, exit_time: datetime | None = None
) -> dict[str, Any]:
    """
    Single Source of Truth for parking fee and package overage breakdown (WP4 D6 & R3d).
    Uses exact integer microsecond interval merging over [entry_time, exit_time).
    """
    exit_dt = _ensure_aware(exit_time or timezone.now())
    entry_dt = _ensure_aware(session.entry_time)
    hourly_rate = _get_hourly_rate(session)

    total_us = 0 if exit_dt <= entry_dt else _timedelta_to_us(exit_dt - entry_dt)
    if total_us > 0:
        tickets = _get_candidate_tickets(session, entry_dt, exit_dt)
        # Reuse the candidate ticket query instead of issuing a duplicate DB hit.
        active_at_exit = next(
            (
                t
                for t in tickets
                if t.status == "ACTIVE"
                and _ensure_aware(t.effective_from) <= exit_dt
                and _ensure_aware(t.effective_to) > exit_dt
            ),
            None,
        )
    else:
        tickets = []
        active_at_exit = get_session_active_ticket(session, exit_dt)

    intervals: list[tuple[datetime, datetime]] = []
    for t in tickets:
        t_from = _ensure_aware(t.effective_from)
        t_to = _ensure_aware(t.effective_to)
        start = max(entry_dt, t_from)
        end = min(exit_dt, t_to)
        if start < end:
            intervals.append((start, end))

    intervals.sort(key=lambda pair: pair[0])
    merged: list[tuple[datetime, datetime]] = []
    for start, end in intervals:
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        elif end > merged[-1][1]:
            merged[-1] = (merged[-1][0], end)

    covered_us = sum(_timedelta_to_us(end - start) for start, end in merged)
    overage_us = max(0, total_us - covered_us)

    # Truncate to integer seconds to stay consistent with int(total_seconds())
    # and absorb millisecond wall-clock drift between entry_time and fee-preview calls.
    total_seconds = total_us // 1_000_000
    covered_seconds = covered_us // 1_000_000
    overage_seconds = overage_us // 1_000_000

    grace_minutes = int(getattr(settings, "PARKING_GRACE_PERIOD_MINUTES", 0) or 0)
    grace_seconds = max(0, grace_minutes) * 60

    ref_ticket = active_at_exit or (tickets[-1] if tickets else None)
    ticket_code = ref_ticket.code if ref_ticket else None
    ticket_type_code = (
        ref_ticket.ticket_type.code
        if ref_ticket and getattr(ref_ticket, "ticket_type", None)
        else None
    )
    ticket_effective_to = ref_ticket.effective_to if ref_ticket else None

    if (
        active_at_exit is not None
        and overage_seconds == 0
        or covered_us > 0
        and overage_seconds == 0
    ):
        billed_hours = 0
        fee_amount = Decimal("0.00")
        mode = "TICKET_EXEMPT"
    elif covered_us > 0 and overage_seconds > 0:
        if grace_seconds > 0 and overage_seconds < grace_seconds:
            billed_hours = 0
        else:
            billed_hours = _ceil_hours_from_seconds(overage_seconds)
        fee_amount = (Decimal(billed_hours) * hourly_rate).quantize(Decimal("0.01"))
        mode = "PACKAGE_OVERAGE"
    else:
        if total_seconds == 0:
            billed_hours = 1
        elif grace_seconds > 0 and total_seconds < grace_seconds:
            billed_hours = 0
        else:
            billed_hours = max(1, _ceil_hours_from_seconds(total_seconds))
        fee_amount = (Decimal(billed_hours) * hourly_rate).quantize(Decimal("0.01"))
        mode = "HOURLY"

    return {
        "fee_amount": fee_amount,
        "hourly_rate": hourly_rate,
        "total_seconds": total_seconds,
        "covered_seconds": covered_seconds,
        "overage_seconds": overage_seconds,
        "covered_minutes": covered_seconds // 60,
        "overage_minutes": ((overage_seconds + 59) // 60 if overage_seconds > 0 else 0),
        "billed_hours": billed_hours,
        "overage_hours": billed_hours if mode == "PACKAGE_OVERAGE" else 0,
        "has_active_ticket": active_at_exit is not None and overage_seconds == 0,
        "has_package_coverage": covered_us > 0,
        "ticket_code": ticket_code,
        "ticket_type_code": ticket_type_code,
        "ticket_effective_to": ticket_effective_to,
        "is_exempt": bool(fee_amount == Decimal("0.00")),
        "fee_breakdown_mode": mode,
    }


def calculate_parking_fee(
    session: VehicleEntryExitLog, exit_time: datetime | None = None
) -> Decimal:
    """
    Tính cước phí đỗ xe tại thời điểm ra theo quy tắc OQ-85, TL-50, và WP4 (D6, R3d):
    - Khoảng thời gian nằm trong hiệu lực vé gói [effective_from, effective_to): 0.00 VND.
    - Khoảng thời gian vượt hạn sau effective_to (hoặc không có vé): ceil(giờ) * PARKING_HOURLY_RATE_VND.
    """
    return calculate_parking_fee_breakdown(session, exit_time)["fee_amount"]


def get_fee_preview(
    license_plate: str | None = None,
    session_code: str | None = None,
) -> dict[str, Any]:
    """
    Dịch vụ xem trước cước phí phiên đỗ xe đang mở (Fee Preview per TL-57).
    Đảm bảo tính nhất quán tuyệt đối giữa cước phí dự kiến và cước phí check-out.
    """
    from apps.parking.selectors.sessions import (
        calculate_session_duration,
        get_open_session_by_identifier,
    )

    has_plate = bool(license_plate and str(license_plate).strip())
    has_code = bool(session_code and str(session_code).strip())

    if not has_plate and not has_code:
        raise BusinessAPIException(
            code="PROP-4.5.1-P11",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P11",
                "Yêu cầu cung cấp ít nhất một tiêu chí: biển số xe hoặc mã phiên đỗ xe.",
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    clean_plate = str(license_plate).strip() if has_plate else None
    clean_code = str(session_code).strip() if has_code else None

    session = get_open_session_by_identifier(
        license_plate=clean_plate, session_code=clean_code
    )
    if not session:
        raise BusinessAPIException(
            code="PROP-4.5.1-P06",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P06",
                "Không tìm thấy phiên đỗ xe đang mở phù hợp.",
            ),
            status_code=status.HTTP_404_NOT_FOUND,
        )

    now = timezone.now()
    duration_seconds, duration_text = calculate_session_duration(session)
    duration_minutes = max(0, int(duration_seconds // 60))

    breakdown = calculate_parking_fee_breakdown(session, now)

    return {
        "session_id": session.id,
        "session_code": session.session_code,
        "license_plate": session.license_plate,
        "entry_time": session.entry_time,
        "duration_minutes": duration_minutes,
        "duration_text": duration_text,
        "fee_amount": breakdown["fee_amount"],
        "has_active_ticket": breakdown["has_active_ticket"],
        "ticket_code": breakdown["ticket_code"],
        "is_exempt": breakdown["is_exempt"],
        "hourly_rate": breakdown["hourly_rate"],
        "covered_minutes": breakdown["covered_minutes"],
        "overage_minutes": breakdown["overage_minutes"],
        "overage_hours": breakdown["overage_hours"],
        "billed_hours": breakdown["billed_hours"],
        "has_package_coverage": breakdown["has_package_coverage"],
        "ticket_type_code": breakdown["ticket_type_code"],
        "ticket_effective_to": breakdown["ticket_effective_to"],
        "fee_breakdown_mode": breakdown["fee_breakdown_mode"],
    }
