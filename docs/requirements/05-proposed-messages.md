# Proposed Backend Messages Catalog Awaiting Approval

This document registers all proposed user messages (**[PROPOSAL]**) for backend API interaction points where the canonical specification `Quan ly bai dau xe oto_SRS_v4.1.docx` **does not define a specific verbatim dialogue string** (where the SRS only describes mutation side-effects or records test scenario descriptions).

All messages in this document **MANDATORILY carry the [PROPOSAL] tag** and require formal approval from the Product Owner (PO) prior to production release. Note on Check_Quality Item 6 (Punctuation): Check_Quality Item 6 specifies terminating punctuation (`.`), whereas verbatim SRS v4.1 messages end without punctuation. By default, SRS messages remain unpunctuated verbatim, while proposed messages here include terminating punctuation (`.`) pending formal PO decision on unified punctuation policy (**OQ-46**).

---

## 1. Principles Distinguishing SRS Verbatim Messages from Proposals

1. **Single Source of Truth**:
   - `docs/requirements/00-srs-catalog.md` contains ONLY messages with verbatim text in SRS v4.1 (identified as `MSG-<Screen>-M<Number>`).
   - Test conditions in the SRS Failure column without verbatim text are cataloged as **Scenario Descriptions** (`CASE-<Screen>-TH<Number>`).
2. **Standardization of Proposals ([PROPOSAL])**:
   - When a backend API must return an error or success message where the SRS provides no text, assign a proposal code: `PROP-<Screen>-P<Number>`.
   - Each `PROP-` entry links directly to an open question in `docs/requirements/01-open-questions.md` (`OQ-13` through `OQ-38`, `OQ-63`, `OQ-67`, `OQ-81`).
   - Strictly prohibit claiming these proposals as "verbatim SRS messages" in rules, skills, or agent prompts.

---

## 2. Catalog of Proposed Messages by Module

### 2.1. Employee Management Module (SRS 4.3)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Open Question |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-4.3.3-P01** | 4.3.3 Edit Employee (Update) | Successful employee update | SRS describes: "Dữ liệu được cập nhật vào bảng Nhân viên..." | `Cập nhật thông tin nhân viên thành công.` | 200 OK | **OQ-13** |
| **PROP-4.3.3-P02** | 4.3.3 Edit Employee (Update) | Employee record not found during update | SRS does not define not-found message | `Nhân viên không tồn tại hoặc đã bị xóa.` | 404 Not Found | **OQ-13** |
| **PROP-4.3.1-P01** | 4.3.1 Employee List (Edit) | `CASE-4.3.1-TH_INV`: Invalid update payload | "hiển thị thông báo phù hợp từng trường" | `Dữ liệu {item} không hợp lệ, xin mời nhập lại.` | 400 Bad Request | **OQ-13** |

---

### 2.2. Customer Management Module (SRS 4.4)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Open Question |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-4.4.3-P01** | 4.4.3 Add Customer (Save) | Customer and vehicle saved successfully | SRS describes: "Dữ liệu sẽ được lưu vào cơ sở dữ liệu..." | `Thêm mới thông tin khách hàng thành công.` | 201 Created | **OQ-14** |
| **PROP-4.4.4-P01** | 4.4.4 Edit Customer (Update) | Customer updated successfully | SRS describes: "Dữ liệu sẽ được cập nhật vào database..." | `Cập nhật thông tin khách hàng thành công.` | 200 OK | **OQ-15** |
| **PROP-4.4.4-P02** | 4.4.4 Edit Customer (Update) | Customer record not found on update | SRS does not define 404 message | `Khách hàng không tồn tại hoặc đã bị xóa.` | 404 Not Found | **OQ-15** |
| **PROP-4.4.5-P01** | 4.4.5 Delete Customer (Confirm) | Customer record not found on delete | SRS does not define 404 message | `Khách hàng không tồn tại hoặc đã bị xóa.` | 404 Not Found | **OQ-15** |
| **PROP-4.4.5-P02** | 4.4.5 Delete Customer (Confirm) | Customer has vehicles parked in lot | SRS does not define guard rule (DEL-02) | `Khách hàng đang có phương tiện trong bãi, không được phép xóa.` | 400 Bad Request | **OQ-15** |
| **PROP-4.4.5-P03** | 4.4.5 Delete Customer (Confirm) | Customer has active tickets | SRS does not define guard rule (DEL-02) | `Khách hàng đang có vé xe còn hiệu lực, không được phép xóa.` | 400 Bad Request | **OQ-15** |

