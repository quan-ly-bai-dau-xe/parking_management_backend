"""
Parking tariff calculation service per OQ-85 and TL-50.
Computes fee based on parking duration, active ticket coverage, and hourly rate.
"""

import math
from datetime import datetime
from decimal import Decimal

from django.conf import settings
from django.utils import timezone

from apps.parking.models import VehicleEntryExitLog
from apps.tickets.models import Ticket


def calculate_parking_fee(
    session: VehicleEntryExitLog, exit_time: datetime | None = None
) -> Decimal:
    """
    Tính cước phí đỗ xe tại thời điểm ra theo quy tắc OQ-85 và TL-50:
    1. Nếu phiên đỗ xe được bảo đảm bởi một vé (Ticket) đang ở trạng thái ACTIVE,
       chưa bị xóa mềm, và có hiệu lực tại thời điểm ra (effective_from <= exit_time < effective_to),
       cước phí được miễn giảm hoàn toàn: fee_amount = Decimal("0.00").
    2. Trường hợp xe vãng lai hoặc không có vé hợp lệ:
       - Thời lượng đỗ xe (giây) = exit_time - entry_time.
       - Số giờ tính phí = ceil(duration_seconds / 3600), tối thiểu là 1 giờ.
       - Cước phí = số giờ tính phí * PARKING_HOURLY_RATE_VND (mặc định 10000.00 VND).
       - Làm tròn chuẩn Decimal("0.01"), kiểu dữ liệu Decimal.
    """
    if exit_time is None:
        exit_time = timezone.now()

    # 1. Kiểm tra vé đỗ xe có hiệu lực
    has_active_ticket = False

    # 1a. Kiểm tra vé gắn trực tiếp trên phiên đỗ xe
    if session.ticket_id:
        # Tối ưu hóa P4: kiểm tra ticket đã được nạp sẵn qua select_related
        fields_cache = getattr(getattr(session, "_state", None), "fields_cache", {})
        if "ticket" in fields_cache:
            t = session.ticket
            if (
                t
                and t.status == "ACTIVE"
                and t.deleted_at is None
                and t.effective_from <= exit_time < t.effective_to
            ):
                has_active_ticket = True

        if not has_active_ticket and "ticket" not in fields_cache:
            ticket = (
                Ticket.objects.filter(
                    id=session.ticket_id,
                    status="ACTIVE",
                    deleted_at__isnull=True,
                    effective_from__lte=exit_time,
                    effective_to__gt=exit_time,
                )
                .only("id")
                .first()
            )
            if ticket:
                has_active_ticket = True

    # 1b. Nếu chưa gắn vé nhưng xe là phương tiện đăng ký (vehicle_id hợp lệ)
    if not has_active_ticket and session.vehicle_id:
        ticket = (
            Ticket.objects.filter(
                vehicle_id=session.vehicle_id,
                status="ACTIVE",
                deleted_at__isnull=True,
                effective_from__lte=exit_time,
                effective_to__gt=exit_time,
            )
            .only("id")
            .first()
        )
        if ticket:
            has_active_ticket = True

    if has_active_ticket:
        return Decimal("0.00")

    # 2. Tính cước phí cho khách vãng lai hoặc không có vé
    duration_seconds = max(0, int((exit_time - session.entry_time).total_seconds()))
    parked_hours = max(1, math.ceil(duration_seconds / 3600))

    hourly_rate = settings.PARKING_HOURLY_RATE_VND
    if not isinstance(hourly_rate, Decimal):
        hourly_rate = Decimal(str(hourly_rate))

    fee_amount = (Decimal(parked_hours) * hourly_rate).quantize(Decimal("0.01"))
    return fee_amount
