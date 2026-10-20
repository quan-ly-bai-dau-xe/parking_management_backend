# ADR-0006: Django Skeleton v2, Database Schema Authority, and Architectural Baseline

- **Status**: Accepted
- **Date**: 2026-10-17
- **Deciders**: Owner, Tech Lead, Engineering Team
- **Technical Context**: Database Schema Governance, Django Backend Architecture, Data Safety, and CI/CD Quality Gates

---

## 1. Context & Problem Statement

In previous development phases (Rounds 23–28), the PostgreSQL 18.6 database schema was comprehensively designed, normalized, and frozen as **Schema v2** (`db/01-schema.sql`, `db/02-seed.sql`, `db/03-erd.asta`). It comprises 28 base tables, 8 analytical views, 69 `ON DELETE RESTRICT` foreign keys, 87 user triggers, and 22 custom user functions.

When implementing the backend REST API in Django 6.1.2 (Round 29), standard Django practice typically involves generating DDL migrations from Python model definitions. However, permitting Django's migration engine to manage DDL would introduce severe synchronization hazards:

1. Risk of schema desynchronization between Django migrations and the frozen, battle-tested PostgreSQL Schema v2.
2. Inability of Django ORM to automatically generate or represent complex PostgreSQL constructs (GiST exclusion constraints, partial GIN trigram indexes, custom trigger functions, row-level immutability guards, and PL/pgSQL soft-delete guards).
3. Risk of destructive automated migrations in production environments.

Therefore, an explicit architecture decision is required to formalize the relationship between Django models and PostgreSQL Schema v2.

---

## 2. Decision Outcome

### 2.1. PostgreSQL Schema Authority & Unmanaged Models (`managed=False`)

- **Schema Authority**: `db/01-schema.sql` (Schema v2) is designated as the absolute and immutable Single Source of Truth for database structure.
- **Unmanaged Models**: All 28 domain tables and 8 analytical views are implemented in Django models with `managed = False` in their `Meta` options. Django's migration engine is strictly forbidden from executing automated `CREATE TABLE`, `ALTER TABLE`, or `DROP TABLE` DDL on domain tables.
- **Django Internal Tables Coexistence**: Django internal operational tables (`django_migrations`, `django_content_type`, `django_session`) remain managed by Django's native migrations, coexisting peacefully within the same PostgreSQL database.

### 2.2. Schema Ingestion via Initial Migration & Sample Data Seeding

- **Initial RunSQL Migration (`apps/core/migrations/0001_initial.py`)**:
  - Ingests the authoritative DDL by reading `db/01-schema.sql` directly from the filesystem at migration runtime.
  - Configured with `atomic = False` to support PostgreSQL extensions (`btree_gist`, `pg_trgm`) and transactions cleanly.
  - Reversible behavior is explicitly set to `noop` (`migrations.RunSQL.noop`) to prevent accidental destruction or drops of database tables upon rollback.
- **Safe Sample Data Seeding (`python manage.py load_sample_data`)**:
  - Implemented as a dedicated, idempotent management command reading `db/02-seed.sql` directly from disk.
  - Guarded by an environment safety check: when `DEBUG=False` (production or staging mode), execution is blocked unless the explicit flag `--force-production` is provided.

### 2.3. Three-Tier Base Model Hierarchy & Safe Soft-Delete

To standardize auditability and safe data deletion across all domain models without violating Schema Authority:

- **`TimeStampedModel`**: Abstract base model providing `created_at` and `updated_at` (`editable=False`, `auto_now_add=True`, `auto_now=True`).
- **`SoftDeleteBaseModel`**: Abstract base model incorporating `row_version = models.IntegerField(default=1, editable=False)` alongside timestamps.
- **`SoftDeleteModel`**: Abstract base model for the 18 soft-deletable business tables, providing `deleted_at`, `deleted_by`, custom managers (`SoftDeleteManager`, `with_deleted()`, `only_deleted()`), and safe methods (`soft_delete()`, `restore()`).
- **Hard Deletion Protection**: Physical `delete()` on business models is overridden to raise `PermissionDenied` or redirect to `soft_delete()`. Exemptions permitting plain `DELETE` are granted exclusively to operational token models (`PersistentLoginToken`, `PasswordResetToken`) per TL-36 / ADR-0004.
- **Foreign Key Declarations**: All foreign keys in unmanaged models use `on_delete=models.DO_NOTHING` and `db_constraint=False`, deferring referential integrity enforcement entirely to PostgreSQL's 69 `ON DELETE RESTRICT` constraints.

