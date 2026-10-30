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

- **Authentication & Session Management**: *(Delivered in Round 43 via TL-52 & ADR-0004)* Login by email or phone (`TL-01`) with Argon2 password hashing, persistent "Remember-Me" token rotation with 30s grace window (`OQ-87`), dual-key brute-force rate limiting (`PROP-4.1-P01`), CSRF handshake, logout, and current user profile (`/api/v1/auth/*`).
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

### Choose how to run the backend

The backend provides two independent startup options depending on developer workflow preference and workstation setup:

| Feature | Option 1: Run with Docker | Option 2: Run locally with Python (no Docker) |
|---|---|---|
| **Target Audience** | Developers who want a turnkey full-stack environment without installing database services on the host machine. | Developers who prefer running without Docker Desktop, using local Python and PostgreSQL (with pgAdmin for database inspection). |
| **Prerequisites** | Docker Desktop or Docker Engine & Docker Compose. | Python 3.14.7 (Python 3.15 is unsupported), PostgreSQL 18.x (with pgAdmin 4). |
| **Advantages** | Self-contained packaging, automatic network/volume provisioning, and automatic PostgreSQL extension loading. | Lower RAM/CPU consumption, direct local debugging, and visual data inspection via pgAdmin 4. |
| **Disadvantages** | Requires host resources for container virtualization. | Requires manual PostgreSQL service installation, role provisioning, and Python virtual environment management. |

---

### Option 1: run with Docker

Launch the complete system consisting of a PostgreSQL 18.6 database and a Python 3.14.7 application server (Gunicorn & ONNX Runtime) via pre-configured container services.

#### 1. Clone repository and create environment file

Clone the repository to your local machine:

```bash
git clone https://github.com/quan-ly-bai-dau-xe/parking_management_backend.git
cd parking_management_backend
```

Create the `.env` configuration file from `.env.example`:

```bash
# On Linux / macOS:
cp .env.example .env

# On Windows (PowerShell):
Copy-Item .env.example .env
```

Configure required environment variables in `.env`:

```env
DEBUG=True
SECRET_KEY=your_secret_key_here
POSTGRES_PASSWORD=your_password_here
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

`DEBUG=True` is required for development: when `DEBUG=False` (production only), `load_sample_data` is blocked and Swagger UI static CSS/JS assets return 404.

Generate a secure random `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

#### Docker Compose Environment Note

The `.env` file is read by Docker Compose on the host machine to interpolate `${...}` variables and is NOT copied into the container image (`.dockerignore`). Any environment variable required by the application inside the container must be explicitly declared and forwarded under `services.web.environment` in `docker-compose.yml`. This requirement is verified by `tests/core/test_compose_env_forwarding.py`.

Other configuration variables have built-in defaults in `docker-compose.yml`, so a minimal `.env` file containing only the required variables is sufficient.

#### 2. Start all services

Build images and launch all services:

```bash
# Build images and start services in the foreground:
docker compose up --build

# Or build images and start in detached mode:
docker compose up --build -d
```

*Security note*: Host ports are bound exclusively to the loopback interface `127.0.0.1` (`127.0.0.1:${WEB_PORT:-8000}` and `127.0.0.1:${POSTGRES_PORT:-5432}`).

#### 3. Seed sample data and set credentials

By default, `LOAD_SAMPLE_DATA` is set to `0` to prevent overwriting existing data. To automatically seed sample data on container startup, set `LOAD_SAMPLE_DATA=1` in `.env` or start with:

```bash
# On Linux / macOS:
LOAD_SAMPLE_DATA=1 docker compose up --build

# On Windows (PowerShell):
$env:LOAD_SAMPLE_DATA="1"; docker compose up --build
```

Alternatively, seed sample data manually while containers are running:

```bash
docker compose exec web python manage.py load_sample_data
```

