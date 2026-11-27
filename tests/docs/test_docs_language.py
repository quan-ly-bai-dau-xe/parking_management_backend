# cspell:words CREATEDB dotenv
"""
Automated quality gate for documentation language, clone URL, and configuration integrity (Round 53).

Validates criteria (a) through (g):
(a) Clone repository URL check (github.com/quan-ly-bai-dau-xe/ vs codegym).
(b) DEBUG=True in both options, CORS/CSRF origins in Option 2 .env block.
(c) No CREATE EXTENSION in Option 2 code blocks.
(d) Verification health check ocr_ready has environment qualifier.
(e) Sample accounts table has exactly 3 columns (Role, Email, Phone) matching db/02-seed.sql.
(f) No Vietnamese diacritics outside code blocks in startup span and frontend guide.
(g) Vietnamese strings in guide code blocks exist in apps.core.messages or db/02-seed.sql.

Includes synthetic unit tests verifying that all validators accurately detect intentional defects.
Zero network, zero Docker, zero database, zero .git dependencies.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Repository root directory
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
README_PATH: Path = REPO_ROOT / "README.md"
GUIDE_PATH: Path = REPO_ROOT / "docs" / "guides" / "01-frontend-api-guide.md"
SEED_PATH: Path = REPO_ROOT / "db" / "02-seed.sql"
MESSAGES_PATH: Path = REPO_ROOT / "apps" / "core" / "messages.py"
PERMISSIONS_PATH: Path = REPO_ROOT / "apps" / "core" / "permissions.py"


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """
    Overrides the root conftest fixture to enforce zero database dependency
    for documentation tests.
    """
    return None


# Regex for detecting Vietnamese diacritics
VIETNAMESE_DIACRITICS_PATTERN: re.Pattern[str] = re.compile(
    r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ"
    r"ÀÁẠẢÃÂẦẤẬẨẪĂẰẮẶẲẴÈÉẸẺẼÊỀẾỆỂỄÌÍỊỈĨÒÓỌỎÕÔỒỐỘỔỖƠỜỚỢỞỠÙÚỤỦŨƯỪỨỰỬỮỲÝỴỶỸĐ]"
)

# Explicit short allowlist for permissible data values with Vietnamese diacritics.
# Each entry maps the allowed token to its explicit reason (seed sample person names from db/02-seed.sql).
ALLOWED_VIETNAMESE_WORDS: dict[str, str] = {
    "Trịnh": "Sample customer surname in db/02-seed.sql (Trịnh Xuân Trường, KH0001)",
    "Xuân": "Sample customer middle name in db/02-seed.sql (Trịnh Xuân Trường, KH0001)",
    "Trường": "Sample customer given name in db/02-seed.sql (Trịnh Xuân Trường, KH0001)",
    "Hoàng": "Sample manager surname in db/02-seed.sql (Hoàng Đình Khang, NV001)",
    "Đình": "Sample manager middle name in db/02-seed.sql (Hoàng Đình Khang, NV001)",
    "Khang": "Sample manager given name in db/02-seed.sql (Hoàng Đình Khang, NV001)",
    "Lương": "Sample employee surname in db/02-seed.sql (Lương Thị Mai Phương, NV002)",
    "Mai": "Sample employee middle name in db/02-seed.sql (Lương Thị Mai Phương, NV002)",
    "Phương": "Sample employee given name in db/02-seed.sql (Lương Thị Mai Phương, NV002)",
}

# Explicit allowlist for composed/formatted Vietnamese strings appearing inside code blocks
# that are dynamically generated at runtime. Each entry maps the exact string literal to
# an explicit citation of the source file and line generating it.
ALLOWED_CODE_BLOCK_VIETNAMESE_STRINGS: dict[str, str] = {
    "Tầng B1 - Zone A - A-06": (
        "Composed slot display string generated at runtime by "
        "apps.parking.serializers.sessions.SessionDetailSerializer.get_slot_display "
        "(apps/parking/serializers/sessions.py:175)"
    ),
    "5 ngày 9 giờ 32 phút": (
        "Formatted duration string generated at runtime by "
        "apps.parking.selectors.sessions.format_duration_text "
        "(apps/parking/selectors/sessions.py:37)"
    ),
    "0 giây": (
        "Zero-duration string generated at runtime by "
        "apps.parking.selectors.sessions.format_duration_text "
        "(apps/parking/selectors/sessions.py:45)"
    ),
}


# =============================================================================
# Extraction Helpers (Zero Network, Zero Docker, Zero Database, Zero .git)
# =============================================================================


def read_file_text(path: Path) -> str:
    """Reads UTF-8 text from a repository file."""
    return path.read_text(encoding="utf-8")


def get_all_guide_paths(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Returns the main index guide and all split topic guides under docs/guides/frontend-api/."""
    index_file = repo_root / "docs" / "guides" / "01-frontend-api-guide.md"
    split_dir = repo_root / "docs" / "guides" / "frontend-api"
    split_files = sorted(split_dir.glob("*.md")) if split_dir.exists() else []
    return [index_file, *split_files]


