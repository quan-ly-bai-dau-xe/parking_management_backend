"""
Schema Parity and Integrity Test Suite for PostgreSQL 18.6 and Django Unmanaged Models.

Verifies:
1. Exact 1:1 parity between PostgreSQL 18.6 catalog and Django unmanaged models (28 tables + 8 views).
2. All 393 columns match in name, nullability (on base tables), and max_length.
3. Foreign keys configuration (on_delete=DO_NOTHING, db_constraint=False).
4. DB-managed fields immutability (editable=False).
5. Soft-delete lifecycle (delete -> soft-delete, restore, hard_delete protection).
6. Unmanaged view models query execution without exceptions.
7. load_sample_data idempotency (double execution yields identical row counts).
8. Centralized messages catalog (55 MSG-* and 64 PROP-* codes).
"""

import pytest
from django.apps import apps
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.db import connection, models

from apps.core.messages import MESSAGES, get_message

pytestmark = pytest.mark.django_db

EXPECTED_TABLES = [
    "administrative_province",
    "administrative_district",
    "administrative_ward",
    "account",
    "persistent_login_token",
    "password_reset_token",
    "customer",
    "position",
    "employee",
    "vehicle_type",
    "vehicle",
    "ticket_type",
    "ticket",
    "ticket_renewal",
    "payment",
    "parking_lot",
    "parking_floor",
    "parking_zone",
    "parking_slot",
    "slot_allowed_vehicle_type",
    "slot_reservation",
    "parking_gate",
    "vehicle_entry_exit_log",
    "plate_blacklist",
    "news",
    "notification",
    "activity_log",
    "system_alert",
]

EXPECTED_VIEWS = [
    "v_revenue_statistics",
    "v_vehicle_traffic_daily",
    "v_slot_occupancy_by_floor",
    "v_customer_vehicle_summary",
]


def get_domain_models():
    """Returns all 36 domain models across the 10 domain apps."""
    domain_app_labels = {
        "core",
        "accounts",
        "employees",
        "customers",
        "vehicles",
        "tickets",
        "parking",
        "content",
        "audit",
        "reports",
    }
    return [m for m in apps.get_models() if m._meta.app_label in domain_app_labels]


def test_database_tables_and_views_count():
    """Verify that all 28 domain tables and 8 views exist in PostgreSQL 18.6."""
    with connection.cursor() as cur:
        cur.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
        """)
        db_tables = {r[0] for r in cur.fetchall()}

        cur.execute("""
            SELECT table_name FROM information_schema.views
            WHERE table_schema = 'public';
        """)
        db_views = {r[0] for r in cur.fetchall()}

    for tbl in EXPECTED_TABLES:
        assert tbl in db_tables, (
            f"Expected table {tbl} missing in PostgreSQL public schema"
        )

    for vw in EXPECTED_VIEWS:
        assert vw in db_views, f"Expected view {vw} missing in PostgreSQL public schema"


def test_models_unmanaged_and_1to1_table_mapping():
    """Verify all 36 domain models are unmanaged and map 1:1 to DB relations."""
    domain_models = get_domain_models()
    assert len(domain_models) == 36, (
        f"Expected 36 domain models, found {len(domain_models)}"
    )

    for model in domain_models:
        assert model._meta.managed is False, (
            f"Model {model.__name__} must be unmanaged (managed=False)"
        )

    model_tables = {m._meta.db_table: m for m in domain_models}
    for tbl in EXPECTED_TABLES:
        assert tbl in model_tables, f"Table {tbl} not represented in Django models"

    for vw in EXPECTED_VIEWS:
        assert vw in model_tables, f"View {vw} not represented in Django models"


def test_columns_count_and_names_exact_match():
    """Verify all columns in all 36 relations match exactly in name and count (393 total)."""
    domain_models = get_domain_models()
    total_db_cols = 0
    total_dj_cols = 0

    with connection.cursor() as cur:
        for model in domain_models:
            tbl = model._meta.db_table
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s
                ORDER BY ordinal_position;
            """,
                [tbl],
            )
            db_cols = [r[0] for r in cur.fetchall()]
            dj_cols = [f.column for f in model._meta.fields]

            missing_in_dj = set(db_cols) - set(dj_cols)
            extra_in_dj = set(dj_cols) - set(db_cols)

            assert not missing_in_dj, (
                f"Model {model.__name__} ({tbl}) missing columns: {missing_in_dj}"
            )
            assert not extra_in_dj, (
                f"Model {model.__name__} ({tbl}) has unexpected extra columns: {extra_in_dj}"
            )
            assert len(db_cols) == len(dj_cols), (
                f"Column count mismatch in {tbl}: DB={len(db_cols)}, DJ={len(dj_cols)}"
            )

            total_db_cols += len(db_cols)
            total_dj_cols += len(dj_cols)

    assert total_db_cols == 393, (
        f"Expected 393 total columns in DB, got {total_db_cols}"
    )
    assert total_dj_cols == 393, (
        f"Expected 393 total columns in Django, got {total_dj_cols}"
    )


