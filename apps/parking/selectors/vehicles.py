"""
Vehicle lookup selectors for parking app.
Provides exact normalized-plate lookup per TL-17, TL-50, and SRS 4.5.1.
"""

from typing import Any

from django.db.models import Exists, Prefetch
from django.utils import timezone

from apps.customers.models import Customer
from apps.parking.models import PlateBlacklist, VehicleEntryExitLog
from apps.parking.services.ocr import PlateRecognizer
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle


class CombinedVehicleContext:
    """
    Data transfer and representation context for combined vehicle lookup (Round 34 P4).
    Contains vehicle, customer, active ticket, open session, and blacklist status
    fetched with minimum database round-trips.
    """

    def __init__(
        self,
        plate_normalized: str,
        vehicle: Vehicle | None = None,
        customer: Customer | None = None,
        open_session: VehicleEntryExitLog | None = None,
        active_ticket: Ticket | None = None,
        is_blacklisted: bool = False,
    ) -> None:
        self.plate_normalized = plate_normalized
        self.vehicle = vehicle
        self.customer = customer
        self.open_session = open_session
        self.active_ticket = active_ticket
        self.is_blacklisted = is_blacklisted

    @property
    def open_session_data(self) -> dict[str, Any] | None:
        """Trả về dictionary định dạng phiên đỗ mở cho response serializer."""
        if not self.open_session:
            return None
        return {
            "id": self.open_session.id,
            "session_code": self.open_session.session_code,
            "entry_time": self.open_session.entry_time.isoformat(),
            "entry_gate_name": (
                self.open_session.entry_gate.name
                if self.open_session.entry_gate
                else None
            ),
            "entry_image_url": self.open_session.entry_image_url,
            "recognition_source": self.open_session.recognition_source,
            "ai_confidence": (
                float(self.open_session.ai_confidence)
                if self.open_session.ai_confidence is not None
                else None
            ),
            "review_status": self.open_session.review_status,
        }

    def to_lookup_dict(self) -> dict[str, Any] | None:
        """
        Chuyển đổi thành dictionary chuẩn cho VehicleLookupResponseSerializer.
        Trả về None nếu phương tiện không được đăng ký trong hệ thống.
        """
        if not self.vehicle:
            return None

        customer = self.customer or self.vehicle.customer
        if customer.is_anonymized:
            customer_info = {
                "id": customer.id,
                "code": customer.code,
                "full_name": "Khách hàng ẩn danh",
                "phone": None,
                "is_anonymized": True,
            }
        else:
            customer_info = {
                "id": customer.id,
                "code": customer.code,
                "full_name": customer.full_name,
                "phone": customer.phone,
                "is_anonymized": False,
            }

        active_ticket_info = None
        if self.active_ticket:
            active_ticket_info = {
                "id": self.active_ticket.id,
                "code": self.active_ticket.code,
                "ticket_type_name": (
                    self.active_ticket.ticket_type.name
                    if self.active_ticket.ticket_type
                    else ""
                ),
                "price": str(self.active_ticket.price),
                "effective_from": self.active_ticket.effective_from.isoformat(),
                "effective_to": self.active_ticket.effective_to.isoformat(),
                "status": self.active_ticket.status,
            }

        target_slot = None
        if self.open_session and self.open_session.slot:
            target_slot = self.open_session.slot
        elif self.active_ticket and self.active_ticket.slot:
            target_slot = self.active_ticket.slot

        parking_position = None
        if target_slot:
            floor = target_slot.zone.floor
            zone = target_slot.zone
            display_str = f"{floor.name} - Zone {zone.code} - {target_slot.code}"
            parking_position = {
                "slot_id": target_slot.id,
                "slot_code": target_slot.code,
                "zone_code": zone.code,
                "floor_code": floor.code,
                "floor_name": floor.name,
                "display_text": display_str,
            }

        vtype = self.vehicle.vehicle_type
        return {
            "vehicle": {
                "id": self.vehicle.id,
                "code": self.vehicle.code,
                "license_plate": self.vehicle.license_plate,
                "license_plate_norm": self.vehicle.license_plate_norm,
                "model_name": self.vehicle.model_name,
                "brand": self.vehicle.brand,
                "color": self.vehicle.color,
                "vehicle_type": vtype.name if vtype else "",
                "vehicle_type_code": vtype.code if vtype else "",
            },
            "customer": customer_info,
            "parking_position": parking_position,
            "active_ticket": active_ticket_info,
            "open_session": self.open_session_data,
            "is_blacklisted": self.is_blacklisted,
        }