def get_startup_span_text(readme_text: str) -> str:
    """
    Extracts the start-up portion of README.md Section 3:
    From '### Choose how to run the backend' (or '<summary>Choose how to run the backend' in collapsible README)
    up to but excluding '### Step 5.1: Purge Orphan Scan Images' (or '### Step 8:').
    """
    start_match = re.search(
        r"^(?:###\s+|<summary>)(?:Choose how to run the backend|Chọn cách chạy|Step 1:\s+Environment Configuration)",
        readme_text,
        flags=re.MULTILINE,
    )
    if not start_match:
        raise ValueError("Could not find start of start-up span in README.md")

    start_idx = start_match.start()

    end_match = re.search(
        r"^(?:###\s+|<summary>)(?:Step 5\.1:\s+Purge Orphan Scan Images|Step 8:\s+Interactive API Documentation)",
        readme_text[start_idx:],
        flags=re.MULTILINE,
    )
    if not end_match:
        raise ValueError("Could not find end of start-up span in README.md")

    end_idx = start_idx + end_match.start()
    return readme_text[start_idx:end_idx]


def get_option_block(readme_text: str, option_num: int) -> str | None:
    """
    Extracts the block of Option 1 or Option 2 from its level-3 heading or summary
    to the next level-3 heading or details block.
    """
    if option_num == 1:
        pattern = r"^(?:###\s+|<summary>)(?:Option\s+1|Cách\s+1)\b.*$"
    elif option_num == 2:
        pattern = r"^(?:###\s+|<summary>)(?:Option\s+2|Cách\s+2)\b.*$"
    else:
        raise ValueError(f"Invalid option number: {option_num}")

    match = re.search(pattern, readme_text, flags=re.MULTILINE | re.IGNORECASE)
    if not match:
        return None

    start_idx = match.start()
    next_heading = re.search(
        r"^(?:###\s+|<details\b|</details>)",
        readme_text[match.end() :],
        flags=re.MULTILINE,
    )
    if next_heading:
        end_idx = match.end() + next_heading.start()
        return readme_text[start_idx:end_idx]
    return readme_text[start_idx:]


def get_verification_block(readme_text: str) -> str | None:
    """
    Extracts the shared verification section block from its level-3 heading or summary
    to the next level-3 heading or details block.
    """
    pattern = r"^(?:###\s+|<summary>)(?:Verify the backend and try a login \(both options\)|Kiểm tra backend và đăng nhập thử \(dùng chung\)).*$"
    match = re.search(pattern, readme_text, flags=re.MULTILINE | re.IGNORECASE)
    if not match:
        return None

    start_idx = match.start()
    next_heading = re.search(
        r"^(?:###\s+|<details\b|</details>)",
        readme_text[match.end() :],
        flags=re.MULTILINE,
    )
    if next_heading:
        end_idx = match.end() + next_heading.start()
        return readme_text[start_idx:end_idx]
    return readme_text[start_idx:]


def extract_fenced_code_blocks_with_lines(text: str) -> list[tuple[int, int, str]]:
    """
    Extracts all fenced code blocks from markdown text, supporting indented blocks.
    Returns a list of tuples: (block_index_1_based, start_line_in_file_1_based, block_content).
    """
    pattern = re.compile(
        r"^[ \t]*```[^\n]*\r?\n([\s\S]*?)^[ \t]*```[^\n]*$",
        re.MULTILINE,
    )
    blocks: list[tuple[int, int, str]] = []
    for idx, match in enumerate(pattern.finditer(text), 1):
        start_line = text[: match.start(1)].count("\n") + 1
        blocks.append((idx, start_line, match.group(1)))
    return blocks


def extract_fenced_code_blocks(text: str) -> list[str]:
    """Extracts all fenced code blocks (```...```) from markdown text."""
    return [b[2] for b in extract_fenced_code_blocks_with_lines(text)]


def extract_env_code_blocks(text: str) -> list[str]:
    """
    Extracts fenced code blocks containing environment variable definitions
    (tagged with env/dotenv/bash or containing KEY=VALUE lines).
    """
    candidates = extract_fenced_code_blocks(text)
    env_blocks: list[str] = []
    for cb in candidates:
        if re.search(r"^[A-Z][A-Z0-9_]{2,}\s*=", cb, flags=re.MULTILINE):
            env_blocks.append(cb)
    return env_blocks


