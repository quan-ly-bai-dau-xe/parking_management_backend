# ADR-0003: Data Deletion Policy, Soft Delete, PROTECT, and Audit Trail

- **Status**: Proposed - pending Owner approval
- **Date**: 2026-10-11
- **Deciders**: Owner, Tech Lead, Engineering Team
- **Technical Context**: Database Integrity, Concurrency, and Regulatory Compliance

## 1. Context & Problem Statement

Operational parking data (tickets, entry/exit logs, slots, vehicles) governs physical access and financial accounting (SRS 4.7 revenue statistics). Physical hard deletion (`DELETE FROM`) risks severe data loss, breaks audit trails, and destroys financial metrics. We establish a comprehensive data deletion and audit policy.

## 2. Decision Outcome

### 2.1. Universal Soft Delete & API `isDeleted` Exposure (`TL-23`)

- All `18` soft-deletable business tables enforce `deleted_at TIMESTAMPTZ NULL` and `deleted_by BIGINT NULL` with `ck_<table_short>_soft_delete_pair CHECK (deleted_by IS NULL OR deleted_at IS NOT NULL)`.
- The 16/10/2026 team meeting's `isDeleted` boolean is exposed at the API/serializer layer (`deleted_at is not None`); no duplicate boolean column is stored in PostgreSQL (`TL-23`).
- Custom `SafeDeleteManager` filters default queries with `WHERE deleted_at IS NULL`, and all `8` statistic views and `4` `fn_stat_*` functions consistently exclude soft-deleted records (`TL-27`).

### 2.2. Database-Enforced Soft-Delete, Restore, and Plain-Delete Guards (`TL-24`–`TL-26`)

- All `69` foreign keys use `ON DELETE RESTRICT` (`on_delete=models.PROTECT`), with `0` `CASCADE` or `SET NULL` FKs.
- Plain `DELETE` from normal client sessions is blocked across all `28` base tables (`fn_guard_prevent_plain_delete()` on `16` purgeable tables, `fn_guard_hard_immutable_table()` on `11` immutable/system tables, and `fn_prevent_activity_log_mutation()` on `activity_log`) (`TL-24`).
- Controlled physical purge of eligible trash rows (`deleted_at < CURRENT_TIMESTAMP - p_retention`) is restricted to `fn_controlled_purge()` (`SECURITY DEFINER`, `SET search_path = public, pg_temp`, `p_dry_run BOOLEAN DEFAULT TRUE`), protected by `PG_CONTEXT` call-stack verification, `pg_proc` anti-spoofing check, and transaction-local nonce (`TL-24`).
- Because `ON DELETE RESTRICT` only guards physical `DELETE`, `db/01-schema.sql` enforces `DEL-01`–`DEL-06` and parent-active restore checks via `BEFORE UPDATE OF deleted_at` triggers (`fn_guard_soft_delete_and_restore()`) plus `ck_ticket_delete_only_expired` (`TL-25`, `TL-26`).

### 2.3. Partial Unique Constraints & Concurrency

- Uniqueness constraints use partial indexes (`WHERE deleted_at IS NULL`) so soft-deleted records do not block active records, while restoring a record with a conflicting active key fails automatically (`TL-26`).
- Deletions use pessimistic locking via `select_for_update()` inside `transaction.atomic()` and Optimistic Concurrency Control (OCC) via `row_version INTEGER NOT NULL DEFAULT 1` (`fn_update_row_version_and_timestamp()`).

### 2.4. Immutable Financial Records & Append-Only Audit Trail (`TL-24`, `TL-26`)

- `ticket`, `ticket_renewal`, `payment`, `vehicle_entry_exit_log`, `activity_log`, and `system_alert` can NEVER be physically deleted or purged (`TL-24`).
- `fn_audit_soft_delete_and_restore()` (`AFTER UPDATE OF deleted_at`) and `fn_controlled_purge()` automatically append `'SOFT_DELETE'`, `'RESTORE'`, and `'PURGE'` rows to the append-only `activity_log` table (`TL-26`).
- Customer Right to Erasure (Nghị định 13/2023/NĐ-CP) anonymizes PII with standardized markers (`is_anonymized = TRUE`) per `docs/requirements/03-delete-rules-catalog.md` (`OQ-12`, `TL-24`).

### 2.5. Non-Destructive Schema Governance (No DROP Statements)

- In accordance with D2, repository SQL scripts (`db/01-schema.sql`, `db/02-seed.sql`) are pure creation scripts strictly containing ZERO `DROP TABLE` or `DROP VIEW` statements. Re-running scripts against existing environments fails safely without data loss.

## 3. Consequences & References

- **Consequences**: Zero accidental financial data loss, database-enforced `DEL-01`–`DEL-06` and restore guards (`TL-23`–`TL-27`), full compliance with Decree 13/2023/ND-CP, and enforced OCC concurrency.
- Django on_delete: <https://docs.djangoproject.com/en/6.1/ref/models/fields/#django.db.models.ForeignKey.on_delete>
- PostgreSQL Partial Indexes: <https://www.postgresql.org/docs/18/indexes-partial.html>
- django-simple-history: <https://django-simple-history.readthedocs.io/>
- Nghị định 13/2023/NĐ-CP: <https://vanban.chinhphu.vn/?pageid=27160&docid=207705>
