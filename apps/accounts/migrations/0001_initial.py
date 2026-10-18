from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Account',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('email', models.CharField(blank=True, max_length=100, null=True)),
                ('phone', models.CharField(blank=True, max_length=15, null=True)),
                ('password', models.CharField(db_column='password_hash', max_length=255)),
                ('role', models.CharField(choices=[('MANAGER', 'Quản lý'), ('EMPLOYEE', 'Nhân viên'), ('CUSTOMER', 'Khách hàng')], default='EMPLOYEE', max_length=20)),
                ('is_active', models.BooleanField(default=True)),
                ('last_login', models.DateTimeField(blank=True, db_column='last_login_at', null=True)),
                ('row_version', models.IntegerField(default=1, editable=False)),
                ('created_at', models.DateTimeField(editable=False)),
                ('updated_at', models.DateTimeField(editable=False)),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('deleted_by', models.ForeignKey(blank=True, db_constraint=False, editable=False, null=True, on_delete=django.db.models.deletion.DO_NOTHING, related_name='+', to='accounts.account')),
            ],
            options={
                'db_table': 'account',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='PasswordResetToken',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('token_hash', models.CharField(max_length=255)),
                ('expires_at', models.DateTimeField()),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('requested_ip', models.CharField(blank=True, max_length=45, null=True)),
                ('created_at', models.DateTimeField(editable=False)),
                ('account', models.ForeignKey(db_column='account_id', db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, related_name='password_reset_tokens', to='accounts.account')),
            ],
            options={
                'db_table': 'password_reset_token',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='PersistentLoginToken',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('series', models.CharField(max_length=64, unique=True)),
                ('token_hash', models.CharField(max_length=255)),
                ('ip_address', models.CharField(blank=True, max_length=45, null=True)),
                ('user_agent', models.CharField(blank=True, max_length=255, null=True)),
                ('created_at', models.DateTimeField(editable=False)),
                ('last_used_at', models.DateTimeField()),
                ('expires_at', models.DateTimeField()),
                ('account', models.ForeignKey(db_column='account_id', db_constraint=False, on_delete=django.db.models.deletion.DO_NOTHING, related_name='persistent_tokens', to='accounts.account')),
            ],
            options={
                'db_table': 'persistent_login_token',
                'managed': False,
            },
        ),
    ]
