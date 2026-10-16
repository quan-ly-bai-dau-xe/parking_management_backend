# Database Schema & Seed Catalog — Parking Management Backend

<!-- cspell:words VIETQR nonnulls NVVH NVTN -->

This directory defines the enterprise physical relational database schema, lookup reference seed data, and architectural documentation for the Smart Mobility Car Parking Lot Management System backend (`parking_management_backend`), targeting **PostgreSQL 18.6**. Under the **Frontend-First (`FE-First`)** specification hierarchy established in Round 23 ([`docs/requirements/06-frontend-srs-db-alignment.md`](../docs/requirements/06-frontend-srs-db-alignment.md), `TL-01`–`TL-16`), the 11 Frontend UI screens in `Parking Project` are the **primary source of requirements**, while `Quan ly bai dau xe oto_SRS_v4.1.docx` ([`docs/requirements/00-srs-catalog.md`](../docs/requirements/00-srs-catalog.md)) is **secondary** where the Frontend is silent.

---

## 1. Database Execution & Loading Instructions

### 1.1. Native Execution via `psql` (Local / CI Pipeline)

Execution must specify `ON_ERROR_STOP=1` to ensure execution halts immediately upon any syntax or constraint violation:

```bash
# Load DDL Schema and Analytical Views (Zero DROP statements, transactional BEGIN...COMMIT)
psql -h 127.0.0.1 -p 5432 -U parking_user -d parking_db -v ON_ERROR_STOP=1 -f db/01-schema.sql

# Load Lookup Reference Seed Data
psql -h 127.0.0.1 -p 5432 -U parking_user -d parking_db -v ON_ERROR_STOP=1 -f db/02-seed.sql
```

### 1.2. Execution via Docker Compose Service

When launching the backend PostgreSQL service defined in `docker-compose.yml`:

```bash
# Start PostgreSQL 18.6 container
docker compose up -d db

# Execute SQL scripts inside container
docker compose exec -T db psql -U parking_user -d parking_db -v ON_ERROR_STOP=1 < db/01-schema.sql
docker compose exec -T db psql -U parking_user -d parking_db -v ON_ERROR_STOP=1 < db/02-seed.sql
```

---

## 2. Frontend & SRS Entity Mapping Table

The table below maps the Frontend UI screens/labels (`TL-01`–`TL-16`) and secondary SRS v4.1 entity names to their normalized PostgreSQL relational database tables:

| Frontend / SRS Name | Relational Table Name | Architectural & Business Representation |
| :--- | :--- | :--- |
| `Đăng nhập` / `ACCOUNT` | `account` | Authentication principals using `email` and/or `phone`, password hashes, and roles (`MANAGER`, `EMPLOYEE`, `CUSTOMER`) (`TL-01`). |
| `Nhân viên` / `NHAN_VIEN` | `employee` | Staff profiles (`NV001`, `NV0005`), contact details, status (`ACTIVE`, `INACTIVE`), position, and address links (`TL-11`, `TL-15`). |
| `Chức vụ` | `position` | Staff position catalog: `Quản lý`, `Nhân viên vận hành`, `Nhân viên thu ngân`, `Kỹ thuật viên` (`TL-11`). |
| `Khách hàng` / `KHACH_HANG` | `customer` | Customer profiles (`KH0001`), CCCD, status (`ACTIVE`, `SUSPENDED`, `BLACKLISTED`), and Decree 13 anonymization (`TL-08`, `TL-15`). |
| `Blacklist biển số` | `plate_blacklist` | Blacklisted license plates (including visitor plates) with normalized uniqueness and unpaid debt amount (`TL-08`). |
| `Loại xe` | `vehicle_type` | Vehicle type catalog: `CAR` (`Ô tô`), `MOTO` (`Xe máy`), `EV` (`Xe điện`) (`TL-09`). |
| `Quản lý xe` / `XE` | `vehicle` | Customer-linked vehicles (`XE0001`), raw + normalized plate, ticket preferences, and `notes` (`TL-09`, `TL-15`). |
| `Loại vé` / `LoaiVe` | `ticket_type` | Subscription tariff catalog: `DAILY` (`50k`), `MONTHLY` (`500k`), `QUARTERLY` (`1.2M`), `YEARLY` (`4.8M`) (`TL-10`). |
| `Bãi xe` -> `Tầng` -> `Khu` -> `Ô đỗ` | `parking_lot`, `parking_floor`, `parking_zone`, `parking_slot` | 4-level physical parking structure (`Bãi xe Smart Mobility`, `B1..B3/F1`, `Khu A..C`, `A-01`/`B-01`) (`TL-02`, `TL-03`). |
| `Đặt trước ô đỗ` | `slot_reservation` | Pre-booked slot reservations with GiST anti-overlap exclusion and automatic slot `RESERVED` sync (`TL-04`). |
| `Quản lý vé` / `VE` | `ticket`, `ticket_renewal` | Subscription tickets (`ACTIVE`, `RENEWING`, `RENEWED`, `EXPIRED`, `CANCELLED`) and renewal history (`TL-10`, `TL-15`). |
| `Cổng vào / Cổng ra` | `parking_gate` | Entry and exit barrier gates with camera identifiers (`Cổng vào 1/2`, `Cổng ra 1/2/3`) (`TL-06`). |
| `Lịch sử ra/vào` / `DoXe` | `vehicle_entry_exit_log` | Parking sessions (`session_code`) supporting registered and visitor vehicles (`vehicle_id NULL`), AI OCR confidence, and `fee_amount` (`TL-05`, `TL-06`). |
| `Giao dịch / Thanh toán` | `payment` | Financial transactions (`CASH`, `VIETQR`) targeting exactly one session, ticket, or renewal (`TL-07`). |
| `Hoạt động gần đây` | `activity_log` | Append-only operational activity log displayed on the Parking Map screen (`TL-12`). |
| `Cảnh báo bất thường & khẩn cấp` | `system_alert` | Dashboard security and operational alerts (`BLACKLIST_PLATE`, `OVERSTAY`, `CAMERA_QUALITY`, `SYSTEM`) (`TL-13`). |