### 2.4. Custom Authentication Model (`Account`)

- Replaces Django's default `User` with `apps.accounts.models.Account` (`AUTH_USER_MODEL = 'accounts.Account'`).
- Inherits from `AbstractBaseUser` without `PermissionsMixin` to match the exact schema of `account` (no extra columns like `is_superuser` or `groups`).
- Dual-channel login authentication via Email or Phone number (specified per TL-01 / ADR-0004 to be implemented by the assigned team member; the foundation skeleton defines the `Account` model and token table mappings).
- Session cookie authentication paired with persistent "Remember-Me" token table mapping in `persistent_login_token` per ADR-0004.
- Role-based permissions: `is_staff` and administrative privileges are derived properties based on `role == 'MANAGER'`.

### 2.5. Three-Tier Architectural Pattern for Backend APIs

All API functionality follows strict layer separation:

1. **Views / ViewSets**: Thin HTTP controllers handling protocol negotiation, permission checks (`IsAuthenticated`, `IsManager`), and calling services/selectors.
2. **Services**: Encapsulate write operations, domain validations, atomic transaction boundaries (`@transaction.atomic`), and row locking (`select_for_update()`).
3. **Selectors**: Encapsulate read queries with optimized joins (`select_related()`, `prefetch_related()`) to prevent N+1 query overhead.
4. **Serializers**: DRF `ModelSerializer` with automatic field mapping, strict whitespace trimming, max length checks, and uniform validation error envelopes.
5. **Uniform Error Envelope**: Base exception handler translates standard exceptions and PostgreSQL SQLSTATE codes (`23514` check_violation, `55000` object_not_in_prerequisite_state, `23503` foreign_key_violation, `23505` unique_violation) into `{code, message, details}`.

### 2.6. Continuous Integration & Quality Gates (CI Workflow 02)

Automated verification is enforced via `.github/workflows/02-django-check.yml`:

- **Environment**: Python `3.14.7` and PostgreSQL `18.6-alpine` service container.
- **Linting & Formatting**: `ruff check .` and `ruff format --check .` (88-character line limit).
- **Type Checking**: `mypy .` with `django-stubs` and `djangorestframework-stubs` (0 errors).
- **Test Suite**: `pytest -v --cov=apps` running against a real PostgreSQL instance with line coverage enforced at `>= 80%`.
- **OpenAPI Schema Validation**: `python manage.py spectacular --validate --fail-on-warn` ensuring contract validity.

---

## 3. Consequences & Compliance

### Positive Consequences

- **Absolute Data Integrity**: PostgreSQL Schema v2 triggers, constraints, and audit functions are preserved 100% without ORM interference.
- **No Desync Risk**: Eliminates migration divergence between Django ORM and production database.
- **Developer Velocity**: Unmanaged models allow rapid query writing using Django ORM while relying on rock-solid database constraints.
- **High Test Confidence**: Pytest runs against real PostgreSQL 18.6, catching genuine constraint and trigger behaviors.

### Trade-offs & Mitigations

- **Manual Model Updates**: When database schema changes in future rounds, unmanaged models must be manually updated to mirror schema changes. *Mitigation*: Automated parity test (`tests/test_schema_parity.py`) verifies 1:1 parity (tables, views, columns, types, foreign keys) in test suite.
- **No Automated DDL**: Django's `makemigrations` cannot generate table creation scripts. *Mitigation*: Handled intentionally via `RunSQL` reading versioned SQL scripts.

---

## 4. References

- ADR-0001: Fixed Tech Stack and LTS Roadmap
- ADR-0003: Data Deletion Policy, Soft-Delete, RESTRICT, and Purge
- ADR-0004: Authentication Strategy, SPA Session Management, and Persistent Login Tokens
- ADR-0005: Local Docker Compose for PostgreSQL 18.6
- Django Documentation: `managed = False` (<https://docs.djangoproject.com/en/6.1/ref/models/options/#managed>)
- PostgreSQL 18 Documentation: Foreign Keys and Triggers (<https://www.postgresql.org/docs/18/index.html>)