*Production note*: In production (`DEBUG=False`), `load_sample_data` is blocked to prevent accidental data contamination unless the `--force-production` flag is explicitly provided.

Sample accounts loaded from `db/02-seed.sql` do not contain usable passwords (password hashes use the unusable prefix `!`). Set account passwords using `set_account_password` (passwords are read securely from an interactive prompt or from the `ACCOUNT_PASSWORD` environment variable, never passed via command-line arguments):

```bash
# Interactive password entry via prompt:
docker compose exec web python manage.py set_account_password --identifier hoang.dinh.khang@example.com

# Or pass password via ACCOUNT_PASSWORD environment variable:
docker compose exec -e ACCOUNT_PASSWORD="NewPassword123!" web python manage.py set_account_password --identifier hoang.dinh.khang@example.com
```

Sample test accounts extracted from `db/02-seed.sql`:

| Role | Email | Phone |
|---|---|---|
| `MANAGER` | `hoang.dinh.khang@example.com` | `0880721788` |
| `EMPLOYEE` | `luong.mai.phuong@example.org` | `0385211625` |
| `CUSTOMER` | `trinh.xuan.truong@example.com` | `0868851325` |

#### 4. Stop and update configuration

To stop services while preserving database volume data:

```bash
docker compose stop
```

- **Data loss warning**: Running `docker compose down -v` permanently deletes the database volume `parking_postgres_data`. Use `docker compose down` (without the `-v` flag) to preserve persistent data.
- **Password changes**: Modifying `POSTGRES_PASSWORD` in `.env` after the database volume has already been initialized does not update the password inside PostgreSQL (causing authentication failures). Retain the initial password or remove the development volume to reinitialize from scratch.
- **Environment updates**: After editing `.env`, run `docker compose up -d` to apply updated environment settings without rebuilding images (`--build`).
- **Forwarding new variables**: Any new environment variable required by the web container must be declared under `services.web.environment` in `docker-compose.yml`.

---

### Option 2: run with Python and a locally installed PostgreSQL (no Docker)

<!-- cspell:ignore createdb -->
<!-- cspell:ignore NOSUPERUSER -->

Run the application directly on a workstation with local Python and PostgreSQL installations.

#### 1. Prerequisites

- Python 3.14.7 (Python 3.15 is unsupported). Note: The codebase uses PEP 758 `except A, B:` syntax and therefore needs Python 3.14.7 (older interpreters fail with a SyntaxError).
- PostgreSQL 18.x from postgresql.org (Windows installer includes pgAdmin 4 GUI and contrib extensions). *(not verified: Windows native MSI installer and pgAdmin 4 GUI)*

#### 2. Provision database and user role via pgAdmin

Open pgAdmin 4, connect to the database server using the administrative `postgres` account, open the **Query Tool**, and execute:

```sql
CREATE ROLE parking_user WITH LOGIN CREATEDB PASSWORD 'your_password_here';
CREATE DATABASE parking_db OWNER parking_user ENCODING 'UTF8';
```

*Note*: The `CREATEDB` privilege is required for the automated test suite (`pytest`) to create and tear down the transient `test_parking_db` database.

*PostgreSQL Extensions*: The database schema requires two extensions: `btree_gist` and `pg_trgm`. In standard PostgreSQL 18 (and versions 13+ from postgresql.org), both extensions are trusted (`trusted = true`), allowing the database owner (`parking_user`) to create them automatically during `python manage.py migrate` without superuser privileges. On custom or hardened PostgreSQL installations where extensions are marked untrusted (`trusted = false`), running `python manage.py migrate` as a non-superuser fails with `permission denied to create extension "btree_gist"`. In addition, running `pytest` also fails when creating the test database because `db/01-schema.sql` issues extension creation statements, and pre-installing extensions in `template1` fails with duplicate object errors since `btree_gist` is created without `IF NOT EXISTS`. Therefore, on untrusted-extension installations, grant superuser privileges to the local development role before running migrations and keep it for the test runner: `ALTER ROLE parking_user WITH SUPERUSER;` (apply on local development workstations only, never in production).

