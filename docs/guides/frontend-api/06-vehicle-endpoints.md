# Frontend API Guide — Vehicle Endpoints

[← Previous: 05-parking-endpoints.md](05-parking-endpoints.md) | [↑ Back to Index](../01-frontend-api-guide.md) | [Next: 07-customer-endpoints.md →](07-customer-endpoints.md)

## 9. Details of Vehicle Management Endpoints (`Quản lý xe`)

The Vehicle Management module (`apps/vehicles`) powers the `Quản lý xe` administrative screen (`Quản lý xe — Smart Mobility.png`). It provides comprehensive fleet tracking, multi-criteria search, vehicle registration, optimistic concurrency updates, soft-deletion protected by database trigger guards (DEL-03), and formula-injection-safe CSV exports.

### 9.1 Module Architecture, Car-Only Scope & RBAC Rules

1. **Role-Based Access Control (RBAC)**:
   - **Read Operations** (`GET /api/v1/vehicle-types/`, `GET /api/v1/vehicles/`, `GET /api/v1/vehicles/{id}/`, `GET /api/v1/vehicles/summary/`, `GET /api/v1/vehicles/export/`): Allowed for both `EMPLOYEE` and `MANAGER` roles via `IsEmployeeOrManager`.
   - **Write Operations** (`POST /api/v1/vehicles/`, `PATCH /api/v1/vehicles/{id}/`, `DELETE /api/v1/vehicles/{id}/`): Allowed for both `EMPLOYEE` and `MANAGER` roles via `IsEmployeeOrManager` per Task V0, DEL-03, and SRS 4.4.3/4.4.4. Customer accounts receive HTTP `403 Forbidden` (`MSG-4.2-M01`).
   - **Customer Access**: Customer accounts (`CUSTOMER`) receive HTTP `403 Forbidden` on all vehicle management routes.
   - **Anonymous Access**: Unauthenticated calls receive HTTP `401 Unauthorized` (`MSG-4.1-M02`).
2. **Car-Only Fleet Scope (GAP TRC-FE-04-04)**:
   - The parking facility is strictly a **Car Parking Lot** (SRS v4.1, `TL-09`, `TL-20`, `TL-35`, `OQ-49`).
   - Allowed vehicle types are exclusively `CAR` (`Ô tô`) and `EV` (`Xe điện`).
   - Row 3 of the mockup displaying a motorbike (`Xe máy`) is an excluded designer mockup artifact (`GAP TRC-FE-04-04`). The backend contains no motorbike types and rejects motorbike registrations.
3. **Double-Submit CSRF Protection**:
   - All mutating requests (`POST`, `PATCH`, `DELETE`) require the `X-CSRFToken` header matching the `csrftoken` cookie. Missing or invalid tokens return HTTP `403 Forbidden` (`PROP-4.1-P06`).

---

### 9.2 Dashboard KPI Metrics (`GET /api/v1/vehicles/summary/`)

- **Purpose**: Populate the 4 KPI summary cards at the top of the `Quản lý xe` dashboard.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters (Optional)**:
  - `customer` (string): Filter KPI calculations by customer code or name substring.
  - `vehicle_type` (string): Filter KPI calculations by vehicle type code (`CAR` or `EV`).
- **Default Computation Scope**: When query parameters are omitted, returns global counts across all active, non-deleted vehicles.
- **Unified Single Source of Truth for Ticket State (TL-28.1, OQ-52)**:
  - Each vehicle has exactly one **Representative Ticket** evaluated with a 2-tier priority rule:
    - *Tier 1*: Active unexpired ticket (`status IN ('ACTIVE', 'RENEWING')` and `effective_to >= now()`).
    - *Tier 2*: Most recent non-deleted ticket by `effective_to DESC, id DESC` where `status != 'CANCELLED'`.
    - If no tickets exist or all tickets are `CANCELLED`, representative ticket is `None` (`ticket_state = 'none'`).
  - From the representative ticket, the 4 mutually exclusive ticket states are derived:
    - `valid`: `effective_to > now() + 7 days` (Badge `"Còn hạn"`).
    - `expiring_soon`: `now() <= effective_to <= now() + 7 days` (Badge `"Sắp hết hạn"`).
    - `expired`: `effective_to < now()` (Badge `"Đã hết hạn"`, excluding `CANCELLED`).
    - `none`: Vehicle has no subscription ticket or only cancelled tickets.
