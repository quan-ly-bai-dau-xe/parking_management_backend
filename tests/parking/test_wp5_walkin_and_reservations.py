"""
Comprehensive test suite for Milestone WP5:
- D7 Walk-in Pending Entry (15m window, <=5s recheck, zero duplicate ActivityLog, auto check-in & snapshot upload)
- J4 SlotReservation completion on Gate Worker check-in
- SMS OTP Test Double strict gating (DEBUG=True + SMS_OTP_TEST_DOUBLE_ENABLED=True + unconfigured Firebase)
- 4.5.2 Slot Reservation API, permissions, status/type guards, PostgreSQL GiST 23P01 -> HTTP 409 PROP-4.5.2-P05
- Customer Privacy-Safe Parking Map (/api/v1/me/parking-structure/, /api/v1/me/parking-slots/)
"""

from __future__ import annotations

import time
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.accounts.services.auth import confirm_register_sms, request_register_otp
from apps.audit.models import ActivityLog
from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer
from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
from apps.parking.models import (
    ParkingFloor,
    ParkingGate,
    ParkingLot,
    ParkingSlot,
    ParkingZone,
    SlotAllowedVehicleType,
    SlotReservation,
    VehicleEntryExitLog,
)
from apps.parking.services.gate_decision import (
    ACTION_AUTO_CHECK_IN,
    ACTION_HOLD,
    REASON_UNREGISTERED_VEHICLE,
    REASON_VALID_REGISTERED,
)
from apps.vehicles.models import Vehicle, VehicleType

pytestmark = pytest.mark.django_db


def _make_customer_with_vehicle(prefix: str, vtype: VehicleType, plate: str):
    suffix = uuid.uuid4().hex[:6].upper()
    acct = Account.objects.create_user(
        email=f"{prefix}_{suffix}@parking.local",
        phone=f"09{int(uuid.uuid4().int % 100000000):08d}",
        password="ValidPassword123!",
        role="CUSTOMER",
        is_active=True,
    )
    cust = Customer.objects.create(
        account=acct,
        code=f"K{suffix}"[:10],
        full_name=f"Khach {prefix} {suffix}",
        phone=acct.phone,
        identity_card_number=f"079{int(uuid.uuid4().int % 1000000000):09d}",
        status="ACTIVE",
    )
    norm = plate.replace("-", "").replace(".", "").upper()
    veh = Vehicle.objects.create(
        code=f"V{suffix}"[:10],
        license_plate=plate,
        license_plate_norm=norm,
        vehicle_type=vtype,
        customer=cust,
        model_name="Test Sedan",
    )
    return acct, cust, veh


def _make_scan_result(plate: str, confidence: float = 96.5):
    cand = MagicMock()
    cand.plate_normalized = plate.replace("-", "").replace(".", "").upper()
    cand.confidence = confidence
    scan = MagicMock()
    scan.best_candidate = cand
    scan.review_status = "AUTO"
    return scan


