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

## Dashboard / Trang chủ (`/api/v1/dashboard/`)

> **Access**: Requires authentication (`IsAuthenticated`) + staff role (`IsEmployeeOrManager`). `CUSTOMER` role returns `403 Forbidden` (`MSG-4.2-M01`). Anonymous calls return `401 Unauthorized` (`MSG-4.1-M02`). Revenue KPI data is strictly restricted to `MANAGER` only (financial statistics masked as `null` for `EMPLOYEE` per Rule 01 § 2).

| Method | Endpoint | Access | Purpose |
|---|---|---|---|
| `GET` | `/api/v1/dashboard/` | `EMPLOYEE`, `MANAGER` | Full dashboard overview — returns all five data groups (`kpis`, `floors`, `traffic_chart`, `alerts`, `recent_activities`) in a single call. |
| `GET` | `/api/v1/dashboard/kpis/` | `EMPLOYEE`, `MANAGER` | Four KPI groups: slot occupancy, traffic (entries/exits/active), revenue (MANAGER only), and AI recognition rate. |
| `GET` | `/api/v1/dashboard/floors/` | `EMPLOYEE`, `MANAGER` | Occupancy percentage bars per floor (B1, B2, B3) per TL-28.6. Formula: `ROUND(100 × (occupied + reserved + charging) / operational, 1)`. |
| `GET` | `/api/v1/dashboard/traffic/` | `EMPLOYEE`, `MANAGER` | Hourly vehicle entry/exit counts for the last 24 hours (ascending order). Feeds the 24-hour line chart on the dashboard. |
| `GET` | `/api/v1/dashboard/alerts/` | `EMPLOYEE`, `MANAGER` | Up to 10 system alerts — unresolved alerts first (TL-13). Accepts optional `limit` query param (default 10, max 50). |
| `GET` | `/api/v1/dashboard/activities/` | `EMPLOYEE`, `MANAGER` | Up to 10 most recent vehicle entry/exit log events for the live activity feed. Accepts optional `limit` query param (default 10, max 50). |

### Dashboard Integration Notes

- **Authentication & CSRF**: All 6 dashboard endpoints are read-only (`GET`). Authentication relies on Django session cookies (`sessionid`). No CSRF token is required for `GET` requests.
- **Role-Based Revenue Masking (Rule 01 § 2)**:
  - When invoked by `MANAGER`, `revenue` contains: `revenue_date`, `total_revenue`, `cash_revenue`, `vietqr_revenue`, `cash_pct`, `vietqr_pct`.
  - When invoked by `EMPLOYEE`, `revenue` is strictly `null`. Frontend should conditionally hide financial cards or display "Chỉ dành cho Quản lý".
- **Floor Occupancy Bars (TL-28.6)**:
  - Formatted label: `fe_display_label` (e.g., `"Tầng B1 · 92% (184/200 chỗ)"`) for direct display in progress bar headers without client calculation.
  - Badge: `status_badge` is `"Sắp đầy"` when `occupancy_percentage >= 90.0`, otherwise `"Còn chỗ"`.
- **System Alerts (TL-13)**:
  - Unresolved alerts (`resolved_at IS NULL`) are prioritized at the top, ordered by severity (`CRITICAL` > `WARNING` > `INFO`) then descending timestamp.
- **Data Sources**: Read-only aggregation from PostgreSQL views (`v_slot_occupancy_by_floor`, `v_revenue_today_by_method`, `v_traffic_by_hour`, `v_ai_recognition_stats`) and live tables (`system_alert`, `vehicle_entry_exit_log`).

### Dashboard Response Examples

#### 1. Full Dashboard Overview (`GET /api/v1/dashboard/`)

