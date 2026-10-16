# Open Questions, Contradictions, and Policy Catalog

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

- **Priority / Status**: Blocker
- **Sources**:
  - SRS 4.1, Login Table, Row 5.
  - SRS 4.3.2, Add Employee Table, Rows 5 & 10.
  - SRS 4.3.3, Edit Employee Table, Rows 10 & 11.
- **Issue / Description**:
  - Add Employee screen (4.3.2) defines `ID` (Alpha numeric 5) and `Họ tên`, but no `Tên đăng nhập` field.
  - Login screen (4.1) requires `Tên đăng nhập` (checked against `ACCOUNT.TenDangNhap`).
  - Unclear whether username is derived from ID, email, or a separate input. Default employee password is also unspecified (SRS only states "Thiết lập mặc định mật khẩu nhân viên").
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Default username is the Employee Code (`ID_NV`, e.g. `NV001`) or email prefix. Initial password is an auto-generated high-entropy string dispatched via email, or a temporary password requiring immediate change on first login conforming to complexity rules.
- **Authority / Owner**: **PO** (Business) & **Team Lead** (Technical)

### OQ-03: Actors & Permissions

- **Priority / Status**: Important
- **Sources**:
  - SRS Section 3 Actor List, Table, Rows 1-2.
  - SRS 4.5.2, Parking Map Table, Row 8.
  - Plan `Tasks_Sprint_1`, Row 12 (F12).
  - SRS Section 3 System Pages Flow (`image1.png`).
- **Issue / Description**:
  - SRS Section 3 defines only 2 Actors: `Quản lý` (Manager) and `Nhân viên` (Employee).
  - Section 4.5.2 mentions `Khách hàng` (Customer) clicking slots: "2. Đăng ký đỗ xe (quyền quản lý, khách hàng)".
  - Plan `Tasks_Sprint_1` F12 expands permissions to Employee as well: "1. Xem thông tin xe (quyền quản lý, nhân viên). 2. Đăng ký đỗ xe (quyền quản lý, nhân viên, khách hàng)".
  - Unclear if Customers have web application login accounts.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Maintain 3 distinct roles in database: `MANAGER`, `EMPLOYEE`, `CUSTOMER`. For current scope (Sprint 1), web system serves internal parking staff (`MANAGER` and `EMPLOYEE`). Customer slot registration is supported via API (ready for customer portal/mobile app) or registered by staff on behalf of customers.
- **Authority / Owner**: **PO**

### OQ-04: Address Text vs Dropdown

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.3.2, Row 7 (`Địa chỉ: String(45)`).
  - SRS 4.4.3, Row 8 (`Địa chỉ: String(45)`).
  - Wireframes `image5.png`, `image10.png`.
- **Issue / Description**:
  - SRS text specifies `Địa chỉ` as a free-form text field (`String(45)`).
  - Wireframes illustrate a 3-level dropdown selector for Province, District, and Ward.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Backend stores single `address` string conforming to SRS limit (max 45 characters). Backend accepts full concatenated address string. If frontend implements hierarchical dropdowns, it concatenates before dispatching or backend provides optional auxiliary fields (`province`, `district`, `ward`).
- **Authority / Owner**: **PO**

### OQ-05: Parking Slot Identifier

- **Priority / Status**: Important
- **Sources**:
  - Wireframe 4.5.2 (`image14.png`).
  - SRS 4.8.1, Slot List Table, Row 6.
  - Wireframe 4.8.1 (`image21.png`).
  - Wireframe 4.8.3 (`image23.png`).
- **Issue / Description**:
  - Parking map wireframe (`image14.png`) shows 10 floors with slots numbered integer `1` to `108`.
  - Slot list 4.8.1 and edit slot 4.8.3 wireframes display slot codes as `A-1, A-2, B-1...` (Section letter - Sequence number).
  - System lacks unified naming rule for slot codes.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Design `ParkingSlot` entity with 3 explicit attributes: `floor` (Integer 1..10), `slot_number` (Integer 1..108), and `slot_code` (Unique display identifier, e.g. `T01-A01`). Compatible with both numeric map slots and alphanumeric section layouts.
- **Authority / Owner**: **PO**

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

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.5.2 Parking Map Table (`Bản đồ tầng Button - Number (2)`, `Số chỗ trống Label - Number (3)`).
  - Wireframe 4.5.2 (`image14.png`: 10 floors, 108 slots per floor).
- **Issue / Description**:
  - A single sample wireframe illustrates 10 floors and 108 slots per floor.
  - Hardcoding `CHECK (floor_number BETWEEN 1 AND 10)` and `CHECK (slot_number BETWEEN 1 AND 108)` restricts enterprise scalability.
  - SRS specification native data types are `Number(2)` for floors and `Number(3)` for slot numbers.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Remove rigid 1..10 and 1..108 caps. Enforce boundary constraints based strictly on SRS data types: `CHECK (floor_number > 0 AND floor_number < 100)` (Number(2)) and `CHECK (slot_number > 0 AND slot_number < 1000)` (Number(3)). System accommodates multi-level facilities up to 99 floors and 999 slots per floor.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-55: Customer Actor Taxonomy and Portal Account Linkage

