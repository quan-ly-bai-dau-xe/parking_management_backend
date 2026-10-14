# Delete Rules & Destructive Operations Catalog

This document specifies all deletion flows (Delete Flows) and cancellation/reset actions (Cancel/Reset) across the Car Parking Lot Management System per the canonical SRS v4.1 specification. It defines business guard rules, foreign key referential integrity controls (`models.PROTECT`), role-based access control (RBAC), concurrency locking mechanisms (`select_for_update`), audit trail logging, verbatim SRS error messages, and financial statistics preservation impacts (SRS 4.7).

It also integrates statutory Vietnamese privacy compliance requirements under **Decree No. 13/2023/ND-CP** (Personal Data Protection) and **Accounting Law No. 88/2015/QH13**.

---

## 1. Core Principles Governing Data Deletion (Team Lead Mandatory Decisions)

1. **Soft Delete by Default**:
   - 100% of core domain business entities (`Employee`, `Customer`, `Vehicle`, `Ticket`, `ParkingSlot`, `News`) enforce soft deletion.
   - Deletion mutates `deleted_at = timezone.now()` and `deleted_by = request.user`. Never execute raw SQL `DELETE FROM table WHERE id = ...`.
   - Default querysets (`models.Manager` / `models.QuerySet`) automatically exclude soft-deleted records (`WHERE deleted_at IS NULL`). Explicit query methods (`all_with_deleted()` or `only_deleted()`) are provided for administration and compliance audits.
2. **Strict Prohibition of Hard Deletes in Application Code**:
   - Application code (Views, Services, Serializers) is strictly prohibited from invoking physical hard deletes.
   - Permanent purging is restricted to dedicated management commands (`python manage.py purge_*`) requiring pre-execution database backups, `--dry-run` simulation flags, and formal ADR approvals.
3. **Data Classes That Must Never Be Hard-Deleted**:
   - **Parking Tickets (`Ticket`)**: Fiscal accounting vouchers substantiating parking fee revenue.
   - **Vehicle Entry/Exit Movement Logs (`VehicleEntryExitLog`)**: Physical security access records.
   - **Audit Logs (`AuditLog` / `HistoricalRecords`)**: Immutable append-only inspection records.
4. **Foreign Key Integrity (`on_delete=models.PROTECT`)**:
   - All foreign keys referencing business entities, tickets, and movement logs must configure `on_delete=models.PROTECT`.
   - Cascading database deletions (`CASCADE`) are strictly prohibited across domain entities (with the sole exception permitted under ADR-0004 for temporary `PersistentLoginToken` authentication tokens).

---

## 2. Detailed Catalog of Deletion Flows in SRS v4.1

### 2.1. Flow DEL-01: Employee Deletion (Employee Delete Flow)
- **Stable Source Citations**:
  - SRS Section 4.3.1, Employee Management Table, Action row `Xóa` (Item 12, Action 24).
  - SRS Section 4.3.4, Delete Employee Information Table, Interface row (Row 0), Confirmation row `Xác nhận` (Item 6, Action 10), Cancellation row `Hủy` (Item 7, Action 11).
  - Wireframes: `image4.png` (Delete icon in list), `image7.png` (Delete confirmation modal).
- **Access Control (RBAC)**: Restricted strictly to **Manager (`MANAGER`)** (SRS 4.2 Row 7: "Chỉ có Quản lý mới có thể sử dụng Tab này để quản lý"; SRS 4.3.1 Row 1).
- **Operation Type**: **Soft Delete** (`deleted_at`, `deleted_by`).
- **Domain Guard Rules**:
  1. `[PROPOSAL]` *Self-Deletion Guard* (OQ-10): Authenticated users cannot delete their own employee profile (`request.user.employee_id != target.id`).
  2. `[PROPOSAL]` *Last Manager Safeguard* (OQ-10): Prevent deletion if only 1 active Manager account remains in the system (`active=True, role='MANAGER'`).
  3. `[PROPOSAL]` *Referential Integrity Guard (`PROTECT`)* (OQ-10): Physical deletion blocked when linked to historical records (`Ticket.created_by`, `News.author`); soft deletion preserves foreign key relationships cleanly.
- **Concurrency Control**:
  - Pessimistic locking via `select_for_update()` inside `transaction.atomic()`.
  - If record was soft-deleted by another actor or does not exist: Return HTTP 404 with verbatim SRS message:
    > `Dữ liệu không tồn tại` (SRS 4.3.4 Row 10) or `Kết nối cơ sở dữ liệu hoặc thông tin không tồn tại` (SRS 4.3.1 Row 24).
  - On database connectivity failure: Return HTTP 500 with verbatim message:
    > `Lỗi kết nối server` (SRS 4.3.4 Row 10).
