# Delete Rules & Destructive Operations Catalog

This document specifies all deletion flows (Delete Flows) and cancellation/reset actions (Cancel/Reset) across the Car Parking Lot Management System per the canonical SRS v4.1 specification. It defines business guard rules, foreign key referential integrity controls (`models.PROTECT`), role-based access control (RBAC), concurrency locking mechanisms (`select_for_update`), audit trail logging, verbatim SRS error messages, and financial statistics preservation impacts (SRS 4.7).

It also integrates statutory Vietnamese privacy compliance requirements under **Decree No. 13/2023/ND-CP** (Personal Data Protection) and **Accounting Law No. 88/2015/QH13**.

---

## 1. Core Principles Governing Data Deletion (`TL-23`–`TL-27`)

1. **Soft Delete by Default (`TL-23`)**:
   - All `18` soft-deletable domain tables (`account`, `position`, `employee`, `customer`, `plate_blacklist`, `vehicle_type`, `ticket_type`, `vehicle`, `parking_lot`, `parking_floor`, `parking_zone`, `parking_slot`, `slot_reservation`, `ticket`, `payment`, `news`, `notification`, `parking_gate`) enforce soft deletion via `deleted_at TIMESTAMPTZ NULL` and `deleted_by BIGINT NULL` with `ck_<table_short>_soft_delete_pair CHECK (deleted_by IS NULL OR deleted_at IS NOT NULL)`.
   - The 16/10/2026 team meeting's `isDeleted` flag is exposed at the API/serializer layer (`deleted_at is not None`); no redundant boolean column is stored in PostgreSQL (`TL-23`).
   - Restoring a row sets `deleted_at = NULL`, and the `BEFORE UPDATE OF deleted_at` trigger `fn_guard_soft_delete_and_restore()` automatically clears `NEW.deleted_by := NULL` while verifying all parent FKs are active (`TL-23`, `TL-26`).
   - Default querysets (`models.Manager` / `models.QuerySet`) and every list, detail, create, and update endpoint always filter `WHERE deleted_at IS NULL` (`TL-27`). Explicit query methods (`all_with_deleted()`, `only_deleted()`) are provided for Trash (`Thùng rác`) and compliance audits.
2. **Prohibition of Plain `DELETE` & Hardened Controlled Purge (`TL-24`, `TL-36`, `TL-37`, `TL-40`)**:
   - Plain `DELETE` is blocked on 25 base tables in `db/01-schema.sql`: 16 purgeable tables use `fn_guard_prevent_plain_delete()`, 8 immutable/financial tables use `fn_guard_hard_immutable_table()`, and `activity_log` uses `fn_prevent_activity_log_mutation()`.
   - *Plain DELETE Exceptions (TL-36, TL-37)*: Exactly 3 tables permit plain `DELETE`: `persistent_login_token` and `password_reset_token` (for token rotation, logout, and credential revocation per TL-36), and junction table `slot_allowed_vehicle_type` (for dynamic slot vehicle-type reconfiguration per TL-37, guarded by `trg_guard_slot_allowed_vehicle_type_delete` which blocks removing a type currently used by active tickets, open sessions, or active reservations with error `PROP-DEL-SAVT-IN-USE`).
   - Permanent trash cleanup is restricted exclusively to `fn_controlled_purge(p_table_name varchar, p_retention interval, p_dry_run boolean, p_purged_by bigint, p_target_id bigint)` (`SECURITY DEFINER`, `SET search_path = public, pg_temp`, `p_dry_run BOOLEAN DEFAULT TRUE`), returning `TABLE(table_name varchar, eligible_count bigint, purged_count bigint, status varchar, details text)`.
   - *30-Day Retention Floor & Batch FK Skip (TL-40)*: Enforces `p_retention >= INTERVAL '30 days'` (lower intervals rejected with SQLSTATE `22023`). In batch mode (`p_target_id IS NULL`), catches referential integrity exceptions (`foreign_key_violation` 23503, `restrict_violation` 23001) per row to skip referenced trash records and purge eligible rows. When purging an `account`, linked tokens are cleaned in the same subtransaction before deleting the account (TL-36).
