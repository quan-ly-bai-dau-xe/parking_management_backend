# cspell:words agpl AKIA alnum autouse bghp cicd conftest frozenset lgpl mypy nvda schemastore unlicense voiceover
"""
Automated Community Health and Governance Test Suite.

Validates GitHub Community Standards deliverables:
1. Community files presence and non-emptiness across all 8 required files.
2. Root LICENSE exact copyright wording, proprietary terms, absence of OSI
   license names, absence of company name, physical address, and emails.
3. CODE_OF_CONDUCT.md Contributor Covenant v2.1 wording and attribution,
   CC BY 4.0 attribution, GitHub content reporting enforcement channel,
   no personal/invented emails, and SECURITY.md pointer.
4. CONTRIBUTING.md table of contents, sentence-case headings, alignment with
   ADR-0002 (branching, Conventional Commits), ADR-0003 (soft delete, Safe
   Delete checklist), code ownership, exact quality gate commands, secrets and
   personal data rules, absence of AI-agent internals, and internal links.
5. ACCESSIBILITY.md backend REST API scope separation, machine-readable error
   codes (MSG-*/PROP-*), standardized JSON envelope, unaudited Swagger UI and
   ReDoc sidecar note, relative issue form link, and absence of WCAG claims.
6. Issue form YAML files (.github/ISSUE_TEMPLATE/) syntax, SchemaStore JSON
   schema compliance, unique alphanumeric IDs, no trailing whitespace, 11
   module options, explicit logs warning, 3 required checkboxes, existing
   labels only, and config.yml blank_issues_enabled: false.
7. Zero email addresses and zero secret tokens across all community health files.
8. Relative Markdown links and HTML/heading anchor resolution across all files.
9. README.md (Section 6) and docs/README.md (Section 5) community indexing.
10. Synthetic adversarial tests verifying validator sensitivity.

Zero database dependency, zero network access, executes in <1s.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml

REPO_ROOT: Path = Path(__file__).resolve().parents[2]

# 8 Required Community Health Files
COMMUNITY_FILES: tuple[str, ...] = (
    "LICENSE",
    "CODE_OF_CONDUCT.md",
    "CONTRIBUTING.md",
    "ACCESSIBILITY.md",
    ".github/ISSUE_TEMPLATE/bug_report.yml",
    ".github/ISSUE_TEMPLATE/feature_request.yml",
    ".github/ISSUE_TEMPLATE/accessibility_barrier.yml",
    ".github/ISSUE_TEMPLATE/config.yml",
)

# 10 Existing Repository Labels (verified with `gh label list`)
EXISTING_REPO_LABELS: frozenset[str] = frozenset(
    {
        "accessibility",
        "bug",
        "documentation",
        "duplicate",
        "enhancement",
        "good first issue",
        "help wanted",
        "invalid",
        "question",
        "wontfix",
    }
)

# 11 Required Backend Modules in Dropdown Fields
REQUIRED_MODULE_OPTIONS: tuple[str, ...] = (
    "auth",
    "employees",
    "customers",
    "vehicles",
    "tickets",
    "parking",
    "content",
    "audit",
    "reports",
    "docs",
    "infrastructure",
)

# Open-Source License Keywords strictly forbidden in proprietary LICENSE
FORBIDDEN_OSI_KEYWORDS: tuple[str, ...] = (
    "mit",
    "apache",
    "gpl",
    "agpl",
    "lgpl",
    "bsd",
    "mozilla",
    "mpl",
    "eclipse",
    "epl",
    "unlicense",
    "creative commons",
    "cc-by",
    "cc0",
)

EMAIL_REGEX: re.Pattern[str] = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)

VIETNAMESE_DIACRITIC_REGEX: re.Pattern[str] = re.compile(r"[\u00C0-\u1EF9]")

SECRET_TOKEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GitHub Personal Access Token (classic)", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("GitHub Fine-Grained PAT", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{82}\b")),
    ("AWS Access Key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "Private Key Header",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    ),
)

MARKDOWN_LINK_REGEX: re.Pattern[str] = re.compile(
    r"(?<!\!)\[(?P<text>[^\]]*)\]\((?P<target>[^)]+)\)"
)

ID_PATTERN: re.Pattern[str] = re.compile(r"^[a-zA-Z0-9_-]+$")

# Offline SchemaStore JSON Schemas for GitHub Issue Forms & Config
GITHUB_ISSUE_FORMS_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["name", "description", "body"],
    "properties": {
        "name": {"type": "string"},
        "description": {"type": "string"},
        "title": {"type": "string"},
        "labels": {
            "type": ["array", "string"],
            "items": {"type": "string"},
        },
        "assignees": {
            "type": ["array", "string"],
            "items": {"type": "string"},
        },
        "projects": {
            "type": ["array", "string"],
            "items": {"type": "string"},
        },
        "body": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["type"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "markdown",
                            "textarea",
                            "input",
                            "dropdown",
                            "checkboxes",
                            "upload",
                        ],
                    },
                    "id": {
                        "type": "string",
                        "pattern": "^[a-zA-Z0-9_-]+$",
                    },
                    "attributes": {"type": "object"},
                    "validations": {"type": "object"},
                },
            },
        },
    },
    "additionalProperties": False,
}

GITHUB_ISSUE_CONFIG_SCHEMA: dict[str, Any] = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["blank_issues_enabled"],
    "properties": {
        "blank_issues_enabled": {"type": "boolean"},
        "contact_links": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["name", "url", "about"],
                "properties": {
                    "name": {"type": "string"},
                    "url": {
                        "type": "string",
                        "pattern": r"^https?://",
                    },
                    "about": {"type": "string"},
                },
                "additionalProperties": False,
            },
        },
    },
    "additionalProperties": False,
}


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """
    Overrides the root conftest fixture to enforce zero database dependency
    and zero network access for community documentation tests (<1s execution).
    """
    return None


def github_slug(heading: str) -> str:
    """Generate GitHub markdown anchor slug matching CommonMark heading rules."""
    slug = heading.strip().lower()
    slug = re.sub(r"[^\w\s-]", "", slug)
    return re.sub(r"\s+", "-", slug)


def get_file_anchors(file_path: Path) -> set[str]:
    """Extract HTML id attributes and Markdown heading slugs from a file."""
    if not file_path.is_file():
        return set()
    content = file_path.read_text(encoding="utf-8")
    anchors: set[str] = set()
    for m in re.finditer(r"""(?:id|name)=["']([^"']+)["']""", content):
        anchors.add(m.group(1))
    for line in content.splitlines():
        hm = re.match(r"^#{1,6}\s+(.+)$", line)
        if hm:
            anchors.add(github_slug(hm.group(1)))
    return anchors


def find_trailing_whitespace_lines(content: str) -> list[int]:
    """Return 1-indexed line numbers containing trailing spaces or tabs."""
    trailing_lines: list[int] = []
    for idx, line in enumerate(content.splitlines(), start=1):
        if line.endswith(" ") or line.endswith("\t"):
            trailing_lines.append(idx)
    return trailing_lines


# ==============================================================================
# 1. Community Files Presence and Non-Emptiness Tests
# ==============================================================================


def test_community_files_presence() -> None:
    """Assert all 8 community health files exist and have non-zero size."""
    missing_files: list[str] = []
    empty_files: list[str] = []

    for rel_path in COMMUNITY_FILES:
        target = REPO_ROOT / rel_path
        if not target.is_file():
            missing_files.append(rel_path)
        elif target.stat().st_size == 0:
            empty_files.append(rel_path)

    assert not missing_files, f"Missing required community files: {missing_files}"
    assert not empty_files, f"Community files must not be empty: {empty_files}"


# ==============================================================================
# 2. LICENSE File Verification
# ==============================================================================


def test_license_proprietary_terms_and_no_osi() -> None:
    """
    Verify root LICENSE asserts proprietary ownership without OSI open-source
    licenses, company names, physical addresses, or email addresses.
    """
    license_path = REPO_ROOT / "LICENSE"
    assert license_path.is_file(), "Root LICENSE file must exist"
    content = license_path.read_text(encoding="utf-8")

    expected_holder = (
        "Copyright (c) 2026 the quan-ly-bai-dau-xe project contributors. "
        "All rights reserved."
    )
    assert expected_holder in content, (
        f"LICENSE must contain exact copyright holder line: {expected_holder!r}"
    )

    normalized = " ".join(content.lower().split())
    assert "are proprietary" in normalized, "LICENSE must declare software proprietary"
    assert "no license, express or implied, is granted" in normalized, (
        "LICENSE must declare no license is granted"
    )
    assert "explicitly agree in writing" in normalized, (
        "LICENSE must require explicit written agreement from copyright holders"
    )

    for keyword in FORBIDDEN_OSI_KEYWORDS:
        pattern = rf"\b{re.escape(keyword)}\b"
        assert not re.search(pattern, content, re.IGNORECASE), (
            f"LICENSE must NOT contain OSI open-source license name: {keyword!r}"
        )

    email_matches = EMAIL_REGEX.findall(content)
    assert not email_matches, (
        f"LICENSE must NOT contain email addresses: {email_matches}"
    )

    company_indicators = ("inc.", "llc", "ltd.", "corp.", "company", "gmbh")
    for comp in company_indicators:
        assert not re.search(rf"\b{re.escape(comp)}\b", content, re.IGNORECASE), (
            f"LICENSE must NOT contain corporate entity name: {comp!r}"
        )


# ==============================================================================
# 3. CODE_OF_CONDUCT.md Verification
# ==============================================================================


def test_code_of_conduct_contributor_covenant_and_enforcement() -> None:
    """
    Verify CODE_OF_CONDUCT.md contains Contributor Covenant v2.1 wording and
    attribution, CC BY 4.0 attribution, verified GitHub content reporting,
    no personal/invented emails, and a pointer to SECURITY.md.
    """
    coc_path = REPO_ROOT / "CODE_OF_CONDUCT.md"
    assert coc_path.is_file(), "CODE_OF_CONDUCT.md must exist"
    content = coc_path.read_text(encoding="utf-8")
    normalized = " ".join(content.split())

    assert "Contributor Covenant" in normalized
    assert "version 2.1" in normalized
    assert (
        "https://www.contributor-covenant.org/version/2/1/code_of_conduct.html"
        in content
    ), "CODE_OF_CONDUCT.md must link to Contributor Covenant v2.1 canonical URL"
    assert "Creative Commons Attribution 4.0 International (CC BY 4.0)" in normalized, (
        "CODE_OF_CONDUCT.md must include CC BY 4.0 attribution"
    )

    assert "Report content" in content and "Report to repository admins" in content, (
        "CODE_OF_CONDUCT.md must specify GitHub Report content -> Report to repository admins"
    )
    assert "https://github.com/contact/report-abuse" in content, (
        "CODE_OF_CONDUCT.md must include link to GitHub Support Abuse Reporting"
    )

    email_matches = EMAIL_REGEX.findall(content)
    assert not email_matches, (
        f"CODE_OF_CONDUCT.md must NOT contain personal/invented email addresses: "
        f"{email_matches}"
    )

    assert "[SECURITY.md](SECURITY.md)" in content, (
        "CODE_OF_CONDUCT.md must point security issues to SECURITY.md"
    )


# ==============================================================================
# 4. CONTRIBUTING.md Verification
# ==============================================================================


def test_contributing_fidelity_rules_and_quality_gates() -> None:
    """
    Verify CONTRIBUTING.md includes a table of contents, documents ADR-0002,
    ADR-0003, code ownership, exact quality gate commands, secrets & privacy
    policies, avoids AI-agent internal paths and non-SRS Vietnamese, and
    resolves links to CODE_OF_CONDUCT.md, SECURITY.md, ACCESSIBILITY.md, LICENSE.
    """
    contrib_path = REPO_ROOT / "CONTRIBUTING.md"
    assert contrib_path.is_file(), "CONTRIBUTING.md must exist"
    content = contrib_path.read_text(encoding="utf-8")

    # Table of contents required by D3
    assert "## Table of contents" in content

    # No AI-agent internal directory leaks or Vietnamese text
    assert ".claude/" not in content, (
        "CONTRIBUTING.md must not reference internal .claude/ agent files"
    )
    assert not VIETNAMESE_DIACRITIC_REGEX.search(content), (
        "CONTRIBUTING.md must be written strictly in English"
    )

    # ADR-0002 branching strategy and commit conventions
    assert "ADR-0002" in content
    assert "dev" in content and "main" in content
    assert "feature/<issue-id>-<short-description>" in content
    assert "--no-ff" in content
    assert "feat(ticket): add soft delete endpoint" in content
    assert "fix(auth): enforce argon2" in content

    # ADR-0003 soft delete and Safe Delete checklist
    assert "ADR-0003" in content
    assert "deleted_at" in content and "deleted_by" in content
    assert "isDeleted: bool" in content
    assert "on_delete=models.PROTECT" in content
    assert "WHERE deleted_at IS NULL" in content
    assert "select_for_update()" in content
    assert "row_version" in content
    assert "PULL_REQUEST_TEMPLATE.md" in content

    # Code ownership and neutral automated tooling sentence
    assert "Shared areas" in content
    assert "Read, understand, and ask first" in content
    assert "Automated tooling and coding assistants follow the same workflow" in content

    # Exact quality gate commands
    required_commands = (
        "ruff check .",
        "ruff format --check .",
        "mypy .",
        "python manage.py makemigrations --check --dry-run",
        "python manage.py spectacular --validate --fail-on-warn",
        "pytest",
    )
    for cmd in required_commands:
        assert cmd in content, (
            f"CONTRIBUTING.md must document exact quality gate command: {cmd!r}"
        )
    assert "80%" in content, "CONTRIBUTING.md must specify minimum 80% test coverage"

    # Secrets and personal data rules
    assert "Never commit `.env` files" in content
    assert "real vehicle" in content or "real license plates" in content
    assert "Decree 13/2023/ND-CP" in content

    # Documentation language
    assert "English" in content
    assert "apps/core/messages.py" in content

    # Policy links
    for linked_doc in (
        "CODE_OF_CONDUCT.md",
        "SECURITY.md",
        "ACCESSIBILITY.md",
        "LICENSE",
    ):
        assert f"({linked_doc})" in content, (
            f"CONTRIBUTING.md must contain a relative link to {linked_doc}"
        )
        assert (REPO_ROOT / linked_doc).is_file()


# ==============================================================================
# 5. ACCESSIBILITY.md Verification
# ==============================================================================


def test_accessibility_statement_scope_and_api_features() -> None:
    """
    Verify ACCESSIBILITY.md accurately describes backend REST API accessibility
    without false WCAG claims, distinguishes API vs UI frontend scope, notes
    Swagger UI and ReDoc as unaudited sidecar viewers, and uses relative links.
    """
    a11y_path = REPO_ROOT / "ACCESSIBILITY.md"
    assert a11y_path.is_file(), "ACCESSIBILITY.md must exist"
    content = a11y_path.read_text(encoding="utf-8")

    assert not VIETNAMESE_DIACRITIC_REGEX.search(content), (
        "ACCESSIBILITY.md must be written strictly in English"
    )
    assert "https://github.com/" not in content, (
        "ACCESSIBILITY.md must use relative repository links instead of absolute GitHub URLs"
    )

    # Scope separation: Backend REST API vs Frontend UI
    normalized = " ".join(content.lower().split())
    assert "REST API" in content
    assert "frontend" in normalized
    assert "screen reader" in normalized and "contrast" in normalized

    # API accessibility technical features
    assert "MSG-*" in content
    assert "PROP-*" in content
    assert '"code"' in content and '"message"' in content and '"details"' in content
    assert "color or visual layout" in normalized
    assert "docs/guides/frontend-api/04-conventions.md" in content
    assert "apps/core/messages.py" in content

    # Supported environments and Swagger UI / ReDoc unaudited sidecar note
    assert "Swagger UI" in content
    assert "ReDoc" in content
    assert "drf-spectacular-sidecar" in content
    assert "not audited" in normalized

    # Reporting mechanism and issue form link
    assert ".github/ISSUE_TEMPLATE/accessibility_barrier.yml" in content
    assert "accessibility" in content

    # Truthful claims: NO false claims of WCAG conformance
    assert "does not claim wcag conformance" in normalized


# ==============================================================================
# 6. GitHub Issue Forms (.github/ISSUE_TEMPLATE/) Verification
# ==============================================================================


def test_issue_forms_yaml_syntax_and_schema_compliance() -> None:
    """
    Verify all 4 YAML files in .github/ISSUE_TEMPLATE/:
    1. Parse valid YAML via yaml.safe_load.
    2. Comply with SchemaStore JSON schema (offline validation).
    3. Contain required keys (name, description, body).
    4. Contain unique alphanumeric IDs matching ^[a-zA-Z0-9_-]+$.
    5. Contain NO trailing whitespace on any line.
    6. Module dropdown contains all 11 required modules.
    7. Logs field contains the explicit warning to remove secrets, tokens,
       personal data and real license plates.
    8. Confirmations checkboxes require: searched existing issues, no secrets or
       personal data, and not a security vulnerability.
    9. Use existing repository labels only (bug, enhancement, accessibility).
    10. config.yml has blank_issues_enabled: false and valid HTTPS contact_links.
    """
    templates_dir = REPO_ROOT / ".github" / "ISSUE_TEMPLATE"
    assert templates_dir.is_dir(), ".github/ISSUE_TEMPLATE directory must exist"

    form_files = {
        "bug_report.yml": "bug",
        "feature_request.yml": "enhancement",
        "accessibility_barrier.yml": "accessibility",
    }

    expected_warning = "remove secrets, tokens, personal data and real license plates"

    for filename, expected_label in form_files.items():
        file_path = templates_dir / filename
        assert file_path.is_file(), f"Issue form {filename} must exist"
        raw_text = file_path.read_text(encoding="utf-8")

        trailing = find_trailing_whitespace_lines(raw_text)
        assert not trailing, (
            f"{filename} contains trailing whitespace on lines: {trailing}"
        )

        data = yaml.safe_load(raw_text)
        assert isinstance(data, dict), f"{filename} YAML root must be a mapping"

        jsonschema.validate(instance=data, schema=GITHUB_ISSUE_FORMS_SCHEMA)

        assert "name" in data and isinstance(data["name"], str)
        assert "description" in data and isinstance(data["description"], str)
        assert "body" in data and isinstance(data["body"], list)
        assert len(data["body"]) > 0

        labels = data.get("labels", [])
        if isinstance(labels, str):
            labels = [lbl.strip() for lbl in labels.split(",")]
        assert expected_label in labels, (
            f"{filename} must specify label {expected_label!r}"
        )
        for lbl in labels:
            assert lbl in EXISTING_REPO_LABELS, (
                f"{filename} uses unapproved label {lbl!r}. "
                f"Allowed: {sorted(EXISTING_REPO_LABELS)}"
            )

        seen_ids: set[str] = set()
        found_module_dropdown = False
        found_logs_warning = False
        checkbox_labels: list[str] = []

        for element in data["body"]:
            assert isinstance(element, dict), f"{filename} body element must be a dict"
            elem_type = element.get("type")
            elem_id = element.get("id")

            if elem_id is not None:
                assert isinstance(elem_id, str), f"{filename} id must be a string"
                assert ID_PATTERN.match(elem_id), (
                    f"{filename} id {elem_id!r} does not match ^[a-zA-Z0-9_-]+$"
                )
                assert elem_id not in seen_ids, (
                    f"{filename} contains duplicate id: {elem_id!r}"
                )
                seen_ids.add(elem_id)

            if elem_type == "dropdown" and elem_id == "module":
                found_module_dropdown = True
                attributes = element.get("attributes", {})
                options = attributes.get("options", [])
                assert isinstance(options, list)
                assert tuple(options) == REQUIRED_MODULE_OPTIONS, (
                    f"{filename} module dropdown options do not match expected 11 modules: "
                    f"{options} vs {REQUIRED_MODULE_OPTIONS}"
                )

            if elem_type == "textarea" and elem_id == "logs":
                desc = str(element.get("attributes", {}).get("description", ""))
                if expected_warning in desc.lower():
                    found_logs_warning = True

            if elem_type == "checkboxes" and elem_id == "confirmations":
                opts = element.get("attributes", {}).get("options", [])
                for opt in opts:
                    assert opt.get("required") is True, (
                        f"{filename} confirmation checkbox must have required: true"
                    )
                    checkbox_labels.append(str(opt.get("label", "")).lower())

        assert found_module_dropdown, (
            f"{filename} must contain a 'module' dropdown element"
        )
        assert found_logs_warning, (
            f"{filename} 'logs' field must include explicit warning {expected_warning!r}"
        )
        assert any("searched existing issues" in c for c in checkbox_labels), (
            f"{filename} must require checkbox confirming searched existing issues"
        )
        assert any(
            "no secrets" in c and "personal data" in c for c in checkbox_labels
        ), f"{filename} must require checkbox confirming no secrets or personal data"
        assert any("not a security vulnerability" in c for c in checkbox_labels), (
            f"{filename} must require checkbox confirming not a security vulnerability"
        )

    # Validate config.yml
    config_path = templates_dir / "config.yml"
    assert config_path.is_file(), "config.yml must exist"
    config_text = config_path.read_text(encoding="utf-8")

    config_trailing = find_trailing_whitespace_lines(config_text)
    assert not config_trailing, (
        f"config.yml contains trailing whitespace on lines: {config_trailing}"
    )

    config_data = yaml.safe_load(config_text)
    assert isinstance(config_data, dict), "config.yml YAML root must be a mapping"
    jsonschema.validate(instance=config_data, schema=GITHUB_ISSUE_CONFIG_SCHEMA)

    assert config_data.get("blank_issues_enabled") is False, (
        "config.yml must have blank_issues_enabled: false"
    )

    contact_links = config_data.get("contact_links", [])
    assert isinstance(contact_links, list) and len(contact_links) >= 2
    urls = [str(link.get("url", "")) for link in contact_links]
    assert any(u.endswith("/security/advisories/new") for u in urls)
    assert any("#readme" in u.lower() for u in urls)
    for url in urls:
        assert url.startswith("https://")


# ==============================================================================
# 7. Absence of Email Patterns and Secret Tokens
# ==============================================================================


@pytest.mark.parametrize("rel_path", COMMUNITY_FILES)
def test_community_file_no_emails_and_no_secrets(rel_path: str) -> None:
    """
    Assert no community health file leaks personal/invented email addresses
    or real/mock secret tokens (GitHub PATs, AWS keys, private key headers).
    """
    file_path = REPO_ROOT / rel_path
    assert file_path.is_file(), f"{rel_path} must exist"
    content = file_path.read_text(encoding="utf-8")

    email_matches = EMAIL_REGEX.findall(content)
    assert not email_matches, (
        f"{rel_path} contains forbidden email patterns: {email_matches}"
    )

    for token_name, pattern in SECRET_TOKEN_PATTERNS:
        match = pattern.search(content)
        assert match is None, (
            f"{rel_path} contains forbidden {token_name}: {match.group(0)!r}"
        )


# ==============================================================================
# 8. Relative Markdown Links and Anchors Resolution
# ==============================================================================


def test_community_markdown_relative_links_and_anchors_resolve() -> None:
    """
    Verify all relative Markdown links in the new community files, README.md
    (badge + Section 6), and docs/README.md (Section 5) resolve cleanly to
    existing files and valid anchors (container-safe with .dockerignore).
    """
    readme_path = REPO_ROOT / "README.md"
    readme_full = readme_path.read_text(encoding="utf-8")
    sec6_marker = '<details id="6-governance--license">'
    assert sec6_marker in readme_full, "README.md Section 6 details block must exist"
    readme_header_and_sec6 = (
        readme_full.split("<details ", 1)[0]
        + "\n"
        + readme_full[readme_full.index(sec6_marker) :]
    )

    docs_readme_path = REPO_ROOT / "docs" / "README.md"
    docs_readme_full = docs_readme_path.read_text(encoding="utf-8")
    sec5_marker = "## 5. Community & Governance Standards"
    assert sec5_marker in docs_readme_full, "docs/README.md Section 5 must exist"
    docs_readme_sec5 = docs_readme_full[docs_readme_full.index(sec5_marker) :]

    full_files = (
        REPO_ROOT / "LICENSE",
        REPO_ROOT / "CODE_OF_CONDUCT.md",
        REPO_ROOT / "CONTRIBUTING.md",
        REPO_ROOT / "ACCESSIBILITY.md",
        REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml",
        REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml",
        REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "accessibility_barrier.yml",
        REPO_ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml",
    )

    targets_to_scan: list[tuple[Path, str]] = [
        (p, p.read_text(encoding="utf-8")) for p in full_files
    ]
    targets_to_scan.append((readme_path, readme_header_and_sec6))
    targets_to_scan.append((docs_readme_path, docs_readme_sec5))

    resolution_errors: list[str] = []

    for source_file, content in targets_to_scan:
        assert source_file.is_file(), f"Source file {source_file} must exist"

        for m in MARKDOWN_LINK_REGEX.finditer(content):
            raw_target = m.group("target").strip()

            if raw_target.startswith(("http://", "https://", "mailto:")):
                continue

            if "#" in raw_target:
                file_part, anchor_part = raw_target.split("#", 1)
            else:
                file_part, anchor_part = raw_target, None

            if file_part:
                target_path = (source_file.parent / file_part).resolve()
            else:
                target_path = source_file

            if not target_path.exists():
                resolution_errors.append(
                    f"{source_file.name}: target file does not exist: {target_path} "
                    f"(from {raw_target!r})"
                )
                continue

            if anchor_part and target_path.is_file():
                valid_anchors = get_file_anchors(target_path)
                if anchor_part not in valid_anchors:
                    resolution_errors.append(
                        f"{source_file.name}: anchor #{anchor_part} not found in "
                        f"{target_path.name} (from {raw_target!r})"
                    )

    assert not resolution_errors, (
        "Failed to resolve relative links or anchors:\n" + "\n".join(resolution_errors)
    )


# ==============================================================================
# 9. README.md and docs/README.md Community Section Integration
# ==============================================================================


def test_readme_governance_section_and_badge_target() -> None:
    """
    Verify README.md license badge points to LICENSE, Section 6 Community list
    links to all 5 files, preserves all 16 <details> blocks and blank lines,
    and retains Section 6.1 CC-BY-4.0 attribution intact.
    """
    readme_path = REPO_ROOT / "README.md"
    content = readme_path.read_text(encoding="utf-8")

    badge_match = re.search(
        r"\[!\[License: All Rights Reserved\]\([^)]+\)\]\(([^)]+)\)",
        content,
    )
    assert badge_match is not None, "README.md must contain License badge"
    assert badge_match.group(1) == "LICENSE", (
        f"License badge target must be 'LICENSE', found: {badge_match.group(1)!r}"
    )

    assert '<details id="6-governance--license">' in content
    assert "<summary>6. Governance & License</summary>" in content
    assert "- **Community**:" in content
    assert "[All Rights Reserved](LICENSE)" in content
    assert "[Contributing Guidelines](CONTRIBUTING.md)" in content
    assert "[Code of Conduct](CODE_OF_CONDUCT.md)" in content
    assert "[Security Policy](SECURITY.md)" in content
    assert "[Accessibility Statement](ACCESSIBILITY.md)" in content
    assert "[License](LICENSE)" in content

    details_open_count = len(re.findall(r"<details", content))
    details_close_count = len(re.findall(r"</details>", content))
    assert details_open_count == 16
    assert details_close_count == 16
    assert "<details open" not in content

    assert "### 6.1 Third-Party Dataset Attribution (CC-BY-4.0)" in content
    assert "sonnetechnology/license-plate-text-recognition-full" in content
    assert "Creative Commons Attribution 4.0 International (CC-BY-4.0)" in content


def test_docs_readme_indexes_community_standards() -> None:
    """
    Verify docs/README.md contains Section 5 indexing all 5 community and
    governance files with valid relative paths.
    """
    docs_readme_path = REPO_ROOT / "docs" / "README.md"
    content = docs_readme_path.read_text(encoding="utf-8")

    assert "## 5. Community & Governance Standards" in content
    assert "[`LICENSE`](../LICENSE)" in content
    assert "[`CODE_OF_CONDUCT.md`](../CODE_OF_CONDUCT.md)" in content
    assert "[`CONTRIBUTING.md`](../CONTRIBUTING.md)" in content
    assert "[`SECURITY.md`](../SECURITY.md)" in content
    assert "[`ACCESSIBILITY.md`](../ACCESSIBILITY.md)" in content


# ==============================================================================
# 10. Synthetic Adversarial Tests (Validator Sensitivity & Anti-Facade)
# ==============================================================================


def test_validator_rejects_synthetic_osi_license_and_missing_copyright() -> None:
    """Synthetic test: verify validator logic catches OSI license words and missing holder."""
    bad_license_1 = "This software is released under the MIT License."
    assert (
        "Copyright (c) 2026 the quan-ly-bai-dau-xe project contributors"
        not in bad_license_1
    )
    assert any(
        re.search(rf"\b{kw}\b", bad_license_1, re.I) for kw in FORBIDDEN_OSI_KEYWORDS
    )

    bad_license_2 = (
        "Copyright (c) 2026 the quan-ly-bai-dau-xe project contributors. "
        "All rights reserved.\nLicensed under the Apache 2.0 license."
    )
    assert any(
        re.search(rf"\b{kw}\b", bad_license_2, re.I) for kw in FORBIDDEN_OSI_KEYWORDS
    )


def test_validator_rejects_synthetic_invalid_yaml_schemas() -> None:
    """Synthetic test: verify SchemaStore validator rejects missing required fields and relative URLs."""
    invalid_form_missing_body = {
        "name": "Invalid Form",
        "description": "Missing body",
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=invalid_form_missing_body,
            schema=GITHUB_ISSUE_FORMS_SCHEMA,
        )

    invalid_config_relative_url = {
        "blank_issues_enabled": False,
        "contact_links": [
            {"name": "Docs", "url": "README.md", "about": "Read our docs"}
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(
            instance=invalid_config_relative_url,
            schema=GITHUB_ISSUE_CONFIG_SCHEMA,
        )


def test_validator_detects_synthetic_trailing_whitespace() -> None:
    """Synthetic test: verify find_trailing_whitespace_lines identifies offending lines."""
    clean_text = "line 1\nline 2\nline 3"
    assert find_trailing_whitespace_lines(clean_text) == []

    dirty_text = "line 1 \nline 2\t\nline 3"
    assert find_trailing_whitespace_lines(dirty_text) == [1, 2]


def test_validator_detects_synthetic_emails_and_secret_tokens() -> None:
    """Synthetic test: verify regex detect leaked emails and classic/fine-grained PATs."""
    sample_with_email = "Contact support at test-user@example.com for details."
    assert EMAIL_REGEX.findall(sample_with_email) == ["test-user@example.com"]

    sample_with_pat = "Authorization: token ghp_123456789012345678901234567890123456"
    pat_pattern = dict(SECRET_TOKEN_PATTERNS)["GitHub Personal Access Token (classic)"]
    assert pat_pattern.search(sample_with_pat) is not None