- **Priority / Status**: Important
- **Sources**:
  - SRS Section 3 Actor List (defines only Manager and Employee).
  - SRS 4.5.2 Row 8 ("Đăng ký đỗ xe (quyền quản lý, khách hàng)").
  - Plan `Tasks_Sprint_1` Task 10 ("quyền quản lý, nhân viên, khách hàng").
- **Issue / Description**:
  - SRS actor table lists only 2 actors, but parking map 4.5.2 explicitly mentions `Khách hàng` (Customer) role for slot registration.
  - The system provides no Customer Login wireframe or credential issuance form.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Declare `role = 'CUSTOMER'` in `account` and `customer.account_id` as an architectural **[PROPOSAL]** (OQ-55). For Sprint 1, internal staff perform slot registration on behalf of customers. The schema remains forward-compatible with external customer web/mobile self-service registration.
- **Authority / Owner**: **Product Owner**

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
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Maintain separate `account` and `employee` tables linked via `employee.account_id BIGINT NULL REFERENCES account(id) ON DELETE RESTRICT`, paired with a partial unique index `uq_employee_account_active` on `(account_id) WHERE deleted_at IS NULL AND account_id IS NOT NULL` guaranteeing 1-to-1 association. In the Django application service layer, creating an employee via screen 4.3.2 atomically provisions both the account (with default password) and the employee profile within an atomic database transaction.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-57: Lookup Seed Data Provenance and Taxonomy Verification

- **Priority / Status**: Important
- **Sources**:
  - Wireframe `image4.png`, `image5.png` (Positions: `Bảo vệ`, `Giữ xe`).
  - Wireframe `image15.png` (Ticket type: `Năm ... 100.000đ`).
  - Wireframe `image16.png` (Dropdown: `Tháng`, `Năm`).
  - Wireframe `image6.png` (`Quảng Nam`, `Điện Bàn`, `Điện Ngọc`).
- **Issue / Description**:
  - Previous seed data contained unverified items labeled "from SRS": position `Quản lý`, ticket type `Vé Ngày`, prices 1000000/10000, and locations `Hà Nội`, `Hải Châu`, `Cầu Giấy`.
  - Rigorous audit confirms only `Bảo vệ`, `Giữ xe`, `Vé Năm` (100,000 VND), `Quảng Nam`, `Điện Bàn`, `Điện Ngọc`, and address string `Đà Nẵng` genuinely exist in wireframes.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: In `db/02-seed.sql`, strictly retain genuine SRS wireframe items. Label position `Quản lý` as **[PROPOSAL] (OQ-57)** derived from SRS 3.1. Label ticket type `Vé Tháng` (100,000 VND) and `Vé Ngày` (10,000 VND) as **[PROPOSAL] (OQ-57)**. Exclude unevidenced administrative entities.
- **Authority / Owner**: **Product Owner**

### OQ-58: Ticket Renewal Tariff and Price Mutation Audit History

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.6.3 Edit/Renew Ticket Table, Rows 12-16 (`image17.png`).
  - Table `ticket_renewal`.
- **Issue / Description**:
  - Renewal screen (4.6.3) allows customer to alter ticket type, floor, slot, and billed price when extending duration.
  - `ticket_renewal` previously stored only slot modification and additional surcharge, losing historical record of ticket type and tariff price changes.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Extend `ticket_renewal` with `old_ticket_type_id BIGINT NULL REFERENCES ticket_type(id)`, `new_ticket_type_id BIGINT NULL REFERENCES ticket_type(id)`, `old_price NUMERIC(12, 2) NULL`, and `new_price NUMERIC(12, 2) NULL`. Fully captures tariff adjustments and financial evolution across all renewal cycles.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-59: Parking Slot Code Uniqueness Scoped per Floor

- **Priority / Status**: Important
- **Sources**:
  - Wireframe 4.8.1 Slot List (`image21.png`: Floor 1 shows slot `A-1`).
  - Wireframe 4.8.3 Edit Slot (`image23.png`: Floor 8, Slot 6 shows slot `A-1`).
- **Issue / Description**:
  - SRS displays slot code `A-1` on Floor 1 and simultaneously displays `A-1` on Floor 8.
  - Global `UNIQUE(code)` prevents assigning identical section codes across different floors.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Replace global unique constraint with floor-scoped composite unique index: `CREATE UNIQUE INDEX uq_parking_slot_floor_code_active ON parking_slot (floor_number, code) WHERE deleted_at IS NULL;`. Allows each floor to possess its own `A-1`, `A-2` nomenclature while preventing duplicate codes on the same floor.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-60: Vehicle Barrier Gate Camera In/Out Photography Storage

- **Priority / Status**: Nice-to-know
- **Sources**:
  - Wireframe 4.5.1 Vehicle In/Out (`image13.png`).
  - SRS 4.5.1 Table description (Row 4 & Row 5).
