# Frontend-First Specification & Database Schema v2 Decision Record

This document records the authoritative **Frontend-First (`FE-First`)** specification hierarchy established in Rounds 23–26, the **Team Lead Decisions (`TL-01`–`TL-35`)** (which supersede the earlier `D1`–`D8` defaults), the **11-file Frontend-to-Database traceability summary**, and the **Schema v2 catalog delta** implemented in [`db/01-schema.sql`](../../db/01-schema.sql) and [`db/02-seed.sql`](../../db/02-seed.sql).

---

## 1. Source Hierarchy & Governance

1. **Primary Source — Frontend Design (`FE`)**: The 11 exported UI files in `Parking Project` (verified byte-for-byte identical against `Parking Project.zip`) are the primary specification for screens, fields, labels, status badges, filters, and workflows.
2. **Secondary Source — SRS v4.1 (`SRS`)**: `Quan ly bai dau xe oto_SRS_v4.1.docx` (cataloged in [`00-srs-catalog.md`](00-srs-catalog.md) and [`03-delete-rules-catalog.md`](03-delete-rules-catalog.md)) is authoritative for the SRS content and secondary to the Frontend design, governing only where the Frontend is silent (`TL-15`, `TL-19`).
3. **Tertiary Source — Explicit Proposals (`[PROPOSAL]`)**: Any status code, tariff rule, or database guard message not explicitly shown in either the Frontend or the SRS is tagged `[PROPOSAL]` and recorded in [`01-decision-log.md`](01-decision-log.md) and [`05-proposed-messages.md`](05-proposed-messages.md). The **Team Lead** decides all requirement and schema questions (`TL-19`, `TL-22`).

---

## 2. Team Lead Decisions (`TL-01`–`TL-35`)

### 2.1. Compact Decision Index

| ID | Domain | Primary FE Evidence | Schema v2 Target |
| :--- | :--- | :--- | :--- |
| `TL-01` | Login & Self-Registration | `login-container.png` | `account` (`email`, `phone`, `CUSTOMER`) |
| `TL-02` | 4-Level Parking Hierarchy | `Main Page`, `Trang chủ`, `Sơ đồ bãi` | `parking_lot`, `parking_floor`, `parking_zone`, `parking_slot` |
| `TL-03` | Slot Kinds, EV & Statuses | `Main Page.png`, `Sơ đồ bãi đậu xe — Smart Mobility.png` | `parking_slot`, `fn_guard_parking_slot_status` |
| `TL-04` | Slot Reservations | `Main Page.png`, `Sơ đồ bãi đậu xe — Smart Mobility.png` | `slot_reservation`, `excl_reservation_slot_time_overlap` |
| `TL-05` | Visitor Entry & Session Code | `Lịch sử ra/vào — Smart Mobility.png` | `vehicle_entry_exit_log` (`vehicle_id NULL`, `session_code`) |
| `TL-06` | Gates & AI Plate Recognition | `Trang chủ`, `Main Page`, `Lịch sử ra/vào` | `parking_gate`, `vehicle_entry_exit_log` |
| `TL-07` | Payments (`CASH`, `VIETQR`) | `Trang chủ`, `Main Page`, `Quản lý vé`, `Quản lý xe` | `payment`, `v_revenue_today_by_method` |
| `TL-08` | Customer & Plate Blacklist | `Trang chủ`, `Main Page`, `Khách hàng` | `customer`, `plate_blacklist` |
| `TL-09` | Vehicles (`CAR`, `EV`) | `Quản lý xe — Smart Mobility.png` | `vehicle_type`, `vehicle` |
| `TL-10` | Tickets, Tariffs & Renewals | `Quản lý vé — Smart Mobility.png`, `Quản lý xe` | `ticket_type`, `ticket`, `ticket_renewal` |
| `TL-11` | Employees & 4 Positions | `Quản lý nhân viên - Smart mobility.png` | `position`, `employee` |
| `TL-12` | Operational Activity Feed | `Sơ đồ bãi đậu xe — Smart Mobility.png` | `activity_log`, `trg_activity_log_immutable` |
| `TL-13` | Anomaly & Emergency Alerts | `Trang chủ — Smart Mobility.png`, `Main Page.png` | `system_alert` |
| `TL-14` | Dashboard KPIs & Analytics | `Trang chủ — Smart Mobility.png`, `Main Page.png` | `v_slot_occupancy_by_floor`, `v_traffic_by_hour`, `v_ai_recognition_stats` |
| `TL-15` | Preserved SRS Rules & Views | SRS 4.1–4.8, `Tasks_Sprint_1` | `administrative_*`, `news`, `notification`, `fn_stat_*` |
| `TL-16` | Pure UI / Marketing Elements | `Main Page.png`, `Vector.png`, `clarity_edit-line.png` | UI only (`0` database tables) |
| `TL-17` | Visitor Plate Auto-Link | `Lịch sử ra/vào — Smart Mobility.png` | `fn_guard_slot_reservation_on_entry` (`NEW.vehicle_id`) |
| `TL-18` | Optional Profile Fields | `login-container`, `Khách hàng`, `Quản lý nhân viên` | `customer`, `employee` (`uq_customer_email_active`, `uq_employee_idcard_active`) |
| `TL-19` | Docs Hierarchy & cSpell | `.claude/rules/02-*`, `docs/`, `cspell.json` | Documentation wording & `cspell.json` |
| `TL-20` | Car-Only Vehicle Types | `Quản lý xe — Smart Mobility.png`, SRS v4.1 | `vehicle_type` (`CAR`, `EV` only; `db/02-seed.sql`) |
| `TL-21` | Case-Insensitive Email Index | `login-container`, `Khách hàng`, `Quản lý nhân viên` | `uq_account_email_active`, `uq_employee_email_active`, `uq_customer_email_active` |
| `TL-22` | Compact Decision Log | `docs/requirements/01-decision-log.md` | `OQ-01`–`OQ-84` finalized in `01-decision-log.md` |
| `TL-23` | Soft-Delete Representation & Integrity | Team Meeting 16/10/2026 | `ck_*_soft_delete_pair`, `deleted_at`, `deleted_by` |
| `TL-24` | Hard Delete Prohibition & Purge | Team Meeting 16/10/2026 | `trg_prevent_plain_delete_*`, `trg_guard_*_immutable`, `fn_controlled_purge()` |
| `TL-25` | Database Soft-Delete Guards (DEL-01..06) | SRS 4.3–4.8, `03-delete-rules-catalog.md` | `fn_guard_soft_delete_and_restore()`, `trg_guard_soft_delete_and_restore_*` |
| `TL-26` | Restoration Guards & Audit Logging | Team Meeting 16/10/2026 | `fn_audit_soft_delete_and_restore()`, `activity_log` (`SOFT_DELETE`, `RESTORE`, `PURGE`) |
| `TL-27` | Read-Side Soft-Delete Filtering | Team Meeting 16/10/2026 | 8 analytical views, `fn_stat_*`, `deleted_at IS NULL` |
| `TL-28` | Frontend Derived Values (SQL Proofs) | Screens `02`, `03`, `04`, `05`, `07` | `07-fe-srs-traceability.md` Section 4 (6 proof queries) |
| `TL-29` | Dynamic Floor Structure (B3 Alignment) | `Trang chủ`, `Main Page`, `Sơ đồ bãi` | `parking_floor`, data-driven floor management |
| `TL-30` | Employee Area Mapping (District + Province) | `Quản lý nhân viên - Smart mobility.png` | `administrative_district`, `administrative_province`, Serializer |
| `TL-31` | Filter Optimization & Foreign Key Indexes | Screens `03`, `04`, `05`, `06`, `07`, `08` | `ticket_type_id`, gate IDs, reservation & address FK indexes |
| `TL-32` | CHECK Constraints & Soft-Delete Invariant | Schema-wide audit | Preserved enum, regex, amount CHECKs + `TL-23` across 18 tables |
| `TL-33` | Bilingual Schema COMMENTs Policy | Schema & catalog documentation | Standardized English definition + verbatim Vietnamese quotes |
| `TL-34` | Timestamp & Currency Precision | Screens `02`, `05`, `07` | `TIMESTAMPTZ` (UTC) + `NUMERIC(12,2)` |
| `TL-35` | Car-Only Facility Scope Reaffirmation | `Quản lý xe — Smart Mobility.png` (Row 3) | `vehicle_type` (`CAR`, `EV` only; motorcycle mock artifact) |
| `TL-36` | Token Plain DELETE & Account Purge | `login-container.png` | `persistent_login_token`, `password_reset_token` plain DELETE |
| `TL-37` | Slot Allowed Vehicle Type Delete Guard | `Sơ đồ bãi đậu xe — Smart Mobility.png` | `slot_allowed_vehicle_type` delete guard (`PROP-DEL-SAVT-IN-USE`) |
| `TL-38` | Slot Vehicle Type Compatibility Guard | `Sơ đồ bãi`, `Quản lý vé`, `Lịch sử ra/vào` | Slot vehicle type validation (`PROP-SLOT-VEHICLE-TYPE-MISMATCH`) |
| `TL-39` | Payment Soft-Delete Guard for Settled | `Trang chủ`, `Main Page`, `Quản lý vé` | `payment` soft-delete guard (`PROP-DEL-PAYMENT-SETTLED`) |
| `TL-40` | Purge 30-Day Retention & Batch FK Skip | Architecture & Data Retention | `fn_controlled_purge()` 30-day floor & per-row FK skip |
| `TL-41` | Trigram Indexing on Text Search | Screens `02`, `03`, `04`, `05`, `07` | `pg_trgm` extension & 6 partial GIN trigram indexes |
| `TL-42` | Payment Status Transition & Settled Immutability Guard | `Trang chủ`, `Main Page`, `Quản lý vé` | `fn_guard_payment_update()`, `trg_guard_payment_update` |
| `TL-43` | Extension-Independent Function Count in CI | CI Architecture (`.github/workflows/01`) | `pg_depend` filter excluding extension procs (22 user funcs) |
| `TL-44` | Django Schema Authority & RunSQL Initial Migration | Architecture & Database Operations | `apps/core` RunSQL reading `db/01-schema.sql`, `load_sample_data` |
| `TL-45` | 1:1 Unmanaged Models & 3-Tier Base Hierarchy | 28 tables, 8 views, 69 FKs, `tests/` | `managed=False`, `SoftDeleteModel`, `Account` auth, parity tests |
| `TL-46` | Dependency Pinning, Quality Gates & CI Workflow 02 | CI/CD & Development Standards | `requirements/*.txt`, `pyproject.toml`, `02-django-check.yml` |
| `TL-47` | Foundation Base Layer, Auth, OpenAPI & Tests | Architecture, API Standards & Tests | Error envelope, auth APIs, Swagger UI, 6 lookups (Narrowed by `TL-48`) |
| `TL-48` | Foundation Scope Reduction & Feature Handover | Architecture & Teamwork Governance | Gỡ bỏ login/remember-me & 6 lookups; giữ nguyên 100% foundation skeleton |
| `TL-49` | Quality Gates Enforcement & CSpell Cache Exclusion | CI/CD & Development Standards | 0 lỗi ruff, mypy, dry-run, deploy check, test cov >= 80%, cspell cache ignore |
| `TL-50` | Vehicle Entry/Exit Tariff Rules (Round 32) | `Lịch sử ra/vào — Smart Mobility.png` | `vehicle_entry_exit_log.fee_amount`, Decimal tariff calculation |
| `TL-51` | Scan API Response Contract & Corrections (Round 35) | `POST /api/v1/parking/plate-scans/` | `plate_raw`, `plate_final`, `corrections` list, sync `best_candidate` |

