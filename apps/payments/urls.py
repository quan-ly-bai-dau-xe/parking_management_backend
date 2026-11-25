"""
URL configuration for VNPAY payment gateway endpoints (ADR-0013).
"""

from django.urls import path

from apps.payments.views.vnpay import (
    MeVnpayTopupCreateView,
    MeVnpayTopupStatusView,
    VnpayIpnView,
    VnpayReturnView,
)

app_name = "payments"

urlpatterns = [
    path(
        "me/wallet/topups/vnpay/",
        MeVnpayTopupCreateView.as_view(),
        name="me-wallet-topups-vnpay",
    ),
    path(
        "me/wallet/topups/vnpay/<str:txn_ref>/",
        MeVnpayTopupStatusView.as_view(),
        name="me-wallet-topups-vnpay-status",
    ),
    path(
        "payments/vnpay/ipn/",
        VnpayIpnView.as_view(),
        name="vnpay-ipn",
    ),
    path(
        "payments/vnpay/return/",
        VnpayReturnView.as_view(),
        name="vnpay-return",
    ),
]
