"""
Selectors for reports app - Dashboard & Analytics.
Encapsulates read queries for Trang chủ — Smart Mobility.png per TL-13, TL-14, and TL-28.6.
"""

from __future__ import annotations

import datetime
from typing import Any

from django.db.models import Sum
from django.utils import timezone

from apps.audit.models import SystemAlert
from apps.parking.models import VehicleEntryExitLog
from apps.reports.models import (
    VAiRecognitionStats,
    VRevenueTodayByMethod,
    VSlotOccupancyByFloor,
    VTrafficByHour,
)


def get_dashboard_summary_kpis(user: Any) -> dict[str, Any]:
    """
    Tính toán 4 nhóm chỉ số KPI tổng quan trên Trang chủ:
    1. Kho vị trí (Tổng chỗ đỗ, chỗ đang dùng, chỗ trống, tỷ lệ lấp đầy)
    2. Lưu lượng xe trong ngày (Lượt vào, lượt ra, số xe đang đỗ)
    3. Doanh thu hôm nay (Chỉ hiển thị đầy đủ cho MANAGER, nhân viên bị giới hạn)
    4. Tỷ lệ nhận diện AI tự động
    """
    # 1. KPI Kho vị trí
    slot_aggregates = VSlotOccupancyByFloor.objects.aggregate(
        total_slots=Sum("total_slots"),
        operational_slots=Sum("operational_slots"),
        available_slots=Sum("available_slots"),
        occupied_slots=Sum("occupied_slots"),
        reserved_slots=Sum("reserved_slots"),
        charging_slots=Sum("charging_slots"),
    )

    total_slots = int(slot_aggregates["total_slots"] or 0)
    operational_slots = int(slot_aggregates["operational_slots"] or 0)
    available_slots = int(slot_aggregates["available_slots"] or 0)
    occupied_slots = int(slot_aggregates["occupied_slots"] or 0)
    reserved_slots = int(slot_aggregates["reserved_slots"] or 0)
    charging_slots = int(slot_aggregates["charging_slots"] or 0)
    used_slots = occupied_slots + reserved_slots + charging_slots

    occupancy_rate = (
        round(100.0 * used_slots / operational_slots, 1)
        if operational_slots > 0
        else 0.0
    )

    if occupancy_rate >= 90.0:
        status_text = "Sắp đầy"
    elif occupancy_rate >= 75.0:
        status_text = "Gần đầy"
    else:
        status_text = "Còn chỗ"

    slots_kpi = {
        "total_slots": total_slots,
        "operational_slots": operational_slots,
        "available_slots": available_slots,
        "occupied_slots": occupied_slots,
        "used_slots": used_slots,
        "occupancy_rate_pct": occupancy_rate,
        "status_text": status_text,
    }

    # 2. KPI Lưu lượng xe trong ngày
    today = timezone.localdate()
    today_start = timezone.make_aware(
        datetime.datetime.combine(today, datetime.datetime.min.time())
    )
    today_end = timezone.make_aware(
        datetime.datetime.combine(today, datetime.datetime.max.time())
    )

    today_entries = VehicleEntryExitLog.objects.filter(
        entry_time__range=(today_start, today_end)
    ).count()
    today_exits = VehicleEntryExitLog.objects.filter(
        exit_time__range=(today_start, today_end)
    ).count()
    active_parking = VehicleEntryExitLog.objects.filter(exit_time__isnull=True).count()

    traffic_kpi = {
        "today_entries": today_entries,
        "today_exits": today_exits,
        "active_parking": active_parking,
    }

    # 3. KPI Doanh thu hôm nay (Chỉ cho MANAGER per Rule 01 Section 2)
    revenue_kpi: dict[str, Any] | None = None
    is_manager = bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "role", None) == "MANAGER"
    )

    if is_manager:
        rev_record = VRevenueTodayByMethod.objects.first()
        if rev_record:
            revenue_kpi = {
                "revenue_date": rev_record.revenue_date,
                "total_revenue": rev_record.total_revenue,
                "cash_revenue": rev_record.cash_revenue,
                "vietqr_revenue": rev_record.vietqr_revenue,
                "cash_pct": rev_record.cash_pct,
                "vietqr_pct": rev_record.vietqr_pct,
            }
        else:
            revenue_kpi = {
                "revenue_date": today,
                "total_revenue": 0.00,
                "cash_revenue": 0.00,
                "vietqr_revenue": 0.00,
                "cash_pct": 0.00,
                "vietqr_pct": 0.00,
            }

    # 4. KPI Tỷ lệ nhận diện AI
    ai_record = VAiRecognitionStats.objects.first()
    if ai_record:
        ai_kpi = {
            "total_sessions": ai_record.total_sessions,
            "ai_sessions": ai_record.ai_sessions,
            "manual_sessions": ai_record.manual_sessions,
            "ai_recognition_rate_pct": ai_record.ai_recognition_rate_pct,
            "manual_rate_pct": ai_record.manual_rate_pct,
            "avg_ai_confidence": ai_record.avg_ai_confidence,
            "active_auto_scan_gates": ai_record.active_auto_scan_gates,
        }
    else:
        ai_kpi = {
            "total_sessions": 0,
            "ai_sessions": 0,
            "manual_sessions": 0,
            "ai_recognition_rate_pct": 0.00,
            "manual_rate_pct": 0.00,
            "avg_ai_confidence": 0.00,
            "active_auto_scan_gates": 0,
        }

    return {
        "slots": slots_kpi,
        "traffic": traffic_kpi,
        "revenue": revenue_kpi,
        "ai_recognition": ai_kpi,
    }


