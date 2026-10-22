"""
Check-in service for parking app per TL-05, TL-17, TL-50, and SRS 4.5.1.
Handles vehicle entry, visitor entry, blacklist checking, slot assignment,
trigger TL-17 auto-linking, and session code generation.
"""

import re
import time
from decimal import Decimal
from typing import Any

from django.db import DatabaseError, IntegrityError, connection, transaction
from django.utils import timezone

from apps.audit.models import SystemAlert
from apps.core.exceptions import (
    BusinessAPIException,
    map_database_exception_to_business_error,
)
from apps.core.messages import ALL_MESSAGES
from apps.employees.models import Employee
from apps.parking.models import (
    ParkingGate,
    ParkingSlot,
    PlateBlacklist,
    VehicleEntryExitLog,
)
from apps.parking.selectors.vehicles import get_combined_vehicle_context
from apps.parking.services.ocr import PlateRecognizer
from apps.parking.services.session_code import generate_session_code
from apps.parking.services.upload import validate_parking_image_path

PLATE_REGEX = re.compile(r"^[A-Za-z0-9 .\-]+$")


def check_in_vehicle(
    license_plate: str,
    entry_gate_id: int | None = None,
    slot_id: int | None = None,
    recognition_source: str = "AI",
    ai_confidence: float | Decimal | None = None,
    entry_image_url: str | None = None,
    override_blacklist: bool = False,
    user: Any = None,
    notes: str | None = None,
) -> tuple[VehicleEntryExitLog, dict[str, Any] | None]:
    """
    Thực hiện check-in phương tiện vào bãi đỗ:
    1. Kiểm tra tính hợp lệ của biển số xe (PROP-4.5.1-P01).
    2. Chuẩn hóa biển số (lưu biển thô vào license_plate, không ghi license_plate_norm).
    3. Kiểm tra danh sách đen (PlateBlacklist):
       - Tạo dòng cảnh báo trong system_alert với alert_type='BLACKLIST_PLATE'.
       - Nếu không phải MANAGER hoặc không gửi override_blacklist -> từ chối HTTP 409 (PROP-4.5.1-P08).
    4. Xác thực cổng vào (hướng IN).
    5. Tự động xác định slot_id và ticket_id nếu xe đã đăng ký vé active.
    6. Xác định recognition_source, ai_confidence, và review_status:
       - MANUAL -> review_status='AUTO', ai_confidence=None
       - AI -> ai_confidence >= 85.00 thì 'AUTO', ngược lại 'NEEDS_REVIEW'
    7. Sinh mã phiên an toàn race-condition #PK-YYYYMMDD-NNN.
    8. Gán nhân viên trực cổng entry_handled_by từ user đăng nhập.
    9. Chèn bản ghi trong transaction atomic, để trigger TL-17 tự động link vehicle_id.
    """
    # 0. Xác thực đường dẫn hình ảnh (Defense-in-depth per F3)
    entry_image_url = validate_parking_image_path(entry_image_url)

    # 1. Kiểm tra biển số đầu vào
    if not license_plate or not license_plate.strip():
        raise BusinessAPIException(
            code="PROP-4.5.1-P01",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P01", "Định dạng biển số xe không hợp lệ."
            ),
            status_code=400,
        )

    clean_plate = license_plate.strip()
    if not PLATE_REGEX.match(clean_plate):
        raise BusinessAPIException(
            code="PROP-4.5.1-P01",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P01", "Định dạng biển số xe không hợp lệ."
            ),
            status_code=400,
        )

    norm_plate = PlateRecognizer.normalize_plate(clean_plate)
    now = timezone.now()

    # Nạp toàn bộ context phương tiện, vé và blacklist (P4 Combined Selector, bỏ qua open_session)
    context = get_combined_vehicle_context(clean_plate, include_open_session=False)

    # 2. Kiểm tra danh sách đen (Blacklist)
    if context.is_blacklisted:
        blacklist_item = PlateBlacklist.objects.filter(
            license_plate_norm=norm_plate, is_active=True, deleted_at__isnull=True
        ).first()
        if blacklist_item:
            SystemAlert.objects.create(
                alert_type="BLACKLIST_PLATE",
                severity="WARNING",
                message=f"Phát hiện phương tiện biển số {clean_plate} thuộc danh sách đen tại cổng kiểm soát.",
                entity_type="PLATE_BLACKLIST",
                entity_id=blacklist_item.id,
                occurred_at=now,
            )

        user_role = getattr(user, "role", None) if user else None
        is_manager = user_role == "MANAGER"

        if override_blacklist and not is_manager:
            raise BusinessAPIException(
                code="PROP-4.5.1-P14",
                message=ALL_MESSAGES.get(
                    "PROP-4.5.1-P14",
                    "Nhân viên không có quyền ghi đè danh sách đen.",
                ),
                status_code=403,
            )

        if not (is_manager and override_blacklist):
            raise BusinessAPIException(
                code="PROP-4.5.1-P08",
                message=ALL_MESSAGES.get(
                    "PROP-4.5.1-P08",
                    "Biển số xe nằm trong danh sách đen, không được phép vào bãi.",
                ),
                status_code=409,
            )

    # 3. Xác thực cổng vào
    entry_gate = None
    if entry_gate_id:
        entry_gate = ParkingGate.objects.filter(
            id=entry_gate_id, deleted_at__isnull=True
        ).first()
        if not entry_gate or not entry_gate.is_active:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Cổng vào không tồn tại hoặc đã bị vô hiệu hóa.",
                status_code=400,
            )
        if entry_gate.direction != "IN":
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Cổng được chọn không phải là cổng vào (direction != 'IN').",
                status_code=400,
            )

    # 4. Tái sử dụng đối tượng phương tiện và vé đã nạp từ context
    registered_vehicle = context.vehicle
    active_ticket = context.active_ticket

    resolved_ticket_id = None
    resolved_slot_id = slot_id

    if active_ticket:
        resolved_ticket_id = active_ticket.id
        if resolved_slot_id is None and active_ticket.slot_id:
            resolved_slot_id = active_ticket.slot_id

    slot_obj = None
    # Xác thực slot_id nếu có
    if resolved_slot_id:
        if (
            active_ticket
            and active_ticket.slot
            and active_ticket.slot.id == resolved_slot_id
        ):
            slot_obj = active_ticket.slot
        else:
            slot_obj = (
                ParkingSlot.objects.filter(id=resolved_slot_id, deleted_at__isnull=True)
                .select_related("zone__floor")
                .first()
            )
        if not slot_obj:
            raise BusinessAPIException(
                code="PROP-GEN-P01",
                message="Vị trí đỗ xe chỉ định không tồn tại hoặc đã bị vô hiệu hóa.",
                status_code=400,
            )

    # 5. Xử lý recognition_source, confidence, và review_status
    source_val = "MANUAL" if str(recognition_source).upper() == "MANUAL" else "AI"
    conf_decimal: Decimal | None = None

    if source_val == "MANUAL":
        review_status = "AUTO"
        conf_decimal = None
    else:
        if ai_confidence is not None:
            try:
                conf_decimal = Decimal(str(ai_confidence)).quantize(Decimal("0.01"))
            except Exception as exc:
                raise BusinessAPIException(
                    code="PROP-GEN-P01",
                    message="Độ tin cậy AI không đúng định dạng số hợp lệ.",
                    status_code=400,
                ) from exc
            if conf_decimal < Decimal("0.00") or conf_decimal > Decimal("100.00"):
                raise BusinessAPIException(
                    code="PROP-GEN-P01",
                    message="Độ tin cậy AI phải nằm trong khoảng từ 0.00 đến 100.00.",
                    status_code=400,
                )

        if conf_decimal is not None and conf_decimal >= Decimal("85.00"):
            review_status = "AUTO"
        else:
            review_status = "NEEDS_REVIEW"

    # 6. Xác định nhân viên xử lý check-in
    handled_by_employee = None
    if user and getattr(user, "is_authenticated", False):
        handled_by_employee = Employee.objects.filter(
            account=user, deleted_at__isnull=True
        ).first()

    # 7. Sinh mã phiên đỗ xe và thực hiện chèn bản ghi trong atomic transaction (có advisory lock theo ngày per F2)
    max_retries = 5
    session = None
    for attempt in range(max_retries):
        try:
            with transaction.atomic():
                session_code = None
                if connection.vendor == "postgresql":
                    with connection.cursor() as cursor:
                        # Transaction-scoped advisory lock theo ngày (0x504B = 20555 ('PK') và YYYYMMDD)
                        date_int = int(now.strftime("%Y%m%d"))
                        cursor.execute(
                            "SELECT pg_advisory_xact_lock(%s, %s);",
                            (20555, date_int),
                        )
                        session_code = generate_session_code(
                            offset=attempt, cursor=cursor
                        )
                else:
                    session_code = generate_session_code(offset=attempt)

                # Chú ý: Không gán license_plate_norm vì là generated column
                # Để trigger TL-17 tự động gán vehicle_id nếu vehicle_id là None
                session = VehicleEntryExitLog.objects.create(
                    session_code=session_code,
                    vehicle=registered_vehicle,
                    slot_id=resolved_slot_id,
                    ticket_id=resolved_ticket_id,
                    entry_gate=entry_gate,
                    license_plate=clean_plate,
                    ai_confidence=conf_decimal,
                    recognition_source=source_val,
                    review_status=review_status,
                    fee_amount=Decimal("0.00"),
                    entry_time=now,
                    entry_image_url=entry_image_url,
                    entry_handled_by=handled_by_employee,
                    notes=notes,
                )
            break
        except (IntegrityError, DatabaseError) as exc:
            cause_str = str(getattr(exc, "__cause__", None) or exc)
            # Nếu va chạm unique constraint của session_code, retry tối đa max_retries lần
            if (
                "uq_log_session_code" in cause_str or "session_code" in cause_str
            ) and attempt < max_retries - 1:
                time.sleep(0.02 * (attempt + 1))
                continue

            # Fail-fast on deterministic DB business trigger/constraint violations (Standard 4 DRY).
            # Retrying is futile for business rule conflicts (e.g., maintenance slot, active open session).
            mapped_exc = map_database_exception_to_business_error(exc)
            if mapped_exc:
                raise mapped_exc from exc

            # Bubble unmapped infrastructure errors to custom_exception_handler
            raise exc

    if session is None:
        raise BusinessAPIException(
            code="PROP-4.5.1-P07",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P07",
                "Biển số xe đã có phiên đỗ xe đang mở chưa hoàn thành.",
            ),
            status_code=409,
        )

    # Gán đầy đủ quan hệ cho session tránh N+1 khi serialize qua SessionDetailSerializer
    session.entry_gate = entry_gate
    session.entry_handled_by = handled_by_employee
    session.slot = slot_obj
    session.vehicle = registered_vehicle
    session.ticket = active_ticket
    session.exit_gate = None
    session.exit_handled_by = None

    # Cập nhật context phiên mở để trả về dữ liệu tra cứu không tốn thêm truy vấn
    context.open_session = session
    vehicle_lookup_data = context.to_lookup_dict()

    return session, vehicle_lookup_data
