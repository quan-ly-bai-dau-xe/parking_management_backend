# 02-srs-single-source-of-truth.md — SRS Specification Standards

## 1. Single Source of Truth Mandate

- The software requirements catalog in `docs/requirements/00-srs-catalog.md` and delete rules in `docs/requirements/03-delete-rules-catalog.md` are the authoritative Single Source of Truth for all domain models, business logic, validation rules, and response messages.
- Never invent error messages, validation ranges (such as unauthorized age 18-60 or phone length rules), or imaginary statuses.
- If a requirement is missing from the catalog, mark it as `ASSUMPTION` or `PROPOSAL` and submit it to `docs/requirements/01-open-questions.md`.

## 2. Stable Citation Standard

Every model docstring, serializer validation rule, service method, and test case must cite its source using the project Stable Citation Convention:

- **Field Requirement**: `REQ-<Screen>-F<Number>` (e.g., `REQ-4.3.2-F07: Email field in Add Employee, SRS 4.3.2 Row 9`).
- **Action / Endpoint**: `ACT-<Screen>-A<Number>` (e.g., `ACT-4.6.4-A01: Delete Ticket, SRS 4.6.4 Row 10`).
- **Verbatim Message**: `MSG-<Screen>-M<Number>` (e.g., `MSG-4.1-M01: Tên đăng nhập không chứa ký tự đặc biệt, SRS 4.1 Row 11`).
- **Wireframe Citations**: Cite embedded wireframes as `image N: element` (e.g., `image14: slot grid layout`, `image7: delete confirmation popup`).
- **Prohibited Citations**: NEVER cite unstable text line numbers (such as "Line 42 of SRS.docx").

## 3. Scope Additions from Sprint Plan

- Only features explicitly documented in `docs/requirements/02-scope-additions-from-plan.md` (e.g., license plate OCR integration endpoint, vehicle search modal API, news management CRUD) may be implemented alongside SRS v4.1 core features.
