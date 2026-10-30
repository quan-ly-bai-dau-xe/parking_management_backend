"""
Views for Customer Management API per SRS 4.4.1–4.4.5 and Round 66 specifications.
Provides list, create, detail, update, delete, summary, and vehicle create alias endpoints.
"""

from __future__ import annotations

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
from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsEmployeeOrManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.customers.models import Customer
from apps.customers.selectors.customers import (
    get_customer_by_id,
    get_customer_status_summary,
    get_customers_queryset,
)
from apps.customers.serializers.customers import (
    CustomerCreateSerializer,
    CustomerDeleteSuccessSerializer,
    CustomerDetailSerializer,
    CustomerFilterSerializer,
    CustomerListSerializer,
    CustomerSummarySerializer,
    CustomerUpdateSerializer,
    CustomerVehicleCreateSerializer,
)
from apps.customers.services.customers import (
    create_customer,
    delete_customer,
    update_customer,
)
from apps.vehicles.selectors.vehicles import get_vehicle_by_id
from apps.vehicles.serializers.vehicles import VehicleDetailSerializer
from apps.vehicles.services.vehicles import create_vehicle


class CustomerListCreateView(APIView):
    """
    API Danh sách & Thêm mới khách hàng (SRS 4.4.1 & 4.4.3).
    - GET: Xem danh sách phân trang (StandardResultsSetPagination). Quyền: EMPLOYEE, MANAGER.
    - POST: Thêm mới khách hàng (hỗ trợ tạo kèm mảng xe nguyên tử). Quyền: EMPLOYEE, MANAGER. Bảo vệ CSRF.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]
    pagination_class: type[StandardResultsSetPagination] | None = (
        StandardResultsSetPagination
    )

    def get_permissions(self) -> list[Any]:
        return [IsAuthenticated(), IsEmployeeOrManager()]

    @extend_schema(
        operation_id="customers_list",
        tags=["Customers"],
        summary="Danh sách khách hàng phân trang (SRS 4.4.1)",
        description=(
            "Lấy danh sách khách hàng theo các tiêu chí tìm kiếm đa điều kiện (mã KH, tên, SĐT, CCCD, trạng thái), "
            "hỗ trợ phân trang và sắp xếp theo whitelist. "
            "Mỗi dòng hiển thị mã KH, họ tên, SĐT, CCCD, trạng thái, số lượng xe, trạng thái vé còn hạn và row_version. "
            "Khách hàng đã ẩn danh (is_anonymized = True) tự động che dấu PII. "
            "Cam kết loại trừ hoàn toàn truy vấn N+1 (Zero N+1 design)."
        ),
        parameters=[
            OpenApiParameter(
                name="code",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo mã khách hàng (khớp chính xác không phân biệt hoa thường)",
            ),
            OpenApiParameter(
                name="name",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo họ và tên khách hàng (tìm kiếm chuỗi con kích hoạt GIN trigram)",
            ),
            OpenApiParameter(
                name="phone",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo số điện thoại (chứa chuỗi số)",
            ),
            OpenApiParameter(
                name="identity_card",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo số CCCD/CMND (chứa chuỗi số)",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo trạng thái: ACTIVE, SUSPENDED, BLACKLISTED",
            ),
            OpenApiParameter(
                name="ordering",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Trường sắp xếp: code, -code, full_name, -full_name, created_at, -created_at, row_version, -row_version",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Số thứ tự trang kết quả",
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Số lượng bản ghi mỗi trang (mặc định 20, tối đa 100)",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=CustomerListSerializer(many=True),
                description="Lấy danh sách khách hàng thành công",
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
        filter_serializer = CustomerFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        filters = filter_serializer.validated_data

        queryset = get_customers_queryset(filters=filters)

        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = CustomerListSerializer(
            page, many=True, context={"request": request}
        )
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        operation_id="customers_create",
        tags=["Customers"],
        summary="Thêm mới khách hàng (SRS 4.4.3)",
        description=(
            "Thêm mới hồ sơ khách hàng vào hệ thống với thẩm định chuỗi thô (raw-string validation). "
            "Quyền hạn: EMPLOYEE hoặc MANAGER. Yêu cầu CSRF token trong header X-CSRFToken. "
            "Tự động sinh mã KH%04d tuần tự dưới khóa cố vấn giao dịch (pg_advisory_xact_lock) nếu bỏ trống. "
            "Hỗ trợ đăng ký kèm danh sách phương tiện trong cùng một giao dịch (all-or-nothing rollback). "
            "Trả về toàn bộ lỗi xác thực cùng lúc theo chuẩn Rule 04."
        ),
        request=CustomerCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=CustomerDetailSerializer,
                description="Thêm mới thông tin khách hàng thành công",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Dữ liệu đầu vào không hợp lệ hoặc sai định dạng",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Xung đột dữ liệu trùng lặp CCCD, SĐT, Email hoặc Mã KH (MSG-4.3.1-M05)",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = CustomerCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer = create_customer(
            data=data,
            created_by=request.user,
            vehicles_data=data.get("vehicles"),
        )

        detail_customer = get_customer_by_id(customer.id)
        response_serializer = CustomerDetailSerializer(
            detail_customer, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class CustomerSummaryView(APIView):
    """
    API Thống kê 4 thẻ KPI chỉ số khách hàng (SRS 4.4.1).
    Tính toán 4 thẻ số liệu trên đầu màn hình Quản lý khách hàng:
    1. Tổng khách hàng
    2. Thuê bao kích hoạt
    3. Sắp hết hạn (7 ngày)
    4. Blacklist / Tạm khóa
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    def get_permissions(self) -> list[Any]:
        return [IsAuthenticated(), IsEmployeeOrManager()]

    @extend_schema(
        operation_id="customers_summary",
        tags=["Customers"],
        summary="Thống kê 4 thẻ chỉ số KPI khách hàng (SRS 4.4.1)",
        description=(
            "Tính toán 4 chỉ số thống kê tổng quan của khách hàng: "
            "Tổng số khách hàng chưa bị xóa mềm, Số khách hàng có thuê bao kích hoạt, "
            "Số khách hàng có thuê bao sắp hết hạn trong vòng 7 ngày, "
            "và Số khách hàng ở trạng thái SUSPENDED hoặc BLACKLISTED. "
            "Hoạt động như Single Source of Truth (SOT) khớp 100% với danh sách lọc."
        ),
        responses={
            200: OpenApiResponse(
                response=CustomerSummarySerializer,
                description="Tính toán số liệu KPI thành công",
                examples=[
                    OpenApiExample(
                        "Dữ liệu mẫu KPI màn hình Khách hàng",
                        value={
                            "total_customers": 1420,
                            "active_subscriptions": 1280,
                            "active_subscribers": 1280,
                            "expiring_soon_subscriptions": 42,
                            "expiring_soon_subscribers": 42,
                            "blacklisted_or_suspended": 15,
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
        summary_data = get_customer_status_summary()
        serializer = CustomerSummarySerializer(summary_data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class CustomerDetailView(APIView):
    """
    API Xem chi tiết, Cập nhật và Xóa mềm khách hàng (SRS 4.4.2, 4.4.4, 4.4.5).
    - GET: Xem chi tiết hồ sơ khách hàng, 3 cấp hành chính và mảng xe liên kết.
    - PATCH: Cập nhật thông tin khách hàng, kiểm soát OCC (row_version).
    - DELETE: Xóa mềm khách hàng per DEL-02, kích hoạt 3 rào chắn CSDL (xe trong bãi, vé còn hạn, còn xe hoạt động).
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    def get_permissions(self) -> list[Any]:
        return [IsAuthenticated(), IsEmployeeOrManager()]

    @extend_schema(
        operation_id="customers_retrieve",
        tags=["Customers"],
        summary="Chi tiết hồ sơ khách hàng (SRS 4.4.2)",
        description=(
            "Lấy toàn bộ thông tin hồ sơ của khách hàng theo ID khóa chính. "
            "Bao gồm thông tin cá nhân, 3 cấp hành chính (Tỉnh, Quận, Phường), "
            "trạng thái hoạt động, cờ ẩn danh, row_version, "
            "và danh sách phương tiện sở hữu kèm thông tin vé đại diện (zero N+1 design)."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID khóa chính của khách hàng",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=CustomerDetailSerializer,
                description="Lấy chi tiết khách hàng thành công",
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
                description="Khách hàng không tồn tại hoặc đã bị xóa (PROP-4.4.4-P02)",
            ),
        },
    )
    def get(self, request: Request, id: int) -> Response:
        customer = get_customer_by_id(id)
        serializer = CustomerDetailSerializer(customer, context={"request": request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="customers_partial_update",
        tags=["Customers"],
        summary="Cập nhật thông tin khách hàng (SRS 4.4.4)",
        description=(
            "Cập nhật từng phần thông tin hồ sơ khách hàng. "
            "Quyền hạn: EMPLOYEE hoặc MANAGER. Yêu cầu CSRF token trong header X-CSRFToken. "
            "Bắt buộc truyền row_version để kiểm soát cập nhật đồng thời (Optimistic Concurrency Control). "
            "Mã khách hàng là bất biến không được phép sửa. "
            "Nếu chuyển trạng thái sang BLACKLISTED, bắt buộc phải có lý do khóa (status_reason). "
            "Kiểm tra tính toàn vẹn cơ cấu địa giới hành chính (Phường thuộc Quận, Quận thuộc Tỉnh)."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID khóa chính của khách hàng cần cập nhật",
            ),
        ],
        request=CustomerUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=CustomerDetailSerializer,
                description="Cập nhật thông tin khách hàng thành công",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Dữ liệu đầu vào không hợp lệ hoặc thiếu lý do khóa",
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
                description="Khách hàng không tồn tại hoặc đã bị xóa",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Xung đột phiên bản dữ liệu (Stale row_version - MSG-4.3.1-M03) hoặc trùng lặp CCCD/SĐT/Email",
            ),
        },
    )
    def patch(self, request: Request, id: int) -> Response:
        serializer = CustomerUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        updated_customer = update_customer(
            customer_id=id,
            data=serializer.validated_data,
            updated_by=request.user,
        )

        detail_customer = get_customer_by_id(updated_customer.id)
        response_serializer = CustomerDetailSerializer(
            detail_customer, context={"request": request}
        )
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="customers_destroy",
        tags=["Customers"],
        summary="Xóa mềm khách hàng (SRS 4.4.5, DEL-02)",
        description=(
            "Xóa mềm khách hàng khỏi hệ thống (cập nhật deleted_at và deleted_by). "
            "Quyền hạn: EMPLOYEE hoặc MANAGER. Yêu cầu CSRF token trong header X-CSRFToken. "
            "Kích hoạt 3 rào chắn kiểm soát toàn vẹn CSDL (DEL-02): "
            "1. Chặn đứng nếu khách hàng có xe đang trong bãi (409 PROP-4.4.5-P02), "
            "2. Chặn đứng nếu khách hàng có vé còn hiệu lực (409 PROP-4.4.5-P03), "
            "3. Chặn đứng nếu khách hàng còn phương tiện hoạt động trong hệ thống (409 PROP-DEL-02-ACTIVE-VEH)."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID khóa chính của khách hàng cần xóa mềm",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=CustomerDeleteSuccessSerializer,
                description="Xóa thành công (MSG-4.4.5-M01)",
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
                description="Khách hàng không tồn tại hoặc đã bị xóa trước đó",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Vi phạm rào chắn CSDL DEL-02 (xe trong bãi, vé còn hạn, còn xe hoạt động)",
            ),
        },
    )
    def delete(self, request: Request, id: int) -> Response:
        result = delete_customer(
            customer_id=id,
            deleted_by=request.user,
        )
        return Response(result, status=status.HTTP_200_OK)


class CustomerVehicleCreateAliasView(APIView):
    """
    API Đăng ký phương tiện trực tiếp cho khách hàng (SCO-06).
    POST /api/v1/customers/<int:customer_id>/vehicles/
    Gọi trực tiếp service create_vehicle từ apps.vehicles.services.vehicles.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    def get_permissions(self) -> list[Any]:
        return [IsAuthenticated(), IsEmployeeOrManager()]

    @extend_schema(
        operation_id="customers_vehicles_create",
        tags=["Customers"],
        summary="Thêm mới phương tiện cho khách hàng (SCO-06)",
        description=(
            "Endpoint alias hỗ trợ đăng ký phương tiện mới trực tiếp dưới một khách hàng cụ thể. "
            "Quyền hạn: EMPLOYEE hoặc MANAGER. Yêu cầu CSRF token trong header X-CSRFToken. "
            "Thẩm định định dạng biển số xe, loại xe (CAR/EV) và tự sinh mã xe nếu bỏ trống."
        ),
        parameters=[
            OpenApiParameter(
                name="customer_id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID khóa chính của khách hàng sở hữu phương tiện",
            ),
        ],
        request=CustomerVehicleCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=VehicleDetailSerializer,
                description="Thêm mới phương tiện thành công",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Dữ liệu đầu vào không hợp lệ hoặc sai định dạng biển số",
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
                description="Khách hàng không tồn tại hoặc đã bị xóa (PROP-4.4.4-P02)",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Biển số xe đã tồn tại trong hệ thống (MSG-4.3.1-M05)",
            ),
        },
    )
    def post(self, request: Request, customer_id: int) -> Response:
        customer = Customer.objects.filter(
            id=customer_id, deleted_at__isnull=True
        ).first()
        if not customer:
            raise BusinessAPIException(
                code="PROP-4.4.4-P02",
                message="Khách hàng không tồn tại hoặc đã bị xóa.",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        serializer = CustomerVehicleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        vehicle = create_vehicle(
            license_plate=data["license_plate"],
            model_name=data["model_name"],
            vehicle_type_id=data["vehicle_type_id"],
            customer_id=customer.id,
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