### 2.2. Detailed Decision Specifications

- **`TL-01` — Login & Account**:
  - **FE Evidence**: `login-container.png` labels the login input `"Email hoặc Số điện thoại"`, includes `"Ghi nhớ đăng nhập"`, `"Quên mật khẩu?"`, and `"Chưa có tài khoản? Đăng ký ngay"`.
  - **Resolution**: Replaced `account.username` with `email VARCHAR(100) NULL` and `phone VARCHAR(15) NULL`, enforced `ck_account_login_identifier_present CHECK (num_nonnulls(email, phone) >= 1)`, `ck_account_email_format`, `ck_account_phone_digits CHECK (phone IS NULL OR phone ~ '^[0-9]{9,15}$')`, and active partial unique indexes `uq_account_email_active` (`lower(email)`, `TL-21`) and `uq_account_phone_active` (`phone`). Kept `role IN ('MANAGER', 'EMPLOYEE', 'CUSTOMER')` so self-registration creates a `CUSTOMER` account + `customer` profile. Retained `persistent_login_token` and `password_reset_token`.
- **`TL-02` — Parking Structure (Lot -> Floor -> Zone -> Slot)**:
  - **FE Evidence**: `Sơ đồ bãi đậu xe — Smart Mobility.png` (`"Bãi đỗ xe: Bãi xe Smart Mobility"`, `"+ Thêm tầng"`, `"+ Thêm khu"`, `"+ Thêm ô đỗ xe"`, `"Quản lý cấu trúc bãi"`, `"Tầng B1"`, `"Tầng B2"`, `"Tầng F1"`, `"Khu A"`, `"Khu B"`, `"Khu C"`, slots `"A-01"`..`"A-08"`, `"B-01"`..`"B-08"`), `Trang chủ — Smart Mobility.png` (`"Tầng B1"`, `"Tầng B2"`, `"Tầng B3"`), `Quản lý vé — Smart Mobility.png` (`"Tầng B1 - A10"`, `"Tầng B2 - B12"`, `"Tầng B1 - C03"`, `"Tầng B3 - A01"`), and `Quản lý xe — Smart Mobility.png` (`"Khu A · Tầng 2 · Slot 42"`).
  - **Resolution**: Added `parking_lot` (`code`, `name`, `address`, `is_active`), `parking_floor` (`lot_id`, `code VARCHAR(20)`, `name VARCHAR(50)`, `sort_order`, `uq_parking_floor_lot_code_active`), and `parking_zone` (`floor_id`, `code VARCHAR(20)`, `name VARCHAR(50)`, `description`, `uq_parking_zone_floor_code_active`). Updated `parking_slot` to reference `zone_id` via `fk_slot_zone FOREIGN KEY (zone_id) REFERENCES parking_zone (id) ON DELETE RESTRICT`, `code VARCHAR(20)` (`ck_slot_code_format`, `uq_parking_slot_zone_code_active`), and retained `map_row`, `map_col` (`uq_parking_slot_zone_map_pos_active`), `width`, `length`, and `height`.
- **`TL-03` — Slot Types, EV Charging & Statuses**:
  - **FE Evidence**: `Main Page.png` (`"Chỗ trống (Available)"`, `"Đã đỗ xe (Occupied)"`, `"Đã đặt trước (Reserved)"`, `"Sạc xe điện (EV Charging)"`, `"Bảo trì / Tạm khóa"`), `Sơ đồ bãi đậu xe — Smart Mobility.png` (`"DÃY A1 - A08 (XE Ô TÔ TIÊU CHUẨN)"`, `"DÃY B1 - B08 (XE ƯU TIÊN)"`, `"CẢM BIẾN SIÊU ÂM ACTIVE"`, `"Trống (Available)"`, `"Có xe (Occupied)"`, `"Đặt trước (Reserved)"`, `"BẢO TRÌ"`, and manual buttons `"Đánh dấu trống"`, `"Đánh dấu có xe"`, `"Đánh dấu đặt trước"`, `"Đánh dấu bảo trì"`).
  - **Resolution**: Added `slot_kind VARCHAR(20) NOT NULL DEFAULT 'STANDARD'` (`ck_slot_kind_enum CHECK (slot_kind IN ('STANDARD', 'PRIORITY', 'EV_CHARGING'))`), `status IN ('AVAILABLE', 'OCCUPIED', 'RESERVED', 'CHARGING', 'MAINTENANCE')` (`ck_slot_status_enum`), `ck_slot_charging_requires_ev_kind CHECK (status <> 'CHARGING' OR slot_kind = 'EV_CHARGING')`, and `notes TEXT NULL` on `parking_slot`. Slot statuses are synchronized by `fn_recompute_slot_status()` while `fn_guard_parking_slot_status()` blocks manual status changes that contradict open sessions or active tickets/reservations (`PROP-4.5.2-P02`..`P04`, `OQ-81`).
- **`TL-04` — Slot Reservation (`Đặt trước`)**:
  - **FE Evidence**: `Sơ đồ bãi đậu xe — Smart Mobility.png` shows `"Đặt trước / Bảo trì"`, `"A-04 ĐÃ ĐẶT 13:30"`, `"A-05 ĐÃ ĐẶT 14:30"`, `"B-07 ĐÃ ĐẶT 15:00"`, `"Người đặt trước"`, and `"Đánh dấu đặt trước"`.
  - **Resolution**: Added `slot_reservation` (`code`, `slot_id`, `customer_id NULL`, `vehicle_id NULL`, `reserved_name`, `reserved_phone`, `reserved_from`, `reserved_until`, `status IN ('ACTIVE', 'COMPLETED', 'CANCELLED', 'EXPIRED')` `[PROPOSAL]` `OQ-81`, `notes`, `created_by`, soft-delete + `row_version`) with GiST exclusion constraint `excl_reservation_slot_time_overlap` (`tstzrange(reserved_from, reserved_until, '[)') WHERE (deleted_at IS NULL AND status = 'ACTIVE')`), `fn_guard_slot_reservation_write()`, `fn_sync_slot_status_on_reservation()`, and conflict check in `fn_guard_slot_reservation_on_entry()` (`PROP-4.5.2-P05`, `OQ-81`).
