# Frontend API Guide — Employee Endpoints

[← Previous: 07-customer-endpoints.md](07-customer-endpoints.md) | [↑ Back to Index](../01-frontend-api-guide.md) | [Next: 09-reference-data-and-tooling.md →](09-reference-data-and-tooling.md)

## 11. Details of Employee Management Endpoints (`Quản lý nhân viên`)

The Employee Management module (`apps/employees`) implements the backend services for the `Quản lý nhân viên` administrative screen (`Quản lý nhân viên - Smart mobility.png`) and SRS sections 4.3.1–4.3.4. It delivers strict `MANAGER`-only role-based access control, 4 KPI summary cards computed from a single source of truth, employee directory listing with multi-field search and pagination, detailed profile retrieval with 3-tier administrative resolution, atomic employee and account creation with Argon2 password hashing and advisory-locked sequential code generation, optimistic concurrency control via `row_version`, and soft-deletion with DEL-01 security guards and immediate session and remember-me token revocation.

### 11.1 Module Architecture, UI Mockup & RBAC Rules

1. **Role-Based Access Control (RBAC)**:
   - **All Operations** (`GET /api/v1/positions/`, `GET /api/v1/employees/summary/`, `GET /api/v1/employees/`, `GET /api/v1/employees/{id}/`, `POST /api/v1/employees/`, `PATCH /api/v1/employees/{id}/`, `DELETE /api/v1/employees/{id}/`): Strictly restricted to `MANAGER` accounts via `[IsAuthenticated, IsManager]`.
   - **Employee & Customer Access**: Authenticated users with role `EMPLOYEE` or `CUSTOMER` receive HTTP `403 Forbidden` (`MSG-4.2-M01`).
   - **Anonymous Access**: Unauthenticated requests receive HTTP `401 Unauthorized` (`MSG-4.1-M02`).
2. **Double-Submit CSRF Protection**:
   - All state-mutating requests (`POST`, `PATCH`, `DELETE`) require the `X-CSRFToken` header matching the active `csrftoken` session cookie (`PROP-4.1-P06`).
3. **Single Source of Truth (SOT)**:
   - Dashboard KPI cards, list filters, list row counters, and profile views query the same selector foundation. Filter counts in list endpoints match independent raw database counts across all seeded and runtime-created employees.
4. **Zero PII Leakage & Raw String Validation**:
   - Password hashes, session tokens, and sensitive internal IDs are never included in responses or application logs.
   - Raw string inputs are strictly sanitized at the serializer layer before normalization or database execution: accepting valid Vietnamese diacritics while rejecting ASCII control characters, NUL bytes, zero-width characters, emojis, and look-alike non-ASCII digits with clean `400 Bad Request` and zero database exceptions logged.

---

### 11.2 Dashboard KPI Metrics (`GET /api/v1/employees/summary/`)

- **Purpose**: Populate the 4 KPI summary cards at the top of the `Quản lý nhân viên` management dashboard.
- **Required Permission**: `MANAGER` (`[IsAuthenticated, IsManager]`).
- **Query Parameters**: None.
- **Single Source of Truth (SSOT)**: Computed dynamically from tables `employee` and `position` excluding soft-deleted records (`deleted_at IS NULL`).

#### The 4 Employee KPI Cards

| Card # | UI Card Title | Metric Key in JSON | Definition |
|:---:|---|---|---|
| **1** | `Tổng nhân viên` | `total_employees` | Total count of active (`deleted_at IS NULL`) employee profiles in the system. |
| **2** | `Đang hoạt động` | `active_employees` | Count of employees with status `ACTIVE`. |
| **3** | `Không hoạt động` | `inactive_employees` | Count of employees with status `INACTIVE`. |
| **4** | `Chức vụ` | `total_positions` | Total count of active job positions (`deleted_at IS NULL`) configured in the system. |

- **Live Stack Example**:

  ```http
  GET /api/v1/employees/summary/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "total_employees": 8,
    "active_employees": 7,
    "inactive_employees": 1,
    "total_positions": 4
  }
  ```

---

### 11.3 Positions Catalog Dropdown (`GET /api/v1/positions/`)

