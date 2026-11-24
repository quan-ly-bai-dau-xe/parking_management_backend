"""
Parking Slot Views per SRS 4.5.2 and frontend parkingLotService.
Provides:
- GET /api/v1/parking/slots/ (list slots with floor/zone/status filter)
- GET /api/v1/parking/slots/<int:pk>/ (detail slot)
- PATCH /api/v1/parking/slots/<int:pk>/ (update status/notes)
"""

from __future__ import annotations

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import ALL_MESSAGES
from apps.core.permissions import IsEmployeeOrManager
from apps.parking.models import ParkingSlot
from apps.parking.serializers.slots import (
    ParkingSlotSerializer,
    ParkingSlotUpdateSerializer,
)


class SlotListView(APIView):
    """
    Danh sách ô đỗ xe hỗ trợ lọc theo tầng, khu vực, trạng thái, loại ô đỗ và tìm kiếm.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="parking_slots_list",
        tags=["Parking"],
        summary="Danh sách ô đỗ xe",
        description="Lấy danh sách các ô đỗ xe với bộ lọc theo tầng, khu vực, trạng thái, loại xe/ô đỗ.",
        parameters=[
            OpenApiParameter(
                name="floor",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Mã tầng (ví dụ: B1, B2)",
            ),
            OpenApiParameter(
                name="zone",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Mã khu vực (ví dụ: A, B, C)",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Trạng thái ô đỗ: AVAILABLE, OCCUPIED, RESERVED, CHARGING, MAINTENANCE",
            ),
            OpenApiParameter(
                name="slot_kind",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Loại ô đỗ: STANDARD, EV_CHARGING, VIP, ACCESSIBLE",
            ),
            OpenApiParameter(
                name="search",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Tìm kiếm theo mã ô đỗ (code)",
            ),
        ],
        responses={200: ParkingSlotSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        qs = (
            ParkingSlot.objects.filter(deleted_at__isnull=True)
            .select_related("zone", "zone__floor")
            .prefetch_related("entry_exit_logs")
            .order_by("zone__floor__sort_order", "zone__code", "code")
        )

        floor_param = request.query_params.get("floor")
        if floor_param:
            floor_param = floor_param.strip()
            if floor_param.isdigit():
                qs = qs.filter(zone__floor_id=int(floor_param))
            else:
                qs = qs.filter(
                    Q(zone__floor__code__iexact=floor_param)
                    | Q(zone__floor__name__icontains=floor_param)
                )

        zone_param = request.query_params.get("zone")
        if zone_param:
            zone_param = zone_param.strip()
            if zone_param.isdigit():
                qs = qs.filter(zone_id=int(zone_param))
            else:
                qs = qs.filter(
                    Q(zone__code__iexact=zone_param)
                    | Q(zone__name__icontains=zone_param)
                )

        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param.strip().upper())

        slot_kind_param = request.query_params.get("slot_kind")
        if slot_kind_param:
            qs = qs.filter(slot_kind=slot_kind_param.strip().upper())

        search_param = request.query_params.get("search")
        if search_param:
            search_param = search_param.strip()
            qs = qs.filter(
                Q(code__icontains=search_param) | Q(notes__icontains=search_param)
            )

        serializer = ParkingSlotSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SlotDetailUpdateView(APIView):
    """
    Xem chi tiết và cập nhật trạng thái hoặc ghi chú của ô đỗ xe.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    def _get_slot(self, pk: int) -> ParkingSlot:
        slot = (
            ParkingSlot.objects.filter(id=pk, deleted_at__isnull=True)
            .select_related("zone", "zone__floor")
            .prefetch_related("entry_exit_logs")
            .first()
        )
        if not slot:
            raise BusinessAPIException(
                code="MSG-4.4.1-M01",
                message=ALL_MESSAGES.get("MSG-4.4.1-M01", "Không tìm thấy dữ liệu"),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return slot

    @extend_schema(
        operation_id="parking_slot_detail",
        tags=["Parking"],
        summary="Chi tiết ô đỗ xe",
        description="Lấy thông tin chi tiết một ô đỗ xe theo ID.",
        responses={200: ParkingSlotSerializer},
    )
    def get(self, request: Request, pk: int) -> Response:
        slot = self._get_slot(pk)
        serializer = ParkingSlotSerializer(slot)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="parking_slot_update",
        tags=["Parking"],
        summary="Cập nhật ô đỗ xe",
        description="Cập nhật trạng thái hoặc ghi chú cho ô đỗ xe.",
        request=ParkingSlotUpdateSerializer,
        responses={200: ParkingSlotSerializer},
    )
    def patch(self, request: Request, pk: int) -> Response:
        slot = self._get_slot(pk)
        serializer = ParkingSlotUpdateSerializer(slot, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        # Trả về đối tượng đầy đủ
        return Response(ParkingSlotSerializer(slot).data, status=status.HTTP_200_OK)
