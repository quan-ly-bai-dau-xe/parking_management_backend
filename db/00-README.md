# Database Schema & Seed Catalog — Parking Management Backend

This directory defines the enterprise physical relational database schema, lookup reference seed data, and architectural documentation for the Car Parking Lot Management System backend (`parking_management_backend`), targeting **PostgreSQL 18.6**. The schema faithfully implements all business requirements, Action tables, and wireframe elements specified in the SRS v4.1 (`Quan ly bai dau xe oto_SRS_v4.1.docx`), 25 embedded wireframes, and `Tasks_Sprint_1`.

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

## 2. Vietnamese SRS Specification Entity Mapping Table

The table below maps the Vietnamese entity names and informal references appearing throughout the SRS v4.1 text and wireframes to their normalized PostgreSQL relational database tables:

| Vietnamese SRS Name | Relational Table Name | Architectural & Business Representation |
| :--- | :--- | :--- |
| `ACCOUNT` | `account` | System login authentication table storing credentials, Argon2id/PBKDF2 password hashes, and RBAC roles (SRS 4.1). |
| `NHAN_VIEN` | `employee` | Staff profile table storing employee code (`NV-xxxx`), contact details, position, and hierarchical address links (SRS 4.3). |
| `Chức vụ` | `position` | Staff job position lookup catalog: Bảo vệ, Giữ xe, and Quản lý [PROPOSAL OQ-57] (SRS 4.3.1, 4.3.2). |
| `KHACH_HANG` | `customer` | Customer profile table storing code (`KH-xxxx`), national ID, contact details, and Decree 13/2023/ND-CP anonymization flag (SRS 4.4). |
| `XE` | `vehicle` | Customer registered vehicle table storing natural code (`Xe-xxx`), license plate, vehicle type, and ticket preference metadata (SRS 4.4.2, 4.4.3). |
| `LoaiVe` | `ticket_type` | Tariff lookup catalog defining ticket durations and standard prices: Vé Năm 100,000 VND, Vé Tháng, Vé Ngày (SRS 4.6.1). |
| `VE` | `ticket` | Issued parking ticket table binding vehicle, customer, physical parking slot, and temporal duration with anti-overlap exclusion (SRS 4.6). |
| `XeVe` | `ticket` (composite linkage) | Relational association binding vehicle, owner, ticket type, and assigned slot (`vehicle_id`, `customer_id`, `slot_id`, `ticket_type_id`) (SRS 4.4.2, 4.6). |
| `BaiXe` | `parking_slot` (facility modeling) | Physical parking facility represented through multi-level floors (`floor_number` 1..99) and dimensional slot capacity (SRS 4.5.2, 4.8). |
| `DoXe` | `vehicle_entry_exit_log` & `parking_slot.status` | Parking state captured via barrier OCR gate check-in/out timestamps and slot operational availability (SRS 4.5.1, 4.5.2). |
| `Bảng quản lý xe vào ra` | `vehicle_entry_exit_log` | Barrier gate operational log capturing recognized license plates, gate camera photo URLs, and timestamps (SRS 4.5.1). |

---

## 3. Database Entity Catalog & Structural Metrics

The physical database schema comprises strictly **19 Tables**, **44 Foreign Keys** (100% `ON DELETE RESTRICT`, 0 `CASCADE`), **213 Table Columns** (100% documented with `COMMENT ON COLUMN`), **4 Analytical Views** (22 view columns, bringing total columns to **235**), **14 Triggers**, **5 Trigger Functions**, **4 Statistical Functions**, **1 Immutable Normalization Function** (`fn_normalize_license_plate(text)`), and **18 DataTypes** (including `SMALLINT`):

