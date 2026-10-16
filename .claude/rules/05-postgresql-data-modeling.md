---
paths:
  - "apps/**/models.py"
  - "apps/**/models/**"
  - "apps/**/migrations/**"
---

# 05-postgresql-data-modeling.md — PostgreSQL Data Modeling & Migrations

## 1. Schema Authority & Migrations

- Django migration files are the sole authoritative definition of the database schema. Hand-written SQL DDL scripts are strictly prohibited as sources of truth.
- Every model change must be generated via `python manage.py makemigrations`.
- CI strictly verifies schema synchronization via `python manage.py makemigrations --check --dry-run`.

## 2. Naming & Data Types Conventions

- **Table Names**: Snake_case with app prefix (e.g., `tickets_ticket`, `employees_employee`).
- **Primary Keys**: Auto-incrementing BigAutoField or UUID where distributed uniqueness is required.
- **Timestamps**: Always use timezone-aware timestamps (`DateTimeField(auto_now_add=True)` and `DateTimeField(auto_now=True)`). PostgreSQL column type must be `TIMESTAMPTZ`.
- **String Columns**: Specify `max_length` strictly adhering to the SRS catalog (e.g., Họ tên 45, Địa chỉ 45, Mã nhân viên 5, SĐT 15/11).
- **Decimals / Money**: Use `DecimalField(max_digits=12, decimal_places=2)` for financial values (ticket prices, revenue). NEVER use float.

## 3. Constraints & Partial Unique Indexes

- **Soft Delete Compatibility**: Never create standard unconditional `unique=True` on fields that may be re-created after deletion (e.g., username, license plate, slot code).
- **Partial Unique Indexes**: Enforce uniqueness exclusively via `models.UniqueConstraint` scoped to active records:

  ```python
  models.UniqueConstraint(
      fields=["license_plate"],
      condition=models.Q(deleted_at__isnull=True),
      name="uniq_active_vehicle_license_plate",
  )
  ```

- **Database CHECK Constraints**: Enforce domain boundaries in PostgreSQL using `models.CheckConstraint` (e.g., slot length/width/height > 0, ticket end_date >= start_date, `CHECK (deleted_at IS NULL OR effective_to <= deleted_at)` on tickets).
- **Optimistic Concurrency Control (OCC)**: Entities subject to concurrent edits include `row_version = models.IntegerField(default=1)` automatically incremented via `BEFORE UPDATE` trigger.

## 4. Referential Integrity

- **Mandatory PROTECT**: All ForeignKey relations to business entities (`Customer`, `Employee`, `Vehicle`, `Ticket`, `ParkingSlot`) must specify `on_delete=models.PROTECT` (PostgreSQL `ON DELETE RESTRICT`).
- **No Cascade in Business Layer**: `models.CASCADE` is strictly prohibited on business data models to prevent unintended data loss cascades.
- **Composite Ownership Integrity**: Enforce composite foreign keys where sub-entity relationships require strict ownership validation (e.g., ticket binding to vehicle and owner via `(vehicle_id, customer_id)` per D3, and administrative cascading ward-district-province validation per D4).
