"""
Views for vehicle management.
Provides list, create, detail, update, delete, summary, and export endpoints.
"""

from __future__ import annotations

from typing import Any

from django.http import StreamingHttpResponse
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

from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsEmployeeOrManager, IsManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.vehicles.selectors.vehicles import (
    get_vehicle_by_id,
    get_vehicles_queryset,
    get_vehicles_summary,
)
from apps.vehicles.serializers.vehicles import (
    VehicleCreateSerializer,
    VehicleDeleteSuccessSerializer,
    VehicleDetailSerializer,
    VehicleFilterSerializer,
    VehicleListSerializer,
    VehicleSummarySerializer,
    VehicleUpdateSerializer,
)
from apps.vehicles.services.vehicles import (
    create_vehicle,
    delete_vehicle,
    export_vehicles_csv,
    update_vehicle,
)


class VehicleListCreateView(APIView):
    """
    API Danh sách & Thêm mới phương tiện.
    - GET: Xem danh sách phân trang (StandardResultsSetPagination). Quyền: EMPLOYEE, MANAGER.
    - POST: Thêm mới phương tiện. Quyền: MANAGER only. Bảo vệ CSRF bắt buộc.
    """

    pagination_class: type[StandardResultsSetPagination] | None = (
        StandardResultsSetPagination
    )

    def get_permissions(self) -> list[Any]:
        if self.request.method == "POST":
            return [IsAuthenticated(), IsManager()]
        return [IsAuthenticated(), IsEmployeeOrManager()]

    @extend_schema(
        operation_id="vehicles_list",
        tags=["Vehicles"],
        summary="Danh sách phương tiện phân trang",
        description=(
            "Lấy danh sách phương tiện theo các tiêu chí tìm kiếm đa điều kiện, "
            "hỗ trợ phân trang và sắp xếp. Trả về cấu trúc 11 cột hiển thị của màn hình Quản lý xe, "
            "bao gồm thông tin xe, khách hàng, vé liên kết, vị trí đỗ và trạng thái phái sinh TL-28.2. "
            "Cam kết loại trừ hoàn toàn truy vấn N+1 (Zero N+1 design)."
        ),
        parameters=[
            OpenApiParameter(
                name="code",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo mã xe (vd: XE0001, tìm kiếm tiền tố hoặc chứa)",
            ),
            OpenApiParameter(
                name="plate",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo biển số xe (chuẩn hóa tự động theo logic fn_normalize_license_plate)",
            ),
            OpenApiParameter(
                name="customer",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo mã hoặc họ tên khách hàng (tìm kiếm trigram không dấu/có dấu)",
            ),
            OpenApiParameter(
                name="vehicle_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo mã loại xe (chỉ chấp nhận CAR hoặc EV)",
            ),
            OpenApiParameter(
                name="ticket_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo mã loại vé (MONTHLY, DAILY, QUARTERLY, YEARLY)",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo trạng thái đỗ: parked (Đang đỗ), active (Đang hoạt động), left (Đã rời bãi)",
            ),
            OpenApiParameter(
                name="ticket_state",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo tình trạng vé: valid (Còn hạn), expiring_soon (Sắp hết hạn 7 ngày), expired (Đã hết hạn), none (Không có vé)",
            ),
            OpenApiParameter(
                name="ordering",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Sắp xếp kết quả (mặc định: -id; hỗ trợ id, code, license_plate, created_at, ticket_expires_at)",
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
                description="Số bản ghi trên mỗi trang (mặc định: 20, tối đa: 100)",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=VehicleListSerializer(many=True),
                description="Danh sách phương tiện phân trang thành công",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Tham số bộ lọc không hợp lệ",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        filter_serializer = VehicleFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        filters = filter_serializer.validated_data

        queryset = get_vehicles_queryset(
            code=filters.get("code"),
            plate=filters.get("plate"),
            customer=filters.get("customer"),
            vehicle_type=filters.get("vehicle_type"),
            ticket_type=filters.get("ticket_type"),
            status_filter=filters.get("status"),
            ticket_state=filters.get("ticket_state"),
            ordering=filters.get("ordering"),
        )

        paginator = (
            self.pagination_class() if self.pagination_class is not None else None
        )
        page = (
            paginator.paginate_queryset(queryset, request, view=self)
            if paginator
            else None
        )

        # Attach row index for sequential STT calculation in serializer
        if page is not None and paginator is not None:
            for idx, item in enumerate(page):
                item._row_index = idx  # type: ignore[attr-defined]
            serializer = VehicleListSerializer(
                page, many=True, context={"request": request}
            )
            return paginator.get_paginated_response(serializer.data)

        serializer = VehicleListSerializer(
            queryset, many=True, context={"request": request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="vehicles_create",
        tags=["Vehicles"],
        summary="Thêm mới phương tiện",
        description=(
            "Thêm mới phương tiện khách hàng đăng ký vào hệ thống. "
            "Quyền hạn: MANAGER only. Yêu cầu CSRF token trong header X-CSRFToken. "
            "Hệ thống tự động chuẩn hóa và thẩm định biển số xe theo quy chuẩn ô tô dân sự Việt Nam (Thông tư 79/2024/TT-BCA, PROP-4.5.1-P16), "
            "kiểm tra biển số trùng lặp trong các xe đang hoạt động, "
            "kiểm tra khách hàng và loại xe tồn tại (chỉ hỗ trợ CAR và EV). "
            "Nếu bỏ trống mã xe, hệ thống tự động sinh mã dạng 'XE%04d' an toàn theo giao dịch với advisory lock."
        ),
        request=VehicleCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=VehicleDetailSerializer,
                description="Thêm mới phương tiện thành công",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Dữ liệu đầu vào không hợp lệ hoặc sai định dạng biển số xe (PROP-4.5.1-P16)",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền quản lý (chỉ dành cho MANAGER)",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Biển số hoặc mã xe đã tồn tại trong hệ thống (MSG-4.3.1-M05)",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = VehicleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        vehicle = create_vehicle(
            license_plate=data["license_plate"],
            model_name=data["model_name"],
            vehicle_type_id=data["vehicle_type_id"],
            customer_id=data["customer_id"],
            code=data.get("code"),
            brand=data.get("brand"),
            color=data.get("color"),
            image_url=data.get("image_url"),
            notes=data.get("notes"),
            actor_id=request.user.id if request.user else None,
        )

        detail_vehicle = get_vehicle_by_id(vehicle.id)
        response_serializer = VehicleDetailSerializer(
            detail_vehicle, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class VehicleDetailUpdateDeleteView(APIView):
    """
    API Xem chi tiết, Cập nhật và Xóa mềm phương tiện.
    - GET: Xem chi tiết phương tiện và 3 khối panel (xe, chủ xe, vé). Quyền: EMPLOYEE, MANAGER.
    - PATCH: Cập nhật thông số phương tiện. Quyền: MANAGER only. Kiểm soát OCC (row_version).
    - DELETE: Xóa mềm phương tiện. Quyền: MANAGER only. Kiểm soát 3 guard DEL-03 từ CSDL.
    """

    def get_permissions(self) -> list[Any]:
        if self.request.method in ("PATCH", "DELETE"):
            return [IsAuthenticated(), IsManager()]
        return [IsAuthenticated(), IsEmployeeOrManager()]

    @extend_schema(
        operation_id="vehicles_retrieve",
        tags=["Vehicles"],
        summary="Xem chi tiết phương tiện",
        description=(
            "Xem thông số chi tiết phương tiện, bao gồm thông số kỹ thuật, "
            "hồ sơ chủ xe (ẩn danh dữ liệu nếu có yêu cầu bảo vệ quyền riêng tư), "
            "tiến trình vòng đời vé đỗ xe (TL-28.3), vị trí đỗ hiện tại và khóa lạc quan row_version."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID khóa chính của phương tiện",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=VehicleDetailSerializer,
                description="Trả về thông tin chi tiết phương tiện",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập",
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không tìm thấy phương tiện hoặc đã bị xóa mềm",
            ),
        },
    )
    def get(self, request: Request, id: int) -> Response:
        vehicle = get_vehicle_by_id(id)
        serializer = VehicleDetailSerializer(vehicle, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="vehicles_partial_update",
        tags=["Vehicles"],
        summary="Cập nhật thông tin phương tiện (OCC)",
        description=(
            "Cập nhật các thông số cho phép của phương tiện (tên model, hãng xe, màu sắc, ghi chú, "
            "loại xe, chủ xe). Quyền hạn: MANAGER only. Yêu cầu CSRF token. "
            "Trường 'license_plate' là bất biến (read-only) và sẽ bị bỏ qua nếu gửi trong request. "
            "Bắt buộc truyền trường 'row_version' trong body để kiểm soát đồng thời lạc quan (OCC). "
            "Nếu dữ liệu bị sửa đổi bởi người dùng khác, API trả về HTTP 409 Conflict với mã MSG-4.3.1-M03. "
            "Nếu thay đổi chủ xe khi phương tiện đang có vé, phiên đỗ đang mở hoặc đặt chỗ, API trả về HTTP 409 Conflict với mã PROP-VEH-OWNER-CHANGE-CONFLICT."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID khóa chính của phương tiện cần cập nhật",
            ),
        ],
        request=VehicleUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=VehicleDetailSerializer,
                description="Cập nhật thông tin phương tiện thành công",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Thiếu trường row_version hoặc dữ liệu không hợp lệ",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền quản lý",
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không tìm thấy phương tiện hoặc đã bị xóa mềm",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Xung đột phiên bản dữ liệu (Stale row_version - MSG-4.3.1-M03) hoặc xung đột đổi chủ sở hữu (PROP-VEH-OWNER-CHANGE-CONFLICT)",
            ),
        },
    )
    def patch(self, request: Request, id: int) -> Response:
        vehicle = get_vehicle_by_id(id)
        serializer = VehicleUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated_vehicle = update_vehicle(
            vehicle=vehicle,
            data=serializer.validated_data,
            actor_id=request.user.id if request.user else None,
        )

        detail_vehicle = get_vehicle_by_id(updated_vehicle.id)
        response_serializer = VehicleDetailSerializer(
            detail_vehicle, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="vehicles_destroy",
        tags=["Vehicles"],
        summary="Xóa mềm phương tiện (DEL-03)",
        description=(
            "Xóa mềm phương tiện (cập nhật deleted_at và deleted_by). "
            "Quyền hạn: MANAGER only. Yêu cầu CSRF token. "
            "Kích hoạt rào chắn kiểm soát toàn vẹn DEL-03 từ CSDL: "
            "Chặn đứng nếu xe đang có phiên đỗ mở (409 PROP-DEL-03-OPEN-SES), "
            "có vé đỗ còn hiệu lực (409 PROP-DEL-03-ACTIVE-TKT), "
            "hoặc có đặt chỗ còn hiệu lực (409 PROP-DEL-03-ACTIVE-RSV)."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID khóa chính của phương tiện cần xóa",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=VehicleDeleteSuccessSerializer,
                description="Xóa phương tiện thành công",
                examples=[
                    OpenApiExample(
                        "Xóa thành công",
                        value={"code": "MSG-4.3.1-M01", "message": "Xóa thành công"},
                    )
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền quản lý",
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không tìm thấy phương tiện hoặc đã bị xóa trước đó",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Vi phạm rào chắn CSDL DEL-03 (phiên đỗ mở, vé còn hạn, đặt chỗ còn hạn)",
            ),
        },
    )
    def delete(self, request: Request, id: int) -> Response:
        vehicle = get_vehicle_by_id(id)
        result = delete_vehicle(
            vehicle=vehicle,
            actor_id=request.user.id if request.user else None,
        )
        return Response(result, status=status.HTTP_200_OK)


class VehicleSummaryView(APIView):
    """
    API Tổng kết 4 chỉ số KPI phương tiện.
    Tính toán 4 thẻ số liệu trên đầu màn hình Quản lý xe:
    1. Tổng phương tiện
    2. Đang hoạt động (đang đỗ hoặc có vé hiệu lực)
    3. Vé sắp hết hạn (cửa sổ 7 ngày)
    4. Vé đã hết hạn
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="vehicles_summary",
        tags=["Vehicles"],
        summary="Thống kê 4 thẻ chỉ số KPI phương tiện",
        description=(
            "Tính toán 4 chỉ số thống kê tổng quan của đội xe: "
            "Tổng số xe, Số xe đang hoạt động (có vé hoặc đang trong bãi), "
            "Số xe có vé sắp hết hạn (cửa sổ 7 ngày per TL-10, TL-28.1, TL-28.5), "
            "và Số xe có vé đã hết hạn. Hỗ trợ truyền bộ lọc tùy chọn customer và vehicle_type."
        ),
        parameters=[
            OpenApiParameter(
                name="customer",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc số liệu theo mã hoặc họ tên khách hàng",
            ),
            OpenApiParameter(
                name="vehicle_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc số liệu theo loại xe (CAR, EV)",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=VehicleSummarySerializer,
                description="Tính toán số liệu KPI thành công",
                examples=[
                    OpenApiExample(
                        "Dữ liệu mẫu KPI màn hình Quản lý xe",
                        value={
                            "total_vehicles": 6,
                            "active_vehicles": 4,
                            "expiring_soon_tickets": 2,
                            "expired_tickets": 1,
                        },
                    )
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        customer = request.query_params.get("customer")
        vehicle_type = request.query_params.get("vehicle_type")

        summary_data = get_vehicles_summary(
            customer=customer,
            vehicle_type=vehicle_type,
        )
        serializer = VehicleSummarySerializer(summary_data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class VehicleExportView(APIView):
    """
    API Xuất file CSV danh sách phương tiện.
    Kế thừa toàn bộ bộ lọc truy vấn của danh sách xe.
    Mã hóa UTF-8 BOM, chống formula injection, giới hạn cứng 5,000 dòng.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="vehicles_export",
        tags=["Vehicles"],
        summary="Xuất file CSV danh sách phương tiện",
        description=(
            "Xuất danh sách phương tiện theo các tiêu chí bộ lọc hiện tại dưới dạng tệp CSV đính kèm UTF-8 BOM "
            "giúp mở chuẩn xác tiếng Việt trên Microsoft Excel. "
            "Toàn bộ các ô văn bản được lọc và vô hiệu hóa nguy cơ Formula Injection (=, +, -, @, \\t, \\r). "
            "Áp dụng giới hạn trần cứng tối đa 5,000 dòng."
        ),
        parameters=[
            OpenApiParameter(
                name="code",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="plate",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="customer",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="vehicle_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="ticket_type",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
            OpenApiParameter(
                name="ticket_state",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo tình trạng vé: valid (Còn hạn), expiring_soon (Sắp hết hạn 7 ngày), expired (Đã hết hạn), none (Không có vé)",
            ),
            OpenApiParameter(
                name="ordering",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
            ),
        ],
        responses={
            200: OpenApiResponse(
                description="Tệp tin CSV streamed thành công (Content-Type: text/csv; charset=utf-8)",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Tham số bộ lọc không hợp lệ",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập",
            ),
        },
    )
    def get(self, request: Request) -> StreamingHttpResponse:
        filter_serializer = VehicleFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        filters = filter_serializer.validated_data

        queryset = get_vehicles_queryset(
            code=filters.get("code"),
            plate=filters.get("plate"),
            customer=filters.get("customer"),
            vehicle_type=filters.get("vehicle_type"),
            ticket_type=filters.get("ticket_type"),
            status_filter=filters.get("status"),
            ticket_state=filters.get("ticket_state"),
            ordering=filters.get("ordering"),
        )

        response = StreamingHttpResponse(
            export_vehicles_csv(queryset),
            content_type="text/csv; charset=utf-8",
        )
        response["Content-Disposition"] = (
            'attachment; filename="danh_sach_phuong_tien.csv"'
        )
        return response
