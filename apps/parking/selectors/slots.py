"""
Selectors for ParkingSlot domain per TL-27, TL-50, and SRS 4.8.1 - 4.8.5.
Guarantees O(1) query scaling (zero N+1) via select_related and Prefetch.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q, QuerySet
from django.db.models.query import Prefetch
from django.utils import timezone

from apps.parking.models import (
    ParkingSlot,
    SlotReservation,
    VehicleEntryExitLog,
)
from apps.tickets.models import Ticket


def get_slots_base_queryset() -> QuerySet[ParkingSlot]:
    """
    Tập truy vấn cơ sở cho ParkingSlot:
    - Chỉ lấy các ô đỗ chưa bị xóa mềm (deleted_at IS NULL per TL-27).
    - select_related phân cấp bãi đỗ: zone -> floor -> lot.
    - prefetch_related các quan hệ cần thiết để phục vụ danh sách & chi tiết với O(1) queries.
    """
    now = timezone.now()

    return (
        ParkingSlot.objects.filter(deleted_at__isnull=True)
        .select_related("zone", "zone__floor", "zone__floor__lot")
        .prefetch_related(
            "allowed_vehicle_types__vehicle_type",
            Prefetch(
                "entry_exit_logs",
                queryset=VehicleEntryExitLog.objects.filter(
                    exit_time__isnull=True
                ).select_related(
                    "vehicle",
                    "vehicle__vehicle_type",
                    "vehicle__customer",
                    "entry_gate",
                ),
                to_attr="prefetched_open_sessions",
            ),
            Prefetch(
                "reservations",
                queryset=SlotReservation.objects.filter(
                    deleted_at__isnull=True,
                    status="ACTIVE",
                    reserved_until__gt=now,
                ).select_related("customer", "vehicle"),
                to_attr="prefetched_active_reservations",
            ),
            Prefetch(
                "tickets",
                queryset=Ticket.objects.filter(
                    deleted_at__isnull=True,
                    status__in=["ACTIVE", "RENEWING"],
                    effective_to__gt=now,
                ).select_related("customer", "vehicle", "ticket_type"),
                to_attr="prefetched_active_tickets",
            ),
        )
    )


def get_slots_queryset(
    floor: str | None = None,
    zone: str | None = None,
    status_filter: str | None = None,
    vehicle_type: str | None = None,
    slot_kind: str | None = None,
    search: str | None = None,
    ordering: str | None = None,
) -> QuerySet[ParkingSlot]:
    """
    Truy vấn danh sách ô đỗ xe hỗ trợ lọc đa tiêu chí (SRS 4.8.1).
    """
    qs = get_slots_base_queryset()
    requires_distinct = False

    # 1. Lọc theo Tầng (floor code hoặc floor ID)
    if floor:
        floor_clean = str(floor).strip()
        if floor_clean:
            if floor_clean.isdigit():
                qs = qs.filter(
                    Q(zone__floor__code__iexact=floor_clean)
                    | Q(zone__floor_id=int(floor_clean))
                )
            else:
                qs = qs.filter(zone__floor__code__iexact=floor_clean)

    # 2. Lọc theo Khu vực (zone code hoặc zone ID)
    if zone:
        zone_clean = str(zone).strip()
        if zone_clean:
            if zone_clean.isdigit():
                qs = qs.filter(
                    Q(zone__code__iexact=zone_clean) | Q(zone_id=int(zone_clean))
                )
            else:
                qs = qs.filter(zone__code__iexact=zone_clean)

    # 3. Lọc theo Trạng thái (hỗ trợ đơn, danh sách phân cách dấu phẩy, hoặc 'OVERSTAY')
    if status_filter:
        raw_statuses = [
            s.strip().upper() for s in str(status_filter).split(",") if s.strip()
        ]
        if raw_statuses:
            has_overstay = "OVERSTAY" in raw_statuses
            valid_statuses = [s for s in raw_statuses if s != "OVERSTAY"]

            if has_overstay and valid_statuses:
                cutoff = timezone.now() - timedelta(hours=24)
                qs = qs.filter(
                    Q(status__in=valid_statuses)
                    | (
                        Q(status="OCCUPIED")
                        & Q(entry_exit_logs__exit_time__isnull=True)
                        & Q(entry_exit_logs__entry_time__lte=cutoff)
                    )
                )
                requires_distinct = True
            elif has_overstay:
                cutoff = timezone.now() - timedelta(hours=24)
                qs = qs.filter(
                    status="OCCUPIED",
                    entry_exit_logs__exit_time__isnull=True,
                    entry_exit_logs__entry_time__lte=cutoff,
                )
                requires_distinct = True
            else:
                qs = qs.filter(status__in=valid_statuses)

    # 4. Lọc theo loại xe cho phép
    if vehicle_type:
        vt_clean = str(vehicle_type).strip()
        if vt_clean:
            if vt_clean.isdigit():
                qs = qs.filter(
                    Q(allowed_vehicle_types__vehicle_type__code__iexact=vt_clean)
                    | Q(allowed_vehicle_types__vehicle_type_id=int(vt_clean))
                )
            else:
                qs = qs.filter(
                    allowed_vehicle_types__vehicle_type__code__iexact=vt_clean
                )
            requires_distinct = True

    # 5. Lọc theo loại ô đỗ (slot_kind: STANDARD, PRIORITY, EV_CHARGING)
    if slot_kind:
        sk_clean = str(slot_kind).strip().upper()
        if sk_clean:
            qs = qs.filter(slot_kind=sk_clean)

    # 6. Tìm kiếm văn bản trên code hoặc notes
    if search:
        search_clean = str(search).strip()
        if search_clean:
            qs = qs.filter(
                Q(code__icontains=search_clean) | Q(notes__icontains=search_clean)
            )

    if requires_distinct:
        qs = qs.distinct()

    # 7. Sắp xếp kết quả
    default_ordering = (
        "zone__floor__sort_order",
        "zone__floor__id",
        "zone__code",
        "code",
        "id",
    )
    if ordering:
        ordering_clean = str(ordering).strip()
        allowed_sort_fields = {
            "code",
            "-code",
            "status",
            "-status",
            "slot_kind",
            "-slot_kind",
            "created_at",
            "-created_at",
            "updated_at",
            "-updated_at",
            "map_row",
            "-map_row",
            "map_col",
            "-map_col",
        }
        if ordering_clean in allowed_sort_fields:
            return qs.order_by(ordering_clean, "id")

    return qs.order_by(*default_ordering)


def get_slot_by_id(slot_id: int) -> ParkingSlot | None:
    """
    Truy vấn thông tin chi tiết một ô đỗ xe theo ID với đầy đủ thông tin lồng nhau.
    """
    return get_slots_base_queryset().filter(id=slot_id).first()


def get_available_slots(
    lot_id: int | None = None,
    vehicle_type: str | None = None,
    slot_kind: str | None = None,
) -> QuerySet[ParkingSlot]:
    """
    Truy vấn các ô đỗ còn trống (AVAILABLE) phù hợp với loại phương tiện và loại ô.
    Hỗ trợ GateWorkerCoordinator và điều phối cổng.
    """
    qs = get_slots_base_queryset().filter(status="AVAILABLE")

    if lot_id:
        qs = qs.filter(zone__floor__lot_id=lot_id)

    if vehicle_type:
        vt_clean = str(vehicle_type).strip()
        if vt_clean.isdigit():
            qs = qs.filter(
                Q(allowed_vehicle_types__vehicle_type__code__iexact=vt_clean)
                | Q(allowed_vehicle_types__vehicle_type_id=int(vt_clean))
            )
        else:
            qs = qs.filter(allowed_vehicle_types__vehicle_type__code__iexact=vt_clean)
        qs = qs.distinct()

    if slot_kind:
        qs = qs.filter(slot_kind=str(slot_kind).strip().upper())

    return qs.order_by(
        "zone__floor__sort_order", "zone__floor__id", "zone__code", "code", "id"
    )
