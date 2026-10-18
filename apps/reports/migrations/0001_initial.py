from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='VSlotOccupancyByFloor',
            fields=[
                ('lot_id', models.BigAutoField(primary_key=True, serialize=False)),
                ('lot_code', models.CharField(max_length=20)),
                ('lot_name', models.CharField(max_length=100)),
                ('floor_id', models.BigIntegerField()),
                ('floor_code', models.CharField(max_length=20)),
                ('floor_name', models.CharField(max_length=50)),
                ('zone_id', models.BigIntegerField()),
                ('zone_code', models.CharField(max_length=20)),
                ('zone_name', models.CharField(max_length=50)),
                ('total_slots', models.BigIntegerField()),
                ('operational_slots', models.BigIntegerField()),
                ('available_slots', models.BigIntegerField()),
                ('occupied_slots', models.BigIntegerField()),
                ('reserved_slots', models.BigIntegerField()),
                ('charging_slots', models.BigIntegerField()),
                ('maintenance_slots', models.BigIntegerField()),
                ('occupancy_rate_pct', models.DecimalField(decimal_places=2, max_digits=5)),
            ],
            options={
                'db_table': 'v_slot_occupancy_by_floor',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='VRevenueTodayByMethod',
            fields=[
                ('revenue_date', models.DateField(primary_key=True, serialize=False)),
                ('total_revenue', models.DecimalField(decimal_places=2, max_digits=12)),
                ('cash_revenue', models.DecimalField(decimal_places=2, max_digits=12)),
                ('vietqr_revenue', models.DecimalField(decimal_places=2, max_digits=12)),
                ('cash_pct', models.DecimalField(decimal_places=2, max_digits=5)),
                ('vietqr_pct', models.DecimalField(decimal_places=2, max_digits=5)),
            ],
            options={
                'db_table': 'v_revenue_today_by_method',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='VTrafficByHour',
            fields=[
                ('traffic_hour', models.DateTimeField(primary_key=True, serialize=False)),
                ('entry_count', models.BigIntegerField()),
                ('exit_count', models.BigIntegerField()),
                ('total_movements', models.BigIntegerField()),
            ],
            options={
                'db_table': 'v_traffic_by_hour',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='VAiRecognitionStats',
            fields=[
                ('total_sessions', models.BigIntegerField(primary_key=True, serialize=False)),
                ('ai_sessions', models.BigIntegerField()),
                ('manual_sessions', models.BigIntegerField()),
                ('ai_recognition_rate_pct', models.DecimalField(decimal_places=2, max_digits=5)),
                ('manual_rate_pct', models.DecimalField(decimal_places=2, max_digits=5)),
                ('avg_ai_confidence', models.DecimalField(decimal_places=2, max_digits=5)),
                ('active_auto_scan_gates', models.BigIntegerField()),
            ],
            options={
                'db_table': 'v_ai_recognition_stats',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='VCustomerStatusSummary',
            fields=[
                ('total_customers', models.BigIntegerField(primary_key=True, serialize=False)),
                ('active_customers', models.BigIntegerField()),
                ('suspended_customers', models.BigIntegerField()),
                ('blacklisted_customers', models.BigIntegerField()),
            ],
            options={
                'db_table': 'v_customer_status_summary',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='VRevenueStatistics',
            fields=[
                ('report_year', models.IntegerField(primary_key=True, serialize=False)),
                ('report_quarter', models.IntegerField()),
                ('report_month', models.IntegerField()),
                ('total_tickets_sold', models.BigIntegerField()),
                ('total_renewals', models.BigIntegerField()),
                ('total_revenue', models.DecimalField(decimal_places=2, max_digits=12)),
            ],
            options={
                'db_table': 'v_revenue_statistics',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='VVehicleTrafficDaily',
            fields=[
                ('traffic_date', models.DateField(primary_key=True, serialize=False)),
                ('total_entries', models.BigIntegerField()),
                ('total_exits', models.BigIntegerField()),
                ('currently_parked_count', models.BigIntegerField()),
            ],
            options={
                'db_table': 'v_vehicle_traffic_daily',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='VCustomerVehicleSummary',
            fields=[
                ('customer_id', models.BigAutoField(primary_key=True, serialize=False)),
                ('customer_code', models.CharField(max_length=10)),
                ('full_name', models.CharField(max_length=45)),
                ('phone', models.CharField(max_length=15)),
                ('customer_status', models.CharField(max_length=20)),
                ('total_registered_vehicles', models.BigIntegerField()),
                ('total_active_tickets', models.BigIntegerField()),
            ],
            options={
                'db_table': 'v_customer_vehicle_summary',
                'managed': False,
            },
        ),
    ]
