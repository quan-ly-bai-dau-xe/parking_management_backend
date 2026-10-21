"""
Boundary Stress Test Suite for Sessions Filter and Gate Validation.

This test suite empirically verifies:
1. Malformed and boundary query parameters for GET /api/v1/parking/sessions/:
   - Invalid datetimes: entry_time_from=abc, entry_time_to=invalid, exit_time_from=xyz, exit_time_to=xyz
   - Page size out of bounds: page_size=100000, page_size=0, page_size=-1, page_size=101
   - Page bounds: page=0, page=-5
   - Invalid status choices: status=weird, status=OPEN (case-sensitive)
   - Invalid review_status choices: review_status=weird, review_status=auto (lowercase)
   - Inverted fee range: min_fee > max_fee (min_fee=100001, max_fee=100000)
   - Negative fees: min_fee=-10, max_fee=-1
   - Inverted datetime ranges: entry_time_from > entry_time_to, exit_time_from > exit_time_to
   - Boundary valid conditions: page_size=1, page_size=100, page=1, min_fee=0, max_fee=0
   - Oversized / injection strings: license_plate over 20 chars, session_code over 50 chars
2. Unmatched URL 404 handling:
   - GET /api/v1/parking/sessions/abc/ -> returns JSON 404 envelope MSG-4.4.1-M01 (NOT HTML)
   - POST /api/v1/parking/sessions/abc/ -> returns JSON 404 envelope MSG-4.4.1-M01
   - GET /api/v1/non_existent_route/ -> returns JSON 404 envelope MSG-4.4.1-M01
3. Inactive gate rejection:
   - Check-in with parking_gate.is_active = False -> HTTP 400 PROP-GEN-P01
   - Check-out with parking_gate.is_active = False -> HTTP 400 PROP-GEN-P01
4. Strict ai_confidence bounds:
   - ai_confidence outside [0, 100] (150, -5, 100.01, -0.01, non-numeric) -> HTTP 400 PROP-GEN-P01
   - ai_confidence boundary values (0.00, 100.00) -> HTTP 201 Created and NOT clamped
5. Blacklist override permission:
   - EMPLOYEE user sends override_blacklist=True -> HTTP 403 PROP-4.5.1-P14 + SystemAlert created
   - MANAGER user sends override_blacklist=True -> HTTP 201 Created + SystemAlert created
   - EMPLOYEE user sends override_blacklist=False -> HTTP 409 PROP-4.5.1-P08
"""

import json
from decimal import Decimal

import pytest
from django.test import Client
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.audit.models import SystemAlert
from apps.parking.models import (
    ParkingGate,
    ParkingLot,
    PlateBlacklist,
    VehicleEntryExitLog,
)

pytestmark = pytest.mark.django_db


def _get_or_create_test_lot():
    lot = ParkingLot.objects.first()
    if not lot:
        lot = ParkingLot.objects.create(
            code="LOT-VERIFICATION",
            name="Bãi đỗ Verification",
            is_active=True,
        )
    return lot


@pytest.fixture
def active_entry_gate():
    lot = _get_or_create_test_lot()
    gate, _ = ParkingGate.objects.get_or_create(
        code="GATE-IN-ACT",
        defaults={
            "lot": lot,
            "name": "Cổng vào Verification",
            "direction": "IN",
            "is_active": True,
        },
    )
    return gate


@pytest.fixture
def active_exit_gate():
    lot = _get_or_create_test_lot()
    gate, _ = ParkingGate.objects.get_or_create(
        code="GATE-OUT-ACT",
        defaults={
            "lot": lot,
            "name": "Cổng ra Verification",
            "direction": "OUT",
            "is_active": True,
        },
    )
    return gate


@pytest.fixture
def inactive_entry_gate():
    lot = _get_or_create_test_lot()
    gate, _ = ParkingGate.objects.get_or_create(
        code="GATE-IN-INACT",
        defaults={
            "lot": lot,
            "name": "Cổng vào Inactive Verification",
            "direction": "IN",
            "is_active": False,
        },
    )
    return gate


