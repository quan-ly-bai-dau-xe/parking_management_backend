"""
Views for administrative boundary units (provinces, districts, wards).
Provides read-only dropdown endpoints for EMPLOYEE and MANAGER.
"""

from __future__ import annotations

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
from apps.core.selectors.administrative import (
    list_districts,
    list_provinces,
    list_wards,
)
from apps.core.serializers.administrative import (
    AdministrativeDistrictSerializer,
    AdministrativeProvinceSerializer,
    AdministrativeWardSerializer,
    DistrictFilterQuerySerializer,
    WardFilterQuerySerializer,
)
from apps.core.serializers.envelope import ErrorEnvelopeSerializer


class ProvinceListView(APIView):
    """
    API Danh mục Tỉnh / Thành phố trực thuộc trung ương.
    Phục vụ dropdown lựa chọn cấp Tỉnh trên màn hình Nhân viên và Khách hàng.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="administrative_provinces_list",
        tags=["Administrative - Units"],
        summary="Lấy danh mục Tỉnh / Thành phố",
        description=(
            "Lấy danh sách toàn bộ Tỉnh/Thành phố trực thuộc trung ương phục vụ dropdown "
            "khu vực hành chính (bảng danh mục bất biến, không phân trang, sắp xếp theo ID tăng dần)."
        ),
        responses={
            200: OpenApiResponse(
                response=AdministrativeProvinceSerializer(many=True),
                description="Danh sách Tỉnh/Thành phố hợp lệ",
                examples=[
                    OpenApiExample(
                        "Danh sách Tỉnh Thành",
                        value=[
                            {"id": 1, "code": "49", "name": "Tỉnh Quảng Nam"},
                            {"id": 2, "code": "48", "name": "Thành phố Đà Nẵng"},
                        ],
                    )
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực (chưa đăng nhập)",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập (vai trò CUSTOMER)",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        provinces = list_provinces()
        serializer = AdministrativeProvinceSerializer(provinces, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class DistrictListView(APIView):
    """
    API Danh mục Quận / Huyện / Thị xã.
    Phục vụ dropdown lựa chọn cấp Huyện lọc theo Tỉnh đã chọn.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="administrative_districts_list",
        tags=["Administrative - Units"],
        summary="Lấy danh mục Quận / Huyện",
        description=(
            "Lấy danh sách Quận/Huyện/Thị xã thuộc Tỉnh/Thành phố theo query parameter `province_id` "
            "phục vụ dropdown liên hoàn (không phân trang, sắp xếp theo ID tăng dần)."
        ),
        parameters=[DistrictFilterQuerySerializer],
        responses={
            200: OpenApiResponse(
                response=AdministrativeDistrictSerializer(many=True),
                description="Danh sách Quận/Huyện hợp lệ",
                examples=[
                    OpenApiExample(
                        "Danh sách Quận Huyện",
                        value=[
                            {"id": 1, "code": "DB", "name": "Thị xã Điện Bàn"},
                        ],
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Tham số province_id bị thiếu hoặc không đúng định dạng số nguyên dương",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực (chưa đăng nhập)",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập (vai trò CUSTOMER)",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        query_serializer = DistrictFilterQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        province_id = query_serializer.validated_data["province_id"]

        districts = list_districts(province_id=province_id)
        serializer = AdministrativeDistrictSerializer(districts, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class WardListView(APIView):
    """
    API Danh mục Xã / Phường / Thị trấn.
    Phục vụ dropdown lựa chọn cấp Xã lọc theo Huyện đã chọn.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]

    @extend_schema(
        operation_id="administrative_wards_list",
        tags=["Administrative - Units"],
        summary="Lấy danh mục Phường / Xã",
        description=(
            "Lấy danh sách Xã/Phường/Thị trấn thuộc Quận/Huyện theo query parameter `district_id` "
            "phục vụ dropdown liên hoàn (không phân trang, sắp xếp theo ID tăng dần)."
        ),
        parameters=[WardFilterQuerySerializer],
        responses={
            200: OpenApiResponse(
                response=AdministrativeWardSerializer(many=True),
                description="Danh sách Phường/Xã hợp lệ",
                examples=[
                    OpenApiExample(
                        "Danh sách Phường Xã",
                        value=[
                            {"id": 1, "code": "DN", "name": "Phường Điện Ngọc"},
                        ],
                    )
                ],
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Tham số district_id bị thiếu hoặc không đúng định dạng số nguyên dương",
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa xác thực (chưa đăng nhập)",
            ),
            403: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không đủ quyền truy cập (vai trò CUSTOMER)",
            ),
        },
    )
    def get(self, request: Request) -> Response:
        query_serializer = WardFilterQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        district_id = query_serializer.validated_data["district_id"]

        wards = list_wards(district_id=district_id)
        serializer = AdministrativeWardSerializer(wards, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
