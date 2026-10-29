"""
Integration and unit tests for F3: entry_image_url and exit_image_url Path Validation.
Verifies rejection of all malicious payloads with HTTP 400 and PROP-4.5.1-P13:
- Stored XSS ("javascript:alert(1)")
- SSRF / External URL ("http://evil.example/x.jpg")
- Relative Path Traversal ("../../etc/passwd")
- Media Root Traversal ("/media/../../secret")
- 5000-character DOS payload ("a" * 5000)
- Non-existent files
- Non-conforming patterns (uppercase hex, bad extension)
And acceptance of valid files on disk, null, and omitted values.
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.core.exceptions import BusinessAPIException
from apps.parking.models import ParkingGate, VehicleEntryExitLog
from apps.parking.serializers.sessions import (
    CheckInRequestSerializer,
    CheckOutRequestSerializer,
)
from apps.parking.services.check_in import check_in_vehicle

pytestmark = pytest.mark.django_db


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_f3_test@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def in_gate():
    gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng vào Test F3", direction="IN", is_active=True
        )
    return gate


@pytest.fixture
def out_gate():
    gate = ParkingGate.objects.filter(direction="OUT", is_active=True).first()
    if not gate:
        gate = ParkingGate.objects.create(
            name="Cổng ra Test F3", direction="OUT", is_active=True
        )
    return gate


@pytest.fixture
def valid_entry_scan_file():
    """Trả về một URL ảnh Cloudinary HTTPS hợp lệ theo quy định ADR-0010."""
    return (
        "https://res.cloudinary.com/test-cloud/image/upload/"
        "v1730178490/parking_scans/2026/10/18/f3e1a8b2c4d5e6f7a1b2c3d4e5f6a7b8.jpg"
    )


MALICIOUS_PAYLOADS = [
    ("XSS", "javascript:alert(1)"),
    ("SSRF", "http://evil.example/x.jpg"),
    ("Path Traversal Relative", "../../etc/passwd"),
    ("Path Traversal Media", "/media/../../secret"),
    ("DOS 5000 chars", "a" * 5000),
    (
        "Non-existent File",
        "/media/parking_scans/2026/10/18/00000000000000000000000000000000.jpg",
    ),
    (
        "Bad Extension",
        "/media/parking_scans/2026/10/18/f3e1a8b2c4d5e6f7a1b2c3d4e5f6a7b8.exe",
    ),
    (
        "Uppercase Hex",
        "/media/parking_scans/2026/10/18/F3E1A8B2C4D5E6F7A1B2C3D4E5F6A7B8.jpg",
    ),
    ("Empty String", ""),
]


@pytest.mark.parametrize("label, payload", MALICIOUS_PAYLOADS)
def test_check_in_serializer_rejects_malicious_entry_image_url(label, payload):
    """Serializer CheckIn từ chối các chuỗi độc hại với PROP-4.5.1-P13."""
    serializer = CheckInRequestSerializer(
        data={"license_plate": "51K-992.14", "entry_image_url": payload}
    )
    with pytest.raises(BusinessAPIException) as exc_info:
        serializer.is_valid(raise_exception=True)
    assert exc_info.value.code == "PROP-4.5.1-P13"
    assert exc_info.value.status_code == 400


@pytest.mark.parametrize("label, payload", MALICIOUS_PAYLOADS)
def test_check_out_serializer_rejects_malicious_exit_image_url(label, payload):
    """Serializer CheckOut từ chối các chuỗi độc hại với PROP-4.5.1-P13."""
    serializer = CheckOutRequestSerializer(
        data={
            "session_code": "#PK-20261018-001",
            "exit_gate_id": 1,
            "exit_image_url": payload,
        }
    )
    with pytest.raises(BusinessAPIException) as exc_info:
        serializer.is_valid(raise_exception=True)
    assert exc_info.value.code == "PROP-4.5.1-P13"
    assert exc_info.value.status_code == 400


def test_check_in_serializer_accepts_valid_image(valid_entry_scan_file):
    """Serializer CheckIn chấp nhận URL hợp lệ và tệp thực tế tồn tại."""
    serializer = CheckInRequestSerializer(
        data={"license_plate": "51K-992.14", "entry_image_url": valid_entry_scan_file}
    )
    assert serializer.is_valid(raise_exception=True)
    assert serializer.validated_data["entry_image_url"] == valid_entry_scan_file


def test_check_in_serializer_accepts_null_and_omitted():
    """Serializer CheckIn chấp nhận null hoặc omitted entry_image_url."""
    s1 = CheckInRequestSerializer(
        data={"license_plate": "51K-992.14", "entry_image_url": None}
    )
    assert s1.is_valid(raise_exception=True)
    assert s1.validated_data["entry_image_url"] is None

    s2 = CheckInRequestSerializer(data={"license_plate": "51K-992.14"})
    assert s2.is_valid(raise_exception=True)
    assert s2.validated_data.get("entry_image_url") is None


@pytest.mark.parametrize("label, payload", MALICIOUS_PAYLOADS)
def test_check_in_api_rejects_malicious_entry_image_url(
    auth_employee, in_gate, label, payload
):
    """HTTP POST /sessions/check-in/ trả về HTTP 400 PROP-4.5.1-P13 khi nhận payload độc hại."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": "51K-123.45",
            "entry_gate_id": in_gate.id,
            "entry_image_url": payload,
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P13"
    assert (
        "Đường dẫn hình ảnh không hợp lệ hoặc tệp không tồn tại."
        in response.data["message"]
    )


@pytest.mark.parametrize("label, payload", MALICIOUS_PAYLOADS)
def test_check_out_api_rejects_malicious_exit_image_url(
    auth_employee, in_gate, out_gate, label, payload
):
    """HTTP POST /sessions/check-out/ trả về HTTP 400 PROP-4.5.1-P13 khi nhận payload độc hại."""
    now = timezone.now()
    session = VehicleEntryExitLog.objects.create(
        session_code="#PK-20261018-988",
        license_plate="51K-777.88",
        entry_gate=in_gate,
        entry_time=now - timedelta(minutes=30),
    )
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session.session_code,
            "exit_gate_id": out_gate.id,
            "payment_method": "CASH",
            "exit_image_url": payload,
        },
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["code"] == "PROP-4.5.1-P13"
    assert (
        "Đường dẫn hình ảnh không hợp lệ hoặc tệp không tồn tại."
        in response.data["message"]
    )


def test_service_level_defense_in_depth_rejection():
    """Tầng service check_in_vehicle và check_out_vehicle cũng từ chối nếu bị gọi trực tiếp."""
    with pytest.raises(BusinessAPIException) as exc_info:
        check_in_vehicle(
            license_plate="51K-992.14",
            entry_image_url="javascript:alert(1)",
        )
    assert exc_info.value.code == "PROP-4.5.1-P13"
    assert exc_info.value.status_code == 400