- **KPI Metrics Definition**:
  - `total_vehicles`: Total non-deleted vehicles registered in the system (30 on baseline seed).
  - `active_vehicles`: Vehicles currently parked in lot (`exit_time IS NULL`) OR holding a valid/expiring soon subscription ticket (`rep_ticket_state IN ('valid', 'expiring_soon')`). Total is 15 on baseline seed.
  - `expiring_soon_tickets`: Vehicles holding a representative ticket expiring within 7 days (`TICKET_EXPIRING_SOON_DAYS = 7`, 0 on baseline seed).
  - `expired_tickets`: Vehicles holding an expired representative ticket (12 on baseline seed; excluding CANCELLED tickets VT0023, VT0024, VT0025).
- **Distinction: KPI `"Đang hoạt động"` (`active_vehicles`) vs. List Table `status`**:
  - **KPI Card `"Đang hoạt động"` (`active_vehicles`)**: Operational volume metric representing all vehicles actively using lot services (either currently parked OR eligible to enter via active subscription).
    $$\text{KPI active\_vehicles} = \text{Count}(\text{status} = \text{'parked'}) + \text{Count}(\text{status} = \text{'active'}) = 10 + 5 = 15$$
  - **List Table `status` (TL-28.2)**: 3-phase partition of physical presence:
    - `parked` (`"Đang đỗ"`): Vehicle currently inside lot (`exit_time IS NULL`).
    - `active` (`"Đang hoạt động"`): Vehicle currently outside lot but has valid subscription ticket (`rep_ticket_state IN ('valid', 'expiring_soon')`).
    - `left` (`"Đã rời bãi"`): Vehicle outside lot with no valid ticket (`rep_ticket_state IN ('expired', 'none')`).
- **Live Stack Example**:

  ```http
  GET /api/v1/vehicles/summary/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "total_vehicles": 30,
    "active_vehicles": 15,
    "expiring_soon_tickets": 0,
    "expired_tickets": 12
  }
  ```

---

### 9.3 List Vehicles with Multi-Field Filtering & Pagination (`GET /api/v1/vehicles/`)

- **Purpose**: Render the primary vehicle data table with 11 columns, multi-field search filters, sorting, and pagination.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Supported Query Parameters**:
  - `code` (string): Search by vehicle code prefix or substring (e.g., `?code=XE0001`).
  - `plate` (string): Search by license plate (e.g., `?plate=43K-860.50` or `?plate=43K86050`). Normalized via `PlateRecognizer.normalize_plate` and matched against partial Trigram GIN index `idx_vehicle_plate_trgm`.
  - `customer` (string): Substring search on customer code or full name (e.g., `?customer=Trường`).
  - `vehicle_type` (string): Filter by vehicle type code (`CAR` or `EV`).
  - `ticket_type` (string): Filter by subscription type code (`DAILY`, `MONTHLY`, `QUARTERLY`, `YEARLY`).
  - `status` (string): Filter by runtime derived parking status:
    - `parked`: Vehicle currently parked in the lot (`exit_time IS NULL`).
    - `active`: Vehicle has an active subscription ticket and is outside the lot.
    - `left`: Vehicle has no active ticket and is outside the lot.
  - `ticket_state` (string): Filter by ticket validity state:
    - `valid`: Ticket valid for more than 7 days.
    - `expiring_soon`: Ticket expiring within 7 days.
    - `expired`: Ticket expired.
    - `none`: Vehicle has no associated ticket.
  - `ordering` (string): Field to sort by (`code`, `-code`, `license_plate`, `-license_plate`, `created_at`, `-created_at`). Default `-id`.
  - `page` (integer): Page number (default 1).
  - `page_size` (integer): Items per page (default 20, max 100).
