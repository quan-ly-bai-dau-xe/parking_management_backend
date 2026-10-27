# Proposed Backend Messages Catalog (`[PROPOSAL]`)

This document registers all proposed user messages (**[PROPOSAL]**) for backend API interaction points where the Frontend export (`Parking Project`) and the secondary SRS specification `Quan ly bai dau xe oto_SRS_v4.1.docx` **do not define a specific verbatim dialogue string** (where the SRS only describes mutation side-effects or records test scenario descriptions).

All messages in this document **MANDATORILY carry the [PROPOSAL] tag** and are decided by the Team Lead (`TL-19`, `TL-22`, `TL-25`). Note on Check_Quality Item 6 (Punctuation, **OQ-46**): Verbatim SRS v4.1 messages without final punctuation stay exact as SRS text, whereas new proposed messages (`PROP-*`) follow the Frontend and ordinary Vietnamese style with terminating punctuation (`.`).

---

## 1. Principles Distinguishing SRS Verbatim Messages from Proposals

1. **Source Hierarchy (`FE-First` & Authoritative SRS Content)**:
   - Under `TL-19`, `TL-22`, and `TL-25`, [`docs/requirements/06-frontend-srs-db-alignment.md`](06-frontend-srs-db-alignment.md) (`TL-01`–`TL-35`) is the primary source of truth from the Frontend design, while [`docs/requirements/00-srs-catalog.md`](00-srs-catalog.md) is authoritative for the SRS v4.1 content (containing ONLY messages with verbatim text in SRS v4.1, identified as `MSG-<Screen>-M<Number>`) and secondary to the Frontend design.
   - Test conditions in the SRS Failure column without verbatim text are cataloged as **Scenario Descriptions** (`CASE-<Screen>-TH<Number>`).
2. **Standardization of Proposals ([PROPOSAL])**:
   - When a backend API or database trigger must return an error or success message where the Frontend and SRS provide no text, assign a proposal code: `PROP-<Screen>-P<Number>` or `PROP-DEL-<Code>`.
   - Each `PROP-` entry links directly to its decision entry in [`docs/requirements/01-decision-log.md`](01-decision-log.md) (`OQ-10`, `OQ-13` through `OQ-43`, `OQ-63`, `OQ-67`, `OQ-81`) and [`docs/requirements/06-frontend-srs-db-alignment.md`](06-frontend-srs-db-alignment.md) (`TL-25`).
   - Strictly prohibit claiming these proposals as "verbatim SRS messages" in rules, skills, or agent prompts.

---

## 2. Catalog of Proposed Messages by Module

### 2.0. Authentication & Session Management Module (SRS 4.1 & ADR-0004)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Decision ID |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-4.1-P01** | 4.1 Login (`POST /api/v1/auth/login/`) | Brute-force throttling exceeded on identifier or IP | SRS does not define brute-force throttling | `Quá nhiều lần đăng nhập không thành công, vui lòng thử lại sau.` | 429 Too Many Requests | **TL-52**, **OQ-87** |
| **PROP-4.1-P02** | 4.1 Auth Bootstrap (`GET /api/v1/auth/csrf/`) | Bootstrap CSRF cookie for SPA handshake | SRS does not define CSRF handshake | `Khởi tạo cookie CSRF thành công.` | 200 OK | **TL-52** |
| **PROP-4.1-P03** | 4.1 Logout (`POST /api/v1/auth/logout/`) | User session destroyed, remember token revoked and cookies cleared | SRS does not define logout response | `Đăng xuất thành công.` | 200 OK | **TL-52** |
| **PROP-4.1-P06** | 4.1 Login / Logout (`POST /api/v1/auth/login/`, `POST /api/v1/auth/logout/`) | Missing or invalid CSRF token in request header / cookie | SRS does not define CSRF validation | `Mã CSRF không hợp lệ hoặc bị thiếu.` | 403 Forbidden | **TL-53**, **Q1** |

---

### 2.1. Employee Management Module (SRS 4.3)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Decision ID |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-4.3.3-P01** | 4.3.3 Edit Employee (Update) | Successful employee update | SRS describes: "Dữ liệu được cập nhật vào bảng Nhân viên..." | `Cập nhật thông tin nhân viên thành công.` | 200 OK | **OQ-13** |
| **PROP-4.3.3-P02** | 4.3.3 Edit Employee (Update) | Employee record not found during update | SRS does not define not-found message | `Nhân viên không tồn tại hoặc đã bị xóa.` | 404 Not Found | **OQ-13** |
| **PROP-4.3.1-P01** | 4.3.1 Employee List (Edit) | `CASE-4.3.1-TH_INV`: Invalid update payload | "hiển thị thông báo phù hợp từng trường" | `Dữ liệu {item} không hợp lệ, xin mời nhập lại.` | 400 Bad Request | **OQ-13** |

