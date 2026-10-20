"""
Offline Unit and Integration Test Suite for Report Integrity Verification.

Validates:
1. Four (4) known-bad defective citation fixtures exit non-zero:
   - Case 1: Wrong document table row (docid=208297 cited as TT 24/2023 -> DOCUMENT_MISMATCH)
   - Case 2: HTTP 404 Not Found (failure_code=HTTP_404)
   - Case 3: Invented/fabricated ONNX quote (failure_code=QUOTE_MISMATCH)
   - Case 4: Bold-backtick numbered list entry with wrong document URL (DOCUMENT_MISMATCH)
2. Valid authentic citation forms exit 0:
   - Valid table row citation
   - Valid bold-backtick numbered list citation
   - Valid authentic ONNX threading quote
   - Valid heading citation followed by URL
3. Unlabelled citation enforcement (UNLABELLED_CITATION):
   - Bare statutory URL lacking document label fails with UNLABELLED_CITATION
   - Bare technical reference URL on REFERENCE_PAGE_ALLOWLIST passes
4. Parsing and extraction invariants across all shapes (clean_label_text, extract_citations, extract_statutory_doc_numbers)
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.tools.verify_report_integrity import (
    clean_label_text,
    extract_citations,
    extract_statutory_doc_numbers,
    is_url_in_reference_allowlist,
    verify_url_and_quote,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFY_SCRIPT = REPO_ROOT / "tests" / "tools" / "verify_report_integrity.py"


@pytest.fixture(autouse=True)
def override_db_fixture() -> None:
    """Override conftest db fixture: no database needed for offline verifier tests."""
    return None


def run_offline_verify_script(
    report_content: str, citations_only: bool = True
) -> tuple[int, str]:
    """Execute verify_report_integrity.py in --offline mode against a temporary Markdown report file."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(report_content)
        temp_path = Path(f.name)

    try:
        cmd = [sys.executable, str(VERIFY_SCRIPT), "--offline"]
        if citations_only:
            cmd.append("--citations-only")
        cmd.append(str(temp_path))

        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        combined_output = proc.stdout + (
            "\nSTDERR:\n" + proc.stderr if proc.stderr else ""
        )
        return proc.returncode, combined_output
    finally:
        if temp_path.exists():
            with contextlib.suppress(Exception):
                temp_path.unlink()


# =============================================================================
# 1. FOUR (4) KNOWN-BAD DEFECT FIXTURES (Exit Non-Zero)
# =============================================================================

FIXTURE_WRONG_DOCUMENT_TABLE_ROW = """# Report: Defect 1 - Wrong Document Table Row
| Document | URL | Verbatim Quote |
| :--- | :--- | :--- |
| Thông tư 24/2023/TT-BCA | https://vanban.chinhphu.vn/?pageid=27160&docid=208297 | Quyết định này có hiệu lực thi hành kể từ ngày ký. |
"""

FIXTURE_HTTP_404 = """# Report: Defect 2 - HTTP 404 Not Found
| Document | URL | Verbatim Quote |
| :--- | :--- | :--- |
| Thông tư 79/2024/TT-BCA | https://vanban.chinhphu.vn/?pageid=27160&docid=404_nonexistent_document | 79-bca.signed.pdf |
"""

FIXTURE_INVENTED_ONNX_QUOTE = """# Report: Defect 3 - Invented ONNX Quote
| Document | URL | Verbatim Quote |
| :--- | :--- | :--- |
| ONNX Runtime Threading | https://onnxruntime.ai/docs/performance/tune-performance/threading.html | ONNX Runtime automatically detects GPU and spawns 128 threads for maximum throughput. |
"""

FIXTURE_BOLD_BACKTICK_WRONG_URL = """# Report: Defect 4 - Bold-Backtick List Entry with Wrong Document URL
2. **Thông tư `24/2023/TT-BCA`** (Cổng Thông tin điện tử Chính phủ — `https://vanban.chinhphu.vn/?pageid=27160&docid=208297`, truy cập ngày `2026-10-19`):
> Quyết định này có hiệu lực thi hành kể từ ngày ký.
"""


