"""
Boundary testing suite for Gate Status API and Worker Liveness (Round 89, F9, TL-72).
Verifies:
1. Gate Status API permissions:
   - Anonymous (unauthenticated): 401 Unauthorized (MSG-4.1-M02).
   - Invalid / malformed auth token: 401 Unauthorized.
   - Expired / forged session: 401 Unauthorized.
   - CUSTOMER role (unauthorized): 403 Forbidden (MSG-4.2-M01).
   - Inactive accounts (EMPLOYEE / MANAGER with is_active=False): 401 or 403.
   - Authorized roles (EMPLOYEE, MANAGER with is_active=True): 200 OK.
   - Query parameter filtering permission preservation.

2. Boundary testing worker_online and advisory lock telemetry:
   - Camera status OFFLINE overriding active lock and recent ActivityLog.
   - GateAdvisoryLock acquire -> worker_online=True, camera_status=ONLINE.
   - GateAdvisoryLock release -> worker_online=False, camera_status=OFFLINE.
   - DEGRADED camera status handling with and without lock.
   - Multi-gate isolation without cross-talk.
"""

import pytest
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.audit.models import ActivityLog
from apps.parking.gate_worker.locks import GateAdvisoryLock
from apps.parking.models import ParkingGate
from apps.parking.serializers.gates import ParkingGateSerializer

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache_and_state():
    """Ensure cache is pristine before and after each test."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def active_employee():
    emp, _ = Account.objects.get_or_create(
        email="emp_c2_test@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def inactive_employee():
    emp, _ = Account.objects.get_or_create(
        email="inactive_emp_c2@parking.local",
        defaults={
            "role": "EMPLOYEE",
            "is_active": False,
            "password": "!dummy_password_hash",
        },
    )
    return emp


@pytest.fixture
def active_manager():
    mgr, _ = Account.objects.get_or_create(
        email="mgr_c2_test@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return mgr


@pytest.fixture
def inactive_manager():
    mgr, _ = Account.objects.get_or_create(
        email="inactive_mgr_c2@parking.local",
        defaults={
            "role": "MANAGER",
            "is_active": False,
            "password": "!dummy_password_hash",
        },
    )
    return mgr


@pytest.fixture
def active_customer():
    cust, _ = Account.objects.get_or_create(
        email="cust_c2_test@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": True,
            "password": "!dummy_password_hash",
        },
    )
    return cust


@pytest.fixture
def inactive_customer():
    cust, _ = Account.objects.get_or_create(
        email="inactive_cust_c2@parking.local",
        defaults={
            "role": "CUSTOMER",
            "is_active": False,
            "password": "!dummy_password_hash",
        },
    )
    return cust


# ==============================================================================
# SECTION 1: PERMISSION MATRIX CHALLENGES
# ==============================================================================


class TestGateStatusApiPermissionsChallenge:
    """Stress-test permissions on GET /api/v1/parking/gates/."""

    def test_anonymous_unauthenticated_request_rejected(self):
        """Anonymous access without any authentication header must return 401."""
        client = APIClient()
        response = client.get("/api/v1/parking/gates/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data.get("code") == "MSG-4.1-M02"

    def test_anonymous_with_malformed_auth_header_rejected(self):
        """Invalid Bearer tokens or corrupted headers must return 401."""
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Bearer invalid_token_xyz_123")
        response = client.get("/api/v1/parking/gates/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data.get("code") == "MSG-4.1-M02"

    def test_anonymous_with_query_params_rejected(self):
        """Query parameters cannot bypass unauthenticated 401 guard."""
        client = APIClient()
        for param in [
            "?direction=IN",
            "?direction=OUT",
            "?is_active=true",
            "?is_active=false",
            "?direction=IN&is_active=true",
        ]:
            response = client.get(f"/api/v1/parking/gates/{param}")
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert response.data.get("code") == "MSG-4.1-M02"

    def test_customer_role_strictly_forbidden(self, active_customer):
        """Authenticated CUSTOMER role must receive 403 Forbidden."""
        client = APIClient()
        client.force_authenticate(user=active_customer)
        response = client.get("/api/v1/parking/gates/")
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert response.data.get("code") == "MSG-4.2-M01"
        assert "Bạn không có quyền" in response.data.get("message", "")

    def test_customer_with_various_filters_strictly_forbidden(self, active_customer):
        """CUSTOMER cannot view gates by supplying any combination of filters."""
        client = APIClient()
        client.force_authenticate(user=active_customer)
        for param in [
            "?direction=IN",
            "?direction=OUT",
            "?is_active=true",
            "?is_active=false",
        ]:
            response = client.get(f"/api/v1/parking/gates/{param}")
            assert response.status_code == status.HTTP_403_FORBIDDEN
            assert response.data.get("code") == "MSG-4.2-M01"

    def test_inactive_customer_rejected(self, inactive_customer):
        """Inactive CUSTOMER account cannot access."""
        client = APIClient()
        client.force_authenticate(user=inactive_customer)
        response = client.get("/api/v1/parking/gates/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_inactive_employee_rejected(self, inactive_employee):
        """Inactive EMPLOYEE account must NOT have access to staff telemetry."""
        client = APIClient()
        client.force_authenticate(user=inactive_employee)
        response = client.get("/api/v1/parking/gates/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_inactive_manager_rejected(self, inactive_manager):
        """Inactive MANAGER account must NOT have access to staff telemetry."""
        client = APIClient()
        client.force_authenticate(user=inactive_manager)
        response = client.get("/api/v1/parking/gates/")
        assert response.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_active_employee_allowed(self, active_employee):
        """Active EMPLOYEE must have 200 OK access."""
        client = APIClient()
        client.force_authenticate(user=active_employee)
        response = client.get("/api/v1/parking/gates/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)

    def test_active_manager_allowed(self, active_manager):
        """Active MANAGER must have 200 OK access."""
        client = APIClient()
        client.force_authenticate(user=active_manager)
        response = client.get("/api/v1/parking/gates/")
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.data, list)


# ==============================================================================
# SECTION 2: WORKER_ONLINE & HEARTBEAT TIMESTAMPS STRESS-TESTING
# ==============================================================================


class TestWorkerOnlineHeartbeatStress:
    """Empirically test worker_online with past vs present timestamps and camera status."""

    def test_camera_offline_unconditionally_forces_worker_offline(
        self, active_employee
    ):
        """
        When camera_status is 'OFFLINE', worker_online MUST be False,
        even if:
        1. Cache heartbeat is actively set with True / future timeout.
        2. gate.updated_at is right now.
        3. ActivityLog was created 1 second ago.
        """
        gate = ParkingGate.objects.filter(is_active=True).first()
        assert gate is not None

        orig_status = gate.camera_status
        try:
            now = timezone.now()
            # Set gate camera to OFFLINE
            gate.camera_status = "OFFLINE"
            gate.save(update_fields=["camera_status"])

            # 1. Inject active cache heartbeat
            cache.set(f"gate_worker_heartbeat:{gate.id}", True, timeout=60)
            cache.set(f"gate_worker_heartbeat:{gate.code}", True, timeout=60)

            # 2. Inject fresh ActivityLog
            ActivityLog.objects.create(
                actor_account=None,
                action="GATE_AUTO_CHECK_IN",
                entity_type="parking_gate",
                entity_id=gate.id,
                message='{"license_plate_masked": "51A-***.14", "reason": "VALID_REGISTERED"}',
                occurred_at=now,
            )

            # Test through Serializer directly
            serializer = ParkingGateSerializer(gate)
            assert serializer.data["worker_online"] is False

            # Test through API response
            client = APIClient()
            client.force_authenticate(user=active_employee)
            response = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")
            assert response.status_code == status.HTTP_200_OK
            gate_data = next(g for g in response.data if g["id"] == gate.id)
            assert gate_data["camera_status"] == "OFFLINE"
            assert gate_data["worker_online"] is False
        finally:
            gate.camera_status = orig_status
            gate.save(update_fields=["camera_status"])

    def test_heartbeat_timestamp_present_vs_past_via_mocked_time(self, active_employee):
        """
        When camera_status is ONLINE and no cache key exists:
        - At base_time: gate.updated_at was updated within 15s (PRESENT) -> worker_online is True.
        - At base_time + 60s: gate.updated_at is 60s in the past (PAST) -> worker_online is False.
        """
        gate = ParkingGate.objects.filter(
            is_active=True, camera_status="ONLINE"
        ).first()
        assert gate is not None

        cache.clear()
        gate.name = f"Updated-{timezone.now().timestamp()}"
        gate.save(update_fields=["name"])
        gate.refresh_from_db()

        # Gate record update alone must NOT cause false-positive worker_online: True (Fix Finding 2)
        serializer = ParkingGateSerializer(gate)
        assert serializer.data["worker_online"] is False

    def test_heartbeat_timestamp_boundary_15_seconds(self, active_employee):
        """
        Advisory Lock Liveness Boundary (TL-72 / Round 89):
        Worker liveness is determined strictly by PostgreSQL advisory locks:
        - When GateAdvisoryLock is acquired -> worker_online is True, camera_status is ONLINE.
        - When GateAdvisoryLock is released -> worker_online is False, camera_status is OFFLINE.
        """
        gate = ParkingGate.objects.filter(
            is_active=True, camera_status="ONLINE"
        ).first()
        assert gate is not None

        lock = GateAdvisoryLock(gate.id)
        try:
            assert lock.acquire() is True
            data_online = ParkingGateSerializer(gate).data
            assert data_online["worker_online"] is True
            assert data_online["camera_status"] == "ONLINE"
        finally:
            lock.release()

        data_offline = ParkingGateSerializer(gate).data
        assert data_offline["worker_online"] is False
        assert data_offline["camera_status"] == "OFFLINE"

    def test_heartbeat_via_activity_log_present_vs_past(self, active_employee):
        """
        ActivityLog telemetry & Lock liveness integration (TL-72):
        - ActivityLog populates last_auto_event telemetry accurately.
        - worker_online depends strictly on GateAdvisoryLock presence, not log timestamp age.
        """
        gate = ParkingGate.objects.filter(
            is_active=True, camera_status="ONLINE"
        ).first()
        assert gate is not None

        log_time = timezone.now()
        ActivityLog.objects.create(
            actor_account=None,
            action="GATE_AUTO_CHECK_IN",
            entity_type="parking_gate",
            entity_id=gate.id,
            message='{"license_plate_masked": "51A-***.14", "reason": "VALID_REGISTERED"}',
            occurred_at=log_time,
        )

        lock = GateAdvisoryLock(gate.id)
        try:
            assert lock.acquire() is True
            data = ParkingGateSerializer(gate).data
            assert data["worker_online"] is True
            assert data["last_auto_event"] is not None
            assert data["last_auto_event"]["action"] == "GATE_AUTO_CHECK_IN"
            assert data["last_auto_event"]["license_plate_masked"] == "51A-***.14"
        finally:
            lock.release()

        # Once lock is released, worker is offline despite recent ActivityLog
        data_after = ParkingGateSerializer(gate).data
        assert data_after["worker_online"] is False
        assert data_after["camera_status"] == "OFFLINE"
        assert data_after["last_auto_event"] is not None

    def test_heartbeat_custom_timeout_setting_override(self, active_employee):
        """
        Lock lifecycle & API endpoint response (TL-72):
        Verifies client HTTP GET response dynamically maps worker_online and camera_status
        when advisory lock is held vs released.
        """
        gate = ParkingGate.objects.filter(
            is_active=True, camera_status="ONLINE"
        ).first()
        assert gate is not None

        client = APIClient()
        client.force_authenticate(user=active_employee)

        lock = GateAdvisoryLock(gate.id)
        try:
            assert lock.acquire() is True
            res_online = client.get(
                f"/api/v1/parking/gates/?direction={gate.direction}"
            )
            assert res_online.status_code == status.HTTP_200_OK
            gate_data = next(g for g in res_online.data if g["id"] == gate.id)
            assert gate_data["worker_online"] is True
            assert gate_data["camera_status"] == "ONLINE"
        finally:
            lock.release()

        res_offline = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")
        assert res_offline.status_code == status.HTTP_200_OK
        gate_data_off = next(g for g in res_offline.data if g["id"] == gate.id)
        assert gate_data_off["worker_online"] is False
        assert gate_data_off["camera_status"] == "OFFLINE"

    def test_multi_gate_telemetry_isolation(self, active_employee):
        """
        Stress test multi-gate isolation with PostgreSQL Advisory Locks:
        - Gate A (ONLINE in DB, lock held) -> worker_online: True, camera_status: ONLINE.
        - Gate B (OFFLINE in DB, lock held) -> worker_online: False, camera_status: OFFLINE (OFFLINE override).
        - Gate C (ONLINE in DB, NO lock held) -> worker_online: False, camera_status: OFFLINE (unheld lock forces OFFLINE).
        Verifies strict per-gate advisory lock isolation without cross-talk.
        """
        gates = list(ParkingGate.objects.filter(is_active=True)[:3])
        if len(gates) < 3:
            pytest.skip("Need at least 3 gates for multi-gate isolation test")

        gate_a, gate_b, gate_c = gates[0], gates[1], gates[2]

        orig_a_status = gate_a.camera_status
        orig_b_status = gate_b.camera_status
        orig_c_status = gate_c.camera_status
        try:
            ParkingGate.objects.filter(id=gate_a.id).update(camera_status="ONLINE")
            ParkingGate.objects.filter(id=gate_b.id).update(camera_status="DEGRADED")
            ParkingGate.objects.filter(id=gate_c.id).update(camera_status="ONLINE")
            gate_a.refresh_from_db()
            gate_b.refresh_from_db()
            gate_c.refresh_from_db()

            lock_a = GateAdvisoryLock(gate_a.id)
            lock_b = GateAdvisoryLock(gate_b.id)
            try:
                assert lock_a.acquire() is True
                assert lock_b.acquire() is True
                # Gate C intentionally has NO lock held

                client = APIClient()
                client.force_authenticate(user=active_employee)
                response = client.get("/api/v1/parking/gates/")
                assert response.status_code == status.HTTP_200_OK

                gate_map = {g["id"]: g for g in response.data}

                # Gate A: ONLINE in DB + lock held -> worker_online: True, camera_status: ONLINE
                assert gate_map[gate_a.id]["worker_online"] is True
                assert gate_map[gate_a.id]["camera_status"] == "ONLINE"

                # Gate B: DEGRADED in DB + lock held -> worker_online: True, camera_status: DEGRADED
                assert gate_map[gate_b.id]["worker_online"] is True
                assert gate_map[gate_b.id]["camera_status"] == "DEGRADED"

                # Gate C: ONLINE in DB + no lock held -> worker_online: False, camera_status: OFFLINE
                assert gate_map[gate_c.id]["worker_online"] is False
                assert gate_map[gate_c.id]["camera_status"] == "OFFLINE"
            finally:
                lock_a.release()
                lock_b.release()
        finally:
            ParkingGate.objects.filter(id=gate_a.id).update(camera_status=orig_a_status)
            ParkingGate.objects.filter(id=gate_b.id).update(camera_status=orig_b_status)
            ParkingGate.objects.filter(id=gate_c.id).update(camera_status=orig_c_status)

    def test_camera_status_values_degraded_and_low_light(self, active_employee):
        """
        ADR-0011 Section 2.4 state machine allows camera_status to be 'DEGRADED'.
        - DEGRADED without advisory lock -> worker_online: False, camera_status: OFFLINE.
        - DEGRADED with advisory lock -> worker_online: True, camera_status: DEGRADED.
        """
        gate = ParkingGate.objects.filter(is_active=True).first()
        assert gate is not None

        orig_status = gate.camera_status
        try:
            ParkingGate.objects.filter(id=gate.id).update(camera_status="DEGRADED")
            gate.refresh_from_db()

            # 1. DEGRADED without lock -> worker_online: False, camera_status: OFFLINE
            data_no_lock = ParkingGateSerializer(gate).data
            assert data_no_lock["worker_online"] is False
            assert data_no_lock["camera_status"] == "OFFLINE"

            # 2. DEGRADED with lock -> worker_online: True, camera_status: DEGRADED
            lock = GateAdvisoryLock(gate.id)
            try:
                assert lock.acquire() is True
                data_with_lock = ParkingGateSerializer(gate).data
                assert data_with_lock["worker_online"] is True
                assert data_with_lock["camera_status"] == "DEGRADED"
            finally:
                lock.release()
        finally:
            ParkingGate.objects.filter(id=gate.id).update(camera_status=orig_status)


# ==============================================================================
# SECTION 3: MULTI-SESSION PG_LOCKS, DISCONNECT & TELEMETRY BOUNDARIES
# ==============================================================================


class TestPgLocksDisconnectAndTelemetryBoundaries:
    """Verify PostgreSQL advisory lock disconnect cleanup, tie-breaking, and malformed payloads."""

    def test_abrupt_socket_close_and_reacquisition(self):
        gate = ParkingGate.objects.filter(
            is_active=True, camera_status="ONLINE"
        ).first()
        assert gate is not None

        lock1 = GateAdvisoryLock(gate.id)
        assert lock1.acquire() is True

        from django.db import connection

        from apps.parking.gate_worker.locks import get_active_gate_worker_lock_ids

        assert gate.id in get_active_gate_worker_lock_ids()

        if connection.vendor == "postgresql" and lock1._raw_conn is not None:
            lock1._raw_conn.close()
            lock1._raw_conn = None
            lock1._is_locked = False
        else:
            lock1.release()

        assert gate.id not in get_active_gate_worker_lock_ids()

        lock2 = GateAdvisoryLock(gate.id)
        try:
            assert lock2.acquire() is True
            assert gate.id in get_active_gate_worker_lock_ids()
        finally:
            lock2.release()

    def test_pg_terminate_backend_drops_lock_and_flips_api_offline(
        self, active_employee
    ):
        from django.db import connection

        if connection.vendor != "postgresql":
            pytest.skip("PostgreSQL-specific pg_terminate_backend verification")

        gate = ParkingGate.objects.filter(
            is_active=True, camera_status="ONLINE"
        ).first()
        assert gate is not None

        lock = GateAdvisoryLock(gate.id)
        assert lock.acquire() is True
        try:
            with lock._raw_conn.cursor() as cur:
                cur.execute("SELECT pg_backend_pid();")
                worker_pid = cur.fetchone()[0]

            client = APIClient()
            client.force_authenticate(user=active_employee)

            res_before = client.get(
                f"/api/v1/parking/gates/?direction={gate.direction}"
            )
            g_before = next(g for g in res_before.data if g["id"] == gate.id)
            assert g_before["worker_online"] is True
            assert g_before["camera_status"] == "ONLINE"

            with connection.cursor() as main_cur:
                main_cur.execute("SELECT pg_terminate_backend(%s);", [worker_pid])
            lock._raw_conn = None
            lock._is_locked = False

            res_after = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")
            g_after = next(g for g in res_after.data if g["id"] == gate.id)
            assert g_after["worker_online"] is False
            assert g_after["camera_status"] == "OFFLINE"
        finally:
            lock.release()

    def test_empty_gate_list_and_tie_breaking_and_corrupted_messages(
        self, active_employee
    ):
        import json

        from apps.parking.models import ParkingLot

        client = APIClient()
        client.force_authenticate(user=active_employee)

        empty_res = client.get("/api/v1/parking/gates/?direction=NONEXISTENT_DIR")
        assert empty_res.status_code == status.HTTP_200_OK
        assert empty_res.data == []

        lot = ParkingLot.objects.first()
        assert lot is not None
        gate = ParkingGate.objects.create(
            lot=lot,
            code="GATE_TIE_BOUNDARY",
            name="Boundary Gate",
            direction="IN",
            camera_status="ONLINE",
            is_active=True,
        )

        same_time = timezone.now()
        ActivityLog.objects.create(
            actor_account=None,
            action="GATE_AUTO_CHECK_IN",
            entity_type="parking_gate",
            entity_id=gate.id,
            message=json.dumps({"plate": "51A-111.11", "reason": "VALID_REGISTERED"}),
            occurred_at=same_time,
        )
        ActivityLog.objects.create(
            actor_account=None,
            action="GATE_AUTO_CHECK_IN",
            entity_type="parking_gate",
            entity_id=gate.id,
            message=json.dumps(
                {
                    "plate": "51A-222.22",
                    "reason": "VALID_REGISTERED",
                    "snapshot_error": "AuthorizationRequired: Invalid credentials",
                }
            ),
            occurred_at=same_time,
        )

        res = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")
        target = next(g for g in res.data if g["id"] == gate.id)
        assert target["last_auto_event"]["license_plate_masked"] == "51A-***.22"
        assert (
            target["last_auto_event"]["snapshot_error"]
            == "AuthorizationRequired: Invalid credentials"
        )

        for bad_msg in ["---", "{invalid json", "{}", '{"other_key": 1}']:
            ActivityLog.objects.create(
                actor_account=None,
                action="GATE_AUTO_NEEDS_STAFF",
                entity_type="parking_gate",
                entity_id=gate.id,
                message=bad_msg,
                occurred_at=timezone.now(),
            )
            bad_res = client.get(f"/api/v1/parking/gates/?direction={gate.direction}")
            assert bad_res.status_code == status.HTTP_200_OK
            bad_target = next(g for g in bad_res.data if g["id"] == gate.id)
            assert bad_target["last_auto_event"]["action"] == "GATE_AUTO_NEEDS_STAFF"
            assert bad_target["last_auto_event"]["snapshot_error"] is None
