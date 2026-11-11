"""
Views for tickets app.
Provides TicketType list, Ticket list, create, detail, and renew endpoints.
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsEmployeeOrManager
from apps.customers.models import Customer
from apps.parking.models import ParkingSlot
from apps.tickets.models import Ticket, TicketRenewal, TicketType
from apps.tickets.serializers import (
    TicketCreateSerializer,
    TicketDetailSerializer,
    TicketListSerializer,
    TicketRenewSerializer,
    TicketTypeSerializer,
)
from apps.vehicles.models import Vehicle


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
    """API Danh sách vé & Đăng ký vé mới."""

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        operation_id="tickets_list",
        tags=["Tickets"],
        summary="Lấy danh sách vé đỗ xe phân trang",
        responses={200: TicketListSerializer(many=True)},
    )
    def get(self, request: Request) -> Response:
        queryset = (
            Ticket.objects.filter(deleted_at__isnull=True)
            .select_related(
                "ticket_type",
                "customer",
                "vehicle",
                "vehicle__vehicle_type",
                "slot",
                "slot__zone",
                "slot__zone__floor",
            )
            .order_by("-id")
        )

        search_query = request.query_params.get("q", "").strip()
        if search_query:
            queryset = queryset.filter(
                Q(code__icontains=search_query)
                | Q(customer__full_name__icontains=search_query)
                | Q(customer__phone__icontains=search_query)
                | Q(customer__code__icontains=search_query)
                | Q(vehicle__license_plate__icontains=search_query)
            )

        status_param = request.query_params.get("status", "").strip().upper()
        if status_param and status_param != "ALL":
            queryset = queryset.filter(status=status_param)

        ticket_type_param = request.query_params.get("ticket_type", "").strip()
        if ticket_type_param and ticket_type_param != "ALL":
            if ticket_type_param.isdigit():
                queryset = queryset.filter(ticket_type_id=int(ticket_type_param))
            else:
                queryset = queryset.filter(ticket_type__code=ticket_type_param)

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
        data = serializer.validated_data

        ticket_type = TicketType.objects.filter(
            id=data["ticket_type_id"], deleted_at__isnull=True
        ).first()
        if not ticket_type:
            return Response(
                {"detail": "Loại vé không tồn tại hoặc đã bị xóa."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Tìm Customer
        customer = None
        if data.get("customer_id"):
            customer = Customer.objects.filter(
                id=data["customer_id"], deleted_at__isnull=True
            ).first()
        elif data.get("customer_code"):
            customer = Customer.objects.filter(
                code=data["customer_code"].strip(), deleted_at__isnull=True
            ).first()

        if not customer:
            return Response(
                {"detail": "Khách hàng không tồn tại."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Tìm Vehicle
        vehicle = None
        if data.get("vehicle_id"):
            vehicle = Vehicle.objects.filter(
                id=data["vehicle_id"], deleted_at__isnull=True
            ).first()
        elif data.get("license_plate"):
            vehicle = Vehicle.objects.filter(
                license_plate=data["license_plate"].strip(), deleted_at__isnull=True
            ).first()

        if not vehicle:
            return Response(
                {"detail": "Phương tiện không tồn tại."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Slot (nếu có)
        slot = None
        if data.get("slot_id"):
            slot = ParkingSlot.objects.filter(
                id=data["slot_id"], deleted_at__isnull=True
            ).first()

        now = timezone.now()
        effective_from = data.get("effective_from") or now
        duration_days = ticket_type.duration_days or 30
        effective_to = data.get("effective_to") or (
            effective_from + timedelta(days=duration_days)
        )
        price = data.get("price") or ticket_type.default_price or 0

        # Sinh mã vé VT%04d
        last_ticket = Ticket.objects.order_by("-id").first()
        next_num = (last_ticket.id + 1) if last_ticket else 1
        ticket_code = f"VT{next_num:04d}"

        employee = getattr(request.user, "employee_profile", None)

        ticket = Ticket.objects.create(
            code=ticket_code,
            ticket_type=ticket_type,
            customer=customer,
            vehicle=vehicle,
            slot=slot,
            issued_by=employee,
            price=price,
            effective_from=effective_from,
            effective_to=effective_to,
            status="ACTIVE",
            notes=data.get("notes", ""),
        )

        res_serializer = TicketDetailSerializer(ticket)
        return Response(res_serializer.data, status=status.HTTP_201_CREATED)


class TicketDetailView(APIView):
    """API Chi tiết & Hủy vé đỗ xe."""

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    def get(self, request: Request, id: int) -> Response:
        ticket = (
            Ticket.objects.filter(id=id, deleted_at__isnull=True)
            .select_related(
                "ticket_type",
                "customer",
                "vehicle",
                "vehicle__vehicle_type",
                "slot",
                "slot__zone",
                "slot__zone__floor",
            )
            .first()
        )
        if not ticket:
            return Response(
                {"detail": "Không tìm thấy vé đỗ xe."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = TicketDetailSerializer(ticket)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request: Request, id: int) -> Response:
        ticket = Ticket.objects.filter(id=id, deleted_at__isnull=True).first()
        if not ticket:
            return Response(
                {"detail": "Không tìm thấy vé đỗ xe."},
                status=status.HTTP_404_NOT_FOUND,
            )
        ticket.status = "TERMINATED"
        ticket.soft_delete()
        return Response(
            {"detail": f"Đã hủy vé đỗ xe {ticket.code} thành công."},
            status=status.HTTP_200_OK,
        )


class TicketRenewView(APIView):
    """API Gia hạn vé đỗ xe."""

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    def post(self, request: Request, id: int) -> Response:
        ticket = Ticket.objects.filter(id=id, deleted_at__isnull=True).first()
        if not ticket:
            return Response(
                {"detail": "Không tìm thấy vé đỗ xe để gia hạn."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = TicketRenewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        old_effective_to = ticket.effective_to
        extend_days = data.get("extend_days", 30)
        new_effective_to = max(old_effective_to, timezone.now()) + timedelta(
            days=extend_days
        )

        old_type = ticket.ticket_type
        new_type = old_type
        if data.get("ticket_type_id"):
            found_type = TicketType.objects.filter(
                id=data["ticket_type_id"], deleted_at__isnull=True
            ).first()
            if found_type:
                new_type = found_type

        old_slot = ticket.slot
        new_slot = old_slot
        if data.get("new_slot_id"):
            found_slot = ParkingSlot.objects.filter(
                id=data["new_slot_id"], deleted_at__isnull=True
            ).first()
            if found_slot:
                new_slot = found_slot

        employee = getattr(request.user, "employee_profile", None)

        TicketRenewal.objects.create(
            ticket=ticket,
            old_slot=old_slot,
            new_slot=new_slot,
            old_ticket_type=old_type,
            new_ticket_type=new_type,
            old_price=ticket.price,
            new_price=ticket.price + data.get("additional_price", 0),
            old_effective_to=old_effective_to,
            new_effective_to=new_effective_to,
            additional_price=data.get("additional_price", 0),
            notes=data.get("notes", ""),
            renewed_by=employee,
        )

        ticket.effective_to = new_effective_to
        ticket.ticket_type = new_type
        ticket.slot = new_slot
        ticket.status = "ACTIVE"
        ticket.save()

        res_serializer = TicketDetailSerializer(ticket)
        return Response(res_serializer.data, status=status.HTTP_200_OK)
