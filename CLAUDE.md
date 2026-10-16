# CLAUDE.md — Car Parking Lot Management System Backend

Project guidance and architectural pointers for AI assistants in `parking_management_backend`.

## 1. Project Boundaries & Public Repo Scope

- **Scope**: Backend REST API only (Django 6.1.2 + PostgreSQL 18.6 + DRF 3.18.3). Frontend is out of scope.
- **Contract Interface**: OpenAPI 3.0 specification (`drf-spectacular`).
- **Public Repo Discipline**: Zero secrets, zero live credentials. Verify exclusions with `git check-ignore -v`.
- **Single Source of Truth**: All requirements and messages derive from `docs/requirements/00-srs-catalog.md`.

## 2. Technology Stack & Planned Commands

- **Runtime & DB**: Python `3.14.7` (3.15 forbidden), Django `6.1.2` (ADR-0001), PostgreSQL `18.6` (ADR-0005).
- **Core Commands**:
  - `docker compose up -d db` (Start PostgreSQL 18.6 container)
  - `ruff check .` / `ruff format --check .` (Linting & formatting)
  - `mypy .` (Type checking)
  - `pytest` (Automated testing with >= 80% coverage)

## 3. Architecture Pointers

- **3-Tier Django Pattern**: Thin `views/` -> Transactional `services/` -> Read-optimized `selectors/`.
- **Safe Delete Policy ([ADR-0003](docs/adr/0003-data-deletion-soft-delete-protect-and-audit.md))**:
  - Soft delete by default (`SafeDeleteModel`). Hard row deletion is banned.
  - `on_delete=models.PROTECT` blocks hard delete; service guards validate before setting `deleted_at`.
  - Financial records (`Ticket`, `VehicleEntryExitLog`) are immutable. Concurrency via `select_for_update()`.

## 4. Documentation Index

- **Requirements (`docs/requirements/`)**: `00-srs-catalog.md`, `01-open-questions.md`, `02-scope-additions-from-plan.md`, `03-delete-rules-catalog.md`, `04-dod-and-quality-check.md`, `05-proposed-messages.md`.
- **ADRs (`docs/adr/`)**: `0001-fixed-tech-stack-and-lts-roadmap.md`, `0002-git-branching-and-collaboration-workflow.md`, `0003-data-deletion-soft-delete-protect-and-audit.md`, `0004-authentication-session-and-remember-token.md`, `0005-local-docker-compose-for-postgresql.md`.
- **AI Rules (`.claude/rules/`)**: `01` to `09` (Numbered, imperative, testable).

## 5. AI Engineering Constraints & Safety

- **Evidence-Based Loop**: Follow `Study Deeply -> Parallel Research -> Best Solution -> Real Test`. Tasks are only complete when supported by raw terminal execution evidence. Never use dummy facades.
- **Safety Net Disclosure**: Permission rules in `.claude/settings.json` (`deny`/`ask`) serve as a local defensive safety net, not an absolute guarantee. Authoritative protection is enforced by GitHub push protection, branch protection rules, and human peer review.
- **Git Write Governance**: AI agents must NEVER execute git write operations (`add`, `commit`, `push`, `merge`, `rebase`, `tag`, `reset`, branch changes) without explicit human approval (enforced via `ask` list).
