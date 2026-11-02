# Frontend & SRS Requirements Traceability Matrix

Traceability matrix for `parking_management_backend` (Round 28). Cross-references 100% of **11 UI design files** (`Parking Project`) and **SRS v4.1** (Sections 4.1–4.8, NFRs) against [`db/01-schema.sql`](../../db/01-schema.sql) and [`db/02-seed.sql`](../../db/02-seed.sql).

---

## 1. Traceability Methodology & UI Assets

- **`COVERED`**: Directly mapped to schema objects (tables, columns, constraints, FKs, views).
- **`DERIVED`**: Computed dynamically at runtime via SQL or serializers per **TL-28**.
- **`GAP`**: Variations resolved by Team Lead decisions (`TL-01`–`TL-41`).
- **Trigram Rule (TL-41, G4)**: Query GIN trigram columns via direct `col ILIKE '%x%'` (`Bitmap Index Scan`); avoid `lower(col) LIKE ...` (forces Seq Scan).

### Authoritative UI Design Files (11 Files in `Parking Project`)

1. `login-container.png`
2. `Trang chủ — Smart Mobility.png`
3. `Khách hàng — Smart Mobility.png`
4. `Quản lý xe — Smart Mobility.png`
5. `Lịch sử ra/vào — Smart Mobility.png` (Windows: `Lịch sử ra\vào — Smart Mobility.png`)
6. `Sơ đồ bãi đậu xe — Smart Mobility.png`
7. `Quản lý vé — Smart Mobility.png`
8. `Quản lý nhân viên - Smart mobility.png`
9. `Main Page.png`
10. `Vector.png`
11. `clarity_edit-line.png`

---

## 2. Frontend Screen Traceability Matrix (67 Items)

