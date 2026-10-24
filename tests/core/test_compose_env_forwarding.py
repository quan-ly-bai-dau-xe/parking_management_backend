# cspell:words unforwarded
"""
tests/core/test_compose_env_forwarding.py

AST-backed drift guard test ensuring docker-compose.yml web service forwards
all required environment variables declared in .env.example and read by
Django settings (config/settings/*.py) and Gunicorn (docker/gunicorn.conf.py).

Zero database, zero network, zero docker daemon dependencies.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE_FILE = REPO_ROOT / ".env.example"
SETTINGS_DIR = REPO_ROOT / "config" / "settings"
GUNICORN_CONF_FILE = REPO_ROOT / "docker" / "gunicorn.conf.py"


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """Override conftest db fixture: no database needed for AST/static inspection."""
    return None


# Required 16 security, session, CORS, throttle, proxy, DB-SSL, and DB pool keys
REQUIRED_SECURITY_AND_RUNTIME_KEYS: frozenset[str] = frozenset(
    {
        "CORS_ALLOWED_ORIGINS",
        "CSRF_TRUSTED_ORIGINS",
        "SESSION_COOKIE_AGE",
        "REMEMBER_ROTATION_GRACE_SECONDS",
        "REMEMBER_TOKEN_LIFETIME_DAYS",
        "REMEMBER_MAX_TOKENS_PER_ACCOUNT",
        "AUTH_THROTTLE_PAIR_LIMIT",
        "AUTH_THROTTLE_IDENTIFIER_LIMIT",
        "AUTH_THROTTLE_IP_LIMIT",
        "AUTH_THROTTLE_WINDOW_SECONDS",
        "NUM_PROXIES",
        "DB_SSLMODE",
        "DB_POOL_MIN_SIZE",
        "DB_POOL_MAX_SIZE",
        "DB_POOL_TIMEOUT",
        "DB_CONN_HEALTH_CHECKS",
    }
)

# Keys read by code that are intentionally not forwarded to the local compose development container.
# Production email/HSTS settings are deferred to production topology decisions;
# internal Gunicorn tuning parameters use safe in-code defaults.
UNFORWARDED_ALLOWLIST: dict[str, str] = {
    "EMAIL_HOST": "Read in config/settings/production.py only (compose runs config.settings.local); production deployment and settings module are an Owner decision not yet made, so forwarding is decided together with that",
    "EMAIL_PORT": "Read in config/settings/production.py only (compose runs config.settings.local); production deployment and settings module are an Owner decision not yet made, so forwarding is decided together with that",
    "EMAIL_HOST_USER": "Read in config/settings/production.py only (compose runs config.settings.local); production deployment and settings module are an Owner decision not yet made, so forwarding is decided together with that",
    "EMAIL_HOST_PASSWORD": "Read in config/settings/production.py only (compose runs config.settings.local); production deployment and settings module are an Owner decision not yet made, so forwarding is decided together with that",
    "EMAIL_USE_TLS": "Read in config/settings/production.py only (compose runs config.settings.local); production deployment and settings module are an Owner decision not yet made, so forwarding is decided together with that",
    "EMAIL_USE_SSL": "Read in config/settings/production.py only (compose runs config.settings.local); production deployment and settings module are an Owner decision not yet made, so forwarding is decided together with that",
    "SECURE_HSTS_INCLUDE_SUBDOMAINS": "Read in config/settings/production.py only (compose runs config.settings.local); production deployment and settings module are an Owner decision not yet made, so forwarding is decided together with that",
    "SECURE_HSTS_PRELOAD": "Read in config/settings/production.py only (compose runs config.settings.local); production deployment and settings module are an Owner decision not yet made, so forwarding is decided together with that",
    "SECURE_HSTS_SECONDS": "Read in config/settings/production.py only (compose runs config.settings.local); production deployment and settings module are an Owner decision not yet made, so forwarding is decided together with that",
    "SECURE_SSL_HOST": "Read in config/settings/production.py only (compose runs config.settings.local); production deployment and settings module are an Owner decision not yet made, so forwarding is decided together with that",
    "SECURE_SSL_REDIRECT": "Read in config/settings/production.py only (compose runs config.settings.local); production deployment and settings module are an Owner decision not yet made, so forwarding is decided together with that",
    "GUNICORN_BIND": "Internal container tuning with in-code defaults, not documented for operators; GUNICORN_BIND must stay 0.0.0.0:8000 to match the port mapping",
    "GUNICORN_BACKLOG": "Internal container listen-backlog tuning with in-code defaults, not documented for operators",
    "GUNICORN_GRACEFUL_TIMEOUT": "Internal container worker graceful-timeout tuning with in-code defaults, not documented for operators",
    "GUNICORN_KEEPALIVE": "Internal container HTTP keepalive tuning with in-code defaults, not documented for operators",
    "GUNICORN_LOG_LEVEL": "Internal container log-level tuning with in-code defaults, not documented for operators",
}

# Allowlist for keys permitted to have a hard-coded literal value in compose instead of ${KEY...} interpolation.
FIXED_CONTAINER_LITERAL_ALLOWLIST: dict[str, str] = {
    "POSTGRES_HOST": "Fixed to internal compose network service hostname 'db' for container networking",
    "POSTGRES_PORT": "Fixed to internal container PostgreSQL service port 5432",
}

# Allowlist for keys whose default value in docker-compose.yml intentionally differs from .env.example.
INTENTIONAL_DEFAULT_MISMATCH_ALLOWLIST: dict[str, str] = {
    "DEBUG": "Compose defaults to True for local development while .env.example defaults to False",
    "ALLOWED_HOSTS": "Compose defaults to 'localhost,127.0.0.1,web' to permit container inter-service calls",
    "SECRET_KEY": "Compose enforces mandatory required expansion ${SECRET_KEY:?...} without fallback default",
    "POSTGRES_PASSWORD": "Compose enforces mandatory required expansion ${POSTGRES_PASSWORD:?...} without fallback default",
}

# Allowlist for keys whose default value in docker-compose.yml intentionally differs from in-code defaults.
INTENTIONAL_CODE_DEFAULT_MISMATCH_ALLOWLIST: dict[str, str] = {
    "CORS_ALLOWED_ORIGINS": "Compose defaults to local dev origins http://localhost:3000,http://127.0.0.1:3000 while code defaults to empty list [] (deliberate local-stack convenience)",
    "CSRF_TRUSTED_ORIGINS": "Compose defaults to local dev origins http://localhost:3000,http://127.0.0.1:3000 while code defaults to empty list [] (deliberate local-stack convenience)",
    "ALLOWED_HOSTS": "Compose defaults to 'localhost,127.0.0.1,web' for container networking while local settings default to ['localhost', '127.0.0.1', '[::1]']",
    "POSTGRES_DB": "Compose supplies the local-development default 'parking_db' (the same value as .env.example) while the code has no usable default for this key (declared with an empty-string default in base.py and read without a default in local.py, so it is required); deliberate local-stack convenience.",
    "POSTGRES_USER": "Compose supplies the local-development default 'parking_user' (the same value as .env.example) while the code has no usable default for this key (declared with an empty-string default in base.py and read without a default in local.py, so it is required); deliberate local-stack convenience.",
}

INTERPOLATION_PATTERN = re.compile(r"^\$\{([A-Za-z0-9_]+)(?::?[-?].*)?\}$")
DEFAULT_EXTRACTION_PATTERN = re.compile(r"^\$\{([A-Za-z0-9_]+)(?::?-)(.*)\}$")
STALE_WORDING_LINE_PATTERN = re.compile(r"\bline[s]? \d+", re.IGNORECASE)


def normalize_compose_environment(raw_env: Any) -> tuple[dict[str, Any], list[str]]:
    """
    Normalizes services.web.environment into a mapping of key to value.
    Supports both YAML mapping (dict) and sequence of 'KEY=value' strings (list).
    Returns (normalized_dict, problems_list).
    """
    problems: list[str] = []
    normalized: dict[str, Any] = {}

    if isinstance(raw_env, dict):
        for k, v in raw_env.items():
            key_str = str(k).strip()
            if not key_str:
                problems.append(
                    "Empty environment variable key name in compose mapping."
                )
                continue
            normalized[key_str] = v
        return normalized, problems

    if isinstance(raw_env, list):
        for idx, item in enumerate(raw_env):
            if not isinstance(item, str):
                problems.append(
                    f"Invalid environment item at index {idx}: expected string, got {type(item).__name__}."
                )
                continue
            if "=" not in item:
                problems.append(
                    f"Malformed environment item '{item}' at index {idx}: missing '=' separator."
                )
                continue
            k, v = item.split("=", 1)
            key_str = k.strip()
            if not key_str:
                problems.append(
                    f"Malformed environment item '{item}' at index {idx}: empty key name."
                )
                continue
            normalized[key_str] = v.strip()
        return normalized, problems

    problems.append(
        f"Invalid environment format: expected dict or list, got {type(raw_env).__name__}."
    )
    return normalized, problems


def check_rule1_code_keys_forwarded_or_allowlisted(
    code_keys: set[str],
    forwarded_keys: set[str],
    unforwarded_allowlist: dict[str, str],
) -> list[str]:
    """Rule 1: Every key READ by the code is either forwarded to web.environment or in unforwarded allowlist."""
    problems: list[str] = []
    for key in sorted(code_keys):
        if key in forwarded_keys:
            continue
        if key in unforwarded_allowlist:
            if not unforwarded_allowlist[key].strip():
                problems.append(
                    f"Rule 1 violation: Allowlist entry for '{key}' must have a non-empty reason."
                )
            continue
        problems.append(
            f"Rule 1 violation: Key '{key}' read by code is neither forwarded in compose nor listed in unforwarded allowlist."
        )
    return problems


def check_rule2_interpolation_variable_names(
    normalized_env: dict[str, Any],
) -> list[str]:
    """Rule 2: Any forwarded value with interpolation must reference its own key (NAME == KEY)."""
    problems: list[str] = []
    for key, val in sorted(normalized_env.items()):
        val_str = str(val).strip()
        if val_str.startswith("${") and val_str.endswith("}"):
            match = INTERPOLATION_PATTERN.match(val_str)
            if match:
                interpolated_var = match.group(1)
                if interpolated_var != key:
                    problems.append(
                        f"Rule 2 violation: Forwarded key '{key}' interpolates variable '{interpolated_var}' instead of itself."
                    )
    return problems


def check_rule3_hardcoded_literals(
    code_keys: set[str],
    normalized_env: dict[str, Any],
    fixed_literal_allowlist: dict[str, str],
) -> list[str]:
    """Rule 3: Forwarded keys read by code must use interpolation unless listed in FIXED_CONTAINER_LITERAL_ALLOWLIST."""
    problems: list[str] = []
    forwarded_code_keys = sorted(code_keys & set(normalized_env.keys()))
    for key in forwarded_code_keys:
        val = normalized_env[key]
        val_str = str(val).strip()
        is_interpolated = (
            val_str.startswith("${")
            and val_str.endswith("}")
            and bool(INTERPOLATION_PATTERN.match(val_str))
        )
        if not is_interpolated:
            if key in fixed_literal_allowlist:
                if not fixed_literal_allowlist[key].strip():
                    problems.append(
                        f"Rule 3 violation: Fixed literal allowlist entry for '{key}' must have a non-empty reason."
                    )
            else:
                problems.append(
                    f"Rule 3 violation: Forwarded key '{key}' uses hard-coded literal '{val}' without being in FIXED_CONTAINER_LITERAL_ALLOWLIST."
                )
    return problems


def check_rule4_defaults_match_env_example(
    normalized_env: dict[str, Any],
    env_example: dict[str, str],
    mismatch_allowlist: dict[str, str],
    fixed_literal_allowlist: dict[str, str],
) -> list[str]:
    """Rule 4: Default fallback in compose must match .env.example unless exempted in mismatch allowlist."""
    problems: list[str] = []
    for key, val in sorted(normalized_env.items()):
        if key not in env_example:
            continue
        if key in fixed_literal_allowlist:
            continue
        if key in mismatch_allowlist:
            if not mismatch_allowlist[key].strip():
                problems.append(
                    f"Rule 4 violation: Mismatch allowlist entry for '{key}' must have a non-empty reason."
                )
            continue

        val_str = str(val).strip().strip("'\"")
        match = DEFAULT_EXTRACTION_PATTERN.match(val_str)
        if not match:
            continue

        compose_default = match.group(2).strip().strip("'\"")
        expected_val = env_example[key].strip().strip("'\"")
        if compose_default != expected_val:
            problems.append(
                f"Rule 4 violation: Key '{key}' default value '{compose_default}' does not match .env.example value '{expected_val}'."
            )
    return problems


def check_rule5_no_stale_allowlists(
    code_keys: set[str],
    forwarded_keys: set[str],
    unforwarded_allowlist: dict[str, str],
    fixed_literal_allowlist: dict[str, str],
    mismatch_allowlist: dict[str, str],
    env_example: dict[str, str],
    code_mismatch_allowlist: dict[str, str] | None = None,
) -> list[str]:
    """Rule 5: Allowlists must not go stale (unused keys or contradictory forwarding)."""
    problems: list[str] = []
    for key in sorted(unforwarded_allowlist.keys()):
        if key not in code_keys:
            problems.append(
                f"Rule 5 violation: Stale key '{key}' in UNFORWARDED_ALLOWLIST is not read by code."
            )
        if key in forwarded_keys:
            problems.append(
                f"Rule 5 violation: Key '{key}' in UNFORWARDED_ALLOWLIST is unexpectedly forwarded in compose."
            )

    for key in sorted(fixed_literal_allowlist.keys()):
        if key not in forwarded_keys:
            problems.append(
                f"Rule 5 violation: Stale key '{key}' in FIXED_CONTAINER_LITERAL_ALLOWLIST is not forwarded in compose."
            )

    for key in sorted(mismatch_allowlist.keys()):
        if key not in forwarded_keys:
            problems.append(
                f"Rule 5 violation: Stale key '{key}' in INTENTIONAL_DEFAULT_MISMATCH_ALLOWLIST is not forwarded in compose."
            )
        if key not in env_example:
            problems.append(
                f"Rule 5 violation: Stale key '{key}' in INTENTIONAL_DEFAULT_MISMATCH_ALLOWLIST is not defined in .env.example."
            )

    if code_mismatch_allowlist is not None:
        for key in sorted(code_mismatch_allowlist.keys()):
            if not code_mismatch_allowlist[key].strip():
                problems.append(
                    f"Rule 5 violation: Code mismatch allowlist entry for '{key}' must have a non-empty reason."
                )
            if key not in forwarded_keys:
                problems.append(
                    f"Rule 5 violation: Stale key '{key}' in INTENTIONAL_CODE_DEFAULT_MISMATCH_ALLOWLIST is not forwarded in compose."
                )
            if key not in code_keys:
                problems.append(
                    f"Rule 5 violation: Stale key '{key}' in INTENTIONAL_CODE_DEFAULT_MISMATCH_ALLOWLIST is not read by code."
                )

    return problems


def check_rule6_env_example_keys_forwarded_or_allowlisted(
    code_keys: set[str],
    env_example: dict[str, str],
    forwarded_keys: set[str],
    unforwarded_allowlist: dict[str, str],
) -> list[str]:
    """Rule 6: Every key in .env.example read by code is forwarded or in unforwarded allowlist."""
    problems: list[str] = []
    example_code_keys = sorted(set(env_example.keys()) & code_keys)
    for key in example_code_keys:
        if key in forwarded_keys:
            continue
        if key in unforwarded_allowlist:
            if not unforwarded_allowlist[key].strip():
                problems.append(
                    f"Rule 6 violation: Key '{key}' in unforwarded allowlist must have a non-empty reason."
                )
            continue
        problems.append(
            f"Rule 6 violation: Key '{key}' defined in .env.example and read by code is neither forwarded in compose nor in UNFORWARDED_ALLOWLIST."
        )
    return problems


def check_rule7_required_keys_present(
    forwarded_keys: set[str],
    required_keys: frozenset[str],
) -> list[str]:
    """Rule 7: Required security/session/CORS/throttle/pool keys must be forwarded in compose."""
    problems: list[str] = []
    missing_required = sorted(required_keys - forwarded_keys)
    for key in missing_required:
        problems.append(
            f"Rule 7 violation: Required security/runtime key '{key}' is missing from compose forwarded keys."
        )
    return problems


def check_rule8_defaults_match_code(
    normalized_env: dict[str, Any],
    code_defaults: dict[str, Any],
    code_mismatch_allowlist: dict[str, str],
    skipped_non_literal: dict[str, str] | None = None,
) -> list[str]:
    """
    Rule 8: For every forwarded key written ${NAME:-default} or ${NAME-default} whose default
    is in code_defaults, compare the compose default against the code default after normalization:
    - Booleans: 1/true/True -> True, 0/false/False -> False
    - Numbers: compared numerically (10 == 10.0)
    - Lists: comma-separated string split into stripped non-empty strings ([] for empty)
    - Strings: exact match
    """
    problems: list[str] = []
    skipped = skipped_non_literal or {}

    for key, val in sorted(normalized_env.items()):
        val_str = str(val).strip().strip("'\"")
        match = DEFAULT_EXTRACTION_PATTERN.match(val_str)
        if not match:
            continue

        if key in skipped:
            continue

        if key not in code_defaults:
            continue

        if key in code_mismatch_allowlist:
            if not code_mismatch_allowlist[key].strip():
                problems.append(
                    f"Rule 8 violation: Code mismatch allowlist entry for '{key}' must have a non-empty reason."
                )
            continue

        compose_default = match.group(2).strip().strip("'\"")
        code_val = code_defaults[key]
        match_found = False

        if isinstance(code_val, bool):
            c_low = compose_default.lower()
            if (c_low in ("1", "true") and code_val is True) or (
                c_low in ("0", "false") and code_val is False
            ):
                match_found = True
        elif isinstance(code_val, (int, float)):
            try:
                match_found = float(compose_default) == float(code_val)
            except ValueError:
                match_found = False
        elif isinstance(code_val, (list, tuple)):
            compose_parts = (
                [p.strip() for p in compose_default.split(",") if p.strip()]
                if compose_default
                else []
            )
            code_parts = [str(p).strip() for p in code_val if str(p).strip()]
            match_found = compose_parts == code_parts
        elif isinstance(code_val, str):
            match_found = compose_default == code_val

        if not match_found:
            problems.append(
                f"Rule 8 violation: Key '{key}' compose default '{compose_default}' does not match code default {code_val!r}."
            )

    return problems


def check_allowlist_reasons_no_stale_wording(
    allowlists: dict[str, dict[str, str]],
) -> list[str]:
    """
    Checks allowlist reasons against forbidden stale wording patterns:
    - regex r'\\bline[s]? \\d+' (line numbers)
    - case-insensitive 'pending'
    - case-insensitive 'reported to'

    Returns a list of violation messages naming the dictionary and key.
    """
    problems: list[str] = []
    for dict_name, allowlist in sorted(allowlists.items()):
        for key, reason in sorted(allowlist.items()):
            violations: list[str] = []
            if STALE_WORDING_LINE_PATTERN.search(reason):
                violations.append("line number reference")
            reason_lower = reason.lower()
            if "pending" in reason_lower:
                violations.append("'pending'")
            if "reported to" in reason_lower:
                violations.append("'reported to'")

            if violations:
                problems.append(
                    f"{dict_name} entry for '{key}' contains stale wording ({', '.join(violations)}): {reason}"
                )
    return problems


def get_all_module_allowlists() -> dict[str, dict[str, str]]:
    """Discovers all *_ALLOWLIST dictionaries defined at module level."""
    return {
        name: val
        for name, val in globals().items()
        if name.endswith("_ALLOWLIST") and isinstance(val, dict)
    }


def run_all_compose_env_checks(
    code_keys: set[str],
    env_example: dict[str, str],
    raw_compose_env: Any,
    unforwarded_allowlist: dict[str, str] = UNFORWARDED_ALLOWLIST,
    fixed_literal_allowlist: dict[str, str] = FIXED_CONTAINER_LITERAL_ALLOWLIST,
    mismatch_allowlist: dict[str, str] = INTENTIONAL_DEFAULT_MISMATCH_ALLOWLIST,
    required_keys: frozenset[str] = REQUIRED_SECURITY_AND_RUNTIME_KEYS,
    code_defaults: dict[str, Any] | None = None,
    code_mismatch_allowlist: dict[
        str, str
    ] = INTENTIONAL_CODE_DEFAULT_MISMATCH_ALLOWLIST,
    skipped_non_literal: dict[str, str] | None = None,
) -> list[str]:
    """Executes all checks R1 through R8 on normalized compose environment and aggregates problems."""
    problems: list[str] = []
    normalized_env, norm_problems = normalize_compose_environment(raw_compose_env)
    problems.extend(norm_problems)

    forwarded_keys = set(normalized_env.keys())

    problems.extend(
        check_rule1_code_keys_forwarded_or_allowlisted(
            code_keys=code_keys,
            forwarded_keys=forwarded_keys,
            unforwarded_allowlist=unforwarded_allowlist,
        )
    )
    problems.extend(
        check_rule2_interpolation_variable_names(
            normalized_env=normalized_env,
        )
    )
    problems.extend(
        check_rule3_hardcoded_literals(
            code_keys=code_keys,
            normalized_env=normalized_env,
            fixed_literal_allowlist=fixed_literal_allowlist,
        )
    )
    problems.extend(
        check_rule4_defaults_match_env_example(
            normalized_env=normalized_env,
            env_example=env_example,
            mismatch_allowlist=mismatch_allowlist,
            fixed_literal_allowlist=fixed_literal_allowlist,
        )
    )
    problems.extend(
        check_rule5_no_stale_allowlists(
            code_keys=code_keys,
            forwarded_keys=forwarded_keys,
            unforwarded_allowlist=unforwarded_allowlist,
            fixed_literal_allowlist=fixed_literal_allowlist,
            mismatch_allowlist=mismatch_allowlist,
            env_example=env_example,
            code_mismatch_allowlist=code_mismatch_allowlist,
        )
    )
    problems.extend(
        check_rule6_env_example_keys_forwarded_or_allowlisted(
            code_keys=code_keys,
            env_example=env_example,
            forwarded_keys=forwarded_keys,
            unforwarded_allowlist=unforwarded_allowlist,
        )
    )
    problems.extend(
        check_rule7_required_keys_present(
            forwarded_keys=forwarded_keys,
            required_keys=required_keys,
        )
    )
    if code_defaults is not None:
        problems.extend(
            check_rule8_defaults_match_code(
                normalized_env=normalized_env,
                code_defaults=code_defaults,
                code_mismatch_allowlist=code_mismatch_allowlist,
                skipped_non_literal=skipped_non_literal,
            )
        )
    return problems


def extract_settings_and_gunicorn_keys(
    settings_dir: Path, gunicorn_conf: Path
) -> set[str]:
    """Extracts all environment variable keys read in config/settings/*.py and docker/gunicorn.conf.py via AST."""
    keys: set[str] = set()
    source_files = sorted(settings_dir.glob("*.py"))
    if gunicorn_conf.is_file():
        source_files.append(gunicorn_conf)

    for py_file in source_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                is_env_call = (isinstance(fn, ast.Name) and fn.id == "env") or (
                    isinstance(fn, ast.Attribute)
                    and getattr(fn.value, "id", None) == "env"
                )
                is_getenv_call = (
                    isinstance(fn, ast.Attribute)
                    and getattr(fn.value, "id", None) == "os"
                    and fn.attr == "getenv"
                )
                is_environ_get_call = (
                    isinstance(fn, ast.Attribute)
                    and isinstance(fn.value, ast.Attribute)
                    and getattr(fn.value.value, "id", None) == "os"
                    and fn.value.attr == "environ"
                    and fn.attr in ("get", "setdefault")
                )

                if is_env_call or is_getenv_call or is_environ_get_call:
                    if (
                        node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)
                    ):
                        keys.add(node.args[0].value)
                elif (
                    isinstance(fn, ast.Attribute)
                    and getattr(fn.value, "id", None) == "environ"
                    and fn.attr == "Env"
                ):
                    for kw in node.keywords:
                        if kw.arg:
                            keys.add(kw.arg)
            elif (
                isinstance(node, ast.Subscript)
                and isinstance(node.value, ast.Attribute)
                and getattr(node.value.value, "id", None) == "os"
                and node.value.attr == "environ"
                and isinstance(node.slice, ast.Constant)
                and isinstance(node.slice.value, str)
            ):
                keys.add(node.slice.value)
    return keys


def parse_env_example_keys(env_file: Path) -> dict[str, str]:
    """Parses key-value definitions from .env.example."""
    definitions: dict[str, str] = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            definitions[key.strip()] = val.strip().strip("'\"")
    return definitions


def load_raw_compose_web_environment(compose_file: Path) -> Any:
    """Loads services.web.environment directly from docker-compose.yml."""
    compose_data = yaml.safe_load(compose_file.read_text(encoding="utf-8"))
    assert "services" in compose_data and "web" in compose_data["services"], (
        "docker-compose.yml missing services.web"
    )
    return compose_data["services"]["web"].get("environment", {})


def _eval_ast_default(node: ast.AST) -> tuple[bool, Any]:
    """Evaluates an AST node to a literal python value or returns its unparsed expression string."""
    try:
        return True, ast.literal_eval(node)
    except ValueError, TypeError, SyntaxError:
        return False, ast.unparse(node)


def extract_code_defaults(
    base_path: Path, local_path: Path, gunicorn_path: Path
) -> tuple[dict[str, Any], dict[str, str]]:
    """
    Pure AST inspection extracting environment variable defaults from settings and gunicorn.
    Precedence: local.py > base.py / environ.Env schema > gunicorn.conf.py.
    Ignores production.py and test.py.

    Returns:
    - resolved_defaults: mapping of environment variable key to its literal evaluated default
    - skipped_non_literal: mapping of environment variable key to its non-literal expression or reason
    """
    base_defaults: dict[str, Any] = {}
    base_skipped: dict[str, str] = {}
    local_defaults: dict[str, Any] = {}
    local_skipped: dict[str, str] = {}
    gunicorn_defaults: dict[str, Any] = {}
    gunicorn_skipped: dict[str, str] = {}

    if base_path.is_file():
        tree_base = ast.parse(
            base_path.read_text(encoding="utf-8"), filename=str(base_path)
        )
        for node in ast.walk(tree_base):
            if isinstance(node, ast.Call):
                fn = node.func
                # Case 1: environ.Env(KEY=(type, default), ...) schema in base.py
                if (
                    isinstance(fn, ast.Attribute)
                    and getattr(fn.value, "id", None) == "environ"
                    and fn.attr == "Env"
                ):
                    for kw in node.keywords:
                        if (
                            kw.arg
                            and isinstance(kw.value, ast.Tuple)
                            and len(kw.value.elts) >= 2
                        ):
                            is_lit, val = _eval_ast_default(kw.value.elts[1])
                            if is_lit:
                                base_defaults[kw.arg] = val
                                base_skipped.pop(kw.arg, None)
                            else:
                                base_skipped[kw.arg] = (
                                    f"Non-literal AST expression in base.py: {val}"
                                )
                                base_defaults.pop(kw.arg, None)
                # Case 2: env("KEY", default=...) or env.type("KEY", default=...)
                is_env = (isinstance(fn, ast.Name) and fn.id == "env") or (
                    isinstance(fn, ast.Attribute)
                    and getattr(fn.value, "id", None) == "env"
                )
                if (
                    is_env
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    key = node.args[0].value
                    def_node = next(
                        (kw.value for kw in node.keywords if kw.arg == "default"), None
                    )
                    if def_node is None and len(node.args) >= 2:
                        def_node = node.args[1]
                    if def_node is not None:
                        is_lit, val = _eval_ast_default(def_node)
                        if is_lit:
                            base_defaults[key] = val
                            base_skipped.pop(key, None)
                        else:
                            base_skipped[key] = (
                                f"Non-literal AST expression in base.py: {val}"
                            )
                            base_defaults.pop(key, None)

    if gunicorn_path.is_file():
        tree_gun = ast.parse(
            gunicorn_path.read_text(encoding="utf-8"), filename=str(gunicorn_path)
        )
        for node in ast.walk(tree_gun):
            if isinstance(node, ast.Call):
                fn = node.func
                is_getenv = (
                    isinstance(fn, ast.Attribute)
                    and getattr(fn.value, "id", None) == "os"
                    and fn.attr == "getenv"
                )
                is_env_get = (
                    isinstance(fn, ast.Attribute)
                    and isinstance(fn.value, ast.Attribute)
                    and getattr(fn.value.value, "id", None) == "os"
                    and fn.value.attr == "environ"
                    and fn.attr in ("get", "setdefault")
                )
                if (
                    (is_getenv or is_env_get)
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    key = node.args[0].value
                    def_node = next(
                        (kw.value for kw in node.keywords if kw.arg == "default"), None
                    )
                    if def_node is None and len(node.args) >= 2:
                        def_node = node.args[1]
                    if def_node is not None:
                        is_lit, val = _eval_ast_default(def_node)
                        if is_lit:
                            gunicorn_defaults[key] = val
                            gunicorn_skipped.pop(key, None)
                        else:
                            gunicorn_skipped[key] = (
                                f"Non-literal AST expression in gunicorn.conf.py: {val}"
                            )
                            gunicorn_defaults.pop(key, None)

    if local_path.is_file():
        tree_local = ast.parse(
            local_path.read_text(encoding="utf-8"), filename=str(local_path)
        )
        for node in ast.walk(tree_local):
            if isinstance(node, ast.Call):
                fn = node.func
                is_env = (isinstance(fn, ast.Name) and fn.id == "env") or (
                    isinstance(fn, ast.Attribute)
                    and getattr(fn.value, "id", None) == "env"
                )
                if (
                    is_env
                    and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    key = node.args[0].value
                    def_node = next(
                        (kw.value for kw in node.keywords if kw.arg == "default"), None
                    )
                    if def_node is None and len(node.args) >= 2:
                        def_node = node.args[1]
                    if def_node is not None:
                        is_lit, val = _eval_ast_default(def_node)
                        if is_lit:
                            local_defaults[key] = val
                            local_skipped.pop(key, None)
                        else:
                            local_skipped[key] = (
                                f"Non-literal AST expression in local.py: {val}"
                            )
                            local_defaults.pop(key, None)

    # Priority merging: fallback gunicorn -> base -> local (highest precedence)
    resolved = dict(gunicorn_defaults)
    skipped = dict(gunicorn_skipped)

    resolved.update(base_defaults)
    skipped.update(base_skipped)
    for k in base_defaults:
        skipped.pop(k, None)
    for k in base_skipped:
        resolved.pop(k, None)

    resolved.update(local_defaults)
    skipped.update(local_skipped)
    for k in local_defaults:
        skipped.pop(k, None)
    for k in local_skipped:
        resolved.pop(k, None)

    return resolved, skipped


# ==============================================================================
# Live Repository Integration Test
# ==============================================================================


def test_compose_environment_forwarding_live_repo() -> None:
    """Live repository check ensuring docker-compose.yml satisfies all 8 environment rules."""
    code_keys = extract_settings_and_gunicorn_keys(SETTINGS_DIR, GUNICORN_CONF_FILE)
    env_example = parse_env_example_keys(ENV_EXAMPLE_FILE)
    raw_compose_env = load_raw_compose_web_environment(COMPOSE_FILE)
    code_defaults, skipped_non_literal = extract_code_defaults(
        SETTINGS_DIR / "base.py",
        SETTINGS_DIR / "local.py",
        GUNICORN_CONF_FILE,
    )

    problems = run_all_compose_env_checks(
        code_keys=code_keys,
        env_example=env_example,
        raw_compose_env=raw_compose_env,
        code_defaults=code_defaults,
        code_mismatch_allowlist=INTENTIONAL_CODE_DEFAULT_MISMATCH_ALLOWLIST,
        skipped_non_literal=skipped_non_literal,
    )
    skipped_info = "\nSkipped non-literal AST expressions:\n" + "\n".join(
        f"  {k}: {expr}" for k, expr in sorted(skipped_non_literal.items())
    )
    assert not problems, (
        "Compose environment forwarding drift detected on live repository:\n"
        + "\n".join(f"- {p}" for p in problems)
        + skipped_info
    )


# ==============================================================================
# Synthetic Unit Tests (R1 through R7 and Compose Format Support)
# ==============================================================================


def test_normalize_compose_environment_mapping() -> None:
    """Ensures YAML mapping dictionary format is normalized correctly."""
    raw = {"FOO": "${FOO:-bar}", "BAZ": 123}
    normalized, problems = normalize_compose_environment(raw)
    assert problems == []
    assert normalized == {"FOO": "${FOO:-bar}", "BAZ": 123}


def test_normalize_compose_environment_list_format() -> None:
    """Ensures YAML sequence 'KEY=value' list format is normalized correctly."""
    raw = ["FOO=${FOO:-bar}", "BAZ=123", "EMPTY="]
    normalized, problems = normalize_compose_environment(raw)
    assert problems == []
    assert normalized == {"FOO": "${FOO:-bar}", "BAZ": "123", "EMPTY": ""}


def test_normalize_compose_environment_invalid_format() -> None:
    """Ensures malformed entries or invalid types report clear errors."""
    raw_invalid_item: list[Any] = ["VALID=1", "INVALID_NO_EQUALS", 12345]
    _, problems = normalize_compose_environment(raw_invalid_item)
    assert len(problems) == 2
    assert "missing '=' separator" in problems[0]
    assert "expected string, got int" in problems[1]

    _, type_problems = normalize_compose_environment("not_a_dict_or_list")
    assert len(type_problems) == 1
    assert "expected dict or list, got str" in type_problems[0]


def test_rule1_missing_code_key_reported() -> None:
    """R1: Key read by code but neither forwarded nor allowlisted must report problem naming the key."""
    code_keys = {"VAR_A", "VAR_B"}
    forwarded_keys = {"VAR_A"}
    allowlist: dict[str, str] = {}
    problems = check_rule1_code_keys_forwarded_or_allowlisted(
        code_keys, forwarded_keys, allowlist
    )
    assert len(problems) == 1
    assert "VAR_B" in problems[0]


def test_rule1_empty_allowlist_reason_reported() -> None:
    """R1: Allowlist entry with empty reason must report problem naming the key."""
    code_keys = {"VAR_A"}
    forwarded_keys: set[str] = set()
    allowlist = {"VAR_A": "   "}
    problems = check_rule1_code_keys_forwarded_or_allowlisted(
        code_keys, forwarded_keys, allowlist
    )
    assert len(problems) == 1
    assert "VAR_A" in problems[0]
    assert "non-empty reason" in problems[0]


def test_rule2_mismatched_interpolation_variable_reported() -> None:
    """R2: Mismatched variable interpolation name (e.g. NUM_PROXIES: ${NUM_PROXY:-0}) must report both names."""
    env = {"NUM_PROXIES": "${NUM_PROXY:-0}"}
    problems = check_rule2_interpolation_variable_names(env)
    assert len(problems) == 1
    assert "NUM_PROXIES" in problems[0]
    assert "NUM_PROXY" in problems[0]


def test_rule3_hardcoded_literal_without_allowlist_reported() -> None:
    """R3: Hard-coded literal for code-read key without allowlist must report problem naming the key."""
    code_keys = {"CORS_ALLOWED_ORIGINS"}
    env = {"CORS_ALLOWED_ORIGINS": "http://evil.example"}
    allowlist: dict[str, str] = {}
    problems = check_rule3_hardcoded_literals(code_keys, env, allowlist)
    assert len(problems) == 1
    assert "CORS_ALLOWED_ORIGINS" in problems[0]
    assert "http://evil.example" in problems[0]


def test_rule3_fixed_literal_allowlist_permitted() -> None:
    """R3: Hard-coded literal permitted if listed in FIXED_CONTAINER_LITERAL_ALLOWLIST with non-empty reason."""
    code_keys = {"POSTGRES_HOST"}
    env = {"POSTGRES_HOST": "db"}
    allowlist = {"POSTGRES_HOST": "Fixed compose service host"}
    problems = check_rule3_hardcoded_literals(code_keys, env, allowlist)
    assert problems == []


def test_rule4_default_value_mismatch_reported() -> None:
    """R4: Compose default mismatching .env.example must report problem naming the key and both values."""
    env = {"SESSION_COOKIE_AGE": "${SESSION_COOKIE_AGE:-99999}"}
    example = {"SESSION_COOKIE_AGE": "43200"}
    problems = check_rule4_defaults_match_env_example(env, example, {}, {})
    assert len(problems) == 1
    assert "SESSION_COOKIE_AGE" in problems[0]
    assert "99999" in problems[0]
    assert "43200" in problems[0]


def test_rule4_intentional_mismatch_permitted() -> None:
    """R4: Compose default mismatch permitted when declared in INTENTIONAL_DEFAULT_MISMATCH_ALLOWLIST."""
    env = {"DEBUG": "${DEBUG:-True}"}
    example = {"DEBUG": "False"}
    mismatch_allowlist = {"DEBUG": "Local compose default"}
    problems = check_rule4_defaults_match_env_example(
        env, example, mismatch_allowlist, {}
    )
    assert problems == []


def test_rule5_stale_key_in_unforwarded_allowlist_reported() -> None:
    """R5: Stale key in UNFORWARDED_ALLOWLIST not read by code must report problem naming the key."""
    code_keys = {"ACTUAL_KEY"}
    forwarded = {"ACTUAL_KEY"}
    unforwarded = {"STALE_UNUSED_KEY": "Some obsolete rationale"}
    problems = check_rule5_no_stale_allowlists(
        code_keys, forwarded, unforwarded, {}, {}, {}
    )
    assert any("STALE_UNUSED_KEY" in p and "not read by code" in p for p in problems)


def test_rule5_key_in_both_allowlist_and_forwarded_reported() -> None:
    """R5: Key in UNFORWARDED_ALLOWLIST that is also forwarded in compose must report problem naming the key."""
    code_keys = {"MY_KEY"}
    forwarded = {"MY_KEY"}
    unforwarded = {"MY_KEY": "Some rationale"}
    problems = check_rule5_no_stale_allowlists(
        code_keys, forwarded, unforwarded, {}, {}, {}
    )
    assert any("MY_KEY" in p and "unexpectedly forwarded" in p for p in problems)


def test_rule6_example_key_unhandled_reported() -> None:
    """R6: Key in .env.example read by code but neither forwarded nor allowlisted must report problem."""
    code_keys = {"NEW_DOC_FLAG"}
    example = {"NEW_DOC_FLAG": "1"}
    forwarded: set[str] = set()
    unforwarded: dict[str, str] = {}
    problems = check_rule6_env_example_keys_forwarded_or_allowlisted(
        code_keys, example, forwarded, unforwarded
    )
    assert len(problems) == 1
    assert "NEW_DOC_FLAG" in problems[0]


def test_rule7_missing_required_key_reported() -> None:
    """R7: Required security/runtime key missing from compose forwarded keys must report problem."""
    forwarded = {"CSRF_TRUSTED_ORIGINS"}
    required = frozenset({"CORS_ALLOWED_ORIGINS", "CSRF_TRUSTED_ORIGINS"})
    problems = check_rule7_required_keys_present(forwarded, required)
    assert len(problems) == 1
    assert "CORS_ALLOWED_ORIGINS" in problems[0]


def test_normalize_compose_environment_empty_key_in_mapping_reported() -> None:
    """Ensures empty key in compose mapping reports an error."""
    raw = {"": "some_value", "   ": "other_value", "VALID": "1"}
    normalized, problems = normalize_compose_environment(raw)
    assert len(problems) == 2
    assert all(
        "Empty environment variable key name in compose mapping." in p for p in problems
    )
    assert normalized == {"VALID": "1"}


def test_normalize_compose_environment_empty_key_in_list_reported() -> None:
    """Ensures empty key before '=' in sequence format reports an error."""
    raw = ["=", "=val", "   =val", "VALID=1"]
    normalized, problems = normalize_compose_environment(raw)
    assert len(problems) == 3
    assert "Malformed environment item '=' at index 0: empty key name." in problems[0]
    assert (
        "Malformed environment item '=val' at index 1: empty key name." in problems[1]
    )
    assert (
        "Malformed environment item '   =val' at index 2: empty key name."
        in problems[2]
    )
    assert normalized == {"VALID": "1"}


def test_rule4_hyphen_only_syntax_detects_mismatch() -> None:
    """R4: Hyphen-only syntax ${KEY-default} without colon must detect mismatch against .env.example."""
    env = {"AUTH_THROTTLE_PAIR_LIMIT": "${AUTH_THROTTLE_PAIR_LIMIT-99}"}
    example = {"AUTH_THROTTLE_PAIR_LIMIT": "5"}
    problems = check_rule4_defaults_match_env_example(env, example, {}, {})
    assert len(problems) == 1
    assert "AUTH_THROTTLE_PAIR_LIMIT" in problems[0]
    assert "99" in problems[0]
    assert "5" in problems[0]


def test_rule4_hyphen_only_syntax_matching_passes() -> None:
    """R4: Hyphen-only syntax ${KEY-default} matching .env.example must pass with zero problems."""
    env = {"AUTH_THROTTLE_PAIR_LIMIT": "${AUTH_THROTTLE_PAIR_LIMIT-5}"}
    example = {"AUTH_THROTTLE_PAIR_LIMIT": "5"}
    problems = check_rule4_defaults_match_env_example(env, example, {}, {})
    assert problems == []


def test_rule5_stale_key_in_mismatch_allowlist_not_in_env_example_reported() -> None:
    """R5: Stale key in INTENTIONAL_DEFAULT_MISMATCH_ALLOWLIST missing from .env.example must report problem."""
    code_keys = {"KEY_A"}
    forwarded = {"KEY_A", "OBSOLETE_KEY"}
    mismatch_allowlist = {"OBSOLETE_KEY": "Legacy mismatch rationale"}
    env_example = {"KEY_A": "1"}
    problems = check_rule5_no_stale_allowlists(
        code_keys=code_keys,
        forwarded_keys=forwarded,
        unforwarded_allowlist={},
        fixed_literal_allowlist={},
        mismatch_allowlist=mismatch_allowlist,
        env_example=env_example,
    )
    assert len(problems) == 1
    assert "OBSOLETE_KEY" in problems[0]
    assert (
        "Stale key 'OBSOLETE_KEY' in INTENTIONAL_DEFAULT_MISMATCH_ALLOWLIST is not defined in .env.example."
        in problems[0]
    )


# ==============================================================================
# Synthetic Unit Tests for Rule R8 (Code Defaults AST Inspection & Matching)
# ==============================================================================


def test_extract_code_defaults_precedence_local_over_base(tmp_path: Path) -> None:
    """AST extraction: defaults defined in local.py must override defaults in base.py."""
    base_file = tmp_path / "base.py"
    local_file = tmp_path / "local.py"
    gunicorn_file = tmp_path / "gunicorn.conf.py"

    base_file.write_text(
        "\n".join(
            [
                "import environ",
                "env = environ.Env(FOO=(int, 10), BAR=(str, 'base'))",
                "",
            ]
        ),
        encoding="utf-8",
    )
    local_file.write_text(
        "\n".join(
            [
                "from .base import env",
                "FOO = env.int('FOO', default=20)",
                "",
            ]
        ),
        encoding="utf-8",
    )
    gunicorn_file.write_text("", encoding="utf-8")

    resolved, skipped = extract_code_defaults(base_file, local_file, gunicorn_file)
    assert resolved["FOO"] == 20
    assert resolved["BAR"] == "base"
    assert skipped == {}


def test_extract_code_defaults_non_literal_placed_in_skipped(tmp_path: Path) -> None:
    """AST extraction: non-literal default expressions must be placed in skipped_non_literal."""
    base_file = tmp_path / "base.py"
    local_file = tmp_path / "local.py"
    gunicorn_file = tmp_path / "gunicorn.conf.py"

    base_file.write_text(
        "import environ\n"
        "env = environ.Env()\n"
        "DYNAMIC_VAL = env('DYNAMIC_VAL', default=str(BASE_DIR))\n"
        "STATIC_VAL = env.int('STATIC_VAL', default=42)\n",
        encoding="utf-8",
    )
    local_file.write_text("", encoding="utf-8")
    gunicorn_file.write_text("", encoding="utf-8")

    resolved, skipped = extract_code_defaults(base_file, local_file, gunicorn_file)
    assert "STATIC_VAL" in resolved
    assert resolved["STATIC_VAL"] == 42
    assert "DYNAMIC_VAL" not in resolved
    assert "DYNAMIC_VAL" in skipped
    assert "str(BASE_DIR)" in skipped["DYNAMIC_VAL"]


def test_rule8_matching_booleans() -> None:
    """R8: Normalization of booleans matches '1'/'true' to True and '0'/'false' to False."""
    env = {
        "FLAG_1": "${FLAG_1:-1}",
        "FLAG_2": "${FLAG_2:-true}",
        "FLAG_3": "${FLAG_3:-True}",
        "FLAG_4": "${FLAG_4:-0}",
        "FLAG_5": "${FLAG_5:-false}",
        "FLAG_6": "${FLAG_6:-False}",
    }
    code_defaults = {
        "FLAG_1": True,
        "FLAG_2": True,
        "FLAG_3": True,
        "FLAG_4": False,
        "FLAG_5": False,
        "FLAG_6": False,
    }
    problems = check_rule8_defaults_match_code(env, code_defaults, {})
    assert problems == []


def test_rule8_matching_numbers() -> None:
    """R8: Normalization compares integer and float numerically (10 == 10.0)."""
    env = {
        "NUM_INT": "${NUM_INT:-10}",
        "NUM_FLOAT": "${NUM_FLOAT:-10.0}",
    }
    code_defaults = {
        "NUM_INT": 10.0,
        "NUM_FLOAT": 10,
    }
    problems = check_rule8_defaults_match_code(env, code_defaults, {})
    assert problems == []


def test_rule8_matching_lists() -> None:
    """R8: Normalization compares comma-separated strings to lists of stripped strings."""
    env = {
        "HOSTS": "${HOSTS:-localhost, 127.0.0.1, [::1]}",
        "EMPTY": "${EMPTY:-}",
    }
    code_defaults = {
        "HOSTS": ["localhost", "127.0.0.1", "[::1]"],
        "EMPTY": [],
    }
    problems = check_rule8_defaults_match_code(env, code_defaults, {})
    assert problems == []


def test_rule8_matching_strings() -> None:
    """R8: String comparison matches exact strings."""
    env = {"ENGINE": "${ENGINE:-fast_alpr}"}
    code_defaults = {"ENGINE": "fast_alpr"}
    problems = check_rule8_defaults_match_code(env, code_defaults, {})
    assert problems == []


def test_rule8_mismatch_reported() -> None:
    """R8: Mismatch between compose default and code default reports problem naming the key and both values."""
    env = {"DB_POOL_MIN_SIZE": "${DB_POOL_MIN_SIZE:-1}"}
    code_defaults = {"DB_POOL_MIN_SIZE": 2}
    problems = check_rule8_defaults_match_code(env, code_defaults, {})
    assert len(problems) == 1
    assert "DB_POOL_MIN_SIZE" in problems[0]
    assert "1" in problems[0]
    assert "2" in problems[0]


def test_rule8_intentional_mismatch_permitted() -> None:
    """R8: Compose default mismatch is permitted when listed in allowlist with non-empty reason."""
    env = {"ALLOWED_HOSTS": "${ALLOWED_HOSTS:-localhost,127.0.0.1,web}"}
    code_defaults = {"ALLOWED_HOSTS": ["localhost", "127.0.0.1", "[::1]"]}
    allowlist = {"ALLOWED_HOSTS": "Inter-service compose communication"}
    problems = check_rule8_defaults_match_code(env, code_defaults, allowlist)
    assert problems == []


def test_rule8_empty_allowlist_reason_reported() -> None:
    """R8: Allowlist entry with empty reason must report a violation."""
    env = {"ALLOWED_HOSTS": "${ALLOWED_HOSTS:-localhost,127.0.0.1,web}"}
    code_defaults = {"ALLOWED_HOSTS": ["localhost", "127.0.0.1", "[::1]"]}
    allowlist = {"ALLOWED_HOSTS": "   "}
    problems = check_rule8_defaults_match_code(env, code_defaults, allowlist)
    assert len(problems) == 1
    assert "ALLOWED_HOSTS" in problems[0]
    assert "non-empty reason" in problems[0]


def test_rule8_stale_allowlist_entry_reported() -> None:
    """R8 / R5: Stale key in INTENTIONAL_CODE_DEFAULT_MISMATCH_ALLOWLIST must be reported by Rule 5."""
    code_keys = {"ACTUAL_KEY"}
    code_mismatch_allowlist = {
        "NOT_FORWARDED": "Rationale",
        "NOT_IN_CODE": "Rationale",
    }
    problems = check_rule5_no_stale_allowlists(
        code_keys=code_keys,
        forwarded_keys={"ACTUAL_KEY", "NOT_IN_CODE"},
        unforwarded_allowlist={},
        fixed_literal_allowlist={},
        mismatch_allowlist={},
        env_example={},
        code_mismatch_allowlist=code_mismatch_allowlist,
    )
    assert any(
        "NOT_FORWARDED" in p and "not forwarded in compose" in p for p in problems
    )
    assert any("NOT_IN_CODE" in p and "not read by code" in p for p in problems)


def test_rule8_required_compared_keys_present() -> None:
    """R8: The compared set of keys on live repository must contain at least the 10 required security/runtime keys."""
    raw_compose_env = load_raw_compose_web_environment(COMPOSE_FILE)
    normalized_env, _ = normalize_compose_environment(raw_compose_env)
    code_defaults, skipped_non_literal = extract_code_defaults(
        SETTINGS_DIR / "base.py",
        SETTINGS_DIR / "local.py",
        GUNICORN_CONF_FILE,
    )

    compared_keys: set[str] = set()
    for key, val in normalized_env.items():
        val_str = str(val).strip().strip("'\"")
        match = DEFAULT_EXTRACTION_PATTERN.match(val_str)
        if (
            match
            and key in code_defaults
            and key not in skipped_non_literal
            and key not in INTENTIONAL_CODE_DEFAULT_MISMATCH_ALLOWLIST
        ):
            compared_keys.add(key)

    required_10 = {
        "DB_POOL_MIN_SIZE",
        "DB_POOL_MAX_SIZE",
        "DB_POOL_TIMEOUT",
        "DB_CONN_HEALTH_CHECKS",
        "SESSION_COOKIE_AGE",
        "AUTH_THROTTLE_PAIR_LIMIT",
        "AUTH_THROTTLE_IDENTIFIER_LIMIT",
        "AUTH_THROTTLE_IP_LIMIT",
        "AUTH_THROTTLE_WINDOW_SECONDS",
        "NUM_PROXIES",
    }
    missing = required_10 - compared_keys
    assert not missing, f"Missing required keys from Rule 8 compared set: {missing}"


def test_allowlists_no_stale_wording() -> None:
    """Guard against stale allowlist reasons across all *_ALLOWLIST dictionaries in the module."""
    allowlists = get_all_module_allowlists()
    assert allowlists, "Expected module to define at least one *_ALLOWLIST dictionary"
    problems = check_allowlist_reasons_no_stale_wording(allowlists)
    assert not problems, (
        f"Found {len(problems)} stale wording violation(s) in allowlists:\n"
        + "\n".join(f"  - {p}" for p in problems)
    )


def test_stale_wording_detector_synthetic() -> None:
    """Synthetic unit test proving each of the three stale wording patterns is detected."""
    # Pattern 1: regex r'\bline[s]? \d+' (singular and plural)
    dict_pattern1_single = {
        "SYNTHETIC_ALLOWLIST": {"KEY_LINE": "Declared in base.py line 42."}
    }
    problems1_single = check_allowlist_reasons_no_stale_wording(dict_pattern1_single)
    assert len(problems1_single) == 1
    assert "SYNTHETIC_ALLOWLIST" in problems1_single[0]
    assert "KEY_LINE" in problems1_single[0]
    assert "line number reference" in problems1_single[0]

    dict_pattern1_plural = {
        "SYNTHETIC_ALLOWLIST": {"KEY_LINES": "Declared in local.py lines 105."}
    }
    problems1_plural = check_allowlist_reasons_no_stale_wording(dict_pattern1_plural)
    assert len(problems1_plural) == 1
    assert "KEY_LINES" in problems1_plural[0]
    assert "line number reference" in problems1_plural[0]

    # Pattern 2: 'pending' (case-insensitive)
    dict_pattern2 = {
        "SYNTHETIC_ALLOWLIST": {"KEY_PENDING": "Decision Pending from lead."}
    }
    problems2 = check_allowlist_reasons_no_stale_wording(dict_pattern2)
    assert len(problems2) == 1
    assert "SYNTHETIC_ALLOWLIST" in problems2[0]
    assert "KEY_PENDING" in problems2[0]
    assert "'pending'" in problems2[0]

    # Pattern 3: 'reported to' (case-insensitive)
    dict_pattern3 = {
        "SYNTHETIC_ALLOWLIST": {"KEY_REPORTED": "Already Reported To the team."}
    }
    problems3 = check_allowlist_reasons_no_stale_wording(dict_pattern3)
    assert len(problems3) == 1
    assert "SYNTHETIC_ALLOWLIST" in problems3[0]
    assert "KEY_REPORTED" in problems3[0]
    assert "'reported to'" in problems3[0]

    # Clean reason with no patterns passes
    dict_clean = {
        "SYNTHETIC_ALLOWLIST": {
            "KEY_CLEAN": "Deliberate local development convenience."
        }
    }
    assert check_allowlist_reasons_no_stale_wording(dict_clean) == []
