"""
Supplementary tests for apps.vehicles targeting edge cases and uncovered branches
to boost test coverage strictly >= 95.0% using 100% real DB entities (no mocks).
"""

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer
from apps.parking.models import ParkingSlot, SlotReservation
from apps.tickets.models import Ticket, TicketType
from apps.vehicles.models import Vehicle
from apps.vehicles.selectors.vehicles import get_vehicles_queryset
from apps.vehicles.serializers.vehicles import (
    VehicleCreateSerializer,
    VehicleDetailSerializer,
    VehicleListSerializer,
)
from apps.vehicles.services.vehicles import (
    PROP_VEH_OWNER_CHANGE_CONFLICT_CODE,
    create_vehicle,
    export_vehicles_csv,
    update_vehicle,
)

pytestmark = pytest.mark.django_db


def test_ordering_ticket_expires_at_asc(car_type, active_customer):
    """
    Test ordering by ticket_expires_at ascending (nulls last) in get_vehicles_queryset.
    Covers line 255 in apps/vehicles/selectors/vehicles.py.
    """
    qs = get_vehicles_queryset(ordering="ticket_expires_at")
    assert qs is not None
    # Execute query to verify SQL generation and execution
    list(qs[:5])


def test_serializer_list_item_stt_without_request(car_type, active_customer):
    """
    Test VehicleListItemSerializer.get_stt when request is missing from context.
    Covers lines 164->170 in apps/vehicles/serializers/vehicles.py.
    """
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert v is not None
    serializer = VehicleListSerializer(v, context={})
    data = serializer.data
    assert data["stt"] == 1


def test_serializer_list_item_rep_ticket_missing_effective_to():
    """
    Test VehicleListSerializer.get_ticket when rep_state is present but
    rep_ticket_effective_to or rep_ticket_type_code is None.
    Covers line 188 in apps/vehicles/serializers/vehicles.py.
    """
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert v is not None
    v.rep_ticket_state = "valid"
    v.rep_ticket_type_code = None
    v.rep_ticket_effective_to = None

    serializer = VehicleListSerializer(v, context={})
    data = serializer.data
    assert data["ticket"] is None


def test_serializer_list_item_unannotated_fallbacks(car_type, active_customer):
    """
    Test VehicleListSerializer.get_ticket when vehicle is plain/unannotated.
    Covers lines 194, 201, 203 in apps/vehicles/serializers/vehicles.py.
    """
    now = timezone.now()
    tt = TicketType.objects.first()

    # Case 1: No ticket_type or ticket_expires_at -> None (line 194)
    v1 = Vehicle(
        code="XE8801",
        license_plate="51K-111.01",
        license_plate_norm="51K11101",
        model_name="TestFallback",
        vehicle_type=car_type,
        customer=active_customer,
        ticket_type=None,
        ticket_expires_at=None,
    )
    s1 = VehicleListSerializer(v1, context={})
    assert s1.data["ticket"] is None

    # Case 2: ticket_expires_at < now -> expired (line 201)
    v2 = Vehicle(
        code="XE8802",
        license_plate="51K-111.02",
        license_plate_norm="51K11102",
        model_name="TestFallback",
        vehicle_type=car_type,
        customer=active_customer,
        ticket_type=tt,
        ticket_expires_at=now - timedelta(days=5),
    )
    s2 = VehicleListSerializer(v2, context={})
    assert s2.data["ticket"]["state"] == "expired"

    # Case 3: ticket_expires_at <= expiring_window -> expiring_soon (line 203)
    v3 = Vehicle(
        code="XE8803",
        license_plate="51K-111.03",
        license_plate_norm="51K11103",
        model_name="TestFallback",
        vehicle_type=car_type,
        customer=active_customer,
        ticket_type=tt,
        ticket_expires_at=now + timedelta(days=2),
    )
    s3 = VehicleListSerializer(v3, context={})
    assert s3.data["ticket"]["state"] == "expiring_soon"


