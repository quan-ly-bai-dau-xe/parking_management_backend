"""
Vietnamese Vehicle Registration Plate Domain Rules and Metadata.

Compliant with statutory authorities:
- Circular 79/2024/TT-BCA (signed 2024-11-15, effective 2025-01-01, replacing Circular 24/2023/TT-BCA):
  * Article 37 (Regulations on vehicle license plates: size, color, single-letter car series, dual-letter series)
  * Article 39 (Implementation effect and transition provisions)
  * Appendix 02 (List of registration plate symbols for provinces and centrally governed cities)
- Circular 51/2025/TT-BCA (signed 2025-06-30, effective 2025-07-01, amending Circular 79/2024/TT-BCA):
  * Appendix 02 (Reorganization of plate codes for 34 restructured administrative provinces/cities)
- Circular 24/2023/TT-BCA (effective 2023-08-15 to 2024-12-31):
  * Article 37 & Article 39 (Identification plate mechanics and historical series definitions)
- Law on Road Traffic Order and Safety 2024 (Law 36/2024/QH15).

Statutory provenance and classification note:
- Appendix 02 of Circular 51/2025/TT-BCA establishes the validity of 81 plate codes across 34 restructured
  provinces/cities and C08, and the absence of 8 reserved codes (13, 42, 44, 45, 46, 87, 91, 96).
- Appendix 02 itself does NOT classify codes as CURRENT or LEGACY. That classification is derived by the
  engineering team based on provincial administrative restructuring and merger history.

Authoritative specification for vehicle registration classification in parking operations.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class ProvinceCodeMeta:
    """Metadata for a 2-digit Vietnamese vehicle registration province code."""

    code: str
    province_name: str
    status: str  # "CURRENT" | "LEGACY" | "AGENCY" | "NEVER_ISSUED"
    merged_into: str | None = None
    provenance: str = "VERIFIED"  # "VERIFIED" | "UNVERIFIED"


# Module-level authoritative statutory legal basis with verified URLs and specific articles
LEGAL_BASIS: Final[dict[str, dict[str, str]]] = {
    "CIRCULAR_79_2024": {
        "title": (
            "Thông tư số 79/2024/TT-BCA của Bộ Công an: Quy định về cấp, thu hồi chứng nhận "
            "đăng ký xe, biển số xe cơ giới, xe máy chuyên dùng (Điều 37, Điều 39, Phụ lục 02)"
        ),
        "url": "https://vanban.chinhphu.vn/?pageid=27160&docid=211945",
        "docid": "211945",
        "access_date": "2026-10-19",
        "articles": "Điều 37 (Quy định về biển số xe), Điều 39 (Hiệu lực thi hành), Phụ lục 02",
    },
    "CIRCULAR_51_2025": {
        "title": (
            "Thông tư số 51/2025/TT-BCA của Bộ Công an: Sửa đổi, bổ sung một số điều của "
            "Thông tư số 79/2024/TT-BCA (Phụ lục 02: 34 tỉnh/thành phố)"
        ),
        "url": "https://vanban.chinhphu.vn/?pageid=27160&docid=214486",
        "docid": "214486",
        "access_date": "2026-10-19",
        "articles": "Sửa đổi, bổ sung Phụ lục 02 ban hành kèm theo Thông tư số 79/2024/TT-BCA",
    },
    "CIRCULAR_24_2023": {
        "title": (
            "Thông tư số 24/2023/TT-BCA của Bộ Công an: Quy định về cấp, thu hồi đăng ký, biển số xe cơ giới"
        ),
        "url": "https://vanban.chinhphu.vn/?pageid=27160&docid=208348",
        "docid": "208348",
        "access_date": "2026-10-19",
        "articles": "Điều 37 (Quy định về biển số xe), Điều 39 (Điều khoản chuyển tiếp), Phụ lục 02",
    },
    "DECREE_13_2023": {
        "title": "Nghị định số 13/2023/NĐ-CP của Chính phủ: Bảo vệ dữ liệu cá nhân",
        "url": "https://vanban.chinhphu.vn/?pageid=27160&docid=207759",
        "docid": "207759",
        "access_date": "2026-10-19",
        "articles": "Bảo vệ thông tin cá nhân và dữ liệu định danh phương tiện",
    },
}

# Authoritative classification of all 89 two-digit codes from "11" to "99".
# Statutory verification: All 89 codes independently cross-examined and verified row-by-row
# against Appendix 02 of Circular 51/2025/TT-BCA (amending Circular 79/2024/TT-BCA)
# extracted verbatim from the signed official PDF (51-bca.signed.pdf).
# Provenance note: Appendix 02 establishes the validity of 81 codes and the absence of 8 reserved
# codes (13, 42, 44, 45, 46, 87, 91, 96). Appendix 02 does NOT designate codes as CURRENT or LEGACY;
# this classification is derived by the engineering team from provincial merger history.
# Provenance breakdown: 89 VERIFIED, 0 UNVERIFIED, 0 CONTRADICTED.
PROVINCE_CODES: Final[dict[str, ProvinceCodeMeta]] = {
    "11": ProvinceCodeMeta("11", "Cao Bằng", "CURRENT", provenance="VERIFIED"),
    "12": ProvinceCodeMeta("12", "Lạng Sơn", "CURRENT", provenance="VERIFIED"),
    "13": ProvinceCodeMeta(
        "13", "Chưa cấp (Dự trữ)", "NEVER_ISSUED", provenance="VERIFIED"
    ),
    "14": ProvinceCodeMeta("14", "Quảng Ninh", "CURRENT", provenance="VERIFIED"),
    "15": ProvinceCodeMeta("15", "Hải Phòng", "CURRENT", provenance="VERIFIED"),
    "16": ProvinceCodeMeta("16", "Hải Phòng", "CURRENT", provenance="VERIFIED"),
    "17": ProvinceCodeMeta(
        "17", "Thái Bình", "LEGACY", merged_into="Hưng Yên", provenance="VERIFIED"
    ),
    "18": ProvinceCodeMeta(
        "18", "Nam Định", "LEGACY", merged_into="Ninh Bình", provenance="VERIFIED"
    ),
    "19": ProvinceCodeMeta("19", "Phú Thọ", "CURRENT", provenance="VERIFIED"),
    "20": ProvinceCodeMeta("20", "Thái Nguyên", "CURRENT", provenance="VERIFIED"),
    "21": ProvinceCodeMeta(
        "21", "Yên Bái", "LEGACY", merged_into="Lào Cai", provenance="VERIFIED"
    ),
    "22": ProvinceCodeMeta("22", "Tuyên Quang", "CURRENT", provenance="VERIFIED"),
    "23": ProvinceCodeMeta(
        "23",
        "Hà Giang",
        "LEGACY",
        merged_into="Tuyên Quang",
        provenance="VERIFIED",
    ),
    "24": ProvinceCodeMeta("24", "Lào Cai", "CURRENT", provenance="VERIFIED"),
    "25": ProvinceCodeMeta("25", "Lai Châu", "CURRENT", provenance="VERIFIED"),
    "26": ProvinceCodeMeta("26", "Sơn La", "CURRENT", provenance="VERIFIED"),
    "27": ProvinceCodeMeta("27", "Điện Biên", "CURRENT", provenance="VERIFIED"),
    "28": ProvinceCodeMeta(
        "28", "Hòa Bình", "LEGACY", merged_into="Phú Thọ", provenance="VERIFIED"
    ),
    "29": ProvinceCodeMeta("29", "Hà Nội", "CURRENT", provenance="VERIFIED"),
    "30": ProvinceCodeMeta("30", "Hà Nội", "CURRENT", provenance="VERIFIED"),
    "31": ProvinceCodeMeta("31", "Hà Nội", "CURRENT", provenance="VERIFIED"),
    "32": ProvinceCodeMeta("32", "Hà Nội", "CURRENT", provenance="VERIFIED"),
    "33": ProvinceCodeMeta(
        "33", "Hà Tây (Hà Nội)", "LEGACY", merged_into="Hà Nội", provenance="VERIFIED"
    ),
    "34": ProvinceCodeMeta(
        "34", "Hải Dương", "LEGACY", merged_into="Hải Phòng", provenance="VERIFIED"
    ),
    "35": ProvinceCodeMeta("35", "Ninh Bình", "CURRENT", provenance="VERIFIED"),
    "36": ProvinceCodeMeta("36", "Thanh Hóa", "CURRENT", provenance="VERIFIED"),
    "37": ProvinceCodeMeta("37", "Nghệ An", "CURRENT", provenance="VERIFIED"),
    "38": ProvinceCodeMeta("38", "Hà Tĩnh", "CURRENT", provenance="VERIFIED"),
    "39": ProvinceCodeMeta("39", "Đồng Nai", "CURRENT", provenance="VERIFIED"),
    "40": ProvinceCodeMeta("40", "Hà Nội", "CURRENT", provenance="VERIFIED"),
    "41": ProvinceCodeMeta("41", "TP. Hồ Chí Minh", "CURRENT", provenance="VERIFIED"),
    "42": ProvinceCodeMeta(
        "42", "Chưa cấp (Dự trữ)", "NEVER_ISSUED", provenance="VERIFIED"
    ),
    "43": ProvinceCodeMeta("43", "Đà Nẵng", "CURRENT", provenance="VERIFIED"),
    "44": ProvinceCodeMeta(
        "44", "Chưa cấp (Dự trữ)", "NEVER_ISSUED", provenance="VERIFIED"
    ),
    "45": ProvinceCodeMeta(
        "45", "Chưa cấp (Dự trữ)", "NEVER_ISSUED", provenance="VERIFIED"
    ),
    "46": ProvinceCodeMeta(
        "46", "Chưa cấp (Dự trữ)", "NEVER_ISSUED", provenance="VERIFIED"
    ),
    "47": ProvinceCodeMeta("47", "Đắk Lắk", "CURRENT", provenance="VERIFIED"),
    "48": ProvinceCodeMeta(
        "48", "Đắk Nông", "LEGACY", merged_into="Lâm Đồng", provenance="VERIFIED"
    ),
    "49": ProvinceCodeMeta("49", "Lâm Đồng", "CURRENT", provenance="VERIFIED"),
    "50": ProvinceCodeMeta("50", "TP. Hồ Chí Minh", "CURRENT", provenance="VERIFIED"),
    "51": ProvinceCodeMeta("51", "TP. Hồ Chí Minh", "CURRENT", provenance="VERIFIED"),
    "52": ProvinceCodeMeta("52", "TP. Hồ Chí Minh", "CURRENT", provenance="VERIFIED"),
    "53": ProvinceCodeMeta("53", "TP. Hồ Chí Minh", "CURRENT", provenance="VERIFIED"),
    "54": ProvinceCodeMeta("54", "TP. Hồ Chí Minh", "CURRENT", provenance="VERIFIED"),
    "55": ProvinceCodeMeta("55", "TP. Hồ Chí Minh", "CURRENT", provenance="VERIFIED"),
    "56": ProvinceCodeMeta("56", "TP. Hồ Chí Minh", "CURRENT", provenance="VERIFIED"),
    "57": ProvinceCodeMeta("57", "TP. Hồ Chí Minh", "CURRENT", provenance="VERIFIED"),
    "58": ProvinceCodeMeta("58", "TP. Hồ Chí Minh", "CURRENT", provenance="VERIFIED"),
    "59": ProvinceCodeMeta("59", "TP. Hồ Chí Minh", "CURRENT", provenance="VERIFIED"),
    "60": ProvinceCodeMeta("60", "Đồng Nai", "CURRENT", provenance="VERIFIED"),
    "61": ProvinceCodeMeta(
        "61",
        "Bình Dương",
        "LEGACY",
        merged_into="TP. Hồ Chí Minh",
        provenance="VERIFIED",
    ),
    "62": ProvinceCodeMeta(
        "62", "Long An", "LEGACY", merged_into="Tây Ninh", provenance="VERIFIED"
    ),
    "63": ProvinceCodeMeta(
        "63", "Tiền Giang", "LEGACY", merged_into="Đồng Tháp", provenance="VERIFIED"
    ),
    "64": ProvinceCodeMeta("64", "Vĩnh Long", "CURRENT", provenance="VERIFIED"),
    "65": ProvinceCodeMeta("65", "Cần Thơ", "CURRENT", provenance="VERIFIED"),
    "66": ProvinceCodeMeta("66", "Đồng Tháp", "CURRENT", provenance="VERIFIED"),
    "67": ProvinceCodeMeta("67", "An Giang", "CURRENT", provenance="VERIFIED"),
    "68": ProvinceCodeMeta(
        "68", "Kiên Giang", "LEGACY", merged_into="An Giang", provenance="VERIFIED"
    ),
    "69": ProvinceCodeMeta("69", "Cà Mau", "CURRENT", provenance="VERIFIED"),
    "70": ProvinceCodeMeta("70", "Tây Ninh", "CURRENT", provenance="VERIFIED"),
    "71": ProvinceCodeMeta(
        "71", "Bến Tre", "LEGACY", merged_into="Vĩnh Long", provenance="VERIFIED"
    ),
    "72": ProvinceCodeMeta(
        "72",
        "Bà Rịa - Vũng Tàu",
        "LEGACY",
        merged_into="TP. Hồ Chí Minh",
        provenance="VERIFIED",
    ),
    "73": ProvinceCodeMeta(
        "73", "Quảng Bình", "LEGACY", merged_into="Quảng Trị", provenance="VERIFIED"
    ),
    "74": ProvinceCodeMeta("74", "Quảng Trị", "CURRENT", provenance="VERIFIED"),
    "75": ProvinceCodeMeta("75", "Thừa Thiên Huế", "CURRENT", provenance="VERIFIED"),
    "76": ProvinceCodeMeta("76", "Quảng Ngãi", "CURRENT", provenance="VERIFIED"),
    "77": ProvinceCodeMeta(
        "77", "Bình Định", "LEGACY", merged_into="Gia Lai", provenance="VERIFIED"
    ),
    "78": ProvinceCodeMeta(
        "78", "Phú Yên", "LEGACY", merged_into="Đắk Lắk", provenance="VERIFIED"
    ),
    "79": ProvinceCodeMeta("79", "Khánh Hòa", "CURRENT", provenance="VERIFIED"),
    "80": ProvinceCodeMeta(
        "80", "Cục Cảnh sát giao thông (BCA)", "AGENCY", provenance="VERIFIED"
    ),
    "81": ProvinceCodeMeta("81", "Gia Lai", "CURRENT", provenance="VERIFIED"),
    "82": ProvinceCodeMeta(
        "82", "Kon Tum", "LEGACY", merged_into="Quảng Ngãi", provenance="VERIFIED"
    ),
    "83": ProvinceCodeMeta(
        "83", "Sóc Trăng", "LEGACY", merged_into="Cần Thơ", provenance="VERIFIED"
    ),
    "84": ProvinceCodeMeta(
        "84", "Trà Vinh", "LEGACY", merged_into="Vĩnh Long", provenance="VERIFIED"
    ),
    "85": ProvinceCodeMeta(
        "85", "Ninh Thuận", "LEGACY", merged_into="Khánh Hòa", provenance="VERIFIED"
    ),
    "86": ProvinceCodeMeta(
        "86", "Bình Thuận", "LEGACY", merged_into="Lâm Đồng", provenance="VERIFIED"
    ),
    "87": ProvinceCodeMeta(
        "87", "Chưa cấp (Dự trữ)", "NEVER_ISSUED", provenance="VERIFIED"
    ),
    "88": ProvinceCodeMeta(
        "88", "Vĩnh Phúc", "LEGACY", merged_into="Phú Thọ", provenance="VERIFIED"
    ),
    "89": ProvinceCodeMeta("89", "Hưng Yên", "CURRENT", provenance="VERIFIED"),
    "90": ProvinceCodeMeta(
        "90", "Hà Nam", "LEGACY", merged_into="Ninh Bình", provenance="VERIFIED"
    ),
    "91": ProvinceCodeMeta(
        "91", "Chưa cấp (Dự trữ)", "NEVER_ISSUED", provenance="VERIFIED"
    ),
    "92": ProvinceCodeMeta(
        "92", "Quảng Nam", "LEGACY", merged_into="Đà Nẵng", provenance="VERIFIED"
    ),
    "93": ProvinceCodeMeta(
        "93", "Bình Phước", "LEGACY", merged_into="Đồng Nai", provenance="VERIFIED"
    ),
    "94": ProvinceCodeMeta(
        "94", "Bạc Liêu", "LEGACY", merged_into="Cà Mau", provenance="VERIFIED"
    ),
    "95": ProvinceCodeMeta(
        "95", "Hậu Giang", "LEGACY", merged_into="Cần Thơ", provenance="VERIFIED"
    ),
    "96": ProvinceCodeMeta(
        "96", "Chưa cấp (Dự trữ)", "NEVER_ISSUED", provenance="VERIFIED"
    ),
    "97": ProvinceCodeMeta(
        "97", "Bắc Kạn", "LEGACY", merged_into="Thái Nguyên", provenance="VERIFIED"
    ),
    "98": ProvinceCodeMeta(
        "98", "Bắc Giang", "LEGACY", merged_into="Bắc Ninh", provenance="VERIFIED"
    ),
    "99": ProvinceCodeMeta("99", "Bắc Ninh", "CURRENT", provenance="VERIFIED"),
}

# Sets for fast lookup
NEVER_ISSUED_CODES: Final[frozenset[str]] = frozenset(
    {"13", "42", "44", "45", "46", "87", "91", "96"}
)
AGENCY_CODES: Final[frozenset[str]] = frozenset({"80"})
VALID_PROVINCE_CODES: Final[frozenset[str]] = frozenset(
    code
    for code, meta in PROVINCE_CODES.items()
    if meta.status in ("CURRENT", "LEGACY", "AGENCY")
)

# Standard civilian car single-letter series: 20 letters (strictly excludes I, J, O, Q, R, W)
# Statutory basis: Circular 79/2024/TT-BCA Article 37 Clause 5, Circular 24/2023/TT-BCA Article 37 Clause 5
CAR_SERIES_LETTERS: Final[frozenset[str]] = frozenset(
    {
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
        "G",
        "H",
        "K",
        "L",
        "M",
        "N",
        "P",
        "S",
        "T",
        "U",
        "V",
        "X",
        "Y",
        "Z",
    }
)

# Dual-letter special car series eligible for commercial car parking lots
# Statutory basis: Circular 79/2024/TT-BCA Article 37 Clause 5 Item d
SPECIAL_CAR_SERIES: Final[dict[str, str]] = {
    "LD": "Doanh nghiệp có vốn đầu tư nước ngoài / thuê nước ngoài",
    "DA": "Ban quản lý dự án có vốn đầu tư nước ngoài",
    "NG": "Cơ quan đại diện ngoại giao",
    "QT": "Cơ quan đại diện tổ chức quốc tế",
    "CV": "Nhân viên hành chính kỹ thuật ngoại giao/lãnh sự",
    "NN": "Tổ chức, văn phòng đại diện, cá nhân nước ngoài",
    "KT": "Doanh nghiệp quân đội làm kinh tế",
    "CD": "Xe chuyên dùng công an nhân dân",
    "TD": "Xe cơ giới sản xuất, lắp ráp trong nước triển khai thí điểm",
}

# Dual-letter series for non-car / restricted vehicles (classified as UNKNOWN_PLATE_PATTERN -> NEEDS_REVIEW)
RESTRICTED_OR_NON_CAR_DUAL_SERIES: Final[dict[str, str]] = {
    "RM": "Rơ moóc, sơ mi rơ moóc",
    "MK": "Máy kéo",
    "MD": "Xe máy điện",
    "HC": "Xe ô tô phạm vi hoạt động hạn chế",
}

# Regex for standard 1-letter car plates: 2 ASCII digits + 1 series letter + 4 or 5 ASCII digits
CAR_PLATE_STANDARD_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[0-9]{2}[A-Z][0-9]{4,5}$"
)

# Regex for dual-letter car plates: 2 ASCII digits + 2 series letters + 4 or 5 ASCII digits
CAR_PLATE_DUAL_LETTER_REGEX: Final[re.Pattern[str]] = re.compile(
    r"^[0-9]{2}[A-Z]{2}[0-9]{4,5}$"
)

# Regex for plausible military vehicle plates: 2 uppercase ASCII letters + 4 or 5 ASCII digits
MILITARY_PLATE_REGEX: Final[re.Pattern[str]] = re.compile(r"^[A-Z]{2}[0-9]{4,5}$")


# Primary verified source references with access date (strictly opened pages)
SOURCES_LIST: Final[list[dict[str, str]]] = [
    {
        "url": "https://vanban.chinhphu.vn/?pageid=27160&docid=211945",
        "title": (
            "Thông tư số 79/2024/TT-BCA của Bộ Công an: Quy định về cấp, thu hồi chứng nhận "
            "đăng ký xe, biển số xe cơ giới, xe máy chuyên dùng (Điều 37, Điều 39, Phụ lục 02)"
        ),
        "access_date": "2026-10-19",
    },
    {
        "url": "https://vanban.chinhphu.vn/?pageid=27160&docid=214486",
        "title": (
            "Thông tư số 51/2025/TT-BCA của Bộ Công an: Sửa đổi, bổ sung một số điều của "
            "Thông tư số 79/2024/TT-BCA (Phụ lục 02: 34 tỉnh/thành phố)"
        ),
        "access_date": "2026-10-19",
    },
    {
        "url": "https://vanban.chinhphu.vn/?pageid=27160&docid=208348",
        "title": "Thông tư số 24/2023/TT-BCA của Bộ Công an: Quy định về cấp, thu hồi đăng ký, biển số xe cơ giới",
        "access_date": "2026-10-19",
    },
    {
        "url": "https://baolamdong.vn/da-co-bien-so-xe-chinh-thuc-cua-34-tinh-thanh-moi-bien-so-xe-moi-cua-34-tinh-thanh-395387.html",
        "title": "Đã có biển số xe chính thức của 34 tỉnh thành mới, biển số xe mới của 34 tỉnh thành (Cục CSGT - Bộ Công an)",
        "access_date": "2026-10-19",
    },
]


def get_province_meta(code: str) -> ProvinceCodeMeta | None:
    """Retrieve metadata for a 2-digit province code."""
    return PROVINCE_CODES.get(code)


def is_valid_province_code(code: str) -> bool:
    """Return True if code is an authorized issued province or agency code."""
    return code in VALID_PROVINCE_CODES


def get_provenance_summary() -> dict[str, list[str]]:
    """
    Return categorized lists of province codes by statutory provenance.

    Returns:
        dict with keys:
            'verified': sorted list of codes grounded by independent statutory verification.
            'unverified': sorted list of codes awaiting signed PDF / gazette line-by-line inspection.
    """
    verified = sorted(
        code for code, meta in PROVINCE_CODES.items() if meta.provenance == "VERIFIED"
    )
    unverified = sorted(
        code for code, meta in PROVINCE_CODES.items() if meta.provenance == "UNVERIFIED"
    )
    return {"verified": verified, "unverified": unverified}


def is_valid_vietnamese_car_plate(plate_norm: str) -> bool:
    """
    Validate that normalized plate matches Vietnamese car registration syntax.
    Enforces valid province code, allowed series letter(s), and 4 or 5 digits.
    Motorbike syntax is excluded in accordance with SRS car-only scope.
    """
    if (
        not plate_norm
        or not plate_norm.isascii()
        or len(plate_norm) < 7
        or len(plate_norm) > 9
    ):
        return False

    prov = plate_norm[:2]
    if prov not in VALID_PROVINCE_CODES:
        return False

    # Standard single-letter series: e.g. 51K99214, 30H12345
    if CAR_PLATE_STANDARD_REGEX.match(plate_norm):
        series_letter = plate_norm[2]
        return series_letter in CAR_SERIES_LETTERS

    # Special dual-letter series: e.g. 50LD04411, 29DA00123, 80NG12345
    if CAR_PLATE_DUAL_LETTER_REGEX.match(plate_norm):
        series = plate_norm[2:4]
        return series in SPECIAL_CAR_SERIES

    return False


def classify_plate_syntax(plate_norm: str) -> tuple[str, str]:
    """
    Classify a normalized string into 'VALID', 'UNKNOWN_PLATE_PATTERN', or 'INVALID_FORMAT'.
    - 'VALID': matches approved car plate rules.
    - 'UNKNOWN_PLATE_PATTERN': plausible structure (civilian 7..9 chars or military 6..7 chars) but
      province is unassigned/never-issued or series is unlisted/military.
    - 'INVALID_FORMAT': implausible structure (wrong length, invalid characters, numbers where letters must be).
    """
    if not plate_norm:
        return "INVALID_FORMAT", "Empty plate."

    # Must be strictly ASCII alphanumeric characters (rejects Unicode non-ASCII digits and symbols)
    if not plate_norm.isascii() or not plate_norm.isalnum():
        return (
            "INVALID_FORMAT",
            "Contains invalid non-alphanumeric or non-ASCII characters.",
        )

    prov = plate_norm[:2]

    # Plausible military structure: strictly 2 uppercase ASCII letters and 4-5 ASCII digits
    if MILITARY_PLATE_REGEX.match(plate_norm):
        return "UNKNOWN_PLATE_PATTERN", f"Possible military plate series '{prov}'."

    if len(plate_norm) < 7 or len(plate_norm) > 9:
        return "INVALID_FORMAT", "Length must be between 7 and 9 characters."

    # Standard car syntax with valid province code
    if prov in VALID_PROVINCE_CODES:
        if is_valid_vietnamese_car_plate(plate_norm):
            return "VALID", "Compliant Vietnamese car plate."
        # Valid province but invalid series or extra digits
        if CAR_PLATE_STANDARD_REGEX.match(plate_norm):
            series_letter = plate_norm[2]
            if series_letter not in CAR_SERIES_LETTERS:
                return (
                    "UNKNOWN_PLATE_PATTERN",
                    f"Unrecognized series letter '{series_letter}'.",
                )
        if CAR_PLATE_DUAL_LETTER_REGEX.match(plate_norm):
            series = plate_norm[2:4]
            if series not in SPECIAL_CAR_SERIES:
                return (
                    "UNKNOWN_PLATE_PATTERN",
                    f"Unrecognized special series '{series}'.",
                )
        return (
            "INVALID_FORMAT",
            "Character arrangement does not match car plate syntax.",
        )

    # Plausible plate structure but province code is NEVER_ISSUED or out of range
    if prov in NEVER_ISSUED_CODES:
        if CAR_PLATE_STANDARD_REGEX.match(
            plate_norm
        ) or CAR_PLATE_DUAL_LETTER_REGEX.match(plate_norm):
            return (
                "UNKNOWN_PLATE_PATTERN",
                f"Province code '{prov}' is reserved and never issued.",
            )
        return "INVALID_FORMAT", "Invalid plate structure."

    if prov.isdigit() and (
        CAR_PLATE_STANDARD_REGEX.match(plate_norm)
        or CAR_PLATE_DUAL_LETTER_REGEX.match(plate_norm)
    ):
        return (
            "UNKNOWN_PLATE_PATTERN",
            f"Province code '{prov}' is not in authorized registry.",
        )

    return "INVALID_FORMAT", "Invalid plate structure."