---

### 2.2. Customer Management Module (SRS 4.4)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Decision ID |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-4.4.3-P01** | 4.4.3 Add Customer (Save) | Customer and vehicle saved successfully | SRS describes: "Dữ liệu sẽ được lưu vào cơ sở dữ liệu..." | `Thêm mới thông tin khách hàng thành công.` | 201 Created | **OQ-14** |
| **PROP-4.4.4-P01** | 4.4.4 Edit Customer (Update) | Customer updated successfully | SRS describes: "Dữ liệu sẽ được cập nhật vào database..." | `Cập nhật thông tin khách hàng thành công.` | 200 OK | **OQ-15** |
| **PROP-4.4.4-P02** | 4.4.4 Edit Customer (Update) | Customer record not found on update | SRS does not define 404 message | `Khách hàng không tồn tại hoặc đã bị xóa.` | 404 Not Found | **OQ-15** |
| **PROP-4.4.5-P01** | 4.4.5 Delete Customer (Confirm) | Customer record not found on delete | SRS does not define 404 message | `Khách hàng không tồn tại hoặc đã bị xóa.` | 404 Not Found | **OQ-15** |
| **PROP-4.4.5-P02** | 4.4.5 Delete Customer (Confirm) | Customer has vehicles parked in lot | SRS does not define guard rule (DEL-02) | `Khách hàng đang có phương tiện trong bãi, không được phép xóa.` | 400 Bad Request | **OQ-15**, **OQ-40** |
| **PROP-4.4.5-P03** | 4.4.5 Delete Customer (Confirm) | Customer has active tickets | SRS does not define guard rule (DEL-02) | `Khách hàng đang có vé xe còn hiệu lực, không được phép xóa.` | 400 Bad Request | **OQ-15**, **OQ-40** |

---

### 2.2.1. Vehicle Management Module (SRS 4.4 / FE `Quản lý xe`, Round 63)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Decision ID |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-DEL-03-OPEN-SES** | `Quản lý xe` (`DELETE /api/v1/vehicles/{id}/`) | Vehicle currently has an open parking session in lot (`exit_time IS NULL`) | Database trigger `trg_guard_soft_delete_and_restore_vehicle` check violation (DEL-03 Guard 1) | `Phương tiện đang đỗ trong bãi xe (có phiên đỗ đang mở), không được phép xóa.` | 409 Conflict | **OQ-41**, **TL-25** |
| **PROP-DEL-03-ACTIVE-TKT** | `Quản lý xe` (`DELETE /api/v1/vehicles/{id}/`) | Vehicle currently linked to an active unexpired subscription ticket | Database trigger `trg_guard_soft_delete_and_restore_vehicle` check violation (DEL-03 Guard 2) | `Phương tiện đang có vé đỗ xe còn hiệu lực, không được phép xóa.` | 409 Conflict | **OQ-41**, **TL-25** |
| **PROP-DEL-03-ACTIVE-RSV** | `Quản lý xe` (`DELETE /api/v1/vehicles/{id}/`) | Vehicle currently holds an active advance slot reservation | Database trigger `trg_guard_soft_delete_and_restore_vehicle` check violation (DEL-03 Guard 3) | `Phương tiện đang có đặt trước vị trí đỗ xe còn hiệu lực, không được phép xóa.` | 409 Conflict | **OQ-41**, **TL-25** |
| **PROP-VEH-OWNER-CHANGE-CONFLICT** | `Quản lý xe` (`PATCH /api/v1/vehicles/{id}/`) | Changing vehicle customer_id while vehicle is linked to tickets, open parking sessions, or active reservations | SRS 4.4 / FE Quản lý xe do not define owner reassignment guard | `Không thể thay đổi chủ sở hữu khi phương tiện đang có vé đỗ xe, phiên đỗ đang mở hoặc đặt chỗ còn hiệu lực.` | 409 Conflict | **TL-25**, **OQ-61** |

---