- **Verbatim Success Message**:
  > `Xóa thành công` (SRS 4.3.4 Row 10 and SRS 4.3.1 Row 24).
- **Audit Trail**: Record `action='SOFT_DELETE'`, `actor_id`, `target_employee_id`, `timestamp`, `ip_address` via middleware.
- **Impact on Statistics (SRS 4.7)**: Zero impact on historical operational reporting.

---

### 2.2. Flow DEL-02: Customer Deletion (Customer Delete Flow)
- **Stable Source Citations**:
  - SRS Section 4.4.1, Customer List Table, Action row `xóa` (Item 12, Action 31).
  - SRS Section 4.4.5, Delete Customer Notice Table, Dialog row `Thông báo xóa khách hàng` (Item 5), Confirmation row `Xác nhận` (Item 6), Cancellation row `Hủy` (Item 7).
  - Wireframes: `image8.png` (Delete button), `image12.png` (Delete confirmation modal showing customer name and ID).
- **Access Control (RBAC)**: **Manager (`MANAGER`)** and **Employee (`EMPLOYEE`)** (SRS Section 3: Employees authorized to execute Customer Management).
- **Operation Type**: **Soft Delete** (`deleted_at`, `deleted_by`).
- **Domain Guard Rules**:
  1. `[PROPOSAL]` *Parked Vehicle Guard* (OQ-40): If customer owns vehicles with active uncompleted parking sessions (`VehicleEntryExitLog.exit_time IS NULL`), reject deletion.
  2. `[PROPOSAL]` *Active Ticket Guard* (OQ-40): If customer holds unexpired parking tickets (`Ticket.end_date >= current_time`), reject deletion (`PROTECT`).
- **Concurrency Control**:
  - Row locking via `select_for_update()`.
  - If record is concurrently being deleted: Return HTTP 409/404 with verbatim message:
    > `Dữ liệu đang được xóa bởi người dùng khác` (SRS 4.4.5 Row 6).
  - On server error: Return HTTP 500 with verbatim message:
    > `Lỗi server` (SRS 4.4.5 Row 6).
- **Verbatim Success Status**:
  > SRS 4.4.5 describes transition back to customer list upon deletion. Proposed message: see 05-proposed-messages.md.
- **Audit Trail & PII Handling**: Customer soft deletion triggers anonymization review under Decree 13/2023/ND-CP.

---

### 2.3. Flow DEL-03: Vehicle Row Deletion Inside Customer Form (Vehicle Row Delete Flow)
- **Stable Source Citations**:
  - SRS Section 4.4.3, Add Customer Table, Action row `Xóa` (Item 9, Action 23).
  - SRS Section 4.4.4, Edit Customer Table, Action row `Xóa` (Item 10, Action 26).
  - Wireframes: `image10.png` (Delete link on vehicle row), `image11.png` (Vehicle list table inside edit form).
- **Access Control (RBAC)**: **Manager (`MANAGER`)** and **Employee (`EMPLOYEE`)**.
- **Operation Type**: Form-level row removal / Soft Delete (`deleted_at`).
- **Domain Guard Rules**:
  1. `[PROPOSAL]` *Active Parking Guard* (OQ-41): Cannot delete vehicle row if vehicle is currently inside lot (`is_parked=True`).
  2. `[PROPOSAL]` *Active Ticket Guard* (OQ-41): Cannot delete vehicle row if associated with an active unexpired ticket (`Ticket.end_date >= current_time`).
- **Concurrency & Error Responses**:
  - On system failure: Return HTTP 500 with verbatim SRS message:
    > `Lỗi hệ thống` (SRS 4.4.4 Row 26).

---

### 2.4. Flow DEL-04: Parking Ticket Deletion (Ticket Delete Flow)
- **Stable Source Citations**:
  - SRS Section 4.6.1, Ticket List Table, Action column `Icon Xóa` (Item 10, Action 30).
  - SRS Section 4.6.4, Confirm Ticket Deletion Table, Dialog title (Row 0), Confirmation button `Yes` (Item 6, Action 12), Cancellation button `No` (Item 7, Action 13).
  - Wireframe: `image18.png` (Modal popup deletion confirmation dialog).