---

## 3. Database Entity Catalog & Structural Metrics

The physical database schema (Schema v2) comprises strictly **28 Base Tables**, **8 Analytical Views**, **69 Foreign Keys** (100% `ON DELETE RESTRICT`, `0` non-`RESTRICT`), **338 Base Table Columns** (100% documented with `COMMENT ON COLUMN`), **55 View Columns** (bringing total columns to **393**, with `0` undocumented tables, views, or columns), **25 Triggers**, **9 Trigger Functions**, **6 Non-Trigger Functions** (`fn_normalize_license_plate`, `fn_recompute_slot_status`, and 4 `fn_stat_*` functions), **150 `CHECK` Constraints**, **9 `UNIQUE` Constraints**, **2 GiST `EXCLUDE` Constraints**, and **116 Indexes** (`28` `pk_*` primary-key indexes, `38` partial unique indexes + `9` `UNIQUE` constraint indexes = `47` `uq_*` unique indexes, `39` `idx_*` secondary B-tree indexes, and `2` `excl_*` GiST exclusion indexes):

| Table / View Name | Type | Cols | FKs | Functional Summary |
| :--- | :---: | :---: | :---: | :--- |
| `account` | Table | 12 | 1 | Email/phone login principals, password hashes, and RBAC roles (`TL-01`). |
| `persistent_login_token` | Table | 9 | 1 | OWASP persistent remember-me session tokens (`TL-01`, ADR-0004). |
| `password_reset_token` | Table | 7 | 1 | One-time password recovery tokens (`TL-01`, `SCO-05`). |
| `position` | Table | 9 | 1 | Staff position catalog (`QL`, `NVVH`, `NVTN`, `KTV`) (`TL-11`). |
| `administrative_province` | Table | 5 | 0 | Level-1 provincial administrative units (`TL-15`, `OQ-50`). |
| `administrative_district` | Table | 6 | 1 | Level-2 district administrative units (`TL-15`, `OQ-50`). |
| `administrative_ward` | Table | 6 | 1 | Level-3 ward/commune administrative units (`TL-15`, `OQ-50`). |
| `employee` | Table | 20 | 5 | Staff profiles (`NV001`..`NV0005`), `ACTIVE`/`INACTIVE` status, and address FKs (`TL-11`). |
| `customer` | Table | 22 | 4 | Customer profiles (`KH0001`), `ACTIVE`/`SUSPENDED`/`BLACKLISTED` status, and PII flags (`TL-08`). |
| `plate_blacklist` | Table | 12 | 2 | Blacklisted license plates with normalized uniqueness and unpaid debt (`TL-08`). |
| `vehicle_type` | Table | 9 | 1 | Vehicle type catalog (`CAR`, `MOTO`, `EV`) (`TL-09`). |
| `ticket_type` | Table | 11 | 1 | Subscription ticket tariff catalog (`DAILY`, `MONTHLY`, `QUARTERLY`, `YEARLY`) (`TL-10`). |
| `vehicle` | Table | 18 | 4 | Registered customer vehicles with `license_plate_norm`, ticket preferences, and `notes` (`TL-09`). |
| `parking_lot` | Table | 10 | 1 | Top-level parking facility (`Bãi xe Smart Mobility`) (`TL-02`). |
| `parking_floor` | Table | 10 | 2 | Parking floors (`B1..B3`, `F1`) scoped per lot (`TL-02`). |
| `parking_zone` | Table | 10 | 2 | Parking zones (`A..C`) scoped per floor (`TL-02`). |
| `parking_slot` | Table | 16 | 2 | Physical parking slots with `slot_kind` (`STANDARD`, `PRIORITY`, `EV_CHARGING`) and 5 statuses (`TL-02`, `TL-03`). |
| `slot_allowed_vehicle_type` | Table | 3 | 2 | M:N mapping of allowed vehicle types per parking slot (`TL-15`). |
| `slot_reservation` | Table | 17 | 5 | Pre-booked slot reservations with GiST anti-overlap exclusion (`TL-04`). |
| `ticket` | Table | 17 | 6 | Issued parking tickets with GiST anti-overlap exclusion and `RENEWING` status (`TL-10`). |
| `ticket_renewal` | Table | 15 | 6 | Ticket renewal history tracking old/new types, slots, prices, and `notes` (`TL-10`, `TL-15`). |
| `parking_gate` | Table | 13 | 2 | Entry and exit gates (`IN`, `OUT`) with `camera_status` and `is_auto_scan` (`TL-06`). |
| `vehicle_entry_exit_log` | Table | 22 | 7 | Parking sessions (`session_code`), nullable `vehicle_id` for visitors, AI OCR metrics, and `fee_amount` (`TL-05`, `TL-06`). |
| `payment` | Table | 17 | 5 | Unified payments (`CASH`, `VIETQR`) targeting exactly one session, ticket, or renewal (`TL-07`). |
| `activity_log` | Table | 7 | 1 | Append-only operational activity feed (`Hoạt động gần đây`) (`TL-12`). |
| `system_alert` | Table | 10 | 1 | Dashboard security and operational anomaly alerts (`TL-13`). |
| `news` | Table | 15 | 2 | Facility news articles (`TL-15`, `SCO-03`). |
| `notification` | Table | 10 | 2 | Portal notifications (`TL-15`). |
| **Total Base Tables** | **28** | **338** | **69** | **100% `ON DELETE RESTRICT`, `0` `CASCADE`, `0` `DROP` statements** |
| `v_slot_occupancy_by_floor` | View | 17 | — | Real-time floor/zone occupancy, EV charging, priority slots, and utilization percentage (`TL-14`). |
| `v_revenue_today_by_method` | View | 6 | — | Today's paid revenue split across `CASH` (`Tiền mặt`) and `VIETQR` (`QR`) (`TL-07`, `TL-14`). |
| `v_traffic_by_hour` | View | 4 | — | Hourly entry/exit traffic series (`00..23`) for today (`TL-14`). |
| `v_ai_recognition_stats` | View | 7 | — | AI plate recognition accuracy, scan count, and error count (`TL-06`, `TL-14`). |
| `v_customer_status_summary` | View | 4 | — | Customer KPI summary (`total`, `active`, `currently_parked`, `blacklisted_or_suspended`) (`TL-08`). |
| `v_revenue_statistics` | View | 6 | — | Monthly, quarterly, and annual revenue aggregation (`TL-07`, `TL-15`). |
| `v_vehicle_traffic_daily` | View | 4 | — | Daily vehicle traffic flow metrics (`TL-15`). |
| `v_customer_vehicle_summary` | View | 7 | — | Customer registered vehicle and active ticket counts (`TL-15`). |

