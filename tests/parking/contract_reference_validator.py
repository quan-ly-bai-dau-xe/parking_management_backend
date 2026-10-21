"""
Independent Reference Contract Validator for Plate Scan Responses.

This module implements an authoritative, pure-Python specification validator for the
POST /api/v1/parking/plate-scans/ HTTP response contract documented in the OpenAPI schema.

Architectural Mandate:
- ZERO imports from apps.parking.services.plate_scan or internal service composition helpers.
- Validates 14 canonical keys, exact data types, and deep semantic domain invariants.
- Used as the ground-truth contract verifier to eliminate circular tautological comparisons.
"""

from __future__ import annotations

from typing import Any


class ContractSchemaError(AssertionError):
    """Raised when a response payload violates structural keys or typing contracts."""


class ContractInvariantError(AssertionError):
    """Raised when a response payload violates business logic invariants."""


class ReferenceContractValidator:
    """
    Pure-Python reference validator for OpenAPI plate scan contract.
    Operates strictly on raw deserialized JSON dictionary structures.
    """

    CANONICAL_ROOT_KEYS: frozenset[str] = frozenset(
        {
            "plate_raw",
            "plate_final",
            "candidates",
            "best_candidate",
            "image_url",
            "vehicle_lookup",
            "is_blacklisted",
            "open_session",
            "engine_name",
            "latency_ms",
            "review_status",
            "review_reasons",
            "corrections",
            "suggestions",
        }
    )

    CANONICAL_CANDIDATE_KEYS: frozenset[str] = frozenset(
        {
            "plate_text",
            "plate_normalized",
            "confidence",
            "char_confidences",
            "min_char_confidence",
            "bounding_box",
        }
    )

    CANONICAL_BOUNDING_BOX_KEYS: frozenset[str] = frozenset({"x1", "y1", "x2", "y2"})

    CANONICAL_CORRECTION_KEYS: frozenset[str] = frozenset(
        {
            "position",
            "from",
            "to",
            "rule",
            "reason",
            "original_char",
            "corrected_char",
        }
    )

    ALLOWED_REVIEW_STATUSES: frozenset[str] = frozenset({"AUTO", "NEEDS_REVIEW"})

    @classmethod
    def validate(cls, payload: dict[str, Any]) -> None:
        """
        Validates the entire response payload against structural and semantic contracts.
        Raises ContractSchemaError or ContractInvariantError if any rule is violated.
        """
        if not isinstance(payload, dict):
            raise ContractSchemaError(
                f"Expected payload to be dict, got {type(payload).__name__}"
            )

        cls._validate_root_keys(payload)
        cls._validate_types(payload)
        cls._validate_candidates(payload["candidates"])

        if payload["best_candidate"] is not None:
            cls._validate_candidate_item(
                payload["best_candidate"], field_name="best_candidate"
            )
            cls._validate_best_candidate_synchrony(payload)

        cls._validate_review_invariants(payload)
        cls._validate_corrections(payload)
        cls._validate_image_url(payload["image_url"])

    @classmethod
    def _validate_root_keys(cls, payload: dict[str, Any]) -> None:
        actual_keys = set(payload.keys())
        missing = cls.CANONICAL_ROOT_KEYS - actual_keys
        unexpected = actual_keys - cls.CANONICAL_ROOT_KEYS

        if missing:
            raise ContractSchemaError(
                f"Payload is missing mandatory canonical root keys: {sorted(missing)}"
            )
        if unexpected:
            raise ContractSchemaError(
                f"Payload contains unexpected non-canonical root keys: {sorted(unexpected)}"
            )

    @classmethod
    def _validate_types(cls, payload: dict[str, Any]) -> None:
        type_rules: dict[str, tuple[type, ...]] = {
            "plate_raw": (str,),
            "plate_final": (str,),
            "candidates": (list,),
            "image_url": (str,),
            "is_blacklisted": (bool,),
            "engine_name": (str,),
            "latency_ms": (int, float),
            "review_status": (str,),
            "review_reasons": (list,),
            "corrections": (list,),
            "suggestions": (list,),
        }

        for field, expected_types in type_rules.items():
            val = payload[field]
            if not isinstance(val, expected_types):
                raise ContractSchemaError(
                    f"Field '{field}' must be of type {expected_types}, got {type(val).__name__}"
                )

        if payload["best_candidate"] is not None and not isinstance(
            payload["best_candidate"], dict
        ):
            raise ContractSchemaError(
                f"Field 'best_candidate' must be dict or None, got {type(payload['best_candidate']).__name__}"
            )

        if payload["vehicle_lookup"] is not None and not isinstance(
            payload["vehicle_lookup"], dict
        ):
            raise ContractSchemaError(
                f"Field 'vehicle_lookup' must be dict or None, got {type(payload['vehicle_lookup']).__name__}"
            )

        if payload["open_session"] is not None and not isinstance(
            payload["open_session"], dict
        ):
            raise ContractSchemaError(
                f"Field 'open_session' must be dict or None, got {type(payload['open_session']).__name__}"
            )

        if payload["review_status"] not in cls.ALLOWED_REVIEW_STATUSES:
            raise ContractSchemaError(
                f"Field 'review_status' must be one of {sorted(cls.ALLOWED_REVIEW_STATUSES)}, "
                f"got '{payload['review_status']}'"
            )

        for reason in payload["review_reasons"]:
            if not isinstance(reason, str):
                raise ContractSchemaError(
                    f"All items in 'review_reasons' must be str, found {type(reason).__name__}"
                )

        for suggestion in payload["suggestions"]:
            if not isinstance(suggestion, str):
                raise ContractSchemaError(
                    f"All items in 'suggestions' must be str, found {type(suggestion).__name__}"
                )

    @classmethod
    def _validate_candidates(cls, candidates: list[Any]) -> None:
        for idx, item in enumerate(candidates):
            cls._validate_candidate_item(item, field_name=f"candidates[{idx}]")

    @classmethod
    def _validate_candidate_item(
        cls, candidate: Any, field_name: str = "candidate"
    ) -> None:
        if not isinstance(candidate, dict):
            raise ContractSchemaError(
                f"{field_name} must be a dict, got {type(candidate).__name__}"
            )

        keys = set(candidate.keys())
        missing = cls.CANONICAL_CANDIDATE_KEYS - keys
        unexpected = keys - cls.CANONICAL_CANDIDATE_KEYS

        if missing:
            raise ContractSchemaError(
                f"{field_name} is missing mandatory keys: {sorted(missing)}"
            )
        if unexpected:
            raise ContractSchemaError(
                f"{field_name} contains unexpected keys: {sorted(unexpected)}"
            )

        if not isinstance(candidate["plate_text"], str):
            raise ContractSchemaError(
                f"{field_name}.plate_text must be str, got {type(candidate['plate_text']).__name__}"
            )
        if not isinstance(candidate["plate_normalized"], str):
            raise ContractSchemaError(
                f"{field_name}.plate_normalized must be str, got {type(candidate['plate_normalized']).__name__}"
            )
        if not isinstance(candidate["confidence"], (int, float)):
            raise ContractSchemaError(
                f"{field_name}.confidence must be numeric, got {type(candidate['confidence']).__name__}"
            )
        if not isinstance(candidate["min_char_confidence"], (int, float)):
            raise ContractSchemaError(
                f"{field_name}.min_char_confidence must be numeric, got {type(candidate['min_char_confidence']).__name__}"
            )
        if not isinstance(candidate["char_confidences"], list):
            raise ContractSchemaError(
                f"{field_name}.char_confidences must be list, got {type(candidate['char_confidences']).__name__}"
            )

        bbox = candidate["bounding_box"]
        if bbox is not None:
            if not isinstance(bbox, dict):
                raise ContractSchemaError(
                    f"{field_name}.bounding_box must be dict or None, got {type(bbox).__name__}"
                )
            bb_keys = set(bbox.keys())
            if bb_keys != cls.CANONICAL_BOUNDING_BOX_KEYS:
                raise ContractSchemaError(
                    f"{field_name}.bounding_box keys mismatch: expected {sorted(cls.CANONICAL_BOUNDING_BOX_KEYS)}, got {sorted(bb_keys)}"
                )
            for coord in ("x1", "y1", "x2", "y2"):
                if not isinstance(bbox[coord], (int, float)):
                    raise ContractSchemaError(
                        f"{field_name}.bounding_box.{coord} must be numeric, got {type(bbox[coord]).__name__}"
                    )
            if bbox["x2"] < bbox["x1"]:
                raise ContractInvariantError(
                    f"{field_name}.bounding_box invariant violation: x2 ({bbox['x2']}) must be >= x1 ({bbox['x1']})"
                )
            if bbox["y2"] < bbox["y1"]:
                raise ContractInvariantError(
                    f"{field_name}.bounding_box invariant violation: y2 ({bbox['y2']}) must be >= y1 ({bbox['y1']})"
                )

    @classmethod
    def _validate_best_candidate_synchrony(cls, payload: dict[str, Any]) -> None:
        """
        Critical Contract Invariant: best_candidate.plate_normalized MUST strictly match plate_final.
        """
        best_cand = payload["best_candidate"]
        plate_final = payload["plate_final"]

        if best_cand["plate_normalized"] != plate_final:
            raise ContractInvariantError(
                f"best_candidate.plate_normalized ('{best_cand['plate_normalized']}') "
                f"must strictly equal plate_final ('{plate_final}')"
            )

    @classmethod
    def _validate_review_invariants(cls, payload: dict[str, Any]) -> None:
        status_val = payload["review_status"]
        reasons = payload["review_reasons"]

        if status_val == "AUTO" and len(reasons) > 0:
            raise ContractInvariantError(
                f"Contract invariant violation: review_status is 'AUTO' but review_reasons is non-empty: {reasons}"
            )

        if status_val == "NEEDS_REVIEW" and len(reasons) == 0:
            raise ContractInvariantError(
                "Contract invariant violation: review_status is 'NEEDS_REVIEW' but review_reasons is empty"
            )

    @classmethod
    def _validate_corrections(cls, payload: dict[str, Any]) -> None:
        corrections = payload["corrections"]
        status_val = payload["review_status"]
        reasons = payload["review_reasons"]

        for idx, corr in enumerate(corrections):
            if not isinstance(corr, dict):
                raise ContractSchemaError(
                    f"corrections[{idx}] must be dict, got {type(corr).__name__}"
                )
            keys = set(corr.keys())
            missing = cls.CANONICAL_CORRECTION_KEYS - keys
            unexpected = keys - cls.CANONICAL_CORRECTION_KEYS
            if missing or unexpected:
                raise ContractSchemaError(
                    f"corrections[{idx}] keys mismatch: missing={sorted(missing)}, unexpected={sorted(unexpected)}"
                )

        # Positional Correction Invariant (J4):
        # When corrections are present, review_status MUST be NEEDS_REVIEW and POSITION_CORRECTED must be in reasons.
        if len(corrections) > 0:
            if status_val != "NEEDS_REVIEW":
                raise ContractInvariantError(
                    f"Contract invariant violation: corrections are present ({len(corrections)}) "
                    f"but review_status is '{status_val}' (must be 'NEEDS_REVIEW')"
                )
            if "POSITION_CORRECTED" not in reasons:
                raise ContractInvariantError(
                    f"Contract invariant violation: corrections are present but 'POSITION_CORRECTED' "
                    f"is missing from review_reasons: {reasons}"
                )

    @classmethod
    def _validate_image_url(cls, image_url: str) -> None:
        if not image_url or not isinstance(image_url, str):
            raise ContractSchemaError(
                f"image_url must be a non-empty string, got '{image_url}'"
            )
        if not (
            image_url.startswith("/")
            or image_url.startswith("http://")
            or image_url.startswith("https://")
        ):
            raise ContractInvariantError(
                f"image_url must be an absolute or root-relative URL path, got '{image_url}'"
            )


def validate_plate_scan_reference_contract(payload: dict[str, Any]) -> None:
    """Convenience helper to validate a plate scan response payload."""
    ReferenceContractValidator.validate(payload)