@pytest.fixture
def inactive_exit_gate():
    lot = _get_or_create_test_lot()
    gate, _ = ParkingGate.objects.get_or_create(
        code="GATE-OUT-INACT",
        defaults={
            "lot": lot,
            "name": "Cổng ra Inactive Verification",
            "direction": "OUT",
            "is_active": False,
        },
    )
    return gate


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_verification_m2@parking.local",
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
        email="mgr_verification_m2@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return mgr


# =============================================================================
# PART 1: Boundary Query Parameters for GET /api/v1/parking/sessions/
# =============================================================================


@pytest.mark.parametrize(
    "query_param,expected_error_field",
    [
        ("entry_time_from=abc", "entry_time_from"),
        ("entry_time_from=9999-99-99T99:99:99", "entry_time_from"),
        ("entry_time_to=invalid_date", "entry_time_to"),
        ("exit_time_from=xyz", "exit_time_from"),
        ("exit_time_to=2026-13-45", "exit_time_to"),
        ("page_size=100000", "page_size"),
        ("page_size=0", "page_size"),
        ("page_size=-1", "page_size"),
        ("page_size=101", "page_size"),
        ("page=0", "page"),
        ("page=-5", "page"),
        ("status=weird", "status"),
        ("status=OPEN", "status"),
        ("review_status=weird", "review_status"),
        ("review_status=auto", "review_status"),
        ("min_fee=-10", "min_fee"),
        ("max_fee=-1", "max_fee"),
        ("license_plate=" + "X" * 25, "license_plate"),
        ("session_code=" + "S" * 55, "session_code"),
    ],
)
def test_sessions_filter_boundary_malformed_params_rejected(
    auth_employee, query_param, expected_error_field
):
    """Xác nhận 100% query params sai lệch trả về HTTP 400 PROP-GEN-P01 kèm trường lỗi trong details."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.get(f"/api/v1/parking/sessions/?{query_param}")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "PROP-GEN-P01"
    assert expected_error_field in resp.data["details"]


@pytest.mark.parametrize(
    "query_params,expected_error_field",
    [
        ("min_fee=100001&max_fee=100000", "min_fee"),
        ("min_fee=50000.00&max_fee=10000.00", "min_fee"),
        (
            "entry_time_from=2026-10-25T10:00:00Z&entry_time_to=2026-10-20T10:00:00Z",
            "entry_time_from",
        ),
        (
            "exit_time_from=2026-10-30T10:00:00Z&exit_time_to=2026-10-01T10:00:00Z",
            "exit_time_from",
        ),
    ],
)
def test_sessions_filter_boundary_inverted_ranges_rejected(
    auth_employee, query_params, expected_error_field
):
    """Xác nhận min_fee > max_fee và from > to đều trả về HTTP 400 PROP-GEN-P01."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.get(f"/api/v1/parking/sessions/?{query_params}")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "PROP-GEN-P01"
    assert expected_error_field in resp.data["details"]