- **Purpose**: Populate position dropdown filters on the list screen and position selector dropdowns in create/edit employee dialogs.
- **Required Permission**: `MANAGER`.
- **Response Format**: Bare JSON array of active positions deterministically ordered by `id ASC`.
- **Position Role Derivation Matrix**:
  - `QL` (`Quản lý`): Maps to account role `MANAGER`.
  - `NVVH` (`Nhân viên vận hành`): Maps to account role `EMPLOYEE`.
  - `NVTN` (`Nhân viên thu ngân`): Maps to account role `EMPLOYEE`.
  - `KTV` (`Kỹ thuật viên`): Maps to account role `EMPLOYEE`.
- **Live Stack Example**:

  ```http
  GET /api/v1/positions/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  [
    {
      "id": 1,
      "code": "QL",
      "name": "Quản lý"
    },
    {
      "id": 2,
      "code": "NVVH",
      "name": "Nhân viên vận hành"
    },
    {
      "id": 3,
      "code": "NVTN",
      "name": "Nhân viên thu ngân"
    },
    {
      "id": 4,
      "code": "KTV",
      "name": "Kỹ thuật viên"
    }
  ]
  ```

---

### 11.4 List Employees with Multi-Field Filtering & Pagination (`GET /api/v1/employees/`)

- **Purpose**: Retrieve the paginated directory table of employee records with comprehensive multi-criteria filtering.
- **Required Permission**: `MANAGER`.
- **Supported Query Parameters**:
  - `q`: Generic search query matching case-insensitively across `full_name`, `code`, or `email`.
  - `name`: Case-insensitive substring match on `full_name` with wildcard escaping.
  - `code`: Case-insensitive substring match on `code`.
  - `address`: Case-insensitive substring match on `address`.
  - `birth_from`: Filter employees born on or after `YYYY-MM-DD`.
  - `birth_to`: Filter employees born on or before `YYYY-MM-DD`.
  - `position`: Filter by position code (e.g., `QL`, `NVVH`) or position integer ID.
  - `status`: Filter by status (`ACTIVE`, `INACTIVE`).
  - `ordering`: Whitelisted sorting field (`id`, `-id`, `code`, `-code`, `full_name`, `-full_name`, `date_of_birth`, `-date_of_birth`, `created_at`, `-created_at`). Default ordering is `code ASC`.
  - `page`: Page index (default: `1`).
  - `page_size`: Records per page (default: `20`, maximum: `100`).
- **UI Table Column Mapping**:
  - `NHÂN VIÊN`: `full_name`
  - `MÃ NV`: `code`
  - `CHỨC VỤ`: `position.name`
  - `LIÊN HỆ`: `phone`, `email`
  - `KHU VỰC`: `area.district_name`, `area.province_name`
  - `TRẠNG THÁI`: `status`, `status_display`
  - `THAO TÁC`: Row actions (View, Edit, Delete)
- **Live Stack Example**:

  ```http
  GET /api/v1/employees/?status=ACTIVE&page=1&page_size=2 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "count": 7,
    "next": "http://127.0.0.1:8000/api/v1/employees/?page=2&page_size=2&status=ACTIVE",
    "previous": null,
    "results": [
      {
        "id": 1,
        "code": "NV001",
        "full_name": "Hoàng Đình Khang",
        "position": {
          "id": 1,
          "code": "QL",
          "name": "Quản lý"
        },
        "phone": "0880721788",
        "email": "hoang.dinh.khang@example.com",
        "area": {
          "district_name": "Quận Hải Châu",
          "province_name": "Thành phố Đà Nẵng"
        },
        "status": "ACTIVE",
        "status_display": "Đang hoạt động",
        "row_version": 1
      },
      {
        "id": 2,
        "code": "NV002",
        "full_name": "Lương Thị Mai Phương",
        "position": {
          "id": 2,
          "code": "NVVH",
          "name": "Nhân viên vận hành"
        },
        "phone": "0385211625",
        "email": "luong.mai.phuong@example.org",
        "area": {
          "district_name": "Quận Hải Châu",
          "province_name": "Thành phố Đà Nẵng"
        },
        "status": "ACTIVE",
        "status_display": "Đang hoạt động",
        "row_version": 1
      }
    ]
  }
  ```

---

### 11.5 Employee Profile Detail (`GET /api/v1/employees/{id}/`)