def test_serializer_detail_ticket_edge_cases(car_type, active_customer):
    """
    Test VehicleDetailSerializer.get_ticket edge cases:
    - Missing ticket_type or effective_to (line 307)
    - Non-positive or invalid duration for progress_pct (lines 334->342, 337->342)
    """
    now = timezone.now()
    tt = TicketType.objects.first()
    v = Vehicle.objects.filter(deleted_at__isnull=True).first()
    assert v is not None

    # Case 1: rep_ticket missing expires_at -> None (line 307)
    v._representative_ticket = Ticket(
        code="TK8801",
        vehicle=v,
        customer=active_customer,
        ticket_type=tt,
        effective_from=now,
        effective_to=None,
    )
    s1 = VehicleDetailSerializer(v, context={})
    assert s1.data["ticket"] is None

    # Case 2: effective_from is None -> progress_pct = 0.0 (branch 334->342)
    v._representative_ticket = Ticket(
        code="TK8802",
        vehicle=v,
        customer=active_customer,
        ticket_type=tt,
        effective_from=None,
        effective_to=now + timedelta(days=10),
    )
    s2 = VehicleDetailSerializer(v, context={})
    assert s2.data["ticket"]["progress_pct"] == 0.0

    # Case 3: effective_to <= effective_from -> progress_pct = 0.0 (branch 334->342)
    v._representative_ticket = Ticket(
        code="TK8803",
        vehicle=v,
        customer=active_customer,
        ticket_type=tt,
        effective_from=now,
        effective_to=now - timedelta(days=1),
    )
    s3 = VehicleDetailSerializer(v, context={})
    assert s3.data["ticket"]["progress_pct"] == 0.0

    # Case 4: effective_to == effective_from -> total_duration == 0 (branch 337->342)
    v._representative_ticket = Ticket(
        code="TK8804",
        vehicle=v,
        customer=active_customer,
        ticket_type=tt,
        effective_from=now,
        effective_to=now,
    )
    s4 = VehicleDetailSerializer(v, context={})
    assert s4.data["ticket"]["progress_pct"] == 0.0


def test_serializer_create_field_validations():
    """
    Test VehicleCreateSerializer validation methods for invalid inputs.
    Covers lines 422, 431, 437 in apps/vehicles/serializers/vehicles.py.
    """
    serializer = VehicleCreateSerializer()

    # validate_code with invalid characters (line 422)
    with pytest.raises(ValidationError) as exc1:
        serializer.validate_code("XE!#@$%")
    assert "Mã xe chỉ được chứa chữ cái" in str(exc1.value)

    # validate_license_plate empty (line 431)
    with pytest.raises(ValidationError) as exc2:
        serializer.validate_license_plate("   ")
    assert "Biển số xe không được để trống" in str(exc2.value)

    # validate_model_name empty (line 437)
    with pytest.raises(ValidationError) as exc3:
        serializer.validate_model_name("   ")
    assert "Tên mẫu xe không được để trống" in str(exc3.value)


def test_update_vehicle_type_and_same_customer(car_type, ev_type, active_customer):
    """
    Test update_vehicle updating vehicle_type_id and updating with same customer_id.
    Covers line 308 and branch 312->346 in apps/vehicles/services/vehicles.py.
    """
    v = create_vehicle(
        license_plate="51K-771.12",
        model_name="Transition Test",
        vehicle_type_id=car_type.id,
        customer_id=active_customer.id,
    )

    try:
        # 1. Update vehicle_type from CAR to EV (line 308)
        updated_v = update_vehicle(
            vehicle=v,
            data={"vehicle_type_id": ev_type.id, "row_version": v.row_version},
        )
        assert updated_v.vehicle_type_id == ev_type.id

        # 2. Update with same customer_id (branch 312->346)
        updated_v2 = update_vehicle(
            vehicle=updated_v,
            data={
                "customer_id": active_customer.id,
                "row_version": updated_v.row_version,
            },
        )
        assert updated_v2.customer_id == active_customer.id
    finally:
        v.delete()


