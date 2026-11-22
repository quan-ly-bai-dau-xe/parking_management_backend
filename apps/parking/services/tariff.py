"""
Parking tariff calculation and fee preview service per OQ-85, TL-50, and TL-57.
Computes fee based on parking duration, active ticket coverage, and hourly rate.
"""

import math
from datetime import datetime
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.utils import timezone
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import ALL_MESSAGES
from apps.parking.models import VehicleEntryExitLog
from apps.tickets.models import Ticket


def get_session_active_ticket(
    session: VehicleEntryExitLog, at_time: datetime | None = None
) -> Ticket | None:
    """
    Xác định và trả về vé (Ticket) ACTIVE có hiệu lực phủ phiên đỗ xe tại thời điểm at_time.
    Single Source of Truth cho ticket coverage logic (TL-50, TL-57).
    """
    if at_time is None:
        at_time = timezone.now()

    # 1. Kiểm tra vé gắn trực tiếp trên phiên đỗ xe
    if session.ticket_id:
        fields_cache = getattr(getattr(session, "_state", None), "fields_cache", {})
        if "ticket" in fields_cache:
            t = session.ticket
            if (
                t
                and t.status == "ACTIVE"
                and t.deleted_at is None
                and t.effective_from <= at_time < t.effective_to
            ):
                return t

        ticket = (
            Ticket.objects.filter(
                id=session.ticket_id,
                status="ACTIVE",
                deleted_at__isnull=True,
                effective_from__lte=at_time,
                effective_to__gt=at_time,
            )
            .only("id", "code")
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
                effective_from__lte=at_time,
                effective_to__gt=at_time,
            )
            .only("id", "code")
            .first()
        )
        if ticket:
            return ticket

    return None


def calculate_parking_fee(
    session: VehicleEntryExitLog, exit_time: datetime | None = None
) -> Decimal:
    """
    Tính cước phí đỗ xe tại thời điểm ra theo quy tắc OQ-85 và TL-50:
    1. Nếu phiên đỗ xe được bảo đảm bởi một vé (Ticket) ACTIVE (effective_from <= exit_time < effective_to),
       cước phí được miễn giảm hoàn toàn: fee_amount = Decimal("0.00").
    2. Trường hợp xe vãng lai hoặc không có vé hợp lệ:
       - Thời lượng đỗ xe (giây) = exit_time - entry_time.
       - Số giờ tính phí = ceil(duration_seconds / 3600), tối thiểu là 1 giờ.
       - Cước phí = số giờ tính phí * PARKING_HOURLY_RATE_VND (mặc định 10000.00 VND).
       - Làm tròn chuẩn Decimal("0.01"), kiểu dữ liệu Decimal.
    """
    if exit_time is None:
        exit_time = timezone.now()

    # Tái sử dụng Single Source of Truth cho ticket coverage
    active_ticket = get_session_active_ticket(session, exit_time)
    if active_ticket is not None:
        return Decimal("0.00")

    # 2. Tính cước phí cho khách vãng lai hoặc không có vé
    duration_seconds = max(0, int((exit_time - session.entry_time).total_seconds()))
    parked_hours = max(1, math.ceil(duration_seconds / 3600))

    hourly_rate = settings.PARKING_HOURLY_RATE_VND
    if not isinstance(hourly_rate, Decimal):
        hourly_rate = Decimal(str(hourly_rate))

    fee_amount = (Decimal(parked_hours) * hourly_rate).quantize(Decimal("0.01"))
    return fee_amount


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

    covering_ticket = get_session_active_ticket(session, now)
    has_active_ticket = covering_ticket is not None
    ticket_code = covering_ticket.code if covering_ticket else None

    fee_amount = calculate_parking_fee(session, now)

    hourly_rate = getattr(settings, "PARKING_HOURLY_RATE_VND", Decimal("10000.00"))
    if not isinstance(hourly_rate, Decimal):
        hourly_rate = Decimal(str(hourly_rate))

    return {
        "session_id": session.id,
        "session_code": session.session_code,
        "license_plate": session.license_plate,
        "entry_time": session.entry_time,
        "duration_minutes": duration_minutes,
        "duration_text": duration_text,
        "fee_amount": fee_amount,
        "has_active_ticket": has_active_ticket,
        "ticket_code": ticket_code,
        "is_exempt": bool(fee_amount == Decimal("0.00")),
        "hourly_rate": hourly_rate,
    }