- **Zero N+1 Query Guarantee**: Batch hydrates `customer`, `vehicle_type`, `ticket_type`, active parking session, and ticket validity via annotated SQL subqueries.
- **Live Stack Example**:

  ```http
  GET /api/v1/vehicles/?page=1&page_size=2 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "count": 30,
    "total_pages": 15,
    "current_page": 1,
    "page_size": 2,
    "next": "http://127.0.0.1:8000/api/v1/vehicles/?page=2&page_size=2",
    "previous": null,
    "results": [
      {
        "stt": 1,
        "id": 30,
        "code": "XE0030",
        "license_plate": "75D-216.14",
        "image_url": "/media/vehicles/xe0030.jpg",
        "customer": {
          "id": 1,
          "code": "KH0020",
          "full_name": "Sơn Thị Bích Hợp",
          "is_anonymized": false
        },
        "vehicle_type": {
          "id": 2,
          "code": "EV",
          "name": "Xe điện"
        },
        "ticket": {
          "ticket_type_code": "DAILY",
          "ticket_type_name": "Vé ngày",
          "type": {
            "code": "DAILY",
            "name": "Vé ngày"
          },
          "expires_at": "2026-11-30T12:43:47Z",
          "state": "valid",
          "state_display": "Còn hạn",
          "days_remaining": 35
        },
        "current_slot": null,
        "status": "active",
        "status_display": "Đang hoạt động",
        "row_version": 1,
        "created_at": "2026-10-26T10:00:00Z"
      },
      {
        "stt": 2,
        "id": 29,
        "code": "XE0029",
        "license_plate": "92E-227.97",
        "image_url": "/media/vehicles/xe0029.jpg",
        "customer": {
          "id": 7,
          "code": "KH0019",
          "full_name": "Lục Văn Khải",
          "is_anonymized": false
        },
        "vehicle_type": {
          "id": 1,
          "code": "CAR",
          "name": "Ô tô"
        },
        "ticket": null,
        "current_slot": null,
        "status": "left",
        "status_display": "Đã rời bãi",
        "row_version": 1,
        "created_at": "2026-10-26T10:00:00Z"
      }
    ]
  }
  ```

---

### 9.4 Vehicle Detail with 3 Information Panels (`GET /api/v1/vehicles/{id}/`)

- **Purpose**: Fetch complete vehicle specifications, owner contact block, and subscription lifecycle details for the 3 detail panels displayed when a vehicle row is selected in the UI.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Panel Mapping**:
  - **Panel 1 (`Chi tiết xe`)**: `code`, `license_plate`, `brand`, `model_name`, `color`, `image_url`, `notes`, `created_at`, `current_slot`, `status`, `row_version`.
  - **Panel 2 (`Thông tin chủ xe`)**: `customer` object (`id`, `code`, `full_name`, `phone`, `email`, `registered_vehicles_count`, `is_anonymized`). When `is_anonymized = true`, full name displays masked string per Decree 13/2023/ND-CP.
  - **Panel 3 (`Trạng thái vé`)**: `ticket` object (`ticket_type_name`, `effective_from`, `expires_at`, `days_remaining`, `progress_pct`, `is_valid`, `validity_message`).
- **Live Stack Example (`GET /api/v1/vehicles/1/`)**:

  ```http
  GET /api/v1/vehicles/1/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "id": 1,
    "code": "XE0001",
    "license_plate": "43K-860.50",
    "license_plate_norm": "43K86050",
    "brand": "Toyota",
    "model_name": "Vios 1.5G",
    "color": "Trắng",
    "image_url": "/media/vehicles/xe0001.jpg",
    "notes": "Phương tiện đăng ký gói vé định kỳ",
    "created_at": "2026-10-17T00:00:00Z",
    "updated_at": "2026-10-17T00:00:00Z",
    "row_version": 1,
    "vehicle_type": {
      "id": 1,
      "code": "CAR",
      "name": "Ô tô"
    },
    "customer": {
      "id": 16,
      "code": "KH0001",
      "full_name": "Trịnh Xuân Trường",
      "phone": "0868851325",
      "email": "trinh.xuan.truong@example.com",
      "registered_vehicles_count": 2,
      "is_anonymized": false
    },
    "ticket": {
      "ticket_type_code": "MONTHLY",
      "ticket_type_name": "Vé tháng",
      "type": {
        "code": "MONTHLY",
        "name": "Vé tháng"
      },
      "effective_from": "2026-03-31T17:00:00Z",
      "expires_at": "2026-11-30T17:00:00Z",
      "state": "valid",
      "state_display": "Còn hạn",
      "days_remaining": 36,
      "progress_pct": 85.6,
      "is_valid": true,
      "validity_message": "Vé còn hiệu lực."
    },
    "current_slot": "Tầng B1 - Zone A - A-06",
    "status": "parked",
    "status_display": "Đang đỗ"
  }
  ```

