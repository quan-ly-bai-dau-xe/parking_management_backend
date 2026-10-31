"""
tests/core/test_compose_fullstack.py

Static inspection and drift guard test suite ensuring docker-compose.yml
satisfies production full-stack integration requirements:
- frontend service definition (build context, target runtime, dockerfile, restart policy, profiles, ports loopback, health dependency)
- web service network alias 'backend' on default network with explanatory comment
- default CORS and CSRF origins contain port 5173 and 3000 for localhost and 127.0.0.1
- .env.example parity for CORS and CSRF default origins
- .env.example documents # COMPOSE_PROFILES=frontend as a commented line
- config/settings/local.py CORS and CSRF defaults match compose while base.py retains empty list
- postgres_data named volume preservation

Zero database, zero network, zero docker daemon dependencies.
File-backed mutation proof using real files and temporary disk copies (tmp_path).
"""

from __future__ import annotations

import ast
import contextlib
import re
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
ENV_EXAMPLE_FILE = REPO_ROOT / ".env.example"

REQUIRED_ORIGINS: frozenset[str] = frozenset(
    {
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    }
)

REQUIRED_POSTGRES_VOLUME_NAME = "parking_postgres_data"

BACKEND_ALIAS_COMMENT_PATTERN = re.compile(
    r"#.*(?:backend|nginx|proxy).*alias|#.*alias.*(?:backend|nginx|proxy)|#.*(?:nginx|proxy).*backend",
    re.IGNORECASE,
)

COMPOSE_PROFILES_COMMENT_PATTERN = re.compile(
    r"^\s*#\s*COMPOSE_PROFILES\s*=\s*frontend\b",
    re.MULTILINE,
)


@pytest.fixture(autouse=True)
def ensure_sample_data() -> None:
    """Override conftest db fixture: zero database needed for static inspection."""
    return None


# ==============================================================================
# Helper Normalization and Inspection Functions
# ==============================================================================


def create_temp_copies(tmp_path: Path) -> tuple[Path, Path]:
    """Creates disk-backed temporary copies of real compose and env files."""
    temp_compose = tmp_path / "docker-compose.yml"
    temp_env = tmp_path / ".env.example"
    shutil.copyfile(COMPOSE_FILE, temp_compose)
    shutil.copyfile(ENV_EXAMPLE_FILE, temp_env)
    return temp_compose, temp_env


def load_compose_file(file_path: Path) -> dict[str, Any]:
    """Loads and parses a Docker Compose YAML file into a dictionary."""
    content = file_path.read_text(encoding="utf-8")
    data = yaml.safe_load(content)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid compose file structure at {file_path}")
    return data


def parse_env_file(file_path: Path) -> dict[str, str]:
    """Parses key-value definitions from an environment file like .env.example."""
    definitions: dict[str, str] = {}
    for line in file_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            definitions[key.strip()] = val.strip().strip("'\"")
    return definitions


def normalize_environment(raw_env: Any) -> dict[str, str]:
    """Normalizes services.<service>.environment mapping or sequence into a dict."""
    env_dict: dict[str, str] = {}
    if isinstance(raw_env, dict):
        for k, v in raw_env.items():
            key_str = str(k).strip()
            if key_str:
                env_dict[key_str] = str(v).strip()
    elif isinstance(raw_env, list):
        for item in raw_env:
            if isinstance(item, str) and "=" in item:
                k, v = item.split("=", 1)
                key_str = k.strip()
                if key_str:
                    env_dict[key_str] = v.strip()
    return env_dict


def extract_origin_set(raw_origins_str: str) -> set[str]:
    """Splits comma-separated origins string into a set of stripped URLs."""
    cleaned = raw_origins_str.strip().strip("'\"")
    if not cleaned:
        return set()
    return {origin.strip() for origin in cleaned.split(",") if origin.strip()}


def extract_interpolation_default(raw_env_val: str) -> str:
    """Extracts default value from bash-style interpolation ${VAR:-default}."""
    match = re.match(r"^\$\{[A-Za-z0-9_]+(?::?-(.*))?\}$", raw_env_val)
    if match and match.group(1) is not None:
        return match.group(1).strip()
    return raw_env_val.strip()