def get_combined_vehicle_context(
    plate: str, include_open_session: bool = True
) -> CombinedVehicleContext:
    """
    Combined vehicle lookup selector (Round 34 P4):
    Nạp toàn bộ context: vehicle + customer + position + ticket + open session + blacklist flag
    với số lượng truy vấn tối thiểu:
    - Query 1: Vehicle kèm customer, vehicle_type và cờ Exists(PlateBlacklist).
    - Query 2: Prefetch active Ticket kèm ticket_type và slot__zone__floor.
    - Query 3 (nếu include_open_session=True): Open session kèm slot__zone__floor và entry_gate.
    (Nếu xe vãng lai chưa đăng ký: Query 1 trả về None, Query 2 là open session, Query 3 là blacklist Exists).
    """
    if not plate or not plate.strip():
        return CombinedVehicleContext(plate_normalized="", is_blacklisted=False)

    norm_plate = PlateRecognizer.normalize_plate(plate.strip())
    now = timezone.now()

    # 1. Truy vấn phương tiện kèm quan hệ và annotate cờ blacklist
    vehicle = (
        Vehicle.objects.filter(license_plate_norm=norm_plate, deleted_at__isnull=True)
        .select_related("vehicle_type", "customer")
        .annotate(
            is_blacklisted_flag=Exists(
                PlateBlacklist.objects.filter(
                    license_plate_norm=norm_plate,
                    is_active=True,
                    deleted_at__isnull=True,
                )
            )
        )
        .prefetch_related(
            Prefetch(
                "tickets",
                queryset=Ticket.objects.filter(
                    status="ACTIVE",
                    deleted_at__isnull=True,
                    effective_from__lte=now,
                    effective_to__gt=now,
                ).select_related("ticket_type", "slot__zone__floor"),
                to_attr="prefetched_active_tickets",
            )
        )
        .first()
    )

    # 2. Truy vấn phiên đỗ đang mở (nếu include_open_session=True)
    open_session = None
    if include_open_session:
        open_session = (
            VehicleEntryExitLog.objects.filter(
                license_plate_norm=norm_plate, exit_time__isnull=True
            )
            .select_related("slot__zone__floor", "entry_gate")
            .first()
        )

    if vehicle:
        is_blacklisted = bool(getattr(vehicle, "is_blacklisted_flag", False))
        active_tickets = getattr(vehicle, "prefetched_active_tickets", [])
        active_ticket = active_tickets[0] if active_tickets else None
        customer = vehicle.customer
    else:
        # Nếu xe chưa đăng ký, kiểm tra cờ blacklist độc lập
        is_blacklisted = PlateBlacklist.objects.filter(
            license_plate_norm=norm_plate,
            is_active=True,
            deleted_at__isnull=True,
        ).exists()
        active_ticket = None
        customer = None

    return CombinedVehicleContext(
        plate_normalized=norm_plate,
        vehicle=vehicle,
        customer=customer,
        open_session=open_session,
        active_ticket=active_ticket,
        is_blacklisted=is_blacklisted,
    )


def lookup_vehicle_by_plate(plate: str) -> dict[str, Any] | None:
    """
    Tra cứu thông tin phương tiện chính xác theo biển số đã chuẩn hóa.
    Tái sử dụng get_combined_vehicle_context để bảo toàn tính tương thích ngược.
    """
    return get_combined_vehicle_context(plate).to_lookup_dict()
