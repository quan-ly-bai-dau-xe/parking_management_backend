"""
Views for SlotReservation and Customer Parking Map endpoints (SRS 4.5.2).
"""

from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_message
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsCustomer, get_request_customer
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.parking.selectors.reservations import (
    get_reservation_by_id,
    get_reservations_queryset,
)
from apps.parking.selectors.slots import get_slots_queryset
from apps.parking.serializers.reservations import (
    CustomerSlotItemSerializer,
    SlotReservationCreateSerializer,
    SlotReservationSerializer,
)
from apps.parking.serializers.slots import SlotFilterSerializer
from apps.parking.services.reservations import (
    cancel_slot_reservation,
    create_slot_reservation,
)
from apps.parking.views.structure import (
    StructureFloorSerializer,
    build_parking_structure_data,
)


class SlotReserveView(APIView):
    """
    POST /api/v1/parking/slots/<int:pk>/reserve/
    Allow CUSTOMER (for own vehicle), EMPLOYEE, or MANAGER to reserve a slot.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="parking_slots_reserve",
        tags=["Parking - Reservations"],
        summary="Đăng ký đặt chỗ ô đỗ xe",
        request=SlotReservationCreateSerializer,
        responses={
            201: OpenApiResponse(response=SlotReservationSerializer),
            400: OpenApiResponse(response=ErrorEnvelopeSerializer),
            403: OpenApiResponse(response=ErrorEnvelopeSerializer),
            404: OpenApiResponse(response=ErrorEnvelopeSerializer),
            409: OpenApiResponse(response=ErrorEnvelopeSerializer),
        },
    )
    def post(self, request: Request, pk: int) -> Response:
        serializer = SlotReservationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        reservation = create_slot_reservation(
            slot_id=pk,
            data=serializer.validated_data,
            actor_user=request.user,
        )
        hydrated = get_reservation_by_id(reservation.id) or reservation
        return Response(
            SlotReservationSerializer(hydrated).data,
            status=status.HTTP_201_CREATED,
        )


class SlotReservationListView(APIView):
    """
    GET /api/v1/parking/reservations/
    EMPLOYEE/MANAGER see all reservations; CUSTOMER sees only their own reservations.
    """

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        operation_id="parking_reservations_list",
        tags=["Parking - Reservations"],
        summary="Danh sách đặt chỗ ô đỗ xe",
        parameters=[
            OpenApiParameter(name="slot_id", type=int, location=OpenApiParameter.QUERY),
            OpenApiParameter(name="status", type=str, location=OpenApiParameter.QUERY),
        ],
        responses={200: SlotReservationSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        role = getattr(request.user, "role", None)
        customer_id: int | None = None

        if role == "CUSTOMER":
            customer = get_request_customer(request)
            if customer is None:
                raise BusinessAPIException(
                    code="MSG-4.2-M01",
                    message=get_message(
                        "MSG-4.2-M01", "Bạn không có quyền thực hiện thao tác này."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            customer_id = customer.id
        elif role not in ("EMPLOYEE", "MANAGER"):
            raise BusinessAPIException(
                code="MSG-4.2-M01",
                message=get_message(
                    "MSG-4.2-M01", "Bạn không có quyền thực hiện thao tác này."
                ),
                status_code=status.HTTP_403_FORBIDDEN,
            )

        raw_slot_id = request.query_params.get("slot_id")
        slot_id = (
            int(raw_slot_id) if raw_slot_id and str(raw_slot_id).isdigit() else None
        )
        status_filter = request.query_params.get("status")

        qs = get_reservations_queryset(
            customer_id=customer_id,
            slot_id=slot_id,
            status_filter=status_filter,
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        if page is not None:
            return paginator.get_paginated_response(
                SlotReservationSerializer(page, many=True).data
            )
        return Response(
            SlotReservationSerializer(qs, many=True).data,
            status=status.HTTP_200_OK,
        )


class SlotReservationCancelView(APIView):
    """
    POST /api/v1/parking/reservations/<int:pk>/cancel/
    Cancel an active reservation (CUSTOMER own only; EMPLOYEE/MANAGER any).
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="parking_reservations_cancel",
        tags=["Parking - Reservations"],
        summary="Hủy đặt chỗ ô đỗ xe",
        request=None,
        responses={
            200: OpenApiResponse(response=SlotReservationSerializer),
            403: OpenApiResponse(response=ErrorEnvelopeSerializer),
            404: OpenApiResponse(response=ErrorEnvelopeSerializer),
            409: OpenApiResponse(response=ErrorEnvelopeSerializer),
        },
    )
    def post(self, request: Request, pk: int) -> Response:
        reservation = cancel_slot_reservation(
            reservation_id=pk,
            actor_user=request.user,
        )
        hydrated = get_reservation_by_id(reservation.id) or reservation
        return Response(
            SlotReservationSerializer(hydrated).data,
            status=status.HTTP_200_OK,
        )


class MeParkingStructureView(APIView):
    """GET /api/v1/me/parking-structure/ — Sơ đồ phân cấp bãi xe cho Customer."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_parking_structure_list",
        tags=["Customer Self-Service"],
        summary="Sơ đồ cấu trúc bãi đỗ xe cho khách hàng",
        responses={200: StructureFloorSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        return Response(build_parking_structure_data(), status=status.HTTP_200_OK)


class MeParkingSlotsView(APIView):
    """GET /api/v1/me/parking-slots/ — Danh sách ô đỗ ẩn PII của khách khác cho Customer."""

    permission_classes = [IsAuthenticated, IsCustomer]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        operation_id="me_parking_slots_list",
        tags=["Customer Self-Service"],
        summary="Danh sách ô đỗ xe (ẩn thông tin cá nhân khách khác)",
        responses={200: CustomerSlotItemSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        customer = get_request_customer(request)
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

        context = {"customer_id": customer.id if customer else None}
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        if page is not None:
            serializer = CustomerSlotItemSerializer(page, many=True, context=context)
            return paginator.get_paginated_response(serializer.data)

        serializer = CustomerSlotItemSerializer(qs, many=True, context=context)
        return Response(serializer.data, status=status.HTTP_200_OK)
