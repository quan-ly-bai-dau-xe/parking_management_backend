"""
Adversarial Stress-Testing & Empirical Verification Suite for Vietnamese Plate Rules.

Verifies:
1. Mathematical invariants & provenance partition in apps/parking/data/vn_plate_rules.py
2. Exotic / Unicode inputs (Fullwidth, Arabic-Indic, Bengali, Cyrillic, Greek, Controls, Emojis)
3. Never-issued province codes (NEVER_ISSUED_CODES: 13, 42, 44, 45, 46, 87, 91, 96)
4. Special dual-letter car series & restricted/non-car series & military patterns
5. 100+ Boundary, edge-case, and malformed plate strings
6. Consistency between PROVINCE_CODES[code].provenance and get_provenance_summary()
7. ADR-0007 ONNX verbatim quote and configuration integrity
"""

from __future__ import annotations

from pathlib import Path

import pytest

from apps.parking.data.vn_plate_rules import (
    NEVER_ISSUED_CODES,
    PROVINCE_CODES,
    RESTRICTED_OR_NON_CAR_DUAL_SERIES,
    SPECIAL_CAR_SERIES,
    VALID_PROVINCE_CODES,
    classify_plate_syntax,
    get_provenance_summary,
    get_province_meta,
    is_valid_province_code,
    is_valid_vietnamese_car_plate,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """Override conftest db fixture: no database needed for domain rules tests."""
    return None


class TestMathematicalInvariantsAndProvenance:
    """Verify set theory invariants, partitioning, and provenance consistency."""

    def test_all_89_codes_dense_coverage_and_uniqueness(self) -> None:
        """Every integer from 11 to 99 must exist exactly once in PROVINCE_CODES."""
        expected_codes = [str(i) for i in range(11, 100)]
        assert len(expected_codes) == 89
        assert len(PROVINCE_CODES) == 89
        assert set(PROVINCE_CODES.keys()) == set(expected_codes)

    def test_provenance_summary_mathematical_partition(self) -> None:
        """
        get_provenance_summary() must return a mathematically strict partition:
        1. verified intersect unverified == empty set (no overlap)
        2. verified union unverified == all 89 codes (exhaustiveness)
        3. len(verified) + len(unverified) == 89
        4. Both lists are strictly sorted with zero duplicates
        """
        summary = get_provenance_summary()
        assert isinstance(summary, dict)
        assert set(summary.keys()) == {"verified", "unverified"}

        verified = summary["verified"]
        unverified = summary["unverified"]

        assert isinstance(verified, list)
        assert isinstance(unverified, list)

        assert verified == sorted(verified), "verified list must be sorted ascending"
        assert unverified == sorted(unverified), (
            "unverified list must be sorted ascending"
        )

        assert len(verified) == len(set(verified)), (
            "verified list has duplicate elements"
        )
        assert len(unverified) == len(set(unverified)), (
            "unverified list has duplicate elements"
        )

        set_v = set(verified)
        set_u = set(unverified)

        overlap = set_v & set_u
        assert len(overlap) == 0, (
            f"Violation of mathematical disjointness: overlap={overlap}"
        )

        union_codes = set_v | set_u
        all_expected = {str(i) for i in range(11, 100)}
        assert union_codes == all_expected, (
            f"Missing codes: {all_expected - union_codes}"
        )

        assert len(verified) + len(unverified) == 89
        assert len(verified) == 89, f"Expected 89 verified codes, got {len(verified)}"
        assert len(unverified) == 0, (
            f"Expected 0 unverified codes, got {len(unverified)}"
        )

    def test_provenance_field_bidirectional_consistency(self) -> None:
        """
        Bidirectional invariant between PROVINCE_CODES[code].provenance and get_provenance_summary():
        - code in summary['verified'] <===> meta.provenance == 'VERIFIED'
        - code in summary['unverified'] <===> meta.provenance == 'UNVERIFIED'
        """
        summary = get_provenance_summary()
        verified_set = set(summary["verified"])
        unverified_set = set(summary["unverified"])

        for code, meta in PROVINCE_CODES.items():
            assert meta.provenance in {"VERIFIED", "UNVERIFIED"}, (
                f"Code {code} has invalid provenance state: {meta.provenance}"
            )
            if meta.provenance == "VERIFIED":
                assert code in verified_set, (
                    f"Code {code} is VERIFIED in meta but missing from summary['verified']"
                )
                assert code not in unverified_set
            elif meta.provenance == "UNVERIFIED":
                assert code in unverified_set, (
                    f"Code {code} is UNVERIFIED in meta but missing from summary['unverified']"
                )
                assert code not in verified_set

    def test_province_status_partition_and_validity(self) -> None:
        """
        The 89 codes must partition into CURRENT (50), LEGACY (30), AGENCY (1), NEVER_ISSUED (8).
        VALID_PROVINCE_CODES must strictly equal CURRENT | LEGACY | AGENCY (81 codes).
        """
        status_map: dict[str, list[str]] = {
            "CURRENT": [],
            "LEGACY": [],
            "AGENCY": [],
            "NEVER_ISSUED": [],
        }
        for code, meta in PROVINCE_CODES.items():
            assert meta.status in status_map, (
                f"Code {code} has unknown status: {meta.status}"
            )
            status_map[meta.status].append(code)

        assert len(status_map["CURRENT"]) == 50, (
            f"Expected 50 CURRENT, got {len(status_map['CURRENT'])}"
        )
        assert len(status_map["LEGACY"]) == 30, (
            f"Expected 30 LEGACY, got {len(status_map['LEGACY'])}"
        )
        assert len(status_map["AGENCY"]) == 1, (
            f"Expected 1 AGENCY, got {len(status_map['AGENCY'])}"
        )
        assert len(status_map["NEVER_ISSUED"]) == 8, (
            f"Expected 8 NEVER_ISSUED, got {len(status_map['NEVER_ISSUED'])}"
        )

        expected_valid = (
            set(status_map["CURRENT"])
            | set(status_map["LEGACY"])
            | set(status_map["AGENCY"])
        )
        assert len(VALID_PROVINCE_CODES) == 81
        assert expected_valid == VALID_PROVINCE_CODES

        assert len(VALID_PROVINCE_CODES & NEVER_ISSUED_CODES) == 0

        for code in status_map["LEGACY"]:
            meta = PROVINCE_CODES[code]
            assert meta.merged_into is not None and len(meta.merged_into) > 0, (
                f"Legacy code {code} ({meta.province_name}) missing merged_into target"
            )


class TestNeverIssuedCodesAdversarial:
    """Stress-test the 8 reserved/never-issued province codes."""

    @pytest.mark.parametrize("code", sorted(NEVER_ISSUED_CODES))
    def test_never_issued_codes_behavior(self, code: str) -> None:
        """All never-issued codes must fail validity and return UNKNOWN_PLATE_PATTERN when structure is plausible."""
        assert is_valid_province_code(code) is False
        meta = get_province_meta(code)
        assert meta is not None
        assert meta.status == "NEVER_ISSUED"
        assert meta.provenance == "VERIFIED"
        assert "Chưa cấp" in meta.province_name

        p5 = f"{code}A12345"
        assert is_valid_vietnamese_car_plate(p5) is False
        cat5, msg5 = classify_plate_syntax(p5)
        assert cat5 == "UNKNOWN_PLATE_PATTERN"
        assert f"'{code}'" in msg5 and "never issued" in msg5.lower()

        p4 = f"{code}B9999"
        assert is_valid_vietnamese_car_plate(p4) is False
        cat4, msg4 = classify_plate_syntax(p4)
        assert cat4 == "UNKNOWN_PLATE_PATTERN"
        assert f"'{code}'" in msg4 and "never issued" in msg4.lower()

        p_dual = f"{code}LD01234"
        assert is_valid_vietnamese_car_plate(p_dual) is False
        cat_d, msg_d = classify_plate_syntax(p_dual)
        assert cat_d == "UNKNOWN_PLATE_PATTERN"
        assert f"'{code}'" in msg_d and "never issued" in msg_d.lower()

        assert classify_plate_syntax(f"{code}")[0] == "INVALID_FORMAT"
        assert classify_plate_syntax(f"{code}A")[0] == "INVALID_FORMAT"
        assert classify_plate_syntax(f"{code}12345")[0] == "INVALID_FORMAT"
        assert classify_plate_syntax(f"{code}A1234567")[0] == "INVALID_FORMAT"


class TestSpecialAndDualLetterSeries:
    """Validate approved dual-letter car series, restricted dual-letter series, and military syntax."""

    @pytest.mark.parametrize("series", sorted(SPECIAL_CAR_SERIES.keys()))
    def test_all_special_car_series_valid_in_multiple_provinces(
        self, series: str
    ) -> None:
        """Each special series must pass is_valid_vietnamese_car_plate and classify as VALID."""
        sample_provinces = ["29", "51", "80", "39", "40", "41", "43"]
        for prov in sample_provinces:
            plate_5d = f"{prov}{series}12345"
            plate_4d = f"{prov}{series}1234"

            assert is_valid_vietnamese_car_plate(plate_5d) is True
            cat5, _ = classify_plate_syntax(plate_5d)
            assert cat5 == "VALID"

            assert is_valid_vietnamese_car_plate(plate_4d) is True
            cat4, _ = classify_plate_syntax(plate_4d)
            assert cat4 == "VALID"

    @pytest.mark.parametrize("series", sorted(RESTRICTED_OR_NON_CAR_DUAL_SERIES.keys()))
    def test_restricted_or_non_car_dual_series_return_unknown_pattern(
        self, series: str
    ) -> None:
        """RM, MK, MD, HC must be rejected from car validation and return UNKNOWN_PLATE_PATTERN."""
        sample_plates = [f"29{series}12345", f"51{series}1234", f"80{series}99999"]
        for plate in sample_plates:
            assert is_valid_vietnamese_car_plate(plate) is False
            cat, msg = classify_plate_syntax(plate)
            assert cat == "UNKNOWN_PLATE_PATTERN"
            assert series in msg

    @pytest.mark.parametrize("disallowed_letter", ["I", "J", "O", "Q", "R", "W"])
    def test_disallowed_single_letter_series_return_unknown_pattern(
        self, disallowed_letter: str
    ) -> None:
        """Letters I, J, O, Q, R, W in civilian plates must return UNKNOWN_PLATE_PATTERN."""
        plate = f"51{disallowed_letter}12345"
        assert is_valid_vietnamese_car_plate(plate) is False
        cat, msg = classify_plate_syntax(plate)
        assert cat == "UNKNOWN_PLATE_PATTERN"
        assert disallowed_letter in msg

    def test_unregistered_dual_letter_series_return_unknown_pattern(self) -> None:
        """Arbitrary 2-letter series like ZZ, XY, AA on valid province must return UNKNOWN_PLATE_PATTERN."""
        unregistered = ["51ZZ12345", "30AA12345", "29XY12345", "40BB1234"]
        for plate in unregistered:
            assert is_valid_vietnamese_car_plate(plate) is False
            cat, msg = classify_plate_syntax(plate)
            assert cat == "UNKNOWN_PLATE_PATTERN"
            assert "Unrecognized special series" in msg

    def test_military_plate_syntax(self) -> None:
        """Military vehicles (2 uppercase letters + 4-5 digits) return UNKNOWN_PLATE_PATTERN."""
        valid_mil = ["TM1234", "QA5678", "TC12345", "KP9999", "AA1234", "BB56789"]
        for plate in valid_mil:
            assert is_valid_vietnamese_car_plate(plate) is False
            cat, msg = classify_plate_syntax(plate)
            assert cat == "UNKNOWN_PLATE_PATTERN"
            assert "military" in msg.lower()

        invalid_mil = ["tm1234", "TM123", "TM123456", "T11234"]
        for plate in invalid_mil:
            cat, _ = classify_plate_syntax(plate)
            assert cat == "INVALID_FORMAT"


class TestUnicodeAndAdversarialExoticInputs:
    """Stress-test non-ASCII, Unicode homoglyphs, script injections, and malformed characters."""

    @pytest.mark.parametrize(
        "exotic_plate,description",
        [
            ("５１Ａ１２３４５", "Fullwidth plate string"),
            ("51A１２３４５", "Fullwidth digits tail"),
            ("５１A12345", "Fullwidth province code"),
            ("51Ａ12345", "Fullwidth series letter A"),
            ("٥١A12345", "Arabic-Indic province digits"),
            ("51A١٢٣٤٥", "Arabic-Indic digits tail"),
            ("۵۱A12345", "Eastern Arabic-Indic province digits"),
            ("51A۱۲۳۴۵", "Eastern Arabic-Indic digits tail"),
            ("৫১A12345", "Bengali province digits"),
            ("51A১২৩৪৫", "Bengali digits tail"),
            ("५१A12345", "Devanagari province digits"),
            ("51A१२३४५", "Devanagari digits tail"),
            ("51А12345", "Cyrillic letter A (U+0410)"),
            ("51В12345", "Cyrillic letter B (U+0412)"),
            ("51С12345", "Cyrillic letter C (U+0421)"),
            ("51Е12345", "Cyrillic letter E (U+0415)"),
            ("51Н12345", "Cyrillic letter H (U+041D)"),
            ("51Α12345", "Greek letter Alpha (U+0391)"),
            ("51Β12345", "Greek letter Beta (U+0392)"),
            ("51Ε12345", "Greek letter Epsilon (U+0395)"),
            ("51A\u200b12345", "Zero-width space injection"),
            ("51A\u200c12345", "Zero-width non-joiner injection"),
            ("51A\ufeff12345", "Byte order mark (BOM) injection"),
            ("51A12345\x00", "Trailing NULL byte injection"),
            ("\x0051A12345", "Leading NULL byte injection"),
            ("51A\r\n12345", "CRLF injection inside plate"),
            ("51A\t12345", "Tab character inside plate"),
            ("51A12345' OR '1'='1", "SQL injection payload"),
            ("51A12345<script>", "XSS payload"),
            ("51A12345%00", "URL-encoded NULL byte"),
            ("../../51A12345", "Path traversal prefix"),
            ("🚗51A12345", "Leading emoji"),
            ("51A12345🚙", "Trailing emoji"),
            ("51🚗12345", "Emoji replacing series letter"),
            ("51Á12345", "Combining acute accent on ASCII A"),
        ],
    )
    def test_exotic_and_unicode_inputs_strictly_rejected(
        self, exotic_plate: str, description: str
    ) -> None:
        """Exotic characters must never pass car plate validation and must classify as INVALID_FORMAT."""
        assert is_valid_vietnamese_car_plate(exotic_plate) is False
        cat, msg = classify_plate_syntax(exotic_plate)
        assert cat == "INVALID_FORMAT", (
            f"{description} ('{exotic_plate}') got '{cat}': {msg}"
        )


class Test100PlusBoundaryPlates:
    """Comprehensive test harness testing >100 distinct boundary, malformed, and valid corner cases."""

    def test_empty_none_and_whitespace_boundaries(self) -> None:
        """Check empty, whitespace-only, and None handling."""
        assert is_valid_vietnamese_car_plate("") is False
        assert classify_plate_syntax("")[0] == "INVALID_FORMAT"

        assert is_valid_vietnamese_car_plate(None) is False  # type: ignore[arg-type]
        assert classify_plate_syntax(None)[0] == "INVALID_FORMAT"  # type: ignore[arg-type]

        whitespaces = [
            " ",
            "   ",
            "\t",
            "\n",
            "\r\n",
            " 51A12345",
            "51A12345 ",
            "51 A 12345",
            "51A 12345",
        ]
        for ws in whitespaces:
            assert is_valid_vietnamese_car_plate(ws) is False
            assert classify_plate_syntax(ws)[0] == "INVALID_FORMAT"

    def test_length_boundaries_from_0_to_30_characters(self) -> None:
        """Systematically test lengths from 1 to 30 characters."""
        base_valid_7 = "51A1234"
        base_valid_8 = "51A12345"
        base_valid_9 = "50LD12345"

        assert is_valid_vietnamese_car_plate(base_valid_7) is True
        assert classify_plate_syntax(base_valid_7)[0] == "VALID"
        assert is_valid_vietnamese_car_plate(base_valid_8) is True
        assert classify_plate_syntax(base_valid_8)[0] == "VALID"
        assert is_valid_vietnamese_car_plate(base_valid_9) is True
        assert classify_plate_syntax(base_valid_9)[0] == "VALID"

        under_lengths = ["5", "51", "51A", "51A1", "51A12", "51A123"]
        for p in under_lengths:
            assert is_valid_vietnamese_car_plate(p) is False
            cat, msg = classify_plate_syntax(p)
            assert cat == "INVALID_FORMAT", (
                f"Under-length plate '{p}' got {cat} ({msg})"
            )

        p9_single = "51A123456"
        assert is_valid_vietnamese_car_plate(p9_single) is False
        assert classify_plate_syntax(p9_single)[0] == "INVALID_FORMAT"

        over_lengths = [
            "51A1234567",
            "50LD123456",
            "51A12345678",
            "51A123456789",
            "51A" + "1" * 20,
            "51A" + "1" * 50,
        ]
        for p in over_lengths:
            assert is_valid_vietnamese_car_plate(p) is False
            assert classify_plate_syntax(p)[0] == "INVALID_FORMAT"

    def test_motorbike_syntax_adversarial_suite(self) -> None:
        """
        Motorbike patterns (2 digits province + 1 letter + 1 district digit + 5 registration digits = 9 chars,
        with 6 consecutive digits after series letter) must be strictly rejected as INVALID_FORMAT.
        """
        motorbike_plates = [
            "29B112345",
            "59P212345",
            "43C199999",
            "79N212345",
            "99G156789",
            "36B888888",
            "14P112345",
            "60B112345",
            "51F199999",
            "30E211111",
        ]
        for mb in motorbike_plates:
            assert is_valid_vietnamese_car_plate(mb) is False
            cat, msg = classify_plate_syntax(mb)
            assert cat == "INVALID_FORMAT", f"Motorbike plate '{mb}' got {cat} ({msg})"

    def test_punctuation_and_unnormalized_formats(self) -> None:
        """Punctuation marks (hyphens, dots, slashes) must fail validation."""
        punctuated = [
            "51A-123.45",
            "51A-12345",
            "51-A-12345",
            "51A.12345",
            "51A.123.45",
            "51/A/12345",
            "51_A_12345",
            "51A:12345",
            "51A#12345",
            "(51A)12345",
        ]
        for p in punctuated:
            assert is_valid_vietnamese_car_plate(p) is False
            assert classify_plate_syntax(p)[0] == "INVALID_FORMAT"

    def test_out_of_range_province_numbers(self) -> None:
        """Numbers 00..10 and >=100."""
        for oc in ["00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10"]:
            p = f"{oc}A12345"
            assert is_valid_province_code(oc) is False
            assert is_valid_vietnamese_car_plate(p) is False
            cat, msg = classify_plate_syntax(p)
            assert cat == "UNKNOWN_PLATE_PATTERN", f"Code {oc} got {cat} ({msg})"
            assert "not in authorized registry" in msg

        for oc3 in ["100", "001", "999", "050"]:
            p3 = f"{oc3}A12345"
            assert is_valid_vietnamese_car_plate(p3) is False
            assert classify_plate_syntax(p3)[0] == "INVALID_FORMAT"

    def test_all_numeric_and_all_alpha_strings(self) -> None:
        """Strings that are strictly digits or strictly letters."""
        all_numeric = ["1234567", "12345678", "123456789", "511234567", "510000000"]
        for an in all_numeric:
            assert is_valid_vietnamese_car_plate(an) is False
            assert classify_plate_syntax(an)[0] == "INVALID_FORMAT"

        all_alpha = [
            "ABCDEFG",
            "ABCDEFGH",
            "ABCDEFGHI",
            "ABCDEFGHIJ",
            "VIETNAM",
            "PARKING",
        ]
        for aa in all_alpha:
            assert is_valid_vietnamese_car_plate(aa) is False
            cat, _ = classify_plate_syntax(aa)
            assert cat == "INVALID_FORMAT"

    def test_boundary_zero_prefix_numbers(self) -> None:
        """Valid plates with all zeroes or leading zeroes in registration number."""
        zero_plates = [
            "51A00001",
            "30H00000",
            "29A0001",
            "40A00000",
            "50LD00001",
            "80NG00000",
        ]
        for zp in zero_plates:
            assert is_valid_vietnamese_car_plate(zp) is True
            assert classify_plate_syntax(zp)[0] == "VALID"

    def test_exhaustive_all_81_valid_provinces_with_standard_and_dual_series(
        self,
    ) -> None:
        """
        Verify that EVERY SINGLE valid province code (81 total) successfully validates
        with both 4-digit and 5-digit civilian series, as well as LD special series.
        Total checks: 81 * 3 = 243 valid combinations.
        """
        assert len(VALID_PROVINCE_CODES) == 81

        for prov in sorted(VALID_PROVINCE_CODES):
            p_std_5 = f"{prov}A12345"
            p_std_4 = f"{prov}K9999"
            p_ld_5 = f"{prov}LD04411"

            assert is_valid_vietnamese_car_plate(p_std_5) is True, (
                f"Failed for {p_std_5}"
            )
            assert classify_plate_syntax(p_std_5)[0] == "VALID"

            assert is_valid_vietnamese_car_plate(p_std_4) is True, (
                f"Failed for {p_std_4}"
            )
            assert classify_plate_syntax(p_std_4)[0] == "VALID"

            assert is_valid_vietnamese_car_plate(p_ld_5) is True, f"Failed for {p_ld_5}"
            assert classify_plate_syntax(p_ld_5)[0] == "VALID"


class TestAdrAndStatutoryRulesConsistency:
    """Verify ADR-0007 ONNX Runtime configuration quote and statutory rule consistency."""

    def test_adr_0007_onnx_quote_and_config(self) -> None:
        """Verify ADR-0007 contains exact ONNX quote and config, without fabricated snake_case."""
        adr_path = (
            REPO_ROOT
            / "docs"
            / "adr"
            / "0007-backend-service-in-docker-compose-and-plate-ocr-engine.md"
        )
        assert adr_path.exists(), "ADR-0007 file must exist!"
        content = adr_path.read_text(encoding="utf-8")

        expected_quote = (
            "Controls whether additional INTRA or INTER threads spin waiting for work."
        )
        expected_code = (
            'sess_opt.AddConfigEntry("session.intra_op.allow_spinning", "0")'
        )
        bad_snake_case = "session_intra_op_allow_spinning"

        assert expected_quote in content, "ADR-0007 missing verbatim quote!"
        assert expected_code in content, "ADR-0007 missing verbatim code configuration!"
        assert bad_snake_case not in content, (
            "ADR-0007 still contains fabricated snake_case!"
        )