| Table / View Name | Type | Columns | Foreign Keys | Functional Summary (1 Line per Entity) |
| :--- | :---: | :---: | :---: | :--- |
| `account` | Table | 11 | 1 | System user credentials, Argon2id hashes, and RBAC roles (SRS 4.1). |
| `persistent_login_token` | Table | 9 | 1 | OWASP persistent remember-me session tokens replacing insecure cookies (SRS 4.1, ADR-0004). |
| `password_reset_token` | Table | 7 | 1 | One-time password recovery tokens dispatched via registered email (SRS 4.1, SCO-05). |
| `position` | Table | 9 | 1 | Staff position catalog: Bảo vệ, Giữ xe, and Quản lý [PROPOSAL OQ-57] (SRS 4.3). |
| `administrative_province` | Table | 5 | 0 | Level-1 provincial administrative units for cascading address dropdown (SRS 4.3.2, 4.4.3, OQ-50). |
| `administrative_district` | Table | 6 | 1 | Level-2 district administrative units linked to parent province with composite uniqueness (SRS 4.3.2, OQ-50). |
| `administrative_ward` | Table | 6 | 1 | Level-3 commune/ward units linked to parent district with composite uniqueness (SRS 4.3.2, OQ-50). |
| `employee` | Table | 18 | 5 | Staff profiles with natural codes `NV-xxxx`, OCC versioning, and composite address integrity (SRS 4.3). |
| `customer` | Table | 19 | 4 | Customer profiles with natural codes `KH-xxxx`, national ID, and Decree 13 PII anonymization flag (SRS 4.4). |
| `vehicle_type` | Table | 9 | 1 | Vehicle categorization catalog: Xe 4 chỗ, Xe 7 chỗ, Xe 12 chỗ, and Xe máy (SRS 4.8.2, OQ-49). |
| `ticket_type` | Table | 11 | 1 | Ticket duration and tariff pricing catalog in VND (SRS 4.6.1, OQ-06, Rule 05). |
| `vehicle` | Table | 15 | 4 | Registered vehicles with raw `license_plate`, generated `license_plate_norm` uniqueness, ticket preference metadata, and composite owner key (SRS 4.4.2, OQ-52, OQ-53, OQ-75). |
| `parking_slot` | Table | 15 | 1 | Physical parking spaces with 2D grid coordinates, floor-scoped code uniqueness, and positive dimensions (SRS 4.5.2, 4.8, OQ-54, OQ-59, OQ-69). |
| `slot_allowed_vehicle_type` | Table | 3 | 2 | M:N association specifying allowed vehicle categories per parking slot (SRS 4.8.2). |
| `ticket` | Table | 16 | 5 | Issued parking tickets with GiST anti-overlap slot exclusion and composite vehicle-customer FK (SRS 4.6, OQ-61, OQ-64). |
| `ticket_renewal` | Table | 14 | 6 | Audit trail of ticket renewals tracking old/new tariff types and historical price mutations (SRS 4.6.3, OQ-58). |
| `vehicle_entry_exit_log` | Table | 15 | 5 | Barrier gate movements with raw `license_plate`, generated `license_plate_norm`, OCR camera snapshots, and operator tracking (SRS 4.5.1, SCO-01, OQ-75). |
| `news` | Table | 15 | 2 | Facility news articles published on landing portal home page (SCO-03, Tasks_Sprint_1). |
| `notification` | Table | 10 | 2 | System announcements and notifications displayed on portal home page (SRS 4.2). |
| **Total Tables** | **19 Tables** | **213 Cols** | **44 FKs** | **100% ON DELETE RESTRICT, 0 CASCADE, 0 DROP statements** |
| `v_revenue_statistics` | View | 6 | — | Monthly, quarterly, and annual revenue metrics preserving 100% historical sales (SRS 4.7.1). |
| `v_vehicle_traffic_daily` | View | 4 | — | Daily vehicle traffic flow metrics (entries, exits, currently parked) (SRS 4.7.2). |
| `v_slot_occupancy_by_floor` | View | 6 | — | Floor-by-floor slot committed capacity and utilization metrics computed dynamically from live sessions and active tickets, excluding maintenance from denominator (SRS 4.7.2, OQ-63). |
| `v_customer_vehicle_summary` | View | 6 | — | Registered vehicle and active ticket counts per customer eliminating Cartesian duplication (SRS 4.7.2). |

### 3.1. Database Triggers & Procedural Functions Summary
The database enforces real-time synchronization, temporal validity, OCC versioning, and barrier access security through **14 Triggers**, **5 Trigger Functions**, and **1 Immutable Normalization Function** (`fn_normalize_license_plate(p_input TEXT)`):
1. `fn_normalize_license_plate(p_input TEXT)` (`IMMUTABLE STRICT PARALLEL SAFE` SQL function): Normalizes license plates via `UPPER(REGEXP_REPLACE(p_input, '[^A-Za-z0-9]', '', 'g'))` to compute stored generated columns `vehicle.license_plate_norm` and `vehicle_entry_exit_log.license_plate_norm` and compare barrier gate plates (D5, F17, OQ-75).
2. `fn_update_row_version_and_timestamp()` (10 Triggers): Attached `BEFORE UPDATE` on `account`, `position`, `employee`, `customer`, `vehicle_type`, `vehicle`, `parking_slot`, `ticket_type`, `ticket`, `news` (ADR-0003, OQ-64).
3. `fn_sync_ticket_status()` (1 Trigger: `trg_ticket_status_sync`): Attached `BEFORE INSERT OR UPDATE` on `ticket` synchronizing `EXPIRED` status upon temporal boundary (OQ-63).
4. `fn_sync_slot_status_on_traffic()` (1 Trigger: `trg_slot_status_on_traffic`): Attached `AFTER INSERT OR UPDATE` on `vehicle_entry_exit_log` updating physical slot to `OCCUPIED` upon check-in, handling slot reassignment and session reopening, and resetting to `AVAILABLE` / `RESERVED` upon check-out (OQ-63, OQ-67).
5. `fn_sync_slot_status_on_ticket()` (1 Trigger: `trg_slot_status_on_ticket`): Attached `AFTER INSERT OR UPDATE` on `ticket` reserving slots upon ticket purchase, freeing them upon expiration/cancellation/renewal reassignment, and deterministically synchronizing vehicle ticket preference metadata (`ticket_type_id`, `ticket_expires_at`) to the latest active valid ticket (OQ-52, OQ-63).
6. `fn_guard_slot_reservation_on_entry()` (1 Trigger: `trg_guard_slot_reservation_on_entry`): Attached `BEFORE INSERT OR UPDATE OF slot_id, exit_time, vehicle_id, license_plate` on `vehicle_entry_exit_log` serializing slot access, validating that `fn_normalize_license_plate(NEW.license_plate)` matches `fn_normalize_license_plate(v.license_plate)` of the registered active vehicle (raising verbatim SRS error `'Lỗi dữ liệu không tìm thấy đê lưu'` with `SQLSTATE 23514` on mismatch), guarding reserved ticket slots against unauthorized other vehicles with verbatim SRS error `'Vị trí này đã có xe đk vé và đang sử dụng'`, and blocking check-in/reassignment into maintenance slots with proposed message `'Vị trí này đang bảo trì.'` (SRS 4.5.1, 4.5.2 ACT-4.5.2-A02, MSG-4.5.1-M02, MSG-4.5.2-M02, PROP-4.5.2-P01, OQ-46, OQ-63, OQ-67, OQ-75, Owner Decision 10).