@pytest.mark.parametrize(
    "valid_params",
    [
        "page=1&page_size=1",
        "page=1&page_size=100",
        "status=open",
        "status=closed",
        "review_status=AUTO",
        "review_status=MATCHED",
        "review_status=NEEDS_REVIEW",
        "review_status=APPROVED",
        "review_status=REJECTED",
        "min_fee=0&max_fee=0",
        "min_fee=10000&max_fee=10000",
        "entry_time_from=2026-10-01T00:00:00Z&entry_time_to=2026-10-01T00:00:00Z",
    ],
)
def test_sessions_filter_boundary_valid_params_succeed(auth_employee, valid_params):
    """Xác nhận các điều kiện biên hợp lệ (page_size=1..100, min_fee==max_fee) trả về HTTP 200 OK."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.get(f"/api/v1/parking/sessions/?{valid_params}")
    assert resp.status_code == status.HTTP_200_OK
    assert "results" in resp.data
    assert "count" in resp.data


# =============================================================================
# PART 2: Non-Existent URL 404 JSON Envelope (MSG-4.4.1-M01)
# =============================================================================


@pytest.mark.parametrize(
    "bad_url,method",
    [
        ("/api/v1/parking/sessions/abc/", "get"),
        ("/api/v1/parking/sessions/abc/", "post"),
        ("/api/v1/parking/sessions/999999/unknown_subpath/", "get"),
        ("/api/v1/does_not_exist_at_all/", "get"),
        ("/completely_random_url/", "get"),
    ],
)
def test_unmatched_url_returns_json_404_envelope(auth_employee, bad_url, method):
    """Xác nhận mọi URL không tồn tại trả về JSON 404 envelope chứa MSG-4.4.1-M01, KHÔNG trả về HTML."""
    client = Client()
    client.force_login(auth_employee)

    call_func = getattr(client, method)
    resp = call_func(bad_url)

    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert resp.headers.get("Content-Type") == "application/json"

    data = json.loads(resp.content.decode("utf-8"))
    assert data["code"] == "MSG-4.4.1-M01"
    assert data["message"] == "Không tìm thấy dữ liệu"
    assert data["details"] == {}


# =============================================================================
# PART 3: Inactive Gate Rejection (Check-in & Check-out)
# =============================================================================


def test_check_in_inactive_gate_rejected(auth_employee, inactive_entry_gate):
    """Check-in qua cổng inactive (is_active=False) bị từ chối HTTP 400 PROP-GEN-P01."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": "51A-123.45",
            "entry_gate_id": inactive_entry_gate.id,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "PROP-GEN-P01"
    assert "vô hiệu hóa" in resp.data["message"].lower()


def test_check_out_inactive_gate_rejected(
    auth_employee, active_entry_gate, inactive_exit_gate
):
    """Check-out qua cổng inactive (is_active=False) bị từ chối HTTP 400 PROP-GEN-P01."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Tạo session mở bằng cổng vào hợp lệ
    in_resp = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": "51A-999.88",
            "entry_gate_id": active_entry_gate.id,
        },
        format="json",
    )
    assert in_resp.status_code == status.HTTP_201_CREATED
    session_code = in_resp.data["session"]["session_code"]

    # 2. Check-out qua cổng ra inactive
    out_resp = client.post(
        "/api/v1/parking/sessions/check-out/",
        {
            "session_code": session_code,
            "exit_gate_id": inactive_exit_gate.id,
            "payment_method": "CASH",
        },
        format="json",
    )
    assert out_resp.status_code == status.HTTP_400_BAD_REQUEST
    assert out_resp.data["code"] == "PROP-GEN-P01"
    assert "vô hiệu hóa" in out_resp.data["message"].lower()


# =============================================================================
# PART 4: Strict ai_confidence Bounds & Non-Clamping
# =============================================================================


@pytest.mark.parametrize(
    "invalid_conf",
    [
        150,
        -5,
        100.01,
        -0.01,
        250.50,
        -100.00,
        "not_a_number",
    ],
)
def test_check_in_ai_confidence_out_of_bounds_rejected(
    auth_employee, active_entry_gate, invalid_conf
):
    """Xác nhận ai_confidence ngoài [0.00, 100.00] bị từ chối HTTP 400 PROP-GEN-P01 (không clamp)."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": "51B-777.88",
            "entry_gate_id": active_entry_gate.id,
            "ai_confidence": invalid_conf,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "PROP-GEN-P01"
    assert "ai_confidence" in resp.data["details"]