class TestKnownBadDefectFixtures:
    """Verify that all 4 known-bad defective citation forms fail with exit non-zero."""

    def test_defect_1_wrong_document_table_row_fails(self) -> None:
        """Case 1: Table row cites TT 24/2023 on QĐ 861 URL (docid=208297). Must trigger DOCUMENT_MISMATCH and exit non-zero."""
        code, out = run_offline_verify_script(FIXTURE_WRONG_DOCUMENT_TABLE_ROW)
        assert code != 0, f"Expected non-zero exit code, got {code}"
        assert "DOCUMENT_MISMATCH" in out, (
            f"Expected DOCUMENT_MISMATCH in output:\n{out}"
        )
        assert "24/2023/TT-BCA" in out
        assert "861/QĐ-TTG" in out or "861" in out

    def test_defect_2_http_404_fails(self) -> None:
        """Case 2: Citing an HTTP 404 URL. Must trigger HTTP_404 failure and exit non-zero."""
        code, out = run_offline_verify_script(FIXTURE_HTTP_404)
        assert code != 0, f"Expected non-zero exit code, got {code}"
        assert "HTTP_404" in out or "404 Not Found" in out, (
            f"Expected 404 in output:\n{out}"
        )

    def test_defect_3_invented_onnx_quote_fails(self) -> None:
        """Case 3: Invented/fabricated verbatim quote on authentic ONNX page. Must trigger QUOTE_MISMATCH and exit non-zero."""
        code, out = run_offline_verify_script(FIXTURE_INVENTED_ONNX_QUOTE)
        assert code != 0, f"Expected non-zero exit code, got {code}"
        assert "QUOTE_MISMATCH" in out, f"Expected QUOTE_MISMATCH in output:\n{out}"

    def test_defect_4_bold_backtick_wrong_url_fails(self) -> None:
        """Case 4: Bold-backtick numbered list entry citing TT 24/2023 on QĐ 861 URL. Must trigger DOCUMENT_MISMATCH and exit non-zero."""
        code, out = run_offline_verify_script(FIXTURE_BOLD_BACKTICK_WRONG_URL)
        assert code != 0, f"Expected non-zero exit code, got {code}"
        assert "DOCUMENT_MISMATCH" in out, (
            f"Expected DOCUMENT_MISMATCH in output:\n{out}"
        )
        assert "24/2023/TT-BCA" in out


# =============================================================================
# 2. VALID CITATION FORMS (Exit Zero)
# =============================================================================

FIXTURE_VALID_TABLE = """# Report: Valid Table Citation
| Document | URL | Verbatim Quote |
| :--- | :--- | :--- |
| Thông tư 79/2024/TT-BCA | https://vanban.chinhphu.vn/?pageid=27160&docid=211945 | 79-bca.signed.pdf |
| Thông tư 51/2025/TT-BCA | https://vanban.chinhphu.vn/?pageid=27160&docid=214486 | 51-bca.signed.pdf |
"""

FIXTURE_VALID_BOLD_BACKTICK = """# Report: Valid Bold-Backtick List Citation
2. **Thông tư `24/2023/TT-BCA`** (Cổng Thông tin điện tử Chính phủ — `https://vanban.chinhphu.vn/?pageid=27160&docid=208348`, truy cập ngày `2026-10-19`):
> 24-bca.signed.pdf
"""

FIXTURE_VALID_ONNX_QUOTE = """# Report: Valid Authentic ONNX Quote
| Document | URL | Verbatim Quote |
| :--- | :--- | :--- |
| ONNX Runtime Threading | https://onnxruntime.ai/docs/performance/tune-performance/threading.html | Controls whether additional INTRA or INTER threads spin waiting for work. |
"""

FIXTURE_VALID_HEADING_CITATION = """# Report: Valid Heading Citation
### Thông tư 51/2025/TT-BCA
Nguồn chính thức: https://vanban.chinhphu.vn/?pageid=27160&docid=214486
> 51-bca.signed.pdf
"""


