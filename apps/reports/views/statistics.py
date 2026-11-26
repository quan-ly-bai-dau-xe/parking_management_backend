"""
Views for reports app - Statistics Summary (SRS 4.7.1).
Manager-only endpoint aggregating revenue, non-revenue wallet top-ups,
vehicle traffic, and live slot occupancy.
"""

from __future__ import annotations

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_message
from apps.core.permissions import IsManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.reports.selectors.statistics import get_statistics_summary
from apps.reports.serializers.statistics import (
    StatisticsSummaryFilterSerializer,
    StatisticsSummaryResponseSerializer,
)


class StatisticsSummaryView(APIView):
    """
    API Thống kê tổng hợp (SRS 4.7.1) - Chỉ dành cho Quản lý (MANAGER).
    """

    permission_classes = [IsAuthenticated, IsManager]

    @extend_schema(
        operation_id="reports_statistics_summary",
        tags=["Dashboard / Reports"],
        summary="Lấy báo cáo thống kê tổng hợp (SRS 4.7.1)",
        description=(
            "Endpoint dành riêng cho Quản lý (MANAGER) cung cấp báo cáo thống kê tổng hợp:\n"
            "- Tổng doanh thu thực thu (Payment status=PAID, loại trừ soft-delete TL-27) "
            "phân rã theo 5 nhóm vé (HOURLY, DAILY, MONTHLY, QUARTERLY, YEARLY) "
            "và 3 phương thức thanh toán (CASH, VIETQR, WALLET).\n"
            "- Chỉ số Non-Revenue: Tổng tiền nạp ví khách hàng (TOPUP_CASH, TOPUP_VIETQR, TOPUP_VNPAY), "
            "tách biệt hoàn toàn khỏi tổng doanh thu.\n"
            "- Lưu lượng xe vào/ra trong kỳ và số xe đang đỗ hiện tại.\n"
            "- Tỷ lệ lấp đầy ô đỗ thời gian thực."
        ),
        parameters=[
            OpenApiParameter(
                name="start_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Ngày bắt đầu lọc (YYYY-MM-DD theo Asia/Ho_Chi_Minh). Mặc định đầu tháng hiện tại.",
            ),
            OpenApiParameter(
                name="end_date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Ngày kết thúc lọc (YYYY-MM-DD theo Asia/Ho_Chi_Minh). Mặc định ngày hôm nay.",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=StatisticsSummaryResponseSerializer,
                description="Báo cáo thống kê tổng hợp thành công",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Tham số ngày không hợp lệ (PROP-4.7.1-P01)",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa đăng nhập hoặc phiên hết hạn",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không có quyền truy cập (chỉ MANAGER được phép)",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        raw_params: dict[str, str] = {}
        start_param = request.query_params.get("start_date")
        end_param = request.query_params.get("end_date")
        if start_param is not None and start_param != "":
            raw_params["start_date"] = start_param
        if end_param is not None and end_param != "":
            raw_params["end_date"] = end_param

        filter_serializer = StatisticsSummaryFilterSerializer(data=raw_params)
        if not filter_serializer.is_valid():
            raise BusinessAPIException(
                code="PROP-4.7.1-P01",
                message=get_message("PROP-4.7.1-P01"),
                status_code=status.HTTP_400_BAD_REQUEST,
                details=filter_serializer.errors,
            )

        validated = filter_serializer.validated_data
        summary = get_statistics_summary(
            start_date=validated["start_date"],
            end_date=validated["end_date"],
        )
        serializer = StatisticsSummaryResponseSerializer(summary)
        return Response(serializer.data, status=status.HTTP_200_OK)