### 2.3. Vehicle In/Out & Parking Map Module (SRS 4.5 & FE `Sơ đồ bãi đậu xe`)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Decision ID |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-4.5.1-P01** | 4.5.1 Vehicle In/Out | Invalid license plate format regex `^[A-Za-z0-9 .\-]+$` | SRS does not define plate format error | `Định dạng biển số xe không hợp lệ.` | 400 Bad Request | **TL-50** |
| **PROP-4.5.1-P02** | 4.5.1 Vehicle In/Out (`plate-scans`) | Missing image file in multipart upload | SRS does not define missing image error | `Tệp hình ảnh biển số xe không được để trống.` | 400 Bad Request | **TL-50** |
| **PROP-4.5.1-P03** | 4.5.1 Vehicle In/Out (`plate-scans`) | Upload image exceeds size limit (> 5 MB) | SRS does not define image size limit error | `Kích thước tệp hình ảnh vượt quá giới hạn cho phép.` | 400 Bad Request | **TL-50** |
| **PROP-4.5.1-P04** | 4.5.1 Vehicle In/Out (`plate-scans`) | Unsupported image format (not JPEG/PNG/WebP) | SRS does not define image type error | `Định dạng tệp hình ảnh không được hỗ trợ.` | 400 Bad Request | **TL-50** |
| **PROP-4.5.1-P05** | 4.5.1 Vehicle In/Out (`plate-scans`) | Image corrupt, decompression bomb, or unreadable | SRS does not define corrupt image error | `Tệp hình ảnh bị hỏng hoặc không thể xử lý an toàn.` | 400 Bad Request | **TL-50** |
| **PROP-4.5.1-P06** | 4.5.1 Vehicle In/Out (`plate-scans`) | OCR engine recognized no license plate in image | SRS does not define OCR failure error | `Không nhận diện được biển số xe từ hình ảnh đã cung cấp.` | 422 Unprocessable | **TL-50** |
| **PROP-4.5.1-P07** | 4.5.1 Vehicle In/Out (`check-in`) | Plate or vehicle already has an active open session | Violated partial unique index `uq_log_open_session_plate` | `Biển số xe đã có phiên đỗ xe đang mở chưa hoàn thành.` | 409 Conflict | **TL-50** |
| **PROP-4.5.1-P08** | 4.5.1 Vehicle In/Out (`check-in`) | License plate is on active blacklist without manager override | SRS does not define blacklist rejection message | `Biển số xe nằm trong danh sách đen, không được phép vào bãi.` | 409 Conflict | **TL-50** |
| **PROP-4.5.1-P09** | 4.5.1 Vehicle In/Out (`check-out`) | Parking fee > 0 but payment method is missing | SRS does not define payment method requirement | `Yêu cầu chọn phương thức thanh toán hợp lệ khi cước phí đỗ xe lớn hơn 0.` | 400 Bad Request | **TL-50** |
| **PROP-4.5.1-P10** | 4.5.1 Vehicle In/Out (`check-out`) | Parking session has already been closed | SRS does not define session already closed error | `Phiên đỗ xe này đã được kết thúc trước đó.` | 409 Conflict | **TL-50** |
| **PROP-4.5.1-P11** | 4.5.1 Vehicle In/Out (`check-out`) | Both or neither session_code and license_plate provided | SRS does not define checkout lookup parameter validation | `Yêu cầu cung cấp chính xác một trong hai tiêu chí: mã phiên đỗ xe hoặc biển số xe.` | 400 Bad Request | **TL-50** |
| **PROP-4.5.1-P12** | 4.5.1 Vehicle In/Out (`check-out`) | Exit gate not found or direction is not OUT | SRS does not define gate direction error | `Cổng ra không hợp lệ hoặc không phải cổng có hướng ra (OUT).` | 400 Bad Request | **TL-50** |
| **PROP-4.5.1-P13** | 4.5.1 Vehicle In/Out (`check-in`/`check-out`) | Invalid image URL format, directory traversal, or file not found on disk | SRS does not define image path validation | `Đường dẫn hình ảnh không hợp lệ hoặc tệp không tồn tại.` | 400 Bad Request | **TL-50** |
| **PROP-4.5.1-P14** | 4.5.1 Vehicle In/Out (`check-in`) | Employee attempts to override blacklist without manager authorization | SRS 4.5.1 does not define employee override error | `Nhân viên không có quyền ghi đè danh sách đen.` | 403 Forbidden | **TL-50** |
| **PROP-4.5.1-P15** | 4.5.1 Vehicle In/Out (`plate-scans`) | OCR engine concurrency gate timeout / back-pressure | SRS does not define OCR overload error | `Hệ thống nhận diện biển số xe đang quá tải, vui lòng thử lại sau.` | 503 Service Unavailable | **TL-50** |
| **PROP-4.5.1-P16** | 4.5.1 Vehicle In/Out (`plate-scans`) | License plate has uncataloged pattern, reserved code, or military syntax | SRS does not define uncataloged plate pattern review message | `Biển số xe có định dạng chưa được định nghĩa trong danh mục quy chuẩn hoặc thuộc nhóm cần xác minh thủ công.` | 200 OK (`NEEDS_REVIEW`) | **TL-51**, **OQ-86** |
| **PROP-4.5.2-P01** | 4.5.2 Parking Map / 4.5.1 Vehicle In/Out | Attempting to occupy or select a slot currently under maintenance | SRS does not define error dialogue string for maintenance slots | `Vị trí này đang bảo trì.` | 400 Bad Request | **OQ-63**, **OQ-67** |
| **PROP-4.5.2-P02** | `Sơ đồ bãi đậu xe` (`TL-03`) | Changing slot status away from `OCCUPIED` while an open session exists | FE & SRS do not define guard message | `Không thể chuyển trạng thái vị trí khi đang có xe đỗ trong ô.` | 400 Bad Request | **OQ-81** |
| **PROP-4.5.2-P03** | `Sơ đồ bãi đậu xe` (`TL-03`) | Manually setting slot to `OCCUPIED` without an open parking session | FE & SRS do not define guard message | `Không thể chuyển vị trí sang trạng thái đang có xe khi không có phiên đỗ xe đang mở.` | 400 Bad Request | **OQ-81** |
| **PROP-4.5.2-P04** | `Sơ đồ bãi đậu xe` (`TL-03`) | Manually setting slot to `AVAILABLE` while an active ticket or reservation exists | FE & SRS do not define guard message | `Không thể đánh dấu vị trí trống khi đang có xe đỗ hoặc đặt trước còn hiệu lực.` | 400 Bad Request | **OQ-81** |
| **PROP-4.5.2-P05** | 4.5.1 Vehicle In/Out (`TL-04`) | Attempting to enter a slot reserved via `slot_reservation` for another vehicle | FE & SRS do not define reservation conflict message | `Vị trí này đã được đặt trước cho phương tiện khác.` | 400 Bad Request | **OQ-81** |
| **PROP-4.5.2-P06** | `Sơ đồ bãi đậu xe` (`TL-12`) | Attempting `UPDATE` or `DELETE` on append-only `activity_log` | FE & SRS do not define immutability guard message | `Nhật ký hoạt động là bảng chỉ ghi (append-only), không cho phép cập nhật hoặc xóa.` | 400 Bad Request | **OQ-81** |

