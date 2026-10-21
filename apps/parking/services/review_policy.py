"""
Review policy evaluation service for vehicle license plate scans (A2, H7, J4, J6).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from apps.parking.enums import ReviewReasonCode, ReviewStatus

# Named constants for secondary review signals (Standard 4, J6)
DEFAULT_DETECTOR_BOX_CONF_MIN: float = 80.0
DEFAULT_PLATE_ASPECT_RATIO_MIN: float = 1.3
DEFAULT_PLATE_ASPECT_RATIO_MAX: float = 6.0
DEFAULT_CROP_SHARPNESS_MIN: float = 30.0


def evaluate_review_policy(
    model_agreement: bool,
    min_char_confidence: float,
    threshold: float,
    is_valid_format: bool,
    used_detection_fallback: bool = False,
    is_unknown_pattern: bool = False,
    detector_box_confidence: float | None = None,
    plate_aspect_ratio: float | None = None,
    crop_sharpness: float | None = None,
    corrections: Sequence[Any] | None = None,
    has_corrections: bool | None = None,
    *,
    min_detector_box_confidence: float = DEFAULT_DETECTOR_BOX_CONF_MIN,
    min_aspect_ratio: float = DEFAULT_PLATE_ASPECT_RATIO_MIN,
    max_aspect_ratio: float = DEFAULT_PLATE_ASPECT_RATIO_MAX,
    min_sharpness: float = DEFAULT_CROP_SHARPNESS_MIN,
) -> tuple[str, list[str]]:
    """
    Business review policy evaluation (A2, H7, J4, J6).

    review_status is 'AUTO' ONLY when all required conditions hold simultaneously:
      1. Both OCR models agree on normalized plate (model_agreement == True).
      2. Minimum per-character confidence >= threshold (e.g. 85.0% or 0.85).
      3. Normalized plate matches valid Vietnamese plate syntax (is_valid_format == True).
      4. Not an unknown plate pattern (is_unknown_pattern == False).
      5. Detection succeeded on first pass without fallback retry (used_detection_fallback == False).
      6. No character position correction was applied (corrections is empty / has_corrections is False).
      7. Secondary signals within acceptable operating bounds if provided.

    Otherwise returns 'NEEDS_REVIEW' and the list of specific review reasons.
    """
    # Normalize threshold to 0..100 scale if given as 0..1
    eff_threshold = threshold * 100.0 if threshold <= 1.0 else threshold

    reasons: list[str] = []

    if not model_agreement:
        reasons.append(ReviewReasonCode.MODEL_DISAGREEMENT)

    if min_char_confidence < eff_threshold:
        reasons.append(ReviewReasonCode.LOW_CHAR_CONFIDENCE)

    if is_unknown_pattern:
        reasons.append(ReviewReasonCode.UNKNOWN_PLATE_PATTERN)
    elif not is_valid_format:
        reasons.append(ReviewReasonCode.INVALID_FORMAT)

    if used_detection_fallback:
        reasons.append(ReviewReasonCode.NO_DETECTION_RETRY)

    # Secondary low-cost signals (H7, J6)
    if (
        detector_box_confidence is not None
        and detector_box_confidence < min_detector_box_confidence
    ):
        reasons.append(ReviewReasonCode.LOW_DETECTION_CONFIDENCE)

    if plate_aspect_ratio is not None and (
        plate_aspect_ratio < min_aspect_ratio or plate_aspect_ratio >= max_aspect_ratio
    ):
        reasons.append(ReviewReasonCode.IRREGULAR_ASPECT_RATIO)

    if crop_sharpness is not None and crop_sharpness < min_sharpness:
        reasons.append(ReviewReasonCode.LOW_IMAGE_SHARPNESS)

    # Non-silent substitution enforcement (J4):
    # Any non-empty corrections list forces NEEDS_REVIEW and registers POSITION_CORRECTED.
    is_corrected = (
        bool(has_corrections) if has_corrections is not None else bool(corrections)
    )
    if is_corrected and ReviewReasonCode.POSITION_CORRECTED not in reasons:
        reasons.append(ReviewReasonCode.POSITION_CORRECTED)

    if not reasons:
        return ReviewStatus.AUTO, []
    return ReviewStatus.NEEDS_REVIEW, reasons
