"""
Health check endpoint for Parking Management Backend per TL-47.
"""

import logging

from django.db import connection
from drf_spectacular.utils import (
    OpenApiExample,
    OpenApiResponse,
    extend_schema,
    inline_serializer,
)
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.parking.services.ocr import is_ocr_ready

logger = logging.getLogger(__name__)

HealthCheckResponseSerializer = inline_serializer(
    name="HealthCheckResponse",
    fields={
        "status": serializers.CharField(
            help_text="Trạng thái hệ thống: healthy hoặc unhealthy"
        ),
        "database": serializers.CharField(
            help_text="Trạng thái kết nối CSDL: connected hoặc disconnected"
        ),
        "ocr_ready": serializers.BooleanField(
            help_text="Trạng thái sẵn sàng của mô hình OCR"
        ),
    },
)


class HealthCheckView(APIView):
    """
    Kiểm tra trạng thái sẵn sàng của hệ thống và kết nối cơ sở dữ liệu PostgreSQL.
    Bổ sung cờ ocr_ready kiểm tra trạng thái mô hình OCR.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        summary="Kiểm tra trạng thái sẵn sàng của hệ thống",
        description=(
            "Kiểm tra trạng thái sẵn sàng của hệ thống, kết nối cơ sở dữ liệu PostgreSQL và mô hình OCR.\n"
            "Cả hai đường dẫn `/api/health/` (hạ tầng hệ thống) và `/api/v1/health/` (API v1) "
            "đều được cung cấp có chủ đích để tương thích với các bộ kiểm tra sức khỏe hạ tầng "
            "(Docker/K8s/reverse proxy) và định tuyến phiên bản của frontend."
        ),
        responses={
            200: OpenApiResponse(
                response=HealthCheckResponseSerializer,
                description="Hệ thống và cơ sở dữ liệu hoạt động bình thường",
                examples=[
                    OpenApiExample(
                        "Hệ thống hoạt động bình thường",
                        value={
                            "status": "healthy",
                            "database": "connected",
                            "ocr_ready": True,
                        },
                        response_only=True,
                        status_codes=["200"],
                    )
                ],
            ),
            503: OpenApiResponse(
                response=HealthCheckResponseSerializer,
                description="Không thể kết nối tới cơ sở dữ liệu",
                examples=[
                    OpenApiExample(
                        "Hệ thống mất kết nối CSDL",
                        value={
                            "status": "unhealthy",
                            "database": "disconnected",
                            "ocr_ready": False,
                        },
                        response_only=True,
                        status_codes=["503"],
                    )
                ],
            ),
        },
        tags=["System"],
    )
    def get(self, request: Request) -> Response:
        ocr_status = is_ocr_ready()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
            return Response(
                {
                    "status": "healthy",
                    "database": "connected",
                    "ocr_ready": ocr_status,
                },
                status=status.HTTP_200_OK,
            )
        except Exception:
            logger.exception("Database health check probe failed")
            return Response(
                {
                    "status": "unhealthy",
                    "database": "disconnected",
                    "ocr_ready": ocr_status,
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