- **Issue / Description**:
  - Wireframe `image13.png` depicts TWO visual image frames under "Xe vào" (Entry) and TWO visual image frames under "Xe ra" (Exit), showing both overall vehicle snapshot and close-up plate photo.
  - SRS text only mentions "Ảnh chụp biển số xe".
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: For Sprint 1, schema provisions `entry_image_url TEXT` and `exit_image_url TEXT` storing image asset URI. If PO mandates dual-capture (vehicle overview + cropped plate), schema can extend to `entry_plate_image_url` and `entry_overview_image_url` without architectural rework.
- **Authority / Owner**: **Product Owner**

### OQ-61: Referential Integrity Guard Between Vehicle and Customer on Ticket

- **Priority / Status**: Blocker
- **Sources**:
  - SRS 4.6.1 Ticket List & SRS 4.6.2 Add Ticket (`image16.png`).
  - Table `ticket` foreign keys.
- **Issue / Description**:
  - In screen 4.6.2, selecting customer code populates customer name and restricts vehicle selection to vehicles owned by that customer.
  - Lacking composite constraint, database previously permitted creating a ticket referencing Customer A with Vehicle owned by Customer B.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Enforce database integrity constraint: Add `CONSTRAINT uq_vehicle_id_customer UNIQUE (id, customer_id)` on `vehicle`, and establish composite foreign key `CONSTRAINT fk_ticket_vehicle_customer FOREIGN KEY (vehicle_id, customer_id) REFERENCES vehicle (id, customer_id) ON DELETE RESTRICT` on `ticket`. Guarantees vehicle ownership consistency at the database level.
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
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Enforce `CONSTRAINT uq_admin_district_id_province UNIQUE (id, province_id)` on `administrative_district`, `CONSTRAINT uq_admin_ward_id_district UNIQUE (id, district_id)` on `administrative_ward`, and composite foreign keys on `employee` and `customer` (`(district_id, province_id)` and `(ward_id, district_id)`), preventing cross-hierarchy corruption while preserving SRS 3-dropdown compatibility as an architectural **[PROPOSAL] (OQ-50, OQ-62)**.
- **Authority / Owner**: **Team Lead**

### OQ-63: Real-Time Derived Status Synchronization & Disclosure of Extended Slot Statuses

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.5.2 Parking Map (`parking_slot.status`: AVAILABLE, OCCUPIED, RESERVED, MAINTENANCE).
  - SRS 4.6.1 Ticket Lifecycle (`ticket.status`: ACTIVE, EXPIRED, RENEWED, CANCELLED).
  - Wireframe `image14.png`.
  - View `v_slot_occupancy_by_floor`.
- **Issue / Description**:
  - Wireframe `image14.png` visually renders only two slot states (green for available, red for occupied). Stored database statuses `RESERVED` and `MAINTENANCE` are architectural proposals beyond the literal wireframe.
  - PostgreSQL triggers fire only on DML. When a ticket's `effective_to` timestamp passes purely by wall-clock time without DML, stored `parking_slot.status` remains `'RESERVED'` and `ticket.status` remains `'ACTIVE'` until the next DML or reconciliation sweep.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: (1) **Explicit Status Disclosure**: Formally disclose that `parking_slot.status` values `RESERVED` and `MAINTENANCE` are architectural **[PROPOSAL]** extensions enabling subscription pre-allocation and maintenance out-of-service locking; entering or selecting a maintenance slot raises proposed message `'Vị trí này đang bảo trì.'` (`PROP-4.5.2-P01`, ending with a period per `OQ-46` and Rule 09). (2) **Live-Data View**: Compute `v_slot_occupancy_by_floor` dynamically from live relational predicates (`EXISTS` open session in `vehicle_entry_exit_log WHERE exit_time IS NULL` OR active valid ticket window `CURRENT_TIMESTAMP >= effective_from AND CURRENT_TIMESTAMP < effective_to`, excluding `MAINTENANCE` slots from the operational denominator). (3) **DML Triggers & Sweeps**: Retain DML triggers (`trg_ticket_status_sync`, `trg_slot_status_on_traffic`, `trg_slot_status_on_ticket`) for immediate synchronization and pair with scheduled background sweeps for stored status reconciliation.
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
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: (1) Attach trigger `trg_*_row_version BEFORE UPDATE` across all versioned tables, automatically executing `NEW.row_version = OLD.row_version + 1; NEW.updated_at = CURRENT_TIMESTAMP;`. (2) Enforce database CHECK guard on `ticket`: `CONSTRAINT ck_ticket_delete_only_expired CHECK (deleted_at IS NULL OR effective_to <= deleted_at)`. Prevents deleting active tickets at the database constraint layer.
- **Authority / Owner**: **Team Lead**

### OQ-65: Beyond-SRS Constraint Justifications, Literal SRS Gender & Strict Registered Vehicle Policy

- **Priority / Status**: Important
- **Sources**:
  - Phone numbers format `^[0-9]+$` & unique phone/email.
  - Gender domain (`Nam`, `Nữ`).
  - Business code format `^[A-Za-z0-9-]+$`.
  - SRS 4.5.1 Barrier Entry & Owner Decisions 10, 11.