---

### 2.3. Vehicle In/Out & Parking Map Module (SRS 4.5 & FE `Sơ đồ bãi đậu xe`)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Open Question |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-4.5.2-P01** | 4.5.2 Parking Map / 4.5.1 Vehicle In/Out | Attempting to occupy or select a slot currently under maintenance | SRS does not define error dialogue string for maintenance slots | `Vị trí này đang bảo trì.` | 400 Bad Request | **OQ-63**, **OQ-67** |
| **PROP-4.5.2-P02** | `Sơ đồ bãi đậu xe` (`TL-03`) | Changing slot status away from `OCCUPIED` while an open session exists | FE & SRS do not define guard message | `Không thể chuyển trạng thái vị trí khi đang có xe đỗ trong ô.` | 400 Bad Request | **OQ-81** |
| **PROP-4.5.2-P03** | `Sơ đồ bãi đậu xe` (`TL-03`) | Manually setting slot to `OCCUPIED` without an open parking session | FE & SRS do not define guard message | `Không thể chuyển vị trí sang trạng thái đang có xe khi không có phiên đỗ xe đang mở.` | 400 Bad Request | **OQ-81** |
| **PROP-4.5.2-P04** | `Sơ đồ bãi đậu xe` (`TL-03`) | Manually setting slot to `AVAILABLE` while an active ticket or reservation exists | FE & SRS do not define guard message | `Không thể đánh dấu vị trí trống khi đang có xe đỗ hoặc đặt trước còn hiệu lực.` | 400 Bad Request | **OQ-81** |
| **PROP-4.5.2-P05** | 4.5.1 Vehicle In/Out (`TL-04`) | Attempting to enter a slot reserved via `slot_reservation` for another vehicle | FE & SRS do not define reservation conflict message | `Vị trí này đã được đặt trước cho phương tiện khác.` | 400 Bad Request | **OQ-81** |
| **PROP-4.5.2-P06** | `Sơ đồ bãi đậu xe` (`TL-12`) | Attempting `UPDATE` or `DELETE` on append-only `activity_log` | FE & SRS do not define immutability guard message | `Nhật ký hoạt động là bảng chỉ ghi (append-only), không cho phép cập nhật hoặc xóa.` | 400 Bad Request | **OQ-81** |

---

### 2.4. Ticket Management Module (SRS 4.6)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Open Question |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-4.6.2-P01** | 4.6.2 Add Ticket (Save) | Ticket created successfully | SRS describes: "Một vé đã được thêm mới vào database..." | `Thêm mới vé đỗ xe thành công.` | 201 Created | **OQ-16** |
| **PROP-4.6.3-P01** | 4.6.3 Edit Ticket (Renew) | Ticket renewed successfully | SRS describes: "Dữ liệu được cập nhật vào bảng Vé..." | `Gia hạn vé đỗ xe thành công.` | 200 OK | **OQ-17** |
| **PROP-4.6.4-P01** | 4.6.4 Delete Ticket (Yes) | `CASE-4.6.4-TH1`: Ticket is active / not expired | SRS describes case: "vé được xóa là vé chưa hết hạn thì không được xóa" | `Vé chưa hết hạn sử dụng, không được phép xóa.` | 400 Bad Request | **OQ-18** |
| **PROP-4.6.4-P02** | 4.6.4 Delete Ticket (Yes) | `CASE-4.6.4-TH1`: Ticket already renewed | Decomposed from TH1: "không cho phép xóa vé đã gia hạn" | `Vé đã được gia hạn, không được phép xóa.` | 400 Bad Request | **OQ-18** |
| **PROP-4.6.4-P03** | 4.6.4 Delete Ticket (Yes) | `CASE-4.6.4-TH2`: Concurrent deletion contention | SRS describes case: "vé được xóa đang được xóa bởi 1 người dùng khác thì không được xóa" | `Vé đang được xử lý bởi người dùng khác, vui lòng thử lại sau.` | 409 Conflict | **OQ-19** |
| **PROP-4.6.4-P04** | 4.6.4 Delete Ticket (Yes) | `CASE-4.6.4-TH3`: Connection error on delete | SRS describes case: "Vé được xóa không kết nối được" | `Lỗi kết nối cơ sở dữ liệu khi thực hiện xóa vé.` | 500 Internal Error | **OQ-20** |
| **PROP-4.6.4-P05** | 4.6.4 Delete Ticket (Yes) | Ticket not found or already deleted | SRS 4.6.4 contains zero Not Found message | `Vé không tồn tại hoặc đã bị xóa.` | 404 Not Found | **OQ-21** |

