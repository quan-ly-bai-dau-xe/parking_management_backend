"""
Vehicle lookup view for parking app.
GET /api/v1/parking/vehicle-lookup/
"""

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
from apps.core.permissions import IsEmployeeOrManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.parking.selectors.vehicles import get_combined_vehicle_context
from apps.parking.serializers.lookup import VehicleLookupResponseSerializer


class VehicleLookupView(APIView):
    """
    API Tra cứu thông tin phương tiện chính xác theo biển số đã chuẩn hóa.
    Phục vụ tự động điền (auto-fill) màn hình barrier xe vào/ra theo SRS 4.5.1.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="parking_vehicle_lookup_retrieve",
        tags=["Parking - Vehicle entry/exit"],
        summary="Tra cứu chi tiết phương tiện chính xác theo biển số",
        description=(
            "Tra cứu phương tiện dựa trên biển số xe (chuẩn hóa tự động theo logic "
            "fn_normalize_license_plate, bỏ qua ký tự phân cách, dấu chấm, dấu gạch ngang, "
            "không phân biệt chữ hoa/thường). Trả về thông tin xe, chủ xe (ẩn danh nếu có yêu cầu "
            "bảo vệ PII), vị trí đỗ hiện tại, vé đỗ xe còn hạn, và cờ danh sách đen. "
            "Nếu không tìm thấy phương tiện đăng ký -> trả về HTTP 404 với thông điệp MSG-4.5.1-M01."
        ),
        parameters=[
            OpenApiParameter(
                name="license_plate",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Biển số xe cần tra cứu (vd: 51K-992.14 hoặc 51K99214)",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=VehicleLookupResponseSerializer,
                description="Tìm thấy phương tiện và trả về thông tin chi tiết",
                examples=[
                    OpenApiExample(
                        "Tra cứu thành công xe Camry 51K-992.14",
                        value={
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
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Thiếu hoặc sai định dạng tham số biển số xe",
                examples=[
                    OpenApiExample(
                        "Thiếu tham số biển số",
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
                description="Chưa đăng nhập",
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
                description="Không tìm thấy phương tiện trùng khớp (MSG-4.5.1-M01)",
                examples=[
                    OpenApiExample(
                        "Không tìm thấy phương tiện",
                        value={
                            "code": "MSG-4.5.1-M01",
                            "message": "Không tìm thấy dữ liệu trùng khớp",
                            "details": {},
                        },
                    ),
                    OpenApiExample(
                        "Không tìm thấy nhưng bị Blacklist",
                        value={
                            "code": "MSG-4.5.1-M01",
                            "message": "Không tìm thấy dữ liệu trùng khớp",
                            "details": {"is_blacklisted": True},
                        },
                    ),
                ],
            ),
        },
    )
    def get(self, request: Request) -> Response:
        plate = request.query_params.get("license_plate")
        if not plate or not str(plate).strip():
            raise BusinessAPIException(
                code="PROP-4.5.1-P01",
                message=ALL_MESSAGES.get(
                    "PROP-4.5.1-P01", "Định dạng biển số xe không hợp lệ."
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        context = get_combined_vehicle_context(str(plate).strip())
        if not context.vehicle:
            details = {"is_blacklisted": True} if context.is_blacklisted else {}
            raise BusinessAPIException(
                code="MSG-4.5.1-M01",
                message=ALL_MESSAGES.get(
                    "MSG-4.5.1-M01", "Không tìm thấy dữ liệu trùng khớp"
                ),
                status_code=status.HTTP_404_NOT_FOUND,
                details=details,
            )

        data = context.to_lookup_dict()
        return Response(data, status=status.HTTP_200_OK)
