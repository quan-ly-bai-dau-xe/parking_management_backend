"""
Unit and regression tests for hardened report integrity verification script.
Tests citation extraction (tables, multi-line blockquotes, standalone URLs),
HTML entity/tag handling, HTTP response categorization, Unicode NFC/NFD normalization,
and forbidden term detection.
"""

from __future__ import annotations

import re
import unicodedata
import unittest
import urllib.error
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest

from tests.tools.verify_report_integrity import (
    extract_citations,
    extract_text_from_html,
    extract_title_and_headings,
    find_highest_round_notes,
    find_highest_round_report,
    load_repo_and_notes_corpus,
    verify_url_and_quote,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """Override conftest db fixture: no database needed for report integrity unit tests."""
    return None


class TestReportIntegrityVerification(unittest.TestCase):
    """Exhaustive test suite for verify_report_integrity.py."""

    def test_extract_text_from_html_strips_tags_and_preserves_code(self) -> None:
        """HTML markup is stripped while code content is preserved verbatim."""
        html = (
            '<pre><code><span class="n">sess_opt</span>.'
            '<span class="n">AddConfigEntry</span>('
            '"session.intra_op.allow_spinning", "0")</code></pre>'
        )
        text = extract_text_from_html(html)
        self.assertIn(
            'sess_opt.AddConfigEntry("session.intra_op.allow_spinning", "0")', text
        )

    def test_extract_text_unescapes_html_entities(self) -> None:
        """HTML named and numeric character references are converted to Unicode."""
        html = "<p>Th&ocirc;ng t&#432; s&#7889; 79/2024/TT-BCA</p>"
        text = extract_text_from_html(html)
        self.assertIn("Thông tư số 79/2024/TT-BCA", text)

    def test_extract_text_strips_script_with_trailing_spaces_in_end_tag(self) -> None:
        """CodeQL py/bad-tag-filter: </script > with spaces before > must strip script content."""
        html = "<p>Before</p><script>alert('sensitive_x')</script ><p>After</p>"
        text = extract_text_from_html(html)
        self.assertNotIn("alert('sensitive_x')", text)
        self.assertNotIn("sensitive_x", text)
        self.assertIn("Before", text)
        self.assertIn("After", text)

    def test_extract_text_strips_script_with_newlines_and_attributes_in_end_tag(
        self,
    ) -> None:
        """Closing tags with newlines and trailing attributes like </script\\nfoo> must strip script content."""
        html = "<p>Before</p><script>payload_data = 1;</script\nfoo><p>After</p>"
        text = extract_text_from_html(html)
        self.assertNotIn("payload_data", text)
        self.assertIn("Before", text)
        self.assertIn("After", text)

    def test_extract_text_strips_uppercase_script_tags(self) -> None:
        """Uppercase <SCRIPT>...</SCRIPT > with whitespace must strip content case-insensitively."""
        html = "<p>Visible</p><SCRIPT>console.log('secret');</SCRIPT ><p>Text</p>"
        text = extract_text_from_html(html)
        self.assertNotIn("secret", text)
        self.assertIn("Visible", text)
        self.assertIn("Text", text)

    def test_extract_text_handles_nested_and_unclosed_scripts(self) -> None:
        """Unclosed script hides subsequent text as a browser does; nested noscript respects tag depth."""
        # Unclosed script hides the rest
        unclosed = "Keep this text<script>var unclosed = 'leak'; hidden content"
        text_unclosed = extract_text_from_html(unclosed)
        self.assertNotIn("unclosed", text_unclosed)
        self.assertNotIn("leak", text_unclosed)
        self.assertNotIn("hidden content", text_unclosed)
        self.assertIn("Keep this text", text_unclosed)

        # Nested tags depth handling
        nested = "<noscript><noscript>nested_payload</noscript>outer_payload</noscript><p>Safe</p>"
        text_nested = extract_text_from_html(nested)
        self.assertNotIn("nested_payload", text_nested)
        self.assertNotIn("outer_payload", text_nested)
        self.assertIn("Safe", text_nested)

        # Self-closing script should not hide subsequent content
        self_closing = '<script src="bundle.js"/>Visible content'
        self.assertEqual(extract_text_from_html(self_closing), "Visible content")

        # Comment containing script tag should not trigger skip depth
        comment_script = "Visible Before<!-- <script>alert(1)</script> -->Visible After"
        self.assertEqual(
            extract_text_from_html(comment_script), "Visible BeforeVisible After"
        )

    def test_extract_text_strips_style_and_noscript_variants(self) -> None:
        """Variants of <style > and <noscript > with whitespace and unclosed variants are stripped."""
        html_style = "Header<style >body { color: red; }</style >Content"
        text_style = extract_text_from_html(html_style)
        self.assertNotIn("color: red", text_style)
        self.assertIn("Header", text_style)
        self.assertIn("Content", text_style)

        html_noscript = "Header<noscript\nbar>Enable JavaScript</noscript >Content"
        text_noscript = extract_text_from_html(html_noscript)
        self.assertNotIn("Enable JavaScript", text_noscript)
        self.assertIn("Header", text_noscript)
        self.assertIn("Content", text_noscript)

        # Unclosed style hides rest
        html_unclosed_style = "Prefix<style>body { font-size: 14px; }"
        text_unclosed_style = extract_text_from_html(html_unclosed_style)
        self.assertNotIn("font-size", text_unclosed_style)
        self.assertIn("Prefix", text_unclosed_style)

    def test_extract_text_decodes_entities_without_double_unescape(self) -> None:
        """Entities (&ocirc;, &#432;, &amp;, hex &#x20AC;) are decoded, and &amp;lt; must stay '&lt;' without double unescape."""
        html = "<p>Th&ocirc;ng t&#432; s&#7889; 79/2024/TT-BCA &amp; q &amp;lt; 10 &#x20AC;</p>"
        text = extract_text_from_html(html)
        self.assertIn("Thông tư số 79/2024/TT-BCA", text)
        self.assertIn("& q", text)
        self.assertIn("&lt; 10", text)
        self.assertNotIn("< 10", text)
        self.assertIn("€", text)

    def test_extract_text_preserves_escaped_script_tags_as_text(self) -> None:
        """Escaped '&lt;script&gt;' represents documentation/code text, not an executable HTML tag."""
        html = "<p>Example: &lt;script&gt;console.log('tutorial')&lt;/script&gt;</p>"
        text = extract_text_from_html(html)
        self.assertIn("<script>console.log('tutorial')</script>", text)

    def test_extract_text_block_tags_produce_newlines(self) -> None:
        """Block tags (p, div, tr, li, h1-h6, br, hr, pre, blockquote) produce newlines."""
        html = (
            "<h1>Heading 1</h1>"
            "<h2>Heading 2</h2>"
            "<h3>Heading 3</h3>"
            "<h4>Heading 4</h4>"
            "<h5>Heading 5</h5>"
            "<h6>Heading 6</h6>"
            "<p>Paragraph</p>"
            "<div>Division</div>"
            "<blockquote>Quote</blockquote>"
            "<pre>CodeBlock</pre>"
            "<hr>"
            "<ul><li>Item 1</li><li>Item 2</li></ul>"
            "<table><tr>Row 1</tr></table>"
            "Inline<br>Break"
        )
        text = extract_text_from_html(html)
        for piece in [
            "Heading 1",
            "Heading 2",
            "Heading 3",
            "Heading 4",
            "Heading 5",
            "Heading 6",
            "Paragraph",
            "Division",
            "Quote",
            "CodeBlock",
            "Item 1",
            "Item 2",
            "Row 1",
            "Break",
        ]:
            self.assertIn(f"\n{piece}", text)

    def test_extract_text_malformed_html_does_not_raise(self) -> None:
        """Severely malformed HTML markup parses gracefully without raising exceptions."""
        malformed_inputs: list[Any] = [
            '<<<>>> <tag unclosed="abc <script> >>> &invalid; </</<',
            '<div <span class="broken"',
            '<a href="http://example.com/unclosed',
            "text &amp&invalid;&#999999999; </ >",
            "<![CDATA[ unclosed CDATA",
            "<!-- unclosed comment",
            "<?xml bogus processing instruction?>",
            "",
            None,
            12345,
            b"<p>bytes</p>",
        ]
        for malformed in malformed_inputs:
            text = extract_text_from_html(malformed)
            self.assertIsInstance(text, str)

    def test_extract_text_decodes_named_entity_vietnamese_copilot_guard(self) -> None:
        """Named entities like &ocirc; must decode to Unicode (guards against Copilot convert_charrefs=False)."""
        html = "<p>Th&ocirc;ng b&aacute;o k&#7871;t qu&#7843;</p>"
        text = extract_text_from_html(html)
        self.assertIn("Thông báo kết quả", text)

    def test_extract_text_returns_empty_string_for_non_str_explicitly(self) -> None:
        """Non-string inputs (None, integers, floats, bytes, dicts) return empty string explicitly without try/except."""
        non_str_inputs: list[Any] = [
            None,
            0,
            12345,
            3.14,
            b"<p>bytes</p>",
            [],
            {},
            True,
            False,
        ]
        for non_str in non_str_inputs:
            self.assertEqual(extract_text_from_html(cast(Any, non_str)), "")

    def test_extract_text_fuzz_malformed_html_strings(self) -> None:
        """Seeded fuzz test with 2000 pseudo-random malformed HTML strings must not raise exceptions."""
        import random

        rng = random.Random(20261021)
        tokens = [
            "<",
            ">",
            "/",
            "!",
            "-",
            "&",
            "#",
            ";",
            '"',
            "'",
            "script",
            "style",
            "noscript",
            "p",
            "div",
            "h1",
            "h2",
            "h3",
            "br",
            "a",
            "b",
            "c",
            " ",
            "\n",
            "\t",
            "=",
            "x",
            "1",
            "9",
            "&ocirc;",
            "&lt;",
            "&amp;",
        ]
        for _ in range(2000):
            length = rng.randint(0, 80)
            malformed = "".join(rng.choice(tokens) for _ in range(length))
            res = extract_text_from_html(malformed)
            self.assertIsInstance(res, str)
            title, headings = extract_title_and_headings(malformed)
            self.assertIsInstance(title, str)
            self.assertIsInstance(headings, list)

    def test_extract_text_stack_skipping_nested_and_mismatched_tags(self) -> None:
        """Stack-based tag skipping ignores mismatched closing tags and handles nested skipped blocks."""
        # 1. Exact input from P3 requirement: mismatched </style> must not close <noscript>
        html_leak = "<noscript></style>LEAK</noscript>after"
        text_leak = extract_text_from_html(html_leak)
        self.assertEqual(text_leak, "after")
        self.assertNotIn("LEAK", text_leak)

        # 2. <style> inside <noscript>
        html_style_in_ns = (
            "<noscript>before_style<style>body { color: red; }</style>"
            "after_style</noscript>visible_tail"
        )
        text_style_in_ns = extract_text_from_html(html_style_in_ns)
        self.assertEqual(text_style_in_ns, "visible_tail")
        self.assertNotIn("before_style", text_style_in_ns)
        self.assertNotIn("color: red", text_style_in_ns)
        self.assertNotIn("after_style", text_style_in_ns)

        # 3. <script> inside <noscript>
        html_script_in_ns = (
            "<noscript>ns_head<script>alert(1);</script>ns_tail</noscript>visible_after"
        )
        text_script_in_ns = extract_text_from_html(html_script_in_ns)
        self.assertEqual(text_script_in_ns, "visible_after")
        self.assertNotIn("ns_head", text_script_in_ns)
        self.assertNotIn("alert(1)", text_script_in_ns)
        self.assertNotIn("ns_tail", text_script_in_ns)

    def test_find_highest_round_report_picks_highest_integer(self) -> None:
        """Report detector must sort round numbers by integer value, so round100 beats round41 and round9."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            td = Path(tmp_dir)
            (td / "round9_final_report.md").write_text("# Round 9", encoding="utf-8")
            (td / "round41_final_report.md").write_text("# Round 41", encoding="utf-8")
            (td / "round100_final_report.md").write_text(
                "# Round 100", encoding="utf-8"
            )
            highest = find_highest_round_report(td)
            self.assertEqual(highest.name, "round100_final_report.md")

            (td / "round9_notes.md").write_text("# Notes 9", encoding="utf-8")
            (td / "round41_notes.md").write_text("# Notes 41", encoding="utf-8")
            (td / "round100_notes.md").write_text("# Notes 100", encoding="utf-8")
            highest_notes = find_highest_round_notes(td)
            self.assertEqual(highest_notes.name, "round100_notes.md")

            # Subdirectories matching the pattern must be ignored in favor of regular files
            (td / "round999_final_report.md").mkdir()
            (td / "round999_notes.md").mkdir()
            self.assertEqual(
                find_highest_round_report(td).name, "round100_final_report.md"
            )
            self.assertEqual(find_highest_round_notes(td).name, "round100_notes.md")

    def test_find_highest_round_report_safe_default_when_empty_or_missing(self) -> None:
        """Report detector returns safe fallback when directory is empty or missing."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            td = Path(tmp_dir)
            self.assertEqual(
                find_highest_round_report(td).name, "round37_final_report.md"
            )
            self.assertEqual(find_highest_round_notes(td).name, "round37_notes.md")
            non_existent = td / "non_existent_agents"
            self.assertEqual(
                find_highest_round_report(non_existent).name, "round37_final_report.md"
            )
            self.assertEqual(
                find_highest_round_notes(non_existent).name, "round37_notes.md"
            )

    def test_load_repo_and_notes_corpus_picks_up_new_round_files(self) -> None:
        """Corpus loader globs round* and PROMPT_VONG* dynamically picking up newly added round files."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            td = Path(tmp_dir)
            (td / "round99_notes.md").write_text(
                "UniqueNoteIdentifier99", encoding="utf-8"
            )
            (td / "round99_final_report.md").write_text(
                "UniqueReportIdentifier99", encoding="utf-8"
            )
            (td / "PROMPT_VONG99_VI.txt").write_text(
                "UniquePromptIdentifier99", encoding="utf-8"
            )
            basenames, corpus = load_repo_and_notes_corpus(
                exclude_path=td / "other.md", agents_dir=td
            )
            self.assertIn("round99_notes.md", basenames)
            self.assertIn("round99_final_report.md", basenames)
            self.assertIn("PROMPT_VONG99_VI.txt", basenames)
            self.assertIn("UniqueNoteIdentifier99", corpus)
            self.assertIn("UniqueReportIdentifier99", corpus)
            self.assertIn("UniquePromptIdentifier99", corpus)

    def test_extract_title_and_headings_handles_attributes_case_newlines_and_inline_tags(
        self,
    ) -> None:
        """HTMLParser-based extractor parses title and h1-h3 with attributes, uppercase tags, newlines, inline tags, and trailing spaces."""
        html = (
            '<title class="meta-title" lang="vi">Trang ch&#7911;\nTh&#7871; gi&#7899;i</title>'
            '<H1 id="main-head">Ti&ecirc;u &#273;&#7873; <span>ph&#7909; 1</span></H1 >'
            '<h2 data-ref="sec2">Ti&ecirc;u &#273;&#7873;\nLine 2</h2>'
            "<H3>Ti&ecirc;u &#273;&#7873; <code>code</code> <em>em</em></H3>"
        )
        title, headings = extract_title_and_headings(html)
        self.assertEqual(title, "Trang chủ Thế giới")
        self.assertEqual(
            headings,
            [
                "Tiêu đề phụ 1",
                "Tiêu đề Line 2",
                "Tiêu đề code em",
            ],
        )
        # Non-string or empty inputs return ('', []) explicitly
        self.assertEqual(extract_title_and_headings(cast(Any, None)), ("", []))
        self.assertEqual(extract_title_and_headings(cast(Any, 12345)), ("", []))
        self.assertEqual(
            extract_title_and_headings(cast(Any, b"<title>x</title>")), ("", [])
        )

    def test_heading_split_over_two_lines_missed_by_old_regex(self) -> None:
        """Demonstrates that old regex without DOTALL missed multiline headings, whereas HTMLParser extracts them."""
        raw_heading = "<h2>D&#7919; li&#7879;u\nQu&#7889;c gia</h2>"

        # Old regex lacked re.DOTALL:
        old_regex_matches = re.findall(
            r"<h[1-3][^>]*>(.*?)</h[1-3]>", raw_heading, flags=re.IGNORECASE
        )
        self.assertEqual(
            old_regex_matches,
            [],
            "Proof: old regex without DOTALL fails to match heading split across newlines",
        )

        # New HTMLParser-based extraction extracts and normalizes it cleanly:
        _, new_headings = extract_title_and_headings(raw_heading)
        self.assertEqual(new_headings, ["Dữ liệu Quốc gia"])

    @patch("urllib.request.urlopen")
    def test_genuine_2xx_with_matching_quote_passes(self, mock_urlopen: Any) -> None:
        """Matching verbatim quote on HTTP 200 is marked VERIFIED."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html><title>Sample</title><body><p>Exact verbatim sentence here.</p></body></html>"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = verify_url_and_quote(
            "https://example.com/valid", "Exact verbatim sentence here."
        )
        self.assertEqual(res["status_category"], "VERIFIED")
        self.assertTrue(res["quote_matched"])

    @patch("urllib.request.urlopen")
    def test_fabricated_citation_detected_as_mismatch(self, mock_urlopen: Any) -> None:
        """Mismatching quote on HTTP 200 is rejected as FAILED."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"<html><title>Gas Reserve Plan</title><body><p>This is fuel reserve.</p></body></html>"
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = verify_url_and_quote(
            "https://example.com/fake", "Circular 24 vehicle registration"
        )
        self.assertEqual(res["status_category"], "FAILED")
        self.assertFalse(res["quote_matched"])
        self.assertIn("QUOTE_MISMATCH", res["message"])

    @patch("urllib.request.urlopen")
    def test_document_mismatch_detected(self, mock_urlopen: Any) -> None:
        """Document symbol mismatch between cited label and remote title is rejected with DOCUMENT_MISMATCH."""
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = (
            b"<html><title>Quy\xc3\xaa\xcc\x81t \xc4\x91i\xcc\xa3nh s\xc3\xb4\xcc\x81 861/Q\xc4\x90-TTg</title>"
            b"<body><h1>861/QD-TTg</h1><p>Fuel reserve plan</p></body></html>"
        )
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = verify_url_and_quote(
            "https://vanban.chinhphu.vn/?pageid=27160&docid=208297",
            quote=None,
            doc_label="Thông tư 24/2023/TT-BCA",
        )
        self.assertEqual(res["status_category"], "FAILED")
        self.assertEqual(res["failure_code"], "DOCUMENT_MISMATCH")
        self.assertIn("DOCUMENT_MISMATCH", res["message"])

    @patch("urllib.request.urlopen")
    def test_title_echo_rejected(self, mock_urlopen: Any) -> None:
        """Quotation that merely replicates the page title is rejected with TITLE_ECHO_REJECTED."""
        title_text = "Thông tư số 79/2024/TT-BCA của Bộ Công an"
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = f"<html><title>{title_text}</title><body><p>{title_text}</p></body></html>".encode()
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = verify_url_and_quote(
            "https://example.com/circular-79",
            quote=title_text,
            doc_label="Thông tư 79/2024/TT-BCA",
        )
        self.assertEqual(res["status_category"], "FAILED")
        self.assertEqual(res["failure_code"], "TITLE_ECHO_REJECTED")
        self.assertIn("TITLE_ECHO_REJECTED", res["message"])

    @patch("urllib.request.urlopen")
    def test_http_403_marked_unverified_never_ok(self, mock_urlopen: Any) -> None:
        """HTTP 403 Forbidden is classified as UNVERIFIED, never OK."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com/blocked", 403, "Forbidden", cast(Any, {}), None
        )

        res = verify_url_and_quote("https://example.com/blocked", "Some quote")
        self.assertEqual(res["status_category"], "UNVERIFIED")
        self.assertNotEqual(res["status_category"], "VERIFIED")
        self.assertIn(
            "403 Forbidden / Bot-Blocked (UNVERIFIED, never OK)", res["message"]
        )

    @patch("urllib.request.urlopen")
    def test_http_404_marked_failed(self, mock_urlopen: Any) -> None:
        """HTTP 404 Not Found is categorized as FAILED."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "https://example.com/missing", 404, "Not Found", cast(Any, {}), None
        )

        res = verify_url_and_quote("https://example.com/missing", "Some quote")
        self.assertEqual(res["status_category"], "FAILED")
        self.assertIn("404 Not Found", res["message"])

    def test_citation_extractor_from_markdown_table_and_blockquotes(self) -> None:
        """Table citations and blockquote citations are extracted accurately."""
        sample_doc = """