- **Not Found Example (`GET /api/v1/vehicles/999999/`)**:

  ```http
  HTTP/1.1 404 Not Found
  Content-Type: application/json

  {
    "code": "MSG-4.4.1-M01",
    "message": "Không tìm thấy dữ liệu",
    "details": {}
  }
  ```

---

### 9.5 Registering New Vehicles (`POST /api/v1/vehicles/`)

- **Purpose**: Register a new vehicle to an existing customer.
- **Required Permission**: `EMPLOYEE` or `MANAGER` (`IsEmployeeOrManager`). Customer role receives `403 Forbidden`.
- **Request Headers**:
  - `Content-Type: application/json`
  - `X-CSRFToken: [csrftoken_cookie_value]`
- **Payload Fields**:
  - `license_plate` (string, required): License plate text conforming to Vietnamese formatting rules.
  - `model_name` (string, required): Vehicle model name (e.g. `"VF8"`).
  - `vehicle_type_id` (integer, required): ID of vehicle type (1 for `CAR`, 2 for `EV`).
  - `customer_id` (integer, required): ID of active customer.
  - `code` (string, optional): Unique vehicle code (`^[A-Za-z0-9-]+$`, max 10 chars). **If omitted or blank**, the server atomically allocates the next sequential code `XE%04d` (e.g. `XE0031`).
  - `brand` (string, optional): Manufacturer brand (e.g. `"VinFast"`).
  - `color` (string, optional): Exterior color (e.g. `"Đỏ"`).
  - `image_url` (string, optional): Static photo URI.
  - `notes` (string, optional): Administrative notes.
- **Live Stack Example**:

  ```http
  POST /api/v1/vehicles/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]
  Content-Type: application/json

  {
    "license_plate": "51K-888.12",
    "model_name": "VF8",
    "brand": "VinFast",
    "color": "Đỏ",
    "vehicle_type_id": 2,
    "customer_id": 16,
    "notes": null
  }

  HTTP/1.1 201 Created
  Content-Type: application/json

  {
    "id": 31,
    "code": "XE0031",
    "license_plate": "51K-888.12",
    "license_plate_norm": "51K88812",
    "brand": "VinFast",
    "model_name": "VF8",
    "color": "Đỏ",
    "image_url": null,
    "notes": null,
    "created_at": "2026-10-26T13:00:00Z",
    "updated_at": "2026-10-26T13:00:00Z",
    "row_version": 1,
    "vehicle_type": {
      "id": 2,
      "code": "EV",
      "name": "Xe điện"
    },
    "customer": {
      "id": 16,
      "code": "KH0001",
      "full_name": "Trịnh Xuân Trường",
      "phone": "0868851325",
      "email": "trinh.xuan.truong@example.com",
      "registered_vehicles_count": 3,
      "is_anonymized": false
    },
    "ticket": null,
    "current_slot": null,
    "status": "left",
    "status_display": "Đã rời bãi"
  }
  ```

- **Conflict on Duplicate Active License Plate (`HTTP 409 Conflict`)**:

  ```http
  HTTP/1.1 409 Conflict
  Content-Type: application/json

  {
    "code": "MSG-4.3.1-M05",
    "message": "Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.",
    "details": {}
  }
  ```

- **Validation Rules for `license_plate`**:
  - **Mandatory & Non-Empty**: Cannot be empty or whitespace-only (returns `400 PROP-GEN-P01`).
  - **Length Restriction**: Length after trimming ASCII spaces must be between 5 and 20 characters (`5 <= len <= 20`). Violations return `400 PROP-4.5.1-P16` with reason `"Length must be between 5 and 20 characters."`.
  - **Strict ASCII Only**: Non-ASCII characters (e.g. Vietnamese diacritics like `Đ`, full-width unicode, emoji, tabs `\t`, newlines `\n`) are rejected before reaching the database, returning `400 PROP-4.5.1-P16` with reason `"Contains non-ASCII characters or unsupported symbols."`.
  - **Automatic Uppercase**: Valid lowercase input (e.g. `51k-992.14`) is automatically converted to uppercase (`51K-992.14`) for database persistence and consistency.
  - **Separator Syntax**: Must match regex `^[A-Z0-9][A-Z0-9 .\-]{3,18}[A-Z0-9]$`. Leading or trailing separators (`-`, `.`, space) return `400 PROP-4.5.1-P16` with reason `"Plate contains invalid characters or separator positions."`.
  - **No Consecutive Separators**: Multiple adjacent separators (`--`, `..`, `.-`, `  `) return `400 PROP-4.5.1-P16` with reason `"Consecutive separators are not allowed."`.
  - **Civilian Vehicle Standard**: Must conform to Vietnamese civilian vehicle standards (car series letters, valid province codes, strictly car/EV).

