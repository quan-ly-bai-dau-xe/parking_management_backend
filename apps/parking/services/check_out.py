"""
Check-out service for parking app per TL-50, OQ-67, OQ-85, and SRS 4.5.1.
Handles atomic vehicle exit, fee computation, select_for_update locking,
payment generation, and soft-deleted vehicle exit support.
"""

from typing import Any

from django.db import transaction
from django.utils import timezone

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import ALL_MESSAGES
from apps.employees.models import Employee
from apps.parking.models import ParkingGate, VehicleEntryExitLog
from apps.parking.selectors.vehicles import get_combined_vehicle_context
from apps.parking.services.ocr import PlateRecognizer
from apps.parking.services.tariff import calculate_parking_fee
from apps.parking.services.upload import validate_parking_image_path
from apps.tickets.models import Payment


def check_out_vehicle(
    license_plate: str | None = None,
    session_code: str | None = None,
    exit_gate_id: int | None = None,
    payment_method: str | None = None,
    exit_image_url: str | None = None,
    user: Any = None,
    notes: str | None = None,
) -> tuple[VehicleEntryExitLog, Payment | None, dict[str, Any] | None]:
    """
    Thực hiện check-out kết thúc phiên đỗ xe:
    1. Kiểm tra tham số nhận diện phiên: Yêu cầu chính xác 1 trong 2 (mã phiên hoặc biển số).
    2. Khóa dòng bản ghi bằng select_for_update() trong transaction.atomic().
    3. Xác thực cổng ra: Bắt buộc tồn tại và có direction == 'OUT'.
    4. Gán thời gian ra exit_time = server time (timezone.now()).
    5. Tính toán cước phí fee_amount theo quy tắc OQ-85 và TL-50:
       - 0.00 VND nếu có vé ACTIVE hợp lệ.
       - Ngược lại: ceil(số giờ) * PARKING_HOURLY_RATE_VND.
    6. Nếu fee_amount > 0:
       - Bắt buộc payment_method trong ('CASH', 'VIETQR').
       - Tạo đúng 1 bản ghi Payment trạng thái 'PAID' trong cùng transaction (ck_payment_single_target).
    7. Lưu phiên đỗ và giải phóng vị trí (DB trigger tự động cập nhật trạng thái slot).
    8. Đảm bảo check-out thành công ngay cả khi xe bị soft-deleted khi đang đỗ (OQ-67).
    """
    # 0. Xác thực đường dẫn hình ảnh (Defense-in-depth per F3)
    exit_image_url = validate_parking_image_path(exit_image_url)

    # 1. Kiểm tra tiêu chí nhận diện phiên
    has_plate = bool(license_plate and str(license_plate).strip())
    has_code = bool(session_code and str(session_code).strip())

    if (has_plate and has_code) or (not has_plate and not has_code):
        raise BusinessAPIException(
            code="PROP-4.5.1-P11",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P11",
                "Yêu cầu cung cấp chính xác một trong hai tiêu chí: mã phiên đỗ xe hoặc biển số xe.",
            ),
            status_code=400,
        )

    # 2. Xác thực cổng ra (exit_gate)
    if not exit_gate_id:
        raise BusinessAPIException(
            code="PROP-4.5.1-P12",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P12",
                "Cổng ra không hợp lệ hoặc không phải cổng có hướng ra (OUT).",
            ),
            status_code=400,
        )

    exit_gate = ParkingGate.objects.filter(
        id=exit_gate_id, deleted_at__isnull=True
    ).first()
    if not exit_gate or not exit_gate.is_active:
        raise BusinessAPIException(
            code="PROP-GEN-P01",
            message="Cổng ra không tồn tại hoặc đã bị vô hiệu hóa.",
            status_code=400,
        )
    if exit_gate.direction != "OUT":
        raise BusinessAPIException(
            code="PROP-4.5.1-P12",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P12",
                "Cổng ra không hợp lệ hoặc không phải cổng có hướng ra (OUT).",
            ),
            status_code=400,
        )

    # 3. Thực hiện check-out trong atomic transaction với khóa select_for_update
    with transaction.atomic():
        if has_code:
            code_val = str(session_code).strip()
            session = (
                VehicleEntryExitLog.objects.select_for_update(of=("self",))
                .select_related(
                    "ticket",
                    "vehicle__vehicle_type",
                    "vehicle__customer",
                    "slot__zone__floor",
                    "entry_gate",
                    "entry_handled_by",
                )
                .filter(session_code=code_val)
                .first()
            )
            if not session:
                raise BusinessAPIException(
                    code="MSG-4.5.1-M01",
                    message=ALL_MESSAGES.get(
                        "MSG-4.5.1-M01", "Không tìm thấy dữ liệu trùng khớp"
                    ),
                    status_code=404,
                )
            if session.exit_time is not None:
                raise BusinessAPIException(
                    code="PROP-4.5.1-P10",
                    message=ALL_MESSAGES.get(
                        "PROP-4.5.1-P10", "Phiên đỗ xe này đã được kết thúc trước đó."
                    ),
                    status_code=409,
                )
        else:
            plate_val = str(license_plate).strip()
            norm_plate = PlateRecognizer.normalize_plate(plate_val)

            # Tìm phiên đỗ xe đang mở (exit_time IS NULL)
            session = (
                VehicleEntryExitLog.objects.select_for_update(of=("self",))
                .select_related(
                    "ticket",
                    "vehicle__vehicle_type",
                    "vehicle__customer",
                    "slot__zone__floor",
                    "entry_gate",
                    "entry_handled_by",
                )
                .filter(license_plate_norm=norm_plate, exit_time__isnull=True)
                .first()
            )

            if not session:
                # Kiểm tra nếu xe đã có phiên kết thúc trước đó
                closed_exists = VehicleEntryExitLog.objects.filter(
                    license_plate_norm=norm_plate, exit_time__isnull=False
                ).exists()
                if closed_exists:
                    raise BusinessAPIException(
                        code="PROP-4.5.1-P10",
                        message=ALL_MESSAGES.get(
                            "PROP-4.5.1-P10",
                            "Phiên đỗ xe này đã được kết thúc trước đó.",
                        ),
                        status_code=409,
                    )
                raise BusinessAPIException(
                    code="MSG-4.5.1-M01",
                    message=ALL_MESSAGES.get(
                        "MSG-4.5.1-M01", "Không tìm thấy dữ liệu trùng khớp"
                    ),
                    status_code=404,
                )

        now = timezone.now()

        # 4. Tính toán cước phí (OQ-85, TL-50)
        fee_amount = calculate_parking_fee(session, now)

        # 5. Xác định nhân viên xử lý
        handled_by_employee = None
        if user and getattr(user, "is_authenticated", False):
            handled_by_employee = Employee.objects.filter(
                account=user, deleted_at__isnull=True
            ).first()

        # 6. Xử lý thanh toán nếu cước phí > 0
        payment_record = None
        if fee_amount > 0:
            if not payment_method or str(payment_method).upper() not in (
                "CASH",
                "VIETQR",
            ):
                raise BusinessAPIException(
                    code="PROP-4.5.1-P09",
                    message=ALL_MESSAGES.get(
                        "PROP-4.5.1-P09",
                        "Yêu cầu chọn phương thức thanh toán hợp lệ khi cước phí đỗ xe lớn hơn 0.",
                    ),
                    status_code=400,
                )

            clean_code = session.session_code.replace("#", "")
            payment_code = f"PAY-SES-{clean_code}"

            payment_record = Payment.objects.create(
                code=payment_code,
                amount=fee_amount,
                method=str(payment_method).upper(),
                status="PAID",
                paid_at=now,
                received_by=handled_by_employee,
                session=session,
                ticket=None,
                renewal=None,
                notes=f"Thanh toán cước phí phiên đỗ xe {session.session_code}",
            )

        # 7. Cập nhật thông tin kết thúc phiên đỗ xe
        session.exit_time = now
        session.exit_gate = exit_gate
        session.exit_image_url = exit_image_url
        session.exit_handled_by = handled_by_employee
        session.fee_amount = fee_amount
        if notes:
            session.notes = notes
        session.save()

    # Gán đầy đủ quan hệ cho session tránh N+1 khi serialize qua SessionDetailSerializer
    session.exit_gate = exit_gate
    session.exit_handled_by = handled_by_employee

    # Tra cứu thông tin xe sau khi check-out để trả về trong response (chỉ khi xe đã đăng ký)
    if session.vehicle_id is not None:
        context = get_combined_vehicle_context(
            session.license_plate, include_open_session=False
        )
        vehicle_lookup_data = context.to_lookup_dict()
    else:
        vehicle_lookup_data = None

    return session, payment_record, vehicle_lookup_data