- **Purpose**: Retrieve complete personal, administrative, position, and account details for a specific employee profile.
- **Required Permission**: `MANAGER`.
- **Soft-Delete Handling**: Returns HTTP `404 Not Found` (`MSG-4.3.1-M02` or `PROP-GEN-P01`) if the record does not exist or has been soft-deleted (`deleted_at IS NOT NULL`).
- **Security & Privacy**: Linked account metadata exposes only safe operational flags (`id`, `role`, `is_active`). Password hashes, session identifiers, and internal authentication secrets are strictly excluded.
- **Live Stack Example**:

  ```http
  GET /api/v1/employees/1/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "id": 1,
    "code": "NV001",
    "full_name": "Hoàng Đình Khang",
    "date_of_birth": "1984-03-18",
    "gender": "Nam",
    "identity_card_number": "048084786891",
    "phone": "0880721788",
    "email": "hoang.dinh.khang@example.com",
    "address": "Số 114 Đường Bạch Đằng",
    "province": {
      "id": 2,
      "code": "48",
      "name": "Thành phố Đà Nẵng"
    },
    "district": {
      "id": 2,
      "code": "HC",
      "name": "Quận Hải Châu"
    },
    "ward": {
      "id": 2,
      "code": "TT",
      "name": "Phường Thạch Thang"
    },
    "position": {
      "id": 1,
      "code": "QL",
      "name": "Quản lý"
    },
    "account": {
      "id": 1,
      "role": "MANAGER",
      "is_active": true
    },
    "status": "ACTIVE",
    "status_display": "Đang hoạt động",
    "row_version": 1,
    "created_at": "2026-01-10T08:00:00Z",
    "updated_at": "2026-01-10T08:00:00Z"
  }
  ```

---

### 11.6 Create Employee & Account Atomically (`POST /api/v1/employees/`)

- **Purpose**: Atomically provision a new employee profile and its corresponding authentication account in a single database transaction.
- **Required Permission**: `MANAGER` + CSRF header.
- **Atomic Synchronization**:
  1. Creates linked `Account` with matching `email`, `phone`, and synchronized `is_active` (`True` if employee status is `ACTIVE`, `False` if `INACTIVE`).
  2. Sets `Account.role` derived from position: `QL` results in `MANAGER`; all other positions (`NVVH`, `NVTN`, `KTV`) result in `EMPLOYEE`. Client-supplied role overrides are strictly rejected.
  3. Hashes password using configured Argon2 hasher (`make_password`). Password must comply with SRS 4.3.3 / Rule 07 policy (minimum 8 characters, at least one uppercase letter, one lowercase letter, one digit, and one special symbol).
  4. Auto-generates sequential code `NV%03d` (or `NV%04d` after 999) under a transaction-level advisory lock (`pg_advisory_xact_lock`) if `code` is omitted. If provided, `code` must match regex `^NV[0-9]{3,4}$`.
  5. If employee insertion fails, the entire transaction rolls back completely, leaving zero orphan `Account` records.
- **Conflict Handling**: Unique constraint violations on `email`, `phone`, `identity_card_number`, or `code` return HTTP `409 Conflict` (`MSG-4.3.1-M05`) without echoing confidential PII values.
- **Live Stack Example**:

  ```http
  POST /api/v1/employees/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Content-Type: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]

  {
    "full_name": "Đỗ Minh Quân",
    "date_of_birth": "1995-11-09",
    "gender": "Nam",
    "identity_card_number": "048095001122",
    "phone": "0905112233",
    "email": "quan.do.new@example.net",
    "address": "Số 27 Đường Trần Đại Nghĩa",
    "province_id": 2,
    "district_id": 2,
    "ward_id": 2,
    "position_id": 2,
    "status": "ACTIVE",
    "password": "[MASKED]"
  }

  HTTP/1.1 201 Created
  Content-Type: application/json

  {
    "id": 9,
    "code": "NV009",
    "full_name": "Đỗ Minh Quân",
    "date_of_birth": "1995-11-09",
    "gender": "Nam",
    "identity_card_number": "048095001122",
    "phone": "0905112233",
    "email": "quan.do.new@example.net",
    "address": "Số 27 Đường Trần Đại Nghĩa",
    "province": {
      "id": 2,
      "code": "48",
      "name": "Thành phố Đà Nẵng"
    },
    "district": {
      "id": 2,
      "code": "HC",
      "name": "Quận Hải Châu"
    },
    "ward": {
      "id": 2,
      "code": "TT",
      "name": "Phường Thạch Thang"
    },
    "position": {
      "id": 2,
      "code": "NVVH",
      "name": "Nhân viên vận hành"
    },
    "account": {
      "id": 21,
      "role": "EMPLOYEE",
      "is_active": true
    },
    "status": "ACTIVE",
    "status_display": "Đang hoạt động",
    "row_version": 1,
    "created_at": "2026-10-27T10:00:00Z",
    "updated_at": "2026-10-27T10:00:00Z"
  }
  ```