- **Access Control (RBAC)**: **Manager-only (`MANAGER`)** (Conservative default; see OQ-39). The alternative allowing Employee deletion is an open question proposal `[PROPOSAL]` in OQ-39 awaiting Product Owner decision.
- **Operation Type**: **Soft Delete** (`deleted_at`, `deleted_by`).
- **Domain Guard Rules**:
  1. *Expired and Non-Renewed Constraint (Canonical SRS Fact)*: SRS 4.6.4 Row 1 & Row 6 dictate that ticket deletion is permitted **ONLY** for tickets that have expired and have not been renewed.
  2. *Active Unexpired Guard*: SRS 4.6.4 Row 6 defines case `TH1: vé được xóa là vé chưa hết hạn thì không được xóa`. Proposed error dialogue: `[PROPOSAL]` "Vé chưa hết hạn sử dụng, không được phép xóa." (`PROP-4.6.4-P01`).
  3. *Renewed Guard*: If ticket was renewed, deletion blocked. Proposed error dialogue: `[PROPOSAL]` "Vé đã được gia hạn, không được phép xóa." (`PROP-4.6.4-P02`).
  4. `[PROPOSAL]` *Parked Vehicle Guard* (OQ-42): Deletion rejected if associated vehicle has not completed physical exit (`exit_time IS NULL`).
- **Concurrency Control**:
  - Pessimistic locking via `select_for_update()`.
  - If ticket is concurrently being deleted: SRS 4.6.4 Row 6 defines case `TH2: vé được xóa đang được xóa bởi 1 người dùng khác thì không được xóa`. Proposed dialogue: `[PROPOSAL]` "Vé đang được xử lý bởi người dùng khác, vui lòng thử lại sau." (`PROP-4.6.4-P03`).
  - On connectivity failure: SRS 4.6.4 Row 6 defines case `TH3: Vé được xóa không kết nối được`. Proposed dialogue: `[PROPOSAL]` "Lỗi kết nối cơ sở dữ liệu khi thực hiện xóa vé." (`PROP-4.6.4-P04`).
  - If ticket is not found: Proposed dialogue `[PROPOSAL]` "Vé không tồn tại hoặc đã bị xóa." (`PROP-4.6.4-P05`).
- **Verbatim Success Message**:
  > `Xóa thành công` (SRS 4.6.4 Row 6: MSG-4.6.4-M01).
- **Preservation of Revenue Statistics (SRS 4.7)**:
  - Parking tickets form legal substantiation for revenue calculations in **4.7.1 Aggregate Statistics** (by Month, Quarter, Year).
  - Soft-delete policy ensures ticket records remain preserved in physical table `Ticket`.
  - Revenue computation service (`RevenueStatisticsService`) queries all issued tickets with valid payment status (including records where `deleted_at IS NOT NULL`).
  - **Inviolable Principle**: Deleting expired tickets removes them from current management views (4.6.1) while **PRESERVING 100% OF HISTORICAL REVENUE AUDIT ACCURACY**.

---

### 2.5. Flow DEL-05: Parking Slot Deletion (Parking Slot Delete Flow)
- **Stable Source Citations**:
  - SRS Section 4.8.1, Parking Slot List Table, Action column `Xoá` (Item 9).
  - SRS Section 4.8.5, Delete Parking Slot Confirmation Table, Action button `Xóa` (Item 6, Action 9), Cancellation button `Hủy` (Item 7, Action 10).
  - Wireframe: `image21.png` (Delete link in table), `image25.png` (Delete confirmation modal).
- **Access Control (RBAC)**: `[PROPOSAL]` Manager role (`MANAGER`): Module 4.8 is parking lot administrative infrastructure (OQ-03, OQ-30).
- **Operation Type**: **Soft Delete** (`deleted_at`, `deleted_by`).
- **Domain Guard Rules**:
  1. *Slot Bound to Active Ticket Guard (Canonical SRS Fact)*: SRS 4.8.5 Row 9 mandates case: `TH: Xóa vị trí đang được xe đk vé đỗ` -> System must reject deletion if an active ticket reserves this slot (`Ticket.slot_id == target.id AND Ticket.end_date >= current_time`).
  2. `[PROPOSAL]` *Physically Occupied Guard* (OQ-43): If sensors or entry logs indicate physical occupancy (`is_occupied=True`), deletion is blocked.
- **Concurrency Control**:
  - Pessimistic locking via `select_for_update()`.
  - If slot is concurrently being deleted: SRS 4.8.5 Row 9 TH2 defines case `Xoa vị trí đang được xóa bởi người khác`: Reject and return conflict envelope.
  - On server error: SRS 4.8.5 Row 9 TH3 defines case `xóa nhưng không kết nối được`: Return server connectivity error.
- **Verbatim Success Behavior**:
  > SRS 4.8.5 Row 9 describes: Vị trí đỗ được xóa và quay lại màn hình danh sách vị trí đỗ.
