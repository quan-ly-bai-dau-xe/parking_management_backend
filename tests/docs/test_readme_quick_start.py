# cspell:words alnum cach dotenv unpermitted
"""
Automated quality gate for README.md Quick Start (Section 3) dual-path setup documentation.

Validates documentation invariants (a) through (g):
(a) New level-3 headings exist in Section 3 in exact order, and legacy Option A/B headings no longer exist.
(b) Text of Option 2 contains no mentions of docker, compose, or Docker, except the single allowed
    closing sentence pointing to Option 1 (asserted by an explicit marker).
(c) Every `python manage.py <command>` in the startup span is a real management command.
(d) Every environment variable written in .env code blocks of the startup span exists in .env.example.
(e) Every relative file path or markdown link in the startup span points to an existing repository file.
(f) The login URL in README.md is `/api/v1/auth/login/` and no occurrence of `/api/v1/login` remains.
(g) Headings for Steps 8, 9, 10, 11 and anchor `#step-11-production-operations-runbook--incident-playbooks-j7d-standard-6`
    remain intact.

Includes synthetic unit tests verifying that all validators accurately detect intentional defects.
Zero network, zero Docker, zero database dependencies.
"""

import re
from pathlib import Path

import pytest

# Repository root directory
REPO_ROOT: Path = Path(__file__).resolve().parents[2]
README_PATH: Path = REPO_ROOT / "README.md"
ENV_EXAMPLE_PATH: Path = REPO_ROOT / ".env.example"


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """
    Overrides the root conftest fixture to enforce zero database dependency
    for documentation tests.
    """
    return None


# Expected new level-3 headings in Section 3
EXPECTED_NEW_HEADINGS: list[str] = [
    "### Choose how to run the backend",
    "### Option 1: run with Docker",
    "### Option 2: run with Python and a locally installed PostgreSQL (no Docker)",
    "### Verify the backend and try a login (both options)",
    "### Environment variables",
    "### Troubleshooting",
]

# Explicit marker required on the single allowed closing sentence in Option 2 pointing to Option 1
CLOSING_DOCKER_POINTER_MARKER: str = "<!-- closing-docker-pointer -->"

# Expected Step 11 anchor slug referenced by docs/adr/0007-*.md
EXPECTED_STEP_11_ANCHOR: str = (
    "step-11-production-operations-runbook--incident-playbooks-j7d-standard-6"
)

# Standard Django built-in management commands permitted in documentation
STANDARD_DJANGO_COMMANDS: set[str] = {
    "check",
    "collectstatic",
    "createsuperuser",
    "dbshell",
    "diffsettings",
    "dumpdata",
    "flush",
    "inspectdb",
    "loaddata",
    "makemigrations",
    "migrate",
    "optimizemigration",
    "runserver",
    "sendtestemail",
    "shell",
    "showmigrations",
    "sqlflush",
    "sqlmigrate",
    "sqlsequencereset",
    "squashmigrations",
    "startapp",
    "startproject",
    "test",
    "testserver",
    "spectacular",
}


def github_markdown_slug(heading_text: str) -> str:
    """
    Derives GitHub Markdown anchor slug from a heading line.

    GitHub strips '#' prefix and punctuation (leaving alnum, spaces, hyphens),
    lowercases characters, and converts spaces to hyphens. For example, ' & '
    loses '&' leaving two spaces, which become '--'.
    """
    stripped = re.sub(r"^#+\s*", "", heading_text).strip().lower()
    filtered = "".join(c if c.isalnum() or c in " -" else "" for c in stripped)
    return filtered.replace(" ", "-")


def read_readme_text(path: Path = README_PATH) -> str:
    """Reads and returns the complete text of README.md."""
    return path.read_text(encoding="utf-8")


def get_section_3_text(readme_text: str) -> str:
    """
    Extracts Section 3 of README.md (from '3. Quick Start' to the next Section 4).
    Supports both collapsible <details>/<summary> structure and legacy '## 3.' headings.
    """
    start_match = re.search(
        r"^(?:<details\s+id=[\"']3-quick-start-development--operations[\"']>|<summary>3\. Quick Start|## 3\. Quick Start).*$",
        readme_text,
        flags=re.MULTILINE,
    )
    if not start_match:
        raise ValueError(
            "Could not find '## 3. Quick Start' or Section 3 details/summary in README.md"
        )

    start_pos = start_match.start()
    end_match = re.search(
        r"^(?:<details\s+id=[\"']4-cicd|<summary>4\. CI/CD|## 4\.).*$",
        readme_text[start_match.end() :],
        flags=re.MULTILINE,
    )
    if end_match:
        end_pos = start_match.end() + end_match.start()
        return readme_text[start_pos:end_pos]
    return readme_text[start_pos:]


