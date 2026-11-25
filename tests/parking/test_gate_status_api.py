"""
Integration tests for Gate Worker Status & Telemetry API (Round 88/89, TL-70, F1/F2 Fixes).
Endpoint: GET /api/v1/parking/gates/

Verifies:
- Read-only fields worker_online (bool) and last_auto_event (telemetry object or null).
- Role-based permissions (anonymous -> 401, CUSTOMER -> 403, EMPLOYEE -> 200, MANAGER -> 200).
- Truthful liveness via PostgreSQL advisory locks (pg_locks / mock fallback):
  * True when GateAdvisoryLock is actively held by a worker.
  * False when GateAdvisoryLock is not held or released (worker crash/stop).
  * camera_status dynamically mapped to 'OFFLINE' when worker is offline (pure-read, no DB UPDATE).
  * row_version and updated_at on parking_gate are strictly unchanged (no trigger firing).
  * Idle worker without ActivityLog events for >60s remains worker_online: True while lock is held.
- last_auto_event extraction solely from ActivityLog (cache completely removed):
  * Parsed from JSON payload in ActivityLog message.
  * Parsed from structured text in ActivityLog message.
  * Cache entries are completely ignored.
  * Correct fields: action, license_plate_masked, reason, occurred_at.
- Query filters: direction ('IN', 'OUT') and is_active ('true', 'false').
"""

import json

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.audit.models import ActivityLog
from apps.parking.gate_worker.locks import (
    GateAdvisoryLock,
    clear_mock_lock_registry,
    get_active_gate_worker_lock_ids,
)
from apps.parking.models import ParkingGate
from apps.parking.serializers.gates import ParkingGateSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_gate_state():
    """Ensure cache and mock locks are clean before and after each test."""
    cache.clear()
    clear_mock_lock_registry()
    yield
    cache.clear()
    clear_mock_lock_registry()


@pytest.fixture
def auth_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_gate_status@parking.local",
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
        email="mgr_gate_status@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return mgr


@pytest.fixture
def auth_customer():
    cust, _ = Account.objects.get_or_create(
        email="cust_gate_status@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return cust


# ==============================================================================
# Permission Guard Tests
# ==============================================================================


def test_gates_api_anonymous_denied():
    """Chưa đăng nhập -> 401 Unauthorized (MSG-4.1-M02)."""
    client = APIClient()
    response = client.get("/api/v1/parking/gates/")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED
    assert response.data["code"] == "MSG-4.1-M02"


def test_gates_api_customer_forbidden(auth_customer):
    """Khách hàng (CUSTOMER) bị từ chối truy cập -> 403 Forbidden (MSG-4.2-M01)."""
    client = APIClient()
    client.force_authenticate(user=auth_customer)
    response = client.get("/api/v1/parking/gates/")
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert response.data["code"] == "MSG-4.2-M01"


def test_gates_api_manager_allowed(auth_manager):
    """Quản lý (MANAGER) được phép truy cập -> 200 OK."""
    client = APIClient()
    client.force_authenticate(user=auth_manager)
    response = client.get("/api/v1/parking/gates/")
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.data, list)


def test_gates_api_employee_allowed(auth_employee):
    """Nhân viên (EMPLOYEE) được phép truy cập -> 200 OK."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/gates/")
    assert response.status_code == status.HTTP_200_OK
    assert isinstance(response.data, list)


# ==============================================================================
# Response Schema & Advisory Lock Liveness Tests
# ==============================================================================


def test_gates_api_contains_worker_online_and_last_auto_event(auth_employee):
    """Mỗi cổng trả về phải chứa đầy đủ trường worker_online và last_auto_event."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/gates/")

    assert response.status_code == status.HTTP_200_OK
    assert len(response.data) > 0

    for gate in response.data:
        assert "worker_online" in gate, "Missing worker_online field"
        assert isinstance(gate["worker_online"], bool)

        assert "last_auto_event" in gate, "Missing last_auto_event field"
        if gate["last_auto_event"] is not None:
            event = gate["last_auto_event"]
            assert "action" in event
            assert "license_plate_masked" in event
            assert "reason" in event
            assert "occurred_at" in event