def extract_markdown_tables(text: str) -> list[list[list[str]]]:
    """
    Extracts all markdown tables from text as a list of tables, where each
    table is a list of rows, and each row is a list of trimmed cell strings.
    Excludes delimiter rows (e.g. |---|---|).
    """
    tables: list[list[list[str]]] = []
    current_table: list[list[str]] = []
    in_table = False

    for line in text.splitlines():
        line_str = line.strip()
        if line_str.startswith("|") and line_str.endswith("|"):
            cells = [c.strip() for c in line_str.split("|")[1:-1]]
            # Check if delimiter row
            if all(re.match(r"^:?-+:?$", c) for c in cells):
                continue
            if not in_table:
                in_table = True
                current_table = [cells]
            else:
                current_table.append(cells)
        else:
            if in_table:
                if len(current_table) >= 2:
                    tables.append(current_table)
                current_table = []
                in_table = False

    if in_table and len(current_table) >= 2:
        tables.append(current_table)

    return tables


def get_authorized_message_catalog(repo_root: Path = REPO_ROOT) -> set[str]:
    """
    Derives authorized message strings from apps/core/messages.py, permissions,
    and search serializer validation messages.
    Pure text parsing — zero Django imports, zero database access.
    """
    catalog: set[str] = set()

    messages_file = repo_root / "apps" / "core" / "messages.py"
    if messages_file.exists():
        text = messages_file.read_text(encoding="utf-8")
        for match in re.finditer(r'"((?:MSG|PROP)-[^"]+)"\s*:\s*"([^"]+)"', text):
            catalog.add(match.group(2))

    permissions_file = repo_root / "apps" / "core" / "permissions.py"
    if permissions_file.exists():
        text = permissions_file.read_text(encoding="utf-8")
        for match in re.finditer(r'message\s*=\s*"([^"]+)"', text):
            catalog.add(match.group(1))

    search_serializer_file = (
        repo_root / "apps" / "parking" / "serializers" / "search.py"
    )
    if search_serializer_file.exists():
        text = search_serializer_file.read_text(encoding="utf-8")
        for match in re.finditer(r'field\s*:\s*"([^"]+)"', text):
            catalog.add(match.group(1))

    return catalog


def get_authorized_seed_strings(seed_file: Path = SEED_PATH) -> set[str]:
    """
    Extracts all single-quoted text values from db/02-seed.sql after stripping SQL comments.
    Pure text parsing — zero database access.
    """
    if not seed_file.exists():
        return set()
    text = seed_file.read_text(encoding="utf-8")
    no_comments = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("--")
    )
    raw_strings = set(re.findall(r"'([^'\\]*(?:\\.[^'\\]*)*)'", no_comments))
    expanded: set[str] = set(raw_strings)
    for s in raw_strings:
        for part in s.split(" - "):
            expanded.add(part.strip())
    return expanded


def get_authorized_apps_strings(repo_root: Path = REPO_ROOT) -> set[str]:
    """
    Extracts all Vietnamese string literals defined in apps/**/*.py.
    Pure text parsing — zero Django imports, zero database access.
    """
    catalog: set[str] = set()
    apps_dir = repo_root / "apps"
    if not apps_dir.exists():
        return catalog

    for py_file in apps_dir.rglob("*.py"):
        try:
            text = py_file.read_text(encoding="utf-8")
        except Exception:
            continue
        for m in re.finditer(r'"([^"\\]*(?:\\.[^"\\]*)*)"', text):
            val = m.group(1)
            if VIETNAMESE_DIACRITICS_PATTERN.search(val):
                catalog.add(val)
        for m in re.finditer(r"'([^'\\]*(?:\\.[^'\\]*)*)'", text):
            val = m.group(1)
            if VIETNAMESE_DIACRITICS_PATTERN.search(val):
                catalog.add(val)
    return catalog


# =============================================================================
# Invariant Validator Logic Functions
# =============================================================================


def validate_req_a_clone_urls(readme_text: str, guide_text: str) -> list[str]:
    """
    Validates criterion (a):
    README.md contains 'github.com/quan-ly-bai-dau-xe/parking_management_backend'
    and neither README.md nor docs/guides/01-frontend-api-guide.md contains 'github.com/codegym/'.
    """
    violations: list[str] = []
    if "github.com/quan-ly-bai-dau-xe/parking_management_backend" not in readme_text:
        violations.append(
            "Authoritative repository clone URL 'github.com/quan-ly-bai-dau-xe/parking_management_backend' not found in README.md"
        )
    if "github.com/codegym/" in readme_text:
        violations.append("Found legacy 'github.com/codegym/' clone URL in README.md")
    if "github.com/codegym/" in guide_text:
        violations.append(
            "Found legacy 'github.com/codegym/' clone URL in docs/guides/01-frontend-api-guide.md"
        )
    return violations