def get_floor_occupancy_bars() -> list[dict[str, Any]]:
    """
    Truy vấn và tính toán tỷ lệ lấp đầy theo tầng (TL-28.6).
    Ánh xạ chính xác thanh phần trăm tầng B1, B2, B3 trên Trang chủ.
    """
    floors_data = (
        VSlotOccupancyByFloor.objects.values("floor_id", "floor_code", "floor_name")
        .annotate(
            total_slots=Sum("total_slots"),
            operational_slots=Sum("operational_slots"),
            available_slots=Sum("available_slots"),
            occupied_slots=Sum("occupied_slots"),
            reserved_slots=Sum("reserved_slots"),
            charging_slots=Sum("charging_slots"),
        )
        .order_by("floor_code")
    )

    results: list[dict[str, Any]] = []
    for item in floors_data:
        total = int(item["total_slots"] or 0)
        operational = int(item["operational_slots"] or 0)
        available = int(item["available_slots"] or 0)
        occupied = int(item["occupied_slots"] or 0)
        reserved = int(item["reserved_slots"] or 0)
        charging = int(item["charging_slots"] or 0)
        used = occupied + reserved + charging

        occ_pct = round(100.0 * used / operational, 1) if operational > 0 else 0.0
        status_badge = "Sắp đầy" if occ_pct >= 90.0 else "Còn chỗ"
        fe_display_label = (
            f"{item['floor_name']} · {round(occ_pct)}% ({used}/{operational} chỗ)"
        )

        results.append(
            {
                "floor_id": item["floor_id"],
                "floor_code": item["floor_code"],
                "floor_name": item["floor_name"],
                "total_slots": total,
                "operational_slots": operational,
                "used_slots": used,
                "available_slots": available,
                "occupancy_percentage": occ_pct,
                "status_badge": status_badge,
                "fe_display_label": fe_display_label,
            }
        )

    return results


def get_traffic_chart_24h() -> list[dict[str, Any]]:
    """
    Truy vấn số liệu lưu lượng xe theo khung giờ (tối đa 24 mốc giờ gần nhất).
    Phục vụ biểu đồ đường 'Lưu lượng xe vào / ra theo giờ' trên Trang chủ.
    """
    traffic_rows = list(VTrafficByHour.objects.order_by("-traffic_hour")[:24])
    traffic_rows.reverse()  # Sắp xếp theo chiều tăng dần thời gian cho đồ thị

    return [
        {
            "traffic_hour": row.traffic_hour,
            "entry_count": row.entry_count,
            "exit_count": row.exit_count,
            "total_movements": row.total_movements,
        }
        for row in traffic_rows
    ]


def get_emergency_alerts(limit: int = 10) -> list[dict[str, Any]]:
    """
    Truy vấn danh sách cảnh báo bất thường và khẩn cấp từ system_alert (TL-13).
    Ưu tiên cảnh báo chưa được xử lý (resolved_at IS NULL).
    """
    alerts = list(
        SystemAlert.objects.filter(resolved_at__isnull=True).order_by("-occurred_at")[
            :limit
        ]
    )

    if not alerts:
        alerts = list(SystemAlert.objects.order_by("-occurred_at")[:limit])

    return [
        {
            "id": alert.id,
            "alert_type": alert.alert_type,
            "severity": alert.severity,
            "message": alert.message,
            "entity_type": alert.entity_type,
            "entity_id": alert.entity_id,
            "occurred_at": alert.occurred_at,
            "resolved_at": alert.resolved_at,
        }
        for alert in alerts
    ]


def get_recent_activity_feed(limit: int = 10) -> list[dict[str, Any]]:
    """
    Truy vấn các lượt ra/vào bãi đỗ xe gần nhất phục vụ danh sách hoạt động trực tiếp.
    """
    logs = list(VehicleEntryExitLog.objects.order_by("-entry_time")[:limit])

    feed: list[dict[str, Any]] = []
    for log in logs:
        is_exit = log.exit_time is not None
        direction = "OUT" if is_exit else "IN"
        event_time = log.exit_time if is_exit else log.entry_time

        feed.append(
            {
                "id": log.id,
                "session_code": log.session_code,
                "license_plate": log.license_plate,
                "direction": direction,
                "timestamp": event_time,
                "fee_amount": log.fee_amount,
                "recognition_source": log.recognition_source,
            }
        )

    return feed
