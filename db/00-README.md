# Database Schema & Seed Catalog — Parking Management Backend

This directory defines the enterprise physical relational database schema, lookup reference and synthetic sample seed data, and architectural documentation for the Smart Mobility Car Parking Lot Management System backend (`parking_management_backend`), targeting **PostgreSQL 18.6**. Under the **Frontend-First (`FE-First`)** specification hierarchy established in Rounds 23–28 ([`docs/requirements/06-frontend-srs-db-alignment.md`](../docs/requirements/06-frontend-srs-db-alignment.md), `TL-01`–`TL-43`), the 11 Frontend UI screens in `Parking Project` are the **primary source of requirements**, while `Quan ly bai dau xe oto_SRS_v4.1.docx` ([`docs/requirements/00-srs-catalog.md`](../docs/requirements/00-srs-catalog.md)) is authoritative for the SRS content and **secondary** where the Frontend is silent.

---

## 1. Database Execution & Loading Instructions

### 1.1. Native Execution via `psql` (Local / CI Pipeline)

Execution must specify `ON_ERROR_STOP=1` to ensure execution halts immediately upon any syntax or constraint violation:

```bash
# Load DDL Schema and Analytical Views (Zero DROP statements, transactional BEGIN...COMMIT)
psql -h 127.0.0.1 -p 5432 -U parking_user -d parking_db -v ON_ERROR_STOP=1 -f db/01-schema.sql

# Load Reference & Sample Seed Data (Idempotent — safe to run multiple times)
psql -h 127.0.0.1 -p 5432 -U parking_user -d parking_db -f db/02-seed.sql -v ON_ERROR_STOP=1
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

### 1.3. Two-Part Seed Structure (`db/02-seed.sql`) & Synthetic Data Attestation

- **Cutting Out Part 2 for Production Deployment (Two Sentences)**: [`db/02-seed.sql`](02-seed.sql) is divided inside a single transaction into **PART 1** (mandatory reference lookup catalogs and the default parking lot) and **PART 2** (a single contiguous sample operational data block delimited by `-- PART 2 START: SAMPLE OPERATIONAL DATA` and `-- PART 2 END: SAMPLE OPERATIONAL DATA`). For a clean production deployment that seeds only reference catalogs, delete the lines between `-- PART 2 START: SAMPLE OPERATIONAL DATA` and `-- PART 2 END: SAMPLE OPERATIONAL DATA` (keeping `COMMIT;` at the end of the file) before running `psql -v ON_ERROR_STOP=1 -f db/02-seed.sql`.
- **Synthetic Personal Data & Password Attestation**: **ALL personal data in [`db/02-seed.sql`](02-seed.sql) is 100% synthetic** and describes no real person; all names, 10-digit mobile numbers, 12-digit CCCD numbers, street addresses, and automobile license plates are deterministically generated from fixed seed `20261017`, all email addresses use only RFC 2606 reserved domains (`@example.com`, `@example.org`, `@example.net`), and all `account.password_hash` values use an Argon2id hash of the shared development-only password `Parking@Dev2026` for local testing (automatically reset to Django unusable-password hashes with prefix `!` whenever loaded in production environments via `load_sample_data --force-production`).

---

## 2. Frontend & SRS Entity Mapping Table

The table below maps the Frontend UI screens/labels (`TL-01`–`TL-43`) and secondary SRS v4.1 entity names to their normalized PostgreSQL relational database tables:

| Frontend / SRS Name | Relational Table Name | Architectural & Business Representation |
| :--- | :--- | :--- |
| `Đăng nhập` / `ACCOUNT` | `account` | Authentication principals using `email` (`lower(email)` unique per `TL-21`) and/or `phone`, password hashes, and roles (`MANAGER`, `EMPLOYEE`, `CUSTOMER`) (`TL-01`, `TL-21`). |
| `Nhân viên` / `NHAN_VIEN` | `employee` | Staff profiles (`NV001`, `NV0005`), contact details (`lower(email)` unique per `TL-21`), optional SRS fields (`TL-18`), status (`ACTIVE`, `INACTIVE`), position, and address links (`TL-11`, `TL-15`, `TL-18`, `TL-21`). |
| `Chức vụ` | `position` | Staff position catalog: `Quản lý`, `Nhân viên vận hành`, `Nhân viên thu ngân`, `Kỹ thuật viên` (`TL-11`). |
| `Khách hàng` / `KHACH_HANG` | `customer` | Customer profiles (`KH0001`), CCCD, optional SRS fields (`TL-18`, `lower(email)` unique per `TL-21`), status (`ACTIVE`, `SUSPENDED`, `BLACKLISTED`), and Decree 13 anonymization (`TL-08`, `TL-15`, `TL-18`, `TL-21`). |
| `Blacklist biển số` | `plate_blacklist` | Blacklisted license plates (including visitor plates) with normalized uniqueness and unpaid debt amount (`TL-08`). |
| `Loại xe` | `vehicle_type` | Car-only vehicle type catalog: `CAR` (`Ô tô`, standard passenger car) and `EV` (`Xe điện`, electric car `"ô tô điện"`) (`TL-09`, `TL-20`). |
| `Quản lý xe` / `XE` | `vehicle` | Customer-linked cars (`XE0001`), raw + normalized plate, ticket preferences, and `notes` (`TL-09`, `TL-15`, `TL-20`). |
| `Loại vé` / `LoaiVe` | `ticket_type` | Subscription tariff catalog: `DAILY` (`50k`), `MONTHLY` (`500k`), `QUARTERLY` (`1.2M`), `YEARLY` (`4.8M`) (`TL-10`). |
| `Bãi xe` -> `Tầng` -> `Khu` -> `Ô đỗ` | `parking_lot`, `parking_floor`, `parking_zone`, `parking_slot` | 4-level physical parking structure (`Bãi xe Smart Mobility`, `B1..B2/F1`, `Khu A..C`, `A-01`/`B-01`/`C-01`) (`TL-02`, `TL-03`). |
| `Đặt trước ô đỗ` | `slot_reservation` | Pre-booked slot reservations with GiST anti-overlap exclusion and automatic slot `RESERVED` sync (`TL-04`). |
| `Quản lý vé` / `VE` | `ticket`, `ticket_renewal` | Subscription tickets (`ACTIVE`, `RENEWING`, `EXPIRED`, `CANCELLED`; `"Sắp hết hạn"` derived per `TL-28`) and renewal history (`TL-10`, `TL-15`). |
| `Cổng vào / Cổng ra` | `parking_gate` | Entry and exit barrier gates with camera identifiers (`Cổng vào 1/2`, `Cổng ra 1/2/3`) (`TL-06`). |
| `Lịch sử ra/vào` / `DoXe` | `vehicle_entry_exit_log` | Parking sessions (`session_code`) supporting registered and visitor vehicles (`vehicle_id NULL` with `TL-17` auto-link), AI OCR confidence, and `fee_amount` (`TL-05`, `TL-06`, `TL-17`). |
| `Giao dịch / Thanh toán` | `payment` | Financial transactions (`CASH`, `VIETQR`) targeting exactly one session, ticket, or renewal (`TL-07`). |
| `Hoạt động gần đây` | `activity_log` | Append-only operational activity log displayed on the Parking Map screen (`TL-12`). |
| `Cảnh báo bất thường & khẩn cấp` | `system_alert` | Dashboard security and operational alerts (`BLACKLIST_PLATE`, `OVERSTAY`, `CAMERA_QUALITY`, `SYSTEM`) (`TL-13`). |

---

## 3. Database Entity Catalog & Structural Metrics

The physical database schema (Schema v2) comprises strictly **28 Base Tables**, **8 Analytical Views**, **69 Foreign Keys** (100% `ON DELETE RESTRICT`, `0` non-`RESTRICT`), **338 Base Table Columns** (100% documented with `COMMENT ON COLUMN`), **55 View Columns** (bringing total columns to **393**, with `0` undocumented tables, views, or columns), **87 Triggers**, **15 Trigger Functions**, **7 Non-Trigger Functions** (total **22 User Functions**; **265 Functions** in schema `public` including 212 `btree_gist` and 31 `pg_trgm` extension functions), **150 `CHECK` Constraints**, **9 `UNIQUE` Constraints**, **2 GiST `EXCLUDE` Constraints**, and **135 Indexes** (`28` `pk_*` primary-key indexes, `38` partial unique indexes + `9` `UNIQUE` constraint indexes = `47` `uq_*` unique indexes, `58` `idx_*` secondary indexes — comprising 52 secondary B-tree indexes and 6 partial GIN trigram indexes per `TL-41`, and `2` `excl_*` GiST exclusion indexes):

| Table / View Name | Type | Cols | FKs | Functional Summary |
| :--- | :---: | :---: | :---: | :--- |
| `account` | Table | 12 | 1 | Email/phone login principals (`lower(email)` unique per `TL-21`), password hashes, and RBAC roles (`TL-01`, `TL-21`). |
| `persistent_login_token` | Table | 9 | 1 | OWASP persistent remember-me session tokens (`TL-01`, ADR-0004). |
| `password_reset_token` | Table | 7 | 1 | One-time password recovery tokens (`TL-01`, `SCO-05`). |
| `position` | Table | 9 | 1 | Staff position catalog (`QL`, `NVVH`, `NVTN`, `KTV`) (`TL-11`). |
| `administrative_province` | Table | 5 | 0 | Level-1 provincial administrative units (`TL-15`, `OQ-50`). |
| `administrative_district` | Table | 6 | 1 | Level-2 district administrative units (`TL-15`, `OQ-50`). |
| `administrative_ward` | Table | 6 | 1 | Level-3 ward/commune administrative units (`TL-15`, `OQ-50`). |
| `employee` | Table | 20 | 5 | Staff profiles (`NV001`..`NV0005`), `ACTIVE`/`INACTIVE` status, optional SRS fields (`TL-18`), `lower(email)` unique (`TL-21`), and address FKs (`TL-11`). |
| `customer` | Table | 22 | 4 | Customer profiles (`KH0001`), `ACTIVE`/`SUSPENDED`/`BLACKLISTED` status, optional SRS fields (`TL-18`), `lower(email)` unique (`TL-21`), and PII flags (`TL-08`). |
| `plate_blacklist` | Table | 12 | 2 | Blacklisted license plates with normalized uniqueness and unpaid debt (`TL-08`). |
| `vehicle_type` | Table | 9 | 1 | Car-only vehicle type catalog (`CAR`, `EV`) (`TL-09`, `TL-20`). |
| `ticket_type` | Table | 11 | 1 | Subscription ticket tariff catalog (`DAILY`, `MONTHLY`, `QUARTERLY`, `YEARLY`) (`TL-10`). |
| `vehicle` | Table | 18 | 4 | Registered customer cars with `license_plate_norm`, ticket preferences, and `notes` (`TL-09`, `TL-20`). |
| `parking_lot` | Table | 10 | 1 | Top-level parking facility (`Bãi xe Smart Mobility`) (`TL-02`). |
| `parking_floor` | Table | 10 | 2 | Parking floors (`B1..B2`, `F1`) scoped per lot (`TL-02`). |
| `parking_zone` | Table | 10 | 2 | Parking zones (`A..C`) scoped per floor (`TL-02`). |
| `parking_slot` | Table | 16 | 2 | Physical parking slots with `slot_kind` (`STANDARD`, `PRIORITY`, `EV_CHARGING`) and 5 statuses (`TL-02`, `TL-03`). |
| `slot_allowed_vehicle_type` | Table | 3 | 2 | M:N mapping of allowed vehicle types per parking slot (`TL-15`, `TL-20`). |
| `slot_reservation` | Table | 17 | 5 | Pre-booked slot reservations with GiST anti-overlap exclusion (`TL-04`). |
| `ticket` | Table | 17 | 6 | Issued parking tickets with GiST anti-overlap exclusion and `RENEWING` status (`TL-10`). |
| `ticket_renewal` | Table | 15 | 6 | Ticket renewal history tracking old/new types, slots, prices, and `notes` (`TL-10`, `TL-15`). |
| `parking_gate` | Table | 13 | 2 | Entry and exit gates (`IN`, `OUT`) with `camera_status` and `is_auto_scan` (`TL-06`). |
| `vehicle_entry_exit_log` | Table | 22 | 7 | Parking sessions (`session_code`), nullable `vehicle_id` (`TL-17` auto-link), AI OCR metrics, and `fee_amount` (`TL-05`, `TL-06`, `TL-17`). |
| `payment` | Table | 17 | 5 | Unified payments (`CASH`, `VIETQR`) targeting exactly one session, ticket, or renewal (`TL-07`). |
| `activity_log` | Table | 7 | 1 | Append-only operational activity feed (`Hoạt động gần đây`) (`TL-12`). |
| `system_alert` | Table | 10 | 1 | Dashboard security and operational anomaly alerts (`TL-13`). |
| `news` | Table | 15 | 2 | Facility news articles (`TL-15`, `SCO-03`). |
| `notification` | Table | 10 | 2 | Portal notifications (`TL-15`). |
| **Total Base Tables** | **28** | **338** | **69** | **100% `ON DELETE RESTRICT`, `0` `CASCADE`, `0` `DROP` statements** |
| `v_slot_occupancy_by_floor` | View | 17 | — | Real-time floor/zone occupancy, EV charging, priority slots, and utilization percentage (`TL-14`). |
| `v_revenue_today_by_method` | View | 6 | — | Today's paid revenue split across `CASH` (`Tiền mặt`) and `VIETQR` (`QR`) (`TL-07`, `TL-14`). |
| `v_traffic_by_hour` | View | 4 | — | Hourly entry/exit traffic series (`00..23`) for sessions (`TL-14`). |
| `v_ai_recognition_stats` | View | 7 | — | AI plate recognition accuracy, scan count, and manual count (`TL-06`, `TL-14`). |
| `v_customer_status_summary` | View | 4 | — | Customer KPI summary (`total`, `active`, `suspended`, `blacklisted`) (`TL-08`). |
| `v_revenue_statistics` | View | 6 | — | Monthly, quarterly, and annual revenue aggregation (`TL-07`, `TL-15`). |
| `v_vehicle_traffic_daily` | View | 4 | — | Daily vehicle traffic flow metrics (`TL-15`). |
| `v_customer_vehicle_summary` | View | 7 | — | Customer registered vehicle and active ticket counts (`TL-15`). |

### 3.1. Database Triggers & Procedural Functions Summary

The database enforces real-time synchronization, temporal validity, OCC versioning, append-only immutability, barrier access security, and full delete policy safeguards (soft-delete, restore, controlled purge) through **87 Triggers**, **15 Trigger Functions**, and **7 Non-Trigger Functions** (total **22 User Functions**, all `22` configured with fixed `SET search_path = public, pg_temp` and `REVOKE ALL ON FUNCTION ... FROM PUBLIC` on all `15` internal trigger functions and `fn_controlled_purge`; **265 Functions** in schema `public` including 212 `btree_gist` and 31 `pg_trgm` extension functions):

1. `fn_normalize_license_plate(p_input TEXT)` (`IMMUTABLE STRICT PARALLEL SAFE` SQL function): Normalizes license plates via `UPPER(REGEXP_REPLACE(p_input, '[^A-Za-z0-9]', '', 'g'))` for stored generated columns `vehicle.license_plate_norm`, `vehicle_entry_exit_log.license_plate_norm`, and `plate_blacklist.license_plate_norm` (`TL-05`, `TL-08`, `TL-09`, `OQ-75`).
2. `fn_update_row_version_and_timestamp()` (`17` Triggers): Attached `BEFORE UPDATE` on `account`, `position`, `employee`, `customer`, `plate_blacklist`, `vehicle_type`, `ticket_type`, `vehicle`, `parking_lot`, `parking_floor`, `parking_zone`, `parking_slot`, `slot_reservation`, `ticket`, `parking_gate`, `payment`, and `news` (`TL-15`, `OQ-64`).
3. `fn_guard_parking_slot_status()` (`1` Trigger: `trg_guard_parking_slot_status` on `parking_slot`): Blocks manual status changes that contradict open sessions (`PROP-4.5.2-P02`, `PROP-4.5.2-P03`) or active tickets/reservations (`PROP-4.5.2-P04`) (`TL-03`, `OQ-81`).
4. `fn_sync_ticket_status()` (`1` Trigger: `trg_ticket_status_sync` on `ticket`): Rejects assigning a `MAINTENANCE` slot (`PROP-4.5.2-P01`), validates slot allowed vehicle type compatibility (`PROP-SLOT-VEHICLE-TYPE-MISMATCH`, `TL-38`), and auto-transitions active tickets to `EXPIRED` when `effective_to <= CURRENT_TIMESTAMP` (`TL-03`, `TL-10`, `TL-38`, `OQ-63`).
5. `fn_guard_slot_reservation_write()` (`1` Trigger: `trg_guard_slot_reservation_write` on `slot_reservation`): Rejects reserving a `MAINTENANCE` slot (`PROP-4.5.2-P01`), validates slot allowed vehicle type compatibility (`PROP-SLOT-VEHICLE-TYPE-MISMATCH`, `TL-38`), rejects a slot already covered by an overlapping active ticket (`MSG-4.5.2-M02`), and auto-transitions expired reservations (`TL-04`, `TL-38`).
6. `fn_guard_slot_reservation_on_entry()` (`1` Trigger: `trg_guard_slot_reservation_on_entry` on `vehicle_entry_exit_log`): Auto-links `NEW.vehicle_id` when `NEW.vehicle_id IS NULL` and the normalized plate matches an active registered vehicle (`TL-17`), allows unregistered visitor entries (`vehicle_id IS NULL`), verifies normalized plate match on open sessions when `vehicle_id` or `license_plate` is inserted or changed (`MSG-4.5.1-M02`), blocks `MAINTENANCE` slots (`PROP-4.5.2-P01`), verifies slot allowed vehicle type compatibility (`PROP-SLOT-VEHICLE-TYPE-MISMATCH`, `TL-38`), blocks slots reserved by another vehicle's ticket (`MSG-4.5.2-M02`), and blocks slots reserved via `slot_reservation` for another vehicle (`PROP-4.5.2-P05`) (`TL-03`, `TL-04`, `TL-05`, `TL-17`, `TL-38`, `OQ-67`, `OQ-81`).
7. `fn_recompute_slot_status(p_slot_id BIGINT)` + `fn_sync_slot_status_on_traffic()`, `fn_sync_slot_status_on_ticket()`, `fn_sync_slot_status_on_reservation()` (`3` `AFTER` Triggers): Deterministically recompute `parking_slot.status` (`OCCUPIED` -> `RESERVED` -> `AVAILABLE`, preserving `MAINTENANCE` and `CHARGING`) under `FOR UPDATE` row lock and synchronize `vehicle.ticket_type_id` and `vehicle.ticket_expires_at` (`TL-03`, `TL-04`, `TL-15`, `OQ-52`, `OQ-63`).
8. `fn_prevent_activity_log_mutation()` (`1` Trigger: `trg_activity_log_immutable` on `activity_log`): Blocks `UPDATE` and `DELETE` on `activity_log` (`PROP-4.5.2-P06`, `TL-12`, `OQ-81`).
9. `fn_guard_hard_immutable_table()` (`8` Triggers): Attached `BEFORE DELETE` on 5 business/financial/audit tables (`ticket`, `ticket_renewal`, `payment`, `vehicle_entry_exit_log`, `system_alert`) and 3 reference tables (`administrative_province`, `administrative_district`, `administrative_ward`), enforcing absolute hard-delete immutability (`TL-24`, `TL-36`, `TL-37`, ADR-0003). Authentication token tables (`persistent_login_token`, `password_reset_token`) allow direct plain `DELETE` per `TL-36`, and `slot_allowed_vehicle_type` is guarded by `fn_guard_slot_allowed_vehicle_type_delete()` per `TL-37`.
10. `fn_guard_slot_allowed_vehicle_type_delete()` (`1` Trigger: `trg_guard_slot_allowed_vehicle_type_delete` on `slot_allowed_vehicle_type`): Guards direct `DELETE` statements on slot vehicle type allocations, rejecting disassociation if the slot is currently referenced by open sessions (`exit_time IS NULL`), active tickets, or active reservations (`PROP-DEL-SAVT-IN-USE`, `TL-37`).
11. `fn_guard_prevent_plain_delete()` (`16` Triggers): Attached `BEFORE DELETE` across all 16 purgeable tables, blocking direct client DELETE statements and requiring authorization via `fn_controlled_purge()` with call-stack inspection and cryptographic transaction nonce (`TL-24`).
12. `fn_controlled_purge(p_table_name VARCHAR DEFAULT NULL, p_retention INTERVAL DEFAULT INTERVAL '30 days', p_dry_run BOOLEAN DEFAULT TRUE, p_purged_by BIGINT DEFAULT NULL, p_target_id BIGINT DEFAULT NULL)` (`Non-Trigger Function`, `SECURITY DEFINER`): Secure administrative purge routine returning 5 columns (`table_name`, `eligible_count`, `purged_count`, `status`, `details`) for trash records older than retention interval. Enforces a strict `>= 30 days` retention floor (`SQLSTATE 22023`, `TL-40`), Decree 13/2023/ND-CP customer anonymization checks, per-row foreign key exception skipping, co-purge cleanup of linked tokens in the same transaction when purging `account` (`TL-36`), dry-run simulation, and audit logging to `activity_log` (`TL-24`, `TL-36`, `TL-40`). `REVOKE ALL ON FUNCTION fn_controlled_purge(VARCHAR, INTERVAL, BOOLEAN, BIGINT, BIGINT) FROM PUBLIC;`.
13. `fn_guard_soft_delete_and_restore()` (`18` Triggers): Attached `BEFORE UPDATE OF deleted_at` on all 18 soft-deletable tables; guards business constraints on delete (DEL-01..DEL-06, TL-25 probes), blocks soft-deleting settled payments (`status IN ('PAID', 'REFUNDED')`, `PROP-DEL-PAYMENT-SETTLED`, `TL-39`), and auto-clears `deleted_by = NULL` while validating active parent hierarchy upon restore (`TL-23`, `TL-25`, `TL-26`, `TL-39`).
14. `fn_audit_soft_delete_and_restore()` (`18` Triggers): Attached `AFTER UPDATE OF deleted_at` on all 18 soft-deletable tables, recording `SOFT_DELETE` and `RESTORE` audit events into `activity_log` (`TL-26`).
15. `fn_guard_payment_update()` (`1` Trigger: `trg_guard_payment_update` on `payment`): Enforces valid payment status transitions (`UNPAID -> PAID | CANCELLED`, `PAID -> REFUNDED` only; terminal statuses; `PROP-PAY-STATUS-TRANSITION`) and locks settled payment financial/relational link columns (`amount`, `method`, `paid_at`, `session_id`, `ticket_id`, `renewal_id`, `code`; `PROP-PAY-SETTLED-IMMUTABLE`), allowing only harmless `notes` edits (`TL-42`).

### 3.2. Statistical Stored Functions for Date-Range Reporting (`TL-15`, `TL-27`, SRS 4.7.1 & 4.7.2)

The database provides **4 Statistical Functions** accepting `(p_from_date DATE, p_to_date DATE)` and validating `p_from_date <= p_to_date` (`PROP-4.7.2-P02`, `OQ-37`):

1. `fn_stat_vehicles_by_day(p_from_date DATE, p_to_date DATE)`
2. `fn_stat_vehicles_by_floor(p_from_date DATE, p_to_date DATE)`
3. `fn_stat_vehicles_by_customer(p_from_date DATE, p_to_date DATE)`
4. `fn_stat_revenue_by_period(p_from_date DATE, p_to_date DATE)`

### 3.3. Substring Text Search Acceleration via pg_trgm & GIN Indexes (`TL-41`)

The database accelerates substring and prefix text searches (`ILIKE '%...%'`) across high-frequency operational screens (Screens `02`, `03`, `04`, `05`, `07`) through the `pg_trgm` extension and **6 Partial GIN Trigram Indexes**:

1. `idx_customer_full_name_trgm`: `customer (full_name gin_trgm_ops) WHERE deleted_at IS NULL`
2. `idx_customer_phone_trgm`: `customer (phone gin_trgm_ops) WHERE deleted_at IS NULL`
3. `idx_customer_idcard_trgm`: `customer (identity_card_number gin_trgm_ops) WHERE deleted_at IS NULL`
4. `idx_vehicle_plate_trgm`: `vehicle (license_plate_norm gin_trgm_ops) WHERE deleted_at IS NULL`
5. `idx_log_license_plate_trgm`: `vehicle_entry_exit_log (license_plate_norm gin_trgm_ops)`
6. `idx_log_session_code_trgm`: `vehicle_entry_exit_log (session_code gin_trgm_ops)`

---

## 4. Key Architectural & Database Design Decisions (Schema v2)

- **Frontend-First Login, Self-Registration & Case-Insensitive Email Uniqueness (`TL-01`, `TL-21`, `OQ-71`, `OQ-84`)**: `account` authenticates via `email` and/or `phone` (`ck_account_login_identifier_present`), enforces case-insensitive active email uniqueness on `lower(email)` (`uq_account_email_active`, `uq_employee_email_active`, `uq_customer_email_active`) and phone uniqueness (`uq_account_phone_active`), and supports `CUSTOMER` self-registration.
- **4-Level Parking Hierarchy & Slot Kinds (`TL-02`, `TL-03`, `OQ-73`, `OQ-77`)**: Physical topology is normalized into `parking_lot -> parking_floor -> parking_zone -> parking_slot` with `fk_slot_zone FOREIGN KEY (zone_id) REFERENCES parking_zone (id) ON DELETE RESTRICT`, `slot_kind IN ('STANDARD', 'PRIORITY', 'EV_CHARGING')`, `status IN ('AVAILABLE', 'OCCUPIED', 'RESERVED', 'CHARGING', 'MAINTENANCE')`, and `ck_slot_charging_requires_ev_kind`.
- **Slot Reservations & Ticket Anti-Overlap (`TL-04`, `TL-10`)**: Both `ticket` (`excl_ticket_slot_time_overlap`) and `slot_reservation` (`excl_reservation_slot_time_overlap`) use `btree_gist` exclusion constraints over `tstzrange(..., '[)')` to prevent overlapping allocations on the same slot.
- **Unregistered Visitor Sessions, Gates & AI Recognition (`TL-05`, `TL-06`, `TL-17`, `OQ-65`, `OQ-66`)**: `vehicle_entry_exit_log` supports visitor vehicles (`vehicle_id NULL` with `TL-17` active registered-plate auto-link), unique `session_code`, `entry_gate_id`/`exit_gate_id` referencing `parking_gate`, `ai_confidence`, `recognition_source`, `review_status`, and `fee_amount`, guarded by 3 open-session partial unique indexes (`uq_log_open_session_slot`, `uq_log_open_session_vehicle`, `uq_log_open_session_plate`).
- **Unified Payments (`TL-07`, `OQ-72`)**: `payment` supports `CASH` and `VIETQR` methods with `ck_payment_single_target CHECK (num_nonnulls(session_id, ticket_id, renewal_id) = 1)` and `ck_payment_paid_timestamp`.
- **Customer & Plate Blacklist (`TL-08`)**: `customer` tracks `status IN ('ACTIVE', 'SUSPENDED', 'BLACKLISTED')` (`ck_customer_blacklist_reason`), while `plate_blacklist` tracks blacklisted plates (including visitors) using stored generated `license_plate_norm` (`uq_plate_blacklist_norm_active`).
- **Append-Only Activity Log & System Alerts (`TL-12`, `TL-13`)**: `activity_log` is protected against `UPDATE`/`DELETE` by `trg_activity_log_immutable`, and `system_alert` tracks operational/security anomalies (`BLACKLIST_PLATE`, `OVERSTAY`, `CAMERA_QUALITY`, `SYSTEM`).

---

## 5. Audit Trail Architecture via `django-simple-history`

In accordance with ADR-0003:

- When the Django backend application is initialized, `django-simple-history` automatically generates historical audit tables (`historical_employee`, `historical_ticket`, `historical_customer`).
- Application-level soft deletion updates `deleted_at` and `deleted_by` (`ck_*_soft_delete_pair`, `TL-23`), guarded by `fn_guard_soft_delete_and_restore()` (`TL-25`, `TL-26`, `TL-39`), audited by `fn_audit_soft_delete_and_restore()` (`TL-26`). Deletion policies strictly distinguish 16 purgeable tables protected against direct client `DELETE` via `fn_guard_prevent_plain_delete()` (`TL-24`), 8 hard-immutable tables via `fn_guard_hard_immutable_table()` (`TL-24`, `TL-36`, `TL-37`), 1 junction table guarded against active-usage `DELETE` via `fn_guard_slot_allowed_vehicle_type_delete()` (`TL-37`), 1 immutable audit table (`activity_log`), and 2 token tables allowing direct plain `DELETE` for session rotation and revocation (`TL-36`). All `69` foreign keys enforce `ON DELETE RESTRICT` with `0` cascading deletes.

---

## 6. Decision Log Index (`docs/requirements/01-decision-log.md`)

All technical proposals and finalized requirement/schema decisions (`OQ-01`–`OQ-84` and `TL-01`–`TL-43`) are recorded in [`docs/requirements/01-decision-log.md`](../docs/requirements/01-decision-log.md) and [`docs/requirements/06-frontend-srs-db-alignment.md`](../docs/requirements/06-frontend-srs-db-alignment.md):

- **OQ-01..OQ-70**: Core security, administrative hierarchy (`OQ-50`, `OQ-62`), car-only vehicle types with deferred seat classes (`OQ-49`, `TL-20`), OCC & soft-delete guards (`OQ-64`), and operational constraints.
- **OQ-71..OQ-77**: Schema v2 structural and seed decisions (`TL-01`–`TL-20`).
- **OQ-78**: Schema v2 ERD model and 400 DPI diagram exports (`db/04-erd.png`–`db/09-erd-reference-views.png`).
- **OQ-79**: Annual ticket (`Vé năm`) default price (`4.800.000đ`, `DECIDED` per `TL-22`).
- **OQ-80**: Per-session tariff computed by the application and stored in `vehicle_entry_exit_log.fee_amount` (`DECIDED-DEFERRED` per `TL-22` until the Owner supplies a price list).
- **OQ-81**: Database `CHECK` status value lists and guard messages (`DECIDED` per `TL-22`, `TL-37`–`TL-39`, `TL-42`).
- **OQ-82**: Provider-agnostic `VIETQR` payment storage via `payment.method` and `payment.provider_ref` (`DECIDED` per `TL-22`).
- **OQ-83**: Camera / AI recognition service integration out of database scope; only `ai_confidence`, `recognition_source`, and `review_status` are stored (`DECIDED` per `TL-22`).
- **OQ-84**: Case-insensitive email uniqueness on `lower(email)` across `account`, `employee`, and `customer` (`DECIDED` per `TL-21`, `TL-22`, `TL-36`).
- **TL-36..TL-43 (Rounds 27–28 Technical Refinements)**:
  - **TL-36**: Plain `DELETE` allowed on `persistent_login_token` and `password_reset_token` with RESTRICT FK and co-purge cleanup in `fn_controlled_purge()`.
  - **TL-37**: Plain `DELETE` allowed on `slot_allowed_vehicle_type` guarded by active usage check (`PROP-DEL-SAVT-IN-USE`).
  - **TL-38**: Slot allowed vehicle type compatibility validation across tickets, reservations, and entry logs (`PROP-SLOT-VEHICLE-TYPE-MISMATCH`).
  - **TL-39**: Soft-delete guard for settled payments (`status IN ('PAID', 'REFUNDED')`, `PROP-DEL-PAYMENT-SETTLED`).
  - **TL-40**: Retention floor enforcement (`>= 30 days`, `SQLSTATE 22023`) and per-row FK exception skipping in `fn_controlled_purge()`.
  - **TL-41**: Substring text search acceleration via `pg_trgm` and 6 partial GIN trigram indexes.
  - **TL-42**: Payment status transition matrix (`UNPAID -> PAID | CANCELLED`, `PAID -> REFUNDED` only; terminal `REFUNDED`/`CANCELLED`, `PROP-PAY-STATUS-TRANSITION`) and settled-payment financial/link immutability (`PROP-PAY-SETTLED-IMMUTABLE`) via `fn_guard_payment_update()`.
  - **TL-43**: Extension-independent project function count (`deptype <> 'e'`) in `.github/workflows/01-db-schema-check.yml` (`"28 8 69 0 87 22"`).

---

## 7. UML Entity Relationship Diagram (ERD) Specifications & Artifacts

The database architecture is visually modeled and maintained through native Astah UML specifications conforming to the official OMG UML 2.1 standard and Astah Open API 12.0.0 guidelines:

### 7.1. Diagram Deliverables & Formats

- **Editable Source Model**: [`db/03-erd.asta`](03-erd.asta) — Native Astah UML 12.0.0 project file containing the complete Schema v2 object-oriented domain representation, classes, stereotypes, attributes, and associations.
- **Master Overview Export**: [`db/04-erd.png`](04-erd.png) — High-resolution rendering exported at 400 DPI via the `astah-uml` MCP tool `astah_export_diagram_image` (Resolution: **4486 × 1997 px**, 36 classes, 69 FK links).
- **Module Diagrams (5 Sub-systems with 100% Attribute & Business FK Coverage)**:
  - [`db/05-erd-account-staff.png`](05-erd-account-staff.png) — Account, Authentication & Staff Management (**2220 × 1564 px**, 7 nodes: 5 expanded tables + 2 collapsed stubs, 7 links).
  - [`db/06-erd-customer-vehicle.png`](06-erd-customer-vehicle.png) — Customer, Vehicle, Vehicle Types & Plate Blacklist (**3284 × 1785 px**, 9 nodes: 4 expanded tables + 5 collapsed stubs, 11 links).
  - [`db/07-erd-parking-ticket.png`](07-erd-parking-ticket.png) — Parking Structure (`Lot -> Floor -> Zone -> Slot`), Reservations, Tariffs & Ticketing Lifecycle (**3372 × 2349 px**, 14 nodes: 9 expanded tables + 5 collapsed stubs, 23 links).
  - [`db/08-erd-operations-content.png`](08-erd-operations-content.png) — Gate Operations, Entry/Exit Sessions, Payments, Activity Feed, Alerts, News & Notifications (**4593 × 2269 px**, 19 nodes: 7 expanded tables + 12 collapsed stubs, 24 links).
  - [`db/09-erd-reference-views.png`](09-erd-reference-views.png) — Administrative Geography (`Province -> District -> Ward`) & 8 Analytical Database Views (**2486 × 1526 px**, 11 expanded nodes: 3 tables + 8 views, 2 links).

### 7.2. Model Metrics & Structural Parity (PostgreSQL 18.6 Schema v2 Match)

The on-disk `db/03-erd.asta` is 100% synchronized with `db/01-schema.sql` (`28` tables, `8` views, `338` table columns, `55` view columns, `393` total attributes, `69` FK associations, and `0` missing non-`deleted_by` business FK links across all 6 diagrams `04..09`):

- **36 Business Classes**:
  - **28 Physical Tables**: Modeled as UML Classes adorned with the `«table»` stereotype, encompassing all `338` database table columns with constraint stereotypes (`«PK»`, `«FK»`, `«UQ»`, `«PUQ»`, `«UQ1»`, `«PUQ1»`, `«PUQ2»`).
  - **8 Analytical Views**: Encapsulated within a dedicated `Views` UML Package (`v_slot_occupancy_by_floor`, `v_revenue_today_by_method`, `v_traffic_by_hour`, `v_ai_recognition_stats`, `v_customer_status_summary`, `v_revenue_statistics`, `v_vehicle_traffic_daily`, `v_customer_vehicle_summary`) with the `«view»` stereotype (`55` view attributes total).
- **22 SQL Primitive Datatype Classes Encapsulated**:
  - `22` SQL primitive types (`BIGINT`, `INTEGER`, `SMALLINT`, `VARCHAR(10)`, `VARCHAR(15)`, `VARCHAR(20)`, `VARCHAR(30)`, `VARCHAR(45)`, `VARCHAR(50)`, `VARCHAR(64)`, `VARCHAR(100)`, `VARCHAR(150)`, `VARCHAR(200)`, `VARCHAR(220)`, `VARCHAR(255)`, `VARCHAR(500)`, `TEXT`, `BOOLEAN`, `DATE`, `TIMESTAMPTZ`, `NUMERIC(5, 2)`, `NUMERIC(12, 2)`) are encapsulated within a dedicated `DataTypes` package.
  - Total classes in `03-erd.asta`: `58` classes (`36` business entities + `22` datatype classes).
- **69 Foreign Key Associations (100% Populated & Modeled on `ERD_Overview`, 100% Business FKs Drawn on `05..09`)**:
  - 100% of physical relational constraints are modeled as directed associations from child table to parent table with exact multiplicities (`0..1 -> 1` for `fk_customer_account` and `fk_employee_account`, `0..* -> 1` for required FKs, and `0..* -> 0..1` for nullable FKs).
  - **18 Soft-Deletion Audit Links**: All `18` `deleted_by -> account` foreign keys are modeled and rendered on `ERD_Overview` using quiet grey lines (`#B0BEC5`).

