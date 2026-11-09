"""
License plate formatting helper for display consistency per Circular 79/2024/TT-BCA
and seed data standards (e.g. 51A-897.14, 30C-468.58, 81-B3 343.03).
"""

from __future__ import annotations

import re

# Standard civilian car with 5 digits (e.g., 51A89714 -> 51A-897.14, 50LD04411 -> 50LD-044.11)
CAR_5DIGIT_RE = re.compile(r"^([0-9]{2}[A-Z]{1,2})([0-9]{3})([0-9]{2})$")

# Standard civilian car with 4 digits (e.g., 29A1234 -> 29A-1234, 43B4096 -> 43B-4096)
CAR_4DIGIT_RE = re.compile(r"^([0-9]{2}[A-Z]{1,2})([0-9]{4})$")

# Motorcycle with 5 digits (e.g., 81B334303 -> 81-B3 343.03, 59T249609 -> 59-T2 496.09)
MOTO_5DIGIT_RE = re.compile(r"^([0-9]{2})([A-Z][0-9A-Z])([0-9]{3})([0-9]{2})$")

# Motorcycle with 4 digits (e.g., 29H11234 -> 29-H1 1234)
MOTO_4DIGIT_RE = re.compile(r"^([0-9]{2})([A-Z][0-9A-Z])([0-9]{4})$")

# Explicit motorcycle patterns with province hyphen (e.g., 29-H1 1234, 81-B3 343.03)
MOTO_EXPLICIT_4_RE = re.compile(r"^([0-9]{2})-([A-Z][0-9A-Z])[\s.-]*([0-9]{4})$")
MOTO_EXPLICIT_5_RE = re.compile(
    r"^([0-9]{2})-([A-Z][0-9A-Z])[\s.-]*([0-9]{3})[\s.-]*([0-9]{2})$"
)

# Explicit car patterns with series hyphen (e.g., 51A-897.14, 29A-1234, 30A-612.35)
CAR_EXPLICIT_4_RE = re.compile(r"^([0-9]{2}[A-Z]{1,2})-([0-9]{4})$")
CAR_EXPLICIT_5_RE = re.compile(r"^([0-9]{2}[A-Z]{1,2})-([0-9]{3})[\s.-]*([0-9]{2})$")

# Unambiguous compact patterns (only 1 valid vehicle type is possible)
MOTO_UNAMBIGUOUS_5_RE = re.compile(r"^([0-9]{2})([A-Z][0-9])([0-9]{3})([0-9]{2})$")
CAR_UNAMBIGUOUS_4_RE = re.compile(r"^([0-9]{2}[A-Z])([0-9]{4})$")

# Compact ambiguous shapes (match more than one pattern: car vs motorcycle)
AMBIGUOUS_SHAPES = [
    re.compile(
        r"^[0-9]{2}[A-Z][0-9]{5}$"
    ),  # Shape A: Car 5-digit vs Moto 4-digit (e.g. 29H11234, 51A89714)
    re.compile(
        r"^[0-9]{2}[A-Z]{2}[0-9]{5}$"
    ),  # Shape B: Car 5-digit 2-letter vs Moto electric (e.g. 29MD12345)
    re.compile(
        r"^[0-9]{2}[A-Z]{2}[0-9]{4}$"
    ),  # Shape C: Car 4-digit 2-letter vs Moto 4-digit 2-letter (e.g. 29LD1234)
]


def format_display_license_plate(
    plate: str | None, vehicle_type: str | None = None
) -> str:
    """
    Format license plate string into standard Vietnamese display representation
    with hyphens and dots (e.g. '51A-897.14', '30C-468.58', '81-B3 343.03').

    Vehicle-type aware disambiguation (Finding 2 / TL-65):
    - When vehicle_type is known (CAR/EV vs MOTORCYCLE): format according to vehicle type.
    - When vehicle_type is unknown / None:
        * If explicit separators are already present, preserve them.
        * If shape is unambiguous (e.g. 81B334303, 29A1234), format automatically.
        * If shape is ambiguous (e.g. 29H11234, 51A89714, 30A61235, 29MD12345),
          return the cleaned compact plate without separators rather than guessing.
    """
    if not plate or not str(plate).strip():
        return ""

    s = str(plate).strip().upper()

    # 1. Explicit motorcycle patterns with province hyphen
    m_exp4 = MOTO_EXPLICIT_4_RE.match(s)
    if m_exp4:
        return f"{m_exp4.group(1)}-{m_exp4.group(2)} {m_exp4.group(3)}"

    m_exp5 = MOTO_EXPLICIT_5_RE.match(s)
    if m_exp5:
        return (
            f"{m_exp5.group(1)}-{m_exp5.group(2)} {m_exp5.group(3)}.{m_exp5.group(4)}"
        )

    # 2. Explicit car patterns with series hyphen
    m_car_exp5 = CAR_EXPLICIT_5_RE.match(s)
    if m_car_exp5:
        return f"{m_car_exp5.group(1)}-{m_car_exp5.group(2)}.{m_car_exp5.group(3)}"

    m_car_exp4 = CAR_EXPLICIT_4_RE.match(s)
    if m_car_exp4:
        return f"{m_car_exp4.group(1)}-{m_car_exp4.group(2)}"

    # 3. Clean alphanumeric characters
    raw = re.sub(r"[^A-Z0-9]", "", s)

    vt = str(vehicle_type).strip().upper() if vehicle_type else ""
    is_moto = vt in ("MOTORCYCLE", "MOTO", "XE_MAY", "BIKE") or (
        "MOTO" in vt or "XE_MAY" in vt or "BIKE" in vt
    )
    is_car = not is_moto and (
        vt in ("CAR", "EV", "AUTO", "OTO")
        or ("CAR" in vt or "AUTO" in vt or vt == "OTO")
    )

    # 4. If vehicle type is known:
    if is_car:
        m_car5 = CAR_5DIGIT_RE.match(raw)
        if m_car5:
            return f"{m_car5.group(1)}-{m_car5.group(2)}.{m_car5.group(3)}"
        m_car4 = CAR_4DIGIT_RE.match(raw)
        if m_car4:
            return f"{m_car4.group(1)}-{m_car4.group(2)}"
        return s

    if is_moto:
        m_moto5 = MOTO_5DIGIT_RE.match(raw)
        if m_moto5:
            return f"{m_moto5.group(1)}-{m_moto5.group(2)} {m_moto5.group(3)}.{m_moto5.group(4)}"
        m_moto4 = MOTO_4DIGIT_RE.match(raw)
        if m_moto4:
            return f"{m_moto4.group(1)}-{m_moto4.group(2)} {m_moto4.group(3)}"
        return s

    # 5. When vehicle type is unknown:
    # 5a. Unambiguous motorcycle 5-digit: e.g. 81B334303 -> 81-B3 343.03
    m_u_m5 = MOTO_UNAMBIGUOUS_5_RE.match(raw)
    if m_u_m5:
        return (
            f"{m_u_m5.group(1)}-{m_u_m5.group(2)} {m_u_m5.group(3)}.{m_u_m5.group(4)}"
        )

    # 5b. Unambiguous car 4-digit: e.g. 29A1234 -> 29A-1234
    m_u_c4 = CAR_UNAMBIGUOUS_4_RE.match(raw)
    if m_u_c4:
        return f"{m_u_c4.group(1)}-{m_u_c4.group(2)}"

    # 5c. Ambiguous shapes without known vehicle type: DO NOT GUESS -> return raw cleaned compact
    for amb_re in AMBIGUOUS_SHAPES:
        if amb_re.match(raw):
            return raw

    return s
