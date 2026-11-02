"""
Views for reports app - Dashboard & Analytics.
Exposes REST endpoints for Trang chủ — Smart Mobility.png per TL-13, TL-14, and TL-28.6.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsEmployeeOrManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.reports.selectors.dashboard import (
    get_dashboard_summary_kpis,
    get_emergency_alerts,
    get_floor_occupancy_bars,
    get_recent_activity_feed,
    get_traffic_chart_24h,
)
from apps.reports.serializers.dashboard import (
    DashboardOverviewResponseSerializer,
    DashboardSummaryKPISerializer,
    EmergencyAlertSerializer,
    FloorOccupancyBarSerializer,
    RecentActivitySerializer,
    TrafficHourPointSerializer,
)


class DashboardOverviewView(APIView):
    """
    API Tổng quan Trang chủ (Dashboard Overview).
    Tổng hợp toàn bộ 4 thẻ KPI, thanh tỷ lệ lấp đầy tầng, biểu đồ lưu lượng 24h,
    danh sách cảnh báo bất thường và nhật ký hoạt động xe vào/ra trong 1 HTTP request duy nhất.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="reports_dashboard_overview",
        tags=["Dashboard / Reports"],
        summary="Lấy toàn bộ dữ liệu tổng quan cho Trang chủ (Dashboard)",
        description=(
            "Trả về toàn bộ số liệu tổng hợp phục vụ hiển thị Trang chủ — Smart Mobility.png:\n"
            "- 4 thẻ chỉ số KPI (Vị trí đỗ, lưu lượng xe, doanh thu hôm nay, tỷ lệ AI).\n"
            "- Tỷ lệ lấp đầy các tầng (B1, B2, B3) theo chuẩn TL-28.6.\n"
            "- Biểu đồ lưu lượng xe vào/ra theo 24 giờ.\n"
            "- Cảnh báo khẩn cấp/bất thường từ system_alert.\n"
            "- Dòng hoạt động các lượt xe ra/vào gần nhất.\n\n"
            "*Lưu ý*: Chỉ vai trò MANAGER mới nhận được số liệu doanh thu tài chính chi tiết (Rule 01 Section 2)."
        ),
        responses={
            200: OpenApiResponse(
                response=DashboardOverviewResponseSerializer,
                description="Dữ liệu tổng quan Dashboard trang chủ thành công",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa đăng nhập hoặc phiên hết hạn",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập (CUSTOMER bị từ chối)",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        user = request.user
        kpis = get_dashboard_summary_kpis(user)
        floors = get_floor_occupancy_bars()
        traffic_chart = get_traffic_chart_24h()
        alerts = get_emergency_alerts(limit=10)
        recent_activities = get_recent_activity_feed(limit=10)

        data = {
            "kpis": kpis,
            "floors": floors,
            "traffic_chart": traffic_chart,
            "alerts": alerts,
            "recent_activities": recent_activities,
        }

        serializer = DashboardOverviewResponseSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DashboardKPIsView(APIView):
    """
    API 4 thẻ chỉ số KPI đầu trang chủ (Slots, Traffic, Revenue, AI).
    Phục vụ tải nhanh hoặc cập nhật định kỳ (polling) riêng khối số liệu KPI.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="reports_dashboard_kpis",
        tags=["Dashboard / Reports"],
        summary="Lấy 4 thẻ chỉ số KPI tổng quan",
        description="Trả về số liệu 4 thẻ KPI trên đầu Trang chủ (Kho vị trí, Lượt xe, Doanh thu hôm nay, Tỷ lệ AI).",
        responses={
            200: OpenApiResponse(
                response=DashboardSummaryKPISerializer,
                description="Số liệu 4 nhóm KPI thành công",
            ),
            401: OpenApiResponse(response=ErrorEnvelopeSerializer),
            403: OpenApiResponse(response=ErrorEnvelopeSerializer),
        },
    )
    def get(self, request: Request) -> Response:
        kpis = get_dashboard_summary_kpis(request.user)
        serializer = DashboardSummaryKPISerializer(kpis)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DashboardFloorOccupancyView(APIView):
    """
    API Tỷ lệ lấp đầy theo tầng (TL-28.6).
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="reports_dashboard_floors",
        tags=["Dashboard / Reports"],
        summary="Lấy thanh tỷ lệ lấp đầy các tầng (B1, B2, B3)",
        description="Trả về thông tin số chỗ đã dùng, chỗ trống, % lấp đầy và badge trạng thái từng tầng theo TL-28.6.",
        responses={
            200: OpenApiResponse(
                response=FloorOccupancyBarSerializer(many=True),
                description="Danh sách tỷ lệ lấp đầy theo tầng",
            ),
            401: OpenApiResponse(response=ErrorEnvelopeSerializer),
            403: OpenApiResponse(response=ErrorEnvelopeSerializer),
        },
    )
    def get(self, request: Request) -> Response:
        floors = get_floor_occupancy_bars()
        serializer = FloorOccupancyBarSerializer(floors, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DashboardTrafficChartView(APIView):
    """
    API Biểu đồ lưu lượng xe vào / ra 24h.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="reports_dashboard_traffic",
        tags=["Dashboard / Reports"],
        summary="Lấy số liệu biểu đồ lưu lượng xe vào / ra 24 giờ",
        description="Trả về danh sách các điểm dữ liệu theo khung giờ phục vụ vẽ biểu đồ lưu lượng xe trên Trang chủ.",
        responses={
            200: OpenApiResponse(
                response=TrafficHourPointSerializer(many=True),
                description="Dữ liệu biểu đồ lưu lượng 24h thành công",
            ),
            401: OpenApiResponse(response=ErrorEnvelopeSerializer),
            403: OpenApiResponse(response=ErrorEnvelopeSerializer),
        },
    )
    def get(self, request: Request) -> Response:
        chart_data = get_traffic_chart_24h()
        serializer = TrafficHourPointSerializer(chart_data, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DashboardAlertsView(APIView):
    """
    API Danh sách cảnh báo khẩn cấp và bất thường (TL-13).
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="reports_dashboard_alerts",
        tags=["Dashboard / Reports"],
        summary="Lấy danh sách cảnh báo bất thường và khẩn cấp",
        description="Trả về các cảnh báo an ninh, lỗi camera hoặc cảnh báo quá hạn đỗ xe từ bảng system_alert.",
        responses={
            200: OpenApiResponse(
                response=EmergencyAlertSerializer(many=True),
                description="Danh sách cảnh báo thành công",
            ),
            401: OpenApiResponse(response=ErrorEnvelopeSerializer),
            403: OpenApiResponse(response=ErrorEnvelopeSerializer),
        },
    )
    def get(self, request: Request) -> Response:
        alerts = get_emergency_alerts(limit=10)
        serializer = EmergencyAlertSerializer(alerts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DashboardActivityFeedView(APIView):
    """
    API Nhật ký hoạt động xe ra vào gần nhất.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="reports_dashboard_activities",
        tags=["Dashboard / Reports"],
        summary="Lấy danh sách hoạt động xe ra vào gần nhất",
        description="Trả về các lượt xe vào và ra bãi đỗ mới nhất hiển thị tại danh sách hoạt động trên Trang chủ.",
        responses={
            200: OpenApiResponse(
                response=RecentActivitySerializer(many=True),
                description="Danh sách hoạt động thành công",
            ),
            401: OpenApiResponse(response=ErrorEnvelopeSerializer),
            403: OpenApiResponse(response=ErrorEnvelopeSerializer),
        },
    )
    def get(self, request: Request) -> Response:
        activities = get_recent_activity_feed(limit=10)
        serializer = RecentActivitySerializer(activities, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

