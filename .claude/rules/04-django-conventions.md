---
paths:
  - "apps/**"
  - "config/**"
  - "manage.py"
---

# 04-django-conventions.md — Django & DRF Architectural Conventions

## 1. Project Layout & App Boundaries
- All functional modules reside in `apps/<module>/`:
  - `apps/accounts/`: Authentication, users, roles, password policies.
  - `apps/employees/`: Employee management (4.3).
  - `apps/customers/`: Customer management and owned vehicle lists (4.4).
  - `apps/vehicles/`: Vehicle tracking, entries, exits, plate OCR (4.5).
  - `apps/tickets/`: Ticket issuance, renewal, expiration, soft deletion (4.6).
  - `apps/parking/`: Slot management, floor layouts 1..10, slot capacity (4.8).
  - `apps/reports/`: Revenue and vehicle volume analytics (4.7).
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
   - Encapsulate read queries. Always use `select_related()` and `prefetch_related()` to eliminate N+1 query antipatterns.
4. **Serializers (`apps/<module>/serializers/`)**:
   - Validate request inputs thoroughly and return all validation errors simultaneously (Check_Quality item 8: "Các message check validate có xuất hiện cùng lúc chưa?").
   - Automatically trim leading/trailing whitespace on all string inputs before validation and storage (Check_Quality item 11: "Đã thực hiện Trim character khi input space chưa?").
   - Mark non-updatable identifiers as `read_only=True` and reject modification attempts per specification (Check_Quality item 10: "Xử lí enable/disable cho các item đã đúng theo spec chưa?").
   - Enforce `max_length` strictly at serializer and database levels to prevent truncation or obscuring of data (Check_Quality item 12: "Tất cả các item load data hiển thị trên màn hình đã test trường hợp data max length chưa?").

## 3. Standardized Error Response Format
All non-2xx responses must return a uniform JSON envelope:
```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "[PROPOSAL] Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu",
    "details": [
      {
        "field": "ten_dang_nhap",
        "message": "Tên đăng nhập không chứa ký tự đặc biệt"
      }
    ]
  }
}
```

## 4. Logging & Privacy
- Use Python's standard `logging` configured in `settings/base.py`.
- **PII & Secret Filter**: NEVER log plaintext passwords, bearer tokens, full identity card numbers (CMND/CCCD), or raw customer phone numbers.