### 3.2. Statistical Stored Functions for Date-Range Reporting (SRS 4.7.1 & 4.7.2)
To fulfill conditional date-range analytics specified in SRS 4.7.1 and 4.7.2 without modifying static operational views, the database provides **4 Statistical Functions** accepting `(p_from_date DATE, p_to_date DATE)`:
1. `fn_stat_vehicles_by_day(p_from_date DATE, p_to_date DATE)`: Aggregates daily vehicle traffic flow (`traffic_date`, `total_entries`, `total_exits`, `distinct_vehicles`) within the specified date boundary (SRS 4.7.2 REQ-4.7.2-F03).
2. `fn_stat_vehicles_by_floor(p_from_date DATE, p_to_date DATE)`: Aggregates vehicle parking sessions and ticket allocations grouped by active facility floor (`floor_number`, `entry_count`, `distinct_vehicle_count`, `ticket_count`), utilizing pre-aggregated CTEs to eliminate Cartesian distortion (SRS 4.7.2 REQ-4.7.2-F04).
3. `fn_stat_vehicles_by_customer(p_from_date DATE, p_to_date DATE)`: Evaluates customer vehicle onboarding and ticket purchasing activity (`customer_id`, `customer_code`, `customer_name`, `registered_vehicle_count`, `period_ticket_count`) over the target window (SRS 4.7.2 REQ-4.7.2-F05).
4. `fn_stat_revenue_by_period(p_from_date DATE, p_to_date DATE)`: Computes financial revenue across initial ticket issuance and renewal transactions (`report_year`, `report_quarter`, `report_month`, `total_tickets_sold`, `total_renewals`, `total_revenue`), preserving 100% of historical transactions (SRS 4.7.1).

All 4 statistical functions validate date parameters (`p_from_date IS NOT NULL AND p_to_date IS NOT NULL AND p_from_date <= p_to_date`), raising proposed error message `PROP-4.7.2-P02`: `'Khoảng thời gian thống kê không hợp lệ (Từ ngày phải nhỏ hơn hoặc bằng Đến ngày).'` upon invalid boundary input (`OQ-37`).


---

## 4. Key Architectural & Database Design Decisions

### 4.1. Elimination of Cartesian Row Duplication in Analytical Views
In previous view designs, joining `customer` simultaneously with `vehicle` and `ticket` created a Cartesian product (e.g., a customer owning 2 vehicles and 3 active tickets produced 6 joined rows). Consequently, `COUNT(v.id)` erroneously evaluated to 6 instead of 2.
- **Resolution**: `v_customer_vehicle_summary` and `v_slot_occupancy_by_floor` now utilize pre-aggregated Common Table Expressions (CTEs) grouping by foreign key before joining with the primary dimension. This guarantees mathematical accuracy and prevents Cartesian row multiplication.

### 4.2. Pure Non-Destructive Creation Script
In accordance with ADR-0003 and `.claude/rules/05-postgresql-data-modeling.md`, destructive DDL statements (`DROP TABLE ... CASCADE` and `DROP VIEW`) are strictly prohibited in repository schema files.
- **Resolution**: All 19 `DROP TABLE` and 4 `DROP VIEW` statements were completely removed. `db/01-schema.sql` is a pure creation script executed within an atomic `BEGIN ... COMMIT` transaction block. Re-running the script against an existing database fails safely without data loss.

### 4.3. Referential Integrity Between Customer and Vehicle on Ticket (OQ-61)
The SRS requires that when issuing a ticket for a customer, the selectable vehicles are strictly those owned by that customer.
- **Resolution**: A composite unique constraint `CONSTRAINT uq_vehicle_id_customer UNIQUE (id, customer_id)` is defined on `vehicle`. A composite foreign key `CONSTRAINT fk_ticket_vehicle_customer FOREIGN KEY (vehicle_id, customer_id) REFERENCES vehicle (id, customer_id) ON DELETE RESTRICT` is established on `ticket`. This prevents creating a ticket referencing Customer A with a vehicle owned by Customer B at the database constraint layer.

### 4.4. Hierarchical Administrative Boundary Validation (OQ-50, OQ-62)
Under Vietnam's primary legal framework:
- **Law No. 72/2025/QH15** (*Luật Tổ chức chính quyền địa phương*, passed `16-06-2025`, effective `16-06-2025` per **Article 51 Clause 1**, published in Official Gazette / Công báo Nos. 807 + 808 on `24-06-2025`, primary PDF at <https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/7/2025_807-808_72-2025-qh15..pdf>):
  - **Article 1 Clause 1**: Administrative units are organized into **02 levels**: provincial level (*tỉnh, thành phố trực thuộc trung ương*) and communal level (*xã, phường, đặc khu trực thuộc cấp tỉnh*).
  - **Article 51 Clause 3**: District-level local government bodies end their operation from **`01-07-2025`**.