```json
{
  "kpis": {
    "slots": {
      "total_slots": 300,
      "operational_slots": 285,
      "available_slots": 120,
      "occupied_slots": 150,
      "used_slots": 165,
      "occupancy_rate_pct": 57.9,
      "status_text": "Còn chỗ"
    },
    "traffic": {
      "today_entries": 245,
      "today_exits": 198,
      "active_parking": 47
    },
    "revenue": {
      "revenue_date": "2026-11-01",
      "total_revenue": "18500000.00",
      "cash_revenue": "6500000.00",
      "vietqr_revenue": "12000000.00",
      "cash_pct": "35.14",
      "vietqr_pct": "64.86"
    },
    "ai_recognition": {
      "total_sessions": 245,
      "ai_sessions": 231,
      "manual_sessions": 14,
      "ai_recognition_rate_pct": "94.29",
      "manual_rate_pct": "5.71",
      "avg_ai_confidence": "94.50",
      "active_auto_scan_gates": 3
    }
  },
  "floors": [
    {
      "floor_id": 1,
      "floor_code": "B1",
      "floor_name": "Tầng B1 - Xe ô tô & EV",
      "total_slots": 100,
      "operational_slots": 95,
      "used_slots": 88,
      "available_slots": 7,
      "occupancy_percentage": 92.6,
      "status_badge": "Sắp đầy",
      "fe_display_label": "Tầng B1 - Xe ô tô & EV · 93% (88/95 chỗ)"
    },
    {
      "floor_id": 2,
      "floor_code": "B2",
      "floor_name": "Tầng B2 - Ô tô vãng lai",
      "total_slots": 100,
      "operational_slots": 100,
      "used_slots": 45,
      "available_slots": 55,
      "occupancy_percentage": 45.0,
      "status_badge": "Còn chỗ",
      "fe_display_label": "Tầng B2 - Ô tô vãng lai · 45% (45/100 chỗ)"
    },
    {
      "floor_id": 3,
      "floor_code": "B3",
      "floor_name": "Tầng B3 - Ô tô tháng & dài hạn",
      "total_slots": 100,
      "operational_slots": 90,
      "used_slots": 32,
      "available_slots": 58,
      "occupancy_percentage": 35.6,
      "status_badge": "Còn chỗ",
      "fe_display_label": "Tầng B3 - Ô tô tháng & dài hạn · 36% (32/90 chỗ)"
    }
  ],
  "traffic_chart": [
    {
      "traffic_hour": "2026-11-01T00:00:00Z",
      "entry_count": 5,
      "exit_count": 2,
      "total_movements": 7
    },
    {
      "traffic_hour": "2026-11-01T01:00:00Z",
      "entry_count": 3,
      "exit_count": 1,
      "total_movements": 4
    }
  ],
  "alerts": [
    {
      "id": 14,
      "alert_type": "BLACKLIST_PLATE",
      "severity": "CRITICAL",
      "message": "Phát hiện xe thuộc danh sách đen cố gắng check-in: 51K-999.99",
      "entity_type": "VEHICLE",
      "entity_id": 102,
      "occurred_at": "2026-11-01T08:30:00Z",
      "resolved_at": null
    },
    {
      "id": 12,
      "alert_type": "OVERSTAY",
      "severity": "WARNING",
      "message": "Xe đỗ quá 72 giờ chưa check-out: 30E-123.45",
      "entity_type": "PARKING_SESSION",
      "entity_id": 554,
      "occurred_at": "2026-11-01T07:15:00Z",
      "resolved_at": null
    }
  ],
  "recent_activities": [
    {
      "id": 1205,
      "session_code": "#PK-20261101-0089",
      "license_plate": "51A-888.88",
      "direction": "IN",
      "timestamp": "2026-11-01T08:45:12Z",
      "fee_amount": "0.00",
      "recognition_source": "AI"
    },
    {
      "id": 1204,
      "session_code": "#PK-20261101-0042",
      "license_plate": "43A-567.89",
      "direction": "OUT",
      "timestamp": "2026-11-01T08:43:05Z",
      "fee_amount": "35000.00",
      "recognition_source": "AI"
    }
  ]
}
```

*(Note: When logged in as `EMPLOYEE`, `kpis.revenue` is `null`).*

#### 2. Floor Occupancy List (`GET /api/v1/dashboard/floors/`)

Returns the array of floor occupancy bars shown in `floors` above.

#### 3. Traffic 24h Chart (`GET /api/v1/dashboard/traffic/`)

Returns an array of 24 hourly data points ordered ascending by hour.

#### 4. System Alerts (`GET /api/v1/dashboard/alerts/?limit=10`)

Returns the array of alert objects (default 10, max 50).

#### 5. Recent Activity Feed (`GET /api/v1/dashboard/activities/?limit=10`)

Returns the array of recent entry/exit events (default 10, max 50).

- **HTTP Status Codes**:
  - `200 OK`: Successful data retrieval.
  - `401 Unauthorized`: Session missing or expired (`MSG-4.1-M02`).
  - `403 Forbidden`: Insufficient role — `CUSTOMER` access denied (`MSG-4.2-M01`).

## API documentation routes

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/schema/` | Serve the generated OpenAPI schema. |
| `GET` | `/api/docs/` | Open Swagger UI. |
| `GET` | `/api/redoc/` | Open ReDoc. |

Django Admin is available at `/admin/` and is not part of the REST API. Other application modules (`tickets` and `employees`) define database models and schema relationships but have no standalone CRUD management routes exposed; do not treat planned or SRS-listed operations as implemented routes until they appear in the live schema.
