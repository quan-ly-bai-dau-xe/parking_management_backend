# Frontend API Guide — Customer Endpoints

[← Previous: 06-vehicle-endpoints.md](06-vehicle-endpoints.md) | [↑ Back to Index](../01-frontend-api-guide.md) | [Next: 08-employee-endpoints.md →](08-employee-endpoints.md)

## 10. Details of Customer Management Endpoints (`Quản lý khách hàng`)

The Customer Management module (`apps/customers`) powers the `Khách hàng` administrative screen (`Khách hàng — Smart Mobility.png`). It provides multi-criteria customer searching, 4 KPI summary cards, customer profile management with 3-tier administrative hierarchy resolution, vehicle ownership sub-grid, atomic customer-vehicle creation under advisory locks, optimistic concurrency updates via `row_version`, and soft-deletion protected by DEL-02 database triggers.

### 10.1 Module Architecture, UI Mockup & RBAC Rules

1. **Role-Based Access Control (RBAC)**:
   - **Read Operations** (`GET /api/v1/customers/`, `GET /api/v1/customers/summary/`, `GET /api/v1/customers/{id}/`): Allowed for both `EMPLOYEE` and `MANAGER` roles via `IsEmployeeOrManager`.
   - **Write Operations** (`POST /api/v1/customers/`, `PATCH /api/v1/customers/{id}/`, `DELETE /api/v1/customers/{id}/`, `POST /api/v1/customers/{customer_id}/vehicles/`): Allowed for both `EMPLOYEE` and `MANAGER` roles via `IsEmployeeOrManager` per SRS 4.4.3/4.4.4 and DEL-02.
   - **Customer Access**: Customer accounts (`CUSTOMER`) receive HTTP `403 Forbidden` (`MSG-4.2-M01`).
   - **Anonymous Access**: Unauthenticated calls receive HTTP `401 Unauthorized` (`MSG-4.1-M02`).
2. **Double-Submit CSRF Protection**:
   - All mutating requests (`POST`, `PATCH`, `DELETE`) require the `X-CSRFToken` header matching the `csrftoken` session cookie (`PROP-4.1-P06`).
3. **Vietnamese Diacritics & Trigram Acceleration (TL-41)**:
   - Full name search uses PostgreSQL GIN trigram index `idx_customer_full_name_trgm` via `DirectILike` (`full_name__ilike=f"%{name}%"`), accepting legitimate UTF-8 Vietnamese names with diacritics while safely escaping wildcards.

---

### 10.2 Dashboard KPI Metrics (`GET /api/v1/customers/summary/`)

- **Purpose**: Populate the 4 KPI summary cards at the top of the `Khách hàng` dashboard.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters**: None.
- **Single Source of Truth (SSOT)**: The selector `get_customers_summary(now)` computes metrics dynamically from table `customer` and active subscription tickets in table `ticket`. Counts strictly match list filter totals.

#### The 4 Customer KPI Cards

| Card # | Card Title | Business Definition | API Field |
|:---:|---|---|---|
| **1** | `Tổng khách hàng` | Total non-deleted customers (`deleted_at IS NULL`) | `total_customers: int` |
| **2** | `Thuê bao kích hoạt` | Non-deleted customers holding >= 1 active, unexpired subscription ticket (`effective_to >= now()`) | `active_subscribers: int` |
| **3** | `Sắp hết hạn (7 ngày)` | Non-deleted customers holding >= 1 active subscription ticket expiring within 7 days (`TL-28.5`) | `expiring_soon_subscribers: int` |
| **4** | `Blacklist/Tạm khoá` | Non-deleted customers with status `SUSPENDED` or `BLACKLISTED` | `blacklisted_or_suspended: int` |

#### Example Response (`GET /api/v1/customers/summary/`)

```http
GET /api/v1/customers/summary/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: sessionid=[MASKED]

HTTP/1.1 200 OK
Content-Type: application/json

{
  "total_customers": 20,
  "active_subscribers": 14,
  "expiring_soon_subscribers": 0,
  "blacklisted_or_suspended": 1
}
```

---

### 10.3 List Customers with Multi-Field Filtering & Pagination (`GET /api/v1/customers/`)

