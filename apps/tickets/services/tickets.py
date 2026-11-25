"""
Services for tickets app.
Implements business operations for tickets: create, update (with OCC),
delete (with DEL-04 guards), and renew.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import status

from apps.core.exceptions import BusinessAPIException
from apps.customers.models import Customer
from apps.parking.models import ParkingSlot, VehicleEntryExitLog
from apps.tickets.models import Ticket, TicketRenewal, TicketType
from apps.tickets.selectors.tickets import get_ticket_by_id
from apps.vehicles.models import Vehicle


def _resolve_employee_id(actor_id: int | None) -> int | None:
    """Helper to resolve Employee.id from Account.id or directly from Employee.id."""
    if not actor_id:
        return None
    from apps.employees.models import Employee

    emp = Employee.objects.filter(account_id=actor_id, deleted_at__isnull=True).first()
    if emp:
        return emp.id
    emp_by_id = Employee.objects.filter(id=actor_id, deleted_at__isnull=True).first()
    if emp_by_id:
        return emp_by_id.id
    return None


def create_ticket(data: dict[str, Any], actor_id: int | None = None) -> Ticket:
    """
    Creates a new parking ticket.
    Validates ticket type, customer, vehicle, and finds an available parking slot.
    """
    ticket_type_id = data.get("ticket_type_id")
    ticket_type = (
        TicketType.objects.filter(id=ticket_type_id, deleted_at__isnull=True).first()
        if ticket_type_id is not None
        else None
    )
    if not ticket_type:
        raise BusinessAPIException(
            code="MSG-4.6.2-M01",
            message="Loại vé không tồn tại hoặc đã bị xóa.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    customer = None
    if data.get("customer_id"):
        customer = Customer.objects.filter(
            id=data["customer_id"], deleted_at__isnull=True
        ).first()
    elif data.get("customer_code"):
        customer = Customer.objects.filter(
            code=str(data["customer_code"]).strip(), deleted_at__isnull=True
        ).first()

    if not customer:
        raise BusinessAPIException(
            code="MSG-4.6.2-M01",
            message="Khách hàng không tồn tại.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    vehicle = None
    if data.get("vehicle_id"):
        vehicle = Vehicle.objects.filter(
            id=data["vehicle_id"], deleted_at__isnull=True
        ).first()
    elif data.get("license_plate"):
        vehicle = Vehicle.objects.filter(
            license_plate=str(data["license_plate"]).strip(), deleted_at__isnull=True
        ).first()

    if not vehicle:
        raise BusinessAPIException(
            code="MSG-4.6.2-M01",
            message="Phương tiện không tồn tại.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    slot = None
    if data.get("slot_id"):
        slot = ParkingSlot.objects.filter(
            id=data["slot_id"], deleted_at__isnull=True
        ).first()

    if slot is None:
        slot = ParkingSlot.objects.filter(
            status="AVAILABLE", deleted_at__isnull=True
        ).first()

    if slot is None:
        raise BusinessAPIException(
            code="MSG-4.6.2-M01",
            message="Không tìm thấy vị trí đỗ xe khả dụng để đăng ký vé.",
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    now = timezone.now()
    effective_from = data.get("effective_from") or now
    duration_days = ticket_type.duration_days or 30
    effective_to = data.get("effective_to") or (
        effective_from + timedelta(days=duration_days)
    )
    price = data.get("price") or ticket_type.default_price or Decimal("0")

    last_ticket = Ticket.objects.order_by("-id").first()
    next_num = (last_ticket.id + 1) if last_ticket else 1
    ticket_code = f"VT{next_num:04d}"

    employee_id = _resolve_employee_id(actor_id)

    ticket = Ticket.objects.create(
        code=ticket_code,
        ticket_type=ticket_type,
        customer=customer,
        vehicle=vehicle,
        slot=slot,
        issued_by_id=employee_id,
        price=price,
        effective_from=effective_from,
        effective_to=effective_to,
        status="ACTIVE",
        notes=data.get("notes", ""),
    )

    result = get_ticket_by_id(ticket.id)
    return result or ticket


def update_ticket(
    lookup: str | int,
    data: dict[str, Any],
    actor_id: int | None = None,
) -> Ticket:
    """
    Updates an existing ticket with Optimistic Concurrency Control (OCC)
    and business validation according to SRS 4.6.3.
    """
    lookup_str = str(lookup).strip()

    with transaction.atomic():
        qs = Ticket.objects.select_for_update().filter(deleted_at__isnull=True)
        if lookup_str.isdigit():
            ticket = qs.filter(id=int(lookup_str)).first()
        else:
            ticket = qs.filter(code__iexact=lookup_str).first()

        if not ticket:
            raise BusinessAPIException(
                code="PROP-4.6.4-P05",
                message="Vé không tồn tại hoặc đã bị xóa.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        # 1. Kiểm tra Optimistic Concurrency Control (OCC) với row_version
        incoming_row_version = data.get("row_version")
        if (
            incoming_row_version is not None
            and incoming_row_version != ticket.row_version
        ):
            raise BusinessAPIException(
                code="PROP-4.6.3-P03",
                message="Vé đang được xử lý bởi người dùng khác, vui lòng thử lại sau.",
                status_code=status.HTTP_409_CONFLICT,
            )

        # 2. Kiểm tra nghiệp vụ ngày hết hạn mới
        new_effective_to = data.get("effective_to")
        if new_effective_to is not None and new_effective_to <= ticket.effective_to:
            raise BusinessAPIException(
                code="MSG-4.6.3-M01",
                message="Lỗi dữ liệu trên Ngày Gia hạn không hợp lệ: ngày hết hạn mới phải lớn hơn ngày cũ.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # 3. Chuẩn bị các giá trị cập nhật
        old_slot = ticket.slot
        new_slot: ParkingSlot = old_slot
        if data.get("slot_id") is not None:
            found_slot = ParkingSlot.objects.filter(
                id=data["slot_id"], deleted_at__isnull=True
            ).first()
            if not found_slot:
                raise BusinessAPIException(
                    code="MSG-4.6.3-M01",
                    message="Vị trí đỗ xe chỉ định không tồn tại hoặc đã bị xóa.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            new_slot = found_slot

        old_type = ticket.ticket_type
        new_type = old_type
        if data.get("ticket_type_id"):
            found_type = TicketType.objects.filter(
                id=data["ticket_type_id"], deleted_at__isnull=True
            ).first()
            if not found_type:
                raise BusinessAPIException(
                    code="MSG-4.6.3-M01",
                    message="Loại vé chỉ định không tồn tại hoặc đã bị xóa.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            new_type = found_type

        old_price: Decimal = ticket.price or Decimal("0")
        raw_new_price = data.get("price")
        new_price: Decimal = (
            raw_new_price
            if isinstance(raw_new_price, Decimal)
            else (
                Decimal(str(raw_new_price)) if raw_new_price is not None else old_price
            )
        )
        additional_price = max(Decimal("0"), new_price - old_price)
        employee_id = _resolve_employee_id(actor_id)

        # Ghi nhận lịch sử gia hạn khi và chỉ khi new_effective_to > old_effective_to
        # để tuân thủ CHECK constraint ck_renewal_time_extension
        if new_effective_to is not None and new_effective_to > ticket.effective_to:
            TicketRenewal.objects.create(
                ticket=ticket,
                old_slot=old_slot,
                new_slot=new_slot,
                old_ticket_type=old_type,
                new_ticket_type=new_type,
                old_price=old_price,
                new_price=new_price,
                old_effective_to=ticket.effective_to,
                new_effective_to=new_effective_to,
                additional_price=additional_price,
                notes=data.get("notes") or "Cập nhật vé (PATCH)",
                renewed_by_id=employee_id,
            )

        # 4. Lưu thay đổi vào Ticket
        if new_effective_to is not None:
            ticket.effective_to = new_effective_to
        if data.get("slot_id") is not None:
            ticket.slot = new_slot
        if "ticket_type_id" in data and new_type:
            ticket.ticket_type = new_type
        if "price" in data and data["price"] is not None:
            ticket.price = data["price"]
        if "notes" in data:
            ticket.notes = data["notes"]
        if "status" in data and data["status"]:
            ticket.status = data["status"]
        elif new_effective_to and new_effective_to > timezone.now():
            ticket.status = "ACTIVE"

        ticket.save()

    result = get_ticket_by_id(ticket.id)
    return result or ticket


def delete_ticket(
    lookup: str | int,
    actor_id: int | None = None,
) -> dict[str, str]:
    """
    Soft-delete a ticket with DEL-04 guards (SRS 4.6.4).
    Only expired, non-renewed tickets with no open parking sessions are deletable.
    DO NOT change ticket.status to 'TERMINATED' because PostgreSQL constraint
    ck_ticket_status_enum only accepts ('ACTIVE', 'EXPIRED', 'CANCELLED', 'RENEWING').
    """
    lookup_str = str(lookup).strip()

    with transaction.atomic():
        qs = Ticket.objects.select_for_update().filter(deleted_at__isnull=True)
        if lookup_str.isdigit():
            ticket = qs.filter(id=int(lookup_str)).first()
        else:
            ticket = qs.filter(code__iexact=lookup_str).first()

        if not ticket:
            raise BusinessAPIException(
                code="PROP-4.6.4-P05",
                message="Vé không tồn tại hoặc đã bị xóa.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        now = timezone.now()

        # Rào chắn 1: Active Unexpired Guard (PROP-4.6.4-P01)
        if ticket.effective_to > now and ticket.status in ("ACTIVE", "RENEWING"):
            raise BusinessAPIException(
                code="PROP-4.6.4-P01",
                message="Vé chưa hết hạn, không được phép xóa.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Rào chắn 2: Renewed Ticket Guard (PROP-4.6.4-P02)
        has_renewals = TicketRenewal.objects.filter(ticket_id=ticket.id).exists()
        if has_renewals or ticket.status == "RENEWED":
            raise BusinessAPIException(
                code="PROP-4.6.4-P02",
                message="Vé đã được gia hạn, không được phép xóa.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Rào chắn 3: Parked Vehicle Guard (PROP-DEL-04-OPEN-SES)
        is_parked = VehicleEntryExitLog.objects.filter(
            Q(vehicle_id=ticket.vehicle_id) | Q(ticket_id=ticket.id),
            exit_time__isnull=True,
        ).exists()
        if is_parked:
            raise BusinessAPIException(
                code="PROP-DEL-04-OPEN-SES",
                message="Phương tiện liên kết với vé đang đỗ trong bãi xe, không được phép xóa vé.",
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        # Soft delete: Chỉ cập nhật deleted_at, deleted_by.
        # TUYỆT ĐỐI KHÔNG set ticket.status = 'TERMINATED'.
        try:
            ticket.deleted_at = now
            ticket.deleted_by_id = actor_id
            ticket.save(update_fields=["deleted_at", "deleted_by_id"])
        except (IntegrityError, DatabaseError) as exc:
            err_str = str(exc)
            if "Vé chưa hết hạn" in err_str or "PROP-4.6.4-P01" in err_str:
                raise BusinessAPIException(
                    code="PROP-4.6.4-P01",
                    message="Vé chưa hết hạn, không được phép xóa.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                ) from exc
            if "Vé đã được gia hạn" in err_str or "PROP-4.6.4-P02" in err_str:
                raise BusinessAPIException(
                    code="PROP-4.6.4-P02",
                    message="Vé đã được gia hạn, không được phép xóa.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                ) from exc
            if (
                "Phương tiện liên kết với vé đang đỗ" in err_str
                or "PROP-DEL-04-OPEN-SES" in err_str
            ):
                raise BusinessAPIException(
                    code="PROP-DEL-04-OPEN-SES",
                    message="Phương tiện liên kết với vé đang đỗ trong bãi xe, không được phép xóa vé.",
                    status_code=status.HTTP_400_BAD_REQUEST,
                ) from exc
            raise

    return {
        "code": "MSG-4.6.4-M01",
        "message": "Xóa thành công",
    }


def renew_ticket(
    lookup: str | int,
    data: dict[str, Any],
    actor_id: int | None = None,
) -> Ticket:
    """
    Extends ticket validity period, records renewal in TicketRenewal.
    """
    lookup_str = str(lookup).strip()

    with transaction.atomic():
        qs = Ticket.objects.select_for_update().filter(deleted_at__isnull=True)
        if lookup_str.isdigit():
            ticket = qs.filter(id=int(lookup_str)).first()
        else:
            ticket = qs.filter(code__iexact=lookup_str).first()

        if not ticket:
            raise BusinessAPIException(
                code="PROP-4.6.4-P05",
                message="Không tìm thấy vé đỗ xe để gia hạn.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        old_effective_to = ticket.effective_to
        extend_days = data.get("extend_days", 30)
        new_effective_to = max(old_effective_to, timezone.now()) + timedelta(
            days=extend_days
        )

        old_type = ticket.ticket_type
        new_type = old_type
        if data.get("ticket_type_id"):
            found_type = TicketType.objects.filter(
                id=data["ticket_type_id"], deleted_at__isnull=True
            ).first()
            if found_type:
                new_type = found_type

        old_slot = ticket.slot
        new_slot = old_slot
        if data.get("new_slot_id"):
            found_slot = ParkingSlot.objects.filter(
                id=data["new_slot_id"], deleted_at__isnull=True
            ).first()
            if found_slot:
                new_slot = found_slot

        add_price = data.get("additional_price", Decimal("0"))
        employee_id = _resolve_employee_id(actor_id)

        TicketRenewal.objects.create(
            ticket=ticket,
            old_slot=old_slot,
            new_slot=new_slot,
            old_ticket_type=old_type,
            new_ticket_type=new_type,
            old_price=ticket.price,
            new_price=ticket.price + add_price,
            old_effective_to=old_effective_to,
            new_effective_to=new_effective_to,
            additional_price=add_price,
            notes=data.get("notes", ""),
            renewed_by_id=employee_id,
        )

        ticket.effective_to = new_effective_to
        ticket.ticket_type = new_type
        ticket.slot = new_slot
        ticket.status = "ACTIVE"
        ticket.save()

    result = get_ticket_by_id(ticket.id)
    return result or ticket
