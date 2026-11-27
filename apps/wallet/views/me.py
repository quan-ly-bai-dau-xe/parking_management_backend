"""
Customer Self-Service views (/api/v1/me/) for profile, vehicles, tickets, and reference types.
Strictly scoped to the authenticated CUSTOMER account's own Customer record via IsCustomer.
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
from apps.customers.models import Customer
from apps.tickets.models import TicketType
from apps.tickets.serializers.tickets import TicketTypeSerializer
from apps.vehicles.selectors.types import get_vehicle_types
from apps.vehicles.selectors.vehicles import get_vehicle_by_id
from apps.vehicles.serializers.types import VehicleTypeSerializer
from apps.vehicles.serializers.vehicles import (
    VehicleDeleteSuccessSerializer,
    VehicleDetailSerializer,
)
from apps.wallet.selectors.wallet import (
    get_me_notifications_queryset,
    get_me_tickets_queryset,
    get_me_unread_notifications_count,
    get_me_vehicles_queryset,
)
from apps.wallet.serializers.me import (
    MeNotificationListResponseSerializer,
    MeNotificationMarkAllReadResponseSerializer,
    MeNotificationMarkReadResponseSerializer,
    MeNotificationSerializer,
    MeProfileSerializer,
    MeProfileUpdateSerializer,
    MeTicketCancelResponseSerializer,
    MeTicketPurchaseResponseSerializer,
    MeTicketPurchaseSerializer,
    MeTicketSerializer,
    MeVehicleCreateSerializer,
    MeVehicleListSerializer,
    MeVehicleUpdateSerializer,
)
from apps.wallet.serializers.wallet import WalletTransactionSerializer
from apps.wallet.services.self_service import (
    _resolve_customer_vehicle,
    cancel_my_ticket,
    create_my_vehicle,
    delete_my_vehicle,
    mark_all_my_notifications_read,
    mark_my_notification_read,
    purchase_ticket_with_wallet,
    update_my_profile,
    update_my_vehicle,
)
from apps.wallet.services.wallet import ensure_wallet_for_customer


class MeProfileView(APIView):
    """GET / PATCH /api/v1/me/profile/ — Hồ sơ cá nhân khách hàng kèm số dư ví thực."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_profile_retrieve",
        tags=["Customer Self-Service"],
        summary="Xem hồ sơ khách hàng cá nhân",
        responses={200: MeProfileSerializer},
    )
    def get(self, request: Request) -> Response:
        customer = get_request_customer(request)
        customer_hydrated = (
            Customer.objects.select_related("province", "district", "ward")
            .filter(id=customer.id, deleted_at__isnull=True)
            .first()
        )
        wallet = ensure_wallet_for_customer(customer.id)
        serializer = MeProfileSerializer(
            customer_hydrated or customer,
            context={"wallet": wallet},
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="me_profile_partial_update",
        tags=["Customer Self-Service"],
        summary="Cập nhật hồ sơ khách hàng cá nhân (OCC row_version)",
        request=MeProfileUpdateSerializer,
        responses={
            200: MeProfileSerializer,
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Dữ liệu không hợp lệ"
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Xung đột row_version hoặc trùng email/CCCD",
            ),
        },
    )
    def patch(self, request: Request) -> Response:
        customer = get_request_customer(request)
        req_serializer = MeProfileUpdateSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)

        updated = update_my_profile(
            customer=customer, data=req_serializer.validated_data
        )
        hydrated = (
            Customer.objects.select_related("province", "district", "ward")
            .filter(id=updated.id, deleted_at__isnull=True)
            .first()
        )
        wallet = ensure_wallet_for_customer(customer.id)
        return Response(
            MeProfileSerializer(hydrated or updated, context={"wallet": wallet}).data,
            status=status.HTTP_200_OK,
        )