### 3.1. Database Triggers & Procedural Functions Summary

The database enforces real-time synchronization, temporal validity, OCC versioning, append-only immutability, and barrier access security through **25 Triggers**, **9 Trigger Functions**, and **6 Non-Trigger Functions**:

1. `fn_normalize_license_plate(p_input TEXT)` (`IMMUTABLE STRICT PARALLEL SAFE` SQL function): Normalizes license plates via `UPPER(REGEXP_REPLACE(p_input, '[^A-Za-z0-9]', '', 'g'))` for stored generated columns `vehicle.license_plate_norm`, `vehicle_entry_exit_log.license_plate_norm`, and `plate_blacklist.license_plate_norm` (`TL-05`, `TL-08`, `TL-09`, `OQ-75`).
2. `fn_update_row_version_and_timestamp()` (`17` Triggers): Attached `BEFORE UPDATE` on `account`, `position`, `employee`, `customer`, `plate_blacklist`, `vehicle_type`, `ticket_type`, `vehicle`, `parking_lot`, `parking_floor`, `parking_zone`, `parking_slot`, `slot_reservation`, `ticket`, `parking_gate`, `payment`, and `news` (`TL-15`, `OQ-64`).
3. `fn_guard_parking_slot_status()` (`1` Trigger: `trg_guard_parking_slot_status` on `parking_slot`): Blocks manual status changes that contradict open sessions (`PROP-4.5.2-P02`, `PROP-4.5.2-P03`) or active tickets/reservations (`PROP-4.5.2-P04`) (`TL-03`, `OQ-81`).
4. `fn_sync_ticket_status()` (`1` Trigger: `trg_ticket_status_sync` on `ticket`): Rejects assigning a `MAINTENANCE` slot (`PROP-4.5.2-P01`) and auto-transitions active tickets to `EXPIRED` when `effective_to <= CURRENT_TIMESTAMP` (`TL-03`, `TL-10`, `OQ-63`).
5. `fn_guard_slot_reservation_write()` (`1` Trigger: `trg_guard_slot_reservation_write` on `slot_reservation`): Rejects reserving a `MAINTENANCE` slot (`PROP-4.5.2-P01`) or a slot already covered by an overlapping active ticket (`MSG-4.5.2-M02`), and auto-transitions expired reservations (`TL-04`).
6. `fn_guard_slot_reservation_on_entry()` (`1` Trigger: `trg_guard_slot_reservation_on_entry` on `vehicle_entry_exit_log`): Allows visitor entries (`vehicle_id IS NULL`), verifies normalized plate match when `vehicle_id IS NOT NULL` (`MSG-4.5.1-M02`), blocks `MAINTENANCE` slots (`PROP-4.5.2-P01`), blocks slots reserved by another vehicle's ticket (`MSG-4.5.2-M02`), and blocks slots reserved via `slot_reservation` for another vehicle (`PROP-4.5.2-P05`) (`TL-03`, `TL-04`, `TL-05`, `OQ-67`, `OQ-81`).
7. `fn_recompute_slot_status(p_slot_id BIGINT)` + `fn_sync_slot_status_on_traffic()`, `fn_sync_slot_status_on_ticket()`, `fn_sync_slot_status_on_reservation()` (`3` `AFTER` Triggers): Deterministically recompute `parking_slot.status` (`OCCUPIED` -> `RESERVED` -> `AVAILABLE`, preserving `MAINTENANCE` and `CHARGING`) and synchronize `vehicle.ticket_type_id` and `vehicle.ticket_expires_at` (`TL-03`, `TL-04`, `TL-15`, `OQ-52`, `OQ-63`).
8. `fn_prevent_activity_log_mutation()` (`1` Trigger: `trg_activity_log_immutable` on `activity_log`): Blocks `UPDATE` and `DELETE` on `activity_log` (`PROP-4.5.2-P06`, `TL-12`, `OQ-81`).