@pytest.mark.parametrize(
    "valid_conf",
    [Decimal("0.00"), Decimal("100.00"), Decimal("84.99"), Decimal("85.00")],
)
def test_check_in_ai_confidence_boundaries_preserved_without_clamping(
    auth_employee, active_entry_gate, valid_conf
):
    """Xác nhận ai_confidence tại biên [0.00, 100.00] được lưu chính xác, không bị biến đổi."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    plate = f"51B-{int(valid_conf * 10):03d}.11"
    resp = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": plate,
            "entry_gate_id": active_entry_gate.id,
            "ai_confidence": float(valid_conf),
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    saved_session = VehicleEntryExitLog.objects.get(id=resp.data["session"]["id"])
    assert saved_session.ai_confidence == valid_conf

    # Kiểm tra phân loại review_status: >= 85 -> AUTO, < 85 -> NEEDS_REVIEW
    if valid_conf >= Decimal("85.00"):
        assert saved_session.review_status == "AUTO"
    else:
        assert saved_session.review_status == "NEEDS_REVIEW"


# =============================================================================
# PART 5: Blacklist Override Permission & Dedicated Code PROP-4.5.1-P14
# =============================================================================


def test_employee_override_blacklist_forbidden_with_p14(
    auth_employee, active_entry_gate
):
    """
    Xác nhận EMPLOYEE gửi override_blacklist=True bị từ chối HTTP 403 với mã PROP-4.5.1-P14
    (thông báo 'Nhân viên không có quyền ghi đè danh sách đen.') và có SystemAlert được ghi nhận.
    """
    plate = "29A-999.99"
    PlateBlacklist.objects.filter(license_plate_norm="29A99999").delete()
    bl = PlateBlacklist.objects.create(
        license_plate=plate,
        license_plate_norm="29A99999",
        reason="Xe bị truy tìm trộm cắp",
        is_active=True,
    )

    alerts_before = SystemAlert.objects.filter(
        alert_type="BLACKLIST_PLATE", entity_id=bl.id
    ).count()

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": plate,
            "entry_gate_id": active_entry_gate.id,
            "override_blacklist": True,
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.data["code"] == "PROP-4.5.1-P14"
    assert resp.data["message"] == "Nhân viên không có quyền ghi đè danh sách đen."

    alerts_after = SystemAlert.objects.filter(
        alert_type="BLACKLIST_PLATE", entity_id=bl.id
    ).count()
    assert alerts_after == alerts_before + 1


def test_manager_override_blacklist_allowed(auth_manager, active_entry_gate):
    """
    Xác nhận MANAGER gửi override_blacklist=True được phép check-in HTTP 201 Created
    và có SystemAlert được ghi nhận.
    """
    plate = "30E-888.88"
    PlateBlacklist.objects.filter(license_plate_norm="30E88888").delete()
    bl = PlateBlacklist.objects.create(
        license_plate=plate,
        license_plate_norm="30E88888",
        reason="Xe tranh chấp bảo lãnh",
        is_active=True,
    )

    alerts_before = SystemAlert.objects.filter(
        alert_type="BLACKLIST_PLATE", entity_id=bl.id
    ).count()

    client = APIClient()
    client.force_authenticate(user=auth_manager)

    resp = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": plate,
            "entry_gate_id": active_entry_gate.id,
            "override_blacklist": True,
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["session"]["license_plate"] == plate

    alerts_after = SystemAlert.objects.filter(
        alert_type="BLACKLIST_PLATE", entity_id=bl.id
    ).count()
    assert alerts_after == alerts_before + 1


def test_employee_without_override_blacklist_rejected_409(
    auth_employee, active_entry_gate
):
    """
    Xác nhận khi không gửi override_blacklist (mặc định False), xe blacklist bị từ chối HTTP 409 PROP-4.5.1-P08.
    """
    plate = "43B-777.77"
    PlateBlacklist.objects.filter(license_plate_norm="43B77777").delete()
    PlateBlacklist.objects.create(
        license_plate=plate,
        license_plate_norm="43B77777",
        reason="Biển số bị cấm",
        is_active=True,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    resp = client.post(
        "/api/v1/parking/sessions/check-in/",
        {
            "license_plate": plate,
            "entry_gate_id": active_entry_gate.id,
            "override_blacklist": False,
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_409_CONFLICT
    assert resp.data["code"] == "PROP-4.5.1-P08"