---

### 2.4. Ticket Management Module (SRS 4.6)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Decision ID |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-4.6.2-P01** | 4.6.2 Add Ticket (Save) | Ticket created successfully | SRS describes: "Một vé đã được thêm mới vào database..." | `Thêm mới vé đỗ xe thành công.` | 201 Created | **OQ-16** |
| **PROP-4.6.3-P01** | 4.6.3 Edit Ticket (Renew) | Ticket renewed successfully | SRS describes: "Dữ liệu được cập nhật vào bảng Vé..." | `Gia hạn vé đỗ xe thành công.` | 200 OK | **OQ-17** |
| **PROP-4.6.4-P01** | 4.6.4 Delete Ticket (Yes) | `CASE-4.6.4-TH1`: Ticket is active / not expired | SRS describes case: "vé được xóa là vé chưa hết hạn thì không được xóa" | `Vé chưa hết hạn, không được phép xóa.` | 400 Bad Request | **OQ-18** |
| **PROP-4.6.4-P02** | 4.6.4 Delete Ticket (Yes) | `CASE-4.6.4-TH1`: Ticket already renewed | Decomposed from TH1: "không cho phép xóa vé đã gia hạn" | `Vé đã được gia hạn, không được phép xóa.` | 400 Bad Request | **OQ-18** |
| **PROP-4.6.4-P03** | 4.6.4 Delete Ticket (Yes) | `CASE-4.6.4-TH2`: Concurrent deletion contention | SRS describes case: "vé được xóa đang được xóa bởi 1 người dùng khác thì không được xóa" | `Vé đang được xử lý bởi người dùng khác, vui lòng thử lại sau.` | 409 Conflict | **OQ-19** |
| **PROP-4.6.4-P04** | 4.6.4 Delete Ticket (Yes) | `CASE-4.6.4-TH3`: Connection error on delete | SRS describes case: "Vé được xóa không kết nối được" | `Lỗi kết nối cơ sở dữ liệu khi thực hiện xóa vé.` | 500 Internal Error | **OQ-20** |
| **PROP-4.6.4-P05** | 4.6.4 Delete Ticket (Yes) | Ticket not found or already deleted | SRS 4.6.4 contains zero Not Found message | `Vé không tồn tại hoặc đã bị xóa.` | 404 Not Found | **OQ-21** |

