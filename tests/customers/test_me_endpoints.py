import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Account
from apps.customers.models import Customer
from apps.parking.models import ParkingSlot, SlotReservation, VehicleEntryExitLog
from apps.tickets.models import Payment, Ticket, TicketType
from apps.vehicles.models import Vehicle, VehicleType
from apps.wallet.services.wallet import credit_wallet, ensure_wallet_for_customer


@pytest.fixture
def me_customer():
    suffix = uuid.uuid4().hex[:6]
    acc = Account.objects.create_user(
        email=f"me_cust_{suffix}@example.com",
        password="TestPassword123!",
        role="CUSTOMER",
    )
    cust = Customer.objects.create(
        code=f"KHM{suffix[:4].upper()}",
        full_name="Lê Minh Tự Phục Vụ",
        identity_card_number=f"079{uuid.uuid4().int % 10**9:09d}",
        phone=f"08{uuid.uuid4().int % 10**8:08d}",
        email=acc.email,
        account=acc,
        status="ACTIVE",
    )
    wallet = ensure_wallet_for_customer(cust.id)
    client = APIClient()
    client.force_authenticate(user=acc)
    return acc, cust, wallet, client


@pytest.fixture
def other_me_customer():
    suffix = uuid.uuid4().hex[:6]
    acc = Account.objects.create_user(
        email=f"other_me_{suffix}@example.com",
        password="TestPassword123!",
        role="CUSTOMER",
    )
    cust = Customer.objects.create(
        code=f"KHO{suffix[:4].upper()}",
        full_name="Phạm Thị Khác",
        identity_card_number=f"079{uuid.uuid4().int % 10**9:09d}",
        phone=f"07{uuid.uuid4().int % 10**8:08d}",
        email=acc.email,
        account=acc,
        status="ACTIVE",
    )
    ensure_wallet_for_customer(cust.id)
    client = APIClient()
    client.force_authenticate(user=acc)
    return acc, cust, client