def test_gates_api_worker_online_via_advisory_lock(auth_employee):
    """Khi GateAdvisoryLock được giữ bởi worker, worker_online là True và camera_status giữ nguyên."""
    gate = ParkingGate.objects.filter(is_active=True, camera_status="ONLINE").first()
    assert gate is not None

    with GateAdvisoryLock(gate.id):
        client = APIClient()
        client.force_authenticate(user=auth_employee)
        response = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")

        assert response.status_code == status.HTTP_200_OK
        target_gate = next((g for g in response.data if g["id"] == gate.id), None)
        assert target_gate is not None
        assert target_gate["worker_online"] is True
        assert target_gate["camera_status"] == "ONLINE"


def test_gates_api_worker_offline_when_no_advisory_lock(auth_employee):
    """
    Khi không có worker giữ lock (hoặc worker dừng/crash), worker_online là False
    và camera_status tự động map sang 'OFFLINE' ở tầng đọc, ngay cả khi trong DB là ONLINE.
    """
    gate = ParkingGate.objects.filter(is_active=True, camera_status="ONLINE").first()
    assert gate is not None

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")

    assert response.status_code == status.HTTP_200_OK
    target_gate = next((g for g in response.data if g["id"] == gate.id), None)
    assert target_gate is not None
    assert target_gate["worker_online"] is False
    assert target_gate["camera_status"] == "OFFLINE"


def test_gates_api_worker_crash_releases_lock_and_maps_camera_offline(auth_employee):
    """
    Giả lập worker bị ngắt đột ngột (crash/kill):
    Khi lock bị đóng, API ngay lập tức phản ánh worker_online=False và camera_status='OFFLINE'.
    """
    gate = ParkingGate.objects.filter(is_active=True, camera_status="ONLINE").first()
    assert gate is not None

    lock = GateAdvisoryLock(gate.id)
    assert lock.acquire() is True
    assert gate.id in get_active_gate_worker_lock_ids()

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Khi lock đang giữ -> Online
    resp1 = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")
    g1 = next(g for g in resp1.data if g["id"] == gate.id)
    assert g1["worker_online"] is True
    assert g1["camera_status"] == "ONLINE"

    # 2. Worker crash -> release lock
    lock.release()
    assert gate.id not in get_active_gate_worker_lock_ids()

    # 3. Sau khi crash -> Offline tức thì
    resp2 = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")
    g2 = next(g for g in resp2.data if g["id"] == gate.id)
    assert g2["worker_online"] is False
    assert g2["camera_status"] == "OFFLINE"


def test_gates_api_idle_worker_stays_online_without_activity_log(auth_employee):
    """
    Khắc phục F1: Một worker nhàn rỗi (idle) không có xe (không có ActivityLog nào mới)
    vẫn báo worker_online: True và camera_status: ONLINE chừng nào advisory lock còn giữ.
    """
    gate = ParkingGate.objects.filter(is_active=True, camera_status="ONLINE").first()
    assert gate is not None

    # Không tạo bất kỳ ActivityLog nào
    with GateAdvisoryLock(gate.id):
        client = APIClient()
        client.force_authenticate(user=auth_employee)
        response = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")

        assert response.status_code == status.HTTP_200_OK
        target_gate = next((g for g in response.data if g["id"] == gate.id), None)
        assert target_gate is not None
        assert target_gate["worker_online"] is True
        assert target_gate["camera_status"] == "ONLINE"


