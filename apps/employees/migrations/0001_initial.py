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
            name='Position',
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
                'db_table': 'position',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Employee',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('code', models.CharField(max_length=10, unique=True)),
                ('full_name', models.CharField(max_length=45)),
                ('date_of_birth', models.DateField(blank=True, null=True)),
                ('gender', models.CharField(blank=True, max_length=10, null=True)),
                ('identity_card_number', models.CharField(blank=True, max_length=20, null=True)),
                ('phone', models.CharField(max_length=15)),
                ('email', models.CharField(max_length=100)),
                ('address', models.CharField(blank=True, max_length=100, null=True)),
                ('province', models.ForeignKey(
                    blank=True,
                    db_column='province_id',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='employees',
                    to='core.administrativeprovince',
                )),
                ('district', models.ForeignKey(
                    blank=True,
                    db_column='district_id',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='employees',
                    to='core.administrativedistrict',
                )),
                ('ward', models.ForeignKey(
                    blank=True,
                    db_column='ward_id',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='employees',
                    to='core.administrativeward',
                )),
                ('position', models.ForeignKey(
                    db_column='position_id',
                    db_constraint=False,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='employees',
                    to='employees.position',
                )),
                ('account', models.ForeignKey(
                    blank=True,
                    db_column='account_id',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='employee_profile',
                    to='accounts.account',
                )),
                ('status', models.CharField(
                    choices=[('ACTIVE', 'Đang làm việc'), ('ON_LEAVE', 'Nghỉ phép'), ('TERMINATED', 'Đã nghỉ việc')],
                    default='ACTIVE',
                    max_length=20,
                )),
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
                'db_table': 'employee',
                'managed': False,
            },
        ),
    ]