3. **Data Classes That Must Never Be Hard-Deleted or Purged (`TL-24`, `TL-39`, `TL-42`)**:
   - **Fiscal Vouchers & Renewals (`ticket`, `ticket_renewal`, `payment`)**: Accounting vouchers substantiating parking revenue under Accounting Law No. 88/2015/QH13.
   - *Payment Soft-Delete Guard (TL-39)*: Soft-delete is strictly blocked for any `payment` record with `status IN ('PAID', 'REFUNDED')` with exception `PROP-DEL-PAYMENT-SETTLED`. Soft-delete is only allowed on `UNPAID` or `CANCELLED` payments to safeguard financial revenue reporting.
   - *Payment Status Transition & Immutability Guard (TL-42)*: Enforces valid status transitions on `payment` (`UNPAID -> PAID | CANCELLED`; `PAID -> REFUNDED` only; `REFUNDED` and `CANCELLED` are terminal; no transition back to `UNPAID`; `PROP-PAY-STATUS-TRANSITION`). When a payment is settled (`PAID`, `REFUNDED`), financial and relational link columns (`amount`, `method`, `paid_at`, `session_id`, `ticket_id`, `renewal_id`, `code`) are strictly immutable (`PROP-PAY-SETTLED-IMMUTABLE`), preventing any backdoor modification of revenue or links. Only harmless metadata edits (`notes`) are permitted.
   - **Movement & Security Logs (`vehicle_entry_exit_log`, `activity_log`, `system_alert`)**: Physical gate access records and append-only audit trails (`SOFT_DELETE`, `RESTORE`, `PURGE` logged by `fn_audit_soft_delete_and_restore()` and `fn_controlled_purge()`).
   - **System Lookup Tables (`administrative_province`, `administrative_district`, `administrative_ward`)**.
4. **Foreign Key Integrity (`ON DELETE RESTRICT` / `on_delete=models.PROTECT`) & Database Soft-Delete Guards (`TL-25`)**:
   - All `69` foreign keys in `db/01-schema.sql` enforce `ON DELETE RESTRICT` (`0` `CASCADE` / `SET NULL`).
   - Because `ON DELETE RESTRICT` only guards physical `DELETE`, `db/01-schema.sql` enforces `DEL-01`–`DEL-06` directly in the database via `BEFORE UPDATE OF deleted_at` triggers calling `fn_guard_soft_delete_and_restore()` (`TL-25`).

---

## 2. Detailed Catalog of Deletion Flows in SRS v4.1

### 2.1. Flow DEL-01: Employee & Account Deletion (`employee`, `account`)

- **Stable Source Citations**:
  - SRS Section 4.3.1, Employee Management Table, Action row `Xóa` (Item 12, Action 24).
  - SRS Section 4.3.4, Delete Employee Information Table, Confirmation row `Xác nhận` (Item 6, Action 10), Cancellation row `Hủy` (Item 7, Action 11).
  - Wireframes: `image4.png`, `image7.png`; Frontend: `Danh sách nhân viên.png`.
- **Access Control (RBAC)**: Restricted strictly to **Manager (`MANAGER`)** (SRS 4.2 Row 7; SRS 4.3.1 Row 1).
- **Operation Type**: **Soft Delete** (`deleted_at`, `deleted_by`) guarded by `trg_guard_soft_delete_and_restore_employee` and `trg_guard_soft_delete_and_restore_account`.
- **Domain & Database Guard Rules (`fn_guard_soft_delete_and_restore`, `TL-25`)**:
  1. `[PROPOSAL]` *Self-Deletion Guard* (`OQ-10`, `PROP-DEL-01-SELF`, `PROP-DEL-01-SELF-EMP`): Rejects soft delete when `NEW.deleted_by = OLD.id` on `account` or `NEW.deleted_by = OLD.account_id` on `employee`.
  2. `[PROPOSAL]` *Last Active Manager Safeguard* (`OQ-10`, `PROP-DEL-01-LAST-MGR`, `PROP-DEL-01-LAST-MGR-EMP`): Rejects soft delete if the target `account` (or the `account` linked to `employee`) is the last active `MANAGER` (`role = 'MANAGER' AND is_active = TRUE AND deleted_at IS NULL`).
  3. `[PROPOSAL]` *Referential Integrity Guard (`ON DELETE RESTRICT`)* (`OQ-10`): Physical purge blocked when linked to historical records (`ticket.created_by_id`, `news.author_id`); soft deletion preserves foreign key relationships cleanly.
