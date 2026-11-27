"""
Wallet views for both Customer Self-Service (/api/v1/me/wallet/*)
and Staff/Manager operations (/api/v1/customers/{id}/wallet/*).
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
from apps.core.permissions import IsCustomer, IsEmployeeOrManager, get_request_customer
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.customers.models import Customer
from apps.wallet.selectors.wallet import (
    get_wallet_by_customer_id,
    get_wallet_transactions_queryset,
)
from apps.wallet.serializers.wallet import (
    MeWalletDetailSerializer,
    StaffTopupResponseSerializer,
    StaffTopupSerializer,
    TopupRequestSerializer,
    WalletSerializer,
    WalletTopupResponseSerializer,
    WalletTransactionSerializer,
)
from apps.wallet.services.wallet import (
    ensure_wallet_for_customer,
    simulated_vietqr_topup,
    staff_topup_wallet,
)


class MeWalletDetailView(APIView):
    """GET /api/v1/me/wallet/ — Lấy thông tin ví của khách hàng đang đăng nhập."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_wallet_retrieve",
        tags=["Customer Self-Service"],
        summary="Xem thông tin ví điện tử cá nhân",
        responses={
            200: MeWalletDetailSerializer,
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Chưa đăng nhập"
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không phải tài khoản khách hàng",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        customer = get_request_customer(request)
        wallet = ensure_wallet_for_customer(customer.id)
        wallet = get_wallet_by_customer_id(customer.id)
        serializer = MeWalletDetailSerializer(wallet)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MeWalletTransactionListView(APIView):
    """GET /api/v1/me/wallet/transactions/ — Sổ cái giao dịch ví phân trang."""

    permission_classes = [IsAuthenticated, IsCustomer]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        operation_id="me_wallet_transactions_list",
        tags=["Customer Self-Service"],
        summary="Lấy lịch sử giao dịch ví cá nhân",
        parameters=[
            OpenApiParameter(name="kind", type=str, location=OpenApiParameter.QUERY),
            OpenApiParameter(
                name="direction",
                type=str,
                location=OpenApiParameter.QUERY,
                description="Lọc hướng giao dịch: CREDIT/deposit hoặc DEBIT/payment",
            ),
        ],
        responses={
            200: WalletTransactionSerializer(many=True),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Chưa đăng nhập"
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không phải tài khoản khách hàng",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        customer = get_request_customer(request)
        wallet = ensure_wallet_for_customer(customer.id)
        kind = request.query_params.get("kind")
        direction = request.query_params.get("direction")

        qs = get_wallet_transactions_queryset(
            wallet_id=wallet.id,
            kind=kind,
            direction=direction,
        )
        paginator = self.pagination_class()
        paginated = paginator.paginate_queryset(qs, request)
        serializer = WalletTransactionSerializer(paginated, many=True)
        return paginator.get_paginated_response(serializer.data)


class MeWalletTopupView(APIView):
    """POST /api/v1/me/wallet/topups/ — Nạp tiền ví qua cổng VietQR giả lập."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_wallet_topups_create",
        tags=["Customer Self-Service"],
        summary="Nạp tiền ví qua VietQR giả lập",
        request=TopupRequestSerializer,
        responses={
            201: WalletTopupResponseSerializer,
            200: WalletTopupResponseSerializer,
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Số tiền hoặc khóa không hợp lệ",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Tính năng nạp tiền giả lập đang tắt",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Ví bị khóa hoặc xung đột idempotency",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        customer = get_request_customer(request)
        req_serializer = TopupRequestSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)

        wallet, tx, created = simulated_vietqr_topup(
            customer_id=customer.id,
            amount=req_serializer.validated_data["amount"],
            idempotency_key=req_serializer.validated_data["idempotency_key"],
            actor_id=request.user.id,
            note=req_serializer.validated_data.get("note"),
        )
        wallet = get_wallet_by_customer_id(customer.id)

        payload = {
            "wallet": WalletSerializer(wallet).data,
            "transaction": WalletTransactionSerializer(tx).data,
            "replayed": not created,
            "simulated_qr": {
                "is_simulated": True,
                "disclaimer": "Cổng nạp tiền VietQR giả lập phục vụ môi trường kiểm thử. Không phát sinh trừ tiền ngân hàng thật.",
                "qr_payload": f"VIETQR|SIMULATED|{customer.code}|{int(tx.amount)}|{tx.idempotency_key}",
            },
        }
        return Response(
            payload,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class StaffCustomerWalletDetailView(APIView):
    """GET /api/v1/customers/{id}/wallet/ — Nhân viên/Quản lý xem số dư ví của khách hàng."""

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="customers_wallet_retrieve",
        tags=["Customers - Wallet"],
        summary="Xem thông tin ví khách hàng (Nhân viên / Quản lý)",
        responses={
            200: WalletSerializer,
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không tìm thấy khách hàng hoặc ví",
            ),
        },
    )
    def get(self, request: Request, id: int) -> Response:
        customer = Customer.objects.filter(id=id, deleted_at__isnull=True).first()
        if not customer:
            raise BusinessAPIException(
                code="PROP-4.4.4-P02",
                message=get_message("PROP-4.4.4-P02"),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        ensure_wallet_for_customer(customer.id)
        wallet = get_wallet_by_customer_id(customer.id)
        return Response(WalletSerializer(wallet).data, status=status.HTTP_200_OK)


class StaffCustomerWalletTransactionListView(APIView):
    """GET /api/v1/customers/{id}/wallet/transactions/ — Nhân viên/Quản lý xem lịch sử ví khách hàng."""

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        operation_id="customers_wallet_transactions_list",
        tags=["Customers - Wallet"],
        summary="Xem lịch sử giao dịch ví khách hàng (Nhân viên / Quản lý)",
        parameters=[
            OpenApiParameter(name="kind", type=str, location=OpenApiParameter.QUERY),
            OpenApiParameter(
                name="direction", type=str, location=OpenApiParameter.QUERY
            ),
        ],
        responses={
            200: WalletTransactionSerializer(many=True),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không tìm thấy khách hàng",
            ),
        },
    )
    def get(self, request: Request, id: int) -> Response:
        customer = Customer.objects.filter(id=id, deleted_at__isnull=True).first()
        if not customer:
            raise BusinessAPIException(
                code="PROP-4.4.4-P02",
                message=get_message("PROP-4.4.4-P02"),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        wallet = ensure_wallet_for_customer(customer.id)
        qs = get_wallet_transactions_queryset(
            wallet_id=wallet.id,
            kind=request.query_params.get("kind"),
            direction=request.query_params.get("direction"),
        )
        paginator = self.pagination_class()
        paginated = paginator.paginate_queryset(qs, request)
        serializer = WalletTransactionSerializer(paginated, many=True)
        return paginator.get_paginated_response(serializer.data)


class StaffCustomerWalletTopupView(APIView):
    """POST /api/v1/customers/{id}/wallet/topup/ — Nhân viên/Quản lý nạp tiền mặt tại quầy."""

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="customers_wallet_topup_create",
        tags=["Customers - Wallet"],
        summary="Nạp tiền mặt vào ví khách hàng tại quầy",
        request=StaffTopupSerializer,
        responses={
            201: StaffTopupResponseSerializer,
            200: StaffTopupResponseSerializer,
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Dữ liệu không hợp lệ"
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Không đủ quyền"
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không tìm thấy khách hàng",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Ví bị khóa hoặc xung đột idempotency",
            ),
        },
    )
    def post(self, request: Request, id: int) -> Response:
        req_serializer = StaffTopupSerializer(data=request.data)
        req_serializer.is_valid(raise_exception=True)

        wallet, tx, created = staff_topup_wallet(
            customer_id=id,
            amount=req_serializer.validated_data["amount"],
            payment_method=req_serializer.validated_data.get("payment_method", "CASH"),
            note=req_serializer.validated_data.get("note"),
            idempotency_key=req_serializer.validated_data.get("idempotency_key"),
            actor_id=request.user.id,
        )
        wallet = get_wallet_by_customer_id(id)

        payload = {
            "wallet": WalletSerializer(wallet).data,
            "transaction": WalletTransactionSerializer(tx).data,
            "replayed": not created,
        }
        return Response(
            payload,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
