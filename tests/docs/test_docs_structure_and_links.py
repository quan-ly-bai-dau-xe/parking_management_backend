# cspell:words alnum cicd
"""
Structural and link integrity tests for documentation restructure (Round 77).

Validates:
1. README.md top-level sections (1 to 6) are closed <details id="..."> blocks with <summary>.
2. README.md Section 3 subsections are nested closed <details id="..."> blocks with <summary>.
3. README.md plain-text section index exists under the intro/horizontal rule before any details block.
4. Strict CommonMark: 1 blank line after </summary> and 1 blank line before </details>.
5. docs/guides/01-frontend-api-guide.md index links to all 10 split files.
6. All 10 split files exist under docs/guides/frontend-api/ with non-zero size.
7. Each split file has a 1-line navigation header on line 1 with correct links (Index, Previous, Next).
8. All 15 original section numbers (## 1. to ## 15.) are present across the 10 split files in expected mapping.
9. Synthetic tests confirming that validators reject invalid structures.

Zero database dependency, zero network access, executes in <1s.
"""

import re
from collections.abc import Sequence
from pathlib import Path

import pytest

REPO_ROOT: Path = Path(__file__).resolve().parents[2]
README_PATH: Path = REPO_ROOT / "README.md"
GUIDE_INDEX_PATH: Path = REPO_ROOT / "docs" / "guides" / "01-frontend-api-guide.md"
SPLIT_GUIDES_DIR: Path = REPO_ROOT / "docs" / "guides" / "frontend-api"


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """
    Overrides the root conftest fixture to enforce zero database dependency
    for documentation tests.
    """
    return None


EXPECTED_TOP_LEVEL_SECTIONS: list[tuple[str, str]] = [
    ("1-project-overview--scope", "1. Project Overview & Scope"),
    ("2-architecture--data-safety", "2. Architecture & Data Safety"),
    (
        "3-quick-start-development--operations",
        "3. Quick Start (Development & Operations)",
    ),
    (
        "4-cicd--branch-protection-rules-for-repository-owner",
        "4. CI/CD & Branch Protection Rules for Repository Owner",
    ),
    ("5-documentation--ai-operating-system", "5. Documentation & AI Operating System"),
    ("6-governance--license", "6. Governance & License"),
]

EXPECTED_SECTION_3_SUBSECTIONS: list[tuple[str, str]] = [
    ("choose-how-to-run-the-backend", "Choose how to run the backend"),
    ("option-1-run-with-docker", "Option 1: run with Docker"),
    (
        "option-2-run-with-python-and-a-locally-installed-postgresql-no-docker",
        "Option 2: run with Python and a locally installed PostgreSQL (no Docker)",
    ),
    (
        "verify-the-backend-and-try-a-login-both-options",
        "Verify the backend and try a login (both options)",
    ),
    ("environment-variables", "Environment variables"),
    ("troubleshooting", "Troubleshooting"),
    (
        "step-8-interactive-api-documentation-csrf--swagger-try-it-out",
        'Step 8: Interactive API Documentation, CSRF & Swagger "Try it out"',
    ),
    ("step-9-run-automated-test-suite", "Step 9: Run Automated Test Suite"),
    (
        "step-10-performance-testing--high-concurrency-soak-runbook-h1-h3-h4-h5-h9a-k2-k7",
        "Step 10: Performance Testing & High-Concurrency Soak Runbook (H1, H3, H4, H5, H9a, K2, K7)",
    ),
    (
        "step-11-production-operations-runbook--incident-playbooks-j7d-standard-6",
        "Step 11: Production Operations Runbook & Incident Playbooks (J7.d, Standard 6)",
    ),
]

EXPECTED_SPLIT_FILES: list[str] = [
    "01-getting-started.md",
    "02-authentication-flow.md",
    "03-client-code-cors-cookies.md",
    "04-conventions.md",
    "05-parking-endpoints.md",
    "06-vehicle-endpoints.md",
    "07-customer-endpoints.md",
    "08-employee-endpoints.md",
    "09-reference-data-and-tooling.md",
    "10-troubleshooting-and-cloudinary.md",
]

EXPECTED_SECTION_TO_FILE: dict[int, str] = {
    1: "01-getting-started.md",
    2: "01-getting-started.md",
    3: "01-getting-started.md",
    4: "02-authentication-flow.md",
    5: "03-client-code-cors-cookies.md",
    6: "03-client-code-cors-cookies.md",
    7: "04-conventions.md",
    8: "05-parking-endpoints.md",
    9: "06-vehicle-endpoints.md",
    10: "07-customer-endpoints.md",
    11: "08-employee-endpoints.md",
    12: "09-reference-data-and-tooling.md",
    13: "09-reference-data-and-tooling.md",
    14: "10-troubleshooting-and-cloudinary.md",
    15: "10-troubleshooting-and-cloudinary.md",
}


