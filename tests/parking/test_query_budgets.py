"""
Unit & Integration tests for SQL Query Budgets.
Verifies strict database query budgets using django_assert_max_num_queries:
- POST /api/v1/parking/plate-scans/ <= 5 queries
- GET /api/v1/parking/vehicle-lookup/ <= 5 queries
- GET /api/v1/parking/vehicle-search/ <= 5 queries
- POST /api/v1/parking/sessions/check-in/ <= 10 queries
- POST /api/v1/parking/sessions/check-out/ <= 9 queries
"""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from PIL import Image
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.parking.models import ParkingGate, VehicleEntryExitLog
from apps.parking.services.ocr import DummyPlateRecognizer, set_global_recognizer
from apps.vehicles.models import Vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="budget_emp@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def entry_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào Budget Test", direction="IN", is_active=True
        )
    return gate


@pytest.fixture
def exit_gate():
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng ra Budget Test", direction="OUT", is_active=True
        )
    return gate


def generate_test_image(format_name: str = "JPEG") -> bytes:
    """Tạo tệp ảnh hợp lệ trong bộ nhớ phục vụ kiểm thử."""
    img = Image.new("RGB", (320, 240), color=(73, 109, 137))
    buf = io.BytesIO()
    img.save(buf, format=format_name)
    return buf.getvalue()


def test_query_budget_plate_scan(
    auth_employee, django_assert_max_num_queries, monkeypatch, settings
):
    """
    POST /api/v1/parking/plate-scans/
    Ngân sách: <= 5 queries (thực tế: auth user + combined vehicle context <= 4 queries).
    """
    monkeypatch.setattr(settings, "PARKING_OCR_ENGINE", "dummy")
    set_global_recognizer(
        DummyPlateRecognizer(default_plate="51K-992.14", default_confidence=98.5)
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    img_bytes = generate_test_image("JPEG")
    upload_file = SimpleUploadedFile(
        "test_scan.jpg", img_bytes, content_type="image/jpeg"
    )

    with django_assert_max_num_queries(5):
        response = client.post(
            "/api/v1/parking/plate-scans/",
            {"image": upload_file},
            format="multipart",
        )
        assert response.status_code == status.HTTP_200_OK


def test_query_budget_vehicle_lookup(auth_employee, django_assert_max_num_queries):
    """
    GET /api/v1/parking/vehicle-lookup/
    Ngân sách: <= 5 queries (thực tế: auth user + vehicle context <= 4 queries).
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Tra cứu xe đã đăng ký
    registered_plate = (
        Vehicle.objects.filter(deleted_at__isnull=True)
        .values_list("license_plate", flat=True)
        .first()
        or "51K-992.14"
    )

    with django_assert_max_num_queries(5):
        response = client.get(
            f"/api/v1/parking/vehicle-lookup/?license_plate={registered_plate}"
        )
        assert response.status_code == status.HTTP_200_OK

    # 2. Tra cứu xe chưa đăng ký
    with django_assert_max_num_queries(5):
        response = client.get(
            "/api/v1/parking/vehicle-lookup/?license_plate=99Z-999.99"
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


def test_query_budget_vehicle_search(auth_employee, django_assert_max_num_queries):
    """
    GET /api/v1/parking/vehicle-search/
    Ngân sách: <= 5 queries (thực tế: count + select page + 3 batch hydration queries = 5 queries).
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Tìm kiếm tổng hợp q=
    with django_assert_max_num_queries(5):
        response = client.get("/api/v1/parking/vehicle-search/?q=Toyota&page_size=20")
        assert response.status_code == status.HTTP_200_OK

    # 2. Tìm kiếm tường minh customer_name=
    with django_assert_max_num_queries(5):
        response = client.get(
            "/api/v1/parking/vehicle-search/?customer_name=Nguyen&page_size=20"
        )
        assert response.status_code == status.HTTP_200_OK


def test_query_budget_check_in(
    auth_employee, entry_gate, django_assert_max_num_queries
):
    """
    POST /api/v1/parking/sessions/check-in/
    Ngân sách: <= 10 queries (thực tế: 7-9 queries bao gồm gate, context, employee, lock, insert, hydrate).
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    unique_plate = f"30A-{int(timezone.now().timestamp()) % 10000:04d}.11"

    with django_assert_max_num_queries(10):
        response = client.post(
            "/api/v1/parking/sessions/check-in/",
            {
                "license_plate": unique_plate,
                "entry_gate_id": entry_gate.id,
                "recognition_source": "MANUAL",
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert "session" in response.data


def test_query_budget_check_out(
    auth_employee, entry_gate, exit_gate, django_assert_max_num_queries
):
    """
    POST /api/v1/parking/sessions/check-out/
    Ngân sách: <= 9 queries (thực tế: 6-8 queries bao gồm gate, select_for_update, payment, update, hydrate, lookup).
    """
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    unique_plate = f"43A-{int(timezone.now().timestamp()) % 10000:04d}.22"

    # Tạo phiên đỗ xe trước (check-in)
    in_resp = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": unique_plate,
            "entry_gate_id": entry_gate.id,
            "recognition_source": "MANUAL",
        },
        format="json",
    )
    assert in_resp.status_code == status.HTTP_201_CREATED
    session_code = in_resp.data["session"]["session_code"]

    # Giả lập thời gian vào trước 2 giờ để phát sinh cước phí và thanh toán
    session_obj = VehicleEntryExitLog.objects.get(session_code=session_code)
    session_obj.entry_time = timezone.now() - timezone.timedelta(hours=2)
    session_obj.save(update_fields=["entry_time"])

    # Thực hiện check-out và kiểm tra ngân sách
    with django_assert_max_num_queries(9):
        out_resp = client.post(
            "/api/v1/parking/sessions/check-out/",
            {
                "session_code": session_code,
                "exit_gate_id": exit_gate.id,
                "payment_method": "CASH",
            },
            format="json",
        )
        assert out_resp.status_code == status.HTTP_200_OK
        assert out_resp.data["session"]["exit_time"] is not None
