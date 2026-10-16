# 01-project-overview.md — Project Overview & Engineering Standards

## 1. Context & Purpose

- This repository (`parking_management_backend`) hosts the backend REST API service for the Smart Mobility Car Parking Lot Management System (`Bãi xe Smart Mobility` / Hệ thống quản lý bãi đậu xe).
- The repository is PUBLIC on GitHub. Scope is strictly backend: Python 3.14.7 + Django 6.1.2 + PostgreSQL 18.6 + Django REST Framework 3.18.3. Frontend clients interact exclusively via OpenAPI 3.0 contracts.

## 2. Actors & Permission Roles (`TL-01` & SRS Section 3)

1. **Quản lý (`MANAGER`)**:
   - Full access to all modules: Dashboard & Alerts, Employee Management, Customer & Blacklist Management, Vehicle & Entry/Exit Sessions, Ticket & Payment Management, Revenue & Traffic Statistics, and Parking Lot/Floor/Zone/Slot Configuration.
2. **Nhân viên (`EMPLOYEE`)**:
   - Operational access: Customer Management, Vehicle & Gate Entry/Exit Sessions, Ticket & Payment Management, and Parking Map slot view/reservation.
   - Denied access to Employee Management, Financial Statistics, and Structural Lot/Floor/Zone Configuration.
3. **Khách hàng (`CUSTOMER`)**:
   - Self-service portal account (`"Đăng ký ngay"`, `TL-01`) linked to a `customer` profile for viewing vehicles, tickets, and slot reservations.

## 3. Senior Engineer Mindset & Evidence Loop

- Act as a Senior Software Engineer. Before proposing architectural decisions or code, conduct parallel research across authoritative docs (Django, PostgreSQL, DRF, OWASP). Cite documentation URLs.
- Adhere strictly to the evidence loop: **Study Deeply -> Parallel Research -> Best Solution -> Real Test**.
- Never claim completion without verifiable proof (commands run, raw output, passed tests). Zero fabrication.
- Follow the **Frontend-First** requirement hierarchy (`docs/requirements/06-frontend-srs-db-alignment.md` primary, `docs/requirements/00-srs-catalog.md` secondary where the Frontend is silent, and `docs/requirements/02-scope-additions-from-plan.md`). Ambiguities belong in `docs/requirements/01-open-questions.md`.

## 4. Secret Safety & Destructive Operation Safeguards

- Zero tolerance for committing secrets, tokens, passwords, database credentials, or server IPs. Never print secrets in logs, commits, or chat.
- Destructive commands (`rm -rf`, `git reset --hard`, `git push --force`, `manage.py flush`, `psql DROP/TRUNCATE`) are strictly forbidden.
- Permissions `deny` and `ask` in `.claude/settings.json` serve as a local safety net; true protection relies on GitHub push protection, branch protection, and human review.
- Data modifications must adhere strictly to `06-data-deletion-and-destructive-operations.md` and [ADR-0003](../../docs/adr/0003-data-deletion-soft-delete-protect-and-audit.md).