def test_update_vehicle_owner_conflict_with_open_session_and_reservation(
    car_type, active_customer
):
    """
    Test update_vehicle owner reassignment guards when vehicle has:
    - Open parking session (lines 326-328)
    - Active slot reservation (lines 329-331)
    """
    new_cust = Customer.objects.create(
        code="KH9911",
        full_name="Chủ Mới Session Test",
        phone="0911991122",
        identity_card_number="049090123111",
    )
    slot = ParkingSlot.objects.filter(
        status="AVAILABLE", deleted_at__isnull=True
    ).first()

    # Case 1: Open session guard using seed vehicle
    v_open = Vehicle.objects.filter(
        deleted_at__isnull=True,
        entry_exit_logs__exit_time__isnull=True,
    ).first()
    assert v_open is not None, (
        "Seed data must contain a parked vehicle with open session"
    )

    with pytest.raises(BusinessAPIException) as exc1:
        update_vehicle(
            vehicle=v_open,
            data={"customer_id": new_cust.id, "row_version": v_open.row_version},
        )
    assert exc1.value.code == PROP_VEH_OWNER_CHANGE_CONFLICT_CODE
    assert exc1.value.details.get("has_open_session") is True

    # Case 2: Active reservation guard on unlinked vehicle
    v = create_vehicle(
        license_plate="51K-772.34",
        model_name="Conflict Guard Test",
        vehicle_type_id=car_type.id,
        customer_id=active_customer.id,
    )
    try:
        rsv = SlotReservation.objects.create(
            code="RSV-2026-9999",
            vehicle=v,
            slot=slot,
            customer=active_customer,
            status="ACTIVE",
            reserved_from=timezone.now(),
            reserved_until=timezone.now() + timedelta(hours=3),
        )
        with pytest.raises(BusinessAPIException) as exc2:
            update_vehicle(
                vehicle=v,
                data={"customer_id": new_cust.id, "row_version": v.row_version},
            )
        assert exc2.value.code == PROP_VEH_OWNER_CHANGE_CONFLICT_CODE
        assert exc2.value.details.get("has_active_reservation") is True

        rsv.status = "CANCELLED"
        rsv.save()
    finally:
        v.delete()
        new_cust.delete()


def test_csv_export_stream_unannotated_fallbacks(car_type, active_customer):
    """
    Test generate_vehicles_csv_stream with unannotated Vehicle queryset.
    Covers lines 519-531 in apps/vehicles/services/vehicles.py.
    """
    now = timezone.now()
    tt = TicketType.objects.first()

    # Vehicles with different ticket_expires_at states
    v_exp = Vehicle.objects.create(
        code="XE8901",
        license_plate="51K-991.01",
        license_plate_norm="51K99101",
        model_name="CSV Test Exp",
        vehicle_type=car_type,
        customer=active_customer,
        ticket_type=tt,
        ticket_expires_at=now - timedelta(days=10),
    )
    v_soon = Vehicle.objects.create(
        code="XE8902",
        license_plate="51K-991.02",
        license_plate_norm="51K99102",
        model_name="CSV Test Soon",
        vehicle_type=car_type,
        customer=active_customer,
        ticket_type=tt,
        ticket_expires_at=now + timedelta(days=2),
    )
    v_valid = Vehicle.objects.create(
        code="XE8903",
        license_plate="51K-991.03",
        license_plate_norm="51K99103",
        model_name="CSV Test Valid",
        vehicle_type=car_type,
        customer=active_customer,
        ticket_type=tt,
        ticket_expires_at=now + timedelta(days=30),
    )
    v_none = Vehicle.objects.create(
        code="XE8904",
        license_plate="51K-991.04",
        license_plate_norm="51K99104",
        model_name="CSV Test None",
        vehicle_type=car_type,
        customer=active_customer,
        ticket_type=None,
        ticket_expires_at=None,
    )

    try:
        raw_qs = Vehicle.objects.filter(
            id__in=[v_exp.id, v_soon.id, v_valid.id, v_none.id]
        )
        rows = list(export_vehicles_csv(raw_qs))
        assert len(rows) == 6  # BOM + header + 4 rows
        combined = "".join(rows)
        assert "Đã hết hạn" in combined
        assert "Sắp hết hạn" in combined
        assert "Còn hạn" in combined
    finally:
        raw_qs.delete()