class MeVehicleListCreateView(APIView):
    """GET / POST /api/v1/me/vehicles/ — Danh sách & đăng ký xe cá nhân."""

    permission_classes = [IsAuthenticated, IsCustomer]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        operation_id="me_vehicles_list",
        tags=["Customer Self-Service"],
        summary="Danh sách phương tiện của tôi",
        responses={200: MeVehicleListSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        customer = get_request_customer(request)
        qs = get_me_vehicles_queryset(customer.id)
        paginator = self.pagination_class()
        paginated = paginator.paginate_queryset(qs, request)
        if paginated is not None:
            for idx, item in enumerate(paginated):
                item._row_index = idx  # type: ignore[attr-defined]
            serializer = MeVehicleListSerializer(
                paginated, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)
        serializer = MeVehicleListSerializer(
            qs, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="me_vehicles_create",
        tags=["Customer Self-Service"],
        summary="Đăng ký phương tiện mới cho tài khoản cá nhân",
        request=MeVehicleCreateSerializer,
        responses={
            201: VehicleDetailSerializer,
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Dữ liệu không hợp lệ"
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Biển số đã tồn tại"
            ),
        },
    )
    def post(self, request: Request) -> Response:
        customer = get_request_customer(request)
        req_serializer = MeVehicleCreateSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)

        vehicle = create_my_vehicle(
            customer=customer,
            data=req_serializer.validated_data,
            actor_id=request.user.id,
        )
        detail = get_vehicle_by_id(vehicle.id)
        return Response(
            VehicleDetailSerializer(detail).data,
            status=status.HTTP_201_CREATED,
        )


class MeVehicleDetailView(APIView):
    """GET / PATCH / DELETE /api/v1/me/vehicles/{lookup}/ — Chi tiết, sửa & xóa xe cá nhân."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_vehicles_retrieve",
        tags=["Customer Self-Service"],
        summary="Xem chi tiết phương tiện của tôi (ID hoặc mã xe)",
        responses={
            200: VehicleDetailSerializer,
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không tìm thấy phương tiện",
            ),
        },
    )
    def get(self, request: Request, lookup: str) -> Response:
        customer = get_request_customer(request)
        vehicle = _resolve_customer_vehicle(customer.id, lookup)
        detail = get_vehicle_by_id(vehicle.id)
        return Response(VehicleDetailSerializer(detail).data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="me_vehicles_partial_update",
        tags=["Customer Self-Service"],
        summary="Cập nhật thông tin phương tiện của tôi",
        request=MeVehicleUpdateSerializer,
        responses={
            200: VehicleDetailSerializer,
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không tìm thấy phương tiện",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Xung đột row_version"
            ),
        },
    )
    def patch(self, request: Request, lookup: str) -> Response:
        customer = get_request_customer(request)
        req_serializer = MeVehicleUpdateSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)

        updated = update_my_vehicle(
            customer=customer,
            lookup=lookup,
            data=req_serializer.validated_data,
            actor_id=request.user.id,
        )
        detail = get_vehicle_by_id(updated.id)
        return Response(VehicleDetailSerializer(detail).data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="me_vehicles_destroy",
        tags=["Customer Self-Service"],
        summary="Xóa phương tiện của tôi (chặn nếu đang có vé hiệu lực / đang đỗ / đặt chỗ)",
        responses={
            200: VehicleDeleteSuccessSerializer,
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không tìm thấy phương tiện",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Xe đang có vé hoạt động hoặc đang đỗ (DEL-03 / R3c)",
            ),
        },
    )
    def delete(self, request: Request, lookup: str) -> Response:
        customer = get_request_customer(request)
        result = delete_my_vehicle(
            customer=customer,
            lookup=lookup,
            actor_id=request.user.id,
        )
        return Response(result, status=status.HTTP_200_OK)


class MeTicketListCreateView(APIView):
    """GET / POST /api/v1/me/tickets/ — Danh sách vé & mua vé trực tiếp bằng ví."""

    permission_classes = [IsAuthenticated, IsCustomer]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        operation_id="me_tickets_list",
        tags=["Customer Self-Service"],
        summary="Danh sách vé đỗ xe của tôi",
        parameters=[
            OpenApiParameter(name="status", type=str, location=OpenApiParameter.QUERY),
        ],
        responses={200: MeTicketSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        customer = get_request_customer(request)
        qs = get_me_tickets_queryset(
            customer_id=customer.id,
            status_filter=request.query_params.get("status"),
        )
        paginator = self.pagination_class()
        paginated = paginator.paginate_queryset(qs, request)
        serializer = MeTicketSerializer(paginated, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        operation_id="me_tickets_create",
        tags=["Customer Self-Service"],
        summary="Mua vé đỗ xe mới bằng số dư ví",
        request=MeTicketPurchaseSerializer,
        responses={
            201: MeTicketPurchaseResponseSerializer,
            200: MeTicketPurchaseResponseSerializer,
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Dữ liệu không hợp lệ"
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Không tìm thấy xe"
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Số dư ví không đủ hoặc xung đột vé/vị trí",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        customer = get_request_customer(request)
        req_serializer = MeTicketPurchaseSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)
        vdata = req_serializer.validated_data

        vehicle_lookup = vdata.get("vehicle_id") or vdata.get("vehicle_code")
        ticket_type_lookup = vdata.get("ticket_type_id") or vdata.get(
            "ticket_type_code"
        )

        ticket, tx, created = purchase_ticket_with_wallet(
            customer=customer,
            vehicle_lookup=vehicle_lookup,
            ticket_type_lookup=ticket_type_lookup,
            idempotency_key=vdata["idempotency_key"],
            slot_id=vdata.get("slot_id"),
            effective_from=vdata.get("effective_from"),
            notes=vdata.get("notes"),
            actor_id=request.user.id,
        )

        payload = {
            "ticket": MeTicketSerializer(ticket).data,
            "transaction": WalletTransactionSerializer(tx).data,
            "replayed": not created,
        }
        return Response(
            payload,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MeTicketCancelView(APIView):
    """POST /api/v1/me/tickets/{lookup}/cancel/ — Yêu cầu hủy vé của khách hàng."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_tickets_cancel",
        tags=["Customer Self-Service"],
        summary="Yêu cầu hủy vé đỗ xe cá nhân",
        request=None,
        responses={
            200: MeTicketCancelResponseSerializer,
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Không tìm thấy vé"
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Vé đã thanh toán không được phép tự hủy (PROP-4.6.4-P06)",
            ),
        },
    )
    def post(self, request: Request, lookup: str) -> Response:
        customer = get_request_customer(request)
        ticket = cancel_my_ticket(customer=customer, lookup=lookup)
        hydrated = (
            get_me_tickets_queryset(customer.id).filter(id=ticket.id).first() or ticket
        )
        return Response(
            {
                "ticket": MeTicketSerializer(hydrated).data,
                "message": "Đã hủy vé thành công.",
            },
            status=status.HTTP_200_OK,
        )


