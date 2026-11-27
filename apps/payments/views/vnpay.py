"""
Thin API views for VNPAY wallet top-up, IPN callback, and browser return redirect.
"""

from __future__ import annotations

from django.http import HttpResponseRedirect, QueryDict
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services.throttling import get_client_ip
from apps.core.permissions import IsCustomer, get_request_customer
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.payments.selectors.topup import get_vnpay_topup_status
from apps.payments.serializers.vnpay import (
    VnpayIpnResponseSerializer,
    VnpayTopupCreateResponseSerializer,
    VnpayTopupCreateSerializer,
    VnpayTopupStatusResponseSerializer,
)
from apps.payments.services.throttling import VnpayTopupLimiter
from apps.payments.services.topup import (
    create_vnpay_topup_intent,
    process_vnpay_ipn,
    verify_vnpay_return,
)


class MeVnpayTopupCreateView(APIView):
    """POST /api/v1/me/wallet/topups/vnpay/ — Khởi tạo giao dịch nạp ví qua VNPAY Sandbox."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_wallet_topups_vnpay_create",
        tags=["Customer Self-Service"],
        summary="Tạo URL thanh toán VNPAY để nạp tiền vào ví cá nhân",
        request=VnpayTopupCreateSerializer,
        responses={
            201: VnpayTopupCreateResponseSerializer,
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Số tiền không hợp lệ hoặc ngoài giới hạn",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Chưa đăng nhập"
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không phải khách hàng hoặc tài khoản bị khóa",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Ví đang bị khóa"
            ),
            429: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Vượt giới hạn tần suất"
            ),
            503: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="VNPAY chưa được cấu hình"
            ),
        },
    )
    def post(self, request: Request) -> Response:
        customer = get_request_customer(request)
        serializer = VnpayTopupCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        VnpayTopupLimiter().check_and_increment(customer.id)
        client_ip = get_client_ip(request._request) or "127.0.0.1"
        return_fallback = request.build_absolute_uri("/api/v1/payments/vnpay/return/")

        result = create_vnpay_topup_intent(
            customer=customer,
            amount_vnd=serializer.validated_data["amount"],
            client_ip=client_ip,
            locale=serializer.validated_data.get("locale", "vn"),
            bank_code=serializer.validated_data.get("bank_code"),
            order_info=serializer.validated_data.get("order_info"),
            return_url_fallback=return_fallback,
        )
        out_serializer = VnpayTopupCreateResponseSerializer(result)
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class MeVnpayTopupStatusView(APIView):
    """GET /api/v1/me/wallet/topups/vnpay/{txn_ref}/ — Kiểm tra trạng thái ghi có ví của giao dịch VNPAY."""

    permission_classes = [IsAuthenticated, IsCustomer]

    @extend_schema(
        operation_id="me_wallet_topups_vnpay_retrieve",
        tags=["Customer Self-Service"],
        summary="Tra cứu trạng thái ghi có ví theo mã tham chiếu VNPAY",
        responses={
            200: VnpayTopupStatusResponseSerializer,
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="Chưa đăng nhập"
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không phải tài khoản khách hàng",
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Mã giao dịch không hợp lệ hoặc không thuộc khách hàng",
            ),
            503: OpenApiResponse(
                response=ErrorEnvelopeSerializer, description="VNPAY chưa được cấu hình"
            ),
        },
    )
    def get(self, request: Request, txn_ref: str) -> Response:
        customer = get_request_customer(request)
        payload = get_vnpay_topup_status(customer_id=customer.id, txn_ref=txn_ref)
        out_serializer = VnpayTopupStatusResponseSerializer(payload)
        return Response(out_serializer.data, status=status.HTTP_200_OK)


class VnpayIpnView(APIView):
    """GET /api/v1/payments/vnpay/ipn/ — Webhook IPN server-to-server từ cổng VNPAY."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="payments_vnpay_ipn_retrieve",
        tags=["Payments - VNPAY"],
        summary="VNPAY IPN callback (server-to-server)",
        parameters=[
            OpenApiParameter(
                name="vnp_TxnRef", type=str, location=OpenApiParameter.QUERY
            ),
            OpenApiParameter(
                name="vnp_Amount", type=str, location=OpenApiParameter.QUERY
            ),
            OpenApiParameter(
                name="vnp_ResponseCode", type=str, location=OpenApiParameter.QUERY
            ),
            OpenApiParameter(
                name="vnp_TransactionStatus", type=str, location=OpenApiParameter.QUERY
            ),
            OpenApiParameter(
                name="vnp_SecureHash", type=str, location=OpenApiParameter.QUERY
            ),
        ],
        responses={200: VnpayIpnResponseSerializer},
        auth=[],
    )
    def get(self, request: Request) -> Response:
        raw_qs = request.META.get("QUERY_STRING")
        query_source: str | QueryDict = (
            raw_qs
            if isinstance(raw_qs, str) and (raw_qs or not request.query_params)
            else request.query_params
        )
        rsp_code, message = process_vnpay_ipn(query_source)
        return Response(
            {"RspCode": rsp_code, "Message": message},
            status=status.HTTP_200_OK,
        )


class VnpayReturnView(APIView):
    """GET /api/v1/payments/vnpay/return/ — Điểm đón trình duyệt từ VNPAY, chỉ chuyển hướng hiển thị."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="payments_vnpay_return_retrieve",
        tags=["Payments - VNPAY"],
        summary="VNPAY browser return redirect (không ghi có ví)",
        parameters=[
            OpenApiParameter(
                name="vnp_TxnRef", type=str, location=OpenApiParameter.QUERY
            ),
            OpenApiParameter(
                name="vnp_ResponseCode", type=str, location=OpenApiParameter.QUERY
            ),
            OpenApiParameter(
                name="vnp_TransactionStatus", type=str, location=OpenApiParameter.QUERY
            ),
            OpenApiParameter(
                name="vnp_SecureHash", type=str, location=OpenApiParameter.QUERY
            ),
        ],
        responses={
            302: OpenApiResponse(
                description="Chuyển hướng về trang kết quả Frontend",
            )
        },
        auth=[],
    )
    def get(self, request: Request) -> HttpResponseRedirect:
        raw_qs = request.META.get("QUERY_STRING")
        query_source: str | QueryDict = (
            raw_qs
            if isinstance(raw_qs, str) and (raw_qs or not request.query_params)
            else request.query_params
        )
        redirect_url = verify_vnpay_return(query_source)
        return HttpResponseRedirect(redirect_url)
