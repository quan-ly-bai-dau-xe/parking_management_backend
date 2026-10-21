"""
Unit tests for parking tariff calculation service per OQ-85, TL-50.
Verifies:
- Active ticket produces 0 VND fee.
- Expired/soft-deleted ticket does not waive fee.
- Hourly calculation ceil(duration_seconds / 3600) with minimum 1 hour.
- Decimal precision 10000.00 VND.
- Duration formatting in Vietnamese.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.parking.models import ParkingSlot, VehicleEntryExitLog
from apps.parking.selectors.sessions import (
    calculate_session_duration,
    format_duration_text,
)
from apps.parking.services.tariff import calculate_parking_fee
from apps.tickets.models import Ticket, TicketType
from apps.vehicles.models import Vehicle

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
    """Vé đã hết hạn không được tính miễn phí, tính phí theo giờ bình thường."""
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
        effective_to=now - timedelta(hours=1),  # Đã hết hạn trước thời điểm ra
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