- **Impact on Statistics and Parking Map (4.5.2 & 4.7)**:
  - When slot is soft-deleted, total capacity decreases by 1, and available slots recalculate automatically (`available_slots`).
  - Parking map (4.5.2) hides or disables the slot.
  - Historical movement records linked to slot remain intact via `PROTECT` foreign keys.

---

### 2.6. Flow DEL-06: Cancellation and Rollback Actions (Cancel / Reset / Back)

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

| Entity | Deletion Flow ID | Permitted Roles | Domain Guard Rules | Database Action | Verbatim SRS Error Strings |
| :--- | :---: | :---: | :--- | :--- | :--- |
| **Employee (`Employee`)** | DEL-01 | `MANAGER` | - `[PROPOSAL]` Cannot self-delete active account (OQ-10).<br>- `[PROPOSAL]` Cannot delete last active Manager (OQ-10).<br>- `[PROPOSAL]` Foreign key `PROTECT` on tickets and articles. | Soft delete (`deleted_at`) | `Dữ liệu không tồn tại` / `Kết nối cơ sở dữ liệu hoặc thông tin không tồn tại` / `Lỗi kết nối server` |
| **Customer (`Customer`)** | DEL-02 | `MANAGER`, `EMPLOYEE` | - `[PROPOSAL]` No vehicles currently inside lot (OQ-40).<br>- `[PROPOSAL]` No active parking tickets (`PROTECT` - OQ-40). | Soft delete (`deleted_at`) | `Dữ liệu đang được xóa bởi người dùng khác` / `Lỗi server` |
| **Vehicle Row (`Vehicle`)** | DEL-03 | `MANAGER`, `EMPLOYEE` | - `[PROPOSAL]` Vehicle not bound to active ticket (OQ-41).<br>- `[PROPOSAL]` Vehicle not physically present in lot (OQ-41). | Soft delete (`deleted_at`) | `Lỗi hệ thống` |
| **Ticket (`Ticket`)** | DEL-04 | `MANAGER` (Conservative default; Employee access is `[PROPOSAL]` in OQ-39) | - **Ticket must be expired and non-renewed (SRS Fact)**.<br>- `[PROPOSAL]` Vehicle has physically exited lot (OQ-42). | Soft delete (`deleted_at`) | `vé được xóa là vé chưa hết hạn thì không được xóa` / `vé được xóa đang được xóa bởi 1 người dùng khác thì không được xóa` / `Vé được xóa không kết nối được` |
| **Parking Slot (`ParkingSlot`)** | DEL-05 | `MANAGER` | - **Slot not reserved by active ticket (SRS Fact)**.<br>- `[PROPOSAL]` Slot not physically occupied by vehicle (OQ-43). | Soft delete (`deleted_at`) | `TH: Xóa vị trí đang được xe đk vé đỗ` / `Xoa vị trí đang được xóa bởi người khác` / `xóa nhưng không kết nối được` |

---

## 4. Legal Compliance Analysis: Decree 13/2023/ND-CP

### 4.1. Official Legal Foundation
- **Statute**: **Decree No. 13/2023/ND-CP** dated 17/04/2023 of the Government of Vietnam on Personal Data Protection (effective from 01/07/2023).
- **Verified Official Sources**:
  * Government Web Portal: https://vanban.chinhphu.vn/?pageid=27160&docid=207705 (Accessed: 2026-10-11).
  * National Legal Database: https://vbpl.vn/bocongan/Pages/vbpq-van-ban-goc.aspx?ItemID=160246 (Accessed: 2026-10-11).
- **Associated Statute**: **Accounting Law No. 88/2015/QH13** dated 20/11/2015 (Article 41 regarding statutory retention periods for financial vouchers).

### 4.2. Personal Data Collected by the Car Parking Lot System
Per canonical SRS v4.1, the system processes:
1. *Basic Personal Data (Article 2 Clause 3)*:
   - Full name (`HoTenNV`, `HoTenKH`).
   - Date of birth (`NgaySinhNV`, `NgaySinhKH`).
   - Gender (`SexNV`, `SexKH`).
   - Telephone number (`SDT_NV`, `SDTKH`).
   - Address (`DiaChiNV`, `DiaChiKH`).
   - Email address (`MailNV`, `MailKH`).
   - National Identification Number (`CMND`).
   - Vehicle license plate and registration data (`BienSoXe`).
2. *Sensitive Personal Data (Article 2 Clause 4)*:
   - Spatial location and movement tracking data (via automated camera license plate capture with real-time timestamps `Thời gian vào`, `Thời gian ra` at SRS 4.5.1).

