"""
Plate scan business domain service module (H6 contract, J5 DRY refactoring).
Encapsulates plate scan execution, image safety validation, OCR concurrency gating,
disk persistence with rollback, position-aware corrections, review policy evaluation,
vehicle context lookup, trigram suggestions, and canonical response payload composition.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from django.conf import settings
from rest_framework import status

from apps.core.concurrency import get_ocr_concurrency_gate
from apps.core.exceptions import BusinessAPIException
from apps.core.messages import ALL_MESSAGES
from apps.parking.data.vn_plate_rules import classify_plate_syntax
from apps.parking.selectors.vehicles import get_combined_vehicle_context
from apps.parking.services.ocr import (
    DummyPlateRecognizer,
    PlateRecognizer,
    PlateScanResult,
    get_plate_recognizer,
)
from apps.parking.services.plate_correction import (
    correct_plate_characters,
    evaluate_review_policy,
    get_plate_suggestions,
)
from apps.parking.services.upload import (
    process_uploaded_image,
    save_processed_image,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PlateScanExecutionResult:
    """Result context containing response payload and observability metadata."""

    payload: dict[str, Any]
    review_status: str
    review_reasons: list[str]
    plate_normalized: str
    saved_file_path: Path | None = None


def compose_scan_contract_payload(
    scan_result: PlateScanResult,
    image_relative_url: str,
    vehicle_lookup_data: dict[str, Any] | None,
    is_blacklisted: bool,
    open_session_data: dict[str, Any] | None,
    threshold: float | None = None,
    preset_review: tuple[str, list[str]] | None = None,
) -> dict[str, Any]:
    """
    Produce the canonical H6 scan response contract payload:
    - plate_raw: exact OCR reading
    - plate_final: post-correction proposal (used for lookup, suggestions, and review)
    - best_candidate: synchronized with plate_final for full backward compatibility
    - corrections: list of {position, from, to, rule, reason, original_char, corrected_char}
    - review_status & review_reasons
    - suggestions: up to 3 candidate plates
    """
    eff_threshold = (
        threshold
        if threshold is not None
        else float(settings.PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD)
    )
    best_cand = scan_result.best_candidate
    if not best_cand:
        raw_text = ""
        raw_norm = ""
    else:
        raw_text = best_cand.plate_text
        raw_norm = best_cand.plate_normalized

    # Position-aware character correction
    corrected_plate, corrections = correct_plate_characters(raw_text)
    final_norm_plate = (
        PlateRecognizer.normalize_plate(corrected_plate)
        if corrected_plate
        else raw_norm
    )

    # Syntax classification
    syntax_status, _ = classify_plate_syntax(final_norm_plate)
    is_format_valid = syntax_status == "VALID"
    is_unknown_pattern = syntax_status == "UNKNOWN_PLATE_PATTERN"

    min_conf = (
        best_cand.min_char_confidence
        if best_cand and best_cand.min_char_confidence is not None
        else (best_cand.confidence if best_cand else 0.0)
    )

    aspect_ratio = None
    if best_cand and best_cand.bounding_box:
        bb = best_cand.bounding_box
        w = abs(bb.x2 - bb.x1)
        h = abs(bb.y2 - bb.y1)
        if h > 0:
            aspect_ratio = w / h

    if preset_review is not None:
        review_status, review_reasons = preset_review
    else:
        review_status, review_reasons = evaluate_review_policy(
            model_agreement=scan_result.model_agreement,
            min_char_confidence=min_conf,
            threshold=eff_threshold,
            is_valid_format=is_format_valid,
            used_detection_fallback=scan_result.used_detection_fallback,
            is_unknown_pattern=is_unknown_pattern,
            plate_aspect_ratio=aspect_ratio,
            corrections=corrections,
            min_detector_box_confidence=float(
                settings.PARKING_REVIEW_DETECTOR_CONF_THRESHOLD
            ),
            min_aspect_ratio=float(settings.PARKING_REVIEW_MIN_ASPECT_RATIO),
            max_aspect_ratio=float(settings.PARKING_REVIEW_MAX_ASPECT_RATIO),
            min_sharpness=float(settings.PARKING_REVIEW_MIN_SHARPNESS),
        )

    suggestions: list[str] = []
    if review_status == "NEEDS_REVIEW" or vehicle_lookup_data is None:
        suggestions = get_plate_suggestions(final_norm_plate, limit=3)

    best_candidate_dict = None
    if best_cand:
        best_candidate_dict = best_cand.to_dict()
        best_candidate_dict["plate_text"] = (
            corrected_plate if corrected_plate else raw_text
        )
        best_candidate_dict["plate_normalized"] = final_norm_plate

    return {
        "plate_raw": raw_text,
        "plate_final": final_norm_plate,
        "candidates": [c.to_dict() for c in scan_result.candidates],
        "best_candidate": best_candidate_dict,
        "image_url": image_relative_url,
        "vehicle_lookup": vehicle_lookup_data,
        "is_blacklisted": is_blacklisted,
        "open_session": open_session_data,
        "engine_name": scan_result.engine_name,
        "latency_ms": scan_result.latency_ms,
        "review_status": review_status,
        "review_reasons": review_reasons,
        "corrections": [c.to_dict() for c in corrections],
        "suggestions": suggestions,
    }


def execute_plate_scan(
    image_file: Any,
    *,
    recognizer: PlateRecognizer | DummyPlateRecognizer | None = None,
    concurrency_gate: Any | None = None,
    lookup_func: Callable[[str], Any] | None = None,
    stages: dict[str, float] | None = None,
    threshold: float | None = None,
) -> PlateScanExecutionResult:
    """
    Orchestrate end-to-end plate scan execution:
    1. Image decode & safety validation (process_uploaded_image).
    2. Concurrency-gated OCR inference (get_plate_recognizer).
    3. Candidate presence validation (PROP-4.5.1-P06 on empty candidates).
    4. Disk persistence with defensive unlink on exception (save_processed_image).
    5. Combined vehicle context lookup (get_combined_vehicle_context).
    6. Canonical contract payload composition (compose_scan_contract_payload).
    7. Observability timing collection across decode, detect, ocr1, ocr2, write, db.
    """
    # 1. Image decode & safety validation
    t_dec0 = time.perf_counter()
    processed_image = process_uploaded_image(image_file)
    if stages is not None:
        stages["decode"] = (time.perf_counter() - t_dec0) * 1000.0

    # 2. Concurrency-gated OCR inference
    rec = recognizer if recognizer is not None else get_plate_recognizer()
    gate = (
        concurrency_gate if concurrency_gate is not None else get_ocr_concurrency_gate()
    )
    with gate.acquire():
        if isinstance(rec, DummyPlateRecognizer):
            scan_result = rec.recognize(processed_image.image_bytes)
        else:
            scan_result = rec.recognize(processed_image.pil_image)

    if stages is not None:
        stages["detect"] = float(getattr(scan_result, "detect_ms", 0.0))
        stages["ocr1"] = float(getattr(scan_result, "ocr1_ms", 0.0))
        stages["ocr2"] = float(getattr(scan_result, "ocr2_ms", 0.0))

    # 3. Candidate validation
    if not scan_result.candidates or not scan_result.best_candidate:
        raise BusinessAPIException(
            code="PROP-4.5.1-P06",
            message=ALL_MESSAGES.get(
                "PROP-4.5.1-P06",
                "Không nhận diện được biển số xe từ hình ảnh đã cung cấp.",
            ),
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )

    # 4. Save processed image to Cloudinary (with compensating destroy rollback on failure)
    relative_url: str | None = None
    try:
        t_wr0 = time.perf_counter()
        _, relative_url = save_processed_image(processed_image)
        if stages is not None:
            stages["write"] = (time.perf_counter() - t_wr0) * 1000.0

        best_cand = scan_result.best_candidate
        raw_text = best_cand.plate_text
        raw_norm = best_cand.plate_normalized

        corrected_plate, _ = correct_plate_characters(raw_text)
        final_norm_plate = (
            PlateRecognizer.normalize_plate(corrected_plate)
            if corrected_plate
            else raw_norm
        )

        # 5. Database lookup for vehicle context
        t_db0 = time.perf_counter()
        lookup = (
            lookup_func if lookup_func is not None else get_combined_vehicle_context
        )
        context = lookup(final_norm_plate)
        vehicle_lookup_data = context.to_lookup_dict()
        is_blacklisted = context.is_blacklisted
        open_session_data = context.open_session_data
        if stages is not None:
            stages["db"] = (time.perf_counter() - t_db0) * 1000.0

        # 6. Test double preset handling
        preset_review: tuple[str, list[str]] | None = None
        if getattr(rec, "preset_result", None) is not None:
            preset_review = (
                scan_result.review_status,
                scan_result.review_reasons,
            )

        # 7. Compose canonical response payload
        payload = compose_scan_contract_payload(
            scan_result=scan_result,
            image_relative_url=relative_url,
            vehicle_lookup_data=vehicle_lookup_data,
            is_blacklisted=is_blacklisted,
            open_session_data=open_session_data,
            threshold=threshold,
            preset_review=preset_review,
        )

        return PlateScanExecutionResult(
            payload=payload,
            review_status=payload["review_status"],
            review_reasons=payload["review_reasons"],
            plate_normalized=final_norm_plate,
            saved_file_path=None,
        )
    except Exception:
        # Anchored match on the whole url (host included), never a substring test.
        m = (
            re.fullmatch(
                r"https://res\.cloudinary\.com/[^/]+/image/upload/(?:v\d+/)?"
                r"(parking_scans/\d{4}/\d{2}/\d{2}/[0-9a-f]{32})\.(?:jpg|png|webp)",
                relative_url,
            )
            if relative_url
            else None
        )
        if m:
            try:
                import cloudinary.uploader

                cloudinary.uploader.destroy(m.group(1))
            except Exception as exc:
                logger.warning(
                    "Compensating destroy failed: %s", exc.__class__.__name__
                )
        raise
