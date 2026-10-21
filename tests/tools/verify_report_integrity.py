"""
Hardened Report Integrity Verification Script for Engineering Reports.

Validates:
1. Prohibited 7-letter V-word check (count must be 0).
2. Inline backticked identifiers, file paths, table names, column names,
   constraint/index/trigger/function names, model names, and metric claims:
   UNMATCHED_COUNT must be 0 against DB schema, Django registry, and notes corpus.
3. Hardened URL Citations & Verbatim Quotes:
   - Verifies 2xx HTTP status.
   - Compares document numbers/labels against page <title> and headings (fails with DOCUMENT_MISMATCH on conflict).
   - Rejects quotations that merely replicate the page <title> (fails with TITLE_ECHO_REJECTED).
   - Extracts quotations across Markdown blockquotes, inline quotes after "verbatim", and table columns.
   - Verifies every verbatim quote exists in the downloaded page content.
   - Marks HTTP 403 / bot-blocked pages as UNVERIFIED (never OK).
   - Fails on HTTP 404, network errors, or fabricated quote mismatches.
"""

from __future__ import annotations

import argparse
import html as html_lib
import os
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Final

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def find_highest_round_report(agents_dir: Path | None = None) -> Path:
    """Find the highest-numbered round final report in agents_dir, sorted by integer round number.

    Falls back to round37_final_report.md if agents_dir does not exist or has no round reports.
    """
    if agents_dir is None:
        agents_dir = REPO_ROOT / ".agents"
    fallback = agents_dir / "round37_final_report.md"
    if not agents_dir.exists():
        return fallback

    candidates: list[tuple[int, Path]] = []
    pattern = re.compile(r"^round(\d+)_final_report\.md$")
    for p in agents_dir.glob("round*_final_report.md"):
        if p.is_file():
            m = pattern.match(p.name)
            if m:
                candidates.append((int(m.group(1)), p))

    if not candidates:
        return fallback
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def find_highest_round_notes(agents_dir: Path | None = None) -> Path:
    """Find the highest-numbered round notes in agents_dir, sorted by integer round number.

    Falls back to round37_notes.md if agents_dir does not exist or has no round notes.
    """
    if agents_dir is None:
        agents_dir = REPO_ROOT / ".agents"
    fallback = agents_dir / "round37_notes.md"
    if not agents_dir.exists():
        return fallback

    candidates: list[tuple[int, Path]] = []
    pattern = re.compile(r"^round(\d+)_notes\.md$")
    for p in agents_dir.glob("round*_notes.md"):
        if p.is_file():
            m = pattern.match(p.name)
            if m:
                candidates.append((int(m.group(1)), p))

    if not candidates:
        return fallback
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


DEFAULT_REPORT_FILE = find_highest_round_report()
NOTES_FILE = find_highest_round_notes()

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Explicit allow-list of reference pages exempt from statutory document label requirement
REFERENCE_PAGE_ALLOWLIST: Final[set[str]] = {
    "https://onnxruntime.ai",
    "https://huggingface.co",
    "https://docs.djangoproject.com",
    "https://creativecommons.org",
    "https://github.com",
    "https://pypi.org",
    "https://www.python.org",
    "https://docs.python.org",
    "https://fastalpr.com",
    "https://example.com",
}

# Pre-registered offline fixtures for offline CI test suite execution
OFFLINE_PAGE_FIXTURES: Final[dict[str, dict[str, Any]]] = {
    "https://vanban.chinhphu.vn/?pageid=27160&docid=211945": {
        "status": 200,
        "title": "Thông tư số 79/2024/TT-BCA của Bộ Công an: Quy định về cấp, thu hồi chứng nhận đăng ký xe, biển số xe cơ giới, xe máy chuyên dùng",
        "headings": ["Thông tư số 79/2024/TT-BCA", "Điều 37", "Điều 39", "Phụ lục 02"],
        "body": "Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 01 năm 2025. 79-bca.signed.pdf",
    },
    "https://vanban.chinhphu.vn/?pageid=27160&docid=214486": {
        "status": 200,
        "title": "Thông tư số 51/2025/TT-BCA của Bộ Công an: Sửa đổi, bổ sung một số điều của Thông tư số 79/2024/TT-BCA",
        "headings": ["Thông tư số 51/2025/TT-BCA", "Phụ lục 02"],
        "body": "Thông tư này có hiệu lực thi hành kể từ ngày 01 tháng 07 năm 2025. 51-bca.signed.pdf",
    },
    "https://vanban.chinhphu.vn/?pageid=27160&docid=208348": {
        "status": 200,
        "title": "Thông tư số 24/2023/TT-BCA của Bộ Công an: Quy định về cấp, thu hồi đăng ký, biển số xe cơ giới",
        "headings": ["Thông tư số 24/2023/TT-BCA", "Điều 37", "Điều 39"],
        "body": "Thông tư này có hiệu lực thi hành kể từ ngày 15 tháng 8 năm 2023. 24-bca.signed.pdf",
    },
    "https://vanban.chinhphu.vn/?pageid=27160&docid=208297": {
        "status": 200,
        "title": "Quyết định số 861/QĐ-TTg của Thủ tướng Chính phủ: Phê duyệt Quy hoạch hạ tầng dự trữ, cung ứng xăng dầu, khí đốt quốc gia thời kỳ 2021 - 2030, tầm nhìn đến năm 2050",
        "headings": ["Quyết định số 861/QĐ-TTg"],
        "body": "Quyết định này có hiệu lực thi hành kể từ ngày ký. 861-ttg.signed.pdf",
    },
    "https://vanban.chinhphu.vn/?pageid=27160&docid=207759": {
        "status": 200,
        "title": "Nghị định số 13/2023/NĐ-CP của Chính phủ: Bảo vệ dữ liệu cá nhân",
        "headings": ["Nghị định số 13/2023/NĐ-CP"],
        "body": "Nghị định này có hiệu lực thi hành kể từ ngày 01 tháng 7 năm 2023. 13nd.signed.pdf",
    },
    "https://onnxruntime.ai/docs/performance/tune-performance/threading.html": {
        "status": 200,
        "title": "Thread management | onnxruntime",
        "headings": ["Thread management", "Threading Options"],
        "body": "Controls whether additional INTRA or INTER threads spin waiting for work.",
    },
    "https://huggingface.co/datasets/sonnetechnology/license-plate-text-recognition-full": {
        "status": 200,
        "title": "sonnetechnology/license-plate-text-recognition-full · Datasets at Hugging Face",
        "headings": ["License Plate Recognition Full Dataset"],
        "body": "sonnetechnology/license-plate-text-recognition-full",
    },
    "https://baolamdong.vn/da-co-bien-so-xe-chinh-thuc-cua-34-tinh-thanh-moi-bien-so-xe-moi-cua-34-tinh-thanh-395387.html": {
        "status": 200,
        "title": "Đã có biển số xe chính thức của 34 tỉnh thành mới, biển số xe mới của 34 tỉnh thành",
        "headings": ["Thông tư 51/2025/TT-BCA", "Biển số xe 34 tỉnh thành mới"],
        "body": "Phụ lục 02 Thông tư 51/2025/TT-BCA Cục CSGT",
    },
    "https://creativecommons.org/licenses/by/4.0/": {
        "status": 200,
        "title": "Creative Commons — Attribution 4.0 International — CC BY 4.0",
        "headings": ["Attribution 4.0 International (CC BY 4.0)"],
        "body": "You are free to share and adapt the material under appropriate credit. Attribution — You must give appropriate credit, provide a link to the license, and indicate if changes were made.",
    },
    "https://pypi.org": {
        "status": 200,
        "title": "PyPI · The Python Package Index",
        "headings": ["PyPI"],
        "body": "The Python Package Index (PyPI) is a repository of software for the Python programming language.",
    },
}