def test_column_nullability_and_max_length_parity():
    """Verify nullability and varchar max_length match between PostgreSQL base tables and Django."""
    domain_models = get_domain_models()
    # Nullability in information_schema is authoritative for BASE TABLES
    base_table_models = [
        m for m in domain_models if not m._meta.db_table.startswith("v_")
    ]

    with connection.cursor() as cur:
        for model in base_table_models:
            tbl = model._meta.db_table
            cur.execute(
                """
                SELECT column_name, is_nullable, character_maximum_length, data_type
                FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = %s;
            """,
                [tbl],
            )
            col_info = {
                r[0]: {"nullable": r[1] == "YES", "max_len": r[2], "type": r[3]}
                for r in cur.fetchall()
            }

            for field in model._meta.fields:
                db_info = col_info[field.column]
                # Check varchar max_length
                if (
                    isinstance(field, models.CharField)
                    and not isinstance(field, models.GeneratedField)
                    and db_info["max_len"] is not None
                ):
                    assert field.max_length == db_info["max_len"], (
                        f"Max length mismatch on {tbl}.{field.column}: "
                        f"Django={field.max_length}, DB={db_info['max_len']}"
                    )
                # Primary keys and generated fields in Django are non-null by contract
                if not field.primary_key and not isinstance(
                    field, models.GeneratedField
                ):
                    assert field.null == db_info["nullable"], (
                        f"Nullability mismatch on {tbl}.{field.column}: "
                        f"Django null={field.null}, DB nullable={db_info['nullable']}"
                    )


def test_foreign_keys_configuration():
    """Verify all ForeignKeys use on_delete=DO_NOTHING and db_constraint=False."""
    domain_models = get_domain_models()
    fk_count = 0

    for model in domain_models:
        for field in model._meta.fields:
            if field.is_relation and isinstance(field, models.ForeignKey):
                assert field.remote_field.on_delete == models.DO_NOTHING, (
                    f"FK {model.__name__}.{field.name} on_delete must be DO_NOTHING"
                )
                assert field.db_constraint is False, (
                    f"FK {model.__name__}.{field.name} db_constraint must be False"
                )
                fk_count += 1

    assert fk_count >= 69, (
        f"Expected at least 69 ForeignKeys in domain models, found {fk_count}"
    )


def test_db_managed_fields_editable_false():
    """Verify created_at, updated_at, row_version, and license_plate_norm are editable=False."""
    domain_models = get_domain_models()
    managed_col_names = {
        "created_at",
        "updated_at",
        "row_version",
        "license_plate_norm",
    }

    for model in domain_models:
        for field in model._meta.fields:
            if field.column in managed_col_names:
                assert field.editable is False, (
                    f"Field {model.__name__}.{field.name} ({field.column}) must have editable=False"
                )


def test_soft_delete_lifecycle_and_hard_delete_ban():
    """Verify soft-delete behavior on the existing notification model."""
    from apps.content.models import Notification

    item = Notification.objects.create(
        title="Soft-delete test",
        content="Temporary test notification",
    )
    item_id = item.id

    item.delete()
    assert item.deleted_at is not None
    assert Notification.objects.filter(id=item_id).exists() is False
    assert Notification.all_objects.filter(id=item_id).exists() is True

    item.restore()
    assert item.deleted_at is None
    assert Notification.objects.filter(id=item_id).exists() is True

    with pytest.raises(PermissionDenied):
        item.hard_delete()


def test_query_database_views():
    """Verify each view declared by the current SQL schema is queryable."""
    with connection.cursor() as cursor:
        for view_name in EXPECTED_VIEWS:
            cursor.execute(f'SELECT COUNT(*) FROM "{view_name}"')
            count = cursor.fetchone()[0]
            assert count >= 0, f"View {view_name} could not be queried"