def parse_details_blocks(markdown_text: str) -> list[dict[str, str]]:
    """
    Parses <details ...> and <summary>...</summary> definitions from markdown text.
    Returns list of dicts with 'id', 'summary', and 'is_open' flags.
    """
    results: list[dict[str, str]] = []
    # Pattern to capture opening details tag and its immediately following summary
    pattern = re.compile(
        r"<details(?P<attrs>[^>]*)>\s*<summary>(?P<summary>[^<]+)</summary>",
        re.MULTILINE,
    )
    for match in pattern.finditer(markdown_text):
        attrs = match.group("attrs")
        summary = match.group("summary").strip()
        id_match = re.search(r'id=["\']([^"\']+)["\']', attrs)
        block_id = id_match.group(1) if id_match else ""
        is_open = "open" in attrs.split() or bool(re.search(r"\bopen\b", attrs))
        results.append(
            {
                "id": block_id,
                "summary": summary,
                "is_open": str(is_open),
            }
        )
    return results


def validate_commonmark_details_spacing(markdown_text: str) -> list[str]:
    """
    Validates CommonMark requirement:
    - Exactly 1 blank line after </summary>
    - Exactly 1 blank line before </details>
    Returns list of violation descriptions.
    """
    violations: list[str] = []
    lines = markdown_text.splitlines()

    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.endswith("</summary>"):
            if idx + 1 >= len(lines):
                violations.append(
                    f"Line {idx + 1}: </summary> at end of file without blank line."
                )
            elif lines[idx + 1].strip() != "":
                violations.append(
                    f"Line {idx + 1}: Expected blank line after </summary>, got: '{lines[idx + 1]}'"
                )
        if stripped == "</details>":
            if idx - 1 < 0:
                violations.append(f"Line {idx + 1}: </details> at start of file.")
            elif lines[idx - 1].strip() != "":
                violations.append(
                    f"Line {idx + 1}: Expected blank line before </details>, got: '{lines[idx - 1]}'"
                )

    return violations


def validate_split_navigation_header(
    file_name: str, first_line: str, all_files: Sequence[str]
) -> list[str]:
    """
    Validates that a 1-line navigation header conforms to standard pattern:
    - Back to Index link
    - Previous link (if not first file)
    - Next link (if not last file)
    """
    violations: list[str] = []
    file_idx = all_files.index(file_name) if file_name in all_files else -1
    if file_idx == -1:
        return [f"File {file_name} is not in expected files list"]

    if "../01-frontend-api-guide.md" not in first_line:
        violations.append(
            f"{file_name}: Missing back-link to '../01-frontend-api-guide.md'"
        )

    if file_idx > 0:
        prev_file = all_files[file_idx - 1]
        if "Previous" not in first_line or prev_file not in first_line:
            violations.append(
                f"{file_name}: Missing or incorrect Previous link to '{prev_file}'"
            )
    else:
        if "Previous" in first_line:
            violations.append(f"{file_name}: First file must not have a Previous link")

    if file_idx < len(all_files) - 1:
        next_file = all_files[file_idx + 1]
        if "Next" not in first_line or next_file not in first_line:
            violations.append(
                f"{file_name}: Missing or incorrect Next link to '{next_file}'"
            )
    else:
        if "Next" in first_line:
            violations.append(f"{file_name}: Last file must not have a Next link")

    return violations


# ==============================================================================
# Production Tests (Documentation Structure & Links)
# ==============================================================================


def test_readme_top_level_sections_structure() -> None:
    """
    Validates that README.md top-level sections (1 through 6):
    - Are closed <details id="..."> blocks with matching <summary> headings (no 'open' attribute).
    - Have a plain-text section list right under the intro / horizontal rule.
    """
    assert README_PATH.exists(), f"README.md not found at {README_PATH}"
    readme_text = README_PATH.read_text(encoding="utf-8")

    # 1. Plain text list under horizontal rule
    # Find intro separator ---
    intro_split = readme_text.split("---", 1)
    assert len(intro_split) >= 2, "README.md missing intro separator '---'"
    post_intro = intro_split[1]

    first_details_idx = post_intro.find("<details")
    assert first_details_idx != -1, "README.md contains no <details> block"
    section_index_span = post_intro[:first_details_idx]

    for section_id, section_title in EXPECTED_TOP_LEVEL_SECTIONS:
        expected_anchor_link = f"(#{section_id})"
        assert expected_anchor_link in section_index_span, (
            f"Section index under intro missing link to '{section_title}' ({expected_anchor_link})"
        )

    # 2. Top-level details blocks
    blocks = parse_details_blocks(readme_text)
    block_map = {b["id"]: b for b in blocks}

    for section_id, section_title in EXPECTED_TOP_LEVEL_SECTIONS:
        assert section_id in block_map, (
            f"Top-level section '{section_title}' (id='{section_id}') not found in README.md"
        )
        block = block_map[section_id]
        assert block["summary"] == section_title, (
            f"Summary text mismatch for '{section_id}': got '{block['summary']}', expected '{section_title}'"
        )
        assert block["is_open"] == "False", (
            f"Top-level section '{section_id}' must be closed (must not have 'open' attribute)"
        )


