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
- **Specification Hierarchy**: The Frontend UI design ([`docs/requirements/06-frontend-srs-db-alignment.md`](docs/requirements/06-frontend-srs-db-alignment.md), `TL-01`–`TL-49`) serves as the **primary** specification; the SRS v4.1 catalog ([`docs/requirements/00-srs-catalog.md`](docs/requirements/00-srs-catalog.md)) is **secondary** where frontend screens are silent.
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

*Note*: Ensure `SECRET_KEY`, `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` match your local development environment.

### Step 2: Start PostgreSQL 18.6 Database

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

### Step 8: Interactive API Documentation & Health Check

Access the interactive API documentation and health endpoints:

- **Swagger UI**: [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)
- **ReDoc**: [http://127.0.0.1:8000/api/redoc/](http://127.0.0.1:8000/api/redoc/)
- **OpenAPI 3.0 Schema**: [http://127.0.0.1:8000/api/schema/](http://127.0.0.1:8000/api/schema/)
- **System Health Check**: [http://127.0.0.1:8000/api/health/](http://127.0.0.1:8000/api/health/)

### Step 9: Run Automated Test Suite

Execute the full automated test suite with coverage against live PostgreSQL 18.6:

```bash
pytest -v --cov=apps
```

*Threshold*: All tests must pass with line coverage enforced at `>= 80%` (current baseline: `55` passed, `92.87%` coverage).

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
  - [`docs/requirements/06-frontend-srs-db-alignment.md`](docs/requirements/06-frontend-srs-db-alignment.md) — Primary FE-first decisions (`TL-01`–`TL-49`).
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
- **AI Operating System**:
  - [`.claude/rules/`](.claude/rules/) — Numbered enterprise rules (`01`–`10`).
  - [`.claude/skills/`](.claude/skills/) — Numbered specialized skills (`01`–`13`).
  - [`CLAUDE.md`](CLAUDE.md) — Project context for AI coding assistants.

---

## 6. Governance & License

- **License**: All Rights Reserved. (No open-source license granted).
- **Vulnerability Reporting**: Strictly via GitHub Private Vulnerability Reporting. See [SECURITY.md](SECURITY.md).
