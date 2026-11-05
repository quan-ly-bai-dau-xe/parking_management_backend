"""
URL configuration for reports app per TL-13, TL-14, and TL-28.6.
Routes for Trang chủ (Dashboard & Analytics).
"""

from django.urls import path

from apps.reports.views.dashboard import (
    DashboardActivityFeedView,
    DashboardAlertsView,
    DashboardFloorOccupancyView,
    DashboardKPIsView,
    DashboardOverviewView,
    DashboardTrafficChartView,
)

app_name = "reports"

urlpatterns = [
    # 1. Tổng quan toàn bộ Dashboard Trang chủ
    path("dashboard/", DashboardOverviewView.as_view(), name="dashboard-overview"),
    # 2. 4 nhóm thẻ KPI đầu trang (Kho vị trí, Lưu lượng, Doanh thu, AI)
    path("dashboard/kpis/", DashboardKPIsView.as_view(), name="dashboard-kpis"),
    # 3. Tỷ lệ lấp đầy theo tầng (TL-28.6: B1, B2, B3)
    path(
        "dashboard/floors/",
        DashboardFloorOccupancyView.as_view(),
        name="dashboard-floors",
    ),
    # 4. Biểu đồ lưu lượng xe 24 giờ
    path(
        "dashboard/traffic/",
        DashboardTrafficChartView.as_view(),
        name="dashboard-traffic",
    ),
    # 5. Danh sách cảnh báo khẩn cấp và bất thường (TL-13)
    path("dashboard/alerts/", DashboardAlertsView.as_view(), name="dashboard-alerts"),
    # 6. Nhật ký dòng hoạt động gần đây
    path(
        "dashboard/activities/",
        DashboardActivityFeedView.as_view(),
        name="dashboard-activities",
    ),
]
