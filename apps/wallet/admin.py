from django.contrib import admin

from apps.wallet.models import Wallet, WalletTransaction


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("id", "customer", "balance", "currency", "status", "updated_at")
    search_fields = ("customer__code", "customer__full_name")
    readonly_fields = ("balance", "row_version", "created_at", "updated_at")


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "wallet",
        "transaction_type",
        "kind",
        "amount",
        "balance_after",
        "created_at",
    )
    list_filter = ("transaction_type", "kind")
    search_fields = ("idempotency_key", "wallet__customer__code")
    readonly_fields = (
        "wallet",
        "amount",
        "balance_after",
        "transaction_type",
        "kind",
        "idempotency_key",
        "reference_type",
        "reference_id",
        "note",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
