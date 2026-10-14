# 06-data-deletion-and-destructive-operations.md — Data Deletion & Destructive Operations Policy

## 1. Core Principles
- **Default Soft Delete**: All business entities (`Employee`, `Customer`, `Vehicle`, `Ticket`, `ParkingSlot`, `News`) must implement soft delete. Hard delete (`DELETE FROM ...`) is strictly forbidden in application code.
- **Immutable Financial & Audit Records**: Tickets (`Ticket`), entry/exit history (`VehicleEntryExitLog`), and revenue/audit records must NEVER be hard deleted.

## 2. Technical Soft-Delete Architecture
- **SafeDeleteModel**: All business models inherit `deleted_at = DateTimeField(null=True, blank=True, db_index=True)` and `deleted_by = ForeignKey(AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT)`.
- **Manager & QuerySet Protection**: Default `.filter()` excludes soft-deleted records (`WHERE deleted_at IS NULL`). Overriding `QuerySet.delete()` and `Model.delete()` to set `deleted_at` instead of hard deleting. Administrative queries explicitly call `.all_with_deleted()`.

## 3. Referential Integrity & Service-Layer Guards
- **Mandatory PROTECT**: Every ForeignKey pointing to business entities must use `on_delete=models.PROTECT`.
- **Critical Architectural Truth**: Django's `on_delete=PROTECT` exclusively prevents physical HARD deletes at the DB/ORM schema level; it does NOT prevent SOFT deletes (which only update `deleted_at`). Therefore, the Service layer MUST implement explicit domain guards to inspect active dependent relations before setting `deleted_at`.
- **Prohibited CASCADE**: Database-level `CASCADE` is strictly forbidden for business tables.
- **Service Guards**: Block customer/vehicle delete if parked in lot; block ticket delete unless expired and not renewed (SRS 4.6.4); block slot delete if reserved or occupied (SRS 4.8.5).

## 4. Partial Unique Constraints & Concurrency
- **Partial Indexes**: Unique constraints must use `models.UniqueConstraint(..., condition=models.Q(deleted_at__isnull=True))` so soft-deleted records do not block re-creating records with the same code.
- **Pessimistic Concurrency**: Mutating operations must use `select_for_update()` inside `transaction.atomic()`.

## 5. Audit Trail & Safe Migrations
- Business models must track history with `HistoricalRecords()` from `django-simple-history` (append-only diffs).
- Never edit applied migrations. Schema changes use expand/contract. DDL drops/truncates are prohibited in application migrations.

## 6. Mandatory Test Matrix & Destructive Command Ban
- Unit/integration tests must verify: soft delete flag update, service guards blocking deletion with exact SRS messages, `on_delete=PROTECT` blocking hard delete, and partial index uniqueness.
- AI agents must NEVER execute or suggest destructive commands (`rm -rf`, `git reset --hard`, `git push --force`, `manage.py flush`, `psql DROP/TRUNCATE`). Pattern rules in `settings.json` act as a local safety net; zero bypass allowed without explicit Owner approval.