def get_startup_span_text(readme_text: str) -> str:
    """
    Extracts the start-up portion of Section 3:
    From 'Choose how to run the backend' (or legacy headings)
    up to but excluding 'Step 8: Interactive API Documentation'.
    Supports both collapsible <details>/<summary> structure and legacy '### ' headings.
    """
    section_3 = get_section_3_text(readme_text)

    new_start_match = re.search(
        r"^(?:<details\s+id=[\"']choose-how-to-run-the-backend[\"']>|<summary>Choose how to run the backend</summary>|###\s+Choose how to run the backend)",
        section_3,
        flags=re.MULTILINE,
    )
    if new_start_match:
        start_idx = new_start_match.start()
    else:
        old_start_match = re.search(
            r"^###\s+(?:Chọn cách chạy|Step 1:\s+Environment Configuration)",
            section_3,
            flags=re.MULTILINE,
        )
        if not old_start_match:
            raise ValueError("Could not find start of start-up span in Section 3")
        start_idx = old_start_match.start()

    end_match = re.search(
        r"^(?:<details\s+id=[\"']step-8-interactive-api-documentation|<summary>Step 8:\s+Interactive API Documentation|###\s+Step 8:\s+Interactive API Documentation)",
        section_3[start_idx:],
        flags=re.MULTILINE,
    )
    if not end_match:
        raise ValueError(
            "Could not find '### Step 8: Interactive API Documentation' or summary in Section 3"
        )

    end_idx = start_idx + end_match.start()
    return section_3[start_idx:end_idx]


def get_cach_2_block(readme_text: str) -> str | None:
    """
    Extracts the block of Option 2 from its heading/summary/details to the next section.
    Returns None if Option 2 is not present.
    """
    pattern = (
        r"^(?:<details\s+id=[\"']option-2-run-with-python-and-a-locally-installed-postgresql-no-docker[\"']>"
        r"|<summary>Option 2: run with Python and a locally installed PostgreSQL \(no Docker\)</summary>"
        r"|###\s+Option 2: run with Python and a locally installed PostgreSQL \(no Docker\))"
    )
    match = re.search(pattern, readme_text, flags=re.MULTILINE)
    if not match:
        return None

    pos = match.start()
    after_heading = match.end()

    next_section_pattern = (
        r"^(?:<details\s+id=[\"']verify-the-backend-and-try-a-login-both-options[\"']>"
        r"|<summary>Verify the backend and try a login \(both options\)</summary>"
        r"|###\s+Verify the backend and try a login \(both options\)"
        r"|###\s+)"
    )
    next_match = re.search(
        next_section_pattern, readme_text[after_heading:], flags=re.MULTILINE
    )
    if next_match:
        end_pos = after_heading + next_match.start()
        return readme_text[pos:end_pos]
    return readme_text[pos:]


# Alias for backward compatibility / explicit naming
get_option_2_block = get_cach_2_block


def get_valid_management_commands(repo_root: Path = REPO_ROOT) -> set[str]:
    """
    Derives valid Django management command names dynamically from
    apps/*/management/commands/*.py stems plus standard Django built-ins.
    """
    commands = set(STANDARD_DJANGO_COMMANDS)
    for cmd_file in repo_root.glob("apps/**/management/commands/*.py"):
        if cmd_file.stem != "__init__" and not cmd_file.stem.startswith("_"):
            commands.add(cmd_file.stem)
    return commands


def get_env_example_vars(env_example_path: Path = ENV_EXAMPLE_PATH) -> set[str]:
    """
    Parses .env.example and extracts all defined environment variable keys.
    """
    text = env_example_path.read_text(encoding="utf-8")
    var_matches = re.findall(
        r"^[#\s]*([A-Z][A-Z0-9_]{2,})\s*=", text, flags=re.MULTILINE
    )
    return set(var_matches)