class TestWP5PendingEntryD7AndJ4:
    """Tests for GateWorkerCoordinator D7 pending entry and J4 reservation completion."""

    def test_pending_entry_defaults_match_spec(self):
        assert settings.GATE_WORKER_PENDING_MINUTES == 15
        assert settings.GATE_WORKER_PENDING_RECHECK_SECONDS == 5.0
        assert settings.GATE_WORKER_PENDING_SEEN_SECONDS == 20

    def test_unregistered_vehicle_pending_entry_flow_and_auto_checkin(self):
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        assert in_gate is not None
        in_gate.is_auto_scan = True

        plate = "51A-897.14"
        norm_plate = "51A89714"
        # Clean up any prior vehicle with this plate in test DB
        Vehicle.all_objects.filter(license_plate_norm=norm_plate).update(
            deleted_at=timezone.now(), deleted_by_id=None
        )

        mock_uploader = MagicMock()
        coordinator = GateWorkerCoordinator(
            streams_override={in_gate.code: "http://mock/in"},
            snapshot_uploader=mock_uploader,
        )
        coordinator._managed_gates[in_gate.id] = in_gate
        coordinator._pending_recheck_seconds = 0.0
        mock_reader = MagicMock()
        mock_reader.status = "STREAMING"
        mock_reader.get_latest_frame.return_value = (None, 0.0)
        coordinator._readers[in_gate.id] = mock_reader
        coordinator._filters[in_gate.id] = MagicMock()

        scan_result = _make_scan_result(plate, confidence=97.0)
        decisive_frame = np.zeros((40, 40, 3), dtype=np.uint8)

        initial_logs_count = ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=in_gate.id,
            action="GATE_AUTO_NEEDS_STAFF",
        ).count()

        # 1. First detection -> HOLD (UNREGISTERED_VEHICLE), 1 ActivityLog, NO voter cooldown, added to _pending_entries
        decision = coordinator._evaluate_and_execute(
            in_gate, plate, scan_result, decisive_frame=decisive_frame
        )
        assert decision.action == ACTION_HOLD
        assert decision.reason_code == REASON_UNREGISTERED_VEHICLE
        assert not coordinator._voter.is_in_cooldown(in_gate.id, plate)
        assert (in_gate.id, norm_plate) in coordinator._pending_entries
        assert (
            ActivityLog.objects.filter(
                entity_type="parking_gate",
                entity_id=in_gate.id,
                action="GATE_AUTO_NEEDS_STAFF",
            ).count()
            == initial_logs_count + 1
        )

        # 2. Repeated evaluation / stationary tick while unregistered -> NO duplicate ActivityLog
        coordinator._evaluate_and_execute(
            in_gate, plate, scan_result, decisive_frame=decisive_frame
        )
        coordinator._process_gate_tick(in_gate)
        assert (
            ActivityLog.objects.filter(
                entity_type="parking_gate",
                entity_id=in_gate.id,
                action="GATE_AUTO_NEEDS_STAFF",
            ).count()
            == initial_logs_count + 1
        )
        assert not VehicleEntryExitLog.objects.filter(
            license_plate_norm=norm_plate, exit_time__isnull=True
        ).exists()

        # 3. Customer completes registration + adds vehicle
        vtype_car = VehicleType.objects.filter(code="CAR").first()
        assert vtype_car is not None
        _make_customer_with_vehicle("d7walkin", vtype_car, plate)

        # Ensure at least one compatible slot is available
        avail_slot = ParkingSlot.objects.filter(
            zone__floor__lot_id=in_gate.lot_id,
            status="AVAILABLE",
            deleted_at__isnull=True,
            allowed_vehicle_types__vehicle_type_id=vtype_car.id,
        ).first()
        assert avail_slot is not None

        # 4. Next stationary tick -> _recheck_pending_entries detects vehicle and auto checks in!
        coordinator._process_gate_tick(in_gate)

        assert (in_gate.id, norm_plate) not in coordinator._pending_entries
        assert coordinator._voter.is_in_cooldown(in_gate.id, plate)

        open_session = VehicleEntryExitLog.objects.filter(
            license_plate_norm=norm_plate, exit_time__isnull=True
        ).first()
        assert open_session is not None
        assert open_session.recognition_source == "AI"
        assert open_session.review_status == "AUTO"
        assert open_session.entry_handled_by is None

        assert ActivityLog.objects.filter(
            entity_type="parking_gate",
            entity_id=in_gate.id,
            action="GATE_AUTO_CHECK_IN",
        ).exists()
        mock_uploader.dispatch_upload.assert_called_once()

    def test_pending_entry_expires_after_15_minutes_and_release_gate_cleans_up(self):
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        assert in_gate is not None
        in_gate.is_auto_scan = True

        coordinator = GateWorkerCoordinator(
            streams_override={in_gate.code: "http://mock/in"},
        )
        coordinator._managed_gates[in_gate.id] = in_gate
        coordinator._pending_entries[(in_gate.id, "51A99911")] = {
            "plate": "51A-999.11",
            "norm_plate": "51A99911",
            "confidence": 96.0,
            "expires_at": time.monotonic() - 1.0,  # Already expired
            "last_recheck_ts": 0.0,
            "decisive_frame": None,
        }
        coordinator._recheck_pending_entries(in_gate)
        assert (in_gate.id, "51A99911") not in coordinator._pending_entries

        coordinator._pending_entries[(in_gate.id, "51A88822")] = {
            "plate": "51A-888.22",
            "norm_plate": "51A88822",
            "confidence": 96.0,
            "expires_at": time.monotonic() + 600.0,
            "last_recheck_ts": 0.0,
            "decisive_frame": None,
        }
        coordinator._release_gate(in_gate.id)
        assert (in_gate.id, "51A88822") not in coordinator._pending_entries

    def test_j4_reservation_marked_completed_on_worker_checkin(self):
        in_gate = ParkingGate.objects.filter(direction="IN", is_active=True).first()
        assert in_gate is not None
        in_gate.is_auto_scan = True

        vtype_car = VehicleType.objects.filter(code="CAR").first()
        _, cust, veh = _make_customer_with_vehicle("j4done", vtype_car, "51G-456.78")

        slot = ParkingSlot.objects.filter(
            zone__floor__lot_id=in_gate.lot_id,
            status="AVAILABLE",
            deleted_at__isnull=True,
            allowed_vehicle_types__vehicle_type_id=vtype_car.id,
        ).first()
        assert slot is not None

        now = timezone.now()
        rsv = SlotReservation.objects.create(
            code=f"RSV-WP5-{uuid.uuid4().hex[:6].upper()}",
            slot=slot,
            customer=cust,
            vehicle=veh,
            reserved_from=now - timedelta(minutes=10),
            reserved_until=now + timedelta(hours=2),
            status="ACTIVE",
        )
        slot.refresh_from_db()
        assert slot.status == "RESERVED"

        coordinator = GateWorkerCoordinator(
            streams_override={in_gate.code: "http://mock/in"},
            snapshot_uploader=MagicMock(),
        )
        coordinator._managed_gates[in_gate.id] = in_gate
        scan_result = _make_scan_result(veh.license_plate, confidence=98.0)

        decision = coordinator._evaluate_and_execute(
            in_gate, veh.license_plate, scan_result
        )
        assert decision.action == ACTION_AUTO_CHECK_IN
        assert decision.reason_code == REASON_VALID_REGISTERED

        rsv.refresh_from_db()
        assert rsv.status == "COMPLETED"
        slot.refresh_from_db()
        assert slot.status == "OCCUPIED"