### 7.3. Constraint Stereotype Conventions & Legend Note

Composite and partial unique constraints are explicitly marked using standardized UML stereotypes:

- `«PK»`: Primary key (single column or component of composite PK).
- `«FK»`: Foreign key referencing parent entity.
- `«UQ»`: Standard global single-column unique constraint (e.g., `persistent_login_token.series`, `password_reset_token.token_hash`, `vehicle_entry_exit_log.session_code`, `administrative_province.code`).
- `«PUQ»`: Active-record partial unique index (filtered by `WHERE deleted_at IS NULL` or active session), applied to `account.email`, `account.phone`, `employee.code`, `employee.identity_card_number`, `customer.code`, `customer.email`, `vehicle.license_plate_norm`, `plate_blacklist.license_plate_norm`, `vehicle_entry_exit_log.license_plate_norm`, etc.
- Composite Multi-Column Stereotypes:
  - `parking_slot`: `zone_id`: `«FK, PUQ1, PUQ2»`, `code`: `«PUQ1»`, `map_row`: `«PUQ2»`, `map_col`: `«PUQ2»` (enforcing zone-scoped code and 2D grid position uniqueness for active slots).
  - `parking_floor`: `lot_id`: `«FK, PUQ1»`, `code`: `«PUQ1»`.
  - `parking_zone`: `floor_id`: `«FK, PUQ1»`, `code`: `«PUQ1»`.
  - `parking_gate`: `lot_id`: `«FK, PUQ1»`, `code`: `«PUQ1»`.
  - `vehicle`: `id`: `«PK, UQ1»`, `customer_id`: `«FK, UQ1»` (enforcing composite parentage integrity for tickets).
  - `administrative_district`: `id`: `«PK, UQ1»`, `province_id`: `«FK, UQ1»`.
  - `administrative_ward`: `id`: `«PK, UQ1»`, `district_id`: `«FK, UQ1»`.