### 3.2. Statistical Stored Functions for Date-Range Reporting (`TL-15`, SRS 4.7.1 & 4.7.2)

The database provides **4 Statistical Functions** accepting `(p_from_date DATE, p_to_date DATE)` and validating `p_from_date <= p_to_date` (`PROP-4.7.2-P02`, `OQ-37`):

1. `fn_stat_vehicles_by_day(p_from_date DATE, p_to_date DATE)`
2. `fn_stat_vehicles_by_floor(p_from_date DATE, p_to_date DATE)`
3. `fn_stat_vehicles_by_customer(p_from_date DATE, p_to_date DATE)`
4. `fn_stat_revenue_by_period(p_from_date DATE, p_to_date DATE)`

---

## 4. Key Architectural & Database Design Decisions (Schema v2)

- **Frontend-First Login & Self-Registration (`TL-01`, `OQ-71`)**: `account` authenticates via `email` and/or `phone` (`ck_account_login_identifier_present`), enforces active email uniqueness (`uq_account_email_active`) and phone uniqueness (`uq_account_phone_active`), and supports `CUSTOMER` self-registration.
- **4-Level Parking Hierarchy & Slot Kinds (`TL-02`, `TL-03`, `OQ-73`, `OQ-77`)**: Physical topology is normalized into `parking_lot -> parking_floor -> parking_zone -> parking_slot` with `fk_slot_zone FOREIGN KEY (zone_id) REFERENCES parking_zone (id) ON DELETE RESTRICT`, `slot_kind IN ('STANDARD', 'PRIORITY', 'EV_CHARGING')`, `status IN ('AVAILABLE', 'OCCUPIED', 'RESERVED', 'CHARGING', 'MAINTENANCE')`, and `ck_slot_charging_requires_ev_kind`.
- **Slot Reservations & Ticket Anti-Overlap (`TL-04`, `TL-10`)**: Both `ticket` (`excl_ticket_slot_time_overlap`) and `slot_reservation` (`excl_reservation_slot_time_overlap`) use `btree_gist` exclusion constraints over `tstzrange(..., '[)')` to prevent overlapping allocations on the same slot.
- **Unregistered Visitor Sessions, Gates & AI Recognition (`TL-05`, `TL-06`, `OQ-65`, `OQ-66`)**: `vehicle_entry_exit_log` supports visitor vehicles (`vehicle_id NULL`), unique `session_code`, `entry_gate_id`/`exit_gate_id` referencing `parking_gate`, `ai_confidence`, `recognition_source`, `review_status`, and `fee_amount`, guarded by 3 open-session partial unique indexes (`uq_log_open_session_slot`, `uq_log_open_session_vehicle`, `uq_log_open_session_plate`).
- **Unified Payments (`TL-07`, `OQ-72`)**: `payment` supports `CASH` and `VIETQR` methods with `ck_payment_single_target CHECK (num_nonnulls(session_id, ticket_id, renewal_id) = 1)` and `ck_payment_paid_timestamp`.
- **Customer & Plate Blacklist (`TL-08`)**: `customer` tracks `status IN ('ACTIVE', 'SUSPENDED', 'BLACKLISTED')` (`ck_customer_blacklist_reason`), while `plate_blacklist` tracks blacklisted plates (including visitors) using stored generated `license_plate_norm` (`uq_plate_blacklist_norm_active`).
- **Append-Only Activity Log & System Alerts (`TL-12`, `TL-13`)**: `activity_log` is protected against `UPDATE`/`DELETE` by `trg_activity_log_immutable`, and `system_alert` tracks operational/security anomalies (`BLACKLIST_PLATE`, `OVERSTAY`, `CAMERA_QUALITY`, `SYSTEM`).