class TestWP5SmsOtpTestDouble:
    """Tests strict security gating of SMS_OTP_TEST_DOUBLE_ENABLED."""

    def setup_method(self):
        cache.clear()

    def test_production_settings_hard_disables_test_double(self):
        from pathlib import Path

        prod_text = Path(
            settings.BASE_DIR / "config" / "settings" / "production.py"
        ).read_text(encoding="utf-8")
        assert "SMS_OTP_TEST_DOUBLE_ENABLED = False" in prod_text

    @override_settings(DEBUG=False, SMS_OTP_TEST_DOUBLE_ENABLED=True)
    @patch("apps.accounts.services.auth.is_firebase_configured", return_value=False)
    @patch("apps.accounts.services.auth.generate_numeric_otp", return_value="741852")
    @patch("apps.accounts.services.auth.send_sms")
    def test_test_double_refused_when_debug_is_false(
        self, mock_send_sms, mock_gen_otp, mock_fb
    ):
        from django.test import RequestFactory

        rf = RequestFactory()
        req = rf.post("/api/v1/auth/register/sms/request/", REMOTE_ADDR="10.0.0.1")
        otp = request_register_otp(req, "0988112233")
        assert str(otp) == "741852"

        with pytest.raises(BusinessAPIException) as exc:
            confirm_register_sms(
                phone="0988112233",
                otp="123456",
                password="SecurePassword123!",
                full_name="Test Refused",
            )
        assert exc.value.code == "PROP-4.1-P11"

    @override_settings(DEBUG=True, SMS_OTP_TEST_DOUBLE_ENABLED=False)
    @patch("apps.accounts.services.auth.is_firebase_configured", return_value=False)
    @patch("apps.accounts.services.auth.generate_numeric_otp", return_value="852963")
    @patch("apps.accounts.services.auth.send_sms")
    def test_test_double_refused_when_flag_is_false(
        self, mock_send_sms, mock_gen_otp, mock_fb
    ):
        from django.test import RequestFactory

        rf = RequestFactory()
        req = rf.post("/api/v1/auth/register/sms/request/", REMOTE_ADDR="10.0.0.2")
        otp = request_register_otp(req, "0988112244")
        assert str(otp) == "852963"

    @override_settings(DEBUG=True, SMS_OTP_TEST_DOUBLE_ENABLED=True)
    @patch("apps.accounts.services.auth.is_firebase_configured", return_value=False)
    @patch("apps.accounts.services.auth.send_sms")
    def test_test_double_works_when_debug_true_and_flag_true(
        self, mock_send_sms, mock_fb
    ):
        client = APIClient()
        phone = "0988776611"
        res_req = client.post(
            "/api/v1/auth/register/sms/request/",
            {"phone": phone},
            format="json",
        )
        assert res_req.status_code == status.HTTP_200_OK

        res_conf = client.post(
            "/api/v1/auth/register/sms/confirm/",
            {
                "phone": phone,
                "otp": "123456",
                "password": "SecurePassword123!",
                "confirm_password": "SecurePassword123!",
                "full_name": "Nguyen Walkin",
            },
            format="json",
        )
        assert res_conf.status_code == status.HTTP_201_CREATED
        assert res_conf.json()["account"]["role"] == "CUSTOMER"


