"""
Vehicle search selectors for parking app.
Provides multi-criteria search with Trigram GIN index activation (TL-41),
deterministic ordering, soft-delete filtering, PII anonymization,
and zero N+1 batch hydration per SRS 4.5.1 and Task 9.
"""

import re
from collections.abc import Sequence
from typing import Any

from django.db.models import Case, Field, IntegerField, Lookup, Q, QuerySet, Value, When
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.parking.models import PlateBlacklist, VehicleEntryExitLog
from apps.parking.services.ocr import PlateRecognizer
from apps.tickets.models import Ticket
from apps.vehicles.models import Vehicle


class DirectILike(Lookup):
    """
    Toán tử ILIKE trực tiếp trong PostgreSQL (col ILIKE pattern).
    Không bọc hàm UPPER() như __icontains mặc định của Django ORM,
    đáp ứng 100% điều kiện kích hoạt Trigram GIN index (TL-41).
    """

    lookup_name = "ilike"

    def as_sql(self, compiler: Any, connection: Any) -> tuple[str, tuple[Any, ...]]:
        lhs, lhs_params = self.process_lhs(compiler, connection)
        rhs, rhs_params = self.process_rhs(compiler, connection)
        params = tuple(lhs_params) + tuple(rhs_params)
        return f"{lhs} ILIKE {rhs}", params


# Đăng ký custom lookup toàn cục trên django.db.models.Field
Field.register_lookup(DirectILike)


def escape_like(text: str) -> str:
    r"""
    Escape các ký tự đặc biệt của cú pháp LIKE / ILIKE trong PostgreSQL.
    Thứ tự: escape dấu gạch chéo ngược (\) trước, sau đó là % và _.
    """
    if not text:
        return ""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def normalize_phone_query(phone: str) -> str:
    """
    Chuẩn hóa số điện thoại phục vụ tìm kiếm:
    - Loại bỏ ký tự phân cách, dấu chấm, khoảng trắng, chỉ giữ lại số và dấu cộng.
    - Chuyển đổi tiền tố quốc tế +84 hoặc 84 về đầu số 0.
    """
    if not phone:
        return ""
    cleaned = re.sub(r"[^\d+]", "", phone)
    if cleaned.startswith("+84"):
        cleaned = "0" + cleaned[3:]
    elif cleaned.startswith("84") and len(cleaned) >= 11:
        cleaned = "0" + cleaned[2:]
    return cleaned


