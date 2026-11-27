# Contributing to parking_management_backend

This document defines the contribution workflow, code ownership rules, data
safety policies, and automated quality gates for `parking_management_backend`.

## Table of contents

- [1. Scope and who contributes](#1-scope-and-who-contributes)
- [2. Getting started](#2-getting-started)
- [3. Branch naming and workflow](#3-branch-naming-and-workflow)
- [4. Commit messages](#4-commit-messages)
- [5. Tests and quality gates](#5-tests-and-quality-gates)
- [6. Pull request process](#6-pull-request-process)
- [7. Code ownership and collaboration](#7-code-ownership-and-collaboration)
- [8. Data deletion policy](#8-data-deletion-policy)
- [9. Secrets and personal data](#9-secrets-and-personal-data)
- [10. Documentation language](#10-documentation-language)
- [11. Where to ask questions](#11-where-to-ask-questions)
- [12. Related policies](#12-related-policies)

## 1. Scope and who contributes

This repository is a team-maintained backend REST API for car parking lot
management. Outside contributors must open an issue first using one of the
repository issue forms to discuss scope and alignment before starting a pull
request.

## 2. Getting started

Follow the setup instructions in the
[README Quick Start](README.md#3-quick-start-development--operations) for
Docker Compose and local Python/PostgreSQL development, database migrations,
sample data loading, and environment variables. Setup steps are maintained in
one place in `README.md` and are not duplicated here.

## 3. Branch naming and workflow

Branching and integration follow
[ADR-0002](docs/adr/0002-git-branching-and-collaboration-workflow.md):

- **`main` (protected release)**: Production-ready code, merged exclusively
  from `dev` by the Tech Lead. Direct pushes are blocked.
- **`dev` (protected integration)**: Active integration branch. Split all
  development branches from `dev`, and target `dev` in all development pull
  requests.
- **Branch naming**:
  - `feature/<issue-id>-<short-description>` for new features or enhancements.
  - `bugfix/<issue-id>-<short-description>` for defect fixes.
  - `hotfix/<issue-id>-<short-description>` split from `main` only for critical
    production fixes.
- **Merge strategy**: Pull requests merge into `dev` via merge commit
  (`--no-ff`). Squash and rebase merges are disabled so commit provenance is
  preserved.

## 4. Commit messages

Commit messages follow Conventional Commits v1.0.0 in English using the
imperative mood, as specified in
[ADR-0002](docs/adr/0002-git-branching-and-collaboration-workflow.md):

```text
<type>(<scope>): <subject>
```

- **Supported types**: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`,
  `build`, `ci`, `chore`.
- **Examples from ADR-0002**:
  - `feat(ticket): add soft delete endpoint`
  - `fix(auth): enforce argon2`

## 5. Tests and quality gates

Run and pass every quality gate before opening or updating a pull request:

```bash
# 1. Python linting
ruff check .

# 2. Code formatting check
ruff format --check .

# 3. Static type checking (django-stubs)
mypy .

# 4. Uncommitted migration check
python manage.py makemigrations --check --dry-run

# 5. OpenAPI 3.0 contract validation
python manage.py spectacular --validate --fail-on-warn

# 6. Automated test suite with line coverage >= 80%
pytest --cov=apps --cov-report=term-missing --cov-fail-under=80
```

`pyproject.toml` configures `pytest` with `--cov=apps` and
`--cov-fail-under=80` by default, so running `pytest` enforces the minimum 80%
coverage threshold across `apps/`.

## 6. Pull request process

1. Branch from `dev` using the naming format in section 3.
2. Keep changes minimal, focused on the linked issue, and compliant with all
   quality gates in section 5.
3. Open a pull request into `dev` and complete every section of
   [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md):
   - Explain the architectural rationale (why the change is needed, not only
     what changed) and link the issue (`Closes #<id>`).
   - Complete the **Destructive Operations & Delete Policy Checklist** (Safe
     Delete checklist) whenever models, migrations, views, or services are
     touched.
   - Complete the **Definition of Done (DoD) Checklist**.
   - Paste raw terminal output from `pytest`, `ruff`, and `mypy`.
4. Obtain at least 1 approving peer review and ensure all CI workflows
   (`01-db-schema-check.yml` and `02-django-check.yml`) pass before merge.

## 7. Code ownership and collaboration

- **Shared areas**: Core configuration (`config/`), database schema and seed
  scripts (`db/`), shared base models, middlewares, common serializers, and CI
  workflows (`.github/`) affect the entire team. Discuss changes to shared
  areas with the team beforehand and obtain peer review approval.
- **Assigned feature areas**: Feature branches and assigned module tasks belong
  to their designated author, subject to shared API contracts and database
  constraints.
- **Read, understand, and ask first**: Do not modify, refactor, or remove
  another contributor's code, schema, or tests without reading its design
  context and coordinating with the author first. Never push directly to
  another contributor's branch without explicit agreement.
- Automated tooling and coding assistants follow the same workflow, ownership
  boundaries, and quality gates.

## 8. Data deletion policy

Physical row deletion (`DELETE FROM`) is prohibited in application code and
blocked by PostgreSQL triggers on 25 of the 28 base tables; the three
exceptions are `persistent_login_token`, `password_reset_token` and
`slot_allowed_vehicle_type`. Follow
[ADR-0003](docs/adr/0003-data-deletion-soft-delete-protect-and-audit.md) and
[`docs/requirements/03-delete-rules-catalog.md`](docs/requirements/03-delete-rules-catalog.md):

- **Soft delete only**: Deletable entities record `deleted_at` and `deleted_by`
  and expose computed `isDeleted: bool` at the API boundary.
- **Referential integrity**: Foreign keys to business entities use
  `on_delete=models.PROTECT` (`ON DELETE RESTRICT`); `CASCADE` and `SET NULL`
  are not permitted.
- **Partial unique indexes**: Active uniqueness constraints scope with
  `WHERE deleted_at IS NULL`.
- **Concurrency safety**: Soft-delete services lock rows with
  `select_for_update()` inside `transaction.atomic()` and honor `row_version`
  optimistic concurrency control.
- **Immutable records**: Financial, gate session, and audit tables (`ticket`,
  `ticket_renewal`, `payment`, `vehicle_entry_exit_log`, `activity_log`,
  `system_alert`) are never deleted or purged.

## 9. Secrets and personal data

- **No secrets**: Never commit `.env` files, passwords, secret keys, API keys,
  session cookies, or tokens.
- **No real plates or personal data**: Never commit or paste real vehicle
  license plates, real citizen ID numbers (CCCD/CMND), real phone numbers, real
  customer names, or production data dumps in code, tests, fixtures,
  documentation, pull requests, or issues. Use synthetic test data only.
- **Privacy compliance**: Customer erasure requests under Decree 13/2023/ND-CP
  are handled through PII anonymization (`is_anonymized = TRUE`), never hard
  row deletion.

## 10. Documentation language

Write all documentation, ADRs, code comments, commit messages, and pull request
descriptions in English. Verbatim Vietnamese strings are restricted to code
spans quoting user-facing dialogue messages defined in
[`apps/core/messages.py`](apps/core/messages.py) and SRS v4.1 specifications.

## 11. Where to ask questions

- Review [`README.md`](README.md), [`docs/README.md`](docs/README.md), and the
  [Frontend API Integration Guide](docs/guides/01-frontend-api-guide.md) first.
- For defect reports, feature proposals, or API accessibility barriers, open an
  issue with [`.github/ISSUE_TEMPLATE/bug_report.yml`](.github/ISSUE_TEMPLATE/bug_report.yml),
  [`.github/ISSUE_TEMPLATE/feature_request.yml`](.github/ISSUE_TEMPLATE/feature_request.yml),
  or [`.github/ISSUE_TEMPLATE/accessibility_barrier.yml`](.github/ISSUE_TEMPLATE/accessibility_barrier.yml).
- Do not open public issues for security vulnerabilities; follow
  [`SECURITY.md`](SECURITY.md).

## 12. Related policies

- [Code of Conduct](CODE_OF_CONDUCT.md)
- [Security Policy](SECURITY.md)
- [Accessibility Statement](ACCESSIBILITY.md)
- [License](LICENSE)