---

### 2.5. Statistics Module (SRS 4.7)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Decision ID |
| :---: | :--- | :--- | :--- | :--- | :--- | :---: |
| **PROP-4.7.1-P01** | 4.7.1 Aggregate Stats (Chart) | `CASE-4.7.1-TH2`: Invalid selection criteria | SRS states: "Không thống kê được do lỗi dữ liệu chọn không hợp lệ" | `Dữ liệu điều kiện thống kê không hợp lệ.` | 400 Bad Request | **OQ-34** |
| **PROP-4.7.1-P02** | 4.7.1 Aggregate Stats (Chart) | `CASE-4.7.1-TH3`: Connection error | SRS states: "Không thống kê được do lỗi kết nối" | `Lỗi kết nối hệ thống khi tạo biểu đồ thống kê.` | 500 Internal Error | **OQ-35** |
| **PROP-4.7.2-P01** | 4.7.2 Conditional Stats | `CASE-4.7.2-TH1`: No matching data | SRS states: "TH: Không có dữ liệu để thống kê" | `Không có dữ liệu phù hợp để thống kê.` | 200 OK (Empty) | **OQ-36** |
| **PROP-4.7.2-P02** | 4.7.2 Conditional Stats | `CASE-4.7.2-TH2`: Invalid date range criteria | SRS states: "TH: Dữ liệu nhập từ điều kiện thống kê chưa đúng" | `Khoảng thời gian thống kê không hợp lệ (Từ ngày phải nhỏ hơn hoặc bằng Đến ngày).` | 400 Bad Request | **OQ-37** |
| **PROP-4.7.2-P03** | 4.7.2 Conditional Stats | `CASE-4.7.2-TH3`: Connection error | SRS states: "TH: Lỗi kết nối" | `Lỗi kết nối hệ thống khi thực hiện thống kê.` | 500 Internal Error | **OQ-38** |

---

### 2.6. Parking Lot & Slot Management Module (SRS 4.8)

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Decision ID |
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
| **PROP-4.8.5-P02** | 4.8.5 Delete Slot (Delete) | `CASE-4.8.5-TH1`: Slot has active parking vehicle / ticket | SRS states: "TH: Xóa vị trí đang được xe đk vé đỗ" | `Vị trí đỗ xe đang có phương tiện đăng ký vé, không được phép xóa.` | 400 Bad Request | **OQ-31**, **OQ-32** |
| **PROP-4.8.5-P03** | 4.8.5 Delete Slot (Delete) | `CASE-4.8.5-TH2`: Slot deletion contention | SRS states: "TH: Xoa vị trí đang được xóa bởi người khác" | `Vị trí đỗ xe đang được xóa bởi người dùng khác.` | 409 Conflict | **OQ-32**, **OQ-33** |
| **PROP-4.8.5-P04** | 4.8.5 Delete Slot (Delete) | `CASE-4.8.5-TH3`: Connection error | SRS states: "TH: xóa nhưng không kết nối được" | `Lỗi kết nối máy chủ khi xóa vị trí đỗ xe.` | 500 Internal Error | **OQ-33** |
| **PROP-4.8.5-P05** | 4.8.5 Delete Slot (Delete) | Slot not found on delete request | SRS does not define 404 message | `Vị trí đỗ xe không tồn tại hoặc đã bị xóa.` | 404 Not Found | **OQ-30**, **OQ-33** |

---

### 2.7. Standard Generic API Error Envelope

| Proposal ID | Screen & Action | SRS Scenario / Behavior | Original SRS Status | Proposed Message [PROPOSAL] | HTTP Status | Decision ID |
| :---: | :--- | :--- | :--- | :--- | :---: | :---: |
| **PROP-GEN-P01** | Generic Error Envelope | General validation error envelope | SRS defines no generic 400 error string | `Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu` | 400 Bad Request | **OQ-13** |