- **Purpose**: Query paginated customer records for the central data table.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters**:
  - `code` (string): Case-insensitive substring match on `customer.code` (for example `KH00` matches `KH0001`, `KH0002`, etc., and exact codes like `KH0001` continue to match; wildcard characters `%` and `_` are safely escaped).
  - `name` (string): Substring match on `customer.full_name` accelerated by PostgreSQL GIN trigram index.
  - `phone` (string): Substring match on `customer.phone`.
  - `identity_card` (string): Substring match on `customer.identity_card_number` (CCCD).
  - `status` (string): Filter by exact status enum (`ACTIVE`, `SUSPENDED`, `BLACKLISTED`).
  - `ordering` (string): Whitelisted sort fields: `code`, `-code`, `full_name`, `-full_name`, `created_at`, `-created_at`, `row_version`, `-row_version`, `id`, `-id`. Default: `code`.
  - `page` (integer): Page number (default: 1).
  - `page_size` (integer): Records per page (default: 20, max: 100).
- **PII Masking (`OQ-12`, Decree 13/2023/ND-CP)**:
  - If a customer is flagged `is_anonymized = True`, PII fields are automatically masked: `full_name = "Khách hàng ẩn danh"`, `phone = "***"`, `identity_card_number = "***"`.
- **Zero N+1 Query Guarantee**:
  - `vehicles_count` and `has_active_ticket` are computed via annotated subqueries in a single database query.
- **Empty State**: Returns `count: 0`, `results: []`, HTTP `200 OK` (displaying empty state illustration with message `MSG-4.4.1-M01`).

#### Example Response (`GET /api/v1/customers/?page=1&page_size=20`)

```http
GET /api/v1/customers/?page=1&page_size=20 HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: sessionid=[MASKED]

HTTP/1.1 200 OK
Content-Type: application/json

{
  "count": 20,
  "total_pages": 1,
  "current_page": 1,
  "page_size": 20,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 1,
      "code": "KH0001",
      "full_name": "Trịnh Xuân Trường",
      "phone": "0905123456",
      "identity_card_number": "048095001111",
      "status": "ACTIVE",
      "status_display": "Đang hoạt động",
      "vehicles_count": 2,
      "has_active_ticket": true,
      "row_version": 1
    }
  ]
}
```

---

### 10.4 Customer Profile Detail & Vehicles Sub-grid (`GET /api/v1/customers/{id}/`)

- **Purpose**: Render the full customer detail view, 3-tier administrative hierarchy, and registered vehicles sub-grid (SRS 4.4.2).
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Administrative Units**: Resolved with IDs and names (`province`, `district`, `ward`) via `select_related`.
- **Vehicles Sub-grid**: Reuses `get_representative_ticket_subquery` from `apps.vehicles.selectors.vehicles` to display owned vehicles with accurate representative ticket information (`code`, `ticket_type`, `expires_at`, `ticket_state`, `fe_display_status`, `remaining_days`).
- **404 Handling**: Non-existent or soft-deleted ID returns HTTP `404 Not Found` with `PROP-4.4.4-P02` (`Khách hàng không tồn tại hoặc đã bị xóa.`).

#### Example Response (`GET /api/v1/customers/1/`)

```http
GET /api/v1/customers/1/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: sessionid=[MASKED]

HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 1,
  "code": "KH0001",
  "full_name": "Trịnh Xuân Trường",
  "date_of_birth": "1979-04-12",
  "gender": "Nam",
  "identity_card_number": "048079995469",
  "phone": "0868851325",
  "email": "trinh.xuan.truong@example.com",
  "address": "Số 32 Đường Đống Đa",
  "province": {
    "id": 48,
    "code": "48",
    "name": "Thành phố Đà Nẵng"
  },
  "district": {
    "id": 1,
    "code": "HC",
    "name": "Quận Hải Châu"
  },
  "ward": {
    "id": 1,
    "code": "TT",
    "name": "Phường Thạch Thang"
  },
  "status": "ACTIVE",
  "status_display": "Đang hoạt động",
  "status_reason": null,
  "is_anonymized": false,
  "anonymized_at": null,
  "row_version": 1,
  "created_at": "2026-01-10T08:00:00Z",
  "updated_at": "2026-01-10T08:00:00Z",
  "vehicles": [
    {
      "id": 1,
      "code": "XE0001",
      "license_plate": "43A-123.45",
      "brand": "Toyota",
      "model_name": "Vios",
      "color": "Trắng",
      "vehicle_type": {
        "id": 1,
        "code": "CAR",
        "name": "Ô tô"
      },
      "ticket": {
        "code": "VT0001",
        "ticket_type": "Vé tháng",
        "expires_at": "2026-11-15T23:59:59Z",
        "ticket_state": "valid",
        "fe_display_status": "Còn hạn",
        "remaining_days": 19
      }
    }
  ]
}
```

---