def test_readme_section_3_nested_subsections_structure() -> None:
    """
    Validates that README.md Section 3 (Quick Start):
    - Has 10 major subsections enclosed in nested closed <details id="..."> blocks.
    - Each block has matching <summary> heading and no 'open' attribute.
    - Opening and closing tags balance exactly.
    """
    readme_text = README_PATH.read_text(encoding="utf-8")

    # Extract Section 3 span
    sec3_start = readme_text.find('id="3-quick-start-development--operations"')
    assert sec3_start != -1, "Section 3 details block not found"
    sec4_start = readme_text.find(
        'id="4-cicd--branch-protection-rules-for-repository-owner"'
    )
    assert sec4_start != -1, "Section 4 details block not found"

    sec3_text = readme_text[sec3_start:sec4_start]
    blocks = parse_details_blocks(sec3_text)
    block_map = {b["id"]: b for b in blocks}

    for sub_id, sub_title in EXPECTED_SECTION_3_SUBSECTIONS:
        assert sub_id in block_map, (
            f"Section 3 subsection '{sub_title}' (id='{sub_id}') not found in README.md"
        )
        block = block_map[sub_id]
        assert block["summary"] == sub_title, (
            f"Summary text mismatch for subsection '{sub_id}': got '{block['summary']}', expected '{sub_title}'"
        )
        assert block["is_open"] == "False", (
            f"Subsection '{sub_id}' must be closed (must not have 'open' attribute)"
        )

    # Check total balance of details tags in entire README
    open_tags = len(re.findall(r"<details\b", readme_text))
    close_tags = len(re.findall(r"</details>", readme_text))
    assert open_tags == close_tags, (
        f"Mismatched <details> tags in README.md: {open_tags} opening vs {close_tags} closing"
    )
    # 6 top-level + 10 nested in section 3 = 16 details tags
    assert open_tags == 16, (
        f"Expected 16 <details> tags in README.md, found {open_tags}"
    )


def test_readme_strict_commonmark_details_spacing() -> None:
    """
    Validates strict CommonMark compliance in README.md:
    - 1 blank line after </summary>
    - 1 blank line before </details>
    """
    readme_text = README_PATH.read_text(encoding="utf-8")
    violations = validate_commonmark_details_spacing(readme_text)
    assert not violations, (
        f"CommonMark spacing violations found in README.md ({len(violations)}):\n"
        + "\n".join(violations)
    )


def test_frontend_guide_split_files_existence_and_index_links() -> None:
    """
    Validates that:
    - docs/guides/01-frontend-api-guide.md exists and links to all 10 split files.
    - All 10 split files exist in docs/guides/frontend-api/ with non-zero size.
    """
    assert GUIDE_INDEX_PATH.exists(), f"Guide index not found at {GUIDE_INDEX_PATH}"
    index_text = GUIDE_INDEX_PATH.read_text(encoding="utf-8")

    assert SPLIT_GUIDES_DIR.exists(), (
        f"Split guides directory not found at {SPLIT_GUIDES_DIR}"
    )
    assert SPLIT_GUIDES_DIR.is_dir(), f"{SPLIT_GUIDES_DIR} is not a directory"

    for file_name in EXPECTED_SPLIT_FILES:
        # Check link in index
        expected_rel_link = f"frontend-api/{file_name}"
        assert expected_rel_link in index_text, (
            f"Guide index missing link to split file: {expected_rel_link}"
        )

        # Check physical existence and size
        file_path = SPLIT_GUIDES_DIR / file_name
        assert file_path.exists(), f"Expected split file not found: {file_path}"
        assert file_path.is_file(), f"Path is not a regular file: {file_path}"
        file_size = file_path.stat().st_size
        assert file_size > 0, f"Split file {file_name} is empty (0 bytes)"