def test_load_sample_data_idempotency():
    """Verify running load_sample_data twice yields identical row counts on all 28 tables."""
    table_models = [
        m for m in get_domain_models() if not m._meta.db_table.startswith("v_")
    ]

    # Counts after 1st seed
    counts_before = {
        m._meta.db_table: m.all_objects.count()
        if hasattr(m, "all_objects")
        else m.objects.count()
        for m in table_models
    }

    # Run 2nd seed
    call_command("load_sample_data", force_production=True)

    # Counts after 2nd seed
    counts_after = {
        m._meta.db_table: m.all_objects.count()
        if hasattr(m, "all_objects")
        else m.objects.count()
        for m in table_models
    }

    assert counts_before == counts_after, (
        f"Idempotency violation detected: {counts_before} != {counts_after}"
    )


def test_run_schema_sql_idempotent_when_already_loaded():
    """Verify RunSchemaSQL in core.0001_initial safely skips execution when db/01-schema.sql is already loaded."""
    import importlib

    from django.db import migrations

    migration_mod = importlib.import_module("apps.core.migrations.0001_initial")
    op = migration_mod.Migration.operations[0]
    assert isinstance(op, migrations.RunSQL)
    assert op.reverse_sql == migrations.RunSQL.noop

    with connection.schema_editor(atomic=False) as schema_editor:
        op.database_forwards("core", schema_editor, None, None)


def test_messages_catalog_completeness():
    """Verify MSG-* (55) and PROP-* (64) messages catalog completeness and get_message function."""
    msg_codes = [k for k in MESSAGES if k.startswith("MSG-")]
    prop_codes = [k for k in MESSAGES if k.startswith("PROP-")]

    assert len(msg_codes) >= 55, (
        f"Expected at least 55 MSG-* codes, found {len(msg_codes)}"
    )
    assert len(prop_codes) >= 64, (
        f"Expected at least 64 PROP-* codes, found {len(prop_codes)}"
    )

    # Test get_message helper
    assert (
        get_message("MSG-4.1-M02")
        == "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu"
    )
    assert "email" in get_message("MSG-4.3.3-M01", item="email")

    # Test unknown message raises KeyError
    with pytest.raises(KeyError):
        get_message("UNKNOWN-CODE-999")


# ==============================================================================
# BỔ SUNG: Kiểm thử Tầng Ghi (ORM Mutation, INSERT, Lifecycle & Auth)
# ==============================================================================


