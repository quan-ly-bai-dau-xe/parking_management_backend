from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessAPIException
from apps.core.permissions import IsEmployeeOrManager
from apps.customers.models import Customer
from apps.customers.serializers.wallet import (
    CustomerWalletDetailSerializer,
    WalletDeductRequestSerializer,
    WalletDepositRequestSerializer,
)
from apps.customers.services.wallet import (
    deduct_from_wallet,
    deposit_to_wallet,
    get_or_create_customer_wallet,
)


class CustomerWalletDetailView(APIView):
    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        summary="Xem chi tiết ví khách hàng",
        responses={200: CustomerWalletDetailSerializer},
    )
    def get(self, request: Request, customer_id: int) -> Response:
        customer = Customer.objects.filter(
            id=customer_id, deleted_at__isnull=True
        ).first()
        if not customer:
            raise BusinessAPIException(
                code="PROP-CUSTOMER-NOT-FOUND",
                message="Không tìm thấy khách hàng.",
                status_code=404,
            )

        wallet = get_or_create_customer_wallet(customer)
        serializer = CustomerWalletDetailSerializer(wallet)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CustomerWalletDepositView(APIView):
    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        summary="Nạp tiền vào ví khách hàng",
        request=WalletDepositRequestSerializer,
    )
    def post(self, request: Request, customer_id: int) -> Response:
        serializer = WalletDepositRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = deposit_to_wallet(
            customer_id=customer_id,
            amount=data["amount"],
            description=data.get("description"),
            reference_code=data.get("reference_code"),
        )
        return Response(result, status=status.HTTP_200_OK)


class CustomerWalletDeductView(APIView):
    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        summary="Trừ tiền từ ví khách hàng",
        request=WalletDeductRequestSerializer,
    )
    def post(self, request: Request, customer_id: int) -> Response:
        serializer = WalletDeductRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = deduct_from_wallet(
            customer_id=customer_id,
            amount=data["amount"],
            session_id=data.get("session_id"),
            description=data.get("description"),
            reference_code=data.get("reference_code"),
        )
        return Response(result, status=status.HTTP_200_OK)
