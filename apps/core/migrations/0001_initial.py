from pathlib import Path
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def read_schema_sql() -> str:
    schema_path = Path(settings.BASE_DIR) / "db" / "01-schema.sql"
    return schema_path.read_text(encoding="utf-8")


class RunSchemaSQL(migrations.RunSQL):
    """Execute db/01-schema.sql from disk at migration time if not already loaded."""

    def database_forwards(self, app_label, schema_editor, from_state, to_state):
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                "AND table_name IN ("
                "'administrative_province', 'account', 'parking_slot', 'vehicle_entry_exit_log'"
                ");"
            )
            row = cursor.fetchone()
            if row and row[0] == 4:
                return
        self.sql = read_schema_sql()
        super().database_forwards(app_label, schema_editor, from_state, to_state)


class Migration(migrations.Migration):
    atomic = False
    initial = True

    dependencies = []

    operations = [
        RunSchemaSQL(
            sql=read_schema_sql(),
            reverse_sql=migrations.RunSQL.noop,
        ),
        migrations.CreateModel(
            name="AdministrativeProvince",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=20, unique=True)),
                ("name", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(editable=False)),
                ("updated_at", models.DateTimeField(editable=False)),
            ],
            options={
                "db_table": "administrative_province",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="AdministrativeDistrict",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=20)),
                ("name", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(editable=False)),
                ("updated_at", models.DateTimeField(editable=False)),
                (
                    "province",
                    models.ForeignKey(
                        db_column="province_id",
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="districts",
                        to="core.administrativeprovince",
                    ),
                ),
            ],
            options={
                "db_table": "administrative_district",
                "managed": False,
            },
        ),
        migrations.CreateModel(
            name="AdministrativeWard",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("code", models.CharField(max_length=20)),
                ("name", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(editable=False)),
                ("updated_at", models.DateTimeField(editable=False)),
                (
                    "district",
                    models.ForeignKey(
                        db_column="district_id",
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="wards",
                        to="core.administrativedistrict",
                    ),
                ),
            ],
            options={
                "db_table": "administrative_ward",
                "managed": False,
            },
        ),
    ]