#### 3. Set up Python virtual environment and dependencies

Open a terminal in the project directory:

```bash
git clone https://github.com/quan-ly-bai-dau-xe/parking_management_backend.git
cd parking_management_backend
```

Create and activate a virtual environment:

On Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On Linux / macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install development dependencies:

```bash
pip install -r requirements/02-dev.txt
```

#### 4. Configure local environment variables

Create `.env` from `.env.example`:

```bash
# On Linux / macOS:
cp .env.example .env

# On Windows (PowerShell):
Copy-Item .env.example .env
```

Configure required environment variables in `.env` (including `DEBUG=True`, database connection settings with `POSTGRES_HOST=127.0.0.1`, `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS`):

```env
DEBUG=True
SECRET_KEY=your_secret_key_here
POSTGRES_DB=parking_db
POSTGRES_USER=parking_user
POSTGRES_PASSWORD=your_password_here
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
CLOUDINARY_CLOUD_NAME=your_cloud_name
CLOUDINARY_API_KEY=your_api_key
CLOUDINARY_API_SECRET=your_api_secret
```

`DEBUG=True` is required for development: when `DEBUG=False` (production only), `load_sample_data` is blocked and Swagger UI static CSS/JS assets return 404. While the backend starts with minimal database and secret settings, a browser frontend accessing the API from another origin (such as `http://localhost:3000`) requires `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` in `.env` to prevent HTTP 403 Forbidden CSRF rejection errors (`PROP-4.1-P06`).

Generate a secure random `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

#### 5. Apply migrations, seed data, and set credentials

Apply database schema migrations and load initial sample data:

```bash
python manage.py migrate
python manage.py load_sample_data
```

Sample accounts from `db/02-seed.sql` do not contain usable passwords (password hashes use the unusable prefix `!`). Set account passwords using `set_account_password` (passwords are read securely from an interactive prompt or from the `ACCOUNT_PASSWORD` environment variable, never passed via command-line arguments):

```bash
# Interactive password entry via prompt:
python manage.py set_account_password --identifier hoang.dinh.khang@example.com
```

Or pass the password via `ACCOUNT_PASSWORD` on Windows (PowerShell):

```powershell
$env:ACCOUNT_PASSWORD="NewPassword123!"
python manage.py set_account_password --identifier hoang.dinh.khang@example.com
```

Or on Linux / macOS:

```bash
ACCOUNT_PASSWORD="NewPassword123!" python manage.py set_account_password --identifier hoang.dinh.khang@example.com
```

Sample test accounts extracted from `db/02-seed.sql`:

| Role | Email | Phone |
|---|---|---|
| `MANAGER` | `hoang.dinh.khang@example.com` | `0880721788` |
| `EMPLOYEE` | `luong.mai.phuong@example.org` | `0385211625` |
| `CUSTOMER` | `trinh.xuan.truong@example.com` | `0868851325` |

#### 6. Run development server and tests

Start the Django development server:

```bash
python manage.py runserver
```

Run the automated test suite to confirm end-to-end functionality:

```bash
pytest
```

#### 7. Technical notes

- `DEBUG=True` is required when running with `runserver` so that the development server serves Swagger UI static CSS and JavaScript assets.
- License plate recognition automatically downloads ONNX weight files from the network to `~/.cache` on the first scan request if `PARKING_OCR_MODELS_DIR` does not contain pre-baked weights (refer to `apps/parking/services/ocr.py`), requiring internet connectivity during the initial scan.
- Native Windows PostgreSQL installer, pgAdmin 4 GUI configuration screens, and Windows service (`services.msc`) management are marked as `(not verified)` in automated headless test pipelines.

If you prefer running the backend with Docker, see [Option 1: run with Docker](#option-1-run-with-docker). <!-- closing-docker-pointer -->

---

### Verify the backend and try a login (both options)

After starting the backend using either option, verify operational status and test authentication:

#### 1. Service health check

- **Health Check Endpoint**: Access [http://127.0.0.1:8000/api/health/](http://127.0.0.1:8000/api/health/) (or `/api/v1/health/`).
  - Under Docker with Gunicorn, worker initialization pre-warms OCR models via the `post_fork` hook, returning `{"status": "healthy", "database": "connected", "ocr_ready": true}`.
  - Under `runserver`, OCR models load lazily upon first plate scan, returning `{"status": "healthy", "database": "connected", "ocr_ready": false}` before any scan request (verified: `ocr_ready` remains `false` under `runserver` as model warm-up is managed exclusively via Gunicorn `post_fork` in container deployments).
- **Interactive API Documentation (Swagger UI)**: Access [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/) to view the API catalog and execute requests via "Try it out".
- **ReDoc Documentation**: Access [http://127.0.0.1:8000/api/redoc/](http://127.0.0.1:8000/api/redoc/).
- **OpenAPI Schema**: Access [http://127.0.0.1:8000/api/schema/](http://127.0.0.1:8000/api/schema/).

#### 2. CSRF authentication and login flow

The backend protects session authentication with Double-Submit Cookie CSRF defense:

- **Authoritative Login URL**: `/api/v1/auth/login/` (must include the `/auth/` subpath).

**Step 1 — Retrieve CSRF Cookie**: Send a `GET` request to `/api/v1/auth/csrf/`:

```http
GET /api/v1/auth/csrf/ HTTP/1.1
Host: 127.0.0.1:8000
```

The response sets the `csrftoken` cookie in the browser or HTTP client.

**Step 2 — Submit Login Request**: Send a `POST` request to `/api/v1/auth/login/` with the CSRF token in the `X-CSRFToken` header:

```http
POST /api/v1/auth/login/ HTTP/1.1
Host: 127.0.0.1:8000
Content-Type: application/json
X-CSRFToken: <received_csrftoken_value>
Origin: http://localhost:3000