- **Resolution No. 202/2025/QH15** (*Nghị quyết về việc sắp xếp đơn vị hành chính cấp tỉnh*, passed `12-06-2025`, effective `12-06-2025` per **Article 2 Clause 1** with new provincial administrations operating from `01-07-2025` per **Article 2 Clause 2**, official portal at <https://vanban.chinhphu.vn/?pageid=27160&docid=213930>, signed PDF at <https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/6/202qh.signed.pdf>):
  - **Article 1 Clause 10 & Clause 24**: Merges Quảng Nam province and Đà Nẵng city into the new **Đà Nẵng city** ($11,859.59\text{ km}^2$, population $3,065,628$), establishing **34 provincial-level units** nationwide (28 provinces and 06 centrally-run cities).
- **Architectural Proposal (`[PROPOSAL]` OQ-50, OQ-62)**: Because the SRS v4.1 wireframes (`image5.png`, `image6.png`, `image10.png`) still display 3 cascading dropdowns (`Tỉnh/TP -> Quận/Huyện -> Phường/Xã`, e.g., `Quảng Nam -> Điện Bàn -> Điện Ngọc`), the schema retains the 3-table design (`administrative_province`, `administrative_district`, `administrative_ward`) with composite foreign keys (`FOREIGN KEY (district_id, province_id) REFERENCES administrative_district (id, province_id)` and `FOREIGN KEY (ward_id, district_id) REFERENCES administrative_ward (id, district_id)`) as an explicit `[PROPOSAL]` pending Product Owner decision on migrating to a 2-level address model.

### 4.5. Real-Time Derived State Synchronization & Dynamic Occupancy View (OQ-63)
To prevent physical slot status and ticket status from drifting over time, the database implements event-driven synchronization triggers and dynamic analytical metrics:
- **Resolution**: 
  1. Trigger `trg_ticket_status_sync` automatically updates ticket status to `EXPIRED` whenever `effective_to <= CURRENT_TIMESTAMP`.
  2. Trigger `trg_slot_status_on_traffic` dynamically synchronizes slot status upon barrier vehicle movements (`OCCUPIED` upon vehicle entry, handling slot reassignment and session reopening, and resetting to `AVAILABLE` or `RESERVED` upon exit if an active ticket remains).
  3. Trigger `trg_slot_status_on_ticket` synchronizes parking slot status directly with the ticket lifecycle: transitions slot status to `RESERVED` immediately upon issuing an active ticket, and returns it to `AVAILABLE` when a ticket expires, is cancelled, soft-deleted, or moved to another slot upon renewal.
  4. View `v_slot_occupancy_by_floor` computes dynamic real-time utilization directly from live presence in `vehicle_entry_exit_log` (`exit_time IS NULL`) or active ticket duration windows (`CURRENT_TIMESTAMP BETWEEN effective_from AND effective_to` with `status = 'ACTIVE'` and `deleted_at IS NULL`), completely eliminating time-based status drift. Moreover, `MAINTENANCE` slots are excluded from the denominator (`operational_slots = total_slots - maintenance_slots`), guaranteeing the invariant `available_slots + occupied_slots = operational_slots` and returning accurate operational occupancy percentages.

### 4.6. Database-Level Optimistic Concurrency Control & Ticket Deletion Guard (OQ-64)
- **Resolution**: 
  1. A `BEFORE UPDATE` trigger function `fn_update_row_version_and_timestamp()` is attached to all versioned entities, automatically incrementing `row_version = OLD.row_version + 1` and updating `updated_at = CURRENT_TIMESTAMP`.
  2. A check constraint `CONSTRAINT ck_ticket_delete_only_expired CHECK (deleted_at IS NULL OR effective_to <= deleted_at)` enforces at the database level that active tickets can never be soft-deleted before expiration.

### 4.7. Customer Vehicle Onboarding with Ticket Preferences & Preference Constraints (OQ-52)
Wireframe screens 4.4.3 and 4.4.4 allow adding vehicles with ticket preferences (`Loại vé`, `Hạn vé`) without immediately choosing a physical floor, slot, or billing price.
- **Resolution**: Columns `ticket_type_id BIGINT NULL REFERENCES ticket_type(id)` and `ticket_expires_at TIMESTAMPTZ NULL` are added directly to `vehicle`. A pair check constraint `CONSTRAINT ck_vehicle_ticket_pref_pair CHECK ((ticket_type_id IS NULL AND ticket_expires_at IS NULL) OR (ticket_type_id IS NOT NULL AND ticket_expires_at IS NOT NULL))` guarantees that both preference fields are provided together or neither is provided. Full ticket issuance and physical slot allocation take place when formal tickets are created in Module 4.6.

### 4.8. Vehicle Manufacturer Brand Nullability (OQ-53)
The Add-Vehicle modal for customer onboarding (images 10 & 11) does not contain a field for `Hãng xe` (brand); brand appears only in gate check-in (4.5.1) and slot detail (4.8.4).
- **Resolution**: `vehicle.brand` is defined as `VARCHAR(50) NULL`, enabling customer vehicle registration to proceed without uncollected data.

### 4.9. Capacity Boundary Checks Derived from SRS Data Types (OQ-54)
Replacing rigid hardcoded bounds (1..10 floors and 1..108 slots per floor):
- **Resolution**: Constraints are based on SRS native data types: `CHECK (floor_number > 0 AND floor_number < 100)` for `Number(2)` and `CHECK (slot_number > 0 AND slot_number < 1000)` for `Number(3)`.

### 4.10. Floor-Scoped Parking Slot Code Uniqueness (OQ-59)
The SRS wireframes illustrate slot code `A-1` on Floor 1 (image 21) and simultaneously `A-1` on Floor 8 (image 23).
- **Resolution**: Global uniqueness is replaced by floor-scoped composite partial index: `CREATE UNIQUE INDEX uq_parking_slot_floor_code_active ON parking_slot (floor_number, code) WHERE deleted_at IS NULL;`.

### 4.11. Ticket Renewal Tariff & Price Mutation Audit Trail (OQ-58)
Screen 4.6.3 allows changing ticket type and price upon renewal.
- **Resolution**: `ticket_renewal` stores `old_ticket_type_id`, `new_ticket_type_id`, `old_price`, and `new_price` (`NUMERIC(12, 2)`), preserving complete financial and plan history.

### 4.12. Decoupled Architecture for Employee Profiles and System Credentials (OQ-56)
SRS 4.3.2 creates an employee profile while setting a default password, but login (4.1) validates credentials against `ACCOUNT`.
- **Resolution**: Adhering to the Separation of Concerns (SoC) principle, the relational schema completely decouples human resource profiles (`employee`) from system authentication credentials (`account`) via a nullable foreign key `employee.account_id BIGINT NULL REFERENCES account(id) ON DELETE RESTRICT`:
  1. **Operational Flexibility**: Physical parking lot operations employ personnel (e.g. outdoor attendants, cleaners, physical barrier guards) who do not interact with software terminals and therefore do not require user accounts, avoiding unnecessary credential attack surface.
  2. **Independent Lifecycle Management**: An employee's system login privileges can be temporarily suspended or deactivated (`account_id = NULL` or `account.is_active = FALSE`) without corrupting or deleting their underlying HR audit profile.
  3. **Bootstrap Integrity**: Nullability prevents circular dependency issues during system initial deployment and database seeding.
  4. **Application Transaction Guarantee**: In the application service layer (Django), creating an employee through screen 4.3.2 atomically generates both the `account` record (with default password) and the `employee` record within a single database transaction.
  5. **1-to-1 Enforcement**: A partial unique index `CREATE UNIQUE INDEX uq_employee_account_active ON employee (account_id) WHERE deleted_at IS NULL AND account_id IS NOT NULL;` guarantees that each system account is bound to at most one active employee.

### 4.13. Open Session Partial Unique Indexes & Double-Entry Prevention (OQ-66, OQ-75)
- **Open Session Safeguards (OQ-66, OQ-75)**: To prevent physical impossibilities (a single vehicle occupying two slots simultaneously, or two vehicles occupying the same slot), three partial unique indexes are enforced on `vehicle_entry_exit_log WHERE exit_time IS NULL`:
  1. `uq_log_open_session_slot`: `UNIQUE (slot_id) WHERE exit_time IS NULL AND slot_id IS NOT NULL` — ensures at most one open parking session per physical slot.
  2. `uq_log_open_session_vehicle`: `UNIQUE (vehicle_id) WHERE exit_time IS NULL` — ensures at most one open parking session per registered vehicle.
  3. `uq_log_open_session_plate`: `UNIQUE (license_plate_norm) WHERE exit_time IS NULL` — ensures a normalized license plate cannot check in multiple times without checking out, regardless of separator punctuation or letter case.

### 4.14. Strict Registered Vehicle Barrier Gate Policy (Owner Decision 10, OQ-65, OQ-75)
In previous drafts, a transient walk-in vehicle policy (`vehicle_id NULL`) was considered as an architectural proposal. However, under **Owner Decision 10** and strict fidelity to SRS Section 4.5.1, barrier gate check-in requires operators to search and identify a registered vehicle before saving. Saving without finding a registered vehicle triggers the verbatim SRS error: `"Lỗi dữ liệu không tìm thấy đê lưu"` (`MSG-4.5.1-M02`).
- **Resolution**:
  1. The column `vehicle_entry_exit_log.vehicle_id` is defined strictly as `BIGINT NOT NULL REFERENCES vehicle(id) ON DELETE RESTRICT`. All walk-in transient vehicle allowances are eliminated.
  2. In trigger `fn_guard_slot_reservation_on_entry()`, for any active check-in session (`exit_time IS NULL`), the camera-captured `license_plate` is validated against the active registered vehicle (`vehicle.license_plate`) by comparing `fn_normalize_license_plate(NEW.license_plate)` with `fn_normalize_license_plate(v.license_plate)`. Any mismatch raises exception `"Lỗi dữ liệu không tìm thấy đê lưu"` (`MSG-4.5.1-M02`, `SQLSTATE 23514`).

### 4.15. Slot Reservation Guard and Maintenance Slot Protection (OQ-63, OQ-67, PROP-4.5.2-P01)
When a parking slot is reserved by an active subscription ticket for a registered vehicle, other vehicles must be prevented from occupying or being assigned to that slot at barrier check-in or via slot reassignment. Furthermore, slots placed under maintenance must be locked against check-in.
- **Resolution**: A database-level trigger `trg_guard_slot_reservation_on_entry` and function `fn_guard_slot_reservation_on_entry()` are attached `BEFORE INSERT OR UPDATE OF slot_id, exit_time, vehicle_id, license_plate ON vehicle_entry_exit_log`:
  1. Serializes concurrent assignments by acquiring a row lock on the target slot (`FOR NO KEY UPDATE`).
  2. Rejects any entry, slot reassignment, or session reopening into slots currently under maintenance (`parking_slot.status = 'MAINTENANCE'`), raising proposed error message: `'Vị trí này đang bảo trì.'` (`PROP-4.5.2-P01`, `OQ-46`).
  3. If the slot has an active valid subscription ticket (`CURRENT_TIMESTAMP BETWEEN effective_from AND effective_to`), the trigger verifies that the entering vehicle matches the ticket's registered vehicle (`NEW.vehicle_id = ticket.vehicle_id`).
  4. If another vehicle attempts to occupy the reserved slot upon entry or slot update, the trigger raises an exception with the verbatim SRS error message: `'Vị trí này đã có xe đk vé và đang sử dụng'` (ERRCODE `check_violation`, HINT: `'Slot is reserved by an active ticket for another vehicle.'`, SRS 4.5.2 ACT-4.5.2-A02, MSG-4.5.2-M02, OQ-67). Normal checkout updates (`exit_time` becoming non-NULL) are unaffected.

### 4.16. Synchronizing Vehicle Ticket Preferences with Ticket Lifecycle (OQ-52)
When customer vehicles are onboarded in screen 4.4.3/4.4.4, `vehicle.ticket_type_id` and `vehicle.ticket_expires_at` store initial customer subscription desires. Once tickets are issued in Module 4.6, table `ticket` becomes the authoritative Single Source of Truth:
- **Resolution**: Trigger `fn_sync_slot_status_on_ticket()` (`AFTER INSERT OR UPDATE ON ticket`) automatically updates `vehicle.ticket_type_id` and `vehicle.ticket_expires_at` to match the latest active valid ticket (`ORDER BY effective_to DESC, id DESC LIMIT 1`). When all tickets for a vehicle expire or are soft-deleted, the trigger resets both columns to `NULL`, maintaining absolute synchronization across the ticket lifecycle.

### 4.17. Floor Map Geometric Slot Grid Coordinates (OQ-69)
SRS 4.5.2 specifies that each floor has a distinct spatial parking layout and wireframe `image14.png` illustrates a 2D geometric grid with dedicated entrance (`Cửa vào`) and exit (`Cửa ra`) portals.
- **Resolution**: Columns `map_row SMALLINT NULL` and `map_col SMALLINT NULL` are added to `parking_slot`. Check constraint `CONSTRAINT ck_slot_map_coords_pair CHECK ((map_row IS NULL AND map_col IS NULL) OR (map_row IS NOT NULL AND map_col IS NOT NULL AND map_row > 0 AND map_col > 0))` enforces 1-based positive grid coordinates. Partial unique index `CREATE UNIQUE INDEX uq_parking_slot_floor_map_pos_active ON parking_slot (floor_number, map_row, map_col) WHERE deleted_at IS NULL AND map_row IS NOT NULL AND map_col IS NOT NULL;` guarantees that no two active slots on the same floor occupy the same 2D grid cell, supporting responsive 2D floor map rendering.

### 4.18. Extended Slot Status Values and Maintenance Proposal Disclosure (OQ-63, PROP-4.5.2-P01)
Wireframe `image14.png` visually renders only two slot states (green for available, red for occupied).
- **Resolution**: The relational schema explicitly discloses that `parking_slot.status` values `RESERVED` and `MAINTENANCE` are architectural **[PROPOSAL]** extensions enabling pre-allocation for subscription tickets and maintenance out-of-service locking. Attempting to occupy or assign a maintenance slot returns proposed message `'Vị trí này đang bảo trì.'` (`PROP-4.5.2-P01`, `OQ-46`).

### 4.19. Literal SRS Gender and Business Code Format Validation (OQ-65, Owner Decisions 10 & 11)
- **Literal SRS Gender (Owner Decision 11)**: SRS 4.3.2 wireframe dropdown defines gender as `Nam` and `Nữ` only. Check constraints `ck_employee_gender` and `ck_customer_gender` strictly enforce `CHECK (gender IN ('Nam', 'Nữ'))`.
- **Business Code Format**: The SRS table specifies `Alpha numeric (5)` while its wireframes illustrate hyphenated codes (`NV-1234`, `KH-1234`, `Xe-001`, `VE-01`). Check constraints `ck_employee_code_format`, `ck_customer_code_format`, `ck_vehicle_code_format`, and `ck_ticket_code_format` enforce `CHECK (code ~ '^[A-Za-z0-9-]+$')` across all four entities, accommodating both 5-character alphanumeric strings and hyphenated codes while rejecting arbitrary punctuation strings like `"!!??"`.
- **Customer ID Card Format**: Documented via constraint `ck_customer_idcard_digits` (`identity_card_number ~ '^[0-9]+$'`), allowing digit strings up to 20 characters matching SRS `Number` type and wireframe 9- and 10-digit examples.

### 4.20. Dedicated Statistical Stored Functions for Date-Range Reporting (OQ-37, PROP-4.7.2-P02)
Analytical views provide real-time snapshots but cannot accept dynamic date-range arguments.
- **Resolution**: 4 stored PL/pgSQL functions (`fn_stat_vehicles_by_day`, `fn_stat_vehicles_by_floor`, `fn_stat_vehicles_by_customer`, `fn_stat_revenue_by_period`) accept `(p_from_date DATE, p_to_date DATE)`. Each function performs parameter validation, throwing `PROP-4.7.2-P02` (`'Khoảng thời gian thống kê không hợp lệ (Từ ngày phải nhỏ hơn hoặc bằng Đến ngày).'`) if `p_from_date > p_to_date` or either is NULL. All functions utilize independent CTEs to eliminate Cartesian row inflation and respect soft deletion.

### 4.21. Canonical License-Plate Normalization via Immutable Function & Stored Generated Columns (D5, F17, OQ-75)
Vehicle license plates in the Frontend mockups (e.g., `51K-992.14`, `30A-123.45` vs `51K-992-14`, `30A-123-45`) and SRS wireframes (`92D1-1234`) may be entered with dots, hyphens, spaces, or varying letter case across customer registration forms and barrier OCR cameras.
- **Resolution**:
  1. **Immutable Normalization Function**: `fn_normalize_license_plate(p_input TEXT) RETURNS TEXT LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE` computes `UPPER(REGEXP_REPLACE(p_input, '[^A-Za-z0-9]', '', 'g'))` (e.g., `'51K-992.14'`, `'51K-992-14'`, `'51k 992 14'`, and `'51K99214'` all normalize to `'51K99214'`; `'92D1-1234'` normalizes to `'92D11234'`).
  2. **Stored Generated Columns & Non-Empty Guards**: Both `vehicle` and `vehicle_entry_exit_log` preserve `license_plate VARCHAR(20) NOT NULL` exactly as entered for UI display while adding `license_plate_norm VARCHAR(20) GENERATED ALWAYS AS (fn_normalize_license_plate(license_plate)) STORED` guarded by `CHECK (license_plate_norm <> '')` (`ck_vehicle_license_plate_norm_nonempty` and `ck_log_license_plate_norm_nonempty`), rejecting empty or punctuation-only inputs (`''`, `'---'`, `'... . -'`).
  3. **Normalized Uniqueness & Indexing**: `uq_vehicle_license_plate_active` enforces `UNIQUE (license_plate_norm) WHERE deleted_at IS NULL` on `vehicle`; `uq_log_open_session_plate` enforces `UNIQUE (license_plate_norm) WHERE exit_time IS NULL` on `vehicle_entry_exit_log`; and `idx_log_license_plate` indexes `vehicle_entry_exit_log (license_plate_norm)` for fast indexed lookups independent of separator punctuation.
  4. **BEFORE Trigger Compatibility**: Because PostgreSQL computes `STORED` generated columns *after* `BEFORE ROW` triggers execute, `fn_guard_slot_reservation_on_entry()` compares `fn_normalize_license_plate(NEW.license_plate)` against `fn_normalize_license_plate(v.license_plate)` directly rather than reading `NEW.license_plate_norm`.
  5. **Mandatory Backend API Rule**: All backend APIs and services searching, filtering, or comparing license plates (including customer vehicle lookup, ticket search by plate in SRS 4.6.1, and barrier gate check-in/check-out in SRS 4.5.1) **MUST** query and compare via `license_plate_norm = fn_normalize_license_plate(:input)` (or normalize the search parameter in Python before filtering on `license_plate_norm`).

---

## 5. Audit Trail Architecture via `django-simple-history`

In accordance with ADR-0003:
- When the Django backend application is initialized, `django-simple-history` automatically generates historical audit tables (`historical_employee`, `historical_ticket`, `historical_customer`).
- These audit tables operate in an append-only mode, recording `history_user`, `history_type` (`+`, `~`, `-`), `history_date`, and client IP address.
- Application-level soft deletion updates `deleted_at` and `deleted_by`, preserving full referential integrity and auditability.

---

## 6. Open Questions Catalog Index

All technical proposals, open business questions, and assumptions are tracked with unique identifiers in [`docs/requirements/01-open-questions.md`](../docs/requirements/01-open-questions.md):
- **OQ-49**: Scope of permitted vehicle types and dual semantic meaning of "Loại xe" (model line vs seat capacity group) (SRS 4.4, 4.5.1, 4.8.2, 4.8.4).
- **OQ-50**: Vietnam administrative legal framework (Law No. 72/2025/QH15, Resolution No. 202/2025/QH15, 2-tier local government, 34 provincial units).
- **OQ-51**: News management and notification board specifications (SRS 4.2, Tasks_Sprint_1).
- **OQ-52**: Vehicle ticket preference persistence and bidirectional synchronization with ticket lifecycle (SRS 4.4.3, 4.6).
- **OQ-53**: Vehicle brand nullability in customer add-vehicle modal (SRS 4.4.3).
- **OQ-54**: Floor and slot capacity bounds derived from SRS data types Number(2) and Number(3) (SRS 4.8).
- **OQ-55**: Customer actor taxonomy and portal account linkage (SRS 4.1, 4.4).
- **OQ-56**: Decoupled account credentials versus employee profile architecture (SRS 4.3.2).
- **OQ-57**: Lookup seed data provenance verification (SRS 4.3.1, 4.6.1, 4.8.2).
- **OQ-58**: Ticket renewal tariff and price mutation history (SRS 4.6.3).
- **OQ-59**: Parking slot code uniqueness scoped per floor (SRS 4.5.2, 4.8).
- **OQ-60**: Vehicle gate camera dual-photo capture architecture (SRS 4.5.1).
- **OQ-61**: Referential integrity between customer and vehicle on ticket (SRS 4.6).
- **OQ-62**: Multi-level administrative hierarchy validation via composite FKs (SRS 4.3.2, 4.4.3).
- **OQ-63**: Real-time derived status synchronization and disclosure of extended slot statuses (RESERVED, MAINTENANCE) (SRS 4.5.2, 4.6, 4.7.2).
- **OQ-64**: Optimistic concurrency control triggers and ticket deletion guards (SRS 4.6.4, ADR-0003).
- **OQ-65**: Beyond-SRS constraint justifications, literal gender (Nam/Nữ), and strict registered vehicle policy (SRS 4.3.2, 4.5.1, Owner Decisions 10, 11).
- **OQ-66**: Open parking session partial unique indexes and double-entry prevention (SRS 4.5.1, 4.5.2).
- **OQ-67**: Slot reservation guard and maintenance slot protection trigger on entry & update (SRS 4.5.2).
- **OQ-68**: Employee working time and shift scheduling scope clarification (SRS 2.2 vs Section 4).
- **OQ-69**: Floor map slot 2D geometric grid coordinates (`map_row`, `map_col`) (SRS 4.5.2, image14).
- **OQ-70**: Duplicate license plate sample data in wireframes (`92D1-1234`) and active plate uniqueness (SRS 4.4.1, 4.4.4, image9, image10).
- **OQ-71..OQ-74, OQ-76, OQ-77**: Frontend-vs-SRS-vs-DB scope and alignment decisions (`D1..D4`, `D6`, `D7` — Owner approved defaults; deferred/out-of-scope features).
- **OQ-75**: License-plate normalization via `fn_normalize_license_plate(text)` and stored generated columns `license_plate_norm` (`D5`, `F17` — Owner approved & implemented in `db/01-schema.sql`).
- **OQ-78**: Module ERD diagram FK link completeness and 213-column sync (`D8`, `F27`, `F31` — Owner approved & implemented in `db/03-erd.asta` and `db/04-erd.png`..`db/09-erd-reference-views.png` via `astah-uml` MCP tools).

---

## 7. UML Entity Relationship Diagram (ERD) Specifications & Artifacts

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
| `03-erd.asta` | Master Astah UML Model | `9D7468DEF8FD8A5946EFCE992F84E8CEEC47AE4E262A254D81382989A167B199` | 55,517 bytes |
| `04-erd.png` | Master ERD Overview (44 Links) | `93CAB0653BA799F1FD79AF16842FF01D7F93D32E509FE76A0B2BF311BD3DC5FB` | 4166 × 1432 px (204,481 bytes) |
| `05-erd-account-staff.png` | Account & Staff Module ERD (7 Links) | `606CE91C9A7A2AC86B9A660FCB42797F153FF322B4E0D42CE3811D14853D0545` | 1473 × 1564 px (142,609 bytes) |
| `06-erd-customer-vehicle.png` | Customer & Vehicle Module ERD (7 Links) | `1C67D84F023F4FCF4CCE29A06168D27A124029C38617AC43D0268520130F51BE` | 2006 × 1097 px (122,549 bytes) |
| `07-erd-parking-ticket.png` | Parking & Ticket Module ERD (14 Links) | `0E1572E09EFCD930E5B5166B8C34FB2D0299DE6CB0A5413319BDCD0E4B3E7F8E` | 2520 × 1736 px (217,467 bytes) |
| `08-erd-operations-content.png` | Operations & Content Module ERD (11 Links) | `94D76460E06B2AFE63B6FF9B6BA7F51350E47A23EF41484ADD3AC6F49AE4CEF1` | 2513 × 1276 px (149,600 bytes) |
| `09-erd-reference-views.png` | Reference & Views Module ERD (2 Links) | `7DD070142C7D07DB90B752F8885353BD608FCACCD55169CFACE7E2E7BE4EDEEA` | 1500 × 1046 px (92,638 bytes) |

### 7.6. Method Disclosure & Integrity Attestation
- **Model Generation, Round 19 MCP Update & Routing**: Initially architected via Astah Open API 12.0.0 (`astah-api.jar` — `ProjectAccessor`, `ClassDiagramEditor`, `TransactionManager`) per Owner Decision (9), and updated in Round 19 on a sandbox copy exclusively via the live `astah-uml` MCP tools (`astah_delete_element`, `astah_add_attribute`, `astah_set_presentation_style`, `astah_add_presentation_link`, and the new `astah_set_note_text` tool) before SHA-256-verified copy back to `db/`.
- **Export Pipeline via Live MCP**: Exported through the live Antigravity MCP tool `astah_export_diagram_image` (`dpi=400`, `format="png"`, backed by Astah's official batch CLI command engine `astah-command.bat` / `JudeCommandRunner`), guaranteeing crisp anti-aliased font rendering and exact graphical fidelity.
- **Verification**: A read-only Astah API check on a copy of `03-erd.asta` (the check program is not committed) found 213 table attributes, 22 view attributes, 44 associations and every non-`deleted_by` foreign key drawn on each module diagram whose two tables are both shown. Display in the Astah GUI was not verified by the team.




