"""
Plate scan view for vehicle entry/exit license plate recognition.
POST /api/v1/parking/plate-scans/
"""

import json
import logging
import re
import time
import uuid
from typing import Any

from drf_spectacular.utils import OpenApiExample, OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import BusinessAPIException
from apps.core.logging import format_plate_for_log
from apps.core.messages import ALL_MESSAGES
from apps.core.permissions import IsEmployeeOrManager
from apps.core.serializers import ErrorEnvelopeSerializer
from apps.parking.selectors.vehicles import get_combined_vehicle_context
from apps.parking.serializers.scans import (
    PlateScanRequestSerializer,
    PlateScanResponseSerializer,
)
from apps.parking.services.ocr import get_plate_recognizer
from apps.parking.services.plate_scan import execute_plate_scan

logger = logging.getLogger(__name__)

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Vehicle lookup function used by execute_plate_scan; aliased for test patching. Tests patch apps.parking.views.scans.vehicle_lookup_func to simulate a DB failure.
vehicle_lookup_func = get_combined_vehicle_context


def resolve_request_id(request: Any) -> str:
    """Extract a validated X-Request-ID header or generate a correlation UUID."""
    raw_id = ""
    if hasattr(request, "headers"):
        raw_id = str(request.headers.get("X-Request-ID", "")).strip()
    elif hasattr(request, "META"):
        raw_id = str(request.META.get("HTTP_X_REQUEST_ID", "")).strip()
    if raw_id and _REQUEST_ID_RE.match(raw_id):
        return raw_id
    return uuid.uuid4().hex


def init_observability_context(request: Any) -> None:
    """Initialize per-request stage timing and correlation attributes."""
    request._obs_start = time.perf_counter()
    request._request_id = resolve_request_id(request)
    request._obs_stages = {
        "decode": 0.0,
        "detect": 0.0,
        "ocr1": 0.0,
        "ocr2": 0.0,
        "db": 0.0,
        "write": 0.0,
    }
    request._obs_review_status = None
    request._obs_review_reasons = []
    request._obs_plate = None


def set_observability_metadata(
    request: Any,
    *,
    review_status: str | None = None,
    review_reasons: list[str] | None = None,
    plate: str | None = None,
) -> None:
    """Record observability attributes on the request object."""
    if review_status is not None:
        request._obs_review_status = review_status
    if review_reasons is not None:
        request._obs_review_reasons = review_reasons
    if plate is not None:
        request._obs_plate = plate


def finalize_observability_response(
    request: Any, response: Response, endpoint_label: str
) -> Response:
    """Attach X-Request-ID and emit a structured single-line observability log record (Standard 6)."""
    req_id = getattr(request, "_request_id", None) or resolve_request_id(request)
    response["X-Request-ID"] = req_id
    t0 = getattr(request, "_obs_start", None)
    total_ms = round((time.perf_counter() - t0) * 1000.0, 2) if t0 is not None else 0.0
    stages = getattr(
        request,
        "_obs_stages",
        {
            "decode": 0.0,
            "detect": 0.0,
            "ocr1": 0.0,
            "ocr2": 0.0,
            "db": 0.0,
            "write": 0.0,
        },
    )
    user = getattr(request, "user", None)
    user_id = (
        user.pk
        if user is not None and getattr(user, "is_authenticated", False)
        else None
    )
    record = {
        "event": "parking_api_request",
        "request_id": req_id,
        "endpoint": getattr(request, "path", endpoint_label),
        "status": response.status_code,
        "total_ms": total_ms,
        "stage_timings_ms": {k: round(float(v), 2) for k, v in stages.items()},
        "user_id": user_id,
        "review_status": getattr(request, "_obs_review_status", None),
        "review_reasons": getattr(request, "_obs_review_reasons", []),
        "plate": format_plate_for_log(getattr(request, "_obs_plate", None)),
    }
    logger.info(json.dumps(record, ensure_ascii=False))
    return response