- **UML Legend Note**: Rendered on `ERD_Overview` (`db/04-erd.png`) with zero relationship lines crossing the note box, documenting the `28` tables (`338` attributes), `8` views (`55` attributes), `36` classes (`393` attributes), and `69` FK links (`18` `deleted_by` links in `#B0BEC5`).

### 7.4. Visual Readability & Layout Architecture

- **Master Overview (`db/04-erd.png`) - 100% Visual Association Coverage**:
  - **All 69 Relationships Visually Rendered**: 100% of the `69` associations (`51` business FKs in `#37474F` and `18` `deleted_by` FKs in `#B0BEC5`) are rendered on the canvas with `0` table crossings and `0` label/multiplicity overlaps.
- **5 Detailed Module Diagrams (`05`..`09`) - Orthogonal Layout**:
  - Primary subsystem tables display **100% of attributes and column types** (`338` table attributes + `55` view attributes = `393` total attributes across the 5 module diagrams).
  - Inter-module relationships are linked via **Collapsed Neighbor Stubs** (`#ECEFF1`) with at most `1` link per stub side (`0` stub-side sharing violations) and `100%` of non-`deleted_by` business FKs between present tables drawn (`7` on `05`, `11` on `06`, `23` on `07`, `24` on `08`, `2` on `09`).