class MeTicketTypeListView(APIView):
    """GET /api/v1/me/ticket-types/ — Danh mục loại vé và đơn giá niêm yết cho khách hàng."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_ticket_types_list",
        tags=["Customer Self-Service"],
        summary="Xem danh mục loại vé và giá niêm yết",
        responses={200: TicketTypeSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        queryset = TicketType.objects.filter(deleted_at__isnull=True).order_by("id")
        return Response(
            TicketTypeSerializer(queryset, many=True).data, status=status.HTTP_200_OK
        )


class MeVehicleTypeListView(APIView):
    """GET /api/v1/me/vehicle-types/ — Danh mục loại xe (CAR, EV) cho khách hàng."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_vehicle_types_list",
        tags=["Customer Self-Service"],
        summary="Xem danh mục loại phương tiện cho phép",
        responses={200: VehicleTypeSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        queryset = get_vehicle_types()
        return Response(
            VehicleTypeSerializer(queryset, many=True).data, status=status.HTTP_200_OK
        )


_VALID_NOTIFICATION_TYPES = {"SYSTEM", "TICKET_EXPIRY", "PAYMENT", "SECURITY"}


class MeNotificationListView(APIView):
    """GET /api/v1/me/notifications/ — Danh sách thông báo cá nhân có phân trang."""

    permission_classes = [IsAuthenticated, IsCustomer]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        operation_id="me_notifications_list",
        tags=["Customer Self-Service"],
        summary="Danh sách thông báo của tài khoản khách hàng",
        parameters=[
            OpenApiParameter(
                name="is_read",
                type=bool,
                location=OpenApiParameter.QUERY,
                description="Lọc trạng thái đã đọc (true/false)",
            ),
            OpenApiParameter(
                name="notification_type",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Lọc loại thông báo (SYSTEM, TICKET_EXPIRY, PAYMENT, SECURITY)",
            ),
        ],
        responses={
            200: MeNotificationListResponseSerializer,
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Tham số lọc không hợp lệ"
            ),
        },
    )
    def get(self, request: Request) -> Response:
        get_request_customer(request)
        account_id = request.user.pk
        assert isinstance(account_id, int)

        raw_is_read = request.query_params.get("is_read")
        is_read_filter: bool | None = None
        if raw_is_read is not None and str(raw_is_read).strip() != "":
            norm_read = str(raw_is_read).strip().lower()
            if norm_read in ("true", "1"):
                is_read_filter = True
            elif norm_read in ("false", "0"):
                is_read_filter = False
            else:
                raise BusinessAPIException(
                    code="PROP-GEN-P01",
                    message=get_message("PROP-GEN-P01"),
                    status_code=status.HTTP_400_BAD_REQUEST,
                    details={"is_read": ["Giá trị is_read phải là true hoặc false."]},
                )

        raw_type = request.query_params.get("notification_type")
        type_filter: str | None = None
        if raw_type is not None and str(raw_type).strip() != "":
            norm_type = str(raw_type).strip().upper()
            if norm_type not in _VALID_NOTIFICATION_TYPES:
                raise BusinessAPIException(
                    code="PROP-GEN-P01",
                    message=get_message("PROP-GEN-P01"),
                    status_code=status.HTTP_400_BAD_REQUEST,
                    details={
                        "notification_type": [
                            "Loại thông báo phải thuộc SYSTEM, TICKET_EXPIRY, PAYMENT hoặc SECURITY."
                        ]
                    },
                )
            type_filter = norm_type

        qs = get_me_notifications_queryset(
            account_id=account_id,
            is_read=is_read_filter,
            notification_type=type_filter,
        )
        paginator = self.pagination_class()
        paginated = paginator.paginate_queryset(qs, request)
        serializer = MeNotificationSerializer(paginated, many=True)
        resp = paginator.get_paginated_response(serializer.data)
        resp.data["unread_count"] = get_me_unread_notifications_count(account_id)
        return resp


