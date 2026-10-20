"""
Adversarial Stress-Testing Suite for verify_report_integrity.py.

Covers:
1. Single-character mutation in quotations (QUOTE_MISMATCH)
2. Title echo attacks (TITLE_ECHO_REJECTED)
3. Document number/label mismatches (DOCUMENT_MISMATCH)
4. Complex Markdown citation formats (multi-column tables, nested/multiline blockquotes)
5. Synthetic failure cases (HTTP 404, 403 UNVERIFIED, forbidden V-word, unmatched tokens)
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
VERIFY_SCRIPT = REPO_ROOT / "tests" / "tools" / "verify_report_integrity.py"


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """Override conftest db fixture: no database needed for verify report tool tests."""
    return None


def run_verify_script(
    report_content: str, citations_only: bool = True
) -> tuple[int, str]:
    """Execute verify_report_integrity.py against a temporary Markdown report file."""
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8"
    ) as f:
        f.write(report_content)
        temp_path = Path(f.name)

    try:
        cmd = [sys.executable, str(VERIFY_SCRIPT)]
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
# OFFLINE TESTS (Default Suite: Run with zero network requirements)
# =============================================================================


class TestOfflineReportIntegrityAdversarial:
    """Offline verification tests for forbidden words, tokens, and markdown syntax."""

    def test_forbidden_7_letter_v_word_all_casings_rejected(self) -> None:
        """Every casing variant of the prohibited 7-letter word is rejected."""
        base_template = "# Report\n`parking_db`\n`apps/parking`\n"
        for v_casing in [
            "vic" + "tory",
            "Vic" + "tory",
            "VIC" + "TORY",
            "vIc" + "torY",
        ]:
            report = base_template + f"\nWe achieved a great {v_casing} here.\n"
            code, out = run_verify_script(report, citations_only=False)
            assert code != 0, f"Casing '{v_casing}' was not rejected!"
            assert "Found forbidden word" in out or "AssertionError" in out

    def test_unmatched_code_token_rejected(self) -> None:
        """An inline backticked token not matching schema, registry, or corpus is rejected."""
        import uuid

        base_template = "# Report\n`parking_db`\n`apps/parking`\n"
        dynamic_fake_token = f"dyn_unmatched_token_{uuid.uuid4().hex}"
        report = base_template + f"\nUsing unregistered model `{dynamic_fake_token}`.\n"
        code, out = run_verify_script(report, citations_only=False)
        assert code != 0, "Script should have rejected unmatched backtick token!"
        assert "Unmatched Tokens Count:" in out
        assert dynamic_fake_token in out

    def test_clean_schema_tokens_pass_offline(self) -> None:
        """Legitimate database and codebase tokens pass with 0 unmatched tokens."""
        clean_report = (
            "# Clean Report\n\n"
            "- App: `parking`\n"
            "- Model: `PlateBlacklist`\n"
            "- Field: `license_plate`\n"
            "- File: `README.md`\n"
        )
        code, out = run_verify_script(clean_report, citations_only=False)
        assert code == 0, (
            f"Expected exit code 0 for valid report tokens, got {code}:\n{out}"
        )
        assert "Unmatched Tokens Count: 0" in out


# =============================================================================
# ONLINE / NETWORK TESTS (Opt-in: Skipped by default in offline CI)
# =============================================================================


@pytest.mark.network
class TestOnlineAdversarialK4Verification:
    """Empirical challenge tests targeting citation integrity enforcement against real URLs."""

    def test_single_character_mutation_content(self) -> None:
        """Mutate a single letter in an authentic quote (work -> works). Must trigger QUOTE_MISMATCH."""
        content = """# Test Report: Single Character Mutation
| Document | URL | Quote |
| :--- | :--- | :--- |
| ONNX Runtime | https://onnxruntime.ai/docs/performance/tune-performance/threading.html | Controls whether additional INTRA or INTER threads spin waiting for works. |
"""
        code, out = run_verify_script(content)
        assert code != 0, f"Expected non-zero exit code on mutated quote, got {code}."
        assert "QUOTE_MISMATCH" in out, (
            f"Expected QUOTE_MISMATCH failure code in output:\n{out}"
        )

    def test_single_character_mutation_casing(self) -> None:
        """Mutate initial letter casing (Controls -> controls). Must trigger QUOTE_MISMATCH."""
        content = """# Test Report: Casing Mutation
