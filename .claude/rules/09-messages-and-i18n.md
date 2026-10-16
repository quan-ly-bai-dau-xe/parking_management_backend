# 09-messages-and-i18n.md — Verbatim Messages & Localization Standards

## 1. Verbatim Message Authority

- All user-facing error and notification strings returned by the API must be transcribed verbatim from `docs/requirements/00-srs-catalog.md` and `docs/requirements/03-delete-rules-catalog.md`.
- Never invent error messages or paraphrase SRS strings. Historical refuted inventions are strictly forbidden.
- For behaviors lacking verbatim messages, refer to `docs/requirements/05-proposed-messages.md` for proposals (`[PROPOSAL]`).

## 2. Check_Quality Formatting Rules (Item 6)

- **Punctuation**: Verbatim SRS messages terminate without ending punctuation (e.g., `Đã thêm thành công nhân viên`, `Xóa thành công`). Preserve verbatim text without adding invented periods. Proposed messages include ending periods pending PO review (OQ-46).
- **Item Name**: Errors for specific fields must include the field name (e.g., `Dữ liệu {item} không hợp lệ, xin mời nhập lại dữ liệu`).

## 3. Core Verbatim Messages by Module

- **Login (4.1)**:
  - `MSG-4.1-M01`: `Tên đăng nhập không chứa ký tự đặc biệt`
  - `MSG-4.1-M02`: `Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu`
  - `MSG-4.1-M03`: `Xin nhập đầy đủ Tên đăng nhập và Mật khẩu`
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
- **Vehicle In/Out & Parking Map (4.5)**:
  - `MSG-4.5.1-M01`: `Không tìm thấy dữ liệu trùng khớp` | `MSG-4.5.1-M02`: `Lỗi dữ liệu không tìm thấy đê lưu`
  - `MSG-4.5.1-M03` / `MSG-4.5.2-M01`: `lỗi kết nối` / `Lỗi kết nối` | `MSG-4.5.2-M02`: `Vị trí này đã có xe đk vé và đang sử dụng`
- **Ticket (4.6)**:
  - `MSG-4.6.4-M01`: `Xóa thành công` | `MSG-4.6.1-M01`: `Không tìm thấy dữ liệu`
  - `MSG-4.6.2-M01`: `Dữ liệu {item} không hợp lệ` | `MSG-4.6.3-M01`: `Lỗi dữ liệu trên {item} không hợp lệ`
- **Statistics (4.7)**: `MSG-4.7.1-M01`: `Dữ liệu không tìm thấy`
- **Parking Lot (4.8)**:
  - `MSG-4.8.4-M01`: `Có vấn đề, Không thể quay lại trang danh sách vị trí` | `MSG-4.8.5-M04`: `Lỗi kết nối`