def validate_cach_2_content(cach_2_text: str) -> list[str]:
    """
    Validates that the body of Option 2 (or 'Cách 2') contains no mentions of docker, compose, or Docker,
    except for the single allowed closing sentence that points to Option 1 (or 'Cách 1') (asserted by
    the explicit marker CLOSING_DOCKER_POINTER_MARKER).
    Returns a list of violation messages.
    """
    lines = [line.strip() for line in cach_2_text.splitlines() if line.strip()]
    if not lines:
        return ["Block 'Option 2' is empty"]

    # Exclude the heading/summary/details opening tags and any trailing horizontal rule ('---') or closing tag ('</details>')
    start_idx = 0
    while start_idx < len(lines) and (
        lines[start_idx].startswith("### Option 2")
        or lines[start_idx].startswith("<details")
        or lines[start_idx].startswith("<summary")
        or lines[start_idx] == "</summary>"
    ):
        start_idx += 1
    body_lines = lines[start_idx:]
    while body_lines and body_lines[-1] in ("---", "</details>"):
        body_lines = body_lines[:-1]

    forbidden_pattern = re.compile(r"\b(docker|compose)\b", flags=re.IGNORECASE)
    c1_pointer_pattern = re.compile(r"Option\s+1\b", flags=re.IGNORECASE)

    violations: list[str] = []
    marked_pointer_count = 0

    for idx, line in enumerate(body_lines, start=1):
        has_marker = CLOSING_DOCKER_POINTER_MARKER in line
        line_without_marker = line.replace(CLOSING_DOCKER_POINTER_MARKER, "").strip()
        forbidden_matches = forbidden_pattern.findall(line_without_marker)

        if has_marker:
            marked_pointer_count += 1
            if idx != len(body_lines):
                violations.append(
                    f"Line {idx}: Explicit marker {CLOSING_DOCKER_POINTER_MARKER} is only allowed on the final closing line of Option 2"
                )
            if not c1_pointer_pattern.search(line_without_marker):
                violations.append(
                    f"Line {idx}: Line with explicit marker {CLOSING_DOCKER_POINTER_MARKER} must point to 'Option 1'"
                )
            if marked_pointer_count > 1:
                violations.append(
                    f"Line {idx}: Multiple lines with explicit marker {CLOSING_DOCKER_POINTER_MARKER} found"
                )
            continue

        if forbidden_matches:
            violations.append(
                f"Line {idx}: Forbidden word(s) {forbidden_matches} found without explicit marker {CLOSING_DOCKER_POINTER_MARKER} in: {line!r}"
            )

    if marked_pointer_count != 1:
        violations.append(
            f"Expected exactly 1 closing pointer line with marker {CLOSING_DOCKER_POINTER_MARKER} in Option 2, found {marked_pointer_count}"
        )

    return violations


# Alias for backward compatibility / explicit naming
validate_option_2_content = validate_cach_2_content


def extract_env_vars_from_startup_span(startup_span: str) -> set[str]:
    """
    Extracts environment variable names written in .env code blocks
    (fenced blocks tagged with 'env', 'dotenv', or pure assignment blocks).
    """
    found_vars: set[str] = set()

    code_block_pattern = re.compile(
        r"^[ \t]*```([a-zA-Z0-9_-]*)[ \t]*\n([\s\S]*?)^[ \t]*```[ \t]*$",
        flags=re.MULTILINE,
    )
    for match in code_block_pattern.finditer(startup_span):
        lang = match.group(1).lower().strip()
        code = match.group(2)
        lines = [line.strip() for line in code.splitlines() if line.strip()]

        is_env_block = False
        if lang in ("env", "dotenv"):
            is_env_block = True
        elif lang in ("", "text") and lines:
            non_comments = [
                line_entry for line_entry in lines if not line_entry.startswith("#")
            ]
            if non_comments and all(
                re.match(r"^[A-Z][A-Z0-9_]{2,}\s*=", line_entry)
                and not re.search(
                    r"\b(docker|compose|python|curl|pip|git|cp)\b", line_entry
                )
                for line_entry in non_comments
            ):
                is_env_block = True

        if is_env_block:
            for line_entry in lines:
                var_match = re.match(r"^[#\s]*([A-Z][A-Z0-9_]{2,})\s*=", line_entry)
                if var_match:
                    found_vars.add(var_match.group(1))

    return found_vars


