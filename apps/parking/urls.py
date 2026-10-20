"""
URL configuration for parking app per TL-05, TL-50, and SRS 4.5.1.
Routes for Task 8: Vehicle Entry/Exit Management.
"""

from django.urls import path

from apps.parking.views import (
    CheckInView,
    CheckOutView,
    GateListView,
    PlateScanView,
    SessionDetailView,
    SessionListView,
    VehicleLookupView,
    VehicleSearchView,
)

app_name = "parking"

urlpatterns = [
    # 1. Quét biển số xe từ hình ảnh OCR
    path("plate-scans/", PlateScanView.as_view(), name="plate-scans"),
    # 2. Tra cứu phương tiện chính xác theo biển số đã chuẩn hóa
    path("vehicle-lookup/", VehicleLookupView.as_view(), name="vehicle-lookup"),
    # 3. Modal tìm kiếm phương tiện đa tiêu chí (Task 9)
    path("vehicle-search/", VehicleSearchView.as_view(), name="vehicle-search"),
    # 4. Check-in xe vào bãi
    path("sessions/check-in/", CheckInView.as_view(), name="sessions-check-in"),
    # 5. Check-out xe rời bãi và thu phí
    path("sessions/check-out/", CheckOutView.as_view(), name="sessions-check-out"),
    # 6. Danh sách các cổng kiểm soát barrier
    path("gates/", GateListView.as_view(), name="gates"),
    # 7. Danh sách lịch sử và chi tiết phiên đỗ xe
    path("sessions/", SessionListView.as_view(), name="sessions-list"),
    path("sessions/<int:pk>/", SessionDetailView.as_view(), name="sessions-detail"),
]
