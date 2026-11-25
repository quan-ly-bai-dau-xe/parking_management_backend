"""
Serializers for reports app - Statistics Summary (SRS 4.7.1).
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.reports.selectors.statistics import get_default_statistics_dates


class StatisticsSummaryFilterSerializer(serializers.Serializer):
    """
    Validate tham số lọc khoảng ngày cho API thống kê tổng hợp 4.7.1.
    Mặc định: từ ngày đầu tháng hiện tại đến hôm nay theo Asia/Ho_Chi_Minh.
    """

    start_date = serializers.DateField(
        required=False,
        allow_null=True,
        input_formats=["%Y-%m-%d"],
        help_text="Ngày bắt đầu lọc (YYYY-MM-DD, Asia/Ho_Chi_Minh)",
    )
    end_date = serializers.DateField(
        required=False,
        allow_null=True,
        input_formats=["%Y-%m-%d"],
        help_text="Ngày kết thúc lọc (YYYY-MM-DD, Asia/Ho_Chi_Minh)",
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        default_start, default_end = get_default_statistics_dates()
        start_date = attrs.get("start_date")
        end_date = attrs.get("end_date")

        if start_date is None and end_date is None:
            start_date = default_start
            end_date = default_end
        elif start_date is None and end_date is not None:
            start_date = end_date.replace(day=1)
        elif start_date is not None and end_date is None:
            end_date = default_end

        if start_date is not None and end_date is not None and start_date > end_date:
            raise serializers.ValidationError(
                {"date_range": ("Ngày bắt đầu không được lớn hơn ngày kết thúc.")}
            )

        attrs["start_date"] = start_date
        attrs["end_date"] = end_date
        return attrs


class StatisticsPeriodSerializer(serializers.Serializer):
    """Khoảng thời gian thống kê (YYYY-MM-DD theo Asia/Ho_Chi_Minh)."""

    start_date = serializers.DateField(help_text="Ngày bắt đầu kỳ thống kê")
    end_date = serializers.DateField(help_text="Ngày kết thúc kỳ thống kê")


class RevenueByTicketTypeSerializer(serializers.Serializer):
    """Phân rã doanh thu thực thu theo 5 nhóm loại vé."""

    HOURLY = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Doanh thu gửi xe theo lượt/giờ và cước quá hạn (VND)",
    )
    DAILY = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Doanh thu vé ngày (VND)",
    )
    MONTHLY = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Doanh thu vé tháng (VND)",
    )
    QUARTERLY = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Doanh thu vé quý (VND)",
    )
    YEARLY = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Doanh thu vé năm (VND)",
    )


class RevenueByPaymentMethodSerializer(serializers.Serializer):
    """Phân rã doanh thu thực thu theo phương thức thanh toán."""

    CASH = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Doanh thu thanh toán bằng tiền mặt (VND)",
    )
    VIETQR = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Doanh thu thanh toán bằng VietQR (VND)",
    )
    WALLET = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Doanh thu thanh toán trừ từ ví khách hàng (VND)",
    )


class NonRevenueWalletTopupSerializer(serializers.Serializer):
    """Chỉ tiêu Non-Revenue: Tiền nạp ví khách hàng (nợ phải trả, không tính doanh thu)."""

    wallet_topup_total = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Tổng tiền nạp vào ví khách hàng trong kỳ (Non-Revenue, VND)",
    )
    topup_cash_total = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Tổng tiền nạp ví bằng tiền mặt tại quầy (VND)",
    )
    topup_vietqr_total = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Tổng tiền nạp ví qua VietQR (VND)",
    )
    topup_vnpay_total = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Tổng tiền nạp ví qua VNPAY (VND)",
    )
    description = serializers.CharField(
        help_text="Ghi chú phân loại kế toán cho khoản tiền trả trước"
    )


class StatisticsTrafficSerializer(serializers.Serializer):
    """Chỉ số lưu lượng xe vào/ra trong kỳ và đang đỗ hiện tại."""

    total_entries = serializers.IntegerField(
        help_text="Tổng lượt xe check-in vào bãi trong kỳ"
    )
    total_exits = serializers.IntegerField(
        help_text="Tổng lượt xe check-out ra khỏi bãi trong kỳ"
    )
    currently_parked = serializers.IntegerField(
        help_text="Tổng số xe hiện đang đỗ trong bãi (snapshot thời gian thực)"
    )


class StatisticsOccupancySerializer(serializers.Serializer):
    """Tỷ lệ lấp đầy ô đỗ thời gian thực trên toàn bãi."""

    total_slots = serializers.IntegerField(help_text="Tổng số ô đỗ đang hoạt động")
    operational_slots = serializers.IntegerField(
        help_text="Số ô đỗ sẵn sàng vận hành (loại trừ MAINTENANCE)"
    )
    occupied_slots = serializers.IntegerField(
        help_text="Số ô đỗ đang có xe (OCCUPIED + CHARGING)"
    )
    available_slots = serializers.IntegerField(help_text="Số ô đỗ đang trống")
    reserved_slots = serializers.IntegerField(help_text="Số ô đỗ đang đặt trước")
    charging_slots = serializers.IntegerField(help_text="Số ô đỗ đang sạc xe điện")
    maintenance_slots = serializers.IntegerField(help_text="Số ô đỗ đang bảo trì")
    occupancy_rate = serializers.FloatField(
        help_text="Tỷ lệ lấp đầy (%) = occupied_slots / operational_slots * 100"
    )


class StatisticsSummaryResponseSerializer(serializers.Serializer):
    """Schema phản hồi chuẩn JSON trực tiếp cho API Thống kê tổng hợp 4.7.1."""

    period = StatisticsPeriodSerializer(help_text="Khoảng ngày lọc thống kê")
    total_revenue = serializers.DecimalField(
        max_digits=20,
        decimal_places=2,
        help_text="Tổng doanh thu thực thu trong kỳ (VND)",
    )
    revenue_by_ticket_type = RevenueByTicketTypeSerializer(
        help_text="Phân rã doanh thu theo loại vé"
    )
    revenue_by_payment_method = RevenueByPaymentMethodSerializer(
        help_text="Phân rã doanh thu theo phương thức thanh toán"
    )
    non_revenue = NonRevenueWalletTopupSerializer(
        help_text="Chỉ tiêu Non-Revenue từ nạp tiền ví khách hàng"
    )
    traffic = StatisticsTrafficSerializer(help_text="Thống kê lưu lượng xe")
    occupancy = StatisticsOccupancySerializer(help_text="Thống kê tỷ lệ lấp đầy bãi xe")