{
  "identifier": "hoang.dinh.khang@example.com",
  "password": "NewPassword123!",
  "remember": false
}
```

Upon successful authentication, the server responds with HTTP `200 OK`, returning user profile details and setting the authenticated `sessionid` session cookie.

#### 3. Frontend integration notes

- **Frontend Integration Guide**: For comprehensive integration patterns, see [`docs/guides/01-frontend-api-guide.md`](docs/guides/01-frontend-api-guide.md).
- **Security & Authentication Architecture**: See [Step 8: Interactive API Documentation, CSRF & Swagger "Try it out"](#step-8-interactive-api-documentation-csrf--swagger-try-it-out) for detailed cookie security, Argon2 password hashing, and token rotation specifications.
- **Same Host Requirement**: Run the frontend and backend on the same host name (`127.0.0.1` or `localhost`) during local development to avoid cross-site cookie restrictions in modern browsers.
- **Trusted Origins**: Default CORS and CSRF configurations (`CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS`) permit cross-origin requests from `http://localhost:3000` and `http://127.0.0.1:3000`.

---

### Environment variables

Key environment variables:

- `SECRET_KEY`: Django secret key (required).
- `POSTGRES_PASSWORD`: PostgreSQL database password (required).
- `CLOUDINARY_CLOUD_NAME`: Cloudinary cloud name for scan image storage (required; halts startup if unset).
- `CLOUDINARY_API_KEY`: Cloudinary API key (required; halts startup if unset).
- `CLOUDINARY_API_SECRET`: Cloudinary API secret (required; halts startup if unset).
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

### Troubleshooting

#### Table 1: Troubleshooting Option 1 (Docker)