| Document | URL | Quote |
| :--- | :--- | :--- |
| ONNX Runtime | https://onnxruntime.ai/docs/performance/tune-performance/threading.html | controls whether additional INTRA or INTER threads spin waiting for work. |
"""
        code, out = run_verify_script(content)
        assert code != 0, f"Expected non-zero exit code on cased quote, got {code}."
        assert "QUOTE_MISMATCH" in out, (
            f"Expected QUOTE_MISMATCH failure code in output:\n{out}"
        )

    def test_single_character_mutation_punctuation(self) -> None:
        """Mutate trailing punctuation (. -> !). Must trigger QUOTE_MISMATCH."""
        content = """# Test Report: Punctuation Mutation
| Document | URL | Quote |
| :--- | :--- | :--- |
| ONNX Runtime | https://onnxruntime.ai/docs/performance/tune-performance/threading.html | Controls whether additional INTRA or INTER threads spin waiting for work! |
"""
        code, out = run_verify_script(content)
        assert code != 0, (
            f"Expected non-zero exit code on punctuation mutation, got {code}."
        )
        assert "QUOTE_MISMATCH" in out, (
            f"Expected QUOTE_MISMATCH failure code in output:\n{out}"
        )

    def test_title_echo_exact_match(self) -> None:
        """Quotation repeats exactly the page <title>. Must trigger TITLE_ECHO_REJECTED."""
        content = """# Test Report: Title Echo Exact Match
| Document | URL | Verbatim Quote |
| :--- | :--- | :--- |
| Thông tư 79/2024/TT-BCA | https://vanban.chinhphu.vn/?pageid=27160&docid=211945 | Thông tư số 79/2024/TT-BCA của Bộ Công an: Quy định về cấp, thu hồi chứng nhận đăng ký xe, biển số xe cơ giới, xe máy chuyên dùng |
"""
        code, out = run_verify_script(content)
        assert code != 0, f"Expected non-zero exit code on title echo, got {code}."
        assert "TITLE_ECHO_REJECTED" in out, (
            f"Expected TITLE_ECHO_REJECTED failure code in output:\n{out}"
        )

    def test_title_echo_exact_match_onnx(self) -> None:
        """Quotation repeats exactly the ONNX page <title>. Must trigger TITLE_ECHO_REJECTED."""
        content = r"""# Test Report: Title Echo Exact Match ONNX
| Document | URL | Verbatim Quote |
| :--- | :--- | :--- |
| ONNX Runtime | https://onnxruntime.ai/docs/performance/tune-performance/threading.html | Thread management \| onnxruntime |
"""
        code, out = run_verify_script(content)
        assert code != 0, f"Expected non-zero exit code on title echo, got {code}."
        assert "TITLE_ECHO_REJECTED" in out, (
            f"Expected TITLE_ECHO_REJECTED failure code in output:\n{out}"
        )

    def test_document_mismatch_nd13_vs_tt79(self) -> None:
        """Citing Decree 13/2023/ND-CP while pointing to Circular 79/2024/TT-BCA URL. Must trigger DOCUMENT_MISMATCH."""
        content = """# Test Report: Document Mismatch in Table
| Document | URL | Verbatim Quote |
| :--- | :--- | :--- |
| Nghị định 13/2023/NĐ-CP | https://vanban.chinhphu.vn/?pageid=27160&docid=211945 | Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2025 |
"""
        code, out = run_verify_script(content)
        assert code != 0, (
            f"Expected non-zero exit code on document mismatch, got {code}."
        )
        assert "DOCUMENT_MISMATCH" in out, (
            f"Expected DOCUMENT_MISMATCH failure code in output:\n{out}"
        )

    def test_document_mismatch_tt24_vs_qd861(self) -> None:
        """Citing Circular 24/2023/TT-BCA on Decision 861/QD-TTg URL (docid=208297). Must trigger DOCUMENT_MISMATCH."""
        content = """# Test Report: Document Mismatch in Markdown Link