- **Issue / Description**:
  - SRS specifies phone as `Number(15)` / `Number(11)` without regex; wireframe dropdown specifies gender `Nam`, `Nữ` only; SRS specifies codes as `Alpha numeric (5)` while wireframes depict hyphenated codes (`NV-1234`, `KH-1234`, `Xe-001`, `VE-01`).
  - Previous draft permitted walk-in transient vehicles (`vehicle_id NULL`), contradicting SRS 4.5.1 which mandates that saving without finding a registered vehicle triggers error `"Lỗi dữ liệu không tìm thấy đê lưu"` (`MSG-4.5.1-M02`).
- **Proposed Default / Resolution**: **PROPOSED DEFAULT & OWNER DECISIONS**: (1) **Strict Registered Vehicle Policy (Owner Decision 10)**: Eliminate walk-in transient policy completely. Enforce `vehicle_id BIGINT NOT NULL` on `vehicle_entry_exit_log`; barrier gate saves require an active registered vehicle matching recognized license plate; (2) **Literal SRS Gender (Owner Decision 11)**: Dropdown in 4.3.2 contains only `Nam` and `Nữ`. Revert proposal of `'Khác'`; enforce `CHECK (gender IN ('Nam', 'Nữ'))` on `employee` and `customer`; (3) **Business Code Format**: Maintain `VARCHAR(10)` / `VARCHAR(20)` and enforce format constraint `CHECK (code ~ '^[A-Za-z0-9-]+$')` across `employee`, `customer`, `vehicle`, `ticket`, allowing both alphanumeric 5 and hyphenated wireframe codes while rejecting invalid characters; (4) **ID Card Comment**: Document `customer.identity_card_number` as digits-only up to 20 chars (`CHECK (identity_card_number ~ '^[0-9]+$')`).
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-66: Open Parking Session Partial Unique Indexes & Double-Entry Prevention

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.5.1 Vehicle In/Out Table.
  - `db/01-schema.sql:737-739`.
  - Table `vehicle_entry_exit_log`.
- **Issue / Description**:
  - SRS does not define multi-session prevention rules when vehicle enters without exiting or when two vehicles are assigned to the same physical slot.
  - Without database guards, a single registered vehicle could enter multiple slots simultaneously, or a single physical slot could have concurrent open check-in sessions.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Enforce 3 partial unique indexes on `vehicle_entry_exit_log WHERE exit_time IS NULL`: (1) `uq_log_open_session_slot` on `(slot_id) WHERE exit_time IS NULL AND slot_id IS NOT NULL`; (2) `uq_log_open_session_vehicle` on `(vehicle_id) WHERE exit_time IS NULL`; (3) `uq_log_open_session_plate` on `(license_plate_norm) WHERE exit_time IS NULL` (updated in Round 18 per `OQ-75`). Prevents double-entry and slot collision anomalies at the database layer.
- **Authority / Owner**: **Team Lead**

### OQ-67: Slot Reservation Guard and Maintenance Slot Protection on Entry & Update

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.5.2 Parking Map, Row 14 (ACT-4.5.2-A02, MSG-4.5.2-M02: "Vị trí này đã có xe đk vé và đang sử dụng").
  - `db/01-schema.sql`: `fn_guard_slot_reservation_on_entry()` & `trg_guard_slot_reservation_on_entry`.
  - Table `vehicle_entry_exit_log`.
- **Issue / Description**:
  - When a slot is reserved by an active subscription ticket for Vehicle A, another registered Vehicle B must be prevented from occupying that slot at barrier check-in or via slot reassignment.
  - Attempting to enter or select a slot currently undergoing maintenance must also be rejected.
  - With `vehicle_id NOT NULL` enforced per Owner Decision 10, the guard no longer needs walk-in branches.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Implement database guard trigger `trg_guard_slot_reservation_on_entry` (`BEFORE INSERT OR UPDATE OF slot_id, exit_time, vehicle_id, license_plate ON vehicle_entry_exit_log`): (1) Serializes slot access via row locking (`FOR NO KEY UPDATE`); (2) Rejects entry, reassignment, or session reopening into maintenance slots (`parking_slot.status = 'MAINTENANCE'`), raising proposed error `'Vị trí này đang bảo trì.'` (`PROP-4.5.2-P01`, aligned with ending period in `db/01-schema.sql` and `db/00-README.md` per `OQ-46` and Rule 09); (3) Rejects occupying slots reserved by an active subscription ticket for a different registered vehicle (`NEW.vehicle_id <> ticket.vehicle_id`), raising verbatim SRS error message `'Vị trí này đã có xe đk vé và đang sử dụng'` with `check_violation` ERRCODE. Normal exit updates (`exit_time` becoming non-NULL) are unaffected.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-68: Employee Working Time & Shift Scheduling Scope OQ

- **Priority / Status**: Important
- **Sources**:
  - SRS Section 2.2 Main Functions list, bullet 4 (`Quản lý thời gian làm việc của nhân viên, hệ thống admin`).
  - SRS Section 4 (Modules 4.1 to 4.8).
