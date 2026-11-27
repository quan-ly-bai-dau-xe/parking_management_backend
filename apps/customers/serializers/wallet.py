from __future__ import annotations

from rest_framework import serializers

from apps.customers.models import CustomerWallet, CustomerWalletTransaction


class CustomerWalletTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerWalletTransaction
        fields = (
            "id",
            "transaction_type",
            "amount",
            "balance_before",
            "balance_after",
            "session_id",
            "reference_code",
            "description",
            "created_at",
        )


class CustomerWalletDetailSerializer(serializers.ModelSerializer):
    transactions = serializers.SerializerMethodField()
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    customer_code = serializers.CharField(source="customer.code", read_only=True)

    class Meta:
        model = CustomerWallet
        fields = (
            "id",
            "customer_id",
            "customer_code",
            "customer_name",
            "balance",
            "status",
            "created_at",
            "updated_at",
            "transactions",
        )

    def get_transactions(self, obj: CustomerWallet):
        qs = obj.transactions.order_by("-id")[:10]
        return CustomerWalletTransactionSerializer(qs, many=True).data


class WalletDepositRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1000)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    reference_code = serializers.CharField(required=False, allow_blank=True, default="")


class WalletDeductRequestSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=1)
    session_id = serializers.IntegerField(required=False, allow_null=True)
    session_code = serializers.CharField(required=False, allow_blank=True)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    reference_code = serializers.CharField(required=False, allow_blank=True, default="")