- **`TL-05` — Unregistered Visitor Vehicles & Session Code**:
  - **FE Evidence**: `Lịch sử ra/vào — Smart Mobility.png` displays `"Mã phiên đỗ"` / `"Mã phiên đỗ xe"`, `"Biển số xe"`, `"Thời gian vào"`, `"Thời gian ra"`, `"Tổng thời gian đỗ"`, `"Cước phí"`, and `"Hình ảnh đối soát"`.
  - **Resolution**: Changed `vehicle_entry_exit_log.vehicle_id` to `BIGINT NULL` so unregistered visitors can check in and out. Added `session_code VARCHAR(30) NOT NULL UNIQUE` (`uq_log_session_code`) and `fee_amount NUMERIC(12,2) NOT NULL DEFAULT 0` (`ck_log_fee_nonnegative`). Kept `license_plate` and stored generated `license_plate_norm`. Updated `uq_log_open_session_vehicle` to `WHERE exit_time IS NULL AND vehicle_id IS NOT NULL` while `uq_log_open_session_plate` prevents duplicate open sessions for any normalized plate. Updated `fn_guard_slot_reservation_on_entry()` to verify normalized plate match against the active vehicle on open sessions (`NEW.exit_time IS NULL`) when `NEW.vehicle_id IS NOT NULL` on `INSERT` or when `license_plate`/`vehicle_id` changes (raising verbatim SRS message `'Lỗi dữ liệu không tìm thấy đê lưu'` on mismatch, while never blocking session closure when `NEW.exit_time IS NOT NULL`). Parking duration (`Tổng thời gian đỗ`) is derived from `COALESCE(exit_time, CURRENT_TIMESTAMP) - entry_time`.
- **`TL-06` — Gates & AI License-Plate Recognition**:
  - **FE Evidence**: `Trang chủ — Smart Mobility.png` (`"Tỉ lệ AI nhận dạng"` `98.4%`, `"AI: 98.4% (Tự động mở)"`, `"Nhập thủ công: 1.6% (19 xe)"`, `"Cổng vào 1"`, `"Cổng vào 2"`, `"Cổng ra 2"`, `"Xem ảnh (99%)"`, `"Ảnh khớp"`, `"Cần duyệt"`, `"Camera cổng ra 1: Độ sáng thấp, tỉ lệ chính xác thấp"`), `Main Page.png` (`"4 Cổng quét tự động"`, `"Cổng ra 1"`, `"Cổng vào 2"`, `"Cổng vào 1"`, `"Cổng ra 3"`).
  - **Resolution**: Added `parking_gate` (`lot_id`, `code`, `name`, `direction IN ('IN', 'OUT')`, `camera_status IN ('ONLINE', 'LOW_LIGHT', 'DEGRADED', 'OFFLINE')`, `is_auto_scan`, `is_active`, `uq_parking_gate_lot_code_active`) and added `entry_gate_id`, `exit_gate_id`, `ai_confidence NUMERIC(5,2) NULL` (`0..100`), `recognition_source VARCHAR(20) NOT NULL DEFAULT 'AI'` (`'AI'`, `'MANUAL'`), and `review_status VARCHAR(20) NOT NULL DEFAULT 'AUTO'` (`'AUTO'`, `'MATCHED'`, `'NEEDS_REVIEW'`, `'APPROVED'`, `'REJECTED'` `[PROPOSAL]` `OQ-81`) on `vehicle_entry_exit_log`.
- **`TL-07` — Payments (`Tiền mặt`, `QR` / `VietQR`, Per-Session & Ticket Fees)**:
  - **FE Evidence**: `Trang chủ — Smart Mobility.png` (`"Doanh thu hôm nay"` `150.000đ`, `"Tiền mặt: 18% | QR: 82%"`), `Main Page.png` (`"VietQR"`, `"DOANH THU HÔM NAY"` `35.4M`), `Quản lý vé — Smart Mobility.png` (`"Giá vé"`, `"Giá gia hạn"`), `Lịch sử ra/vào — Smart Mobility.png` (`"Cước phí"`), and `Quản lý xe — Smart Mobility.png` (`"Chi phí thuộc module Vé/Giao dịch"`).
  - **Resolution**: Added `payment` (`code`, `amount`, `method IN ('CASH', 'VIETQR')`, `status IN ('UNPAID', 'PAID', 'CANCELLED', 'REFUNDED')` `[PROPOSAL]` `OQ-81`, `paid_at`, `received_by`, `provider_ref`, `session_id`, `ticket_id`, `renewal_id`, `notes`, `ck_payment_single_target CHECK (num_nonnulls(session_id, ticket_id, renewal_id) = 1)`, `ck_payment_paid_timestamp`). Added `v_revenue_today_by_method` and updated `v_revenue_statistics` and `fn_stat_revenue_by_period`.
- **`TL-08` — Customer Status, Blacklist & Debt**:
  - **FE Evidence**: `Khách hàng — Smart Mobility.png` (`"Tổng khách hàng"` `1,420`, `"Thuê bao kích hoạt"` `1,280`, `"Sắp hết hạn (7 ngày)"` `42`, `"Blacklist/Tạm khoá"` `15`), `Trang chủ — Smart Mobility.png` & `Main Page.png` (`"Biển số 51G-888.88 thuộc Blacklist (Nợ phí)"`).
  - **Resolution**: Added `status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'` (`'ACTIVE'`, `'SUSPENDED'`, `'BLACKLISTED'`) and `status_reason TEXT NULL` (`ck_customer_blacklist_reason`) on `customer`. Added `plate_blacklist` (`license_plate`, `license_plate_norm`, `reason NOT NULL`, `unpaid_amount NUMERIC(12,2) NOT NULL DEFAULT 0`, `is_active`, `added_by`, `uq_plate_blacklist_norm_active`) and view `v_customer_status_summary`.
- **`TL-09` — Vehicles (`Ô tô`, `Xe điện`, `Ảnh`, `Ghi chú`, Derived Status)**:
  - **FE Evidence**: `Quản lý xe — Smart Mobility.png` (`"Mã xe"`, `"Ảnh"`, `"Loại xe"`: `"Ô tô"`, `"Xe điện"`, `"Ghi chú"`, `"Trạng thái"`: `"Đang đỗ"`, `"Đang hoạt động"`, `"Đã rời bãi"`, `"Khách hàng liên kết với phương tiện"`).
  - **Resolution**: Seeded `vehicle_type` with 2 car-only rows (`CAR` `"Ô tô"` and `EV` `"Xe điện"` per `TL-20`). Added `image_url TEXT NULL` and `notes TEXT NULL` on `vehicle` and kept `customer_id NOT NULL`. Vehicle parking status (`Đang đỗ` / `Đã rời bãi` / `Đang hoạt động`) is derived from `vehicle_entry_exit_log` (`exit_time IS NULL`).
- **`TL-10` — Tickets, Types, Prices, Statuses & Renewals**:
  - **FE Evidence**: `Quản lý vé — Smart Mobility.png` (`"Vé ngày"` `50.000đ`, `"Vé tháng"` `500.000đ`, `"Vé quý"` `1.200.000đ`) and `Quản lý xe — Smart Mobility.png` (`"Vé năm"`); 5 status badges on `Quản lý vé` (`"Đang hoạt động"`, `"Sắp hết hạn"`, `"Đã hết hạn"`, `"Đã hủy"`, `"Đang gia hạn"`); 3 dialogs (`"Thêm vé mới"`, `"Gia hạn vé"`, `"Chi tiết vé"` with `"Ghi chú"` and `"Lịch sử gia hạn"`).
  - **Resolution**: Seeded `ticket_type` with 4 rows (`DAILY` `"Vé ngày"` `1` day `50000.00`, `MONTHLY` `"Vé tháng"` `30` days `500000.00`, `QUARTERLY` `"Vé quý"` `90` days `1200000.00`, `YEARLY` `"Vé năm"` `365` days `4800000.00` `[PROPOSAL]` `OQ-79`). Updated `ck_ticket_status_enum` to `('ACTIVE', 'RENEWING', 'EXPIRED', 'CANCELLED')`; `"Sắp hết hạn"` is derived when `status = 'ACTIVE' AND effective_to <= CURRENT_TIMESTAMP + INTERVAL '7 days'`. Added `notes TEXT NULL` on `ticket` and `ticket_renewal`. Kept `ck_ticket_time_order CHECK (effective_to > effective_from)` (1-day tickets stored as `[effective_from, effective_from + INTERVAL '1 day')`).
- **`TL-11` — Employees & Positions**:
  - **FE Evidence**: `Quản lý nhân viên - Smart mobility.png` (`"MÃ NV"`: `NV001..NV008`; 4 positions `"Quản lý"`, `"Nhân viên vận hành"`, `"Nhân viên thu ngân"`, `"Kỹ thuật viên"`; statuses `"Đang hoạt động"`, `"Không hoạt động"`) and `Quản lý vé — Smart Mobility.png` Dialog 3 (`"Nhân viên phát hành: NV0005"`).
  - **Resolution**: Seeded `position` with 4 rows (`QL` `"Quản lý"`, `NVVH` `"Nhân viên vận hành"`, `NVTN` `"Nhân viên thu ngân"`, `KTV` `"Kỹ thuật viên"`). Updated `ck_employee_code_format` to `CHECK (code ~ '^NV[0-9]{3,4}$')` and added `employee.status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE'` (`CHECK (status IN ('ACTIVE', 'INACTIVE'))`).
- **`TL-12` — Activity Feed (`Hoạt động gần đây`)**:
  - **FE Evidence**: `Sơ đồ bãi đậu xe — Smart Mobility.png` (`"Hoạt động gần đây"` / `"Nhật ký thao tác"`).
  - **Resolution**: Added append-only table `activity_log` (`id`, `actor_account_id`, `action`, `entity_type`, `entity_id`, `message`, `occurred_at`) protected by `trg_activity_log_immutable` (`fn_prevent_activity_log_mutation()`, `PROP-4.5.2-P06`, `OQ-81`).