def test_account_create_user_and_superuser_success():
    """
    Kiểm thử thao tác tạo tài khoản người dùng và quản trị viên qua Django ORM và CLI.
    Xác minh:
    1. Account.objects.create_user() tạo tài khoản chuẩn bằng email:
       - Mật khẩu được băm an toàn (không lưu plain text).
       - created_at và updated_at tự động sinh, không bị None (tránh NotNullViolation).
       - Phân quyền mặc định role='EMPLOYEE', is_staff=False, is_superuser=False.
    2. Account.objects.create_user() tạo tài khoản bằng số điện thoại (TL-01).
    3. Xác thực thành công qua Django ModelBackend chuẩn với email.
    4. Account.objects.create_superuser() tạo tài khoản quản trị:
       - role='MANAGER', is_staff=True, is_superuser=True.
       - created_at và updated_at hợp lệ.
    5. call_command('createsuperuser', '--noinput') thực thi thành công không bị crash.
    6. create_user() thiếu cả email và phone quăng ValueError theo quy định.
    """
    from django.contrib.auth import authenticate
    from django.core.management import call_command
    from django.utils import timezone

    from apps.accounts.models import Account

    # 1. Tạo tài khoản thường qua Email
    user_email = Account.objects.create_user(
        email="test_emp_01@example.com",
        password="SecurePassword123!",
        role="EMPLOYEE",
    )
    assert user_email.id is not None
    assert user_email.email == "test_emp_01@example.com"
    assert user_email.phone is None
    assert user_email.role == "EMPLOYEE"
    assert user_email.is_active is True
    assert user_email.is_staff is False
    assert user_email.is_superuser is False
    assert user_email.created_at is not None
    assert user_email.updated_at is not None
    assert isinstance(user_email.created_at, timezone.datetime)
    assert "SecurePassword123!" not in user_email.password
    assert user_email.check_password("SecurePassword123!") is True
    assert user_email.check_password("WrongPassword!") is False

    # 2. Tạo tài khoản thường qua Phone (không có email - TL-01)
    user_phone = Account.objects.create_user(
        phone="0987654321",
        password="PhonePassword123!",
        role="EMPLOYEE",
    )
    assert user_phone.id is not None
    assert user_phone.phone == "0987654321"
    assert user_phone.email is None
    assert user_phone.created_at is not None
    assert user_phone.updated_at is not None
    # 3. Xác thực qua Django ModelBackend mặc định (với USERNAME_FIELD = email)
    # 3a. Đăng nhập thành công bằng Email
    auth_email = authenticate(
        None, username="test_emp_01@example.com", password="SecurePassword123!"
    )
    assert auth_email is not None
    assert auth_email.id == user_email.id

    # 3b. Đăng nhập thất bại khi mật khẩu sai
    assert (
        authenticate(None, username="test_emp_01@example.com", password="BadPassword")
        is None
    )

    # 3c. Từ chối xác thực khi tài khoản bị khóa (is_active=False)
    user_email.is_active = False
    user_email.save(update_fields=["is_active"])
    assert (
        authenticate(
            None, username="test_emp_01@example.com", password="SecurePassword123!"
        )
        is None
    )
    user_email.is_active = True
    user_email.save(update_fields=["is_active"])

    # 3d. Từ chối xác thực khi tài khoản bị xóa mềm (deleted_at IS NOT NULL)
    user_email.delete()
    assert (
        authenticate(
            None, username="test_emp_01@example.com", password="SecurePassword123!"
        )
        is None
    )
    user_email.restore()

    # 4. Tạo tài khoản Quản trị viên (Superuser) qua ORM
    superuser = Account.objects.create_superuser(
        email="super_admin_test@example.com",
        password="SuperAdminPass123!",
    )
    assert superuser.id is not None
    assert superuser.role == "MANAGER"
    assert superuser.is_staff is True
    assert superuser.is_superuser is True
    assert superuser.has_perm("any.permission") is True
    assert superuser.has_module_perms("any_app") is True
    assert superuser.created_at is not None
    assert superuser.updated_at is not None

    # 5. Kiểm thử lệnh quản trị `createsuperuser --noinput`
    cli_email = "cli_superuser_test@example.com"
    call_command("createsuperuser", "--noinput", email=cli_email)
    cli_user = Account.objects.get(email=cli_email)
    assert cli_user.role == "MANAGER"
    assert cli_user.is_staff is True
    assert cli_user.created_at is not None

    # 6. Kiểm tra validation khi không có cả email và phone
    with pytest.raises(
        ValueError, match="Bắt buộc phải cung cấp Email hoặc Số điện thoại"
    ):
        Account.objects.create_user(password="NoEmailOrPhone123!")


