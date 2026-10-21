# Car Parking Lot Management System Backend

Intelligent Parking Lot Management System (`Bãi xe Smart Mobility`) — Backend REST API.

[![Python 3.14.7](https://img.shields.io/badge/python-3.14.7-blue.svg)](https://www.python.org/downloads/)
[![Django 6.1.2](https://img.shields.io/badge/django-6.1.2-green.svg)](https://www.djangoproject.com/)
[![PostgreSQL 18.6](https://img.shields.io/badge/postgresql-18.6-blue.svg)](https://www.postgresql.org/)
[![DRF 3.18.3](https://img.shields.io/badge/drf-3.18.3-red.svg)](https://www.django-rest-framework.org/)
[![License: All Rights Reserved](https://img.shields.io/badge/license-All%20Rights%20Reserved-lightgrey.svg)](#6-governance--license)

---

## 1. Project Overview & Scope

- **Scope**: Backend REST API exclusively (`parking_management_backend`). Client applications (Web SPA / Mobile) integrate via OpenAPI 3.0 contracts.
- **Specification Hierarchy**: The Frontend UI design ([`docs/requirements/06-frontend-srs-db-alignment.md`](docs/requirements/06-frontend-srs-db-alignment.md), `TL-01`–`TL-51`) serves as the **primary** specification; the SRS v4.1 catalog ([`docs/requirements/00-srs-catalog.md`](docs/requirements/00-srs-catalog.md)) is **secondary** where frontend screens are silent.
- **Fixed Tech Stack**: Python `3.14.7` (Python 3.15 is strictly forbidden), Django `6.1.2` (LTS roadmap to 6.2 in April 2027), DRF `3.18.3`, PostgreSQL `18.6` via Docker Compose (psycopg `3.3.6`). Detailed rationale in [ADR-0001](docs/adr/0001-fixed-tech-stack-and-lts-roadmap.md) and [ADR-0006](docs/adr/0006-django-skeleton-v2-schema-authority.md).
- **Public Repo Security**: Zero secrets, zero production tokens, zero live credentials committed.

### 1.1. Note for PR #13 Contributor (`@Mercenarya`) and Team

Thank you to `@Mercenarya` for establishing the initial Django project skeleton and domain app structure (`accounts`, `customers`, `employees`, `vehicles`, `tickets`, `parking`, `reports`) in Pull Request #13. That foundation defined the core package layout, settings split (`config/settings/`), and modular app boundaries (`views/`, `services/`, `selectors/`, `serializers/`) that Round 29 builds upon directly.

To align the skeleton with the finalized PostgreSQL 18.6 Schema v2 (`db/01-schema.sql`), Round 29 removes duplicate placeholder files (`create_superuser.py`, `config/settings.py`, `images/`, `Docs/`, and duplicate `views.py` modules), transitions all 28 domain tables and 8 analytical views to unmanaged models (`managed = False`) ingested via `apps/core/migrations/0001_initial.py` (`RunSQL`), and establishes the 3-tier soft-delete base hierarchy, Account authentication model as `AUTH_USER_MODEL`, standardized SQLSTATE exception handling, OpenAPI/Swagger endpoints, and automated CI quality gates (`ruff`, `mypy`, `pytest` against PostgreSQL 18.6).

### 1.2. Not in this foundation (to be built by the assigned members)

Per Team Lead decision **TL-48**, this branch provides only the skeleton foundation (unmanaged models, soft-delete base layer, health check, OpenAPI/Swagger, quality gates, and CI workflow). The following features are intentionally excluded and will be implemented by the assigned team members:

- **Authentication & Session Management**: Login by email or phone (`TL-01`) with the persistent "Remember-Me" token rotation of [ADR-0004](docs/adr/0004-authentication-session-and-remember-token.md), logout, and current user (`/api/auth/me/`).
- **Lookup Reference Endpoints**: Administrative divisions (provinces, districts, wards), positions, vehicle types, and ticket types (`/api/lookups/*`).
- **Domain Business Modules**: Full CRUD and business workflows across all modules (`customers`, `employees`, `vehicles`, `tickets`, `parking`, `reports`, `content`, `audit`).

**Development Guidance for Assigned Members**:

- Refer to [`.claude/skills/05-django-feature-implementation/SKILL.md`](.claude/skills/05-django-feature-implementation/SKILL.md) for 3-tier architecture patterns (`selectors/`, `services/`, `views/`, `serializers/`).
- Refer to [`.claude/skills/13-api-first-contract-and-mock-data/SKILL.md`](.claude/skills/13-api-first-contract-and-mock-data/SKILL.md) for API-first schema contract design.
- Utilize the pre-configured 3-tier template package layouts in each domain app.

---

## 2. Architecture & Data Safety

### 2.1. PostgreSQL Schema Authority & Unmanaged Models ([ADR-0006](docs/adr/0006-django-skeleton-v2-schema-authority.md))

- **Schema Authority**: The database structure is 100% frozen in [`db/01-schema.sql`](db/01-schema.sql) (Schema v2) as the absolute Single Source of Truth (28 base tables, 8 analytical views, 69 `ON DELETE RESTRICT` foreign keys, 87 user triggers, and 22 custom functions).
- **Unmanaged Models (`managed = False`)**: All 28 domain tables and 8 views are mapped to Django models declaring `managed = False`. Django migrations must NEVER emit automated DDL (`CREATE/ALTER/DROP TABLE`) on domain entities.
- **Django Internal Tables Coexistence**: Native Django tables (`django_migrations`, `django_content_type`, `django_session`) remain managed by Django's native migrations, coexisting safely in the same PostgreSQL schema.
- **Foreign Keys**: Declared with `on_delete=models.DO_NOTHING` and `db_constraint=False` in unmanaged models; referential integrity is enforced 100% by PostgreSQL `ON DELETE RESTRICT` constraints.
- **Live Parity Verification**: Automated test suite ([`tests/test_schema_parity.py`](tests/test_schema_parity.py)) verifies 100% schema parity (tables, views, columns, foreign keys) between Django models and live PostgreSQL catalog.

### 2.2. Three-Tier Base Hierarchy & Safe Soft-Delete ([ADR-0003](docs/adr/0003-data-deletion-soft-delete-protect-and-audit.md))

- **Base Hierarchy**:
  - `TimeStampedModel`: Base timestamps (`created_at`, `updated_at`, `editable=False`).
  - `SoftDeleteBaseModel`: Timestamps plus `row_version` for optimistic concurrency.
  - `SoftDeleteModel`: Implements `deleted_at`, `deleted_by`, custom managers (`deleted_at IS NULL`, `with_deleted()`, `only_deleted()`), and methods (`soft_delete()`, `restore()`).
- **Hard Deletion Protection**: Physical `delete()` on business models is overridden to prevent accidental data loss. Plain `DELETE` is permitted only on temporary token models (`PersistentLoginToken`, `PasswordResetToken` per TL-36 / ADR-0004).
- **Audit Immutability**: Financial and operational logs (`Ticket`, `TicketRenewal`, `VehicleEntryExitLog`, `Payment`, `ActivityLog`) are protected against tampering by database triggers.

### 2.3. Three-Tier API Architecture

- **`views/`**: Thin API ViewSets handling HTTP status codes, permissions (`IsAuthenticated`, `IsManager`), and calling services/selectors.
- **`services/`**: Write operations, transaction boundaries (`@transaction.atomic`), row locking (`select_for_update()`), and soft-delete guards.
- **`selectors/`**: Read-only queries with `select_related()` and `prefetch_related()` preventing N+1 queries.
- **`serializers/`**: DRF `ModelSerializer` with automatic field mapping, whitespace trimming, max-length validation, and standardized error envelopes.
- **Standard Error Envelope**: Uniform JSON response `{"code": "...", "message": "...", "details": {...}}` translating PostgreSQL SQLSTATE codes (`23514`, `55000`, `23503`, `23505`, `22023`).

---

## 3. Quick Start (Development & Operations)

### Step 1: Environment Configuration

Copy the template and configure local environment variables:

```bash
cp .env.example .env
```

Key environment variables:

- `SECRET_KEY`: Django secret key (required).
- `POSTGRES_PASSWORD`: PostgreSQL database password (required).
- `POSTGRES_DB`: PostgreSQL database name (default: `parking_db`).
- `POSTGRES_USER`: PostgreSQL database user (default: `parking_user`).
- `WEB_PORT`: Host port for Django backend (default: `8000`, bound exclusively to `127.0.0.1`).
- `POSTGRES_PORT`: Host port for PostgreSQL database (default: `5432`, bound exclusively to `127.0.0.1`).
- `DEBUG`: Django debug mode (default: `True`).
- `ALLOWED_HOSTS`: Permitted HTTP host headers (default: `localhost,127.0.0.1`).
- `PARKING_HOURLY_RATE_VND`: Hourly parking fee rate in VND (default: `10000`).

**Production Serving & Concurrency (H3, H4)**:

- `GUNICORN_WORKERS`: Gunicorn worker processes (default: `4`).
- `GUNICORN_THREADS`: Concurrent threads per worker using `gthread` (default: `6`).
- `GUNICORN_MAX_REQUESTS`: Max requests before worker recycle (default: `0` to disable cyclic restarts and avoid restart storms; memory guarded via RSS).
- `GUNICORN_MAX_REQUESTS_JITTER`: Random jitter for worker recycle (default: `100`).
- `GUNICORN_MEMORY_LIMIT_MB`: Max RSS threshold in MB checked via `post_request` hook before graceful exit (default: `1536`).
- `GUNICORN_TIMEOUT`: Worker timeout in seconds (default: `30`).
- `PARKING_OCR_CONCURRENCY_LIMIT`: Maximum simultaneous OCR inference requests per worker (default: `4`).
- `PARKING_OCR_QUEUE_TIMEOUT`: Max seconds to wait for OCR semaphore queue before returning 503 (default: `2.0`).
- `ONNX_INTRA_OP_THREADS`: Parallel threads per ONNX operator execution (default: `1` to avoid thread contention).
- `ONNX_INTER_OP_THREADS`: Parallel threads across ONNX graph operators (default: `1`).
- `ONNX_ALLOW_SPINNING`: Disable CPU thread spinning when idle (`session.intra_op.allow_spinning`, default: `0`).
- `PARKING_OCR_ADAPTIVE_ENSEMBLE`: Enable fast single-pass OCR when Model 1 achieves high confidence (`min_char_conf >= 94.0%`, `c0 >= 99.2%`, and valid Vietnamese car plate grammar; default: `True`).
- `PARKING_OCR_CROP_MARGIN`: Padding margin in pixels applied to detected plate crop (default: `4`).
- `PARKING_OCR_MODELS_DIR`: Directory path containing baked ONNX models (default: `/app/models/ocr`).
- `DB_POOL_ENABLE`: Enable psycopg database connection pooling (default: `False`, using `CONN_MAX_AGE=60` with `CONN_HEALTH_CHECKS=True`).
- `DB_CONN_MAX_AGE`: Persistent database connection lifespan in seconds (default: `60`).

---

### Option A: Launch Full Stack via Docker Compose (Recommended)

Run both the PostgreSQL 18.6 database and the Python 3.14.7 backend container with a single command:

```bash
# Build images and start all services:
docker compose up --build

# Or run in detached background mode:
docker compose up -d --build
```

*Operational Details*:

- **Automated Readiness**: The `web` container entrypoint automatically waits for PostgreSQL health checks and runs `python manage.py migrate --noinput` (controlled by `RUN_MIGRATIONS: "1"`). By default, `LOAD_SAMPLE_DATA` is set to `0` (`${LOAD_SAMPLE_DATA:-0}`) in `docker-compose.yml` to prevent accidental seed data ingestion into existing databases.
- **Enabling Sample Data**: To automatically seed sample data on container startup, set `LOAD_SAMPLE_DATA=1` in your `.env` file or run:

  ```bash
  LOAD_SAMPLE_DATA=1 docker compose up --build
  ```

- **Production Fail-Loud Protection**: When running with `DEBUG=False` (production/staging), enabling `LOAD_SAMPLE_DATA=1` will fail loudly: `python manage.py load_sample_data` raises `CommandError` and halts the container immediately (`set -eu` in `entrypoint.sh`), preventing accidental production data pollution unless `--force-production` is explicitly passed manually.
- **Manual Data Loading**: If needed, sample data can be re-loaded manually via:

  ```bash
  docker compose exec web python manage.py load_sample_data
  ```

- **Security Boundary**: Ports are strictly bound to local loopback interface `127.0.0.1:${WEB_PORT:-8000}`.
- **Media Storage**: Uploaded captures are mounted via bind mount (`./media:/app/media`). Zero named volumes are allocated for media to preserve host Docker volume safety.
- **Check Status**: Run `docker compose ps` to inspect container health.

---

### Option B: Local Python Development Setup

#### Step 2: Start PostgreSQL 18.6 Database Standalone

Launch the official PostgreSQL 18.6 container via Docker Compose:

```bash
docker compose up -d db
```

*Verification*: PostgreSQL binds to `127.0.0.1:${POSTGRES_PORT:-5432}`. Persistent data volume is named `parking_postgres_data`.

### Step 3: Python Environment & Dependencies

Activate Python 3.14.7 virtual environment and install dependencies:

```bash
python -m venv .venv

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# On Linux / macOS:
source .venv/bin/activate

# Install development dependencies:
pip install -r requirements/02-dev.txt
```

### Step 4: Initialize Database (RunSQL Ingestion)

Execute initial migration to ingest Schema v2 directly from `db/01-schema.sql`:

```bash
python manage.py migrate
```

*Architecture Note*: `apps/core/migrations/0001_initial.py` reads `db/01-schema.sql` directly from disk (`atomic=False`, `reverse_sql=RunSQL.noop`). It provisions all 28 tables, 8 views, 69 foreign keys, and 87 triggers without automated Django DDL.

### Step 5: Seed Sample Data Safely

Load initial catalog and operational seed data:

```bash
python manage.py load_sample_data
```

*Production Protection*: In production/staging (`DEBUG=False`), the command is locked by default and requires the `--force-production` flag to execute.

### Step 5.1: Purge Orphan Scan Images (`purge_orphan_scans`)

To reclaim disk space by purging unreferenced scan images under `MEDIA_ROOT/parking_scans` that are not tied to any parking session log (`VehicleEntryExitLog.entry_image_url` or `exit_image_url`), use the dedicated management command:

```bash
# 1. Dry-run simulation (default, safe inspection without deleting files):
python manage.py purge_orphan_scans

# Or inside Docker web container:
docker compose exec web python manage.py purge_orphan_scans

# 2. Execute actual deletion (purges unreferenced files older than 24 hours):
python manage.py purge_orphan_scans --no-dry-run --older-than-hours 24

# Or inside Docker web container:
docker compose exec web python manage.py purge_orphan_scans --no-dry-run --older-than-hours 24
```

**Command Parameters**:

- `--dry-run` / `--no-dry-run`: Defaults to `--dry-run` for safety. Pass `--no-dry-run` to permanently remove orphan files.
- `--older-than-hours <N>`: Only considers files modified earlier than $N$ hours ago (default: `24.0`). Prevents deleting scan images from active uploads or ongoing check-in sessions.
- Preserves 100% of referenced image files and never mutates or drops database log rows.
- Automatically cleans up empty `YYYY/MM/DD` date subdirectories.

### Step 6: Create Administrative Superuser

Create an administrative account interactively:

```bash
python manage.py createsuperuser
```

*Usage*: When prompted, provide your **Email** (or Phone), Full Name, and a strong password. This creates an `Account` record with role `MANAGER` and access privileges. Never commit hardcoded credential scripts to Git.

### Step 7: Launch Development Server

```bash
python manage.py runserver
```

### Step 8: Interactive API Documentation, CSRF & Swagger "Try it out"

Access the interactive API documentation and health endpoints:

- **Swagger UI**: [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)
- **ReDoc**: [http://127.0.0.1:8000/api/redoc/](http://127.0.0.1:8000/api/redoc/)
- **OpenAPI 3.0 Schema**: [http://127.0.0.1:8000/api/schema/](http://127.0.0.1:8000/api/schema/)
- **System Health Check**: [http://127.0.0.1:8000/api/health/](http://127.0.0.1:8000/api/health/)

#### Session Authentication & CSRF Handling

The backend implements `SessionAuthentication` per ADR-0004. For all unsafe state-changing requests (`POST`, `PUT`, `PATCH`, `DELETE`):

1. The client must supply an active `sessionid` cookie.
2. The client must include the **`X-CSRFToken`** header matching the value of the `csrftoken` cookie.

#### Minting an Authenticated Session for Swagger "Try it out"

To test protected parking endpoints via Swagger UI "Try it out" without exposing or committing user credentials, mint a temporary authenticated session key for a seeded `EMPLOYEE` or `MANAGER` account using this one-liner:

```bash
docker compose exec web python manage.py shell -c "from importlib import import_module; from django.conf import settings; from django.contrib.auth import SESSION_KEY, BACKEND_SESSION_KEY, HASH_SESSION_KEY; from apps.accounts.models import Account; s = import_module(settings.SESSION_ENGINE).SessionStore(); u = Account.objects.filter(role__in=['MANAGER','EMPLOYEE'], is_active=True).first(); s[SESSION_KEY] = str(u.pk); s[BACKEND_SESSION_KEY] = settings.AUTHENTICATION_BACKENDS[0]; s[HASH_SESSION_KEY] = u.get_session_auth_hash(); s.save(); print(f'MINTED_SESSION_KEY={s.session_key}')"
```

Then in your browser developer tools (or via browser automation), add the cookie:

- **Name**: `sessionid`
- **Value**: `<MINTED_SESSION_KEY>`
- **Domain**: `127.0.0.1` / `localhost`

And ensure your requests send the header `X-CSRFToken` matching your browser's `csrftoken` cookie.

### Step 9: Run Automated Test Suite

Execute the full automated test suite with coverage against live PostgreSQL 18.6:

```bash
pytest -v --cov=apps
```

*Threshold*: All tests must pass with line coverage enforced at `>= 80%` (default deterministic suite: `992` passed, `7` skipped; opt-in relative performance benchmarks marked `@pytest.mark.perf` run when `RUN_PERF_TESTS=1`).

### Step 10: Performance Testing & High-Concurrency Soak Runbook (H1, H3, H4, H5, H9a, K2, K7)

The repository provides a standalone, high-performance load testing tool (`tests/perf/load_test.py`) that uses native standard libraries (`urllib`, `http.client`, `threading`) and Pillow for synthetic runtime image generation.

#### Features

- **Runtime Synthetic Images (H9a, K2)**: Pre-generates realistic Vietnamese license plates before worker threads start across multiple resolutions (`640x480`, `1920x1080`, and `4000x3000` 12 MP) using Pillow. Zero dependency on external sample files.
- **Cold vs. Warm Burst Profiling (K2)**: Supports `--warmup` and `--warmup-duration` (default `3.0` seconds) to report separate `COLD RUN METRICS` and `WARM RUN METRICS` tables.
- **Throwaway Media Hygiene (K7)**: Provides `tests/perf/docker-compose.tmpfs.yml` (mounting `/app/media` on RAM `tmpfs`) and `--purge-scans` (invoking `purge_orphan_scans` automatically after local runs) so benchmarks never pollute the repository `media/` directory.
- **Fail-Fast Error Accounting (H8c)**: Fatal errors (`500 Internal Server Error`, connection drops, or unexpected status codes outside `--allow-status`) are counted and reported. The process exits with code `1` upon any unexpected failure.
- **Circuit Breaker Validation**: Tests backend under heavy concurrency (`32` to `64` concurrent workers) while verifying semaphore admission (`503 Service Unavailable` with `Retry-After`) under saturation.

#### Running Soak & Concurrency Tests

```bash
# 0. Recommended: Start stack with RAM tmpfs over /app/media so zero scan files persist on host disk:
docker compose -f docker-compose.yml -f tests/perf/docker-compose.tmpfs.yml up -d

# 1. Full benchmark suite across all scenarios at concurrency 32 and 64 (with automatic orphan scan cleanup):
python tests/perf/load_test.py --duration 10 --purge-scans

# 2. High-concurrency 180-second soak test (64 clients for 180 seconds):
python tests/perf/load_test.py --concurrency 64 --duration 180 --scenario lookup

# 3. Targeted 12 MP cold-start vs. warm-state burst test (K2):
python tests/perf/load_test.py --concurrency 32,64 --duration 10 --scenario scan_12mp --warmup --purge-scans
```

#### Query Ceiling Budgets & Database Safeguards (H5)

Automated tests (`tests/parking/test_query_budgets.py`) enforce hard SQL query ceilings using `django_assert_max_num_queries`:

- Plate Scan (`POST /api/v1/parking/plate-scans/`): `4 <= 5` queries
- Vehicle Lookup (`GET /api/v1/parking/vehicles/lookup/`): `3 <= 5` queries
- Vehicle Search (`GET /api/v1/parking/vehicles/search/`): `5 <= 5` queries
- Check-in (`POST /api/v1/parking/sessions/check-in/`): `10 <= 10` queries
- Check-out (`POST /api/v1/parking/sessions/{id}/check-out/`): `7 <= 9` queries
- Sessions List (`GET /api/v1/parking/sessions/`): `267.1 RPS` (`p95 = 196.9 ms <= 277 ms`, `4.26x` Round 33 throughput at `c = 32`)

### Step 11: Production Operations Runbook & Incident Playbooks (J7.d, Standard 6)

This runbook provides authoritative operational procedures, parameter safety envelopes, structured log specifications, and incident response playbooks for on-call engineers managing the Smart Mobility parking backend stack.

#### 3.11.1 System Start/Stop Lifecycle (Zero Volume Loss)

```bash
# ------------------------------------------------------------------------------
# 1. STARTUP
# ------------------------------------------------------------------------------
# Build images and start backend stack in detached mode:
docker compose up -d --build

# Verify container health status (expected: web: healthy, db: healthy):
docker compose ps

# Follow application logs:
docker compose logs -f web

# Verify readiness via HTTP probe:
curl -f http://127.0.0.1:8000/api/health/

# ------------------------------------------------------------------------------
# 2. DATA INITIALIZATION & MAINTENANCE
# ------------------------------------------------------------------------------
# Run pending database migrations:
docker compose exec web python manage.py migrate --noinput

# Load sample seed data (Development only; production is protected by default):
docker compose exec web python manage.py load_sample_data

# Purge unreferenced scan images older than 24 hours:
docker compose exec web python manage.py purge_orphan_scans --no-dry-run --older-than-hours 24

# ------------------------------------------------------------------------------
# 3. GRACEFUL SHUTDOWN
# ------------------------------------------------------------------------------
# Stop containers gracefully (sends SIGTERM, allowing inflight requests to finish):
docker compose stop

# Remove containers while STRICTLY PRESERVING ALL DATA VOLUMES:
docker compose down

# CRITICAL INVARIANT WARNING:
# NEVER execute `docker compose down -v` or `docker volume prune` on the host!
# The host Docker volume count must strictly remain pinned at 27.
```

#### 3.11.2 Key Operational Tunables & Safe Ranges

The table below enumerates all core operational parameters configured through environment variables via `django-environ` in `config/settings/base.py`:

| Parameter | Default | Type | Safe Range | Description & Architectural Constraints |
| :--- | :---: | :---: | :---: | :--- |
| `GUNICORN_WORKERS` | `4` | `int` | `2` – `8` | Number of Gunicorn worker processes. Typically $1 - 2 \times \text{CPU cores}$. |
| `GUNICORN_THREADS` | `6` | `int` | `5` – `8` | Threads per worker (`gthread`). **MANDATORY**: `GUNICORN_THREADS` (`6`) > `PARKING_OCR_CONCURRENCY_LIMIT` (`4`) to ensure queuing threads trigger HTTP 503 back-pressure. |
| `GUNICORN_TIMEOUT` | `30` | `int` | `15` – `60` | Request timeout before worker SIGKILL recycle. |
| `GUNICORN_MAX_REQUESTS` | `0` | `int` | `0` or $\ge 5000$ | Requests before recycle. Defaults to `0` (disabled) to avoid simultaneous worker restart storms. |
| `GUNICORN_MEMORY_LIMIT_MB` | `1536` | `int` | `1024` – `3072` | Worker RSS memory ceiling checked via `post_request` hook for graceful memory recycling. |
| `PARKING_OCR_CONCURRENCY_LIMIT` | `4` | `int` | `2` – `4` | Semaphore slot limit for concurrent ONNX OCR inference per worker to prevent CPU saturation. |
| `PARKING_OCR_QUEUE_TIMEOUT` | `2.0` | `float` | `0.5` – `5.0` | Maximum queue wait time before shedding load with HTTP `503 Service Unavailable` and `Retry-After: 3`. |
| `PARKING_OCR_RETRY_AFTER` | `3` | `int` | `2` – `10` | Header value `Retry-After` (seconds) returned on 503 overload. |
| `PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD` | `90.0` | `float` | `85.0` – `95.0` | Minimum per-character confidence (%) required for `AUTO` verdict. 90.0% guarantees $\le 1.0\%$ wrong-in-AUTO. |
| `PARKING_OCR_ADAPTIVE_ENSEMBLE` | `True` | `bool` | `True` / `False` | When `True`, skips Model 2 (Mobile-ViT-v2) if Model 1 (CCT) confidence exceeds thresholds (~50% CPU savings). |
| `PARKING_OCR_ADAPTIVE_THRESHOLD` | `94.0` | `float` | `90.0` – `98.0` | Model 1 character confidence threshold for adaptive single-model path. |
| `PARKING_OCR_LEADING_CHAR_THRESHOLD` | `99.2` | `float` | `95.0` – `99.9` | Model 1 leading province digit confidence threshold for adaptive single-model path. |
| `PARKING_OCR_CROP_MARGIN` | `4` | `int` | `0` – `10` | Padding margin (pixels) added around detected plate bounding box before OCR inference. |
| `PARKING_REVIEW_DETECTOR_CONF_THRESHOLD` | `80.0` | `float` | `50.0` – `95.0` | Bounding box detection confidence (%) threshold; below triggers `LOW_DETECTION_CONFIDENCE`. |
| `PARKING_REVIEW_MIN_ASPECT_RATIO` | `1.3` | `float` | `1.0` – `2.0` | Minimum plate aspect ratio; outside triggers `IRREGULAR_ASPECT_RATIO`. |
| `PARKING_REVIEW_MAX_ASPECT_RATIO` | `6.0` | `float` | `4.0` – `10.0` | Maximum plate aspect ratio. |
| `PARKING_REVIEW_MIN_SHARPNESS` | `30.0` | `float` | `10.0` – `100.0` | Minimum Laplacian sharpness score; below triggers `LOW_IMAGE_SHARPNESS`. |
| `ONNX_INTRA_OP_THREADS` | `1` | `int` | `1` – `2` | Parallel execution threads per ONNX operator. Kept at 1 to eliminate thread contention. |
| `ONNX_INTER_OP_THREADS` | `1` | `int` | `1` – `2` | Parallel execution threads between ONNX operators. |
| `ONNX_ALLOW_SPINNING` | `False` | `bool` | `False` (`0`) | Disables busy-wait thread spinning in ONNX Runtime (`session.intra_op.allow_spinning = "0"`). |
| `PARKING_LOG_MASK_PLATES` | `True` | `bool` | `True` / `False` | Masks PII plate numbers in structured JSON stdout logs (e.g., `51F***81`). Mandatory for Decree 13/2023. |
| `DB_CONN_MAX_AGE` | `60` | `int` | `0` – `300` | Lifetime (seconds) of persistent PostgreSQL database connections. |
| `DB_POOL_ENABLE` | `False` | `bool` | `True` / `False` | Optional psycopg connection pool. When enabled, `DB_POOL_MAX_SIZE=8` ($4 \times 8 = 32 < 100$). |

#### 3.11.3 Reading Structured JSON Observability Logs

Every critical API request (`/api/v1/parking/plate-scans/`, check-in, check-out) emits a single, structured JSON line to `stdout` via `finalize_observability_response`:

```json
{
  "event": "parking_api_request",
  "request_id": "9a7b4c2d-8e1f-4a3b-b5c6-7d8e9f0a1b2c",
  "endpoint": "/api/v1/parking/plate-scans/",
  "status": 200,
  "total_ms": 52.34,
  "stage_timings_ms": {
    "decode": 2.14,
    "detect": 38.65,
    "ocr1": 4.59,
    "ocr2": 0.00,
    "db": 5.82,
    "write": 1.14
  },
  "user_id": 14,
  "review_status": "AUTO",
  "review_reasons": [],
  "plate": "51F***81"
}
```

- **`event`**: Standardized event identifier (`parking_api_request`) for centralized log aggregators (ELK, Datadog, Loki).
- **`request_id`**: Traceable UUIDv4 matching the `X-Request-ID` response header.
- **`status`**: HTTP response status code (`200`, `400`, `401`, `422`, `503`).
- **`total_ms`**: End-to-end processing latency in milliseconds.
- **`stage_timings_ms`**: Fine-grained latency breakdown:
  - `decode`: Image buffer read and JPEG decode (draft-first mode, typically $\le 3\text{ ms}$).
  - `detect`: YOLOv9 plate detection inference ($\sim 35 - 45\text{ ms}$, ~70-80% of total OCR budget).
  - `ocr1`: Model 1 CCT character recognition inference ($\sim 4.3\text{ ms}$).
  - `ocr2`: Model 2 Mobile-ViT-v2 fallback OCR ($0.00\text{ ms}$ when adaptive skip succeeds; $\sim 4.3\text{ ms}$ otherwise).
  - `db`: Database lookups (vehicle indexing, active ticket, open session queries).
  - `write`: File storage write to `parking_scans/YYYY/MM/DD/`.
- **`review_status`**: Policy verdict (`AUTO` for automated barrier opening; `NEEDS_REVIEW` for manual operator inspection).
- **`review_reasons`**: Specific trigger codes requiring review (`LOW_CHAR_CONFIDENCE`, `POSITION_CORRECTED`, `MODEL_DISAGREEMENT`, `UNKNOWN_PLATE_PATTERN`, etc.).
- **`plate`**: Privacy-masked license plate string (`51F***81`). Full raw plates are persisted exclusively in encrypted/audited database tables.

#### 3.11.4 Incident Playbook 1: 503 Service Unavailable Storm

**Symptoms**:

- Sudden surge of HTTP 503 responses on `/api/v1/parking/plate-scans/`.
- Error payload code: `{"code": "PROP-4.5.1-P15", "message": "OCR engine is currently busy..."}` with `Retry-After: 3`.
- CPU utilization approaching 100%.

**Root Causes**:

- Traffic spike exceeding OCR semaphore capacity (e.g., $> 50\text{ RPS}$ concurrent scans).
- Client or gate controller retry storms failing to respect the `Retry-After` header.
- Semaphore timeout `PARKING_OCR_QUEUE_TIMEOUT` configured too aggressively (e.g., $< 0.5\text{ s}$).

**Triage Commands**:

```bash
# 1. Count 503 occurrences in recent logs:
docker compose logs --tail=200 web | grep -c '"status": 503'

# 2. Check container CPU/RAM utilization:
docker stats --no-stream

# 3. Inspect PostgreSQL connection pool and lock states:
docker compose exec db psql -U parking_user -d parking_db -c \
  "SELECT count(*), state, wait_event_type FROM pg_stat_activity GROUP BY state, wait_event_type;"
```

**Remediation**:

1. Confirm gate controllers enforce exponential back-off respecting `Retry-After: 3`.
2. If traffic burst is transient, temporarily raise `PARKING_OCR_QUEUE_TIMEOUT=3.5` in `.env` and reload (`docker compose up -d web`).
3. Scale workers vertically on multi-core hosts: `GUNICORN_WORKERS=6`, `GUNICORN_THREADS=6`.
4. Ensure `PARKING_OCR_ADAPTIVE_ENSEMBLE=True` is active to preserve 50% OCR CPU capacity.

#### 3.11.5 Incident Playbook 2: Memory Footprint Growth

**Symptoms**:

- Worker container RSS steadily climbs without plateauing.
- Docker container terminated with Exit Code 137 (OOMKilled).
- Gunicorn logs indicate `Worker ... was killed by signal 9` or watchdog log `Graceful memory exit: worker RSS ... MB exceeds limit ... MB`.

**Root Causes**:

- Ingestion of unconstrained 12 MP to 25 MP images decoding into large uncompressed rasters (36 MB - 75 MB per thread).
- Decompression bomb exploits attempting to exhaust memory.

**Triage Commands**:

```bash
# 1. Inspect live container memory:
docker stats --no-stream parking_management_backend-web-1

# 2. Check for memory-triggered worker restarts:
docker compose logs web | grep -E "Graceful memory exit|worker was killed|Booting worker"

# 3. Check disk space in scan upload directory:
docker compose exec web du -sh /app/media/parking_scans
```

**Remediation**:

1. Confirm `GUNICORN_MEMORY_LIMIT_MB=1536` is configured in `.env` for proactive worker recycling.
2. Verify image dimension guards: `DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880` (5 MB) and `MAX_IMAGE_PIXELS = 25_000_000`.
3. In `docker-compose.yml`, enforce container hard memory limits (`mem_limit: 2048m`).

#### 3.11.6 Incident Playbook 3: Worker Restart Loop & Healthcheck Failure

**Symptoms**:

- Continuous `Booting worker with pid: ...` messages in Gunicorn logs.
- Container state shows `unhealthy` in `docker compose ps`.
- Clients receive `502 Bad Gateway` or `Connection reset by peer`.

**Root Causes**:

- Database connection pool exhaustion (`max_connections = 100` exceeded).
- Healthcheck probe (`/api/health/`) starved or timing out due to lock contention.
- Missing ONNX model files in `/app/models/ocr/` causing import failure during worker boot.
- Unhandled query timeouts exceeding `GUNICORN_TIMEOUT=30s`.

**Triage Commands**:

```bash
# 1. Count worker reboots in the last 5 minutes:
docker compose logs --tail=200 web | grep -c "Booting worker"

# 2. Probe healthcheck directly from inside container:
docker compose exec web curl -v http://127.0.0.1:8000/api/health/

# 3. Check for critical exceptions or tracebacks:
docker compose logs --tail=100 web | grep -E "CRITICAL|TIMEOUT|Traceback"

# 4. Verify presence of required ONNX models:
docker compose exec web ls -la /app/models/ocr
```

**Remediation**:

1. If PostgreSQL connection exhaustion occurs, ensure `DB_CONN_MAX_AGE=60` and `DB_POOL_MAX_SIZE <= 8` so total connections ($4 \text{ workers} \times 8 = 32$) remain safely below the 100 connection cap.
2. The `/api/health/` probe is isolated and lightweight; verify it does not contend for OCR semaphores.
3. Temporarily increase `GUNICORN_TIMEOUT=60` during heavy maintenance operations.

#### 3.11.7 Safe Rollback Plan (Zero Volume Loss)

**Core Safety Rules**:

- **Zero Volume Destruction**: NEVER run `docker compose down -v` or `docker volume prune`. The host volume count must remain strictly `27`.
- **Database Schema Protection**: Business tables are unmanaged (`managed = False`). Schema migrations in `apps/core/migrations/0001_initial.py` declare `reverse_sql=RunSQL.noop` to protect the frozen schema from accidental drops.

**Rollback Scenarios**:

##### Scenario 1: Application Image Rollback

```bash
# Re-tag previous stable release image and restart container:
export WEB_IMAGE=parking_management_backend-web:v35
docker compose up -d --no-deps web
docker compose ps
curl -f http://127.0.0.1:8000/api/health/
```

##### Scenario 2: Configuration Rollback

```bash
# Restore previous settings in .env and reload without database downtime:
docker compose up -d web
```

##### Scenario 3: Database Migration Rollback (Django Core Only)

```bash
docker compose exec web python manage.py showmigrations
docker compose exec web python manage.py migrate core <target_migration>
```

---

## 4. CI/CD & Branch Protection Rules for Repository Owner

To maintain production stability and prevent untested code merges, the **Repository Owner** must configure GitHub Branch Protection Rules on branches `main` and `dev`:

1. **Require Status Checks to Pass Before Merging**:
   - Enable status check: `django-check` (workflow `.github/workflows/02-django-check.yml`).
   - Checks enforced in workflow:
     - `ruff check .` (Python linting)
     - `ruff format --check .` (Formatting style)
     - `mypy .` (Strict type checking with django-stubs)
     - `python manage.py makemigrations --check --dry-run` (No unintended migrations)
     - `python manage.py spectacular --validate --fail-on-warn` (OpenAPI contract validation)
     - `pytest --cov=apps --cov-report=term-missing --cov-fail-under=80` (All tests passed, coverage >= 80% on live PostgreSQL 18.6)
2. **Require Pull Request Reviews Before Merging**: Minimum 1 approving review from team leads.
3. **Require Linear History / No Direct Push**: Direct commits to `main` and `dev` are strictly blocked.
4. **Preserved Schema Check**: Keep `.github/workflows/01-db-schema-check.yml` active to protect frozen `db/` schema files.

---

## 5. Documentation & AI Operating System

- **Requirements & Specifications**:
  - [`docs/requirements/06-frontend-srs-db-alignment.md`](docs/requirements/06-frontend-srs-db-alignment.md) — Primary FE-first decisions (`TL-01`–`TL-51`).
  - [`docs/requirements/07-fe-srs-traceability.md`](docs/requirements/07-fe-srs-traceability.md) — Bidirectional traceability matrix.
  - [`docs/requirements/00-srs-catalog.md`](docs/requirements/00-srs-catalog.md) — Secondary SRS v4.1 requirements catalog.
  - [`docs/requirements/03-delete-rules-catalog.md`](docs/requirements/03-delete-rules-catalog.md) — Soft-delete and purge specifications.
- **Database Architecture**:
  - [`db/00-README.md`](db/00-README.md) — Database schema architecture and object documentation.
  - [`db/01-schema.sql`](db/01-schema.sql) — Authoritative DDL Schema v2 (frozen).
  - [`db/02-seed.sql`](db/02-seed.sql) — Authoritative sample seed data (frozen).
  - [`db/03-erd.asta`](db/03-erd.asta) — Astah UML model.
- **Architecture Decision Records (ADRs)**:
  - [`docs/adr/0001-fixed-tech-stack-and-lts-roadmap.md`](docs/adr/0001-fixed-tech-stack-and-lts-roadmap.md)
  - [`docs/adr/0002-git-branching-and-collaboration-workflow.md`](docs/adr/0002-git-branching-and-collaboration-workflow.md)
  - [`docs/adr/0003-data-deletion-soft-delete-protect-and-audit.md`](docs/adr/0003-data-deletion-soft-delete-protect-and-audit.md)
  - [`docs/adr/0004-authentication-session-and-remember-token.md`](docs/adr/0004-authentication-session-and-remember-token.md)
  - [`docs/adr/0005-local-docker-compose-for-postgresql.md`](docs/adr/0005-local-docker-compose-for-postgresql.md)
  - [`docs/adr/0006-django-skeleton-v2-schema-authority.md`](docs/adr/0006-django-skeleton-v2-schema-authority.md)
  - [`docs/adr/0007-backend-service-in-docker-compose-and-plate-ocr-engine.md`](docs/adr/0007-backend-service-in-docker-compose-and-plate-ocr-engine.md)
- **AI Operating System**:
  - [`.claude/rules/`](.claude/rules/) — Numbered enterprise rules (`01`–`10`).
  - [`.claude/skills/`](.claude/skills/) — Numbered specialized skills (`01`–`13`).
  - [`CLAUDE.md`](CLAUDE.md) — Project context for AI coding assistants.

---

## 6. Governance & License

- **License**: All Rights Reserved. (No open-source license granted).
- **Vulnerability Reporting**: Strictly via GitHub Private Vulnerability Reporting. See [SECURITY.md](SECURITY.md).

### 6.1 Third-Party Dataset Attribution (CC-BY-4.0)

This project utilizes the 322-plate Vietnamese license plate benchmark dataset for model evaluation and confidence calibration:

- **Dataset Name**: `sonnetechnology/license-plate-text-recognition-full`
- **Author**: Sonnetechnology
- **Source Link**: [Hugging Face Dataset: sonnetechnology/license-plate-text-recognition-full](https://huggingface.co/datasets/sonnetechnology/license-plate-text-recognition-full)
- **License**: [Creative Commons Attribution 4.0 International (CC-BY-4.0)](https://creativecommons.org/licenses/by/4.0/)