def test_gates_api_pure_read_does_not_bump_row_version(auth_employee):
    """
    Xác nhận việc đọc status API và ánh xạ camera_status='OFFLINE' là pure-read,
    tuyệt đối KHÔNG chạy câu lệnh UPDATE lên bảng parking_gate, không làm tăng row_version.
    """
    gate = ParkingGate.objects.filter(is_active=True, camera_status="ONLINE").first()
    assert gate is not None

    initial_row_version = gate.row_version
    initial_updated_at = gate.updated_at

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # Gọi API liên tiếp nhiều lần khi worker offline
    for _ in range(5):
        response = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")
        assert response.status_code == status.HTTP_200_OK

    gate.refresh_from_db()
    assert gate.row_version == initial_row_version, (
        "row_version must not be incremented by read API"
    )
    assert gate.updated_at == initial_updated_at, (
        "updated_at must not change on pure read"
    )


def test_gates_api_two_sessions_liveness_simulation(auth_employee):
    """
    Kiểm tra cơ chế liveness giữa 2 phiên CSDL:
    Phiên 1 (worker) acquire lock -> API kiểm tra: online = True.
    Phiên 1 giải phóng lock -> API kiểm tra: online = False, camera_status = 'OFFLINE'.
    """
    gate = ParkingGate.objects.filter(is_active=True, camera_status="ONLINE").first()
    assert gate is not None

    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Ban đầu chưa có worker: offline
    res1 = client.get("/api/v1/parking/gates/")
    g1 = next(g for g in res1.data if g["id"] == gate.id)
    assert g1["worker_online"] is False
    assert g1["camera_status"] == "OFFLINE"

    # 2. Worker acquire lock
    lock = GateAdvisoryLock(gate.id)
    assert lock.acquire() is True

    try:
        res2 = client.get("/api/v1/parking/gates/")
        g2 = next(g for g in res2.data if g["id"] == gate.id)
        assert g2["worker_online"] is True
        assert g2["camera_status"] == "ONLINE"
    finally:
        # 3. Worker terminate / release lock
        lock.release()

    res3 = client.get("/api/v1/parking/gates/")
    g3 = next(g for g in res3.data if g["id"] == gate.id)
    assert g3["worker_online"] is False
    assert g3["camera_status"] == "OFFLINE"


# ==============================================================================
# ActivityLog Telemetry Tests (Sole Source of Truth, Cache Removed)
# ==============================================================================


