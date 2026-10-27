# API Endpoint Index

This page is a compact index of API routes currently registered by the backend. It is not a specification of planned endpoints. For request and response examples, authentication details, CSRF handling, and integration guidance, see the [Frontend API Integration Guide](guides/01-frontend-api-guide.md). The running OpenAPI schema at `/api/schema/` and Swagger UI at `/api/docs/` are the runtime references.

## Authentication (`/api/v1/auth/`)

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/auth/csrf/` | Public | Initialize the CSRF cookie before state-changing requests. |
| `POST` | `/api/v1/auth/login/` | Public + CSRF | Sign in using `identifier` (email or phone), `password`, and optional `remember` boolean. Send the `csrftoken` cookie value in the `X-CSRFToken` header. |
| `POST` | `/api/v1/auth/logout/` | Public/authenticated + CSRF | End the session and revoke the presented remember-me token, if any. |
| `GET` | `/api/v1/auth/me/` | Authenticated | Return the current account profile; a valid remember-me cookie can restore a session. |

For login, first call `GET /api/v1/auth/csrf/`, retain the `csrftoken` cookie, then include its value in `X-CSRFToken` on `POST /api/v1/auth/login/`. The request field is `identifier`, not `username`. See the integration guide for complete examples and error responses.

## Health checks

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/health/` | Service health check for infrastructure. |
| `GET` | `/api/v1/health/` | Versioned health check for API clients. |

## Parking (`/api/v1/parking/`)

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/v1/parking/plate-scans/` | Scan a plate image using OCR. |
| `GET` | `/api/v1/parking/vehicle-lookup/` | Look up a vehicle by normalized plate. |
| `GET` | `/api/v1/parking/vehicle-search/` | Search vehicles by supported criteria. |
| `POST` | `/api/v1/parking/sessions/check-in/` | Check a vehicle into the parking lot. |
| `POST` | `/api/v1/parking/sessions/check-out/` | Check a vehicle out and calculate the fee. |
| `GET` | `/api/v1/parking/gates/` | List parking gates. |
| `GET` | `/api/v1/parking/sessions/` | List parking sessions. |
| `GET` | `/api/v1/parking/sessions/{id}/` | Retrieve a parking session. |

## Vehicle Management (`/api/v1/vehicles/`, `/api/v1/vehicle-types/`)

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/vehicle-types/` | `EMPLOYEE`, `MANAGER` | List allowed vehicle types for filters and registration (strictly `CAR` and `EV` in Car-Only scope). |
| `GET` | `/api/v1/vehicles/` | `EMPLOYEE`, `MANAGER` | List vehicles with multi-field filtering, search, pagination, and derived status/slot. |
| `POST` | `/api/v1/vehicles/` | `EMPLOYEE`, `MANAGER` + CSRF | Register a new vehicle. Auto-generates sequential code `XE%04d` if omitted. |
| `GET` | `/api/v1/vehicles/{id}/` | `EMPLOYEE`, `MANAGER` | Retrieve granular vehicle specifications, owner contact block, and ticket lifecycle details. |
| `PATCH` | `/api/v1/vehicles/{id}/` | `EMPLOYEE`, `MANAGER` + CSRF | Partial update of vehicle details. Enforces OCC via `row_version`. |
| `DELETE` | `/api/v1/vehicles/{id}/` | `EMPLOYEE`, `MANAGER` + CSRF | Soft delete vehicle guarded by DEL-03 database triggers. |
| `GET` | `/api/v1/vehicles/summary/` | `EMPLOYEE`, `MANAGER` | Aggregate 4 KPI metrics (total, active, expiring soon <= 7d, expired) for dashboard cards. |
| `GET` | `/api/v1/vehicles/export/` | `EMPLOYEE`, `MANAGER` | Stream CSV export with RFC 4180 formatting, UTF-8 BOM, and formula-injection neutralization. |

### Vehicle Management Integration Notes