---

## 5. Audit Trail Architecture via `django-simple-history`

In accordance with ADR-0003:

- When the Django backend application is initialized, `django-simple-history` automatically generates historical audit tables (`historical_employee`, `historical_ticket`, `historical_customer`).
- Application-level soft deletion updates `deleted_at` and `deleted_by`, while all `69` foreign keys enforce `ON DELETE RESTRICT`.

---

## 6. Open Questions Catalog Index

All technical proposals, resolved Frontend-vs-SRS decisions (`TL-01`–`TL-16`), and remaining open questions (`OQ-79`–`OQ-83`) are tracked in [`docs/requirements/01-open-questions.md`](../docs/requirements/01-open-questions.md) and [`docs/requirements/06-frontend-srs-db-alignment.md`](../docs/requirements/06-frontend-srs-db-alignment.md):

- **OQ-01..OQ-70**: Core security, administrative hierarchy (`OQ-50`, `OQ-62`), OCC & soft-delete guards (`OQ-64`), and operational constraints updated with `TL-01`–`TL-16` resolutions where applicable.
- **OQ-71..OQ-77**: Resolved and implemented in Schema v2 per Team Lead Decisions `TL-01`–`TL-16`.
- **OQ-78**: ERD diagram completeness implemented for Schema v1 in Rounds 19 & 21; Schema v2 ERD regeneration is scheduled for Round 24.
- **OQ-79**: Year ticket default price (`4.800.000đ` from `1.200.000đ × 4` quarters vs annual discount).
- **OQ-80**: Exact per-session tariff calculation rules (hourly/daily rates by vehicle type, grace minutes, 36h overstay fee).
- **OQ-81**: Status value lists (`slot_reservation.status`, `payment.status`, `system_alert.severity`, `vehicle_entry_exit_log.review_status`) and guard messages (`PROP-4.5.2-P02`–`P06`) not shown in the Frontend.
- **OQ-82**: VietQR payment provider, webhook verification, and `provider_ref` format.
- **OQ-83**: Camera / AI license-plate recognition service integration and confidence threshold.