- **Automated Geometry Verification**:
  - `ERD_Overview`: Table Crossings = **0**, Missing FKs = **0** (`69` links: `51` business + `18` `deleted_by`).
  - `Account_Staff`: Table Crossings = **0**, Missing Business FKs = **0**, Stub Side Violations = **0** (`7` links).
  - `Customer_Vehicle`: Table Crossings = **0**, Missing Business FKs = **0**, Stub Side Violations = **0** (`11` links).
  - `Parking_Ticket`: Table Crossings = **0**, Missing Business FKs = **0**, Stub Side Violations = **0** (`23` links).
  - `Operations_Content`: Table Crossings = **0**, Missing Business FKs = **0**, Stub Side Violations = **0** (`24` links).
  - `Reference_Views`: Table Crossings = **0**, Missing Business FKs = **0**, Stub Side Violations = **0** (`2` links).
  - **TOTAL**: Table Crossings = **0**, Missing Business FKs Across All 6 Diagrams = **0**, Stub Side Violations = **0**.

### 7.5. Cryptographic Deliverables Verification (SHA-256 Checksums)

All ERD deliverables are verified with SHA-256 checksums:

| Artifact File | Description | SHA-256 Checksum | Dimensions / File Size |
|---|---|---|---|
| `03-erd.asta` | Master Astah UML Model | `27BE91FFF265D505D09FC25F99D31F507FA29A1B5112A4CFD85F6B3961FA0F70` | 109,849 bytes |
| `04-erd.png` | Master ERD Overview (69 Links) | `B49DAED08A0CE8ADB35528D6896550D861E7B6B5AAC3C6605559B07B142D14E9` | 4486 × 1997 px (327,141 bytes) |
| `05-erd-account-staff.png` | Account & Staff Module ERD (7 Links) | `BCEBAE58D9752576ECE0783E455B35F91E8FBC4C0777A5D06747DE7AFAC46DB3` | 2220 × 1564 px (170,673 bytes) |
| `06-erd-customer-vehicle.png` | Customer & Vehicle Module ERD (11 Links) | `09C36710BA0C12C0E28D219322629B6A60F5A74FEABFE0BE7F5B108AC7FB272B` | 3284 × 1785 px (220,186 bytes) |
| `07-erd-parking-ticket.png` | Parking & Ticket Module ERD (23 Links) | `9EDC483D13C83143D511C179A1677210AF7178BC6452AB70514D21EA112C8945` | 3372 × 2349 px (395,296 bytes) |
| `08-erd-operations-content.png` | Operations & Content Module ERD (24 Links) | `6D0563183834271791A65CD6C57D022988120F70119735F0778D7A8D0333EAB9` | 4593 × 2269 px (383,013 bytes) |
| `09-erd-reference-views.png` | Reference & Views Module ERD (2 Links) | `FAD409B35A8F2CA1E77DB914D79CD68330730B698649B65BC9727CF5DC124D5C` | 2486 × 1526 px (163,916 bytes) |