def validate_req_b_env_code_blocks(readme_text: str) -> list[str]:
    """
    Validates criterion (b):
    The .env code block of EACH option contains DEBUG=True,
    and Option 2 also contains CORS_ALLOWED_ORIGINS and CSRF_TRUSTED_ORIGINS.
    """
    violations: list[str] = []
    opt1 = get_option_block(readme_text, 1)
    if not opt1:
        return ["Option 1 block not found in README.md"]
    opt2 = get_option_block(readme_text, 2)
    if not opt2:
        return ["Option 2 block not found in README.md"]

    # Option 1 validation
    opt1_env_blocks = extract_env_code_blocks(opt1)
    if not opt1_env_blocks:
        violations.append("No .env code block found in Option 1")
    else:
        combined_opt1 = "\n".join(opt1_env_blocks)
        if not re.search(r"^DEBUG\s*=\s*True\b", combined_opt1, re.MULTILINE):
            violations.append("Option 1 .env code block does not contain 'DEBUG=True'")

    # Option 2 validation
    opt2_env_blocks = extract_env_code_blocks(opt2)
    if not opt2_env_blocks:
        violations.append("No .env code block found in Option 2")
    else:
        combined_opt2 = "\n".join(opt2_env_blocks)
        if not re.search(r"^DEBUG\s*=\s*True\b", combined_opt2, re.MULTILINE):
            violations.append("Option 2 .env code block does not contain 'DEBUG=True'")
        if not re.search(r"^CORS_ALLOWED_ORIGINS\s*=", combined_opt2, re.MULTILINE):
            violations.append(
                "Option 2 .env code block does not contain 'CORS_ALLOWED_ORIGINS'"
            )
        if not re.search(r"^CSRF_TRUSTED_ORIGINS\s*=", combined_opt2, re.MULTILINE):
            violations.append(
                "Option 2 .env code block does not contain 'CSRF_TRUSTED_ORIGINS'"
            )

    return violations


def validate_req_c_option_2_no_create_extension(readme_text: str) -> list[str]:
    """
    Validates criterion (c):
    No code block of Option 2 in README.md contains CREATE EXTENSION.
    """
    violations: list[str] = []
    opt2 = get_option_block(readme_text, 2)
    if not opt2:
        return ["Option 2 block not found in README.md"]

    code_blocks = extract_fenced_code_blocks(opt2)
    for idx, block in enumerate(code_blocks, 1):
        if re.search(r"\bCREATE\s+EXTENSION\b", block, flags=re.IGNORECASE):
            violations.append(
                f"Option 2 code block #{idx} contains forbidden 'CREATE EXTENSION' statement"
            )
    return violations


def validate_req_d_ocr_ready_qualifier(readme_text: str) -> list[str]:
    """
    Validates criterion (d):
    The shared verification section does not contain "ocr_ready":true or "ocr_ready": true
    without a qualifier (asserting that every occurrence is within a sentence that also
    names Docker or runserver).
    """
    violations: list[str] = []
    verification_block = get_verification_block(readme_text)
    if not verification_block:
        return ["Shared verification section not found in README.md"]

    ocr_pattern = re.compile(r'"ocr_ready"\s*:\s*true\b', flags=re.IGNORECASE)

    # Split into sentences or lines
    sentences = re.split(r"(?<=[.!?])\s+|\r?\n\r?\n+", verification_block)
    for idx, sentence in enumerate(sentences, 1):
        if ocr_pattern.search(sentence):
            has_docker = bool(re.search(r"\bdocker\b", sentence, re.IGNORECASE))
            has_runserver = bool(re.search(r"\brunserver\b", sentence, re.IGNORECASE))
            if not (has_docker or has_runserver):
                clean_sentence = " ".join(sentence.split())
                violations.append(
                    f"Sentence #{idx} contains '\"ocr_ready\": true' without environment qualifier (Docker or runserver): {clean_sentence!r}"
                )
    return violations


