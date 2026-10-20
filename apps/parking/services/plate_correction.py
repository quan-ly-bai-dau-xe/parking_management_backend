"""
Vietnamese License Plate Format Validation, Position-Aware Correction, and Review Policy Service.
Compliant with Circular 24/2023/TT-BCA and Circular 79/2024/TT-BCA.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from django.db import connection

from apps.parking.data.vn_plate_rules import (
    VALID_PROVINCE_CODES,
    is_valid_vietnamese_car_plate,
)
from apps.parking.enums import ReviewReasonCode, ReviewStatus
from apps.parking.services.review_policy import evaluate_review_policy

logger = logging.getLogger(__name__)

# Re-exported domain constants and policies for 100% backward compatibility
__all__ = [
    "CONFUSABLE_TO_DIGIT",
    "CONFUSABLE_TO_LETTER",
    "CorrectionDetail",
    "ReviewReasonCode",
    "ReviewStatus",
    "VALID_PROVINCES",
    "correct_plate_characters",
    "evaluate_review_policy",
    "get_plate_suggestions",
    "is_valid_vietnamese_plate",
]

# Backward compatibility alias for province codes
VALID_PROVINCES: frozenset[str] = VALID_PROVINCE_CODES

# Common OCR confusion character mappings by positional syntax
CONFUSABLE_TO_DIGIT: dict[str, str] = {
    "D": "0",
    "O": "0",
    "Q": "0",
    "I": "1",
    "L": "1",
    "Z": "2",
    "A": "4",
    "S": "5",
    "G": "6",
    "B": "8",
}

CONFUSABLE_TO_LETTER: dict[str, str] = {
    "5": "S",
    "8": "B",
    "2": "Z",
    "0": "D",  # 'O' is not a valid series letter in VN civilian cars; 'D' is standard for vans/trucks
}


@dataclass(frozen=True)
class CorrectionDetail:
    """Record of a character corrected based on positional grammar (H6)."""

    position: int
    original_char: str
    corrected_char: str
    rule: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "position": self.position,
            "from": self.original_char,
            "to": self.corrected_char,
            "rule": self.rule,
            "reason": self.reason
            or f"Positional grammar correction from '{self.original_char}' to '{self.corrected_char}'",
            "original_char": self.original_char,
            "corrected_char": self.corrected_char,
        }


def is_valid_vietnamese_plate(plate_norm: str) -> bool:
    """
    Check if a normalized plate matches standard Vietnamese car syntax.
    Enforces valid province code, allowed series letter(s), and 4 or 5 digits.
    Motorbike syntax is excluded in accordance with SRS car-only scope.
    """
    return is_valid_vietnamese_car_plate(plate_norm)


def correct_plate_characters(
    raw_or_norm_plate: str,
) -> tuple[str, list[CorrectionDetail]]:
    """
    Apply position-aware character corrections for Vietnamese license plates (A3).
    Only modifies characters where positional syntax unambiguously dictates character class.
    Preserves all already-valid plates untouched (0 broken correct reads).
    """
    cleaned = re.sub(r"[^A-Za-z0-9]", "", raw_or_norm_plate or "").upper()
    if not cleaned:
        return "", []

    # Guard 1: If already valid, do not modify anything
    if is_valid_vietnamese_plate(cleaned):
        return cleaned, []

    chars = list(cleaned)
    n = len(chars)
    corrections: list[CorrectionDetail] = []

    # Positional rules apply only to lengths 7, 8, 9
    if n in (7, 8, 9):
        # 1. Province code digits: Pos 0 and 1
        # Case 1A: Pos 0 is digit, Pos 1 is confusable letter (e.g. '5DZ1630' -> Pos 1 'D' -> '0')
        if (
            chars[0].isdigit()
            and not chars[1].isdigit()
            and chars[1] in CONFUSABLE_TO_DIGIT
            and (
                (n >= 3 and chars[2].isalpha())
                or (n in (7, 8) and "".join(chars[3:]).isdigit())
            )
        ):
            old_c = chars[1]
            chars[1] = CONFUSABLE_TO_DIGIT[old_c]
            corrections.append(
                CorrectionDetail(
                    position=1,
                    original_char=old_c,
                    corrected_char=chars[1],
                    rule="province_second_digit_fix",
                    reason=f"Positional grammar requires digit at position 1; corrected '{old_c}' to '{chars[1]}'",
                )
            )

        # Case 1B: Pos 0 is confusable letter, Pos 1 is digit (e.g. 'OZ1630' -> '0Z' or 'D1A12345')
        if (
            not chars[0].isdigit()
            and chars[0] in CONFUSABLE_TO_DIGIT
            and chars[1].isdigit()
            and n >= 3
            and chars[2].isalpha()
        ):
            old_c = chars[0]
            chars[0] = CONFUSABLE_TO_DIGIT[old_c]
            corrections.append(
                CorrectionDetail(
                    position=0,
                    original_char=old_c,
                    corrected_char=chars[0],
                    rule="province_first_digit_fix",
                    reason=f"Positional grammar requires digit at position 0; corrected '{old_c}' to '{chars[0]}'",
                )
            )

        # 2. Series letter: Pos 2 in standard single-letter series
        # Pos 0 and 1 are digits, Pos 3..end are digits, but Pos 2 was recognized as a digit (e.g. '51599214' -> '51S99214')
        if (
            "".join(chars[:2]).isdigit()
            and "".join(chars[3:]).isdigit()
            and chars[2].isdigit()
            and chars[2] in CONFUSABLE_TO_LETTER
        ):
            old_c = chars[2]
            chars[2] = CONFUSABLE_TO_LETTER[old_c]
            corrections.append(
                CorrectionDetail(
                    position=2,
                    original_char=old_c,
                    corrected_char=chars[2],
                    rule="series_letter_fix",
                    reason=f"Positional grammar requires letter at position 2; corrected '{old_c}' to '{chars[2]}'",
                )
            )

        # 3. Number group digits: Pos 3..end (protecting joint venture series like 'LD' where Pos 3 is 'D')
        if "".join(chars[:2]).isdigit() and chars[2].isalpha():
            is_dual_letter = (chars[2] == "L" and n >= 4 and chars[3] == "D") or (
                chars[2] in ("D", "N") and n >= 4 and chars[3] in ("A", "G")
            )
            start_num_pos = 4 if is_dual_letter else 3
            for p in range(start_num_pos, n):
                if not chars[p].isdigit() and chars[p] in CONFUSABLE_TO_DIGIT:
                    old_c = chars[p]
                    chars[p] = CONFUSABLE_TO_DIGIT[old_c]
                    corrections.append(
                        CorrectionDetail(
                            position=p,
                            original_char=old_c,
                            corrected_char=chars[p],
                            rule=f"number_group_digit_fix_pos_{p}",
                            reason=f"Positional grammar requires digit at position {p}; corrected '{old_c}' to '{chars[p]}'",
                        )
                    )

    corrected_str = "".join(chars)

    # Enforce H6 rule: Never auto-correct when the corrected plate would still be UNKNOWN_PLATE_PATTERN or INVALID_FORMAT
    if corrections and not is_valid_vietnamese_car_plate(corrected_str):
        return cleaned, []

    return corrected_str, corrections


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Compute exact Levenshtein edit distance between two strings."""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)

    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def get_plate_suggestions(norm_plate: str, limit: int = 3) -> list[str]:
    """
    Search up to `limit` registered or blacklisted plates with edit distance <= 1
    and pg_trgm similarity (A5).
    Never modifies database records. Returned for human operator convenience.
    """
    if not norm_plate:
        return []

    suggestions: list[str] = []
    seen: set[str] = {norm_plate}
    used_pg_trgm = False

    # Attempt PostgreSQL pg_trgm query when available (uses idx_vehicle_plate_trgm)
    if connection.vendor == "postgresql":
        try:
            with connection.cursor() as cursor:
                query = """
                    SELECT candidate_plate, license_plate_norm, similarity(license_plate_norm, %s) AS sm
                    FROM (
                        SELECT license_plate AS candidate_plate, license_plate_norm
                        FROM vehicle
                        WHERE deleted_at IS NULL AND license_plate_norm %% %s
                        UNION
                        SELECT license_plate AS candidate_plate, license_plate_norm
                        FROM plate_blacklist
                        WHERE deleted_at IS NULL AND is_active = TRUE AND license_plate_norm %% %s
                    ) sub
                    WHERE license_plate_norm <> %s
                    ORDER BY sm DESC
                    LIMIT %s;
                """
                cursor.execute(
                    query,
                    [norm_plate, norm_plate, norm_plate, norm_plate, limit * 5],
                )
                rows = cursor.fetchall()
                used_pg_trgm = True
                for row in rows:
                    cand = str(row[0]).strip()
                    cand_norm = (
                        str(row[1]).strip().upper()
                        if row[1]
                        else re.sub(r"[^A-Za-z0-9]", "", cand).upper()
                    )
                    if (
                        cand_norm not in seen
                        and _levenshtein_distance(norm_plate, cand_norm) <= 1
                        and len(suggestions) < limit
                    ):
                        seen.add(cand_norm)
                        suggestions.append(cand)
        except Exception as exc:
            logger.warning(
                "PostgreSQL pg_trgm suggestion query failed, falling back: %s", exc
            )

    # Fallback to ORM + Python Levenshtein only when pg_trgm is unavailable
    if not used_pg_trgm and len(suggestions) < limit:
        try:
            from apps.parking.models import PlateBlacklist
            from apps.vehicles.models import Vehicle

            min_len = max(len(norm_plate) - 1, 6)
            max_len = len(norm_plate) + 1

            veh_plates = list(
                Vehicle.objects.filter(
                    deleted_at__isnull=True,
                ).values_list("license_plate", "license_plate_norm")
            )
            blk_plates = list(
                PlateBlacklist.objects.filter(
                    deleted_at__isnull=True,
                    is_active=True,
                ).values_list("license_plate", "license_plate_norm")
            )

            all_candidates = veh_plates + blk_plates
            scored_candidates: list[tuple[int, str, str]] = []

            for display_plate, cand_norm in all_candidates:
                if not cand_norm or cand_norm in seen:
                    continue
                if min_len <= len(cand_norm) <= max_len:
                    dist = _levenshtein_distance(norm_plate, cand_norm)
                    if dist <= 1:
                        scored_candidates.append((dist, display_plate, cand_norm))

            scored_candidates.sort(key=lambda x: x[0])
            for _, display_plate, cand_norm in scored_candidates:
                if cand_norm not in seen and len(suggestions) < limit:
                    seen.add(cand_norm)
                    suggestions.append(display_plate)
        except Exception as exc:
            logger.warning("Fallback plate suggestions failed: %s", exc)

    return suggestions[:limit]
