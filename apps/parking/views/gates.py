"""
Gate views for parking app.
GET /api/v1/parking/gates/
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

from apps.core.permissions import IsEmployeeOrManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.parking.selectors.gates import get_gates
from apps.parking.serializers.gates import ParkingGateSerializer


class GateListView(APIView):
    """
    API Danh sách cổng kiểm soát barrier xe vào/ra.
    Phục vụ giao diện lựa chọn cổng quét biển số và kiểm soát lưu thông.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="parking_gates_list",
        tags=["Parking - Vehicle entry/exit"],
        summary="Lấy danh sách các cổng kiểm soát barrier",
        description=(
            "Truy vấn danh sách toàn bộ các cổng barrier (ParkingGate) trong bãi xe, "
            "hỗ trợ lọc theo hướng di chuyển (direction: IN hoặc OUT) và trạng thái hoạt động (is_active)."
        ),
        parameters=[
            OpenApiParameter(
                name="direction",
                type=str,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo hướng cổng: 'IN' (cổng vào) hoặc 'OUT' (cổng ra)",
            ),
            OpenApiParameter(
                name="is_active",
                type=bool,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Lọc theo trạng thái hoạt động: true hoặc false",
            ),
        ],
        responses={
            200: OpenApiResponse(
                response=ParkingGateSerializer(many=True),
                description="Danh sách cổng kiểm soát hợp lệ",
                examples=[
                    OpenApiExample(
                        "Danh sách cổng mẫu",
                        value=[
                            {
                                "id": 1,
                                "lot_id": 1,
                                "code": "IN_01",
                                "name": "Cổng vào 1",
                                "direction": "IN",
                                "camera_status": "ONLINE",
                                "is_auto_scan": True,
                                "is_active": True,
                            },
                            {
                                "id": 2,
                                "lot_id": 1,
                                "code": "OUT_01",
                                "name": "Cổng ra 1",
                                "direction": "OUT",
                                "camera_status": "ONLINE",
                                "is_auto_scan": True,
                                "is_active": True,
                            },
                        ],
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
        direction = request.query_params.get("direction")
        is_active_param = request.query_params.get("is_active")

        is_active: bool | None = None
        if is_active_param is not None:
            is_active = is_active_param.lower() in ("true", "1")

        gates = get_gates(direction=direction, is_active=is_active)
        serializer = ParkingGateSerializer(gates, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
