"""
Generates 42 Golden JSON Fixtures for Plate Scan API Contract Verification.

Each fixture represents an authoritative, ground-truth response matching the OpenAPI schema:
- 14 canonical root keys
- Invariant: best_candidate.plate_normalized == plate_final
- Invariant: review_status == AUTO => review_reasons == []
- Invariant: len(corrections) > 0 => review_status == NEEDS_REVIEW and POSITION_CORRECTED in review_reasons
- BoundingBox: x2 > x1, y2 > y1
- No secrets, no images, pure JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.parking.contract_reference_validator import ReferenceContractValidator

FIXTURES_DIR = Path(__file__).resolve().parent / "golden_fixtures"
FIXTURES_DIR.mkdir(parents=True, exist_ok=True)


def make_candidate(
    plate_text: str,
    plate_norm: str,
    conf: float = 98.5,
    min_char_c: float = 96.0,
    box: tuple[int, int, int, int] = (50, 50, 350, 150),
) -> dict:
    char_confs = [conf] * max(len(plate_norm) - 1, 1) + [min_char_c]
    return {
        "plate_text": plate_text,
        "plate_normalized": plate_norm,
        "confidence": conf,
        "char_confidences": char_confs,
        "min_char_confidence": min_char_c,
        "bounding_box": {
            "x1": box[0],
            "y1": box[1],
            "x2": box[2],
            "y2": box[3],
        },
    }


def make_payload(
    plate_raw: str,
    plate_final: str,
    candidates: list[dict],
    best_cand: dict | None,
    image_url: str = (
        "https://res.cloudinary.com/test-cloud/image/upload/"
        "v1730178490/parking_scans/2026/10/20/12345678901234567890123456789012.jpg"
    ),
    vehicle_lookup: dict | None = None,
    is_blacklisted: bool = False,
    open_session: dict | None = None,
    engine_name: str = "fast_alpr",
    latency_ms: float = 45.2,
    review_status: str = "AUTO",
    review_reasons: list[str] | None = None,
    corrections: list[dict] | None = None,
    suggestions: list[str] | None = None,
) -> dict:
    return {
        "plate_raw": plate_raw,
        "plate_final": plate_final,
        "candidates": candidates,
        "best_candidate": best_cand,
        "image_url": image_url,
        "vehicle_lookup": vehicle_lookup,
        "is_blacklisted": is_blacklisted,
        "open_session": open_session,
        "engine_name": engine_name,
        "latency_ms": latency_ms,
        "review_status": review_status,
        "review_reasons": review_reasons or [],
        "corrections": corrections or [],
        "suggestions": suggestions or [],
    }


FIXTURE_SPECS: list[dict] = [
    # Group 1: Standard Valid Plates (8 fixtures)
    {
        "id": "01_valid_saigon_51k99214",
        "raw": "51K-992.14",
        "final": "51K99214",
        "conf": 98.5,
        "min_c": 96.0,
        "box": (120, 340, 450, 440),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    {
        "id": "02_valid_hanoi_30e12345",
        "raw": "30E-123.45",
        "final": "30E12345",
        "conf": 97.8,
        "min_c": 95.5,
        "box": (100, 200, 400, 300),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    {
        "id": "03_valid_danang_43a67890",
        "raw": "43A-678.90",
        "final": "43A67890",
        "conf": 99.1,
        "min_c": 98.0,
        "box": (110, 220, 420, 310),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    {
        "id": "04_valid_dongnai_60a34567",
        "raw": "60A-345.67",
        "final": "60A34567",
        "conf": 96.5,
        "min_c": 94.0,
        "box": (90, 180, 390, 280),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    {
        "id": "05_valid_binhduong_61b88888",
        "raw": "61B-888.88",
        "final": "61B88888",
        "conf": 98.9,
        "min_c": 97.2,
        "box": (130, 250, 440, 340),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    {
        "id": "06_valid_quangninh_14a55555",
        "raw": "14A-555.55",
        "final": "14A55555",
        "conf": 97.0,
        "min_c": 95.0,
        "box": (105, 210, 415, 305),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    {
        "id": "07_valid_khanhhoa_79a11111",
        "raw": "79A-111.11",
        "final": "79A11111",
        "conf": 98.2,
        "min_c": 96.5,
        "box": (115, 230, 425, 320),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    {
        "id": "08_valid_haiphong_15a99999",
        "raw": "15A-999.99",
        "final": "15A99999",
        "conf": 99.0,
        "min_c": 97.5,
        "box": (125, 240, 435, 330),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    # Group 2: Legacy 7-character & Positional Corrections (5 fixtures)
    {
        "id": "09_pos_corrected_5dz1630",
        "raw": "5DZ-1630",
        "final": "50Z1630",
        "conf": 93.5,
        "min_c": 91.0,
        "box": (100, 200, 380, 290),
        "status": "NEEDS_REVIEW",
        "reasons": ["POSITION_CORRECTED"],
        "corr": [
            {
                "position": 1,
                "from": "D",
                "to": "0",
                "rule": "0_to_D_O_Q",
                "reason": "Character at position 1 must be digit in 7-char format",
                "original_char": "D",
                "corrected_char": "0",
            }
        ],
    },
    {
        "id": "10_pos_corrected_52y649o",
        "raw": "52Y-649O",
        "final": "52Y6490",
        "conf": 94.0,
        "min_c": 92.0,
        "box": (100, 200, 380, 290),
        "status": "NEEDS_REVIEW",
        "reasons": ["POSITION_CORRECTED"],
        "corr": [
            {
                "position": 6,
                "from": "O",
                "to": "0",
                "rule": "0_to_D_O_Q",
                "reason": "Character at tail position must be digit",
                "original_char": "O",
                "corrected_char": "0",
            }
        ],
    },
    {
        "id": "11_pos_corrected_29s1234",
        "raw": "29S-1234",
        "final": "2951234",
        "conf": 92.5,
        "min_c": 90.5,
        "box": (100, 200, 380, 290),
        "status": "NEEDS_REVIEW",
        "reasons": ["POSITION_CORRECTED"],
        "corr": [
            {
                "position": 2,
                "from": "S",
                "to": "5",
                "rule": "5_to_S",
                "reason": "Character at position 2 corrected from S to 5",
                "original_char": "S",
                "corrected_char": "5",
            }
        ],
    },
    {
        "id": "12_pos_corrected_43b5678",
        "raw": "43B-5678",
        "final": "4385678",
        "conf": 93.0,
        "min_c": 91.5,
        "box": (100, 200, 380, 290),
        "status": "NEEDS_REVIEW",
        "reasons": ["POSITION_CORRECTED"],
        "corr": [
            {
                "position": 2,
                "from": "B",
                "to": "8",
                "rule": "8_to_B",
                "reason": "Character at position 2 corrected from B to 8",
                "original_char": "B",
                "corrected_char": "8",
            }
        ],
    },
    {
        "id": "13_pos_corrected_multiple_rules",
        "raw": "5DZS-630",
        "final": "50Z5630",
        "conf": 91.0,
        "min_c": 90.2,
        "box": (100, 200, 380, 290),
        "status": "NEEDS_REVIEW",
        "reasons": ["POSITION_CORRECTED"],
        "corr": [
            {
                "position": 1,
                "from": "D",
                "to": "0",
                "rule": "0_to_D_O_Q",
                "reason": "Position 1 digit fix",
                "original_char": "D",
                "corrected_char": "0",
            },
            {
                "position": 3,
                "from": "S",
                "to": "5",
                "rule": "5_to_S",
                "reason": "Position 3 digit fix",
                "original_char": "S",
                "corrected_char": "5",
            },
        ],
    },
    # Group 3: Special Vehicle Series (4 fixtures)
    {
        "id": "14_special_diplomatic_ng",
        "raw": "80-NG-123.45",
        "final": "80NG12345",
        "conf": 98.0,
        "min_c": 96.0,
        "box": (100, 200, 420, 300),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    {
        "id": "15_special_foreign_nn",
        "raw": "80-NN-567.89",
        "final": "80NN56789",
        "conf": 97.5,
        "min_c": 95.8,
        "box": (100, 200, 420, 300),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    {
        "id": "16_special_joint_venture_ld",
        "raw": "50-LD-044.11",
        "final": "50LD04411",
        "conf": 98.2,
        "min_c": 96.5,
        "box": (100, 200, 420, 300),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    {
        "id": "17_special_commercial_truck_51c",
        "raw": "51C-123.45",
        "final": "51C12345",
        "conf": 98.7,
        "min_c": 97.0,
        "box": (100, 200, 410, 300),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
    },
    # Group 4: Unknown Province & Syntax Anomalies (4 fixtures)
    {
        "id": "18_unknown_province_13a",
        "raw": "13A-123.45",
        "final": "13A12345",
        "conf": 98.0,
        "min_c": 96.0,
        "box": (100, 200, 400, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["UNKNOWN_PLATE_PATTERN"],
        "corr": [],
    },
    {
        "id": "19_unknown_province_42a",
        "raw": "42A-999.99",
        "final": "42A99999",
        "conf": 97.0,
        "min_c": 95.0,
        "box": (100, 200, 400, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["UNKNOWN_PLATE_PATTERN"],
        "corr": [],
    },
    {
        "id": "20_invalid_format_too_short",
        "raw": "51A-12",
        "final": "51A12",
        "conf": 95.0,
        "min_c": 92.0,
        "box": (100, 200, 300, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["INVALID_FORMAT"],
        "corr": [],
    },
    {
        "id": "21_invalid_format_special_chars",
        "raw": "51A-9999",
        "final": "51A9999",
        "conf": 96.0,
        "min_c": 93.0,
        "box": (100, 200, 350, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["UNKNOWN_PLATE_PATTERN"],
        "corr": [],
    },
    # Group 5: Low Confidence & Image Quality Edge Cases (4 fixtures)
    {
        "id": "22_low_min_char_confidence",
        "raw": "51F-698.81",
        "final": "51F69881",
        "conf": 94.0,
        "min_c": 88.0,
        "box": (100, 200, 400, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["LOW_CHAR_CONFIDENCE"],
        "corr": [],
    },
    {
        "id": "23_low_overall_confidence",
        "raw": "30A-123.45",
        "final": "30A12345",
        "conf": 86.5,
        "min_c": 82.0,
        "box": (100, 200, 400, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["LOW_CHAR_CONFIDENCE"],
        "corr": [],
    },
    {
        "id": "24_low_sharpness_blur",
        "raw": "51F-698.81",
        "final": "51F69881",
        "conf": 95.0,
        "min_c": 92.0,
        "box": (100, 200, 400, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["LOW_IMAGE_SHARPNESS"],
        "corr": [],
    },
    {
        "id": "25_low_detector_confidence",
        "raw": "51F-698.81",
        "final": "51F69881",
        "conf": 96.0,
        "min_c": 94.0,
        "box": (100, 200, 400, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["LOW_DETECTOR_CONFIDENCE"],
        "corr": [],
    },
    # Group 6: Aspect Ratio & Geometric Anomalies (4 fixtures)
    {
        "id": "26_aspect_ratio_too_wide",
        "raw": "51F-698.81",
        "final": "51F69881",
        "conf": 97.0,
        "min_c": 95.0,
        "box": (50, 100, 700, 190),  # width=650, height=90, ratio=7.22 > 6.0
        "status": "NEEDS_REVIEW",
        "reasons": ["IRREGULAR_ASPECT_RATIO"],
        "corr": [],
    },
    {
        "id": "27_aspect_ratio_too_tall",
        "raw": "51F-698.81",
        "final": "51F69881",
        "conf": 97.0,
        "min_c": 95.0,
        "box": (100, 100, 210, 200),  # width=110, height=100, ratio=1.10 < 1.3
        "status": "NEEDS_REVIEW",
        "reasons": ["IRREGULAR_ASPECT_RATIO"],
        "corr": [],
    },
    {
        "id": "28_detection_fallback_retry",
        "raw": "51F-698.81",
        "final": "51F69881",
        "conf": 96.0,
        "min_c": 94.0,
        "box": (100, 200, 400, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["NO_DETECTION_RETRY"],
        "corr": [],
    },
    {
        "id": "29_aspect_ratio_and_low_conf",
        "raw": "51F-698.81",
        "final": "51F69881",
        "conf": 89.0,
        "min_c": 85.0,
        "box": (50, 100, 700, 190),
        "status": "NEEDS_REVIEW",
        "reasons": ["LOW_CHAR_CONFIDENCE", "IRREGULAR_ASPECT_RATIO"],
        "corr": [],
    },
    # Group 7: Model Disagreement (3 fixtures)
    {
        "id": "30_model_disagreement_digit",
        "raw": "51F-698.81",
        "final": "51F69881",
        "conf": 97.0,
        "min_c": 95.0,
        "box": (100, 200, 400, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["MODEL_DISAGREEMENT"],
        "corr": [],
    },
    {
        "id": "31_model_disagreement_series",
        "raw": "30E-123.45",
        "final": "30E12345",
        "conf": 96.5,
        "min_c": 94.5,
        "box": (100, 200, 400, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["MODEL_DISAGREEMENT"],
        "corr": [],
    },
    {
        "id": "32_model_disagreement_province",
        "raw": "51K-123.45",
        "final": "51K12345",
        "conf": 97.5,
        "min_c": 95.0,
        "box": (100, 200, 400, 300),
        "status": "NEEDS_REVIEW",
        "reasons": ["MODEL_DISAGREEMENT"],
        "corr": [],
    },
    # Group 8: Vehicle Lookup in Database (4 fixtures)
    {
        "id": "33_vehicle_found_active_monthly_ticket",
        "raw": "51K-992.14",
        "final": "51K99214",
        "conf": 98.5,
        "min_c": 96.0,
        "box": (120, 340, 450, 440),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
        "lookup": {
            "vehicle": {
                "id": 101,
                "code": "XE0101",
                "plate_number": "51K99214",
                "vehicle_type": "CAR_UP_TO_9_SEATS",
            },
            "customer": {"id": 201, "full_name": "Nguyen Van A", "phone": "0901234567"},
            "parking_position": {"id": 1, "code": "A-01", "name": "Vi tri A-01"},
            "active_ticket": {
                "id": 501,
                "ticket_code": "TKT-2026-001",
                "start_date": "2026-10-01",
                "end_date": "2026-10-31",
                "is_active": True,
            },
            "open_session": None,
            "is_blacklisted": False,
        },
    },
    {
        "id": "34_vehicle_found_expired_ticket",
        "raw": "30E-123.45",
        "final": "30E12345",
        "conf": 97.8,
        "min_c": 95.5,
        "box": (100, 200, 400, 300),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
        "lookup": {
            "vehicle": {
                "id": 102,
                "code": "XE0102",
                "plate_number": "30E12345",
                "vehicle_type": "CAR_UP_TO_9_SEATS",
            },
            "customer": {"id": 202, "full_name": "Tran Van B", "phone": "0912345678"},
            "parking_position": None,
            "active_ticket": None,
            "open_session": None,
            "is_blacklisted": False,
        },
    },
    {
        "id": "35_vehicle_found_no_ticket",
        "raw": "43A-678.90",
        "final": "43A67890",
        "conf": 99.1,
        "min_c": 98.0,
        "box": (110, 220, 420, 310),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
        "lookup": {
            "vehicle": {
                "id": 103,
                "code": "XE0103",
                "plate_number": "43A67890",
                "vehicle_type": "CAR_UP_TO_9_SEATS",
            },
            "customer": {"id": 203, "full_name": "Le Van C", "phone": "0923456789"},
            "parking_position": None,
            "active_ticket": None,
            "open_session": None,
            "is_blacklisted": False,
        },
    },
    {
        "id": "36_vehicle_found_customer_details",
        "raw": "60A-345.67",
        "final": "60A34567",
        "conf": 96.5,
        "min_c": 94.0,
        "box": (90, 180, 390, 280),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
        "lookup": {
            "vehicle": {
                "id": 104,
                "code": "XE0104",
                "plate_number": "60A34567",
                "vehicle_type": "CAR_UP_TO_9_SEATS",
            },
            "customer": {"id": 204, "full_name": "Pham Thi D", "phone": "0934567890"},
            "parking_position": {"id": 2, "code": "B-05", "name": "Vi tri B-05"},
            "active_ticket": None,
            "open_session": None,
            "is_blacklisted": False,
        },
    },
    # Group 9: Vehicle Not Found & Trigram Suggestions (3 fixtures)
    {
        "id": "37_vehicle_not_found_with_suggestions",
        "raw": "51K-992.14",
        "final": "51K99214",
        "conf": 98.5,
        "min_c": 96.0,
        "box": (120, 340, 450, 440),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
        "lookup": None,
        "suggestions": ["51K99215", "51K99216"],
    },
    {
        "id": "38_vehicle_not_found_empty_suggestions",
        "raw": "14A-555.55",
        "final": "14A55555",
        "conf": 97.0,
        "min_c": 95.0,
        "box": (105, 210, 415, 305),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
        "lookup": None,
        "suggestions": [],
    },
    {
        "id": "39_vehicle_not_found_single_suggestion",
        "raw": "30E-123.45",
        "final": "30E12345",
        "conf": 97.8,
        "min_c": 95.5,
        "box": (100, 200, 400, 300),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
        "lookup": None,
        "suggestions": ["30E12346"],
    },
    # Group 10: Blacklist & Active Open Session (3 fixtures)
    {
        "id": "40_blacklisted_plate",
        "raw": "51F-698.81",
        "final": "51F69881",
        "conf": 98.5,
        "min_c": 96.0,
        "box": (100, 200, 400, 300),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
        "is_bl": True,
    },
    {
        "id": "41_active_open_session",
        "raw": "51F-698.81",
        "final": "51F69881",
        "conf": 98.5,
        "min_c": 96.0,
        "box": (100, 200, 400, 300),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
        "open_sess": {
            "id": 999,
            "session_code": "SSN-2026-0001",
            "entry_time": "2026-10-20T07:30:00Z",
            "entry_gate_code": "GATE-IN-01",
        },
    },
    {
        "id": "42_blacklisted_and_open_session",
        "raw": "51F-698.81",
        "final": "51F69881",
        "conf": 98.5,
        "min_c": 96.0,
        "box": (100, 200, 400, 300),
        "status": "AUTO",
        "reasons": [],
        "corr": [],
        "is_bl": True,
        "open_sess": {
            "id": 1000,
            "session_code": "SSN-2026-0002",
            "entry_time": "2026-10-20T08:00:00Z",
            "entry_gate_code": "GATE-IN-02",
        },
    },
]


def generate_all_fixtures() -> int:
    count = 0
    for spec in FIXTURE_SPECS:
        cand = make_candidate(
            plate_text=spec["raw"],
            plate_norm=spec["final"],
            conf=spec["conf"],
            min_char_c=spec["min_c"],
            box=spec["box"],
        )
        # Bounding box and candidate sync
        payload = make_payload(
            plate_raw=spec["raw"],
            plate_final=spec["final"],
            candidates=[cand],
            best_cand=dict(cand),
            vehicle_lookup=spec.get("lookup"),
            is_blacklisted=spec.get("is_bl", False),
            open_session=spec.get("open_sess"),
            review_status=spec["status"],
            review_reasons=spec["reasons"],
            corrections=spec["corr"],
            suggestions=spec.get("suggestions"),
        )

        # Validate with pure-reference validator before serializing
        ReferenceContractValidator.validate(payload)

        out_path = FIXTURES_DIR / f"{spec['id']}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        count += 1

    return count


if __name__ == "__main__":
    total = generate_all_fixtures()
    print(
        f"Successfully generated and validated {total} golden fixtures in {FIXTURES_DIR}"
    )