def extract_env_call_defaults(file_path: Path) -> dict[str, Any]:
    """Extracts default values passed to env.list or env() in a python settings file via pure AST."""
    defaults: dict[str, Any] = {}
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            is_env = (isinstance(fn, ast.Name) and fn.id == "env") or (
                isinstance(fn, ast.Attribute) and getattr(fn.value, "id", None) == "env"
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
                    with contextlib.suppress(ValueError, TypeError, SyntaxError):
                        defaults[key] = ast.literal_eval(def_node)
    return defaults


# ==============================================================================
# Domain Check Rules
# ==============================================================================


def check_frontend_service_exists(compose_data: dict[str, Any]) -> list[str]:
    """Verifies that the 'frontend' service is declared under services."""
    services = compose_data.get("services")
    if not isinstance(services, dict):
        return [
            "Top-level 'services' mapping is missing or invalid in docker-compose.yml."
        ]
    if "frontend" not in services or not isinstance(services.get("frontend"), dict):
        return [
            "Service 'frontend' is missing from docker-compose.yml services mapping."
        ]
    return []


def check_frontend_profiles(compose_data: dict[str, Any]) -> list[str]:
    """Verifies that frontend has profiles containing 'frontend'."""
    problems: list[str] = []
    frontend = compose_data.get("services", {}).get("frontend", {})
    profiles = frontend.get("profiles")
    if not isinstance(profiles, list) or "frontend" not in profiles:
        problems.append(
            "frontend service must declare profiles containing 'frontend' (e.g. profiles: [\"frontend\"])."
        )
    return problems


def check_frontend_build_context_and_target(compose_data: dict[str, Any]) -> list[str]:
    """Verifies frontend build configuration (context, dockerfile, runtime target)."""
    problems: list[str] = []
    frontend = compose_data.get("services", {}).get("frontend", {})
    build_cfg = frontend.get("build")

    if not isinstance(build_cfg, dict):
        problems.append("frontend service missing valid 'build' configuration mapping.")
        return problems

    context = str(build_cfg.get("context", "")).strip()
    if not (
        context == "../parking_management_frontend"
        or (
            "${FRONTEND_CONTEXT" in context
            and "../parking_management_frontend" in context
        )
    ):
        problems.append(
            f"frontend build context must default to '${{FRONTEND_CONTEXT:-../parking_management_frontend}}', got: '{context}'."
        )

    target = build_cfg.get("target")
    if target != "runtime":
        problems.append(f"frontend build target must be 'runtime', got '{target}'.")

    dockerfile = build_cfg.get("dockerfile")
    if dockerfile != "Dockerfile":
        problems.append(
            f"frontend build dockerfile must be 'Dockerfile', got '{dockerfile}'."
        )

    return problems


def check_frontend_restart_policy(compose_data: dict[str, Any]) -> list[str]:
    """Verifies frontend restart policy is unless-stopped."""
    problems: list[str] = []
    frontend = compose_data.get("services", {}).get("frontend", {})
    restart = frontend.get("restart")
    if restart != "unless-stopped":
        problems.append(
            f"frontend service restart policy must be 'unless-stopped', got '{restart}'."
        )
    return problems


def check_frontend_port_bindings(compose_data: dict[str, Any]) -> list[str]:
    """Verifies frontend ports are bound exclusively to 127.0.0.1 on port 5173."""
    problems: list[str] = []
    frontend = compose_data.get("services", {}).get("frontend", {})
    ports = frontend.get("ports", [])

    if not isinstance(ports, list) or not ports:
        problems.append("frontend service missing port bindings.")
        return problems

    for port_entry in ports:
        port_str = str(port_entry).strip()
        if not port_str.startswith("127.0.0.1:"):
            problems.append(
                f"Insecure port binding detected: port '{port_str}' must bind exclusively to local loopback '127.0.0.1:'."
            )
        if not (port_str.endswith(":5173") or port_str.endswith(":5173/tcp")):
            problems.append(
                f"Frontend container port must be 5173 in binding '{port_str}'."
            )

    return problems


def check_frontend_depends_on(compose_data: dict[str, Any]) -> list[str]:
    """Verifies frontend depends on web being healthy."""
    problems: list[str] = []
    frontend = compose_data.get("services", {}).get("frontend", {})
    depends_on = frontend.get("depends_on")

    if not isinstance(depends_on, dict):
        problems.append("frontend must declare depends_on with 'web' service.")
        return problems

    if "web" not in depends_on:
        problems.append("frontend must declare depends_on with 'web' service.")
        return problems

    web_dep = depends_on.get("web")
    if not isinstance(web_dep, dict):
        problems.append(
            "frontend depends_on 'web' must be configured as a dictionary with condition."
        )
        return problems

    condition = web_dep.get("condition")
    if condition != "service_healthy":
        problems.append(
            f"frontend depends_on 'web' must require condition 'service_healthy', got '{condition}'."
        )

    return problems


def check_web_network_alias_and_comment(
    compose_data: dict[str, Any],
    raw_yaml_text: str,
) -> list[str]:
    """Verifies web service has network alias 'backend' and explanatory comment."""
    problems: list[str] = []
    web = compose_data.get("services", {}).get("web", {})

    networks = web.get("networks")
    has_alias = False
    if isinstance(networks, dict):
        default_net = networks.get("default", {})
        if isinstance(default_net, dict):
            aliases = default_net.get("aliases", [])
            if isinstance(aliases, list) and "backend" in aliases:
                has_alias = True

    if not has_alias:
        problems.append(
            "web service missing network alias 'backend' on default network."
        )

    if not BACKEND_ALIAS_COMMENT_PATTERN.search(raw_yaml_text):
        problems.append(
            "Missing explanatory comment for 'backend' network alias in docker-compose.yml."
        )

    return problems


def check_cors_and_csrf_defaults(
    compose_data: dict[str, Any],
    env_example_data: dict[str, str] | None = None,
) -> list[str]:
    """Verifies compose defaults and .env.example parity for CORS and CSRF origins."""
    problems: list[str] = []
    web = compose_data.get("services", {}).get("web", {})
    env_dict = normalize_environment(web.get("environment", {}))

    for key in ("CORS_ALLOWED_ORIGINS", "CSRF_TRUSTED_ORIGINS"):
        raw_val = env_dict.get(key)
        if not raw_val:
            problems.append(f"web service environment missing {key}.")
            continue

        default_str = extract_interpolation_default(raw_val)
        origins = extract_origin_set(default_str)
        missing = REQUIRED_ORIGINS - origins
        if missing:
            problems.append(
                f"{key} missing required origins: {sorted(missing)}. "
                f"Configured default: '{default_str}'."
            )

        if env_example_data is not None:
            example_val = env_example_data.get(key)
            if not example_val:
                problems.append(f".env.example missing definition for {key}.")
            else:
                example_origins = extract_origin_set(example_val)
                if origins != example_origins:
                    problems.append(
                        f"Mismatch between compose default and .env.example for {key}: "
                        f"compose has {sorted(origins)}, .env.example has {sorted(example_origins)}."
                    )

    return problems


def check_postgres_volume_preserved(compose_data: dict[str, Any]) -> list[str]:
    """Verifies postgres_data volume definition retains fixed name parking_postgres_data."""
    problems: list[str] = []
    volumes = compose_data.get("volumes")
    if not isinstance(volumes, dict):
        return ["Top-level 'volumes' section missing from docker-compose.yml."]

    pg_vol = volumes.get("postgres_data")
    if not isinstance(pg_vol, dict):
        return ["Named volume 'postgres_data' is missing from docker-compose.yml."]

    vol_name = pg_vol.get("name")
    if vol_name != REQUIRED_POSTGRES_VOLUME_NAME:
        problems.append(
            f"Volume 'postgres_data' must have fixed name '{REQUIRED_POSTGRES_VOLUME_NAME}', got '{vol_name}'."
        )

    return problems


def check_env_example_profiles_commented(
    raw_env_text: str,
    env_example_data: dict[str, str],
) -> list[str]:
    """Verifies that .env.example documents COMPOSE_PROFILES=frontend as a commented line."""
    problems: list[str] = []
    if "COMPOSE_PROFILES" in env_example_data:
        problems.append(
            ".env.example must not have uncommented COMPOSE_PROFILES; "
            "COMPOSE_PROFILES=frontend must be documented as a commented line."
        )
    if not COMPOSE_PROFILES_COMMENT_PATTERN.search(raw_env_text):
        problems.append(
            ".env.example missing documented commented line '# COMPOSE_PROFILES=frontend'."
        )
    return problems


def check_frontend_no_env_or_vite_leaks(
    compose_data: dict[str, Any],
    raw_yaml_text: str,
    raw_env_text: str,
) -> list[str]:
    """
    Verifies that the frontend service has no environment, no env_file,
    and no build.args entry, and that no VITE_ string appears anywhere in
    docker-compose.yml or .env.example (preventing configuration leakage).
    """
    problems: list[str] = []
    frontend = compose_data.get("services", {}).get("frontend")
    if isinstance(frontend, dict):
        if "environment" in frontend:
            problems.append(
                "frontend service must not define 'environment'; frontend configuration must remain isolated in frontend repository."
            )
        if "env_file" in frontend:
            problems.append(
                "frontend service must not define 'env_file'; frontend configuration must remain isolated in frontend repository."
            )
        build_cfg = frontend.get("build")
        if isinstance(build_cfg, dict) and "args" in build_cfg:
            problems.append(
                "frontend service must not define 'build.args'; frontend configuration must remain isolated in frontend repository."
            )

    if "VITE_" in raw_yaml_text:
        problems.append(
            "String 'VITE_' must not appear anywhere in docker-compose.yml; frontend variables must not leak into backend compose."
        )

    if "VITE_" in raw_env_text:
        problems.append(
            "String 'VITE_' must not appear anywhere in .env.example; frontend variables must not leak into backend compose."
        )

    return problems


# ==============================================================================
# File-Reading Validation Entry Points
# ==============================================================================


def validate_compose_fullstack(
    compose_path: Path = COMPOSE_FILE,
    env_example_path: Path = ENV_EXAMPLE_FILE,
) -> list[str]:
    """
    Validates docker-compose.yml and .env.example against full-stack requirements.
    Reads REAL files from disk at compose_path and env_example_path.
    Returns a list of violation messages (empty list if fully compliant).
    """
    problems: list[str] = []

    if not compose_path.is_file():
        return [f"Compose file does not exist: {compose_path}"]
    if not env_example_path.is_file():
        return [f"Env example file does not exist: {env_example_path}"]

    try:
        raw_yaml_text = compose_path.read_text(encoding="utf-8")
        compose_data = yaml.safe_load(raw_yaml_text)
    except Exception as exc:
        return [f"Failed to read/parse compose file at {compose_path}: {exc}"]

    if not isinstance(compose_data, dict):
        return [
            f"Invalid compose file structure at {compose_path}: top-level mapping expected"
        ]

    try:
        raw_env_text = env_example_path.read_text(encoding="utf-8")
        env_example_data = parse_env_file(env_example_path)
    except Exception as exc:
        return [f"Failed to read/parse env example file at {env_example_path}: {exc}"]

    problems.extend(check_frontend_service_exists(compose_data))
    problems.extend(check_frontend_profiles(compose_data))
    problems.extend(check_frontend_build_context_and_target(compose_data))
    problems.extend(check_frontend_restart_policy(compose_data))
    problems.extend(check_frontend_port_bindings(compose_data))
    problems.extend(check_frontend_depends_on(compose_data))
    problems.extend(check_web_network_alias_and_comment(compose_data, raw_yaml_text))
    problems.extend(
        check_cors_and_csrf_defaults(
            compose_data=compose_data,
            env_example_data=env_example_data,
        )
    )
    problems.extend(check_postgres_volume_preserved(compose_data))
    problems.extend(
        check_env_example_profiles_commented(
            raw_env_text=raw_env_text,
            env_example_data=env_example_data,
        )
    )
    problems.extend(
        check_frontend_no_env_or_vite_leaks(
            compose_data=compose_data,
            raw_yaml_text=raw_yaml_text,
            raw_env_text=raw_env_text,
        )
    )

    return problems


def run_all_compose_fullstack_checks(
    compose_path: Path = COMPOSE_FILE,
    env_example_path: Path = ENV_EXAMPLE_FILE,
) -> list[str]:
    """Backward compatibility alias for validate_compose_fullstack."""
    return validate_compose_fullstack(compose_path, env_example_path)


# ==============================================================================
# Unit Tests (Settings Defaults and Mutation Proofs)
# ==============================================================================


def test_settings_cors_csrf_defaults() -> None:
    """
    Local settings verification: config/settings/local.py defaults must include all 4 local origins
    (port 5173 and 3000 for localhost and 127.0.0.1) for zero-Docker runs, while
    config/settings/base.py retains default=[] to ensure production stays fail-closed.
    """
    local_path = REPO_ROOT / "config" / "settings" / "local.py"
    base_path = REPO_ROOT / "config" / "settings" / "base.py"

    local_defaults = extract_env_call_defaults(local_path)
    base_defaults = extract_env_call_defaults(base_path)

    assert "CORS_ALLOWED_ORIGINS" in local_defaults, (
        "local.py missing explicit CORS_ALLOWED_ORIGINS override default"
    )
    assert "CSRF_TRUSTED_ORIGINS" in local_defaults, (
        "local.py missing explicit CSRF_TRUSTED_ORIGINS override default"
    )

    local_cors = set(local_defaults["CORS_ALLOWED_ORIGINS"])
    local_csrf = set(local_defaults["CSRF_TRUSTED_ORIGINS"])

    assert REQUIRED_ORIGINS.issubset(local_cors), (
        f"local.py CORS_ALLOWED_ORIGINS missing required origins: {REQUIRED_ORIGINS - local_cors}"
    )
    assert REQUIRED_ORIGINS.issubset(local_csrf), (
        f"local.py CSRF_TRUSTED_ORIGINS missing required origins: {REQUIRED_ORIGINS - local_csrf}"
    )

    assert base_defaults.get("CORS_ALLOWED_ORIGINS") == [], (
        f"base.py CORS_ALLOWED_ORIGINS must remain default=[], got {base_defaults.get('CORS_ALLOWED_ORIGINS')}"
    )
    assert base_defaults.get("CSRF_TRUSTED_ORIGINS") == [], (
        f"base.py CSRF_TRUSTED_ORIGINS must remain default=[], got {base_defaults.get('CSRF_TRUSTED_ORIGINS')}"
    )


def test_mutation_missing_frontend_service(tmp_path: Path) -> None:
    """MUT-01: Omitting frontend service reports clear missing service problem."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    mutated_text = re.sub(r"\n  frontend:.*?(?=\n\S|\Z)", "", text, flags=re.DOTALL)
    assert mutated_text != text
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        "Service 'frontend' is missing from docker-compose.yml" in p for p in problems
    )


def test_mutation_frontend_missing_profiles(tmp_path: Path) -> None:
    """MUT-01b: Omitting profiles or missing 'frontend' in profiles reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    assert 'profiles: ["frontend"]' in text
    mutated_text = text.replace('profiles: ["frontend"]', "profiles: []")
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        "frontend service must declare profiles containing 'frontend'" in p
        for p in problems
    )


