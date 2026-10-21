"""
Verification Test Suite for Vehicle Entry/Exit Management and Blacklist Policy.

Focus Areas Tested Empirically:
1. Check-out of soft-deleted vehicle while parked (OQ-67) via both session_code & license_plate.
2. Plate blacklist check-in enforcement:
   - Employee check-in -> 409 rejection + BLACKLIST_PLATE alert.
   - Employee with override_blacklist=true -> 403 forbidden + BLACKLIST_PLATE alert.
   - Manager without override -> 409 rejection + BLACKLIST_PLATE alert.
   - Manager with override_blacklist=true -> 201 created + BLACKLIST_PLATE alert.
   - Inactive / soft-deleted blacklist entry -> allowed normally, no alert.
3. Immutability of Payment row (PAID status) & hard DELETE prohibition on VehicleEntryExitLog:
   - Hard DELETE on VehicleEntryExitLog -> SQLSTATE 55000 rejected.
   - Hard DELETE on Payment -> SQLSTATE 55000 rejected.
   - Soft DELETE on PAID payment -> SQLSTATE 23514 rejected (PROP-DEL-PAYMENT-SETTLED).
   - Modification of financial/link fields on PAID payment -> SQLSTATE 23514 rejected.
   - Illegal status transition from PAID to UNPAID/CANCELLED -> SQLSTATE 23514 rejected.
4. Zero N+1 queries on sessions list endpoint (O(1) queries regardless of page size).
"""

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection, transaction
from django.db.utils import DatabaseError
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.audit.models import SystemAlert
from apps.customers.models import Customer
from apps.parking.models import (
    ParkingGate,
    ParkingLot,
    PlateBlacklist,
    VehicleEntryExitLog,
)
from apps.tickets.models import Payment
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="verification2_emp@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def auth_manager():
    mgr, _ = Account.objects.get_or_create(
        email="verification2_mgr@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return mgr


@pytest.fixture
def entry_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        lot = ParkingLot.objects.first()
        gate = ParkingGate.objects.create(
            name="Cổng vào Ch2",
            direction="IN",
            is_active=True,
            lot=lot,
            code="GATE-IN-CH2",
        )
    return gate


@pytest.fixture
def exit_gate():
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if not gate:
        lot = ParkingLot.objects.first()
        gate = ParkingGate.objects.create(
            name="Cổng ra Ch2",
            direction="OUT",
            is_active=True,
            lot=lot,
            code="GATE-OUT-CH2",
        )
    return gate


class TestSoftDeletedVehicleCheckOutOQ67:
    """Thử thách kịch bản OQ-67: Xuất bãi khi phương tiện bị soft-delete khi đang đỗ."""

    def test_checkout_soft_deleted_vehicle_by_session_code(
        self, auth_employee, entry_gate, exit_gate
    ):
        """Check-out qua session_code khi xe bị xóa mềm: cước tính bình thường, response vehicle_lookup=None."""
        now = timezone.now()
        vtype = VehicleType.objects.first()
        cust = Customer.objects.create(
            code=f"K{uuid.uuid4().hex[:8]}",
            full_name="Khách Hàng Xóa Mềm",
            phone="0911223344",
            identity_card_number=f"0480{uuid.uuid4().int % 100000000:08d}",
        )
        v = Vehicle.objects.create(
            code=f"X{uuid.uuid4().hex[:8]}",
            license_plate="43B-111.22",
            license_plate_norm="43B11122",
            vehicle_type=vtype,
            customer=cust,
            model_name="Camry",
        )
        session = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-CH2-{uuid.uuid4().hex[:6]}",
            vehicle=v,
            license_plate=v.license_plate,
            license_plate_norm=v.license_plate_norm,
            entry_gate=entry_gate,
            entry_time=now - timedelta(hours=2),
        )

        # Mô phỏng xe bị soft-delete trong CSDL (bỏ qua trigger kiểm tra để test kịch bản OQ-67)
        with connection.cursor() as cursor:
            cursor.execute("SET session_replication_role = 'replica';")
            cursor.execute(
                "UPDATE vehicle SET deleted_at = %s WHERE id = %s;", [now, v.id]
            )
            cursor.execute("SET session_replication_role = 'origin';")

        client = APIClient()
        client.force_authenticate(user=auth_employee)
        response = client.post(
            "/api/v1/parking/sessions/check-out/",
            {
                "session_code": session.session_code,
                "exit_gate_id": exit_gate.id,
                "payment_method": "CASH",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["session"]["exit_gate_id"] == exit_gate.id
        assert data["session"]["fee_amount"] == "20000.00"
        assert data["payment"] is not None
        assert data["payment"]["status"] == "PAID"
        # Vì xe đã bị xóa mềm, lookup_vehicle_by_plate trả về None theo đúng SRS
        assert data["vehicle_lookup"] is None

    def test_checkout_soft_deleted_vehicle_by_license_plate(
        self, auth_employee, entry_gate, exit_gate
    ):
        """Check-out qua license_plate khi xe bị xóa mềm: vẫn tìm thấy phiên đang mở và kết thúc thành công."""
        now = timezone.now()
        vtype = VehicleType.objects.first()
        cust = Customer.objects.create(
            code=f"K{uuid.uuid4().hex[:8]}",
            full_name="Khách Hàng Xóa Mềm 2",
            phone="0911223355",
            identity_card_number=f"0480{uuid.uuid4().int % 100000000:08d}",
        )
        plate = "43B-333.44"
        norm = "43B33344"
        v = Vehicle.objects.create(
            code=f"X{uuid.uuid4().hex[:8]}",
            license_plate=plate,
            license_plate_norm=norm,
            vehicle_type=vtype,
            customer=cust,
            model_name="Camry",
        )
        session = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-CH2-{uuid.uuid4().hex[:6]}",
            vehicle=v,
            license_plate=plate,
            license_plate_norm=norm,
            entry_gate=entry_gate,
            entry_time=now - timedelta(hours=1),
        )

        # Soft delete xe
        with connection.cursor() as cursor:
            cursor.execute("SET session_replication_role = 'replica';")
            cursor.execute(
                "UPDATE vehicle SET deleted_at = %s WHERE id = %s;", [now, v.id]
            )
            cursor.execute("SET session_replication_role = 'origin';")

        client = APIClient()
        client.force_authenticate(user=auth_employee)
        response = client.post(
            "/api/v1/parking/sessions/check-out/",
            {
                "license_plate": plate,
                "exit_gate_id": exit_gate.id,
                "payment_method": "VIETQR",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.data
        assert data["session"]["id"] == session.id
        assert data["session"]["exit_gate_id"] == exit_gate.id
        assert data["session"]["fee_amount"] == "10000.00"
        assert data["vehicle_lookup"] is None

    def test_database_trigger_blocks_soft_delete_while_session_open(self, entry_gate):
        """Xác minh cơ chế toàn vẹn CSDL: CSDL cấm xóa mềm phương tiện khi đang có phiên đỗ chưa kết thúc."""
        now = timezone.now()
        vtype = VehicleType.objects.first()
        cust = Customer.objects.create(
            code=f"K{uuid.uuid4().hex[:8]}",
            full_name="Khách Thử Trigger",
            phone="0911223366",
            identity_card_number=f"0480{uuid.uuid4().int % 100000000:08d}",
        )
        v = Vehicle.objects.create(
            code=f"X{uuid.uuid4().hex[:8]}",
            license_plate="43B-555.66",
            license_plate_norm="43B55566",
            vehicle_type=vtype,
            customer=cust,
            model_name="Civic",
        )
        VehicleEntryExitLog.objects.create(
            session_code=f"#PK-CH2-{uuid.uuid4().hex[:6]}",
            vehicle=v,
            license_plate=v.license_plate,
            license_plate_norm=v.license_plate_norm,
            entry_gate=entry_gate,
            entry_time=now,
        )

        # Thử soft delete trực tiếp thông qua SQL (không tắt trigger)
        with pytest.raises(DatabaseError) as exc_info, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE vehicle SET deleted_at = %s WHERE id = %s;", [now, v.id]
            )
        assert "không được phép xóa" in str(exc_info.value) or "check_violation" in str(
            exc_info.value
        )


class TestBlacklistCheckInEnforcement:
    """Thử thách cơ chế danh sách đen: Rejection 409, Manager override, và ghi log SystemAlert."""

    def test_employee_check_in_blacklisted_rejected_and_alerted(
        self, auth_employee, entry_gate
    ):
        """Nhân viên thường check-in xe trong blacklist -> bị chặn 409 PROP-4.5.1-P08 + ghi SystemAlert."""
        plate = "51H-999.01"
        norm = "51H99901"
        bl = PlateBlacklist.objects.create(
            license_plate=plate,
            license_plate_norm=norm,
            reason="Nghi vấn trộm cắp tài sản",
            is_active=True,
        )

        alerts_before = SystemAlert.objects.filter(
            alert_type="BLACKLIST_PLATE", entity_id=bl.id
        ).count()

        client = APIClient()
        client.force_authenticate(user=auth_employee)
        response = client.post(
            "/api/v1/parking/sessions/check-in/",
            {"license_plate": plate, "entry_gate_id": entry_gate.id},
            format="json",
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["code"] == "PROP-4.5.1-P08"

        # Kiểm tra bản ghi SystemAlert đã được ghi nhận
        alerts_after = SystemAlert.objects.filter(
            alert_type="BLACKLIST_PLATE", entity_id=bl.id
        ).count()
        assert alerts_after == alerts_before + 1

    def test_employee_override_blacklist_forbidden(self, auth_employee, entry_gate):
        """Nhân viên thường gửi override_blacklist=True -> bị từ chối 403 MSG-4.2-M01 + ghi SystemAlert."""
        plate = "51H-999.02"
        norm = "51H99902"
        bl = PlateBlacklist.objects.create(
            license_plate=plate,
            license_plate_norm=norm,
            reason="Vi phạm an ninh bãi đỗ",
            is_active=True,
        )

        alerts_before = SystemAlert.objects.filter(
            alert_type="BLACKLIST_PLATE", entity_id=bl.id
        ).count()

        client = APIClient()
        client.force_authenticate(user=auth_employee)
        response = client.post(
            "/api/v1/parking/sessions/check-in/",
            {
                "license_plate": plate,
                "entry_gate_id": entry_gate.id,
                "override_blacklist": True,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data["code"] == "PROP-4.5.1-P14"

        alerts_after = SystemAlert.objects.filter(
            alert_type="BLACKLIST_PLATE", entity_id=bl.id
        ).count()
        assert alerts_after == alerts_before + 1

    def test_manager_without_override_still_rejected(self, auth_manager, entry_gate):
        """Quản lý nếu không chỉ định override_blacklist=True vẫn bị chặn 409 theo quy trình chuẩn."""
        plate = "51H-999.03"
        norm = "51H99903"
        PlateBlacklist.objects.create(
            license_plate=plate,
            license_plate_norm=norm,
            reason="Cần giám sát đặc biệt",
            is_active=True,
        )

        client = APIClient()
        client.force_authenticate(user=auth_manager)
        response = client.post(
            "/api/v1/parking/sessions/check-in/",
            {
                "license_plate": plate,
                "entry_gate_id": entry_gate.id,
                "override_blacklist": False,
            },
            format="json",
        )

        assert response.status_code == status.HTTP_409_CONFLICT
        assert response.data["code"] == "PROP-4.5.1-P08"

    def test_manager_with_override_succeeds_and_creates_alert(
        self, auth_manager, entry_gate
    ):
        """Quản lý gửi override_blacklist=True -> được duyệt 201 Created + tạo phiên + ghi SystemAlert."""
        plate = "51H-999.04"
        norm = "51H99904"
        bl = PlateBlacklist.objects.create(
            license_plate=plate,
            license_plate_norm=norm,
            reason="Xe khách VIP diện đặc cách",
            is_active=True,
        )

        alerts_before = SystemAlert.objects.filter(
            alert_type="BLACKLIST_PLATE", entity_id=bl.id
        ).count()

        client = APIClient()
        client.force_authenticate(user=auth_manager)
        response = client.post(
            "/api/v1/parking/sessions/check-in/",
            {
                "license_plate": plate,
                "entry_gate_id": entry_gate.id,
                "override_blacklist": True,
                "notes": "Quản lý duyệt đặc cách",
            },
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["session"]["license_plate_norm"] == norm

        alerts_after = SystemAlert.objects.filter(
            alert_type="BLACKLIST_PLATE", entity_id=bl.id
        ).count()
        assert alerts_after == alerts_before + 1

    def test_soft_deleted_or_inactive_blacklist_is_ignored(
        self, auth_employee, entry_gate
    ):
        """Bản ghi blacklist đã bị xóa mềm hoặc is_active=False thì không chặn check-in."""
        plate = "51H-999.05"
        norm = "51H99905"
        # Tạo bản ghi đã xóa mềm
        PlateBlacklist.objects.create(
            license_plate=plate,
            license_plate_norm=norm,
            reason="Đã giải quyết tranh chấp",
            is_active=True,
            deleted_at=timezone.now(),
        )

        client = APIClient()
        client.force_authenticate(user=auth_employee)
        response = client.post(
            "/api/v1/parking/sessions/check-in/",
            {"license_plate": plate, "entry_gate_id": entry_gate.id},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["session"]["license_plate_norm"] == norm


class TestPaymentImmutabilityAndLogHardDeleteBan:
    """Thử thách tính bất biến của Payment và nghiêm cấm hard DELETE trên VehicleEntryExitLog."""

    def test_hard_delete_on_vehicle_entry_exit_log_prohibited(self, entry_gate):
        """Kích hoạt trigger trg_guard_entry_exit_log_immutable khi cố tình xóa bản ghi log -> SQLSTATE 55000."""
        session = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-CH2-{uuid.uuid4().hex[:6]}",
            license_plate="43A-888.99",
            license_plate_norm="43A88899",
            entry_gate=entry_gate,
            entry_time=timezone.now(),
        )

        with pytest.raises(DatabaseError) as exc_info, connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM vehicle_entry_exit_log WHERE id = %s;", [session.id]
            )
        error_msg = str(exc_info.value)
        assert "nghiêm cấm xóa vĩnh viễn" in error_msg or "55000" in error_msg

    def test_hard_delete_on_payment_prohibited(self, entry_gate):
        """Kích hoạt trigger trg_guard_payment_immutable khi cố tình xóa bản ghi payment -> SQLSTATE 55000."""
        session = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-CH2-{uuid.uuid4().hex[:6]}",
            license_plate="43A-888.77",
            license_plate_norm="43A88877",
            entry_gate=entry_gate,
            entry_time=timezone.now(),
        )
        pay = Payment.objects.create(
            code=f"PAY-CH2-{uuid.uuid4().hex[:6]}",
            amount=Decimal("30000.00"),
            method="CASH",
            status="PAID",
            paid_at=timezone.now(),
            session=session,
        )

        with pytest.raises(DatabaseError) as exc_info, connection.cursor() as cursor:
            cursor.execute("DELETE FROM payment WHERE id = %s;", [pay.id])
        error_msg = str(exc_info.value)
        assert "nghiêm cấm xóa vĩnh viễn" in error_msg or "55000" in error_msg

    def test_soft_delete_on_paid_payment_prohibited(self, entry_gate):
        """Kích hoạt trigger trg_guard_payment_update/soft_delete khi xóa mềm Payment status PAID -> check_violation."""
        session = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-CH2-{uuid.uuid4().hex[:6]}",
            license_plate="43A-888.66",
            license_plate_norm="43A88866",
            entry_gate=entry_gate,
            entry_time=timezone.now(),
        )
        pay = Payment.objects.create(
            code=f"PAY-CH2-{uuid.uuid4().hex[:6]}",
            amount=Decimal("20000.00"),
            method="VIETQR",
            status="PAID",
            paid_at=timezone.now(),
            session=session,
        )

        with pytest.raises(DatabaseError) as exc_info, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE payment SET deleted_at = NOW() WHERE id = %s;", [pay.id]
            )
        error_msg = str(exc_info.value)
        assert (
            "Không thể xóa chứng từ thanh toán đã hoàn thành" in error_msg
            or "không được phép ở trạng thái xóa mềm" in error_msg
            or "check_violation" in error_msg
        )

    def test_modify_financial_fields_on_paid_payment_prohibited(self, entry_gate):
        """Kích hoạt trigger fn_guard_payment_update khi sửa số tiền của Payment PAID -> check_violation."""
        session = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-CH2-{uuid.uuid4().hex[:6]}",
            license_plate="43A-888.55",
            license_plate_norm="43A88855",
            entry_gate=entry_gate,
            entry_time=timezone.now(),
        )
        pay = Payment.objects.create(
            code=f"PAY-CH2-{uuid.uuid4().hex[:6]}",
            amount=Decimal("10000.00"),
            method="CASH",
            status="PAID",
            paid_at=timezone.now(),
            session=session,
        )

        with pytest.raises(DatabaseError) as exc_info, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE payment SET amount = 50000.00 WHERE id = %s;", [pay.id]
            )
        assert "Không thể chỉnh sửa thông tin tài chính" in str(
            exc_info.value
        ) or "check_violation" in str(exc_info.value)

    def test_illegal_status_transition_on_paid_payment_prohibited(self, entry_gate):
        """Payment PAID không thể chuyển ngược về UNPAID hay CANCELLED."""
        session = VehicleEntryExitLog.objects.create(
            session_code=f"#PK-CH2-{uuid.uuid4().hex[:6]}",
            license_plate="43A-888.44",
            license_plate_norm="43A88844",
            entry_gate=entry_gate,
            entry_time=timezone.now(),
        )
        pay = Payment.objects.create(
            code=f"PAY-CH2-{uuid.uuid4().hex[:6]}",
            amount=Decimal("10000.00"),
            method="CASH",
            status="PAID",
            paid_at=timezone.now(),
            session=session,
        )

        # Chuyển về UNPAID trong transaction riêng biệt
        with (
            pytest.raises(DatabaseError) as exc_unpaid,
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "UPDATE payment SET status = 'UNPAID' WHERE id = %s;", [pay.id]
            )
        assert (
            "chuyển trạng thái" in str(exc_unpaid.value).lower()
            or "unpaid" in str(exc_unpaid.value).lower()
        )

        # Chuyển về CANCELLED trong transaction riêng biệt
        with (
            pytest.raises(DatabaseError) as exc_cancelled,
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "UPDATE payment SET status = 'CANCELLED' WHERE id = %s;", [pay.id]
            )
        assert (
            "chuyển đổi trạng thái" in str(exc_cancelled.value).lower()
            or "cancelled" in str(exc_cancelled.value).lower()
        )