class TestValidCitationFormsPass:
    """Verify that all authentic citation shapes pass with exit code 0."""

    def test_valid_table_citation_passes(self) -> None:
        """Valid table citations pass with TOTAL_FAILURES=0 and exit 0."""
        code, out = run_offline_verify_script(FIXTURE_VALID_TABLE)
        assert code == 0, f"Expected exit code 0, got {code}:\n{out}"
        assert "TOTAL_FAILURES=0" in out
        assert "VERIFIED (HTTP 200 OK - Verbatim quote matched)" in out

    def test_valid_bold_backtick_list_citation_passes(self) -> None:
        """Valid bold-backtick numbered list entry with matching docid passes with exit code 0."""
        code, out = run_offline_verify_script(FIXTURE_VALID_BOLD_BACKTICK)
        assert code == 0, f"Expected exit code 0, got {code}:\n{out}"
        assert "TOTAL_FAILURES=0" in out
        assert "VERIFIED" in out

    def test_valid_onnx_quote_passes(self) -> None:
        """Valid authentic ONNX quotation passes with exit code 0."""
        code, out = run_offline_verify_script(FIXTURE_VALID_ONNX_QUOTE)
        assert code == 0, f"Expected exit code 0, got {code}:\n{out}"
        assert "TOTAL_FAILURES=0" in out
        assert "Controls whether additional INTRA or INTER threads" in out

    def test_valid_heading_citation_passes(self) -> None:
        """Valid heading citation followed by URL passes with exit code 0."""
        code, out = run_offline_verify_script(FIXTURE_VALID_HEADING_CITATION)
        assert code == 0, f"Expected exit code 0, got {code}:\n{out}"
        assert "TOTAL_FAILURES=0" in out


# =============================================================================
# 3. UNLABELLED CITATION ENFORCEMENT & ALLOWLIST EXEMPTIONS
# =============================================================================


class TestUnlabelledCitationAndAllowlist:
    """Validate strict UNLABELLED_CITATION rejection and explicit allowlist exemptions."""

    def test_unlabelled_bare_statutory_url_rejected(self) -> None:
        """A bare statutory URL lacking a document label fails with UNLABELLED_CITATION."""
        content = """# Report: Bare Unlabelled URL
Tài liệu được tra cứu tại: https://vanban.chinhphu.vn/?pageid=27160&docid=211945
"""
        code, out = run_offline_verify_script(content)
        assert code != 0, (
            f"Expected non-zero exit code for unlabelled citation, got {code}"
        )
        assert "UNLABELLED_CITATION" in out
        assert "Unlabelled Citations: 1" in out

    def test_unlabelled_table_column_rejected(self) -> None:
        """A table missing Document column entirely triggers UNLABELLED_CITATION."""
        content = """# Report: Table Missing Document Column
| Item | Link | Notes |
| :--- | :--- | :--- |
| #1 | https://vanban.chinhphu.vn/?pageid=27160&docid=211945 | Note without label |
"""
        code, out = run_offline_verify_script(content)
        assert code != 0, f"Expected non-zero exit code, got {code}"
        assert "UNLABELLED_CITATION" in out

    def test_allowlist_exempt_url_without_label_passes(self) -> None:
        """A bare technical reference URL on REFERENCE_PAGE_ALLOWLIST is not rejected as UNLABELLED_CITATION."""
        content = """# Report: Reference Page Allowlist
Giấy phép mở: https://creativecommons.org/licenses/by/4.0/
"""
        code, out = run_offline_verify_script(content)
        assert code == 0, f"Expected exit code 0 for allowlist URL, got {code}:\n{out}"
        assert "UNLABELLED_CITATION" not in out
        assert "TOTAL_FAILURES=0" in out

    def test_all_reference_allowlist_domains(self) -> None:
        """Confirm all expected reference domains are present in REFERENCE_PAGE_ALLOWLIST."""
        assert is_url_in_reference_allowlist(
            "https://onnxruntime.ai/docs/threading.html"
        )
        assert is_url_in_reference_allowlist(
            "https://huggingface.co/datasets/sonnetechnology"
        )
        assert is_url_in_reference_allowlist("https://docs.djangoproject.com/en/5.1/")
        assert is_url_in_reference_allowlist(
            "https://creativecommons.org/licenses/by/4.0/"
        )
        assert is_url_in_reference_allowlist("https://github.com/microsoft/onnxruntime")
        assert is_url_in_reference_allowlist(
            "https://pypi.org/project/rapidocr-onnxruntime/"
        )
        # Statutory URL is not exempt
        assert not is_url_in_reference_allowlist(
            "https://vanban.chinhphu.vn/?pageid=27160&docid=211945"
        )


# =============================================================================
# 4. IN-PROCESS PARSING & EXTRACTION UNIT TESTS
# =============================================================================


