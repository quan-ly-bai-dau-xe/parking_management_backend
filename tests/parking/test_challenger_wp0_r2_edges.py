import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone

from apps.parking.gate_worker.coordinator import (
    ACTION_AUTO_CHECK_IN,
    GateWorkerCoordinator,
)
from apps.parking.models import (
    ParkingGate,
    ParkingLot,
    ParkingSlot,
    VehicleEntryExitLog,
)
from apps.tickets.models import Ticket, TicketType
from apps.vehicles.models import Vehicle


class TestChallengerActiveTicketReservedSlotEdges(TestCase):
    """
    Adversarial and Edge tests by Challenger 2 for Milestone WP0 Round 2:
    Validates ticket assigned slot handling when slot is in 'RESERVED' or other states.
    Uses django.test.TestCase for automatic per-test transaction rollback,
    guaranteeing zero database pollution and respecting immutable table triggers.
    """

    def setUp(self):
        self.lot = ParkingLot.objects.first()
        assert self.lot is not None
        self.gate = ParkingGate.objects.filter(
            lot=self.lot, direction="IN", is_active=True
        ).first()
        assert self.gate is not None
        self.gate.is_auto_scan = True

    def _get_free_available_slot(self):
        """Helper to get an available slot not bound to any ticket."""
        ticket_slot_ids = Ticket.objects.filter(
            slot__isnull=False, deleted_at__isnull=True
        ).values_list("slot_id", flat=True)
        slot = (
            ParkingSlot.objects.filter(
                zone__floor__lot_id=self.gate.lot_id,
                status="AVAILABLE",
                deleted_at__isnull=True,
            )
            .exclude(id__in=ticket_slot_ids)
            .order_by("id")
            .first()
        )
        assert slot is not None, "No free available slot found in lot"
        return slot

    def _get_vehicle_without_open_session(self):
        """Helper to get a registered vehicle that is currently outside the lot."""
        open_ids = VehicleEntryExitLog.objects.filter(
            exit_time__isnull=True, vehicle_id__isnull=False
        ).values_list("vehicle_id", flat=True)
        vehicle = (
            Vehicle.objects.filter(deleted_at__isnull=True)
            .exclude(id__in=open_ids)
            .first()
        )
        assert vehicle is not None, "No vehicle without open session found"
        return vehicle

    def test_active_ticket_assigned_slot_reserved_status_auto_check_in_decision(self):
        """
        Test Case 1: Vehicle with active ticket assigned to a slot in 'RESERVED' status.
        Coordinator must allocate that assigned slot and decide ACTION_AUTO_CHECK_IN.
        """
        coordinator = GateWorkerCoordinator.__new__(GateWorkerCoordinator)
        coordinator._managed_gates = {self.gate.id: self.gate}
        coordinator._voter = MagicMock()
        coordinator._record_auto_event = MagicMock()

        now = timezone.now()
        vehicle = self._get_vehicle_without_open_session()
        slot = self._get_free_available_slot()
        ticket_type = TicketType.objects.first()
        assert ticket_type is not None

        ticket = Ticket.objects.create(
            code=f"TK{uuid.uuid4().hex[:6]}",
            vehicle=vehicle,
            customer=vehicle.customer,
            slot=slot,
            ticket_type=ticket_type,
            effective_from=now - timedelta(days=5),
            effective_to=now + timedelta(days=25),
            status="ACTIVE",
            price=Decimal("500000.00"),
        )

        slot.refresh_from_db()
        if slot.status != "RESERVED":
            ParkingSlot.objects.filter(id=slot.id).update(status="RESERVED")
            slot.refresh_from_db()
        assert slot.status == "RESERVED"

        mock_context = MagicMock()
        mock_context.vehicle = vehicle
        mock_context.active_ticket = ticket
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
            scan_result.best_candidate = MagicMock(confidence=98.0)
            scan_result.review_status = "AUTO"

            res = coordinator._evaluate_and_execute(
                self.gate, vehicle.license_plate, scan_result, None
            )

            # Verification 1: Action must be AUTO_CHECK_IN with VALID_REGISTERED
            assert res.action == ACTION_AUTO_CHECK_IN
            assert res.reason_code == "VALID_REGISTERED"

            # Verification 2: check_in_vehicle called with ticket assigned slot ID
            mock_checkin.assert_called_once()
            call_kwargs = mock_checkin.call_args[1]
            assert call_kwargs["slot_id"] == slot.id
            assert call_kwargs["license_plate"] == vehicle.license_plate

    def test_active_ticket_assigned_slot_reserved_status_end_to_end_real_db(self):
        """
        Test Case 2: Real DB execution (NO mocking of check_in_vehicle).
        Verifies that check_in_vehicle and DB triggers allow check-in for ticket's assigned RESERVED slot.
        """
        coordinator = GateWorkerCoordinator.__new__(GateWorkerCoordinator)
        coordinator._managed_gates = {self.gate.id: self.gate}
        coordinator._voter = MagicMock()
        coordinator._record_auto_event = MagicMock()
        coordinator._snapshot_uploader = MagicMock()

        now = timezone.now()
        vehicle = self._get_vehicle_without_open_session()
        slot = self._get_free_available_slot()
        ticket_type = TicketType.objects.first()

        # Invalidate any prior active tickets for this vehicle
        Ticket.objects.filter(vehicle=vehicle, status="ACTIVE").update(status="EXPIRED")

        Ticket.objects.create(
            code=f"TK{uuid.uuid4().hex[:6]}",
            vehicle=vehicle,
            customer=vehicle.customer,
            slot=slot,
            ticket_type=ticket_type,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=29),
            status="ACTIVE",
            price=Decimal("600000.00"),
        )

        ParkingSlot.objects.filter(id=slot.id).update(status="RESERVED")
        slot.refresh_from_db()
        assert slot.status == "RESERVED"

        scan_result = MagicMock()
        scan_result.best_candidate = MagicMock(confidence=97.5)
        scan_result.review_status = "AUTO"

        # Execute end-to-end through real coordinator and real DB
        res = coordinator._evaluate_and_execute(
            self.gate, vehicle.license_plate, scan_result, None
        )

        # Assert decision
        assert res.action == ACTION_AUTO_CHECK_IN
        assert res.reason_code == "VALID_REGISTERED"

        # Verify real database session created
        entry_log = (
            VehicleEntryExitLog.objects.filter(
                license_plate=vehicle.license_plate,
                exit_time__isnull=True,
            )
            .order_by("-id")
            .first()
        )
        assert entry_log is not None
        assert entry_log.slot_id == slot.id

        # Verify DB trigger updated slot status to OCCUPIED
        slot.refresh_from_db()
        assert slot.status == "OCCUPIED"

    def test_active_ticket_assigned_slot_subsequently_maintenance_falls_back(self):
        """
        Test Case 3 (Adversarial): Assigned slot later marked as MAINTENANCE.
        Coordinator must skip the maintenance slot and allocate another AVAILABLE slot.
        """
        coordinator = GateWorkerCoordinator.__new__(GateWorkerCoordinator)
        coordinator._managed_gates = {self.gate.id: self.gate}
        coordinator._voter = MagicMock()
        coordinator._record_auto_event = MagicMock()

        now = timezone.now()
        vehicle = self._get_vehicle_without_open_session()
        slot = self._get_free_available_slot()
        ticket_type = TicketType.objects.first()

        ticket = Ticket.objects.create(
            code=f"TK{uuid.uuid4().hex[:6]}",
            vehicle=vehicle,
            customer=vehicle.customer,
            slot=slot,
            ticket_type=ticket_type,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=29),
            status="ACTIVE",
            price=Decimal("500000.00"),
        )

        # Slot later marked as MAINTENANCE by admin
        ParkingSlot.objects.filter(id=slot.id).update(status="MAINTENANCE")
        slot.refresh_from_db()
        assert slot.status == "MAINTENANCE"

        mock_context = MagicMock()
        mock_context.vehicle = vehicle
        mock_context.active_ticket = ticket
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
            scan_result.best_candidate = MagicMock(confidence=96.0)
            scan_result.review_status = "AUTO"

            res = coordinator._evaluate_and_execute(
                self.gate, vehicle.license_plate, scan_result, None
            )

            assert res.action == ACTION_AUTO_CHECK_IN
            mock_checkin.assert_called_once()
            call_kwargs = mock_checkin.call_args[1]
            chosen_slot_id = call_kwargs["slot_id"]
            # Invariant: Must NOT allocate the maintenance slot
            assert chosen_slot_id != slot.id
            # Invariant: Must allocate a valid AVAILABLE slot
            allocated_slot = ParkingSlot.objects.get(id=chosen_slot_id)
            assert allocated_slot.status == "AVAILABLE"
            assert allocated_slot.deleted_at is None

    def test_other_unregistered_vehicle_cannot_steal_reserved_slot(self):
        """
        Test Case 4 (Adversarial Security): Slot in RESERVED status (owned by active ticket).
        An unregistered or regular vehicle MUST NOT be assigned this RESERVED slot.
        """
        coordinator = GateWorkerCoordinator.__new__(GateWorkerCoordinator)
        coordinator._managed_gates = {self.gate.id: self.gate}
        coordinator._voter = MagicMock()
        coordinator._record_auto_event = MagicMock()

        now = timezone.now()
        ticket_owner = self._get_vehicle_without_open_session()
        reserved_slot = self._get_free_available_slot()
        ticket_type = TicketType.objects.first()

        Ticket.objects.create(
            code=f"TK{uuid.uuid4().hex[:6]}",
            vehicle=ticket_owner,
            customer=ticket_owner.customer,
            slot=reserved_slot,
            ticket_type=ticket_type,
            effective_from=now - timedelta(days=1),
            effective_to=now + timedelta(days=29),
            status="ACTIVE",
            price=Decimal("500000.00"),
        )

        ParkingSlot.objects.filter(id=reserved_slot.id).update(status="RESERVED")
        reserved_slot.refresh_from_db()
        assert reserved_slot.status == "RESERVED"

        # Another vehicle arriving at the gate
        other_vehicle = (
            Vehicle.objects.filter(deleted_at__isnull=True)
            .exclude(id=ticket_owner.id)
            .first()
        )
        assert other_vehicle is not None

        mock_context = MagicMock()
        mock_context.vehicle = other_vehicle
        mock_context.active_ticket = None  # No ticket for this other vehicle
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
            mock_decide.return_value = MagicMock(
                action=ACTION_AUTO_CHECK_IN, reason_code="TEST"
            )
            scan_result = MagicMock()
            scan_result.best_candidate = MagicMock(confidence=98.0)
            scan_result.review_status = "AUTO"

            coordinator._evaluate_and_execute(
                self.gate, other_vehicle.license_plate, scan_result, None
            )

            call_kwargs = mock_decide.call_args[1]
            chosen_slot_data = call_kwargs.get("available_slot")
            if chosen_slot_data:
                # Security invariant: General vehicle cannot be assigned the RESERVED slot
                assert chosen_slot_data["slot_id"] != reserved_slot.id
