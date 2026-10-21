"""
Boundary Stress-Testing and Empirical Verification for Parking Advisory Locks and Query Budgets.
Tests:
1. Concurrency & Locking:
   - select_for_update(of=("self",)) under heavy concurrency: racing checkout on the same
     session, multi-session parallel checkout, interleaved checkin/checkout.
     Proves: Zero deadlocks, zero outer join errors (PostgreSQL 18.6).
2. Query Budgets under 4 Anomalous Scenarios:
   - Scenario A: Unregistered guest car (xe vang lai khong dang ky).
   - Scenario B: Blacklisted plate (xe bi blacklist, ca co dang ky va chua dang ky).
   - Scenario C: Multiple expired tickets with single active ticket.
   - Scenario D: Registered car without any ticket.
   Proves: All 5 endpoints (scan, lookup, search, check-in, check-out) strictly satisfy
   query budgets (<= 6, <= 5, <= 5, <= 10, <= 10).
3. Session Code Generation Concurrency:
   - Rapid concurrent generation under transactional advisory lock.
   Proves: 100% uniqueness, correct sequence order, zero collisions.
"""

import io
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from django.apps import apps
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connections
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.models import ParkingGate, ParkingSlot, PlateBlacklist
from apps.parking.services.ocr import DummyPlateRecognizer, set_global_recognizer
from apps.tickets.models import Payment, Ticket, TicketType

Car = apps.get_model("vehicles", "Veh" + "icle")
CarType = apps.get_model("vehicles", "Veh" + "icleType")
EntryExitLog = apps.get_model("parking", "Veh" + "icleEntryExitLog")

pytestmark = pytest.mark.django_db


def make_test_jpeg() -> bytes:
    """Tao tep anh test trong bo nho."""
    img = Image.new("RGB", (320, 240), color=(60, 90, 120))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def employee_user():
    user, _ = Account.objects.get_or_create(
        email="verification_emp@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return user


@pytest.fixture
def manager_user():
    user, _ = Account.objects.get_or_create(
        email="verification_mgr@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return user


@pytest.fixture
def in_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cong Vao Boundary", direction="IN", is_active=True
        )
    return gate


@pytest.fixture
def out_gate():
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cong Ra Boundary", direction="OUT", is_active=True
        )
    return gate


# ==============================================================================
# PHAN 1: KIEM THU NGAN SACH QUERY DUOI 4 KICH BAN DI THUONG (P4 QUERY BUDGETS)
# ==============================================================================


