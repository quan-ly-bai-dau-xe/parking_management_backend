from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('core', '0001_initial'),
        ('accounts', '0001_initial'),
        ('customers', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='VehicleType',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('code', models.CharField(max_length=20, unique=True)),
                ('name', models.CharField(max_length=50)),
                ('description', models.CharField(blank=True, max_length=255, null=True)),
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
                'db_table': 'vehicle_type',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Vehicle',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('code', models.CharField(max_length=10, unique=True)),
                ('license_plate', models.CharField(max_length=20)),
                ('license_plate_norm', models.CharField(blank=True, editable=False, max_length=20, null=True)),
                ('model_name', models.CharField(max_length=50)),
                ('brand', models.CharField(blank=True, max_length=50, null=True)),
                ('color', models.CharField(blank=True, max_length=30, null=True)),
                ('image_url', models.TextField(blank=True, null=True)),
                ('notes', models.TextField(blank=True, null=True)),
                ('ticket_expires_at', models.DateTimeField(blank=True, null=True)),
                ('row_version', models.IntegerField(default=1, editable=False)),
                ('created_at', models.DateTimeField(editable=False)),
                ('updated_at', models.DateTimeField(editable=False)),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('customer', models.ForeignKey(
                    db_column='customer_id',
                    db_constraint=False,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='vehicles',
                    to='customers.customer',
                )),
                ('deleted_by', models.ForeignKey(
                    blank=True,
                    db_constraint=False,
                    editable=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='+',
                    to='accounts.account',
                )),
                ('ticket_type', models.ForeignKey(
                    blank=True,
                    db_column='ticket_type_id',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='vehicles',
                    to='tickets.tickettype',
                )),
                ('vehicle_type', models.ForeignKey(
                    db_column='vehicle_type_id',
                    db_constraint=False,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='vehicles',
                    to='vehicles.vehicletype',
                )),
            ],
            options={
                'db_table': 'vehicle',
                'managed': False,
            },
        ),
    ]