---

### 11.7 Partial Update with OCC & DEL-01 Guards (`PATCH /api/v1/employees/{id}/`)

- **Purpose**: Partially update fields on an employee profile and propagate changes to the linked user account.
- **Required Permission**: `MANAGER` + CSRF header.
- **Key Architectural Rules**:
  1. **Mandatory OCC `row_version`**: The request payload must include `row_version`. If the provided version does not match the database, the request fails with HTTP `409 Conflict` (`MSG-4.3.1-M03`: `Dữ liệu hiện đang được cập nhật bởi user khác`).
  2. **Immutable Employee Code**: Field `code` is immutable. Attempting to modify `code` returns HTTP `400 Bad Request`.
  3. **Role & Account Synchronization**:
     - Updating `position_id` automatically re-derives `Account.role` (`QL -> MANAGER`, others `-> EMPLOYEE`).
     - Updating `email` or `phone` propagates immediately to `Account`.
     - Updating `status` (`ACTIVE` / `INACTIVE`) synchronizes `Account.is_active`.
  4. **Immediate Session Revocation on Deactivation & Bounded Performance (M5)**:
     - When `status` transitions to `INACTIVE`, all active `Session` and `RememberToken` records for the linked account are deleted immediately in the same transaction.
     - **Performance Bounds & Resource Optimization**: Session iteration streams via PostgreSQL cursor `.values_list("session_key", "session_data").iterator(chunk_size=2000)` combined with `SessionStore().decode()`, avoiding ORM model instantiation overhead. Wall-clock benchmark measured: 100 sessions ~12ms, 1,000 sessions ~29ms, 10,000 sessions ~371ms (strictly bounded < 1.0s). Sessions of other users remain 100% isolated and intact.
  5. **DEL-01 Guard Validation**:
     - Self-deactivation guard: A logged-in employee cannot deactivate their own account (`PROP-DEL-01-SELF-DEACT` -> `409 Conflict`).
     - Self-demotion guard: A logged-in manager cannot demote themselves (`PROP-DEL-01-SELF-DEMOTE` -> `409 Conflict`).
     - Last active manager guard: Deactivating or demoting the last remaining active manager is prohibited (`PROP-DEL-01-LAST-MGR-EMP` -> `409 Conflict`).
- **Live Stack Example**:

  ```http
  PATCH /api/v1/employees/9/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Content-Type: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]

  {
    "row_version": 1,
    "phone": "0905998877",
    "address": "Số 48 Đường Trần Phú"
  }

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "id": 9,
    "code": "NV009",
    "full_name": "Đỗ Minh Quân",
    "date_of_birth": "1995-11-09",
    "gender": "Nam",
    "identity_card_number": "048095001122",
    "phone": "0905998877",
    "email": "quan.do.new@example.net",
    "address": "Số 48 Đường Trần Phú",
    "province": {
      "id": 2,
      "code": "48",
      "name": "Thành phố Đà Nẵng"
    },
    "district": {
      "id": 2,
      "code": "HC",
      "name": "Quận Hải Châu"
    },
    "ward": {
      "id": 2,
      "code": "TT",
      "name": "Phường Thạch Thang"
    },
    "position": {
      "id": 2,
      "code": "NVVH",
      "name": "Nhân viên vận hành"
    },
    "account": {
      "id": 21,
      "role": "EMPLOYEE",
      "is_active": true
    },
    "status": "ACTIVE",
    "status_display": "Đang hoạt động",
    "row_version": 2,
    "created_at": "2026-10-27T10:00:00Z",
    "updated_at": "2026-10-27T10:05:00Z"
  }
  ```

