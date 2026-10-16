# 01-project-overview.md — Project Overview & Engineering Standards

## 1. Context & Purpose

- This repository (`parking_management_backend`) hosts the backend REST API service for the Car Parking Lot Management System (Hệ thống quản lý bãi đậu xe ô tô).
- The repository is PUBLIC on GitHub. Scope is strictly backend: Python 3.14.7 + Django 6.1.2 + PostgreSQL 18.6 + Django REST Framework 3.18.3. Frontend clients interact exclusively via OpenAPI 3.0 contracts.

## 2. Actors & Permission Roles (SRS v4.1 Section 3)

1. **Quản lý (Manager)**:
   - Full access to all modules: System Management, Employee Management (4.3), Customer Management (4.4), Vehicle In/Out (4.5), Ticket Management (4.6), Statistics & Revenue (4.7), and Parking Lot/Slot Management (4.8).
2. **Nhân viên (Employee)**:
   - Operational access: Customer Management (4.4), Vehicle In/Out (4.5), Ticket Management (4.6), and slot view/registration.
   - Denied access to Employee Management (4.3), Financial Statistics (4.7), and Slot Configuration (4.8).

## 3. Senior Engineer Mindset & Evidence Loop

- Act as a Senior Software Engineer. Before proposing architectural decisions or code, conduct parallel research across authoritative docs (Django, PostgreSQL, DRF, OWASP). Cite documentation URLs.
- Adhere strictly to the evidence loop: **Study Deeply -> Parallel Research -> Best Solution -> Real Test**.
- Never claim completion without verifiable proof (commands run, raw output, passed tests). Zero fabrication.
- Implement only verified requirements from `docs/requirements/00-srs-catalog.md` and approved scope in `docs/requirements/02-scope-additions-from-plan.md`. Ambiguities belong in `docs/requirements/01-open-questions.md`.

## 4. Secret Safety & Destructive Operation Safeguards

- Zero tolerance for committing secrets, tokens, passwords, database credentials, or server IPs. Never print secrets in logs, commits, or chat.
- Destructive commands (`rm -rf`, `git reset --hard`, `git push --force`, `manage.py flush`, `psql DROP/TRUNCATE`) are strictly forbidden.
- Permissions `deny` and `ask` in `.claude/settings.json` serve as a local safety net; true protection relies on GitHub push protection, branch protection, and human review.
- Data modifications must adhere strictly to `06-data-deletion-and-destructive-operations.md` and [ADR-0003](../../docs/adr/0003-data-deletion-soft-delete-protect-and-audit.md).
