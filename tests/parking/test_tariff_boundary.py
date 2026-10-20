"""
Tariff calculation boundary and stress scenarios per OQ-85 and TL-50.
"""

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest


def reference_calculate_parking_fee(
    entry_time: datetime,
    exit_time: datetime,
    has_active_ticket: bool,
    hourly_rate: Decimal = Decimal("10000.00"),
) -> Decimal:
    """
    Hàm tham chiếu chuẩn tắc (Reference Oracle) tính cước đỗ xe theo OQ-85 và TL-50:
    - Nếu có vé ACTIVE hiệu lực: fee = Decimal("0.00").
    - Ngược lại: duration = exit_time - entry_time.
      Yêu cầu: exit_time >= entry_time (chặn nghịch đảo thời gian).
      parked_hours = max(1, math.ceil(duration_seconds / 3600)).
      fee = parked_hours * hourly_rate (quantize Decimal("0.01")).
    """
    if has_active_ticket:
        return Decimal("0.00")

    if exit_time < entry_time:
        raise ValueError(
            "Thời điểm ra (exit_time) không thể xảy ra trước thời điểm vào (entry_time)."
        )

    total_sec = (exit_time - entry_time).total_seconds()
    hours = math.ceil(total_sec / 3600.0)
    parked_hours = max(1, hours)

    fee = (Decimal(parked_hours) * Decimal(str(hourly_rate))).quantize(Decimal("0.01"))
    return fee