---

### 2.8. Database Soft-Delete Guard Messages (`fn_guard_soft_delete_and_restore`, `TL-25`)

| Proposal ID | Target Table & Flow | Guard Condition (`BEFORE UPDATE OF deleted_at`) | Proposed Message [PROPOSAL] | HTTP Status | Decision ID |
| :---: | :--- | :--- | :--- | :---: | :---: |
| **PROP-DEL-01-SELF** | `account` (`DEL-01`) | Self-deletion of authenticated account (`NEW.deleted_by = OLD.id`) | `Tài khoản đang đăng nhập không được phép tự xóa chính mình.` | 400 Bad Request | **OQ-10**, **TL-25** |
| **PROP-DEL-01-LAST-MGR** | `account` (`DEL-01`) | Deleting the last active `MANAGER` account | `Không thể xóa tài khoản Quản lý hoạt động cuối cùng trong hệ thống.` | 400 Bad Request | **OQ-10**, **TL-25** |
| **PROP-DEL-01-SELF-EMP** | `employee` (`DEL-01`) | Self-deletion of authenticated employee profile (`NEW.deleted_by = OLD.account_id`) | `Nhân viên đang đăng nhập không được phép tự xóa hồ sơ của chính mình.` | 400 Bad Request | **OQ-10**, **TL-25** |
| **PROP-DEL-01-LAST-MGR-EMP** | `employee` (`DEL-01`) | Deleting employee linked to the last active `MANAGER` account | `Không thể xóa nhân viên gắn với tài khoản Quản lý hoạt động cuối cùng.` | 400 Bad Request | **OQ-10**, **TL-25** |
| **PROP-DEL-02-ACTIVE-VEH** | `customer` (`DEL-02`) | Customer still owns active (`deleted_at IS NULL`) vehicles | `Khách hàng đang có phương tiện hoạt động trong hệ thống, không được phép xóa.` | 400 Bad Request | **OQ-40**, **TL-25** |
| **PROP-DEL-03-OPEN-SES** | `vehicle` (`DEL-03`) | Vehicle has an open parking session (`exit_time IS NULL`) | `Phương tiện đang đỗ trong bãi xe (có phiên đỗ đang mở), không được phép xóa.` | 409 Conflict | **OQ-41**, **TL-25** |
| **PROP-DEL-03-ACTIVE-TKT** | `vehicle` (`DEL-03`) | Vehicle holds an active unexpired ticket | `Phương tiện đang có vé đỗ xe còn hiệu lực, không được phép xóa.` | 409 Conflict | **OQ-41**, **TL-25** |
| **PROP-DEL-03-ACTIVE-RSV** | `vehicle` (`DEL-03`) | Vehicle holds an active advance slot reservation | `Phương tiện đang có đặt trước vị trí đỗ xe còn hiệu lực, không được phép xóa.` | 409 Conflict | **OQ-41**, **TL-25** |
| **PROP-DEL-04-OPEN-SES** | `ticket` (`DEL-04`) | Linked vehicle currently has an open parking session (`exit_time IS NULL`) | `Phương tiện liên kết với vé đang đỗ trong bãi xe, không được phép xóa vé.` | 400 Bad Request | **OQ-42**, **TL-25** |
| **PROP-DEL-05-OCCUPIED** | `parking_slot` (`DEL-05`) | Slot status is `'OCCUPIED'`/`'CHARGING'` or has an open parking session | `Không thể xóa vị trí đỗ xe đang có phương tiện đỗ (trạng thái OCCUPIED).` | 400 Bad Request | **OQ-31**, **OQ-43**, **TL-25** |
| **PROP-DEL-05-RESERVED** | `parking_slot` (`DEL-05`) | Slot has an active reservation (`slot_reservation`) or status `'RESERVED'` | `Vị trí đỗ xe đang được đặt trước còn hiệu lực, không được phép xóa.` | 400 Bad Request | **OQ-43**, **TL-25** |
| **PROP-DEL-06-LOT** | `parking_lot` (`DEL-06`) | Parking lot still has active (`deleted_at IS NULL`) floors | `Bãi đỗ xe còn tầng đang hoạt động, không được phép xóa.` | 400 Bad Request | **TL-25** |
| **PROP-DEL-06-FLOOR** | `parking_floor` (`DEL-06`) | Parking floor still has active (`deleted_at IS NULL`) zones | `Tầng bãi xe còn khu vực (zone) đang hoạt động, không được phép xóa.` | 400 Bad Request | **TL-25** |
| **PROP-DEL-06-ZONE** | `parking_zone` (`DEL-06`) | Parking zone still has active (`deleted_at IS NULL`) slots | `Khu vực đỗ xe còn vị trí (slot) đang hoạt động, không được phép xóa.` | 400 Bad Request | **TL-25** |
| **PROP-DEL-06-TICKET-TYPE** | `ticket_type` (`DEL-06`) | Ticket type is referenced by active unexpired tickets | `Loại vé đang được sử dụng bởi các vé còn hiệu lực, không được phép xóa.` | 400 Bad Request | **TL-25** |
| **PROP-DEL-06-POSITION** | `position` (`DEL-06`) | Position is assigned to active (`deleted_at IS NULL`) employees | `Chức vụ đang được phân công cho nhân viên đang hoạt động, không được phép xóa.` | 400 Bad Request | **TL-25** |
| **PROP-DEL-06-VEHICLE-TYPE** | `vehicle_type` (`DEL-06`) | Vehicle type is linked to active (`deleted_at IS NULL`) vehicles | `Loại xe đang được liên kết với phương tiện đang hoạt động, không được phép xóa.` | 400 Bad Request | **TL-25** |
| **PROP-DEL-06-GATE** | `parking_gate` (`DEL-06`) | Gate is handling an open parking session (`exit_time IS NULL`) | `Cổng kiểm soát đang xử lý phiên đỗ xe chưa hoàn thành, không được phép xóa.` | 400 Bad Request | **TL-25** |
| **PROP-DEL-SAVT-IN-USE** | `slot_allowed_vehicle_type` | Deleting type from slot currently referenced by active tickets, open sessions, or reservations (`trg_guard_slot_allowed_vehicle_type_delete`) | `Không thể xóa loại xe khỏi vị trí đỗ khi đang có vé, phiên đỗ hoặc đặt chỗ hiệu lực của loại xe này.` | 400 Bad Request | **TL-37** |
| **PROP-SLOT-VEHICLE-TYPE-MISMATCH** | `ticket`, `slot_reservation`, `log` | Assigning/parking vehicle into slot not allowing vehicle's type | `Loại phương tiện không tương thích với danh sách loại xe cho phép của vị trí đỗ này.` | 400 Bad Request | **TL-38** |
| **PROP-DEL-PAYMENT-SETTLED** | `payment` | Soft-deleting payment with `status IN ('PAID', 'REFUNDED')` | `Không thể xóa giao dịch thanh toán đã hoàn thành (PAID) hoặc đã hoàn tiền (REFUNDED).` | 400 Bad Request | **TL-39** |
| **PROP-PAY-STATUS-TRANSITION** | `payment` (`trg_guard_payment_update`) | Invalid status transition (`UNPAID -> PAID/CANCELLED`, `PAID -> REFUNDED` only; terminal statuses) | `Chuyển đổi trạng thái thanh toán không hợp lệ.` | 400 Bad Request | **TL-42** |
| **PROP-PAY-SETTLED-IMMUTABLE** | `payment` (`trg_guard_payment_update`) | Modifying financial or link columns on settled/refunded payments (`status IN ('PAID', 'REFUNDED')`) | `Không thể chỉnh sửa thông tin tài chính hoặc liên kết của chứng từ thanh toán đã hoàn thành (PAID) hoặc đã hoàn tiền (REFUNDED).` | 400 Bad Request | **TL-42** |

---

## 3. Governance and Implementation Protocol

1. Backend developers and AI coding agents **MUST NOT** modify the strings above without authorization.
2. In API serializers, exception handlers, and PostgreSQL triggers (`fn_guard_soft_delete_and_restore`), reference centralized constants (e.g. `apps.core.messages.PROPOSAL_MESSAGES`), explicitly marking `[PROPOSAL]` and referencing `PROP-` IDs.
3. All proposed message strings in this catalog are decided by the Team Lead (`TL-19`, `TL-22`, `TL-25`) and linked to [`docs/requirements/01-decision-log.md`](01-decision-log.md) and [`docs/requirements/06-frontend-srs-db-alignment.md`](06-frontend-srs-db-alignment.md).