class MeNotificationMarkReadView(APIView):
    """POST /api/v1/me/notifications/{id}/read/ — Đánh dấu một thông báo là đã đọc."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_notifications_mark_read",
        tags=["Customer Self-Service"],
        summary="Đánh dấu thông báo đã đọc",
        request=None,
        responses={
            200: MeNotificationMarkReadResponseSerializer,
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Không tìm thấy thông báo"
            ),
        },
    )
    def post(self, request: Request, id: int) -> Response:
        get_request_customer(request)
        account_id = request.user.pk
        assert isinstance(account_id, int)
        notif = mark_my_notification_read(account_id=account_id, notification_id=id)
        return Response(
            {
                "notification": MeNotificationSerializer(notif).data,
                "unread_count": get_me_unread_notifications_count(account_id),
            },
            status=status.HTTP_200_OK,
        )


class MeNotificationMarkAllReadView(APIView):
    """POST /api/v1/me/notifications/read-all/ — Đánh dấu toàn bộ thông báo là đã đọc."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_notifications_mark_all_read",
        tags=["Customer Self-Service"],
        summary="Đánh dấu tất cả thông báo đã đọc",
        request=None,
        responses={200: MeNotificationMarkAllReadResponseSerializer},
    )
    def post(self, request: Request) -> Response:
        get_request_customer(request)
        account_id = request.user.pk
        assert isinstance(account_id, int)
        updated_count = mark_all_my_notifications_read(account_id=account_id)
        return Response(
            {
                "updated_count": updated_count,
                "unread_count": 0,
            },
            status=status.HTTP_200_OK,
        )