def validate_startup_span_links_and_paths(
    startup_span: str, repo_root: Path = REPO_ROOT
) -> list[str]:
    """
    Validates that every relative file path or markdown link in startup_span points
    to an existing file in the repository.
    """
    violations: list[str] = []

    # 1. Validate markdown link targets: [label](target)
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    for match in link_pattern.finditer(startup_span):
        target = match.group(2).strip()
        # Skip absolute external URLs and intra-page anchors
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue

        rel_path = target.split("#")[0].strip()
        if not rel_path:
            continue

        target_path = repo_root / rel_path
        if not target_path.exists():
            violations.append(
                f"Markdown link target '{target}' does not exist on disk at: {target_path}"
            )

    # 2. Validate backticked relative repository file paths
    known_root_files = {
        ".env.example",
        "docker-compose.yml",
        "manage.py",
        "Dockerfile",
        "CLAUDE.md",
        "README.md",
        "pyproject.toml",
    }
    known_repo_prefixes = (
        "docs/",
        "db/",
        "requirements/",
        "apps/",
        "config/",
        "tests/",
        "docker/",
        ".claude/",
        ".github/",
    )

    backtick_pattern = re.compile(r"`([^`\n]+)`")
    for match in backtick_pattern.finditer(startup_span):
        token = match.group(1).strip()
        norm_token = token.replace("\\", "/")

        is_repo_path = norm_token in known_root_files or (
            any(norm_token.startswith(prefix) for prefix in known_repo_prefixes)
            and ("." in norm_token.split("/")[-1] or (repo_root / norm_token).is_dir())
        )

        if is_repo_path:
            resolved_file = repo_root / norm_token
            if not resolved_file.exists():
                violations.append(
                    f"Backticked path '{token}' does not exist on disk at: {resolved_file}"
                )

    return violations


# ==============================================================================
# Documentation Invariant Tests (a) through (g)
# ==============================================================================


def test_readme_req_a_new_headings_order_and_no_option_a_b() -> None:
    """
    (a) The 6 new level-3 headings exist in Section 3 in the exact expected order,
    and old headings 'Option A' and 'Option B' no longer exist.
    """
    readme_text = read_readme_text()
    section_3 = get_section_3_text(readme_text)

    # 1. Assert old headings Option A and Option B no longer exist in Section 3
    # Strip fenced code blocks so bash comments like '# Option A:' inside code blocks are ignored
    section_3_no_code = re.sub(r"```[\s\S]*?```", "", section_3)
    forbidden_old_options = re.findall(
        r"^#{1,6}\s+.*Option\s+[AB]\b.*$", section_3_no_code, flags=re.MULTILINE
    )
    assert not forbidden_old_options, (
        f"Old Option A/B headings must not exist in Section 3, but found: {forbidden_old_options}"
    )

    # 2. Assert the 6 new level-3 headings / summaries exist in Section 3 in exact order
    positions: list[tuple[str, int]] = []
    missing_headings: list[str] = []
    for heading in EXPECTED_NEW_HEADINGS:
        raw_title = heading.lstrip("#").strip()
        summary_pattern = f"<summary>{raw_title}</summary>"
        pos = section_3.find(summary_pattern)
        if pos == -1:
            pos = section_3.find(heading)
        if pos == -1:
            missing_headings.append(heading)
        else:
            positions.append((heading, pos))

    assert not missing_headings, (
        f"Missing required level-3 headings / summaries in Section 3: {missing_headings}"
    )

    for i in range(len(positions) - 1):
        h_current, pos_current = positions[i]
        h_next, pos_next = positions[i + 1]
        assert pos_current < pos_next, (
            f"Headings out of order in Section 3: '{h_current}' (offset {pos_current}) "
            f"must appear before '{h_next}' (offset {pos_next})"
        )


def test_readme_req_b_cach_2_docker_word_guard() -> None:
    """
    (b) The text of Option 2 contains none of the words 'docker', 'compose', 'Docker',
    except the single allowed closing sentence that points to Option 1 (asserted by explicit marker).
    """
    readme_text = read_readme_text()
    cach_2_block = get_cach_2_block(readme_text)

    assert cach_2_block is not None, (
        "Heading '### Option 2: run with Python and a locally installed PostgreSQL (no Docker)' "
        "not found in README.md"
    )

    violations = validate_cach_2_content(cach_2_block)
    assert not violations, (
        f"Found forbidden Docker/Compose word violations in Option 2: {violations}"
    )