@pytest.mark.django_db
def test_me_profile_get_and_patch_with_occ(me_customer):
    _, cust, wallet, client = me_customer
    credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("125000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"prof-{uuid.uuid4().hex}",
    )

    resp = client.get("/api/v1/me/profile/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == cust.code
    assert Decimal(data["wallet_balance"]) == Decimal("125000.00")
    ver = data["row_version"]

    # Valid PATCH
    patch_resp = client.patch(
        "/api/v1/me/profile/",
        data={"row_version": ver, "full_name": "Lê Minh Đã Cập Nhật", "gender": "Nam"},
        format="json",
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["full_name"] == "Lê Minh Đã Cập Nhật"
    assert patch_resp.json()["row_version"] == ver + 1

    # Stale row_version -> 409
    stale_resp = client.patch(
        "/api/v1/me/profile/",
        data={"row_version": ver, "full_name": "Should Fail"},
        format="json",
    )
    assert stale_resp.status_code == 409
    assert stale_resp.json()["code"] == "MSG-4.3.1-M03"


@pytest.mark.django_db
def test_me_vehicles_crud_and_cross_customer_isolation(me_customer, other_me_customer):
    _, cust, _, client = me_customer
    _, other_cust, other_client = other_me_customer
    vtype = VehicleType.objects.filter(code="CAR", deleted_at__isnull=True).first()
    assert vtype is not None

    # Create vehicle for me_customer
    plate = f"51F-{uuid.uuid4().int % 900 + 100}.{uuid.uuid4().int % 90 + 10}"
    create_resp = client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": plate,
            "model_name": "Camry",
            "brand": "Toyota",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert create_resp.status_code == 201
    v_data = create_resp.json()
    v_code = v_data["code"]

    # List returns only own vehicles AND includes editable fields for CustomerVehicleModal
    list_resp = client.get("/api/v1/me/vehicles/")
    assert list_resp.status_code == 200
    assert list_resp.json()["count"] == 1
    list_item = list_resp.json()["results"][0]
    assert list_item["model_name"] == "Camry"
    assert list_item["brand"] == "Toyota"
    assert "color" in list_item
    assert "notes" in list_item
    assert list_item["vehicle_type_id"] == vtype.id
    assert list_item["vehicle_type_name"] == vtype.name

    # Other customer cannot see/patch/delete this vehicle -> 404
    assert other_client.get(f"/api/v1/me/vehicles/{v_code}/").status_code == 404
    assert (
        other_client.patch(
            f"/api/v1/me/vehicles/{v_code}/",
            data={"row_version": 1, "color": "Đen"},
            format="json",
        ).status_code
        == 404
    )
    assert other_client.delete(f"/api/v1/me/vehicles/{v_code}/").status_code == 404

    # Owner updates by code
    upd = client.patch(
        f"/api/v1/me/vehicles/{v_code}/",
        data={"row_version": v_data["row_version"], "color": "Trắng"},
        format="json",
    )
    assert upd.status_code == 200
    assert upd.json()["color"] == "Trắng"

    # Owner deletes when no ticket/session/reservation -> 200
    del_resp = client.delete(f"/api/v1/me/vehicles/{v_code}/")
    assert del_resp.status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize(
    "ticket_code_type", ["DAILY", "MONTHLY", "QUARTERLY", "YEARLY"]
)
def test_me_vehicle_delete_blocked_for_all_active_ticket_types_r3c(
    me_customer, ticket_code_type
):
    _, cust, wallet, client = me_customer
    vtype = VehicleType.objects.filter(code="CAR", deleted_at__isnull=True).first()
    tt = TicketType.objects.filter(
        code=ticket_code_type, deleted_at__isnull=True
    ).first()
    assert vtype is not None and tt is not None

    credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("10000000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"r3c-fund-{uuid.uuid4().hex}",
    )

    plate = f"51G-{uuid.uuid4().int % 900 + 100}.{uuid.uuid4().int % 90 + 10}"
    v_resp = client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": plate,
            "model_name": "Vios",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert v_resp.status_code == 201
    v_code = v_resp.json()["code"]

    buy_resp = client.post(
        "/api/v1/me/tickets/",
        data={
            "vehicle_code": v_code,
            "ticket_type_code": ticket_code_type,
            "idempotency_key": f"buy-{ticket_code_type}-{uuid.uuid4().hex}",
        },
        format="json",
    )
    assert buy_resp.status_code == 201

    # Delete must be blocked with 409 PROP-DEL-03-ACTIVE-TKT
    del_resp = client.delete(f"/api/v1/me/vehicles/{v_code}/")
    assert del_resp.status_code == 409
    assert del_resp.json()["code"] == "PROP-DEL-03-ACTIVE-TKT"


@pytest.mark.django_db
def test_me_vehicle_delete_allowed_when_ticket_expired(me_customer):
    _, cust, _, client = me_customer
    vtype = VehicleType.objects.filter(code="CAR", deleted_at__isnull=True).first()
    tt = TicketType.objects.filter(code="MONTHLY", deleted_at__isnull=True).first()
    slot = ParkingSlot.objects.filter(
        status="AVAILABLE", deleted_at__isnull=True
    ).first()
    assert vtype and tt and slot

    plate = f"51H-{uuid.uuid4().int % 900 + 100}.{uuid.uuid4().int % 90 + 10}"
    v_resp = client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": plate,
            "model_name": "Accent",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert v_resp.status_code == 201
    v_id = v_resp.json()["id"]
    v_code = v_resp.json()["code"]

    now = timezone.now()
    Ticket.objects.create(
        code=f"VTX{uuid.uuid4().hex[:5].upper()}",
        vehicle_id=v_id,
        customer=cust,
        slot=slot,
        ticket_type=tt,
        price=tt.default_price,
        effective_from=now - timedelta(days=40),
        effective_to=now - timedelta(days=10),
        status="EXPIRED",
    )

    del_resp = client.delete(f"/api/v1/me/vehicles/{v_code}/")
    assert del_resp.status_code == 200


@pytest.mark.django_db
def test_me_ticket_purchase_atomic_rollback_and_cancel_policy(me_customer):
    _, cust, wallet, client = me_customer
    vtype = VehicleType.objects.filter(code="CAR", deleted_at__isnull=True).first()
    tt_monthly = TicketType.objects.filter(
        code="MONTHLY", deleted_at__isnull=True
    ).first()
    assert vtype and tt_monthly

    plate = f"51K-{uuid.uuid4().int % 900 + 100}.{uuid.uuid4().int % 90 + 10}"
    v_resp = client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": plate,
            "model_name": "Mazda 3",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert v_resp.status_code == 201
    v_code = v_resp.json()["code"]

    # 1. Insufficient balance (0 < 500,000) -> 409 and full atomic rollback
    tickets_before = Ticket.objects.count()
    payments_before = Payment.objects.count()
    fail_resp = client.post(
        "/api/v1/me/tickets/",
        data={
            "vehicle_code": v_code,
            "ticket_type_code": "MONTHLY",
            "idempotency_key": f"buy-fail-{uuid.uuid4().hex}",
        },
        format="json",
    )
    assert fail_resp.status_code == 409
    assert fail_resp.json()["code"] == "PROP-WALLET-INSUFFICIENT"
    assert Ticket.objects.count() == tickets_before
    assert Payment.objects.count() == payments_before

    # 2. Top up exact amount and purchase atomically
    credit_wallet(
        wallet_id=wallet.id,
        amount=tt_monthly.default_price,
        kind="TOPUP_VIETQR",
        idempotency_key=f"fund-{uuid.uuid4().hex}",
    )
    buy_key = f"buy-ok-{uuid.uuid4().hex}"
    ok_resp = client.post(
        "/api/v1/me/tickets/",
        data={
            "vehicle_code": v_code,
            "ticket_type_code": "MONTHLY",
            "idempotency_key": buy_key,
        },
        format="json",
    )
    assert ok_resp.status_code == 201
    t_data = ok_resp.json()["ticket"]
    t_code = t_data["code"]
    assert Decimal(t_data["price"]) == tt_monthly.default_price

    wallet.refresh_from_db()
    assert wallet.balance == Decimal("0.00")

    # Payment WALLET PAID created
    pay = Payment.objects.filter(ticket_id=t_data["id"]).first()
    assert pay is not None
    assert pay.method == "WALLET"
    assert pay.status == "PAID"

    # 3. Idempotent retry -> 200 replayed=True
    retry_resp = client.post(
        "/api/v1/me/tickets/",
        data={
            "vehicle_code": v_code,
            "ticket_type_code": "MONTHLY",
            "idempotency_key": buy_key,
        },
        format="json",
    )
    assert retry_resp.status_code == 200
    assert retry_resp.json()["replayed"] is True

    # 4. Self-cancel paid ticket -> 409 PROP-4.6.4-P06, no silent refund
    cancel_resp = client.post(f"/api/v1/me/tickets/{t_code}/cancel/")
    assert cancel_resp.status_code == 409
    assert cancel_resp.json()["code"] == "PROP-4.6.4-P06"
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("0.00")

    # 5. Ticket & Vehicle reference endpoints
    assert client.get("/api/v1/me/ticket-types/").status_code == 200
    assert client.get("/api/v1/me/vehicle-types/").status_code == 200
    assert client.get("/api/v1/me/tickets/").json()["count"] == 1


@pytest.mark.django_db
def test_me_ticket_cancel_unpaid_succeeds_and_blacklisted_customer_blocked(me_customer):
    _, cust, _, client = me_customer
    vtype = VehicleType.objects.filter(code="CAR", deleted_at__isnull=True).first()
    tt = TicketType.objects.filter(code="MONTHLY", deleted_at__isnull=True).first()
    slot = ParkingSlot.objects.filter(
        status="AVAILABLE", deleted_at__isnull=True
    ).first()
    assert vtype and tt and slot

    veh = Vehicle.objects.create(
        code=f"XEU{uuid.uuid4().hex[:4].upper()}",
        license_plate=f"51L-{uuid.uuid4().int % 900 + 100}.{uuid.uuid4().int % 90 + 10}",
        model_name="City",
        vehicle_type=vtype,
        customer=cust,
    )
    now = timezone.now()
    unpaid_ticket = Ticket.objects.create(
        code=f"VTU{uuid.uuid4().hex[:5].upper()}",
        vehicle=veh,
        customer=cust,
        slot=slot,
        ticket_type=tt,
        price=tt.default_price,
        effective_from=now,
        effective_to=now + timedelta(days=30),
        status="ACTIVE",
    )
    cancel_resp = client.post(f"/api/v1/me/tickets/{unpaid_ticket.id}/cancel/")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["ticket"]["status"] == "CANCELLED"

    # Blacklisted customer blocked on write operations
    Customer.objects.filter(id=cust.id).update(
        status="BLACKLISTED", status_reason="Nợ phí"
    )
    # Clear cached customer on next request automatically because new APIClient request builds fresh Request
    bl_resp = client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": "51M-123.45",
            "model_name": "Morning",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert bl_resp.status_code == 403
    assert bl_resp.json()["code"] == "PROP-CUSTOMER-INACTIVE"
    # Keep imports clean
    assert SlotReservation is not None and VehicleEntryExitLog is not None


@pytest.mark.django_db
def test_me_ticket_purchase_blocks_occupied_slot_and_open_session(me_customer):
    _, cust, wallet, client = me_customer
    vtype = VehicleType.objects.filter(code="CAR", deleted_at__isnull=True).first()
    tt = TicketType.objects.filter(code="DAILY", deleted_at__isnull=True).first()
    occupied_slot = ParkingSlot.objects.filter(
        status="OCCUPIED", deleted_at__isnull=True
    ).first()
    assert vtype and tt and occupied_slot

    credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("200000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"occ-fund-{uuid.uuid4().hex}",
    )

    plate = f"51N-{uuid.uuid4().int % 900 + 100}.{uuid.uuid4().int % 90 + 10}"
    v_resp = client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": plate,
            "model_name": "Civic",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert v_resp.status_code == 201
    v_code = v_resp.json()["code"]

    # Explicit occupied slot -> 409 and wallet untouched
    tickets_before = Ticket.objects.count()
    occ_resp = client.post(
        "/api/v1/me/tickets/",
        data={
            "vehicle_code": v_code,
            "ticket_type_code": "DAILY",
            "slot_id": occupied_slot.id,
            "effective_from": timezone.now().isoformat(),
            "idempotency_key": f"occ-slot-{uuid.uuid4().hex}",
        },
        format="json",
    )
    assert occ_resp.status_code == 409
    assert Ticket.objects.count() == tickets_before
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("200000.00")

    # Slot marked AVAILABLE in DB but having an open entry/exit session must also be blocked
    avail_slot = ParkingSlot.objects.filter(
        status="AVAILABLE",
        deleted_at__isnull=True,
        allowed_vehicle_types__vehicle_type_id=vtype.id,
    ).first()
    assert avail_slot is not None
    other_veh = Vehicle.objects.create(
        code=f"XEO{uuid.uuid4().hex[:4].upper()}",
        license_plate=f"51P-{uuid.uuid4().int % 900 + 100}.{uuid.uuid4().int % 90 + 10}",
        model_name="Kona",
        vehicle_type=vtype,
        customer=cust,
    )
    VehicleEntryExitLog.objects.create(
        session_code=f"SES-{uuid.uuid4().hex[:8].upper()}",
        vehicle=other_veh,
        license_plate=other_veh.license_plate,
        slot=avail_slot,
        entry_time=timezone.now() - timedelta(minutes=10),
        recognition_source="MANUAL",
    )
    open_ses_resp = client.post(
        "/api/v1/me/tickets/",
        data={
            "vehicle_code": v_code,
            "ticket_type_code": "DAILY",
            "slot_id": avail_slot.id,
            "effective_from": timezone.now().isoformat(),
            "idempotency_key": f"open-ses-{uuid.uuid4().hex}",
        },
        format="json",
    )
    assert open_ses_resp.status_code == 409
    wallet.refresh_from_db()
    assert wallet.balance == Decimal("200000.00")


@pytest.mark.django_db
def test_me_ticket_purchase_effective_from_iso_and_future_timezone(me_customer):
    _, _, wallet, client = me_customer
    vtype = VehicleType.objects.filter(code="CAR", deleted_at__isnull=True).first()
    tt = TicketType.objects.filter(code="DAILY", deleted_at__isnull=True).first()
    assert vtype and tt

    credit_wallet(
        wallet_id=wallet.id,
        amount=Decimal("200000.00"),
        kind="TOPUP_CASH",
        idempotency_key=f"tz-fund-{uuid.uuid4().hex}",
    )

    plate = f"51A-{uuid.uuid4().int % 900 + 100}.{uuid.uuid4().int % 90 + 10}"
    v_resp = client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": plate,
            "model_name": "CX-5",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert v_resp.status_code == 201
    v_code = v_resp.json()["code"]

    # ISO timestamp for current day succeeds
    ok_today = client.post(
        "/api/v1/me/tickets/",
        data={
            "vehicle_code": v_code,
            "ticket_type_code": "DAILY",
            "effective_from": timezone.now().isoformat(),
            "idempotency_key": f"tz-today-{uuid.uuid4().hex}",
        },
        format="json",
    )
    assert ok_today.status_code == 201
    assert ok_today.json()["ticket"]["status"] == "ACTIVE"

    # Future date with explicit +07:00 timezone offset succeeds for another vehicle
    plate2 = f"51B-{uuid.uuid4().int % 900 + 100}.{uuid.uuid4().int % 90 + 10}"
    v2_resp = client.post(
        "/api/v1/me/vehicles/",
        data={
            "license_plate": plate2,
            "model_name": "Morning",
            "vehicle_type_id": vtype.id,
        },
        format="json",
    )
    assert v2_resp.status_code == 201
    tomorrow = (timezone.now() + timedelta(days=2)).date().isoformat()
    ok_future = client.post(
        "/api/v1/me/tickets/",
        data={
            "vehicle_code": v2_resp.json()["code"],
            "ticket_type_code": "DAILY",
            "effective_from": f"{tomorrow}T00:00:00+07:00",
            "idempotency_key": f"tz-future-{uuid.uuid4().hex}",
        },
        format="json",
    )
    assert ok_future.status_code == 201

    # Past date rejected with 400
    yesterday = (timezone.now() - timedelta(days=1)).date().isoformat()
    past_resp = client.post(
        "/api/v1/me/tickets/",
        data={
            "vehicle_code": v_code,
            "ticket_type_code": "DAILY",
            "effective_from": f"{yesterday}T00:00:00+07:00",
            "idempotency_key": f"tz-past-{uuid.uuid4().hex}",
        },
        format="json",
    )
    assert past_resp.status_code == 400