class PlateScanView(APIView):
    """
    Plate scan endpoint for vehicle entry/exit camera frames or uploaded images.
    Delegates OCR inference and review policy evaluation to execute_plate_scan service.
    """

    permission_classes = [IsAuthenticated, IsEmployeeOrManager]
    parser_classes = [MultiPartParser, FormParser]

    def initial(self, request: Request, *args: Any, **kwargs: Any) -> None:
        init_observability_context(request)
        super().initial(request, *args, **kwargs)

    def finalize_response(
        self, request: Request, response: Response, *args: Any, **kwargs: Any
    ) -> Response:
        resp = super().finalize_response(request, response, *args, **kwargs)
        return finalize_observability_response(
            request, resp, "/api/v1/parking/plate-scans/"
        )

    def handle_exception(self, exc: Exception) -> Response:
        """
        Handle UnsupportedMediaType when client sends form without image or invalid multipart data.
        Normalizes to HTTP 400 Bad Request with error code PROP-4.5.1-P02.
        """
        if not hasattr(self.request, "_request_id"):
            init_observability_context(self.request)
        if isinstance(exc, exceptions.UnsupportedMediaType):
            exc = BusinessAPIException(
                code="PROP-4.5.1-P02",
                message=ALL_MESSAGES.get(
                    "PROP-4.5.1-P02",
                    "Tệp hình ảnh biển số xe không được để trống.",
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        return super().handle_exception(exc)

    @extend_schema(
        operation_id="parking_plate_scans_create",
        tags=["Parking - Vehicle entry/exit"],
        summary="Quét nhận diện biển số xe từ tệp hình ảnh",
        description=(
            "Nhận tệp hình ảnh từ camera barrier hoặc upload qua multipart/form-data, "
            "kiểm tra an toàn upload (dung lượng <= 5MB, magic bytes, Pillow integrity, "
            "tước bỏ EXIF/GPS, chống decompression bomb), sau đó chạy mô hình AI Dual-OCR offline "
            "để trích xuất danh sách biển số xe kèm per-character confidence, áp dụng quy tắc vị trí (A3), "
            "đánh giá chính sách duyệt AUTO/NEEDS_REVIEW (A2) và tự động tra cứu phương tiện."
        ),
        request=PlateScanRequestSerializer,
        examples=[
            OpenApiExample(
                "Upload hình ảnh quét biển số xe",
                value={
                    "image": "camera_front_plate.jpg",
                    "gate_id": 1,
                },
                request_only=True,
                media_type="multipart/form-data",
            )
        ],
        responses={
            200: OpenApiResponse(
                response=PlateScanResponseSerializer,
                description="Nhận diện thành công biển số xe",
                examples=[
                    OpenApiExample(
                        "Quét thành công biển số 51K-992.14 (Trạng thái AUTO)",
                        value={
                            "plate_raw": "51K-992.14",
                            "plate_final": "51K99214",
                            "candidates": [
                                {
                                    "plate_text": "51K-992.14",
                                    "plate_normalized": "51K99214",
                                    "confidence": 98.50,
                                    "char_confidences": [
                                        99.1,
                                        98.8,
                                        99.5,
                                        97.9,
                                        98.4,
                                        98.0,
                                        99.2,
                                        98.7,
                                    ],
                                    "min_char_confidence": 97.90,
                                    "bounding_box": {
                                        "x1": 120,
                                        "y1": 340,
                                        "x2": 450,
                                        "y2": 440,
                                    },
                                }
                            ],
                            "best_candidate": {
                                "plate_text": "51K-992.14",
                                "plate_normalized": "51K99214",
                                "confidence": 98.50,
                                "char_confidences": [
                                    99.1,
                                    98.8,
                                    99.5,
                                    97.9,
                                    98.4,
                                    98.0,
                                    99.2,
                                    98.7,
                                ],
                                "min_char_confidence": 97.90,
                                "bounding_box": {
                                    "x1": 120,
                                    "y1": 340,
                                    "x2": 450,
                                    "y2": 440,
                                },
                            },
                            "image_url": "/media/parking_scans/2026/10/18/f3e1a8b2c4d5.jpg",
                            "vehicle_lookup": {
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
                            "is_blacklisted": False,
                            "open_session": None,
                            "engine_name": "dual_ensemble",
                            "latency_ms": 45.2,
                            "review_status": "AUTO",
                            "review_reasons": [],
                            "corrections": [],
                            "suggestions": [],
                        },
                    ),
                    OpenApiExample(
                        "Quét có nghi vấn sửa ký tự (Trạng thái NEEDS_REVIEW)",
                        value={
                            "plate_raw": "5DZ-1630",
                            "plate_final": "50Z1630",
                            "candidates": [
                                {
                                    "plate_text": "5DZ-1630",
                                    "plate_normalized": "5DZ1630",
                                    "confidence": 88.20,
                                    "char_confidences": [
                                        95.0,
                                        72.0,
                                        94.0,
                                        92.0,
                                        90.0,
                                        89.0,
                                        91.0,
                                    ],
                                    "min_char_confidence": 72.00,
                                    "bounding_box": {
                                        "x1": 100,
                                        "y1": 200,
                                        "x2": 350,
                                        "y2": 300,
                                    },
                                }
                            ],
                            "best_candidate": {
                                "plate_text": "50Z-1630",
                                "plate_normalized": "50Z1630",
                                "confidence": 88.20,
                                "char_confidences": [
                                    95.0,
                                    72.0,
                                    94.0,
                                    92.0,
                                    90.0,
                                    89.0,
                                    91.0,
                                ],
                                "min_char_confidence": 72.00,
                                "bounding_box": {
                                    "x1": 100,
                                    "y1": 200,
                                    "x2": 350,
                                    "y2": 300,
                                },
                            },
                            "image_url": "/media/parking_scans/2026/10/18/a1b2c3d4e5f6.jpg",
                            "vehicle_lookup": None,
                            "is_blacklisted": False,
                            "open_session": None,
                            "engine_name": "dual_ensemble",
                            "latency_ms": 48.0,
                            "review_status": "NEEDS_REVIEW",
                            "review_reasons": [
                                "LOW_CHAR_CONFIDENCE",
                                "POSITION_CORRECTED",
                            ],
                            "corrections": [
                                {
                                    "position": 1,
                                    "from": "D",
                                    "to": "0",
                                    "rule": "province_second_digit_fix",
                                    "reason": "Positional grammar requires digit at position 1; corrected 'D' to '0'",
                                    "original_char": "D",
                                    "corrected_char": "0",
                                }
                            ],
                            "suggestions": ["50Z-1630", "50Z-1631"],
                        },
                    ),
                ],
            ),
            400: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Lỗi tải lên tệp ảnh (thiếu file, quá dung lượng, định dạng không hỗ trợ, hoặc ảnh hỏng)",
                examples=[
                    OpenApiExample(
                        "File ảnh quá 5MB",
                        value={
                            "code": "PROP-4.5.1-P03",
                            "message": "Kích thước tệp hình ảnh vượt quá giới hạn cho phép.",
                            "details": {},
                        },
                    ),
                    OpenApiExample(
                        "Định dạng không hỗ trợ",
                        value={
                            "code": "PROP-4.5.1-P04",
                            "message": "Định dạng tệp hình ảnh không được hỗ trợ.",
                            "details": {},
                        },
                    ),
                ],
            ),
            401: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Chưa đăng nhập hoặc phiên làm việc đã hết hạn",
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
                description="Không có quyền truy cập (yêu cầu vai trò EMPLOYEE hoặc MANAGER)",
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
            422: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Không nhận diện được biển số xe trong hình ảnh",
                examples=[
                    OpenApiExample(
                        "Không phát hiện biển số",
                        value={
                            "code": "PROP-4.5.1-P06",
                            "message": "Không nhận diện được biển số xe từ hình ảnh đã cung cấp.",
                            "details": {},
                        },
                    )
                ],
            ),
            503: OpenApiResponse(
                response=ErrorEnvelopeSerializer,
                description="Hệ thống nhận diện biển số xe đang quá tải (Back-pressure)",
                examples=[
                    OpenApiExample(
                        "Hệ thống quá tải",
                        value={
                            "code": "PROP-4.5.1-P15",
                            "message": "Hệ thống nhận diện biển số xe đang quá tải, vui lòng thử lại sau.",
                            "details": {},
                        },
                    )
                ],
            ),
        },
    )
    def post(self, request: Request) -> Response:
        image_file = request.FILES.get("image")
        if not image_file:
            raise BusinessAPIException(
                code="PROP-4.5.1-P02",
                message=ALL_MESSAGES.get(
                    "PROP-4.5.1-P02",
                    "Tệp hình ảnh biển số xe không được để trống.",
                ),
                status_code=status.HTTP_400_BAD_REQUEST,
            )

        stages: dict[str, float] = getattr(request, "_obs_stages", {})
        result = execute_plate_scan(
            image_file=image_file,
            stages=stages,
            recognizer=get_plate_recognizer(),
            lookup_func=vehicle_lookup_func,
        )

        set_observability_metadata(
            request,
            review_status=result.review_status,
            review_reasons=result.review_reasons,
            plate=result.plate_normalized,
        )

        return Response(result.payload, status=status.HTTP_200_OK)
