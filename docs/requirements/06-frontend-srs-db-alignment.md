# Frontend-First Specification & Database Schema v2 Decision Record

This document records the authoritative **Frontend-First (`FE-First`)** specification hierarchy established in Rounds 23–25, the **Team Lead Decisions (`TL-01`–`TL-22`)** (which supersede the earlier `D1`–`D8` defaults), the **11-file Frontend-to-Database traceability summary**, and the **Schema v2 catalog delta** implemented in [`db/01-schema.sql`](../../db/01-schema.sql) and [`db/02-seed.sql`](../../db/02-seed.sql).

---

## 1. Source Hierarchy & Governance

1. **Primary Source — Frontend Design (`FE`)**: The 11 exported UI files in `Parking Project` (verified byte-for-byte identical against `Parking Project.zip`) are the primary specification for screens, fields, labels, status badges, filters, and workflows.
2. **Secondary Source — SRS v4.1 (`SRS`)**: `Quan ly bai dau xe oto_SRS_v4.1.docx` (cataloged in [`00-srs-catalog.md`](00-srs-catalog.md) and [`03-delete-rules-catalog.md`](03-delete-rules-catalog.md)) is authoritative for the SRS content and secondary to the Frontend design, governing only where the Frontend is silent (`TL-15`, `TL-19`).
3. **Tertiary Source — Explicit Proposals (`[PROPOSAL]`)**: Any status code, tariff rule, or database guard message not explicitly shown in either the Frontend or the SRS is tagged `[PROPOSAL]` and recorded in [`01-decision-log.md`](01-decision-log.md) and [`05-proposed-messages.md`](05-proposed-messages.md). The **Team Lead** decides all requirement and schema questions (`TL-19`, `TL-22`).

---

## 2. Team Lead Decisions (`TL-01`–`TL-22`)

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

### 2.2. Detailed Decision Specifications

- **`TL-01` — Login & Account**:
  - **FE Evidence**: `login-container.png` labels the login input `"Email hoặc Số điện thoại"`, includes `"Ghi nhớ đăng nhập"`, `"Quên mật khẩu?"`, and `"Chưa có tài khoản? Đăng ký ngay"`.
  - **Resolution**: Replaced `account.username` with `email VARCHAR(100) NULL` and `phone VARCHAR(15) NULL`, enforced `ck_account_login_identifier_present CHECK (num_nonnulls(email, phone) >= 1)`, `ck_account_email_format`, `ck_account_phone_digits CHECK (phone IS NULL OR phone ~ '^[0-9]{9,15}$')`, and active partial unique indexes `uq_account_email_active` (`lower(email)`, `TL-21`) and `uq_account_phone_active` (`phone`). Kept `role IN ('MANAGER', 'EMPLOYEE', 'CUSTOMER')` so self-registration creates a `CUSTOMER` account + `customer` profile. Retained `persistent_login_token` and `password_reset_token`.
- **`TL-02` — Parking Structure (Lot -> Floor -> Zone -> Slot)**:
  - **FE Evidence**: `Sơ đồ bãi đậu xe — Smart Mobility.png` (`"Bãi đỗ xe: Bãi xe Smart Mobility"`, `"+ Thêm tầng"`, `"+ Thêm khu"`, `"+ Thêm ô đỗ xe"`, `"Quản lý cấu trúc bãi"`, `"Tầng B1"`, `"Tầng B2"`, `"Tầng F1"`, `"Khu A"`, `"Khu B"`, `"Khu C"`, slots `"A-01"`..`"A-08"`, `"B-01"`..`"B-08"`), `Trang chủ — Smart Mobility.png` (`"Tầng B1"`, `"Tầng B2"`, `"Tầng B3"`), `Quản lý vé — Smart Mobility.png` (`"Tầng B1 - A10"`, `"Tầng B2 - B12"`, `"Tầng B1 - C03"`, `"Tầng B3 - A01"`), and `Quản lý xe — Smart Mobility.png` (`"Khu A · Tầng 2 · Slot 42"`).
  - **Resolution**: Added `parking_lot` (`code`, `name`, `address`, `is_active`), `parking_floor` (`lot_id`, `code VARCHAR(20)`, `name VARCHAR(50)`, `sort_order`, `uq_parking_floor_lot_code_active`), and `parking_zone` (`floor_id`, `code VARCHAR(20)`, `name VARCHAR(50)`, `description`, `uq_parking_zone_floor_code_active`). Updated `parking_slot` to reference `zone_id` via `fk_slot_zone FOREIGN KEY (zone_id) REFERENCES parking_zone (id) ON DELETE RESTRICT`, `code VARCHAR(20)` (`ck_slot_code_format`, `uq_parking_slot_zone_code_active`), and retained `map_row`, `map_col` (`uq_parking_slot_zone_map_pos_active`), `width`, `length`, and `height`.