- **`TL-13` — Dashboard Alerts (`Cảnh báo bất thường và khẩn cấp`)**:
  - **FE Evidence**: `Trang chủ — Smart Mobility.png` & `Main Page.png` (`"Biển số 51G-888.88 thuộc Blacklist (Nợ phí)"`, `"Cảnh báo đỗ xe quá 48 giờ tại vị trí B2 - 55"`, `"Camera cổng ra 1: Độ sáng thấp, tỉ lệ chính xác thấp"`).
  - **Resolution**: Added `system_alert` (`id`, `alert_type IN ('BLACKLIST_PLATE', 'OVERSTAY', 'CAMERA_QUALITY', 'SYSTEM')`, `severity IN ('INFO', 'WARNING', 'CRITICAL')` `[PROPOSAL]` `OQ-81`, `message`, `entity_type`, `entity_id`, `occurred_at`, `resolved_at`, `resolved_by`, `created_at`).
- **`TL-14` — Dashboard KPIs & Charts**:
  - **FE Evidence**: `Trang chủ — Smart Mobility.png` (`"Kho vị trí"`, `"Lượt xe trong ngày"`, `"Doanh thu hôm nay"`, `"Tỉ lệ AI nhận dạng"`, `"Sơ đồ các tầng"`, `"Biểu đồ lưu lượng và công suất theo giờ"`).
  - **Resolution**: Updated `v_slot_occupancy_by_floor` (grouping by `parking_lot`, `parking_floor`, and `parking_zone` with `occupied_slots`, `reserved_slots`, `charging_slots`, `available_slots`, `maintenance_slots`, and `occupancy_rate_pct`) and added `v_revenue_today_by_method`, `v_traffic_by_hour`, and `v_ai_recognition_stats`.
- **`TL-15` — Keep SRS Rules Where FE Is Silent**:
  - **Resolution**: Preserved 3-level administrative address hierarchy (`administrative_province`, `administrative_district`, `administrative_ward` with composite FKs on `employee` and `customer`), `date_of_birth`, `gender IN ('Nam', 'Nữ')`, `identity_card_number`, `news`, `notification`, `v_customer_vehicle_summary`, `v_vehicle_traffic_daily`, `v_revenue_statistics`, `fn_stat_*` functions, `row_version` OCC triggers, soft-delete columns (`deleted_at`, `deleted_by`), and `ON DELETE RESTRICT` across all `69` foreign keys.
- **`TL-16` — Pure UI / Marketing Elements (`UI only`)**:
  - **FE Evidence**: `Main Page.png` (hero banner copy, `SmartPark UI Template Kit` footer), `Vector.png` (`17x17` icon), `clarity_edit-line.png` (`18x18` icon), and CSV/report export buttons (`"Xuất CSV"`, `"Xuất báo cáo"`).
  - **Resolution**: Classified as pure frontend presentation / query-parameter controls requiring `0` database tables or columns.
- **`TL-17` — Visitor Plate Auto-Link on Entry & Update**:
  - **Resolution**: When a parking session is inserted or its plate changes with `vehicle_id IS NULL` and its normalized plate matches an active registered vehicle (`vehicle.license_plate_norm WHERE deleted_at IS NULL`), `fn_guard_slot_reservation_on_entry()` sets `NEW.vehicle_id` to that vehicle (`LIMIT 1`), preventing registered vehicles from entering as unlinked visitor rows or bypassing `uq_log_open_session_vehicle`. The active-vehicle plate verification (`NEW.vehicle_id IS NOT NULL`) runs only on open sessions (`NEW.exit_time IS NULL`) on `INSERT` or when `license_plate`/`vehicle_id` changes so closing a session always succeeds even if the vehicle was later soft-deleted.
- **`TL-18` — Optional Profile Fields Not Collected by the Frontend**:
  - **Resolution**: Changed `customer.date_of_birth`, `customer.gender`, `customer.address`, `customer.email` and `employee.date_of_birth`, `employee.gender`, `employee.identity_card_number`, `employee.address` to `NULL` (optional) so phone-only self-registration (`TL-01`) and Frontend profile forms succeed without requiring uncollected SRS fields. Kept all format `CHECK` constraints for non-null values and partial unique indexes `uq_customer_email_active` (`WHERE deleted_at IS NULL AND is_anonymized = FALSE AND email IS NOT NULL`) and `uq_employee_idcard_active` (`WHERE deleted_at IS NULL AND identity_card_number IS NOT NULL`), while keeping `customer.identity_card_number`, `customer.phone`, `customer.full_name`, `employee.phone`, `employee.email`, and `employee.full_name` `NOT NULL`.
- **`TL-19` — Documentation Source Hierarchy, Team Lead Decision Authority & cSpell Hygiene**:
  - **Resolution**: Updated `docs/README.md`, `docs/requirements/00-srs-catalog.md`, and `docs/requirements/05-proposed-messages.md` to state that the SRS is authoritative for the SRS content and secondary to the Frontend design; updated `.claude/rules/02-srs-single-source-of-truth.md` to state that the Team Lead decides all requirement and schema questions; and moved all inline `cspell` words into `cspell.json`.
- **`TL-20` — Car-Only Vehicle Types (`CAR`, `EV`)**:
  - **Resolution**: The parking facility supports cars only (`vehicle_type` seeds `('CAR', 'Ô tô', ...)` for ordinary cars and `('EV', 'Xe điện', ...)` for electric cars `"ô tô điện"`). Kept `EV_CHARGING` slots and `CHARGING` status for electric cars, and recorded the SRS 4/7/12-seat classification as a decided deferral in [`01-decision-log.md`](01-decision-log.md) (`OQ-49`).
- **`TL-21` — Case-Insensitive Email Uniqueness (`lower(email)`)**:
  - **Resolution**: Replaced the active-row partial unique indexes `uq_account_email_active`, `uq_employee_email_active`, and `uq_customer_email_active` in [`db/01-schema.sql`](../../db/01-schema.sql) with expression indexes on `lower(email)` keeping the same `WHERE` predicates (`OQ-84`).
- **`TL-22` — Compact Decision Log (`01-decision-log.md`)**:
  - **Resolution**: Replaced the legacy open-questions catalog with the compact decision log [`01-decision-log.md`](01-decision-log.md) (`OQ-01`–`OQ-84`) recording all decided outcomes and deferrals (`OQ-49`, `OQ-68`, `OQ-80`).
- **`TL-23` — Soft-Delete Representation & Integrity**:
  - **Resolution**: The database keeps `deleted_at TIMESTAMPTZ NULL` and `deleted_by BIGINT NULL`. A deleted row is defined strictly as `deleted_at IS NOT NULL`. The team meeting's `isDeleted` flag is exposed at the API serializer / model property layer without adding redundant columns to the physical schema. Added `ck_*_soft_delete_pair CHECK ((deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL))` across all 18 soft-deletable tables. Restoring a record clears both `deleted_at` and `deleted_by` back to `NULL`.
- **`TL-24` — Hard Delete Prohibition & Controlled Purge**:
  - **Resolution**: Hard `DELETE` statements from application client sessions are rejected across all 28 tables by `BEFORE DELETE` trigger guards (`trg_activity_log_immutable`, `11` `trg_guard_*_immutable` via `fn_guard_hard_immutable_table()`, and `16` `trg_prevent_plain_delete_*` via `fn_guard_prevent_plain_delete()`). Critical financial, audit, and reference entities (`ticket`, `ticket_renewal`, `payment`, `vehicle_entry_exit_log`, `activity_log`, `system_alert`, `persistent_login_token`, `password_reset_token`, `administrative_province`, `administrative_district`, `administrative_ward`, `slot_allowed_vehicle_type`) can NEVER be purged. A hardened `SECURITY DEFINER` function `fn_controlled_purge(p_table_name, p_retention, p_dry_run, p_purged_by, p_target_id)` allows automated administrator cleanup strictly for rows already in trash (`deleted_at < CURRENT_TIMESTAMP - p_retention`) on the 16 eligible purgeable tables (`news`, `notification`, `slot_reservation`, `plate_blacklist`, `parking_slot`, `parking_zone`, `parking_floor`, `parking_lot`, `parking_gate`, `vehicle`, `customer`, `employee`, `account`, `ticket_type`, `vehicle_type`, `position`), enforcing Decree 13/2023/ND-CP anonymization on `customer` and writing `'PURGE'` audit rows to `activity_log`.
- **`TL-25` — Database Soft-Delete Guards (DEL-01..DEL-06)**:
  - **Resolution**: Enforced business soft-delete guard rules at the database level via `BEFORE UPDATE OF deleted_at` triggers (`fn_guard_soft_delete_and_restore()`, `18` `trg_guard_soft_delete_and_restore_*` triggers):
    - `parking_slot`: Rejects deletion if slot is `OCCUPIED`, `RESERVED`, or `CHARGING`, or has open sessions/active tickets (`DEL-05`).
    - `customer`: Rejects deletion if customer has active vehicles, open sessions, or unexpired tickets (`DEL-02`).
    - `vehicle`: Rejects deletion if vehicle has an active ticket, active reservation, or open parking session (`DEL-03`).
    - `employee` / `account`: Rejects self-deletion and deletion of the last active `MANAGER` account (`DEL-01`).
    - Structural tables: Rejects deletion of lots with active floors, floors with active zones, and zones with active slots (`DEL-06`).
    - Lookup tables: Rejects deletion of `ticket_type` with active tickets, `position` with active employees, `vehicle_type` with active vehicles, and `parking_gate` with open sessions (`DEL-06`).
    - `ticket`: Enforces `ck_ticket_delete_only_expired` and rejects deletion of active, renewed, or currently parked tickets (`DEL-04`).
