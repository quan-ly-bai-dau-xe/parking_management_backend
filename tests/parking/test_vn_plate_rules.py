"""
Unit and integration tests for Vietnamese License Plate domain rules and metadata.
Validates:
1. Exhaustive classification of all 89 two-digit codes (11..99).
2. Validity of newly added codes: 39 (Đồng Nai), 40 (Hà Nội), 41 (TP.HCM).
3. Motorbike exclusion (SRS v4.1 car-only parking facility).
4. Strict separation of INVALID_FORMAT vs UNKNOWN_PLATE_PATTERN (military, unassigned codes).
5. Synthetic image generation for all 81 valid province codes.
6. Validation against 322 ground-truth Vietnamese dataset rows.
"""

from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from apps.parking.data.vn_plate_rules import (
    AGENCY_CODES,
    NEVER_ISSUED_CODES,
    PROVINCE_CODES,
    SOURCES_LIST,
    VALID_PROVINCE_CODES,
    classify_plate_syntax,
    get_provenance_summary,
    get_province_meta,
    is_valid_province_code,
    is_valid_vietnamese_car_plate,
)


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """Override conftest db fixture: no database needed for domain rules tests."""
    return None


class TestProvinceCodeClassification:
    """Test suite for complete administrative code space 11..99."""

    def test_all_89_codes_present_and_accounted_for(self) -> None:
        """Every integer from 11 to 99 must have deterministic metadata."""
        all_expected_codes = [str(i) for i in range(11, 100)]
        assert len(all_expected_codes) == 89
        for code in all_expected_codes:
            assert code in PROVINCE_CODES, f"Code {code} missing from PROVINCE_CODES"
            meta = PROVINCE_CODES[code]
            assert meta.code == code
            assert meta.status in {"CURRENT", "LEGACY", "AGENCY", "NEVER_ISSUED"}
            assert len(meta.province_name) > 0
            assert meta.provenance in {"VERIFIED", "UNVERIFIED"}

    def test_never_issued_codes_partition(self) -> None:
        """Reserve codes unissued by Ministry of Public Security."""
        expected_never_issued = {"13", "42", "44", "45", "46", "87", "91", "96"}
        assert frozenset(expected_never_issued) == NEVER_ISSUED_CODES
        for code in NEVER_ISSUED_CODES:
            assert is_valid_province_code(code) is False
            meta = get_province_meta(code)
            assert meta is not None
            assert meta.status == "NEVER_ISSUED"
            assert meta.provenance == "VERIFIED"
            assert "Chưa cấp" in meta.province_name

    def test_agency_code_partition(self) -> None:
        """Agency code 80 managed by Cục Cảnh sát giao thông."""
        assert frozenset({"80"}) == AGENCY_CODES
        assert is_valid_province_code("80") is True
        meta = get_province_meta("80")
        assert meta is not None
        assert meta.status == "AGENCY"
        assert meta.provenance == "VERIFIED"

    def test_valid_province_codes_count(self) -> None:
        """Union of CURRENT (50), LEGACY (30), and AGENCY (1) must equal 81 codes."""
        current_codes = [c for c, m in PROVINCE_CODES.items() if m.status == "CURRENT"]
        legacy_codes = [c for c, m in PROVINCE_CODES.items() if m.status == "LEGACY"]
        agency_codes = [c for c, m in PROVINCE_CODES.items() if m.status == "AGENCY"]
        never_codes = [
            c for c, m in PROVINCE_CODES.items() if m.status == "NEVER_ISSUED"
        ]
        assert len(current_codes) == 50
        assert len(legacy_codes) == 30
        assert len(agency_codes) == 1
        assert len(never_codes) == 8
        assert len(VALID_PROVINCE_CODES) == 81
        assert (
            frozenset(PROVINCE_CODES.keys() - NEVER_ISSUED_CODES)
            == VALID_PROVINCE_CODES
        )

    def test_new_codes_39_40_41_are_valid_and_current(self) -> None:
        """Circular 79/2024 and 51/2025 allocations for Đồng Nai, Hà Nội, TP.HCM."""
        for code, expected_name in [
            ("39", "Đồng Nai"),
            ("40", "Hà Nội"),
            ("41", "TP. Hồ Chí Minh"),
        ]:
            assert is_valid_province_code(code) is True
            meta = get_province_meta(code)
            assert meta is not None
            assert meta.status == "CURRENT"
            assert meta.provenance == "VERIFIED"
            assert meta.province_name == expected_name

    def test_module_level_legal_basis(self) -> None:
        """Statutory legal basis citations must be present and well-formed."""
        from apps.parking.data.vn_plate_rules import LEGAL_BASIS

        assert len(LEGAL_BASIS) >= 4
        assert "CIRCULAR_79_2024" in LEGAL_BASIS
        assert "CIRCULAR_51_2025" in LEGAL_BASIS
        assert "CIRCULAR_24_2023" in LEGAL_BASIS
        assert "DECREE_13_2023" in LEGAL_BASIS
        for entry in LEGAL_BASIS.values():
            assert entry["url"].startswith("https://vanban.chinhphu.vn/")
            assert len(entry["docid"]) > 0

    def test_sources_list_metadata(self) -> None:
        """Audit trail citations must have valid URLs and recent access date."""
        assert len(SOURCES_LIST) >= 4
        for src in SOURCES_LIST:
            assert src["url"].startswith("https://")
            assert src["access_date"] == "2026-10-19"

    def test_get_provenance_summary_contract(self) -> None:
        """Helper get_provenance_summary must return strict partition of all 89 codes."""
        summary = get_provenance_summary()
        assert isinstance(summary, dict)
        assert set(summary.keys()) == {"verified", "unverified"}

        verified_codes = summary["verified"]
        unverified_codes = summary["unverified"]
        assert isinstance(verified_codes, list)
        assert isinstance(unverified_codes, list)

        # Sorted invariants
        assert verified_codes == sorted(verified_codes)
        assert unverified_codes == sorted(unverified_codes)

        # Mutually exclusive and collectively exhaustive partition
        set_verified = set(verified_codes)
        set_unverified = set(unverified_codes)
        assert len(set_verified & set_unverified) == 0, (
            "Overlap between verified and unverified!"
        )
        assert len(set_verified | set_unverified) == 89, "Total codes must equal 89"

        # Verify against PROVINCE_CODES actual provenance metadata
        for c in verified_codes:
            assert PROVINCE_CODES[c].provenance == "VERIFIED"
        for c in unverified_codes:
            assert PROVINCE_CODES[c].provenance == "UNVERIFIED"

    def test_statutory_provenance_partition(self) -> None:
        """Confirm ground-truth verified codes per Appendix 02 of Circular 51/2025/TT-BCA."""
        for code, meta in PROVINCE_CODES.items():
            assert meta.provenance == "VERIFIED", f"Code {code} expected VERIFIED"

    def test_legal_basis_article_citations(self) -> None:
        """LEGAL_BASIS must contain accurate article citations for Circulars 79, 51, and 24."""
        from apps.parking.data.vn_plate_rules import LEGAL_BASIS

        assert "articles" in LEGAL_BASIS["CIRCULAR_79_2024"]
        assert "Điều 37" in LEGAL_BASIS["CIRCULAR_79_2024"]["articles"]
        assert "Điều 39" in LEGAL_BASIS["CIRCULAR_79_2024"]["articles"]
        assert "Phụ lục 02" in LEGAL_BASIS["CIRCULAR_79_2024"]["articles"]

        assert "articles" in LEGAL_BASIS["CIRCULAR_51_2025"]
        assert "Phụ lục 02" in LEGAL_BASIS["CIRCULAR_51_2025"]["articles"]

        assert "articles" in LEGAL_BASIS["CIRCULAR_24_2023"]
        assert "Điều 37" in LEGAL_BASIS["CIRCULAR_24_2023"]["articles"]
        assert "Phụ lục 02" in LEGAL_BASIS["CIRCULAR_24_2023"]["articles"]


