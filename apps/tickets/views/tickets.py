"""
Views for tickets app.
Provides TicketType list, Ticket list, create, detail, update (with OCC),
delete (with DEL-04 guards, Manager-only), and renew endpoints.
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsEmployeeOrManager, IsManager
from apps.tickets.models import TicketType
from apps.tickets.selectors.tickets import (
    get_ticket_by_lookup,
    get_tickets_queryset,
)
from apps.tickets.serializers.tickets import (
    TicketCreateSerializer,
    TicketDeleteSuccessSerializer,
    TicketDetailSerializer,
    TicketListSerializer,
    TicketRenewSerializer,
    TicketTypeSerializer,
    TicketUpdateSerializer,
)
from apps.tickets.services.tickets import (
    create_ticket,
    delete_ticket,
    renew_ticket,
    update_ticket,
)


class TicketTypeListView(APIView):
    """API Danh mục loại vé đỗ xe (Vé ngày, Vé tháng, Vé quý, Vé năm...)."""

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="ticket_types_list",
        tags=["Tickets"],
        summary="Danh mục loại vé đỗ xe",
        responses={200: TicketTypeSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        queryset = TicketType.objects.filter(deleted_at__isnull=True).order_by("id")
        serializer = TicketTypeSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TicketListCreateView(APIView):
    """API Danh sách vé & Đăng ký vé mới (SRS 4.6.1 & 4.6.2)."""

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        operation_id="tickets_list",
        tags=["Tickets"],
        summary="Lấy danh sách vé đỗ xe phân trang",
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Tìm kiếm theo biển số xe, mã vé, tên KH, SĐT, mã KH",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Lọc theo trạng thái: ACTIVE, EXPIRED, RENEWING, CANCELLED",
            ),
            OpenApiParameter(
                name="ticket_type",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Lọc theo mã loại vé (DAILY, MONTHLY, QUARTERLY, YEARLY) hoặc ID",
            ),
        ],
        responses={200: TicketListSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        search_query = request.query_params.get("q", "").strip()
        status_param = request.query_params.get("status", "").strip()
        ticket_type_param = request.query_params.get("ticket_type", "").strip()

        queryset = get_tickets_queryset(
            search=search_query or None,
            status=status_param or None,
            ticket_type=ticket_type_param or None,
        )

        paginator = self.pagination_class()
        paginated_qs = paginator.paginate_queryset(queryset, request)
        serializer = TicketListSerializer(paginated_qs, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        operation_id="tickets_create",
        tags=["Tickets"],
        summary="Tạo mới vé đỗ xe",
        request=TicketCreateSerializer,
        responses={201: TicketDetailSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = TicketCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ticket = create_ticket(
            data=serializer.validated_data,
            actor_id=request.user.id if request.user.is_authenticated else None,
        )

        res_serializer = TicketDetailSerializer(ticket)
        return Response(res_serializer.data, status=status.HTTP_201_CREATED)


class TicketDetailUpdateDeleteView(APIView):
    """
    API Chi tiết, Chỉnh sửa & Xóa vé đỗ xe (SRS 4.6.1, 4.6.3, 4.6.4).
    Hỗ trợ tra cứu linh hoạt bằng ID số hoặc Mã vé (chuỗi).
    """

    def get_permissions(self):
        if self.request.method == "DELETE":
            return [IsAuthenticated(), IsManager()]
        return [IsAuthenticated(), IsEmployeeOrManager()]

    @extend_schema(
        operation_id="tickets_retrieve",
        tags=["Tickets"],
        summary="Chi tiết vé đỗ xe",
        description="Lấy thông tin chi tiết vé đỗ xe kèm lịch sử gia hạn theo ID hoặc Mã vé.",
        responses={
            200: TicketDetailSerializer,
            404: OpenApiResponse(description="Không tìm thấy vé đỗ xe"),
        },
    )
    def get(self, request: Request, lookup: str) -> Response:
        ticket = get_ticket_by_lookup(lookup)
        if not ticket:
            return Response(
                {
                    "code": "PROP-4.6.4-P05",
                    "message": "Vé không tồn tại hoặc đã bị xóa.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = TicketDetailSerializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="tickets_update",
        tags=["Tickets"],
        summary="Chỉnh sửa vé đỗ xe / gia hạn vé (SRS 4.6.3)",
        description="Cập nhật thông tin vé với kiểm soát khóa lạc quan (OCC) row_version.",
        request=TicketUpdateSerializer,
        responses={
            200: TicketDetailSerializer,
            400: OpenApiResponse(description="Dữ liệu không hợp lệ"),
            404: OpenApiResponse(description="Không tìm thấy vé đỗ xe"),
            409: OpenApiResponse(description="Xung đột khóa lạc quan OCC"),
        },
    )
    def patch(self, request: Request, lookup: str) -> Response:
        serializer = TicketUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ticket = update_ticket(
            lookup=lookup,
            data=serializer.validated_data,
            actor_id=request.user.id if request.user.is_authenticated else None,
        )

        res_serializer = TicketDetailSerializer(ticket)
        return Response(res_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="tickets_destroy",
        tags=["Tickets"],
        summary="Xóa mềm vé đỗ xe (SRS 4.6.4 / DEL-04)",
        description="Xóa mềm vé đỗ xe (Chỉ dành riêng cho Quản lý / MANAGER-only).",
        responses={
            200: TicketDeleteSuccessSerializer,
            400: OpenApiResponse(description="Vé không đủ điều kiện xóa (DEL-04)"),
            403: OpenApiResponse(description="Chỉ Quản lý mới có quyền xóa vé"),
            404: OpenApiResponse(description="Không tìm thấy vé đỗ xe"),
        },
    )
    def delete(self, request: Request, lookup: str) -> Response:
        result = delete_ticket(
            lookup=lookup,
            actor_id=request.user.id if request.user.is_authenticated else None,
        )
        return Response(result, status=status.HTTP_200_OK)


class TicketRenewView(APIView):
    """API Gia hạn vé đỗ xe (SRS 4.6.3)."""

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="tickets_renew",
        tags=["Tickets"],
        summary="Gia hạn vé đỗ xe",
        description="Gia hạn thời hạn vé đỗ xe, có thể đổi loại vé hoặc đổi vị trí đỗ.",
        request=TicketRenewSerializer,
        responses={
            200: TicketDetailSerializer,
            404: OpenApiResponse(description="Không tìm thấy vé đỗ xe để gia hạn"),
        },
    )
    def post(self, request: Request, lookup: str) -> Response:
        serializer = TicketRenewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        ticket = renew_ticket(
            lookup=lookup,
            data=serializer.validated_data,
            actor_id=request.user.id if request.user.is_authenticated else None,
        )

        res_serializer = TicketDetailSerializer(ticket)
        return Response(res_serializer.data, status=status.HTTP_200_OK)