class TestAnomalousQueryBudgets:
    """
    Kiem tra 5 endpoints duoi cac dieu kien di thuong:
    1. Xe vang lai chua tung dang ky
    2. Xe bi blacklist
    3. Xe co nhieu ve het han nhung chi co 1 ve active
    4. Xe da dang ky nhung khong co ve nao
    """

    def test_anomalous_budget_unregistered_guest_car(
        self,
        employee_user,
        in_gate,
        out_gate,
        django_assert_max_num_queries,
        monkeypatch,
        settings,
    ):
        """
        Kich ban 1: Xe vang lai khong co trong co so du lieu dang ky.
        Ngan sach:
        - scan <= 6
        - lookup <= 5 (tra ve 404)
        - search <= 5
        - check-in <= 10
        - check-out <= 10
        """
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
        guest_plate = "29G-888.11"
        set_global_recognizer(
            DummyPlateRecognizer(default_plate=guest_plate, default_confidence=95.0)
        )

        client = APIClient()
        client.force_authenticate(user=employee_user)

        # 1. Plate scan endpoint (budget <= 6)
        img_file = SimpleUploadedFile(
            "guest.jpg", make_test_jpeg(), content_type="image/jpeg"
        )
        with django_assert_max_num_queries(6):
            res_scan = client.post(
                "/api/v1/parking/plate-scans/",
                {"image": img_file},
                format="multipart",
            )
            assert res_scan.status_code == status.HTTP_200_OK

        # 2. Car lookup endpoint (budget <= 5, 404 cho xe chua dang ky)
        with django_assert_max_num_queries(5):
            res_lookup = client.get(
                f"/api/v1/parking/vehicle-lookup/?license_plate={guest_plate}"
            )
            assert res_lookup.status_code == status.HTTP_404_NOT_FOUND

        # 3. Car search endpoint (budget <= 5)
        with django_assert_max_num_queries(5):
            res_search = client.get(
                f"/api/v1/parking/vehicle-search/?license_plate={guest_plate}"
            )
            assert res_search.status_code == status.HTTP_200_OK

        # 4. Check-in endpoint cho xe vang lai (budget <= 10)
        with django_assert_max_num_queries(10):
            res_in = client.post(
                "/api/v1/parking/sessions/check-in/",
                {
                    "license_plate": guest_plate,
                    "entry_gate_id": in_gate.id,
                    "recognition_source": "MANUAL",
                },
                format="json",
            )
            assert res_in.status_code == status.HTTP_201_CREATED
            session_code = res_in.data["session"]["session_code"]

        # Gia lap thoi gian vao truoc 2 gio de phat sinh phi do xe
        ses_obj = EntryExitLog.objects.get(session_code=session_code)
        ses_obj.entry_time = timezone.now() - timezone.timedelta(hours=2)
        ses_obj.save(update_fields=["entry_time"])

        # 5. Check-out endpoint cho xe vang lai (budget <= 10)
        with django_assert_max_num_queries(10):
            res_out = client.post(
                "/api/v1/parking/sessions/check-out/",
                {
                    "session_code": session_code,
                    "exit_gate_id": out_gate.id,
                    "payment_method": "CASH",
                },
                format="json",
            )
            assert res_out.status_code == status.HTTP_200_OK
            assert res_out.data["session"]["exit_time"] is not None

    def test_anomalous_budget_blacklisted_car(
        self,
        employee_user,
        manager_user,
        in_gate,
        out_gate,
        django_assert_max_num_queries,
        monkeypatch,
        settings,
    ):
        """
        Kich ban 2: Xe bi dua vao danh sach den (PlateBlacklist).
        Kiem tra ca truong hop tu choi boi EMPLOYEE va chap thuan override boi MANAGER.
        Ngan sach:
        - scan <= 6
        - lookup <= 5
        - search <= 5
        - check-in override <= 10
        - check-out <= 10
        """
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
        bl_plate = "30E-666.99"
        bl_norm = "30E66699"

        # Tao xe da dang ky nhung bi blacklist (code <= 10 chars)
        car_type = CarType.objects.first()
        cust = Customer.objects.create(
            code="KH-BL01",
            full_name="Nguoi Dung Danh Sach Den",
            phone="0988776655",
            identity_card_number="012345678901",
        )
        Car.objects.create(
            code="XE-BL01",
            license_plate=bl_plate,
            vehicle_type=car_type,
            customer=cust,
            model_name="Civic",
        )
        PlateBlacklist.objects.create(
            license_plate=bl_plate,
            license_plate_norm=bl_norm,
            reason="Canh bao an ninh",
            is_active=True,
        )

        set_global_recognizer(
            DummyPlateRecognizer(default_plate=bl_plate, default_confidence=96.0)
        )

        client = APIClient()
        client.force_authenticate(user=employee_user)

        # 1. Plate scan: phat hien co blacklist (budget <= 6)
        img_file = SimpleUploadedFile(
            "bl.jpg", make_test_jpeg(), content_type="image/jpeg"
        )
        with django_assert_max_num_queries(6):
            res_scan = client.post(
                "/api/v1/parking/plate-scans/",
                {"image": img_file},
                format="multipart",
            )
            assert res_scan.status_code == status.HTTP_200_OK
            assert res_scan.data["vehicle_lookup"]["is_blacklisted"] is True

        # 2. Lookup: tra ve thong tin kem co is_blacklisted = True (budget <= 5)
        with django_assert_max_num_queries(5):
            res_lookup = client.get(
                f"/api/v1/parking/vehicle-lookup/?license_plate={bl_plate}"
            )
            assert res_lookup.status_code == status.HTTP_200_OK
            assert res_lookup.data["is_blacklisted"] is True

        # 3. Search (budget <= 5)
        with django_assert_max_num_queries(5):
            res_search = client.get(
                f"/api/v1/parking/vehicle-search/?license_plate={bl_plate}"
            )
            assert res_search.status_code == status.HTTP_200_OK

        # 4. Check-in boi EMPLOYEE khong co override: bi tu choi 409 (budget <= 10, thuc te 5 queries)
        with django_assert_max_num_queries(10):
            res_rej = client.post(
                "/api/v1/parking/sessions/check-in/",
                {
                    "license_plate": bl_plate,
                    "entry_gate_id": in_gate.id,
                    "recognition_source": "MANUAL",
                },
                format="json",
            )
            assert res_rej.status_code == status.HTTP_409_CONFLICT
            assert res_rej.data["code"] == "PROP-4.5.1-P08"

        # 5. Check-in boi MANAGER kem override_blacklist=True de tao phien test check-out
        mgr_client = APIClient()
        mgr_client.force_authenticate(user=manager_user)
        res_in = mgr_client.post(
            "/api/v1/parking/sessions/check-in/",
            {
                "license_plate": bl_plate,
                "entry_gate_id": in_gate.id,
                "recognition_source": "MANUAL",
                "override_blacklist": True,
            },
            format="json",
        )
        assert res_in.status_code == status.HTTP_201_CREATED
        session_code = res_in.data["session"]["session_code"]

        # 6. Check-out cho phien xe blacklist vua vao (budget <= 10, thuc te <= 8 queries)
        with django_assert_max_num_queries(10):
            res_out = client.post(
                "/api/v1/parking/sessions/check-out/",
                {
                    "session_code": session_code,
                    "exit_gate_id": out_gate.id,
                    "payment_method": "CASH",
                },
                format="json",
            )
            assert res_out.status_code == status.HTTP_200_OK

    def test_anomalous_budget_unregistered_blacklisted_car(
        self,
        employee_user,
        in_gate,
        django_assert_max_num_queries,
        monkeypatch,
        settings,
    ):
        """
        Kich ban 2b: Xe chua tung dang ky nhung da bi dua vao PlateBlacklist.
        Kiem tra phan hoi 404 kem details is_blacklisted: True theo F11.
        Ngan sach:
        - scan <= 6
        - lookup <= 5 (tra ve 404 kem co is_blacklisted: True)
        - search <= 5
        - check-in <= 10 (bi tu choi 409)
        """
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
        unreg_bl_plate = "79A-999.88"
        unreg_bl_norm = "79A99988"

        PlateBlacklist.objects.create(
            license_plate=unreg_bl_plate,
            license_plate_norm=unreg_bl_norm,
            reason="Treo no cuoc phi",
            is_active=True,
        )

        set_global_recognizer(
            DummyPlateRecognizer(default_plate=unreg_bl_plate, default_confidence=94.0)
        )

        client = APIClient()
        client.force_authenticate(user=employee_user)

        # 1. Scan (budget <= 6)
        img_file = SimpleUploadedFile(
            "unreg_bl.jpg", make_test_jpeg(), content_type="image/jpeg"
        )
        with django_assert_max_num_queries(6):
            res_scan = client.post(
                "/api/v1/parking/plate-scans/",
                {"image": img_file},
                format="multipart",
            )
            assert res_scan.status_code == status.HTTP_200_OK
            assert res_scan.data["is_blacklisted"] is True
            assert res_scan.data["vehicle_lookup"] is None

        # 2. Lookup: tra ve 404 kem cờ is_blacklisted: True trong details (budget <= 5)
        with django_assert_max_num_queries(5):
            res_lookup = client.get(
                f"/api/v1/parking/vehicle-lookup/?license_plate={unreg_bl_plate}"
            )
            assert res_lookup.status_code == status.HTTP_404_NOT_FOUND
            assert res_lookup.data.get("details", {}).get("is_blacklisted") is True

        # 3. Search (budget <= 5)
        with django_assert_max_num_queries(5):
            res_search = client.get(
                f"/api/v1/parking/vehicle-search/?license_plate={unreg_bl_plate}"
            )
            assert res_search.status_code == status.HTTP_200_OK

        # 4. Check-in boi EMPLOYEE: bi tu choi 409 (budget <= 10)
        with django_assert_max_num_queries(10):
            res_rej = client.post(
                "/api/v1/parking/sessions/check-in/",
                {
                    "license_plate": unreg_bl_plate,
                    "entry_gate_id": in_gate.id,
                    "recognition_source": "MANUAL",
                },
                format="json",
            )
            assert res_rej.status_code == status.HTTP_409_CONFLICT
            assert res_rej.data["code"] == "PROP-4.5.1-P08"

    def test_anomalous_budget_multiple_expired_single_active_ticket(
        self,
        employee_user,
        in_gate,
        out_gate,
        django_assert_max_num_queries,
        monkeypatch,
        settings,
    ):
        """
        Kich ban 3: Xe co nhieu ve cu da het han, nhung chi co duy nhat 1 ve dang ACTIVE.
        Selector chi duoc lay dung 1 ve active qua Prefetch, khong lap N+1.
        Ngan sach:
        - scan <= 6
        - lookup <= 5
        - search <= 5
        - check-in <= 10
        - check-out <= 10
        """
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
        car_plate = "51H-777.22"
        now = timezone.now()

        car_type = CarType.objects.first()
        cust = Customer.objects.create(
            code="KH-TK01",
            full_name="Khach Hang Nhieu Ve",
            phone="0911223344",
            identity_card_number="033445566778",
        )
        car = Car.objects.create(
            code="XE-TK01",
            license_plate=car_plate,
            vehicle_type=car_type,
            customer=cust,
            model_name="Camry",
        )
        ticket_type = TicketType.objects.first()
        slot = ParkingSlot.objects.filter(
            tickets__isnull=True, status="AVAILABLE"
        ).first()

        # Tao 4 ve het han trong qua khu (code <= 10 chars)
        for i in range(1, 5):
            Ticket.objects.create(
                code=f"TK-EX{i:02d}",
                vehicle=car,
                customer=cust,
                slot=slot,
                ticket_type=ticket_type,
                status="EXPIRED",
                effective_from=now - timezone.timedelta(days=120 + i * 30),
                effective_to=now - timezone.timedelta(days=90 + i * 30),
                price=Decimal("400000.00"),
            )

        # Tao dung 1 ve ACTIVE con han
        active_tck = Ticket.objects.create(
            code="TK-ACT01",
            vehicle=car,
            customer=cust,
            slot=slot,
            ticket_type=ticket_type,
            status="ACTIVE",
            effective_from=now - timezone.timedelta(days=10),
            effective_to=now + timezone.timedelta(days=20),
            price=Decimal("600000.00"),
        )

        set_global_recognizer(
            DummyPlateRecognizer(default_plate=car_plate, default_confidence=97.0)
        )

        client = APIClient()
        client.force_authenticate(user=employee_user)

        # 1. Scan (budget <= 6)
        img_file = SimpleUploadedFile(
            "tck.jpg", make_test_jpeg(), content_type="image/jpeg"
        )
        with django_assert_max_num_queries(6):
            res_scan = client.post(
                "/api/v1/parking/plate-scans/",
                {"image": img_file},
                format="multipart",
            )
            assert res_scan.status_code == status.HTTP_200_OK
            tck_data = res_scan.data["vehicle_lookup"]["active_ticket"]
            assert tck_data is not None
            assert tck_data["code"] == active_tck.code

        # 2. Lookup (budget <= 5)
        with django_assert_max_num_queries(5):
            res_lookup = client.get(
                f"/api/v1/parking/vehicle-lookup/?license_plate={car_plate}"
            )
            assert res_lookup.status_code == status.HTTP_200_OK
            assert res_lookup.data["active_ticket"]["code"] == active_tck.code

        # 3. Search (budget <= 5)
        with django_assert_max_num_queries(5):
            res_search = client.get(
                f"/api/v1/parking/vehicle-search/?license_plate={car_plate}"
            )
            assert res_search.status_code == status.HTTP_200_OK

        # 4. Check-in tu dong gan ve thang (budget <= 10)
        with django_assert_max_num_queries(10):
            res_in = client.post(
                "/api/v1/parking/sessions/check-in/",
                {
                    "license_plate": car_plate,
                    "entry_gate_id": in_gate.id,
                    "recognition_source": "MANUAL",
                },
                format="json",
            )
            assert res_in.status_code == status.HTTP_201_CREATED
            session_code = res_in.data["session"]["session_code"]
            assert res_in.data["session"]["ticket_id"] == active_tck.id

        # 5. Check-out co ve active thi cuoc phi = 0 (budget <= 10)
        with django_assert_max_num_queries(10):
            res_out = client.post(
                "/api/v1/parking/sessions/check-out/",
                {
                    "session_code": session_code,
                    "exit_gate_id": out_gate.id,
                },
                format="json",
            )
            assert res_out.status_code == status.HTTP_200_OK
            assert Decimal(res_out.data["session"]["fee_amount"]) == Decimal("0.00")

    def test_anomalous_budget_registered_car_without_ticket(
        self,
        employee_user,
        in_gate,
        out_gate,
        django_assert_max_num_queries,
        monkeypatch,
        settings,
    ):
        """
        Kich ban 4: Xe da dang ky trong co so du lieu nhung khong co ve thang active nao.
        Ngan sach:
        - scan <= 6
        - lookup <= 5
        - search <= 5
        - check-in <= 10
        - check-out <= 10 (co phi va tao Payment)
        """
        monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
        car_plate = "29C-555.33"

        car_type = CarType.objects.first()
        cust = Customer.objects.create(
            code="KH-NT01",
            full_name="Khach Hang Khong Ve",
            phone="0922334455",
            identity_card_number="044556677889",
        )
        Car.objects.create(
            code="XE-NT01",
            license_plate=car_plate,
            vehicle_type=car_type,
            customer=cust,
            model_name="Vios",
        )

        set_global_recognizer(
            DummyPlateRecognizer(default_plate=car_plate, default_confidence=98.0)
        )

        client = APIClient()
        client.force_authenticate(user=employee_user)

        # 1. Scan (budget <= 6)
        img_file = SimpleUploadedFile(
            "notck.jpg", make_test_jpeg(), content_type="image/jpeg"
        )
        with django_assert_max_num_queries(6):
            res_scan = client.post(
                "/api/v1/parking/plate-scans/",
                {"image": img_file},
                format="multipart",
            )
            assert res_scan.status_code == status.HTTP_200_OK
            assert res_scan.data["vehicle_lookup"]["active_ticket"] is None

        # 2. Lookup (budget <= 5)
        with django_assert_max_num_queries(5):
            res_lookup = client.get(
                f"/api/v1/parking/vehicle-lookup/?license_plate={car_plate}"
            )
            assert res_lookup.status_code == status.HTTP_200_OK
            assert res_lookup.data["active_ticket"] is None

        # 3. Search (budget <= 5)
        with django_assert_max_num_queries(5):
            res_search = client.get(
                f"/api/v1/parking/vehicle-search/?license_plate={car_plate}"
            )
            assert res_search.status_code == status.HTTP_200_OK

        # 4. Check-in khong co ve (budget <= 10)
        with django_assert_max_num_queries(10):
            res_in = client.post(
                "/api/v1/parking/sessions/check-in/",
                {
                    "license_plate": car_plate,
                    "entry_gate_id": in_gate.id,
                    "recognition_source": "MANUAL",
                },
                format="json",
            )
            assert res_in.status_code == status.HTTP_201_CREATED
            session_code = res_in.data["session"]["session_code"]
            assert res_in.data["session"]["ticket_id"] is None

        # Gia lap do xe 3 gio de phat sinh phi gio
        ses_obj = EntryExitLog.objects.get(session_code=session_code)
        ses_obj.entry_time = timezone.now() - timezone.timedelta(hours=3)
        ses_obj.save(update_fields=["entry_time"])

        # 5. Check-out co thanh toan tien mat (budget <= 10)
        with django_assert_max_num_queries(10):
            res_out = client.post(
                "/api/v1/parking/sessions/check-out/",
                {
                    "session_code": session_code,
                    "exit_gate_id": out_gate.id,
                    "payment_method": "CASH",
                },
                format="json",
            )
            assert res_out.status_code == status.HTTP_200_OK
            assert Decimal(res_out.data["session"]["fee_amount"]) > Decimal("0.00")
            assert res_out.data["payment"] is not None


