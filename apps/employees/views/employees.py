"""
Views for Employee Management API per SRS 4.3.1–4.3.4 and Round 67 specifications.
Provides positions list, employee summary, list, create, detail, update, and soft delete endpoints.
Strictly MANAGER-only role-based access control [IsAuthenticated, IsManager].
Full OpenAPI documentation annotations with drf-spectacular.
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

from apps.core.pagination import StandardResultsSetPagination
from apps.core.permissions import IsManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.employees.selectors.employees import (
    get_employee_by_id,
    get_employee_summary,
    list_employees,
    list_positions,
)
from apps.employees.serializers.employees import (
    EmployeeCreateSerializer,
    EmployeeDeleteSuccessSerializer,
    EmployeeDetailSerializer,
    EmployeeFilterSerializer,
    EmployeeListSerializer,
    EmployeeSummarySerializer,
    EmployeeUpdateSerializer,
    PositionSerializer,
)
from apps.employees.services.employees import (
    create_employee,
    soft_delete_employee,
    update_employee,
)

# ==============================================================================
# 1. POSITIONS LIST VIEW
# ==============================================================================


class PositionListView(APIView):
    """
    API Danh mục Chức vụ Nhân viên (phục vụ filter và form dropdown).
    GET /api/v1/positions/
    Quyền hạn: MANAGER-only ([IsAuthenticated, IsManager]).
    """

    permission_classes = [IsAuthenticated, IsManager]

    def get_permissions(self) -> list[Any]:
        return [IsAuthenticated(), IsManager()]

    @extend_schema(
        operation_id="positions_list",
        tags=["Positions"],
        summary="Danh mục chức vụ nhân viên (SRS 4.3.1)",
        description=(
            "Lấy danh sách các chức vụ công việc chưa bị xóa mềm trong hệ thống, "
            "sắp xếp đơn định theo id ASC. Phục vụ dropdown chọn chức vụ trên form thêm/sửa "
            "và bộ lọc tìm kiếm màn hình Quản lý nhân viên. "
            "Quyền truy cập: Chỉ Quản lý (MANAGER)."
        ),
        responses={
            200: OpenApiResponse(
                response=PositionSerializer(many=True),
                description="Lấy danh mục chức vụ thành công",
                examples=[
                    OpenApiExample(
                        "Danh mục chức vụ mẫu",
                        value=[
                            {"id": 1, "code": "QL", "name": "Quản lý"},
                            {"id": 2, "code": "NVVH", "name": "Nhân viên vận hành"},
                            {"id": 3, "code": "NVTN", "name": "Nhân viên thu ngân"},
                            {"id": 4, "code": "KTV", "name": "Kỹ thuật viên"},
                        ],
                    )
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính (MSG-4.1-M02)",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập (yêu cầu MANAGER - MSG-4.2-M01)",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        positions = list_positions()
        serializer = PositionSerializer(positions, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ==============================================================================
# 2. EMPLOYEE SUMMARY KPI VIEW
# ==============================================================================


class EmployeeSummaryView(APIView):
    """
    API Thống kê 4 thẻ chỉ số KPI nhân viên (SRS 4.3.1 / Mockup).
    GET /api/v1/employees/summary/
    Quyền hạn: MANAGER-only ([IsAuthenticated, IsManager]).
    """

    permission_classes = [IsAuthenticated, IsManager]

    def get_permissions(self) -> list[Any]:
        return [IsAuthenticated(), IsManager()]

    @extend_schema(
        operation_id="employees_summary",
        tags=["Employees"],
        summary="Thống kê 4 thẻ KPI nhân viên (SRS 4.3.1)",
        description=(
            "Tính toán 4 chỉ số thống kê tổng quan nhân sự trên đầu màn hình Quản lý nhân viên: "
            "Tổng số nhân viên (total_employees), Nhân viên đang hoạt động (active_employees), "
            "Nhân viên không hoạt động (inactive_employees), và Tổng số chức vụ (total_positions). "
            "Đóng vai trò Single Source of Truth (SOT) khớp 100% với independent raw SQL và bộ đếm filter."
        ),
        responses={
            200: OpenApiResponse(
                response=EmployeeSummarySerializer,
                description="Lấy thông tin thống kê KPI thành công",
                examples=[
                    OpenApiExample(
                        "Dữ liệu mẫu KPI màn hình Quản lý nhân viên",
                        value={
                            "total_employees": 8,
                            "active_employees": 7,
                            "inactive_employees": 1,
                            "total_positions": 4,
                        },
                    )
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính (MSG-4.1-M02)",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập (yêu cầu MANAGER - MSG-4.2-M01)",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        summary_data = get_employee_summary()
        serializer = EmployeeSummarySerializer(summary_data)
        return Response(serializer.data, status=status.HTTP_200_OK)


# ==============================================================================
# 3. EMPLOYEE LIST & CREATE VIEW
# ==============================================================================


class EmployeeListCreateView(APIView):
    """
    API Danh sách & Thêm mới nhân viên (SRS 4.3.1 & 4.3.2).
    - GET: Xem danh sách nhân viên phân trang (StandardResultsSetPagination).
    - POST: Thêm mới hồ sơ nhân viên và tài khoản nguyên tử trong một transaction.
    Quyền hạn: MANAGER-only ([IsAuthenticated, IsManager]).
    """

    permission_classes = [IsAuthenticated, IsManager]
    pagination_class = StandardResultsSetPagination

    def get_permissions(self) -> list[Any]:
        return [IsAuthenticated(), IsManager()]

    @extend_schema(
        operation_id="employees_list",
        tags=["Employees"],
        summary="Danh sách nhân viên phân trang (SRS 4.3.1)",
        description=(
            "Lấy danh sách nhân viên theo nhiều tiêu chí lọc (chuỗi con q trên tên, mã, email; "
            "tên, mã, địa chỉ, khoảng ngày sinh, chức vụ, trạng thái), "
            "hỗ trợ phân trang và sắp xếp theo danh sách cho phép (whitelist). "
            "Mỗi dòng hiển thị id, code, full_name, position {id, code, name}, phone, email, "
            "area {district_name, province_name}, status, status_display, row_version. "
            "Cam kết loại trừ hoàn toàn truy vấn N+1 (Zero N+1 guarantee). "
            "Tuyệt đối không chứa bất kỳ trường mật khẩu hay hash nào."
        ),
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Tìm kiếm chuỗi con trên họ tên, mã nhân viên hoặc email (DirectILike)",
            ),
            OpenApiParameter(
                name="name",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo họ và tên nhân viên (chuỗi con)",
            ),
            OpenApiParameter(
                name="code",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo mã nhân viên",
            ),
            OpenApiParameter(
                name="address",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo địa chỉ chi tiết",
            ),
            OpenApiParameter(
                name="birth_from",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Ngày sinh từ ngày (định dạng YYYY-MM-DD)",
            ),
            OpenApiParameter(
                name="birth_to",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Ngày sinh đến ngày (định dạng YYYY-MM-DD)",
            ),
            OpenApiParameter(
                name="position",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo chức vụ (ID số hoặc mã chức vụ như QL, NVVH, NVTN, KTV)",
            ),
            OpenApiParameter(
                name="status",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo trạng thái: ACTIVE hoặc INACTIVE",
            ),
            OpenApiParameter(
                name="ordering",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Trường sắp xếp trong whitelist: code, -code, full_name, -full_name, created_at, -created_at, row_version, -row_version",
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
                response=EmployeeListSerializer(many=True),
                description="Lấy danh sách nhân viên thành công",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Tham số truy vấn không hợp lệ (birth_from > birth_to hoặc ordering sai whitelist)",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính (MSG-4.1-M02)",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập (yêu cầu MANAGER - MSG-4.2-M01)",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        filter_serializer = EmployeeFilterSerializer(data=request.query_params)
        filter_serializer.is_valid(raise_exception=True)
        validated_filters = filter_serializer.validated_data

        queryset = list_employees(
            q=validated_filters.get("q"),
            name=validated_filters.get("name"),
            code=validated_filters.get("code"),
            address=validated_filters.get("address"),
            birth_from=validated_filters.get("birth_from"),
            birth_to=validated_filters.get("birth_to"),
            position=validated_filters.get("position"),
            status=validated_filters.get("status"),
            ordering=validated_filters.get("ordering"),
        )

        paginator = self.pagination_class()
        paginated_employees = paginator.paginate_queryset(queryset, request, view=self)
        serializer = EmployeeListSerializer(paginated_employees, many=True)
        return paginator.get_paginated_response(serializer.data)

    @extend_schema(
        operation_id="employees_create",
        tags=["Employees"],
        summary="Thêm mới nhân viên & tài khoản nguyên tử (SRS 4.3.2)",
        description=(
            "Tạo mới đồng thời bản ghi Account và Employee trong một transaction nguyên tử: "
            "1. Tự động suy diễn Account.role từ Position.code (QL -> MANAGER, NVVH/NVTN/KTV -> EMPLOYEE). "
            "2. Đồng bộ Account.is_active theo Employee.status (ACTIVE -> True, INACTIVE -> False). "
            "3. Kiểm tra độ phức tạp mật khẩu theo SRS 4.3.3 / Rule 07 và băm bằng Argon2. "
            "4. Tự động sinh mã nhân viên tuần tự (NVxxx / NVxxxx) dưới khóa cố vấn pg_advisory_xact_lock nếu bỏ trống mã. "
            "5. Thẩm định chuỗi thô (raw-string validation) từ chối byte NUL, control chars, zero-width chars, emoji. "
            "6. Gom toàn bộ lỗi validation trả về cùng lúc per Rule 04. "
            "7. Chuyển đổi va chạm unique index sang 409 Conflict (MSG-4.3.1-M05) mà không để lộ PII. "
            "Bảo vệ CSRF với cookieAuth + csrfAuth."
        ),
        request=EmployeeCreateSerializer,
        responses={
            201: OpenApiResponse(
                response=EmployeeDetailSerializer,
                description="Đã thêm thành công nhân viên (MSG-4.3.2-M01)",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Dữ liệu đầu vào không hợp lệ hoặc mật khẩu không đủ độ phức tạp (Rule 04 / MSG-4.3.2-M02)",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính (MSG-4.1-M02)",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập (yêu cầu MANAGER - MSG-4.2-M01)",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Xung đột dữ liệu trùng lặp Mã NV, CCCD, SĐT hoặc Email (MSG-4.3.1-M05)",
            ),
        },
    )
    def post(self, request: Request) -> Response:
        serializer = EmployeeCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        employee = create_employee(
            data=validated_data,
            actor=request.user,
        )

        detail_employee = get_employee_by_id(employee.id)
        response_serializer = EmployeeDetailSerializer(detail_employee)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


# ==============================================================================
# 4. EMPLOYEE DETAIL, UPDATE & DELETE VIEW
# ==============================================================================


class EmployeeDetailView(APIView):
    """
    API Chi tiết, Cập nhật & Xóa mềm nhân viên (SRS 4.3.1, 4.3.3, 4.3.4, DEL-01).
    - GET: Xem đầy đủ hồ sơ nhân viên (404 nếu không tìm thấy hoặc đã xóa mềm).
    - PATCH: Cập nhật từng phần (yêu cầu bắt buộc row_version để kiểm soát OCC).
    - DELETE: Xóa mềm cả Nhân viên và Tài khoản liên kết, thu hồi tức thì session & remember token.
    Quyền hạn: MANAGER-only ([IsAuthenticated, IsManager]).
    """

    permission_classes = [IsAuthenticated, IsManager]

    def get_permissions(self) -> list[Any]:
        return [IsAuthenticated(), IsManager()]

    @extend_schema(
        operation_id="employees_retrieve",
        tags=["Employees"],
        summary="Xem chi tiết hồ sơ nhân viên (SRS 4.3.1)",
        description=(
            "Lấy thông tin chi tiết đầy đủ của nhân viên bao gồm: thông tin cá nhân, "
            "phân cấp hành chính 3 cấp (Tỉnh, Quận, Phường kèm ID và tên), "
            "chức vụ công việc, metadata tài khoản (id, role, is_active) và row_version. "
            "Nếu nhân viên không tồn tại hoặc đã bị xóa mềm, trả về 404 Not Found (PROP-4.3.3-P02). "
            "Tuyệt đối ZERO trường mật khẩu hoặc hash."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID định danh của nhân viên",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=EmployeeDetailSerializer,
                description="Lấy chi tiết hồ sơ nhân viên thành công",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính (MSG-4.1-M02)",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập (yêu cầu MANAGER - MSG-4.2-M01)",
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Nhân viên không tồn tại hoặc đã bị xóa (PROP-4.3.3-P02)",
            ),
        },
    )
    def get(self, request: Request, id: int) -> Response:
        employee = get_employee_by_id(id)
        serializer = EmployeeDetailSerializer(employee)
        return Response(serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="employees_partial_update",
        tags=["Employees"],
        summary="Cập nhật hồ sơ nhân viên (SRS 4.3.3)",
        description=(
            "Cập nhật từng phần thông tin nhân viên với kiểm soát tương tranh lạc quan OCC: "
            "1. Bắt buộc truyền row_version. Nếu lệch phiên bản, trả về ngay 409 Conflict (MSG-4.3.1-M03). "
            "2. Mã nhân viên (code) là bất biến - cấm chỉnh sửa. "
            "3. Thay đổi chức vụ (position_id) tự động suy diễn lại Account.role. "
            "4. Thay đổi trạng thái (status = INACTIVE) tự động cập nhật Account.is_active = False "
            "và thu hồi ngay lập tức toàn bộ phiên đăng nhập (Session) cùng Remember-Me tokens. "
            "5. Đổi email hoặc số điện thoại tự động đồng bộ sang Account liên kết. "
            "6. Cập nhật mật khẩu tùy chọn tuân thủ password policy và cập nhật hash Argon2. "
            "7. Kích hoạt các rào chắn DEL-01: cấm Quản lý tự vô hiệu hóa / tự giáng chức chính mình, "
            "cấm vô hiệu hóa / giáng chức Quản lý hoạt động cuối cùng (409 PROP-DEL-01-*)."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID định danh của nhân viên cần cập nhật",
            ),
        ],
        request=EmployeeUpdateSerializer,
        responses={
            200: OpenApiResponse(
                response=EmployeeDetailSerializer,
                description="Cập nhật thông tin nhân viên thành công (PROP-4.3.3-P01)",
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Dữ liệu đầu vào không hợp lệ hoặc mật khẩu yếu (Rule 04 / MSG-4.3.3-M01)",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính (MSG-4.1-M02)",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập (yêu cầu MANAGER - MSG-4.2-M01)",
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Nhân viên không tồn tại hoặc đã bị xóa (PROP-4.3.3-P02)",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description=(
                    "Xung đột tương tranh lạc quan (Stale row_version - MSG-4.3.1-M03), "
                    "trùng lặp CCCD/SĐT/Email (MSG-4.3.1-M05), "
                    "hoặc vi phạm rào chắn DEL-01 tự vô hiệu hóa / Quản lý cuối cùng (PROP-DEL-01-*)"
                ),
            ),
        },
    )
    def patch(self, request: Request, id: int) -> Response:
        serializer = EmployeeUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        updated_employee = update_employee(
            employee_id=id,
            data=validated_data,
            actor=request.user,
        )

        detail_employee = get_employee_by_id(updated_employee.id)
        response_serializer = EmployeeDetailSerializer(detail_employee)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @extend_schema(
        operation_id="employees_destroy",
        tags=["Employees"],
        summary="Xóa mềm nhân viên & tài khoản liên kết (SRS 4.3.4, DEL-01)",
        description=(
            "Xóa mềm nhân viên và tài khoản liên kết trong một transaction nguyên tử: "
            "1. Cập nhật deleted_at = CURRENT_TIMESTAMP, deleted_by = actor.id trên cả 2 bảng employee và account. "
            "2. Đặt account.is_active = False. "
            "3. Thu hồi ngay lập tức toàn bộ phiên làm việc (Session) và RememberToken của tài khoản bị xóa. "
            "4. Đón bắt các ngoại lệ từ trigger CSDL fn_guard_soft_delete_and_restore: "
            "chặn đứng tự xóa tài khoản của chính mình (409 PROP-DEL-01-SELF-EMP), "
            "chặn đứng xóa tài khoản Quản lý hoạt động cuối cùng (409 PROP-DEL-01-LAST-MGR-EMP). "
            "Trả về 200 OK với thông điệp nguyên văn 'Xóa thành công' (MSG-4.3.4-M01)."
        ),
        parameters=[
            OpenApiParameter(
                name="id",
                type=int,
                location=OpenApiParameter.PATH,
                required=True,
                description="ID định danh của nhân viên cần xóa mềm",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=EmployeeDeleteSuccessSerializer,
                description="Xóa thành công (MSG-4.3.4-M01)",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính (MSG-4.1-M02)",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập (yêu cầu MANAGER - MSG-4.2-M01)",
            ),
            404: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Nhân viên không tồn tại hoặc đã bị xóa trước đó (PROP-4.3.3-P02)",
            ),
            409: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Vi phạm rào chắn xóa mềm DEL-01 (tự xóa chính mình hoặc xóa Quản lý cuối cùng)",
            ),
        },
    )
    def delete(self, request: Request, id: int) -> Response:
        result = soft_delete_employee(
            employee_id=id,
            actor=request.user,
        )
        return Response(result, status=status.HTTP_200_OK)