---

## 7. UML Entity Relationship Diagram (ERD) Specifications & Artifacts

> **Note (Round 23)**: The ERD files (`db/03-erd.asta` and `db/04-erd.png`–`db/09-erd-reference-views.png`) will be regenerated for Schema v2 in Round 24; the descriptions and SHA-256 checksums below reflect Schema v1.

The database architecture is visually modeled and maintained through native Astah UML specifications conforming to the official OMG UML 2.1 standard and Astah Open API 12.0.0 guidelines:

### 7.1. Diagram Deliverables & Formats

- **Editable Source Model**: [`db/03-erd.asta`](03-erd.asta) — Native Astah UML 12.0.0 project file containing the complete object-oriented domain representation, classes, stereotypes, attributes, and associations.
- **Master Overview Export**: [`db/04-erd.png`](04-erd.png) — Ultra-clear, high-resolution rendering exported at 400 DPI via the live MCP tool `astah_export_diagram_image` (backed by official Astah CLI `astah-command.bat` / `JudeCommandRunner`) (Resolution: **4166 × 1432 px**, exceeding the >= 3000px clarity threshold).
- **Module Diagrams (5 Sub-systems with 100% Attribute & Business FK Coverage)**:
  - [`db/05-erd-account-staff.png`](05-erd-account-staff.png) — Account, Authentication & Staff Management (1473 × 1564 px, 7 nodes, 7 links).
  - [`db/06-erd-customer-vehicle.png`](06-erd-customer-vehicle.png) — Customer, Vehicle & Vehicle Types (2006 × 1097 px, 7 nodes, 7 links).
  - [`db/07-erd-parking-ticket.png`](07-erd-parking-ticket.png) — Parking Slots, Tariffs & Ticketing Lifecycle (2520 × 1736 px, 10 nodes / 8 tables, 14 links).
  - [`db/08-erd-operations-content.png`](08-erd-operations-content.png) — Gate Operations Log, News & Notifications (2513 × 1276 px, 9 nodes / 8 tables, 11 links).
  - [`db/09-erd-reference-views.png`](09-erd-reference-views.png) — Administrative Geography & Analytical Database Views (1500 × 1046 px, 7 nodes, 2 links).

### 7.2. Model Metrics & Structural Parity (PostgreSQL 18.6 Schema Match)

The on-disk `db/03-erd.asta` is 100% synchronized with `db/01-schema.sql` (213 table columns, 22 view columns, 235 total attributes, 44 FK associations, and 0 missing non-`deleted_by` business FK links across all 6 diagrams `04..09` per `D8`/`OQ-78`):

- **23 Business Classes**:
  - **19 Physical Tables**: Modeled as UML Classes adorned with the `«table»` stereotype, encompassing all 213 database table columns (including `license_plate_norm VARCHAR(20)` on `vehicle` and `vehicle_entry_exit_log`) with constraint stereotypes (`«PK»`, `«FK»`, `«UQ»`, `«PUQ»`, `«UQ1»`, `«PUQ1»`, `«PUQ2»`, `«PUQ3»`).
  - **4 Analytical Views**: Encapsulated within a dedicated `Views` UML Package (`v_revenue_statistics`, `v_vehicle_traffic_daily`, `v_slot_occupancy_by_floor`, `v_customer_vehicle_summary`) with the `«view»` stereotype (22 view attributes total), strictly isolated from persistent entities.
- **18 SQL Primitive Datatype Classes Encapsulated**:
  - 18 SQL primitive types (`BIGINT`, `INTEGER`, `SMALLINT`, `VARCHAR(10)`, `VARCHAR(20)`, `VARCHAR(45)`, `VARCHAR(50)`, `VARCHAR(64)`, `VARCHAR(100)`, `VARCHAR(255)`, `TEXT`, `BOOLEAN`, `DATE`, `TIMESTAMPTZ`, `NUMERIC(5, 2)`, `NUMERIC(12, 2)`, `SERIAL`, `BIGSERIAL`) are encapsulated within a dedicated `DataTypes` package.
  - Total classes in ASTA: 41 classes (23 business entities + 18 datatype classes).
  - This architecture preserves native PostgreSQL column definitions across all 213 table attributes and 22 view attributes (235 total) without polluting the top-level business domain model.