### 4.3. Data Subject Rights & Technical Execution Architecture

1. **Right to Withdraw Consent (Article 9 Clause 4)**:
   - Data subjects possess the legal right to withdraw consent, subject to statutory retention exceptions.

2. **Right to Erasure (Article 9 Clause 5 & Article 16 Clause 1)**:
   - Customers have the right to request deletion of personal data when no longer necessary for stated collection purposes or upon consent withdrawal (Article 16 Clause 1 Points a, b).
   - Upon receipt of a valid erasure request, the data controller must complete deletion within **72 hours** (Article 16 Clause 5).

3. **Statutory Exceptions to Deletion Obligations (Article 16 Clause 2 Points a & d)**:
   - Personal data deletion obligations do not apply where:
     * *Point a*: Governing law prohibits deletion (Per Accounting Law 2015, accounting vouchers substantiating parking fee revenue must be preserved for 5 to 10 years).
     * *Point d*: Personal data is processed to serve legal obligations, scientific research, or statutory statistics (substantiating Screen 4.7.1 Revenue Statistics and tax compliance).

4. **Proposed Backend Architecture Solution: Data Anonymization Pattern (`[ASSUMPTION]` & `[PROPOSAL]` OQ-12)**:
   - To reconcile the 72-hour erasure obligation under Decree 13/2023/ND-CP with accounting voucher retention exceptions and revenue statistics preservation (SRS 4.7):
   - Upon receiving an authorized personal data erasure request:
     1. Execute soft deletion on the customer record (`Customer.deleted_at = timezone.now()`).
     2. Apply **Irreversible Data Anonymization** on all identifying personal fields according to the Master Anonymization Table below:

#### 4.1. Bảng Quy Chuẩn Giá Trị Ẩn Danh Hóa Dữ Liệu Cá Nhân (Master Anonymization Table)

| Tên Trường (Field) | Entity Áp Dụng | Kiểu Dữ Liệu | Giá Trị Thay Thế (Marker) | Mục Đích & Căn Cứ Pháp Lý (NĐ 13/2023/NĐ-CP) |
| :--- | :--- | :--- | :--- | :--- |
| `full_name` (Họ tên) | Customer / Employee | CharField | `"ANONYMIZED_USER"` | Xóa bỏ họ tên thật của chủ thể dữ liệu |
| `address` (Địa chỉ) | Customer / Employee | CharField | `"ANONYMIZED"` | Loại bỏ địa chỉ cư trú cá nhân |
| `email` (Email) | Customer / Employee | EmailField | `"anonymized_<id>@parking.local"` | Loại bỏ thư điện tử cá nhân; bảo đảm tính duy nhất nếu có unique index |
| `phone_number` (SĐT) | Customer / Employee | CharField | `"0000000000"` | Loại bỏ số điện thoại cá nhân |
| `date_of_birth` (Ngày sinh) | Customer / Employee | DateField | `1970-01-01` | Thay thế ngày sinh thật bằng epoch date chuẩn |
| `identity_card_number` (CMND/CCCD) | Customer / Employee | CharField | `"000000000"` | Che giấu số CMND/CCCD/Hộ chiếu nhạy cảm |
| `is_anonymized` | Customer / Employee | BooleanField | `True` | Flag kỹ thuật đánh dấu bản ghi đã xử lý ẩn danh |
| `deleted_at` | Customer / Employee | DateTimeField | `timezone.now()` | Dấu vết thời gian thực hiện soft-delete |
| `deleted_by` | Customer / Employee | ForeignKey | `<Admin Instance>` | Lưu vết người dùng quản trị thực hiện |

     3. Execution Implementation Snippet:
        ```python
        customer.full_name = "ANONYMIZED_USER"
        customer.address = "ANONYMIZED"
        customer.email = f"anonymized_{customer.id}@parking.local"
        customer.phone_number = "0000000000"
        customer.date_of_birth = datetime.date(1970, 1, 1)
        customer.identity_card_number = "000000000"
        customer.is_anonymized = True
        customer.save(
            update_fields=[
                "full_name",
                "address",
                "email",
                "phone_number",
                "date_of_birth",
                "identity_card_number",
                "is_anonymized",
                "updated_at",
            ]
        )
        ```
     4. Preserve foreign key references to `Ticket`, `Vehicle`, and `VehicleEntryExitLog` with anonymized technical IDs for financial auditability and occupancy reporting without exposing citizen identity.
   - Executed via an administrative Django Management Command (`python manage.py purge_anonymize_customers --dry-run`) with strict administrative audit approvals.
