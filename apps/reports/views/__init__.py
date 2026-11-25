"""
Views module for reports app.
"""

from apps.reports.views.dashboard import (
    DashboardActivityFeedView,
    DashboardAlertsView,
    DashboardFloorOccupancyView,
    DashboardKPIsView,
    DashboardOverviewView,
    DashboardTrafficChartView,
)
from apps.reports.views.statistics import StatisticsSummaryView

__all__ = [
    "DashboardOverviewView",
    "DashboardKPIsView",
    "DashboardFloorOccupancyView",
    "DashboardTrafficChartView",
    "DashboardAlertsView",
    "DashboardActivityFeedView",
    "StatisticsSummaryView",
]