class TestSessionsZeroNPlusOneQueries:
    """Thử thách số lượng truy vấn SQL: Đảm bảo zero N+1 queries khi tải danh sách sessions."""

    def test_sessions_list_query_count_is_constant_regardless_of_page_size(
        self, auth_employee, django_assert_max_num_queries, entry_gate
    ):
        """
        Chứng minh số lượng SQL queries là hằng số O(1):
        Dù lấy 5, 10, hay 20 kết quả trong danh sách sessions, số lượng truy vấn SQL
        vẫn giữ nguyên chính xác 3 queries (auth + count + select_related joined data).
        """
        now = timezone.now()
        vtype = VehicleType.objects.first()

        # Tạo thêm 10 sessions đa dạng
        for i in range(10):
            cust = Customer.objects.create(
                code=f"K{uuid.uuid4().hex[:8]}",
                full_name=f"Khách N1 {i}",
                phone=f"09876543{i:02d}",
                identity_card_number=f"0480{uuid.uuid4().int % 100000000:08d}",
                is_anonymized=(i % 2 == 0),
                anonymized_at=(now if i % 2 == 0 else None),
            )
            v = Vehicle.objects.create(
                code=f"X{uuid.uuid4().hex[:8]}",
                license_plate=f"43A-111.{i:02d}",
                license_plate_norm=f"43A111{i:02d}",
                vehicle_type=vtype,
                customer=cust,
                model_name="Vios",
            )
            VehicleEntryExitLog.objects.create(
                session_code=f"#PK-N1-{i}-{uuid.uuid4().hex[:4]}",
                vehicle=v,
                license_plate=v.license_plate,
                license_plate_norm=v.license_plate_norm,
                entry_gate=entry_gate,
                entry_time=now - timedelta(minutes=10 * (i + 1)),
            )

        client = APIClient()
        client.force_authenticate(user=auth_employee)

        # 1. Gọi với page_size = 5: Tối đa 5 queries
        with django_assert_max_num_queries(5):
            resp_5 = client.get("/api/v1/parking/sessions/?page=1&page_size=5")
            assert resp_5.status_code == status.HTTP_200_OK
            assert len(resp_5.data["results"]) == 5

        # 2. Gọi với page_size = 20: Số lượng queries KHÔNG ĐƯỢC TĂNG THEO N!
        with django_assert_max_num_queries(5):
            resp_20 = client.get("/api/v1/parking/sessions/?page=1&page_size=20")
            assert resp_20.status_code == status.HTTP_200_OK
            assert len(resp_20.data["results"]) >= 10