- **Issue / Description**:
  - SRS Section 2.2 explicitly lists "Quản lý thời gian làm việc của nhân viên, hệ thống admin" as a core system feature in high-level scope.
  - However, across the entire Section 4 (Modules 4.1 through 4.8), there are zero screens, zero data fields, zero action tables, and zero wireframes specifying employee shifts, working hours, attendance tracking, or timesheets.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Employee working time / shift scheduling is deemed out of scope for Sprint 1 because neither functional screens nor data specifications exist in Section 4. Core employee profile management and authentication remain fully functional. If the Product Owner confirms shift management is required in a future sprint, propose a minimal `employee_shift` table (`employee_id`, `shift_start`, `shift_end`, `status`) without blocking Sprint 1 deliverables.
- **Authority / Owner**: **Product Owner**

### OQ-69: Floor Map Slot 2D Geometric Grid Coordinates (`map_row`, `map_col`)

- **Priority / Status**: Important
- **Sources**:
  - SRS 4.5.2 Parking Map (`Cách hiển thị: Mỗi tầng sẽ có sơ đồ vị trí khác nhau`).
  - Wireframe 4.5.2 (`image14.png`).
  - Table `parking_slot`.
- **Issue / Description**:
  - SRS 4.5.2 states that each floor has a distinct spatial parking layout, and wireframe `image14.png` illustrates a 2D geometric grid with dedicated entrance (`Cửa vào`) and exit (`Cửa ra`) portals.
  - However, the SRS textual specification defines only a 1D scalar `slot_number` (1..108) without 2D grid coordinates for UI placement.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT [PROPOSAL]**: Add optional 2D layout grid coordinate columns `map_row SMALLINT NULL` and `map_col SMALLINT NULL` to `parking_slot`. Enforce coordinate integrity via check constraint `CONSTRAINT ck_slot_map_coords_pair CHECK ((map_row IS NULL AND map_col IS NULL) OR (map_row IS NOT NULL AND map_col IS NOT NULL AND map_row > 0 AND map_col > 0))` and partial unique index `CREATE UNIQUE INDEX uq_parking_slot_floor_map_pos_active ON parking_slot (floor_number, map_row, map_col) WHERE deleted_at IS NULL AND map_row IS NOT NULL AND map_col IS NOT NULL;` preventing spatial collisions on the same floor while supporting dynamic 2D visual rendering per `image14.png`.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-70: Duplicate License Plate Sample Data in SRS Wireframes (`92D1-1234`)

- **Priority / Status**: Nice-to-know
- **Sources**:
  - Wireframe 4.4.1 Customer List (`image9.png`).
  - Wireframe 4.4.4 Edit Customer (`image10.png`).
  - Table `vehicle`.
- **Issue / Description**:
  - SRS wireframes `image9.png` and `image10.png` show sample vehicles `Xe-001` and `Xe-002` both carrying the identical license plate `92D1-1234`.
  - In reality and under relational database integrity, active vehicle license plates must be strictly unique within the facility.
- **Proposed Default / Resolution**: **PROPOSED DEFAULT**: Treat the duplicate license plate in wireframes `image9.png` and `image10.png` as an illustrative graphic copy-paste artifact in the SRS. The database strictly enforces active normalized license plate uniqueness via `CREATE UNIQUE INDEX uq_vehicle_license_plate_active ON vehicle (license_plate_norm) WHERE deleted_at IS NULL;` (`OQ-75`), rejecting duplicate active plates while allowing plate reuse only after soft delete.
- **Authority / Owner**: **Product Owner** & **Team Lead**

### OQ-71: Login Identifier (`Email/SĐT` vs `Tên đăng nhập`) & Self-Registration Link (`Đăng ký ngay`)

- **Priority / Status**: Blocker — `status = deferred to PO / Owner approved default D1`
- **Sources**:
  - Frontend `login-container.png` (`Email hoặc Số điện thoại`, `Chưa có tài khoản? Đăng ký ngay`).
  - SRS 4.1 (`image2.png` Row 5: `Tên đăng nhập`, `MSG-4.1-M03`) & SRS 4.3.2 (`image5.png`).
  - `db/01-schema.sql:26, 37` (`account.username`, `ck_account_username_format`).
  - `06-frontend-srs-db-alignment.md` (`F01`, `F02`, `D1`).
- **Issue / Description**:
  - `login-container.png` labels the login input `"Email hoặc Số điện thoại"` and displays `"Chưa có tài khoản? Đăng ký ngay"`.
  - SRS 4.1 requires `"Tên đăng nhập"` (`MSG-4.1-M03: Tên đăng nhập không chứa ký tự đặc biệt`), `ck_account_username_format CHECK (username ~ '^[a-zA-Z0-9_.-]+$')` rejects `@` in email addresses, `account` has no `email`/`phone` columns, and accounts are provisioned exclusively by Admin.
