# Open Questions, Contradictions, and Policy Catalog

<!-- cspell:words VIETQR nonnulls NVVH NVTN -->

This document registers and analyzes all contradictions between the specification text (`Quan ly bai dau xe oto_SRS_v4.1.docx`), wireframe images, and the project plan (`Tasks_Sprint_1`), alongside open business rules and technical workflow questions. For each issue, this catalog establishes a technically grounded **Proposed Default Assumption** and specifies explicit **Decision Ownership (Owner: Product Owner or Team Lead)**.

---

## 1. Decision Authority Matrix

- **Product Owner (PO)**: Authorized decider for Business Rules, functional user scope, actor taxonomy, financial data integrity, and compliance policies.
- **Team Lead (TL)**: Authorized decider for technical conventions, system architecture, Git governance, security posture, repository licensing, and backend engineering standards.

---

## 2. Catalog of Contradictions and Open Questions

### OQ-01: Security & Non-Functional

- **Priority / Status**: Blocker
- **Sources**:
  - SRS 4.1, Login Table, Row 7 (`Ghi nhớ mật khẩu`).
  - SRS Section 5 Non-functional Requirements (SRS Section 5, subsection Security).
- **Issue / Description**:
  - SRS states: "Khi user click vào ô checkbox thì mật khẩu sẽ được lưu trên cookie của máy để đảm bảo lần đăng nhập sau không cần nhập mật khẩu".
  - Storing plaintext credentials in cookies is a critical vulnerability violating OWASP Top 10.
  - SRS non-functional specs (RedHat 4, WebLogic 10, IE6) are entirely obsolete.
- **Proposed Default / Resolution**: **TEAM LEAD DECISION**: Strictly PROHIBIT storing passwords in cookies. Replace with secure Persistent Login Token architecture (Session/Refresh tokens with `HttpOnly`, `Secure`, `SameSite=Lax` flags). Modernize stack to Linux, Docker, Python 3.14, Django 6.1, PostgreSQL 18.
- **Authority / Owner**: **Team Lead**

### OQ-02: Account Credentials

- **Priority / Status**: RESOLVED (`TL-01`)
- **Sources**:
  - Frontend `login-container.png` (`Email hoặc Số điện thoại`, `Chưa có tài khoản? Đăng ký ngay`).
  - SRS 4.1, Login Table, Row 5; SRS 4.3.2, Rows 5 & 10; SRS 4.3.3, Rows 10 & 11.
- **Issue / Description**:
  - Add Employee screen (4.3.2) defines `ID` and `Họ tên`, but no `Tên đăng nhập` field, whereas Frontend `login-container.png` authenticates by `"Email hoặc Số điện thoại"`.
  - Default employee password is also unspecified in the SRS (`Thiết lập mặc định mật khẩu nhân viên`).
- **Proposed Default / Resolution**: **RESOLVED (`TL-01`)**: `account` uses `email VARCHAR(100) NULL` and `phone VARCHAR(15) NULL` with `ck_account_login_identifier_present CHECK (email IS NOT NULL OR phone IS NOT NULL)` and active partial unique indexes (`uq_account_email_active`, `uq_account_phone_active`); `username` is dropped. Initial employee password is an auto-generated high-entropy string or temporary password requiring change on first login.
- **Authority / Owner**: **PO** (Business) & **Team Lead** (Technical)

### OQ-03: Actors & Permissions

- **Priority / Status**: RESOLVED (`TL-01`)
- **Sources**:
  - Frontend `login-container.png` (`Chưa có tài khoản? Đăng ký ngay`).
  - SRS Section 3 Actor List, Table, Rows 1-2; SRS 4.5.2, Row 8; Plan `Tasks_Sprint_1`, Row 12 (F12).
- **Issue / Description**:
  - SRS Section 3 defines only 2 Actors (`Quản lý`, `Nhân viên`), whereas SRS 4.5.2, `Tasks_Sprint_1`, and Frontend `login-container.png` (`"Đăng ký ngay"`) include `Khách hàng` (`CUSTOMER`).
- **Proposed Default / Resolution**: **RESOLVED (`TL-01`)**: Maintain 3 distinct roles in `account`: `MANAGER`, `EMPLOYEE`, `CUSTOMER`. Self-registration via `"Đăng ký ngay"` creates a `CUSTOMER` account and linked `customer` profile.
- **Authority / Owner**: **PO** & **Team Lead**

### OQ-04: Address Text vs Dropdown

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.3.2, Row 7 (`Địa chỉ: String(45)`).
  - SRS 4.4.3, Row 8 (`Địa chỉ: String(45)`).
  - Wireframes `image5.png`, `image10.png`.
- **Issue / Description**:
  - SRS text specifies `Địa chỉ` as a free-form text field (`String(45)`).
  - Wireframes illustrate a 3-level dropdown selector for Province, District, and Ward.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT (`TL-15`)**: Backend stores `address` string plus the 3-level administrative lookup hierarchy (`administrative_province`, `administrative_district`, `administrative_ward`) where the Frontend is silent.
- **Authority / Owner**: **PO**

### OQ-05: Parking Slot Identifier

