"""
Serializers for VNPAY wallet top-up endpoints (ADR-0013).
"""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers, status

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_message

_INT_STRING_PATTERN = re.compile(r"^[+-]?\d+$")
VNPAY_TOPUP_STATUS_CHOICES = [("CREDITED", "CREDITED"), ("PENDING", "PENDING")]


@extend_schema_serializer(component_name="VnpayTopupCreateRequest")
class VnpayTopupCreateSerializer(serializers.Serializer):
    """Request payload for initiating a VNPAY wallet top-up."""

    amount = serializers.JSONField(allow_null=True)
    locale = serializers.ChoiceField(
        choices=[("vn", "Tiếng Việt"), ("en", "English")],
        default="vn",
        required=False,
    )
    bank_code = serializers.ChoiceField(
        choices=[("VNPAYQR", "VNPAYQR"), ("VNBANK", "VNBANK"), ("INTCARD", "INTCARD")],
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    order_info = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    def validate_amount(self, value: Any) -> int:
        min_vnd = int(getattr(settings, "VNPAY_TOPUP_MIN", 10000))
        max_vnd = int(getattr(settings, "VNPAY_TOPUP_MAX", 50000000))

        parsed_int: int | None = None
        if isinstance(value, bool):
            parsed_int = None
        elif isinstance(value, int):
            parsed_int = value
        elif isinstance(value, str):
            stripped = value.strip()
            if _INT_STRING_PATTERN.fullmatch(stripped):
                parsed_int = int(stripped)

        if parsed_int is None or parsed_int < min_vnd or parsed_int > max_vnd:
            raise BusinessAPIException(
                code="PROP-VNPAY-AMOUNT-RANGE",
                message=get_message("PROP-VNPAY-AMOUNT-RANGE"),
                status_code=status.HTTP_400_BAD_REQUEST,
                details={"min": min_vnd, "max": max_vnd},
            )
        return parsed_int


@extend_schema_serializer(component_name="VnpayTopupCreateResponse")
class VnpayTopupCreateResponseSerializer(serializers.Serializer):
    """Response payload containing the signed VNPAY payment URL."""

    payment_url = serializers.CharField()
    txn_ref = serializers.CharField()
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    expires_at = serializers.DateTimeField()
    is_sandbox = serializers.BooleanField()


@extend_schema_serializer(component_name="VnpayTopupStatusResponse")
class VnpayTopupStatusResponseSerializer(serializers.Serializer):
    """Polling response indicating whether a VNPAY top-up has been credited via IPN."""

    txn_ref = serializers.CharField()
    status = serializers.ChoiceField(choices=VNPAY_TOPUP_STATUS_CHOICES)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2)
    balance = serializers.DecimalField(max_digits=14, decimal_places=2)
    wallet_transaction_id = serializers.IntegerField(allow_null=True)
    credited_at = serializers.DateTimeField(allow_null=True)


@extend_schema_serializer(component_name="VnpayIpnResponse")
class VnpayIpnResponseSerializer(serializers.Serializer):
    """Standard VNPAY v2.1.0 IPN acknowledgement JSON body."""

    RspCode = serializers.CharField()
    Message = serializers.CharField()