- **Concurrency & Error Messages**:
  - Pessimistic locking via `select_for_update()` inside `transaction.atomic()` and OCC via `row_version`.
  - Not found / already deleted (HTTP 404): `Dữ liệu không tồn tại` (`MSG-4.3.4-M02`) or `Kết nối cơ sở dữ liệu hoặc thông tin không tồn tại` (`MSG-4.3.1-M02`).
  - Connectivity failure (HTTP 500): `Lỗi kết nối server` (`MSG-4.3.4-M03`).
- **Verbatim Success Message**: `Xóa thành công` (`MSG-4.3.1-M01`, `MSG-4.3.4-M01`).
- **Audit Trail**: `trg_audit_soft_delete_and_restore_employee` and `trg_audit_soft_delete_and_restore_account` append `action = 'SOFT_DELETE'` / `'RESTORE'` to `activity_log` (`TL-26`).

---

### 2.2. Flow DEL-02: Customer Deletion (`customer`)

- **Stable Source Citations**:
  - SRS Section 4.4.1, Customer List Table, Action row `xóa` (Item 12, Action 31).
  - SRS Section 4.4.5, Delete Customer Notice Table, Dialog row `Thông báo xóa khách hàng` (Item 5), Confirmation row `Xác nhận` (Item 6), Cancellation row `Hủy` (Item 7).
  - Wireframes: `image8.png`, `image12.png`; Frontend: `Danh sách khách hàng.png`.
- **Access Control (RBAC)**: **Manager (`MANAGER`)** and **Employee (`EMPLOYEE`)**.
- **Operation Type**: **Soft Delete** (`deleted_at`, `deleted_by`) guarded by `trg_guard_soft_delete_and_restore_customer`.
- **Domain & Database Guard Rules (`fn_guard_soft_delete_and_restore`, `TL-25`)**:
  1. `[PROPOSAL]` *Parked Vehicle Guard* (`OQ-15`, `OQ-40`, `PROP-4.4.5-P02`): Rejects soft delete if the customer owns any vehicle with an open parking session (`vehicle_entry_exit_log.exit_time IS NULL`).
  2. `[PROPOSAL]` *Active Ticket Guard* (`OQ-15`, `OQ-40`, `PROP-4.4.5-P03`): Rejects soft delete if the customer holds any active unexpired ticket (`deleted_at IS NULL AND status IN ('ACTIVE', 'RENEWING') AND effective_to > CURRENT_TIMESTAMP`).
  3. `[PROPOSAL]` *Active Registered Vehicle Guard* (`OQ-40`, `TL-25`, `PROP-DEL-02-ACTIVE-VEH`): Rejects soft delete if the customer still has active vehicles (`vehicle.deleted_at IS NULL`).
- **Concurrency & Error Messages**:
  - Verbatim success message: `Xóa thành công` (`MSG-4.4.5-M01`).
  - Concurrent deletion (HTTP 409): `Dữ liệu đang được xóa bởi người dùng khác` (`MSG-4.4.5-M02`).
  - Server error (HTTP 500): `Lỗi server` (`MSG-4.4.5-M03`).
  - Not found (HTTP 404): `Khách hàng không tồn tại hoặc đã bị xóa.` (`PROP-4.4.5-P01`).
- **Audit Trail & PII Handling**: Appends `SOFT_DELETE` to `activity_log` (`TL-26`); physical purge via `fn_controlled_purge()` additionally requires `is_anonymized = TRUE` per Decree 13/2023/ND-CP (`TL-24`).

---

### 2.3. Flow DEL-03: Vehicle Deletion (`vehicle`)

- **Stable Source Citations**:
  - SRS Section 4.4.3, Add Customer Table, Action row `Xóa` (Item 9, Action 23).
  - SRS Section 4.4.4, Edit Customer Table, Action row `Xóa` (Item 10, Action 26).
  - Wireframes: `image10.png`, `image11.png`; Frontend: `Quản lý phương tiện.png`.