- **Invalid Raw License Plate Syntax Error Example (`HTTP 400 Bad Request`)**:

  ```http
  HTTP/1.1 400 Bad Request
  Content-Type: application/json

  {
    "code": "PROP-4.5.1-P16",
    "message": "Biển số xe có định dạng chưa được định nghĩa trong danh mục quy chuẩn hoặc thuộc nhóm cần xác minh thủ công.",
    "details": {
      "syntax_status": "INVALID_FORMAT",
      "reason": "Contains non-ASCII characters or unsupported symbols."
    }
  }
  ```

---

### 9.6 Updating Vehicle & Optimistic Concurrency Control (`PATCH /api/v1/vehicles/{id}/`)

- **Purpose**: Update mutable vehicle attributes (color, notes, model name, brand, vehicle type, customer owner).
- **Required Permission**: `EMPLOYEE` or `MANAGER` (`IsEmployeeOrManager`).
- **Immutable Fields**: `id`, `code`, `license_plate`, `license_plate_norm` cannot be altered after registration.
- **Mandatory OCC Field (`row_version`)**:
  - The request payload **must** include `row_version: int` containing the version number read during detail retrieval.
  - When the database record is updated, database trigger `trg_vehicle_row_version` automatically increments `row_version := row_version + 1`.

#### Optimistic Concurrency Control (OCC) Workflow

```text
[Frontend: User A]                         [Backend API]                       [Database]
        |                                        |                                  |
        |--- 1. GET /api/v1/vehicles/1/ -------->|                                  |
        |<-- 2. Detail with row_version: 1 ------|                                  |
        |                                        |                                  |
   (User A opens modal,                          |                                  |
    edits color to "Xanh")                       |                                  |
        |                                        |                                  |
        |                                   [User B concurrently updates record]   |
        |                                   [DB trigger increments row_version to 2]|
        |                                        |                                  |
        |--- 3. PATCH { row_version: 1 } ------->|                                  |
        |                                        |--- 4. SELECT row_version ------->|
        |                                        |<-- 5. Returns current: 2 --------|
        |                                        |                                  |
        |                                   (Version mismatch: 1 != 2)              |
        |<-- 6. HTTP 409 MSG-4.3.1-M03 ----------|                                  |
        |                                        |                                  |
   (Frontend catches 409:                        |                                  |
    Displays reload warning toast,               |                                  |
    re-fetches GET /api/v1/vehicles/1/,          |                                  |
    prompts user to reconcile edits)             |                                  |
```

- **Live Stack Example — Successful Update**:

  ```http
  PATCH /api/v1/vehicles/1/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]
  Content-Type: application/json

  {
    "row_version": 1,
    "color": "Bạc",
    "notes": null
  }

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "id": 1,
    "code": "XE0001",
    "license_plate": "43K-860.50",
    "color": "Bạc",
    "notes": null,
    "row_version": 2,
    "updated_at": "2026-10-26T13:10:00Z"
  }
  ```

- **Live Stack Example — Stale Token Conflict (`HTTP 409 Conflict`)**:

  ```http
  PATCH /api/v1/vehicles/1/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]
  Content-Type: application/json

  {
    "row_version": 1,
    "color": "Đỏ"
  }

  HTTP/1.1 409 Conflict
  Content-Type: application/json

  {
    "code": "MSG-4.3.1-M03",
    "message": "Dữ liệu hiện đang được cập nhật bởi user khác",
    "details": {}
  }
  ```

---

