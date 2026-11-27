"""
Unit tests for parking tariff calculation service per OQ-85, TL-50.
Verifies:
- Active ticket produces 0 VND fee.
- Expired/soft-deleted ticket does not waive fee.
- Hourly calculation ceil(duration_seconds / 3600) with minimum 1 hour.
- Decimal precision 10000.00 VND.
- Duration formatting in Vietnamese.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.customers.models import Customer
from apps.parking.models import (
    ParkingSlot,
    ParkingZone,
    SlotAllowedVehicleType,
    VehicleEntryExitLog,
)
from apps.parking.selectors.sessions import (
    calculate_session_duration,
    format_duration_text,
)
from apps.parking.services.tariff import (
    calculate_parking_fee,
    calculate_parking_fee_breakdown,
)
from apps.tickets.models import Ticket, TicketType
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


def test_tariff_visitor_vehicle_minimum_one_hour():
    """Xe vãng lai vào và ra ngay (0s) tính phí tối thiểu 1 giờ = 10,000 VND."""
    now = timezone.now()
    session = VehicleEntryExitLog(
        session_code="#PK-20261018-001",
        license_plate="43A-999.99",
        license_plate_norm="43A99999",
        entry_time=now,
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("10000.00")


def test_tariff_visitor_vehicle_partial_hour():
    """Xe vãng lai đỗ 45 phút (< 1 giờ) tính 1 giờ = 10,000 VND."""
    now = timezone.now()
    session = VehicleEntryExitLog(
        session_code="#PK-20261018-002",
        license_plate="43A-999.99",
        license_plate_norm="43A99999",
        entry_time=now - timedelta(minutes=45),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("10000.00")


def test_tariff_visitor_vehicle_exact_one_hour():
    """Xe vãng lai đỗ đúng 3600 giây tính 1 giờ = 10,000 VND."""
    now = timezone.now()
    session = VehicleEntryExitLog(
        session_code="#PK-20261018-003",
        license_plate="43A-999.99",
        license_plate_norm="43A99999",
        entry_time=now - timedelta(seconds=3600),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("10000.00")


def test_tariff_visitor_vehicle_boundary_one_second_over():
    """Xe vãng lai đỗ 3601 giây (1 giờ 1 giây) làm tròn lên 2 giờ = 20,000 VND."""
    now = timezone.now()
    session = VehicleEntryExitLog(
        session_code="#PK-20261018-004",
        license_plate="43A-999.99",
        license_plate_norm="43A99999",
        entry_time=now - timedelta(seconds=3601),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("20000.00")


def test_tariff_visitor_vehicle_multiple_hours():
    """Xe vãng lai đỗ 5 giờ 10 phút tính 6 giờ = 60,000 VND."""
    now = timezone.now()
    session = VehicleEntryExitLog(
        session_code="#PK-20261018-005",
        license_plate="43A-999.99",
        license_plate_norm="43A99999",
        entry_time=now - timedelta(hours=5, minutes=10),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("60000.00")


def test_tariff_active_ticket_attached_to_session_zero_fee():
    """Xe có vé ACTIVE gắn trực tiếp trên phiên đỗ xe được miễn phí hoàn toàn = 0 VND."""
    now = timezone.now()
    ticket_type = TicketType.objects.first()
    ticket = Ticket.objects.filter(status="ACTIVE").first()
    if not ticket:
        v = Vehicle.objects.first()
        slot = ParkingSlot.objects.first()
        ticket = Ticket.objects.create(
            code="TCK-TST-01",
            vehicle=v,
            customer=v.customer,
            slot=slot,
            ticket_type=ticket_type,
            status="ACTIVE",
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=29),
            price=Decimal("500000.00"),
        )

    session = VehicleEntryExitLog(
        session_code="#PK-20261018-006",
        license_plate="43A-888.88",
        license_plate_norm="43A88888",
        ticket=ticket,
        entry_time=now - timedelta(hours=8),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("0.00")


def test_tariff_expired_ticket_charges_hourly_fee():
    """Vé hết hạn giữa phiên đỗ: phần trước effective_to = 0đ, phần vượt hạn tính block 1h (1h = 10,000 VND)."""
    now = timezone.now()
    ticket_type = TicketType.objects.first()
    v = Vehicle.objects.first()
    slot = ParkingSlot.objects.first()
    ticket = Ticket.objects.create(
        code="TCK-TST-02",
        vehicle=v,
        customer=v.customer,
        slot=slot,
        ticket_type=ticket_type,
        status="ACTIVE",
        effective_from=now - timedelta(days=30),
        effective_to=now
        - timedelta(hours=1),  # Hết hạn giữa phiên (đỗ 3h, 2h trong hạn, 1h vượt hạn)
        price=Decimal("500000.00"),
    )

    session = VehicleEntryExitLog(
        session_code="#PK-20261018-007",
        license_plate="43A-888.88",
        license_plate_norm="43A88888",
        ticket=ticket,
        entry_time=now - timedelta(hours=3),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("10000.00")


def test_tariff_ticket_expired_before_entry_charges_full_hourly_fee():
    """Vé đã hết hạn hoàn toàn TRƯỚC lúc xe vào bãi -> tính đủ 3h = 30,000 VND."""
    now = timezone.now()
    ticket_type = TicketType.objects.first()
    v = Vehicle.objects.first()
    slot = ParkingSlot.objects.first()
    ticket = Ticket.objects.create(
        code="TCK-PRE-01",
        vehicle=v,
        customer=v.customer,
        slot=slot,
        ticket_type=ticket_type,
        status="EXPIRED",
        effective_from=now - timedelta(days=31),
        effective_to=now - timedelta(days=1),
        price=Decimal("500000.00"),
    )

    session = VehicleEntryExitLog(
        session_code="#PK-20261018-007B",
        license_plate="43A-888.88",
        license_plate_norm="43A88888",
        ticket=ticket,
        entry_time=now - timedelta(hours=3),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("30000.00")


def test_tariff_soft_deleted_ticket_charges_hourly_fee():
    """Vé bị soft-deleted không được áp dụng miễn phí."""
    now = timezone.now()
    ticket_type = TicketType.objects.first()
    v = Vehicle.objects.first()
    slot = ParkingSlot.objects.first()
    ticket = Ticket.objects.create(
        code="TCK-TST-03",
        vehicle=v,
        customer=v.customer,
        slot=slot,
        ticket_type=ticket_type,
        status="EXPIRED",
        effective_from=now - timedelta(days=30),
        effective_to=now - timedelta(days=1),
        price=Decimal("500000.00"),
        deleted_at=now,
    )

    session = VehicleEntryExitLog(
        session_code="#PK-20261018-008",
        license_plate="43A-888.88",
        license_plate_norm="43A88888",
        ticket=ticket,
        entry_time=now - timedelta(hours=2),
    )
    fee = calculate_parking_fee(session, exit_time=now)
    assert fee == Decimal("20000.00")


def test_format_duration_text_variations():
    """Kiểm tra hiển thị thời lượng bằng tiếng Việt các trường hợp biên."""
    assert format_duration_text(0) == "0 giây"
    assert format_duration_text(45) == "45 giây"
    assert format_duration_text(60) == "1 phút"
    assert format_duration_text(150) == "2 phút"
    assert format_duration_text(3600) == "1 giờ"
    assert format_duration_text(3720) == "1 giờ 2 phút"
    assert format_duration_text(86400) == "1 ngày 0 giờ"
    assert format_duration_text(90060) == "1 ngày 1 giờ 1 phút"
    assert format_duration_text(-10) == "0 giây"


def test_calculate_session_duration_helper():
    """Kiểm tra helper calculate_session_duration cho cả session đang mở và đã đóng."""
    now = timezone.now()
    entry = now - timedelta(hours=2, minutes=15)
    exit_t = now - timedelta(minutes=15)

    closed_session = VehicleEntryExitLog(
        session_code="#PK-20261018-009",
        license_plate="43A-777.77",
        license_plate_norm="43A77777",
        entry_time=entry,
        exit_time=exit_t,
    )
    duration_sec, text = calculate_session_duration(closed_session)
    assert duration_sec == 7200  # 2 hours
    assert text == "2 giờ"


def _make_isolated_vehicle_and_slot(suffix: str):
    vtype = VehicleType.objects.first()
    assert vtype is not None
    cust = Customer.objects.create(
        code=f"KHOV{suffix}",
        full_name=f"Khach Overage {suffix}",
        phone=f"0988{suffix[-6:].zfill(6)}",
        identity_card_number=f"079090{suffix[-6:].zfill(6)}",
    )
    v = Vehicle.objects.create(
        code=f"XEOV{suffix}",
        license_plate=f"51F-{suffix[-5:].zfill(5)}",
        license_plate_norm=f"51F{suffix[-5:].zfill(5)}",
        vehicle_type=vtype,
        customer=cust,
        model_name="Civic",
    )
    zone = ParkingZone.objects.first()
    assert zone is not None
    slot = ParkingSlot.objects.create(
        zone=zone,
        code=f"OV{suffix}",
        slot_kind="STANDARD",
        status="AVAILABLE",
    )
    SlotAllowedVehicleType.objects.get_or_create(slot=slot, vehicle_type=vtype)
    return v, slot


def test_tariff_package_overage_exact_boundary_and_microseconds():
    """
    Kiểm tra ranh giới overage vé gói (OVG-03, OVG-04, OVG-06, OVG-08, OVG-09):
    - Exit == effective_to -> 0đ.
    - Quá 1s / 14m -> 1 block (10,000 VND), không grace period.
    - Quá 1h 10m -> 2 blocks (20,000 VND).
    - Quá 1h 1s -> 2 blocks (20,000 VND).
    """
    ict = ZoneInfo("Asia/Ho_Chi_Minh")
    v, slot = _make_isolated_vehicle_and_slot("001")
    ttype = (
        TicketType.objects.filter(code="MONTHLY").first() or TicketType.objects.first()
    )

    eff_from = datetime(2026, 10, 12, 0, 0, 0, tzinfo=ict)
    eff_to = datetime(2026, 11, 11, 0, 0, 0, tzinfo=ict)
    ticket = Ticket.objects.create(
        code="OVG-001",
        vehicle=v,
        customer=v.customer,
        slot=slot,
        ticket_type=ttype,
        status="EXPIRED",
        effective_from=eff_from,
        effective_to=eff_to,
        price=Decimal("500000.00"),
    )

    entry = datetime(2026, 11, 10, 20, 0, 0, tzinfo=ict)
    session = VehicleEntryExitLog(
        session_code="#PK-OVG-001",
        vehicle=v,
        ticket=ticket,
        license_plate=v.license_plate,
        license_plate_norm=v.license_plate_norm,
        entry_time=entry,
    )

    # Exact boundary -> 0.00
    assert calculate_parking_fee(session, eff_to) == Decimal("0.00")
    # 1 second over -> 1h = 10,000.00
    assert calculate_parking_fee(session, eff_to + timedelta(seconds=1)) == Decimal(
        "10000.00"
    )
    # 14 minutes over -> 1h = 10,000.00 (no grace period)
    assert calculate_parking_fee(session, eff_to + timedelta(minutes=14)) == Decimal(
        "10000.00"
    )
    # Exact 60 minutes over -> 1h = 10,000.00
    assert calculate_parking_fee(session, eff_to + timedelta(minutes=60)) == Decimal(
        "10000.00"
    )
    # 1h 1s over -> 2h = 20,000.00
    assert calculate_parking_fee(
        session, eff_to + timedelta(hours=1, seconds=1)
    ) == Decimal("20000.00")
    # 1h 10m over -> 2h = 20,000.00
    breakdown = calculate_parking_fee_breakdown(
        session, eff_to + timedelta(hours=1, minutes=10)
    )
    assert breakdown["fee_amount"] == Decimal("20000.00")
    assert breakdown["fee_breakdown_mode"] == "PACKAGE_OVERAGE"
    assert breakdown["overage_hours"] == 2
    assert breakdown["has_package_coverage"] is True
    assert breakdown["has_active_ticket"] is False


def test_tariff_package_overage_multiday_no_daily_cap():
    """Đỗ lố 25 giờ sau effective_to -> tính đủ 25h = 250,000.00 VND (không áp trần 100k/ngày)."""
    ict = ZoneInfo("Asia/Ho_Chi_Minh")
    v, slot = _make_isolated_vehicle_and_slot("002")
    ttype = (
        TicketType.objects.filter(code="DAILY").first() or TicketType.objects.first()
    )

    eff_from = datetime(2026, 11, 10, 8, 0, 0, tzinfo=ict)
    eff_to = datetime(2026, 11, 11, 8, 0, 0, tzinfo=ict)
    ticket = Ticket.objects.create(
        code="OVG-002",
        vehicle=v,
        customer=v.customer,
        slot=slot,
        ticket_type=ttype,
        status="EXPIRED",
        effective_from=eff_from,
        effective_to=eff_to,
        price=Decimal("50000.00"),
    )
    session = VehicleEntryExitLog(
        session_code="#PK-OVG-002",
        vehicle=v,
        ticket=ticket,
        license_plate=v.license_plate,
        license_plate_norm=v.license_plate_norm,
        entry_time=datetime(2026, 11, 10, 10, 0, 0, tzinfo=ict),
    )
    fee = calculate_parking_fee(session, datetime(2026, 11, 12, 9, 0, 0, tzinfo=ict))
    assert fee == Decimal("250000.00")


def test_tariff_package_interval_merging_two_tickets_and_cancelled():
    """
    Kiểm tra hợp khoảng (Interval Merging) với 2 vé và vé CANCELLED:
    - Hai vé nối tiếp sát nhau -> 0đ.
    - Hai vé có khoảng hở 1h30m -> tính ceil(1.5h) = 2h = 20,000.00 VND.
    - Vé TERMINATED/CANCELLED không được miễn.
    """
    ict = ZoneInfo("Asia/Ho_Chi_Minh")
    v, slot = _make_isolated_vehicle_and_slot("003")
    _, slot2 = _make_isolated_vehicle_and_slot("004")
    ttype = (
        TicketType.objects.filter(code="MONTHLY").first() or TicketType.objects.first()
    )

    t1 = Ticket.objects.create(
        code="OVG-003A",
        vehicle=v,
        customer=v.customer,
        slot=slot,
        ticket_type=ttype,
        status="EXPIRED",
        effective_from=datetime(2026, 10, 12, 0, 0, 0, tzinfo=ict),
        effective_to=datetime(2026, 11, 11, 0, 0, 0, tzinfo=ict),
        price=Decimal("500000.00"),
    )
    t2 = Ticket.objects.create(
        code="OVG-003B",
        vehicle=v,
        customer=v.customer,
        slot=slot2,
        ticket_type=ttype,
        status="ACTIVE",
        effective_from=datetime(2026, 11, 11, 1, 30, 0, tzinfo=ict),
        effective_to=datetime(2026, 12, 11, 1, 30, 0, tzinfo=ict),
        price=Decimal("500000.00"),
    )

    session = VehicleEntryExitLog(
        session_code="#PK-OVG-003",
        vehicle=v,
        ticket=t1,
        license_plate=v.license_plate,
        license_plate_norm=v.license_plate_norm,
        entry_time=datetime(2026, 11, 10, 22, 0, 0, tzinfo=ict),
    )
    # Gap between 00:00 and 01:30 = 1h30m -> ceil(1.5h) = 2h = 20,000.00
    assert calculate_parking_fee(
        session, datetime(2026, 11, 11, 5, 0, 0, tzinfo=ict)
    ) == Decimal("20000.00")

    # If t2 starts right when t1 ends -> contiguous 0.00
    t2.effective_from = datetime(2026, 11, 11, 0, 0, 0, tzinfo=ict)
    t2.save(update_fields=["effective_from"])
    assert calculate_parking_fee(
        session, datetime(2026, 11, 11, 5, 0, 0, tzinfo=ict)
    ) == Decimal("0.00")

    # Cancelled ticket must not grant coverage
    t1.status = "CANCELLED"
    t1.save(update_fields=["status"])
    t2.status = "CANCELLED"
    t2.save(update_fields=["status"])
    # 7h total (22:00 to 05:00) -> 70,000.00
    assert calculate_parking_fee(
        session, datetime(2026, 11, 11, 5, 0, 0, tzinfo=ict)
    ) == Decimal("70000.00")


def test_tariff_leap_year_and_ict_midnight_boundary():
    """Kiểm tra biên nửa đêm ICT (+07:00 vs UTC) và năm nhuận 2028-02-29."""
    ict = ZoneInfo("Asia/Ho_Chi_Minh")
    v, slot = _make_isolated_vehicle_and_slot("005")
    ttype = (
        TicketType.objects.filter(code="MONTHLY").first() or TicketType.objects.first()
    )

    ticket = Ticket.objects.create(
        code="OVG-005",
        vehicle=v,
        customer=v.customer,
        slot=slot,
        ticket_type=ttype,
        status="EXPIRED",
        effective_from=datetime(2028, 1, 31, 0, 0, 0, tzinfo=ict),
        effective_to=datetime(2028, 3, 1, 0, 0, 0, tzinfo=ict),
        price=Decimal("500000.00"),
    )
    session = VehicleEntryExitLog(
        session_code="#PK-OVG-005",
        vehicle=v,
        ticket=ticket,
        license_plate=v.license_plate,
        license_plate_norm=v.license_plate_norm,
        entry_time=datetime(2028, 2, 29, 22, 30, 0, tzinfo=ict).astimezone(UTC),
    )
    # Exit at 2028-03-01 00:45+07 -> 45m overage = 1h = 10,000.00
    exit_utc = datetime(2028, 3, 1, 0, 45, 0, tzinfo=ict).astimezone(UTC)
    assert calculate_parking_fee(session, exit_utc) == Decimal("10000.00")