class TestPlateSyntaxClassification:
    """Test suite for syntax validation and classification."""

    def test_valid_civilian_car_plates(self) -> None:
        """Civilian cars with single-letter series."""
        valid_samples = [
            "51K99214",
            "30H12345",
            "29A5678",
            "40A12345",
            "39B12345",
            "41C12345",
            "14A99999",
            "80A12345",
        ]
        for plate in valid_samples:
            assert is_valid_vietnamese_car_plate(plate) is True
            cat, msg = classify_plate_syntax(plate)
            assert cat == "VALID", f"Plate {plate} failed: {msg}"

    def test_valid_dual_letter_special_car_plates(self) -> None:
        """Foreign investment, diplomatic, and special authority car plates."""
        valid_special = [
            "50LD04411",
            "29DA00123",
            "80NG12345",
            "30QT12345",
            "51CV12345",
            "51NN12345",
            "29KT01234",
            "80CD00123",
        ]
        for plate in valid_special:
            assert is_valid_vietnamese_car_plate(plate) is True
            cat, msg = classify_plate_syntax(plate)
            assert cat == "VALID", f"Special plate {plate} failed: {msg}"

    def test_disallowed_series_letters_return_unknown_pattern(self) -> None:
        """Letters I, J, O, Q, R, W are excluded from civilian single-letter series."""
        disallowed = [
            "51J12345",
            "51W12345",
            "51R12345",
            "51I12345",
            "51O12345",
            "51Q12345",
        ]
        for plate in disallowed:
            assert is_valid_vietnamese_car_plate(plate) is False
            cat, msg = classify_plate_syntax(plate)
            assert cat == "UNKNOWN_PLATE_PATTERN", f"Plate {plate} got: {cat} ({msg})"

    def test_military_plates_classified_as_unknown_pattern(self) -> None:
        """Military plates starting with 2 letters and 4-5 digits."""
        military_samples = ["TM1234", "QA5678", "TC12345", "KP9999"]
        for plate in military_samples:
            assert is_valid_vietnamese_car_plate(plate) is False
            cat, msg = classify_plate_syntax(plate)
            assert cat == "UNKNOWN_PLATE_PATTERN", f"Military plate {plate} got: {cat}"
            assert "military" in msg.lower()

    def test_motorbike_syntax_classified_as_invalid_format(self) -> None:
        """Motorbike plates are rejected because this facility is car-only (SRS v4.1)."""
        motorbike_samples = ["29B199988", "59P212345"]
        for plate in motorbike_samples:
            assert is_valid_vietnamese_car_plate(plate) is False
            cat, msg = classify_plate_syntax(plate)
            assert cat == "INVALID_FORMAT", (
                f"Motorbike plate {plate} got: {cat} ({msg})"
            )

    def test_never_issued_province_codes_return_unknown_pattern(self) -> None:
        """Plausible car format but with reserved unissued province code."""
        never_issued_plates = ["13A12345", "42B12345", "87C12345", "96A12345"]
        for plate in never_issued_plates:
            assert is_valid_vietnamese_car_plate(plate) is False
            cat, msg = classify_plate_syntax(plate)
            assert cat == "UNKNOWN_PLATE_PATTERN", f"Plate {plate} got: {cat}"

    def test_structural_failures_return_invalid_format(self) -> None:
        """Non-alphanumeric, too short, too long, or letters where digits must be."""
        garbage_samples = [
            "",
            "51",
            "51A",
            "51A1",
            "51A1234567",  # 10 chars
            "5DZ1630",  # letter in province code
            "51A-123.45",  # un-normalized punctuation
            "51A123#5",  # invalid character
        ]
        for plate in garbage_samples:
            assert is_valid_vietnamese_car_plate(plate) is False
            cat, _ = classify_plate_syntax(plate)
            assert cat == "INVALID_FORMAT", f"Garbage plate '{plate}' got: {cat}"

    @pytest.mark.parametrize(
        "plate_norm,description",
        [
            ("51K9921\u09ea", "Bengali digit 4 (\u09ea) in civilian plate tail"),
            ("30H1234\u0660", "Arabic-Indic digit 0 (\u0660) in civilian plate tail"),
            (
                "40A123\u06f15",
                "Extended Arabic-Indic / Persian digit 1 (\u06f1) in civilian plate tail",
            ),
            ("39B1234\uff11", "Fullwidth digit 1 (\uff11) in civilian plate tail"),
            ("50LD0441\u09ea", "Bengali digit 4 (\u09ea) in dual-letter series tail"),
            ("29DA0012\uff11", "Fullwidth digit 1 (\uff11) in dual-letter series tail"),
            ("80NG1234\u0660", "Diplomatic NG with Arabic-Indic digit 0"),
            ("\u0665\u0661K99214", "Arabic-Indic digits in province code prefix"),
            ("\uff15\uff11A12345", "Fullwidth digits in province code prefix"),
            ("TM123\u09ea", "Bengali digit in military plate structure"),
            ("13A1234\u09ea", "Bengali digit in never-issued province plate"),
        ],
    )
    def test_non_ascii_unicode_digits_rejected(
        self, plate_norm: str, description: str
    ) -> None:
        """Non-ASCII Unicode digits must be strictly rejected as INVALID_FORMAT."""
        assert is_valid_vietnamese_car_plate(plate_norm) is False
        cat, msg = classify_plate_syntax(plate_norm)
        assert cat == "INVALID_FORMAT", f"{description} got '{cat}' ({msg})"

    def test_non_ascii_letters_and_military_strictness(self) -> None:
        """Verify that homoglyphs, non-ASCII letters, and lowercase military plates are rejected."""
        # Cyrillic homoglyphs (looks like Latin A \u0410, C \u0421, etc.)
        assert is_valid_vietnamese_car_plate("51\u041012345") is False
        cat_cyrillic, _ = classify_plate_syntax("51\u041012345")
        assert cat_cyrillic == "INVALID_FORMAT"

        # Greek homoglyphs (looks like Latin A \u0391, B \u0392, etc.)
        assert is_valid_vietnamese_car_plate("51\u039112345") is False
        cat_greek, _ = classify_plate_syntax("51\u039112345")
        assert cat_greek == "INVALID_FORMAT"

        # Military plates must be uppercase ASCII only
        cat_lower_mil, _ = classify_plate_syntax("tm1234")
        assert cat_lower_mil == "INVALID_FORMAT"

        cat_mil_non_ascii, _ = classify_plate_syntax("TM123\u09ea")
        assert cat_mil_non_ascii == "INVALID_FORMAT"