- **Permissions & Roles**: All operations (`GET`, `POST`, `PATCH`, `DELETE`) require `IsEmployeeOrManager` (`EMPLOYEE` or `MANAGER` role). Unauthenticated calls return `401 Unauthorized` (`MSG-4.1-M02`). Insufficient permission returns `403 Forbidden` (`MSG-4.2-M01`).
- **CSRF Protection**: All mutating calls (`POST`, `PATCH`, `DELETE`) require the `X-CSRFToken` header matching the `csrftoken` session cookie. Missing or mismatched CSRF returns `403 Forbidden` (`PROP-4.1-P06`).
- **Query Parameters**:
  - `GET /api/v1/vehicles/` and `GET /api/v1/vehicles/export/` accept:
    - `code`: Case-insensitive substring match on vehicle code.
    - `plate`: Matched against `license_plate_norm` using PostgreSQL Trigram GIN index.
    - `customer`: Substring search on customer code or full name.
    - `vehicle_type`: Filter by vehicle type code (`CAR`, `EV`).
    - `ticket_type`: Filter by ticket type code (`DAILY`, `MONTHLY`, `QUARTERLY`, `YEARLY`).
    - `status`: Filter by runtime derived parking status (`parked`, `active`, `left`).
    - `ticket_state`: Filter by derived subscription state (`valid`, `expiring_soon`, `expired`, `none`).
    - `ordering`: Ordering field (`code`, `-code`, `license_plate`, `-license_plate`, `created_at`, `-created_at`).
    - `page`, `page_size`: Standard pagination parameters (`page_size` default 20, max 100).
  - `GET /api/v1/vehicles/summary/` accepts optional `customer` and `vehicle_type` filters to narrow KPI calculations.
- **Request Bodies**:
  - `POST /api/v1/vehicles/`:

    ```json
    {
      "license_plate": "51K-992.14",
      "model_name": "VF8",
      "vehicle_type_id": 1,
      "customer_id": 1,
      "code": "XE0031",
      "brand": "VinFast",
      "color": "Đỏ",
      "image_url": "/media/vehicles/xe0031.jpg",
      "notes": "Xe giao ban giám đốc"
    }
    ```

    (`code` is optional; when omitted, the server atomically allocates the next sequential code `XE%04d`).

  - `PATCH /api/v1/vehicles/{id}/`:

    ```json
    {
      "row_version": 1,
      "model_name": "VF8 Plus",
      "brand": "VinFast",
      "color": "Xanh dương",
      "notes": "Đã đổi màu sơn",
      "customer_id": 1,
      "vehicle_type_id": 1
    }
    ```

    (`row_version` is mandatory for optimistic concurrency control).
- **Optimistic Concurrency Control (OCC)**: `PATCH /api/v1/vehicles/{id}/` validates that `row_version` in the request body matches the current database record. If another user has updated the record in the interim, the API returns `409 Conflict` with `MSG-4.3.1-M03` (`Dữ liệu hiện đang được cập nhật bởi user khác`). The client must re-fetch the latest entity and re-apply changes.
- **DEL-03 Soft-Delete Database Guards**: `DELETE /api/v1/vehicles/{id}/` executes a guarded soft delete (`deleted_at = timezone.now()`, `deleted_by = actor_id`). Database triggers intercept deletions and return `409 Conflict` under 3 conditions:
  1. `PROP-DEL-03-OPEN-SES`: Vehicle has an open parking session in the lot (`exit_time IS NULL`).
  2. `PROP-DEL-03-ACTIVE-TKT`: Vehicle holds an active, unexpired subscription ticket (`effective_to > CURRENT_TIMESTAMP`).
  3. `PROP-DEL-03-ACTIVE-RSV`: Vehicle holds an active slot reservation (`reserved_until > CURRENT_TIMESTAMP`).
  Plain SQL hard `DELETE` is blocked by database trigger `trg_prevent_plain_delete_vehicle` with SQLSTATE `55000`. Successful soft-deletion returns `200 OK` with `MSG-4.3.1-M01` (`Xóa thành công`).
