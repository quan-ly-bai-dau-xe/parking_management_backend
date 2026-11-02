"""
Vehicle search view and pagination for parking app.
GET /api/v1/parking/vehicle-search/
Provides multi-criteria vehicle search with Trigram GIN index (TL-41),
Zero N+1 batch hydration, deterministic ordering, and OpenAPI schema per Task 9.
"""

from typing import Any

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.messages import ALL_MESSAGES
from apps.core.permissions import IsEmployeeOrManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.parking.selectors.search import (
    hydrate_vehicle_search_results,
    search_vehicles_query,
)
from apps.parking.serializers.search import (
    VehicleSearchListResponseSerializer,
    VehicleSearchQuerySerializer,
)


class VehicleSearchPagination(PageNumberPagination):
    """
    Phân trang dành riêng cho Modal tìm xe (Task 9):
    - Mặc định: 20 mục / trang.
    - Tối đa: 50 mục / trang (max_page_size = 50).
    - Hỗ trợ tham số query: page, page_size.
    - Khi kết quả rỗng (count == 0): trả về message nguyên văn 'Không tìm thấy dữ liệu trùng khớp'.
    """

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50

    def get_paginated_response(self, data: list[dict[str, Any]]) -> Response:
        assert self.page is not None
        assert self.request is not None
        count = self.page.paginator.count
        message = None
        total_pages = self.page.paginator.num_pages if count > 0 else 0

        if count == 0:
            message = ALL_MESSAGES.get(
                "MSG-4.5.1-M01", "Không tìm thấy dữ liệu trùng khớp"
            )

        return Response(
            {
                "count": count,
                "total_pages": total_pages,
                "current_page": self.page.number,
                "page_size": self.get_page_size(self.request),
                "next": self.get_next_link(),
                "previous": self.get_previous_link(),
                "results": data,
                "message": message,
            }
        )