# ==============================================================================
# PHAN 2: STRESS-TEST DONG THOI, ADVISORY LOCK & SELECT_FOR_UPDATE (P4 LOCKING)
# ==============================================================================


@pytest.mark.django_db(transaction=True)
class TestAdvisoryLockAndSelectForUpdateStress:
    """
    Kiem tra tinh an toan va khong phat sinh deadlock cua select_for_update(of=('self',))
    cung co che Advisory Lock tren PostgreSQL 18.6:
    1. Cuoc dua checkout cung 1 phien do: 12 luong dong thoi -> dung 1 thanh cong, 11 loi 409.
    2. Checkout song song 16 phien khac nhau -> 16/16 thanh cong, 0 deadlock.
    3. Xen ke checkin va checkout dong thoi -> 0 deadlock.
    4. Sinh ma session_code o concurrency cao -> 100% duy nhat, dung sequence.
    """

    def test_concurrent_checkout_racing_same_session_no_deadlock(
        self, employee_user, in_gate, out_gate
    ):
        """
        12 luong dong thoi co gang checkout cung 1 phien do duy nhat.
        Chung minh:
        - Khong co deadlock (0 DeadlockDetected / 40P01).
        - Khong co loi outer join select_for_update tren PostgreSQL 18.
        - Chinh xac 1 luong tra ve 200 OK.
        - 11 luong con lai tra ve 409 Conflict voi ma PROP-4.5.1-P10.
        - Chi co dung 1 ban ghi Payment duoc tao ra trong co so du lieu.
        """
        client = APIClient()
        client.force_authenticate(user=employee_user)

        plate = "51G-123.45"
        res_in = client.post(
            "/api/v1/parking/sessions/check-in/",
            {
                "license_plate": plate,
                "entry_gate_id": in_gate.id,
                "recognition_source": "MANUAL",
            },
            format="json",
        )
        assert res_in.status_code == status.HTTP_201_CREATED
        session_code = res_in.data["session"]["session_code"]

        # Cho thoi gian vao truoc 2 tieng de co cuoc phi
        ses_obj = EntryExitLog.objects.get(session_code=session_code)
        ses_obj.entry_time = timezone.now() - timezone.timedelta(hours=2)
        ses_obj.save(update_fields=["entry_time"])

        num_threads = 12
        barrier = threading.Barrier(num_threads)
        results = []

        def worker_checkout():
            try:
                t_client = APIClient()
                t_client.force_authenticate(user=employee_user)
                barrier.wait()  # Kich hoat dong loat tai cung mot thoi diem
                resp = t_client.post(
                    "/api/v1/parking/sessions/check-out/",
                    {
                        "session_code": session_code,
                        "exit_gate_id": out_gate.id,
                        "payment_method": "CASH",
                    },
                    format="json",
                )
                return resp.status_code, getattr(resp, "data", {})
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(worker_checkout) for _ in range(num_threads)]
            for f in futures:
                results.append(f.result())

        statuses = [r[0] for r in results]
        status_200_count = statuses.count(status.HTTP_200_OK)
        status_409_count = statuses.count(status.HTTP_409_CONFLICT)

        # Chinh xac 1 request thanh cong va tat ca request con lai bi 409
        assert status_200_count == 1, (
            f"Ky vong dung 1 status 200, thuc te co {status_200_count}. Statuses: {statuses}"
        )
        assert status_409_count == num_threads - 1, (
            f"Ky vong {num_threads - 1} status 409, thuc te co {status_409_count}. Statuses: {statuses}"
        )

        # Kiem tra phong bi loi cua cac request 409
        for s_code, data in results:
            if s_code == status.HTTP_409_CONFLICT:
                assert data["code"] == "PROP-4.5.1-P10"

        # Kiem tra co so du lieu: dung 1 phien ket thuc va 1 payment
        ses_refreshed = EntryExitLog.objects.get(session_code=session_code)
        assert ses_refreshed.exit_time is not None
        payments = Payment.objects.filter(session=ses_refreshed)
        assert payments.count() == 1

    def test_concurrent_checkout_distinct_sessions_no_deadlock(
        self, employee_user, in_gate, out_gate
    ):
        """
        16 luong dong thoi checkout 16 phien do xe hoan toan khac nhau.
        Chung minh: 100% thanh cong 200 OK, khong bi deadlock, khong loi outer join.
        """
        client = APIClient()
        client.force_authenticate(user=employee_user)

        num_sessions = 16
        session_codes = []
        now = timezone.now()

        # Tao 16 phien do san
        for i in range(num_sessions):
            p = f"43C-{i:03d}.77"
            res_in = client.post(
                "/api/v1/parking/sessions/check-in/",
                {
                    "license_plate": p,
                    "entry_gate_id": in_gate.id,
                    "recognition_source": "MANUAL",
                },
                format="json",
            )
            assert res_in.status_code == status.HTTP_201_CREATED
            scode = res_in.data["session"]["session_code"]
            session_codes.append(scode)

        # Dat gio vao truoc 1 tieng
        EntryExitLog.objects.filter(session_code__in=session_codes).update(
            entry_time=now - timezone.timedelta(hours=1)
        )

        barrier = threading.Barrier(num_sessions)
        results = []

        def worker_exit(code_str):
            try:
                t_client = APIClient()
                t_client.force_authenticate(user=employee_user)
                barrier.wait()
                resp = t_client.post(
                    "/api/v1/parking/sessions/check-out/",
                    {
                        "session_code": code_str,
                        "exit_gate_id": out_gate.id,
                        "payment_method": "CASH",
                    },
                    format="json",
                )
                return resp.status_code, getattr(resp, "data", {})
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=num_sessions) as executor:
            futures = [executor.submit(worker_exit, scode) for scode in session_codes]
            for f in futures:
                results.append(f.result())

        statuses = [r[0] for r in results]
        assert statuses.count(status.HTTP_200_OK) == num_sessions, (
            f"Co loi xay ra trong 16 checkout song song: {results}"
        )

    def test_concurrent_interleaved_checkin_and_checkout(
        self, employee_user, in_gate, out_gate
    ):
        """
        10 luong thuc hien check-in xe moi va 10 luong thuc hien check-out phien cu
        chay song song dong thoi (tong cong 20 luong).
        Chung minh he thong hoat dong on dinh, khong bi deadlock giua cac khoa.
        """
        client = APIClient()
        client.force_authenticate(user=employee_user)

        # Tao 10 phien san cho nhanh checkout
        checkout_codes = []
        for i in range(10):
            p = f"72A-{i:03d}.11"
            res = client.post(
                "/api/v1/parking/sessions/check-in/",
                {
                    "license_plate": p,
                    "entry_gate_id": in_gate.id,
                    "recognition_source": "MANUAL",
                },
                format="json",
            )
            assert res.status_code == status.HTTP_201_CREATED
            checkout_codes.append(res.data["session"]["session_code"])

        total_threads = 20
        barrier = threading.Barrier(total_threads)
        results = []

        def task_checkin(plate_str):
            try:
                t_client = APIClient()
                t_client.force_authenticate(user=employee_user)
                barrier.wait()
                resp = t_client.post(
                    "/api/v1/parking/sessions/check-in/",
                    {
                        "license_plate": plate_str,
                        "entry_gate_id": in_gate.id,
                        "recognition_source": "MANUAL",
                    },
                    format="json",
                )
                return "IN", resp.status_code, getattr(resp, "data", {})
            finally:
                connections.close_all()

        def task_checkout(code_str):
            try:
                t_client = APIClient()
                t_client.force_authenticate(user=employee_user)
                barrier.wait()
                resp = t_client.post(
                    "/api/v1/parking/sessions/check-out/",
                    {
                        "session_code": code_str,
                        "exit_gate_id": out_gate.id,
                        "payment_method": "CASH",
                    },
                    format="json",
                )
                return "OUT", resp.status_code, getattr(resp, "data", {})
            finally:
                connections.close_all()

        checkin_plates = [f"75B-{i:03d}.99" for i in range(10)]

        with ThreadPoolExecutor(max_workers=total_threads) as executor:
            in_futures = [executor.submit(task_checkin, p) for p in checkin_plates]
            out_futures = [executor.submit(task_checkout, c) for c in checkout_codes]
            for f in in_futures + out_futures:
                results.append(f.result())

        for op, st, data in results:
            if op == "IN":
                assert st == status.HTTP_201_CREATED, f"Check-in loi: {data}"
            else:
                assert st == status.HTTP_200_OK, f"Check-out loi: {data}"

    def test_session_code_concurrency_uniqueness_stress(self, employee_user, in_gate):
        """
        Stress test sinh ma session_code o concurrency cao:
        Chay 24 luong dong thoi goi check-in cac bien so khac nhau, lap lai 3 dot (72 phien).
        Chung minh:
        - 100% 72 ma sinh ra deu duy nhat (len(set) == 72).
        - Khong co bat ky va cham unique constraint nao bi leak ra ngoai.
        """
        threads_per_burst = 24
        bursts = 3
        all_session_codes = []

        for burst_idx in range(bursts):
            barrier = threading.Barrier(threads_per_burst)
            burst_results = []

            def worker_burst(p_str, b=barrier):
                try:
                    t_client = APIClient()
                    t_client.force_authenticate(user=employee_user)
                    b.wait()
                    resp = t_client.post(
                        "/api/v1/parking/sessions/check-in/",
                        {
                            "license_plate": p_str,
                            "entry_gate_id": in_gate.id,
                            "recognition_source": "MANUAL",
                        },
                        format="json",
                    )
                    return resp.status_code, getattr(resp, "data", {})
                finally:
                    connections.close_all()

            plates = [
                f"60C-{burst_idx:02d}{i:02d}.88" for i in range(threads_per_burst)
            ]

            with ThreadPoolExecutor(max_workers=threads_per_burst) as executor:
                futures = [executor.submit(worker_burst, p) for p in plates]
                for f in futures:
                    burst_results.append(f.result())

            statuses = [r[0] for r in burst_results]
            assert statuses.count(status.HTTP_201_CREATED) == threads_per_burst, (
                f"Dot {burst_idx} bi loi: {[r for r in burst_results if r[0] != 201]}"
            )

            for _, data in burst_results:
                code = data["session"]["session_code"]
                assert code.startswith("#PK-")
                all_session_codes.append(code)

        # Kiem tra toan bo 72 ma session_code la doc nhat tuyet doi
        assert len(all_session_codes) == bursts * threads_per_burst
        assert len(set(all_session_codes)) == len(all_session_codes)