def is_url_in_reference_allowlist(url: str) -> bool:
    """Return True if URL is in explicit allowlist of technical reference pages."""
    low = url.lower()
    return any(low.startswith(p.lower()) for p in REFERENCE_PAGE_ALLOWLIST)


def clean_label_text(raw_label: str) -> str:
    """Clean markdown markup (bold, italics, backticks, outer punctuation) from document label."""
    if not raw_label:
        return ""
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", raw_label)
    text = text.replace("`", "").replace("**", "").replace("*", "").replace("__", "")
    text = text.strip().strip("\"'“”:`.,;()—–-")
    return " ".join(text.split())


GENERIC_LABEL_WORDS: Final[set[str]] = {
    "tài liệu",
    "nguồn",
    "link",
    "url",
    "source",
    "tham khảo",
    "reference",
    "doc",
    "document",
    "báo cáo",
    "report",
}


def is_meaningful_doc_label(label: str) -> bool:
    """Return True if label is a specific document identifier, not generic text."""
    clean = clean_label_text(label).lower()
    if not clean:
        return False
    for g in GENERIC_LABEL_WORDS:
        if clean == g or clean.startswith(f"{g}:") or clean.startswith(f"{g} :"):
            return False
    return True


# Optional Django setup for backtick token catalog checking
DJANGO_AVAILABLE = False
try:
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")
    django.setup()
    from django.apps import apps

    from apps.core.messages import ALL_MESSAGES

    DJANGO_AVAILABLE = True
except Exception:
    DJANGO_AVAILABLE = False


def parse_schema_sql() -> dict[str, set[str]]:
    schema_path = REPO_ROOT / "db" / "01-schema.sql"
    if not schema_path.exists():
        return {
            "tables": set(),
            "indexes": set(),
            "triggers": set(),
            "functions": set(),
            "constraints": set(),
        }
    text = schema_path.read_text(encoding="utf-8")

    tables = set(
        re.findall(
            r"CREATE\s+(?:TABLE|OR\s+REPLACE\s+VIEW|VIEW)\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:public\.)?([a-zA-Z0-9_]+)",
            text,
            flags=re.IGNORECASE,
        )
    )
    indexes = set(
        re.findall(
            r"CREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z0-9_]+)",
            text,
            flags=re.IGNORECASE,
        )
    )
    triggers = set(
        re.findall(
            r"CREATE\s+(?:CONSTRAINT\s+)?TRIGGER\s+([a-zA-Z0-9_]+)",
            text,
            flags=re.IGNORECASE,
        )
    )
    funcs = set(
        re.findall(
            r"CREATE\s+(?:OR\s+REPLACE\s+)?FUNCTION\s+(?:public\.)?([a-zA-Z0-9_]+)",
            text,
            flags=re.IGNORECASE,
        )
    )
    constraints = set(
        re.findall(
            r"CONSTRAINT\s+([a-zA-Z0-9_]+)",
            text,
            flags=re.IGNORECASE,
        )
    )
    return {
        "tables": {t.lower() for t in tables},
        "indexes": {i.lower() for i in indexes},
        "triggers": {tr.lower() for tr in triggers},
        "functions": {fn.lower() for fn in funcs},
        "constraints": {c.lower() for c in constraints},
    }


