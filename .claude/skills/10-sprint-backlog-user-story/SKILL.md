---
name: 10-sprint-backlog-user-story
description: Guidelines for decomposing requirements into INVEST-compliant User Stories and managing Sprint Backlog deliverables.
---

# Skill: User Story Decomposition & Sprint Backlog Management

## 1. Objective

Guide backend software engineers and business analysts in decomposing large functional requirements from `docs/requirements/00-srs-catalog.md` into well-sized User Stories meeting the INVEST criteria, defining rigorous Acceptance Criteria, and tracking execution on the Sprint Backlog.

## 2. Standard Structure of a Backend User Story

Each User Story follows the standard template:

```text
As a [User Role / Actor]
I want [Technical API action / Feature capability]
So that [Business benefit / System objective]
```

### Mandatory Associated Components

1. **Story Identifier**: `US-<Sprint>-<Number>` (e.g. `US-S1-05: Parking Ticket Deletion API`).
2. **SRS Traceability Citation**: Linked to Stable IDs in the canonical catalog (e.g. `SRS 4.6.4, ACT-4.6.4-A01`).
3. **Role-Based Access Control (RBAC)**: Explicitly defined actor permissions (`MANAGER` or `EMPLOYEE`).
4. **Acceptance Criteria (AC)**:
   - AC1: On valid request, system updates `deleted_at`, returning HTTP 200 with verbatim response: `"Xóa thành công"`.
   - AC2: When ticket has not expired, system returns HTTP 400 with domain guard error.
   - AC3: When ticket is already soft-deleted or non-existent, system returns HTTP 404 with proposed message [PROPOSAL]: "Vé không tồn tại hoặc đã bị xóa." (PROP-4.6.4-P05, see OQ-21).
   - AC4: On unauthorized request, returns HTTP 403 Forbidden.
5. **Technical Engineering Sub-Tasks**:
   - [ ] Write unit tests for service and serializer.
   - [ ] Implement pessimistic row locking and soft-delete mutations in Service layer.
   - [ ] Register endpoint actions in ViewSet and URL routing.
   - [ ] Verify static cleanliness with `ruff` and `mypy`.

## 3. Sprint Backlog Planning Procedure

1. **Select User Stories from Product Backlog**: Prioritized by business value and Sprint goals.
2. **Estimate Complexity (Story Points)**: Apply Fibonacci sequence sizing (1, 2, 3, 5, 8).
3. **Assign Engineering Ownership**: Explicit assignee designated per technical task.
4. **Track Execution States**: `To Do` -> `In Progress` -> `In Review` -> `Done` (transitioning to Done strictly when Definition of Done criteria are satisfied).

## 4. Verification Checklist

- [ ] User story contains all 3 standard clauses (Role, Action, Benefit).
- [ ] Acceptance criteria can be verified independently via automated API tests.
- [ ] Zero ungrounded requirements or speculative assumptions contradictory to the SRS catalog.
- [ ] Automated testing tasks are coupled with every user story.