### 9.7 Soft-Deletion & DEL-03 Database Trigger Guards (`DELETE /api/v1/vehicles/{id}/`)

- **Purpose**: Soft delete a vehicle record from the system.
- **Required Permission**: `EMPLOYEE` or `MANAGER` (`IsEmployeeOrManager`).
- **Audit Logging**: Populates `deleted_at = now()` and `deleted_by = actor_id`.
- **Hard Delete Prevention**: Direct SQL `DELETE FROM vehicle` is permanently blocked by database trigger `trg_prevent_plain_delete_vehicle` with SQLSTATE `55000`.

#### The 3 DEL-03 Database Trigger Guards

Database trigger `trg_guard_soft_delete_and_restore_vehicle` invokes `fn_guard_soft_delete_and_restore()`, evaluating 3 deletion guards in strict order:

| Guard | Trigger Condition in Database | Mapped Error Code | HTTP Status | Response Message |
|:---:|---|:---:|:---:|---|
| **DEL-03 Guard 1** | Open session exists in `vehicle_entry_exit_log` (`exit_time IS NULL`) | `PROP-DEL-03-OPEN-SES` | `409 Conflict` | `Phương tiện đang đỗ trong bãi xe (có phiên đỗ đang mở), không được phép xóa.` |
| **DEL-03 Guard 2** | Active unexpired ticket exists in `ticket` (`status IN ('ACTIVE', 'RENEWING') AND effective_to > now()`) | `PROP-DEL-03-ACTIVE-TKT` | `409 Conflict` | `Phương tiện đang có vé đỗ xe còn hiệu lực, không được phép xóa.` |
| **DEL-03 Guard 3** | Active slot reservation exists in `slot_reservation` (`status = 'ACTIVE' AND reserved_until > now()`) | `PROP-DEL-03-ACTIVE-RSV` | `409 Conflict` | `Phương tiện đang có đặt trước vị trí đỗ xe còn hiệu lực, không được phép xóa.` |

- **Live Stack Example — Deletion Blocked by Guard 1 (Vehicle parked in lot, e.g. `XE0001`)**:

  ```http
  DELETE /api/v1/vehicles/1/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]

  HTTP/1.1 409 Conflict
  Content-Type: application/json

  {
    "code": "PROP-DEL-03-OPEN-SES",
    "message": "Phương tiện đang đỗ trong bãi xe (có phiên đỗ đang mở), không được phép xóa.",
    "details": {}
  }
  ```

- **Live Stack Example — Deletion Blocked by Guard 2 (Active ticket, e.g. `XE0007`)**:

  ```http
  DELETE /api/v1/vehicles/7/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]

  HTTP/1.1 409 Conflict
  Content-Type: application/json

  {
    "code": "PROP-DEL-03-ACTIVE-TKT",
    "message": "Phương tiện đang có vé đỗ xe còn hiệu lực, không được phép xóa.",
    "details": {}
  }
  ```

- **Live Stack Example — Successful Soft-Delete (Unencumbered vehicle, e.g. `XE0029`)**:

  ```http
  DELETE /api/v1/vehicles/29/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "code": "MSG-4.3.1-M01",
    "message": "Xóa thành công"
  }
  ```

  Upon successful soft-deletion, the vehicle immediately disappears from all list views, search queries, and lookup endpoints (`deleted_at IS NOT NULL`).

---

### 9.8 Streaming CSV Export with UTF-8 BOM (`GET /api/v1/vehicles/export/`)

- **Purpose**: Export the filtered vehicle fleet to CSV format for administrative reporting.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters**: Inherits 100% of the query filters supported by `GET /api/v1/vehicles/` (`code`, `plate`, `customer`, `vehicle_type`, `ticket_type`, `status`, `ticket_state`, `ordering`).
- **Response Headers**:
  - `Content-Type: text/csv; charset=utf-8`
  - `Content-Disposition: attachment; filename="danh_sach_phuong_tien.csv"`