| ID | Element | Target Object | Status | Decision / Logic |
|---|---|---|:---:|---|
| TRC-FE-01-01 | Login ID | account(email,phone) | COVERED | Lowercase lookup (TL-01,21) |
| TRC-FE-01-02 | Password | account.password_hash | COVERED | Argon2 hash (OQ-01) |
| TRC-FE-01-03 | Remember Login | persistent_login_token | COVERED | Split-token (OQ-01,TL-36) |
| TRC-FE-01-04 | Forgot Password | password_reset_token | COVERED | Timed token (OQ-84,TL-36) |
| TRC-FE-01-05 | Register Link | account, customer | COVERED | Auto-create account (TL-01) |
| TRC-FE-01-06 | Hero Banner | N/A (UI asset) | COVERED | UI asset (TL-16) |
| TRC-FE-02-01 | Slot KPI (342/550) | v_slot_occupancy_by_floor | COVERED | Occupancy (TL-14) |
| TRC-FE-02-02 | Traffic KPI (52 in) | vehicle_entry_exit_log | DERIVED | Daily count (entry >= TODAY) |
| TRC-FE-02-03 | Revenue KPI (150k) | v_revenue_today_by_method | COVERED | Daily sum (TL-07,14) |
| TRC-FE-02-04 | AI KPI (98.4%) | v_ai_recognition_stats | COVERED | AI ratio (TL-06,14) |
| TRC-FE-02-05 | Activity Feed | vehicle_entry_exit_log, gate | COVERED | Feed log (TL-06) |
| TRC-FE-02-06 | Floor Bars (B1 92%) | v_slot_occupancy_by_floor | DERIVED | Occupancy bar (TL-28.6,29) |
| TRC-FE-02-07 | Traffic Chart 24h | v_traffic_by_hour | COVERED | Hourly traffic (TL-14) |
| TRC-FE-02-08 | Emergency Alerts | system_alert, blacklist | COVERED | Alerts (TL-08,13) |
| TRC-FE-03-01 | Total Customers | apps/customers/views/customers.py (`GET /api/v1/customers/summary/`) | COVERED | v_customer_status_summary count (TL-08) |
| TRC-FE-03-02 | Active Subscribers | apps/customers/views/customers.py (`GET /api/v1/customers/summary/`) | DERIVED | Active subscription ticket holders (TL-28.5) |
| TRC-FE-03-03 | Expiring Soon (7d) | apps/customers/views/customers.py (`GET /api/v1/customers/summary/`) | DERIVED | Expiring <= 7d subscription holders (TL-28.5) |
| TRC-FE-03-04 | Blacklist/Suspended | apps/customers/views/customers.py (`GET /api/v1/customers/summary/`) | COVERED | customer.status IN ('SUSPENDED', 'BLACKLISTED') (TL-08) |
| TRC-FE-03-05 | Customer Filters | apps/customers/views/customers.py (`GET /api/v1/customers/`) | COVERED | Trigram ILIKE & prefix filters: code, name, phone, idcard (TL-31, 41) |
| TRC-FE-03-06 | Customer Table | apps/customers/views/customers.py (`GET /api/v1/customers/`) | COVERED | Paginated table envelope with vehicles_count, has_active_ticket, row_version, PII masking (TL-15, OQ-12) |
| TRC-FE-04-01 | Vehicle Filters | vehicle, vehicle_type, ticket | COVERED | Indexed FKs (TL-31) |
| TRC-FE-04-02 | Vehicle KPIs | vehicle, ticket | DERIVED | State/validity (TL-28) |
| TRC-FE-04-03 | Vehicle Grid | vehicle, customer, ticket, slot | COVERED | Profile (TL-09) |
| TRC-FE-04-04 | Mockup "Xe máy" | vehicle_type | GAP | Cars only (CAR, EV) (TL-20,35) |
| TRC-FE-04-05 | Derived Status | vehicle_entry_exit_log, ticket | DERIVED | Derived status (TL-28.2) |
| TRC-FE-04-06 | Vehicle Detail | vehicle(brand,model,color,date) | COVERED | Attributes (TL-09) |
| TRC-FE-04-07 | Owner Detail | customer, vehicle summary | COVERED | Contact & vehicles |
| TRC-FE-04-08 | Ticket Lifecycle | ticket, ticket_type | DERIVED | Days & % (TL-28.3) |
| TRC-FE-05-01 | Session Filters | vehicle_entry_exit_log | COVERED | Indexed (TL-05,31) |
| TRC-FE-05-02 | Session Code | vehicle_entry_exit_log.session_code | COVERED | Unique code (TL-05) |
| TRC-FE-05-03 | Plate & Photos | vehicle_entry_exit_log(plate,photos) | COVERED | Plate & URLs (TL-06) |
| TRC-FE-05-04 | Timestamps in/out | vehicle_entry_exit_log(entry, exit) | COVERED | TIMESTAMPTZ (TL-34) |
| TRC-FE-05-05 | Parking Duration | vehicle_entry_exit_log | DERIVED | Duration interval (TL-28.4) |
| TRC-FE-05-06 | Parking Fee | vehicle_entry_exit_log.fee_amount | COVERED | Fee NUMERIC(12,2) (TL-05) |
| TRC-FE-05-07 | ALPR Camera Scan | apps/parking/views/scans.py (`POST /api/v1/parking/plate-scans/`) | COVERED | Round 32 Fast-ALPR scan + Pillow security validation |
| TRC-FE-05-08 | Auto Vehicle & Customer Fill | apps/parking/views/lookup.py (`GET /api/v1/parking/vehicle-lookup/`) | COVERED | Round 32 Exact lookup by license_plate_norm (TL-17) |
| TRC-FE-05-09 | Check-in Action | apps/parking/views/sessions.py (`POST /api/v1/parking/sessions/check-in/`) | COVERED | Round 32 Session creation (#PK-YYYYMMDD-NN), blacklist guard |
| TRC-FE-05-10 | Check-out & Tariff Payment | apps/parking/views/sessions.py (`POST /api/v1/parking/sessions/check-out/`) | COVERED | Round 32 TL-50 tariff Decimal, atomic payment row |
| TRC-FE-05-11 | Gate Selection | apps/parking/views/gates.py (`GET /api/v1/parking/gates/`) | COVERED | Round 32 Active barrier gates list |
| TRC-FE-05-12 | Modal Tìm Xe (Unified Search) | apps/parking/views/search.py (`GET /api/v1/parking/vehicle-search/`) | COVERED | Round 32 Task 9 multi-field search (TL-41 GIN trigram) |
| TRC-FE-06-01 | Hierarchy 4-lvl | lot, floor, zone, slot | COVERED | 4-level model (TL-02,29) |
| TRC-FE-06-02 | Slot Filters | parking_slot, allowed_type | COVERED | Filters (TL-37) |
| TRC-FE-06-03 | Slot Stats KPI | v_slot_occupancy_by_floor | COVERED | Counts (TL-14) |
| TRC-FE-06-04 | 2D Grid (A1-B08) | parking_slot(map_row, map_col) | COVERED | Grid coords (TL-02,03) |
| TRC-FE-06-05 | Slot Live States | parking_slot.status, triggers | COVERED | Sync guards (TL-03) |
| TRC-FE-06-06 | Slot Reservation | slot_reservation | COVERED | Exclusion (TL-04) |
| TRC-FE-06-07 | Manual Slot Action | parking_slot, guard triggers | COVERED | Guarded (TL-03,38) |
| TRC-FE-06-08 | Activity Feed | activity_log | COVERED | Append-only (TL-12) |
| TRC-FE-07-01 | Ticket Filters | ticket, customer, vehicle, slot | COVERED | Search indexes (TL-31) |
| TRC-FE-07-02 | Ticket Badges | ticket.status | COVERED / DERIVED | Enum / Derived (TL-28.1) |
| TRC-FE-07-03 | Slot Location | parking_floor.name, slot.code | DERIVED | Floor + slot code (TL-29) |
| TRC-FE-07-04 | Dialog 1: Add | ticket, payment | COVERED | Issue ticket (TL-10,38) |
| TRC-FE-07-05 | Dialog 2: Renew | ticket_renewal, payment | COVERED | Renewal flow (TL-10) |
| TRC-FE-07-06 | Dialog 3: Detail | ticket, renewal, employee | COVERED | Detail view |
| TRC-FE-08-01 | Employee KPIs | employee, position | COVERED | Staff counts (`GET /api/v1/employees/summary/`, TL-11) |
| TRC-FE-08-02 | Employee Filters | employee(code, name, email, pos) | COVERED | Staff lookup (`GET /api/v1/employees/`, TL-31) |
| TRC-FE-08-03 | Employee Code | employee.code, ck constraint | COVERED | Regex `^NV[0-9]{3,4}$`, advisory lock `NV%03d`/`NV%04d` (TL-11) |
| TRC-FE-08-04 | Four Positions | position | COVERED | Positions (`GET /api/v1/positions/`, TL-11) |
| TRC-FE-08-05 | Employee Area | district, province | COVERED | 3 tiers resolution (`GET /api/v1/employees/{id}/`, TL-15,30) |
| TRC-FE-08-06 | Employee Status | employee.status | COVERED | ACTIVE/INACTIVE (`PATCH /api/v1/employees/{id}/`, TL-11) |
| TRC-FE-08-07 | Delete Emp Guard | employee.deleted_at, trigger | COVERED | Soft delete (`DELETE /api/v1/employees/{id}/`, DEL-01) |
| TRC-FE-09-01 | Executive KPIs | v_slot_occupancy_by_floor, payment | COVERED | Aggregation (TL-14) |
| TRC-FE-09-02 | Gate Scanners | parking_gate, log | COVERED | Gate scans (TL-06) |
| TRC-FE-09-03 | Floor Tab (B1-B3) | parking_floor | COVERED | Floor tabs (TL-02,29) |
| TRC-FE-09-04 | Hero Marketing | N/A (UI asset) | COVERED | UI copy (TL-16) |
| TRC-FE-10-01 | Trash Icon 17x17 | N/A (UI icon asset) | COVERED | Delete modal (`Vector.png`, TL-16) |
| TRC-FE-10-02 | Edit Icon 18x18 | N/A (UI icon asset) | COVERED | Edit modal (`clarity_edit-line.png`, TL-16) |

---

## 3. SRS v4.1 Functional & Non-Functional Traceability Matrix (45 Items)

| ID | Requirement | Target Object | Status | Guard & Logic |
|---|---|---|:---:|---|
| TRC-SRS-01-01 | Login by ID/Password (4.1.1) | account, customer, employee | COVERED | Case-insensitive email or normalized phone (TL-01, TL-52) |
| TRC-SRS-01-02 | Invalid Credential (4.1.1) | MSG-4.1-M02 | COVERED | 'Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu' (401, uniform anti-timing) |
| TRC-SRS-01-03 | Special Chars Msg (4.1.1) | MSG-4.1-M01 | NOT APPLICABLE | Email/Phone requires @, ., -; exempt per TL-52/D3 to prevent account enumeration |
| TRC-SRS-01-04 | Persistent Login (4.1.1) | persistent_login_token | COVERED | Split-token with 30s grace window in token_hash (OQ-01, OQ-87, TL-36, TL-52) |
| TRC-SRS-02-01 | Role-Based Access (4.2.1) | account.role, ck constraint | COVERED | Enum roles (TL-01) |
| TRC-SRS-02-02 | Manager vs Staff Menu (4.2.1) | API Permissions / DRF | COVERED | Manager only (OQ-45) |
| TRC-SRS-03-01 | Employee List & Filter (4.3.1) | apps/employees/views/employees.py (`GET /api/v1/employees/`) | COVERED | Filter by q, name, code, address, birth dates, position, status with zero N+1 (TL-11) |
| TRC-SRS-03-02 | Add Employee Form (4.3.2) | apps/employees/views/employees.py (`POST /api/v1/employees/`) | COVERED | Atomic Employee+Account creation, Argon2, role derivation, advisory lock NV code (TL-15) |
| TRC-SRS-03-03 | Edit Employee Profile (4.3.3) | apps/employees/views/employees.py (`PATCH /api/v1/employees/{id}/`) | COVERED | OCC row_version, immutable code, account sync & session revocation, DEL-01 guards |
| TRC-SRS-03-04 | Delete Employee (DEL-01, 4.3.4) | apps/employees/views/employees.py (`DELETE /api/v1/employees/{id}/`) | COVERED | Soft-delete Employee+Account, DEL-01 triggers -> 409, immediate session revocation (TL-25) |
| TRC-SRS-03-05 | Employee Delete Msgs (4.3.4) | MSG-4.3.4-M01, MSG-4.3.1-M01, PROP-DEL-01-* | COVERED | 'Xóa thành công' (200), DEL-01 trigger guards mapped to 409 Conflict |
| TRC-SRS-04-01 | Customer Search (4.4.1) | apps/customers/views/customers.py (`GET /api/v1/customers/`) | COVERED | Search by code, trigram name, phone, CCCD, status with standard pagination (TL-31, 41) |
| TRC-SRS-04-02 | View Customer Cars (4.4.2) | apps/customers/views/customers.py (`GET /api/v1/customers/{id}/`) | COVERED | Customer profile, administrative hierarchy, vehicles sub-grid with representative tickets |
| TRC-SRS-04-03 | Add Customer & Cars (4.4.3) | apps/customers/views/customers.py (`POST /api/v1/customers/`) | COVERED | Atomic creation of customer and optional vehicle array under KH%04d advisory lock |
| TRC-SRS-04-04 | Edit Customer Profile (4.4.4) | apps/customers/views/customers.py (`PATCH /api/v1/customers/{id}/`) | COVERED | Partial update enforced by OCC row_version, blacklist status_reason guard |
| TRC-SRS-04-05 | Delete Customer (DEL-02, 4.4.5) | apps/customers/views/customers.py (`DELETE /api/v1/customers/{id}/`) | COVERED | Guarded soft-delete (parked vehicles, active tickets, active vehicles) returning 409 (TL-25) |
| TRC-SRS-04-06 | PII Anonymization (4.4.5) | apps/customers/serializers/customers.py | COVERED | Masking name, phone, CCCD when is_anonymized=True per Decree 13/2023/NĐ-CP (OQ-12) |
| TRC-SRS-05-01 | Vehicle Entry Check-in (4.5.1) | vehicle_entry_exit_log, guard (`POST /api/v1/parking/sessions/check-in/`) | COVERED | Check-in, session_code, blacklist guard (Round 32) |
| TRC-SRS-05-02 | Exit & Payment (4.5.1) | vehicle_entry_exit_log, payment (`POST /api/v1/parking/sessions/check-out/`) | COVERED | Check-out, TL-50 tariff Decimal, atomic payment (Round 32) |
| TRC-SRS-05-03 | Entry Guard Msgs (4.5.1) | MSG-4.5.1-M01..M03, PROP-4.5.1-P01..P12 | COVERED | Verbatim M03 fix ('lỗi kết nối'), mapped trigger exceptions (Round 32) |
| TRC-SRS-05-04 | Parking Visual Grid (4.5.2) | lot, floor, zone, slot | COVERED | 4-level map (TL-02) |
| TRC-SRS-05-05 | Slot Maint Guard (4.5.2) | MSG-4.5.2-M02, PROP-4.5.2-P01 | COVERED | 'Vị trí này đang bảo trì, chọn vị trí khác' |
| TRC-SRS-05-06 | Offline Plate Scan ALPR (4.5.1) | apps/parking/views/scans.py (`POST /api/v1/parking/plate-scans/`) | COVERED | Offline Fast-ALPR OCR, Pillow magic validation & EXIF strip (Round 32) |
| TRC-SRS-05-07 | Exact Vehicle Lookup (4.5.1) | apps/parking/views/lookup.py (`GET /api/v1/parking/vehicle-lookup/`) | COVERED | Exact match on license_plate_norm, parking position, ticket (Round 32) |
| TRC-SRS-05-08 | Vehicle Search Modal (Task 9) | apps/parking/views/search.py (`GET /api/v1/parking/vehicle-search/`) | COVERED | Multi-field search (q, name, phone, plate) utilizing TL-41 GIN trigram (Round 32) |
| TRC-SRS-06-01 | Ticket List & Expiry (4.6.1) | ticket, ticket_type | COVERED / DERIVED | Filter/derived (TL-28) |
| TRC-SRS-06-02 | Issue / Buy Ticket (4.6.2) | ticket, payment | COVERED | Issue ticket (TL-10,38) |
| TRC-SRS-06-03 | Ticket Renewal Flow (4.6.3) | ticket_renewal, ticket | COVERED | Renewal (OQ-52) |
| TRC-SRS-06-04 | Delete Ticket (DEL-04, 4.6.4) | ticket.deleted_at, guard | COVERED | Expired only (TL-25) |
| TRC-SRS-06-05 | Delete Ticket Msgs (4.6.4) | MSG-4.6.4-M01..M03 | COVERED | 'Xóa vé thành công', 'Lỗi kết nối CSDL' |
| TRC-SRS-07-01 | Revenue Statistics (4.7.1) | v_revenue_statistics, stat fn | COVERED | Sum revenue (TL-07,27) |
| TRC-SRS-07-02 | Traffic Statistics (4.7.2) | v_vehicle_traffic_daily, stat fn | COVERED | Daily traffic (TL-27) |
| TRC-SRS-07-03 | Export Reports (4.7.1/2) | API ViewSet export | COVERED | Export (TL-27) |
| TRC-SRS-08-01 | Slot List & Dimensions (4.8.1) | parking_slot, parking_zone | COVERED | Dimensions/types (TL-37) |
| TRC-SRS-08-02 | Add Parking Slot (4.8.2) | parking_slot, allowed_type | COVERED | Validation (TL-02,37) |
| TRC-SRS-08-03 | Edit Parking Slot (4.8.3) | parking_slot, row_version | COVERED | OCC row_version |
| TRC-SRS-08-04 | Slot Detail View (4.8.4) | parking_slot, allowed_type | COVERED | Dimensions/EV (TL-37) |
| TRC-SRS-08-05 | Delete Slot (DEL-05, 4.8.5) | parking_slot.deleted_at, guard | COVERED | Guarded delete (TL-25) |
| TRC-SRS-09-01 | Administrative Units (NFR) | province, district, ward | COVERED | VN admin units (TL-15) |
| TRC-SRS-09-02 | News & Announcements (NFR) | news | COVERED | News (TL-15) |
| TRC-SRS-09-03 | In-App Notifications (NFR) | notification | COVERED | Notifications (TL-15) |
| TRC-SRS-09-04 | Automated ALPR Gates (NFR) | parking_gate | COVERED | ALPR gates (TL-06) |
| TRC-SRS-09-05 | Blacklist & Debt (NFR) | plate_blacklist | COVERED | Blacklist (TL-08) |
| TRC-SRS-09-06 | Multi-Target Payments (NFR) | payment | COVERED | Payment link (TL-39) |
| TRC-SRS-09-07 | Activity Log Audit (NFR) | activity_log | COVERED | Audit log (TL-12) |

---

### 3.1. Detailed Traceability for SRS Section 4.1 (Login Screen, Actions & Messages)

#### A. Field Inventory (REQ-4.1-F01..F04)

| Field ID | SRS Field Name | Frontend Label | Required | Data Type / Format | Implementation & Database Target | Status | Decision Reference |
|---|---|---|:---:|---|---|:---:|---|
| **REQ-4.1-F01** | Tên đăng nhập | Email hoặc Số điện thoại | Yes | Text (`VARCHAR(100)` / `VARCHAR(15)`) | `POST /api/v1/auth/login/` field `identifier`. Authenticated against `account.email` (via case-insensitive expression index `uq_account_email_active` on `lower(email)`) OR `account.phone` (`^[0-9]{9,15}$`). | **COVERED** | `TL-01`, `TL-21`, `TL-52` |
| **REQ-4.1-F02** | Mật khẩu | Mật khẩu | Yes | Password string | `POST /api/v1/auth/login/` field `password`. Verified via primary `Argon2PasswordHasher` (`account.password_hash`). | **COVERED** | `OQ-01`, `TL-52` |
| **REQ-4.1-F03** | Ghi nhớ mật khẩu | Ghi nhớ đăng nhập | No | Boolean (default: `false`) | `POST /api/v1/auth/login/` field `remember`. When true, generates a secure 256-bit token (`secrets.token_hex(32)`), stores SHA-256 composite hash in `persistent_login_token.token_hash VARCHAR(255)`, sets `parking_remember_token` cookie (`HttpOnly=True`, `SameSite='Lax'`, 30-day TTL). Replaces insecure plaintext cookie rule with OWASP ASVS persistent login pattern. | **COVERED** | `OQ-01`, `OQ-87`, `TL-36`, `TL-52`, `ADR-0004` |
| **REQ-4.1-F04** | Quên mật khẩu | Quên mật khẩu? | N/A | Navigation link | Triggers password reset workflow using `password_reset_token` (`account_id`, `token_hash`, `expires_at`). | **COVERED** | `OQ-84`, `TL-36` |

#### B. Action Inventory (ACT-4.1-A01..A02)

| Action ID | SRS Action Name | Frontend Element | Trigger & Workflow | Implementation Target | Status | Decision Reference |
|---|---|---|---|---|:---:|---|
| **ACT-4.1-A01** | Log in | Nút "Đăng nhập" | Click "Đăng nhập" after entering identifier and password. Successful login navigates to system home, cycles session key (`request.session.cycle_key()`), updates `last_login`, sets `sessionid` and optional `parking_remember_token`. Failure returns standard error envelope. | `POST /api/v1/auth/login/` (`LoginView`) | **COVERED** | `TL-52` |
| **ACT-4.1-A02** | Reset | Clear inputs | Clears entered identifier and password fields. Managed on client side by SPA state; backend REST API is stateless with respect to unsubmitted form inputs. | Client SPA UI interaction | **COVERED** | `TL-52` |

#### C. Messages Traceability (MSG-4.1-M01..M03 & PROP-4.1-P01..P03, P06)

| Message ID | Type | Message Content | Trigger Condition & Behavior | HTTP Status | Status | Decision & Rationale |
|---|---|---|---|:---:|:---:|---|
| **MSG-4.1-M01** | Verbatim SRS | `Tên đăng nhập không chứa ký tự đặc biệt` | Entering invalid/special characters in login identifier | 401 | **NOT APPLICABLE** | **Exempt per Decision D3 / TL-52**: Under Frontend-First design (`TL-01`), login is by "Email hoặc Số điện thoại". Email addresses strictly require special characters (`@`, `.`, `+`, `_`, `-`) and phone numbers accept formatting separators (`-`, ` `, `.`). Rejecting special characters prevents valid email authentication. Furthermore, returning character-specific errors aids credential enumeration. All invalid or non-existent identifiers uniformly receive HTTP 401 with `MSG-4.1-M02`. |
| **MSG-4.1-M02** | Verbatim SRS | `Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu` | Incorrect password, non-existent account, inactive account (`is_active = FALSE`), or soft-deleted account (`deleted_at IS NOT NULL`). | 401 Unauthorized | **COVERED** | Byte-identical envelope returned across all credential failure modes. Anti-timing defense executes dummy Argon2 hash when account is not found (`RSK-03`). |
| **MSG-4.1-M03** | Verbatim SRS | `Xin nhập đầy đủ Tên đăng nhập và Mật khẩu` | Empty string, whitespace-only, missing key, or invalid data types in login request payload. | 400 Bad Request | **COVERED** | DRF serializer validation enforced in `LoginSerializer`. |
| **PROP-4.1-P01** | Proposal | `Quá nhiều lần đăng nhập không thành công, vui lòng thử lại sau.` | Exceeding brute-force rate limit (>5 failed attempts / 15 min per identifier, or >30 attempts / 15 min per client IP). | 429 Too Many Requests | **COVERED** | Enforced by `LoginIdentifierRateThrottle` and `LoginIPRateThrottle` with `Retry-After: 900` header (`OQ-87`, `TL-52`). |
| **PROP-4.1-P02** | Proposal | `Khởi tạo cookie CSRF thành công.` | GET `/api/v1/auth/csrf/` endpoint for SPA CSRF cookie handshake. | 200 OK | **COVERED** | `CSRFBootstrapView` sets `csrftoken` cookie for double-submit header (`TL-52`). |
| **PROP-4.1-P03** | Proposal | `Đăng xuất thành công.` | POST `/api/v1/auth/logout/` endpoint to destroy user session. | 200 OK | **COVERED** | Flushes Django session, revokes persistent token row via plain `DELETE` (`TL-36`), clears cookies (`TL-52`). |
| **PROP-4.1-P06** | Proposal | `Mã CSRF không hợp lệ hoặc bị thiếu.` | Missing or invalid CSRF header/token on POST login or logout endpoints. | 403 Forbidden | **COVERED** | Handled by `custom_csrf_failure_view` and `custom_exception_handler` returning standard JSON error envelope (`TL-53`, Q1). |

---

### 3.2. Detailed Traceability for Vehicle Management (Screen "Quản lý xe", TRC-FE-04-01..08, Round 63)

#### A. Comprehensive 36-Element UI Contract Inventory

The table below maps all 36 visual elements from the frontend mockup `Quản lý xe — Smart Mobility.png` to their backend REST endpoints, methods, and response fields.

| # | Mockup Element | API Endpoint | HTTP Method | Request / Query Param | Response Field / Structure | Business Rule / Status |
|:---:|---|---|:---:|---|---|:---:|
| 1 | Logo & Brand Icon (`LOGO`) | SPA Shell / Static Asset | N/A | None | Client static asset | **COVERED** |
| 2 | Navigation Menu (7 items, `Quản lý xe` active) | SPA Shell / Client Router | N/A | Route `/vehicles` | Visible to `EMPLOYEE` and `MANAGER` | **COVERED** |
| 3 | Camera Button & User Badge ("Admin") | `GET /api/v1/auth/me/` | GET | Session Cookie `sessionid` | `UserResponse: { id, email, phone, role }` | **COVERED** |
| 4 | Page Title & Subtitle (`Quản lý xe`) | Static UI Header | N/A | None | Client static header text | **COVERED** |
| 5 | Primary CTA `+ Thêm xe` | `POST /api/v1/vehicles/` | POST | Header: `X-CSRFToken`<br>Body: Vehicle payload | `201 Created`<br>`VehicleDetailResponse` | **COVERED** (RBAC: `IsEmployeeOrManager`) |
| 6 | KPI Card 1: `Tổng phương tiện` (6) | `GET /api/v1/vehicles/summary/` | GET | Optional: `customer`, `vehicle_type` | `total_vehicles: int` | **COVERED** (Global non-deleted count) |
| 7 | KPI Card 2: `Đang hoạt động` (4) | `GET /api/v1/vehicles/summary/` | GET | Optional: `customer`, `vehicle_type` | `active_vehicles: int` | **DERIVED** (Active ticket or in-lot) |
| 8 | KPI Card 3: `Vé sắp hết hạn` (2) | `GET /api/v1/vehicles/summary/` | GET | Optional: `customer`, `vehicle_type` | `expiring_soon_tickets: int` | **DERIVED** (Active ticket <= 7 days) |
| 9 | KPI Card 4: `Vé đã hết hạn` (1) | `GET /api/v1/vehicles/summary/` | GET | Optional: `customer`, `vehicle_type` | `expired_tickets: int` | **DERIVED** (Expired ticket < now) |
| 10 | Filter Input 1: `Mã xe` | `GET /api/v1/vehicles/` | GET | Query: `code=XE0001` | Substring match on `vehicle.code` | **COVERED** |
| 11 | Filter Input 2: `Biển số xe` | `GET /api/v1/vehicles/` | GET | Query: `plate=51K-992.14` | GIN trigram on `license_plate_norm` | **COVERED** |
| 12 | Filter Input 3: `Khách hàng` | `GET /api/v1/vehicles/` | GET | Query: `customer=Nguyen` | Trigram on customer code / full name | **COVERED** |
| 13 | Filter Dropdown 4: `Loại xe` | `GET /api/v1/vehicle-types/` | GET | Query: `vehicle_type=CAR` | Dropdown options: `CAR`, `EV` | **COVERED** (Car-only scope) |
| 14 | Filter Dropdown 5: `Loại vé` | `GET /api/v1/vehicles/` | GET | Query: `ticket_type=MONTHLY` | Matches `ticket_type.code` via FK | **COVERED** |
| 15 | Filter Dropdown 6: `Trạng thái` | `GET /api/v1/vehicles/` | GET | Query: `status=parked` | Runtime derived (`parked`, `active`, `left`) | **DERIVED** (TL-28.2) |
| 16 | Filter Dropdown 7: `Tình trạng vé` | `GET /api/v1/vehicles/` | GET | Query: `ticket_state=expiring_soon` | Derived (`valid`, `expiring_soon`, `expired`) | **DERIVED** (TL-28.1) |
| 17 | Filter Button: `Tìm kiếm` | `GET /api/v1/vehicles/` | GET | Combined filter query params | Paginated results matching all criteria | **COVERED** |
| 18 | Filter Button: `Làm mới` | `GET /api/v1/vehicles/` | GET | Default pagination parameters | Unfiltered page 1 results | **COVERED** |
| 19 | Table Title & Fleet Count ("6 phương tiện") | `GET /api/v1/vehicles/` | GET | Sourced from list envelope | `count: int` in pagination envelope | **COVERED** |
| 20 | Table Action: `Xuất CSV` | `GET /api/v1/vehicles/export/` | GET | Inherits list query filters | Streamed CSV (UTF-8 BOM, anti-injection) | **COVERED** (Hard cap 5,000) |
| 21 | Column 1: `STT` (Row index: 1, 2...) | Serializer / Client dynamic | N/A | None | `(page - 1) * page_size + index + 1` | **DERIVED** |
| 22 | Column 2: `Mã xe` (`XE0001`) | `GET /api/v1/vehicles/` | GET | None | `row.code: str` | **COVERED** |
| 23 | Column 3: `Ảnh` (Thumbnail) | `GET /api/v1/vehicles/` | GET | None | `row.image_url: str \| null` | **GAP** (Static URI; upload deferred) |
| 24 | Column 4: `Biển số xe` (`51K-992.14`) | `GET /api/v1/vehicles/` | GET | None | `row.license_plate: str` | **COVERED** |
| 25 | Column 5: `Khách hàng` (Name + Code) | `GET /api/v1/vehicles/` | GET | None | `row.customer: { id, code, full_name }` | **COVERED** (Zero N+1 select_related) |
| 26 | Column 6: `Loại xe` (`Ô tô`, `Xe điện`) | `GET /api/v1/vehicles/` | GET | None | `row.vehicle_type: { id, code, name }` | **COVERED** (Car-only `CAR`, `EV`) |
| 27 | Column 7: `Loại vé` (`Vé tháng`) | `GET /api/v1/vehicles/` | GET | None | `row.ticket: { ticket_type_code, name }` | **COVERED** |
| 28 | Column 8: `Ngày hết hạn vé` (Date + Badge) | `GET /api/v1/vehicles/` | GET | None | `row.ticket: { expires_at, state, days }` | **DERIVED** (TL-28.1) |
| 29 | Column 9: `Vị trí đỗ` (`Khu A · Slot 42`) | `GET /api/v1/vehicles/` | GET | None | `row.current_slot: str \| null` | **DERIVED** (Open session or assigned slot) |
| 30 | Column 10: `Trạng thái` (Badge + Dot) | `GET /api/v1/vehicles/` | GET | None | `row.status`, `row.status_display` | **DERIVED** (TL-28.2) |
| 31 | Column 11: `Thao tác` (Xem, Sửa, Xóa) | `GET/PATCH/DELETE /api/v1/vehicles/{id}/` | GET/PATCH/DEL | `id`, `X-CSRFToken`, `row_version` | Detail, Update, Soft-delete envelope | **COVERED** (OCC & DEL-03 guards) |
| 32 | Pagination Dropdown & Navigation | `GET /api/v1/vehicles/` | GET | `page`, `page_size` | `StandardResultsSetPagination` envelope | **COVERED** |
| 33 | Detail Panel 1: `Chi tiết xe` | `GET /api/v1/vehicles/{id}/` | GET | `id` | `VehicleDetailResponse` | **COVERED** |
| 34 | Detail Panel 2: `Thông tin chủ xe` | `GET /api/v1/vehicles/{id}/` | GET | Sourced from `customer` in detail | Customer contact, registered vehicle count | **COVERED** (PII masked if anonymized) |
| 35 | Detail Panel 3: `Trạng thái vé` | `GET /api/v1/vehicles/{id}/` | GET | Sourced from `ticket` in detail | Ticket duration, progress %, validity banner | **DERIVED** (TL-28.3) |
| 36 | Add Vehicle via Customer Modal | `POST /api/v1/customers/{id}/vehicles/` | POST | Customer path param + vehicle body | Thin alias to create vehicle service | **GAP / DEFERRED** (Customer module unbuilt) |

#### B. Architectural Decisions & Scope Boundary Analysis

1. **Car-Only Fleet Scope & Exclusion of Motorbikes (GAP TRC-FE-04-04)**:
   - **Mockup Anomaly**: Row 3 of mockup `Quản lý xe — Smart Mobility.png` depicts `"Xe máy"` with license plate `59P1-678.90` at slot `Khu B · Slot M12`.
   - **Authoritative Rule**: Under SRS v4.1, `TL-09`, `TL-20`, `TL-35`, and `OQ-49`, the Owner confirmed in chat on 2026-10-26 that the lot is for cars only.
   - **Implementation**: Database table `vehicle_type` contains exactly two records: `CAR` ("Ô tô") and `EV` ("Xe điện"). Endpoint `GET /api/v1/vehicle-types/` returns only `CAR` and `EV`. Registration (`POST`) and update (`PATCH`) reject any other vehicle type with HTTP 400 (`PROP-GEN-P01`). The motorbike row is formally classified as a **Known Designer Mockup Artifact (GAP TRC-FE-04-04)**.
2. **Optimistic Concurrency Control (OCC)**:
   - Table `vehicle` maintains `row_version INTEGER NOT NULL DEFAULT 1` with DB trigger `trg_vehicle_row_version`.
   - `PATCH /api/v1/vehicles/{id}/` requires `row_version: int`. Mismatched versions immediately abort with HTTP 409 Conflict (`MSG-4.3.1-M03`), preventing lost updates between concurrent staff (EMPLOYEE or MANAGER).
3. **DEL-03 Database Soft-Delete Guards**:
   - Soft-delete operations (`DELETE /api/v1/vehicles/{id}/`) set `deleted_at = now()` and `deleted_by = actor.id`.
   - Database trigger function `fn_guard_soft_delete_and_restore()` enforces 3 guards, mapped to HTTP 409 Conflict:
     - `PROP-DEL-03-OPEN-SES`: Vehicle currently parked in lot (`exit_time IS NULL`).
     - `PROP-DEL-03-ACTIVE-TKT`: Vehicle holds an active, unexpired ticket.
     - `PROP-DEL-03-ACTIVE-RSV`: Vehicle holds an active slot reservation.
   - Plain SQL hard delete is blocked by trigger `trg_prevent_plain_delete_vehicle` with PostgreSQL SQLSTATE `55000`.
4. **Summary KPI Cards Scope (TL-10, TL-28.1, TL-28.5)**:
   - `GET /api/v1/vehicles/summary/` by default computes global metrics across all active non-deleted vehicles.
   - Optional query filters (`customer`, `vehicle_type`) allow dynamic dashboard narrowing.
   - Expiring soon threshold is strictly defined as 7 days (`TICKET_EXPIRING_SOON_DAYS = 7`).
5. **Vehicle Thumbnail Gap (`image_url`)**:
   - `image_url` is stored as a text/URI field referencing static assets (e.g., `"/media/vehicles/xe0001.jpg"`).
   - Multipart vehicle photo upload is deferred as an unbuilt feature; no upload endpoint is exposed.
6. **Customer Vehicle Alias Endpoint (SCO-06)**:
   - `POST /api/v1/customers/{customer_id}/vehicles/` is fully implemented in Round 66 as a RESTful sub-resource alias delegating directly to `create_vehicle(customer_id=customer_id, ...)` with identical permissions (`IsEmployeeOrManager`) and transaction guarantees.

---

### 3.3. Detailed Traceability for Customer Management (Screen "Khách hàng", TRC-FE-03-01..06, TRC-SRS-04-01..06, Round 66)

#### A. Comprehensive UI Contract Inventory ("Khách hàng — Smart Mobility.png")

The table below maps all visual elements from the frontend mockup `Khách hàng — Smart Mobility.png` to their backend REST endpoints, methods, parameters, and response structures.

| # | Mockup Element | API Endpoint | HTTP Method | Request / Query Param | Response Field / Structure | Business Rule / Status |
|:---:|---|---|:---:|---|---|:---:|
| 1 | Logo & Navigation (`Khách hàng` active) | SPA Shell / Router | N/A | Route `/customers` | Visible to `EMPLOYEE` and `MANAGER` | **COVERED** |
| 2 | Camera Icon & User Profile Badge ("Admin") | `GET /api/v1/auth/me/` | GET | Session Cookie `sessionid` | `UserResponse: { id, email, phone, role }` | **COVERED** |
| 3 | Page Title: "Quản lý khách hàng" | Static UI Header | N/A | None | Client static text | **COVERED** |
| 4 | KPI Card 1: `Tổng khách hàng` (1,420) | `GET /api/v1/customers/summary/` | GET | None | `total_customers: int` | **COVERED** (`v_customer_status_summary`) |
| 5 | KPI Card 2: `Thuê bao kích hoạt` (1,280) | `GET /api/v1/customers/summary/` | GET | None | `active_subscribers: int` | **DERIVED** (Active ticket holders) |
| 6 | KPI Card 3: `Sắp hết hạn (7 ngày)` (42) | `GET /api/v1/customers/summary/` | GET | None | `expiring_soon_subscribers: int` | **DERIVED** (Active ticket <= 7d, TL-28.5) |
| 7 | KPI Card 4: `Blacklist/Tạm khoá` (15) | `GET /api/v1/customers/summary/` | GET | None | `blacklisted_or_suspended: int` | **COVERED** (`SUSPENDED` + `BLACKLISTED`) |
| 8 | Filter Input 1: `Mã khách hàng` | `GET /api/v1/customers/` | GET | Query: `code=KH0001` | Prefix/substring on `customer.code` | **COVERED** (`uq_customer_code_active`) |
| 9 | Filter Input 2: `Tên khách hàng` | `GET /api/v1/customers/` | GET | Query: `name=Nguyen` | PostgreSQL GIN trigram `idx_customer_full_name_trgm` | **COVERED** (`TL-41`) |
| 10 | Filter Input 3: `Số điện thoại` | `GET /api/v1/customers/` | GET | Query: `phone=0905` | Substring match on `customer.phone` | **COVERED** (`TL-41`) |
| 11 | Filter Input 4: `Số CCCD` | `GET /api/v1/customers/` | GET | Query: `identity_card=048` | Substring match on `identity_card_number` | **COVERED** (`TL-41`) |
| 12 | Supplemental Filter: `Trạng thái` | `GET /api/v1/customers/` | GET | Query: `status=ACTIVE` | Exact match enum: `ACTIVE`, `SUSPENDED`, `BLACKLISTED` | **COVERED** |
| 13 | Button: `Tìm kiếm` | `GET /api/v1/customers/` | GET | Combined filter params | Paginated list envelope | **COVERED** |
| 14 | Button: `Reset` | `GET /api/v1/customers/` | GET | Default params (`page=1`) | Unfiltered default customer list | **COVERED** |
| 15 | Primary CTA: `+ Thêm` | `POST /api/v1/customers/` | POST | Header: `X-CSRFToken`<br>Body: Customer payload | `201 Created`<br>`CustomerDetailResponse` | **COVERED** (RBAC: `IsEmployeeOrManager`) |
| 16 | Column 1: `Mã khách hàng` (`KH0001`) | `GET /api/v1/customers/` | GET | None | `row.code: str` | **COVERED** (Immutable, `KH%04d`) |
| 17 | Column 2: `Tên khách hàng` | `GET /api/v1/customers/` | GET | None | `row.full_name: str` | **COVERED** (Masked if anonymized, OQ-12) |
| 18 | Column 3: `Số điện thoại` | `GET /api/v1/customers/` | GET | None | `row.phone: str` | **COVERED** (Masked if anonymized) |
| 19 | Column 4: `Số CCCD` | `GET /api/v1/customers/` | GET | None | `row.identity_card_number: str` | **COVERED** (Masked if anonymized) |
| 20 | Row Enrichment: `Trạng thái` | `GET /api/v1/customers/` | GET | None | `row.status`, `row.status_display` | **COVERED** |
| 21 | Row Enrichment: `Số lượng xe` | `GET /api/v1/customers/` | GET | None | `row.vehicles_count: int` | **DERIVED** (Count active vehicles, zero N+1) |
| 22 | Row Enrichment: `Vé hiệu lực` | `GET /api/v1/customers/` | GET | None | `row.has_active_ticket: bool` | **DERIVED** (Exists active ticket, zero N+1) |
| 23 | OCC Token: `Phiên bản` | `GET /api/v1/customers/` | GET | None | `row.row_version: int` | **COVERED** (OCC concurrency token) |
| 24 | Pagination Envelope | `GET /api/v1/customers/` | GET | Query: `page`, `page_size` | `count, total_pages, current_page, page_size, next, previous, results` | **COVERED** (`StandardResultsSetPagination`) |
| 25 | Customer Profile Detail | `GET /api/v1/customers/{id}/` | GET | Path: `id` | Full profile + administrative units + vehicles sub-grid | **COVERED** (Zero duplicate logic) |
| 26 | Edit Customer Action | `PATCH /api/v1/customers/{id}/` | PATCH | Header: `X-CSRFToken`<br>Body: Update payload + `row_version` | `200 OK`<br>`CustomerDetailResponse` | **COVERED** (Enforces OCC) |
| 27 | Soft Delete Action | `DELETE /api/v1/customers/{id}/` | DELETE | Header: `X-CSRFToken`<br>Path: `id` | `200 OK`<br>`{"message": "Xóa thành công"}` | **COVERED** (DEL-02 guards) |
| 28 | Customer Vehicle Sub-resource | `POST /api/v1/customers/{customer_id}/vehicles/` | POST | Header: `X-CSRFToken`<br>Path: `customer_id`<br>Body: Vehicle payload | `201 Created`<br>`VehicleDetailResponse` | **COVERED** (`SCO-06` alias) |

#### B. Architectural Rules & Implementation Notes

1. **Role-Based Access Control (RBAC)**:
   - All customer operations (`GET`, `POST`, `PATCH`, `DELETE`) require `IsEmployeeOrManager` (`EMPLOYEE` and `MANAGER` roles).
   - Customer accounts (`CUSTOMER`) receive HTTP `403 Forbidden` (`MSG-4.2-M01`).
   - Unauthenticated callers receive HTTP `401 Unauthorized` (`MSG-4.1-M02`).
2. **Double-Submit CSRF Protection**:
   - Mutating operations (`POST`, `PATCH`, `DELETE`) enforce `X-CSRFToken` header validation matching the `csrftoken` session cookie (`PROP-4.1-P06`).
3. **Atomic Customer Creation with Optional Vehicles Array**:
   - `POST /api/v1/customers/` accepts an optional `vehicles: [...]` list.
   - Entire payload executed inside `@transaction.atomic`. If any vehicle registration fails, the customer creation is completely rolled back (all-or-nothing atomicity).
4. **Advisory Lock for Monotonic `KH%04d` Generation**:
   - Auto-generated sequential code acquires PostgreSQL transaction-scoped advisory lock: `SELECT pg_advisory_xact_lock(hashtext('customer_code_sequence'));`.
   - Guarantees zero race condition collisions (`uq_customer_code_active`) under high concurrency.
5. **Optimistic Concurrency Control (OCC)**:
   - `PATCH /api/v1/customers/{id}/` mandates `row_version`.
   - Stale version returns HTTP `409 Conflict` with `MSG-4.3.1-M03`.
6. **DEL-02 Soft-Delete Database Guards**:
   - Intercepted by database trigger `trg_guard_soft_delete_and_restore_customer`:
     - `PROP-4.4.5-P02`: Customer owns a vehicle currently in parking lot (`exit_time IS NULL`).
     - `PROP-4.4.5-P03`: Customer holds an active, unexpired subscription ticket.
     - `PROP-DEL-02-ACTIVE-VEH`: Customer owns active (`deleted_at IS NULL`) registered vehicles.
   - Prohibits plain SQL `DELETE` via trigger `trg_prevent_plain_delete_customer` (SQLSTATE `55000`).
7. **PII Anonymization & Data Protection (`OQ-12`, Decree 13/2023/NĐ-CP)**:
   - When `is_anonymized = True`, customer profile returns masked PII (`full_name = "Khách hàng ẩn danh"`, `phone = "***"`, `identity_card_number = "***"`).
   - Strict PII protection: raw PII is never echoed in error details or log messages.
8. **Administrative Unit Dropdown Endpoints (`TL-48`, Task T2)**:
   - Administrative Unit dropdown endpoints are fully implemented in `apps/core` under `/api/v1/administrative/provinces/`, `districts/?province_id=`, and `wards/?district_id=`.
   - Customer and employee APIs validate foreign keys (`province_id`, `district_id`, `ward_id`) against these active records.

---

### 3.4. Detailed Traceability for Employee Management (Screen "Quản lý nhân viên", TRC-FE-08-01..07, TRC-SRS-03-01..05, Round 67)

#### A. Comprehensive 25-Element UI Contract Inventory

The table below maps all 25 visual elements from the frontend mockup `Quản lý nhân viên - Smart mobility.png` to their backend REST endpoints, methods, and response fields.

| # | Mockup Element | API Endpoint | HTTP Method | Request / Query Param | Response Field / Structure | Business Rule / Status |
|:---:|---|---|:---:|---|---|:---:|
| 1 | Logo & Brand Icon (`LOGO`) | SPA Shell / Static Asset | N/A | None | Client static asset | **COVERED** |
| 2 | Navigation Menu (`Quản lý nhân viên` active) | SPA Shell / Client Router | N/A | Route `/employees` | Strictly visible to `MANAGER` | **COVERED** |
| 3 | Camera Button & User Badge ("Admin") | `GET /api/v1/auth/me/` | GET | Session Cookie `sessionid` | `UserResponse: { id, email, phone, role: "MANAGER" }` | **COVERED** |
| 4 | Page Title & Subtitle (`Quản lý nhân viên`) | Static UI Header | N/A | None | Client static header text | **COVERED** |
| 5 | Primary CTA: `+ Thêm nhân viên` | `POST /api/v1/employees/` | POST | Header: `X-CSRFToken`<br>Body: Employee payload + password | `201 Created`<br>`EmployeeDetailResponse` | **COVERED** (RBAC: `MANAGER`-only, atomic creation) |
| 6 | KPI Card 1: `Tổng nhân viên` | `GET /api/v1/employees/summary/` | GET | None | `total_employees: int` | **COVERED** (SOT, active employee count) |
| 7 | KPI Card 2: `Đang hoạt động` | `GET /api/v1/employees/summary/` | GET | None | `active_employees: int` | **COVERED** (SOT, status `ACTIVE`) |
| 8 | KPI Card 3: `Không hoạt động` | `GET /api/v1/employees/summary/` | GET | None | `inactive_employees: int` | **COVERED** (SOT, status `INACTIVE`) |
| 9 | KPI Card 4: `Chức vụ` | `GET /api/v1/employees/summary/` | GET | None | `total_positions: int` | **COVERED** (SOT, active position count) |
| 10 | Search Box: `"Tìm tên, mã, email..."` | `GET /api/v1/employees/` | GET | Query: `q=val` | Substring match across `full_name`, `code`, `email` | **COVERED** |
| 11 | Filter Dropdown: `Chức vụ` | `GET /api/v1/employees/` | GET | Query: `position=QL` or `position=1` | Filter by position code or ID (catalog from `GET /api/v1/positions/`) | **COVERED** |
| 12 | Filter Dropdown: `Trạng thái` | `GET /api/v1/employees/` | GET | Query: `status=ACTIVE` | Filter by status (`ACTIVE`, `INACTIVE`) | **COVERED** |
| 13 | Button: `Tìm kiếm` | `GET /api/v1/employees/` | GET | Combined filter params | Paginated list envelope | **COVERED** |
| 14 | Button: `Reset` | `GET /api/v1/employees/` | GET | Default params (`page=1`) | Unfiltered default employee list | **COVERED** |
| 15 | Table Column 1: `NHÂN VIÊN` | `GET /api/v1/employees/` | GET | None | `row.full_name: str` | **COVERED** (Clean UTF-8 Vietnamese diacritics) |
| 16 | Table Column 2: `MÃ NV` (`NV001`) | `GET /api/v1/employees/` | GET | None | `row.code: str` | **COVERED** (Immutable, sequential `NV%03d`/`NV%04d`) |
| 17 | Table Column 3: `CHỨC VỤ` | `GET /api/v1/employees/` | GET | None | `row.position.name: str` | **COVERED** (`select_related('position')`, zero N+1) |
| 18 | Table Column 4: `LIÊN HỆ` | `GET /api/v1/employees/` | GET | None | `row.phone: str`, `row.email: str` | **COVERED** |
| 19 | Table Column 5: `KHU VỰC` | `GET /api/v1/employees/` | GET | None | `row.area.district_name`, `row.area.province_name` | **COVERED** (`select_related`, zero N+1) |
| 20 | Table Column 6: `TRẠNG THÁI` | `GET /api/v1/employees/` | GET | None | `row.status`, `row.status_display` | **COVERED** (`ACTIVE` / `INACTIVE`) |
| 21 | Table Column 7: `THAO TÁC` | `GET/PATCH/DELETE /api/v1/employees/{id}/` | GET/PATCH/DELETE | Path: `id` | Row actions (View, Edit, Delete) | **COVERED** (DEL-01 guards, OCC, immediate revocation) |
| 22 | OCC Token: `Phiên bản` | `GET /api/v1/employees/` | GET | None | `row.row_version: int` | **COVERED** (Optimistic concurrency control token) |
| 23 | Pagination Envelope | `GET /api/v1/employees/` | GET | Query: `page`, `page_size` | `count, total_pages, current_page, page_size, next, previous, results` | **COVERED** (`StandardResultsSetPagination`) |
| 24 | Employee Profile Detail Modal | `GET /api/v1/employees/{id}/` | GET | Path: `id` | Full personal, administrative (3 tiers), and account metadata | **COVERED** (Zero password exposure) |
| 25 | Soft Delete Confirmation Modal | `DELETE /api/v1/employees/{id}/` | DELETE | Header: `X-CSRFToken`<br>Path: `id` | `200 OK`<br>`{"code": "MSG-4.3.4-M01", "message": "Xóa thành công"}` | **COVERED** (DEL-01 trigger guards -> 409) |

#### B. Architectural Rules & Implementation Notes

1. **Role-Based Access Control (RBAC)**:
   - All 7 employee operations (`GET /api/v1/positions/`, `GET /api/v1/employees/summary/`, `GET /api/v1/employees/`, `GET /api/v1/employees/{id}/`, `POST /api/v1/employees/`, `PATCH /api/v1/employees/{id}/`, `DELETE /api/v1/employees/{id}/`) are strictly `MANAGER`-only (`[IsAuthenticated, IsManager]`).
   - Authenticated callers with `EMPLOYEE` or `CUSTOMER` roles receive HTTP `403 Forbidden` (`MSG-4.2-M01`).
   - Unauthenticated callers receive HTTP `401 Unauthorized` (`MSG-4.1-M02`).
2. **Double-Submit CSRF Protection**:
   - Mutating operations (`POST`, `PATCH`, `DELETE`) enforce `X-CSRFToken` header validation matching the active `csrftoken` session cookie (`PROP-4.1-P06`).
3. **Single Source of Truth (SOT) for KPI Cards**:
   - `GET /api/v1/employees/summary/` metrics (`total_employees`, `active_employees`, `inactive_employees`, `total_positions`) query identical selector filters as the directory listing. All numbers match independent raw database counts across all seeded and test-created records.
4. **Atomic Employee & Account Lifecycle with Role Derivation**:
   - `POST /api/v1/employees/` creates both `Account` and `Employee` in a single atomic database transaction (`@transaction.atomic()`).
   - Account `role` is strictly derived from `Position.code`: `QL -> MANAGER`; `NVVH`, `NVTN`, `KTV -> EMPLOYEE`. Direct client specification of `role` is rejected.
   - Account `is_active` is synchronized with `Employee.status` (`ACTIVE -> True`, `INACTIVE -> False`).
   - Password is validated against complexity rules and hashed via Argon2 (`make_password`). If employee insertion fails, account creation is automatically rolled back with zero orphan records.
5. **Advisory Lock for Monotonic `NV` Code Generation**:
   - When `code` is omitted in `POST /api/v1/employees/`, sequential code `NV%03d` (expanding to `NV%04d` after 999) is generated under PostgreSQL transaction advisory lock: `SELECT pg_advisory_xact_lock(hashtext('employee_code_sequence'));`.
   - Guarantees zero race condition collisions (`ck_employee_code_format`) under high-concurrency workloads.
6. **Optimistic Concurrency Control (OCC) & Immutable Code**:
   - `PATCH /api/v1/employees/{id}/` mandates `row_version`. Stale version returns HTTP `409 Conflict` with `MSG-4.3.1-M03`.
   - Field `code` is immutable and cannot be updated.
7. **DEL-01 Soft-Delete & Deactivation Database Guards**:
   - Database triggers (`fn_guard_soft_delete_and_restore`) and service-level guards enforce:
     - `PROP-DEL-01-SELF-EMP`: An employee cannot soft-delete their own profile.
     - `PROP-DEL-01-SELF-DEACT`: An employee cannot deactivate their own account.
     - `PROP-DEL-01-SELF-DEMOTE`: A manager cannot demote themselves.
     - `PROP-DEL-01-LAST-MGR-EMP`: Deactivating, demoting, or soft-deleting the last remaining active manager is prohibited.
   - Violations return clean HTTP `409 Conflict`.
   - Plain SQL hard `DELETE` is blocked by database trigger `trg_prevent_plain_delete_employee` (SQLSTATE `55000`).
8. **Immediate Session & Remember-Token Revocation**:
   - Deactivating (`status = "INACTIVE"`), soft-deleting, or demoting an employee immediately revokes all active Django `Session` records and `RememberToken` records in the same transaction. The very next HTTP request on an existing session is immediately rejected.
9. **Zero PII Leakage & Safe Error Mapping**:
   - Unique constraint conflicts on email, phone, CCCD, or code return generic `409 Conflict` (`MSG-4.3.1-M05`) without echoing user PII values.

#### C. SRS 4.3 Field, Action & Message Matrix

| SRS Item | Name / Description | Target Field / Action | Error / Success Code | HTTP Status | Implementation Target |
|:---:|---|---|:---:|:---:|---|
| **SRS 4.3.1** | Employee Directory & Search | Multi-field filtering (`q`, `name`, `code`, `address`, `birth_from`, `birth_to`, `position`, `status`) | `MSG-4.3.1-M02` | 200 OK | `apps/employees/selectors/employees.py` |
| **SRS 4.3.1** | Concurrency Conflict (OCC) | Update collision on `row_version` mismatch | `MSG-4.3.1-M03` | 409 Conflict | `apps/employees/services/employees.py` |
| **SRS 4.3.1** | Duplicate Value Conflict | Unique collision on email, phone, CCCD, or code | `MSG-4.3.1-M05` | 409 Conflict | `apps/employees/services/error_translation.py` |
| **SRS 4.3.2** | Add Employee Success | Atomic creation of Employee and Account | `MSG-4.3.2-M01` | 201 Created | `apps/employees/views/employees.py` |
| **SRS 4.3.2** | Invalid Employee Code Format | Code does not match `^NV[0-9]{3,4}$` | `MSG-4.3.2-M02` | 400 Bad Request | `apps/employees/serializers/employees.py` |
| **SRS 4.3.3** | Password Complexity Policy | Missing uppercase, lowercase, digit, or special character | `MSG-4.3.3-M01` | 400 Bad Request | `apps/employees/serializers/employees.py` |
| **SRS 4.3.3** | Update Employee Success | Successful profile update | `PROP-4.3.3-P01` | 200 OK | `apps/employees/views/employees.py` |
| **SRS 4.3.4** | Delete Employee Success | Atomic soft-deletion of Employee and Account | `MSG-4.3.4-M01` | 200 OK | `apps/employees/views/employees.py` |
| **SRS 4.3.4** | Concurrent Delete Conflict | Concurrent deletion on same employee | `MSG-4.3.4-M02` | 409 Conflict | `apps/employees/services/error_translation.py` |
| **DEL-01** | Self-Deletion | Logged-in employee self-deletion | `PROP-DEL-01-SELF-EMP` | 409 Conflict | `apps/employees/services/error_translation.py` |
| **DEL-01** | Self-Deactivation | Logged-in employee self-deactivation | `PROP-DEL-01-SELF-DEACT` | 409 Conflict | `apps/employees/services/employees.py` |
| **DEL-01** | Self-Demotion | Logged-in manager self-demotion | `PROP-DEL-01-SELF-DEMOTE` | 409 Conflict | `apps/employees/services/employees.py` |
| **DEL-01** | Last Active Manager Guard | Deactivating, demoting, or deleting the last active manager | `PROP-DEL-01-LAST-MGR-EMP` | 409 Conflict | `apps/employees/services/employees.py` / `error_translation.py` |

---

## 4. SQL Proof Queries for Frontend Derived Values (TL-28)

Six UI values are computed dynamically per **TL-28** to avoid redundancy:

### 4.1. Expiring & Representative Ticket States (TL-28.1, OQ-52)

Single Source of Truth (SOT) via **Representative Ticket** evaluated per vehicle:

1. **Tier 1 (Active)**: `deleted_at IS NULL AND status IN ('ACTIVE', 'RENEWING') AND effective_to >= now()` ordered by `effective_to DESC, id DESC LIMIT 1`.
2. **Tier 2 (Historical)**: If Tier 1 is absent, most recent ticket with `deleted_at IS NULL AND status != 'CANCELLED'` ordered by `effective_to DESC, id DESC LIMIT 1`.
3. If no ticket or only `CANCELLED`, representative ticket is `NULL` (`state = 'none'`).

```sql
WITH rep_ticket AS (
    SELECT v.id AS vehicle_id,
           COALESCE(
               (
                   SELECT t.id
                   FROM ticket t
                   WHERE t.vehicle_id = v.id
                     AND t.deleted_at IS NULL
                     AND t.status IN ('ACTIVE', 'RENEWING')
                     AND t.effective_to >= CURRENT_TIMESTAMP
                   ORDER BY t.effective_to DESC, t.id DESC
                   LIMIT 1
               ),
               (
                   SELECT t.id
                   FROM ticket t
                   WHERE t.vehicle_id = v.id
                     AND t.deleted_at IS NULL
                     AND t.status != 'CANCELLED'
                   ORDER BY t.effective_to DESC, t.id DESC
                   LIMIT 1
               )
           ) AS ticket_id
    FROM vehicle v
    WHERE v.deleted_at IS NULL
)
SELECT v.code, v.license_plate, t.code AS ticket_code, tt.name AS ticket_type,
       t.effective_to AS expires_at, t.status AS base_status,
       CASE
           WHEN t.id IS NULL THEN 'none'
           WHEN t.effective_to < CURRENT_TIMESTAMP THEN 'expired'
           WHEN t.effective_to <= CURRENT_TIMESTAMP + INTERVAL '7 days' THEN 'expiring_soon'
           ELSE 'valid'
       END AS ticket_state,
       CASE
           WHEN t.id IS NULL THEN NULL
           WHEN t.effective_to < CURRENT_TIMESTAMP THEN 'Đã hết hạn'
           WHEN t.effective_to <= CURRENT_TIMESTAMP + INTERVAL '7 days' THEN 'Sắp hết hạn'
           ELSE 'Còn hạn'
       END AS fe_display_status,
       GREATEST(0, CEIL(EXTRACT(EPOCH FROM (t.effective_to - CURRENT_TIMESTAMP)) / 86400))::INTEGER AS remaining_days
FROM vehicle v
JOIN rep_ticket rt ON rt.vehicle_id = v.id
LEFT JOIN ticket t ON t.id = rt.ticket_id
LEFT JOIN ticket_type tt ON tt.id = t.ticket_type_id
WHERE v.deleted_at IS NULL
ORDER BY v.code ASC;
```

### 4.2. Derived Parking Status (TL-28.2)

```sql
SELECT v.code, v.license_plate, c.full_name, vt.name AS vehicle_type,
  CASE WHEN EXISTS (SELECT 1 FROM vehicle_entry_exit_log l WHERE l.vehicle_id = v.id AND l.exit_time IS NULL) THEN 'Đang đỗ'
       WHEN EXISTS (SELECT 1 FROM ticket t WHERE t.vehicle_id = v.id AND t.status IN ('ACTIVE','RENEWING') AND t.effective_to >= '2026-10-17 00:00:00+07'::TIMESTAMPTZ AND t.deleted_at IS NULL) THEN 'Đang hoạt động'
       ELSE 'Đã rời bãi' END AS derived_status,
  (SELECT ps.code || ' (' || pf.name || ')' FROM vehicle_entry_exit_log l JOIN parking_slot ps ON ps.id = l.slot_id JOIN parking_zone pz ON pz.id = ps.zone_id JOIN parking_floor pf ON pf.id = pz.floor_id WHERE l.vehicle_id = v.id AND l.exit_time IS NULL LIMIT 1) AS current_parked_slot
FROM vehicle v JOIN customer c ON c.id = v.customer_id AND c.deleted_at IS NULL
JOIN vehicle_type vt ON vt.id = v.vehicle_type_id AND vt.deleted_at IS NULL
WHERE v.deleted_at IS NULL ORDER BY v.code ASC;
```

### 4.3. Remaining Days & Lifecycle Progress (TL-28.3)

Derived from the vehicle's representative ticket:

- `remaining_days`: `max(0, ceil(diff_seconds / 86400))` (0 for expired tickets).
- `consumed_percentage`: `min(100.0, max(0.0, round(elapsed / total_duration * 100, 1)))`.
- `is_valid`: `true` if `ticket_state IN ('valid', 'expiring_soon')`, `false` if `expired`.
- `validity_message`: "Vé còn hiệu lực.", "Vé sắp hết hạn.", or "Vé đã hết hạn.".

```sql
WITH rep_ticket AS (
    SELECT v.id AS vehicle_id,
           COALESCE(
               (
                   SELECT t.id
                   FROM ticket t
                   WHERE t.vehicle_id = v.id
                     AND t.deleted_at IS NULL
                     AND t.status IN ('ACTIVE', 'RENEWING')
                     AND t.effective_to >= CURRENT_TIMESTAMP
                   ORDER BY t.effective_to DESC, t.id DESC
                   LIMIT 1
               ),
               (
                   SELECT t.id
                   FROM ticket t
                   WHERE t.vehicle_id = v.id
                     AND t.deleted_at IS NULL
                     AND t.status != 'CANCELLED'
                   ORDER BY t.effective_to DESC, t.id DESC
                   LIMIT 1
               )
           ) AS ticket_id
    FROM vehicle v
    WHERE v.deleted_at IS NULL
)
SELECT t.code, v.license_plate, tt.name AS ticket_type, t.effective_from, t.effective_to,
  GREATEST(0, CEIL(EXTRACT(EPOCH FROM (t.effective_to - CURRENT_TIMESTAMP)) / 86400))::INTEGER AS remaining_days,
  ROUND((EXTRACT(EPOCH FROM (LEAST(t.effective_to, CURRENT_TIMESTAMP) - t.effective_from)) / NULLIF(EXTRACT(EPOCH FROM (t.effective_to - t.effective_from)), 0)) * 100, 1) AS consumed_percentage,
  (t.effective_to >= CURRENT_TIMESTAMP AND t.status IN ('ACTIVE', 'RENEWING')) AS is_valid
FROM vehicle v
JOIN rep_ticket rt ON rt.vehicle_id = v.id
JOIN ticket t ON t.id = rt.ticket_id
JOIN ticket_type tt ON tt.id = t.ticket_type_id
WHERE v.deleted_at IS NULL;
```

### 4.4. Session Duration (TL-28.4)

```sql
SELECT l.session_code, l.license_plate, l.entry_time, l.exit_time,
  CASE WHEN l.exit_time IS NULL THEN 'Đang đỗ' ELSE 'Đã rời bãi' END AS session_state,
  COALESCE(l.exit_time, '2026-10-17 12:00:00+07'::TIMESTAMPTZ) - l.entry_time AS duration_interval,
  EXTRACT(HOUR FROM (COALESCE(l.exit_time, '2026-10-17 12:00:00+07'::TIMESTAMPTZ) - l.entry_time))::INTEGER || 'h' || LPAD(EXTRACT(MINUTE FROM (COALESCE(l.exit_time, '2026-10-17 12:00:00+07'::TIMESTAMPTZ) - l.entry_time))::INTEGER::TEXT, 2, '0') || 'm' AS formatted_duration,
  l.fee_amount FROM vehicle_entry_exit_log l ORDER BY l.entry_time DESC LIMIT 10;
```

### 4.5. Subscription Metrics & KPI Aggregation (TL-28.5)

Evaluated via unified representative ticket annotations matching list filtering 100%:

- Baseline seed (clean 30 vehicles): `total_vehicles: 30`, `active_vehicles: 15`, `expiring_soon_tickets: 0`, `expired_tickets: 12`, `valid_tickets: 10`, `none_tickets: 8`.
- Excludes CANCELLED tickets (`VT0023`, `VT0024`, `VT0025`).

```sql
WITH rep_ticket AS (
    SELECT v.id AS vehicle_id,
           COALESCE(
               (
                   SELECT t.id
                   FROM ticket t
                   WHERE t.vehicle_id = v.id
                     AND t.deleted_at IS NULL
                     AND t.status IN ('ACTIVE', 'RENEWING')
                     AND t.effective_to >= CURRENT_TIMESTAMP
                   ORDER BY t.effective_to DESC, t.id DESC
                   LIMIT 1
               ),
               (
                   SELECT t.id
                   FROM ticket t
                   WHERE t.vehicle_id = v.id
                     AND t.deleted_at IS NULL
                     AND t.status != 'CANCELLED'
                   ORDER BY t.effective_to DESC, t.id DESC
                   LIMIT 1
               )
           ) AS ticket_id
    FROM vehicle v
    WHERE v.deleted_at IS NULL
),
vehicle_ticket_classification AS (
    SELECT rt.vehicle_id,
           t.id AS ticket_id,
           CASE
               WHEN t.id IS NULL THEN 'none'
               WHEN t.effective_to < CURRENT_TIMESTAMP THEN 'expired'
               WHEN t.effective_to <= CURRENT_TIMESTAMP + INTERVAL '7 days' THEN 'expiring_soon'
               ELSE 'valid'
           END AS ticket_state
    FROM rep_ticket rt
    LEFT JOIN ticket t ON t.id = rt.ticket_id
)
SELECT
    COUNT(v.id) AS total_vehicles,
    COUNT(v.id) FILTER (WHERE EXISTS (
        SELECT 1 FROM vehicle_entry_exit_log l
        WHERE l.vehicle_id = v.id AND l.exit_time IS NULL
    ) OR vtc.ticket_state IN ('valid', 'expiring_soon')) AS active_vehicles,
    COUNT(v.id) FILTER (WHERE vtc.ticket_state = 'expiring_soon') AS expiring_soon_tickets,
    COUNT(v.id) FILTER (WHERE vtc.ticket_state = 'expired') AS expired_tickets,
    COUNT(v.id) FILTER (WHERE vtc.ticket_state = 'valid') AS valid_tickets,
    COUNT(v.id) FILTER (WHERE vtc.ticket_state = 'none') AS none_tickets
FROM vehicle v
JOIN vehicle_ticket_classification vtc ON vtc.vehicle_id = v.id
WHERE v.deleted_at IS NULL;
```

### 4.6. Floor Occupancy Percentage Bars (TL-28.6)

```sql
WITH occ AS (
  SELECT v.floor_id, v.floor_code, v.floor_name, SUM(v.total_slots)::BIGINT AS total_slots, SUM(v.operational_slots)::BIGINT AS operational_slots,
    SUM(v.occupied_slots + v.reserved_slots + v.charging_slots)::BIGINT AS used_slots, SUM(v.available_slots)::BIGINT AS available_slots,
    COALESCE(ROUND(100.0 * SUM(v.occupied_slots + v.reserved_slots + v.charging_slots) / NULLIF(SUM(v.operational_slots), 0), 1), 0.0) AS occ_pct
  FROM v_slot_occupancy_by_floor v GROUP BY v.floor_id, v.floor_code, v.floor_name
)
SELECT floor_code, floor_name, total_slots, operational_slots, used_slots, available_slots, occ_pct AS occupancy_percentage,
  CASE WHEN occ_pct >= 90.0 THEN 'Sắp đầy' ELSE 'Còn chỗ' END AS status_badge,
  floor_name || ' · ' || ROUND(occ_pct, 0)::TEXT || '% (' || used_slots::TEXT || '/' || operational_slots::TEXT || ' chỗ)' AS fe_display_label
FROM occ ORDER BY floor_code ASC;
```

---

## 5. Traceability Audit Summary & Verification Checklist

- [x] **100% UI Image Coverage**: All 11 UI design files verified across 67 items (Section 1 & 2).
- [x] **100% SRS Coverage**: Sections 4.1–4.8, deletion guards DEL-01..DEL-05, NFRs mapped across 45 items (Section 3).
- [x] **Schema Invariant**: Preserves 28 tables, 8 views, 69 FKs, 338+55 columns.
- [x] **Zero Gaps**: All variations resolved under `TL-29`–`TL-50`.