---

### 2.5. Statistics Module (SRS 4.7)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Open Question |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-4.7.1-P01** | 4.7.1 Aggregate Stats (Chart) | `CASE-4.7.1-TH2`: Invalid selection criteria | SRS states: "Không thống kê được do lỗi dữ liệu chọn không hợp lệ" | `Dữ liệu điều kiện thống kê không hợp lệ.` | 400 Bad Request | **OQ-34** |
| **PROP-4.7.1-P02** | 4.7.1 Aggregate Stats (Chart) | `CASE-4.7.1-TH3`: Connection error | SRS states: "Không thống kê được do lỗi kết nối" | `Lỗi kết nối hệ thống khi tạo biểu đồ thống kê.` | 500 Internal Error | **OQ-35** |
| **PROP-4.7.2-P01** | 4.7.2 Conditional Stats | `CASE-4.7.2-TH1`: No matching data | SRS states: "TH: Không có dữ liệu để thống kê" | `Không có dữ liệu phù hợp để thống kê.` | 200 OK (Empty) | **OQ-36** |
| **PROP-4.7.2-P02** | 4.7.2 Conditional Stats | `CASE-4.7.2-TH2`: Invalid date range criteria | SRS states: "TH: Dữ liệu nhập từ điều kiện thống kê chưa đúng" | `Khoảng thời gian thống kê không hợp lệ (Từ ngày phải nhỏ hơn hoặc bằng Đến ngày).` | 400 Bad Request | **OQ-37** |
| **PROP-4.7.2-P03** | 4.7.2 Conditional Stats | `CASE-4.7.2-TH3`: Connection error | SRS states: "TH: Lỗi kết nối" | `Lỗi kết nối hệ thống khi thực hiện thống kê.` | 500 Internal Error | **OQ-38** |

---