- **44 Foreign Key Associations (100% Populated & Modeled on `ERD_Overview`, 100% Business FKs Drawn on `05..09`)**:
  - 100% of physical relational constraints are modeled as directed associations from child table to parent table with exact multiplicities:
    - Required Parent Links: `0..*` (or `0..1`) to `1` (e.g., `vehicle` to `customer`, `ticket` to `parking_slot`, and `vehicle_entry_exit_log` to `vehicle` via `fk_log_vehicle` per Owner Decision 10).
    - Nullable Parent Links: `0..*` to `0..1` (e.g., `vehicle_entry_exit_log` to `slot_id`).
    - **11 Soft-Deletion Audit Links**: All 11 `deleted_by -> account` foreign keys are fully modeled and visually rendered on `ERD_Overview` using quiet grey lines (`#B0BEC5`).

### 7.3. Constraint Stereotype Conventions & Legend Note

Composite and partial unique constraints are explicitly marked using standardized UML stereotypes:

- `«PK»`: Primary key (single column or component of composite PK).
- `«FK»`: Foreign key referencing parent entity.
- `«UQ»`: Standard global single-column unique constraint (e.g., `persistent_login_token.series`, `password_reset_token.token_hash`, `administrative_province.code`).
- `«PUQ»`: Active-record partial unique index (filtered by `WHERE deleted_at IS NULL` or active session), applied to `account.username`, `employee.code`, `customer.code`, `ticket.code`, `vehicle_type.code`, `vehicle.license_plate_norm`, `vehicle_entry_exit_log.license_plate_norm` (`OQ-75`), etc.
- Composite Multi-Column Stereotypes:
  - `parking_slot`: `floor_number`: `«PUQ1, PUQ2, PUQ3»`, `slot_number`: `«PUQ1»`, `code`: `«PUQ2»`, `map_row`: `«PUQ3»`, `map_col`: `«PUQ3»` (enforcing floor-scoped slot uniqueness, code uniqueness, and spatial 2D grid position uniqueness for active slots).
  - `vehicle`: `id`: `«PK, UQ1»`, `customer_id`: `«FK, UQ1»` (enforcing composite parentage integrity for tickets).
  - `administrative_district`: `id`: `«PK, UQ1»`, `province_id`: `«FK, UQ1»`.
  - `administrative_ward`: `id`: `«PK, UQ1»`, `district_id`: `«FK, UQ1»`.
- **UML Legend Note**: Added directly to `ERD_Overview` (`db/04-erd.png`) below the South Corridor (`x=500, y=675`) so zero relationship lines cross or pass behind the note box, documenting the complete 213-attribute schema.

### 7.4. Visual Readability & Layout Architecture

- **Master Overview (`db/04-erd.png`) - 100% Visual Association Coverage**:
  - **All 44 Relationships Visually Rendered**: 100% of the 44 associations exist directly on the canvas without omitting or hiding any links.
  - **Hub-Centered Layout**: High-degree hub tables `account` (14 incoming FKs) and `employee` (7 FKs) are positioned centrally in Column 3 (`x=1280`), flanked by administrative/content modules on the left and customer/vehicle/ticket/slot modules on the right.
  - **11 `deleted_by -> account` Links**: Rendered with subtle `#B0BEC5` quiet styling, routed along dedicated nested highway channels to prevent visual dominance over core business flows.
  - **Zero Table Crossings**: Every association line routes through dedicated vertical channels (V-Channels between table columns) and horizontal highway corridors. **Zero lines cross through any non-endpoint table boundary**.
  - **Zero Label Overlaps**: Multiplicity labels are cleanly spaced with dedicated attachment ports on table boundaries.
  - **Minimal Link Crossings (`20` Crossings Across 44 FKs)**: By placing `account` and `employee` at the center of the 6-column grid and nesting corridor Y-levels monotonically by distance, orthogonal line-to-line crossings are reduced from 96 down to **20** (well below the $\le 30$ readability ceiling). Both the complete 44-relationship topological overview (`04-erd.png`) AND the 5 zero-table-crossing, 100%-attribute-expanded module diagrams (`05`..`09`) are retained together.
  - **Ultra-High Resolution**: Exported at **4166 × 1432 px** (400 DPI), fully legible at 100% zoom.
