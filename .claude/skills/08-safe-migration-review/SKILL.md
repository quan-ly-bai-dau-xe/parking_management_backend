---
name: safe-migration-review
description: Safe review guidelines for Django migration files, preventing destructive database operations (DROP, TRUNCATE) and ensuring backward compatibility.
---

# Skill: Safe Database Migration Review

## 1. Objective
Guide the verification and approval of Django migration files before integration into the `dev` branch, eliminating data loss risks, table locking hazards, and schema divergence in PostgreSQL environments.

## 2. Review Checklist

### 1. Destructive Operations Prohibition
- [ ] Zero `RunSQL` or `RunPython` operations containing destructive SQL keywords: `DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, `DELETE FROM`.
- [ ] If a column or table must be phased out, enforce a multi-phase expand/contract migration cycle:
  - Phase 1: Mark field as deprecated, loosen to `null=True, blank=True`.
  - Phase 2: Physically remove column only after application code has decoupled and an ADR approval is recorded.

### 2. Foreign Key Referential Integrity
- [ ] All `migrations.AddField` or `migrations.CreateModel` operations containing `ForeignKey` fields specify `on_delete=django.db.models.deletion.PROTECT`.
- [ ] Zero instances of `models.CASCADE` across domain relationships.

### 3. Indexes & Constraints Verification
- [ ] Unique fields declare `UniqueConstraint` with partial filtering: `condition=models.Q(deleted_at__isnull=True)`.
- [ ] Heavy indexes evaluate concurrent creation (`concurrently=True`) for production execution.

### 4. Reversibility Verification
- [ ] Migrations must rollback cleanly via `python manage.py migrate <app_name> <previous_migration_number>`.
- [ ] Zero `migrations.RunPython(code)` without an explicit reverse function (`reverse_code`).

## 3. Independent Verification Procedure
1. Verify migration cleanliness against model declarations:
   ```bash
   python manage.py makemigrations --check --dry-run
   ```
2. Execute forward and backward migration steps on test database:
   ```bash
   python manage.py migrate
   python manage.py migrate <app_name> <previous_migration>
   python manage.py migrate
   ```
3. Inspect generated SQL statements:
   ```bash
   python manage.py sqlmigrate <app_name> <migration_number>
   ```

## 4. Enforcement Action
If a migration introduces unapproved destructive schema changes:
- **REJECT PULL REQUEST** immediately.
- Require author remediation conforming to the safe soft-delete and data preservation policy.
