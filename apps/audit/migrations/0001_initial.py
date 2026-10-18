from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('core', '0001_initial'),
        ('accounts', '0001_initial'),
        ('employees', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='ActivityLog',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('action', models.CharField(max_length=50)),
                ('entity_type', models.CharField(max_length=50)),
                ('entity_id', models.BigIntegerField(blank=True, null=True)),
                ('message', models.TextField()),
                ('occurred_at', models.DateTimeField()),
                ('actor_account', models.ForeignKey(
                    blank=True,
                    db_column='actor_account_id',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='activity_logs',
                    to='accounts.account',
                )),
            ],
            options={
                'db_table': 'activity_log',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='SystemAlert',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('alert_type', models.CharField(max_length=30)),
                ('severity', models.CharField(choices=[('INFO', 'Thông tin'), ('WARNING', 'Cảnh báo'), ('CRITICAL', 'Nghiêm trọng')], max_length=20)),
                ('message', models.TextField()),
                ('entity_type', models.CharField(blank=True, max_length=50, null=True)),
                ('entity_id', models.BigIntegerField(blank=True, null=True)),
                ('occurred_at', models.DateTimeField()),
                ('resolved_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(editable=False)),
                ('resolved_by', models.ForeignKey(
                    blank=True,
                    db_column='resolved_by',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='resolved_alerts',
                    to='employees.employee',
                )),
            ],
            options={
                'db_table': 'system_alert',
                'managed': False,
            },
        ),
    ]