def test_gates_api_last_auto_event_from_activity_log_json(auth_employee):
    """
    Trích xuất last_auto_event từ ActivityLog định dạng JSON message:
    Bao gồm action, license_plate_masked, reason, occurred_at.
    """
    gate = ParkingGate.objects.filter(is_active=True, direction="IN").first()
    assert gate is not None

    now = timezone.now()
    log_payload = {
        "license_plate_masked": "51A-***.14",
        "reason": "VALID_REGISTERED",
    }
    ActivityLog.objects.create(
        actor_account=None,
        action="GATE_AUTO_CHECK_IN",
        entity_type="parking_gate",
        entity_id=gate.id,
        message=json.dumps(log_payload),
        occurred_at=now,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/gates/?direction=IN")

    assert response.status_code == status.HTTP_200_OK
    target_gate = next((g for g in response.data if g["id"] == gate.id), None)
    assert target_gate is not None
    assert target_gate["last_auto_event"] is not None

    event = target_gate["last_auto_event"]
    assert event["action"] == "GATE_AUTO_CHECK_IN"
    assert event["license_plate_masked"] == "51A-***.14"
    assert event["reason"] == "VALID_REGISTERED"
    assert "occurred_at" in event


def test_gates_api_last_auto_event_from_activity_log_text(auth_employee):
    """
    Trích xuất last_auto_event từ ActivityLog chứa thông điệp văn bản có cấu trúc:
    Regex bóc tách biển số che mờ và lý do kỹ thuật.
    """
    gate = ParkingGate.objects.filter(is_active=True, direction="OUT").first()
    assert gate is not None

    now = timezone.now()
    ActivityLog.objects.create(
        actor_account=None,
        action="GATE_AUTO_PAYMENT_REQUIRED",
        entity_type="parking_gate",
        entity_id=gate.id,
        message="Cổng ra OUT_01 yêu cầu thu phí: biển số 51A***14. Lý do: FEE_PAYMENT_REQUIRED.",
        occurred_at=now,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/gates/?direction=OUT")

    assert response.status_code == status.HTTP_200_OK
    target_gate = next((g for g in response.data if g["id"] == gate.id), None)
    assert target_gate is not None
    assert target_gate["last_auto_event"] is not None

    event = target_gate["last_auto_event"]
    assert event["action"] == "GATE_AUTO_PAYMENT_REQUIRED"
    assert event["license_plate_masked"] == "51A***14"
    assert event["reason"] == "FEE_PAYMENT_REQUIRED"


def test_gates_api_last_auto_event_ignores_cache(auth_employee):
    """
    Cache path bị loại bỏ hoàn toàn (F1/TL-1). last_auto_event chỉ lấy từ ActivityLog.
    Dữ liệu giả mạo trong cache bị bỏ qua hoàn toàn.
    """
    gate = ParkingGate.objects.filter(is_active=True).first()
    assert gate is not None

    # Giả lập dữ liệu trong cache
    cached_payload = {
        "action": "GATE_AUTO_NEEDS_STAFF",
        "license_plate_masked": "59-T2***09",
        "reason": "BLACKLISTED",
        "occurred_at": timezone.now().isoformat(),
    }
    cache.set(f"gate_last_auto_event:{gate.id}", cached_payload, timeout=30)

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/gates/")

    assert response.status_code == status.HTTP_200_OK
    target_gate = next((g for g in response.data if g["id"] == gate.id), None)
    assert target_gate is not None
    # DB không có ActivityLog nào cho gate này -> last_auto_event phải là None
    assert target_gate["last_auto_event"] is None


def test_gates_api_last_auto_event_entity_type_gate_and_raw_regex(auth_employee):
    """
    Trích xuất sự kiện khi entity_type là 'gate' hoặc message chứa mã cổng.
    Kiểm tra nhận diện biển số thô không có từ khóa 'biển số'.
    """
    gate = ParkingGate.objects.filter(is_active=True, direction="OUT").first()
    assert gate is not None

    now = timezone.now()
    ActivityLog.objects.create(
        actor_account=None,
        action="GATE_AUTO_CHECK_OUT",
        entity_type="gate",
        entity_id=gate.id,
        message=f"Xử lý hoàn tất tại {gate.code}: xe 29A-888.88 đạt điều kiện VALID_FEE_ZERO",
        occurred_at=now,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/gates/?direction=OUT")

    assert response.status_code == status.HTTP_200_OK
    target_gate = next((g for g in response.data if g["id"] == gate.id), None)
    assert target_gate is not None
    assert target_gate["last_auto_event"] is not None

    event = target_gate["last_auto_event"]
    assert event["action"] == "GATE_AUTO_CHECK_OUT"
    assert event["license_plate_masked"] == "29A-***.88"
    assert event["reason"] == "VALID_FEE_ZERO"


def test_gates_api_last_auto_event_masks_unmasked_plate_in_json(auth_employee):
    """
    Trường hợp JSON payload chứa biển số xe thô (chưa che mờ),
    API bắt buộc phải che mờ (mask) qua hàm mask_plate tuân thủ Nghị định 13/2023/NĐ-CP.
    """
    gate = ParkingGate.objects.filter(is_active=True, direction="IN").first()
    assert gate is not None

    now = timezone.now()
    payload = {
        "plate": "51A-897.14",
        "reason": "VALID_REGISTERED",
    }
    ActivityLog.objects.create(
        actor_account=None,
        action="GATE_AUTO_CHECK_IN",
        entity_type="parking_gate",
        entity_id=gate.id,
        message=json.dumps(payload),
        occurred_at=now,
    )

    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get("/api/v1/parking/gates/?direction=IN")

    assert response.status_code == status.HTTP_200_OK
    target_gate = next((g for g in response.data if g["id"] == gate.id), None)
    assert target_gate is not None
    assert target_gate["last_auto_event"] is not None

    event = target_gate["last_auto_event"]
    assert event["action"] == "GATE_AUTO_CHECK_IN"
    assert event["license_plate_masked"] == "51A-***.14"
    assert event["reason"] == "VALID_REGISTERED"


def test_gates_api_activity_log_does_not_affect_worker_online(auth_employee):
    """
    ActivityLog KHÔNG còn quyết định worker_online.
    Chỉ advisory lock mới quyết định worker_online.
    """
    gate = ParkingGate.objects.filter(is_active=True, camera_status="ONLINE").first()
    assert gate is not None

    # Tạo ActivityLog GATE_AUTO_CHECK_IN mới nhất
    now = timezone.now()
    ActivityLog.objects.create(
        actor_account=None,
        action="GATE_AUTO_CHECK_IN",
        entity_type="parking_gate",
        entity_id=gate.id,
        message=f"Xử lý tự động tại {gate.code}",
        occurred_at=now,
    )

    # Không có lock -> worker_online phải là False, camera_status là OFFLINE
    client = APIClient()
    client.force_authenticate(user=auth_employee)
    response = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")

    assert response.status_code == status.HTTP_200_OK
    target_gate = next((g for g in response.data if g["id"] == gate.id), None)
    assert target_gate is not None
    assert target_gate["worker_online"] is False
    assert target_gate["camera_status"] == "OFFLINE"


def test_gates_advisory_lock_inspection_directly():
    """
    Kiểm tra trực tiếp hàm get_active_gate_worker_lock_ids() khi acquire và release lock.
    """
    gate = ParkingGate.objects.filter(is_active=True).first()
    assert gate is not None

    # Ban đầu không có lock
    assert gate.id not in get_active_gate_worker_lock_ids()

    lock = GateAdvisoryLock(gate.id)
    assert lock.acquire() is True
    assert gate.id in get_active_gate_worker_lock_ids()

    # Thử acquire lại trên cùng gate -> False (mutual exclusion)
    second_lock = GateAdvisoryLock(gate.id)
    assert second_lock.acquire() is False

    # Giải phóng lock ban đầu
    lock.release()
    assert gate.id not in get_active_gate_worker_lock_ids()


def test_gates_serializer_direct_representation():
    """
    Kiểm tra trực tiếp ParkingGateSerializer khi serialize đơn lẻ và theo danh sách.
    """
    gate = ParkingGate.objects.filter(is_active=True, camera_status="ONLINE").first()
    assert gate is not None

    # 1. Khi không có lock -> worker_online: False, camera_status: 'OFFLINE'
    serializer1 = ParkingGateSerializer(gate)
    assert serializer1.data["worker_online"] is False
    assert serializer1.data["camera_status"] == "OFFLINE"

    # 2. Khi có lock -> worker_online: True, camera_status: 'ONLINE'
    with GateAdvisoryLock(gate.id):
        serializer2 = ParkingGateSerializer(gate)
        assert serializer2.data["worker_online"] is True
        assert serializer2.data["camera_status"] == "ONLINE"


# ==============================================================================
# Query Filtering Tests
# ==============================================================================


def test_gates_api_filtering_direction_and_is_active(auth_employee):
    """Xác minh bộ lọc direction và is_active vẫn hoạt động chuẩn xác kèm các trường mới."""
    client = APIClient()
    client.force_authenticate(user=auth_employee)

    # 1. Lọc cổng vào
    resp_in = client.get("/api/v1/parking/gates/?direction=IN")
    assert resp_in.status_code == status.HTTP_200_OK
    assert all(g["direction"] == "IN" for g in resp_in.data)
    assert all("worker_online" in g for g in resp_in.data)

    # 2. Lọc cổng ra
    resp_out = client.get("/api/v1/parking/gates/?direction=OUT")
    assert resp_out.status_code == status.HTTP_200_OK
    assert all(g["direction"] == "OUT" for g in resp_out.data)
    assert all("last_auto_event" in g for g in resp_out.data)

    # 3. Lọc cổng hoạt động
    resp_active = client.get("/api/v1/parking/gates/?is_active=true")
    assert resp_active.status_code == status.HTTP_200_OK
    assert all(g["is_active"] is True for g in resp_active.data)


# ==============================================================================
# Bounded Query Verification Test (H1, TL Decision 1)
# ==============================================================================


def test_h1_bounded_query_activity_logs_5000_rows(django_assert_num_queries):
    """
    TL Decision 1 (H1 Proof 1):
    Inserts 5,100 activity_log rows across 3 gates (1,700 rows/gate).
    Asserts:
    1. At most 2 database queries are executed for all requested gates.
    2. At most 2 * (number of gates) = 6 rows are read from the database into Python.
    3. Correct decision and snapshot error are attached.
    """
    from datetime import timedelta

    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from apps.parking.serializers.gates import get_latest_gate_activity_logs_map

    gates = list(ParkingGate.objects.filter(is_active=True)[:3])
    assert len(gates) == 3
    g_ids = [g.id for g in gates]

    now = timezone.now()
    logs_to_create = []

    # Create 1700 rows per gate = 5100 rows total
    for _idx, gid in enumerate(g_ids):
        # Base decision row
        logs_to_create.append(
            ActivityLog(
                action="GATE_AUTO_CHECK_IN",
                entity_type="parking_gate",
                entity_id=gid,
                message='{"license_plate": "51A-123.45", "reason": "VALID_REGISTERED"}',
                occurred_at=now - timedelta(seconds=10),
            )
        )
        # Subsequent snapshot failure row (newer)
        logs_to_create.append(
            ActivityLog(
                action="GATE_AUTO_SNAPSHOT_FAILED",
                entity_type="parking_gate",
                entity_id=gid,
                message=json.dumps(
                    {"snapshot_error": f"Upload timeout for gate {gid}"}
                ),
                occurred_at=now - timedelta(seconds=5),
            )
        )
        # 1698 older filler decision and failure rows
        for i in range(1698):
            logs_to_create.append(
                ActivityLog(
                    action="GATE_AUTO_CHECK_IN"
                    if i % 2 == 0
                    else "GATE_AUTO_SNAPSHOT_FAILED",
                    entity_type="parking_gate",
                    entity_id=gid,
                    message='{"status": "old_record"}',
                    occurred_at=now - timedelta(minutes=10 + i),
                )
            )

    ActivityLog.objects.bulk_create(logs_to_create, batch_size=1000)

    rows_read_total = 0

    def row_count_wrapper(execute, sql, params, many, context):
        nonlocal rows_read_total
        res = execute(sql, params, many, context)
        cursor = context["cursor"]
        if hasattr(cursor, "rowcount") and cursor.rowcount > 0:
            rows_read_total += cursor.rowcount
        return res

    with (
        connection.execute_wrapper(row_count_wrapper),
        CaptureQueriesContext(connection) as ctx,
    ):
        result_map = get_latest_gate_activity_logs_map(g_ids)

    # 1. At most 2 queries
    assert len(ctx) <= 2, f"Expected at most 2 queries, got {len(ctx)}"

    # 2. At most 2 * len(gates) = 6 rows read from DB
    assert rows_read_total <= 2 * len(g_ids), (
        f"Expected at most {2 * len(g_ids)} rows read from DB, but read {rows_read_total} rows (unbounded query defect!)"
    )

    # 3. Behavior preserved: all 3 gates have latest decision log and attached snapshot error
    assert len(result_map) == 3
    for gid in g_ids:
        assert gid in result_map
        dec_log = result_map[gid]
        assert dec_log.action == "GATE_AUTO_CHECK_IN"
        assert (
            getattr(dec_log, "_snapshot_error", None)
            == f"Upload timeout for gate {gid}"
        )
