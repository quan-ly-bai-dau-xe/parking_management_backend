"""
Self-service domain services for authenticated customers (/api/v1/me/).
Handles atomic wallet-backed ticket purchases, cancellation policy enforcement,
customer profile updates, and strictly scoped vehicle CRUD.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone
from rest_framework import status

from apps.content.models import Notification
from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_message
from apps.core.models import AdministrativeDistrict, AdministrativeWard
from apps.customers.models import Customer
from apps.parking.models import (
    ParkingSlot,
    PlateBlacklist,
    SlotAllowedVehicleType,
    SlotReservation,
    VehicleEntryExitLog,
)
from apps.tickets.models import Payment, Ticket, TicketType
from apps.vehicles.models import Vehicle
from apps.wallet.models import Wallet, WalletTransaction
from apps.wallet.services.wallet import (
    _validate_idempotency_key,
    debit_wallet,
    ensure_wallet_for_customer,
)


def _ensure_customer_active(customer: Customer) -> None:
    if customer.status != "ACTIVE":
        raise BusinessAPIException(
            code="PROP-CUSTOMER-INACTIVE",
            message=get_message("PROP-CUSTOMER-INACTIVE"),
            status_code=status.HTTP_403_FORBIDDEN,
        )


def _resolve_customer_vehicle(customer_id: int, lookup: str | int) -> Vehicle:
    lookup_str = str(lookup).strip()
    qs = Vehicle.objects.select_related("vehicle_type").filter(
        customer_id=customer_id,
        deleted_at__isnull=True,
    )
    if lookup_str.isdigit():
        vehicle = qs.filter(id=int(lookup_str)).first()
    else:
        vehicle = qs.filter(code__iexact=lookup_str).first()

    if not vehicle:
        raise BusinessAPIException(
            code="MSG-4.4.1-M01",
            message=get_message("MSG-4.4.1-M01"),
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return vehicle


def _resolve_ticket_type(lookup: str | int) -> TicketType:
    lookup_str = str(lookup).strip()
    qs = TicketType.objects.filter(deleted_at__isnull=True)
    if lookup_str.isdigit():
        tt = qs.filter(id=int(lookup_str)).first()
    else:
        tt = qs.filter(code__iexact=lookup_str).first()
    if not tt:
        raise BusinessAPIException(
            code="MSG-4.6.2-M01",
            message="Loại vé không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    return tt


def _select_and_lock_slot(
    vehicle: Vehicle,
    effective_from: Any,
    effective_to: Any,
    slot_id: int | None = None,
) -> ParkingSlot:
    overlapping_tickets = Ticket.objects.filter(
        slot_id=OuterRef("pk"),
        deleted_at__isnull=True,
        status__in=["ACTIVE", "RENEWING"],
        effective_from__lt=effective_to,
        effective_to__gt=effective_from,
    )
    overlapping_reservations = SlotReservation.objects.filter(
        slot_id=OuterRef("pk"),
        deleted_at__isnull=True,
        status="ACTIVE",
        reserved_from__lt=effective_to,
        reserved_until__gt=effective_from,
    )
    allowed_type = SlotAllowedVehicleType.objects.filter(
        slot_id=OuterRef("pk"),
        vehicle_type_id=vehicle.vehicle_type_id,
    )
    open_session_slots = VehicleEntryExitLog.objects.filter(
        slot_id=OuterRef("pk"),
        exit_time__isnull=True,
    )

    if slot_id is not None:
        slot = (
            ParkingSlot.objects.select_for_update()
            .filter(id=slot_id, deleted_at__isnull=True)
            .first()
        )
        if not slot:
            raise BusinessAPIException(
                code="PROP-4.8.5-P05",
                message=get_message("PROP-4.8.5-P05"),
                status_code=status.HTTP_404_NOT_FOUND,
            )
        if slot.status == "MAINTENANCE":
            raise BusinessAPIException(
                code="PROP-4.5.2-P01",
                message=get_message("PROP-4.5.2-P01"),
                status_code=status.HTTP_409_CONFLICT,
            )
        if (
            slot.status in ("OCCUPIED", "CHARGING")
            or VehicleEntryExitLog.objects.filter(
                slot_id=slot.id,
                exit_time__isnull=True,
            ).exists()
        ):
            raise BusinessAPIException(
                code="MSG-4.5.2-M02",
                message="Vị trí đỗ xe hiện đang có xe đỗ, không thể đăng ký vé hiệu lực ngay.",
                status_code=status.HTTP_409_CONFLICT,
            )
        if not SlotAllowedVehicleType.objects.filter(
            slot_id=slot.id,
            vehicle_type_id=vehicle.vehicle_type_id,
        ).exists():
            raise BusinessAPIException(
                code="PROP-SLOT-VEHICLE-TYPE-MISMATCH",
                message=get_message("PROP-SLOT-VEHICLE-TYPE-MISMATCH"),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        has_ticket_overlap = Ticket.objects.filter(
            slot_id=slot.id,
            deleted_at__isnull=True,
            status__in=["ACTIVE", "RENEWING"],
            effective_from__lt=effective_to,
            effective_to__gt=effective_from,
        ).exists()
        has_rsv_overlap = SlotReservation.objects.filter(
            slot_id=slot.id,
            deleted_at__isnull=True,
            status="ACTIVE",
            reserved_from__lt=effective_to,
            reserved_until__gt=effective_from,
        ).exists()
        if has_ticket_overlap or has_rsv_overlap:
            raise BusinessAPIException(
                code="MSG-4.5.2-M02",
                message=get_message("MSG-4.5.2-M02"),
                status_code=status.HTTP_409_CONFLICT,
            )
        return slot

    vtype_code = vehicle.vehicle_type.code.upper() if vehicle.vehicle_type else "CAR"
    preferred_kind = "EV_CHARGING" if vtype_code == "EV" else "STANDARD"

    slot = (
        ParkingSlot.objects.select_for_update(skip_locked=True)
        .filter(deleted_at__isnull=True)
        .exclude(status__in=["MAINTENANCE", "OCCUPIED", "CHARGING"])
        .filter(Exists(allowed_type))
        .filter(~Exists(overlapping_tickets))
        .filter(~Exists(overlapping_reservations))
        .filter(~Exists(open_session_slots))
        .order_by(
            Case(
                When(status="AVAILABLE", then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            Case(
                When(slot_kind=preferred_kind, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            "id",
        )
        .first()
    )
    if not slot:
        raise BusinessAPIException(
            code="MSG-4.6.2-M01",
            message="Không tìm thấy vị trí đỗ xe khả dụng phù hợp để đăng ký vé.",
            status_code=status.HTTP_409_CONFLICT,
        )
    return slot


def purchase_ticket_with_wallet(
    customer: Customer,
    vehicle_lookup: str | int,
    ticket_type_lookup: str | int,
    idempotency_key: str,
    slot_id: int | None = None,
    effective_from: Any = None,
    notes: str | None = None,
    actor_id: int | None = None,
) -> tuple[Ticket, WalletTransaction, bool]:
    """
    Atomically purchase a parking ticket using the customer's prepaid wallet.
    Creates Ticket, Payment(method='WALLET', status='PAID'), and WalletTransaction(DEBIT).
    Rolls back all inserts if wallet balance is insufficient (HTTP 409).
    """
    _ensure_customer_active(customer)
    clean_key = _validate_idempotency_key(idempotency_key)
    vehicle = _resolve_customer_vehicle(customer.id, vehicle_lookup)
    ticket_type = _resolve_ticket_type(ticket_type_lookup)

    if PlateBlacklist.objects.filter(
        license_plate_norm=vehicle.license_plate_norm,
        deleted_at__isnull=True,
    ).exists():
        raise BusinessAPIException(
            code="PROP-4.5.1-P08",
            message=get_message("PROP-4.5.1-P08"),
            status_code=status.HTTP_409_CONFLICT,
        )

    price = ticket_type.default_price
    now = timezone.now()
    eff_from = effective_from or now
    if eff_from < now - timedelta(minutes=5):
        raise BusinessAPIException(
            code="MSG-4.6.2-M01",
            message="Ngày hiệu lực vé không được nằm trong quá khứ.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    duration_days = ticket_type.duration_days or 30
    eff_to = eff_from + timedelta(days=duration_days)

    with transaction.atomic():
        ensured_wallet = ensure_wallet_for_customer(customer.id)
        wallet = (
            Wallet.objects.select_for_update()
            .filter(id=ensured_wallet.id, deleted_at__isnull=True)
            .first()
        )
        if not wallet:
            raise BusinessAPIException(
                code="PROP-WALLET-NOT-FOUND",
                message=get_message("PROP-WALLET-NOT-FOUND"),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        existing_tx = WalletTransaction.objects.filter(
            idempotency_key=clean_key
        ).first()
        if existing_tx is not None:
            if (
                existing_tx.wallet_id != wallet.id
                or existing_tx.kind != "TICKET_PURCHASE"
                or existing_tx.amount != -price
                or existing_tx.reference_type != "TICKET"
                or existing_tx.reference_id is None
            ):
                raise BusinessAPIException(
                    code="PROP-WALLET-IDEMPOTENCY-CONFLICT",
                    message=get_message("PROP-WALLET-IDEMPOTENCY-CONFLICT"),
                    status_code=status.HTTP_409_CONFLICT,
                )
            existing_ticket = (
                Ticket.objects.select_related(
                    "ticket_type",
                    "vehicle",
                    "vehicle__vehicle_type",
                    "slot",
                    "slot__zone",
                    "slot__zone__floor",
                )
                .filter(id=existing_tx.reference_id, customer_id=customer.id)
                .first()
            )
            if not existing_ticket:
                raise BusinessAPIException(
                    code="PROP-WALLET-IDEMPOTENCY-CONFLICT",
                    message=get_message("PROP-WALLET-IDEMPOTENCY-CONFLICT"),
                    status_code=status.HTTP_409_CONFLICT,
                )
            return existing_ticket, existing_tx, False

        has_overlapping_vehicle_ticket = Ticket.objects.filter(
            vehicle_id=vehicle.id,
            deleted_at__isnull=True,
            status__in=["ACTIVE", "RENEWING"],
            effective_from__lt=eff_to,
            effective_to__gt=eff_from,
        ).exists()
        if has_overlapping_vehicle_ticket:
            raise BusinessAPIException(
                code="PROP-WALLET-DUPLICATE-ACTIVE-TICKET",
                message=get_message("PROP-WALLET-DUPLICATE-ACTIVE-TICKET"),
                status_code=status.HTTP_409_CONFLICT,
            )

        slot = _select_and_lock_slot(
            vehicle=vehicle,
            effective_from=eff_from,
            effective_to=eff_to,
            slot_id=slot_id,
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext('ticket_code_sequence'));"
            )
            cursor.execute(
                """
                SELECT COALESCE(
                    MAX(
                        CASE
                            WHEN code ~ '^VT[0-9]+$' THEN SUBSTRING(code FROM 3)::INTEGER
                            ELSE 0
                        END
                    ), 0
                )
                FROM ticket;
                """
            )
            max_num = cursor.fetchone()[0]
            ticket_code = f"VT{max_num + 1:04d}"

        try:
            ticket = Ticket.objects.create(
                code=ticket_code,
                ticket_type=ticket_type,
                customer=customer,
                vehicle=vehicle,
                slot=slot,
                issued_by=None,
                price=price,
                effective_from=eff_from,
                effective_to=eff_to,
                status="ACTIVE",
                notes=notes or "",
            )

            Payment.objects.create(
                code=f"PAY-TKT-{ticket.code}",
                amount=price,
                method="WALLET",
                status="PAID",
                paid_at=now,
                received_by=None,
                session=None,
                ticket=ticket,
                renewal=None,
                notes=f"Thanh toán mua vé {ticket.code} bằng ví khách hàng.",
            )

            tx = debit_wallet(
                wallet_id=wallet.id,
                amount=price,
                kind="TICKET_PURCHASE",
                idempotency_key=clean_key,
                note=f"Mua {ticket_type.name} ({ticket.code}) cho xe {vehicle.license_plate}",
                reference_type="TICKET",
                reference_id=ticket.id,
                actor_id=actor_id,
            )
        except (IntegrityError, DatabaseError) as exc:
            err = str(exc)
            if "excl_ticket_slot_time_overlap" in err:
                raise BusinessAPIException(
                    code="MSG-4.5.2-M02",
                    message=get_message("MSG-4.5.2-M02"),
                    status_code=status.HTTP_409_CONFLICT,
                ) from exc
            if "PROP-SLOT-VEHICLE-TYPE-MISMATCH" in err:
                raise BusinessAPIException(
                    code="PROP-SLOT-VEHICLE-TYPE-MISMATCH",
                    message=get_message("PROP-SLOT-VEHICLE-TYPE-MISMATCH"),
                    status_code=status.HTTP_400_BAD_REQUEST,
                ) from exc
            raise

        hydrated = (
            Ticket.objects.select_related(
                "ticket_type",
                "vehicle",
                "vehicle__vehicle_type",
                "slot",
                "slot__zone",
                "slot__zone__floor",
            )
            .filter(id=ticket.id)
            .first()
        )
        return hydrated or ticket, tx, True


def cancel_my_ticket(customer: Customer, lookup: str | int) -> Ticket:
    """
    Customer ticket cancellation endpoint guard per ADR-0012 / TL-102.
    Paid tickets cannot be self-cancelled or silently refunded.
    """
    lookup_str = str(lookup).strip()
    with transaction.atomic():
        qs = Ticket.objects.select_for_update().filter(
            customer_id=customer.id,
            deleted_at__isnull=True,
        )
        if lookup_str.isdigit():
            ticket = qs.filter(id=int(lookup_str)).first()
        else:
            ticket = qs.filter(code__iexact=lookup_str).first()

        if not ticket:
            raise BusinessAPIException(
                code="PROP-4.6.4-P05",
                message=get_message("PROP-4.6.4-P05"),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if ticket.status == "CANCELLED":
            raise BusinessAPIException(
                code="PROP-4.6.4-P07",
                message=get_message("PROP-4.6.4-P07"),
                status_code=status.HTTP_409_CONFLICT,
            )

        now = timezone.now()
        if ticket.status == "EXPIRED" or ticket.effective_to <= now:
            raise BusinessAPIException(
                code="PROP-4.6.4-P08",
                message=get_message("PROP-4.6.4-P08"),
                status_code=status.HTTP_409_CONFLICT,
            )

        if VehicleEntryExitLog.objects.filter(
            Q(ticket_id=ticket.id) | Q(vehicle_id=ticket.vehicle_id),
            exit_time__isnull=True,
        ).exists():
            raise BusinessAPIException(
                code="PROP-DEL-04-OPEN-SES",
                message=get_message("PROP-DEL-04-OPEN-SES"),
                status_code=status.HTTP_409_CONFLICT,
            )

        if Payment.objects.filter(
            ticket_id=ticket.id,
            status="PAID",
            deleted_at__isnull=True,
        ).exists():
            raise BusinessAPIException(
                code="PROP-4.6.4-P06",
                message=get_message("PROP-4.6.4-P06"),
                status_code=status.HTTP_409_CONFLICT,
            )

        ticket.status = "CANCELLED"
        ticket.save(update_fields=["status"])
        return ticket


def update_my_profile(customer: Customer, data: dict[str, Any]) -> Customer:
    """
    Self-service profile update with optimistic concurrency control (row_version).
    Restricts mutable fields to personal profile attributes only.
    """
    with transaction.atomic():
        locked = (
            Customer.objects.select_for_update()
            .filter(id=customer.id, deleted_at__isnull=True)
            .first()
        )
        if not locked:
            raise BusinessAPIException(
                code="PROP-4.4.4-P02",
                message=get_message("PROP-4.4.4-P02"),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if "row_version" in data and data["row_version"] != locked.row_version:
            raise BusinessAPIException(
                code="MSG-4.3.1-M03",
                message=get_message("MSG-4.3.1-M03"),
                status_code=status.HTTP_409_CONFLICT,
            )

        new_prov_id = data.get("province_id", locked.province_id)
        new_dist_id = data.get("district_id", locked.district_id)
        new_ward_id = data.get("ward_id", locked.ward_id)

        if new_ward_id is not None and new_dist_id is None:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Cơ cấu địa giới hành chính không hợp lệ.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if new_dist_id is not None and new_prov_id is None:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Cơ cấu địa giới hành chính không hợp lệ.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if (
            new_ward_id
            and new_dist_id
            and not AdministrativeWard.objects.filter(
                id=new_ward_id, district_id=new_dist_id
            ).exists()
        ):
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Phường/Xã không thuộc Quận/Huyện đã chọn.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        if (
            new_dist_id
            and new_prov_id
            and not AdministrativeDistrict.objects.filter(
                id=new_dist_id, province_id=new_prov_id
            ).exists()
        ):
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Quận/Huyện không thuộc Tỉnh/Thành phố đã chọn.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        if "email" in data:
            raw_email = data["email"]
            clean_email = (
                str(raw_email).strip().lower()
                if raw_email and str(raw_email).strip()
                else None
            )
            if (
                clean_email
                and Customer.objects.filter(
                    email__iexact=clean_email,
                    deleted_at__isnull=True,
                    is_anonymized=False,
                )
                .exclude(id=locked.id)
                .exists()
            ):
                raise BusinessAPIException(
                    code="MSG-4.3.1-M05",
                    message="Email đã được sử dụng bởi khách hàng khác.",
                    status_code=status.HTTP_409_CONFLICT,
                )
            locked.email = clean_email

        if "identity_card_number" in data and data["identity_card_number"]:
            clean_id_card = str(data["identity_card_number"]).strip()
            if (
                Customer.objects.filter(
                    identity_card_number=clean_id_card,
                    deleted_at__isnull=True,
                    is_anonymized=False,
                )
                .exclude(id=locked.id)
                .exists()
            ):
                raise BusinessAPIException(
                    code="PROP-4.1-P18",
                    message=get_message("PROP-4.1-P18"),
                    status_code=status.HTTP_409_CONFLICT,
                )
            locked.identity_card_number = clean_id_card

        for field in ("full_name", "date_of_birth", "gender", "address"):
            if field in data:
                val = data[field]
                if field in ("gender", "address") and isinstance(val, str):
                    val = val.strip() or None
                setattr(locked, field, val)

        locked.province_id = new_prov_id
        locked.district_id = new_dist_id
        locked.ward_id = new_ward_id

        try:
            locked.save()
        except Exception as exc:
            # Lazy import avoids circular dependency: vehicles -> parking -> wallet -> self_service -> customers -> vehicles.
            from apps.customers.services.error_translation import (
                translate_customer_db_error,
            )

            translate_customer_db_error(exc, operation="update")

        locked.refresh_from_db()
        return locked


def create_my_vehicle(
    customer: Customer,
    data: dict[str, Any],
    actor_id: int | None = None,
) -> Vehicle:
    """Create a vehicle strictly owned by the authenticated customer."""
    # Lazy import avoids circular dependency: customers -> vehicles -> parking -> wallet -> self_service -> vehicles.
    from apps.vehicles.services.vehicles import create_vehicle

    _ensure_customer_active(customer)
    return create_vehicle(
        license_plate=data["license_plate"],
        model_name=data["model_name"],
        vehicle_type_id=data["vehicle_type_id"],
        customer_id=customer.id,
        brand=data.get("brand"),
        color=data.get("color"),
        image_url=data.get("image_url"),
        notes=data.get("notes"),
        actor_id=actor_id,
    )


def update_my_vehicle(
    customer: Customer,
    lookup: str | int,
    data: dict[str, Any],
    actor_id: int | None = None,
) -> Vehicle:
    """Update a vehicle strictly owned by the authenticated customer."""
    from apps.vehicles.services.vehicles import update_vehicle

    _ensure_customer_active(customer)
    vehicle = _resolve_customer_vehicle(customer.id, lookup)
    return update_vehicle(
        vehicle=vehicle,
        data=data,
        actor_id=actor_id,
    )


def delete_my_vehicle(
    customer: Customer,
    lookup: str | int,
    actor_id: int | None = None,
) -> dict[str, str]:
    """Delete a customer's own vehicle enforcing all DEL-03 / R3c guards."""
    from apps.vehicles.services.vehicles import delete_vehicle

    vehicle = _resolve_customer_vehicle(customer.id, lookup)
    return delete_vehicle(vehicle=vehicle, actor_id=actor_id)


@transaction.atomic
def mark_my_notification_read(account_id: int, notification_id: int) -> Notification:
    """Mark one notification owned by account_id as read, honoring ck_notification_read_pair."""
    notif = (
        Notification.objects.select_for_update()
        .filter(
            id=notification_id,
            recipient_account_id=account_id,
            deleted_at__isnull=True,
        )
        .first()
    )
    if not notif:
        raise BusinessAPIException(
            code="MSG-4.4.1-M01",
            message=get_message("MSG-4.4.1-M01"),
            status_code=status.HTTP_404_NOT_FOUND,
        )
    if not notif.is_read or notif.read_at is None:
        notif.is_read = True
        notif.read_at = notif.read_at or timezone.now()
        notif.save(update_fields=["is_read", "read_at"])
    return notif


@transaction.atomic
def mark_all_my_notifications_read(account_id: int) -> int:
    """Mark all unread notifications owned by account_id as read in one UPDATE."""
    now = timezone.now()
    return Notification.objects.filter(
        recipient_account_id=account_id,
        deleted_at__isnull=True,
        is_read=False,
    ).update(is_read=True, read_at=now)
