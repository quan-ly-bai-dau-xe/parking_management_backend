"""
Views for ParkingSlot domain per TL-25, TL-27, TL-50, and SRS 4.8.1 - 4.8.5.
Exposes REST endpoints for slot listing, creation, retrieval, updating, and soft-deletion.
"""

from __future__ import annotations

from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_prop_message
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsEmployeeOrManager, IsManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.parking.selectors.slots import get_slot_by_id, get_slots_queryset
from apps.parking.serializers.slots import (
    ParkingSlotCreateSerializer,
    ParkingSlotUpdateSerializer,
    SlotDeleteSuccessSerializer,
    SlotDetailSerializer,
    SlotFilterSerializer,
    SlotItemSerializer,
    SlotPaginatedResponseSerializer,
)
from apps.parking.services.slots import (
    create_parking_slot,
    soft_delete_parking_slot,
    update_parking_slot,
)


class SlotListCreateView(APIView):
    """
    API Danh sách và Thêm mới ô đỗ xe (SRS 4.8.1, 4.8.2).
    - GET: Dành cho nhân viên và quản lý (IsEmployeeOrManager).
    - POST: Chỉ dành cho quản lý (IsManager).
    """

    pagination_class = StandardResultsSetPagination

    def get_permissions(self) -> list[BasePermission]:
        if self.request.method == "POST":
            return [IsAuthenticated(), IsManager()]
        return [IsAuthenticated(), IsEmployeeOrManager()]

    @extend_schema(
        operation_id="parking_slots_list",
        tags=["Parking - Slots"],
        summary="Lấy danh sách ô đỗ xe",
        description=(
            "Truy vấn danh sách các ô đỗ xe trong hệ thống với các bộ lọc đa tiêu chí "
            "(tầng, khu vực, trạng thái, loại xe, loại ô đỗ, tìm kiếm). "
            "Loại trừ hoàn toàn các bản ghi đã xóa mềm (deleted_at IS NULL). "
            "Cam kết tối ưu hóa O(1) query (Zero N+1) qua select_related và prefetch_related."
        ),
        parameters=[
            OpenApiParameter(
                name="floor",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Mã hoặc ID tầng (ví dụ: 'B1', '1')",
            ),
            OpenApiParameter(
                name="zone",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Mã hoặc ID khu vực (ví dụ: 'A', '2')",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description=(
                    "Trạng thái ô đỗ (AVAILABLE, OCCUPIED, RESERVED, CHARGING, MAINTENANCE) "
                    "hoặc danh sách phân cách dấu phẩy, hoặc 'OVERSTAY'"
                ),
            ),
            OpenApiParameter(
                name="vehicle_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Mã hoặc ID loại phương tiện cho phép (ví dụ: 'CAR', 'EV')",
            ),
            OpenApiParameter(
                name="slot_kind",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Loại ô đỗ: 'STANDARD', 'PRIORITY', 'EV_CHARGING'",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Từ khóa tìm kiếm theo mã ô đỗ hoặc ghi chú",
            ),
            OpenApiParameter(
                name="ordering",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Sắp xếp kết quả (ví dụ: 'code', '-code', 'status')",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Số trang (mặc định 1)",
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Số lượng phần tử trên mỗi trang (mặc định 20, tối đa 100)",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=SlotPaginatedResponseSerializer,
                description="Danh sách ô đỗ xe phân trang hợp lệ",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực người dùng",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không có quyền truy cập (yêu cầu vai trò Employee hoặc Manager)",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        filter_serializer = SlotFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        params = filter_serializer.validated_data

        qs = get_slots_queryset(
            floor=params.get("floor"),
            zone=params.get("zone"),
            status_filter=params.get("status"),
            vehicle_type=params.get("vehicle_type"),
            slot_kind=params.get("slot_kind"),
            search=params.get("search"),
            ordering=params.get("ordering"),
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        if page is not None:
            serializer = SlotItemSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = SlotItemSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="parking_slots_create",
        tags=["Parking - Slots"],
        summary="Thêm mới ô đỗ xe",
        description=(
            "Tạo mới một ô đỗ xe trong bãi (SRS 4.8.2). "
            "Chỉ Quản lý (IsManager) mới có quyền thực hiện. "
            "Kiểm tra trùng lặp mã ô trên tầng/khu vực và tính hợp lệ của định dạng mã."
        ),
        request=ParkingSlotCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=SlotDetailSerializer,
                description="Thêm mới vị trí đỗ xe thành công (PROP-4.8.2-P01)",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Dữ liệu vị trí đỗ xe không hợp lệ (PROP-4.8.2-P02)",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa đăng nhập",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền thực hiện (chỉ Quản lý)",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Vị trí đỗ xe đã tồn tại trên tầng này (PROP-4.8.2-P03)",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = ParkingSlotCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = getattr(request.user, "id", None)
        slot = create_parking_slot(serializer.validated_data, actor_id=user_id)

        full_slot = get_slot_by_id(slot.id)
        out_serializer = SlotDetailSerializer(full_slot or slot)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class SlotDetailUpdateDeleteView(APIView):
    """
    API Xem chi tiết, Cập nhật và Xóa mềm ô đỗ xe (SRS 4.8.3, 4.8.4, 4.8.5).
    - GET: Dành cho nhân viên và quản lý (IsEmployeeOrManager).
    - PATCH, DELETE: Chỉ dành cho quản lý (IsManager).
    """

    def get_permissions(self) -> list[BasePermission]:
        if self.request.method in ("PATCH", "DELETE"):
            return [IsAuthenticated(), IsManager()]
        return [IsAuthenticated(), IsEmployeeOrManager()]

    @extend_schema(
        operation_id="parking_slots_retrieve",
        tags=["Parking - Slots"],
        summary="Xem chi tiết thông tin ô đỗ xe",
        description=(
            "Lấy thông tin chi tiết của một ô đỗ xe bao gồm các phiên đỗ đang mở, "
            "thông tin xe đang đỗ, vé tháng/ngày hiệu lực, và đặt chỗ trước (SRS 4.8.4)."
        ),
        responses={
            200: OpenApiResponse(
                response=SlotDetailSerializer,
                description="Thông tin chi tiết ô đỗ xe",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không có quyền truy cập",
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Vị trí đỗ xe không tồn tại hoặc đã bị xóa (PROP-4.8.5-P05)",
            ),
        },
    )
    def get(self, request: Request, pk: int) -> Response:
        slot = get_slot_by_id(pk)
        if not slot:
            raise BusinessAPIException(
                code="PROP-4.8.5-P05",
                message=get_prop_message(
                    "PROP-4.8.5-P05", "Vị trí đỗ xe không tồn tại hoặc đã bị xóa."
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = SlotDetailSerializer(slot)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="parking_slots_partial_update",
        tags=["Parking - Slots"],
        summary="Cập nhật thông tin ô đỗ xe",
        description=(
            "Cập nhật thông tin ô đỗ xe với cơ chế Optimistic Concurrency Control (OCC) (SRS 4.8.3). "
            "Bắt buộc gửi kèm `row_version`. Trả về HTTP 409 Conflict nếu bị xung đột cập nhật "
            "hoặc vi phạm các trigger ràng buộc trạng thái của cơ sở dữ liệu."
        ),
        request=ParkingSlotUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=SlotDetailSerializer,
                description="Cập nhật thông tin vị trí đỗ xe thành công (PROP-4.8.3-P01)",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Dữ liệu cập nhật vị trí đỗ xe không hợp lệ (PROP-4.8.3-P02)",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa đăng nhập",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền thực hiện (chỉ Quản lý)",
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Vị trí đỗ xe không tồn tại hoặc đã bị xóa (PROP-4.8.5-P05)",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description=(
                    "Xung đột phiên bản dữ liệu (PROP-4.8.3-P03) hoặc xung đột trạng thái ô đỗ"
                ),
            ),
        },
    )
    def patch(self, request: Request, pk: int) -> Response:
        serializer = ParkingSlotUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = getattr(request.user, "id", None)
        update_parking_slot(
            slot_id=pk,
            data=serializer.validated_data,
            actor_id=user_id,
        )

        full_slot = get_slot_by_id(pk)
        out_serializer = SlotDetailSerializer(full_slot)
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="parking_slots_destroy",
        tags=["Parking - Slots"],
        summary="Xóa mềm ô đỗ xe",
        description=(
            "Xóa mềm một ô đỗ xe khỏi hệ thống (SRS 4.8.5). "
            "Chỉ Quản lý mới có quyền thực hiện. "
            "Chặn thao tác với HTTP 409 nếu ô đang có xe đỗ (OCCUPIED), "
            "có vé hiệu lực, hoặc có đặt chỗ còn hiệu lực."
        ),
        responses={
            200: OpenApiResponse(
                response=SlotDeleteSuccessSerializer,
                description="Xóa vị trí đỗ xe thành công (PROP-4.8.5-P01)",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa đăng nhập",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền thực hiện (chỉ Quản lý)",
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Vị trí đỗ xe không tồn tại hoặc đã bị xóa (PROP-4.8.5-P05)",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description=(
                    "Không thể xóa ô đỗ do đang có phương tiện, vé hoặc đặt trước hiệu lực"
                ),
            ),
        },
    )
    def delete(self, request: Request, pk: int) -> Response:
        user_id = getattr(request.user, "id", None)
        result = soft_delete_parking_slot(slot_id=pk, actor_id=user_id)
        return Response(result, status=status.HTTP_200_OK)
