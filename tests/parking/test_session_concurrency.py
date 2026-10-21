"""
Test suite cho Defect F2 (Concurrency & Zero Raw Database Error Leakage)
Bao gồm:
1. Concurrency test 20 threads x distinct plates, lặp lại 5 lần (100/100 HTTP 201 Created với session_code phân biệt).
2. Hardened exception test: unmapped IntegrityError/DatabaseError trả về MSG-4.5.1-M03, HTTP 500, details {}.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import DatabaseError, IntegrityError, connections
from rest_framework import status
from rest_framework.test import APIClient, APIRequestFactory

from apps.accounts.models import Account
from apps.core.exceptions import custom_exception_handler
from apps.parking.models import ParkingGate


@pytest.fixture
def test_employee():
    emp, _ = Account.objects.get_or_create(
        email="f2_tester@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def active_entry_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào F2 Test", direction="IN", is_active=True
        )
    return gate


@pytest.mark.django_db(transaction=True)
class TestF2SessionCodeConcurrency:
    """
    Test F2.1: 20 luồng đồng thời check-in 20 biển số xe phân biệt, lặp lại 5 lần liên tiếp.
    Kỳ vọng: 100/100 request đạt HTTP 201 Created với session_code hoàn toàn phân biệt.
    """

    def test_20_threads_distinct_plates_5_iterations(
        self, test_employee, active_entry_gate
    ):
        total_runs = 5
        threads_per_run = 20

        for run_idx in range(1, total_runs + 1):
            barrier = threading.Barrier(threads_per_run)
            results = []

            def worker_check_in(plate_str, cur_barrier=barrier):
                try:
                    client = APIClient()
                    client.force_authenticate(user=test_employee)
                    cur_barrier.wait()  # Kích hoạt tất cả 20 luồng tại cùng một microsecond
                    res = client.post(
                        "/api/v1/parking/sessions/check-in/",
                        {
                            "license_plate": plate_str,
                            "entry_gate_id": active_entry_gate.id,
                            "recognition_source": "MANUAL",
                        },
                        format="json",
                    )
                    return res.status_code, getattr(res, "data", {})
                finally:
                    connections.close_all()

            # Tạo 20 biển số phân biệt cho vòng chạy này
            run_uid = uuid.uuid4().hex[:4].upper()
            plates = [f"51F-{run_uid}{i:02d}.99" for i in range(threads_per_run)]

            with ThreadPoolExecutor(max_workers=threads_per_run) as executor:
                futures = [executor.submit(worker_check_in, p) for p in plates]
                for f in futures:
                    results.append(f.result())

            # 1. Kiểm tra 100% (20/20) trả về HTTP 201 Created
            statuses = [r[0] for r in results]
            status_201_count = statuses.count(status.HTTP_201_CREATED)
            assert status_201_count == threads_per_run, (
                f"Run {run_idx}/{total_runs} failed: Only {status_201_count}/{threads_per_run} succeeded. "
                f"Statuses: {statuses}, Errors: {[r[1] for r in results if r[0] != 201]}"
            )

            # 2. Kiểm tra tất cả session_code sinh ra đều phân biệt
            session_codes = []
            for r in results:
                payload = r[1]
                if isinstance(payload, dict) and "session" in payload:
                    code = payload["session"].get("session_code")
                elif isinstance(payload, dict):
                    code = payload.get("session_code")
                else:
                    code = None
                session_codes.append(code)

            assert len(set(session_codes)) == threads_per_run, (
                f"Run {run_idx}/{total_runs} failed: Duplicate session_code found: {session_codes}"
            )

            # 3. Kiểm tra định dạng session_code đúng mẫu #PK-YYYYMMDD-NNN
            for code in session_codes:
                assert code and code.startswith("#PK-"), f"Invalid code format: {code}"


@pytest.mark.django_db
class TestF2DatabaseErrorLeakageHarden:
    """
    Test F2.2: Kiểm tra custom_exception_handler tuyệt đối không rò rỉ raw SQL / database error.
    """

    def test_unmapped_integrity_error_returns_msg_451_m03_and_500(self):
        raw_sql_error = (
            'duplicate key value violates unique constraint "uq_custom_unmapped"\n'
            "DETAIL: Key (col)=(val) already exists."
        )
        exc = IntegrityError(raw_sql_error)

        factory = APIRequestFactory()
        request = factory.post("/api/v1/parking/sessions/check-in/")
        context = {"request": request, "view": None}

        response = custom_exception_handler(exc, context)

        assert response is not None
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.data.get("code") == "MSG-4.5.1-M03"
        assert response.data.get("message") == "lỗi kết nối"
        assert response.data.get("details") == {}
        # Khẳng định tuyệt đối không có vết tích chuỗi SQL trong body
        body_str = str(response.data)
        assert "duplicate key" not in body_str
        assert "uq_custom_unmapped" not in body_str
        assert "violates" not in body_str

    def test_unmapped_database_error_returns_msg_451_m03_and_500(self):
        exc = DatabaseError("server closed the connection unexpectedly")

        factory = APIRequestFactory()
        request = factory.get("/api/v1/parking/sessions/")
        context = {"request": request, "view": None}

        response = custom_exception_handler(exc, context)

        assert response is not None
        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.data.get("code") == "MSG-4.5.1-M03"
        assert response.data.get("message") == "lỗi kết nối"
        assert response.data.get("details") == {}
