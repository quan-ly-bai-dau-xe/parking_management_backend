---
paths:
  - "apps/**"
  - "config/**"
  - "manage.py"
---

# 04-django-conventions.md — Django & DRF Architectural Conventions

## 1. Project Layout & App Boundaries

- All functional modules reside in `apps/<module>/` (10 domain apps):
  - `apps/core/`: Shared base models (`TimeStampedModel`, `SoftDeleteBaseModel`, `SoftDeleteModel`), message catalog, DRF exception handler, pagination, filters, health check, and administrative boundary models (`AdministrativeProvince`, `AdministrativeDistrict`, `AdministrativeWard`).
  - `apps/accounts/`: Authentication (`Account`, `PersistentLoginToken`, `PasswordResetToken`) and RBAC permissions.
  - `apps/employees/`: Employee and position management (`Position`, `Employee`, 4.3).
  - `apps/customers/`: Customer management (`Customer`, 4.4).
  - `apps/vehicles/`: Vehicle and vehicle type management (`VehicleType`, `Vehicle`, 4.5).
  - `apps/tickets/`: Ticket types, subscriptions, renewals, and payments (`TicketType`, `Ticket`, `TicketRenewal`, `Payment`, 4.6).
  - `apps/parking/`: Lot, floor (`B1`..`F1` / `B3`), zone (`A`..`C`), slot, gate, reservation, entry/exit log, and plate blacklist (`ParkingLot`, `ParkingFloor`, `ParkingZone`, `ParkingSlot`, `SlotAllowedVehicleType`, `SlotReservation`, `ParkingGate`, `VehicleEntryExitLog`, `PlateBlacklist`, 4.8).
  - `apps/content/`: News and notifications (`News`, `Notification`).
  - `apps/audit/`: Append-only audit logs and operational system alerts (`ActivityLog`, `SystemAlert`).
  - `apps/reports/`: Unmanaged analytical view models (`8` views, 4.7).
- Configuration lives in `config/`:
  - `config/settings/base.py`: Shared core settings.
  - `config/settings/local.py`: Local development overrides (DEBUG=True).
  - `config/settings/test.py`: Isolated test settings (in-memory caching, test DB).
  - `config/settings/production.py`: Hardened production settings (DEBUG=False, strict cookie security).

## 2. Three-Tier Architectural Pattern

1. **Views / ViewSets (`apps/<module>/views/`)**:
   - Strictly thin. Responsible only for HTTP protocol negotiation, permission checks, calling serializers, invoking services/selectors, and returning HTTP responses.
   - Never write business rules or direct ORM write queries in views.
2. **Services (`apps/<module>/services/`)**:
   - Contain all write business logic, multi-table transactions (`transaction.atomic`), referential guards, and safe-delete operations.
3. **Selectors (`apps/<module>/selectors/`)**:
   - Encapsulate read queries. Always use `select_related()` and `prefetch_related()` to eliminate N+1 query anti-patterns.
4. **Serializers (`apps/<module>/serializers/`)**:
   - Validate request inputs thoroughly and return all validation errors simultaneously (Check_Quality item 8: "Các message check validate có xuất hiện cùng lúc chưa?").
   - Automatically trim leading/trailing whitespace on all string inputs before validation and storage (Check_Quality item 11: "Đã thực hiện Trim character khi input space chưa?").
   - Mark non-updatable identifiers as `read_only=True` and reject modification attempts per specification (Check_Quality item 10: "Xử lí enable/disable cho các item đã đúng theo spec chưa?").
   - Enforce `max_length` strictly at serializer and database levels to prevent truncation or obscuring of data (Check_Quality item 12: "Tất cả các item load data hiển thị trên màn hình đã test trường hợp data max length chưa?").
5. **API-First & Automatic Mapping (Meeting 16/10/2026, Points a & e)**:
   - Design serializers and OpenAPI 3.0 contracts (`drf-spectacular`) before writing service logic.
   - Strictly utilize `ModelSerializer` and serializer hydration (`validated_data`) to map data into forms, avoiding manual dictionary-to-object mappings.
   - Return mock responses using fixtures (`db/02-seed.sql`) during early integration to unblock frontend developers.

## 3. Unmanaged Models & Database Governance (Schema Authority)

- **`managed = False`**: All 28 domain tables and 8 analytical views must declare `managed = False` in their inner `Meta` class. Django migrations must never execute DDL on domain tables.
- **Primary Keys**: Use `BigAutoField` (`DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"`).
- **Foreign Keys**: Declare all ForeignKey relations in unmanaged models with `on_delete=models.DO_NOTHING` and `db_constraint=False`. All referential constraints (`ON DELETE RESTRICT`) are owned and enforced exclusively by PostgreSQL Schema v2.
- **Base Hierarchy & Soft Delete**: Inherit from `SoftDeleteModel` (for 18 soft-deletable business tables) or `SoftDeleteBaseModel` / `TimeStampedModel`. Physical `delete()` on business models is prohibited (calls `soft_delete()` or raises `PermissionDenied`). Token models (`PersistentLoginToken`, `PasswordResetToken`) are exempt and allow plain `DELETE` per TL-36 / ADR-0004.
- **Non-Editable Columns**: Mark `created_at`, `updated_at`, `row_version`, and generated columns (`license_plate_norm`) as `editable=False`.

## 4. Standardized Error Response Format & SQLSTATE Mapping

All non-2xx responses must return a uniform JSON envelope processed by `apps/core/exceptions.py`:

```json
{
  "code": "PROP-GEN-P01",
  "message": "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu",
  "details": {
    "email": [
      "Dữ liệu Email không đúng định dạng, .."
    ]
  }
}
```

- **PostgreSQL SQLSTATE Error Mapping**:
  - `23514` (`check_violation`): Parse error HINT or message to return specific business code (e.g., `PROP-4.5.2-P02`, `PROP-PAY-STATUS-TRANSITION`).
  - `55000` (`object_not_in_prerequisite_state`): Raised by custom trigger guards when preconditions are violated (e.g., modifying settled payment, moving occupied slot).
  - `23503` (`foreign_key_violation`): Mapped to referential integrity failure or active dependent records.
  - `23505` (`unique_violation`): Mapped to duplicate entity constraint violation.

## 5. Logging & Privacy

- Use Python's standard `logging` configured in `settings/base.py`.
- **PII & Secret Filter**: NEVER log plaintext passwords, bearer tokens, full identity card numbers (CMND/CCCD), or raw customer phone numbers.