- **Key Architectural Features**:
  1. **Streaming HTTP Response**: Server yields CSV records incrementally, maintaining constant $O(1)$ memory usage.
  2. **UTF-8 Byte Order Mark (BOM)**: The stream begins with UTF-8 BOM bytes (`\ufeff`). When Microsoft Excel opens the file, it automatically recognizes UTF-8 encoding and renders Vietnamese accented characters cleanly without character corruption.
  3. **Formula Injection Sanitization (CSV / DDE Protection)**: Text cells starting with formula trigger characters (`=`, `+`, `-`, `@`, `\t`, `\r`) are automatically neutralized by prefixing with a single apostrophe (`'`).
  4. **Hard Row Limit**: Enforces a strict ceiling of 5,000 rows (`MAX_EXPORT_ROWS = 5000`) to safeguard backend performance.
- **CSV Columns Layout (11 Columns)**:
  `STT,Mã xe,Biển số xe,Chủ xe,Mã khách hàng,Loại xe,Loại vé,Ngày hết hạn vé,Tình trạng vé,Vị trí đỗ,Trạng thái`
- **Frontend Download Integration Snippet**:

  ```typescript
  async function downloadVehicleCsv(filters: Record<string, string>) {
    const params = new URLSearchParams(filters);
    const response = await fetch(`/api/v1/vehicles/export/?${params.toString()}`, {
      method: "GET",
      credentials: "include",
    });

    if (!response.ok) {
      throw new Error(`Export failed: ${response.status}`);
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", "danh_sach_phuong_tien.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  }
  ```

---

### 9.9 Vehicle Types Lookup (`GET /api/v1/vehicle-types/`)

- **Purpose**: Populate vehicle type dropdown selectors in filter bars and registration forms.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Scope**: Strictly returns `CAR` (`Ô tô`) and `EV` (`Xe điện`).
- **Live Stack Example**:

  ```http
  GET /api/v1/vehicle-types/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  [
    {
      "id": 1,
      "code": "CAR",
      "name": "Ô tô",
      "description": "Standard passenger automobile"
    },
    {
      "id": 2,
      "code": "EV",
      "name": "Xe điện",
      "description": "Electric passenger automobile"
    }
  ]
  ```

---

### 9.10 Error Code & Status Reference Table for Vehicle Management

| Error Code | HTTP Status | Response Message | Trigger Condition |
|---|:---:|---|---|
| `PROP-GEN-P01` | 400 | `Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu` | Request payload validation failure (missing required field, invalid regex, plate length). |
| `PROP-4.4.4-P02` | 400 | `Khách hàng không tồn tại hoặc đã bị xóa.` | Specified `customer_id` does not exist or has been soft-deleted. |
| `MSG-4.1-M02` | 401 | `Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu` | Session cookie `sessionid` is missing or expired. |
| `MSG-4.2-M01` | 403 | `Bạn không có quyền thực hiện thao tác này.` | Logged-in user lacks necessary role (`CUSTOMER` role attempting vehicle operations, or insufficient permissions). |
| `PROP-4.1-P06` | 403 | `Mã CSRF không hợp lệ hoặc bị thiếu.` | Mutating request lacks valid `X-CSRFToken` header. |
| `MSG-4.4.1-M01` | 404 | `Không tìm thấy dữ liệu` | Vehicle ID does not exist or has been soft-deleted. |
| `MSG-4.3.1-M03` | 409 | `Dữ liệu hiện đang được cập nhật bởi user khác` | Stale `row_version` supplied in `PATCH` update (OCC contention). |
| `MSG-4.3.1-M05` | 409 | `Biển số xe đã tồn tại trong hệ thống.` | Registration of a license plate that is already active (`uq_vehicle_license_plate_active`). |
| `PROP-DEL-03-OPEN-SES` | 409 | `Phương tiện đang đỗ trong bãi xe (có phiên đỗ đang mở), không được phép xóa.` | DEL-03 Guard 1: Vehicle currently parked in parking lot (`exit_time IS NULL`). |
| `PROP-DEL-03-ACTIVE-TKT` | 409 | `Phương tiện đang có vé đỗ xe còn hiệu lực, không được phép xóa.` | DEL-03 Guard 2: Vehicle has an active unexpired subscription ticket. |
| `PROP-DEL-03-ACTIVE-RSV` | 409 | `Phương tiện đang có đặt trước vị trí đỗ xe còn hiệu lực, không được phép xóa.` | DEL-03 Guard 3: Vehicle has an active slot reservation. |
| `MSG-4.3.1-M01` | 200 | `Xóa thành công` | Successful soft-deletion of vehicle. |

---
