# 09-messages-and-i18n.md — Verbatim Messages & Localization Standards

## 1. Message & Label Authority Hierarchy

1. **Primary — Frontend Design (`FE`)**: UI labels, status badge strings, and dialog texts from the 11 Frontend screens (`docs/requirements/06-frontend-srs-db-alignment.md`, `TL-01`–`TL-35`) take first priority.
2. **Secondary — SRS v4.1 (`SRS`)**: Where the Frontend is silent, user-facing error and notification strings must be transcribed verbatim from `docs/requirements/00-srs-catalog.md` and `docs/requirements/03-delete-rules-catalog.md`.
3. **Tertiary — Explicit Proposals (`[PROPOSAL]`)**: For behaviors lacking verbatim text in both the Frontend and the SRS, use the registered `[PROPOSAL]` strings in `docs/requirements/05-proposed-messages.md` (`PROP-*`, `PROP-DEL-*`) linked to their Decision IDs (`OQ-*`, `TL-25`) in `docs/requirements/01-decision-log.md` and `docs/requirements/06-frontend-srs-db-alignment.md`.

## 2. Check_Quality Formatting Rules (Item 6)

- **Punctuation**: Verbatim SRS messages terminate without ending punctuation (e.g., `Đã thêm thành công nhân viên`, `Xóa thành công`). Preserve verbatim text without adding invented periods. Proposed messages (`PROP-*`, `PROP-DEL-*`) include ending periods as decided in `OQ-46`, `OQ-81`, and `TL-25`.
- **Item Name**: Errors for specific fields must include the field name (e.g., `Dữ liệu {item} không hợp lệ, xin mời nhập lại dữ liệu`).

## 3. Core Verbatim & Proposed Messages by Module

- **Login (4.1 / FE `login-container.png` `TL-01`)**:
  - FE Login Field Label: `Email hoặc Số điện thoại` (`Nhập email hoặc số điện thoại`)
  - `MSG-4.1-M02`: `Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu` | `MSG-4.1-M03`: `Xin nhập đầy đủ Tên đăng nhập và Mật khẩu`
- **Home (4.2)**: `MSG-4.2-M01`: `Thông báo lỗi hệ thống` | `MSG-4.2-M02`: `Thông báo lỗi hệ thống, hoặc lỗi kết nối mạng`
- **Employee (4.3)**:
  - `MSG-4.3.2-M01`: `Đã thêm thành công nhân viên` | `MSG-4.3.1-M01` / `MSG-4.3.4-M01`: `Xóa thành công`
  - `MSG-4.3.4-M02`: `Dữ liệu không tồn tại` | `MSG-4.3.1-M02`: `Kết nối cơ sở dữ liệu hoặc thông tin không tồn tại`
  - `MSG-4.3.1-M03`: `Dữ liệu hiện đang được cập nhật bởi user khác` | `MSG-4.3.4-M03`: `Lỗi kết nối server`
  - `MSG-4.3.1-M05`: `Không có dữ liệu trùng` | `MSG-4.3.1-M07`: `Không có dữ liệu được tìm thấy`
  - `MSG-4.3.2-M02`: `Dữ liệu {item} không hợp lệ, xin mời nhập lại dữ liệu` | `MSG-4.3.3-M01`: `Dữ liệu {item} không đúng định dạng, ..`
- **Customer (4.4)**:
  - `MSG-4.4.5-M01`: `Xóa thành công` | `MSG-4.4.5-M02`: `Dữ liệu đang được xóa bởi người dùng khác`
  - `MSG-4.4.1-M01`: `Không tìm thấy dữ liệu` | `MSG-4.4.1-M02`: `Lỗi không kết nối được Server` | `MSG-4.4.5-M03`: `Lỗi server`
  - `MSG-4.4.3-M01` / `MSG-4.4.4-M03`: `Lỗi hệ thống` | `MSG-4.4.3-M02` / `MSG-4.4.4-M01`: `Dữ liệu trên trường {item} không đúng định dạng …`
- **Vehicle In/Out, Parking Map & Activity Log (4.5 / FE `Sơ đồ bãi đậu xe` `TL-03`, `TL-04`, `TL-12`)**:
  - `MSG-4.5.1-M01`: `Không tìm thấy dữ liệu trùng khớp` | `MSG-4.5.1-M02`: `Lỗi dữ liệu không tìm thấy đê lưu`
  - `MSG-4.5.1-M03` / `MSG-4.5.2-M01`: `lỗi kết nối` / `Lỗi kết nối` | `MSG-4.5.2-M02`: `Vị trí này đã có xe đk vé và đang sử dụng`
  - `PROP-4.5.2-P01` (`[PROPOSAL]`, `OQ-63`, `OQ-67`): `Vị trí này đang bảo trì.`
  - `PROP-4.5.2-P02` (`[PROPOSAL]`, `OQ-81`): `Không thể chuyển trạng thái vị trí khi đang có xe đỗ trong ô.`
  - `PROP-4.5.2-P03` (`[PROPOSAL]`, `OQ-81`): `Không thể chuyển vị trí sang trạng thái đang có xe khi không có phiên đỗ xe đang mở.`
  - `PROP-4.5.2-P04` (`[PROPOSAL]`, `OQ-81`): `Không thể đánh dấu vị trí trống khi đang có xe đỗ hoặc đặt trước còn hiệu lực.`
  - `PROP-4.5.2-P05` (`[PROPOSAL]`, `OQ-81`): `Vị trí này đã được đặt trước cho phương tiện khác.`
  - `PROP-4.5.2-P06` (`[PROPOSAL]`, `OQ-81`): `Nhật ký hoạt động là bảng chỉ ghi (append-only), không cho phép cập nhật hoặc xóa.`
- **Ticket (4.6)**:
  - `MSG-4.6.4-M01`: `Xóa thành công` | `MSG-4.6.1-M01`: `Không tìm thấy dữ liệu`
  - `MSG-4.6.2-M01`: `Dữ liệu {item} không hợp lệ` | `MSG-4.6.3-M01`: `Lỗi dữ liệu trên {item} không hợp lệ`
- **Statistics (4.7)**: `MSG-4.7.1-M01`: `Dữ liệu không tìm thấy`
- **Parking Lot (4.8) & Soft-Delete Guards (`DEL-01`–`DEL-06`, `TL-25`)**:
  - `MSG-4.8.4-M01`: `Có vấn đề, Không thể quay lại trang danh sách vị trí` | `MSG-4.8.5-M04`: `Lỗi kết nối`
  - `PROP-DEL-01-SELF`..`PROP-DEL-06-GATE` (`[PROPOSAL]`, `TL-25`): Registered in `docs/requirements/05-proposed-messages.md` Section 2.8 and enforced by `fn_guard_soft_delete_and_restore()`.
