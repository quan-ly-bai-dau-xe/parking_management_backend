"""
Selectors for reports app - Statistics Summary (SRS 4.7.1).
Provides O(1)-query aggregate calculations for revenue by ticket type & payment method,
non-revenue wallet top-ups, vehicle traffic, and live slot occupancy.
Enforces TL-27 soft-delete exclusions and Asia/Ho_Chi_Minh timezone boundaries.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.parking.models import VehicleEntryExitLog
from apps.reports.models import VSlotOccupancyByFloor
from apps.tickets.models import Payment
from apps.wallet.models import WalletTransaction

HCM_TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ZERO_DECIMAL = Decimal("0.00")
NON_REVENUE_TOPUP_DESCRIPTION = (
    "Tổng tiền nạp vào ví khách hàng (tiền trả trước, ghi nhận nợ phải trả, "
    "không tính vào doanh thu dịch vụ bãi xe)"
)


def get_default_statistics_dates() -> tuple[date, date]:
    """
    Trả về khoảng ngày mặc định (đầu tháng hiện tại đến hôm nay)
    theo múi giờ Việt Nam (Asia/Ho_Chi_Minh).
    """
    today_hcm = timezone.now().astimezone(HCM_TZ).date()
    return today_hcm.replace(day=1), today_hcm


def _to_money_decimal(value: Decimal | int | float | None) -> Decimal:
    if value is None:
        return ZERO_DECIMAL
    return Decimal(value).quantize(ZERO_DECIMAL)


def _ticket_type_q(code: str) -> Q:
    """
    Khớp chứng từ thanh toán mua vé hoặc gia hạn vé theo mã loại vé (DAILY/MONTHLY/QUARTERLY/YEARLY).
    Với bản ghi gia hạn, ưu tiên new_ticket_type nếu có, ngược lại dùng loại vé gốc.
    """
    return (
        Q(ticket_id__isnull=False, ticket__ticket_type__code=code)
        | Q(renewal_id__isnull=False, renewal__new_ticket_type__code=code)
        | Q(
            renewal_id__isnull=False,
            renewal__new_ticket_type_id__isnull=True,
            renewal__ticket__ticket_type__code=code,
        )
    )


def get_statistics_summary(start_date: date, end_date: date) -> dict[str, Any]:
    """
    Tổng hợp số liệu thống kê 4.7.1 trong khoảng [start_date, end_date]
    theo múi giờ Asia/Ho_Chi_Minh (nửa mở [range_start, range_end)).
    Thực hiện số lượng truy vấn O(1), không N+1.
    """
    range_start = datetime.combine(start_date, time.min, tzinfo=HCM_TZ)
    # Tránh OverflowError khi end_date == date.max (9999-12-31)
    if end_date >= date.max:
        range_end = datetime.max.replace(tzinfo=HCM_TZ)
    else:
        range_end = datetime.combine(
            end_date + timedelta(days=1), time.min, tzinfo=HCM_TZ
        )

    decimal_zero = Value(
        ZERO_DECIMAL,
        output_field=DecimalField(max_digits=20, decimal_places=2),
    )

    # 1. Doanh thu thực thu (Payment PAID, chưa xóa mềm, lọc TL-27 trên toàn bộ quan hệ)
    payment_tl27_filter = (
        (
            Q(
                session_id__isnull=False,
                session__isnull=False,
            )
            & (
                Q(session__slot_id__isnull=True)
                | Q(session__slot__deleted_at__isnull=True)
            )
            & (
                Q(session__vehicle_id__isnull=True)
                | Q(
                    session__vehicle__deleted_at__isnull=True,
                    session__vehicle__customer__deleted_at__isnull=True,
                )
            )
            & (
                Q(session__ticket_id__isnull=True)
                | Q(session__ticket__deleted_at__isnull=True)
            )
        )
        | Q(
            ticket_id__isnull=False,
            ticket__deleted_at__isnull=True,
            ticket__customer__deleted_at__isnull=True,
            ticket__vehicle__deleted_at__isnull=True,
            ticket__slot__deleted_at__isnull=True,
            ticket__ticket_type__deleted_at__isnull=True,
        )
        | (
            Q(
                renewal_id__isnull=False,
                renewal__ticket__deleted_at__isnull=True,
                renewal__ticket__customer__deleted_at__isnull=True,
                renewal__ticket__vehicle__deleted_at__isnull=True,
                renewal__ticket__slot__deleted_at__isnull=True,
                renewal__ticket__ticket_type__deleted_at__isnull=True,
            )
            & (
                Q(renewal__new_ticket_type_id__isnull=True)
                | Q(renewal__new_ticket_type__deleted_at__isnull=True)
            )
        )
    )

    paid_in_range_filter = Q(paid_at__gte=range_start, paid_at__lt=range_end) | Q(
        paid_at__isnull=True,
        created_at__gte=range_start,
        created_at__lt=range_end,
    )

    base_payments = Payment.objects.filter(
        deleted_at__isnull=True,
        status="PAID",
    ).filter(paid_in_range_filter & payment_tl27_filter)

    rev_agg = base_payments.aggregate(
        total_revenue=Coalesce(Sum("amount"), decimal_zero),
        hourly=Coalesce(
            Sum("amount", filter=Q(session_id__isnull=False)),
            decimal_zero,
        ),
        daily=Coalesce(Sum("amount", filter=_ticket_type_q("DAILY")), decimal_zero),
        monthly=Coalesce(Sum("amount", filter=_ticket_type_q("MONTHLY")), decimal_zero),
        quarterly=Coalesce(
            Sum("amount", filter=_ticket_type_q("QUARTERLY")), decimal_zero
        ),
        yearly=Coalesce(Sum("amount", filter=_ticket_type_q("YEARLY")), decimal_zero),
        cash=Coalesce(Sum("amount", filter=Q(method="CASH")), decimal_zero),
        vietqr=Coalesce(Sum("amount", filter=Q(method="VIETQR")), decimal_zero),
        wallet=Coalesce(Sum("amount", filter=Q(method="WALLET")), decimal_zero),
    )

    total_revenue = _to_money_decimal(rev_agg["total_revenue"])
    revenue_by_ticket_type = {
        "HOURLY": _to_money_decimal(rev_agg["hourly"]),
        "DAILY": _to_money_decimal(rev_agg["daily"]),
        "MONTHLY": _to_money_decimal(rev_agg["monthly"]),
        "QUARTERLY": _to_money_decimal(rev_agg["quarterly"]),
        "YEARLY": _to_money_decimal(rev_agg["yearly"]),
    }
    revenue_by_payment_method = {
        "CASH": _to_money_decimal(rev_agg["cash"]),
        "VIETQR": _to_money_decimal(rev_agg["vietqr"]),
        "WALLET": _to_money_decimal(rev_agg["wallet"]),
    }

    # 2. Non-Revenue: Tiền nạp ví (nợ phải trả / tiền trả trước, KHÔNG cộng vào total_revenue)
    topup_agg = WalletTransaction.objects.filter(
        kind__in=("TOPUP_CASH", "TOPUP_VIETQR", "TOPUP_VNPAY"),
        transaction_type="CREDIT",
        created_at__gte=range_start,
        created_at__lt=range_end,
        wallet__deleted_at__isnull=True,
        wallet__customer__deleted_at__isnull=True,
    ).aggregate(
        wallet_topup_total=Coalesce(Sum("amount"), decimal_zero),
        topup_cash_total=Coalesce(
            Sum("amount", filter=Q(kind="TOPUP_CASH")), decimal_zero
        ),
        topup_vietqr_total=Coalesce(
            Sum("amount", filter=Q(kind="TOPUP_VIETQR")), decimal_zero
        ),
        topup_vnpay_total=Coalesce(
            Sum("amount", filter=Q(kind="TOPUP_VNPAY")), decimal_zero
        ),
    )

    non_revenue = {
        "wallet_topup_total": _to_money_decimal(topup_agg["wallet_topup_total"]),
        "topup_cash_total": _to_money_decimal(topup_agg["topup_cash_total"]),
        "topup_vietqr_total": _to_money_decimal(topup_agg["topup_vietqr_total"]),
        "topup_vnpay_total": _to_money_decimal(topup_agg["topup_vnpay_total"]),
        "description": NON_REVENUE_TOPUP_DESCRIPTION,
    }

    # 3. Lưu lượng xe vào / ra trong kỳ & số xe đang đỗ hiện tại (lọc TL-27)
    log_tl27_qs = VehicleEntryExitLog.objects.filter(
        Q(slot_id__isnull=True) | Q(slot__deleted_at__isnull=True),
        Q(vehicle_id__isnull=True)
        | Q(
            vehicle__deleted_at__isnull=True,
            vehicle__customer__deleted_at__isnull=True,
        ),
        Q(ticket_id__isnull=True) | Q(ticket__deleted_at__isnull=True),
    )

    total_entries = log_tl27_qs.filter(
        entry_time__gte=range_start,
        entry_time__lt=range_end,
    ).count()
    total_exits = log_tl27_qs.filter(
        exit_time__gte=range_start,
        exit_time__lt=range_end,
    ).count()
    currently_parked = log_tl27_qs.filter(exit_time__isnull=True).count()

    traffic = {
        "total_entries": total_entries,
        "total_exits": total_exits,
        "currently_parked": currently_parked,
    }

    # 4. Tỷ lệ lấp đầy hiện tại từ view v_slot_occupancy_by_floor (đã lọc TL-27)
    slot_agg = VSlotOccupancyByFloor.objects.aggregate(
        total_slots=Sum("total_slots"),
        operational_slots=Sum("operational_slots"),
        available_slots=Sum("available_slots"),
        occupied_slots=Sum("occupied_slots"),
        reserved_slots=Sum("reserved_slots"),
        charging_slots=Sum("charging_slots"),
        maintenance_slots=Sum("maintenance_slots"),
    )

    total_slots = int(slot_agg["total_slots"] or 0)
    operational_slots = int(slot_agg["operational_slots"] or 0)
    available_slots = int(slot_agg["available_slots"] or 0)
    occupied_only = int(slot_agg["occupied_slots"] or 0)
    reserved_slots = int(slot_agg["reserved_slots"] or 0)
    charging_slots = int(slot_agg["charging_slots"] or 0)
    maintenance_slots = int(slot_agg["maintenance_slots"] or 0)

    occupied_slots = occupied_only + charging_slots
    occupancy_rate = (
        round(100.0 * occupied_slots / operational_slots, 2)
        if operational_slots > 0
        else 0.0
    )

    occupancy = {
        "total_slots": total_slots,
        "operational_slots": operational_slots,
        "occupied_slots": occupied_slots,
        "available_slots": available_slots,
        "reserved_slots": reserved_slots,
        "charging_slots": charging_slots,
        "maintenance_slots": maintenance_slots,
        "occupancy_rate": occupancy_rate,
    }

    return {
        "period": {
            "start_date": start_date,
            "end_date": end_date,
        },
        "total_revenue": total_revenue,
        "revenue_by_ticket_type": revenue_by_ticket_type,
        "revenue_by_payment_method": revenue_by_payment_method,
        "non_revenue": non_revenue,
        "traffic": traffic,
        "occupancy": occupancy,
    }
