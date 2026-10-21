"""
Domain enums and review reason codes for vehicle license plate scans (A2, H7, J4).
"""

from __future__ import annotations


class ReviewReasonCode:
    """Standard review reason codes for plate scans needing manual review (A2, H7, J4)."""

    MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"
    LOW_CHAR_CONFIDENCE = "LOW_CHAR_CONFIDENCE"
    INVALID_FORMAT = "INVALID_FORMAT"
    UNKNOWN_PLATE_PATTERN = "UNKNOWN_PLATE_PATTERN"
    NO_DETECTION_RETRY = "NO_DETECTION_RETRY"
    LOW_DETECTION_CONFIDENCE = "LOW_DETECTION_CONFIDENCE"
    IRREGULAR_ASPECT_RATIO = "IRREGULAR_ASPECT_RATIO"
    LOW_IMAGE_SHARPNESS = "LOW_IMAGE_SHARPNESS"
    POSITION_CORRECTED = "POSITION_CORRECTED"

    CHOICES: list[tuple[str, str]] = [
        (MODEL_DISAGREEMENT, "Model disagreement"),
        (LOW_CHAR_CONFIDENCE, "Low character confidence"),
        (INVALID_FORMAT, "Invalid plate format"),
        (UNKNOWN_PLATE_PATTERN, "Unknown plate pattern"),
        (NO_DETECTION_RETRY, "No detection retry / fallback used"),
        (LOW_DETECTION_CONFIDENCE, "Low detection confidence"),
        (IRREGULAR_ASPECT_RATIO, "Irregular aspect ratio"),
        (LOW_IMAGE_SHARPNESS, "Low image sharpness"),
        (POSITION_CORRECTED, "Position-aware character correction applied"),
    ]

    ALL_CODES: frozenset[str] = frozenset(
        {
            MODEL_DISAGREEMENT,
            LOW_CHAR_CONFIDENCE,
            INVALID_FORMAT,
            UNKNOWN_PLATE_PATTERN,
            NO_DETECTION_RETRY,
            LOW_DETECTION_CONFIDENCE,
            IRREGULAR_ASPECT_RATIO,
            LOW_IMAGE_SHARPNESS,
            POSITION_CORRECTED,
        }
    )


class ReviewStatus:
    """Review status outcomes for plate scans."""

    AUTO = "AUTO"
    NEEDS_REVIEW = "NEEDS_REVIEW"

    CHOICES: list[tuple[str, str]] = [
        (AUTO, "Automatic approval"),
        (NEEDS_REVIEW, "Needs manual review"),
    ]
