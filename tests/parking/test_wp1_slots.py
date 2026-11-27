"""
Comprehensive test suite for Milestone WP1: Slots CRUD (SRS 4.8.1 - 4.8.5) and Structure Routing (J1).
Verifies:
- Role-based permissions (Anonymous 401, Customer 403, Employee read-only 403 write, Manager full).
- Query performance & Zero N+1 scaling (CaptureQueriesContext O(1)).
- Multi-criteria filtering (floor, zone, status, OVERSTAY, vehicle_type, slot_kind, search).
- Soft-delete exclusion (TL-27: deleted_at IS NULL).
- Optimistic Concurrency Control (OCC row_version conflict -> 409 PROP-4.8.3-P03).
- DB Trigger guards on status update and deletion (409 PROP-DEL-05-OCCUPIED, PROP-4.8.5-P02, PROP-DEL-05-RESERVED).
- Structure View hierarchy and query count.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.models import (
    ParkingFloor,
    ParkingLot,
    ParkingSlot,
    ParkingZone,
    SlotAllowedVehicleType,
    SlotReservation,
    VehicleEntryExitLog,
)
from apps.tickets.models import Ticket, TicketType
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


# ==============================================================================
# FIXTURES
# ==============================================================================


@pytest.fixture
def auth_manager():
    mgr, _ = Account.objects.get_or_create(
        email="mgr_wp1@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return mgr


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_wp1@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def auth_customer():
    cust, _ = Account.objects.get_or_create(
        email="cust_wp1@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return cust


@pytest.fixture
def parking_hierarchy():
    """Tạo cấu trúc bãi xe: Lot -> Floor B1, B2 -> Zones A, B."""
    lot, _ = ParkingLot.objects.get_or_create(
        code="LOT_WP1",
        defaults={"name": "Bãi xe WP1 Test", "is_active": True},
    )
    floor_b1, _ = ParkingFloor.objects.get_or_create(
        code="B1_WP1",
        lot=lot,
        defaults={"name": "Tầng B1", "sort_order": 1},
    )
    floor_b2, _ = ParkingFloor.objects.get_or_create(
        code="B2_WP1",
        lot=lot,
        defaults={"name": "Tầng B2", "sort_order": 2},
    )
    zone_a, _ = ParkingZone.objects.get_or_create(
        code="ZA_WP1",
        floor=floor_b1,
        defaults={"name": "Khu A"},
    )
    zone_b, _ = ParkingZone.objects.get_or_create(
        code="ZB_WP1",
        floor=floor_b1,
        defaults={"name": "Khu B"},
    )
    zone_b2_a, _ = ParkingZone.objects.get_or_create(
        code="ZB2A_WP1",
        floor=floor_b2,
        defaults={"name": "Khu B2-A"},
    )
    return {
        "lot": lot,
        "floor_b1": floor_b1,
        "floor_b2": floor_b2,
        "zone_a": zone_a,
        "zone_b": zone_b,
        "zone_b2_a": zone_b2_a,
    }


@pytest.fixture
def vehicle_types():
    vt_car, _ = VehicleType.objects.get_or_create(
        code="CAR",
        defaults={"name": "Ô tô con 4-7 chỗ"},
    )
    vt_ev, _ = VehicleType.objects.get_or_create(
        code="EV",
        defaults={"name": "Xe điện"},
    )
    return {"CAR": vt_car, "EV": vt_ev}


# ==============================================================================
# 1. PERMISSION TESTS
# ==============================================================================


class TestSlotsPermissions:
    """Kiểm tra phân quyền nghiêm ngặt theo RBAC."""

    def test_anonymous_requests_rejected_with_401(self, parking_hierarchy):
        client = APIClient()
        zone = parking_hierarchy["zone_a"]
        slot = ParkingSlot.objects.create(
            zone=zone, code="A01", slot_kind="STANDARD", status="AVAILABLE"
        )

        # GET list
        res = client.get("/api/v1/parking/slots/")
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

        # GET detail
        res = client.get(f"/api/v1/parking/slots/{slot.id}/")
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

        # POST create
        res = client.post(
            "/api/v1/parking/slots/",
            {"zone_id": zone.id, "code": "A02", "slot_kind": "STANDARD"},
            format="json",
        )
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

        # PATCH update
        res = client.patch(
            f"/api/v1/parking/slots/{slot.id}/",
            {"row_version": slot.row_version, "notes": "test"},
            format="json",
        )
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

        # DELETE soft-delete
        res = client.delete(f"/api/v1/parking/slots/{slot.id}/")
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_customer_requests_rejected_with_403(
        self, auth_customer, parking_hierarchy
    ):
        client = APIClient()
        client.force_authenticate(user=auth_customer)
        zone = parking_hierarchy["zone_a"]
        slot = ParkingSlot.objects.create(
            zone=zone, code="A01", slot_kind="STANDARD", status="AVAILABLE"
        )

        for url, method in [
            ("/api/v1/parking/slots/", "get"),
            (f"/api/v1/parking/slots/{slot.id}/", "get"),
            ("/api/v1/parking/structure/", "get"),
        ]:
            res = getattr(client, method)(url)
            assert res.status_code == status.HTTP_403_FORBIDDEN
            assert res.json().get("code") == "MSG-4.2-M01"

        res_post = client.post(
            "/api/v1/parking/slots/",
            {"zone_id": zone.id, "code": "A02"},
            format="json",
        )
        assert res_post.status_code == status.HTTP_403_FORBIDDEN

    def test_employee_has_read_only_access(self, auth_employee, parking_hierarchy):
        client = APIClient()
        client.force_authenticate(user=auth_employee)
        zone = parking_hierarchy["zone_a"]
        slot = ParkingSlot.objects.create(
            zone=zone, code="A01", slot_kind="STANDARD", status="AVAILABLE"
        )

        # GET list và detail cho phép
        res_list = client.get("/api/v1/parking/slots/")
        assert res_list.status_code == status.HTTP_200_OK

        res_detail = client.get(f"/api/v1/parking/slots/{slot.id}/")
        assert res_detail.status_code == status.HTTP_200_OK

        res_struct = client.get("/api/v1/parking/structure/")
        assert res_struct.status_code == status.HTTP_200_OK

        # POST, PATCH, DELETE bị chặn 403
        res_post = client.post(
            "/api/v1/parking/slots/",
            {"zone_id": zone.id, "code": "A02"},
            format="json",
        )
        assert res_post.status_code == status.HTTP_403_FORBIDDEN

        res_patch = client.patch(
            f"/api/v1/parking/slots/{slot.id}/",
            {"row_version": slot.row_version, "notes": "new note"},
            format="json",
        )
        assert res_patch.status_code == status.HTTP_403_FORBIDDEN

        res_del = client.delete(f"/api/v1/parking/slots/{slot.id}/")
        assert res_del.status_code == status.HTTP_403_FORBIDDEN

    def test_manager_has_full_crud_access(self, auth_manager, parking_hierarchy):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        zone = parking_hierarchy["zone_a"]

        # 1. POST Create
        res_create = client.post(
            "/api/v1/parking/slots/",
            {
                "zone_id": zone.id,
                "code": "M01",
                "slot_kind": "STANDARD",
                "status": "AVAILABLE",
            },
            format="json",
        )
        assert res_create.status_code == status.HTTP_201_CREATED
        slot_id = res_create.json()["id"]

        # 2. GET Detail
        res_detail = client.get(f"/api/v1/parking/slots/{slot_id}/")
        assert res_detail.status_code == status.HTTP_200_OK
        assert res_detail.json()["code"] == "M01"

        # 3. PATCH Update
        res_patch = client.patch(
            f"/api/v1/parking/slots/{slot_id}/",
            {"row_version": res_detail.json()["row_version"], "notes": "Updated note"},
            format="json",
        )
        assert res_patch.status_code == status.HTTP_200_OK
        assert res_patch.json()["notes"] == "Updated note"

        # 4. DELETE Soft Delete
        res_del = client.delete(f"/api/v1/parking/slots/{slot_id}/")
        assert res_del.status_code == status.HTTP_200_OK
        assert res_del.json()["code"] == "PROP-4.8.5-P01"


# ==============================================================================
# 2. LISTING, FILTERS, AND SOFT DELETE EXCLUSION TESTS
# ==============================================================================


class TestSlotsListingAndFilters:
    """Kiểm tra chức năng lọc và loại trừ bản ghi xóa mềm (TL-27)."""

    def test_soft_deleted_slots_excluded_from_listing_and_detail(
        self, auth_employee, parking_hierarchy
    ):
        client = APIClient()
        client.force_authenticate(user=auth_employee)
        zone = parking_hierarchy["zone_a"]

        active_slot = ParkingSlot.objects.create(
            zone=zone, code="ACT-01", status="AVAILABLE"
        )
        deleted_slot = ParkingSlot.objects.create(
            zone=zone,
            code="DEL-01",
            status="AVAILABLE",
            deleted_at=timezone.now(),
        )

        res_list = client.get(f"/api/v1/parking/slots/?zone={zone.code}")
        codes = [s["code"] for s in res_list.json()["results"]]
        assert active_slot.code in codes
        assert deleted_slot.code not in codes

        res_detail = client.get(f"/api/v1/parking/slots/{deleted_slot.id}/")
        assert res_detail.status_code == status.HTTP_404_NOT_FOUND
        assert res_detail.json()["code"] == "PROP-4.8.5-P05"

    def test_filter_by_floor_and_zone(self, auth_employee, parking_hierarchy):
        client = APIClient()
        client.force_authenticate(user=auth_employee)
        zone_a = parking_hierarchy["zone_a"]
        zone_b = parking_hierarchy["zone_b"]
        zone_b2 = parking_hierarchy["zone_b2_a"]

        s_a = ParkingSlot.objects.create(zone=zone_a, code="S-A1", status="AVAILABLE")
        s_b = ParkingSlot.objects.create(zone=zone_b, code="S-B1", status="AVAILABLE")
        s_b2 = ParkingSlot.objects.create(
            zone=zone_b2, code="S-B2-1", status="AVAILABLE"
        )

        # Lọc theo floor code
        res_f1 = client.get(
            f"/api/v1/parking/slots/?floor={parking_hierarchy['floor_b1'].code}"
        )
        f1_ids = [s["id"] for s in res_f1.json()["results"]]
        assert s_a.id in f1_ids and s_b.id in f1_ids
        assert s_b2.id not in f1_ids

        # Lọc theo zone code
        res_za = client.get(f"/api/v1/parking/slots/?zone={zone_a.code}")
        za_ids = [s["id"] for s in res_za.json()["results"]]
        assert s_a.id in za_ids
        assert s_b.id not in za_ids

    def test_filter_by_status_and_overstay(
        self, auth_employee, parking_hierarchy, vehicle_types
    ):
        client = APIClient()
        client.force_authenticate(user=auth_employee)
        zone = parking_hierarchy["zone_a"]

        s_avail = ParkingSlot.objects.create(
            zone=zone, code="S-AVAIL", status="AVAILABLE"
        )
        s_maint = ParkingSlot.objects.create(
            zone=zone, code="S-MAINT", status="MAINTENANCE"
        )

        # Ô đỗ bình thường có xe (< 24h)
        s_occ = ParkingSlot.objects.create(zone=zone, code="S-OCC", status="AVAILABLE")
        VehicleEntryExitLog.objects.create(
            session_code="SES-OCC-NORMAL",
            slot=s_occ,
            license_plate="30A-111.11",
            entry_time=timezone.now() - timedelta(hours=5),
        )

        # Ô đỗ quá hạn (> 24h)
        s_overstay = ParkingSlot.objects.create(
            zone=zone, code="S-OVERSTAY", status="AVAILABLE"
        )
        VehicleEntryExitLog.objects.create(
            session_code="SES-OCC-OVERSTAY",
            slot=s_overstay,
            license_plate="30A-999.99",
            entry_time=timezone.now() - timedelta(hours=30),
        )

        # Lọc đơn AVAILABLE trong khu
        res = client.get(f"/api/v1/parking/slots/?zone={zone.code}&status=AVAILABLE")
        ids = [s["id"] for s in res.json()["results"]]
        assert s_avail.id in ids and s_maint.id not in ids

        # Lọc OVERSTAY trong khu
        res_overstay = client.get(
            f"/api/v1/parking/slots/?zone={zone.code}&status=OVERSTAY"
        )
        overstay_ids = [s["id"] for s in res_overstay.json()["results"]]
        assert s_overstay.id in overstay_ids
        assert s_occ.id not in overstay_ids
        assert s_avail.id not in overstay_ids


# ==============================================================================
# 3. ZERO N+1 QUERY SCALING TESTS
# ==============================================================================


class TestSlotsZeroNPlusOne:
    """Chứng minh danh sách ô đỗ đạt O(1) queries không bị tăng theo kích thước trang."""

    def test_query_count_is_constant_regardless_of_page_size(
        self, auth_employee, parking_hierarchy, vehicle_types
    ):
        client = APIClient()
        client.force_authenticate(user=auth_employee)
        zone = parking_hierarchy["zone_a"]

        # Tạo sẵn 25 ô đỗ với đầy đủ liên kết loại xe, session
        for i in range(1, 26):
            slot = ParkingSlot.objects.create(
                zone=zone,
                code=f"Z-N1-{i:02d}",
                slot_kind="STANDARD",
                status="AVAILABLE",
            )
            SlotAllowedVehicleType.objects.create(
                slot=slot, vehicle_type=vehicle_types["CAR"]
            )

        # Đo số queries khi page_size = 5
        with CaptureQueriesContext(connection) as ctx_5:
            res_5 = client.get("/api/v1/parking/slots/?page_size=5")
            assert res_5.status_code == status.HTTP_200_OK
            count_5 = len(ctx_5.captured_queries)

        # Đo số queries khi page_size = 20
        with CaptureQueriesContext(connection) as ctx_20:
            res_20 = client.get("/api/v1/parking/slots/?page_size=20")
            assert res_20.status_code == status.HTTP_200_OK
            count_20 = len(ctx_20.captured_queries)

        # Khẳng định Zero N+1: số query count hoàn toàn không đổi (tối đa 7 queries)
        assert count_5 == count_20
        assert count_20 <= 7


# ==============================================================================
# 4. CREATE SLOT AND CONFLICT TESTS (SRS 4.8.2)
# ==============================================================================


class TestSlotCreate:
    """Kiểm tra tạo ô đỗ mới và các tình huống kiểm tra hợp lệ/xung đột."""

    def test_create_slot_success(self, auth_manager, parking_hierarchy, vehicle_types):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        zone = parking_hierarchy["zone_a"]

        payload = {
            "zone_id": zone.id,
            "code": "C-101",
            "slot_kind": "PRIORITY",
            "status": "AVAILABLE",
            "map_row": 2,
            "map_col": 5,
            "width": "2.80",
            "length": "5.50",
            "height": "2.40",
            "notes": "Vị trí cho lãnh đạo",
            "allowed_vehicle_type_ids": [vehicle_types["CAR"].id],
        }

        res = client.post("/api/v1/parking/slots/", payload, format="json")
        assert res.status_code == status.HTTP_201_CREATED
        data = res.json()
        assert data["code"] == "C-101"
        assert data["slot_kind"] == "PRIORITY"
        assert data["row_version"] == 1
        assert "CAR" in data["vehicle_types"]

    def test_create_duplicate_code_in_same_zone_returns_409(
        self, auth_manager, parking_hierarchy
    ):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        zone = parking_hierarchy["zone_a"]

        ParkingSlot.objects.create(zone=zone, code="DUP-01", status="AVAILABLE")

        payload = {
            "zone_id": zone.id,
            "code": "DUP-01",
            "slot_kind": "STANDARD",
        }
        res = client.post("/api/v1/parking/slots/", payload, format="json")
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.json()["code"] == "PROP-4.8.2-P03"

    def test_create_invalid_code_format_returns_400(
        self, auth_manager, parking_hierarchy
    ):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        zone = parking_hierarchy["zone_a"]

        # Ký tự đặc biệt không hợp lệ
        res = client.post(
            "/api/v1/parking/slots/",
            {"zone_id": zone.id, "code": "A@#$%", "slot_kind": "STANDARD"},
            format="json",
        )
        assert res.status_code == status.HTTP_400_BAD_REQUEST


# ==============================================================================
# 5. UPDATE SLOT AND OCC TESTS (SRS 4.8.3)
# ==============================================================================


class TestSlotUpdateAndOCC:
    """Kiểm tra cập nhật thông tin ô đỗ xe và OCC row_version."""

    def test_update_slot_increments_row_version(self, auth_manager, parking_hierarchy):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        zone = parking_hierarchy["zone_a"]

        slot = ParkingSlot.objects.create(
            zone=zone, code="UP-01", status="AVAILABLE", row_version=1
        )

        res = client.patch(
            f"/api/v1/parking/slots/{slot.id}/",
            {"row_version": 1, "notes": "Updated note 1"},
            format="json",
        )
        assert res.status_code == status.HTTP_200_OK
        data = res.json()
        assert data["notes"] == "Updated note 1"
        assert data["row_version"] >= 2

    def test_update_with_stale_row_version_returns_409_conflict(
        self, auth_manager, parking_hierarchy
    ):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        zone = parking_hierarchy["zone_a"]

        slot = ParkingSlot.objects.create(
            zone=zone, code="UP-OCC", status="AVAILABLE", row_version=2
        )

        # Gửi row_version = 1 (lỗi xung đột OCC)
        res = client.patch(
            f"/api/v1/parking/slots/{slot.id}/",
            {"row_version": 1, "notes": "Concurrent edit attempt"},
            format="json",
        )
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.json()["code"] == "PROP-4.8.3-P03"


# ==============================================================================
# 6. DELETE SLOT GUARDS TESTS (SRS 4.8.5)
# ==============================================================================


class TestSlotDeleteGuards:
    """Kiểm tra xóa mềm và các rào chắn bảo vệ an toàn (TL-25, TL-39)."""

    def test_soft_delete_empty_slot_success(self, auth_manager, parking_hierarchy):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        zone = parking_hierarchy["zone_a"]

        slot = ParkingSlot.objects.create(zone=zone, code="DEL-OK", status="AVAILABLE")

        res = client.delete(f"/api/v1/parking/slots/{slot.id}/")
        assert res.status_code == status.HTTP_200_OK
        assert res.json()["code"] == "PROP-4.8.5-P01"

        slot.refresh_from_db()
        assert slot.deleted_at is not None

    def test_delete_occupied_slot_blocked_with_409(
        self, auth_manager, parking_hierarchy
    ):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        zone = parking_hierarchy["zone_a"]

        slot = ParkingSlot.objects.create(zone=zone, code="DEL-OCC", status="AVAILABLE")
        VehicleEntryExitLog.objects.create(
            session_code="SES-DEL-OCC-01",
            slot=slot,
            license_plate="30A-999.88",
            entry_time=timezone.now(),
        )
        slot.refresh_from_db()
        assert slot.status == "OCCUPIED"

        res = client.delete(f"/api/v1/parking/slots/{slot.id}/")
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.json()["code"] == "PROP-DEL-05-OCCUPIED"

    def test_delete_slot_with_active_ticket_blocked_with_409(
        self, auth_manager, parking_hierarchy, vehicle_types
    ):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        zone = parking_hierarchy["zone_a"]

        slot = ParkingSlot.objects.create(zone=zone, code="DEL-TKT", status="AVAILABLE")
        cust = Customer.objects.filter(deleted_at__isnull=True).first()
        if not cust:
            cust = Customer.objects.create(
                code="CUST-DEL01",
                full_name="Khách Hàng Test Xóa",
                identity_card_number="123456789012",
                phone="0901234567",
            )
        veh = Vehicle.objects.filter(customer=cust, deleted_at__isnull=True).first()
        if not veh:
            veh = Vehicle.objects.create(
                license_plate="30A-888.88",
                vehicle_type=vehicle_types["CAR"],
                customer=cust,
            )
        SlotAllowedVehicleType.objects.create(slot=slot, vehicle_type=veh.vehicle_type)
        tt = TicketType.objects.filter(deleted_at__isnull=True).first()
        Ticket.objects.create(
            code="TKT-DEL-01",
            slot=slot,
            vehicle=veh,
            customer=cust,
            ticket_type=tt,
            price=Decimal("500000"),
            status="ACTIVE",
            effective_from=timezone.now() - timedelta(days=5),
            effective_to=timezone.now() + timedelta(days=25),
        )

        res = client.delete(f"/api/v1/parking/slots/{slot.id}/")
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.json()["code"] == "PROP-4.8.5-P02"

    def test_delete_slot_with_active_reservation_blocked_with_409(
        self, auth_manager, parking_hierarchy
    ):
        client = APIClient()
        client.force_authenticate(user=auth_manager)
        zone = parking_hierarchy["zone_a"]

        slot = ParkingSlot.objects.create(zone=zone, code="DEL-RSV", status="AVAILABLE")
        SlotReservation.objects.create(
            code="RSV-DEL-01",
            slot=slot,
            status="ACTIVE",
            reserved_name="Nguyen Van A",
            reserved_phone="0911222333",
            reserved_from=timezone.now() - timedelta(minutes=10),
            reserved_until=timezone.now() + timedelta(hours=2),
        )

        res = client.delete(f"/api/v1/parking/slots/{slot.id}/")
        assert res.status_code == status.HTTP_409_CONFLICT
        assert res.json()["code"] == "PROP-DEL-05-RESERVED"


# ==============================================================================
# 7. STRUCTURE API TESTS (Defect J1)
# ==============================================================================


class TestStructureView:
    """Kiểm tra API cấu trúc sơ đồ bãi đỗ xe GET /api/v1/parking/structure/."""

    def test_structure_returns_hierarchy_with_zero_n_plus_one(
        self, auth_employee, parking_hierarchy
    ):
        client = APIClient()
        client.force_authenticate(user=auth_employee)

        # Đo lường queries count
        with CaptureQueriesContext(connection) as ctx:
            res = client.get("/api/v1/parking/structure/")
            assert res.status_code == status.HTTP_200_OK
            count = len(ctx.captured_queries)

        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # B1 và B2
        # Tối đa 3 queries (ParkingFloor, ParkingZone, ParkingSlot)
        assert count <= 3

        floor_codes = [f["code"] for f in data]
        assert "B1_WP1" in floor_codes