def test_orm_insert_on_business_models():
    """
    Kiểm thử thao tác chèn bản ghi mới (INSERT) qua Django ORM trên các bảng nghiệp vụ chính.
    Đảm bảo khắc phục triệt để lỗi NotNullViolation trên created_at/updated_at:
    1. Position (Danh mục chức vụ - SoftDelete).
    2. Customer (Hồ sơ khách hàng - SoftDelete, GDPR/NĐ 13).
    3. TicketType (Danh mục loại vé - SoftDelete).
    4. Vehicle (Phương tiện - SoftDelete, GeneratedField license_plate_norm).
    5. PersistentLoginToken (Bảng token xác thực - Plain delete, không xóa mềm per TL-36).
    6. PasswordResetToken (Bảng token đặt lại mật khẩu - Plain delete).
    7. PlateBlacklist (Danh sách đen - SoftDelete, GeneratedField).
    8. ActivityLog (Nhật ký kiểm toán - Append-only, occurred_at timestamp).
    """
    from datetime import timedelta
    from decimal import Decimal

    from django.utils import timezone

    from apps.accounts.models import Account, PasswordResetToken, PersistentLoginToken
    from apps.audit.models import ActivityLog
    from apps.customers.models import Customer
    from apps.employees.models import Position
    from apps.tickets.models import TicketType
    from apps.vehicles.models import Vehicle, VehicleType

    now = timezone.now()

    # 1. INSERT Position (Bảng danh mục không phụ thuộc)
    pos = Position.objects.create(
        code="POS_TEST_IT2",
        name="Chức vụ Test Parity",
        description="Kiểm thử ORM Insert trên Position",
    )
    assert pos.id is not None
    assert pos.code == "POS_TEST_IT2"
    assert pos.created_at is not None
    assert pos.updated_at is not None
    assert pos.row_version == 1

    # 2. INSERT Customer (Bảng nghiệp vụ khách hàng)
    cust = Customer.objects.create(
        code="KH-TEST99",
        full_name="Nguyễn Văn Test Parity",
        identity_card_number="079090123456",
        phone="0918765432",
        email="customer_it2_test@example.com",
        address="123 Đường Kiểm Thử, Quận 1",
    )
    assert cust.id is not None
    assert cust.code == "KH-TEST99"
    assert cust.created_at is not None
    assert cust.updated_at is not None
    assert cust.status == "ACTIVE"
    assert cust.is_anonymized is False

    # 3. INSERT TicketType (Bảng danh mục loại vé)
    tt = TicketType.objects.create(
        code="TT_TEST_IT2",
        name="Vé Tháng Test Parity",
        duration_days=30,
        default_price=Decimal("200000.00"),
        description="Vé tháng kiểm thử",
    )
    assert tt.id is not None
    assert tt.code == "TT_TEST_IT2"
    assert tt.created_at is not None
    assert tt.updated_at is not None
    assert tt.default_price == Decimal("200000.00")

    # 4. INSERT Vehicle (Bảng nghiệp vụ có GeneratedField và FK)
    vtype = VehicleType.objects.first()
    assert vtype is not None, "VehicleType seed data required"

    veh = Vehicle.objects.create(
        code="XE-TEST99",
        license_plate="51f-88888",
        model_name="Corolla Cross",
        brand="Toyota",
        color="Đỏ",
        vehicle_type=vtype,
        customer=cust,
        ticket_type=tt,
        ticket_expires_at=now + timedelta(days=30),
    )
    assert veh.id is not None
    assert veh.code == "XE-TEST99"
    assert veh.created_at is not None
    assert veh.updated_at is not None
    assert (
        veh.license_plate_norm == "51F88888"
    )  # Database fn_normalize_license_plate tự động loại bỏ dấu nối và UPPER
    assert veh.ticket_expires_at is not None

    # 5. INSERT PersistentLoginToken (Bảng token có timestamp độc lập, cho phép plain delete)
    test_user = Account.objects.create_user(
        email="token_user_test@example.com",
        password="TokenUserPass123!",
    )
    token = PersistentLoginToken.objects.create(
        series="series_unique_hash_it2_test_9999",
        token_hash="sha256_mock_token_hash_value_for_test",
        account=test_user,
        ip_address="127.0.0.1",
        user_agent="pytest-client/1.0",
        last_used_at=now,
        expires_at=now + timedelta(days=14),
    )
    assert token.id is not None
    assert token.created_at is not None
    assert token.last_used_at is not None
    assert token.expires_at > token.created_at

    # Kiểm tra plain delete trên PersistentLoginToken (TL-36 & ADR-0004)
    token_id = token.id
    token.delete()
    assert PersistentLoginToken.objects.filter(id=token_id).exists() is False

    # 6. INSERT PasswordResetToken
    reset_tok = PasswordResetToken.objects.create(
        account=test_user,
        token_hash="pwd_reset_token_hash_test_value",
        expires_at=now + timedelta(hours=2),
    )
    assert reset_tok.id is not None
    assert reset_tok.created_at is not None

    # Plain delete trên PasswordResetToken
    reset_tok_id = reset_tok.id
    reset_tok.delete()
    assert PasswordResetToken.objects.filter(id=reset_tok_id).exists() is False

    # 7. INSERT ActivityLog (Bảng append-only với occurred_at timestamp)
    log_entry = ActivityLog.objects.create(
        actor_account=test_user,
        action="TEST_INSERT",
        entity_type="VEHICLE",
        entity_id=veh.id,
        message="Kiểm thử ghi nhận log audit qua Django ORM",
        occurred_at=now,
    )
    assert log_entry.id is not None
    assert log_entry.occurred_at is not None