class TestTariffBoundaryStress:
    """
    Thử nghiệm tính cước đỗ xe OQ-85/TL-50 với các mốc thời gian biên:
    0s, 1s, 59m 59s, đúng 60m, 60m 01s, 119m 59s, 120m, 120m 01s, vé ACTIVE, và stress dài ngày.
    """

    base_time = datetime(2026, 10, 18, 8, 0, 0, tzinfo=UTC)
    default_rate = Decimal("10000.00")

    def test_tariff_boundary_0_seconds(self):
        """Biên 0 giây (vào và ra cùng thời điểm): Tính tối thiểu 1 giờ = 10,000 VND."""
        entry = self.base_time
        exit_ = self.base_time
        fee = reference_calculate_parking_fee(entry, exit_, has_active_ticket=False)
        assert fee == Decimal("10000.00")
        assert isinstance(fee, Decimal)

    def test_tariff_boundary_1_second(self):
        """Biên 1 giây: Tính 1 giờ = 10,000 VND."""
        entry = self.base_time
        exit_ = entry + timedelta(seconds=1)
        fee = reference_calculate_parking_fee(entry, exit_, has_active_ticket=False)
        assert fee == Decimal("10000.00")

    def test_tariff_boundary_59_minutes_59_seconds(self):
        """Biên 59 phút 59 giây (3599 giây): Vẫn trong giờ thứ 1 = 10,000 VND."""
        entry = self.base_time
        exit_ = entry + timedelta(minutes=59, seconds=59)
        fee = reference_calculate_parking_fee(entry, exit_, has_active_ticket=False)
        assert fee == Decimal("10000.00")

    def test_tariff_boundary_exactly_60_minutes(self):
        """Biên đúng 60 phút tròn (3600 giây): Đúng 1 giờ tròn = 10,000 VND."""
        entry = self.base_time
        exit_ = entry + timedelta(minutes=60)
        fee = reference_calculate_parking_fee(entry, exit_, has_active_ticket=False)
        assert fee == Decimal("10000.00")

    def test_tariff_boundary_60_minutes_1_second(self):
        """Biên 60 phút 1 giây (3601 giây): Vượt sang giờ thứ 2, làm tròn lên 2 giờ = 20,000 VND."""
        entry = self.base_time
        exit_ = entry + timedelta(minutes=60, seconds=1)
        fee = reference_calculate_parking_fee(entry, exit_, has_active_ticket=False)
        assert fee == Decimal("20000.00")

    def test_tariff_boundary_119_minutes_59_seconds(self):
        """Biên 119 phút 59 giây (7199 giây): Vẫn trong giờ thứ 2 = 20,000 VND."""
        entry = self.base_time
        exit_ = entry + timedelta(minutes=119, seconds=59)
        fee = reference_calculate_parking_fee(entry, exit_, has_active_ticket=False)
        assert fee == Decimal("20000.00")

    def test_tariff_boundary_exactly_120_minutes(self):
        """Biên đúng 120 phút (7200 giây): Đúng 2 giờ tròn = 20,000 VND."""
        entry = self.base_time
        exit_ = entry + timedelta(minutes=120)
        fee = reference_calculate_parking_fee(entry, exit_, has_active_ticket=False)
        assert fee == Decimal("20000.00")

    def test_tariff_boundary_120_minutes_1_second(self):
        """Biên 120 phút 1 giây (7201 giây): Vượt sang giờ thứ 3, làm tròn lên 3 giờ = 30,000 VND."""
        entry = self.base_time
        exit_ = entry + timedelta(minutes=120, seconds=1)
        fee = reference_calculate_parking_fee(entry, exit_, has_active_ticket=False)
        assert fee == Decimal("30000.00")

    def test_tariff_active_ticket_waiver(self):
        """
        Trường hợp có vé ACTIVE: Phí luôn bằng 0.00 VND
        bất kể thời gian đỗ (0 giây, 60 phút, 10 ngày).
        """
        entry = self.base_time
        assert reference_calculate_parking_fee(
            entry, entry, has_active_ticket=True
        ) == Decimal("0.00")
        assert reference_calculate_parking_fee(
            entry, entry + timedelta(minutes=59, seconds=59), has_active_ticket=True
        ) == Decimal("0.00")
        assert reference_calculate_parking_fee(
            entry, entry + timedelta(minutes=60, seconds=1), has_active_ticket=True
        ) == Decimal("0.00")
        assert reference_calculate_parking_fee(
            entry, entry + timedelta(days=10), has_active_ticket=True
        ) == Decimal("0.00")

    def test_tariff_long_stay_stress(self):
        """Đỗ dài ngày: 24 giờ (240k), 7 ngày (1.68M), 30 ngày (7.2M)."""
        entry = self.base_time
        fee_24h = reference_calculate_parking_fee(
            entry, entry + timedelta(hours=24), has_active_ticket=False
        )
        assert fee_24h == Decimal("240000.00")
        fee_7d = reference_calculate_parking_fee(
            entry, entry + timedelta(days=7), has_active_ticket=False
        )
        assert fee_7d == Decimal("1680000.00")
        fee_30d = reference_calculate_parking_fee(
            entry, entry + timedelta(days=30), has_active_ticket=False
        )
        assert fee_30d == Decimal("7200000.00")

    def test_tariff_microsecond_precision_edge(self):
        """
        Biên microsecond: 60 phút lẻ 100 microseconds (3600.000100 giây).
        Phải được làm tròn lên 2 giờ (20,000 VND), không bị lỗi do ép kiểu int() sớm!
        """
        entry = self.base_time
        exit_ = entry + timedelta(seconds=3600, microseconds=100)
        fee = reference_calculate_parking_fee(entry, exit_, has_active_ticket=False)
        assert fee == Decimal("20000.00"), (
            "60 phút lẻ microsecond phải làm tròn lên 2 giờ"
        )

    def test_tariff_time_reversal_rejection(self):
        """Nghịch đảo thời gian (exit_time < entry_time): Bắt buộc ném ValueError."""
        entry = self.base_time
        exit_ = entry - timedelta(seconds=1)
        with pytest.raises(ValueError, match="không thể xảy ra trước"):
            reference_calculate_parking_fee(entry, exit_, has_active_ticket=False)

    def test_tariff_custom_hourly_rates_and_decimal_safety(self):
        """Kiểm tra độ chính xác Decimal với các mức đơn giá khác nhau."""
        entry = self.base_time
        exit_ = entry + timedelta(hours=3)

        fee_fraction = reference_calculate_parking_fee(
            entry,
            exit_,
            has_active_ticket=False,
            hourly_rate=Decimal("12500.50"),
        )
        assert fee_fraction == Decimal("37501.50")

        fee_zero = reference_calculate_parking_fee(
            entry, exit_, has_active_ticket=False, hourly_rate=Decimal("0.00")
        )
        assert fee_zero == Decimal("0.00")