### 7.6. Method Disclosure & Integrity Attestation

- **Model Regeneration & Routing via Live MCP (Round 24)**: Updated in Round 24 on a sandbox copy (`D:\GitHub\Server\mcp-uml\test-output\erd24\03-erd.asta`) exclusively via the `astah-uml` MCP tools (`astah_open_project`, `astah_delete_element`, `astah_create_class`, `astah_add_attribute`, `astah_create_relationship`, `astah_delete_presentation`, `astah_add_presentation_node`, `astah_add_presentation_link`, `astah_set_presentation_style`, `astah_set_note_text`, `astah_save_project`) driven by MCP stdio client scripts (`r24_step_b2_model.js`, `r24_step_b3_diagrams.js`, `r24_patch_ov_cv.js`), before SHA-256-verified copy back to `db/`.
- **Export Pipeline via Live MCP**: Exported through the `astah-uml` MCP tool `astah_export_diagram_image` (`dpi=400`, `format="png"`, backed by Astah's official batch CLI command engine `astah-command.bat` / `JudeCommandRunner`).
- **Verification**: A read-only Astah API check on a copy of `03-erd.asta` (the check program is not committed) verified `0` model differences against the live PostgreSQL 18.6 catalog (`28` tables, `8` views, `22` data types, `338` table attributes, `55` view attributes, `69` associations), `0` missing non-`deleted_by` foreign keys across `05..09`, `0` stub-side sharing violations, and `0` link-through-table crossings. Display in the Astah GUI was not verified by the team.