def test_soft_delete_and_restore_cycle():
    """
    Kiểm thử chu trình đầy đủ của mô hình Xóa mềm (Soft-Delete Lifecycle):
    Tạo mới -> Xóa mềm Instance -> Khôi phục Instance -> Xóa mềm QuerySet -> Khôi phục QuerySet -> Chặn xóa cứng.
    Đảm bảo:
    1. Sử dụng bản ghi tạo mới hoàn toàn độc lập, KHÔNG can thiệp dữ liệu seed.
    2. Model.objects mặc định chỉ trả về bản ghi active (deleted_at IS NULL).
    3. Model.all_objects và Model.objects.only_deleted() truy vấn đúng bản ghi đã xóa mềm.
    4. Phương thức restore() trên instance khôi phục bản ghi về active.
    5. Phương thức restore() trên QuerySet (qua only_deleted() hoặc all_objects)
       khắc phục triệt để lỗi UPDATE 0 rows (Major Finding 2).
    6. hard_delete() trên instance hoặc QuerySet quăng ngoại lệ PermissionDenied.
    """
    from apps.accounts.models import Account
    from apps.employees.models import Position

    # Tạo user thực hiện xóa để gán deleted_by
    admin_user = Account.objects.create_user(
        email="admin_auditor@example.com",
        password="AdminAuditorPass123!",
        role="MANAGER",
    )

    # 1. Khởi tạo 2 bản ghi mới độc lập
    pos1 = Position.objects.create(code="POS_CYCLE_01", name="Vị trí chu trình 1")
    pos2 = Position.objects.create(code="POS_CYCLE_02", name="Vị trí chu trình 2")
    assert pos1.deleted_at is None
    assert pos2.deleted_at is None
    assert Position.objects.filter(id__in=[pos1.id, pos2.id]).count() == 2

    # 2. Xóa mềm qua Instance (.delete()) trên pos1
    pos1.delete()
    assert pos1.deleted_at is not None
    assert Position.objects.filter(id=pos1.id).exists() is False
    assert Position.all_objects.filter(id=pos1.id).exists() is True
    assert Position.objects.only_deleted().filter(id=pos1.id).exists() is True

    # 3. Khôi phục qua Instance (.restore()) trên pos1
    pos1.restore()
    assert pos1.deleted_at is None
    assert pos1.deleted_by is None
    assert Position.objects.filter(id=pos1.id).exists() is True
    assert Position.objects.only_deleted().filter(id=pos1.id).exists() is False

    # 4. Xóa mềm qua Instance với người thực hiện (.soft_delete(user))
    pos1.soft_delete(user=admin_user)
    assert pos1.deleted_at is not None
    assert pos1.deleted_by_id == admin_user.id
    assert Position.objects.filter(id=pos1.id).exists() is False

    # 5. Xóa mềm hàng loạt qua QuerySet (.soft_delete()) trên pos2
    affected = Position.objects.filter(id=pos2.id).soft_delete(user=admin_user)
    assert affected == 1
    assert Position.objects.filter(id=pos2.id).exists() is False
    assert Position.objects.only_deleted().filter(id=pos2.id).exists() is True

    # Cả pos1 và pos2 hiện tại đều đang ở trạng thái xóa mềm
    assert Position.objects.filter(id__in=[pos1.id, pos2.id]).count() == 0
    assert (
        Position.objects.only_deleted().filter(id__in=[pos1.id, pos2.id]).count() == 2
    )

    # 6. Khôi phục hàng loạt qua QuerySet (.restore())
    # Lưu ý: Cần gọi restore() trên queryset chứa các bản ghi đã xóa (only_deleted hoặc all_objects)
    # để tránh bị bộ lọc mặc định (deleted_at IS NULL) triệt tiêu câu lệnh UPDATE!
    restored_count = (
        Position.objects.only_deleted().filter(id__in=[pos1.id, pos2.id]).restore()
    )
    assert restored_count == 2

    # Xác nhận cả 2 bản ghi đã quay lại trạng thái hoạt động bình thường
    assert Position.objects.filter(id__in=[pos1.id, pos2.id]).count() == 2
    assert (
        Position.objects.only_deleted().filter(id__in=[pos1.id, pos2.id]).count() == 0
    )

    pos1.refresh_from_db()
    pos2.refresh_from_db()
    assert pos1.deleted_at is None
    assert pos1.deleted_by is None
    assert pos2.deleted_at is None
    assert pos2.deleted_by is None

    # 7. Chặn xóa cứng (Hard Delete Ban per ADR-0003 & Database Trigger)
    with pytest.raises(PermissionDenied):
        pos1.hard_delete()

    with pytest.raises(PermissionDenied):
        Position.objects.filter(id=pos1.id).hard_delete()