def validate_req_e_sample_accounts_table(readme_text: str, seed_text: str) -> list[str]:
    """
    Validates criterion (e):
    The sample accounts table in README.md has exactly the 3 columns (Role, Email, Phone),
    and all its emails and phones exist in db/02-seed.sql.
    """
    violations: list[str] = []
    tables = extract_markdown_tables(readme_text)

    account_tables: list[list[list[str]]] = []
    for t in tables:
        raw_table = "\n".join(" | ".join(row) for row in t)
        if "@example" in raw_table:
            account_tables.append(t)

    if not account_tables:
        return ["No sample accounts table found in README.md"]

    seed_emails = set(re.findall(r"'([a-zA-Z0-9_.+-]+@example\.[a-z]+)'", seed_text))
    seed_phones = set(re.findall(r"'([0-9]{10,11})'", seed_text))

    for t_idx, table in enumerate(account_tables, 1):
        headers = [c.strip().strip("`") for c in table[0]]
        # Normalize header: strip parenthesized text and whitespace
        normalized_headers = [
            re.sub(r"\(.*?\)", "", h).strip().lower() for h in headers
        ]

        if len(headers) != 3:
            violations.append(
                f"Sample accounts table #{t_idx} has {len(headers)} columns ({headers}), expected exactly 3 columns ('Role', 'Email', 'Phone')"
            )
        else:
            expected_keywords = ["role", "email", "phone"]
            for exp, actual in zip(expected_keywords, normalized_headers, strict=True):
                if exp not in actual:
                    violations.append(
                        f"Sample accounts table #{t_idx} column header mismatch: expected {exp!r}, got {actual!r}"
                    )

        # Validate rows
        for r_idx, row in enumerate(table[1:], 2):
            row_text = " ".join(row)
            emails = re.findall(r"[a-zA-Z0-9_.+-]+@example\.[a-z]+", row_text)
            for email in emails:
                if email not in seed_emails:
                    violations.append(
                        f"Sample accounts table #{t_idx} row #{r_idx}: Email '{email}' not found in db/02-seed.sql"
                    )
            phones = re.findall(r"\b0\d{9}\b", row_text)
            for phone in phones:
                if phone not in seed_phones:
                    violations.append(
                        f"Sample accounts table #{t_idx} row #{r_idx}: Phone '{phone}' not found in db/02-seed.sql"
                    )

    return violations


def validate_req_f_vietnamese_diacritics_outside_code(
    startup_span: str, guide_text: str
) -> list[str]:
    """
    Validates criterion (f):
    Neither the rewritten README.md span nor docs/guides/01-frontend-api-guide.md
    contains any Vietnamese diacritic characters outside fenced code blocks and
    inline code spans, except for an explicit short allowlist (ALLOWED_VIETNAMESE_WORDS).
    """
    violations: list[str] = []

    def check_target(name: str, text: str) -> None:
        # Strip fenced code blocks
        stripped = re.sub(r"```[^\n]*\r?\n.*?```", " ", text, flags=re.DOTALL)
        # Strip inline code spans
        stripped = re.sub(r"`[^`\r\n]+`", " ", stripped)
        # Strip markdown links target URLs
        stripped = re.sub(r"\]\([^)]+\)", "] ", stripped)
        # Strip html comments
        stripped = re.sub(r"<!--.*?-->", " ", stripped, flags=re.DOTALL)

        # Find words containing Vietnamese diacritics
        words = re.findall(r"\b[\w\u00C0-\u1EF9]+\b", stripped, flags=re.UNICODE)
        vn_words = [
            w
            for w in words
            if VIETNAMESE_DIACRITICS_PATTERN.search(w)
            and w not in ALLOWED_VIETNAMESE_WORDS
        ]

        if vn_words:
            unique_vn = sorted(set(vn_words))
            violations.append(
                f"{name} contains {len(vn_words)} Vietnamese diacritic words outside code blocks "
                f"({len(unique_vn)} unique: {unique_vn[:10]}...)"
            )

    check_target("README.md start-up span", startup_span)
    check_target("docs/guides/01-frontend-api-guide.md", guide_text)
    return violations


def validate_req_g_fenced_code_blocks_messages(
    guide_text: str,
    authorized_messages: set[str],
    authorized_seed_strings: set[str],
    authorized_apps_strings: set[str] | None = None,
    target_name: str = "docs/guides/01-frontend-api-guide.md",
) -> list[str]:
    """
    Validates criterion (g):
    Every line of every fenced code block containing Vietnamese text must only
    contain authorized quoted strings and zero Vietnamese comments or unquoted text.
    Bypass for envelope schema is completely removed.
    Reports block index, 1-based file line number, block line number, and offending line text.
    """
    violations: list[str] = []
    if authorized_apps_strings is None:
        authorized_apps_strings = set()

    combined_authorized = (
        authorized_messages
        | authorized_seed_strings
        | authorized_apps_strings
        | set(ALLOWED_CODE_BLOCK_VIETNAMESE_STRINGS.keys())
    )

    quote_pattern = re.compile(
        r'"([^"\\]*(?:\\.[^"\\]*)*)"|\'([^\'\\]*(?:\\.[^\'\\]*)*)\''
    )

    blocks = extract_fenced_code_blocks_with_lines(guide_text)

    for b_idx, start_line_no, block_content in blocks:
        lines = block_content.splitlines()
        for rel_idx, line in enumerate(lines, 1):
            file_line_no = start_line_no + rel_idx - 1
            if not VIETNAMESE_DIACRITICS_PATTERN.search(line):
                continue

            matches = list(quote_pattern.finditer(line))

            curr = 0
            outside_parts: list[str] = []
            quotes_on_line: list[str] = []
            for m in matches:
                if m.start() > curr:
                    outside_parts.append(line[curr : m.start()])
                val = m.group(1) if m.group(1) is not None else m.group(2)
                quotes_on_line.append(val)
                curr = m.end()

            if curr < len(line):
                outside_parts.append(line[curr:])

            outside_text = "".join(outside_parts)

            # Condition 1: No Vietnamese diacritics outside quoted string literals
            if VIETNAMESE_DIACRITICS_PATTERN.search(outside_text):
                violations.append(
                    f"{target_name} Code block #{b_idx} (file line {file_line_no}, block line {rel_idx}): "
                    f"Line contains Vietnamese diacritics outside quoted string literals: {line.strip()!r}"
                )
                continue

            # Condition 2: Every quoted string containing Vietnamese must be authorized
            vn_quotes = [
                q for q in quotes_on_line if VIETNAMESE_DIACRITICS_PATTERN.search(q)
            ]
            for q in vn_quotes:
                if q not in combined_authorized:
                    violations.append(
                        f"{target_name} Code block #{b_idx} (file line {file_line_no}, block line {rel_idx}): "
                        f"Unauthorized Vietnamese string literal {q!r} on line: {line.strip()!r}"
                    )

    return violations


