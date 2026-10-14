# ADR-0003: Data Deletion Policy, Soft Delete, PROTECT, and Audit Trail

- **Status**: Proposed - pending Owner approval
- **Date**: 2026-10-11
- **Deciders**: Owner, Tech Lead, Engineering Team
- **Technical Context**: Database Integrity, Concurrency, and Regulatory Compliance

## 1. Context & Problem Statement
Operational parking data (tickets, entry/exit logs, slots, vehicles) governs physical access and financial accounting (SRS 4.7 revenue statistics). Physical hard deletion (`DELETE FROM`) risks severe data loss, breaks audit trails, and destroys financial metrics. We establish a comprehensive data deletion and audit policy.

## 2. Decision Outcome

### 2.1. Universal Soft Delete by Default
- 100% of business entities inherit from `SafeDeleteModel` (`deleted_at`, `deleted_by`).
- Custom `SafeDeleteManager` filters default queries with `WHERE deleted_at IS NULL`.
- Calling `delete()` sets timestamps instead of executing physical deletion. Administrative access uses `.all_with_deleted()`.

### 2.2. Referential Integrity: PROTECT vs Service-Layer Guards
- All foreign keys to business models use `on_delete=models.PROTECT` (PostgreSQL `ON DELETE RESTRICT`). Database-level `CASCADE` is strictly prohibited across all business entities.
- **Architectural Truth**: Django's `on_delete=models.PROTECT` operates exclusively during physical HARD deletions at the ORM/DB level. It does NOT prevent SOFT deletions (which are SQL `UPDATE` statements).
- Therefore, the Service layer MUST implement explicit domain guards inspecting active reverse relations (e.g., active tickets or parked vehicles) before setting `deleted_at`.
- **Database CHECK Guard on Deletion**: Physical database schemas enforce deletion validity constraints where applicable, specifically `CHECK (deleted_at IS NULL OR effective_to <= deleted_at)` on tickets, preventing database-level soft deletion of active tickets prior to expiration (SRS 4.6.4, D6, OQ-64).

### 2.3. Partial Unique Constraints & Concurrency
- Uniqueness constraints use partial indexes (`condition=models.Q(deleted_at__isnull=True)`) so soft-deleted records do not block creating new records with the same code.
- Deletions use pessimistic locking via `select_for_update()` inside `transaction.atomic()`.
- Optimistic Concurrency Control (OCC) is maintained via `row_version INTEGER NOT NULL DEFAULT 1` with automated database `BEFORE UPDATE` triggers (`fn_update_row_version_and_timestamp()`), detecting concurrent updates across operators (D6, OQ-64).

### 2.4. Immutable Financial Records & Audit Trail
- `Ticket` and `VehicleEntryExitLog` records are immutable financial/operational history and must NEVER be physically deleted.
- Append-only audit history via `django-simple-history` (`HistoricalRecords`) captures actor, timestamp, diffs, and client IP via middleware.
- Customer Right to Erasure (Nghị định 13/2023/NĐ-CP) anonymizes PII with standardized markers per `docs/requirements/03-delete-rules-catalog.md`.

### 2.5. Non-Destructive Schema Governance (No DROP Statements)
- In accordance with D2, repository SQL scripts (`db/01-schema.sql`, `db/02-seed.sql`) are pure creation scripts strictly containing ZERO `DROP TABLE` or `DROP VIEW` statements. Re-running scripts against existing environments fails safely without data loss.

## 3. Consequences & References
- **Consequences**: Zero accidental financial data loss, full compliance with Decree 13/2023/ND-CP, preserved revenue metrics, enforced OCC concurrency.
- Django on_delete: https://docs.djangoproject.com/en/6.1/ref/models/fields/#django.db.models.ForeignKey.on_delete
- PostgreSQL Partial Indexes: https://www.postgresql.org/docs/18/indexes-partial.html
- django-simple-history: https://django-simple-history.readthedocs.io/
- Nghị định 13/2023/NĐ-CP: https://vanban.chinhphu.vn/?pageid=27160&docid=207705

