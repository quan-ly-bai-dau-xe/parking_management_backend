---
name: 12-trash-restore-and-purge-lifecycle
description: Administrative management of the recycle bin (trash), safe record restoration with parent checks, and controlled periodic purge with audit logging.
---

# Skill: Trash, Restore & Controlled Purge Lifecycle

## 1. Objective

Provide end-to-end guidance for administrative management of soft-deleted records (Recycle Bin / Thùng rác), validating parent hierarchy integrity during restoration (TL-26), and executing safe, periodic controlled purges (TL-24).

## 2. Recycle Bin (Trash) Querying

- Admin endpoints query soft-deleted records using `SafeDeleteModel.all_with_deleted().filter(deleted_at__isnull=False)`.
- Support filtering by `deleted_at` range, `deleted_by`, and entity type.

## 3. Guarded Restoration Workflow (TL-26)

Restoring an entity (`isDeleted: false`) requires strict validation (enforced at both the service layer and in PostgreSQL via `fn_guard_soft_delete_and_restore()`):

1. **Parent Integrity Check**: Verify that all parent entities are currently active (`deleted_at IS NULL`):
   - `vehicle` cannot be restored if its owning `customer`, `vehicle_type`, or `ticket_type` is soft-deleted.
   - `parking_slot` cannot be restored if its parent `parking_zone` is soft-deleted (`parking_zone` checks `parking_floor`; `parking_floor` and `parking_gate` check `parking_lot`).
   - `employee` cannot be restored if their `position` or linked `account` is soft-deleted.
   - `ticket`, `slot_reservation`, `payment`, `news`, and `notification` require active parent references.
2. **Partial Unique Index Check**: Verify that restoring the row does not collide with an active record sharing the same partial unique key (`WHERE deleted_at IS NULL`).
3. **Execution**: Set `deleted_at = NULL` inside `transaction.atomic()`; `fn_guard_soft_delete_and_restore()` automatically resets `NEW.deleted_by := NULL` (`TL-23`).
4. **Audit**: `trg_audit_soft_delete_and_restore_*` (`fn_audit_soft_delete_and_restore()`) automatically inserts an append-only entry into `activity_log` with `action = 'RESTORE'`.

## 4. Controlled Periodic Purge Workflow (TL-24, TL-36, TL-40)

- **Privilege Hardening**: Purge is restricted to `fn_controlled_purge(p_table_name varchar, p_retention interval, p_dry_run boolean, p_purged_by bigint, p_target_id bigint)` (`SECURITY DEFINER`, `SET search_path = public, pg_temp`, `REVOKE ALL FROM PUBLIC`), returning `TABLE(table_name varchar, eligible_count bigint, purged_count bigint, status varchar, details text)`. Calls are verified by `fn_guard_prevent_plain_delete()` via `PG_CONTEXT` call-stack inspection, `pg_proc` anti-spoofing check, and transaction-local nonce (`app.purge_internal_nonce`).
- **Hard 30-Day Retention Floor (TL-40)**: `p_retention` MUST be `>= INTERVAL '30 days'`. Any shorter retention interval is immediately rejected with SQLSTATE `22023` (`invalid_parameter_value`).
- **Simulation Mode (`p_dry_run`)**: Always default `p_dry_run = TRUE` to report `eligible_count` without deleting rows.
- **Batch FK Skip Mechanism (TL-40)**: In batch mode (`p_target_id IS NULL`), loops through candidate trash rows and catches referential integrity errors (`foreign_key_violation` 23503 and `restrict_violation` 23001) per row to skip referenced rows, purging all remaining eligible rows and returning status `PARTIALLY_PURGED` or `PURGED` with itemized skipped counts. In single-row mode (`p_target_id IS NOT NULL`), foreign key errors are re-raised explicitly.
- **Linked Token Cleanup (TL-36)**: When purging an `account`, linked `persistent_login_token` and `password_reset_token` rows are deleted within the same subtransaction before deleting the account record.
- **Prohibited Entities**: Never purge `ticket`, `ticket_renewal`, `payment`, `vehicle_entry_exit_log`, `activity_log`, `system_alert`, or system lookup tables protected by `fn_guard_hard_immutable_table()`. (Token tables and `slot_allowed_vehicle_type` permit plain DELETE and are not subject to hard immutable triggers).
- **Privacy Compliance**: `customer` records require `is_anonymized = TRUE` under Decree 13/2023/ND-CP prior to any eligible purge.
- **Audit**: `fn_controlled_purge()` logs every non-dry-run purge execution into `activity_log` with `action = 'PURGE'`.

## 5. Verification Checklist

- [ ] Restore resets both `deleted_at` and `deleted_by` to `NULL` (`fn_guard_soft_delete_and_restore`).
- [ ] Restore is blocked with a clear error if any parent entity is soft-deleted (`TL-26`).
- [ ] `fn_controlled_purge` refuses live rows (`deleted_at IS NULL`), unexpired trash (`p_retention < 30 days` fails with 22023), non-anonymized customers, and immutable tables (`TL-24`, `TL-40`).
- [ ] In batch mode, `fn_controlled_purge` skips rows with active FK references without aborting the entire batch (`TL-40`).
- [ ] `fn_controlled_purge(p_dry_run => TRUE)` executes cleanly without altering row counts.
- [ ] All lifecycle actions generate corresponding `'SOFT_DELETE'`, `'RESTORE'`, and `'PURGE'` rows in `activity_log`.