# =============================================================================
# Test Cases (a) through (g)
# =============================================================================


def test_req_a_repo_clone_url_authoritative_and_no_codegym() -> None:
    """
    Invariant (a): README.md contains authoritative clone URL and neither
    README.md nor 01-frontend-api-guide.md (including split topic guides) contains 'github.com/codegym/'.
    """
    readme_text = read_file_text(README_PATH)
    all_guide_text = "\n\n".join(
        read_file_text(p) for p in get_all_guide_paths(REPO_ROOT)
    )
    violations = validate_req_a_clone_urls(readme_text, all_guide_text)
    assert not violations, "Invariant (a) failed:\n" + "\n".join(violations)


def test_req_b_startup_env_code_blocks_debug_and_cors_csrf() -> None:
    """
    Invariant (b): The .env code block of EACH option contains DEBUG=True,
    and Option 2 also contains CORS_ALLOWED_ORIGINS and CSRF_TRUSTED_ORIGINS.
    """
    readme_text = read_file_text(README_PATH)
    violations = validate_req_b_env_code_blocks(readme_text)
    assert not violations, "Invariant (b) failed:\n" + "\n".join(violations)


def test_req_c_option_2_no_create_extension_code_blocks() -> None:
    """
    Invariant (c): No code block of Option 2 in README.md contains CREATE EXTENSION.
    """
    readme_text = read_file_text(README_PATH)
    violations = validate_req_c_option_2_no_create_extension(readme_text)
    assert not violations, "Invariant (c) failed:\n" + "\n".join(violations)


def test_req_d_verification_ocr_ready_qualified_with_environment() -> None:
    """
    Invariant (d): The shared verification section does not contain "ocr_ready":true
    or "ocr_ready": true without a qualifier (naming Docker or runserver).
    """
    readme_text = read_file_text(README_PATH)
    violations = validate_req_d_ocr_ready_qualifier(readme_text)
    assert not violations, "Invariant (d) failed:\n" + "\n".join(violations)


def test_req_e_sample_accounts_table_exact_three_columns_and_seed_match() -> None:
    """
    Invariant (e): Sample accounts table in README.md has exactly the 3 columns
    (Role, Email, Phone), and all its emails and phones exist in db/02-seed.sql.
    """
    readme_text = read_file_text(README_PATH)
    seed_text = read_file_text(SEED_PATH)
    violations = validate_req_e_sample_accounts_table(readme_text, seed_text)
    assert not violations, "Invariant (e) failed:\n" + "\n".join(violations)


def test_req_f_no_vietnamese_diacritics_outside_code_blocks() -> None:
    """
    Invariant (f): Neither the rewritten README.md span nor 01-frontend-api-guide.md
    (including split topic guides) contains any Vietnamese diacritic characters outside fenced code blocks and inline code spans.
    """
    readme_text = read_file_text(README_PATH)
    all_guide_text = "\n\n".join(
        read_file_text(p) for p in get_all_guide_paths(REPO_ROOT)
    )
    startup_span = get_startup_span_text(readme_text)
    violations = validate_req_f_vietnamese_diacritics_outside_code(
        startup_span, all_guide_text
    )
    assert not violations, "Invariant (f) failed:\n" + "\n".join(violations)