- **`TL-26` — Restoration Guards & Append-Only Audit Logging**:
  - **Resolution**: Restoring a soft-deleted row (`deleted_at` set back to `NULL`) is guarded by `fn_guard_soft_delete_and_restore()`, requiring parent entities to be active (e.g. restoring a vehicle requires an active customer and vehicle_type; restoring a slot requires an active zone) and clearing `deleted_by = NULL`. Unique constraint collisions on restore are caught by active-row partial unique indexes. Soft-delete, restore, and purge actions append immutable audit rows to `activity_log` (`fn_audit_soft_delete_and_restore()`, `18` `trg_audit_soft_delete_and_restore_*` triggers) with action codes `'SOFT_DELETE'`, `'RESTORE'`, and `'PURGE'`.
- **`TL-27` — Read-Side Consistency & Analytical View Filtering**:
  - **Resolution**: All 8 analytical views (`v_slot_occupancy_by_floor`, `v_revenue_today_by_method`, `v_traffic_by_hour`, `v_ai_recognition_stats`, `v_customer_status_summary`, `v_revenue_statistics`, `v_vehicle_traffic_daily`, `v_customer_vehicle_summary`) and all `fn_stat_*` functions explicitly filter `deleted_at IS NULL` on underlying business tables. The standard application querying rule for all read/detail/list/filter operations is: `WHERE deleted_at IS NULL`.
- **`TL-28` — Frontend Derived Values & Verification SQL**:
  - **Resolution**: Decided and documented dynamic SQL derivations for 6 specific Frontend values rather than storing redundant physical columns:
    1. Ticket "Sắp hết hạn" (`expiring soon` within 7 days).
    2. Vehicle derived status (`Đang đỗ`, `Đang hoạt động`, `Đã rời bãi`).
    3. Remaining ticket days and elapsed percentage.
    4. Parking session duration (`Tổng thời gian đỗ`).
    5. Customer subscription KPIs (`Thuê bao kích hoạt` and `Sắp hết hạn (7 ngày)`).
    6. Floor occupancy percentage bars on the Home screen.
    Full production SQL proof queries and explanations are cataloged in [`07-fe-srs-traceability.md`](07-fe-srs-traceability.md) Section 4.
- **`TL-29` — Dynamic Floor Hierarchy & Home Screen B3 Alignment**:
  - **FE Evidence**: `Trang chủ — Smart Mobility.png`, `Main Page.png`, and Row 5 of `Quản lý vé — Smart Mobility.png` display `"Tầng B3"`, while `Sơ đồ bãi đậu xe — Smart Mobility.png` (structure management) lists `"Tầng B1"`, `"Tầng B2"`, and `"Tầng F1"`.
  - **Resolution**: Recognized the discrepancy as a Frontend mockup inconsistency. The database table `parking_floor` is designed as a data-driven configuration table, capable of storing any number of floors (`B1`, `B2`, `B3`, `F1`, etc.) via its foreign key `lot_id` and unique code `code VARCHAR(20)`. Default seed data retains 3 operational floors (`B1`, `B2`, `F1`) matching the Structure Management wireframe, while the backend API fully accommodates adding `B3` dynamically without schema alterations.
- **`TL-30` — Employee Area Field Formatting (District + Province)**:
  - **FE Evidence**: `Quản lý nhân viên - Smart mobility.png` displays column `"KHU VỰC"` formatted as a 2-line label with District on top (`Hải Châu`, `Thanh Khê`, `Quận 1`, `Cầu Giấy`) and Province below (`Đà Nẵng`, `Hồ Chí Minh`, `Hà Nội`).
  - **Resolution**: Retained the complete 3-tier administrative hierarchy in [`db/01-schema.sql`](../../db/01-schema.sql) (`administrative_province`, `administrative_district`, `administrative_ward` per `TL-15`), which provides superior normalization and geographic data integrity. The DRF Employee serializer is responsible for combining `district.name` and `province.name` into the formatted `area` object for Frontend consumption.
- **`TL-31` — Query Filter Optimization & Foreign Key Indexes**:
  - **FE Evidence**: High-frequency filter controls across Frontend screens: ticket type filter on Vehicle and Ticket screens, date range and gate filters on Entry/Exit History, customer and plate filters on Reservation, and administrative area filters on Employee and Customer screens.
  - **Resolution**: Enhanced database performance without modifying tables, columns, or ERD multiplicity by adding targeted B-tree and partial indexes:
    - `idx_vehicle_ticket_type_id` on `vehicle (ticket_type_id) WHERE deleted_at IS NULL` (Quản lý xe filter).
    - `idx_ticket_ticket_type_id` on `ticket (ticket_type_id) WHERE deleted_at IS NULL` (Quản lý vé filter).
    - `idx_entry_exit_ticket_id` on `vehicle_entry_exit_log (ticket_id)` (session-to-ticket reconciliation).
    - `idx_entry_exit_gates` on `vehicle_entry_exit_log (entry_gate_id, exit_gate_id)` and `idx_entry_exit_exit_gate_id` on `vehicle_entry_exit_log (exit_gate_id)` (gate traffic analytics).
    - `idx_slot_reservation_customer_id` on `slot_reservation (customer_id) WHERE deleted_at IS NULL` and `idx_slot_reservation_vehicle_id` on `slot_reservation (vehicle_id) WHERE deleted_at IS NULL` (reservation lookups).
    - `idx_employee_district_province` on `employee (district_id, province_id) WHERE deleted_at IS NULL` and `idx_customer_district_province` on `customer (district_id, province_id) WHERE deleted_at IS NULL` (administrative area filters).
    - `idx_log_review_status` on `vehicle_entry_exit_log (review_status, entry_time DESC)` and `idx_news_author_id` on `news (author_id) WHERE deleted_at IS NULL`.
- **`TL-32` — Comprehensive CHECK Constraints & Soft-Delete Invariants**:
  - **Resolution**: Re-audited and preserved 100% of the repository's CHECK constraints across all 28 tables, ensuring strict validation of status enums (`ck_slot_status_enum`, `ck_ticket_status_enum`, `ck_payment_status_enum`, etc.), business code formats (`ck_*_code_format`), nonnegative monetary and physical measurements (`fee_amount >= 0`, `price >= 0`, `width > 0`), valid date/time intervals (`effective_to > effective_from`), and the soft-delete invariant `ck_*_soft_delete_pair CHECK ((deleted_at IS NULL AND deleted_by IS NULL) OR (deleted_at IS NOT NULL))` across all 18 soft-deletable tables (`TL-23`).
- **`TL-33` — Schema COMMENTs Bilingual Policy**:
  - **Resolution**: Established an authoritative bilingual documentation standard for database metadata:
    - All technical descriptions, column behaviors, foreign key purposes, and constraint semantics are written in clean, concise English.
    - Verbatim Vietnamese UI labels (e.g., `"Mã phiên đỗ xe"`, `"Sắp hết hạn"`, `"Xe ô tô tiêu chuẩn"`) and verbatim SRS requirements/error messages are explicitly quoted in double quotes alongside the English definitions.
    - Maintained 100% COMMENT coverage on all 28 base tables, 338 table columns, and 8 views.
- **`TL-34` — Timestamp (TIMESTAMPTZ UTC) & Currency (NUMERIC(12,2)) Precision**:
  - **FE Evidence**: Timestamps displayed across screens (e.g., entry/exit time `2026-10-17 08:30`, reservation time `13:30`) and currency figures (e.g., `150.000đ`, `500.000đ`, `35.4M`).
  - **Resolution**: All temporal attributes (`created_at`, `updated_at`, `deleted_at`, `entry_time`, `exit_time`, `effective_from`, `effective_to`, `reserved_from`, `reserved_until`, `paid_at`, `occurred_at`) are strictly typed as `TIMESTAMPTZ` (UTC storage in PostgreSQL). The API presentation layer localizes timestamps to Indochina Time (ICT, UTC+7). All monetary attributes (`price`, `fee_amount`, `amount`, `default_price`, `unpaid_amount`) use exact decimal arithmetic via `NUMERIC(12,2)` to prevent floating-point rounding errors.
- **`TL-35` — Reaffirmation of Car-Only Parking Facility Scope (`CAR` & `EV`)**:
  - **FE Evidence**: Row 3 of `Quản lý xe — Smart Mobility.png` displays `"Xe máy"` as a sample row.
  - **Resolution**: Reaffirmed foundational decisions `TL-09` and `TL-20`: the system is strictly engineered for automobile parking lots (`Hệ thống quản lý bãi đậu xe ô tô`). `vehicle_type` seeds contain only `CAR` (`"Ô tô"`) and `EV` (`"Xe điện"`). The appearance of "Xe máy" in the mockup is classified as a designer mock artifact; the database and API strictly reject non-car registrations.