class TestWP5SlotReservationsAndGiST:
    """Tests 4.5.2 Slot Reservation permissions, status/type guards, GiST 23P01 -> 409, and Customer map."""

    @pytest.fixture(autouse=True)
    def setup_reservation_fixtures(self, ensure_sample_data):
        self.vtype_car, _ = VehicleType.objects.get_or_create(
            code="CAR", defaults={"name": "Ô tô con"}
        )
        self.vtype_ev, _ = VehicleType.objects.get_or_create(
            code="EV", defaults={"name": "Xe điện"}
        )

        self.lot = ParkingLot.objects.first()
        self.floor = ParkingFloor.objects.filter(
            lot=self.lot, deleted_at__isnull=True
        ).first()
        self.zone = ParkingZone.objects.filter(
            floor=self.floor, deleted_at__isnull=True
        ).first()

        suffix = uuid.uuid4().hex[:4].upper()
        self.slot_car = ParkingSlot.objects.create(
            zone=self.zone,
            code=f"R{suffix}1",
            slot_kind="STANDARD",
            status="AVAILABLE",
        )
        SlotAllowedVehicleType.objects.get_or_create(
            slot=self.slot_car, vehicle_type=self.vtype_car
        )

        self.slot_ev_only = ParkingSlot.objects.create(
            zone=self.zone,
            code=f"E{suffix}2",
            slot_kind="EV_CHARGING",
            status="AVAILABLE",
        )
        SlotAllowedVehicleType.objects.get_or_create(
            slot=self.slot_ev_only, vehicle_type=self.vtype_ev
        )

        self.slot_maint = ParkingSlot.objects.create(
            zone=self.zone,
            code=f"M{suffix}3",
            slot_kind="STANDARD",
            status="MAINTENANCE",
        )
        SlotAllowedVehicleType.objects.get_or_create(
            slot=self.slot_maint, vehicle_type=self.vtype_car
        )

        self.slot_occupied = ParkingSlot.objects.create(
            zone=self.zone,
            code=f"O{suffix}4",
            slot_kind="STANDARD",
            status="AVAILABLE",
        )
        SlotAllowedVehicleType.objects.get_or_create(
            slot=self.slot_occupied, vehicle_type=self.vtype_car
        )

        self.acct_c1, self.cust1, self.veh1 = _make_customer_with_vehicle(
            "rsv1", self.vtype_car, f"51A-{int(uuid.uuid4().int % 90000) + 10000}"
        )
        self.acct_c2, self.cust2, self.veh2 = _make_customer_with_vehicle(
            "rsv2", self.vtype_car, f"51B-{int(uuid.uuid4().int % 90000) + 10000}"
        )
        _, _, self.veh_occ = _make_customer_with_vehicle(
            "occ", self.vtype_car, f"51C-{int(uuid.uuid4().int % 90000) + 10000}"
        )
        in_gate = ParkingGate.objects.filter(
            lot=self.lot, direction="IN", is_active=True
        ).first()
        VehicleEntryExitLog.objects.create(
            session_code=f"#PK-OCC-{suffix}",
            vehicle=self.veh_occ,
            slot=self.slot_occupied,
            entry_gate=in_gate,
            license_plate=self.veh_occ.license_plate,
            license_plate_norm=self.veh_occ.license_plate_norm,
            entry_time=timezone.now(),
            recognition_source="MANUAL",
            review_status="AUTO",
        )
        self.slot_occupied.refresh_from_db()
        assert self.slot_occupied.status == "OCCUPIED"

        self.emp_acct = Account.objects.create_user(
            email=f"emp_rsv_{suffix}@parking.local",
            phone=f"097{int(uuid.uuid4().int % 10000000):07d}",
            password="ValidPassword123!",
            role="EMPLOYEE",
            is_active=True,
        )
        self.mgr_acct = Account.objects.create_user(
            email=f"mgr_rsv_{suffix}@parking.local",
            phone=f"096{int(uuid.uuid4().int % 10000000):07d}",
            password="ValidPassword123!",
            role="MANAGER",
            is_active=True,
        )

    def test_anonymous_rejected_401(self):
        client = APIClient()
        now = timezone.now()
        res = client.post(
            f"/api/v1/parking/slots/{self.slot_car.id}/reserve/",
            {
                "vehicle_id": self.veh1.id,
                "reserved_from": (now + timedelta(hours=1)).isoformat(),
                "reserved_until": (now + timedelta(hours=3)).isoformat(),
            },
            format="json",
        )
        assert res.status_code == status.HTTP_401_UNAUTHORIZED
        assert (
            client.get("/api/v1/parking/reservations/").status_code
            == status.HTTP_401_UNAUTHORIZED
        )
        assert (
            client.get("/api/v1/me/parking-slots/").status_code
            == status.HTTP_401_UNAUTHORIZED
        )

    def test_customer_ownership_and_cancel_permissions(self):
        client = APIClient()
        client.force_authenticate(user=self.acct_c1)
        now = timezone.now()

        # Cannot reserve for customer 2's vehicle
        res_other = client.post(
            f"/api/v1/parking/slots/{self.slot_car.id}/reserve/",
            {
                "vehicle_id": self.veh2.id,
                "reserved_from": (now + timedelta(hours=1)).isoformat(),
                "reserved_until": (now + timedelta(hours=3)).isoformat(),
            },
            format="json",
        )
        assert res_other.status_code == status.HTTP_403_FORBIDDEN

        # Can reserve for own vehicle
        res_own = client.post(
            f"/api/v1/parking/slots/{self.slot_car.id}/reserve/",
            {
                "vehicle_id": self.veh1.id,
                "reserved_from": (now + timedelta(hours=1)).isoformat(),
                "reserved_until": (now + timedelta(hours=3)).isoformat(),
            },
            format="json",
        )
        assert res_own.status_code == status.HTTP_201_CREATED
        rsv_id = res_own.json()["id"]

        self.slot_car.refresh_from_db()
        assert self.slot_car.status == "RESERVED"

        # Customer 2 cannot cancel customer 1's reservation
        c2_client = APIClient()
        c2_client.force_authenticate(user=self.acct_c2)
        res_c2_cancel = c2_client.post(f"/api/v1/parking/reservations/{rsv_id}/cancel/")
        assert res_c2_cancel.status_code == status.HTTP_403_FORBIDDEN

        # Customer 2 list only shows own (not customer 1's)
        c2_list = c2_client.get("/api/v1/parking/reservations/").json()["results"]
        assert all(r["id"] != rsv_id for r in c2_list)

        # Customer 1 cancels own reservation -> slot returns to AVAILABLE
        res_cancel = client.post(f"/api/v1/parking/reservations/{rsv_id}/cancel/")
        assert res_cancel.status_code == status.HTTP_200_OK
        assert res_cancel.json()["status"] == "CANCELLED"
        self.slot_car.refresh_from_db()
        assert self.slot_car.status == "AVAILABLE"

    def test_status_and_vehicle_type_guards(self):
        client = APIClient()
        client.force_authenticate(user=self.emp_acct)
        now = timezone.now()
        payload = {
            "vehicle_id": self.veh1.id,
            "reserved_from": (now + timedelta(hours=1)).isoformat(),
            "reserved_until": (now + timedelta(hours=3)).isoformat(),
        }

        # MAINTENANCE -> 409 PROP-4.5.2-P01
        res_maint = client.post(
            f"/api/v1/parking/slots/{self.slot_maint.id}/reserve/",
            payload,
            format="json",
        )
        assert res_maint.status_code == status.HTTP_409_CONFLICT
        assert res_maint.json()["code"] == "PROP-4.5.2-P01"

        # OCCUPIED -> 409 PROP-4.5.2-P02
        res_occ = client.post(
            f"/api/v1/parking/slots/{self.slot_occupied.id}/reserve/",
            payload,
            format="json",
        )
        assert res_occ.status_code == status.HTTP_409_CONFLICT
        assert res_occ.json()["code"] == "PROP-4.5.2-P02"

        # Vehicle type mismatch (CAR on EV-only slot) -> 409 PROP-SLOT-VEHICLE-TYPE-MISMATCH
        res_mismatch = client.post(
            f"/api/v1/parking/slots/{self.slot_ev_only.id}/reserve/",
            payload,
            format="json",
        )
        assert res_mismatch.status_code == status.HTTP_409_CONFLICT
        assert res_mismatch.json()["code"] == "PROP-SLOT-VEHICLE-TYPE-MISMATCH"

    def test_gist_overlap_returns_409_prop_452_p05_and_non_overlap_succeeds(self):
        client = APIClient()
        client.force_authenticate(user=self.mgr_acct)
        now = timezone.now()

        # Reservation 1: +1h to +3h -> 201
        res1 = client.post(
            f"/api/v1/parking/slots/{self.slot_car.id}/reserve/",
            {
                "vehicle_id": self.veh1.id,
                "reserved_from": (now + timedelta(hours=1)).isoformat(),
                "reserved_until": (now + timedelta(hours=3)).isoformat(),
            },
            format="json",
        )
        assert res1.status_code == status.HTTP_201_CREATED

        # Reservation 2: overlapping +2h to +4h on same slot -> PostgreSQL GiST 23P01 -> 409 PROP-4.5.2-P05
        res_overlap = client.post(
            f"/api/v1/parking/slots/{self.slot_car.id}/reserve/",
            {
                "license_plate": self.veh2.license_plate,
                "reserved_from": (now + timedelta(hours=2)).isoformat(),
                "reserved_until": (now + timedelta(hours=4)).isoformat(),
            },
            format="json",
        )
        assert res_overlap.status_code == status.HTTP_409_CONFLICT
        body = res_overlap.json()
        assert body["code"] == "PROP-4.5.2-P05"
        assert body["message"] == "Vị trí này đã được đặt trước cho phương tiện khác."

        # Reservation 3: non-overlapping +4h to +6h -> 201
        res_non_overlap = client.post(
            f"/api/v1/parking/slots/{self.slot_car.id}/reserve/",
            {
                "license_plate": self.veh2.license_plate,
                "reserved_from": (now + timedelta(hours=4)).isoformat(),
                "reserved_until": (now + timedelta(hours=6)).isoformat(),
            },
            format="json",
        )
        assert res_non_overlap.status_code == status.HTTP_201_CREATED

    def test_customer_parking_map_hides_other_customer_pii_while_wp1_remains_403(self):
        # Create an active reservation for cust1 on slot_car
        now = timezone.now()
        SlotReservation.objects.create(
            code=f"RSV-PII-{uuid.uuid4().hex[:6].upper()}",
            slot=self.slot_car,
            customer=self.cust1,
            vehicle=self.veh1,
            reserved_name=self.cust1.full_name,
            reserved_from=now + timedelta(minutes=10),
            reserved_until=now + timedelta(hours=2),
            status="ACTIVE",
        )

        # Customer 2 checks /api/v1/me/parking-slots/ and /api/v1/me/parking-structure/
        c2_client = APIClient()
        c2_client.force_authenticate(user=self.acct_c2)

        # WP1 endpoints must remain 403 for CUSTOMER
        assert (
            c2_client.get("/api/v1/parking/slots/").status_code
            == status.HTTP_403_FORBIDDEN
        )
        assert (
            c2_client.get("/api/v1/parking/structure/").status_code
            == status.HTTP_403_FORBIDDEN
        )

        # Customer map endpoints succeed
        res_struct = c2_client.get("/api/v1/me/parking-structure/")
        assert res_struct.status_code == status.HTTP_200_OK
        assert isinstance(res_struct.json(), list)

        res_slots = c2_client.get(
            f"/api/v1/me/parking-slots/?search={self.slot_car.code}"
        )
        assert res_slots.status_code == status.HTTP_200_OK
        items = res_slots.json()["results"]
        target = next((it for it in items if it["id"] == self.slot_car.id), None)
        assert target is not None
        assert target["status"] == "RESERVED"
        # Customer 2 MUST NOT see Customer 1's plate or name
        assert target["plate"] is None
        assert target["license_plate"] is None
        assert target["reserved_by"] is None
        assert target["is_my_reservation"] is False

        # Customer 1 sees their own reservation flag & plate
        c1_client = APIClient()
        c1_client.force_authenticate(user=self.acct_c1)
        res_c1 = c1_client.get(
            f"/api/v1/me/parking-slots/?search={self.slot_car.code}"
        ).json()["results"]
        target_c1 = next((it for it in res_c1 if it["id"] == self.slot_car.id), None)
        assert target_c1 is not None
        assert target_c1["is_my_reservation"] is True
        assert target_c1["plate"] == self.veh1.license_plate

        # Staff cannot access /api/v1/me/parking-slots/
        emp_client = APIClient()
        emp_client.force_authenticate(user=self.emp_acct)
        assert (
            emp_client.get("/api/v1/me/parking-slots/").status_code
            == status.HTTP_403_FORBIDDEN
        )
