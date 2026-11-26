"""
Services for ParkingSlot domain per TL-25, TL-27, TL-39, and SRS 4.8.1 - 4.8.5.
Handles atomic transactions, OCC row_version locks, and PostgreSQL trigger guards.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import get_prop_message
from apps.parking.models import (
    ParkingSlot,
    SlotAllowedVehicleType,
    SlotReservation,
    VehicleEntryExitLog,
)
from apps.tickets.models import Ticket
from apps.vehicles.models import VehicleType

logger = logging.getLogger(__name__)


def _translate_slot_db_error(exc: Exception, operation: str = "update") -> None:
    """
    Chuyển đổi các ngoại lệ trigger và ràng buộc CSDL của PostgreSQL thành BusinessAPIException chuẩn HTTP 409/400.
    """
    if isinstance(exc, BusinessAPIException):
        raise exc

    err_text = str(exc)
    logger.warning(
        "Bắt được lỗi CSDL khi thực hiện %s trên ParkingSlot: %s", operation, err_text
    )

    # 1. Rào chắn xóa mềm: đang có xe đỗ (OCCUPIED hoặc open session)
    if "PROP-DEL-05-OCCUPIED" in err_text or "đang có phương tiện đỗ" in err_text:
        raise BusinessAPIException(
            code="PROP-DEL-05-OCCUPIED",
            message=get_prop_message(
                "PROP-DEL-05-OCCUPIED",
                "Không thể xóa vị trí đỗ xe đang có phương tiện đỗ (trạng thái OCCUPIED).",
            ),
            status_code=409,
        )

    # 2. Rào chắn xóa mềm: đang có vé đăng ký hiệu lực
    if "PROP-4.8.5-P02" in err_text or "đang có phương tiện đăng ký vé" in err_text:
        raise BusinessAPIException(
            code="PROP-4.8.5-P02",
            message=get_prop_message(
                "PROP-4.8.5-P02",
                "Vị trí đỗ xe đang có phương tiện đăng ký vé, không được phép xóa.",
            ),
            status_code=409,
        )

    # 3. Rào chắn xóa mềm: đang có đặt chỗ còn hiệu lực hoặc status RESERVED
    if "PROP-DEL-05-RESERVED" in err_text or "đang được đặt trước" in err_text:
        raise BusinessAPIException(
            code="PROP-DEL-05-RESERVED",
            message=get_prop_message(
                "PROP-DEL-05-RESERVED",
                "Vị trí đỗ xe đang được đặt trước còn hiệu lực, không được phép xóa.",
            ),
            status_code=409,
        )

    # 4. Rào chắn xóa loại xe cho phép đang được sử dụng
    if (
        "PROP-DEL-SAVT-IN-USE" in err_text
        or "Không thể xóa loại xe khỏi vị trí đỗ" in err_text
    ):
        raise BusinessAPIException(
            code="PROP-DEL-SAVT-IN-USE",
            message=get_prop_message(
                "PROP-DEL-SAVT-IN-USE",
                "Không thể xóa loại xe khỏi vị trí đỗ khi đang có vé, phiên đỗ hoặc đặt chỗ hiệu lực của loại xe này.",
            ),
            status_code=409,
        )

    # 5. Rào chắn trùng lặp mã ô đỗ trên khu vực
    if "uq_parking_slot_zone_code_active" in err_text or (
        "unique" in err_text.lower() and "code" in err_text.lower()
    ):
        raise BusinessAPIException(
            code="PROP-4.8.2-P03",
            message=get_prop_message(
                "PROP-4.8.2-P03",
                "Vị trí đỗ xe đã tồn tại trên tầng này.",
            ),
            status_code=409,
        )

    # 6. Trigger guard trạng thái: chuyển OCCUPIED khi không có phiên mở
    if (
        "không có phiên đỗ xe đang mở" in err_text
        or "khong co phien do xe dang mo" in err_text.lower()
    ):
        raise BusinessAPIException(
            code="PROP-4.5.2-P03",
            message=get_prop_message(
                "PROP-4.5.2-P03",
                "Không thể chuyển vị trí sang trạng thái đang có xe khi không có phiên đỗ xe đang mở.",
            ),
            status_code=409,
        )

    # 7. Trigger guard trạng thái: chuyển MAINTENANCE/RESERVED khi đang có xe
    if (
        "đang có xe đỗ trong ô" in err_text
        or "dang co xe do trong o" in err_text.lower()
    ):
        raise BusinessAPIException(
            code="PROP-4.5.2-P02",
            message=get_prop_message(
                "PROP-4.5.2-P02",
                "Không thể chuyển trạng thái vị trí khi đang có xe đỗ trong ô.",
            ),
            status_code=409,
        )

    # 8. Trigger guard trạng thái: chuyển AVAILABLE khi đang có xe hoặc vé/đặt chỗ
    if (
        "đang có xe đỗ hoặc đặt trước" in err_text
        or "dang co xe do hoac dat truoc" in err_text.lower()
    ):
        raise BusinessAPIException(
            code="PROP-4.5.2-P04",
            message=get_prop_message(
                "PROP-4.5.2-P04",
                "Không thể đánh dấu vị trí trống khi đang có xe đỗ hoặc đặt trước còn hiệu lực.",
            ),
            status_code=409,
        )

    # 9. Lỗi Check Constraint chung
    if isinstance(exc, IntegrityError):
        code = "PROP-4.8.2-P02" if operation == "create" else "PROP-4.8.3-P02"
        msg = (
            "Dữ liệu vị trí đỗ xe không hợp lệ, xin mời nhập lại."
            if operation == "create"
            else "Dữ liệu cập nhật vị trí đỗ xe không hợp lệ."
        )
        raise BusinessAPIException(
            code=code,
            message=get_prop_message(code, msg),
            status_code=400,
        )

    raise exc


def create_parking_slot(
    data: dict[str, Any],
    actor_id: int | None = None,
) -> ParkingSlot:
    """
    Thực hiện thêm mới ô đỗ xe vào cơ sở dữ liệu (SRS 4.8.2).
    Chạy trong giao dịch nguyên tử, chống trùng lặp mã và liên kết loại phương tiện.
    """
    zone_id = data["zone_id"]
    code = data["code"].strip().upper()

    try:
        with transaction.atomic():
            # Kiểm tra trùng lặp mã ô đỗ trong khu vực
            if ParkingSlot.objects.filter(
                zone_id=zone_id,
                code=code,
                deleted_at__isnull=True,
            ).exists():
                raise BusinessAPIException(
                    code="PROP-4.8.2-P03",
                    message=get_prop_message(
                        "PROP-4.8.2-P03",
                        "Vị trí đỗ xe đã tồn tại trên tầng này.",
                    ),
                    status_code=409,
                )

            slot = ParkingSlot.objects.create(
                zone_id=zone_id,
                code=code,
                slot_kind=data.get("slot_kind", "STANDARD"),
                status=data.get("status", "AVAILABLE"),
                map_row=data.get("map_row"),
                map_col=data.get("map_col"),
                width=Decimal(str(data.get("width", "2.50"))),
                length=Decimal(str(data.get("length", "5.00"))),
                height=Decimal(str(data.get("height", "2.20"))),
                notes=data.get("notes", ""),
                row_version=1,
            )

            # Liên kết các loại phương tiện cho phép
            allowed_type_ids = data.get("allowed_vehicle_type_ids", [])
            if allowed_type_ids:
                existing_types = VehicleType.objects.filter(
                    id__in=allowed_type_ids,
                    deleted_at__isnull=True,
                )
                for vt in existing_types:
                    SlotAllowedVehicleType.objects.create(
                        slot=slot,
                        vehicle_type=vt,
                    )

            return slot
    except Exception as exc:
        _translate_slot_db_error(exc, operation="create")
        raise exc


def update_parking_slot(
    slot_id: int,
    data: dict[str, Any],
    actor_id: int | None = None,
) -> ParkingSlot:
    """
    Cập nhật thông tin ô đỗ xe với kiểm soát đồng thời lạc quan (OCC) qua row_version (SRS 4.8.3).
    Sử dụng select_for_update() và bắt các ngoại lệ trigger ràng buộc trạng thái.
    """
    try:
        with transaction.atomic():
            current_slot = (
                ParkingSlot.objects.select_for_update()
                .filter(id=slot_id, deleted_at__isnull=True)
                .first()
            )
            if not current_slot:
                raise BusinessAPIException(
                    code="PROP-4.8.5-P05",
                    message=get_prop_message(
                        "PROP-4.8.5-P05",
                        "Vị trí đỗ xe không tồn tại hoặc đã bị xóa.",
                    ),
                    status_code=404,
                )

            # 1. Kiểm tra Optimistic Concurrency Control (OCC)
            incoming_version = data.get("row_version")
            if (
                incoming_version is not None
                and current_slot.row_version != incoming_version
            ):
                raise BusinessAPIException(
                    code="PROP-4.8.3-P03",
                    message=get_prop_message(
                        "PROP-4.8.3-P03",
                        "Vị trí đỗ xe đang được cập nhật bởi người dùng khác.",
                    ),
                    status_code=409,
                )

            # 2. Kiểm tra trùng lặp nếu đổi mã ô hoặc đổi khu vực
            target_code = data.get("code", current_slot.code).strip().upper()
            target_zone_id = data.get("zone_id", current_slot.zone_id)
            if (
                target_code != current_slot.code
                or target_zone_id != current_slot.zone_id
            ) and (
                ParkingSlot.objects.filter(
                    zone_id=target_zone_id,
                    code=target_code,
                    deleted_at__isnull=True,
                )
                .exclude(id=current_slot.id)
                .exists()
            ):
                raise BusinessAPIException(
                    code="PROP-4.8.2-P03",
                    message=get_prop_message(
                        "PROP-4.8.2-P03",
                        "Vị trí đỗ xe đã tồn tại trên tầng này.",
                    ),
                    status_code=409,
                )

            # 3. Gán các giá trị mới
            if "code" in data:
                current_slot.code = target_code
            if "zone_id" in data:
                current_slot.zone_id = target_zone_id
            if "slot_kind" in data:
                current_slot.slot_kind = data["slot_kind"]
            if "status" in data:
                current_slot.status = data["status"]
            if "map_row" in data:
                current_slot.map_row = data["map_row"]
            if "map_col" in data:
                current_slot.map_col = data["map_col"]
            if "width" in data:
                current_slot.width = Decimal(str(data["width"]))
            if "length" in data:
                current_slot.length = Decimal(str(data["length"]))
            if "height" in data:
                current_slot.height = Decimal(str(data["height"]))
            if "notes" in data:
                current_slot.notes = data["notes"]

            current_slot.save()

            # 4. Cập nhật danh sách loại phương tiện nếu được truyền
            if "allowed_vehicle_type_ids" in data:
                new_type_ids = set(data["allowed_vehicle_type_ids"])
                existing_links = SlotAllowedVehicleType.objects.filter(
                    slot=current_slot
                )
                existing_ids = {link.vehicle_type_id for link in existing_links}

                to_remove = existing_ids - new_type_ids
                to_add = new_type_ids - existing_ids

                if to_remove:
                    SlotAllowedVehicleType.objects.filter(
                        slot=current_slot,
                        vehicle_type_id__in=to_remove,
                    ).delete()

                if to_add:
                    valid_types = VehicleType.objects.filter(
                        id__in=to_add,
                        deleted_at__isnull=True,
                    )
                    for vt in valid_types:
                        SlotAllowedVehicleType.objects.create(
                            slot=current_slot,
                            vehicle_type=vt,
                        )

            return current_slot
    except Exception as exc:
        _translate_slot_db_error(exc, operation="update")
        raise exc


def soft_delete_parking_slot(
    slot_id: int,
    actor_id: int | None = None,
) -> dict[str, str]:
    """
    Xóa mềm ô đỗ xe (SRS 4.8.5, TL-25, TL-27, TL-39).
    Thực hiện rào chắn chặn xóa nếu ô đang có xe đỗ, có vé active hoặc có đặt chỗ active.
    """
    now = timezone.now()

    try:
        with transaction.atomic():
            slot = (
                ParkingSlot.objects.select_for_update()
                .filter(id=slot_id, deleted_at__isnull=True)
                .first()
            )
            if not slot:
                raise BusinessAPIException(
                    code="PROP-4.8.5-P05",
                    message=get_prop_message(
                        "PROP-4.8.5-P05",
                        "Vị trí đỗ xe không tồn tại hoặc đã bị xóa.",
                    ),
                    status_code=404,
                )

            # 1. Rào chắn: Ô đang đỗ hoặc sạc, hoặc có phiên đỗ xe đang mở
            if (
                slot.status in ("OCCUPIED", "CHARGING")
                or VehicleEntryExitLog.objects.filter(
                    slot_id=slot.id, exit_time__isnull=True
                ).exists()
            ):
                raise BusinessAPIException(
                    code="PROP-DEL-05-OCCUPIED",
                    message=get_prop_message(
                        "PROP-DEL-05-OCCUPIED",
                        "Không thể xóa vị trí đỗ xe đang có phương tiện đỗ (trạng thái OCCUPIED).",
                    ),
                    status_code=409,
                )

            # 2. Rào chắn: Ô đang có vé đỗ xe hiệu lực
            if Ticket.objects.filter(
                slot_id=slot.id,
                deleted_at__isnull=True,
                status__in=["ACTIVE", "RENEWING"],
                effective_to__gt=now,
            ).exists():
                raise BusinessAPIException(
                    code="PROP-4.8.5-P02",
                    message=get_prop_message(
                        "PROP-4.8.5-P02",
                        "Vị trí đỗ xe đang có phương tiện đăng ký vé, không được phép xóa.",
                    ),
                    status_code=409,
                )

            # 3. Rào chắn: Ô đang có đặt trước còn hiệu lực hoặc status RESERVED
            if (
                slot.status == "RESERVED"
                or SlotReservation.objects.filter(
                    slot_id=slot.id,
                    deleted_at__isnull=True,
                    status="ACTIVE",
                    reserved_until__gt=now,
                ).exists()
            ):
                raise BusinessAPIException(
                    code="PROP-DEL-05-RESERVED",
                    message=get_prop_message(
                        "PROP-DEL-05-RESERVED",
                        "Vị trí đỗ xe đang được đặt trước còn hiệu lực, không được phép xóa.",
                    ),
                    status_code=409,
                )

            # Thực hiện xóa mềm bằng cách gán deleted_at và deleted_by
            slot.deleted_at = now
            if actor_id:
                slot.deleted_by_id = actor_id
            slot.save(update_fields=["deleted_at", "deleted_by_id"])

            return {
                "code": "PROP-4.8.5-P01",
                "message": get_prop_message(
                    "PROP-4.8.5-P01", "Xóa vị trí đỗ xe thành công."
                ),
            }
    except Exception as exc:
        _translate_slot_db_error(exc, operation="delete")
        raise exc