class VehicleSearchView(APIView):
    """
    API Tìm kiếm thông tin phương tiện đa tiêu chí (Modal tìm xe).
    Phục vụ tra cứu nhanh theo biển số, khách hàng, số điện thoại per Task 9 và SRS 4.5.1.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="parking_vehicle_search_list",
        tags=["Parking - Vehicle search"],
        summary="Tìm kiếm phương tiện đa tiêu chí (Modal tìm xe)",
        description=(
            "API tìm kiếm thông tin xe phục vụ 'Modal tìm xe' theo SRS 4.5.1 và Task 9.\n\n"
            "- **Tìm kiếm hợp nhất (`q`)**: Một ô tìm kiếm duy nhất khớp đồng thời trên họ tên khách hàng, "
            "số điện thoại, hoặc biển số xe.\n"
            "- **Tìm kiếm tường minh**: Hỗ trợ 3 tham số riêng biệt `customer_name`, `phone`, `license_plate` "
            "(kết hợp điều kiện `AND` khi cùng xuất hiện).\n"
            "- **Quy chuẩn độ dài**: Mọi từ khóa tìm kiếm phải có độ dài tối thiểu 2 ký tự sau khi cắt tỉa khoảng trắng (trim). "
            "Nếu nhỏ hơn 2 ký tự hoặc không có tiêu chí nào, trả về HTTP 400 Bad Request kèm mã lỗi `PROP-GEN-P01`.\n"
            "- **Chuẩn hóa dữ liệu**: Biển số xe được chuẩn hóa tự động theo logic `fn_normalize_license_plate` "
            "(bỏ khoảng trắng, dấu gạch ngang, dấu chấm); số điện thoại được chuẩn hóa đầu số `+84` tương đương `0`; "
            "họ tên khách hàng sử dụng toán tử `ILIKE` trực tiếp để kích hoạt chỉ mục Trigram GIN (`TL-41`). "
            "Mọi ký tự đặc biệt của LIKE (`%`, `_`, `\\`) đều được escape an toàn.\n"
            "- **Bảo mật & Quyền riêng tư**: Tự động lọc bỏ các bản ghi đã xóa mềm (`deleted_at IS NOT NULL`) và "
            "ẩn danh hóa thông tin PII nếu khách hàng có cờ `is_anonymized=True`.\n"
            "- **Trạng thái đỗ xe**: Mỗi kết quả trả về kèm cờ boolean `currently_parked` (`True` nếu xe đang có phiên đỗ mở tại bãi).\n"
            "- **Sắp xếp**: Kết quả được sắp xếp xác định, ưu tiên biển số khớp chính xác (`exact match`) lên đầu, "
            "sau đó sắp xếp theo biển số xe (`license_plate`).\n"
            "- **Kết quả rỗng**: Khi không tìm thấy bản ghi nào phù hợp, API trả về HTTP 200 kèm danh sách kết quả rỗng "
            "và thông điệp nguyên văn: 'Không tìm thấy dữ liệu trùng khớp' (`MSG-4.5.1-M01`)."
        ),
        parameters=[
            OpenApiParameter(
                name="q",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Từ khóa tìm kiếm hợp nhất (khớp họ tên khách hàng, số điện thoại, hoặc biển số xe; tối thiểu 2 ký tự)",
                examples=[
                    OpenApiExample("Tìm theo biển số xe", value="51K-992.14"),
                    OpenApiExample("Tìm theo họ tên", value="Nguyễn Văn An"),
                    OpenApiExample("Tìm theo số điện thoại", value="0912345678"),
                ],
            ),
            OpenApiParameter(
                name="customer_name",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Tìm kiếm theo họ tên khách hàng (khớp ILIKE với chỉ mục Trigram GIN; tối thiểu 2 ký tự)",
            ),
            OpenApiParameter(
                name="phone",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Tìm kiếm theo số điện thoại khách hàng (hỗ trợ quy đổi +84 và 0; tối thiểu 2 ký tự)",
            ),
            OpenApiParameter(
                name="license_plate",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Tìm kiếm theo biển số xe (chuẩn hóa tự động theo license_plate_norm; tối thiểu 2 ký tự)",
            ),
            OpenApiParameter(
                name="page",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Số thứ tự trang cần xem (mặc định: 1)",
            ),
            OpenApiParameter(
                name="page_size",
                type=int,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Số lượng bản ghi trên mỗi trang (mặc định: 20, tối đa: 50)",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=VehicleSearchListResponseSerializer,
                description="Tìm kiếm phương tiện thành công (có kết quả hoặc danh sách rỗng)",
                examples=[
                    OpenApiExample(
                        "Kết quả tìm kiếm có dữ liệu (q='Trịnh Xuân Trường')",
                        value={
                            "count": 2,
                            "total_pages": 1,
                            "current_page": 1,
                            "page_size": 20,
                            "next": None,
                            "previous": None,
                            "results": [
                                {
                                    "vehicle": {
                                        "id": 1,
                                        "code": "XE0001",
                                        "license_plate": "43K-860.50",
                                        "license_plate_norm": "43K86050",
                                        "model_name": "Vios 1.5G",
                                        "brand": "Toyota",
                                        "color": "Trắng",
                                        "vehicle_type": "Ô tô",
                                        "vehicle_type_code": "CAR",
                                    },
                                    "customer": {
                                        "id": 1,
                                        "code": "KH0001",
                                        "full_name": "Trịnh Xuân Trường",
                                        "phone": "0868851325",
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
                                    "open_session": {
                                        "id": 37,
                                        "session_code": "#PK-20261017-037",
                                        "entry_time": "2026-10-17T07:20:00+07:00",
                                        "entry_gate_name": "Cổng vào 1",
                                        "entry_image_url": "https://res.cloudinary.com/parking-cloud/image/upload/v1729152000/parking_scans/2026/10/17/a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6.jpg",
                                        "recognition_source": "AI",
                                        "ai_confidence": 97.10,
                                        "review_status": "MATCHED",
                                    },
                                    "is_blacklisted": False,
                                    "currently_parked": True,
                                },
                                {
                                    "vehicle": {
                                        "id": 11,
                                        "code": "XE0011",
                                        "license_plate": "92V-929.32",
                                        "license_plate_norm": "92V92932",
                                        "model_name": "Camry 2.5Q",
                                        "brand": "Toyota",
                                        "color": "Đen",
                                        "vehicle_type": "Ô tô",
                                        "vehicle_type_code": "CAR",
                                    },
                                    "customer": {
                                        "id": 1,
                                        "code": "KH0001",
                                        "full_name": "Trịnh Xuân Trường",
                                        "phone": "0868851325",
                                        "is_anonymized": False,
                                    },
                                    "parking_position": None,
                                    "active_ticket": None,
                                    "open_session": None,
                                    "is_blacklisted": False,
                                    "currently_parked": False,
                                },
                            ],
                            "message": None,
                        },
                    ),
                    OpenApiExample(
                        "Kết quả tìm kiếm không trùng khớp (q='Không tồn tại')",
                        value={
                            "count": 0,
                            "total_pages": 0,
                            "current_page": 1,
                            "page_size": 20,
                            "next": None,
                            "previous": None,
                            "results": [],
                            "message": "Không tìm thấy dữ liệu trùng khớp",
                        },
                    ),
                ],
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Từ khóa tìm kiếm không hợp lệ hoặc quá ngắn (< 2 ký tự sau khi cắt tỉa khoảng trắng)",
                examples=[
                    OpenApiExample(
                        "Từ khóa tìm kiếm quá ngắn (< 2 ký tự)",
                        value={
                            "code": "PROP-GEN-P01",
                            "message": "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu",
                            "details": {
                                "q": [
                                    "Từ khóa tìm kiếm phải có độ dài tối thiểu 2 ký tự sau khi loại bỏ khoảng trắng."
                                ]
                            },
                        },
                    ),
                    OpenApiExample(
                        "Thiếu tham số tìm kiếm",
                        value={
                            "code": "PROP-GEN-P01",
                            "message": "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu",
                            "details": {
                                "non_field_errors": [
                                    "Yêu cầu cung cấp ít nhất một tiêu chí tìm kiếm hợp lệ (q, customer_name, phone, license_plate)."
                                ]
                            },
                        },
                    ),
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực danh tính người dùng (Anonymous caller)",
                examples=[
                    OpenApiExample(
                        "Chưa xác thực",
                        value={
                            "code": "MSG-4.1-M02",
                            "message": "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu",
                            "details": {
                                "detail": "Authentication credentials were not provided."
                            },
                        },
                    )
                ],
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Người dùng không đủ thẩm quyền truy cập (vai trò CUSTOMER)",
                examples=[
                    OpenApiExample(
                        "Không đủ quyền hạn",
                        value={
                            "code": "MSG-4.2-M01",
                            "message": "Bạn không có quyền thực hiện thao tác này.",
                            "details": {
                                "detail": "Bạn không có quyền thực hiện thao tác này."
                            },
                        },
                    )
                ],
            ),
        },
    )
    def get(self, request: Request) -> Response:
        query_serializer = VehicleSearchQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

        qs = search_vehicles_query(query_serializer.validated_data)

        paginator = VehicleSearchPagination()
        page_vehicles = paginator.paginate_queryset(qs, request, view=self)
        if page_vehicles is not None:
            hydrated_data = hydrate_vehicle_search_results(page_vehicles)
            return paginator.get_paginated_response(hydrated_data)

        hydrated_data = hydrate_vehicle_search_results(list(qs))
        count = len(hydrated_data)
        message = (
            None
            if count > 0
            else ALL_MESSAGES.get("MSG-4.5.1-M01", "Không tìm thấy dữ liệu trùng khớp")
        )
        return Response(
            {
                "count": count,
                "total_pages": 1 if count > 0 else 0,
                "current_page": 1,
                "page_size": count,
                "next": None,
                "previous": None,
                "results": hydrated_data,
                "message": message,
            },
            status=status.HTTP_200_OK,
        )
