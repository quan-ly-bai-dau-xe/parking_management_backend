"""
Health check endpoint for Parking Management Backend per TL-47.
"""

import logging

from django.db import connection
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.parking.services.ocr import is_ocr_ready

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """
    Kiểm tra trạng thái sẵn sàng của hệ thống và kết nối cơ sở dữ liệu PostgreSQL.
    Bổ sung cờ ocr_ready kiểm tra trạng thái mô hình OCR.
    """

    permission_classes = [AllowAny]

    @extend_schema(
        responses={
            200: OpenApiResponse(
                description="Hệ thống và cơ sở dữ liệu hoạt động bình thường"
            ),
            503: OpenApiResponse(description="Không thể kết nối tới cơ sở dữ liệu"),
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
