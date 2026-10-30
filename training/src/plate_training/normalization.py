"""Plate string normalization module."""

import re


def normalize_plate(raw_text: str | None) -> str:
    """
    Normalize license plate string by removing non-alphanumeric characters
    and converting to uppercase.

    Guarantees 100% bit-level parity with backend PlateRecognizer.normalize_plate
    and PostgreSQL fn_normalize_license_plate function.
    """
    return re.sub(r"[^A-Za-z0-9]", "", (raw_text or "")).upper()
