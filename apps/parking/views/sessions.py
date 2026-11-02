"""
Session views for parking app per TL-05, TL-50, and SRS 4.5.1.
Implements check-in, check-out, session listing with filters & pagination, and session details.
"""

import time
from typing import Any

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessAPIException
from apps.core.messages import ALL_MESSAGES
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsEmployeeOrManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.parking.selectors.sessions import get_session_by_id, list_sessions
from apps.parking.serializers.sessions import (
    CheckInRequestSerializer,
    CheckInResponseSerializer,
    CheckOutRequestSerializer,
    CheckOutResponseSerializer,
    ParkingSessionFilterSerializer,
    PaymentSummarySerializer,
    SessionDetailSerializer,
    SessionListItemSerializer,
)
from apps.parking.services.check_in import check_in_vehicle
from apps.parking.services.check_out import check_out_vehicle
from apps.parking.views.scans import (
    finalize_observability_response,
    init_observability_context,
    set_observability_metadata,
)


class CheckInView(APIView):
    """
    API Check-in ghi nhận lượt phương tiện vào bãi đỗ.
    Hỗ trợ cả xe đã đăng ký (tự động link xe qua trigger TL-17) và khách vãng lai (TL-05).
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        init_observability_context(request)
        super().initial(request, *args, **kwargs)

    def finalize_response(
        self, request: Request, response: Response, *args: Any, **kwargs: Any
    ) -> Response:
        resp = super().finalize_response(request, response, *args, **kwargs)
        return finalize_observability_response(
            request, resp, "/api/v1/parking/sessions/check-in/"
        )

    @extend_schema(
        operation_id="parking_sessions_check_in",
        tags=["Parking - Vehicle entry/exit"],
        summary="Check-in phương tiện vào bãi đỗ xe",
        description=(
            "Ghi nhận lượt xe vào bãi tại barrier: chuẩn hóa biển số, tự động liên kết phương tiện "
            "qua trigger CSDL (TL-17), tự động xác định vé còn hạn và vị trí đỗ (nếu có), "
            "kiểm tra danh sách đen (yêu cầu quyền Quản lý và cờ override_blacklist để mở barrier), "
            "sinh mã phiên an toàn race-condition (#PK-YYYYMMDD-NNN) và lưu vết nhân viên xử lý."
        ),
        request=CheckInRequestSerializer,
        examples=[
            OpenApiExample(
                "Check-in xe Camry",
                value={
                    "license_plate": "51K-992.14",
                    "entry_gate_id": 1,
                    "recognition_source": "AI",
                    "ai_confidence": 98.50,
                    "entry_image_url": "https://res.cloudinary.com/parking-cloud/image/upload/v1729238400/parking_scans/2026/10/18/f3e1a8b2c4d5e6f7a8b9c0d1e2f3a4b5.jpg",
                },
                request_only=True,
            )
        ],
        responses={
            201: OpenApiResponse(
                response=CheckInResponseSerializer,
                description="Check-in thành công",
                examples=[
                    OpenApiExample(
                        "Check-in thành công xe Camry",
                        value={
                            "session": {
                                "id": 101,
                                "session_code": "#PK-20261018-001",
                                "vehicle_id": 1,
                                "slot_id": 1,
                                "slot_display": "Tầng B1 - Zone A - A-01",
                                "ticket_id": 1,
                                "entry_gate_id": 1,
                                "entry_gate_name": "Cổng vào 1",
                                "exit_gate_id": None,
                                "exit_gate_name": None,
                                "license_plate": "51K-992.14",
                                "license_plate_norm": "51K99214",
                                "ai_confidence": "98.50",
                                "recognition_source": "AI",
                                "review_status": "AUTO",
                                "fee_amount": "0.00",
                                "entry_time": "2026-10-18T08:00:00Z",
                                "exit_time": None,
                                "duration_seconds": 0,
                                "duration_text": "0 giây",
                                "entry_image_url": "https://res.cloudinary.com/parking-cloud/image/upload/v1729238400/parking_scans/2026/10/18/f3e1a8b2c4d5e6f7a8b9c0d1e2f3a4b5.jpg",
                                "exit_image_url": None,
                                "entry_handled_by": 2,
                                "entry_handled_by_name": "Đỗ Minh Quân",
                                "exit_handled_by": None,
                                "exit_handled_by_name": None,
                                "notes": None,
                                "created_at": "2026-10-18T08:00:00Z",
                            },
                            "vehicle_lookup": {
                                "vehicle": {
                                    "id": 1,
                                    "code": "XE0001",
                                    "license_plate": "51K-992.14",
                                    "license_plate_norm": "51K99214",
                                    "model_name": "Camry 2.5Q",
                                    "brand": "Toyota",
                                    "color": "Đen",
                                    "vehicle_type": "Ô tô",
                                    "vehicle_type_code": "CAR",
                                },
                                "customer": {
                                    "id": 1,
                                    "code": "KH0001",
                                    "full_name": "Nguyễn Văn An",
                                    "phone": "0912345678",
                                    "is_anonymized": False,
                                },
                                "parking_position": {
                                    "slot_id": 1,
                                    "slot_code": "A-01",
                                    "zone_code": "A",
                                    "floor_code": "B1",
                                    "floor_name": "Tầng B1",
                                    "display_text": "Tầng B1 - Zone A - A-01",
                                },
                                "active_ticket": {
                                    "id": 1,
                                    "code": "VT0001",
                                    "ticket_type_name": "Vé tháng",
                                    "price": "500000.00",
                                    "effective_from": "2026-10-01T00:00:00Z",
                                    "effective_to": "2026-10-31T23:59:59Z",
                                    "status": "ACTIVE",
                                },
                                "open_session": None,
                                "is_blacklisted": False,
                            },
                        },
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Dữ liệu đầu vào không hợp lệ",
                examples=[
                    OpenApiExample(
                        "Sai định dạng biển số xe",
                        value={
                            "code": "PROP-4.5.1-P01",
                            "message": "Định dạng biển số xe không hợp lệ.",
                            "details": {},
                        },
                    )
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực",
                examples=[
                    OpenApiExample(
                        "Chưa xác thực",
                        value={
                            "code": "MSG-4.1-M02",
                            "message": "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu",
                            "details": {},
                        },
                    )
                ],
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập",
                examples=[
                    OpenApiExample(
                        "Không đủ quyền",
                        value={
                            "code": "MSG-4.2-M01",
                            "message": "Bạn không có quyền thực hiện thao tác này.",
                            "details": {},
                        },
                    )
                ],
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Xung đột nghiệp vụ (đã có phiên mở, xe thuộc danh sách đen, vị trí đỗ bị xung đột)",
                examples=[
                    OpenApiExample(
                        "Xe đã có phiên đỗ đang mở",
                        value={
                            "code": "PROP-4.5.1-P07",
                            "message": "Biển số xe đã có phiên đỗ xe đang mở chưa hoàn thành.",
                            "details": {},
                        },
                    ),
                    OpenApiExample(
                        "Xe nằm trong danh sách đen",
                        value={
                            "code": "PROP-4.5.1-P08",
                            "message": "Biển số xe nằm trong danh sách đen, không được phép vào bãi.",
                            "details": {},
                        },
                    ),
                    OpenApiExample(
                        "Vị trí đỗ đang bảo trì",
                        value={
                            "code": "PROP-4.5.2-P01",
                            "message": "Vị trí này đang bảo trì.",
                            "details": {},
                        },
                    ),
                ],
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CheckInRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        stages: dict[str, float] = getattr(request, "_obs_stages", {})
        t_db0 = time.perf_counter()
        session, vehicle_lookup = check_in_vehicle(
            license_plate=data["license_plate"],
            entry_gate_id=data.get("entry_gate_id"),
            slot_id=data.get("slot_id"),
            recognition_source=data.get("recognition_source", "AI"),
            ai_confidence=data.get("ai_confidence"),
            entry_image_url=data.get("entry_image_url"),
            override_blacklist=data.get("override_blacklist", False),
            user=request.user,
            notes=data.get("notes"),
        )
        stages["db"] = (time.perf_counter() - t_db0) * 1000.0
        set_observability_metadata(
            request,
            review_status=session.review_status,
            plate=session.license_plate,
        )

        session_serializer = SessionDetailSerializer(session)
        return Response(
            {
                "session": session_serializer.data,
                "vehicle_lookup": vehicle_lookup,
            },
            status=status.HTTP_201_CREATED,
        )


class CheckOutView(APIView):
    """
    API Check-out kết thúc phiên đỗ xe và thu phí tại cổng ra.
    Khóa dòng select_for_update an toàn đồng thời, tính phí tự động (OQ-85, TL-50),
    và tạo hóa đơn thanh toán nếu cước phí > 0.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        init_observability_context(request)
        super().initial(request, *args, **kwargs)

    def finalize_response(
        self, request: Request, response: Response, *args: Any, **kwargs: Any
    ) -> Response:
        resp = super().finalize_response(request, response, *args, **kwargs)
        return finalize_observability_response(
            request, resp, "/api/v1/parking/sessions/check-out/"
        )

    @extend_schema(
        operation_id="parking_sessions_check_out",
        tags=["Parking - Vehicle entry/exit"],
        summary="Check-out phương tiện rời bãi đỗ xe",
        description=(
            "Kết thúc phiên đỗ xe tại cổng ra: nhận diện phiên qua mã phiên đỗ xe HOẶC biển số xe, "
            "khóa dòng bản ghi bằng select_for_update trong transaction atomic, xác thực cổng ra "
            "(bắt buộc direction='OUT'), tính cước phí theo quy tắc (0 VND nếu có vé ACTIVE; "
            "ngược lại ceil(giờ) * 10.000 VND), yêu cầu phương thức thanh toán CASH/VIETQR và tự động "
            "tạo bản ghi Payment trạng thái PAID nếu có phí phát sinh. Hỗ trợ xe bị xóa mềm trong khi đỗ (OQ-67)."
        ),
        request=CheckOutRequestSerializer,
        examples=[
            OpenApiExample(
                "Check-out xe vãng lai",
                value={
                    "session_code": "#PK-20261018-002",
                    "exit_gate_id": 2,
                    "payment_method": "CASH",
                },
                request_only=True,
            )
        ],
        responses={
            200: OpenApiResponse(
                response=CheckOutResponseSerializer,
                description="Check-out thành công",
                examples=[
                    OpenApiExample(
                        "Check-out thành công xe vãng lai có thu phí 20.000đ",
                        value={
                            "session": {
                                "id": 102,
                                "session_code": "#PK-20261018-002",
                                "vehicle_id": None,
                                "slot_id": 2,
                                "slot_display": "Tầng B1 - Zone A - A-02",
                                "ticket_id": None,
                                "entry_gate_id": 1,
                                "entry_gate_name": "Cổng vào 1",
                                "exit_gate_id": 2,
                                "exit_gate_name": "Cổng ra 1",
                                "license_plate": "43A-111.22",
                                "license_plate_norm": "43A11122",
                                "ai_confidence": "97.00",
                                "recognition_source": "AI",
                                "review_status": "AUTO",
                                "fee_amount": "20000.00",
                                "entry_time": "2026-10-18T06:00:00Z",
                                "exit_time": "2026-10-18T07:30:00Z",
                                "duration_seconds": 5400,
                                "duration_text": "1 giờ 30 phút",
                                "entry_image_url": "https://res.cloudinary.com/parking-cloud/image/upload/v1729238400/parking_scans/2026/10/18/f3e1a8b2c4d5e6f7a8b9c0d1e2f3a4b5.jpg",
                                "exit_image_url": "https://res.cloudinary.com/parking-cloud/image/upload/v1729238400/parking_scans/2026/10/18/a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6.jpg",
                                "entry_handled_by": 2,
                                "entry_handled_by_name": "Đỗ Minh Quân",
                                "exit_handled_by": 3,
                                "exit_handled_by_name": "Lương Mai Phương",
                                "notes": None,
                                "created_at": "2026-10-18T06:00:00Z",
                            },
                            "payment": {
                                "id": 45,
                                "code": "PAY-SES-PK-20261018-002",
                                "amount": "20000.00",
                                "method": "VIETQR",
                                "status": "PAID",
                                "paid_at": "2026-10-18T07:30:00Z",
                            },
                            "vehicle_lookup": None,
                        },
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Lỗi tham số đầu vào (cung cấp cả hai hoặc thiếu cả hai mã/biển, cổng ra không hợp lệ, thiếu payment_method khi phí > 0)",
                examples=[
                    OpenApiExample(
                        "Sai tham số nhận diện phiên",
                        value={
                            "code": "PROP-4.5.1-P11",
                            "message": "Yêu cầu cung cấp chính xác một trong hai tiêu chí: mã phiên đỗ xe hoặc biển số xe.",
                            "details": {},
                        },
                    ),
                    OpenApiExample(
                        "Thiếu phương thức thanh toán",
                        value={
                            "code": "PROP-4.5.1-P09",
                            "message": "Yêu cầu chọn phương thức thanh toán hợp lệ khi cước phí đỗ xe lớn hơn 0.",
                            "details": {},
                        },
                    ),
                    OpenApiExample(
                        "Cổng ra không hợp lệ",
                        value={
                            "code": "PROP-4.5.1-P12",
                            "message": "Cổng ra không hợp lệ hoặc không phải cổng có hướng ra (OUT).",
                            "details": {},
                        },
                    ),
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực",
                examples=[
                    OpenApiExample(
                        "Chưa xác thực",
                        value={
                            "code": "MSG-4.1-M02",
                            "message": "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu",
                            "details": {},
                        },
                    )
                ],
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập",
                examples=[
                    OpenApiExample(
                        "Không đủ quyền",
                        value={
                            "code": "MSG-4.2-M01",
                            "message": "Bạn không có quyền thực hiện thao tác này.",
                            "details": {},
                        },
                    )
                ],
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không tìm thấy phiên đỗ xe đang mở (MSG-4.5.1-M01)",
                examples=[
                    OpenApiExample(
                        "Không tìm thấy phiên",
                        value={
                            "code": "MSG-4.5.1-M01",
                            "message": "Không tìm thấy dữ liệu trùng khớp",
                            "details": {},
                        },
                    )
                ],
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Phiên đỗ xe đã được kết thúc trước đó",
                examples=[
                    OpenApiExample(
                        "Phiên đỗ xe đã đóng",
                        value={
                            "code": "PROP-4.5.1-P10",
                            "message": "Phiên đỗ xe này đã được kết thúc trước đó.",
                            "details": {},
                        },
                    )
                ],
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CheckOutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        stages: dict[str, float] = getattr(request, "_obs_stages", {})
        t_db0 = time.perf_counter()
        session, payment, vehicle_lookup = check_out_vehicle(
            license_plate=data.get("license_plate"),
            session_code=data.get("session_code"),
            exit_gate_id=data["exit_gate_id"],
            payment_method=data.get("payment_method"),
            exit_image_url=data.get("exit_image_url"),
            user=request.user,
            notes=data.get("notes"),
        )
        stages["db"] = (time.perf_counter() - t_db0) * 1000.0
        set_observability_metadata(
            request,
            review_status=session.review_status,
            plate=session.license_plate,
        )

        session_serializer = SessionDetailSerializer(session)
        payment_data = PaymentSummarySerializer(payment).data if payment else None

        return Response(
            {
                "session": session_serializer.data,
                "payment": payment_data,
                "vehicle_lookup": vehicle_lookup,
            },
            status=status.HTTP_200_OK,
        )


class SessionListView(APIView):
    """
    API Danh sách lịch sử lượt đỗ xe ra/vào bãi.
    Hỗ trợ phân trang chuẩn và bộ lọc đa tiêu chí (mã phiên, biển số, thời gian, trạng thái, cước phí).
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]
    pagination_class = StandardResultsSetPagination

    @extend_schema(
        operation_id="parking_sessions_list",
        tags=["Parking - Vehicle entry/exit"],
        summary="Lấy danh sách các lượt đỗ xe ra/vào (phân trang và bộ lọc)",
        description=(
            "Truy vấn danh sách lịch sử phiên đỗ xe (màn hình 'Lịch sử ra/vào'), "
            "hỗ trợ lọc theo mã phiên (session_code), biển số xe (license_plate), khoảng thời gian vào/ra, "
            "trạng thái (status: open | closed), trạng thái duyệt (review_status: AUTO, NEEDS_REVIEW..), "
            "khoảng cước phí (min_fee / max_fee). Dữ liệu được sắp xếp giảm dần theo thời gian vào (-entry_time), "
            "tính toán thời lượng đỗ xe (giây và văn bản tiếng Việt thân thiện), loại trừ hoàn toàn N+1 queries."
        ),
        parameters=[
            OpenApiParameter(
                name="session_code",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo mã phiên đỗ xe (tìm kiếm gần đúng)",
            ),
            OpenApiParameter(
                name="license_plate",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo biển số xe (tìm kiếm gần đúng trên biển đã chuẩn hóa)",
            ),
            OpenApiParameter(
                name="entry_time_from",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Thời gian xe vào từ thời điểm (ISO 8601)",
            ),
            OpenApiParameter(
                name="entry_time_to",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Thời gian xe vào đến thời điểm (ISO 8601)",
            ),
            OpenApiParameter(
                name="exit_time_from",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Thời gian xe ra từ thời điểm (ISO 8601)",
            ),
            OpenApiParameter(
                name="exit_time_to",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Thời gian xe ra đến thời điểm (ISO 8601)",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo trạng thái phiên đỗ: 'open' (đang đỗ) hoặc 'closed' (đã rời bãi)",
            ),
            OpenApiParameter(
                name="review_status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo trạng thái duyệt AI: 'AUTO', 'NEEDS_REVIEW', 'APPROVED', 'REJECTED'",
            ),
            OpenApiParameter(
                name="min_fee",
                type=float,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Mức cước phí tối thiểu",
            ),
            OpenApiParameter(
                name="max_fee",
                type=float,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Mức cước phí tối đa",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Số trang cần xem (mặc định: 1)",
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Số bản ghi mỗi trang (mặc định: 20, tối đa: 50)",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=SessionListItemSerializer(many=True),
                description="Danh sách phiên đỗ xe phân trang thành công",
                examples=[
                    OpenApiExample(
                        "Danh sách phiên đỗ xe",
                        value=[
                            {
                                "id": 101,
                                "session_code": "#PK-20261018-001",
                                "license_plate": "51K-992.14",
                                "slot_display": "Tầng B1 - Zone A - A-01",
                                "entry_time": "2026-10-18T08:00:00Z",
                                "exit_time": None,
                                "duration_text": "Đang đỗ",
                                "fee_amount": "0.00",
                                "status": "open",
                                "review_status": "AUTO",
                            }
                        ],
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Bộ lọc truy vấn không hợp lệ",
                examples=[
                    OpenApiExample(
                        "Thời gian sai định dạng",
                        value={
                            "code": "PROP-GEN-P01",
                            "message": "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu",
                            "details": {
                                "entry_time_from": ["Sai định dạng thời gian ISO 8601."]
                            },
                        },
                    )
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực",
                examples=[
                    OpenApiExample(
                        "Chưa xác thực",
                        value={
                            "code": "MSG-4.1-M02",
                            "message": "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu",
                            "details": {},
                        },
                    )
                ],
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập",
                examples=[
                    OpenApiExample(
                        "Không đủ quyền",
                        value={
                            "code": "MSG-4.2-M01",
                            "message": "Bạn không có quyền thực hiện thao tác này.",
                            "details": {},
                        },
                    )
                ],
            ),
        },
    )
    def get(self, request: Request) -> Response:
        filter_serializer = ParkingSessionFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        filters = filter_serializer.validated_data

        qs = list_sessions(filters)
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)

        if page is not None:
            serializer = SessionListItemSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)

        serializer = SessionListItemSerializer(qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class SessionDetailView(APIView):
    """
    API Chi tiết một phiên đỗ xe theo ID.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="parking_sessions_retrieve",
        tags=["Parking - Vehicle entry/exit"],
        summary="Xem chi tiết phiên đỗ xe",
        description="Lấy thông tin chi tiết đầy đủ của một lượt đỗ xe theo khóa chính ID.",
        responses={
            200: OpenApiResponse(
                response=SessionDetailSerializer,
                description="Thông tin chi tiết phiên đỗ xe",
                examples=[
                    OpenApiExample(
                        "Chi tiết phiên đỗ xe",
                        value={
                            "id": 101,
                            "session_code": "#PK-20261018-001",
                            "vehicle_id": 1,
                            "slot_id": 1,
                            "slot_display": "Tầng B1 - Zone A - A-01",
                            "ticket_id": 1,
                            "entry_gate_id": 1,
                            "entry_gate_name": "Cổng vào 1",
                            "exit_gate_id": 2,
                            "exit_gate_name": "Cổng ra 1",
                            "license_plate": "51K-992.14",
                            "license_plate_norm": "51K99214",
                            "ai_confidence": "98.50",
                            "recognition_source": "AI",
                            "review_status": "AUTO",
                            "fee_amount": "0.00",
                            "entry_time": "2026-10-18T08:00:00Z",
                            "exit_time": "2026-10-18T09:30:00Z",
                            "duration_seconds": 5400,
                            "duration_text": "1 giờ 30 phút",
                            "entry_image_url": "https://res.cloudinary.com/parking-cloud/image/upload/v1729238400/parking_scans/2026/10/18/f3e1a8b2c4d5e6f7a8b9c0d1e2f3a4b5.jpg",
                            "exit_image_url": "https://res.cloudinary.com/parking-cloud/image/upload/v1729238400/parking_scans/2026/10/18/a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6.jpg",
                            "entry_handled_by": 2,
                            "entry_handled_by_name": "Đỗ Minh Quân",
                            "exit_handled_by": 3,
                            "exit_handled_by_name": "Lương Mai Phương",
                            "notes": None,
                            "created_at": "2026-10-18T08:00:00Z",
                        },
                    )
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực",
                examples=[
                    OpenApiExample(
                        "Chưa xác thực",
                        value={
                            "code": "MSG-4.1-M02",
                            "message": "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu",
                            "details": {},
                        },
                    )
                ],
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập",
                examples=[
                    OpenApiExample(
                        "Không đủ quyền",
                        value={
                            "code": "MSG-4.2-M01",
                            "message": "Bạn không có quyền thực hiện thao tác này.",
                            "details": {},
                        },
                    )
                ],
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không tìm thấy phiên đỗ xe",
                examples=[
                    OpenApiExample(
                        "Không tìm thấy phiên đỗ",
                        value={
                            "code": "MSG-4.4.1-M01",
                            "message": "Không tìm thấy dữ liệu",
                            "details": {},
                        },
                    )
                ],
            ),
        },
    )
    def get(self, request: Request, pk: int) -> Response:
        session = get_session_by_id(pk)
        if not session:
            raise BusinessAPIException(
                code="MSG-4.4.1-M01",
                message=ALL_MESSAGES.get("MSG-4.4.1-M01", "Không tìm thấy dữ liệu"),
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = SessionDetailSerializer(session)
        return Response(serializer.data, status=status.HTTP_200_OK)
