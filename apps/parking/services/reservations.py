"""
Services for SlotReservation domain (SRS 4.5.2, TL-04, TL-15, TL-38).
Enforces slot status validation, vehicle ownership, allowed vehicle type matching,
and relies on PostgreSQL GiST exclusion constraint excl_reservation_slot_time_overlap
(mapped to HTTP 409 PROP-4.5.2-P05) to prevent overlapping reservations.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone
from rest_framework import status

from apps.audit.models import ActivityLog
from apps.core.exceptions import (
    BusinessAPIException,
    map_database_exception_to_business_error,
)
from apps.core.logging import mask_plate
from apps.core.messages import get_message, get_prop_message
from apps.customers.models import Customer
from apps.employees.models import Employee
from apps.parking.models import (
    ParkingSlot,
    PlateBlacklist,
    SlotAllowedVehicleType,
    SlotReservation,
    VehicleEntryExitLog,
)
from apps.parking.services.ocr import PlateRecognizer
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle

logger = logging.getLogger(__name__)


def _sanitize_reservation_phone(raw_phone: str | None) -> str | None:
    """Normalize phone to 9-15 digits matching ck_reservation_phone_digits or return None."""
    if not raw_phone:
        return None
    digits = re.sub(r"\D", "", str(raw_phone))
    if 9 <= len(digits) <= 15:
        return digits
    return None


def _generate_reservation_code() -> str:
    """Generate unique reservation code RSV-YYYY-NNNN under advisory xact lock."""
    now = timezone.now()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(hashtext('slot_reservation_code_sequence'));"
        )
        cursor.execute(
            """
            SELECT COALESCE(
                MAX(
                    CASE
                        WHEN code ~ '^RSV-[0-9]{4}-[0-9]+$'
                        THEN SUBSTRING(code FROM 'RSV-[0-9]{4}-([0-9]+)$')::INTEGER
                        ELSE 0
                    END
                ), 0
            )
            FROM slot_reservation;
            """
        )
        max_seq = int(cursor.fetchone()[0] or 0)

    next_seq = max_seq + 1
    candidate = f"RSV-{now:%Y}-{next_seq:04d}"
    while SlotReservation.all_objects.filter(code=candidate).exists():
        next_seq += 1
        candidate = f"RSV-{now:%Y}-{next_seq:04d}"
    return candidate


def expire_overdue_reservations(slot_id: int | None = None) -> int:
    """Mark overdue ACTIVE reservations as EXPIRED so DB triggers recompute slot status."""
    now = timezone.now()
    qs = SlotReservation.objects.filter(
        status="ACTIVE",
        reserved_until__lte=now,
        deleted_at__isnull=True,
    )
    if slot_id is not None:
        qs = qs.filter(slot_id=slot_id)
    return qs.update(status="EXPIRED")


def create_slot_reservation(
    slot_id: int,
    data: dict[str, Any],
    actor_user: Any,
) -> SlotReservation:
    """
    Create a slot reservation atomically with strict guards:
    - Slot must exist (404 PROP-4.8.5-P05).
    - MAINTENANCE -> 409 PROP-4.5.2-P01.
    - OCCUPIED/CHARGING or open session -> 409 PROP-4.5.2-P02.
    - CUSTOMER can only reserve for their own vehicle (403 MSG-4.2-M01 otherwise).
    - EMPLOYEE/MANAGER can reserve for any registered non-blacklisted vehicle.
    - Vehicle type must match slot_allowed_vehicle_type -> 409 PROP-SLOT-VEHICLE-TYPE-MISMATCH.
    - Overlapping active ticket -> 409 MSG-4.5.2-M02.
    - Overlapping active reservation -> PostgreSQL GiST 23P01 -> 409 PROP-4.5.2-P05.
    """
    reserved_from = data["reserved_from"]
    reserved_until = data["reserved_until"]
    now = timezone.now()

    if reserved_until <= reserved_from or reserved_until <= now:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Khoảng thời gian đặt chỗ không hợp lệ (thời gian kết thúc phải sau thời gian bắt đầu và sau hiện tại).",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    role = getattr(actor_user, "role", None)
    if role not in ("CUSTOMER", "EMPLOYEE", "MANAGER"):
        raise BusinessAPIException(
            code="MSG-4.2-M01",
            message=get_message(
                "MSG-4.2-M01", "Bạn không có quyền thực hiện thao tác này."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    with transaction.atomic():
        # Clear any overdue active reservations on this slot before locking & checking
        expire_overdue_reservations(slot_id=slot_id)

        slot = (
            ParkingSlot.objects.select_for_update()
            .select_related("zone__floor")
            .filter(id=slot_id, deleted_at__isnull=True)
            .first()
        )
        if not slot:
            raise BusinessAPIException(
                code="PROP-4.8.5-P05",
                message=get_prop_message(
                    "PROP-4.8.5-P05", "Vị trí đỗ xe không tồn tại hoặc đã bị xóa."
                ),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if slot.status == "MAINTENANCE":
            raise BusinessAPIException(
                code="PROP-4.5.2-P01",
                message=get_prop_message("PROP-4.5.2-P01", "Vị trí này đang bảo trì."),
                status_code=status.HTTP_409_CONFLICT,
            )

        has_open_session = VehicleEntryExitLog.objects.filter(
            slot_id=slot.id, exit_time__isnull=True
        ).exists()
        if slot.status in ("OCCUPIED", "CHARGING") or has_open_session:
            raise BusinessAPIException(
                code="PROP-4.5.2-P02",
                message=get_prop_message(
                    "PROP-4.5.2-P02",
                    "Không thể chuyển trạng thái vị trí khi đang có xe đỗ trong ô.",
                ),
                status_code=status.HTTP_409_CONFLICT,
            )

        # Resolve target vehicle
        vehicle_id = data.get("vehicle_id")
        raw_plate = (data.get("license_plate") or "").strip()
        vehicle: Vehicle | None = None

        if vehicle_id is not None:
            vehicle = (
                Vehicle.objects.select_related("vehicle_type", "customer")
                .filter(id=vehicle_id, deleted_at__isnull=True)
                .first()
            )
        elif raw_plate:
            norm_plate = PlateRecognizer.normalize_plate(raw_plate)
            if norm_plate:
                vehicle = (
                    Vehicle.objects.select_related("vehicle_type", "customer")
                    .filter(license_plate_norm=norm_plate, deleted_at__isnull=True)
                    .first()
                )

        if vehicle is None:
            if role == "CUSTOMER":
                raise BusinessAPIException(
                    code="MSG-4.4.1-M01",
                    message=get_message("MSG-4.4.1-M01", "Không tìm thấy phương tiện."),
                    status_code=status.HTTP_404_NOT_FOUND,
                )
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Không tìm thấy phương tiện đã đăng ký trong hệ thống theo biển số hoặc ID cung cấp.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        created_by_employee: Employee | None = None
        if role == "CUSTOMER":
            customer = Customer.objects.filter(
                account_id=actor_user.id, deleted_at__isnull=True
            ).first()
            if customer is None:
                raise BusinessAPIException(
                    code="MSG-4.2-M01",
                    message=get_message(
                        "MSG-4.2-M01", "Bạn không có quyền thực hiện thao tác này."
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            if customer.status != "ACTIVE":
                raise BusinessAPIException(
                    code="PROP-CUSTOMER-INACTIVE",
                    message=get_prop_message(
                        "PROP-CUSTOMER-INACTIVE",
                        "Tài khoản khách hàng đang bị tạm ngưng hoặc thuộc danh sách đen, không thể thực hiện thao tác này.",
                    ),
                    status_code=status.HTTP_403_FORBIDDEN,
                )
            if vehicle.customer_id != customer.id:
                raise BusinessAPIException(
                    code="MSG-4.2-M01",
                    message="Bạn chỉ có thể đặt chỗ cho phương tiện thuộc sở hữu của mình.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )
        else:
            customer = vehicle.customer
            if customer and customer.status == "BLACKLISTED":
                raise BusinessAPIException(
                    code="PROP-4.5.1-P08",
                    message=get_prop_message(
                        "PROP-4.5.1-P08",
                        "Biển số xe nằm trong danh sách đen, không được phép vào bãi.",
                    ),
                    status_code=status.HTTP_409_CONFLICT,
                )
            created_by_employee = Employee.objects.filter(
                account_id=actor_user.id, deleted_at__isnull=True
            ).first()

        if PlateBlacklist.objects.filter(
            license_plate_norm=vehicle.license_plate_norm,
            is_active=True,
            deleted_at__isnull=True,
        ).exists():
            raise BusinessAPIException(
                code="PROP-4.5.1-P08",
                message=get_prop_message(
                    "PROP-4.5.1-P08",
                    "Biển số xe nằm trong danh sách đen, không được phép vào bãi.",
                ),
                status_code=status.HTTP_409_CONFLICT,
            )

        # Enforce slot_allowed_vehicle_type match
        is_allowed_type = SlotAllowedVehicleType.objects.filter(
            slot_id=slot.id,
            vehicle_type_id=vehicle.vehicle_type_id,
        ).exists()
        if not is_allowed_type:
            raise BusinessAPIException(
                code="PROP-SLOT-VEHICLE-TYPE-MISMATCH",
                message=get_prop_message(
                    "PROP-SLOT-VEHICLE-TYPE-MISMATCH",
                    "Loại phương tiện không tương thích với danh sách loại xe cho phép của vị trí đỗ này.",
                ),
                status_code=status.HTTP_409_CONFLICT,
            )

        # Check conflicting active ticket on the slot during [reserved_from, reserved_until)
        has_conflicting_ticket = (
            Ticket.objects.filter(
                slot_id=slot.id,
                deleted_at__isnull=True,
                status__in=["ACTIVE", "RENEWING"],
                effective_from__lt=reserved_until,
                effective_to__gt=reserved_from,
            )
            .exclude(vehicle_id=vehicle.id)
            .exists()
        )
        if has_conflicting_ticket:
            raise BusinessAPIException(
                code="MSG-4.5.2-M02",
                message=get_message(
                    "MSG-4.5.2-M02",
                    "Vị trí này đã có xe đk vé và đang sử dụng",
                ),
                status_code=status.HTTP_409_CONFLICT,
            )

        # If slot is manually marked RESERVED with no underlying active reservation, block it cleanly.
        # If an active reservation exists, let PostgreSQL GiST excl_reservation_slot_time_overlap
        # decide whether [reserved_from, reserved_until) overlaps (23P01 -> 409 PROP-4.5.2-P05).
        if slot.status == "RESERVED":
            has_active_reservation = SlotReservation.objects.filter(
                slot_id=slot.id,
                deleted_at__isnull=True,
                status="ACTIVE",
                reserved_until__gt=now,
            ).exists()
            if not has_active_reservation:
                raise BusinessAPIException(
                    code="PROP-4.5.2-P05",
                    message=get_prop_message(
                        "PROP-4.5.2-P05",
                        "Vị trí này đã được đặt trước cho phương tiện khác.",
                    ),
                    status_code=status.HTTP_409_CONFLICT,
                )

        res_code = _generate_reservation_code()
        reserved_name = (data.get("reserved_name") or "").strip() or (
            customer.full_name if customer else None
        )
        reserved_phone = _sanitize_reservation_phone(
            data.get("reserved_phone") or (customer.phone if customer else None)
        )
        notes = (data.get("notes") or "").strip() or None

        try:
            # Use atomic savepoint so any IntegrityError (23P01 GiST) leaves transaction clean
            with transaction.atomic():
                reservation = SlotReservation.objects.create(
                    code=res_code,
                    slot=slot,
                    customer=customer,
                    vehicle=vehicle,
                    reserved_name=reserved_name,
                    reserved_phone=reserved_phone,
                    reserved_from=reserved_from,
                    reserved_until=reserved_until,
                    status="ACTIVE",
                    notes=notes,
                    created_by=created_by_employee,
                )
        except (IntegrityError, DatabaseError) as exc:
            mapped = map_database_exception_to_business_error(exc)
            if mapped is not None:
                raise mapped from exc
            raise

        ActivityLog.objects.create(
            actor_account_id=getattr(actor_user, "id", None),
            action="SLOT_RESERVE",
            entity_type="SLOT_RESERVATION",
            entity_id=reservation.id,
            message=(
                f"Đặt trước ô {slot.code} ({res_code}) cho xe {mask_plate(vehicle.license_plate)}"
            ),
        )

    return reservation


def cancel_slot_reservation(
    reservation_id: int,
    actor_user: Any,
) -> SlotReservation:
    """
    Cancel an ACTIVE slot reservation.
    - CUSTOMER may only cancel their own reservation (403 otherwise).
    - EMPLOYEE/MANAGER may cancel any active reservation.
    DB trigger trg_sync_slot_status_on_reservation automatically recomputes parking_slot.status.
    """
    role = getattr(actor_user, "role", None)
    if role not in ("CUSTOMER", "EMPLOYEE", "MANAGER"):
        raise BusinessAPIException(
            code="MSG-4.2-M01",
            message=get_message(
                "MSG-4.2-M01", "Bạn không có quyền thực hiện thao tác này."
            ),
            status_code=status.HTTP_403_FORBIDDEN,
        )

    with transaction.atomic():
        reservation = (
            SlotReservation.objects.select_for_update(of=("self",))
            .select_related("slot", "customer", "vehicle")
            .filter(id=reservation_id, deleted_at__isnull=True)
            .first()
        )
        if not reservation:
            raise BusinessAPIException(
                code="MSG-4.4.1-M01",
                message=get_message("MSG-4.4.1-M01", "Không tìm thấy đặt chỗ."),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if role == "CUSTOMER":
            customer = Customer.objects.filter(
                account_id=actor_user.id, deleted_at__isnull=True
            ).first()
            if customer is None or reservation.customer_id != customer.id:
                raise BusinessAPIException(
                    code="MSG-4.2-M01",
                    message="Bạn không có quyền hủy đặt chỗ của khách hàng khác.",
                    status_code=status.HTTP_403_FORBIDDEN,
                )

        if reservation.status != "ACTIVE":
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Chỉ có thể hủy đặt chỗ đang ở trạng thái hoạt động (ACTIVE).",
                status_code=status.HTTP_409_CONFLICT,
            )

        reservation.status = "CANCELLED"
        reservation.save(update_fields=["status", "updated_at"])

        slot_code = (
            reservation.slot.code if reservation.slot else str(reservation.slot_id)
        )
        ActivityLog.objects.create(
            actor_account_id=getattr(actor_user, "id", None),
            action="SLOT_RESERVE_CANCEL",
            entity_type="SLOT_RESERVATION",
            entity_id=reservation.id,
            message=f"Hủy đặt trước ô {slot_code} ({reservation.code})",
        )

    return reservation
