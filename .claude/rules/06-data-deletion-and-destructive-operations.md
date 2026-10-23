# 06-data-deletion-and-destructive-operations.md — Data Deletion & Destructive Operations Policy

## 1. Core Principles (Meeting 16/10/2026 & TL-23..TL-27)

- **Default Soft Delete**: 100% of domain business entities (`Employee`, `Customer`, `Vehicle`, `Ticket`, `ParkingSlot`, etc.) enforce soft deletion. Physical `DELETE FROM ...` is strictly rejected at the database level across all business tables via `BEFORE DELETE` triggers (TL-24).
- **Dual Representation of Deleted State (TL-23)**:
  - **Database Level**: Stored as `deleted_at TIMESTAMPTZ NULL` and `deleted_by BIGINT NULL` (FK to `account`). A record is considered deleted if and only if `deleted_at IS NOT NULL`. Integrity enforced via `CHECK (deleted_by IS NULL OR deleted_at IS NOT NULL)` across all 18 soft-deletable tables.
  - **API Contract Level**: Exposed via DRF Serializers as a computed boolean property `isDeleted: bool` (`false` by default, `true` when soft-deleted), shielding clients from raw database timestamps.
- **Immutable Financial & Audit Records**: Tickets (`ticket`), payments (`payment`), parking sessions (`vehicle_entry_exit_log`), renewals (`ticket_renewal`), audit trail (`activity_log`), and system alerts (`system_alert`) can NEVER be purged (TL-24).

## 2. Universal Application Query Rule (TL-27)

- **One-Line Invariant**: Every `list`, `detail`, `create`, and `update` flow across the application MUST ALWAYS filter `deleted_at IS NULL` (`isDeleted = false`).
- **ORM Enforcement**: Custom `SafeDeleteManager` automatically excludes soft-deleted records by default. Administrative or audit queries must explicitly call `.all_with_deleted()` or `.only_deleted()`.
- **Statistical Hygiene**: All 8 analytical views and `fn_stat_*` reporting functions strictly ignore soft-deleted records (TL-27).

## 3. Database Triggers & Service-Layer Guards (TL-24, TL-25, TL-36..TL-39, TL-42)

- **Database-Level Hard Delete Guard (TL-24, TL-36, TL-37)**: Plain `DELETE` is blocked on 25 base tables (`fn_guard_prevent_plain_delete()` on 16 purgeable tables, `fn_guard_hard_immutable_table()` on 8 immutable tables, and `fn_prevent_activity_log_mutation()` on `activity_log`).
  - *Plain DELETE Exceptions (TL-36, TL-37)*: Exactly 3 tables permit plain `DELETE`: `persistent_login_token` and `password_reset_token` (for token rotation, logout, and credential revocation per TL-36), and junction table `slot_allowed_vehicle_type` (for dynamic slot vehicle-type reconfiguration per TL-37, guarded by `trg_guard_slot_allowed_vehicle_type_delete` which blocks removing a type currently used by active tickets, open sessions, or active reservations with error `PROP-DEL-SAVT-IN-USE`).
- **Database-Level Soft Delete Guard (TL-25, TL-39, TL-42)**: `BEFORE UPDATE OF deleted_at` triggers (`fn_guard_soft_delete_and_restore()`) and `ck_ticket_delete_only_expired` reject invalid soft deletions (`DEL-01`–`DEL-06`) directly in PostgreSQL:
  - Reject soft deletion of occupied/charging/reserved slots, customers with active vehicles/tickets/open sessions, vehicles with active tickets/reservations/open sessions, self-deletion or last active `MANAGER`, facilities with active children, and unexpired/renewed/parked tickets.
  - *Payment Soft-Delete Guard (TL-39)*: Blocks soft deletion of any `payment` record with `status IN ('PAID', 'REFUNDED')` with exception `PROP-DEL-PAYMENT-SETTLED`. Soft-delete is permitted only on `UNPAID` or `CANCELLED` payments to safeguard financial revenue integrity.
  - *Payment Status Transition & Immutability Guard (TL-42)*: `trg_guard_payment_update` (`BEFORE UPDATE ON payment`) restricts status transitions (`UNPAID -> PAID | CANCELLED`, `PAID -> REFUNDED` only; terminal statuses; `PROP-PAY-STATUS-TRANSITION`) and locks settled payment financial/link columns (`amount`, `method`, `paid_at`, `session_id`, `ticket_id`, `renewal_id`, `code`; `PROP-PAY-SETTLED-IMMUTABLE`), allowing only harmless `notes` edits.
- **Service Layer Responsibility**: Domain services MUST implement pre-flight validation guards before initiating deletion, wrapping operations in `transaction.atomic()` with pessimistic locking (`select_for_update()`).

## 4. Trash, Restore & Controlled Purge Lifecycle (TL-24, TL-26, TL-40)

- **Recycle Bin (Thùng rác)**: Soft-deleted records act as a trash bin (`deleted_at IS NOT NULL`).
- **Guarded Restore (TL-26)**: Restoring a record sets `deleted_at = NULL`, and `fn_guard_soft_delete_and_restore()` automatically clears `NEW.deleted_by := NULL` while verifying that all parent entities are currently active and partial unique index constraints (`WHERE deleted_at IS NULL`) are not violated.
- **Controlled Purge (TL-24, TL-40)**: Executed strictly by administrative maintenance via `fn_controlled_purge(p_table_name varchar, p_retention interval, p_dry_run boolean, p_purged_by bigint, p_target_id bigint)` (`SECURITY DEFINER`, `SET search_path = public, pg_temp`, `p_dry_run BOOLEAN DEFAULT TRUE`), guarded by `PG_CONTEXT` call-stack verification, `pg_proc` anti-spoofing check, and transaction-local nonce (`app.purge_internal_nonce`). Returns `TABLE(table_name varchar, eligible_count bigint, purged_count bigint, status varchar, details text)`:
  - *30-Day Retention Floor (TL-40)*: Enforces `p_retention >= INTERVAL '30 days'`; rejects lower intervals with SQLSTATE `22023` (`invalid_parameter_value`).
  - *Batch FK Skip (TL-40)*: In batch mode (`p_target_id IS NULL`), loops through candidate trash rows and catches referential integrity errors (`foreign_key_violation` 23503, `restrict_violation` 23001) to skip referencing rows and purge all eligible rows, returning status `PARTIALLY_PURGED` or `PURGED` with itemized counts. In single-row mode (`p_target_id IS NOT NULL`), re-raises foreign key errors explicitly.
  - *Linked Token Cleanup (TL-36)*: When purging an `account`, linked `persistent_login_token` and `password_reset_token` rows are deleted in the same subtransaction before deleting the account record.
  - Customer rows additionally require `is_anonymized = TRUE` per Decree 13/2023/ND-CP.
- **Audit Logging (TL-26)**: `fn_audit_soft_delete_and_restore()` (`AFTER UPDATE OF deleted_at`) and `fn_controlled_purge()` write append-only audit records to `activity_log` with action `'SOFT_DELETE'`, `'RESTORE'`, or `'PURGE'`.

## 5. Partial Unique Constraints & Destructive Command Ban

- **Partial Indexes**: Uniqueness is scoped exclusively to active records via `condition=models.Q(deleted_at__isnull=True)` (PostgreSQL `WHERE deleted_at IS NULL`).
- **Destructive Command Ban**: AI agents must NEVER execute or propose destructive commands (`rm -rf`, `git reset --hard`, `git push --force`, `manage.py flush`, `psql DROP/TRUNCATE`). Local safety net enforced via `.claude/settings.json`.