- **5 Detailed Module Diagrams (`05`..`09`) - 4-Way Orthogonal Layout**:
  - Primary subsystem tables display **100% of attributes and column types** (all 213 table attributes and 22 view attributes = 235 total attributes visible across the 5 diagrams).
  - Inter-module relationships are cleanly linked via **Collapsed Neighbor Stubs** (`height = 45px`, `width = 200..240px`, soft gray fill `#ECEFF1`).
  - Stubs are placed strictly in the 4 cardinal directions (North, South, East, West) around primary tables so that each boundary side receives at most one relationship link and all non-`deleted_by` business FKs between present tables are drawn (`7` on `05`, `7` on `06`, `14` on `07`, `11` on `08`, `2` on `09`).
- **Automated Geometry Verification**:
  - `ERD_Overview`: Table Crossings = **0**, Missing Business FKs = **0**, Link Crossings = **20**.
  - `Account_Staff`: Table Crossings = **0**, Missing Business FKs = **0** (`7` links).
  - `Customer_Vehicle`: Table Crossings = **0**, Missing Business FKs = **0** (`7` links).
  - `Parking_Ticket`: Table Crossings = **0**, Missing Business FKs = **0** (`14` links).
  - `Operations_Content`: Table Crossings = **0**, Missing Business FKs = **0** (`11` links).
  - `Reference_Views`: Table Crossings = **0**, Missing Business FKs = **0** (`2` links).
  - **TOTAL**: Table Crossings = **0**, Missing Business FKs Across All 6 Diagrams = **0**.

### 7.5. Cryptographic Deliverables Verification (SHA-256 Checksums)

All ERD deliverables are verified with SHA-256 checksums:

| Artifact File | Description | SHA-256 Checksum | Dimensions / File Size |
|---|---|---|---|
| `03-erd.asta` | Master Astah UML Model | `147487C932782F3B850EFB3D5121BC30F17ACF48AAD3C17FD60AE12561BD19C4` | 56,762 bytes |
| `04-erd.png` | Master ERD Overview (44 Links) | `93CAB0653BA799F1FD79AF16842FF01D7F93D32E509FE76A0B2BF311BD3DC5FB` | 4166 × 1432 px (204,481 bytes) |
| `05-erd-account-staff.png` | Account & Staff Module ERD (7 Links) | `9CF15751FD37B0207161B4C000E087CC17F8E2545FF3B7AC4FACBB9AA6FEB560` | 1713 × 1564 px (149,444 bytes) |
| `06-erd-customer-vehicle.png` | Customer & Vehicle Module ERD (7 Links) | `DCD4BA760DAF074E9D6233825AF61C15F9DDA30F9C901964A4D4AF7CD9EBB689` | 2006 × 1097 px (128,426 bytes) |
| `07-erd-parking-ticket.png` | Parking & Ticket Module ERD (14 Links) | `2E979559DF66971D7066C74324FC69FAFB5746698F731291F255BB2100135135` | 2706 × 1736 px (231,397 bytes) |
| `08-erd-operations-content.png` | Operations & Content Module ERD (11 Links) | `E3D0A7504BB7CB5595D7092D5266B613DEBA03017942738293BFF71B55344F46` | 2513 × 1276 px (160,000 bytes) |
| `09-erd-reference-views.png` | Reference & Views Module ERD (2 Links) | `7DD070142C7D07DB90B752F8885353BD608FCACCD55169CFACE7E2E7BE4EDEEA` | 1500 × 1046 px (92,638 bytes) |

### 7.6. Method Disclosure & Integrity Attestation

- **Model Generation, Round 19 MCP Update & Routing**: Initially architected via Astah Open API 12.0.0 (`astah-api.jar` — `ProjectAccessor`, `ClassDiagramEditor`, `TransactionManager`) per Owner Decision (9), and updated in Round 19 on a sandbox copy exclusively via the live `astah-uml` MCP tools (`astah_delete_element`, `astah_add_attribute`, `astah_set_presentation_style`, `astah_add_presentation_link`, and the new `astah_set_note_text` tool) before SHA-256-verified copy back to `db/`.
- **Export Pipeline via Live MCP**: Exported through the live Antigravity MCP tool `astah_export_diagram_image` (`dpi=400`, `format="png"`, backed by Astah's official batch CLI command engine `astah-command.bat` / `JudeCommandRunner`), guaranteeing crisp anti-aliased font rendering and exact graphical fidelity.
- **Verification**: A read-only Astah API check on a copy of `03-erd.asta` (the check program is not committed) found 213 table attributes, 22 view attributes, 44 associations and every non-`deleted_by` foreign key drawn on each module diagram whose two tables are both shown. Display in the Astah GUI was not verified by the team.
