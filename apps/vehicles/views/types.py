"""
Views for vehicle types.
Provides vehicle type list endpoint for filter dropdowns.
"""

from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsEmployeeOrManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.vehicles.selectors.types import get_vehicle_types
from apps.vehicles.serializers.types import VehicleTypeSerializer


class VehicleTypeListView(APIView):
    """
    API Danh mục loại phương tiện (chỉ dành cho Ô tô và Xe điện).
    Phục vụ dropdown bộ lọc danh sách phương tiện theo quy định Car-only (TRC-FE-04-04).
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="vehicles_vehicle_types_list",
        tags=["Vehicles - Types"],
        summary="Lấy danh mục loại phương tiện",
        description=(
            "Lấy danh sách loại phương tiện đang hoạt động phục vụ lựa chọn trên bộ lọc "
            "(chỉ hỗ trợ loại xe Ô tô 'CAR' và Xe điện 'EV' per SRS v4.1, TL-09, TL-20, TL-35, OQ-49)."
        ),
        responses={
            200: OpenApiResponse(
                response=VehicleTypeSerializer(many=True),
                description="Danh sách loại phương tiện hợp lệ",
                examples=[
                    OpenApiExample(
                        "Danh mục loại xe ô tô",
                        value=[
                            {
                                "id": 1,
                                "code": "CAR",
                                "name": "Ô tô",
                                "description": "Ô tô động cơ đốt trong",
                            },
                            {
                                "id": 2,
                                "code": "EV",
                                "name": "Xe điện",
                                "description": "Phương tiện thuần điện",
                            },
                        ],
                    )
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa đăng nhập",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        queryset = get_vehicle_types()
        serializer = VehicleTypeSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