- **Proposed Default / Resolution**: **OWNER APPROVED DEFAULT `[PROPOSAL]` (`D1`)**: Authenticate strictly by `username` (`Tên đăng nhập`) per SRS 4.1 and remove the `"Đăng ký ngay"` link on `login-container.png` (frontend change; no database change required).
- **Authority / Owner**: **PO**

### OQ-72: Per-Session Fees (`Cước phí`), Payment Methods (`Tiền mặt`/`QR`/`VietQR`) & `Giao dịch` Module

- **Priority / Status**: Important — `status = deferred to PO / Owner approved default D2`
- **Sources**:
  - Frontend `Lịch sử ra\vào — Smart Mobility.png` (`Cước phí`, `Mã phiên đỗ`, `Tổng thời gian đỗ`, `Bộ lọc nhanh` without buttons).
  - Frontend `Trang chủ — Smart Mobility.png` (`Tiền mặt: 18% \| QR: 82%`), `Main Page.png` (`VietQR`), `Quản lý xe — Smart Mobility.png` (`module Vé/Giao dịch`).
  - SRS 4.5.1 & 4.7.1 (`image19.png`).
  - `db/01-schema.sql:688-712, 1140` (`vehicle_entry_exit_log`, `v_revenue_statistics`).
  - `06-frontend-srs-db-alignment.md` (`F05`, `F20`, `F25`, `F29`, `D2`).
- **Issue / Description**:
  - Frontend introduces per-session `Cước phí`, `Tiền mặt`/`QR`/`VietQR` payment splits, and references a `Giao dịch` module.
  - SRS 4.7.1 defines revenue strictly from subscription ticket sales (`ticket.price`) and renewals (`ticket_renewal.additional_price`), and `db/01-schema.sql` has no `fee_amount`, `payment_method`, or `transaction` table.
- **Proposed Default / Resolution**: **OWNER APPROVED DEFAULT `[PROPOSAL]` (`D2`)**: Keep payments, per-session fees (`Cước phí`), and transactions out of v1 (deferred to PO); derive parking duration (`exit_time - entry_time`) and formatted session ID (`id`) from `vehicle_entry_exit_log`.
- **Authority / Owner**: **PO**

### OQ-73: Floor Naming (`B1..B3, F1` vs `INTEGER 1..99`) & Multi-Lot / Zone Tables (`Bãi xe`, `Khu A..D`)

- **Priority / Status**: Important — `status = deferred to PO / Owner approved default D3`
- **Sources**:
  - Frontend `Main Page.png`, `Trang chủ — Smart Mobility.png`, `Sơ đồ bãi đậu xe — Smart Mobility.png`, `Quản lý vé — Smart Mobility.png` (`Tầng B1..B3, F1`, `Bãi xe Smart Mobility`, `Khu A..D`, `+ Thêm tầng`, `+ Thêm khu`, `Quản lý cấu trúc bãi`).
  - SRS 4.5.2 (`image14.png`: `Số tầng: Number(2)`) & 4.8.2 (`image22.png`).
  - `db/01-schema.sql:494-496, 511` (`parking_slot.floor_number`, `ck_slot_floor_range`).
  - `06-frontend-srs-db-alignment.md` (`F09`, `F10`, `D3`).
- **Issue / Description**:
  - Frontend names floors `"Tầng B1"`, `"Tầng B2"`, `"Tầng B3"`, `"Tầng F1"` and introduces multi-lot (`24 khu bãi`) and zone (`Khu A..D`) management panels.
  - SRS 4.5.2 and `db/01-schema.sql` model `floor_number INTEGER NOT NULL CHECK (floor_number > 0 AND floor_number < 100)` (`OQ-54`) and `slot_number` (`code`) with no `parking_lot` or `parking_zone` tables.
- **Proposed Default / Resolution**: **OWNER APPROVED DEFAULT `[PROPOSAL]` (`D3`)**: Keep floors as positive integers (`floor_number INTEGER`) and do not add `parking_lot` or `parking_zone` tables in v1 (deferred to PO).
- **Authority / Owner**: **PO**

### OQ-74: Deferred Non-SRS Frontend Features (EV, Priority Slots, Blacklist/Debt, Gates, AI Confidence, Extra `Ghi chú`, Activity Feed)

- **Priority / Status**: Important — `status = deferred to PO / Owner approved default D4`
- **Sources**:
  - Frontend `Main Page.png`, `Trang chủ — Smart Mobility.png`, `Khách hàng — Smart Mobility.png`, `Quản lý xe — Smart Mobility.png`, `Sơ đồ bãi đậu xe — Smart Mobility.png`, `Quản lý vé — Smart Mobility.png`.
  - `db/01-schema.sql:292-739`.
  - `06-frontend-srs-db-alignment.md` (`F06`, `F07`, `F08`, `F11`, `F12`, `F18`, `F25`, `F26`, `D4`).
- **Issue / Description**:
  - Frontend mockups show EV charging (`Sạc xe điện`), priority lanes (`XE ƯU TIÊN`), blacklist/debt alerts (`Blacklist/Tạm khoá`, `Nợ phí`), gate names (`Cổng vào 1/2`, `Cổng ra 1/2/3`, `4 Cổng quét tự động`), AI recognition confidence (`98.4%`, `Ảnh khớp`/`Cần duyệt`), `Ghi chú` on `ticket`/`ticket_renewal`/`vehicle`/`parking_slot`, and `Hoạt động gần đây` activity feed, while omitting SRS slot dimensions (`width`, `length`, `height`).