- **Priority / Status**: RESOLVED (`TL-02`)
- **Sources**:
  - Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` (`Tầng B1..B3, F1`, `Khu A..D`, slot codes `A-01`, `B-15`, `P-02`, `EV-02`) & `Quản lý vé — Smart Mobility.png` (`B1 - A01`).
  - Wireframes `image14.png`, `image21.png`, `image23.png`.
- **Issue / Description**:
  - SRS map wireframe (`image14.png`) shows integer slots `1..108`, whereas Frontend and SRS 4.8 display alphanumeric slot codes (`A-01`, `B-15`, `P-02`, `EV-02`) grouped by lot, floor, and zone.
- **Proposed Default / Resolution**: **RESOLVED (`TL-02`)**: Model the 4-level hierarchy `parking_lot -> parking_floor -> parking_zone -> parking_slot` with `parking_slot.code VARCHAR(20) NOT NULL` (`ck_slot_code_format CHECK (code ~ '^[A-Za-z0-9-]+$')`, unique per zone via `uq_parking_slot_zone_code_active`) and grid coordinates `map_row` / `map_col` (`uq_parking_slot_zone_map_pos_active`).
- **Authority / Owner**: **Team Lead**

### OQ-06: Ticket Type & Price Types

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.6.2 Add Ticket, Rows 12-13.
  - SRS 4.6.3 Edit Ticket, Rows 12 & 15.
  - Wireframes `image16.png`, `image17.png`.
- **Issue / Description**:
  - SRS 4.6.2: `Loại vé` is dropdown, `Giá` is `Input - number`.
  - SRS 4.6.3: `Loại vé` is dropdown, `Giá` is listed as `Input-text`.
  - Wireframes suggest ticket price is auto-populated from ticket type or selected from fixed tiers.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Database stores catalog `TicketType` with fixed tariff price (`price`). On ticket creation or renewal, price auto-populates (`DecimalField(12, 2)`). Permission rule: Only Manager can override pricing; Employees select from approved tariff.
- **Authority / Owner**: **PO**

### OQ-07: Navigation Link 4.5.2

- **Priority / Status**: Nice-to-know
- **Sources**:
  - SRS 4.5.2 Parking Map, Row 2 (`Cách truy cập`).
  - SRS 4.5.1 Vehicle In/Out, Table, Rows 4-20.
- **Issue / Description**:
  - SRS 4.5.2 describes access: "Khi click vào link 'Xem' ở giao diện 'Quản lý xe ra/vào'".
  - Screen 4.5.1 description and wireframe `image13.png` have no button named "Xem" (only "Tìm xe" and "Lưu thông tin").
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Parking map 4.5.2 is an independent top-level navigation item. On screen 4.5.1, provide "Xem bản đồ bãi xe" link next to parking slot input for convenient cross-navigation.
- **Authority / Owner**: **PO** & **Team Lead**

### OQ-08: Git Workflow Conflict

- **Priority / Status**: Important
- **Sources**:
  - `01-Reference/04. [BM] Team Charter.docx`, Git Workflow section.
  - `01-Reference/Git/git-organization.xlsx`.
- **Issue / Description**:
  - Team Charter dictates: Feature branches branch strictly from `dev`, PR targets `dev`, requires >= 1 approval, merged with `--no-ff`.
  - `git-organization.xlsx` instructs PRs directly against `main`.
  - Currently repository has only `main`.
- **Proposed Default / Resolution**: **TEAM LEAD DECISION**: Strictly enforce enterprise Git workflow per Team Charter:
  1. `main` is production release branch (Protected).
  2. `dev` is continuous integration branch (Protected).
  3. Features branch from `dev` as `feature/<issue-id>-<slug>`, PR targets `dev`, CI and peer review required before merge. Leader merges `dev` to `main` upon release sign-off.
- **Authority / Owner**: **Team Lead**

### OQ-09: Repository License Selection

- **Priority / Status**: RESOLVED / CLOSED
- **Sources**:
  - Public repository status of `parking_management_backend`.
  - [README.md](../../README.md#license).
- **Issue / Description**:
  - Repository is public on GitHub. Legal rights over source code and training assets must be established.
  - Under GitHub Terms of Service and copyright law, public repo without license defaults to "All Rights Reserved" (viewing and on-platform forking allowed; commercial reuse or distribution outside platform prohibited).
- **Proposed Default / Resolution**: **OWNER DECISION (2026-10-11)**: Adopt **"No license (All Rights Reserved)"**. Delete `LICENSE` file and remove MIT badges from `README.md`. Assert owner copyright explicitly in `README.md`. Full analysis recorded in Owner decisions.
- **Authority / Owner**: **Owner**

### OQ-10: Self-Deletion & Last Manager Safeguard

- **Priority / Status**: Blocker
- **Sources**:
  - SRS 4.3.4, Delete Employee Table, Rows 1-11.
  - `docs/requirements/03-delete-rules-catalog.md`.
- **Issue / Description**:
  - SRS does not define behavior when a Manager attempts to delete their own account.
  - SRS lacks safeguards against deleting the last remaining Manager in the system.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Enforce 2 hard service guards:
  1. Users cannot delete their own active account (`user.id != target.id`).
  2. System must preserve at least 1 active Manager (`active=True, role='MANAGER'`). Delete blocked if active manager count <= 1.
- **Authority / Owner**: **Team Lead**

### OQ-11: Revenue Statistics and Soft-Deleted Tickets

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.6.4 Ticket Deletion.
  - SRS 4.7.1 Aggregate Statistics (Revenue).
- **Issue / Description**:
  - Expired, non-renewed tickets may be deleted under SRS 4.6.4.
  - Unclear whether deleted tickets remain included in monthly/quarterly/annual revenue aggregates.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Financial revenue is historical and must be preserved 100%. Apply **Soft Delete**: When tickets are deleted, update `deleted_at = timezone.now()`. Statistics queries aggregate over all issued tickets (including soft-deleted records with successful payment status).
- **Authority / Owner**: **PO** & **Team Lead**

### OQ-12: PII Protection under Decree 13/2023/ND-CP

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.3 (Employee: ID/Email/Phone/Address).
  - SRS 4.4 (Customer: ID/Email/Phone/Address).
  - Decree 13/2023/ND-CP dated 17/04/2023.
- **Issue / Description**:
  - System collects basic and sensitive personal data (National ID, Phone, Address, Vehicle Plates).
  - When a user requests consent withdrawal or deletion (Right to Erasure), how to handle data retention while maintaining financial audit history?
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Apply **Data Anonymization / Pseudonymization**: On deletion request under Decree 13, soft-delete record and overwrite identifiable personal fields conforming strictly to Master Anonymization Table in `docs/requirements/03-delete-rules-catalog.md` Section 4.1 (`ho_ten = 'ANONYMIZED_USER'`, `address = 'ANONYMIZED'`, `email = 'anonymized_<id>@parking.local'`, `sdt = '0000000000'`, `ngay_sinh = '1970-01-01'`, `cmnd = '000000000'`), preserving transaction amounts and timestamps for accounting integrity.
- **Authority / Owner**: **PO** & **Team Lead**

### OQ-13: Employee Update & Not Found Messages

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.3.3 Edit Employee, Row 17.
  - SRS 4.3.1 Row 25.
- **Issue / Description**: SRS only describes data save, providing no explicit success or not-found (404) message text.
- **Proposed Default / Resolution**: Apply proposed messages [PROPOSAL]:
  - Success: `Cập nhật thông tin nhân viên thành công.` (`PROP-4.3.3-P01`).
  - Not found: `Nhân viên không tồn tại hoặc đã bị xóa.` (`PROP-4.3.3-P02`).
- **Authority / Owner**: **Product Owner**

### OQ-14: Customer Add Success Message

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.4.3 Add Customer, Row 24.
- **Issue / Description**: SRS only describes data persistence and button toggle without success message.
- **Proposed Default / Resolution**: Apply proposed message [PROPOSAL]:
  `Thêm mới thông tin khách hàng thành công.` (`PROP-4.4.3-P01`).
- **Authority / Owner**: **Product Owner**

### OQ-15: Customer Update & Delete Messages

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.4.4 Edit Customer, Row 27.
  - SRS 4.4.5 Delete Customer, Row 6.
- **Issue / Description**: SRS specifies save and page transition without success or 404 error strings.
- **Proposed Default / Resolution**: Apply proposed messages [PROPOSAL]:
  - Edit success: `Cập nhật thông tin khách hàng thành công.` (`PROP-4.4.4-P01`).
  - Not found: `Khách hàng không tồn tại hoặc đã bị xóa.` (`PROP-4.4.4-P02`).
- **Authority / Owner**: **Product Owner**

### OQ-16: Ticket Add Success Message

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.6.2 Add Ticket, Row 18.
- **Issue / Description**: SRS describes save and navigation to list without success dialogue.
- **Proposed Default / Resolution**: Apply proposed message [PROPOSAL]:
  `Thêm mới vé đỗ xe thành công.` (`PROP-4.6.2-P01`).
- **Authority / Owner**: **Product Owner**

### OQ-17: Ticket Renewal Success Message

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.6.3 Edit Ticket, Row 19.
- **Issue / Description**: SRS describes update to database without success message string.
- **Proposed Default / Resolution**: Apply proposed message [PROPOSAL]:
  `Gia hạn vé đỗ xe thành công.` (`PROP-4.6.3-P01`).
- **Authority / Owner**: **Product Owner**

### OQ-18: Active Ticket Deletion Guard

- **Priority / Status**: Blocker
- **Sources**:
  - SRS 4.6.4 Delete Ticket, Row 6 (TH1).
- **Issue / Description**: SRS describes scenario: `TH1: vé được xóa là vé chưa hết hạn thì không được xóa`, providing no dialogue string.
- **Proposed Default / Resolution**: Apply proposed messages [PROPOSAL]:
  - Active: `Vé chưa hết hạn sử dụng, không được phép xóa.` (`PROP-4.6.4-P01`).
  - Renewed: `Vé đã được gia hạn, không được phép xóa.` (`PROP-4.6.4-P02`).
- **Authority / Owner**: **Product Owner**

### OQ-19: Ticket Deletion Concurrency

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.6.4 Delete Ticket, Row 6 (TH2).
- **Issue / Description**: SRS describes scenario: `TH2: vé được xóa đang được xóa bởi 1 người dùng khác thì không được xóa`.
- **Proposed Default / Resolution**: Apply proposed message [PROPOSAL]:
  `Vé đang được xử lý bởi người dùng khác, vui lòng thử lại sau.` (`PROP-4.6.4-P03`).
- **Authority / Owner**: **Product Owner**

### OQ-20: Ticket Deletion Connection Failure

- **Priority / Status**: Nice-to-know
- **Sources**:
  - SRS 4.6.4 Delete Ticket, Row 6 (TH3).
- **Issue / Description**: SRS describes scenario: `TH3: Vé được xóa không kết nối được`.
- **Proposed Default / Resolution**: Apply proposed message [PROPOSAL]:
  `Lỗi kết nối cơ sở dữ liệu khi thực hiện xóa vé.` (`PROP-4.6.4-P04`).
- **Authority / Owner**: **Product Owner**

### OQ-21: Ticket Not Found (404)

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.6.4 Delete Ticket, Table 19.
- **Issue / Description**: SRS 4.6.4 contains zero message for non-existent or previously deleted tickets.
- **Proposed Default / Resolution**: Apply proposed message [PROPOSAL]:
  `Vé không tồn tại hoặc đã bị xóa.` (`PROP-4.6.4-P05`).
- **Authority / Owner**: **Product Owner**

### OQ-22, OQ-23, OQ-24, OQ-25: Add Slot Messages

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.8.2 Add Slot, Row 14.
- **Issue / Description**: SRS lacks success text, describing scenarios: invalid data, already exists, connection error.
- **Proposed Default / Resolution**: Apply proposed messages `PROP-4.8.2-P01` through `PROP-4.8.2-P04` in `05-proposed-messages.md`.
- **Authority / Owner**: **Product Owner**

### OQ-26, OQ-27, OQ-28, OQ-29: Edit Slot Messages

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.8.3 Edit Slot, Row 16.
- **Issue / Description**: SRS lacks success text, describing scenarios: invalid data, concurrency update, connection error.
- **Proposed Default / Resolution**: Apply proposed messages `PROP-4.8.3-P01` through `PROP-4.8.3-P04` in `05-proposed-messages.md`.
- **Authority / Owner**: **Product Owner**

### OQ-30, OQ-31, OQ-32, OQ-33: Delete Slot Messages

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.8.5 Delete Slot, Row 9.
- **Issue / Description**: SRS lacks success text, describing scenarios: slot has registered ticket, concurrency delete, server error.
- **Proposed Default / Resolution**: Apply proposed messages `PROP-4.8.5-P01` through `PROP-4.8.5-P05` in `05-proposed-messages.md`.
- **Authority / Owner**: **Product Owner**

### OQ-34, OQ-35, OQ-36, OQ-37, OQ-38: Statistics Error Messages

- **Priority / Status**: Nice-to-know
- **Sources**:
  - SRS 4.7.1 Row 15.
  - SRS 4.7.2 Row 13.
- **Issue / Description**: SRS describes scenarios: TH2/TH3 of 4.7.1 and TH1/TH2/TH3 of 4.7.2 without formatted dialogue text.
- **Proposed Default / Resolution**: Apply proposed messages `PROP-4.7.1-P01..P02` and `PROP-4.7.2-P01..P03` in `05-proposed-messages.md`.
- **Authority / Owner**: **Product Owner**

### OQ-39: Ticket Deletion Authorization

- **Priority / Status**: Blocker
- **Sources**:
  - SRS 4.6.1, Ticket List Table, Row 30 (`Icon Xóa`).
  - SRS 4.6.4, Confirm Ticket Delete Table, Row 1 & Row 6.
  - `DEL-04`.
- **Issue / Description**:
  - SRS 4.6.4 states: "chỉ cho phép xóa những vé nào đã quá hạn và không gia hạn", silent on actor role permissions.
  - Discrepancy between DEL-04 (Manager-only) and legacy test suites.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Conservative default is **Manager-only (`MANAGER`)** for ticket deletion (`DELETE /api/v1/tickets/{id}/`, returning HTTP 403 Forbidden for Employee calls). The alternative allowing Employee deletion is maintained as an open proposal (`[PROPOSAL]`) awaiting Product Owner decision.
- **Authority / Owner**: **PO** & **Team Lead**

### OQ-40: Customer Deletion Guard

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.4.5, Delete Customer Confirm Table, Rows 1-7.
  - `DEL-02`.
- **Issue / Description**:
  - SRS 4.4.5 shows deletion confirmation popup with Customer Name and ID.
  - Lacks explicit guards if customer has vehicles currently parked in lot or active tickets.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Enforce 2 hard service guards:
  1. Reject deletion if customer has vehicles with incomplete parking sessions (`exit_time IS NULL`).
  2. Reject deletion if customer possesses active parking tickets (`end_date >= now()`), returning HTTP 400 Bad Request.
- **Authority / Owner**: **Product Owner**

### OQ-41: Customer Vehicle Row Deletion Guard

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.4.3, Row 23.
  - SRS 4.4.4, Row 26.
  - `DEL-03`.
- **Issue / Description**:
  - SRS allows deleting vehicle rows inside customer form.
  - Lacks rules if vehicle is currently inside lot or bound to an active ticket.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Backend rejects vehicle deletion if vehicle is currently parked in lot (`is_parked=True`) or tied to an active ticket (`Ticket.end_date >= now()`).
- **Authority / Owner**: **Product Owner**

### OQ-42: Block Ticket Deletion While Vehicle is Parked

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.6.4, Rows 1 & 6.
  - `DEL-04`.
- **Issue / Description**:
  - SRS allows deleting expired, non-renewed tickets.
  - Unclear if deletion is permitted when physical vehicle has not exited lot.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Reject ticket deletion if vehicle tied to ticket remains parked inside lot (`exit_time IS NULL`). Deletion permitted only after vehicle exits and settles overdue fees.
- **Authority / Owner**: **Product Owner**

### OQ-43: Block Slot Deletion When Physically Occupied

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.8.5, Row 9 (`TH: Xóa vị trí đang được xe đk vé đỗ`).
  - `DEL-05`.
- **Issue / Description**:
  - SRS only blocks deletion when slot has a registered ticket.
  - Unclear if deletion is blocked when an unregistered or walk-in vehicle physically occupies slot.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Reject deletion if sensor/system records slot as physically occupied (`is_occupied=True`), returning a conflict warning.
- **Authority / Owner**: **Product Owner**

### OQ-44: Root Documentation Language Policy

- **Priority / Status**: Nice-to-know
- **Sources**:
  - Public repository root `README.md`.
  - Project documentation standards.
- **Issue / Description**:
  - Unclear whether public repository root `README.md` should contain bilingual Vietnamese translations alongside primary English content.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Maintain repository root `README.md` 100% in English for international open repository cleanliness and compliance, until Product Owner explicitly requests bilingual sections.
- **Authority / Owner**: **Team Lead** & **Product Owner**

### OQ-45: Permission Inference for Modules 4.7 & 4.8

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.7 & 4.8 Table Headers / Row 2 (`Sau admin đăng nhập...`).
  - SRS Section 3 Actor List.
- **Issue / Description**:
  - SRS 4.7 (Statistics) and 4.8 (Parking Management) state: "Sau admin đăng nhập...".
  - SRS Section 3 defines only 2 Actors: `Quản lý` (Manager) and `Nhân viên` (Employee); no `Admin` actor is defined.
  - Restricting Modules 4.7 and 4.8 strictly to Manager is an inference `(inferred)`.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Modules 4.7 and 4.8 are restricted strictly to `MANAGER` by default `(inferred)` as conservative baseline, awaiting Product Owner confirmation of role permissions.
- **Authority / Owner**: **Product Owner**

### OQ-46: Check_Quality Item 6 Punctuation Contradiction

- **Priority / Status**: Important
- **Sources**:
  - Check_Quality Item 6 (`Message phải có chấm câu`).
  - SRS v4.1 Action tables verbatim error messages.
- **Issue / Description**:
  - Check_Quality Item 6 dictates: "Message phải có chấm câu" (ending with punctuation).
  - However, all verbatim messages in SRS v4.1 Action tables terminate without ending punctuation (e.g., `Đã thêm thành công nhân viên`, `Xóa thành công`, `Tên đăng nhập không chứa ký tự đặc biệt`).
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Backend strictly preserves verbatim SRS messages without invented ending punctuation. Proposed messages (`05-proposed-messages.md`) incorporate ending punctuation adhering to Check_Quality Item 6 pending PO final decision on unified punctuation policy.
- **Authority / Owner**: **Product Owner**

### OQ-47: GitHub Review Ownership & CODEOWNERS Handles

- **Priority / Status**: Important
- **Sources**:
  - GitHub Repository Governance.
  - Removal of placeholder `.github/CODEOWNERS`.
- **Issue / Description**:
  - Draft `.github/CODEOWNERS` referenced non-existent GitHub organization teams (`@quan-ly-bai-dau-xe/tech-leads`, `@quan-ly-bai-dau-xe/ba-leads`, `@quan-ly-bai-dau-xe/db-engineers`, `@quan-ly-bai-dau-xe/devops-leads`) and mismatched package path patterns (`apps/*/models.py`).
  - Unclear what the real, active personal GitHub handles or organization teams are for automated review routing.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Remove `.github/CODEOWNERS` from repository until Owner configures valid organization teams or provides exact personal GitHub handles. Pull requests are assigned and reviewed manually per Team Charter.
- **Authority / Owner**: **Owner**

### OQ-48: Employee & Customer Natural Code Formatting: `NV-1234` vs `Alphanumeric 5`

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.3.1 Row 5 & SRS 4.3.2 Row 10 (`ID: Alpha numeric 5`).
  - SRS 4.4.1 Row 5 & SRS 4.4.3 Row 13.
  - Wireframes `image4.png`, `image6.png` (`NV-1234`), `image8.png`, `image9.png` (`KH-1234`, `Xe-001`, `VE-01`).
- **Issue / Description**:
  - SRS text specifies `ID` as alphanumeric length 5 (e.g. `NV001`, `KH001`).
  - Wireframes illustrate prefixed hyphenated format (`NV-1234`, `KH-1234`, `Xe-001`, `VE-01`, `A-1`) having 6 to 7 characters.
  - When updating records, SRS mandates that code is strictly disabled / read-only (`read_only=True`).
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Allocate `code VARCHAR(10)` or `VARCHAR(20)` across all business entities (`employee`, `customer`, `vehicle`, `ticket`, `parking_slot`). Accommodate both 5-character alphanumeric (`NV001`) and hyphenated formats (`NV-1234`). Enforce uniqueness via partial index `WHERE deleted_at IS NULL`.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-49: Scope of Permitted Vehicle Types & Dual Meaning of "Loại xe"

- **Priority / Status**: Important
- **Sources**:
  - SRS Document Title: `Quan ly bai dau xe oto_SRS_v4.1.docx`.
  - SRS 4.4 & 4.8.4 vs SRS 4.5.1 & 4.8.2.
  - Wireframes `image9.png`, `image10.png`, `image22.png`, `image24.png`.
- **Issue / Description**:
  - SRS title states "Quản lý bãi đậu xe ô tô" (Car Parking Lot), yet customer wireframes (`image9.png`, `image10.png`) and slot details (`image24.png`) feature motorcycles (`SH-150i`, `Honda SH`).
  - Crucially, the SRS employs the Vietnamese term `"Loại xe"` with two distinct semantic meanings: (1) Specific commercial vehicle model line (`SH-150i`, `Cerato`, `Morning`) in Customer Vehicle forms (4.4) and Slot Detail (4.8.4); versus (2) Spatial vehicle category / seating capacity group (`Xe 4 chỗ`, `Xe 7 chỗ`, `Xe 12 chỗ`, `Xe máy`) in Barrier Search (4.5.1) and Slot Allowed Vehicle Types (4.8.2).
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Formally decouple the two concepts in the relational data model: (1) Entity `vehicle_type` represents physical parking slot sizing and tariff categories (`Xe 4 chỗ`, `Xe 7 chỗ`, `Xe 12 chỗ`, `Xe máy`, `OTHER`); (2) Attribute `vehicle.model_name` captures the specific commercial vehicle model line (`SH-150i`, `Cerato`, `Morning`); and (3) Attribute `vehicle.brand` captures manufacturer (`Honda`, `Kia`). Seed for `MOTO` is normalized to `'Xe máy'` with `SH-150i` retained only as an illustrative example in `description`.
- **Authority / Owner**: **Product Owner**

### OQ-50: Administrative Hierarchy Structure & Current Legal Framework in Vietnam

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.3.2 Row 7 & SRS 4.4.3 Row 8 (`DiaChi: String(45)`).
  - Wireframes `image5.png`, `image6.png`, `image10.png`.
  - **Law on Organization of Local Government No. 72/2025/QH15** (passed 16-06-2025, Official Gazette Nos. 807 + 808 of 24-06-2025, PDF: `https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/7/2025_807-808_72-2025-qh15..pdf`).
  - **Resolution No. 202/2025/QH15** on Provincial Administrative Unit Arrangement (passed 12-06-2025, Government Portal `https://vanban.chinhphu.vn/?pageid=27160&docid=213930`, signed PDF: `https://datafiles.chinhphu.vn/cpp/files/vbpq/2025/6/202qh.signed.pdf`).
- **Issue / Description**:
  - Under **Law No. 72/2025/QH15**, **Article 1 Clause 1** organizes administrative units into 02 levels (provincial and communal/ward/special-zone); **Article 51 Clause 1** sets the Law's effective date to the date of passage (`16-06-2025`); and **Article 51 Clause 3** states that district-level People's Councils, People's Committees, and administrative agencies end their operation from `01-07-2025`.
  - Under **Resolution No. 202/2025/QH15** (effective from passage on `12-06-2025` per **Article 2 Clause 1**, with newly arranged provincial governments operating from `01-07-2025` per **Article 2 Clause 2**), **Article 1 Clause 10** merges Đà Nẵng city and Quảng Nam province into Đà Nẵng city, and **Article 1 Clause 24** establishes 34 provincial-level units nationwide (28 provinces and 06 centrally-run cities).
  - SRS v4.1 wireframes depict a historical 3-dropdown hierarchy (`Quảng Nam` -> `Điện Bàn` -> `Điện Ngọc`).
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Retain the 3 normalized lookup tables (`administrative_province`, `administrative_district`, `administrative_ward`) with composite foreign keys as a defensive architectural **[PROPOSAL] (OQ-50, OQ-62)** for 100% backward compatibility with the SRS v4.1 3-dropdown UI, legacy datasets, and multi-country hierarchies (`employee.ward_id` is nullable). Seed rows for `Quảng Nam` and `Thị xã Điện Bàn` are labeled as historical wireframe sample seeds; the schema is ready to collapse to a 2-level hierarchy (`province` -> `ward`) upon Product Owner approval.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-51: News Management & Notification Board Specifications (`news`, `notification`)

- **Priority / Status**: Important
- **Sources**:
  - `[CGDN]_Project_Plan.xlsx`, `Tasks_Sprint_1` Row 4 (Task 2) & Row 19 (Task 17).
  - SRS 4.2 Row 13 (`Bảng thông báo`).
  - Reference site `hethongdoxe.com`.
- **Issue / Description**:
  - Sprint 1 plan introduces News Management referencing `hethongdoxe.com` with explicit note to QA with PO.
  - SRS 4.2 lists `Bảng thông báo` without specifying database schema attributes or publishing roles.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Database schema provides `news` table (title, slug, summary, content, thumbnail_url, author_id, is_published, published_at) and `notification` table (recipient_account_id, title, content, notification_type, is_read). Manager and Employee roles are granted authoring privileges.
- **Authority / Owner**: **Product Owner**

### OQ-52: Vehicle Ticket Preference vs `ticket` Table Single Source of Truth Synchronization

- **Priority / Status**: Blocker
- **Sources**:
  - SRS 4.4.3 & 4.4.4 Customer Form (`Chọn ở Xe.LoaiVe: String(10)`, `Chọn ở Xe.HanVe: Date time`).
  - SRS 4.4.2 Vehicle Table (`XeVe_LoaiVe`, `XeVe_NgayHetHan`).
  - SRS 4.6 Ticket Management.
- **Issue / Description**:
  - In Add/Edit Customer (4.4.3/4.4.4), the user assigns ticket type and expiration date directly to each registered vehicle, without selecting parking floor, slot, or price.
  - Ticket management (4.6) requires slot assignment and price calculation.
  - When a ticket is formally issued, renewed, expired, or soft-deleted, metadata on `vehicle` previously risked drifting out of sync. Furthermore, partial preference (one field populated without the other) was possible without a schema guard.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: (1) Enforce `CONSTRAINT ck_vehicle_ticket_pref_pair CHECK ((ticket_type_id IS NULL AND ticket_expires_at IS NULL) OR (ticket_type_id IS NOT NULL AND ticket_expires_at IS NOT NULL))` on `vehicle`; (2) During customer onboarding (4.4.3/4.4.4), persist initial customer subscription preference directly into `vehicle.ticket_type_id` and `vehicle.ticket_expires_at`; (3) Upon formal ticket issuance, renewal (including plan changes), expiration, or soft-deletion in Module 4.6, treat table `ticket` as the authoritative Single Source of Truth: trigger `fn_sync_slot_status_on_ticket()` automatically synchronizes `vehicle.ticket_type_id` and `vehicle.ticket_expires_at` to the latest valid active ticket (`ORDER BY effective_to DESC, id DESC LIMIT 1`), or clears both to NULL if no non-deleted tickets remain.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-53: Vehicle Manufacturer Brand Nullability in Add-Vehicle Modal

- **Priority / Status**: Important
- **Sources**:
  - Wireframe 4.4.3 & 4.4.4 (`image10.png`, `image11.png`).
  - SRS 4.5.1 (REQ-4.5.1-F07) & SRS 4.8.4 (REQ-4.8.4-F01).
- **Issue / Description**:
  - Modal Thêm xe for customer (4.4.3/4.4.4) only inputs `Tên xe` (model_name), `Biển số xe`, `Loại xe`, `Loại vé`, and `Hạn vé`; it completely omits `Hãng xe` (brand).
  - `Hãng xe` only appears in vehicle entry/exit (4.5.1) and slot detail (4.8.4).
  - Imposing `brand NOT NULL` causes customer vehicle creation to fail.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Define `vehicle.brand VARCHAR(50) NULL`. The customer onboarding flow leaves `brand` NULL; the barrier gate camera or staff can later augment the vehicle brand upon first check-in (4.5.1) or via slot management (4.8.4).
- **Authority / Owner**: **Product Owner**

### OQ-54: Parking Facility Floor and Slot Capacity Bounds

- **Priority / Status**: RESOLVED (`TL-02`)
- **Sources**:
  - Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` (`parking_lot -> parking_floor -> parking_zone -> parking_slot`).
  - SRS 4.5.2 Parking Map Table (`Bản đồ tầng Button - Number (2)`, `Số chỗ trống Label - Number (3)`), Wireframe `image14.png`.
- **Issue / Description**:
  - A single sample wireframe illustrates 10 floors and 108 slots per floor, whereas Frontend supports dynamic floor/zone creation (`"+ Thêm tầng"`, `"+ Thêm khu"`).
- **Proposed Default / Resolution**: **RESOLVED (`TL-02`)**: Replaced integer `floor_number`/`slot_number` columns with normalized `parking_lot`, `parking_floor` (`code VARCHAR(20)`, e.g. `B1..B3, F1`), `parking_zone` (`code VARCHAR(20)`, e.g. `A..C`), and `parking_slot` (`code VARCHAR(20)` referencing `zone_id` via `fk_slot_zone`).
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-55: Customer Actor Taxonomy and Portal Account Linkage

- **Priority / Status**: RESOLVED (`TL-01`)
- **Sources**:
  - Frontend `login-container.png` (`Chưa có tài khoản? Đăng ký ngay`).
  - SRS Section 3 Actor List, SRS 4.5.2 Row 8, Plan `Tasks_Sprint_1` Task 10.
- **Issue / Description**:
  - SRS actor table lists only 2 actors, whereas SRS 4.5.2 and Frontend `login-container.png` (`"Đăng ký ngay"`) include `CUSTOMER`.
- **Proposed Default / Resolution**: **RESOLVED (`TL-01`)**: `account.role` includes `'CUSTOMER'` and `customer.account_id` links to `account (id)` (`uq_customer_account_active`). Self-registration via `"Đăng ký ngay"` creates a `CUSTOMER` account + `customer` row.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-56: Decoupled Architecture for Employee Profiles and System Credentials

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.1 Login Table (`ACCOUNT.TenDangNhap`, `ACCOUNT.MatKhau`).
  - SRS 4.3.2 Add Employee Row 14 (`Thiết lập mặc định mật khẩu nhân viên`).
  - SRS 4.3.3 Edit Employee Table.
- **Issue / Description**:
  - SRS couples employee profile creation and default password generation within a single screen (4.3.2), but login verifies against `ACCOUNT`.
  - Design Question: Should `employee.account_id` be `NOT NULL` (strict coupling) or `NULL` (decoupled architecture)?
  - Rationale for Decoupling: Under the Separation of Concerns (SoC) principle, human resource records (`employee`) represent physical personnel, while `account` represents security access principals. Parking facilities employ staff (e.g. outdoor attendants, sweepers, maintenance crew) who do not need software access; enforcing `NOT NULL` would generate dormant attack surface accounts. Furthermore, if an employee is suspended or their credentials revoked (`account.is_active = FALSE` or `account_id = NULL`), their HR profile and audit history must remain intact. Finally, nullability eliminates circular foreign key dependency during database bootstrap.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT (`TL-15`)**: Maintain separate `account` and `employee` tables linked via `employee.account_id BIGINT NULL REFERENCES account(id) ON DELETE RESTRICT`, paired with a partial unique index `uq_employee_account_active` on `(account_id) WHERE deleted_at IS NULL AND account_id IS NOT NULL` guaranteeing 1-to-1 association.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-57: Lookup Seed Data Provenance and Taxonomy Verification

- **Priority / Status**: RESOLVED (`TL-02`, `TL-09`, `TL-10`, `TL-11`, `TL-15`)
- **Sources**:
  - Frontend `Quản lý nhân viên - Smart mobility.png` (4 positions), `Quản lý xe — Smart Mobility.png` (3 vehicle types), `Quản lý vé — Smart Mobility.png` (ticket types & prices), `Sơ đồ bãi đậu xe — Smart Mobility.png` (`Bãi xe Smart Mobility`).
  - SRS Wireframe `image6.png` (`Quảng Nam`, `Điện Bàn`, `Điện Ngọc`).
- **Issue / Description**:
  - Earlier Schema v1 seeds followed SRS wireframes (`Bảo vệ`, `Giữ xe`, `10.000đ` / `100.000đ`), whereas Frontend defines a primary lookup taxonomy.
- **Proposed Default / Resolution**: **RESOLVED (`TL-02`, `TL-09`, `TL-10`, `TL-11`, `TL-15`)**: In `db/02-seed.sql`, seed Frontend-first reference rows: 4 positions (`QL` `"Quản lý"`, `NVVH` `"Nhân viên vận hành"`, `NVTN` `"Nhân viên thu ngân"`, `KTV` `"Kỹ thuật viên"`), 3 vehicle types (`CAR` `"Ô tô"`, `MOTO` `"Xe máy"`, `EV` `"Xe điện"`), 4 ticket types (`DAILY` `"Vé ngày"` `50000.00`, `MONTHLY` `"Vé tháng"` `500000.00`, `QUARTERLY` `"Vé quý"` `1200000.00`, `YEARLY` `"Vé năm"` `4800000.00` `[PROPOSAL]` `OQ-79`), 1 facility (`SMART_MOBILITY` `"Bãi xe Smart Mobility"`), and SRS administrative hierarchy rows (`Đà Nẵng`, `Quảng Nam`, `Hải Châu`, `Điện Bàn`, `Hải Châu I`, `Điện Ngọc`).
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-58: Ticket Renewal Tariff and Price Mutation Audit History

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.6.3 Edit/Renew Ticket Table, Rows 12-16 (`image17.png`) & Frontend `Quản lý vé — Smart Mobility.png` (`Gia hạn vé`, `Chi tiết vé`).
  - Table `ticket_renewal`.
- **Issue / Description**:
  - Renewal screen allows altering ticket type, floor/slot, billed renewal price, and notes (`Ghi chú`) when extending duration.
- **Proposed Default / Resolution**: **RESOLVED (`TL-10`, `TL-15`)**: Retain `old_ticket_type_id`, `new_ticket_type_id`, `old_price`, `new_price`, `additional_price`, and add `notes TEXT NULL` on `ticket_renewal`.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-59: Parking Slot Code Uniqueness Scoped per Zone

- **Priority / Status**: RESOLVED (`TL-02`)
- **Sources**:
  - Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` & `Quản lý vé — Smart Mobility.png` (`Tầng B1 - A10`, `Tầng B2 - B12`).
  - Wireframe 4.8.1 (`image21.png`) & 4.8.3 (`image23.png`).
- **Issue / Description**:
  - Identical slot codes (e.g., `A-01`) can exist across different zones/floors within a facility.
- **Proposed Default / Resolution**: **RESOLVED (`TL-02`)**: Enforce zone-scoped active uniqueness via `CREATE UNIQUE INDEX uq_parking_slot_zone_code_active ON parking_slot (zone_id, code) WHERE deleted_at IS NULL;`.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-60: Vehicle Barrier Gate Camera In/Out Photography Storage

- **Priority / Status**: RESOLVED (`TL-06`)
- **Sources**:
  - Frontend `Trang chủ — Smart Mobility.png` (`Xem ảnh (99%)`, `Ảnh khớp`, `Cần duyệt`), `Lịch sử ra/vào — Smart Mobility.png` (`Hình ảnh đối soát`).
  - Wireframe 4.5.1 Vehicle In/Out (`image13.png`).
- **Issue / Description**:
  - Sessions record entry/exit camera snapshots alongside AI plate recognition confidence and review state.
- **Proposed Default / Resolution**: **RESOLVED (`TL-06`, `TL-15`)**: Provision `entry_image_url TEXT NULL`, `exit_image_url TEXT NULL`, `entry_gate_id`, `exit_gate_id`, `ai_confidence NUMERIC(5,2) NULL`, `recognition_source`, and `review_status` on `vehicle_entry_exit_log`.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-61: Referential Integrity Guard Between Vehicle and Customer on Ticket

- **Priority / Status**: Blocker
- **Sources**:
  - SRS 4.6.1 Ticket List & SRS 4.6.2 Add Ticket (`image16.png`).
  - Table `ticket` foreign keys.
- **Issue / Description**:
  - In screen 4.6.2, selecting customer code populates customer name and restricts vehicle selection to vehicles owned by that customer.
  - Lacking composite constraint, database previously permitted creating a ticket referencing Customer A with Vehicle owned by Customer B.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT (`TL-15`)**: Enforce `CONSTRAINT uq_vehicle_id_customer UNIQUE (id, customer_id)` on `vehicle` and composite foreign key `CONSTRAINT fk_ticket_vehicle_customer FOREIGN KEY (vehicle_id, customer_id) REFERENCES vehicle (id, customer_id) ON DELETE RESTRICT` on `ticket`.
- **Authority / Owner**: **Team Lead**

### OQ-62: Multi-Level Administrative Hierarchy Validation on Employee & Customer

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.3.2 Wireframe `image5.png` & SRS 4.4.3 Wireframe `image10.png`.
  - Law No. 72/2025/QH15 (Art. 1 Cl. 1, Art. 51 Cl. 1 & Cl. 3) & Resolution No. 202/2025/QH15 (Art. 1 Cl. 10 & Cl. 24, Art. 2 Cl. 1 & Cl. 2).
  - Tables `employee`, `customer`.
- **Issue / Description**:
  - Employee and Customer forms feature 3 cascading dropdowns (`Quảng Nam` -> `Điện Bàn` -> `Điện Ngọc`).
  - Independent foreign keys (`province_id`, `district_id`, `ward_id`) without composite cross-checks would allow invalid parent-child combinations.
  - Although Vietnam transitioned to 2 local government levels from `01-07-2025` under Law 72/2025/QH15 and merged Quảng Nam into Đà Nẵng under Resolution 202/2025/QH15, the 3-table hierarchy is retained as a defensive `[PROPOSAL]` (`OQ-50`).
- **Proposed Default / Resolution**: **PROPOSED DEFAULT (`TL-15`)**: Enforce `CONSTRAINT uq_admin_district_id_province UNIQUE (id, province_id)` on `administrative_district`, `CONSTRAINT uq_admin_ward_id_district UNIQUE (id, district_id)` on `administrative_ward`, and composite foreign keys on `employee` and `customer` (`(district_id, province_id)` and `(ward_id, district_id)`).
- **Authority / Owner**: **Team Lead**

### OQ-63: Real-Time Derived Status Synchronization & Disclosure of Extended Slot Statuses

- **Priority / Status**: RESOLVED (`TL-03`, `TL-04`, `TL-14`)
- **Sources**:
  - Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` (`Trống`, `Có xe`, `Đặt trước`, `Bảo trì`) & `Trang chủ — Smart Mobility.png` (`Lấp đầy theo khu/tầng`).
  - SRS 4.5.2 Parking Map & SRS 4.6.1 Ticket Lifecycle.
  - View `v_slot_occupancy_by_floor`.
- **Issue / Description**:
  - Frontend explicitly renders all 4 slot statuses (`Trống` -> `AVAILABLE`, `Có xe` -> `OCCUPIED`, `Đặt trước` -> `RESERVED`, `Bảo trì` -> `MAINTENANCE`) and manual status override buttons.
- **Proposed Default / Resolution**: **RESOLVED (`TL-03`, `TL-04`, `TL-14`)**: (1) Keep `parking_slot.status IN ('AVAILABLE', 'OCCUPIED', 'RESERVED', 'MAINTENANCE')`; entering or reserving a maintenance slot raises `'Vị trí này đang bảo trì.'` (`PROP-4.5.2-P01`). (2) `fn_guard_parking_slot_status()` blocks manual status changes that contradict open sessions or active tickets/reservations (`PROP-4.5.2-P02`..`P04`, `OQ-81`). (3) `fn_recompute_slot_status()` and `v_slot_occupancy_by_floor` synchronize and report live occupancy across open sessions, active tickets, and active `slot_reservation` rows.
- **Authority / Owner**: **Team Lead**

### OQ-64: Optimistic Concurrency Control Triggers and Ticket Soft-Delete Guard

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.3.1 ("Dữ liệu hiện đang được cập nhật bởi user khác").
  - SRS 4.6.4 ("chỉ cho phép xóa những vé nào đã quá hạn và không gia hạn").
  - ADR-0003 & Rule 05.
- **Issue / Description**:
  - `row_version` and `updated_at` previously remained static on SQL UPDATE, rendering OCC ineffective at DB level.
  - Ticket deletion lacked database guard preventing premature deletion of active tickets.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT (`TL-15`)**: (1) Attach `BEFORE UPDATE` trigger `fn_update_row_version_and_timestamp()` across all `17` mutable versioned tables. (2) Enforce `CONSTRAINT ck_ticket_delete_only_expired CHECK (deleted_at IS NULL OR effective_to <= deleted_at)` on `ticket`.
- **Authority / Owner**: **Team Lead**

### OQ-65: Beyond-SRS Constraint Justifications, Literal SRS Gender & Visitor Vehicle Policy

- **Priority / Status**: RESOLVED (`TL-05`, `TL-11`, `TL-15`)
- **Sources**:
  - Frontend `Lịch sử ra\vào — Smart Mobility.png` (`Khách hàng: Đã đăng ký / Khách vãng lai`), `Quản lý nhân viên - Smart mobility.png` (`NV001`, `NV0005`).
  - SRS 4.3.2 (`Nam`, `Nữ`) & SRS 4.5.1 (`MSG-4.5.1-M02`).
- **Issue / Description**:
  - Frontend explicitly supports unregistered walk-in vehicles (`Khách vãng lai`) in `Lịch sử ra/vào` and both 3-digit and 4-digit employee codes (`NV001`, `NV0005`).
- **Proposed Default / Resolution**: **RESOLVED (`TL-05`, `TL-11`, `TL-15`)**: (1) **Visitor Vehicles Permitted (`TL-05`)**: `vehicle_entry_exit_log.vehicle_id` is `BIGINT NULL`; when `vehicle_id IS NOT NULL`, `fn_guard_slot_reservation_on_entry()` verifies normalized plate match and raises `'Lỗi dữ liệu không tìm thấy đê lưu'` (`MSG-4.5.1-M02`) on mismatch; (2) **Literal SRS Gender (`TL-15`)**: Keep `CHECK (gender IN ('Nam', 'Nữ'))` on `employee` and `customer`; (3) **Code Formats (`TL-11`, `TL-15`)**: `employee.code` enforces `CHECK (code ~ '^NV[0-9]{3,4}$')`; other business codes enforce `^[A-Za-z0-9-]+$`.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-66: Open Parking Session Partial Unique Indexes & Double-Entry Prevention

- **Priority / Status**: RESOLVED (`TL-05`, `TL-15`)
- **Sources**:
  - Frontend `Lịch sử ra\vào — Smart Mobility.png` & SRS 4.5.1.
  - [`db/01-schema.sql`](../../db/01-schema.sql) lines 1343–1353 (`uq_log_open_session_slot`, `uq_log_open_session_vehicle`, `uq_log_open_session_plate`).
- **Issue / Description**:
  - Without database guards, a single vehicle or license plate could open multiple concurrent parking sessions, or two vehicles could occupy the same physical slot simultaneously.
- **Proposed Default / Resolution**: **RESOLVED (`TL-05`, `TL-15`)**: Enforce 3 partial unique indexes on `vehicle_entry_exit_log`: (1) `uq_log_open_session_slot ON vehicle_entry_exit_log (slot_id) WHERE exit_time IS NULL AND slot_id IS NOT NULL`; (2) `uq_log_open_session_vehicle ON vehicle_entry_exit_log (vehicle_id) WHERE exit_time IS NULL AND vehicle_id IS NOT NULL`; (3) `uq_log_open_session_plate ON vehicle_entry_exit_log (license_plate_norm) WHERE exit_time IS NULL`.
- **Authority / Owner**: **Team Lead**

### OQ-67: Slot Reservation Guard and Maintenance Slot Protection on Entry & Update

- **Priority / Status**: RESOLVED (`TL-03`, `TL-04`, `TL-05`)
- **Sources**:
  - Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` & `Lịch sử ra\vào — Smart Mobility.png`.
  - SRS 4.5.2 Row 14 (`MSG-4.5.2-M02: Vị trí này đã có xe đk vé và đang sử dụng`).
  - [`db/01-schema.sql`](../../db/01-schema.sql): `fn_guard_slot_reservation_on_entry()` & `trg_guard_slot_reservation_on_entry`.
- **Issue / Description**:
  - Barrier check-in and slot reassignment must prevent occupying maintenance slots, slots reserved by another vehicle's active ticket, or slots reserved via `slot_reservation` for another vehicle.
- **Proposed Default / Resolution**: **RESOLVED (`TL-03`, `TL-04`, `TL-05`)**: `trg_guard_slot_reservation_on_entry` (`BEFORE INSERT OR UPDATE OF slot_id, exit_time, vehicle_id, license_plate ON vehicle_entry_exit_log`) locks the target slot (`FOR NO KEY UPDATE`), rejects `MAINTENANCE` slots with `'Vị trí này đang bảo trì.'` (`PROP-4.5.2-P01`), rejects active `ticket` conflicts with verbatim `'Vị trí này đã có xe đk vé và đang sử dụng'` (`MSG-4.5.2-M02`), and rejects active `slot_reservation` conflicts with `'Vị trí này đã được đặt trước cho phương tiện khác.'` (`PROP-4.5.2-P05`, `OQ-81`).
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-68: Employee Working Time & Shift Scheduling Scope OQ

- **Priority / Status**: Important
- **Sources**:
  - SRS Section 2.2 Main Functions list, bullet 4 (`Quản lý thời gian làm việc của nhân viên, hệ thống admin`).
  - SRS Section 4 (Modules 4.1 to 4.8).
- **Issue / Description**:
  - SRS Section 2.2 explicitly lists "Quản lý thời gian làm việc của nhân viên, hệ thống admin" as a core system feature in high-level scope.
  - However, across both the 11 Frontend screens and SRS Section 4 (Modules 4.1 through 4.8), there are zero screens or fields specifying employee shifts or timesheets.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Employee working time / shift scheduling remains out of scope for Sprint 1 because neither the Frontend nor SRS Section 4 defines screens or fields for shifts.
- **Authority / Owner**: **Product Owner**

### OQ-69: Floor Map Slot 2D Geometric Grid Coordinates (`map_row`, `map_col`)

- **Priority / Status**: RESOLVED (`TL-02`, `TL-15`)
- **Sources**:
  - Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` & Wireframe 4.5.2 (`image14.png`).
  - Table `parking_slot`.
- **Issue / Description**:
  - Floor/zone map layouts render slots on a 2D spatial grid.
- **Proposed Default / Resolution**: **RESOLVED (`TL-02`, `TL-15`)**: Retain optional `map_row SMALLINT NULL` and `map_col SMALLINT NULL` on `parking_slot` with `ck_slot_map_coords_pair` and zone-scoped partial unique index `uq_parking_slot_zone_map_pos_active ON parking_slot (zone_id, map_row, map_col) WHERE deleted_at IS NULL AND map_row IS NOT NULL AND map_col IS NOT NULL`.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-70: Duplicate License Plate Sample Data in SRS Wireframes (`92D1-1234`)

- **Priority / Status**: Nice-to-know
- **Sources**:
  - Wireframe 4.4.1 Customer List (`image9.png`) & Wireframe 4.4.4 Edit Customer (`image10.png`).
  - Table `vehicle`.
- **Issue / Description**:
  - SRS wireframes `image9.png` and `image10.png` show sample vehicles `Xe-001` and `Xe-002` both carrying the identical license plate `92D1-1234`.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT (`TL-15`)**: Enforce active normalized license plate uniqueness via `CREATE UNIQUE INDEX uq_vehicle_license_plate_active ON vehicle (license_plate_norm) WHERE deleted_at IS NULL;` (`OQ-75`).
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-71: Login Identifier (`Email/SĐT` vs `Tên đăng nhập`) & Self-Registration Link (`Đăng ký ngay`)

- **Priority / Status**: Blocker — `status = resolved & implemented (TL-01)`
- **Sources**:
  - Frontend `login-container.png` (`Email hoặc Số điện thoại`, `Chưa có tài khoản? Đăng ký ngay`).
  - SRS 4.1 (`image2.png` Row 5: `Tên đăng nhập`, `MSG-4.1-M03`).
  - [`db/01-schema.sql`](../../db/01-schema.sql) lines 47–84 (`account.email`, `account.phone`, `ck_account_login_identifier_present`, `uq_account_email_active`, `uq_account_phone_active`).
  - [`06-frontend-srs-db-alignment.md`](06-frontend-srs-db-alignment.md) (`TL-01`).
- **Issue / Description**:
  - `login-container.png` authenticates via `"Email hoặc Số điện thoại"` and provides `"Chưa có tài khoản? Đăng ký ngay"`, whereas SRS 4.1 specified `username`.
- **Proposed Default / Resolution**: **RESOLVED & IMPLEMENTED (`TL-01`, Round 23)**: Replaced `account.username` with `email VARCHAR(100) NULL` and `phone VARCHAR(15) NULL` (`ck_account_login_identifier_present CHECK (num_nonnulls(email, phone) >= 1)`), added active partial unique indexes on `email` and `phone`, and kept `role IN ('MANAGER', 'EMPLOYEE', 'CUSTOMER')` so self-registration creates a `CUSTOMER` account + `customer` row.
- **Authority / Owner**: **Owner & Team Lead**

### OQ-72: Per-Session Fees (`Cước phí`), Payment Methods (`Tiền mặt`/`QR`/`VietQR`) & `Giao dịch` Module

- **Priority / Status**: Important — `status = resolved & implemented (TL-05, TL-07)`
- **Sources**:
  - Frontend `Lịch sử ra/vào — Smart Mobility.png` (`Cước phí`, `Mã phiên đỗ`, `Tổng thời gian đỗ`), `Trang chủ — Smart Mobility.png` (`Tiền mặt: 18% | QR: 82%`), `Main Page.png` (`VietQR`), `Quản lý xe — Smart Mobility.png` (`module Vé/Giao dịch`).
  - [`db/01-schema.sql`](../../db/01-schema.sql) lines 1287–1467 (`vehicle_entry_exit_log`, `payment`, `v_revenue_today_by_method`, `v_revenue_statistics`).
  - [`06-frontend-srs-db-alignment.md`](06-frontend-srs-db-alignment.md) (`TL-05`, `TL-07`).
- **Issue / Description**:
  - Frontend displays per-session `Cước phí`, `Mã phiên đỗ`, `Tiền mặt`/`QR`/`VietQR` payment splits, and references `module Vé/Giao dịch`.
- **Proposed Default / Resolution**: **RESOLVED & IMPLEMENTED (`TL-05`, `TL-07`, Round 23)**: Added `session_code VARCHAR(30) NOT NULL UNIQUE` and `fee_amount NUMERIC(12,2) NOT NULL DEFAULT 0` on `vehicle_entry_exit_log`; added `payment` table (`method IN ('CASH', 'VIETQR')`, `status IN ('UNPAID', 'PAID', 'CANCELLED', 'REFUNDED')`, `ck_payment_single_target CHECK (num_nonnulls(session_id, ticket_id, renewal_id) = 1)`); added `v_revenue_today_by_method`; and updated `v_revenue_statistics` and `fn_stat_revenue_by_period`.
- **Authority / Owner**: **Owner & Team Lead**

### OQ-73: Floor Naming (`B1..B3, F1` vs `INTEGER 1..99`) & Multi-Lot / Zone Tables (`Bãi xe`, `Khu A..C`)

- **Priority / Status**: Important — `status = resolved & implemented (TL-02)`
- **Sources**:
  - Frontend `Main Page.png`, `Trang chủ — Smart Mobility.png`, `Sơ đồ bãi đậu xe — Smart Mobility.png`, `Quản lý vé — Smart Mobility.png` (`Tầng B1..B3, F1`, `Bãi xe Smart Mobility`, `Khu A..C`, `+ Thêm tầng`, `+ Thêm khu`, `Quản lý cấu trúc bãi`).
  - [`db/01-schema.sql`](../../db/01-schema.sql) lines 742–964 (`parking_lot`, `parking_floor`, `parking_zone`, `parking_slot`).
  - [`06-frontend-srs-db-alignment.md`](06-frontend-srs-db-alignment.md) (`TL-02`).
- **Issue / Description**:
  - Frontend organizes parking into `parking_lot` (`"Bãi xe Smart Mobility"`), `parking_floor` (`"Tầng B1..B3, F1"`), `parking_zone` (`"Khu A..C"`), and `parking_slot` (`"A-01"`, `"B-01"`).
- **Proposed Default / Resolution**: **RESOLVED & IMPLEMENTED (`TL-02`, Round 23)**: Added `parking_lot`, `parking_floor`, and `parking_zone`; updated `parking_slot` to reference `zone_id` via `fk_slot_zone FOREIGN KEY (zone_id) REFERENCES parking_zone (id) ON DELETE RESTRICT` with `code VARCHAR(20) NOT NULL` (`uq_parking_slot_zone_code_active`) while keeping `map_row`, `map_col`, `width`, `length`, and `height`.
- **Authority / Owner**: **Owner & Team Lead**

### OQ-74: Frontend Operational Features (EV, Priority Slots, Blacklist/Debt, Gates, AI Confidence, Extra `Ghi chú`, Activity Feed)

- **Priority / Status**: Important — `status = resolved & implemented (TL-03, TL-04, TL-06, TL-08, TL-12, TL-13)`
- **Sources**:
  - Frontend `Main Page.png`, `Trang chủ — Smart Mobility.png`, `Khách hàng — Smart Mobility.png`, `Quản lý xe — Smart Mobility.png`, `Sơ đồ bãi đậu xe — Smart Mobility.png`, `Quản lý vé — Smart Mobility.png`, `Lịch sử ra/vào — Smart Mobility.png`.
  - [`db/01-schema.sql`](../../db/01-schema.sql) and [`06-frontend-srs-db-alignment.md`](06-frontend-srs-db-alignment.md) (`TL-03`, `TL-04`, `TL-06`, `TL-08`, `TL-12`, `TL-13`).
- **Issue / Description**:
  - Frontend defines EV charging (`Sạc xe điện`), priority lanes (`XE ƯU TIÊN`), slot reservations (`Đặt trước`), blacklist/debt alerts (`Blacklist/Tạm khoá`, `Nợ phí`), gate names (`Cổng vào 1/2`, `Cổng ra 1/2/3`), AI recognition confidence (`98.4%`, `Ảnh khớp`/`Cần duyệt`), `Ghi chú` on `ticket`/`ticket_renewal`/`vehicle`/`parking_slot`, `Hoạt động gần đây` activity feed, and `Cảnh báo bất thường và khẩn cấp`.
- **Proposed Default / Resolution**: **RESOLVED & IMPLEMENTED (`TL-03`, `TL-04`, `TL-06`, `TL-08`, `TL-12`, `TL-13`, Round 23)**: Added `slot_kind` (`STANDARD`, `PRIORITY`, `EV_CHARGING`), `status` (`CHARGING`), and `notes` on `parking_slot`; added `slot_reservation`, `parking_gate`, `plate_blacklist`, `activity_log`, and `system_alert`; added `status` and `status_reason` on `customer`; added `image_url` and `notes` on `vehicle`; added `notes` on `ticket` and `ticket_renewal`; and added AI recognition columns on `vehicle_entry_exit_log`.
- **Authority / Owner**: **Owner & Team Lead**

### OQ-75: License-Plate Punctuation (`51K-992.14` vs `51K-992-14`) & Canonical DB Normalization

- **Priority / Status**: Blocker — `status = resolved & implemented (TL-05, TL-08, TL-09, TL-15)`
- **Sources**:
  - Frontend `Quản lý xe — Smart Mobility.png` & `Trang chủ — Smart Mobility.png` (`51K-992.14`, `30A-123.45`) vs `Quản lý vé — Smart Mobility.png` (`51K-992-14`, `30A-123-45`).
  - [`db/01-schema.sql`](../../db/01-schema.sql) (`fn_normalize_license_plate`, `vehicle.license_plate_norm`, `vehicle_entry_exit_log.license_plate_norm`, `plate_blacklist.license_plate_norm`).
  - [`06-frontend-srs-db-alignment.md`](06-frontend-srs-db-alignment.md) (`TL-05`, `TL-08`, `TL-09`, `TL-15`).
- **Issue / Description**:
  - Frontend displays the same vehicle `XE0001` (`KH0001`) as `51K-992.14` (dot) on `Quản lý xe` and as `51K-992-14` (hyphen) on `Quản lý vé` (`VT0001`).
- **Proposed Default / Resolution**: **RESOLVED & IMPLEMENTED (`TL-05`, `TL-08`, `TL-09`, `TL-15`)**: Retained `IMMUTABLE STRICT PARALLEL SAFE` SQL function `fn_normalize_license_plate(p_input TEXT)` and stored generated column `license_plate_norm` on `vehicle` and `vehicle_entry_exit_log`, and extended `license_plate_norm` (`uq_plate_blacklist_norm_active`) to `plate_blacklist`.
- **Authority / Owner**: **Owner & Team Lead**

### OQ-76: Ticket/Vehicle/Position Taxonomy, Tariff Seeds, Derived Statuses & Same-Day Ticket Timestamps

- **Priority / Status**: Important — `status = resolved & implemented (TL-09, TL-10, TL-11)`
- **Sources**:
  - Frontend `Quản lý vé — Smart Mobility.png`, `Quản lý xe — Smart Mobility.png`, `Quản lý nhân viên - Smart mobility.png`.
  - [`db/01-schema.sql`](../../db/01-schema.sql) & [`db/02-seed.sql`](../../db/02-seed.sql).
  - [`06-frontend-srs-db-alignment.md`](06-frontend-srs-db-alignment.md) (`TL-09`, `TL-10`, `TL-11`).
- **Issue / Description**:
  - Frontend defines 4 staff positions (`Quản lý`, `Nhân viên vận hành`, `Nhân viên thu ngân`, `Kỹ thuật viên`), 3 vehicle types (`Ô tô`, `Xe máy`, `Xe điện`), 4 ticket types (`Vé ngày` `50k`, `Vé tháng` `500k`, `Vé quý` `1.2M`, `Vé năm`), ticket status `"Đang gia hạn"` (`RENEWING`) and derived `"Sắp hết hạn"`, employee status `"Không hoạt động"` (`INACTIVE`), and same-day 1-day ticket dates (`VT0002` `10/5/2026`–`10/5/2026`).
- **Proposed Default / Resolution**: **RESOLVED & IMPLEMENTED (`TL-09`, `TL-10`, `TL-11`, Round 23)**: Seeded `position` (4 rows: `QL`, `NVVH`, `NVTN`, `KTV`), `vehicle_type` (3 rows: `CAR`, `MOTO`, `EV`), and `ticket_type` (4 rows: `DAILY`, `MONTHLY`, `QUARTERLY`, `YEARLY`) in `db/02-seed.sql`; added `'RENEWING'` to `ck_ticket_status_enum` and `employee.status IN ('ACTIVE', 'INACTIVE')`; kept `"Sắp hết hạn"` and vehicle parking status (`"Đang đỗ"` / `"Đã rời bãi"`) derived; and stored 1-day tickets as half-open intervals `[effective_from, effective_from + INTERVAL '1 day')`.
- **Authority / Owner**: **Owner & Team Lead**

### OQ-77: Manual Slot Status Override Buttons vs Trigger-Managed Slot Status

- **Priority / Status**: Important — `status = resolved & implemented (TL-03, TL-04)`
- **Sources**:
  - Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` (`Chi tiết ô đỗ`: manual buttons `Đánh dấu trống`, `Đánh dấu có xe`, `Đánh dấu đặt trước`, `Đánh dấu bảo trì`).
  - [`db/01-schema.sql`](../../db/01-schema.sql) lines 1755–2088 (`fn_guard_parking_slot_status`, `trg_guard_parking_slot_status`, `fn_recompute_slot_status`).
  - [`06-frontend-srs-db-alignment.md`](06-frontend-srs-db-alignment.md) (`TL-03`, `TL-04`).
- **Issue / Description**:
  - Frontend provides manual slot status buttons (`Đánh dấu trống`, `Đánh dấu có xe`, `Đánh dấu đặt trước`, `Đánh dấu bảo trì`), which must not desynchronize `parking_slot.status` from open sessions or active tickets/reservations.
- **Proposed Default / Resolution**: **RESOLVED & IMPLEMENTED (`TL-03`, `TL-04`, Round 23)**: Added `fn_guard_parking_slot_status()` (`BEFORE UPDATE OF status ON parking_slot`) to block changing an occupied slot away from `OCCUPIED` while an open session exists (`PROP-4.5.2-P02`), block manually setting `OCCUPIED` without an open session (`PROP-4.5.2-P03`), and block manually setting `AVAILABLE` while an active ticket or active reservation exists (`PROP-4.5.2-P04`), while `fn_recompute_slot_status()` automatically synchronizes slot state across sessions, tickets, and reservations.
- **Authority / Owner**: **Owner & Team Lead**

### OQ-78: ERD Module Diagram Completeness (`F27`), Intentional Stub Layout (`F28`) & Master Legend Count (`F31`)

- **Priority / Status**: Important — `status = implemented for Schema v1 (Rounds 19 & 21); Schema v2 ERD regeneration scheduled for Round 24`
- **Sources**:
  - [`db/03-erd.asta`](../../db/03-erd.asta) and [`db/04-erd.png`](../../db/04-erd.png)–[`db/09-erd-reference-views.png`](../../db/09-erd-reference-views.png).
  - [`db/00-README.md`](../../db/00-README.md).
- **Issue / Description**:
  - Rounds 19 and 21 completed all ERD diagram links, orthogonal routing, and legend counts for Schema v1 (`19` tables, `4` views, `44` FKs). Following the Round 23 rework to Schema v2 (`28` tables, `8` views, `69` FKs), the Astah UML model and exported PNG diagrams require regeneration.
- **Proposed Default / Resolution**: **SCHEDULED FOR ROUND 24**: Keep `db/03-erd.asta` and `db/04-erd.png`..`db/09-erd-reference-views.png` untouched in Round 23 and regenerate all ERD diagrams for Schema v2 in Round 24.
- **Authority / Owner**: **Owner & Team Lead**

### OQ-79: Year Ticket Default Tariff (`4.800.000đ` vs Annual Discount)

- **Priority / Status**: Important — `status = open [PROPOSAL]`
- **Sources**:
  - Frontend `Quản lý vé — Smart Mobility.png` (`Vé ngày` `50.000đ`, `Vé tháng` `500.000đ`, `Vé quý` `1.200.000đ`) & `Quản lý xe — Smart Mobility.png` (`Vé năm`).
  - SRS 4.6.1 & 4.7.1 (`Tháng / Quý / Năm`).
  - [`db/02-seed.sql`](../../db/02-seed.sql) (`ticket_type` code `'YEARLY'`, `default_price = 4800000.00`).
- **Issue / Description**:
  - Frontend `Quản lý vé — Smart Mobility.png` explicitly shows prices for `Vé ngày` (`50.000đ`), `Vé tháng` (`500.000đ`), and `Vé quý` (`1.200.000đ`), while `Quản lý xe — Smart Mobility.png` (`XE0005`) and SRS 4.6/4.7 also include `Vé năm` (`YEARLY`, `365` days) without a Frontend-confirmed annual tariff.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT `[PROPOSAL]` (`TL-10`, `OQ-79`)**: Seed `YEARLY` (`"Vé năm"`, `365` days) with `default_price = 4800000.00` (`1.200.000đ × 4` quarters) pending Product Owner confirmation of whether an annual discount applies.
- **Authority / Owner**: **Product Owner**

### OQ-80: Per-Session Parking Tariff Rules (Hourly/Daily Rate by Vehicle Type, Grace Period & Overstay Fee)

- **Priority / Status**: Important — `status = open [PROPOSAL]`
- **Sources**:
  - Frontend `Lịch sử ra/vào — Smart Mobility.png` (`Cước phí`: `0đ`), `Trang chủ — Smart Mobility.png` (`Cảnh báo đỗ xe quá 48 giờ tại vị trí B2 - 55`).
  - [`db/01-schema.sql`](../../db/01-schema.sql) (`vehicle_entry_exit_log.fee_amount`).
- **Issue / Description**:
  - Frontend displays per-session `Cước phí` and alerts on vehicles parked over `48` hours, but neither the Frontend nor the SRS defines the exact calculation formula (hourly vs block tariff by `CAR`/`MOTO`/`EV`, free grace minutes, overnight surcharge, or overstay penalty).
- **Proposed Default / Resolution**: **PROPOSED DEFAULT `[PROPOSAL]` (`TL-05`, `TL-07`, `OQ-80`)**: Store computed session fee in `vehicle_entry_exit_log.fee_amount NUMERIC(12,2) NOT NULL DEFAULT 0` (`0` when covered by an active ticket) and await Product Owner confirmation of the exact per-session tariff schedule and overstay fee formula.
- **Authority / Owner**: **Product Owner**

### OQ-81: Status Value Lists & Database Guard Messages Not Shown in the Frontend

- **Priority / Status**: Important — `status = open [PROPOSAL]`
- **Sources**:
  - [`db/01-schema.sql`](../../db/01-schema.sql) (`ck_reservation_status_enum`, `ck_payment_status_enum`, `ck_alert_type_enum`, `ck_alert_severity_enum`, `ck_log_recognition_source_enum`, `ck_log_review_status_enum`, `fn_guard_parking_slot_status`, `fn_guard_slot_reservation_on_entry`, `fn_prevent_activity_log_mutation`).
  - [`docs/requirements/05-proposed-messages.md`](05-proposed-messages.md) (`PROP-4.5.2-P02`–`PROP-4.5.2-P06`).
- **Issue / Description**:
  - While the Frontend shows UI badges such as `"Đặt trước"`, `"Ảnh khớp"`, and `"Cần duyệt"`, it does not enumerate every internal lifecycle code for `slot_reservation.status`, `payment.status`, `system_alert.severity`, or `vehicle_entry_exit_log.review_status` / `recognition_source`, nor does it specify verbatim error strings when manual slot status overrides, slot reservations, or `activity_log` mutations are rejected.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT `[PROPOSAL]` (`TL-03`, `TL-04`, `TL-06`, `TL-07`, `TL-12`, `TL-13`, `OQ-81`)**: Enforce `slot_reservation.status IN ('ACTIVE', 'FULFILLED', 'EXPIRED', 'CANCELLED')`, `payment.status IN ('UNPAID', 'PAID', 'CANCELLED', 'REFUNDED')`, `system_alert.alert_type IN ('BLACKLIST_PLATE', 'OVERSTAY', 'CAMERA_QUALITY', 'SYSTEM')`, `system_alert.severity IN ('INFO', 'WARNING', 'CRITICAL')`, `vehicle_entry_exit_log.recognition_source IN ('AI', 'MANUAL')`, and `vehicle_entry_exit_log.review_status IN ('AUTO', 'MATCHED', 'NEEDS_REVIEW', 'APPROVED', 'REJECTED')`, and use proposed Vietnamese guard messages `PROP-4.5.2-P02`–`PROP-4.5.2-P06` pending Product Owner review.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-82: VietQR Payment Provider, Webhook Verification & Transfer Reference Format

- **Priority / Status**: Important — `status = open [PROPOSAL]`
- **Sources**:
  - Frontend `Main Page.png` (`VietQR`), `Trang chủ — Smart Mobility.png` (`Tiền mặt: 18% | QR: 82%`).
  - [`db/01-schema.sql`](../../db/01-schema.sql) (`payment.method`, `payment.provider_ref`).
- **Issue / Description**:
  - Frontend specifies `VietQR` / `QR` alongside `Tiền mặt`, but does not specify the acquiring bank/payment gateway, webhook signature verification protocol, or transfer narrative format stored in `payment.provider_ref`.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT `[PROPOSAL]` (`TL-07`, `OQ-82`)**: Provision `payment.method IN ('CASH', 'VIETQR')` and `payment.provider_ref VARCHAR(100) NULL` to store external transaction references or bank transfer narratives, pending Product Owner selection of the payment gateway provider.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-83: Camera & AI License-Plate Recognition Service Integration

- **Priority / Status**: Important — `status = open [PROPOSAL]`
- **Sources**:
  - Frontend `Trang chủ — Smart Mobility.png` (`Tỉ lệ AI nhận dạng: 98.4%`, `Xem ảnh (99%)`, `Ảnh khớp`, `Cần duyệt`), `Main Page.png` (`4 Cổng quét tự động`).
  - [`db/01-schema.sql`](../../db/01-schema.sql) (`parking_gate.camera_status`, `parking_gate.is_auto_scan`, `vehicle_entry_exit_log.ai_confidence`, `recognition_source`, `review_status`).
- **Issue / Description**:
  - Frontend displays AI OCR confidence percentages (`98.4%`, `99%`), automatic vs manual review states (`Ảnh khớp`, `Cần duyệt`), and gate camera status, but does not specify the OCR engine/edge device protocol or the exact confidence threshold separating `MATCHED` from `NEEDS_REVIEW`.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT `[PROPOSAL]` (`TL-06`, `OQ-83`)**: Store `ai_confidence NUMERIC(5,2) NULL`, `recognition_source`, and `review_status` on `vehicle_entry_exit_log` (with default threshold `ai_confidence >= 85.00` for `MATCHED` vs `NEEDS_REVIEW` in the application service layer) pending Product Owner confirmation.
- **Authority / Owner**: **Product Owner** & **Team Lead**