- **Access Control (RBAC)**: **Manager (`MANAGER`)** and **Employee (`EMPLOYEE`)**.
- **Operation Type**: **Soft Delete** (`deleted_at`, `deleted_by`) guarded by `trg_guard_soft_delete_and_restore_vehicle`.
- **Domain & Database Guard Rules (`fn_guard_soft_delete_and_restore`, `TL-25`)**:
  1. `[PROPOSAL]` *Open Parking Session Guard* (`OQ-41`, `PROP-DEL-03-OPEN-SES`): Rejects soft delete if the vehicle has an open parking session (`vehicle_entry_exit_log.exit_time IS NULL`).
  2. `[PROPOSAL]` *Active Ticket Guard* (`OQ-41`, `PROP-DEL-03-ACTIVE-TKT`): Rejects soft delete if the vehicle holds an active unexpired ticket (`status IN ('ACTIVE', 'RENEWING') AND effective_to > CURRENT_TIMESTAMP`).
  3. `[PROPOSAL]` *Active Slot Reservation Guard* (`TL-25`, `PROP-DEL-03-ACTIVE-RSV`): Rejects soft delete if the vehicle has an active advance reservation (`slot_reservation.status = 'ACTIVE' AND reserved_until > CURRENT_TIMESTAMP`).
- **Error Responses**: On system failure, returns HTTP 500 with verbatim SRS message `Lỗi hệ thống` (`MSG-4.4.4-M03`).

---

### 2.4. Flow DEL-04: Parking Ticket Deletion (`ticket`)

- **Stable Source Citations**:
  - SRS Section 4.6.1, Ticket List Table, Action column `Icon Xóa` (Item 10, Action 30).
  - SRS Section 4.6.4, Confirm Ticket Deletion Table, Confirmation button `Yes` (Item 6, Action 12), Cancellation button `No` (Item 7, Action 13).
  - Wireframe: `image18.png`; Frontend: `Quản lý thông tin vé - Danh sách vé.png`.
- **Access Control (RBAC)**: **Manager-only (`MANAGER`)** (`OQ-39`).
- **Operation Type**: **Soft Delete** (`deleted_at`, `deleted_by`) guarded by `trg_guard_soft_delete_and_restore_ticket` and `ck_ticket_delete_only_expired`.
- **Domain & Database Guard Rules (`fn_guard_soft_delete_and_restore`, `TL-25`)**:
  1. *Active Unexpired Guard* (`CASE-4.6.4-TH1`, `OQ-18`, `PROP-4.6.4-P01`, `ck_ticket_delete_only_expired`): Rejects soft delete when `effective_to > CURRENT_TIMESTAMP` and `status IN ('ACTIVE', 'RENEWING')` (`Vé chưa hết hạn, không được phép xóa.`).
  2. *Renewed Ticket Guard* (`CASE-4.6.4-TH1`, `OQ-18`, `PROP-4.6.4-P02`): Rejects soft delete when `status = 'RENEWED'` or rows exist in `ticket_renewal` (`Vé đã được gia hạn, không được phép xóa.`).
  3. `[PROPOSAL]` *Parked Vehicle Guard* (`OQ-42`, `PROP-DEL-04-OPEN-SES`): Rejects soft delete while the linked vehicle or ticket has an open parking session (`exit_time IS NULL`).
- **Concurrency & Error Messages**:
  - Concurrent deletion (`CASE-4.6.4-TH2`, `PROP-4.6.4-P03`): `Vé đang được xử lý bởi người dùng khác, vui lòng thử lại sau.`
  - Connectivity failure (`CASE-4.6.4-TH3`, `PROP-4.6.4-P04`): `Lỗi kết nối cơ sở dữ liệu khi thực hiện xóa vé.`
  - Not found (`PROP-4.6.4-P05`): `Vé không tồn tại hoặc đã bị xóa.`
- **Verbatim Success Message**: `Xóa thành công` (`MSG-4.6.4-M01`).
- **Fiscal Voucher Immutability vs Operational Revenue Statistics (`OQ-11`, `TL-24`, `TL-27`)**:
  - `ticket`, `ticket_renewal`, and `payment` rows are protected by `fn_guard_hard_immutable_table()` and can NEVER be hard-deleted or purged (`TL-24`), preserving 100% of statutory accounting records for audit queries (`all_with_deleted()`).
  - Per `TL-27`, operational statistic views (`v_revenue_statistics`, `v_revenue_today_by_method`) and `fn_stat_revenue_by_period()` consistently filter `WHERE p.deleted_at IS NULL AND (p.ticket_id IS NULL OR t.deleted_at IS NULL)` so soft-deleted rows are excluded from active dashboard statistics.

