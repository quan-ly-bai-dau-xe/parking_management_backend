from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tickets", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="method",
            field=models.CharField(
                choices=[
                    ("CASH", "Tiền mặt"),
                    ("VIETQR", "Chuyển khoản VietQR"),
                    ("WALLET", "Ví khách hàng"),
                ],
                max_length=20,
            ),
        ),
    ]