### 10.5 Customer Registration with Optional Atomic Vehicles Array (`POST /api/v1/customers/`)

- **Purpose**: Register a new customer, with an optional array of vehicles created in the same atomic transaction.
- **Required Permission**: `EMPLOYEE` or `MANAGER` + `X-CSRFToken`.
- **Sequential Code Allocation**:
  - `code` is optional. When omitted, auto-generated sequentially as `KH%04d` (e.g. `KH0021`) protected by a transaction-scoped PostgreSQL advisory lock (`pg_advisory_xact_lock`).
- **Raw-String Validation**:
  - `full_name`: Accepts UTF-8 Vietnamese diacritics. Rejects ASCII control characters (`\x00`–`\x1F`, `\x7F`), zero-width Unicode characters, NUL bytes, and strings > 45 characters.
  - `identity_card_number`: 9 to 20 digits (`^[0-9]{9,20}$`).
  - `phone`: 9 to 15 digits (`^[0-9]{9,15}$`).
  - `email`: Optional RFC compliant email.
  - `gender`: `'Nam'` or `'Nữ'`.
- **All-or-Nothing Atomicity**:
  - If any vehicle in the optional `vehicles` array fails validation or violates database constraints (e.g. duplicate plate), the entire customer creation rolls back. Zero orphaned rows.
- **Consolidated Validation Errors (Rule 04)**: Returns all field validation errors together in `details`.

#### Example Request (`POST /api/v1/customers/`)

```http
POST /api/v1/customers/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Content-Type: application/json
Cookie: sessionid=[MASKED]; csrftoken=[MASKED]
X-CSRFToken: [MASKED]

{
  "full_name": "Cao Tiến Dũng",
  "identity_card_number": "048089638581",
  "phone": "0327855040",
  "email": "cao.tien.dung@example.com",
  "gender": "Nam",
  "address": "Số 54 Đường Bạch Đằng",
  "province_id": 48,
  "district_id": 1,
  "ward_id": 1,
  "vehicles": [
    {
      "license_plate": "43B-777.88",
      "model_name": "VF8",
      "vehicle_type_id": 1,
      "brand": "VinFast",
      "color": "Xanh"
    }
  ]
}
```

#### Example Response (`201 Created`)

```http
HTTP/1.1 201 Created
Content-Type: application/json

{
  "code": "KH0021",
  "full_name": "Cao Tiến Dũng",
  "identity_card_number": "048089638581",
  "phone": "0327855040",
  "email": "cao.tien.dung@example.com",
  "gender": "Nam",
  "address": "Số 54 Đường Bạch Đằng",
  "status": "ACTIVE",
  "status_display": "Đang hoạt động",
  "row_version": 1,
  "message": "Thêm mới thông tin khách hàng thành công."
}
```

---

### 10.6 Customer Partial Update & Optimistic Concurrency Control (`PATCH /api/v1/customers/{id}/`)

- **Purpose**: Partially update customer profile fields (SRS 4.4.4).
- **Required Permission**: `EMPLOYEE` or `MANAGER` + `X-CSRFToken`.
- **Optimistic Concurrency Control (OCC)**:
  - `row_version` (integer) is **mandatory** in the request body.
  - If `row_version` does not match the database version, returns HTTP `409 Conflict` with `MSG-4.3.1-M03` (`Dữ liệu hiện đang được cập nhật bởi user khác`).
- **Blacklist Status Guard**:
  - Setting `status = 'BLACKLISTED'` strictly requires a non-empty `status_reason` (`ck_customer_blacklist_reason`). Missing reason returns HTTP `400 Bad Request`.
- **Immutable Code**: Customer `code` is immutable and cannot be changed.
- **Unique Conflict Handling without PII Echo**:
  - Collisions on CCCD, phone, or email return HTTP `409 Conflict` (`MSG-4.3.1-M05`). Raw PII values are never echoed in error details.

#### Example Request (`PATCH /api/v1/customers/1/`)

```http
PATCH /api/v1/customers/1/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Content-Type: application/json
Cookie: sessionid=[MASKED]; csrftoken=[MASKED]
X-CSRFToken: [MASKED]

{
  "row_version": 1,
  "phone": "0905999888",
  "address": "Số 54 Đường Bạch Đằng"
}
```

#### Example Response (`200 OK`)

```http
HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 1,
  "code": "KH0001",
  "full_name": "Trịnh Xuân Trường",
  "phone": "0905999888",
  "address": "Số 54 Đường Bạch Đằng",
  "row_version": 2,
  "message": "Cập nhật thông tin khách hàng thành công."
}
```