---

### 2.5. Flow DEL-05: Parking Slot Deletion (`parking_slot`)

- **Stable Source Citations**:
  - SRS Section 4.8.1, Parking Slot List Table, Action column `Xoá` (Item 9).
  - SRS Section 4.8.5, Delete Parking Slot Confirmation Table, Action button `Xóa` (Item 6, Action 9), Cancellation button `Hủy` (Item 7, Action 10).
  - Wireframes: `image21.png`, `image25.png`; Frontend: `Sơ đồ bãi đậu xe.png`.
- **Access Control (RBAC)**: **Manager (`MANAGER`)** (`OQ-03`, `OQ-30`, `OQ-45`).
- **Operation Type**: **Soft Delete** (`deleted_at`, `deleted_by`) guarded by `trg_guard_soft_delete_and_restore_parking_slot`.
- **Domain & Database Guard Rules (`fn_guard_soft_delete_and_restore`, `TL-25`)**:
  1. `[PROPOSAL]` *Occupied / Open Session Guard* (`OQ-31`, `OQ-43`, `PROP-DEL-05-OCCUPIED`): Rejects soft delete when `status IN ('OCCUPIED', 'CHARGING')` or an open session (`exit_time IS NULL`) references `slot_id`.
  2. *Slot Bound to Active Ticket Guard* (`CASE-4.8.5-TH1`, `OQ-31`, `PROP-4.8.5-P02`): Rejects soft delete when an active unexpired ticket references `slot_id` (`Vị trí đỗ xe đang có phương tiện đăng ký vé, không được phép xóa.`).
  3. `[PROPOSAL]` *Active Reservation Guard* (`OQ-43`, `PROP-DEL-05-RESERVED`): Rejects soft delete when an active `slot_reservation` exists or `status = 'RESERVED'`.
- **Impact on Statistics and Parking Map (`TL-27`)**:
  - `v_slot_occupancy_by_floor` and `fn_stat_vehicles_by_floor()` exclude `ps.deleted_at IS NOT NULL`, automatically recalculating active capacity and available slots.

---

### 2.6. Flow DEL-06: Hierarchy & Reference Soft-Delete Guards (`TL-25`) and UI Cancel/Reset Actions (`CAN-01`–`CAN-13`)

#### 2.6.1. Hierarchy & Reference Table Soft-Delete Guards (`fn_guard_soft_delete_and_restore`, `TL-25`)

| Target Table | Guard Trigger | Active Child / Dependency Condition (`BEFORE UPDATE OF deleted_at`) | Proposal ID |
| :--- | :--- | :--- | :---: |
| `parking_lot` | `trg_guard_soft_delete_and_restore_parking_lot` | Rejects soft delete while active `parking_floor` rows (`deleted_at IS NULL`) exist under `lot_id` | **PROP-DEL-06-LOT** |
| `parking_floor` | `trg_guard_soft_delete_and_restore_parking_floor` | Rejects soft delete while active `parking_zone` rows (`deleted_at IS NULL`) exist under `floor_id` | **PROP-DEL-06-FLOOR** |
| `parking_zone` | `trg_guard_soft_delete_and_restore_parking_zone` | Rejects soft delete while active `parking_slot` rows (`deleted_at IS NULL`) exist under `zone_id` | **PROP-DEL-06-ZONE** |
| `ticket_type` | `trg_guard_soft_delete_and_restore_ticket_type` | Rejects soft delete while active unexpired `ticket` rows reference `ticket_type_id` | **PROP-DEL-06-TICKET-TYPE** |
| `position` | `trg_guard_soft_delete_and_restore_position` | Rejects soft delete while active `employee` rows (`deleted_at IS NULL`) reference `position_id` | **PROP-DEL-06-POSITION** |
| `vehicle_type` | `trg_guard_soft_delete_and_restore_vehicle_type` | Rejects soft delete while active `vehicle` rows (`deleted_at IS NULL`) reference `vehicle_type_id` | **PROP-DEL-06-VEHICLE-TYPE** |
| `parking_gate` | `trg_guard_soft_delete_and_restore_parking_gate` | Rejects soft delete while open sessions (`exit_time IS NULL`) reference `entry_gate_id` or `exit_gate_id` | **PROP-DEL-06-GATE** |

