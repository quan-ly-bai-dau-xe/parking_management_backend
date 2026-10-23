# Description of Changes
<!-- Provide a concise summary of the changes and the architectural rationale (WHY, not just WHAT). -->

**Related Issue**: Closes #<!-- Issue ID -->

---

## Type of Change

- [ ] `feat`: New feature (backward-compatible)
- [ ] `fix`: Bug fix
- [ ] `refactor`: Code refactoring without behavior change
- [ ] `test`: Adding or improving automated tests
- [ ] `docs`: Documentation updates
- [ ] `chore`: Tooling, CI, or dependency maintenance

---

## 🔒 Destructive Operations & Delete Policy Checklist
<!-- Mandatory for all pull requests touching models, migrations, views, or services -->
- [ ] **Soft Delete Enforcement**: All business models implement `deleted_at` and `deleted_by` (`SafeDeleteModel`).
- [ ] **No Hard Delete**: Physical row removal (`DELETE FROM ...`) is NOT called anywhere in application code.
- [ ] **Foreign Key Safety**: All new ForeignKeys to business entities specify `on_delete=models.PROTECT` (No `models.CASCADE`).
- [ ] **Partial Unique Indexes**: Unique constraints are scoped with `condition=models.Q(deleted_at__isnull=True)`.
- [ ] **Immutable Records**: No hard delete logic introduced for `Ticket`, `VehicleEntryExitLog`, or audit records.
- [ ] **Pessimistic Concurrency**: Delete services use `select_for_update()` inside `transaction.atomic()`.
- [ ] **Verbatim SRS Messages**: All delete failure/success responses return exact strings from `docs/requirements/00-srs-catalog.md`.
- [ ] **Migration Safety**: No migration file contains `DROP TABLE`, `DROP COLUMN`, `TRUNCATE`, or destructive `RunSQL`.

---

## Definition of Done (DoD) Checklist

- [ ] **Peer Review**: Code has been reviewed and approved by at least 1 peer.
- [ ] **Automated Tests**: `pytest` passes 100% with line coverage >= 80%.
- [ ] **Linting & Formatting**: `ruff check .` and `ruff format --check .` report 0 errors.
- [ ] **Type Checking**: `mypy .` reports 0 errors.
- [ ] **Migration Check**: `python manage.py makemigrations --check --dry-run` reports no uncommitted schema changes.
- [ ] **OpenAPI Contract**: API schemas validate cleanly with `drf-spectacular`.
- [ ] **Secret Hygiene**: Verified zero secrets, passwords, or `.env` files staged.

---

## Verification Evidence
<!-- Paste raw terminal command outputs proving test execution and quality gate success. -->
```text
[Paste pytest, ruff, mypy output here]
```
