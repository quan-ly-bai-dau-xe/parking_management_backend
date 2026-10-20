"""
Core logging utilities and structured logging formatters.
Implements Rule 07 & Decree 13/2023/ND-CP compliance for PII masking (J9.2).
"""

from __future__ import annotations

from django.conf import settings


def mask_plate(plate: str) -> str:
    """
    Mask license plate string to obscure personal identifiable numbers.
    Preserves province/series prefix and final digits for debugging.

    Examples:
        - "51F-698.81" -> "51F-***.81"
        - "51F69881"   -> "51F***81"
        - "29A12345"   -> "29A***45"
        - "80B-1234"   -> "80B-***34"
        - "12A"        -> "***"
    """
    cleaned = plate.strip()
    if not cleaned:
        return ""

    # Formatted plate with hyphen: e.g. "51F-698.81" or "80B-1234"
    if "-" in cleaned:
        prefix, rest = cleaned.split("-", 1)
        if "." in rest:
            _, suffix = rest.split(".", 1)
            return f"{prefix}-***.{suffix}"
        if len(rest) >= 4:
            return f"{prefix}-***{rest[-2:]}"
        return f"{prefix}-***"

    # Unpunctuated alphanumeric plate: e.g. "51F69881" (len 8), "29A12345" (len 8)
    length = len(cleaned)
    if length >= 7:
        return f"{cleaned[:3]}***{cleaned[-2:]}"
    if length >= 5:
        return f"{cleaned[:2]}***{cleaned[-1:]}"
    return "***"


def format_plate_for_log(plate: str | None) -> str | None:
    """
    Format license plate for structured logging.
    Controlled by settings.PARKING_LOG_MASK_PLATES (default: True).
    When True, masks the plate to protect customer PII.
    When False, returns the unmasked plate.
    Always returns None if plate is None or empty.
    """
    if not plate:
        return None

    mask_enabled = bool(settings.PARKING_LOG_MASK_PLATES)
    if not mask_enabled:
        return plate

    return mask_plate(plate)