def test_frontend_guide_split_navigation_headers() -> None:
    """
    Validates that each split file:
    - Starts with a level-1 title on line 1 (keeps MD041 enabled).
    - Has a 1-line navigation header on line 3.
    - Links back to index (../01-frontend-api-guide.md).
    - Links to Previous file (files 2-10).
    - Links to Next file (files 1-9).
    """
    all_violations: list[str] = []

    for file_name in EXPECTED_SPLIT_FILES:
        file_path = SPLIT_GUIDES_DIR / file_name
        assert file_path.exists(), f"Split file not found: {file_path}"
        lines = file_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 5, f"Split file {file_name} too short (< 5 lines)"

        # Invariant: line 1 is the level-1 title, line 2 is blank
        assert lines[0].startswith("# "), (
            f"{file_name}: Line 1 must be a level-1 title, got: '{lines[0]}'"
        )
        assert lines[1].strip() == "", (
            f"{file_name}: Line 2 must be blank after the title, got: '{lines[1]}'"
        )

        nav_line = lines[2].strip()
        violations = validate_split_navigation_header(
            file_name, nav_line, EXPECTED_SPLIT_FILES
        )
        all_violations.extend(violations)

        # Invariant: line 4 must be blank after navigation header before first content
        assert lines[3].strip() == "", (
            f"{file_name}: Line 4 must be a blank line following navigation header, got: '{lines[3]}'"
        )

    assert not all_violations, (
        f"Navigation header violations found ({len(all_violations)}):\n"
        + "\n".join(all_violations)
    )


def test_frontend_guide_all_15_sections_present() -> None:
    """
    Validates that all 15 original section numbers (## 1. to ## 15.)
    are present across the 10 split files in their expected target files.
    """
    for sec_num, expected_file in EXPECTED_SECTION_TO_FILE.items():
        file_path = SPLIT_GUIDES_DIR / expected_file
        assert file_path.exists(), f"Split file not found: {file_path}"
        content = file_path.read_text(encoding="utf-8")

        pattern = rf"^##\s+{sec_num}\.\s+"
        match = re.search(pattern, content, flags=re.MULTILINE)
        assert match, (
            f"Section {sec_num} (pattern '{pattern}') not found in expected split file: {expected_file}"
        )


# ==============================================================================
# Synthetic Unit Tests (Test Integrity & Defect Detection Proof)
# ==============================================================================


def test_synthetic_details_parser_detects_open_attribute() -> None:
    """Verifies that parse_details_blocks flags open attribute accurately."""
    sample = '<details open id="test-id"><summary>Test Title</summary>\n\nContent\n\n</details>'
    blocks = parse_details_blocks(sample)
    assert len(blocks) == 1
    assert blocks[0]["id"] == "test-id"
    assert blocks[0]["summary"] == "Test Title"
    assert blocks[0]["is_open"] == "True"


def test_synthetic_spacing_validator_detects_missing_blank_lines() -> None:
    """Verifies that validate_commonmark_details_spacing catches missing blank lines."""
    # Bad sample: no blank line after </summary> and no blank line before </details>
    bad_sample = '<details id="x">\n<summary>Title</summary>\nText without blank line\n</details>'
    violations = validate_commonmark_details_spacing(bad_sample)
    assert len(violations) == 2
    assert "Expected blank line after </summary>" in violations[0]
    assert "Expected blank line before </details>" in violations[1]


def test_synthetic_nav_header_validator_flags_missing_back_link() -> None:
    """Verifies that validate_split_navigation_header flags missing back-to-index link."""
    bad_header = "[Next: 02-authentication-flow.md](02-authentication-flow.md)"
    violations = validate_split_navigation_header(
        "01-getting-started.md", bad_header, EXPECTED_SPLIT_FILES
    )
    assert any("Missing back-link" in v for v in violations)


def test_synthetic_nav_header_validator_flags_improper_previous_on_first_file() -> None:
    """Verifies that validate_split_navigation_header rejects Previous link on file 01."""
    bad_header = (
        "[← Back to Index](../01-frontend-api-guide.md) | "
        "[Previous: 00-intro.md](00-intro.md) | "
        "[Next: 02-authentication-flow.md](02-authentication-flow.md)"
    )
    violations = validate_split_navigation_header(
        "01-getting-started.md", bad_header, EXPECTED_SPLIT_FILES
    )
    assert any("First file must not have a Previous link" in v for v in violations)


def test_synthetic_nav_header_validator_flags_improper_next_on_last_file() -> None:
    """Verifies that validate_split_navigation_header rejects Next link on file 10."""
    bad_header = (
        "[← Back to Index](../01-frontend-api-guide.md) | "
        "[Previous: 09-reference-data-and-tooling.md](09-reference-data-and-tooling.md) | "
        "[Next: 11-extra.md](11-extra.md)"
    )
    violations = validate_split_navigation_header(
        "10-troubleshooting-and-cloudinary.md", bad_header, EXPECTED_SPLIT_FILES
    )
    assert any("Last file must not have a Next link" in v for v in violations)