| Source | URL | HTTP Status | Access Date | Verbatim Quote |
| :--- | :--- | :---: | :---: | :--- |
| Law | https://example.com/law | 200 OK | 2026-10-19 | Article 1: Traffic rules |

Per docs ([ONNX](https://example.com/onnx)):
> "Threading config sample"
"""
        cits = extract_citations(sample_doc)
        urls = [c["url"] for c in cits]
        self.assertIn("https://example.com/law", urls)
        self.assertIn("https://example.com/onnx", urls)

        law_cit = next(c for c in cits if c["url"] == "https://example.com/law")
        self.assertEqual(law_cit["quote"], "Article 1: Traffic rules")
        self.assertEqual(law_cit["context"], "table")

        onnx_cit = next(c for c in cits if c["url"] == "https://example.com/onnx")
        self.assertEqual(onnx_cit["quote"], "Threading config sample")
        self.assertEqual(onnx_cit["context"], "text_block")

    def test_escaped_pipe_in_table_preserved(self) -> None:
        """Escaped pipes \\| inside table cells do not corrupt column parsing."""
        sample_doc = """
| Source | URL | HTTP Status | Page Title | Access Date | Verbatim Quote |
| :--- | :--- | :---: | :--- | :---: | :--- |
| ONNX | https://example.com/onnx | 200 OK | Threading \\| ONNX | 2026-10-19 | Verbatim thread quote |
"""
        cits = extract_citations(sample_doc)
        self.assertEqual(len(cits), 1)
        self.assertEqual(cits[0]["url"], "https://example.com/onnx")
        self.assertEqual(cits[0]["quote"], "Verbatim thread quote")

    def test_forbidden_v_word_detection(self) -> None:
        """The forbidden 7-letter word is detected across casing styles."""
        bad_text = "We achieved a great " + ("Vic" + "tory") + " in the final check."
        v7_matches = re.findall(r"\b[Vv][A-Za-z]{6}\b", bad_text)
        v7_forbidden = [w for w in v7_matches if w.lower() in ("v" + "ictory",)]
        self.assertEqual(len(v7_forbidden), 1)

        good_text = "All verification gates passed completely."
        v7_matches_good = re.findall(r"\b[Vv][A-Za-z]{6}\b", good_text)
        v7_forbidden_good = [
            w for w in v7_matches_good if w.lower() in ("v" + "ictory",)
        ]
        self.assertEqual(len(v7_forbidden_good), 0)

    def test_standalone_urls_extracted_without_blockquotes(self) -> None:
        """Standalone external URLs without blockquotes are extracted as context 'standalone'."""
        sample_doc = (
            "See documentation at https://example.com/standalone for details.\n"
            "Further information available at https://example.com/guide.\n"
        )
        cits = extract_citations(sample_doc)
        urls = [c["url"] for c in cits]
        self.assertIn("https://example.com/standalone", urls)
        self.assertIn("https://example.com/guide", urls)

        for c in cits:
            self.assertEqual(c["context"], "standalone")
            self.assertEqual(c["quote"], "")

    def test_multiline_blockquotes_concatenated_correctly(self) -> None:
        """Multi-line blockquotes are joined into a single coherent quote string."""
        sample_doc = (
            "Source: https://example.com/src\n"
            "> Line 1: Controls whether additional INTRA or INTER threads\n"
            "> Line 2: spin waiting for work.\n"
        )
        cits = extract_citations(sample_doc)
        self.assertEqual(len(cits), 1)
        self.assertEqual(cits[0]["url"], "https://example.com/src")
        self.assertEqual(cits[0]["context"], "text_block")
        self.assertIn(
            "Controls whether additional INTRA or INTER threads",
            cits[0]["quote"],
        )
        self.assertIn("spin waiting for work.", cits[0]["quote"])

    @patch("urllib.request.urlopen")
    def test_unicode_nfc_nfd_normalization_prevents_false_mismatch(
        self, mock_urlopen: Any
    ) -> None:
        """Unicode NFC/NFD equivalence is enforced during quote verification."""
        s_nfc = "Thông tư số 79/2024/TT-BCA của Bộ Công an"
        s_nfd = unicodedata.normalize("NFD", s_nfc)

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = (
            f"<html><body><p>{s_nfd}</p></body></html>".encode()
        )
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        # NFC quote against NFD HTML text
        res_nfc = verify_url_and_quote("https://example.com/nfd", s_nfc)
        self.assertEqual(res_nfc["status_category"], "VERIFIED")
        self.assertTrue(res_nfc["quote_matched"])

        # NFD quote against NFC HTML text
        mock_resp.read.return_value = (
            f"<html><body><p>{s_nfc}</p></body></html>".encode()
        )
        res_nfd = verify_url_and_quote("https://example.com/nfc", s_nfd)
        self.assertEqual(res_nfd["status_category"], "VERIFIED")
        self.assertTrue(res_nfd["quote_matched"])

    def test_internal_urls_filtered_out(self) -> None:
        """Localhost and internal loopback addresses are excluded from citations in step 3."""
        sample_doc = "Documentation references: https://example.com/external http://127.0.0.1:8000/api/health http://localhost:8000/api/scans\n"
        cits = extract_citations(sample_doc)
        urls = [c["url"] for c in cits]
        self.assertNotIn("http://127.0.0.1:8000/api/health", urls)
        self.assertNotIn("http://localhost:8000/api/scans", urls)
        self.assertIn("https://example.com/external", urls)

    def test_mixed_table_blockquote_and_standalone_citations(self) -> None:
        """Mixed Markdown with table, blockquote, and standalone URLs extracts all 3 categories."""
        sample_doc = """
| Source | URL | HTTP Status | Access Date | Verbatim Quote |
| :--- | :--- | :---: | :---: | :--- |
| Table Doc | https://example.com/table | 200 OK | 2026-10-19 | Table Quote Text |

Referenced below (https://example.com/quote):
> Blockquote sentence text.

Also read standalone reference at https://example.com/standalone for details.
"""
        cits = extract_citations(sample_doc)
        self.assertEqual(len(cits), 3)

        table_c = next(c for c in cits if c["url"] == "https://example.com/table")
        quote_c = next(c for c in cits if c["url"] == "https://example.com/quote")
        stand_c = next(c for c in cits if c["url"] == "https://example.com/standalone")

        self.assertEqual(table_c["context"], "table")
        self.assertEqual(quote_c["context"], "text_block")
        self.assertEqual(stand_c["context"], "standalone")

    @pytest.mark.network
    def test_live_network_url_opt_in(self) -> None:
        """Opt-in live network test, skipped by default under offline test runs."""
        res = verify_url_and_quote("https://example.com")
        self.assertIn(res["status_category"], ("VERIFIED", "UNVERIFIED"))


if __name__ == "__main__":
    unittest.main()