class TestInProcessCitationParsingAndExtraction:
    """Unit tests for clean_label_text, extract_citations, and extract_statutory_doc_numbers."""

    def test_clean_label_text_removes_markdown_and_punctuation(self) -> None:
        """clean_label_text cleanly strips backticks, bold asterisks, and outer punctuation."""
        assert (
            clean_label_text("**Thông tư `24/2023/TT-BCA`**")
            == "Thông tư 24/2023/TT-BCA"
        )
        assert (
            clean_label_text("[Thông tư 51/2025/TT-BCA](https://...)")
            == "Thông tư 51/2025/TT-BCA"
        )
        assert (
            clean_label_text("2. **Nghị định 13/2023/NĐ-CP**:")
            == "2. Nghị định 13/2023/NĐ-CP"
        )
        assert clean_label_text("`ONNX Runtime`") == "ONNX Runtime"
        assert clean_label_text("") == ""

    def test_extract_statutory_doc_numbers(self) -> None:
        """Extract statutory doc numbers across various formats."""
        nums = extract_statutory_doc_numbers(
            "Thông tư 79/2024/TT-BCA và Nghị định 13/2023/NĐ-CP"
        )
        assert "79/2024/TT-BCA" in nums
        assert "13/2023/NĐ-CP" in nums

        nums_qd = extract_statutory_doc_numbers(
            "Quyết định số 861/QĐ-TTg của Thủ tướng"
        )
        assert "861/QĐ-TTG" in nums_qd

    def test_extract_citations_across_all_shapes(self) -> None:
        """Verify extraction across numbered list with bold-backticks, bullet list, table, and heading."""
        md_text = """
# Multiple Shapes Report

1. **Thông tư `24/2023/TT-BCA`** (Cổng TTĐT — `https://vanban.chinhphu.vn/?pageid=27160&docid=208348`):
> 24-bca.signed.pdf

### Thông tư 51/2025/TT-BCA
Tham khảo: https://vanban.chinhphu.vn/?pageid=27160&docid=214486

| Document | URL | Verbatim Quote |
| :--- | :--- | :--- |
| Thông tư 79/2024/TT-BCA | https://vanban.chinhphu.vn/?pageid=27160&docid=211945 | 79-bca.signed.pdf |

- Căn cứ Nghị định 13/2023/NĐ-CP tại https://vanban.chinhphu.vn/?pageid=27160&docid=207759
"""
        citations = extract_citations(md_text)
        assert len(citations) == 4

        urls = {c["url"]: c for c in citations}
        assert "https://vanban.chinhphu.vn/?pageid=27160&docid=208348" in urls
        assert (
            "24/2023/TT-BCA"
            in urls["https://vanban.chinhphu.vn/?pageid=27160&docid=208348"][
                "doc_label"
            ]
        )

        assert "https://vanban.chinhphu.vn/?pageid=27160&docid=214486" in urls
        assert (
            "51/2025/TT-BCA"
            in urls["https://vanban.chinhphu.vn/?pageid=27160&docid=214486"][
                "doc_label"
            ]
        )

        assert "https://vanban.chinhphu.vn/?pageid=27160&docid=211945" in urls
        assert (
            "79/2024/TT-BCA"
            in urls["https://vanban.chinhphu.vn/?pageid=27160&docid=211945"][
                "doc_label"
            ]
        )

        assert "https://vanban.chinhphu.vn/?pageid=27160&docid=207759" in urls
        assert (
            "13/2023/NĐ-CP"
            in urls["https://vanban.chinhphu.vn/?pageid=27160&docid=207759"][
                "doc_label"
            ]
        )

    def test_direct_verify_url_and_quote_offline(self) -> None:
        """Direct in-process call to verify_url_and_quote with offline=True."""
        res_ok = verify_url_and_quote(
            "https://vanban.chinhphu.vn/?pageid=27160&docid=211945",
            quote="79-bca.signed.pdf",
            doc_label="Thông tư 79/2024/TT-BCA",
            offline=True,
        )
        assert res_ok["status_category"] == "VERIFIED"
        assert res_ok["quote_matched"] is True

        res_mismatch = verify_url_and_quote(
            "https://vanban.chinhphu.vn/?pageid=27160&docid=208297",
            doc_label="Thông tư 24/2023/TT-BCA",
            offline=True,
        )
        assert res_mismatch["status_category"] == "FAILED"
        assert res_mismatch["failure_code"] == "DOCUMENT_MISMATCH"

        res_unlabelled = verify_url_and_quote(
            "https://vanban.chinhphu.vn/?pageid=27160&docid=211945",
            doc_label="",
            offline=True,
        )
        assert res_unlabelled["status_category"] == "FAILED"
        assert res_unlabelled["failure_code"] == "UNLABELLED_CITATION"
