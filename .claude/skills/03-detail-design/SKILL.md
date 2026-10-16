---
name: 03-detail-design
description: Technical detail design matching the 4-sheet template structure (Use_Case, Class_Diagram, Sequence_Diagram, Pseudo_Code).
---

# Skill: Technical Detail Design

## 1. Objective

Guide the creation of technical Detail Design conforming to the 4-sheet structure found in the project's official template (`01-Template/Detail_Design/`).

## 2. 4-Sheet Specification Structure

1. **Sheet 1: `Use_Case`**:
   - Metadata: Use Case ID (`UC-<Screen-ID>`), Actor (`Manager` / `Employee`), Pre-conditions, Post-conditions.
   - Basic Flow: Step-by-step request flow, authorization check, service coordination, atomic commit, verbatim response.
   - Alternative & Exception Flows: 404 (Not Found), 400 (Guard rule violation with verbatim SRS message), 409 (Concurrency conflict).
2. **Sheet 2: `Class_Diagram`**:
   - 3-tier architecture: ViewSet (`urls/views`), Domain Service (`services.py`), Selector (`selectors.py`), Entity Model (`models.py`), and Serializer (`serializers.py`).
   - Explicit relationships: View dispatches Service; Service queries Selector and persists via Model.
3. **Sheet 3: `Sequence_Diagram`**:
   - Request lifecycle across tiers: Client -> View -> Service -> PostgreSQL.
   - Boundary enforcement: Explicit `transaction.atomic()` demarcations and `select_for_update()` row-locking for race-condition prevention.
4. **Sheet 4: `Pseudo_Code`**:
   - Structured algorithmic steps covering: Input validation, concurrency row lock, business guard evaluations, soft-delete timestamping (`deleted_at`, `deleted_by`), audit logging via `django-simple-history`, and verbatim response mapping.

## 3. Verification Checklist

- [ ] Matches all 4 sheets in the official template structure (`01-Template/Detail_Design/`).
- [ ] Concurrency handling defines `select_for_update()` inside `transaction.atomic()`.
- [ ] All error messages cite canonical IDs (`MSG-*` from SRS catalog or `PROP-*` from proposals).
- [ ] Enforces strict 3-tier separation (View -> Service/Selector -> Model).