- **`TL-36` — Token Tables Plain DELETE Exemption & Account Purge Cleanup**:
  - **Context**: Bảng `persistent_login_token` và `password_reset_token` lưu trữ thông tin xác thực tạm thời, cần xóa vật lý khi logout, rotation hoặc thu hồi token.
  - **Resolution**: Gỡ bỏ trigger immutable trên 2 bảng token, cho phép thực thi plain `DELETE`. Giữ nguyên 100% `ON DELETE RESTRICT` trên khóa ngoại tới `account`. Khi thực hiện dọn dẹp tài khoản qua `fn_controlled_purge()`, thủ tục chủ động xóa các token liên kết của tài khoản trong cùng subtransaction trước khi xóa bản ghi `account`. Thực nghiệm: lệnh xóa token chạy thành công và purge account dọn dẹp sạch sẽ không lỗi khóa ngoại.
- **`TL-37` — Slot Allowed Vehicle Type Editing & Delete Guard (`PROP-DEL-SAVT-IN-USE`)**:
  - **Context**: Bảng liên kết `slot_allowed_vehicle_type` cần cho phép cấu hình linh hoạt loại xe của ô đỗ khi vận hành (SRS 4.8.2).
  - **Resolution**: Gỡ bỏ immutable trigger trên `slot_allowed_vehicle_type`. Bổ sung trigger `trg_guard_slot_allowed_vehicle_type_delete` chặn gỡ loại xe khi ô đang có vé hiệu lực (`ACTIVE`/`RENEWING`), phiên đỗ đang mở (`exit_time IS NULL`), hoặc đặt chỗ hiệu lực (`ACTIVE`) của loại xe đó (`PROP-DEL-SAVT-IN-USE`).
- **`TL-38` — Slot Vehicle Type Compatibility Validation (`PROP-SLOT-VEHICLE-TYPE-MISMATCH`)**:
  - **Context**: Ngăn ngừa trường hợp xe không tương thích (ví dụ xe xăng `CAR`) được cấp vé hoặc check-in vào ô đỗ chuyên dụng (ví dụ ô sạc điện `EV`).
  - **Resolution**: Tích hợp kiểm tra bảng `slot_allowed_vehicle_type` vào 3 trigger functions: `fn_sync_ticket_status`, `fn_guard_slot_reservation_write`, và `fn_guard_slot_reservation_on_entry`. Ném lỗi `check_violation` kèm HINT `PROP-SLOT-VEHICLE-TYPE-MISMATCH, TL-38` khi có sự không tương thích loại xe.
- **`TL-39` — Payment Soft-Delete Guard for Settled Transactions (`PROP-DEL-PAYMENT-SETTLED`)**:
  - **Context**: Giao dịch `PAID` và `REFUNDED` là chứng từ tài chính kế toán theo Luật Kế toán 88/2015/QH13, việc xóa mềm sẽ làm sai lệch doanh thu trên dashboard và các view báo cáo.
  - **Resolution**: Bổ sung nhánh kiểm tra trong `fn_guard_soft_delete_and_restore()` chặn soft-delete khi `payment.status IN ('PAID', 'REFUNDED')` với lỗi `PROP-DEL-PAYMENT-SETTLED, TL-39`. Chỉ cho phép soft-delete giao dịch `UNPAID` hoặc `CANCELLED`.
- **`TL-40` — fn_controlled_purge 30-Day Retention Floor & Batch Foreign Key Skip**:
  - **Context**: Thiết lập sàn bảo vệ dữ liệu thùng rác và ngăn chặn rollback cả batch khi có 1 dòng rác bị khóa ngoại tham chiếu.
  - **Resolution**: Kiểm tra `p_retention >= INTERVAL '30 days'` (ném lỗi `22023` nếu nhỏ hơn). Trong batch mode (`p_target_id IS NULL`), lặp từng dòng và bắt ngoại lệ `foreign_key_violation` (23503) và `restrict_violation` (23001) để tự động bỏ qua dòng bị tham chiếu, tiếp tục dọn dẹp các dòng hợp lệ khác. Trả về bảng 5 cột `(table_name varchar, eligible_count bigint, purged_count bigint, status varchar, details text)`.
- **`TL-41` — Substring Text Search Acceleration via pg_trgm & GIN Trigram Indexes**:
  - **Context**: Các truy vấn tìm kiếm chuỗi con trên FE (`ILIKE '%...%'`) trên bảng lớn gây quét tuần tự (`Seq Scan`) tốn I/O.
  - **Resolution**: Tạo extension `pg_trgm` và 6 partial GIN trigram indexes (`WHERE deleted_at IS NULL`). Số liệu thực nghiệm `EXPLAIN (ANALYZE, BUFFERS)` trên 630.320 bản ghi:
    - Tìm tên KH (50k rows): Seq Scan 23.04ms (513 buffers) -> Bitmap Index Scan 0.54ms (45 buffers) (tăng tốc **43.0x**, giảm **91.2%** buffers).
    - Tìm SĐT KH (50k rows): 5.69ms (1021 buffers) -> 0.58ms (66 buffers) (tăng tốc **9.8x**, giảm **93.5%** buffers).
    - Tìm biển số xe (80k rows): 9.14ms (1381 buffers) -> 0.53ms (63 buffers) (tăng tốc **17.4x**, giảm **95.4%** buffers).
    - Tìm mã phiên log (500k rows): 68.29ms (10210 buffers) -> 6.97ms (527 buffers) (tăng tốc **9.8x**, giảm **94.8%** buffers).
    - Tìm biển số log (500k rows): 21.07ms (10210 buffers) -> 3.70ms (329 buffers) (tăng tốc **5.7x**, giảm **96.8%** buffers).
- **`TL-42` — Payment Status Transition & Settled Immutability Guard (`PROP-PAY-STATUS-TRANSITION`, `PROP-PAY-SETTLED-IMMUTABLE`)**:
  - **Context**: Bổ sung cơ chế kiểm soát chuyển trạng thái thanh toán và bảo vệ tính bất biến của chứng từ tài chính đã thanh toán (`PAID`) hoặc hoàn tiền (`REFUNDED`), ngăn chặn hành vi sửa trạng thái sang `CANCELLED` để luồn lách xóa mềm hoặc chỉnh sửa số tiền/liên kết doanh thu.
  - **Resolution**: Bổ sung hàm `fn_guard_payment_update()` và trigger `trg_guard_payment_update` `BEFORE UPDATE ON payment`:
    - Ràng buộc chuyển đổi trạng thái: `UNPAID -> PAID | CANCELLED`; `PAID -> REFUNDED`; `REFUNDED` và `CANCELLED` là trạng thái kết thúc (terminal); cấm chuyển ngược về `UNPAID`. Mọi chuyển đổi vi phạm đều bị từ chối với lỗi `check_violation` kèm HINT `PROP-PAY-STATUS-TRANSITION, TL-42`.
    - Bảo vệ bất biến chứng từ đã kết toán: Khi bản ghi ở trạng thái `PAID` hoặc `REFUNDED`, cấm sửa đổi bất kỳ cột tài chính hoặc liên kết nào (`amount`, `method`, `paid_at`, `session_id`, `ticket_id`, `renewal_id`, `code`), ném lỗi `check_violation` kèm HINT `PROP-PAY-SETTLED-IMMUTABLE, TL-42`. Cho phép cập nhật cột `notes` (ghi chú nghiệp vụ đối soát).
- **`TL-43` — Extension-Independent Function Count in CI**:
  - **Context**: Query kiểm tra schema trong CI assertion trước đây đếm toàn bộ hàm trong namespace `public`, vô tình gộp cả ~243 hàm nội tại của extension `btree_gist` và `pg_trgm`, gây rủi ro gãy CI khi cập nhật minor version của PostgreSQL hoặc image Docker mà không có thay đổi mã nguồn.
  - **Resolution**: Cập nhật câu lệnh đếm function trong workflow `.github/workflows/01-db-schema-check.yml` loại trừ các hàm thành viên của extension thông qua `pg_depend` (`NOT EXISTS (SELECT 1 FROM pg_depend d WHERE d.classid = 'pg_proc'::regclass AND d.objid = p.oid AND d.deptype = 'e')`), chỉ đếm đúng 22 hàm người dùng thuộc sở hữu dự án (`15` trigger functions + `7` non-trigger functions). Khẳng định tính độc lập và nhất quán trên cả hai môi trường `postgres:18.6-alpine` và `postgres:18.6` (Debian).
- **`TL-44` — Django Schema Authority & Initial RunSQL Migration [COMPLETED]**:
  - **Context**: Xác định vai trò của CSDL PostgreSQL Schema v2 (`db/01-schema.sql`) là Single Source of Truth tuyệt đối. Tránh hiện tượng phân mảnh schema giữa Django ORM migrations và CSDL đã được tối ưu hóa cao độ với triggers, constraints và extensions.
  - **Resolution**:
    - Thiết lập app `apps/core` với migration ban đầu `0001_initial.py` sử dụng `migrations.RunSQL` đọc trực tiếp file `db/01-schema.sql` từ đĩa tại thời điểm migrate với `atomic=False` và `reverse_sql=migrations.RunSQL.noop`. Tuyệt đối không sinh DDL tự động bằng `makemigrations`.
    - Phát triển management command `python manage.py load_sample_data` đọc trực tiếp `db/02-seed.sql` với cờ bảo vệ an toàn `--force-production` khi `DEBUG=False`.