- **`TL-03` — Slot Types, EV Charging & Statuses**:
  - **FE Evidence**: `Main Page.png` (`"Chỗ trống (Available)"`, `"Đã đỗ xe (Occupied)"`, `"Đã đặt trước (Reserved)"`, `"Sạc xe điện (EV Charging)"`, `"Bảo trì / Tạm khóa"`), `Sơ đồ bãi đậu xe — Smart Mobility.png` (`"DÃY A1 - A08 (XE Ô TÔ TIÊU CHUẨN)"`, `"DÃY B1 - B08 (XE ƯU TIÊN)"`, `"CẢM BIẾN SIÊU ÂM ACTIVE"`, `"Trống (Available)"`, `"Có xe (Occupied)"`, `"Đặt trước (Reserved)"`, `"BẢO TRÌ"`, and manual buttons `"Đánh dấu trống"`, `"Đánh dấu có xe"`, `"Đánh dấu đặt trước"`, `"Đánh dấu bảo trì"`).
  - **Resolution**: Added `slot_kind VARCHAR(20) NOT NULL DEFAULT 'STANDARD'` (`ck_slot_kind_enum CHECK (slot_kind IN ('STANDARD', 'PRIORITY', 'EV_CHARGING'))`), `status IN ('AVAILABLE', 'OCCUPIED', 'RESERVED', 'CHARGING', 'MAINTENANCE')` (`ck_slot_status_enum`), `ck_slot_charging_requires_ev_kind CHECK (status <> 'CHARGING' OR slot_kind = 'EV_CHARGING')`, and `notes TEXT NULL` on `parking_slot`. Slot statuses are synchronized by `fn_recompute_parking_slot_status()` while `fn_guard_parking_slot_status()` blocks manual status changes that contradict open sessions or active tickets/reservations (`PROP-4.5.2-P02`..`P04`, `OQ-81`).
- **`TL-04` — Slot Reservation (`Đặt trước`)**:
  - **FE Evidence**: `Sơ đồ bãi đậu xe — Smart Mobility.png` shows `"Đặt trước / Bảo trì"`, `"A-04 ĐÃ ĐẶT 13:30"`, `"A-05 ĐÃ ĐẶT 14:30"`, `"B-07 ĐÃ ĐẶT 15:00"`, `"Người đặt trước"`, and `"Đánh dấu đặt trước"`.
  - **Resolution**: Added `slot_reservation` (`code`, `slot_id`, `customer_id NULL`, `vehicle_id NULL`, `reserved_name`, `reserved_phone`, `reserved_from`, `reserved_until`, `status IN ('ACTIVE', 'COMPLETED', 'CANCELLED', 'EXPIRED')` `[PROPOSAL]` `OQ-81`, `notes`, `created_by`, soft-delete + `version`) with GiST exclusion constraint `excl_reservation_slot_time_overlap` (`tstzrange(reserved_from, reserved_until, '[)') WHERE (deleted_at IS NULL AND status = 'ACTIVE')`), `fn_guard_slot_reservation_write()`, `fn_sync_slot_status_on_reservation()`, and conflict check in `fn_guard_slot_reservation_on_entry()` (`PROP-4.5.2-P05`, `OQ-81`).
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
  - **Resolution**: Seeded `ticket_type` with 4 rows (`DAILY` `"Vé ngày"` `1` day `50000.00`, `MONTHLY` `"Vé tháng"` `30` days `500000.00`, `QUARTERLY` `"Vé quý"` `90` days `1200000.00`, `YEARLY` `"Vé năm"` `365` days `4800000.00` `[PROPOSAL]` `OQ-79`). Updated `ck_ticket_status_enum` to `('ACTIVE', 'RENEWING', 'RENEWED', 'EXPIRED', 'CANCELLED')`; `"Sắp hết hạn"` is derived when `status = 'ACTIVE' AND effective_to <= CURRENT_TIMESTAMP + INTERVAL '7 days'`. Added `notes TEXT NULL` on `ticket` and `ticket_renewal`. Kept `ck_ticket_time_order CHECK (effective_to > effective_from)` (1-day tickets stored as `[effective_from, effective_from + INTERVAL '1 day')`).
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
  - **Resolution**: Updated `v_slot_occupancy_by_floor` (grouping by `parking_lot`, `parking_floor`, and `parking_zone` with `occupied_slots`, `reserved_slots`, `charging_slots`, `available_slots`, `maintenance_slots`, `priority_slots`, `ev_charging_slots`, and `occupancy_rate_pct`) and added `v_revenue_today_by_method`, `v_traffic_by_hour`, and `v_ai_recognition_stats`.
- **`TL-15` — Keep SRS Rules Where FE Is Silent**:
  - **Resolution**: Preserved 3-level administrative address hierarchy (`administrative_province`, `administrative_district`, `administrative_ward` with composite FKs on `employee` and `customer`), `date_of_birth`, `gender IN ('Nam', 'Nữ')`, `identity_card_number`, `news`, `notification`, `v_customer_vehicle_summary`, `v_vehicle_traffic_daily`, `v_revenue_statistics`, `fn_stat_*` functions, `version` OCC triggers, soft-delete columns (`deleted_at`, `deleted_by`), and `ON DELETE RESTRICT` across all `69` foreign keys.
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

---

## 3. Frontend Screen-to-Database Traceability Summary

All `11` PNG files in `Parking Project` (including the 3 ticket dialogs on `Quản lý vé — Smart Mobility.png`) were audited at full resolution:

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

| Catalog Metric | Schema v1 | Schema v2 (Rounds 23–25) | Delta |
| :--- | :---: | :---: | :---: |
| Base tables (`public`) | `19` | `28` | `+9` |
| Views (`public`) | `4` | `8` | `+4` |
| Foreign keys (`contype = 'f'`) | `44` | `69` | `+25` |
| Non-`RESTRICT` FKs (`confdeltype <> 'r'`) | `0` | `0` | `0` |
| User triggers (`NOT tgisinternal`) | `14` | `25` | `+11` |
| Trigger functions (`RETURNS TRIGGER`) | `5` | `9` | `+4` |
| Non-trigger user SQL/PLpgSQL functions | `5` | `6` | `+1` |
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