def test_readme_req_c_real_management_commands_in_new_span() -> None:
    """
    (c) Every `python manage.py <command>` in the startup span is a real management command,
    dynamically derived from apps/*/management/commands/*.py and Django built-ins.
    """
    readme_text = read_readme_text()
    startup_span = get_startup_span_text(readme_text)
    valid_commands = get_valid_management_commands(REPO_ROOT)

    invocations = re.findall(r"python\s+manage\.py\s+([a-zA-Z0-9_-]+)", startup_span)
    assert invocations, (
        "Expected at least one 'python manage.py <command>' in startup span"
    )

    unknown_commands = [cmd for cmd in invocations if cmd not in valid_commands]
    assert not unknown_commands, (
        f"Found unknown management commands in startup span: {unknown_commands}. "
        f"Allowed commands: {sorted(valid_commands)}"
    )


def test_readme_req_d_env_vars_in_code_blocks_exist_in_env_example() -> None:
    """
    (d) Every environment variable name written in a .env code block of the startup span
    exists in .env.example.
    """
    readme_text = read_readme_text()
    startup_span = get_startup_span_text(readme_text)
    env_example_vars = get_env_example_vars(ENV_EXAMPLE_PATH)
    assert env_example_vars, "Could not extract environment variables from .env.example"

    startup_env_vars = extract_env_vars_from_startup_span(startup_span)

    # In the new rewritten span, .env code blocks are required
    if (
        "### Choose how to run the backend" in startup_span
        or "### Chọn cách chạy" in startup_span
    ):
        assert startup_env_vars, (
            "Expected at least one .env code block in new startup span"
        )

    unknown_vars = sorted(startup_env_vars - env_example_vars)
    assert not unknown_vars, (
        f"Found environment variables in startup span not present in .env.example: {unknown_vars}"
    )


def test_readme_req_e_relative_paths_and_links_exist() -> None:
    """
    (e) Every relative file path or markdown link in the startup span points to an existing file.
    """
    readme_text = read_readme_text()
    startup_span = get_startup_span_text(readme_text)
    violations = validate_startup_span_links_and_paths(startup_span, REPO_ROOT)
    assert not violations, (
        f"Found broken relative links or file paths in startup span: {violations}"
    )


def test_readme_req_f_login_url_uses_auth_subpath() -> None:
    """
    (f) The login URL written in README.md is `/api/v1/auth/login/` and no occurrence
    of `/api/v1/login` (legacy path missing /auth/) remains in README.md.
    """
    readme_text = read_readme_text()

    assert "/api/v1/auth/login/" in readme_text, (
        "Authoritative login URL '/api/v1/auth/login/' must be present in README.md"
    )

    legacy_matches = re.findall(r"/api/v1/login(?![a-zA-Z0-9_-])", readme_text)
    assert not legacy_matches, (
        f"Found legacy login URL without '/auth/' in README.md: {legacy_matches}"
    )


def test_readme_req_g_step_headings_and_anchor_preserved() -> None:
    """
    (g) Headings of Steps 8, 9, 10 and 11 and anchor
    #step-11-production-operations-runbook--incident-playbooks-j7d-standard-6 still exist.
    """
    readme_text = read_readme_text()

    step_patterns = {
        "Step 8": r"^(?:###\s+|<summary>)Step 8:\s+Interactive API Documentation",
        "Step 9": r"^(?:###\s+|<summary>)Step 9:\s+Run Automated Test Suite",
        "Step 10": r"^(?:###\s+|<summary>)Step 10:\s+Performance Testing",
        "Step 11": r"^(?:###\s+|<summary>)Step 11:\s+Production Operations Runbook",
    }
    for step_name, pattern in step_patterns.items():
        assert re.search(pattern, readme_text, flags=re.MULTILINE), (
            f"Required heading or summary for '{step_name}' matching '{pattern}' not found in README.md"
        )

    step_11_match = re.search(
        r"^(?:###\s+|<summary>)(Step 11:[^<\n]+)", readme_text, flags=re.MULTILINE
    )
    assert step_11_match, "Could not locate Step 11 heading or summary in README.md"
    step_11_heading = step_11_match.group(1).strip()

    generated_slug = github_markdown_slug(step_11_heading)
    assert generated_slug == EXPECTED_STEP_11_ANCHOR, (
        f"Step 11 generated slug '{generated_slug}' != expected '{EXPECTED_STEP_11_ANCHOR}'"
    )

    # Verify anchor attribute is preserved on details block
    assert f'id="{EXPECTED_STEP_11_ANCHOR}"' in readme_text, (
        f"Step 11 anchor id '{EXPECTED_STEP_11_ANCHOR}' not found in README.md details tag"
    )


