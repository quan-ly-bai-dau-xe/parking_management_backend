from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("core", "0001_initial"),
        ("customers", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Wallet",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("deleted_at", models.DateTimeField(blank=True, editable=False, null=True)),
                (
                    "balance",
                    models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14),
                ),
                ("currency", models.CharField(default="VND", max_length=3)),
                (
                    "status",
                    models.CharField(
                        choices=[("ACTIVE", "Đang hoạt động"), ("LOCKED", "Tạm khóa"), ("CLOSED", "Đã đóng")],
                        default="ACTIVE",
                        max_length=20,
                    ),
                ),
                ("row_version", models.IntegerField(default=1, editable=False)),
                (
                    "customer",
                    models.OneToOneField(
                        db_column="customer_id",
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="wallet",
                        to="customers.customer",
                    ),
                ),
                (
                    "deleted_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="deleted_by",
                        db_constraint=False,
                        editable=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "wallet",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="WalletTransaction",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=14)),
                ("balance_after", models.DecimalField(decimal_places=2, max_digits=14)),
                (
                    "transaction_type",
                    models.CharField(
                        choices=[("CREDIT", "Ghi có"), ("DEBIT", "Ghi nợ")],
                        max_length=10,
                    ),
                ),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("TOPUP_CASH", "Nạp tiền mặt tại quầy"),
                            ("TOPUP_VIETQR", "Nạp tiền qua VietQR"),
                            ("TOPUP_VNPAY", "Nạp tiền qua VNPAY"),
                            ("TICKET_PURCHASE", "Mua vé đỗ xe"),
                            ("TICKET_RENEWAL", "Gia hạn vé đỗ xe"),
                            ("PARKING_FEE", "Thanh toán phí gửi xe"),
                            ("REFUND", "Hoàn tiền"),
                            ("ADJUSTMENT", "Điều chỉnh số dư"),
                        ],
                        max_length=30,
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=100, unique=True)),
                ("reference_type", models.CharField(blank=True, max_length=50, null=True)),
                ("reference_id", models.BigIntegerField(blank=True, null=True)),
                ("note", models.TextField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        db_column="created_by_id",
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="wallet_transactions_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "wallet",
                    models.ForeignKey(
                        db_column="wallet_id",
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="transactions",
                        to="wallet.wallet",
                    ),
                ),
            ],
            options={
                "db_table": "wallet_transaction",
                "managed": False,
            },
        ),
    ]