- **`TL-45` — 1:1 Unmanaged Models, 3-Tier Soft-Delete Hierarchy & Account Auth [COMPLETED]**:
  - **Context**: Ánh xạ toàn bộ cấu trúc CSDL gồm 28 bảng và 8 view sang Django ORM để phục vụ phát triển ứng dụng mà không làm sai lệch cấu trúc CSDL thực tế.
  - **Resolution**:
    - Toàn bộ 28 bảng (338 cột) và 8 view (55 cột) được khai báo thành Django unmanaged models (`managed=False`).
    - Tất cả khóa ngoại trong unmanaged models sử dụng `on_delete=models.DO_NOTHING` và `db_constraint=False`, giao quyền thực thi toàn bộ cho 69 ràng buộc `ON DELETE RESTRICT` ở tầng CSDL.
    - Cấu trúc kế thừa xóa mềm 3 tầng: `TimeStampedModel` (cung cấp `created_at`, `updated_at`), `SoftDeleteBaseModel` (bổ sung `row_version`), `SoftDeleteModel` (quản lý `deleted_at`, `deleted_by`, custom manager `deleted_at IS NULL`, `with_deleted()`, `only_deleted()`, `soft_delete()`, `restore()`). Cấm phương thức physical `delete()` trên business models, cho phép plain `DELETE` trên token models (`PersistentLoginToken`, `PasswordResetToken` per TL-36 / ADR-0004).
    - Model `Account` (`AUTH_USER_MODEL = 'accounts.Account'`) kế thừa `AbstractBaseUser` không kèm `PermissionsMixin`, định nghĩa `email`, `phone`, `role` (`MANAGER`, `EMPLOYEE`, `CUSTOMER`) với `is_staff` dẫn xuất từ `role == 'MANAGER'` (mã đăng nhập tùy biến bằng Email/Phone và remember-me sẽ do thành viên được phân công triển khai theo `TL-48`).
    - Message catalog tập trung tại `apps/core/messages.py` ánh xạ chính xác các mã lỗi và thông báo SRS / PROPOSAL (`119` thông báo).
    - Automated test [`tests/test_schema_parity.py`](../../tests/test_schema_parity.py) kiểm tra đối soát trực tiếp live database: 100% khớp 28 bảng, 8 view, 69 FKs, 393 cột và `14/14` tests passed.
- **`TL-46` — Pinned Dependencies, Quality Gates & CI Workflow 02 [COMPLETED]**:
  - **Context**: Chuẩn hóa toàn bộ môi trường phát triển, công cụ kiểm tra chất lượng mã nguồn tĩnh và tự động hóa quy trình CI/CD.
  - **Resolution**:
    - Ghim chính xác các phiên bản dependencies đã qua kiểm chứng tương thích: Python 3.14.7 (cấm Python 3.15), Django 6.1.2, DRF 3.18.3, psycopg 3.3.6 trong `requirements/01-base.txt` và `requirements/02-dev.txt`.
    - Cấu hình `pyproject.toml` đồng bộ: Ruff (linter & formatter, giới hạn 88 ký tự), Mypy kết hợp `django-stubs` và `djangorestframework-stubs` (0 lỗi), Pytest kết hợp `pytest-django` và `pytest-cov` với ngưỡng chặn coverage `>= 80%`.
    - Xây dựng workflow `.github/workflows/02-django-check.yml` chạy trên Ubuntu với Python 3.14.7 và PostgreSQL 18.6 service container, ghim immutable commit SHA cho tất cả GitHub Actions, tích hợp đầy đủ các bước kiểm tra static analysis, schema check, OpenAPI schema validation và test suite.
- **`TL-47` — Foundation Base Layer, Auth Endpoints, OpenAPI & Real PostgreSQL Tests [NARROWED BY TL-48]**:
  - **Context**: Xây dựng lớp nền tảng kiến trúc API ban đầu trong Round 29 bao gồm exception handler, OpenAPI, xác thực và các endpoint danh mục tham chiếu.
  - **Resolution**:
    - Thiết kế base exception handler tại `apps/core/exceptions.py` bắt và chuyển đổi toàn bộ exceptions và mã PostgreSQL SQLSTATE (`23514`, `55000`, `23503`, `23505`, `22023`) thành chuẩn JSON envelope `{"code": "...", "message": "...", "details": {...}}`.
    - Tích hợp `drf-spectacular` và Swagger UI / ReDoc tại `/api/schema/`, `/api/docs/`, `/api/redoc/` với sidecar assets. Endpoint kiểm tra sức khỏe `/api/health/`.
    - *Ghi chú*: Phạm vi các API xác thực (login, logout, me, remember-me) và 6 danh mục lookup ban đầu trong TL-47 đã được thu hẹp và bàn giao cho các thành viên phụ trách nghiệp vụ theo quyết định `TL-48`.
- **`TL-48` — Scope of Foundation Skeleton & Feature Code Handover [COMPLETED]**:
  - **Context**: Hoàn thiện pull request #13 dưới dạng foundation khung dự án chuẩn mực. Theo nguyên tắc làm việc nhóm của dự án, mã nguồn chức năng nghiệp vụ (login, remember-me token rotation, và các API danh mục lookups) thuộc về các thành viên được phân công triển khai, không đưa vào skeleton dùng chung.
  - **Resolution**:
    - Giữ nguyên 100% nền tảng cốt lõi: 36 unmanaged models (28 bảng, 8 view), hệ thống phân cấp SoftDelete (ADR-0003), `Account` làm `AUTH_USER_MODEL`, bảng `persistent_login_token` và `password_reset_token`, cơ sở hạ tầng core (catalog thông báo `messages.py`, custom `exceptions.py`, `pagination.py`, `HealthCheckView`, `0001_initial.py` RunSQL schema migration, `load_sample_data` command), cấu trúc 3 tầng rỗng cho các domain apps làm template, và cấu hình OpenAPI/Swagger.
    - Gỡ bỏ toàn bộ mã chức năng login, remember-me middleware/backend/views/serializers/services và 6 lookup endpoints; reset 4 file `urls.py` của các app về placeholder rỗng.
    - Thêm tài liệu hướng dẫn bàn giao trong `README.md` ("Not in this foundation") trỏ tới Skill 05 và Skill 13.
- **`TL-49` — Quality Gates Enforcement & CSpell Cache Exclusion [COMPLETED]**:
  - **Context**: Đảm bảo toàn bộ quy trình kiểm soát chất lượng (Quality Gates) của skeleton được duy trì nghiêm ngặt sau khi thu hẹp phạm vi, đồng thời loại bỏ nhiễu sai chính tả sinh ra từ cache của các công cụ linter/tester.
  - **Resolution**:
    - Bổ sung các thư mục cache của công cụ (`.ruff_cache/**`, `.mypy_cache/**`, `.pytest_cache/**`) vào `ignorePaths` trong `cspell.json`.
    - Bắt buộc vượt qua 100% các Quality Gates: `ruff check .` (0 lỗi), `ruff format --check .` (0 lỗi), `mypy .` (0 lỗi), `python manage.py makemigrations --check --dry-run` (0 thay đổi), `python manage.py spectacular --validate --fail-on-warn` (0 cảnh báo/lỗi), `python manage.py check --deploy` (0 lỗi), `pytest` với line coverage trên `apps/` đạt `>= 80%`.
- **`TL-50` — Vehicle Entry/Exit Parking Tariff Calculation Rules [COMPLETED]**:
  - **Context**: Xác lập quy tắc nghiệp vụ tính cước gửi xe tại barrier check-out cho Task 8 (SRS 4.5.1), đảm bảo tính toán tài chính chính xác tuyệt đối, tránh lỗi dấu phẩy động (floating-point).
  - **Resolution**:
    - Khi phương tiện check-out: Kiểm tra xem phương tiện có vé (`ticket`) đang ở trạng thái `ACTIVE`, chưa bị xóa mềm (`deleted_at IS NULL`), và thời điểm ra nằm trong khoảng hiệu lực (`effective_from <= exit_time < effective_to`). Nếu có, cước phí được miễn giảm hoàn toàn: `fee_amount = Decimal("0.00")`.
    - Khi không có vé hợp lệ hoặc là xe vãng lai (`vehicle_id IS NULL`): Tính thời gian đỗ `duration = exit_time - entry_time`. Số giờ tính phí được làm tròn lên (`ceil(duration_seconds / 3600)`), với mức tối thiểu là `1` giờ. Cước phí bằng số giờ tính phí nhân với đơn giá giờ đọc từ cấu hình hệ thống (`PARKING_HOURLY_RATE_VND`, mặc định `Decimal("10000.00")`), làm tròn chính xác `Decimal("0.01")` kiểu `NUMERIC(12,2)`.
    - Bắt buộc sử dụng kiểu dữ liệu `Decimal`, tuyệt đối không dùng `float`.
