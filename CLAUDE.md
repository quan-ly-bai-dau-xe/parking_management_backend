# CLAUDE.md — Car Parking Lot Management System Backend

Project guidance and architectural pointers for AI assistants in `parking_management_backend`.

## 1. Project Boundaries & Public Repo Scope

- **Scope**: Backend REST API only (Django 6.1.2 + PostgreSQL 18.6 + DRF 3.18.3). Frontend is out of scope.
- **Contract Interface**: OpenAPI 3.0 specification (`drf-spectacular` per ADR-0001).
- **Public Repo Discipline**: Zero secrets, zero live credentials. Verify exclusions with `git check-ignore -v`.
- **Source of Truth Hierarchy**: The Frontend design (`docs/requirements/06-frontend-srs-db-alignment.md`, `TL-01`–`TL-35`) is the **primary** source of requirements; the SRS catalog (`docs/requirements/00-srs-catalog.md`) is **secondary** where the Frontend is silent.

## 2. Technology Stack & Planned Commands

- **Runtime & DB**: Python `3.14.7` (3.15 forbidden), Django `6.1.2` (ADR-0001), PostgreSQL `18.6` (ADR-0005; Schema v2 in `db/01-schema.sql` with `28` base tables, `8` views, `69` `ON DELETE RESTRICT` FKs, `88` triggers).
- **Core Commands**:
  - `docker compose up -d db` (Start PostgreSQL 18.6 container)
  - `ruff check .` / `ruff format --check .` (Linting & formatting)
  - `mypy .` (Type checking)
  - `pytest` (Automated testing with >= 80% coverage)

## 3. Architecture Pointers

- **3-Tier Django Pattern**: Thin `views/` -> Transactional `services/` -> Read-optimized `selectors/`.
- **Safe Delete Policy ([ADR-0003](docs/adr/0003-data-deletion-soft-delete-protect-and-audit.md) & TL-23..TL-27)**:
  - Soft delete by default (`SafeDeleteModel`), exposed as `isDeleted: bool` at serializer layer (TL-23). Hard row deletion is banned via `BEFORE DELETE` database triggers (TL-24).
  - Database triggers `BEFORE UPDATE OF deleted_at` enforce domain guards (TL-25); guarded restore checks active parents (TL-26); periodic controlled purge via `SECURITY DEFINER` (`fn_controlled_purge()`, TL-24).
  - Financial and operational audit records (`ticket`, `ticket_renewal`, `vehicle_entry_exit_log`, `payment`, `activity_log`, `system_alert`) cannot be purged (`TL-24`). Concurrency via `select_for_update()` and `row_version`.

## 4. Documentation Index

- **Requirements (`docs/requirements/`)**: `06-frontend-srs-db-alignment.md` (primary FE-first decision record), `07-fe-srs-traceability.md` (FE + SRS traceability matrix & `TL-28` SQL queries), `00-srs-catalog.md` (secondary SRS catalog), `01-decision-log.md`, `02-scope-additions-from-plan.md`, `03-delete-rules-catalog.md`, `04-dod-and-quality-check.md`, `05-proposed-messages.md`.
- **Database (`db/`)**: `00-README.md`, `01-schema.sql`, `02-seed.sql`, `03-erd.asta`, and `04`–`09` ERD PNGs.
- **ADRs (`docs/adr/`)**: `0001-fixed-tech-stack-and-lts-roadmap.md`, `0002-git-branching-and-collaboration-workflow.md`, `0003-data-deletion-soft-delete-protect-and-audit.md`, `0004-authentication-session-and-remember-token.md`, `0005-local-docker-compose-for-postgresql.md`.
- **AI Rules (`.claude/rules/`)**: `01` to `10` (Numbered, imperative, testable; includes `10-team-collaboration-and-code-ownership.md`).
- **AI Skills (`.claude/skills/`)**: `01` to `13` (Domain procedures; includes `12-trash-restore-and-purge-lifecycle` and `13-api-first-contract-and-mock-data`).

## 5. AI Engineering Constraints & Safety

- **Evidence-Based Loop**: Follow `Study Deeply -> Parallel Research -> Best Solution -> Real Test`. Tasks are only complete when supported by raw terminal execution evidence. Never use dummy facades.
- **Safety Net Disclosure**: Permission rules in `.claude/settings.json` (`deny`/`ask`) serve as a local defensive safety net, not an absolute guarantee. Authoritative protection is enforced by GitHub push protection, branch protection rules, and human peer review.
- **Git Write Governance**: AI agents must NEVER execute git write operations (`add`, `commit`, `push`, `merge`, `rebase`, `tag`, `reset`, branch changes) without explicit human approval (enforced via `ask` list).