| Error Symptom | Root Cause | Remediation |
|---|---|---|
| `bind: address already in use` | Host port 8000 or 5432 is occupied by another local process. | Change `WEB_PORT` or `POSTGRES_PORT` to an available port in `.env` (e.g., `WEB_PORT=8015`, `POSTGRES_PORT=5445`). |
| `FATAL: password authentication failed` | `POSTGRES_PASSWORD` was changed in `.env` after the database volume was already initialized. | Restore the original password in `.env`, update the password in PostgreSQL via `ALTER ROLE`, or recreate the volume in development. |
| New variables in `.env` have no effect | The variable was not forwarded into the container. | Declare the variable under `services.web.environment` in `docker-compose.yml`. |
| Missing required variables when running compose | `SECRET_KEY`, `POSTGRES_PASSWORD`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, or `CLOUDINARY_API_SECRET` is not set. | Provide values for all required variables in `.env`. |

#### Table 2: Troubleshooting Option 2 (Local Python & PostgreSQL)

| Error Symptom | Root Cause | Remediation |
|---|---|---|
| `connection to server at "127.0.0.1", port 5432 failed` | Local PostgreSQL service is not running. | Verify PostgreSQL service status in Windows Services (`services.msc`) or run `sudo systemctl start postgresql` on Linux. |
| `permission denied to create database` during `pytest` | Role `parking_user` lacks the `CREATEDB` attribute. | Connect via pgAdmin as `postgres` and execute `ALTER ROLE parking_user CREATEDB;`. |
| Swagger UI missing CSS/JS styling | Development server started with `DEBUG=False`. | Set `DEBUG=True` in `.env` so Django serves static assets in development. |
| First license plate scan is slow or fails | OCR engine is downloading ONNX weights to `~/.cache`. | Ensure active internet connectivity during the first plate scan request. |
| `ImproperlyConfigured: Missing required Cloudinary environment variables` | `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, or `CLOUDINARY_API_SECRET` is unset in `.env`. | Configure Cloudinary credentials in `.env`. |

---

### Step 8: Interactive API Documentation, CSRF & Swagger "Try it out"

Access the interactive API documentation and health endpoints:

- **Swagger UI**: [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)
- **ReDoc**: [http://127.0.0.1:8000/api/redoc/](http://127.0.0.1:8000/api/redoc/)
- **OpenAPI 3.0 Schema**: [http://127.0.0.1:8000/api/schema/](http://127.0.0.1:8000/api/schema/)
- **System Health Check**: [http://127.0.0.1:8000/api/health/](http://127.0.0.1:8000/api/health/)
- **Frontend API Integration Guide**: [`docs/guides/01-frontend-api-guide.md`](docs/guides/01-frontend-api-guide.md)

#### 3.8.1 Authentication & Session Architecture (TL-52, ADR-0004)

The backend provides stateful session authentication with OWASP persistent login token rotation and Argon2 password hashing under `/api/v1/auth/`:

| Endpoint | Method | Access | Description & Request/Response Summary |
|---|:---:|:---:|---|
| `/api/v1/auth/csrf/` | `GET` | Public (`AllowAny`) | Bootstraps the double-submit CSRF cookie (`csrftoken`, `SameSite=Lax`, `HttpOnly=False`) required for SPA mutation handshakes. Returns `{"detail": "Khởi tạo cookie CSRF thành công."}` per catalog `PROP-4.1-P02`. |
| `/api/v1/auth/login/` | `POST` | Public (`AllowAny`) | Authenticates via case-insensitive `email` (using `lower(email)` partial index) or normalized `phone` (`^[0-9]{9,15}$`) and `password`. Mandatory CSRF token enforcement via `X-CSRFToken` header. Issues a browser-session `sessionid` cookie (no `Max-Age` / `Expires`, bounded by `SESSION_COOKIE_AGE=43200` on the server). Supports optional `remember: true` issuing a persistent cookie (`parking_remember_token`, default 30 days via `REMEMBER_TOKEN_LIFETIME_DAYS`). Protected by atomic reserve-then-verify rate limiting. |
| `/api/v1/auth/logout/` | `POST` | Authenticated / Public | Flushes the Django session, revokes the presented remember-me token series via plain `DELETE` (`TL-36`), and sets clearing expiration headers for `sessionid` and `parking_remember_token` cookies. Mandatory CSRF token enforcement. Returns `{"detail": "Đăng xuất thành công."}` per catalog `PROP-4.1-P03`. |
| `/api/v1/auth/me/` | `GET` | `IsAuthenticated` | Returns authenticated account profile `{"id": ..., "email": "...", "phone": "...", "role": "..."}`. Unauthenticated requests without session automatically authenticate if a valid `parking_remember_token` cookie is present; otherwise returns the standard JSON error envelope (`MSG-4.1-M02`). |

#### 3.8.2 Security Baseline & Password Hashing (Argon2)

- **Argon2 Primary Hasher**: Configured as the primary password hasher in `config/settings/base.py` via Django's `Argon2PasswordHasher` backed by `argon2-cffi` (`m=102400, t=2, p=8`), with `PBKDF2PasswordHasher` fallback. Fast hashers (`PBKDF2PasswordHasher`, `PBKDF2SHA1PasswordHasher`, `Argon2PasswordHasher`) are configured exclusively in `config/settings/test.py` to preserve test runner velocity.
- **Anti-Timing Defense**: Non-existent accounts execute a module-level pre-computed dummy password hash check, eliminating CPU timing side-channels between valid and invalid identifiers.
- **Persistent Token Rotation Grace Window (OQ-87)**: Mitigates SPA parallel request race conditions at boot. Rotation state is stored directly in PostgreSQL via a composite hash string `f"{current_hash}:{previous_hash}"` in `persistent_login_token.token_hash VARCHAR(255)`. Requests arriving within the grace window (`REMEMBER_ROTATION_GRACE_SECONDS`, default 30s) skip rotation or accept the previous hash, preventing false-positive session revocations. Transient database errors (`django.db.Error`) preserve existing tokens and cookies without revoking the session.
- **0-Query Middleware Invariant**: `PersistentRememberMeMiddleware` checks `request.COOKIES` in memory before evaluating `request.user`, guaranteeing zero SQL queries (`assertNumQueries(0)`) on standard traffic without remember cookies.
- **Atomic Reserve-then-Verify Login Rate Limiting (`LoginAttemptLimiter`)**: Protects authentication endpoints against parallel brute-force attacks across three quota tiers: (1) normalized identifier and client IP pair (`AUTH_THROTTLE_PAIR_LIMIT`, default 5 attempts / 15m), (2) per-identifier ceiling (`AUTH_THROTTLE_IDENTIFIER_LIMIT`, default 20 attempts / 15m), and (3) per-IP failure ceiling (`AUTH_THROTTLE_IP_LIMIT`, default 30 attempts / 15m). Window is configured via `AUTH_THROTTLE_WINDOW_SECONDS` (default 900s). Counters track in-flight and failed attempts only; successful logins release their reservation, preventing false-positive lockouts on shared corporate networks. Client IP extraction respects DRF `NUM_PROXIES` semantics (default 0; behind a reverse proxy the operator MUST configure `NUM_PROXIES` or all clients share a single IP bucket, marked `UNVERIFIED-for-production`). When using the default in-memory `LocMemCache` in a multi-worker environment (e.g. 4 Gunicorn workers), cache counters are process-local, allowing up to 4x total attempts across distinct workers before all buckets saturate. A shared distributed cache such as Redis (`django-redis`) is recommended for production environments (marked `UNVERIFIED-for-production`; requires ADR and Owner approval).

#### 3.8.3 Authentication Management Commands

##### 1. Set Account Password (`set_account_password`)

Safely sets or updates the Argon2 password for any active `Account` record. Passwords are never accepted via command-line arguments to prevent shell history leaks:

```bash
# Option A: Set via environment variable (ideal for automated setup or scripts):
ACCOUNT_PASSWORD="StrongPassword123!" python manage.py set_account_password --identifier hoang.dinh.khang@example.com