### 2.6. Parking Lot & Slot Management Module (SRS 4.8)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Open Question |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-4.8.2-P01** | 4.8.2 Add Slot (Add) | Parking slot created successfully | SRS describes: "màn hình sẽ chuyển đến trang danh sách vị trí" | `Thêm mới vị trí đỗ xe thành công.` | 201 Created | **OQ-22** |
| **PROP-4.8.2-P02** | 4.8.2 Add Slot (Add) | `CASE-4.8.2-TH1`: Invalid slot data | SRS states: "TH: Dữ liệu thêm không hợp lệ" | `Dữ liệu vị trí đỗ xe không hợp lệ, xin mời nhập lại.` | 400 Bad Request | **OQ-23** |
| **PROP-4.8.2-P03** | 4.8.2 Add Slot (Add) | `CASE-4.8.2-TH2`: Slot already exists | SRS states: "TH: Đã tồn tại" | `Vị trí đỗ xe đã tồn tại trên tầng này.` | 409 Conflict | **OQ-24** |
| **PROP-4.8.2-P04** | 4.8.2 Add Slot (Add) | `CASE-4.8.2-TH3`: Connection error | SRS states: "TH: Lỗi kết nối" | `Lỗi kết nối máy chủ khi thêm vị trí đỗ xe.` | 500 Internal Error | **OQ-25** |
| **PROP-4.8.3-P01** | 4.8.3 Edit Slot (Save) | Parking slot updated successfully | SRS describes: "Dữ liệu được cập nhật vào hệ thống..." | `Cập nhật thông tin vị trí đỗ xe thành công.` | 200 OK | **OQ-26** |
| **PROP-4.8.3-P02** | 4.8.3 Edit Slot (Save) | `CASE-4.8.3-TH1`: Invalid update payload | SRS states: "TH: Lỗi do dữ liệu update không hợp lệ" | `Dữ liệu cập nhật vị trí đỗ xe không hợp lệ.` | 400 Bad Request | **OQ-27** |
| **PROP-4.8.3-P03** | 4.8.3 Edit Slot (Save) | `CASE-4.8.3-TH2`: Concurrent slot update | SRS states: "TH: Lỗi do dữ liệu đang được update bởi 1 user khác" | `Vị trí đỗ xe đang được cập nhật bởi người dùng khác.` | 409 Conflict | **OQ-28** |
| **PROP-4.8.3-P04** | 4.8.3 Edit Slot (Save) | `CASE-4.8.3-TH3`: Connection error | SRS states: "TH: Lỗi do kết nối" | `Lỗi kết nối máy chủ khi cập nhật vị trí đỗ xe.` | 500 Internal Error | **OQ-29** |
| **PROP-4.8.5-P01** | 4.8.5 Delete Slot (Delete) | Parking slot deleted successfully | SRS describes: "Vị trí đỗ được xóa và quay lại..." | `Xóa vị trí đỗ xe thành công.` | 200 OK | **OQ-30** |
| **PROP-4.8.5-P02** | 4.8.5 Delete Slot (Delete) | `CASE-4.8.5-TH1`: Slot has active parking vehicle | SRS states: "TH: Xóa vị trí đang được xe đk vé đỗ" | `Vị trí đỗ xe đang có phương tiện đăng ký vé, không được phép xóa.` | 400 Bad Request | **OQ-31** |
| **PROP-4.8.5-P03** | 4.8.5 Delete Slot (Delete) | `CASE-4.8.5-TH2`: Slot deletion contention | SRS states: "TH: Xoa vị trí đang được xóa bởi người khác" | `Vị trí đỗ xe đang được xóa bởi người dùng khác.` | 409 Conflict | **OQ-32** |
| **PROP-4.8.5-P04** | 4.8.5 Delete Slot (Delete) | `CASE-4.8.5-TH3`: Connection error | SRS states: "TH: xóa nhưng không kết nối được" | `Lỗi kết nối máy chủ khi xóa vị trí đỗ xe.` | 500 Internal Error | **OQ-33** |
| **PROP-4.8.5-P05** | 4.8.5 Delete Slot (Delete) | Slot not found on delete request | SRS does not define 404 message | `Vị trí đỗ xe không tồn tại hoặc đã bị xóa.` | 404 Not Found | **OQ-30** |

---

### 2.7. Standard Generic API Error Envelope

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Open Question |
| :---: | :--- | :--- | :--- | :--- | :--- | :---: |
| **PROP-GEN-P01** | Generic Error Envelope | General validation error envelope | SRS defines no generic 400 error string | `Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu` | 400 Bad Request | **OQ-13** |

---

## 3. Approval and Implementation Protocol

1. Backend developers and AI coding agents **MUST NOT** modify the strings above without authorization.
2. In API serializers and exception handlers, reference centralized constants (e.g. `apps.common.messages.PROPOSAL_MESSAGES`), explicitly marking `[PROPOSAL]` and referencing `PROP-` IDs.
3. When the Product Owner formally approves any proposed message string, it transitions to formal specification status and is integrated into the core product catalog.