# ==============================================================================
# Synthetic Unit Tests (Test Integrity Proof)
# ==============================================================================


def test_synthetic_cach_2_guard_flags_unpermitted_docker_mentions() -> None:
    """Verifies that validate_cach_2_content catches forbidden docker mentions in body."""
    bad_sample = (
        "### Option 2: run with Python and a locally installed PostgreSQL (no Docker)\n"
        "Install PostgreSQL on your local machine.\n"
        "Start service with docker compose up -d db.\n"
        f"If you prefer running the backend with Docker, see [Option 1: run with Docker](#option-1-run-with-docker). {CLOSING_DOCKER_POINTER_MARKER}\n"
    )
    violations = validate_cach_2_content(bad_sample)
    assert len(violations) == 1
    assert "Forbidden word" in violations[0]
    assert "docker" in violations[0].lower()


def test_synthetic_cach_2_guard_permits_valid_closing_pointer() -> None:
    """Verifies that validate_cach_2_content permits exactly one marked closing pointer to Option 1."""
    clean_sample = (
        "### Option 2: run with Python and a locally installed PostgreSQL (no Docker)\n"
        "Install Python 3.14.7 and PostgreSQL 18.\n"
        "Create database parking_db and grant permissions to parking_user.\n"
        f"If you prefer running the backend with Docker, see [Option 1: run with Docker](#option-1-run-with-docker). {CLOSING_DOCKER_POINTER_MARKER}\n"
    )
    violations = validate_cach_2_content(clean_sample)
    assert not violations


def test_synthetic_command_validator_flags_invalid_command() -> None:
    """Verifies that fake commands in startup span are flagged."""
    valid_commands = get_valid_management_commands(REPO_ROOT)
    fake_commands = ["unknown_bogus_command_xyz"]
    unknown = [cmd for cmd in fake_commands if cmd not in valid_commands]
    assert unknown == ["unknown_bogus_command_xyz"]


def test_synthetic_env_var_validator_flags_unlisted_variable() -> None:
    """Verifies that unlisted variables in env code block are flagged."""
    env_example_vars = get_env_example_vars(ENV_EXAMPLE_PATH)
    fake_env_block = (
        "```env\nSECRET_KEY=valid\nTOTALLY_UNKNOWN_ENV_KEY_XYZ=invalid\n```\n"
    )
    extracted = extract_env_vars_from_startup_span(fake_env_block)
    unknown = extracted - env_example_vars
    assert unknown == {"TOTALLY_UNKNOWN_ENV_KEY_XYZ"}


def test_synthetic_link_validator_flags_broken_link(tmp_path: Path) -> None:
    """Verifies that relative links pointing to non-existent files are caught."""
    span_with_broken_link = (
        "Tham khảo [Tài liệu hướng dẫn](docs/non_existent_guide_xyz.md)."
    )
    violations = validate_startup_span_links_and_paths(span_with_broken_link, tmp_path)
    assert len(violations) == 1
    assert "non_existent_guide_xyz.md" in violations[0]


def test_synthetic_login_url_validator_flags_legacy_url() -> None:
    """Verifies that legacy login path '/api/v1/login' without '/auth/' is detected."""
    legacy_text = "Gửi request POST tới /api/v1/login để đăng nhập."
    matches = re.findall(r"/api/v1/login(?![a-zA-Z0-9_-])", legacy_text)
    assert matches == ["/api/v1/login"]


def test_synthetic_markdown_slug_matches_github_anchor() -> None:
    """Verifies that github_markdown_slug reproduces the exact GitHub anchor."""
    heading = (
        "Step 11: Production Operations Runbook & Incident Playbooks (J7.d, Standard 6)"
    )
    slug = github_markdown_slug(heading)
    assert slug == EXPECTED_STEP_11_ANCHOR
