from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('core', '0001_initial'),
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Customer',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('code', models.CharField(max_length=10, unique=True)),
                ('full_name', models.CharField(max_length=45)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('gender', models.CharField(blank=True, max_length=10, null=True)),
                ('identity_card_number', models.CharField(max_length=20)),
                ('phone', models.CharField(max_length=15)),
                ('email', models.CharField(blank=True, max_length=100, null=True)),
                ('address', models.CharField(blank=True, max_length=100, null=True)),
                ('province', models.ForeignKey(
                    blank=True,
                    db_column='province_id',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='customers',
                    to='core.administrativeprovince',
                )),
                ('district', models.ForeignKey(
                    blank=True,
                    db_column='district_id',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='customers',
                    to='core.administrativedistrict',
                )),
                ('ward', models.ForeignKey(
                    blank=True,
                    db_column='ward_id',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='customers',
                    to='core.administrativeward',
                )),
                ('account', models.ForeignKey(
                    blank=True,
                    db_column='account_id',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='customer_profile',
                    to='accounts.account',
                )),
                ('status', models.CharField(
                    choices=[('ACTIVE', 'Hoạt động'), ('SUSPENDED', 'Tạm ngưng'), ('BLACKLISTED', 'Danh sách đen')],
                    default='ACTIVE',
                    max_length=20,
                )),
                ('status_reason', models.TextField(blank=True, null=True)),
                ('is_anonymized', models.BooleanField(default=False)),
                ('anonymized_at', models.DateTimeField(blank=True, null=True)),
                ('row_version', models.IntegerField(default=1, editable=False)),
                ('created_at', models.DateTimeField(editable=False)),
                ('updated_at', models.DateTimeField(editable=False)),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('deleted_by', models.ForeignKey(
                    blank=True,
                    db_constraint=False,
                    editable=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='+',
                    to='accounts.account',
                )),
            ],
            options={
                'db_table': 'customer',
                'managed': False,
            },
        ),
    ]