def search_vehicles_query(params: dict[str, Any]) -> QuerySet[Vehicle]:
    """
    Xây dựng QuerySet tìm kiếm phương tiện đa tiêu chí:
    - Kiểm tra tính hợp lệ tham số: cắt khoảng trắng hai đầu (strip),
      nếu rỗng hoặc độ dài < 2 ký tự -> ném ValidationError.
    - Bắt buộc lọc bỏ các bản ghi đã xóa mềm (deleted_at IS NULL).
    - Hỗ trợ tìm kiếm hợp nhất q (OR) và 3 tham số tường minh (AND).
    - Sắp xếp xác định: ưu tiên xe khớp chính xác biển số lên đầu, sau đó theo biển số tăng dần.
    """
    search_keys = ["q", "customer_name", "phone", "license_plate"]
    has_valid_param = False
    stripped_params: dict[str, str] = {}

    for key in search_keys:
        val = params.get(key)
        if val is not None:
            cleaned = str(val).strip()
            if cleaned:
                if len(cleaned) < 2:
                    raise ValidationError(
                        {key: "Từ khóa tìm kiếm phải có độ dài tối thiểu 2 ký tự."}
                    )
                stripped_params[key] = cleaned
                has_valid_param = True

    if not has_valid_param:
        raise ValidationError(
            {
                "non_field_errors": [
                    "Yêu cầu cung cấp ít nhất một tiêu chí tìm kiếm hợp lệ (q, customer_name, phone, license_plate)."
                ]
            }
        )

    qs = Vehicle.objects.filter(
        deleted_at__isnull=True,
        customer__deleted_at__isnull=True,
    ).select_related("vehicle_type", "customer")

    # 1. Xử lý tìm kiếm hợp nhất q qua UNION subquery trên các cột có Trigram GIN index (F9)
    if "q" in stripped_params:
        q_raw = stripped_params["q"]
        escaped_q = escape_like(q_raw)
        norm_q_plate = PlateRecognizer.normalize_plate(q_raw)
        norm_q_phone = normalize_phone_query(q_raw)

        subqueries = []

        # Nhánh 1: Biển số xe chuẩn hóa (idx_vehicle_plate_trgm)
        if len(norm_q_plate) >= 2:
            subqueries.append(
                Vehicle.objects.filter(
                    deleted_at__isnull=True,
                    license_plate_norm__ilike=f"%{escape_like(norm_q_plate)}%",
                ).values("id")
            )

        # Nhánh 2: Họ tên khách hàng (idx_customer_full_name_trgm)
        if len(escaped_q) >= 2:
            subqueries.append(
                Vehicle.objects.filter(
                    deleted_at__isnull=True,
                    customer__deleted_at__isnull=True,
                    customer__full_name__ilike=f"%{escaped_q}%",
                ).values("id")
            )

        # Nhánh 3: Số điện thoại khách hàng (idx_customer_phone_trgm)
        if len(norm_q_phone) >= 2:
            subqueries.append(
                Vehicle.objects.filter(
                    deleted_at__isnull=True,
                    customer__deleted_at__isnull=True,
                    customer__phone__ilike=f"%{escape_like(norm_q_phone)}%",
                ).values("id")
            )

        if not subqueries:
            return Vehicle.objects.none()

        matching_ids = (
            subqueries[0]
            if len(subqueries) == 1
            else subqueries[0].union(*subqueries[1:])
        )
        qs = qs.filter(id__in=matching_ids)

    # 2. Xử lý các tham số tường minh (explicit parameters)
    explicit_filter = Q()
    has_explicit = False

    if "customer_name" in stripped_params:
        escaped_name = escape_like(stripped_params["customer_name"])
        explicit_filter &= Q(customer__full_name__ilike=f"%{escaped_name}%")
        has_explicit = True

    if "phone" in stripped_params:
        raw_phone = stripped_params["phone"]
        norm_phone = normalize_phone_query(raw_phone)
        phone_term = norm_phone if len(norm_phone) >= 2 else raw_phone
        explicit_filter &= Q(customer__phone__ilike=f"%{escape_like(phone_term)}%")
        has_explicit = True

    if "license_plate" in stripped_params:
        raw_plate = stripped_params["license_plate"]
        norm_plate = PlateRecognizer.normalize_plate(raw_plate)
        search_plate = norm_plate if len(norm_plate) >= 2 else raw_plate
        explicit_filter &= Q(license_plate_norm__ilike=f"%{escape_like(search_plate)}%")
        has_explicit = True

    if has_explicit:
        qs = qs.filter(explicit_filter)

    target_plate_norm = ""
    if "license_plate" in stripped_params:
        target_plate_norm = PlateRecognizer.normalize_plate(
            stripped_params["license_plate"]
        )
    elif "q" in stripped_params:
        cand_norm = PlateRecognizer.normalize_plate(stripped_params["q"])
        if len(cand_norm) >= 2:
            target_plate_norm = cand_norm

    if target_plate_norm:
        qs = qs.annotate(
            exact_match=Case(
                When(license_plate_norm=target_plate_norm, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        ).order_by("exact_match", "license_plate")
    else:
        qs = qs.order_by("license_plate")

    return qs


def hydrate_vehicle_search_results(
    vehicles: Sequence[Vehicle],
) -> list[dict[str, Any]]:
    """
    Nạp dữ liệu mở rộng cho danh sách phương tiện (Batch Hydration In-Memory):
    - Đảm bảo Zero N+1: cố định 3 queries bổ trợ cho toàn bộ trang (tối đa 50 xe).
    - Query 1: Các phiên đỗ đang mở (exit_time IS NULL) kèm vị trí đỗ và cổng vào.
    - Query 2: Các vé đỗ xe đang có hiệu lực (status=ACTIVE, còn hạn) kèm vị trí đỗ và loại vé.
    - Query 3: Cảnh báo danh sách đen (PlateBlacklist).
    - Ghép nối dữ liệu: vị trí đỗ (ưu tiên phiên mở, sau đó vé active),
      ẩn danh hóa PII nếu customer.is_anonymized=True, và gán cờ currently_parked.
    """
    if not vehicles:
        return []

    vehicle_ids = [v.id for v in vehicles]
    norm_plates = [v.license_plate_norm for v in vehicles if v.license_plate_norm]

    # Query 1: Open sessions
    open_sessions = (
        VehicleEntryExitLog.objects.filter(
            license_plate_norm__in=norm_plates,
            exit_time__isnull=True,
        )
        .select_related("slot__zone__floor", "entry_gate")
        .order_by("-id")
    )
    open_session_map: dict[str, VehicleEntryExitLog] = {}
    for session in open_sessions:
        if session.license_plate_norm not in open_session_map:
            open_session_map[session.license_plate_norm] = session

    # Query 2: Active tickets
    now = timezone.now()
    active_tickets = (
        Ticket.objects.filter(
            vehicle_id__in=vehicle_ids,
            status="ACTIVE",
            deleted_at__isnull=True,
            effective_from__lte=now,
            effective_to__gt=now,
        )
        .select_related("ticket_type", "slot__zone__floor")
        .order_by("-id")
    )
    ticket_map: dict[int, Ticket] = {}
    for ticket in active_tickets:
        if ticket.vehicle_id not in ticket_map:
            ticket_map[ticket.vehicle_id] = ticket

    # Query 3: Blacklist
    blacklisted_set = set(
        PlateBlacklist.objects.filter(
            license_plate_norm__in=norm_plates,
            is_active=True,
            deleted_at__isnull=True,
        ).values_list("license_plate_norm", flat=True)
    )

    results: list[dict[str, Any]] = []
    for vehicle in vehicles:
        try:
            customer = vehicle.customer
        except Exception:
            customer = None

        if customer and customer.is_anonymized:
            customer_info: dict[str, Any] = {
                "id": customer.id,
                "code": customer.code,
                "full_name": "Khách hàng ẩn danh",
                "phone": None,
                "is_anonymized": True,
            }
        elif customer:
            customer_info = {
                "id": customer.id,
                "code": customer.code,
                "full_name": customer.full_name,
                "phone": customer.phone,
                "is_anonymized": False,
            }
        else:
            customer_info = {
                "id": 0,
                "code": "",
                "full_name": "",
                "phone": None,
                "is_anonymized": False,
            }

        open_session = open_session_map.get(vehicle.license_plate_norm)
        open_session_info = None
        if open_session:
            open_session_info = {
                "id": open_session.id,
                "session_code": open_session.session_code,
                "entry_time": open_session.entry_time.isoformat(),
                "entry_gate_name": open_session.entry_gate.name
                if open_session.entry_gate
                else None,
                "entry_image_url": open_session.entry_image_url,
                "recognition_source": open_session.recognition_source,
                "ai_confidence": float(open_session.ai_confidence)
                if open_session.ai_confidence is not None
                else None,
                "review_status": open_session.review_status,
            }

        active_ticket = ticket_map.get(vehicle.id)
        active_ticket_info = None
        if active_ticket:
            active_ticket_info = {
                "id": active_ticket.id,
                "code": active_ticket.code,
                "ticket_type_name": active_ticket.ticket_type.name
                if active_ticket.ticket_type
                else "",
                "price": str(active_ticket.price),
                "effective_from": active_ticket.effective_from.isoformat(),
                "effective_to": active_ticket.effective_to.isoformat(),
                "status": active_ticket.status,
            }

        target_slot = None
        if open_session and open_session.slot:
            target_slot = open_session.slot
        elif active_ticket and active_ticket.slot:
            target_slot = active_ticket.slot

        parking_position = None
        if target_slot:
            floor = target_slot.zone.floor
            zone = target_slot.zone
            parking_position = {
                "slot_id": target_slot.id,
                "slot_code": target_slot.code,
                "zone_code": zone.code,
                "floor_code": floor.code,
                "floor_name": floor.name,
                "display_text": f"{floor.name} - Zone {zone.code} - {target_slot.code}",
            }

        is_blacklisted = vehicle.license_plate_norm in blacklisted_set
        currently_parked = open_session is not None

        vtype = vehicle.vehicle_type
        results.append(
            {
                "vehicle": {
                    "id": vehicle.id,
                    "code": vehicle.code,
                    "license_plate": vehicle.license_plate,
                    "license_plate_norm": vehicle.license_plate_norm,
                    "model_name": vehicle.model_name,
                    "brand": vehicle.brand,
                    "color": vehicle.color,
                    "vehicle_type": vtype.name if vtype else "",
                    "vehicle_type_code": vtype.code if vtype else "",
                },
                "customer": customer_info,
                "parking_position": parking_position,
                "active_ticket": active_ticket_info,
                "open_session": open_session_info,
                "is_blacklisted": is_blacklisted,
                "currently_parked": currently_parked,
            }
        )

    return results