- **Proposed Default / Resolution**: **OWNER APPROVED DEFAULT `[PROPOSAL]` (`D4`)**: Defer EV charging, priority slots, blacklist/debt, gates, AI confidence, extra `notes` columns, and audit activity feeds to the PO (no v1 DB changes); retain `width`, `length`, `height` on `parking_slot` per SRS 4.5.2/4.8.2.
- **Authority / Owner**: **PO**

### OQ-75: License-Plate Punctuation (`51K-992.14` vs `51K-992-14`) & Canonical DB Normalization

- **Priority / Status**: Blocker — `status = implemented (Owner approved D5)`
- **Sources**:
  - Frontend `Quản lý xe — Smart Mobility.png` & `Trang chủ — Smart Mobility.png` (`51K-992.14`, `30A-123.45`) vs `Quản lý vé — Smart Mobility.png` (`51K-992-14`, `30A-123-45`).
  - `db/01-schema.sql:424-485, 688-739, 1050-1074` (`fn_normalize_license_plate`, `vehicle.license_plate_norm`, `vehicle_entry_exit_log.license_plate_norm`, `uq_vehicle_license_plate_active`, `uq_log_open_session_plate`, `fn_guard_slot_reservation_on_entry`).
  - `06-frontend-srs-db-alignment.md` (`F17`, `D5`, Section 4.1 & Section 6).
- **Issue / Description**:
  - Frontend displays the same vehicle `XE0001` (`KH0001`) as `51K-992.14` (dot) on `Quản lý xe` and as `51K-992-14` (hyphen) on `Quản lý vé` (`VT0001`).
  - Without normalization, `'51K-992.14'` and `'51K-992-14'` could both be inserted into `vehicle` and `vehicle_entry_exit_log`, while `fn_guard_slot_reservation_on_entry()` rejected log plates differing only by punctuation/spaces/case.
- **Proposed Default / Resolution**: **IMPLEMENTED (`D5`, Round 18)**: Added `IMMUTABLE STRICT PARALLEL SAFE` SQL function `fn_normalize_license_plate(p_input TEXT)` returning `UPPER(REGEXP_REPLACE(p_input, '[^A-Za-z0-9]', '', 'g'))`; added `license_plate_norm VARCHAR(20) GENERATED ALWAYS AS (fn_normalize_license_plate(license_plate)) STORED` with `CHECK (license_plate_norm <> '')` and `COMMENT ON COLUMN` on `vehicle` and `vehicle_entry_exit_log` (preserving `license_plate` as entered); moved `uq_vehicle_license_plate_active`, `uq_log_open_session_plate`, and `idx_log_license_plate` to `license_plate_norm`; and updated `fn_guard_slot_reservation_on_entry()` to compare `fn_normalize_license_plate(NEW.license_plate)` with `fn_normalize_license_plate(v_registered_plate)` (keeping 14 triggers, 5 trigger functions, `SQLSTATE 23514`, and verbatim SRS message `'Lỗi dữ liệu không tìm thấy đê lưu'`).
- **Authority / Owner**: **Owner & Team Lead**

### OQ-76: Ticket/Vehicle/Position Taxonomy, Tariff Seeds, Derived Statuses & Same-Day Ticket Timestamps

- **Priority / Status**: Important — `status = deferred to PO / Owner approved default D6`
- **Sources**:
  - Frontend `Quản lý vé — Smart Mobility.png` (`Vé ngày 50k`, `Vé tháng 500k`, `Vé quý 1.2M`; 5 statuses including `Sắp hết hạn`, `Đang gia hạn`; `VT0002` `10/5/2026`–`10/5/2026`; missing `Họ tên`, `SĐT`, `Thao tác`), `Quản lý xe — Smart Mobility.png` (`Ô tô`/`Xe máy`/`Xe điện`; `Đang đỗ`/`Đang hoạt động`/`Đã rời bãi`), `Quản lý nhân viên - Smart mobility.png` (4 positions, `Không hoạt động`).
  - `db/01-schema.sql:29, 589, 591`, `db/02-seed.sql:21-54`.
  - `06-frontend-srs-db-alignment.md` (`F13`–`F16`, `F19`, `F21`, `F22`, `F30`, `D6`).
- **Issue / Description**:
  - Frontend introduces `Vé quý` (`1.200.000đ`), `Xe điện`, new staff positions, and different ticket prices (`50k`/`500k` vs seeded `10k`/`100k` in `OQ-57`).
  - Ticket `VT0002` has `effective_from = effective_to = 10/5/2026`, violating `ck_ticket_time_order CHECK (effective_to > effective_from)` if stored as identical midnight timestamps.