#### 2.6.2. UI Cancellation and Rollback Actions (`CAN-01`–`CAN-13`)

| Action Identifier | Operation | Stable Source Citation | Technical Behavior | Data Impact Scope |
| :---: | :--- | :--- | :--- | :--- |
| **CAN-01** | **Reset Login** | SRS 4.1, Login Table, Action 12 (`Reset`) | Clears client form inputs for username and password. | Client-side only. Zero backend requests dispatched. |
| **CAN-02** | **Cancel Add Employee** | SRS 4.3.2, Add Employee Table, Action 19 (`Hủy`) | Resets modal form inputs to initial clean state. Closes modal. | Client-side only. Zero database persistence. |
| **CAN-03** | **Cancel Edit Employee** | SRS 4.3.3, Edit Employee Table, Action 18 (`Hủy`) | Closes edit popup without submitting changes. | Client-side only. Discards unsubmitted modifications. |
| **CAN-04** | **Cancel Delete Employee** | SRS 4.3.4, Delete Employee Table, Action 11 (`Hủy`) | Aborts deletion dialog and returns to list. | Closes confirmation modal. Zero database mutations. |
| **CAN-05** | **Close Add Customer** | SRS 4.4.3, Add Customer Table, Action 26 (`Đóng`) | Closes customer addition form and returns to list. | Discards uncommitted customer and vehicle rows. |
| **CAN-06** | **Close Edit Customer** | SRS 4.4.4, Edit Customer Table, Action 29 (`Đóng`) | Closes customer modification form. | Discards uncommitted profile modifications. |
| **CAN-07** | **Cancel Delete Customer** | SRS 4.4.5, Delete Customer Table, Item 7 (`Hủy`) | Closes confirmation modal without executing delete. | Customer records remain active and unchanged. |
| **CAN-08** | **Cancel Add Ticket** | SRS 4.6.2, Add Ticket Table, Action 19 (`Hủy`) | Aborts ticket creation form and returns to list. | Aborts ticket record generation. |
| **CAN-09** | **Cancel Ticket Renewal** | SRS 4.6.3, Edit Ticket Table, Action 20 (`Hủy`) | Aborts renewal form and returns to list. | Ticket expiration date remains unchanged. |
| **CAN-10** | **Cancel Delete Ticket** | SRS 4.6.4, Confirm Ticket Delete Table, Item 7 (`No`) | Closes deletion confirmation modal. | Ticket remains active without deletion mutation. |
| **CAN-11** | **Cancel Edit Slot** | SRS 4.8.3, Edit Slot Table, Action 17 (`Hủy`) | Aborts modification form and returns to list. | Slot dimensions and vehicle types remain unchanged. |
| **CAN-12** | **Back from Slot Detail** | SRS 4.8.4, Slot Detail Table, Action 17 (`Quay lại`) | Navigates back to slot list view. | Pure UI routing navigation. |
| **CAN-13** | **Cancel Delete Slot** | SRS 4.8.5, Delete Slot Table, Action 10 (`Hủy`) | Closes deletion modal and returns to list. | Parking slot record remains active. |

---

## 3. Deletion Authorization and Constraints Matrix