- **HTTP Status Codes**:
  - `200 OK`: Successful retrieval, update, or soft-delete.
  - `201 Created`: Successful vehicle creation (lowercase plate like `51k-992.14` is automatically persisted as uppercase `51K-992.14`).
  - `400 Bad Request`: Payload validation errors (`PROP-GEN-P01`), invalid raw plate syntax (`PROP-4.5.1-P16`), non-existent customer (`PROP-4.4.4-P02`), or invalid vehicle type.
    - Example for raw plate containing non-ASCII / diacritics / invalid separators (`PROP-4.5.1-P16`):

      ```json
      {
        "code": "PROP-4.5.1-P16",
        "message": "Biển số xe có định dạng chưa được định nghĩa trong danh mục quy chuẩn hoặc thuộc nhóm cần xác minh thủ công.",
        "details": {
          "syntax_status": "INVALID_FORMAT",
          "reason": "Contains non-ASCII characters or unsupported symbols."
        }
      }
      ```

  - `401 Unauthorized`: Session missing or expired (`MSG-4.1-M02`).
  - `403 Forbidden`: Insufficient role (`MSG-4.2-M01`) or invalid/missing CSRF (`PROP-4.1-P06`).
  - `404 Not Found`: Target vehicle not found or already deleted (`MSG-4.4.1-M01`).
  - `409 Conflict`: OCC version mismatch (`MSG-4.3.1-M03`), duplicate active plate or separator variant (`MSG-4.3.1-M05`), or DEL-03 delete guards (`PROP-DEL-03-*`).

