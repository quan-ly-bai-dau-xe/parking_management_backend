# Car Parking Lot Management System Backend

Intelligent Parking Lot Management System (`Bãi xe Smart Mobility`) — Backend REST API.

[![Python 3.14.7](https://img.shields.io/badge/python-3.14.7-blue.svg)](https://www.python.org/downloads/)
[![Django 6.1.2](https://img.shields.io/badge/django-6.1.2-green.svg)](https://www.djangoproject.com/)
[![PostgreSQL 18.6](https://img.shields.io/badge/postgresql-18.6-blue.svg)](https://www.postgresql.org/)

## 1. Project Overview & Scope

- **Scope**: Backend REST API only (`parking_management_backend`). Client apps integrate via OpenAPI 3.0.
- **Specification Hierarchy**: The Frontend design (`docs/requirements/06-frontend-srs-db-alignment.md`, `TL-01`–`TL-22`) is the **primary** source of requirements; the SRS v4.1 catalog (`docs/requirements/00-srs-catalog.md`) is **secondary** where the Frontend is silent.
- **Fixed Tech Stack**: Python `3.14.7` (3.15 forbidden), Django `6.1.2` (LTS roadmap to 6.2 in April 2027), DRF `3.18.3`, PostgreSQL `18.6` via Docker Compose (psycopg `3.3.6`). Details in [ADR-0001](docs/adr/0001-fixed-tech-stack-and-lts-roadmap.md).
- **Database Schema v2 (`db/`)**: `28` base tables, `8` analytical views, `69` `ON DELETE RESTRICT` foreign keys, and `25` triggers documented in [`db/00-README.md`](db/00-README.md).
- **Public Repo Security**: Zero secrets, zero production tokens, zero live credentials.

## 2. Architecture & Data Safety

- **3-Tier Django Architecture**:
  - `views/`: Thin API endpoints handling HTTP, permissions, and serialization.
  - `services/`: Write business logic, transactional boundaries (`@transaction.atomic`), safe-delete guards.
  - `selectors/`: Read-only queries with `select_related()` / `prefetch_related()`.
- **Safe Data Deletion ([ADR-0003](docs/adr/0003-data-deletion-soft-delete-protect-and-audit.md))**:
  - Soft delete by default (`deleted_at`, `deleted_by`) on business models. Hard deletion is prohibited.
  - `on_delete=models.PROTECT` on foreign keys prevents physical hard deletion; service guards prevent soft delete if active relations exist.
  - Financial and operational audit records (`Ticket`, `TicketRenewal`, `VehicleEntryExitLog`, `Payment`, `ActivityLog`) are protected by immutability / soft-delete guards.
  - Concurrency control via pessimistic row locking (`select_for_update()`) and optimistic concurrency (`row_version`).

## 3. Quick Start (Development)

1. **Environment Config**: Copy template: `cp .env.example .env` (fill in local variables).
2. **Start Database (PostgreSQL 18.6)**:

   ```bash
   docker compose up -d db
   ```

   *Note*: Binds to `127.0.0.1:${POSTGRES_PORT:-5432}`. Data volume `parking_postgres_data` mounts at `/var/lib/postgresql`.
3. **Application Development (Planned)**:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements/dev.txt
   python manage.py migrate
   pytest
   ```

## 4. Documentation & AI Operating System

- **Requirements**: [`docs/requirements/`](docs/requirements/) (`06-frontend-srs-db-alignment.md` primary FE-first decisions, `00-srs-catalog.md` secondary SRS catalog, `01-decision-log.md` decision log, DoD).
- **Database**: [`db/00-README.md`](db/00-README.md), [`db/01-schema.sql`](db/01-schema.sql), [`db/02-seed.sql`](db/02-seed.sql).
- **Architecture Decision Records**: [`docs/adr/`](docs/adr/) (0001 to 0005).
- **Claude Code AI Rules**: [`.claude/rules/`](.claude/rules/) (01 to 09) and [`CLAUDE.md`](CLAUDE.md).

## 5. Governance & License

- **License**: All Rights Reserved. (No open-source license granted).
- **Vulnerability Reporting**: Strictly via GitHub Private Vulnerability Reporting. See [SECURITY.md](SECURITY.md).