# Or inside Docker web container:
docker compose exec -e ACCOUNT_PASSWORD="StrongPassword123!" web python manage.py set_account_password --identifier hoang.dinh.khang@example.com

# Option B: Set via interactive hidden prompt (no echo to terminal):
python manage.py set_account_password --identifier 0880721788
```

##### 2. Purge Expired Login Tokens (`purge_expired_login_tokens`)

Performs maintenance cleanup of expired tokens from the `persistent_login_token` table (`TL-36` plain DELETE):

```bash
# 1. Dry-run inspection (default, counts expired tokens without deleting):
python manage.py purge_expired_login_tokens

# Or inside Docker web container:
docker compose exec web python manage.py purge_expired_login_tokens

# 2. Execute actual deletion of expired tokens:
python manage.py purge_expired_login_tokens --no-dry-run

# Or inside Docker web container:
docker compose exec web python manage.py purge_expired_login_tokens --no-dry-run
```

#### 3.8.4 Session Authentication & CSRF Handling

The backend implements `SessionAuthentication` per ADR-0004. In addition to standard protected endpoints, mutating authentication endpoints (`POST /api/v1/auth/login/` and `POST /api/v1/auth/logout/`) enforce CSRF validation for both anonymous and authenticated callers via `@method_decorator(csrf_protect)`:

1. The client must obtain the `csrftoken` cookie by invoking `GET /api/v1/auth/csrf/`.
2. The client must include the **`X-CSRFToken`** header matching the cookie on mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`).
3. If CSRF validation fails, `CSRF_FAILURE_VIEW` (`apps.accounts.views.csrf.custom_csrf_failure_view`) returns HTTP 403 Forbidden with the standard JSON error envelope (`PROP-4.1-P06`: `"Mã CSRF không hợp lệ hoặc bị thiếu."`) instead of Django's default HTML 403 page.
4. For protected business endpoints, the client must supply an active `sessionid` cookie along with the matching `X-CSRFToken` header.

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
- **Cloudinary Storage Hygiene (K7, ADR-0010)**: Parking scans are stored exclusively in Cloudinary with zero local disk writes, ensuring load tests and benchmarks never accumulate media files on local storage.
- **Fail-Fast Error Accounting (H8c)**: Fatal errors (`500 Internal Server Error`, connection drops, or unexpected status codes outside `--allow-status`) are counted and reported. The process exits with code `1` upon any unexpected failure.
- **Circuit Breaker Validation**: Tests backend under heavy concurrency (`32` to `64` concurrent workers) while verifying semaphore admission (`503 Service Unavailable` with `Retry-After`) under saturation.

#### Running Soak & Concurrency Tests

```bash
# 1. Full benchmark suite across all scenarios at concurrency 32 and 64:
python tests/perf/load_test.py --duration 10

# 2. High-concurrency 180-second soak test (64 clients for 180 seconds):
python tests/perf/load_test.py --concurrency 64 --duration 180 --scenario lookup

# 3. Targeted 12 MP cold-start vs. warm-state burst test (K2):
python tests/perf/load_test.py --concurrency 32,64 --duration 10 --scenario scan_12mp --warmup
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
  - `write`: Image upload to Cloudinary folder `parking_scans/YYYY/MM/DD/`.
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

- **Developer & Integration Guides**:
  - [`docs/guides/01-frontend-api-guide.md`](docs/guides/01-frontend-api-guide.md) — Comprehensive Frontend API Integration Guide (Authentication, Session/CSRF, OCR Plate Scan, Check-in/Check-out, Error Envelopes, and TypeScript Type Generation).
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
