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
]