---

### 11.8 Soft-Delete Employee & Account (`DELETE /api/v1/employees/{id}/`)

- **Purpose**: Perform an atomic soft-deletion of an employee profile and its associated account.
- **Required Permission**: `MANAGER` + CSRF header.
- **Atomic Deletion & Revocation**:
  1. Sets `deleted_at = timezone.now()` and `deleted_by = actor.id` on both `Employee` and linked `Account`.
  2. Sets `Account.is_active = False`.
  3. Revokes all active user sessions and remember-me tokens immediately.
- **DEL-01 Database Trigger & Service Guards**:
  - Self-deletion guard: A manager cannot delete their own profile (`PROP-DEL-01-SELF-EMP` -> HTTP `409 Conflict`).
  - Last active manager guard: Deleting the last remaining active manager is blocked (`PROP-DEL-01-LAST-MGR-EMP` -> HTTP `409 Conflict`).
  - Hard delete prevention: Database triggers `trg_prevent_plain_delete_employee` and `trg_prevent_plain_delete_account` block direct SQL `DELETE`.
- **Response Format**: Successful soft-deletion returns HTTP `200 OK` with standard confirmation envelope (`MSG-4.3.4-M01` / `MSG-4.3.1-M01`: `"Xóa thành công"`).
- **Live Stack Example**:

  ```http
  DELETE /api/v1/employees/9/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "code": "MSG-4.3.4-M01",
    "message": "Xóa thành công"
  }
  ```

---

### 11.9 Error Code & Status Reference Table for Employee Management

| Error Code | HTTP Status | Response Message | Trigger Condition |
|---|:---:|---|---|
| `PROP-GEN-P01` | 400 | `Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu` | Request payload validation failure, control characters, invalid regex format. |
| `MSG-4.3.2-M02` | 400 | `Mã nhân viên không đúng định dạng.` | Provided employee code does not match `^NV[0-9]{3,4}$`. |
| `MSG-4.3.3-M01` | 400 | `Mật khẩu phải chứa ít nhất 8 ký tự, bao gồm chữ hoa, chữ thường, số và ký tự đặc biệt` | Password does not satisfy complexity requirements. |
| `MSG-4.1-M02` | 401 | `Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu` | Session cookie `sessionid` is missing or expired. |
| `MSG-4.2-M01` | 403 | `Bạn không có quyền thực hiện thao tác này.` | User lacks `MANAGER` role (`EMPLOYEE` or `CUSTOMER` role attempting access). |
| `PROP-4.1-P06` | 403 | `Mã CSRF không hợp lệ hoặc bị thiếu.` | Mutating request lacks valid `X-CSRFToken` header. |
| `MSG-4.3.1-M02` | 404 | `Không tìm thấy dữ liệu` | Employee ID does not exist or has already been soft-deleted. |
| `MSG-4.3.1-M03` | 409 | `Dữ liệu hiện đang được cập nhật bởi user khác` | Stale `row_version` supplied in `PATCH` update (OCC contention). |
| `MSG-4.3.1-M05` | 409 | `Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.` | Unique conflict on email, phone, CCCD, or employee code. |
| `PROP-DEL-01-SELF-EMP` | 409 | `Nhân viên đang đăng nhập không được phép tự xóa hồ sơ của chính mình.` | Employee attempts to soft-delete their own account/profile. |
| `PROP-DEL-01-SELF-DEACT` | 409 | `Nhân viên đang đăng nhập không được phép tự vô hiệu hóa tài khoản của chính mình.` | Employee attempts to deactivate their own account. |
| `PROP-DEL-01-SELF-DEMOTE` | 409 | `Quản lý đang đăng nhập không được phép tự giáng chức chính mình.` | Manager attempts to demote their own account from manager to non-manager. |
| `PROP-DEL-01-LAST-MGR-EMP` | 409 | `Hệ thống phải có ít nhất một Quản lý đang hoạt động.` | Action would deactivate, demote, or delete the last active manager. |
| `MSG-4.3.4-M01` | 200 | `Xóa thành công` | Successful soft-deletion of employee and account. |

---