| Entity | Deletion Flow ID | Permitted Roles | Domain & Database Guard Rules (`fn_guard_soft_delete_and_restore`) | Database Action | Verbatim SRS & Proposal Error Strings |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **Employee & Account (`employee`, `account`)** | DEL-01 | `MANAGER` | - Cannot self-delete active account/employee (`PROP-DEL-01-SELF`, `PROP-DEL-01-SELF-EMP`).<br>- Cannot delete last active `MANAGER` (`PROP-DEL-01-LAST-MGR`, `PROP-DEL-01-LAST-MGR-EMP`). | Soft delete (`deleted_at`, `deleted_by`) | `Dữ liệu không tồn tại` / `Kết nối cơ sở dữ liệu hoặc thông tin không tồn tại` / `Lỗi kết nối server` |
| **Customer (`customer`)** | DEL-02 | `MANAGER`, `EMPLOYEE` | - No vehicles parked in lot (`PROP-4.4.5-P02`).<br>- No active tickets (`PROP-4.4.5-P03`).<br>- No active registered vehicles (`PROP-DEL-02-ACTIVE-VEH`). | Soft delete (`deleted_at`, `deleted_by`) | `Dữ liệu đang được xóa bởi người dùng khác` / `Lỗi server` |
| **Vehicle (`vehicle`)** | DEL-03 | `MANAGER`, `EMPLOYEE` | - No open parking session (`PROP-DEL-03-OPEN-SES`).<br>- No active ticket (`PROP-DEL-03-ACTIVE-TKT`).<br>- No active reservation (`PROP-DEL-03-ACTIVE-RSV`). | Soft delete (`deleted_at`, `deleted_by`) | `Lỗi hệ thống` |
| **Ticket (`ticket`)** | DEL-04 | `MANAGER` | - Ticket must be expired (`ck_ticket_delete_only_expired`, `PROP-4.6.4-P01`) and non-renewed (`PROP-4.6.4-P02`).<br>- Vehicle has no open session (`PROP-DEL-04-OPEN-SES`). | Soft delete (`deleted_at`, `deleted_by`) | `PROP-4.6.4-P01`..`PROP-4.6.4-P05` |
| **Parking Slot (`parking_slot`)** | DEL-05 | `MANAGER` | - Slot not occupied/charging (`PROP-DEL-05-OCCUPIED`).<br>- Slot not bound to active ticket (`PROP-4.8.5-P02`).<br>- Slot not reserved (`PROP-DEL-05-RESERVED`). | Soft delete (`deleted_at`, `deleted_by`) | `PROP-4.8.5-P02`..`PROP-4.8.5-P05` |
| **Hierarchy & Lookups (`parking_lot`, `parking_floor`, `parking_zone`, `ticket_type`, `position`, `vehicle_type`, `parking_gate`)** | DEL-06 | `MANAGER` | - No active child floors/zones/slots, active tickets, active employees, active vehicles, or open gate sessions (`TL-25`). | Soft delete (`deleted_at`, `deleted_by`) | `PROP-DEL-06-LOT`..`PROP-DEL-06-GATE` |
| **Payment (`payment`)** | DEL-07 (`TL-39`) | `MANAGER` | - Cannot soft-delete if `status IN ('PAID', 'REFUNDED')` (`PROP-DEL-PAYMENT-SETTLED`, `TL-39`). Permitted only for `UNPAID` or `CANCELLED`. | Soft delete (`deleted_at`, `deleted_by`) | `PROP-DEL-PAYMENT-SETTLED`: Không thể xóa giao dịch thanh toán đã hoàn thành (PAID) hoặc đã hoàn tiền (REFUNDED). |
| **Slot Allowed Vehicle Type (`slot_allowed_vehicle_type`)** | `TL-37` | `MANAGER` | - Cannot plain-delete type if slot currently has active tickets, open sessions, or active reservations using this type (`PROP-DEL-SAVT-IN-USE`, `TL-37`). | Plain DELETE | `PROP-DEL-SAVT-IN-USE`: Không thể xóa loại xe khỏi vị trí đỗ khi đang có vé, phiên đỗ hoặc đặt chỗ hiệu lực. |
| **Authentication Tokens (`persistent_login_token`, `password_reset_token`)** | `TL-36` | `SYSTEM`, `AUTHENTICATED` | - Permitted plain `DELETE` for session rotation, user logout, and token revocation (`TL-36`). Auto-cleaned during account purge. | Plain DELETE | N/A (Standard token lifecycle) |

---

## 4. Legal Compliance Analysis: Decree 13/2023/ND-CP

### 4.1. Official Legal Foundation

- **Statute**: **Decree No. 13/2023/ND-CP** dated 17/04/2023 of the Government of Vietnam on Personal Data Protection (effective from 01/07/2023).
- **Verified Official Sources**:
  - Government Web Portal: <https://vanban.chinhphu.vn/?pageid=27160&docid=207705> (Accessed: 2026-10-11).
  - National Legal Database: <https://vbpl.vn/bocongan/Pages/vbpq-van-ban-goc.aspx?ItemID=160246> (Accessed: 2026-10-11).