- **Proposed Default / Resolution**: **OWNER APPROVED DEFAULT `[PROPOSAL]` (`D6`)**: Keep ticket, vehicle, and position seeds unchanged until the Product Owner confirms prices and categories; keep `Sắp hết hạn` (ticket), `Đang đỗ`/`Đã rời bãi` (vehicle), and `Không hoạt động` (`account.is_active`) derived rather than adding redundant status columns; store 1-day tickets with `effective_to = effective_from + INTERVAL '1 day'`.
- **Authority / Owner**: **PO**

### OQ-77: Manual Slot Status Override Buttons vs Trigger-Managed Slot Status

- **Priority / Status**: Important — `status = deferred to PO / Owner approved default D7`
- **Sources**:
  - Frontend `Sơ đồ bãi đậu xe — Smart Mobility.png` (`Chi tiết ô đỗ`: manual buttons `Đánh dấu trống`, `Đánh dấu có xe`, `Đánh dấu đặt trước`, `Đánh dấu bảo trì`).
  - `db/01-schema.sql:517, 872-1046` (`ck_slot_status_enum`, `fn_sync_slot_status_on_ticket`, `fn_sync_slot_status_on_traffic`).
  - `06-frontend-srs-db-alignment.md` (`F11`, `D7`).
- **Issue / Description**:
  - Frontend provides manual buttons to set a slot to `Trống`, `Có xe`, `Đặt trước`, or `Bảo trì`.
  - In `db/01-schema.sql` (`OQ-63`), `AVAILABLE`, `OCCUPIED`, and `RESERVED` are automatically synchronized by database triggers from active tickets and open entry/exit sessions; manual overrides would immediately desynchronize slot state from ticket/session truth.
- **Proposed Default / Resolution**: **OWNER APPROVED DEFAULT `[PROPOSAL]` (`D7`)**: Only `MAINTENANCE` is a manual slot status; `AVAILABLE`, `OCCUPIED`, and `RESERVED` remain strictly trigger-managed (`fn_sync_slot_status_on_ticket`, `fn_sync_slot_status_on_traffic`).
- **Authority / Owner**: **PO**

### OQ-78: ERD Module Diagram Completeness (`F27`), Intentional Stub Layout (`F28`) & Master Legend Count (`F31`)

- **Priority / Status**: Important — `status = implemented (Owner approved D8)`
- **Sources**:
  - [`db/03-erd.asta`](../../db/03-erd.asta) and [`db/04-erd.png`](../../db/04-erd.png)–[`db/09-erd-reference-views.png`](../../db/09-erd-reference-views.png).
  - [`db/00-README.md`](../../db/00-README.md) lines 314–318.
  - `06-frontend-srs-db-alignment.md` (`F27`, `F28`, `F31`, Section 4.3, `D8`).
- **Issue / Description**:
  - While `04-erd.png` renders all 44 FKs (`33` business + `11` `deleted_by`), module diagrams `05..08` previously omitted 12 non-`deleted_by` FKs whose both end tables are drawn (`5` in `Parking_Ticket`: `fk_ticket_issued_by`, `fk_renewal_old_slot`, `fk_renewal_old_ticket_type`, `fk_vehicle_ticket_type`, `fk_vehicle_type`; `5` in `Operations_Content`: `fk_log_exit_staff`, `fk_ticket_issued_by`, `fk_ticket_slot`, `fk_ticket_vehicle_customer`, `fk_employee_account`; `1` in `Account_Staff`: `fk_admin_ward_district`; `1` in `Customer_Vehicle`: `fk_admin_ward_district`), and `04-erd.png` legend note said `209-attribute` instead of `213-attribute` (with `235` total including 22 view columns).
  - Duplicate stub nodes (`F28`) are an intentional layout choice per `db/00-README.md` ("Collapsed Neighbor Stubs", at most one link per boundary side).
  - Verification of the `astah-uml` MCP tools confirmed that 4 of the 5 operations (`astah_add_presentation_link` by FK name, `astah_add_attribute` with `VARCHAR(20)` and `stereotype="PUQ"`, `astah_delete_element` + `astah_add_attribute`, and `astah_add_presentation_node` / `astah_set_presentation_style` with `width=240, height=45`) already worked, and only Note text editing (`astah_set_note_text`) was missing.
- **Proposed Default / Resolution**: **IMPLEMENTED (`D8`, Round 19 Task D & Task E)**: Added `astah_set_note_text` to `D:\GitHub\Server\mcp-uml` (`39` tools total); kept the collapsed-neighbor-stub layout design (`F28`); updated `vehicle` and `vehicle_entry_exit_log` with `license_plate : VARCHAR(20)` and `license_plate_norm : VARCHAR(20) «PUQ»` (`213` table attributes + `22` view attributes = `235` total across `41` classes); added all 12 missing non-`deleted_by` business FKs across `05..08` (`F27`, `0` missing business FKs across `04..09`, `0` table crossings); updated the `04-erd.png` legend note to `213-attribute` (`F31`); and re-exported `db/04-erd.png`..`db/09-erd-reference-views.png` at 400 DPI via `astah_export_diagram_image`.
- **Authority / Owner**: **Owner & Team Lead**