def test_mutation_frontend_invalid_context(tmp_path: Path) -> None:
    """MUT-02: Non-sibling build context reports problem naming the invalid context."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    assert "${FRONTEND_CONTEXT:-../parking_management_frontend}" in text
    mutated_text = text.replace(
        "${FRONTEND_CONTEXT:-../parking_management_frontend}",
        "./frontend",
    )
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any("frontend build context must default to" in p for p in problems)


def test_mutation_frontend_invalid_target(tmp_path: Path) -> None:
    """MUT-03: Omitting or changing target from runtime reports problem."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    parts = text.split("frontend:\n")
    assert len(parts) == 2
    frontend_part = parts[1].replace("target: runtime", "target: builder", 1)
    temp_compose.write_text(parts[0] + "frontend:\n" + frontend_part, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any("frontend build target must be 'runtime'" in p for p in problems)


def test_mutation_frontend_invalid_dockerfile(tmp_path: Path) -> None:
    """MUT-03b: Omitting or changing dockerfile from Dockerfile reports problem."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    parts = text.split("frontend:\n")
    assert len(parts) == 2
    frontend_part = parts[1].replace(
        "dockerfile: Dockerfile", "dockerfile: Dockerfile.dev", 1
    )
    temp_compose.write_text(parts[0] + "frontend:\n" + frontend_part, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any("frontend build dockerfile must be 'Dockerfile'" in p for p in problems)


def test_mutation_frontend_insecure_ports_no_loopback(tmp_path: Path) -> None:
    """MUT-04: Port mapping without 127.0.0.1 binding reports insecure port violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    assert '"127.0.0.1:${FRONTEND_PORT:-5173}:5173"' in text
    mutated_text = text.replace(
        '"127.0.0.1:${FRONTEND_PORT:-5173}:5173"',
        '"5173:5173"',
    )
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any("Insecure port binding detected" in p for p in problems)


def test_mutation_frontend_wrong_port_mapping(tmp_path: Path) -> None:
    """MUT-04b: Port mapping with incorrect host or container port reports error."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    assert '"127.0.0.1:${FRONTEND_PORT:-5173}:5173"' in text
    mutated_text = text.replace(
        '"127.0.0.1:${FRONTEND_PORT:-5173}:5173"',
        '"127.0.0.1:8080:8080"',
    )
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any("Frontend container port must be 5173" in p for p in problems)


def test_mutation_frontend_missing_web_dependency(tmp_path: Path) -> None:
    """MUT-05: Missing depends_on for web service reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    parts = text.split("frontend:\n")
    assert len(parts) == 2
    frontend_part = parts[1].replace(
        "      web:\n        condition: service_healthy",
        "      db:\n        condition: service_healthy",
    )
    assert frontend_part != parts[1]
    temp_compose.write_text(parts[0] + "frontend:\n" + frontend_part, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any("frontend must declare depends_on with 'web'" in p for p in problems)


def test_mutation_frontend_wrong_dependency_condition(tmp_path: Path) -> None:
    """MUT-06: Wrong depends_on condition (e.g. service_started) reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    parts = text.split("frontend:\n")
    assert len(parts) == 2
    frontend_part = parts[1].replace(
        "condition: service_healthy", "condition: service_started", 1
    )
    temp_compose.write_text(parts[0] + "frontend:\n" + frontend_part, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        "frontend depends_on 'web' must require condition 'service_healthy'" in p
        for p in problems
    )


def test_mutation_frontend_missing_restart_policy(tmp_path: Path) -> None:
    """MUT-06b: Missing or incorrect restart policy on frontend reports problem."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    parts = text.split("frontend:\n")
    assert len(parts) == 2
    frontend_part = parts[1].replace("restart: unless-stopped", 'restart: "no"', 1)
    temp_compose.write_text(parts[0] + "frontend:\n" + frontend_part, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any("restart policy must be 'unless-stopped'" in p for p in problems)


def test_mutation_web_missing_backend_alias(tmp_path: Path) -> None:
    """MUT-07: Omitting network alias 'backend' reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    assert "- backend" in text
    mutated_text = text.replace("- backend", "- other_alias")
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        "web service missing network alias 'backend' on default network" in p
        for p in problems
    )


def test_mutation_web_missing_alias_comment(tmp_path: Path) -> None:
    """MUT-08: Omitting explanatory comment for backend network alias reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    mutated_text = re.sub(
        r"^[ \t]*#.*(?:alias.*backend|backend.*alias).*$\n?",
        "",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    assert mutated_text != text
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        "Missing explanatory comment for 'backend' network alias" in p for p in problems
    )


def test_mutation_cors_missing_5173_origins(tmp_path: Path) -> None:
    """MUT-09: CORS default missing port 5173 origins reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    mutated_text = text.replace(
        "CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000}",
        "CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS:-http://localhost:3000,http://127.0.0.1:3000}",
    )
    assert mutated_text != text
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        "CORS_ALLOWED_ORIGINS missing required origins" in p and "5173" in p
        for p in problems
    )


def test_mutation_csrf_missing_5173_origins(tmp_path: Path) -> None:
    """MUT-10: CSRF default missing port 5173 origins reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    mutated_text = text.replace(
        "CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000}",
        "CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS:-http://localhost:3000,http://127.0.0.1:3000}",
    )
    assert mutated_text != text
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        "CSRF_TRUSTED_ORIGINS missing required origins" in p and "5173" in p
        for p in problems
    )


def test_mutation_cors_missing_3000_origins(tmp_path: Path) -> None:
    """MUT-10b: CORS default missing legacy port 3000 origins reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    mutated_text = text.replace(
        "CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000}",
        "CORS_ALLOWED_ORIGINS: ${CORS_ALLOWED_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173}",
    )
    assert mutated_text != text
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        "CORS_ALLOWED_ORIGINS missing required origins" in p and "3000" in p
        for p in problems
    )


def test_mutation_csrf_missing_3000_origins(tmp_path: Path) -> None:
    """MUT-10c: CSRF default missing legacy port 3000 origins reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    mutated_text = text.replace(
        "CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000}",
        "CSRF_TRUSTED_ORIGINS: ${CSRF_TRUSTED_ORIGINS:-http://localhost:5173,http://127.0.0.1:5173}",
    )
    assert mutated_text != text
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        "CSRF_TRUSTED_ORIGINS missing required origins" in p and "3000" in p
        for p in problems
    )


def test_mutation_env_example_mismatch(tmp_path: Path) -> None:
    """MUT-11: Mismatch between compose default and .env.example origins reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_env.read_text(encoding="utf-8")
    mutated_text = text.replace(
        "CORS_ALLOWED_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
        "CORS_ALLOWED_ORIGINS=http://localhost:3000",
    )
    assert mutated_text != text
    temp_env.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        "Mismatch between compose default and .env.example" in p for p in problems
    )


def test_mutation_postgres_volume_tampered(tmp_path: Path) -> None:
    """MUT-12: Tampered postgres_data volume name reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_compose.read_text(encoding="utf-8")
    assert "name: parking_postgres_data" in text
    mutated_text = text.replace(
        "name: parking_postgres_data",
        "name: altered_pg_data",
    )
    temp_compose.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any("Volume 'postgres_data' must have fixed name" in p for p in problems)


def test_mutation_env_example_compose_profiles_uncommented(tmp_path: Path) -> None:
    """MUT-13: Uncommented COMPOSE_PROFILES in .env.example reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_env.read_text(encoding="utf-8")
    assert "# COMPOSE_PROFILES=frontend" in text
    mutated_text = text.replace(
        "# COMPOSE_PROFILES=frontend", "COMPOSE_PROFILES=frontend"
    )
    temp_env.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        ".env.example must not have uncommented COMPOSE_PROFILES" in p for p in problems
    )


def test_mutation_env_example_compose_profiles_missing_comment(tmp_path: Path) -> None:
    """MUT-14: Missing documented commented line '# COMPOSE_PROFILES=frontend' reports violation."""
    temp_compose, temp_env = create_temp_copies(tmp_path)
    text = temp_env.read_text(encoding="utf-8")
    assert "# COMPOSE_PROFILES=frontend" in text
    mutated_text = text.replace("# COMPOSE_PROFILES=frontend", "")
    temp_env.write_text(mutated_text, encoding="utf-8")

    problems = validate_compose_fullstack(temp_compose, temp_env)
    assert any(
        ".env.example missing documented commented line '# COMPOSE_PROFILES=frontend'"
        in p
        for p in problems
    )


# ==============================================================================
# Live Repository Integration Test
# ==============================================================================


def test_compose_fullstack_live_repo() -> None:
    """
    Live repository inspection ensuring docker-compose.yml and .env.example
    satisfy all full-stack integration requirements.

    Guards against drift across services, loopback ports, network aliases,
    CORS/CSRF origins, commented compose profiles, and named database volumes.
    """
    problems = validate_compose_fullstack(COMPOSE_FILE, ENV_EXAMPLE_FILE)
    assert not problems, (
        "Compose fullstack drift detected on live repository:\n"
        + "\n".join(f"- {p}" for p in problems)
    )


def test_frontend_service_no_env_or_vite_leaks() -> None:
    """
    Assert that the frontend service in docker-compose.yml has no environment,
    no env_file, and no build.args entry, and that no VITE_ string appears anywhere
    in docker-compose.yml or .env.example (preventing frontend config leakage).
    """
    compose_data = load_compose_file(COMPOSE_FILE)
    raw_yaml_text = COMPOSE_FILE.read_text(encoding="utf-8")
    raw_env_text = ENV_EXAMPLE_FILE.read_text(encoding="utf-8")

    problems = check_frontend_no_env_or_vite_leaks(
        compose_data=compose_data,
        raw_yaml_text=raw_yaml_text,
        raw_env_text=raw_env_text,
    )
    assert not problems, "Frontend environment leakage detected:\n" + "\n".join(
        f"- {p}" for p in problems
    )