class TestSyntheticImageScanGeneration:
    """Test generating synthetic plate images across all 81 valid province codes."""

    def test_synthetic_plate_generation_for_all_valid_codes(self) -> None:
        """Generate a synthetic plate for all 81 valid codes and verify classification."""
        for code in sorted(VALID_PROVINCE_CODES):
            plate = f"{code}A12345"
            assert is_valid_vietnamese_car_plate(plate) is True
            cat, _ = classify_plate_syntax(plate)
            assert cat == "VALID"

            # Create an in-memory synthetic plate image with Pillow
            img = Image.new("RGB", (300, 100), color=(255, 255, 255))
            draw = ImageDraw.Draw(img)
            draw.rectangle([(2, 2), (297, 97)], outline=(0, 0, 0), width=3)
            draw.text((20, 35), plate, fill=(0, 0, 0))

            buf = io.BytesIO()
            img.save(buf, format="JPEG")
            raw_bytes = buf.getvalue()
            assert len(raw_bytes) > 0
            assert raw_bytes[:2] == b"\xff\xd8"  # Valid JPEG magic bytes


@pytest.mark.host
class TestParquetGroundTruthDataset:
    """Evaluation against the 322 ground-truth Vietnamese dataset rows."""

    @classmethod
    def get_parquet_path(cls) -> Path | None:
        for env_var in ("PARQUET_PATH", "PARKING_DATASET_PATH", "DATASET_PATH"):
            val = os.getenv(env_var)
            if val and Path(val).is_file():
                return Path(val)
        hub_root = (
            Path(os.environ["HUGGINGFACE_HUB_CACHE"])
            if os.getenv("HUGGINGFACE_HUB_CACHE")
            else (
                Path(os.environ["HF_HOME"]) / "hub"
                if os.getenv("HF_HOME")
                else Path.home() / ".cache" / "huggingface" / "hub"
            )
        )
        dataset_repo_dir = (
            hub_root / "datasets--sonnetechnology--license-plate-text-recognition-full"
        )
        if dataset_repo_dir.is_dir():
            candidates = list(
                dataset_repo_dir.glob("snapshots/**/data/*.parquet")
            ) or list(dataset_repo_dir.glob("**/*.parquet"))
            if candidates:
                return candidates[0]
        return None

    def test_parquet_dataset_accuracy_and_dirty_label(self) -> None:
        """Assert >= 99.6% valid car plates (321/322) and isolate dirty row 102."""
        parquet_path = self.get_parquet_path()
        if not parquet_path or not parquet_path.exists():
            pytest.skip("Ground-truth parquet dataset file not present in local cache.")

        import re

        pq = pytest.importorskip("pyarrow.parquet")

        table = pq.read_table(str(parquet_path))
        vn_plates: list[str] = []
        for i in range(len(table)):
            target_val = table["target"][i].as_py()
            if (
                target_val
                and len(target_val) > 0
                and re.match(r"^\d{2}[A-Z]", target_val[0])
            ):
                vn_plates.append(target_val[0])

        assert len(vn_plates) == 322, f"Expected 322 rows, got {len(vn_plates)}"

        valid_count = 0
        invalid_rows = []

        for idx, plate_raw in enumerate(vn_plates):
            norm = re.sub(r"[^A-Z0-9]", "", str(plate_raw).upper())
            if is_valid_vietnamese_car_plate(norm):
                valid_count += 1
            else:
                invalid_rows.append((idx, plate_raw, norm))

        # Expected: exactly 321 valid, 1 dirty label
        assert valid_count == 321, f"Expected 321 valid rows, got {valid_count}"
        assert len(invalid_rows) == 1
        dirty_idx, dirty_raw, dirty_norm = invalid_rows[0]
        assert dirty_raw == "51F-222611"
        assert dirty_norm == "51F222611"
        assert len(dirty_norm) == 9  # 6 digits following single letter series
        cat, msg = classify_plate_syntax(dirty_norm)
        assert cat == "INVALID_FORMAT"

    def test_non_car_dual_letter_series_return_unknown_pattern(self) -> None:
        """Non-car / restricted series (MK, MD, RM, HC) must return UNKNOWN_PLATE_PATTERN."""
        non_car_series = ["29MK12345", "30MD12345", "51RM12345", "29HC12345"]
        for plate in non_car_series:
            assert is_valid_vietnamese_car_plate(plate) is False
            cat, _ = classify_plate_syntax(plate)
            assert cat == "UNKNOWN_PLATE_PATTERN"


class TestObservabilityHelpers:
    """Unit tests for Standard 6 correlation ID and log privacy helpers."""

    def test_resolve_request_id_preserves_valid_header_and_generates_uuid(self) -> None:
        """Valid X-Request-ID is preserved; missing or invalid values generate UUID hex."""
        from types import SimpleNamespace

        from apps.parking.views.scans import format_plate_for_log, resolve_request_id

        req_valid = SimpleNamespace(headers={"X-Request-ID": "req-scan-trace-001"})
        assert resolve_request_id(req_valid) == "req-scan-trace-001"

        req_invalid = SimpleNamespace(headers={"X-Request-ID": "bad id with spaces!"})
        gen_id = resolve_request_id(req_invalid)
        assert len(gen_id) == 32

        assert format_plate_for_log("51K99214") == "51K***14"
        assert format_plate_for_log(None) is None

        from django.test import override_settings

        with override_settings(PARKING_LOG_MASK_PLATES=False):
            assert format_plate_for_log("51K99214") == "51K99214"
