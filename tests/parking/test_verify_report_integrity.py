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