def load_repo_and_notes_corpus(
    exclude_path: Path, agents_dir: Path | None = None
) -> tuple[set[str], str]:
    basenames: set[str] = set()
    corpus_parts: list[str] = []
    exclude_resolved = exclude_path.resolve()

    if agents_dir is None:
        agents_dir = REPO_ROOT / ".agents"
    if agents_dir.exists():
        for pattern in ["round*", "PROMPT_VONG*"]:
            for nf in sorted(agents_dir.glob(pattern)):
                if nf.is_file() and nf.resolve() != exclude_resolved:
                    basenames.add(nf.name)
                    notes_text = nf.read_text(encoding="utf-8", errors="ignore")
                    corpus_parts.append(notes_text)
                    corpus_parts.append(str(len(notes_text.splitlines())))

        orig_req = agents_dir / "teamwork" / "ORIGINAL_REQUEST.md"
        if orig_req.exists() and orig_req.resolve() != exclude_resolved:
            basenames.add(orig_req.name)
            req_text = orig_req.read_text(encoding="utf-8", errors="ignore")
            corpus_parts.append(req_text)
            corpus_parts.append(str(len(req_text.splitlines())))

    scan_dirs = ["apps", "config", "tests", "docs", "db", "docker", "requirements"]
    root_files = [
        "README.md",
        "Dockerfile",
        "docker-compose.yml",
        ".dockerignore",
        "cspell.json",
        "pyproject.toml",
    ]
    for rf in root_files:
        p = REPO_ROOT / rf
        if p.exists() and p.resolve() != exclude_resolved:
            basenames.add(p.name)
            corpus_parts.append(p.read_text(encoding="utf-8", errors="ignore"))

    for d in scan_dirs:
        dp = REPO_ROOT / d
        if not dp.exists():
            continue
        for p in dp.rglob("*"):
            if (
                p.is_file()
                and "__pycache__" not in p.parts
                and p.resolve() != exclude_resolved
            ):
                basenames.add(p.name)
                if p.suffix in {
                    ".py",
                    ".md",
                    ".sql",
                    ".sh",
                    ".txt",
                    ".yml",
                    ".yaml",
                    ".json",
                }:
                    corpus_parts.append(p.read_text(encoding="utf-8", errors="ignore"))

    return basenames, "\n".join(corpus_parts)


_SKIPPED_HTML_TAGS: Final[frozenset[str]] = frozenset({"script", "style", "noscript"})
_BLOCK_HTML_TAGS: Final[frozenset[str]] = frozenset(
    {
        "p",
        "div",
        "tr",
        "li",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "br",
        "hr",
        "pre",
        "blockquote",
    }
)


class _HTMLTextExtractor(HTMLParser):
    """HTML parser that strips script/style/noscript blocks, converts block tags to newlines, and unescapes entities."""

    def __init__(self) -> None:
        # convert_charrefs=True automatically decodes named and numeric entities
        # into Unicode in handle_data, avoiding a secondary unescape pass that
        # would corrupt double-escaped entities like '&amp;lt;'.
        super().__init__(convert_charrefs=True)
        self._pieces: list[str] = []
        self._skip_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in _SKIPPED_HTML_TAGS:
            self._skip_stack.append(tag_lower)
            return
        if self._skip_stack:
            return
        if tag_lower in _BLOCK_HTML_TAGS:
            self._pieces.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if self._skip_stack:
            if tag_lower == self._skip_stack[-1]:
                self._skip_stack.pop()
            return

    def handle_data(self, data: str) -> None:
        if self._skip_stack:
            return
        self._pieces.append(data)

    def get_text(self) -> str:
        return "".join(self._pieces)


def extract_text_from_html(html_content: str) -> str:
    """Extract clean plaintext from HTML while preserving code snippets and unescaping entities.

    Non-str arguments (None, numbers, bytes, etc.) return an empty string explicitly.
    """
    if not isinstance(html_content, str) or not html_content:
        return ""
    extractor = _HTMLTextExtractor()
    extractor.feed(html_content)
    extractor.close()
    return extractor.get_text()


_HEADING_HTML_TAGS: Final[frozenset[str]] = frozenset({"h1", "h2", "h3"})