---

### 10.7 Customer Soft Deletion & DEL-02 Database Trigger Guards (`DELETE /api/v1/customers/{id}/`)

- **Purpose**: Soft delete a customer record (`deleted_at = timezone.now()`, `deleted_by = actor_id`).
- **Required Permission**: `EMPLOYEE` or `MANAGER` + `X-CSRFToken`.
- **The 3 DEL-02 Database Trigger Guards**:
  Database trigger `trg_guard_soft_delete_and_restore_customer` blocks deletion with HTTP `409 Conflict` when:
  1. `PROP-4.4.5-P02`: Customer owns a vehicle currently in parking lot (`exit_time IS NULL`).
     - Message: `"Khách hàng đang có phương tiện trong bãi, không được phép xóa."`
  2. `PROP-4.4.5-P03`: Customer holds an active, unexpired subscription ticket (`effective_to > CURRENT_TIMESTAMP`).
     - Message: `"Khách hàng đang có vé xe còn hiệu lực, không được phép xóa."`
  3. `PROP-DEL-02-ACTIVE-VEH`: Customer owns active (`deleted_at IS NULL`) registered vehicles.
     - Message: `"Khách hàng đang có phương tiện hoạt động trong hệ thống, không được phép xóa."`
- **Hard DELETE Protection**: Plain SQL hard `DELETE` is blocked by database trigger `trg_prevent_plain_delete_customer` with SQLSTATE `55000`.
- **Success Response**: HTTP `200 OK` with verbatim message `MSG-4.4.5-M01` (`"Xóa thành công"`).

#### Example Response (`DELETE /api/v1/customers/1/`)

```http
DELETE /api/v1/customers/1/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: sessionid=[MASKED]; csrftoken=[MASKED]
X-CSRFToken: [MASKED]

HTTP/1.1 200 OK
Content-Type: application/json

{
  "message": "Xóa thành công"
}
```

---

### 10.8 Sub-resource: Vehicle Creation Alias (`POST /api/v1/customers/{customer_id}/vehicles/`, SCO-06)

- **Purpose**: RESTful convenience route to register a vehicle directly under a specific customer from the customer profile screen.
- **Required Permission**: `EMPLOYEE` or `MANAGER` + `X-CSRFToken`.
- **Implementation**: Thin alias delegating directly to `create_vehicle(customer_id=customer_id, ...)`.
- **Success Response**: HTTP `201 Created` with created vehicle details.

---

### 10.9 Error Code & Status Reference Table for Customer Management

| Error Code | HTTP Status | Response Message | Trigger Condition |
|---|:---:|---|---|
| `PROP-GEN-P01` | 400 | `Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu` | Request payload validation failure (missing required field, control characters, invalid regex). |
| `MSG-4.1-M02` | 401 | `Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu` | Session cookie `sessionid` is missing or expired. |
| `MSG-4.2-M01` | 403 | `Bạn không có quyền thực hiện thao tác này.` | Logged-in user lacks necessary role (`CUSTOMER` attempting customer management). |
| `PROP-4.1-P06` | 403 | `Mã CSRF không hợp lệ hoặc bị thiếu.` | Mutating request lacks valid `X-CSRFToken` header. |
| `PROP-4.4.4-P02` | 404 | `Khách hàng không tồn tại hoặc đã bị xóa.` | Customer ID does not exist or has already been soft-deleted. |
| `MSG-4.3.1-M03` | 409 | `Dữ liệu hiện đang được cập nhật bởi user khác` | Stale `row_version` supplied in `PATCH` update (OCC contention). |
| `MSG-4.3.1-M05` | 409 | `Dữ liệu đã tồn tại trong hệ thống, không thể tạo trùng lặp.` | Unique conflict on customer code, CCCD, phone, or email. |
| `PROP-4.4.5-P02` | 409 | `Khách hàng đang có phương tiện trong bãi, không được phép xóa.` | DEL-02 Guard 1: Customer has a vehicle currently in the parking lot. |
| `PROP-4.4.5-P03` | 409 | `Khách hàng đang có vé xe còn hiệu lực, không được phép xóa.` | DEL-02 Guard 2: Customer holds an active unexpired subscription ticket. |
| `PROP-DEL-02-ACTIVE-VEH` | 409 | `Khách hàng đang có phương tiện hoạt động trong hệ thống, không được phép xóa.` | DEL-02 Guard 3: Customer still owns active registered vehicles. |
| `MSG-4.4.5-M01` | 200 | `Xóa thành công` | Successful soft-deletion of customer. |

---