- **`TL-51` — Scan API Response Contract & Character Corrections [COMPLETED]**:
  - **Context**: Chuẩn hóa cấu trúc phản hồi của API nhận diện biển số (`POST /api/v1/parking/plate-scans/`) nhằm minh bạch giữa kết quả đọc thô của mô hình OCR và kết quả sau khi áp dụng bộ quy chuẩn ký tự vị trí (position-aware rules), đồng thời bảo toàn tính tương thích ngược cho frontend và các dịch vụ downstream.
  - **Resolution**:
    - Bổ sung 2 trường cấp cao nhất: `plate_raw` (chuỗi chuẩn hóa từ kết quả đọc thô ban đầu của OCR ensemble) và `plate_final` (biển số đề xuất sau khi áp dụng bộ quy tắc sửa ký tự vị trí). Nếu không có sửa đổi, `plate_final == plate_raw`.
    - Trả về danh sách chi tiết các sửa đổi `corrections: list[dict]`, mỗi phần tử gồm: `{position: int, from: str, to: str, rule: str, reason: str}` (giữ `original_char` và `corrected_char` làm alias tương thích ngược).
    - Đồng bộ `best_candidate` để `best_candidate.plate_normalized = plate_final` và `best_candidate.plate_text = corrected_plate`, đảm bảo client đọc `best_candidate` để check-in luôn trùng khớp với kết quả tra cứu `vehicle_lookup`.
    - Toàn bộ các dịch vụ phụ thuộc gồm `vehicle_lookup`, `suggestions`, và Review Policy đều sử dụng nhất quán `plate_final`.
    - Nguyên tắc sửa lỗi: Đảm bảo 0 broken correct reads; không tự ý sửa đổi nếu kết quả sau khi sửa vẫn là `UNKNOWN_PLATE_PATTERN` hoặc không hợp lệ.

---

## 3. Frontend Screen-to-Database Traceability Summary

All `11` PNG files in `Parking Project` (including the 3 ticket dialogs on `Quản lý vé — Smart Mobility.png`) were audited at full resolution:

> For the comprehensive, element-by-element bidirectional requirements traceability matrix covering all 11 Frontend screens and SRS v4.1 (Sections 4.1–4.8), refer to [`07-fe-srs-traceability.md`](07-fe-srs-traceability.md).

| # | FE File Name | Dimensions | Primary Database Tables & Views |
| :-: | :--- | :---: | :--- |
| `01` | `Khách hàng — Smart Mobility.png` | `1440x911` | `customer`, `ticket`, `v_customer_status_summary`, `v_customer_vehicle_summary` |
| `02` | `Lịch sử ra/vào — Smart Mobility.png` | `1440x911` | `vehicle_entry_exit_log`, `parking_gate`, `parking_slot`, `vehicle`, `payment` |
| `03` | `Main Page.png` | `1278x2065` | `parking_lot`, `parking_floor`, `parking_zone`, `parking_slot`, `system_alert`, `vehicle_entry_exit_log`, `v_slot_occupancy_by_floor`; template copy is `UI only (TL-16)` |
| `04` | `Quản lý nhân viên - Smart mobility.png` | `1470x1299` | `employee`, `position`, `account`, `administrative_province`, `administrative_district`, `administrative_ward` |
| `05a` | `Quản lý vé — Smart Mobility.png` (Main) | `3470x911` | `ticket`, `ticket_type`, `vehicle`, `customer`, `parking_floor`, `parking_zone`, `parking_slot` |
| `05b` | `Quản lý vé — Smart Mobility.png` (`Thêm vé mới`) | `3470x911` | `ticket`, `ticket_type`, `vehicle`, `customer`, `parking_slot`, `payment` |
| `05c` | `Quản lý vé — Smart Mobility.png` (`Gia hạn vé`) | `3470x911` | `ticket`, `ticket_renewal`, `ticket_type`, `parking_slot`, `payment` |
| `05d` | `Quản lý vé — Smart Mobility.png` (`Chi tiết vé`) | `3470x911` | `ticket`, `ticket_renewal`, `ticket_type`, `vehicle`, `customer`, `parking_slot`, `employee` |
| `06` | `Quản lý xe — Smart Mobility.png` | `1470x1580` | `vehicle`, `vehicle_type`, `customer`, `ticket`, `ticket_type`, `parking_zone`, `parking_floor`, `parking_slot`, `vehicle_entry_exit_log`, `v_customer_vehicle_summary` |
| `07` | `Sơ đồ bãi đậu xe — Smart Mobility.png` | `1440x1750` | `parking_lot`, `parking_floor`, `parking_zone`, `parking_slot`, `slot_allowed_vehicle_type`, `slot_reservation`, `vehicle_entry_exit_log`, `activity_log`, `v_slot_occupancy_by_floor` |
| `08` | `Trang chủ — Smart Mobility.png` | `1440x911` | `v_slot_occupancy_by_floor`, `v_revenue_today_by_method`, `v_traffic_by_hour`, `v_ai_recognition_stats`, `system_alert`, `plate_blacklist`, `vehicle_entry_exit_log`, `parking_gate` |
| `09` | `Vector.png` | `17x17` | UI action/delete icon asset (`UI only (TL-16)`) |
| `10` | `clarity_edit-line.png` | `18x18` | UI pencil/edit icon asset (`UI only (TL-16)`) |
| `11` | `login-container.png` | `1200x693` | `account` (`email`, `phone`, `password_hash`, `role`), `persistent_login_token`, `password_reset_token`, `customer` |

---

## 4. Schema v1 to Schema v2 Delta Summary

### 4.1. Catalog Counts Comparison

| Catalog Metric | Schema v1 | Schema v2 (Rounds 23–28) | Delta |
| :--- | :---: | :---: | :---: |
| Base tables (`public`) | `19` | `28` | `+9` |
| Views (`public`) | `4` | `8` | `+4` |
| Foreign keys (`contype = 'f'`) | `44` | `69` | `+25` |
| Non-`RESTRICT` FKs (`confdeltype <> 'r'`) | `0` | `0` | `0` |
| User triggers (`NOT tgisinternal`) | `14` | `87` | `+73` |
| Trigger functions (`RETURNS TRIGGER`) | `5` | `15` | `+10` |
| Non-trigger user SQL/PLpgSQL functions | `5` | `7` | `+2` |
| Base table columns | `213` | `338` | `+125` |
| View columns | `22` | `55` | `+33` |
| Total columns (tables + views) | `235` | `393` | `+158` |
| Undocumented tables / views / columns | `0` | `0` | `0` |

### 4.2. New & Reworked Database Objects

1. **9 New Base Tables**:
   - `parking_lot`, `parking_floor`, `parking_zone` (`TL-02`)
   - `slot_reservation` (`TL-04`)
   - `parking_gate` (`TL-06`)
   - `payment` (`TL-07`)
   - `plate_blacklist` (`TL-08`)
   - `activity_log` (`TL-12`)
   - `system_alert` (`TL-13`)
2. **4 New Views**:
   - `v_revenue_today_by_method` (`TL-07`, `TL-14`)
   - `v_traffic_by_hour` (`TL-14`)
   - `v_ai_recognition_stats` (`TL-06`, `TL-14`)
   - `v_customer_status_summary` (`TL-08`)
3. **10 Modified Base Tables**:
   - `account` (`email`/`phone` login identifiers replacing `username`, case-insensitive `uq_account_email_active` on `lower(email)`, `TL-01`, `TL-21`)
   - `position` (seeded with 4 FE positions: `QL`, `NVVH`, `NVTN`, `KTV`, `TL-11`)
   - `employee` (`code ~ '^NV[0-9]{3,4}$'`, `status IN ('ACTIVE', 'INACTIVE')`, optional `date_of_birth`/`gender`/`identity_card_number`/`address` with `uq_employee_idcard_active` and `uq_employee_email_active` on `lower(email)`, `TL-11`, `TL-18`, `TL-21`)
   - `customer` (`status IN ('ACTIVE', 'SUSPENDED', 'BLACKLISTED')`, `status_reason`, optional `date_of_birth`/`gender`/`email`/`address` with `uq_customer_email_active` on `lower(email)`, `TL-08`, `TL-18`, `TL-21`)
   - `vehicle_type` (seeded with car-only types `CAR`, `EV`, `TL-09`, `TL-20`)
   - `ticket_type` (seeded with `DAILY`, `MONTHLY`, `QUARTERLY`, `YEARLY`, `TL-10`)
   - `vehicle` (`image_url TEXT NULL`, `notes TEXT NULL`, `TL-09`)
   - `parking_slot` (`zone_id`, `code VARCHAR(20)`, `slot_kind`, `status` adds `'CHARGING'`, `notes TEXT NULL`, retained `map_row`/`map_col` & `width`/`length`/`height`, `TL-02`, `TL-03`)
   - `ticket` (`status` adds `'RENEWING'`, `notes TEXT NULL`, `TL-10`) and `ticket_renewal` (`notes TEXT NULL`, `TL-10`)
   - `vehicle_entry_exit_log` (`session_code`, `vehicle_id NULL` with `TL-17` visitor plate auto-link, `entry_gate_id`, `exit_gate_id`, `ai_confidence`, `recognition_source`, `review_status`, `fee_amount`, `TL-05`, `TL-06`, `TL-17`)
4. **ERD Alignment (Round 24)**:
   - The Astah UML model ([`db/03-erd.asta`](../../db/03-erd.asta)) and exported diagrams ([`db/04-erd.png`](../../db/04-erd.png)–[`db/09-erd-reference-views.png`](../../db/09-erd-reference-views.png)) are regenerated in Round 24 to match Schema v2 (`28` tables, `8` views, `69` FKs, `338` table attributes + `55` view attributes = `393` total attributes).