- **Associated Statute**: **Accounting Law No. 88/2015/QH13** dated 20/11/2015 (Article 41 regarding statutory retention periods for financial vouchers).

### 4.2. Personal Data Collected by the Car Parking Lot System

Per canonical SRS v4.1, the system processes:

1. *Basic Personal Data (Article 2 Clause 3)*:
   - Full name (`HoTenNV`, `HoTenKH` -> `full_name`).
   - Date of birth (`NgaySinhNV`, `NgaySinhKH` -> `date_of_birth`).
   - Gender (`SexNV`, `SexKH` -> `gender`).
   - Telephone number (`SDT_NV`, `SDTKH` -> `phone`).
   - Address (`DiaChiNV`, `DiaChiKH` -> `address`).
   - Email address (`MailNV`, `MailKH` -> `email`).
   - National Identification Number (`CMND` -> `identity_card_number`).
   - Vehicle license plate and registration data (`BienSoXe` -> `license_plate`, `license_plate_norm`).
2. *Sensitive Personal Data (Article 2 Clause 4)*:
   - Spatial location and movement tracking data (via automated camera license plate capture with real-time timestamps `entry_time`, `exit_time` at SRS 4.5.1).

### 4.3. Data Subject Rights & Technical Execution Architecture (`OQ-12`, `TL-24`)

1. **Right to Withdraw Consent & Right to Erasure (Articles 9 & 16)**:
   - Upon receipt of a valid erasure request, the data controller must complete personal data erasure within **72 hours** (Article 16 Clause 5), subject to statutory accounting retention exceptions (Article 16 Clause 2 Points a & d; Accounting Law 2015).
2. **Database & Backend Anonymization Pattern (`OQ-12`, `ck_customer_anonymized_pair`, `fn_controlled_purge`)**:
   - Soft-delete the `customer` record (`deleted_at`, `deleted_by`) and irreversibly anonymize PII fields while setting `is_anonymized = TRUE` and `anonymized_at = timezone.now()` (enforced by `ck_customer_anonymized_pair`).
   - `fn_controlled_purge()` refuses to physically purge any `customer` row unless `is_anonymized = TRUE` and no child rows reference it (`TL-24`).

#### 4.3.1. Master Anonymization Table (`customer` / `employee`)

| Column Name (`db/01-schema.sql`) | Target Table | PostgreSQL Type | Replacement Marker | Purpose & Legal Basis (Decree 13/2023/ND-CP) |
| :--- | :--- | :--- | :--- | :--- |
| `full_name` | `customer` / `employee` | `VARCHAR(45)` | `'ANONYMIZED_USER'` | Scrubs data subject full name |
| `address` | `customer` / `employee` | `VARCHAR(100)` | `'ANONYMIZED'` | Scrubs residential address |
| `email` | `customer` / `employee` | `VARCHAR(100)` | `'anonymized_<id>@parking.local'` | Scrubs personal email while remaining valid under `ck_customer_email_format` |
| `phone` | `customer` / `employee` | `VARCHAR(15)` | `'0900000000'` | Scrubs personal phone number while satisfying `ck_customer_phone_digits` |
| `date_of_birth` | `customer` / `employee` | `DATE` | `'1970-01-01'` | Replaces birth date with standard epoch date (`ck_customer_dob_past`) |
| `identity_card_number` | `customer` / `employee` | `VARCHAR(20)` | `'000000000000'` | Scrubs national ID while satisfying `ck_customer_idcard_digits` |
| `is_anonymized` | `customer` | `BOOLEAN` | `TRUE` | Marks customer record as anonymized (`ck_customer_anonymized_pair`) |
| `anonymized_at` | `customer` | `TIMESTAMPTZ` | `CURRENT_TIMESTAMP` | Timestamp of irreversible PII anonymization |
| `deleted_at` | `customer` / `employee` | `TIMESTAMPTZ` | `CURRENT_TIMESTAMP` | Soft-delete timestamp (`ck_customer_soft_delete_pair`) |
| `deleted_by` | `customer` / `employee` | `BIGINT` | `<actor_account_id>` | Administrative actor who executed erasure |