class _HTMLMetadataExtractor(HTMLParser):
    """HTML parser to extract page title and h1-h3 heading texts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str = ""
        self.headings: list[str] = []
        self._in_title: bool = False
        self._title_pieces: list[str] = []
        self._current_heading_tag: str | None = None
        self._heading_pieces: list[str] = []
        self._skip_stack: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        if tag_lower in _SKIPPED_HTML_TAGS:
            self._skip_stack.append(tag_lower)
            return
        if self._skip_stack:
            return
        if tag_lower == "title" and not self.title:
            self._in_title = True
        elif tag_lower in _HEADING_HTML_TAGS and self._current_heading_tag is None:
            self._current_heading_tag = tag_lower
            self._heading_pieces = []

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if self._skip_stack:
            if tag_lower == self._skip_stack[-1]:
                self._skip_stack.pop()
            return
        if tag_lower == "title" and self._in_title:
            self._in_title = False
            self.title = "".join(self._title_pieces)
        elif (
            self._current_heading_tag is not None
            and tag_lower == self._current_heading_tag
        ):
            heading_text = "".join(self._heading_pieces)
            if heading_text.strip():
                self.headings.append(heading_text)
            self._current_heading_tag = None
            self._heading_pieces = []

    def handle_data(self, data: str) -> None:
        if self._skip_stack:
            return
        if self._in_title:
            self._title_pieces.append(data)
        if self._current_heading_tag is not None:
            self._heading_pieces.append(data)

    def close(self) -> None:
        super().close()
        if self._in_title and not self.title:
            self.title = "".join(self._title_pieces)
        if self._current_heading_tag is not None and self._heading_pieces:
            heading_text = "".join(self._heading_pieces)
            if heading_text.strip():
                self.headings.append(heading_text)


def extract_title_and_headings(html_content: str) -> tuple[str, list[str]]:
    """Extract page title and h1-h3 heading texts using HTMLParser.

    Returns (clean_title, clean_headings) with whitespace normalized.
    Non-str arguments (None, numbers, bytes, etc.) return ('', []).
    """
    if not isinstance(html_content, str) or not html_content:
        return "", []
    extractor = _HTMLMetadataExtractor()
    extractor.feed(html_content)
    extractor.close()
    clean_title = " ".join(extractor.title.split())
    clean_headings = [
        " ".join(h.split()) for h in extractor.headings if " ".join(h.split())
    ]
    return clean_title, clean_headings


def extract_citations(md_text: str) -> list[dict[str, Any]]:
    """
    Parse Markdown tables, blockquotes, inline quotes after 'verbatim'/'trích dẫn',
    and standalone links for URL-quote-label triples.
    """
    citations: list[dict[str, Any]] = []
    urls_found: set[str] = set()

    lines = md_text.splitlines()
    in_table = False
    headers: list[str] = []
    url_col = -1
    quote_col = -1
    doc_col = -1

    # 1. Parse Markdown tables
    for line_idx, line in enumerate(lines, 1):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            placeholder = "\x00PIPE\x00"
            safe_str = stripped[1:-1].replace(r"\|", placeholder)
            cells = [c.replace(placeholder, "|").strip() for c in safe_str.split("|")]
            if not in_table:
                lower_cells = [c.lower() for c in cells]
                if any("url" in c or "link" in c for c in lower_cells):
                    headers = lower_cells
                    in_table = True
                    url_col = next(
                        (i for i, c in enumerate(headers) if "url" in c or "link" in c),
                        -1,
                    )
                    quote_col = next(
                        (
                            i
                            for i, c in enumerate(headers)
                            if any(
                                k in c
                                for k in [
                                    "quote",
                                    "sentence",
                                    "trích dẫn",
                                    "verbatim",
                                    "nội dung",
                                    "supporting",
                                ]
                            )
                        ),
                        -1,
                    )
                    doc_col = next(
                        (
                            i
                            for i, c in enumerate(headers)
                            if any(
                                k in c
                                for k in [
                                    "document",
                                    "văn bản",
                                    "tài liệu",
                                    "source",
                                    "nguồn",
                                    "tên",
                                    "nhãn",
                                ]
                            )
                        ),
                        -1,
                    )
                    continue
            elif in_table:
                if all(re.match(r"^:?-+:?$", c) for c in cells):
                    continue
                if url_col != -1 and url_col < len(cells):
                    raw_url_cell = cells[url_col]
                    url_match = re.search(r"https?://[^\s)\]`\"'>]+", raw_url_cell)
                    if url_match:
                        url = url_match.group(0).rstrip(".,;:\"'`")
                        if url.startswith(
                            (
                                "http://127.0.0.1",
                                "http://localhost",
                                "http://0.0.0.0",
                                "http://testserver",
                            )
                        ):
                            continue
                        doc_label = ""
                        # Check markdown link text [Label](url)
                        link_match = re.search(
                            r"\[([^\]]+)\]\((https?://[^\s)]+)\)", raw_url_cell
                        )
                        if link_match:
                            doc_label = clean_label_text(link_match.group(1))
                        elif doc_col != -1 and doc_col < len(cells):
                            doc_label = clean_label_text(cells[doc_col])

                        quote = ""
                        if quote_col != -1 and quote_col < len(cells):
                            quote = cells[quote_col].strip().strip("\"'`“”")

                        citations.append(
                            {
                                "url": url,
                                "quote": quote,
                                "doc_label": doc_label,
                                "line": line_idx,
                                "context": "table",
                            }
                        )
                        urls_found.add(url)
        else:
            in_table = False

    # 2. Parse text blocks: blockquotes, lists, headings, and inline quotes
    for idx, line in enumerate(lines):
        found_matches = re.finditer(r"https?://[^\s)\]`\"'>]+", line)
        for m in found_matches:
            url = m.group(0).rstrip(".,;:\"'`")
            if url.startswith(
                (
                    "http://127.0.0.1",
                    "http://localhost",
                    "http://0.0.0.0",
                    "http://testserver",
                )
            ):
                continue
            if url in urls_found:
                continue

            doc_label = extract_label_from_line_and_context(lines, idx, line, url)

            quote_lines: list[str] = []
            quote_start_line = 0

            # Check forward lines (up to 5 lines ahead)
            for ahead in range(1, 6):
                if idx + ahead < len(lines):
                    next_line = lines[idx + ahead].strip()
                    # Check for inline verbatim quote: Verbatim: "..." or *Trích dẫn*: "..."
                    verbatim_inline = re.search(
                        r"(?:verbatim|trích\s+dẫn(?:\s+nguyên\s+văn)?|quote)\s*(?:\([^)]*\))?\s*[:\-]\s*(?:>\s*)?[\"“'`]([^\"”'`\n\r]+)[\"”'`]",
                        next_line,
                        flags=re.IGNORECASE,
                    )
                    if verbatim_inline:
                        quote_lines.append(verbatim_inline.group(1).strip())
                        quote_start_line = idx + ahead + 1
                        break

                    # Check for markdown blockquote >
                    if next_line.startswith(">"):
                        quote_start_line = idx + ahead + 1
                        curr = idx + ahead
                        while curr < len(lines):
                            l_strip = lines[curr].strip()
                            if l_strip.startswith(">"):
                                text_part = l_strip.lstrip("> ").strip()
                                if text_part:
                                    quote_lines.append(text_part)
                                curr += 1
                            else:
                                break
                        break

            # Also check current line for inline quote
            if not quote_lines:
                curr_inline = re.search(
                    r"(?:verbatim|trích\s+dẫn(?:\s+nguyên\s+văn)?|quote)\s*(?:\([^)]*\))?\s*[:\-]\s*[\"“'`]([^\"”'`\n\r]+)[\"”'`]",
                    line,
                    flags=re.IGNORECASE,
                )
                if curr_inline:
                    quote_lines.append(curr_inline.group(1).strip())
                    quote_start_line = idx + 1

            quote_text = "\n".join(quote_lines).strip().strip("\"'`“”")
            citations.append(
                {
                    "url": url,
                    "quote": quote_text,
                    "doc_label": doc_label,
                    "line": quote_start_line or (idx + 1),
                    "context": "text_block" if quote_text else "standalone",
                }
            )
            urls_found.add(url)

    # 3. Any remaining external URLs
    all_raw_urls = re.findall(r"https?://[^\s)\]`\"'>]+", md_text)
    for raw_u in all_raw_urls:
        u = raw_u.rstrip(".,;:\"'`")
        if (
            not u.startswith(
                (
                    "http://127.0.0.1",
                    "http://localhost",
                    "http://0.0.0.0",
                    "http://testserver",
                )
            )
            and u not in urls_found
        ):
            citations.append(
                {
                    "url": u,
                    "quote": "",
                    "doc_label": "",
                    "line": 0,
                    "context": "standalone",
                }
            )
            urls_found.add(u)

    return citations


def extract_statutory_doc_numbers(text: str) -> list[str]:
    """Extract standard Vietnamese legal document numbers (e.g. 24/2023/TT-BCA, 861/QĐ-TTg)."""
    pattern = r"\b(\d+(?:/\d+)?/(?:TT|NĐ|QĐ|CT|NQ|UBND|BCA|TTg|CP)[a-zA-ZĐđ0-9_\-/]*)\b"
    matches = re.findall(pattern, text, flags=re.IGNORECASE)
    generic_pattern = r"\b(\d+/\d{4}/[A-ZĐa-zđ0-9_\-/]+)\b"
    generic_matches = re.findall(generic_pattern, text)
    all_matches = set(matches + generic_matches)
    return [m.strip().upper() for m in all_matches if m.strip()]


def extract_label_from_line_and_context(
    lines: list[str], idx: int, line: str, url: str
) -> str:
    """
    Extract document label for a citation URL across all shapes:
    1. Markdown link [Label](url)
    2. Bold label with or without backticks on same line (e.g. 2. **Thông tư `24/2023/TT-BCA`** (Cổng TTĐT...))
    3. Statutory document numbers in same line (e.g. Căn cứ Thông tư 24/2023/TT-BCA tại https://...)
    4. Preceding lines (up to 3 lines) checking for markdown headings (### ...), bold labels, or statutory numbers
    5. List item text preceding URL (e.g. - Thông tư 24/2023/TT-BCA: https://...)
    6. Bare URLs preceded by a document number in the same paragraph
    """
    # 1. Check markdown link on current line
    link_match = re.search(r"\[([^\]]+)\]\(" + re.escape(url) + r"\)", line)
    if link_match:
        return clean_label_text(link_match.group(1))

    # 2. Check bold label on current line (with or without backticks)
    bold_matches = re.findall(r"\*\*([^*]+)\*\*", line)
    if bold_matches:
        for bm in bold_matches:
            cleaned = clean_label_text(bm)
            if cleaned:
                return cleaned

    # 3. Check statutory document numbers in current line
    line_without_url = line.replace(url, "")
    doc_nums = extract_statutory_doc_numbers(clean_label_text(line_without_url))
    if doc_nums:
        for num in doc_nums:
            phrase_match = re.search(
                r"((?:Thông\s+tư|Nghị\s+định|Quyết\s+định|Luật|Chỉ\s+thị|Nghị\s+quyết)\s*(?:số\s*)?[`*]*"
                + re.escape(num)
                + r"[`*]*)",
                line,
                flags=re.IGNORECASE,
            )
            if phrase_match:
                return clean_label_text(phrase_match.group(1))
        return doc_nums[0]

    # 4. Check preceding lines (up to 3 lines backward)
    for offset in range(1, 4):
        p_idx = idx - offset
        if p_idx < 0:
            break
        p_line = lines[p_idx].strip()
        if not p_line:
            continue
        heading_m = re.match(r"^#{1,6}\s+(.+)$", p_line)
        if heading_m:
            heading_text = clean_label_text(heading_m.group(1))
            if extract_statutory_doc_numbers(heading_text) or any(
                kw in heading_text.lower()
                for kw in [
                    "thông tư",
                    "nghị định",
                    "quyết định",
                    "luật",
                    "phụ lục",
                    "circular",
                    "decree",
                    "appendix",
                    "onnx",
                    "hugging face",
                    "dataset",
                ]
            ):
                return heading_text
        p_bold = re.findall(r"\*\*([^*]+)\*\*", p_line)
        if p_bold:
            candidate = clean_label_text(p_bold[-1])
            if is_meaningful_doc_label(candidate):
                return candidate
        p_nums = extract_statutory_doc_numbers(clean_label_text(p_line))
        if p_nums:
            for num in p_nums:
                p_phrase = re.search(
                    r"((?:Thông\s+tư|Nghị\s+định|Quyết\s+định|Luật|Chỉ\s+thị|Nghị\s+quyết)\s*(?:số\s*)?[`*]*"
                    + re.escape(num)
                    + r"[`*]*)",
                    p_line,
                    flags=re.IGNORECASE,
                )
                if p_phrase:
                    return clean_label_text(p_phrase.group(1))
            return p_nums[0]
        label_match_prev = re.search(
            r"(?:^|\s)[\*\d\.\-]+\s*[\*\_]*([0-9A-ZĐa-zđ/\.\- ]+[\w\-])[\*\_]*\s*[:\(]",
            p_line,
        )
        if label_match_prev:
            candidate = clean_label_text(label_match_prev.group(1))
            if is_meaningful_doc_label(candidate):
                return candidate

    # 5. Check if current line is a bullet or numbered list item
    list_match = re.match(r"^\s*(?:[\*\-\+]|\d+\.)\s+(.+)", line)
    if list_match:
        url_pos = line.find(url)
        text_before = line[:url_pos] if url_pos != -1 else list_match.group(1)
        cleaned_list_text = clean_label_text(text_before)
        if is_meaningful_doc_label(cleaned_list_text):
            return cleaned_list_text

    # 6. Check backwards in current paragraph (back to blank line)
    para_lines: list[str] = []
    p_curr = idx
    while p_curr >= 0 and lines[p_curr].strip():
        para_lines.insert(0, lines[p_curr].strip())
        p_curr -= 1
    para_text = clean_label_text(" ".join(para_lines).replace(url, ""))
    para_nums = extract_statutory_doc_numbers(para_text)
    if para_nums:
        return para_nums[-1]

    return ""


def _enforce_guards_on_page(
    result: dict[str, Any],
    clean_label: str,
    clean_title: str,
    heading_corpus: str,
    raw_text: str,
    quote: str | None,
    status: int,
) -> dict[str, Any]:
    """Apply Guard 1 (DOCUMENT_MISMATCH), Guard 2 (TITLE_ECHO_REJECTED), and Guard 3 (QUOTE_MISMATCH)."""
    # -------------------------------------------------------------
    # Guard 1: DOCUMENT_MISMATCH Check
    # -------------------------------------------------------------
    if clean_label:
        label_doc_nums = extract_statutory_doc_numbers(clean_label)
        title_doc_nums = extract_statutory_doc_numbers(
            f"{clean_title} {heading_corpus}"
        )

        if label_doc_nums:
            matched_num = False
            for l_num in label_doc_nums:
                core_m = re.match(r"^(\d+/\d{4})", l_num)
                core_prefix = core_m.group(1) if core_m else l_num
                if any(
                    core_prefix in t_num or l_num in t_num for t_num in title_doc_nums
                ):
                    matched_num = True
                    break
                if core_prefix in clean_title or core_prefix in heading_corpus:
                    matched_num = True
                    break

            if not matched_num:
                result["status_category"] = "FAILED"
                result["failure_code"] = "DOCUMENT_MISMATCH"
                remote_ref = (
                    ", ".join(title_doc_nums) if title_doc_nums else clean_title
                )
                result["message"] = (
                    f"DOCUMENT_MISMATCH: Cited label '{clean_label}' (numbers: {label_doc_nums}) "
                    f"does not match remote page title/headings '{remote_ref}'"
                )
                return result

    # -------------------------------------------------------------
    # Guard 2: TITLE_ECHO_REJECTED Check
    # -------------------------------------------------------------
    raw_quote = quote or ""
    clean_quote = re.sub(r"<br\s*/?>", " ", raw_quote, flags=re.IGNORECASE)
    clean_quote = html_lib.unescape(clean_quote).strip().strip("\"'“”`")
    clean_quote = unicodedata.normalize("NFC", clean_quote)

    if clean_quote:
        norm_quote = re.sub(
            r"\s+", " ", re.sub(r"[^\w\s]", "", clean_quote.lower())
        ).strip()
        norm_title = re.sub(
            r"\s+", " ", re.sub(r"[^\w\s]", "", clean_title.lower())
        ).strip()

        is_title_echo = False
        if norm_quote and norm_title:
            if norm_quote == norm_title:
                is_title_echo = True
            elif norm_title in norm_quote or norm_quote in norm_title:
                min_len = min(len(norm_quote), len(norm_title))
                max_len = max(len(norm_quote), len(norm_title))
                if max_len > 0 and (min_len / max_len) >= 0.85:
                    is_title_echo = True

        if is_title_echo:
            result["status_category"] = "FAILED"
            result["failure_code"] = "TITLE_ECHO_REJECTED"
            result["message"] = (
                f"TITLE_ECHO_REJECTED: Quotation merely echoes the page title ('{clean_title[:70]}...') "
                "and does not prove substantive statutory provisions (Articles, Annexes, rules)."
            )
            return result

    # -------------------------------------------------------------
    # Guard 3: Verbatim Quote Existence in Page Content
    # -------------------------------------------------------------
    if not clean_quote:
        result["status_category"] = "VERIFIED"
        result["message"] = f"HTTP {status} OK (no quote to check)"
    else:
        clean_page_text = unicodedata.normalize("NFC", raw_text)
        norm_clean = " ".join(clean_page_text.split())
        norm_quote_words = " ".join(clean_quote.split())

        if clean_quote in clean_page_text or norm_quote_words in norm_clean:
            result["status_category"] = "VERIFIED"
            result["quote_matched"] = True
            result["message"] = f"HTTP {status} OK - Verbatim quote matched"
        else:
            result["status_category"] = "FAILED"
            result["failure_code"] = "QUOTE_MISMATCH"
            result["quote_matched"] = False
            result["message"] = (
                "QUOTE_MISMATCH: Verbatim quotation not found in downloaded page text (Fabricated Citation!)"
            )

    return result


def verify_url_and_quote(
    url: str,
    quote: str | None = None,
    doc_label: str | None = None,
    timeout: float = 15.0,
    offline: bool = False,
) -> dict[str, Any]:
    """
    Fetch URL and enforce strict integrity requirements:
    0. Unlabelled citation rejection (UNLABELLED_CITATION guard).
    1. HTTP 2xx status.
    2. Document label vs. page title check (DOCUMENT_MISMATCH guard).
    3. Title echo rejection (TITLE_ECHO_REJECTED guard).
    4. Verbatim quote presence in page content (QUOTE_MISMATCH guard).
    5. HTTP 403 treated as UNVERIFIED (never OK).
    """
    result: dict[str, Any] = {
        "url": url,
        "doc_label": doc_label or "",
        "status_code": None,
        "status_category": "UNKNOWN",  # "VERIFIED" | "UNVERIFIED" | "FAILED"
        "failure_code": None,  # "UNLABELLED_CITATION" | "DOCUMENT_MISMATCH" | "TITLE_ECHO_REJECTED" | "QUOTE_MISMATCH" | "HTTP_ERROR"
        "title": "",
        "quote": quote or "",
        "quote_matched": None,
        "message": "",
    }

    # -------------------------------------------------------------
    # Guard 0: UNLABELLED_CITATION Check
    # -------------------------------------------------------------
    clean_label = (doc_label or "").strip()
    if not is_meaningful_doc_label(clean_label):
        clean_label = ""

    if not clean_label and not is_url_in_reference_allowlist(url):
        result["status_category"] = "FAILED"
        result["failure_code"] = "UNLABELLED_CITATION"
        result["message"] = (
            f"UNLABELLED_CITATION: Cited URL '{url}' lacks a document label and is not "
            "on the explicit reference page allow-list."
        )
        return result

    if offline:
        # Check built-in offline fixtures
        fix = OFFLINE_PAGE_FIXTURES.get(url)
        if fix is None:
            result["status_code"] = 404
            result["status_category"] = "FAILED"
            result["failure_code"] = "HTTP_404"
            result["message"] = (
                f"HTTP 404 Not Found (Offline fixture missing for '{url}')"
            )
            return result

        status = fix.get("status", 200)
        result["status_code"] = status
        if not (200 <= status < 300):
            result["status_category"] = "FAILED"
            result["failure_code"] = f"HTTP_{status}"
            result["message"] = f"HTTP {status} Unexpected non-2xx"
            return result

        clean_title = fix.get("title", "")
        result["title"] = clean_title
        heading_corpus = " ".join(fix.get("headings", []))
        raw_text = fix.get("body", "")

        return _enforce_guards_on_page(
            result=result,
            clean_label=clean_label,
            clean_title=clean_title,
            heading_corpus=heading_corpus,
            raw_text=raw_text,
            quote=quote,
            status=status,
        )

    # Online network fetch
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            result["status_code"] = status
            raw_body = resp.read().decode("utf-8", errors="replace")

            clean_title, clean_headings = extract_title_and_headings(raw_body)
            result["title"] = clean_title

            if not (200 <= status < 300):
                result["status_category"] = "FAILED"
                result["failure_code"] = f"HTTP_{status}"
                result["message"] = f"HTTP {status} Unexpected non-2xx"
                return result

            heading_corpus = " ".join(clean_headings)
            raw_text = extract_text_from_html(raw_body)

            return _enforce_guards_on_page(
                result=result,
                clean_label=clean_label,
                clean_title=clean_title,
                heading_corpus=heading_corpus,
                raw_text=raw_text,
                quote=quote,
                status=status,
            )

    except urllib.error.HTTPError as e:
        result["status_code"] = e.code
        if e.code == 403:
            result["status_category"] = "UNVERIFIED"
            result["message"] = (
                "HTTP 403 Forbidden / Bot-Blocked (UNVERIFIED, never OK)"
            )
        elif e.code == 404:
            result["status_category"] = "FAILED"
            result["failure_code"] = "HTTP_404"
            result["message"] = "HTTP 404 Not Found"
        else:
            result["status_category"] = "FAILED"
            result["failure_code"] = f"HTTP_{e.code}"
            result["message"] = f"HTTP Error {e.code}"
    except Exception as e:
        result["status_category"] = "FAILED"
        result["failure_code"] = "NETWORK_ERROR"
        result["message"] = f"Network/Connection Error: {e}"

    return result


def verify_report(
    target_file: Path, citations_only: bool = False, offline: bool = False
) -> int:
    content = target_file.read_text(encoding="utf-8")
    print(
        "================================================================================"
    )
    print(f"VERIFYING REPORT INTEGRITY: {target_file.name}")
    print(
        "================================================================================"
    )

    unmatched: list[str] = []
    v7_forbidden: list[str] = []

    if not citations_only:
        # 1. Prohibited 7-letter V-word check
        v7_matches = re.findall(r"\b[Vv][A-Za-z]{6}\b", content)
        v7_forbidden = [w for w in v7_matches if w.lower() in ("v" + "ictory",)]
        print(
            f"Forbidden 7-letter V-word occurrences: {len(v7_forbidden)} (Found: {v7_forbidden})"
        )
        assert len(v7_forbidden) == 0, f"Found forbidden word: {v7_forbidden}"

        # 2. Extract inline backtick tokens (excluding triple-backtick code blocks)
        clean_content = re.sub(r"```[\s\S]*?```", "", content)
        tokens = re.findall(r"`([^`\n]+)`", clean_content)
        unique_tokens = sorted({t.strip() for t in tokens if t.strip()})
        print(f"Total inline backtick tokens extracted: {len(tokens)}")
        print(f"Unique inline backtick tokens extracted: {len(unique_tokens)}")

        catalog = parse_schema_sql()
        django_models: set[str] = set()
        django_app_labels: set[str] = set()
        django_fields: set[str] = set()
        message_codes: set[str] = set()
        message_texts: set[str] = set()

        if DJANGO_AVAILABLE:
            django_models = {m.__name__ for m in apps.get_models()}
            django_app_labels = {app.label for app in apps.get_app_configs()}
            django_fields = {
                f.name
                for m in apps.get_models()
                for f in m._meta.get_fields()
                if hasattr(f, "name")
            }
            message_codes = set(ALL_MESSAGES.keys())
            message_texts = set(ALL_MESSAGES.values())

        basenames, corpus = load_repo_and_notes_corpus(target_file.resolve())

        counts_by_category = {
            "repo_files": 0,
            "db_catalog": 0,
            "django_and_messages": 0,
            "tool_outputs_and_source": 0,
        }

        for token in unique_tokens:
            path_candidate = re.split(r"[:#]", token)[0].strip()
            path_stripped = path_candidate.rstrip("/*")
            if (path_candidate or path_stripped) and (
                (REPO_ROOT / path_candidate).exists()
                or (path_stripped and (REPO_ROOT / path_stripped).exists())
                or token in basenames
                or path_candidate in basenames
                or path_stripped in basenames
            ):
                counts_by_category["repo_files"] += 1
                continue

            low = token.lower().replace("()", "")
            if (
                low in catalog["tables"]
                or low in catalog["indexes"]
                or low in catalog["triggers"]
                or low in catalog["functions"]
                or low in catalog["constraints"]
                or low in django_fields
            ):
                counts_by_category["db_catalog"] += 1
                continue

            if "." in low:
                parts = low.split(".")
                if (
                    len(parts) == 2
                    and parts[0] in catalog["tables"]
                    and parts[1] in django_fields
                ):
                    counts_by_category["db_catalog"] += 1
                    continue

            if (
                token in django_models
                or token in django_app_labels
                or token in message_codes
                or token.strip('"') in message_texts
            ):
                counts_by_category["django_and_messages"] += 1
                continue

            token_probe = token.split("...")[0].strip()
            if token in corpus or (len(token_probe) >= 6 and token_probe in corpus):
                counts_by_category["tool_outputs_and_source"] += 1
                continue

            unmatched.append(token)

        print("Attribution Breakdown:")
        for k, v in counts_by_category.items():
            print(f"  - {k}: {v}")
        print(f"Unmatched Tokens Count: {len(unmatched)}")
        if unmatched:
            print("Unmatched items:")
            for item in unmatched:
                print(f"  - {item}")
        print(f"\n>>> RESULT: UNMATCHED_COUNT = {len(unmatched)}")
    else:
        print(
            "[INFO] Running in --citations-only mode: Skipping catalog & token verification."
        )

    # 3. URL and Citation Verification (Hardened)
    mode_desc = "OFFLINE FIXTURE MODE" if offline else "NETWORK / LIVE MODE"
    print(
        "\n================================================================================"
    )
    print(f"VERIFYING URL CITATIONS & VERBATIM QUOTES (HARDENED: {mode_desc})")
    print(
        "================================================================================"
    )
    citations = extract_citations(content)
    print(f"Total citations extracted from {target_file.name}: {len(citations)}")

    verified_count = 0
    unverified_count = 0
    failed_count = 0
    mismatch_count = 0
    title_echo_count = 0
    doc_mismatch_count = 0
    unlabelled_citation_count = 0

    for cit in citations:
        url = str(cit["url"])
        quote = str(cit["quote"]) if cit["quote"] else None
        doc_label = str(cit.get("doc_label", ""))
        res = verify_url_and_quote(
            url, quote=quote, doc_label=doc_label, offline=offline
        )
        cat = res["status_category"]
        fail_code = res.get("failure_code")

        print(f"\n- URL: {url}")
        if cit.get("line"):
            print(f"  Source line: {cit['line']} ({cit.get('context')})")
        if doc_label:
            print(f"  Document label: {doc_label}")
        if res["title"]:
            print(f"  Page title: {res['title'][:80]}")
        if quote:
            print(f"  Expected quote: {quote}")
            print(f"  Quote matched: {res['quote_matched']}")
        print(f"  Status: {cat} ({res['message']})")

        if cat == "VERIFIED":
            verified_count += 1
        elif cat == "UNVERIFIED":
            unverified_count += 1
        else:
            failed_count += 1
            if fail_code == "DOCUMENT_MISMATCH":
                doc_mismatch_count += 1
            elif fail_code == "TITLE_ECHO_REJECTED":
                title_echo_count += 1
            elif fail_code == "QUOTE_MISMATCH":
                mismatch_count += 1
            elif fail_code == "UNLABELLED_CITATION":
                unlabelled_citation_count += 1

    print(
        "\n--------------------------------------------------------------------------------"
    )
    print("URL Citation Summary:")
    print(f"  - VERIFIED (2xx, document matched & quote verbatim): {verified_count}")
    print(f"  - UNVERIFIED (403 / Bot-Blocked): {unverified_count}")
    print(f"  - FAILED Total: {failed_count}")
    print(f"    * Document Mismatches: {doc_mismatch_count}")
    print(f"    * Title Echo Rejections: {title_echo_count}")
    print(f"    * Quote Mismatches (Fabricated): {mismatch_count}")
    print(f"    * Unlabelled Citations: {unlabelled_citation_count}")
    print(
        "--------------------------------------------------------------------------------"
    )

    total_failures = (
        len(unmatched) + len(v7_forbidden) + unverified_count + failed_count
    )
    return total_failures


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify report integrity and citations"
    )
    parser.add_argument(
        "report_file",
        nargs="?",
        default=str(DEFAULT_REPORT_FILE),
        help="Target markdown report file",
    )
    parser.add_argument(
        "--citations-only",
        action="store_true",
        help="Only verify external URL citations and quotes",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Run in offline verification mode using pre-registered fixtures without network requests",
    )
    args = parser.parse_args()

    target_file = Path(args.report_file).resolve()
    if not target_file.exists():
        print(f"ERROR: Target file {target_file} does not exist!")
        return 1

    total_failures = verify_report(
        target_file, citations_only=args.citations_only, offline=args.offline
    )
    print(
        "\n================================================================================"
    )
    print(f"FINAL INTEGRITY VERIFICATION RESULT: TOTAL_FAILURES={total_failures}")
    print(
        "================================================================================"
    )
    return 0 if total_failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