def test_req_g_fenced_code_blocks_vietnamese_strings_in_authorized_catalogs() -> None:
    """
    Invariant (g): Every line of every fenced code block in
    docs/guides/01-frontend-api-guide.md (and split topic guides) and README.md start-up span containing
    Vietnamese text must only contain authorized quoted strings and zero Vietnamese comments/free text.
    """
    readme_text = read_file_text(README_PATH)
    startup_span = get_startup_span_text(readme_text)

    authorized_messages = get_authorized_message_catalog(REPO_ROOT)
    authorized_seed_strings = get_authorized_seed_strings(SEED_PATH)
    authorized_apps_strings = get_authorized_apps_strings(REPO_ROOT)

    violations_guide: list[str] = []
    for guide_path in get_all_guide_paths(REPO_ROOT):
        guide_text = read_file_text(guide_path)
        violations = validate_req_g_fenced_code_blocks_messages(
            guide_text,
            authorized_messages,
            authorized_seed_strings,
            authorized_apps_strings,
            target_name=str(guide_path.relative_to(REPO_ROOT)).replace("\\", "/"),
        )
        violations_guide.extend(violations)

    violations_readme = validate_req_g_fenced_code_blocks_messages(
        startup_span,
        authorized_messages,
        authorized_seed_strings,
        authorized_apps_strings,
        target_name="README.md start-up span",
    )
    violations = violations_guide + violations_readme
    assert not violations, "Invariant (g) failed:\n" + "\n".join(violations)


# =============================================================================
# Synthetic Unit Tests (Verifying Validator Correctness & Defect Detection)
# =============================================================================


def test_synthetic_repo_clone_url_validator() -> None:
    """Verifies that validate_req_a_clone_urls accurately detects clone URL defects."""
    valid_readme = "Clone repo: https://github.com/quan-ly-bai-dau-xe/parking_management_backend.git"
    valid_guide = "Endpoint docs here."
    assert validate_req_a_clone_urls(valid_readme, valid_guide) == []

    bad_readme_codegym = (
        "git clone https://github.com/codegym/parking_management_backend.git"
    )
    bad_readme_missing = "git clone https://github.com/other-org/parking_backend.git"
    bad_guide_codegym = "See https://github.com/codegym/repo"

    assert len(validate_req_a_clone_urls(bad_readme_codegym, valid_guide)) >= 2
    assert len(validate_req_a_clone_urls(bad_readme_missing, valid_guide)) >= 1
    assert len(validate_req_a_clone_urls(valid_readme, bad_guide_codegym)) >= 1


def test_synthetic_env_code_blocks_validator() -> None:
    """Verifies that validate_req_b_env_code_blocks detects missing DEBUG and CORS/CSRF variables."""
    valid_readme = """
### Option 1: run with Docker
```env
DEBUG=True
SECRET_KEY=dev-secret
POSTGRES_PASSWORD=pass
```
### Option 2: run with Python and a locally installed PostgreSQL (no Docker)
```env
DEBUG=True
SECRET_KEY=dev-secret
POSTGRES_PASSWORD=pass
CORS_ALLOWED_ORIGINS=http://localhost:3000
CSRF_TRUSTED_ORIGINS=http://localhost:3000
```
### Next Step
"""
    assert validate_req_b_env_code_blocks(valid_readme) == []

    missing_opt1_debug = valid_readme.replace(
        "### Option 1: run with Docker\n```env\nDEBUG=True",
        "### Option 1: run with Docker\n```env\n",
    )
    violations1 = validate_req_b_env_code_blocks(missing_opt1_debug)
    assert any("Option 1" in v and "DEBUG=True" in v for v in violations1)

    missing_opt2_cors = valid_readme.replace(
        "CORS_ALLOWED_ORIGINS=http://localhost:3000\n", ""
    )
    violations2 = validate_req_b_env_code_blocks(missing_opt2_cors)
    assert any("CORS_ALLOWED_ORIGINS" in v for v in violations2)


def test_synthetic_option_2_create_extension_validator() -> None:
    """Verifies that validate_req_c_option_2_no_create_extension detects CREATE EXTENSION statements."""
    clean_readme = """
### Option 2: run with Python and a locally installed PostgreSQL (no Docker)
```sql
CREATE ROLE parking_user WITH LOGIN CREATEDB PASSWORD 'pass';
CREATE DATABASE parking_db OWNER parking_user;
```
### Next Step
"""
    assert validate_req_c_option_2_no_create_extension(clean_readme) == []

    bad_readme = """
### Option 2: run with Python and a locally installed PostgreSQL (no Docker)
```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;
```
### Next Step
"""
    violations = validate_req_c_option_2_no_create_extension(bad_readme)
    assert len(violations) == 1
    assert "CREATE EXTENSION" in violations[0]


def test_synthetic_ocr_ready_qualifier_validator() -> None:
    """Verifies that validate_req_d_ocr_ready_qualifier enforces environment qualifiers for ocr_ready."""
    valid_readme = """
### Verify the backend and try a login (both options)
Under Docker, health check returns "ocr_ready": true after pre-warming.
Under runserver, health check returns "ocr_ready": false until the first plate scan.
### Next Step
"""
    assert validate_req_d_ocr_ready_qualifier(valid_readme) == []

    unqualified_readme = """
### Verify the backend and try a login (both options)
Access http://127.0.0.1:8000/api/health/ which returns {"status":"healthy","ocr_ready": true}.
### Next Step
"""
    violations = validate_req_d_ocr_ready_qualifier(unqualified_readme)
    assert len(violations) == 1
    assert "without environment qualifier" in violations[0]