Tra cứu tài liệu: [Thông tư 24/2023/TT-BCA](https://vanban.chinhphu.vn/?pageid=27160&docid=208297)

> Quyết định này có hiệu lực thi hành kể từ ngày ký.
"""
        code, out = run_verify_script(content)
        assert code != 0, (
            f"Expected non-zero exit code on document mismatch, got {code}."
        )
        assert "DOCUMENT_MISMATCH" in out, (
            f"Expected DOCUMENT_MISMATCH failure code in output:\n{out}"
        )

    def test_document_mismatch_tt51_vs_tt79(self) -> None:
        """Citing Circular 51/2025/TT-BCA on Circular 79/2024/TT-BCA URL. Must trigger DOCUMENT_MISMATCH."""
        content = """# Test Report: Document Mismatch 51 vs 79
| Văn bản | URL | Trích dẫn |
| :--- | :--- | :--- |
| Thông tư 51/2025/TT-BCA | https://vanban.chinhphu.vn/?pageid=27160&docid=211945 | Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2025 |
"""
        code, out = run_verify_script(content)
        assert code != 0, (
            f"Expected non-zero exit code on document mismatch, got {code}."
        )
        assert "DOCUMENT_MISMATCH" in out, (
            f"Expected DOCUMENT_MISMATCH failure code in output:\n{out}"
        )

    def test_complex_multi_column_table_with_escaped_pipe(self) -> None:
        """Table with 8 columns, scrambled order, escaped pipes, and genuine quote. Must pass."""
        content = r"""# Test Report: Complex Multi-column Table
| Col 1 | Verbatim Supporting Sentence | Col 3 | Notes | URL Link | Issuer | Status | Document |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| #1 | Controls whether additional INTRA or INTER threads spin waiting for work. | Flag \| value | Verified | https://onnxruntime.ai/docs/performance/tune-performance/threading.html | Microsoft | ACTIVE | ONNX Runtime |
"""
        code, out = run_verify_script(content)
        assert code == 0, (
            f"Expected exit code 0 for valid complex table, got {code}. Output:\n{out}"
        )
        assert "VERIFIED (HTTP 200 OK - Verbatim quote matched)" in out

    def test_nested_and_indented_blockquotes(self) -> None:
        """Blockquote format following URL link. Must extract and verify properly."""
        content = """# Test Report: Nested Blockquotes
Tài liệu tham khảo từ [ONNX Runtime](https://onnxruntime.ai/docs/performance/tune-performance/threading.html):
> Controls whether additional INTRA or INTER threads spin waiting for work.
"""
        code, out = run_verify_script(content)
        assert code == 0, (
            f"Expected exit code 0 for blockquote citation, got {code}. Output:\n{out}"
        )
        assert "VERIFIED (HTTP 200 OK - Verbatim quote matched)" in out

    def test_multiline_blockquote(self) -> None:
        """Multiline blockquote with multiple quote lines."""
        content = """# Test Report: Multiline Blockquote
Nguồn: [ONNX Runtime Threading](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)
> Controls whether additional INTRA or INTER threads spin waiting for work.
"""
        code, out = run_verify_script(content)
        assert code == 0, (
            f"Expected exit code 0 for multiline blockquote, got {code}. Output:\n{out}"
        )
        assert "VERIFIED (HTTP 200 OK - Verbatim quote matched)" in out

    def test_inline_verbatim_syntax(self) -> None:
        """Inline verbatim quotation using 'Verbatim: \"...\"' format."""
        content = """# Test Report: Inline Verbatim
Nguồn tra cứu: [ONNX Runtime](https://onnxruntime.ai/docs/performance/tune-performance/threading.html)
Verbatim: "Controls whether additional INTRA or INTER threads spin waiting for work."
"""
        code, out = run_verify_script(content)
        assert code == 0, (
            f"Expected exit code 0 for inline verbatim format, got {code}. Output:\n{out}"
        )
        assert "VERIFIED (HTTP 200 OK - Verbatim quote matched)" in out

    def test_http_404_rejected(self) -> None:
        """Non-existent 404 URL is rejected."""
        content = """# Test Report: 404
| Source | URL | HTTP Status | Page Title | Access Date | Verbatim Supporting Sentence |
| :--- | :--- | :---: | :--- | :---: | :--- |
| 404 URL | https://vanban.chinhphu.vn/?pageid=27160&docid=99999999999_fake_not_found | 404 Not Found | Not Found | 2026-10-19 | Dummy sentence |
"""
        code, out = run_verify_script(content)
        assert code != 0
        assert "404" in out or "FAILED" in out

    def test_http_403_unverified(self) -> None:
        """HTTP 403 Forbidden is classified as UNVERIFIED, never OK."""
        content = """# Test Report: 403
| Source | URL | HTTP Status | Page Title | Access Date | Verbatim Supporting Sentence |
| :--- | :--- | :---: | :--- | :---: | :--- |
| TVPL | https://thuvienphapluat.vn/van-ban/Giao-thong-Van-tai/Thong-tu-79-2024-TT-BCA-cap-thu-hoi-dang-ky-bien-so-xe-co-gioi-xe-may-chuyen-dung-634567.aspx | 403 Forbidden | WAF Block | 2026-10-19 | Dummy text |
"""
        code, out = run_verify_script(content)
        assert code != 0
        assert "UNVERIFIED" in out
        assert "never OK" in out
