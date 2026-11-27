"""
Serializers for customer wallet and ledger transactions.
"""

from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from drf_spectacular.utils import extend_schema_serializer
from rest_framework import serializers

from apps.wallet.models import Wallet, WalletTransaction


@extend_schema_serializer(component_name="Wallet")
class WalletSerializer(serializers.ModelSerializer):
    """Customer prepaid wallet representation."""

    customer_id = serializers.IntegerField(read_only=True)
    customer_code = serializers.CharField(source="customer.code", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Wallet
        fields = [
            "id",
            "customer_id",
            "customer_code",
            "balance",
            "currency",
            "status",
            "status_display",
            "row_version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


@extend_schema_serializer(component_name="TopupChannels")
class TopupChannelsSerializer(serializers.Serializer):
    """Read-only availability and VND limits for customer wallet top-up channels."""

    vnpay_enabled = serializers.BooleanField()
    vnpay_is_sandbox = serializers.BooleanField()
    vnpay_topup_min = serializers.IntegerField()
    vnpay_topup_max = serializers.IntegerField()
    simulated_vietqr_enabled = serializers.BooleanField()


@extend_schema_serializer(component_name="MeWalletDetail")
class MeWalletDetailSerializer(WalletSerializer):
    """Customer self-service wallet detail including available top-up channel flags."""

    topup_channels = serializers.SerializerMethodField()

    class Meta(WalletSerializer.Meta):
        fields = [
            *WalletSerializer.Meta.fields,
            "topup_channels",
        ]
        read_only_fields = fields

    def get_topup_channels(self, obj: Wallet) -> dict[str, bool | int]:
        tmn_code = str(getattr(settings, "VNPAY_TMN_CODE", "") or "").strip()
        hash_secret = str(getattr(settings, "VNPAY_HASH_SECRET", "") or "").strip()
        payment_url = str(getattr(settings, "VNPAY_PAYMENT_URL", "") or "").lower()
        return {
            "vnpay_enabled": bool(tmn_code and hash_secret),
            "vnpay_is_sandbox": "sandbox.vnpayment.vn" in payment_url,
            "vnpay_topup_min": int(getattr(settings, "VNPAY_TOPUP_MIN", 10000)),
            "vnpay_topup_max": int(getattr(settings, "VNPAY_TOPUP_MAX", 50000000)),
            "simulated_vietqr_enabled": bool(
                getattr(settings, "WALLET_SIMULATED_TOPUP_ENABLED", False)
            ),
        }


@extend_schema_serializer(component_name="WalletTransaction")
class WalletTransactionSerializer(serializers.ModelSerializer):
    """Immutable append-only wallet ledger entry representation."""

    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    transaction_type_display = serializers.CharField(
        source="get_transaction_type_display", read_only=True
    )
    direction = serializers.CharField(source="transaction_type", read_only=True)
    created_by_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = WalletTransaction
        fields = [
            "id",
            "wallet_id",
            "amount",
            "balance_after",
            "transaction_type",
            "transaction_type_display",
            "direction",
            "kind",
            "kind_display",
            "idempotency_key",
            "reference_type",
            "reference_id",
            "note",
            "created_by_id",
            "created_at",
        ]
        read_only_fields = fields


@extend_schema_serializer(component_name="WalletTopupRequest")
class TopupRequestSerializer(serializers.Serializer):
    """Customer self-service simulated VietQR top-up request."""

    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("10000.00"),
        max_value=Decimal("50000000.00"),
    )
    idempotency_key = serializers.CharField(
        max_length=100,
        required=True,
        allow_blank=False,
    )
    note = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        allow_null=True,
    )


@extend_schema_serializer(component_name="SimulatedQrMetadata")
class SimulatedQrMetadataSerializer(serializers.Serializer):
    """Metadata describing the simulated VietQR placeholder payload."""

    is_simulated = serializers.BooleanField()
    disclaimer = serializers.CharField()
    qr_payload = serializers.CharField()


@extend_schema_serializer(component_name="WalletTopupResponse")
class WalletTopupResponseSerializer(serializers.Serializer):
    """Response envelope for simulated VietQR wallet top-up."""

    wallet = WalletSerializer()
    transaction = WalletTransactionSerializer()
    replayed = serializers.BooleanField()
    simulated_qr = SimulatedQrMetadataSerializer()


@extend_schema_serializer(component_name="StaffWalletTopupRequest")
class StaffTopupSerializer(serializers.Serializer):
    """Staff-assisted cash top-up request at counter."""

    amount = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("1000.00"),
        max_value=Decimal("100000000.00"),
    )
    payment_method = serializers.ChoiceField(
        choices=[("CASH", "Tiền mặt")],
        default="CASH",
    )
    idempotency_key = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=False,
    )
    note = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        allow_null=True,
    )


@extend_schema_serializer(component_name="StaffWalletTopupResponse")
class StaffTopupResponseSerializer(serializers.Serializer):
    """Response envelope for staff counter cash top-up."""

    wallet = WalletSerializer()
    transaction = WalletTransactionSerializer()
    replayed = serializers.BooleanField()