def test_synthetic_sample_accounts_table_validator() -> None:
    """Verifies that validate_req_e_sample_accounts_table enforces 3 columns and checks seed records."""
    seed_sql = """
INSERT INTO account (email, phone, role) VALUES
    ('user@example.com', '0901234567', 'MANAGER');
"""
    valid_readme = """
| Role | Email | Phone |
|---|---|---|
| `MANAGER` | `user@example.com` | `0901234567` |
"""
    assert validate_req_e_sample_accounts_table(valid_readme, seed_sql) == []

    four_columns_readme = """
| Role | Email | Phone | Extra Permissions |
|---|---|---|---|
| `MANAGER` | `user@example.com` | `0901234567` | Full admin |
"""
    violations1 = validate_req_e_sample_accounts_table(four_columns_readme, seed_sql)
    assert any("4 columns" in v for v in violations1)

    unknown_email_readme = """
| Role | Email | Phone |
|---|---|---|
| `MANAGER` | `unknown@example.com` | `0901234567` |
"""
    violations2 = validate_req_e_sample_accounts_table(unknown_email_readme, seed_sql)
    assert any("unknown@example.com" in v for v in violations2)


def test_synthetic_vietnamese_diacritics_validator() -> None:
    """Verifies that validate_req_f_vietnamese_diacritics_outside_code detects diacritics outside code blocks."""
    clean_span = "Start the server with `python manage.py runserver`. User name: Trịnh Xuân Trường."
    clean_guide = "This guide explains API usage. Sample person: Hoàng Đình Khang."
    assert (
        validate_req_f_vietnamese_diacritics_outside_code(clean_span, clean_guide) == []
    )

    bad_span = "Khởi chạy máy chủ phát triển bằng lệnh runserver."
    violations = validate_req_f_vietnamese_diacritics_outside_code(
        bad_span, clean_guide
    )
    assert len(violations) >= 1
    assert "README.md start-up span" in violations[0]


def test_synthetic_message_catalog_validator() -> None:
    """Verifies that validate_req_g_fenced_code_blocks_messages detects unauthorized messages."""
    authorized_messages = {"Đăng nhập thành công.", "Lỗi kết nối cơ sở dữ liệu"}
    authorized_seeds = {"Ô tô", "Vé tháng"}

    valid_guide = """
```json
{
  "status": "success",
  "message": "Đăng nhập thành công."
}
```
"""
    assert (
        validate_req_g_fenced_code_blocks_messages(
            valid_guide, authorized_messages, authorized_seeds
        )
        == []
    )

    unauthorized_guide = """
```json
{
  "status": "error",
  "message": "Thông báo tự chế không có trong danh mục."
}
```
"""
    violations = validate_req_g_fenced_code_blocks_messages(
        unauthorized_guide, authorized_messages, authorized_seeds
    )
    assert len(violations) == 1
    assert "Thông báo tự chế không có trong danh mục." in violations[0]


def test_synthetic_code_block_vietnamese_comment_and_line_number_validator() -> None:
    """
    Verifies that validate_req_g_fenced_code_blocks_messages detects Vietnamese comments
    (// or #) and unquoted text inside code blocks, and accurately reports line numbers.
    """
    authorized_messages = {"Thành công."}
    authorized_seeds = {"Dữ liệu"}
    authorized_apps: set[str] = set()

    # Code block with a single-line // Vietnamese comment
    bad_comment_guide = """# Test Doc
Some introductory text.

```json
{
  // Chú thích tiếng Việt không hợp lệ
  "status": "success",
  "message": "Thành công."
}
```
"""
    violations = validate_req_g_fenced_code_blocks_messages(
        bad_comment_guide,
        authorized_messages,
        authorized_seeds,
        authorized_apps,
    )
    assert len(violations) == 1
    # Verify line number reporting: block content starts at line 5, comment is at line 6
    assert "file line 6" in violations[0]
    assert "block line 2" in violations[0]
    assert "outside quoted string literals" in violations[0]

    # Code block with a # Vietnamese comment
    bad_hash_comment_guide = """# Python snippet
```python
# Bình luận tiếng Việt cấm
x = 1
```
"""
    violations_hash = validate_req_g_fenced_code_blocks_messages(
        bad_hash_comment_guide,
        authorized_messages,
        authorized_seeds,
        authorized_apps,
    )
    assert len(violations_hash) == 1
    assert "file line 3" in violations_hash[0]
    assert "block line 1" in violations_hash[0]
    assert "outside quoted string literals" in violations_hash[0]
