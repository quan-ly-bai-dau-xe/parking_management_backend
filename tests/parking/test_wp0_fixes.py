"""
Unit tests for WP0 fixes: J4 (coordinator slot allocation), J5 (windowed gate activity query), J6 (in-flight gate guard).
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.utils import timezone

from apps.audit.models import ActivityLog
from apps.parking.gate_worker.coordinator import GateWorkerCoordinator
from apps.parking.models import (
    ParkingFloor,
    ParkingGate,
    ParkingLot,
    ParkingSlot,
    ParkingZone,
    SlotReservation,
)
from apps.parking.serializers.gates import (
    get_latest_gate_activity_logs_map,
)
from apps.parking.services.gate_decision import (
    ACTION_AUTO_CHECK_IN,
    ACTION_AUTO_CHECK_OUT,
    ACTION_HOLD,
    DecisionResult,
)
from apps.vehicles.models import Vehicle, VehicleType


@pytest.mark.django_db
class TestWP0J5GateActivityWindow:
    """Tests for J5: 24h windowed DISTINCT ON query in get_latest_gate_activity_logs_map."""

    def test_windowed_query_filters_out_logs_older_than_window(self):
        now = timezone.now()
        gate = ParkingGate.objects.filter(is_active=True).first()
        if not gate:
            lot = ParkingLot.objects.first()
            gate = ParkingGate.objects.create(
                lot=lot,
                code="IN_TEST_WP0",
                name="Gate WP0 Test",
                direction="IN",
                is_active=True,
            )

        # Create an old event (> 24h ago)
        old_time = now - timedelta(hours=25)
        ActivityLog.objects.create(
            action="GATE_AUTO_CHECK_IN",
            entity_type="parking_gate",
            entity_id=gate.id,
            message="Old event 25h ago",
            occurred_at=old_time,
        )

        # Call with default 24h window
        result = get_latest_gate_activity_logs_map([gate.id], window_hours=24)
        # Should NOT include the event older than 24h
        assert gate.id not in result

        # Create a recent event (< 24h ago)
        recent_time = now - timedelta(hours=2)
        recent_log = ActivityLog.objects.create(
            action="GATE_AUTO_CHECK_IN",
            entity_type="parking_gate",
            entity_id=gate.id,
            message="Recent event 2h ago",
            occurred_at=recent_time,
        )

        result_recent = get_latest_gate_activity_logs_map([gate.id], window_hours=24)
        assert gate.id in result_recent
        assert result_recent[gate.id].id == recent_log.id

    def test_gate_last_event_window_hours_setting_is_respected(self):
        assert hasattr(settings, "GATE_LAST_EVENT_WINDOW_HOURS")
        assert settings.GATE_LAST_EVENT_WINDOW_HOURS == 24


@pytest.mark.django_db
class TestWP0J4CoordinatorSlotSelection:
    """Tests for J4: Smart slot selection prioritizing vehicle types and excluding active reservations."""

    def setup_method(self):
        self.lot = ParkingLot.objects.first()
        self.floor = ParkingFloor.objects.filter(
            lot=self.lot, deleted_at__isnull=True
        ).first()
        self.zone = ParkingZone.objects.filter(
            floor=self.floor, deleted_at__isnull=True
        ).first()
        self.gate = ParkingGate.objects.filter(
            lot=self.lot, direction="IN", is_active=True
        ).first()

        self.car_type = VehicleType.objects.filter(code="CAR").first()
        self.ev_type = VehicleType.objects.filter(code="EV").first()

    def test_ev_vehicle_prefers_ev_charging_slot(self):
        coordinator = GateWorkerCoordinator.__new__(GateWorkerCoordinator)
        coordinator._managed_gates = {self.gate.id: self.gate}

        # Mock EV vehicle context
        mock_context = MagicMock()
        mock_context.vehicle = MagicMock()
        mock_context.vehicle.id = 9991
        mock_context.vehicle.vehicle_type_id = self.ev_type.id
        mock_context.vehicle.vehicle_type = self.ev_type
        mock_context.active_ticket = None
        mock_context.is_blacklisted = False
        mock_context.open_session_data = None
        mock_context.open_session = None

        with (
            patch(
                "apps.parking.gate_worker.coordinator.get_combined_vehicle_context",
                return_value=mock_context,
            ),
            patch(
                "apps.parking.gate_worker.coordinator.decide_gate_action"
            ) as mock_decide,
        ):
            mock_decide.return_value = DecisionResult(
                action=ACTION_HOLD, audit_action=None, reason_code="TEST"
            )
            scan_result = MagicMock()
            scan_result.best_candidate = MagicMock(confidence=99.0)

            # Find an EV slot and standard slot in DB
            ev_slot = ParkingSlot.objects.filter(
                zone__floor__lot_id=self.gate.lot_id,
                slot_kind="EV_CHARGING",
                status="AVAILABLE",
                deleted_at__isnull=True,
            ).first()
            if ev_slot:
                coordinator._evaluate_and_execute(
                    self.gate, "51A-999.99", scan_result, None
                )
                # Verify decide_gate_action received slot_id matching EV slot
                call_kwargs = mock_decide.call_args[1]
                assert call_kwargs["available_slot"]["slot_id"] == ev_slot.id

    def test_active_reservation_is_excluded_for_other_vehicles(self):
        coordinator = GateWorkerCoordinator.__new__(GateWorkerCoordinator)
        coordinator._managed_gates = {self.gate.id: self.gate}

        now = timezone.now()
        other_veh = Vehicle.objects.filter(deleted_at__isnull=True).first()
        assert other_veh is not None

        # Find available slot matching other_veh type
        avail_slot = (
            ParkingSlot.objects.filter(
                zone__floor__lot_id=self.gate.lot_id,
                status="AVAILABLE",
                deleted_at__isnull=True,
                allowed_vehicle_types__vehicle_type_id=other_veh.vehicle_type_id,
            )
            .order_by("id")
            .first()
        )
        assert avail_slot is not None

        # Create active reservation for slot by other_veh
        SlotReservation.objects.create(
            code="RES-TEST-WP0-01",
            slot=avail_slot,
            vehicle=other_veh,
            customer_id=other_veh.customer_id,
            reserved_from=now - timedelta(minutes=10),
            reserved_until=now + timedelta(minutes=50),
            status="ACTIVE",
        )

        mock_context = MagicMock()
        mock_context.vehicle = MagicMock()
        mock_context.vehicle.id = other_veh.id + 9999  # Different vehicle
        mock_context.vehicle.vehicle_type_id = other_veh.vehicle_type_id
        mock_context.vehicle.vehicle_type = other_veh.vehicle_type
        mock_context.active_ticket = None
        mock_context.is_blacklisted = False
        mock_context.open_session_data = None
        mock_context.open_session = None

        with (
            patch(
                "apps.parking.gate_worker.coordinator.get_combined_vehicle_context",
                return_value=mock_context,
            ),
            patch(
                "apps.parking.gate_worker.coordinator.decide_gate_action"
            ) as mock_decide,
        ):
            mock_decide.return_value = DecisionResult(
                action=ACTION_HOLD, audit_action=None, reason_code="TEST"
            )
            scan_result = MagicMock()
            scan_result.best_candidate = MagicMock(confidence=99.0)

            coordinator._evaluate_and_execute(
                self.gate, "51A-777.77", scan_result, None
            )
            call_kwargs = mock_decide.call_args[1]
            chosen_slot_id = (
                call_kwargs["available_slot"]["slot_id"]
                if call_kwargs["available_slot"]
                else None
            )
            # Must NOT pick the reserved slot
            assert chosen_slot_id != avail_slot.id

    def test_reservation_owner_auto_check_in_with_reserved_slot(self):
        """VULN-J4-01 remediation: Vehicle with active reservation gets its reserved slot even when status is RESERVED."""
        coordinator = GateWorkerCoordinator.__new__(GateWorkerCoordinator)
        self.gate.is_active = True
        self.gate.is_auto_scan = True
        coordinator._managed_gates = {self.gate.id: self.gate}
        coordinator._voter = MagicMock()
        coordinator._record_auto_event = MagicMock()

        now = timezone.now()
        owner_veh = Vehicle.objects.filter(deleted_at__isnull=True).first()
        assert owner_veh is not None

        # Pick an AVAILABLE slot in this lot
        reserved_slot = (
            ParkingSlot.objects.filter(
                zone__floor__lot_id=self.gate.lot_id,
                status="AVAILABLE",
                deleted_at__isnull=True,
            )
            .order_by("id")
            .first()
        )
        assert reserved_slot is not None

        # Create active SlotReservation for owner_veh.
        # Database trigger trg_slot_status_on_reservation automatically flips slot.status to 'RESERVED'.
        SlotReservation.objects.create(
            code="RES-WP0-R2-OWNER",
            slot=reserved_slot,
            vehicle=owner_veh,
            customer_id=owner_veh.customer_id,
            reserved_from=now - timedelta(minutes=15),
            reserved_until=now + timedelta(minutes=45),
            status="ACTIVE",
        )

        reserved_slot.refresh_from_db()
        assert reserved_slot.status == "RESERVED"

        mock_context = MagicMock()
        mock_context.vehicle = owner_veh
        mock_context.active_ticket = None
        mock_context.is_blacklisted = False
        mock_context.open_session_data = None
        mock_context.open_session = None

        with (
            patch(
                "apps.parking.gate_worker.coordinator.get_combined_vehicle_context",
                return_value=mock_context,
            ),
            patch(
                "apps.parking.services.check_in.check_in_vehicle",
                return_value=(MagicMock(), True),
            ) as mock_checkin,
        ):
            scan_result = MagicMock()
            scan_result.best_candidate = MagicMock(confidence=98.5)
            scan_result.review_status = "AUTO"

            res = coordinator._evaluate_and_execute(
                self.gate, owner_veh.license_plate, scan_result, None
            )

            # Verification: Decision must be AUTO_CHECK_IN with VALID_REGISTERED
            assert res.action == ACTION_AUTO_CHECK_IN
            assert res.reason_code == "VALID_REGISTERED"

            # Check-in service must have been invoked with the reserved slot ID
            mock_checkin.assert_called_once()
            call_kwargs = mock_checkin.call_args[1]
            assert call_kwargs["slot_id"] == reserved_slot.id
            assert call_kwargs["license_plate"] == owner_veh.license_plate


@pytest.mark.django_db
class TestWP0J6CoordinatorInFlightGuard:
    """Tests for J6: in-flight guard aborts automated execution if gate becomes deactivated or unmanaged."""

    def setup_method(self):
        self.lot = ParkingLot.objects.first()
        self.gate_in = ParkingGate.objects.filter(
            lot=self.lot, direction="IN", is_active=True
        ).first()
        self.gate_out = ParkingGate.objects.filter(
            lot=self.lot, direction="OUT", is_active=True
        ).first()

    def test_inflight_guard_aborts_checkin_when_gate_unmanaged(self):
        coordinator = GateWorkerCoordinator.__new__(GateWorkerCoordinator)
        # Initially gate is in managed_gates, but will be removed before action execution
        coordinator._managed_gates = {self.gate_in.id: self.gate_in}

        mock_context = MagicMock()
        mock_context.vehicle = None
        mock_context.active_ticket = None
        mock_context.is_blacklisted = False
        mock_context.open_session_data = None

        def side_effect_decide(*args, **kwargs):
            # Simulate gate released mid-execution right after decision
            coordinator._managed_gates.pop(self.gate_in.id, None)
            return DecisionResult(
                action=ACTION_AUTO_CHECK_IN,
                audit_action="GATE_AUTO_CHECK_IN",
                reason_code="VALID_REGISTERED",
            )

        with (
            patch(
                "apps.parking.gate_worker.coordinator.get_combined_vehicle_context",
                return_value=mock_context,
            ),
            patch(
                "apps.parking.gate_worker.coordinator.decide_gate_action",
                side_effect=side_effect_decide,
            ),
            patch("apps.parking.services.check_in.check_in_vehicle") as mock_checkin,
        ):
            scan_result = MagicMock()
            scan_result.best_candidate = MagicMock(confidence=99.0)

            res = coordinator._evaluate_and_execute(
                self.gate_in, "51A-123.45", scan_result, None
            )

            # In-flight guard should have prevented check_in_vehicle from being called
            mock_checkin.assert_not_called()
            assert res.action == ACTION_HOLD
            assert res.reason_code == "GATE_DEACTIVATED"

    def test_inflight_guard_aborts_checkout_when_gate_deactivated(self):
        coordinator = GateWorkerCoordinator.__new__(GateWorkerCoordinator)
        mock_gate = MagicMock()
        mock_gate.id = self.gate_out.id
        mock_gate.code = self.gate_out.code
        mock_gate.direction = "OUT"
        mock_gate.is_active = True
        coordinator._managed_gates = {mock_gate.id: mock_gate}

        mock_context = MagicMock()
        mock_context.vehicle = None
        mock_context.active_ticket = None
        mock_context.is_blacklisted = False
        mock_context.open_session_data = {"session_code": "SS-TEST"}
        mock_context.open_session = MagicMock()

        def side_effect_decide(*args, **kwargs):
            # Deactivate gate before execution
            mock_gate.is_active = False
            return DecisionResult(
                action=ACTION_AUTO_CHECK_OUT,
                audit_action="GATE_AUTO_CHECK_OUT",
                reason_code="VALID_FEE_ZERO",
            )

        with (
            patch(
                "apps.parking.gate_worker.coordinator.get_combined_vehicle_context",
                return_value=mock_context,
            ),
            patch(
                "apps.parking.gate_worker.coordinator.calculate_parking_fee",
                return_value=0,
            ),
            patch(
                "apps.parking.gate_worker.coordinator.decide_gate_action",
                side_effect=side_effect_decide,
            ),
            patch("apps.parking.services.check_out.check_out_vehicle") as mock_checkout,
        ):
            scan_result = MagicMock()
            scan_result.best_candidate = MagicMock(confidence=99.0)

            res = coordinator._evaluate_and_execute(
                mock_gate, "51A-123.45", scan_result, None
            )

            # In-flight guard should prevent check_out_vehicle
            mock_checkout.assert_not_called()
            assert res.action == ACTION_HOLD
            assert res.reason_code == "GATE_DEACTIVATED"
