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
            name='News',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200)),
                ('slug', models.CharField(max_length=220, unique=True)),
                ('summary', models.CharField(blank=True, max_length=500, null=True)),
                ('content', models.TextField()),
                ('thumbnail_url', models.TextField(blank=True, null=True)),
                ('is_published', models.BooleanField(default=False)),
                ('published_at', models.DateTimeField(blank=True, null=True)),
                ('view_count', models.IntegerField(default=0)),
                ('row_version', models.IntegerField(default=1, editable=False)),
                ('created_at', models.DateTimeField(editable=False)),
                ('updated_at', models.DateTimeField(editable=False)),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('author', models.ForeignKey(
                    db_column='author_id',
                    db_constraint=False,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='news',
                    to='employees.employee',
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
            ],
            options={
                'db_table': 'news',
                'managed': False,
            },
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('title', models.CharField(max_length=200)),
                ('content', models.TextField()),
                ('notification_type', models.CharField(
                    choices=[('SYSTEM', 'Hệ thống'), ('ALERT', 'Cảnh báo an ninh'), ('TICKET', 'Thông báo vé xe'), ('PAYMENT', 'Thông báo thanh toán')],
                    default='SYSTEM',
                    max_length=30,
                )),
                ('is_read', models.BooleanField(default=False)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(editable=False)),
                ('deleted_at', models.DateTimeField(blank=True, editable=False, null=True)),
                ('recipient_account', models.ForeignKey(
                    blank=True,
                    db_column='recipient_account_id',
                    db_constraint=False,
                    null=True,
                    on_delete=django.db.models.deletion.DO_NOTHING,
                    related_name='notifications',
                    to='accounts.account',
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
            ],
            options={
                'db_table': 'notification',
                'managed': False,
            },
        ),
    ]
