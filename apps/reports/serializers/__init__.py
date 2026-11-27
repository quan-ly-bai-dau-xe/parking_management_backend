"""
Serializers module for reports app.
"""

from apps.reports.serializers.dashboard import (
    AiRecognitionKPISerializer,
    DashboardOverviewResponseSerializer,
    DashboardSummaryKPISerializer,
    EmergencyAlertSerializer,
    FloorOccupancyBarSerializer,
    RecentActivitySerializer,
    RevenueTodayKPISerializer,
    SlotKPISerializer,
    TrafficHourPointSerializer,
    TrafficKPISerializer,
)
from apps.reports.serializers.statistics import (
    NonRevenueWalletTopupSerializer,
    RevenueByPaymentMethodSerializer,
    RevenueByTicketTypeSerializer,
    StatisticsOccupancySerializer,
    StatisticsPeriodSerializer,
    StatisticsSummaryFilterSerializer,
    StatisticsSummaryResponseSerializer,
    StatisticsTrafficSerializer,
)

__all__ = [
    "SlotKPISerializer",
    "TrafficKPISerializer",
    "RevenueTodayKPISerializer",
    "AiRecognitionKPISerializer",
    "DashboardSummaryKPISerializer",
    "FloorOccupancyBarSerializer",
    "TrafficHourPointSerializer",
    "EmergencyAlertSerializer",
    "RecentActivitySerializer",
    "DashboardOverviewResponseSerializer",
    "StatisticsSummaryFilterSerializer",
    "StatisticsPeriodSerializer",
    "RevenueByTicketTypeSerializer",
    "RevenueByPaymentMethodSerializer",
    "NonRevenueWalletTopupSerializer",
    "StatisticsTrafficSerializer",
    "StatisticsOccupancySerializer",
    "StatisticsSummaryResponseSerializer",
]