## Customer Management (`/api/v1/customers/`)

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/customers/` | `EMPLOYEE`, `MANAGER` | List customers with multi-field filtering, search, ordering whitelist, pagination, and PII masking. |
| `GET` | `/api/v1/customers/summary/` | `EMPLOYEE`, `MANAGER` | Aggregate 4 KPI metrics (`total_customers`, `active_subscribers`, `expiring_soon_subscribers`, `blacklisted_or_suspended`). |
| `GET` | `/api/v1/customers/{id}/` | `EMPLOYEE`, `MANAGER` | Retrieve full customer profile, 3-tier administrative units (ID and name), and vehicles sub-grid with representative tickets. |
| `POST` | `/api/v1/customers/` | `EMPLOYEE`, `MANAGER` + CSRF | Create a customer with optional atomic vehicles array in a single transaction. Auto-generates `KH%04d` under advisory lock. |
| `PATCH` | `/api/v1/customers/{id}/` | `EMPLOYEE`, `MANAGER` + CSRF | Partial update of customer details. Enforces OCC via mandatory `row_version`, validates administrative hierarchy and status transition rules. |
| `DELETE` | `/api/v1/customers/{id}/` | `EMPLOYEE`, `MANAGER` + CSRF | Soft delete customer guarded by DEL-02 database triggers (`deleted_at`, `deleted_by`). |
| `POST` | `/api/v1/customers/{customer_id}/vehicles/` | `EMPLOYEE`, `MANAGER` + CSRF | Register a vehicle directly under the specified customer (SCO-06 alias of `POST /api/v1/vehicles/`). |

### Customer Management Integration Notes

- **Permissions & Roles**: All operations (`GET`, `POST`, `PATCH`, `DELETE`) require `IsEmployeeOrManager` (`EMPLOYEE` or `MANAGER` role). Unauthenticated calls return `401 Unauthorized` (`MSG-4.1-M02`). Insufficient permissions return `403 Forbidden` (`MSG-4.2-M01`).
- **CSRF Protection**: All mutating calls (`POST`, `PATCH`, `DELETE`) require the `X-CSRFToken` header matching the `csrftoken` session cookie. Missing or mismatched CSRF returns `403 Forbidden` (`PROP-4.1-P06`).
- **Query Parameters**:
  - `GET /api/v1/customers/` accepts:
    - `code`: Case-insensitive substring match on customer code (`customer.code`).
    - `name` (or `full_name`): Substring match on `customer.full_name` using PostgreSQL GIN trigram index (`TL-41`).
    - `phone`: Substring match on `customer.phone`.
    - `identity_card`: Substring match on `customer.identity_card_number`.
    - `status`: Exact match on customer status enum (`ACTIVE`, `SUSPENDED`, `BLACKLISTED`).
    - `ordering`: Ordering field (`code`, `-code`, `full_name`, `-full_name`, `created_at`, `-created_at`, `row_version`, `-row_version`, `id`, `-id`). Default: `code`.
    - `page`, `page_size`: Standard pagination parameters (`page_size` default 20, max 100).
- **Request Bodies**:
  - `POST /api/v1/customers/`:

    ```json
    {
      "code": "KH0021",
      "full_name": "Nguyễn Văn An",
      "identity_card_number": "048095001234",
      "phone": "0905123456",
      "email": "van.an@example.com",
      "date_of_birth": "1995-05-15",
      "gender": "Nam",
      "address": "123 Lê Duẩn",
      "province_id": 48,
      "district_id": 1,
      "ward_id": 1,
      "vehicles": [
        {
          "license_plate": "43A-999.88",
          "model_name": "VF8",
          "vehicle_type_id": 1,
          "brand": "VinFast",
          "color": "Trắng"
        }
      ]
    }
    ```

    (`code` is optional; when omitted, the server atomically allocates the next sequential code `KH%04d` under transaction advisory lock. `vehicles` array is optional; when provided, customer and all vehicles are created atomically in a single transaction).

  - `PATCH /api/v1/customers/{id}/`:

    ```json
    {
      "row_version": 1,
      "full_name": "Nguyễn Văn Bình",
      "phone": "0905987654",
      "status": "BLACKLISTED",
      "status_reason": "Vi phạm nội quy bãi xe nhiều lần",
      "province_id": 48,
      "district_id": 1,
      "ward_id": 1
    }
    ```

    (`row_version` is mandatory for optimistic concurrency control).

  - `POST /api/v1/customers/{customer_id}/vehicles/`:

    ```json
    {
      "license_plate": "43A-888.99",
      "model_name": "VF9",
      "vehicle_type_id": 1,
      "brand": "VinFast",
      "color": "Đen"
    }
    ```

- **Optimistic Concurrency Control (OCC)**: `PATCH /api/v1/customers/{id}/` validates that `row_version` in the request body matches the current database record. If another user has updated the record in the interim, the API returns `409 Conflict` with `MSG-4.3.1-M03` (`Dữ liệu hiện đang được cập nhật bởi user khác`).
- **DEL-02 Soft-Delete Database Guards**: `DELETE /api/v1/customers/{id}/` executes a guarded soft delete (`deleted_at = timezone.now()`, `deleted_by = actor_id`). Database triggers intercept deletions and return `409 Conflict` under 3 conditions:
  1. `PROP-4.4.5-P02`: Customer owns a vehicle currently parked in the lot (`exit_time IS NULL`).
  2. `PROP-4.4.5-P03`: Customer holds an active, unexpired subscription ticket (`effective_to > CURRENT_TIMESTAMP`).
  3. `PROP-DEL-02-ACTIVE-VEH`: Customer owns active (`deleted_at IS NULL`) registered vehicles.
  Plain SQL hard `DELETE` is blocked by database trigger `trg_prevent_plain_delete_customer` with SQLSTATE `55000`. Successful soft-deletion returns `200 OK` with `MSG-4.4.5-M01` (`Xóa thành công`).
- **PII Protection & Anonymization (`OQ-12`, Decree 13/2023/NĐ-CP)**:
  - Customers marked `is_anonymized = True` return masked PII: `full_name: "Khách hàng ẩn danh"`, `phone: "***"`, `identity_card_number: "***"`.
  - PII values are strictly omitted from exception messages, error `details`, and application logs.
- **HTTP Status Codes**:
  - `200 OK`: Successful retrieval, update, or soft-delete.
  - `201 Created`: Successful customer or vehicle creation.
  - `400 Bad Request`: Payload validation errors (`PROP-GEN-P01`), invalid name format/control chars, missing blacklist reason, or invalid administrative hierarchy.
  - `401 Unauthorized`: Session missing or expired (`MSG-4.1-M02`).
  - `403 Forbidden`: Insufficient role (`MSG-4.2-M01`) or invalid/missing CSRF (`PROP-4.1-P06`).
  - `404 Not Found`: Target customer not found or already deleted (`PROP-4.4.4-P02` / `PROP-4.4.5-P01`).
  - `409 Conflict`: OCC version mismatch (`MSG-4.3.1-M03`), unique conflict on code, CCCD, phone, or email (`MSG-4.3.1-M05`), or DEL-02 delete guards (`PROP-4.4.5-P02`, `PROP-4.4.5-P03`, `PROP-DEL-02-ACTIVE-VEH`).

## API documentation routes

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/schema/` | Serve the generated OpenAPI schema. |
| `GET` | `/api/docs/` | Open Swagger UI. |
| `GET` | `/api/redoc/` | Open ReDoc. |

Django Admin is available at `/admin/` and is not part of the REST API. Other application modules (`tickets`, `employees`, and `reports`) define database models and schema relationships but have no standalone CRUD management routes exposed; do not treat planned or SRS-listed operations as implemented routes until they appear in the live schema.
