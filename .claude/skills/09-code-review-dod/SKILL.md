---
name: code-review-dod
description: Code review and quality assurance guidelines based on 10 Definition of Done (DoD) criteria and 20 Check_Quality criteria.
---

# Skill: Code Review & Definition of Done Verification

## 1. Objective
Guide software engineers in conducting rigorous peer code reviews on Pull Requests targeting the `dev` branch, ensuring compliance with:
- 10 Definition of Done (DoD) criteria from `docs/requirements/04-dod-and-quality-check.md`.
- 20 Check_Quality criteria (focusing on backend-applicable items).
- 7 Team Lead technical quality gates (TL-GATE-01 through TL-GATE-07).

## 2. 10 Definition of Done (DoD) Review Matrix
| No. | DoD Criterion | Reviewer Verification Method | Pass |
| :---: | :--- | :--- | :---: |
| 1 | Peer Code Review | PR has at least 1 peer review comment and explicit approval on GitHub. | [ ] |
| 2 | Cross-role Testing | QA or peer engineer validates endpoints on local/dev environment. | [ ] |
| 3 | Multi-browser Testing | N/A for backend repository (frontend scope). | N/A |
| 4 | Data Validation | Serializers declare complete format, length, and mandatory validations. | [ ] |
| 5 | I18n & Error Messages | Error messages match verbatim SRS catalog text without altering punctuation (default: verbatim unpunctuated; pending PO resolution of OQ-46). | [ ] |
| 6 | Clean Data Envelope | Standard snake_case JSON response, ISO 8601 timestamps, no redundant nulls. | [ ] |
| 7 | Refactored Architecture | Clean 3-tier layering (View - Service - Selector), N+1 queries eliminated. | [ ] |
| 8 | Merge to Dev Branch | Target branch is `dev`, configured with `--no-ff` merge commits. | [ ] |
| 9 | Bootstrap Default Color | N/A for backend repository (frontend scope). | N/A |
| 10 | Interface Spec Compliance | N/A for UI. Adapted for Backend: 100% adherence to OpenAPI 3.0 contracts. | [ ] |

## 3. Backend Check_Quality Review Checklist
- [ ] **Check_Quality 6 (Message text, field insertion, punctuation)**: Error messages include specific field names; verbatim SRS strings kept without invented punctuation; proposed messages include ending punctuation pending PO decision (OQ-46).
- [ ] **Check_Quality 7 (Format validation for email, phone, date, password)**: Standard email regex, phone length bounds, password meeting 4 SRS 4.3.3 constraints.
- [ ] **Check_Quality 8 (Simultaneous validation display)**: Serializer aggregates all field errors into a single HTTP 400 response.
- [ ] **Check_Quality 10 (Enable/Disable / Read-only)**: Non-editable fields (Employee ID, Vehicle ID, Ticket Code) marked `read_only=True`.
- [ ] **Check_Quality 11 (Whitespace trimming)**: All string inputs automatically apply `strip()` to remove leading/trailing whitespace.
- [ ] **Check_Quality 12 (Max-length enforcement)**: Validate `max_length` constraints at both Serializer and Model column levels.
- [ ] **Check_Quality 14 (Confirm field persistence to DB)**: Zero SRS fields omitted during PostgreSQL persistence.
- [ ] **Check_Quality 16 (Delete confirmation)**: Safe deletion endpoints enforce business guard preconditions before execution.
- [ ] **Check_Quality 18 (Pagination pager)**: List endpoints return `count`, `next`, `previous`, `results`.
- [ ] **Check_Quality 19 (Search across all items)**: Multi-field search filters supported; empty query returns all active records.
- [ ] **Check_Quality 20 (Business logic accuracy)**: Strict business rules enforced (e.g. only expired tickets eligible for deletion).

## 4. 7 Team Lead Technical Quality Gates
- [ ] **[TL-GATE-01] Tests**: `pytest` passes 100%, test coverage >= 80%.
- [ ] **[TL-GATE-02] Ruff**: `ruff check .` and `ruff format --check .` report 0 errors.
- [ ] **[TL-GATE-03] Mypy**: `mypy .` reports 0 type errors.
- [ ] **[TL-GATE-04] Migrations**: `makemigrations --check --dry-run` reports 0 uncommitted schema changes.
- [ ] **[TL-GATE-05] OpenAPI**: `drf-spectacular` generates valid schema without warnings.
- [ ] **[TL-GATE-06] Security**: `check --deploy` passes; secret scans report zero violations.
- [ ] **[TL-GATE-07] Safe Delete**: Adheres strictly to soft deletion and `PROTECT` foreign key constraints.
