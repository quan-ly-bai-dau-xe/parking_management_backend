# Verified SRS Requirements Catalog

This catalog is authoritative for the SRS content — all functional requirements, data fields, validation rules, user actions, and verbatim dialogue messages extracted directly from `Quan ly bai dau xe oto_SRS_v4.1.docx` and the 25 embedded wireframe diagrams (`image1.png` through `image25.png`) — and serves as the secondary source of truth to the Frontend design ([`06-frontend-srs-db-alignment.md`](06-frontend-srs-db-alignment.md), `TL-19`).

Every requirement is assigned a stable identifier (Stable ID) and a stable citation (Section + Table Name + Row/Item Label, or `image N: element`). File line numbers are strictly prohibited as citations.

---

## 1. Stable Identifier Conventions

- **Data Field**: `REQ-<Screen>-F<Sequence>` (e.g., `REQ-4.1-F01`, `REQ-4.3.2-F07`).
- **User Action**: `ACT-<Screen>-A<Sequence>` (e.g., `ACT-4.1-A01`, `ACT-4.3.4-A01`).
- **Verbatim Message**: `MSG-<Screen>-M<Sequence>` (e.g., `MSG-4.1-M01`, `MSG-4.3.2-M02`).
- **Case Description**: `CASE-<Screen>-TH<Sequence>` (e.g., `CASE-4.6.4-TH1`, `CASE-4.8.5-TH1`), applied when the SRS describes failure or exception conditions without quoted dialog text or explicit message strings. Accompanied by annotation `NO SRS MESSAGE - see OQ-xx`.

---

## 2. Screen Requirements Specifications (Sections 4.1 through 4.8)

---

### 4.1. Màn Hình Đăng Nhập (Login)

- **Stable Citation**: SRS Section 4.1, Bảng `Đăng nhập`. Wireframe: `image2.png`.
- **Description**: Cho phép người dùng đăng nhập vào hệ thống.
- **Access Method**: Click vào chương trình sẽ hiển thị lên giao diện đăng nhập.

#### 4.1.1. Data Field Inventory (Fields)

| Stable ID | Item Name | Data Type | Length | Required (inferred) | Default | Stable Citation | Description & Business Rules |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- | :--- |
| **REQ-4.1-F01** | Tên đăng nhập | Text field | *(Không ghi)* | Có | Trống | SRS 4.1, Table Đăng nhập, Row 5 | Nhập tên đăng nhập được admin cấp điền vào để đăng nhập hệ thống. So sánh ở `ACCOUNT.TenDangNhap`. Không chứa ký tự đặc biệt. |
| **REQ-4.1-F02** | Mật khẩu | Password field | *(Không ghi)* | Có | Trống | SRS 4.1, Table Đăng nhập, Row 6 | Nhập mật khẩu để đăng nhập. So sánh ở `ACCOUNT.MatKhau`. |
| **REQ-4.1-F03** | Ghi nhớ mật khẩu | Checkbox | 1 bit | Không | Trống (Unchecked) | SRS 4.1, Table Đăng nhập, Row 7 | Khi user click vào ô checkbox thì lưu token đăng nhập phiên làm việc (Thay thế quy định cookie mật khẩu plaintext để đảm bảo an ninh OWASP). |
| **REQ-4.1-F04** | Quên mật khẩu | Link | N/A | N/A | N/A | SRS 4.1, Table Đăng nhập, Row 8 | Khi quên mật khẩu, click vào để lấy lại mật khẩu thông qua email đã đăng ký. |

#### 4.1.2. Action Inventory (Actions)

| Stable ID | Action Name | Stable Citation | Operation Description | Successful Outcome | Failure Outcome & Exceptions |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ACT-4.1-A01** | Log in | SRS 4.1, Table Đăng nhập, Row 11 | Sau khi điền Tên đăng nhập và mật khẩu thì click vào nút "Log in" để tiến hành đăng nhập. | Hiển thị trang chủ của hệ thống. | Trả về thông báo lỗi tương ứng theo từng trường hợp kiểm tra. |
| **ACT-4.1-A02** | Reset | SRS 4.1, Table Đăng nhập, Row 12 | Xóa tên đăng nhập và mật khẩu vừa điền. | Xóa các trường dữ liệu vừa nhập trên giao diện. | N/A |

#### 4.1.3. Verbatim Message Inventory (Verbatim Messages)

| Stable ID | Verbatim Message (Source String) | Type | Trigger Condition | Stable Citation |
| :--- | :--- | :---: | :--- | :--- |
| **MSG-4.1-M01** | `Tên đăng nhập không chứa ký tự đặc biệt` | Thất bại | Nhập tên đăng nhập với các ký tự sai, ký tự đặc biệt. | SRS 4.1, Table Đăng nhập, Row 11 |
| **MSG-4.1-M02** | `Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu` | Thất bại | Nhập tên đăng nhập sai, hoặc mật khẩu sai. | SRS 4.1, Table Đăng nhập, Row 11 |
| **MSG-4.1-M03** | `Xin nhập đầy đủ Tên đăng nhập và Mật khẩu` | Thất bại | Để trống Tên đăng nhập hoặc Mật khẩu khi bấm Log in. | SRS 4.1, Table Đăng nhập, Row 11 |

---

### 4.2. Màn Hình Trang Chủ (Home)

- **Stable Citation**: SRS Section 4.2, Bảng `Trang chủ`. Wireframe: `image3.png`.
- **Description**: Đăng nhập thành công vào hệ thống, đầu tiên sẽ hiện lên giao diện trang chủ cho người dùng.
- **Access Method**: Login thành công từ giao diện Đăng nhập.

#### 4.2.1. Screen Elements Inventory (Items)

| Stable ID | Item Name | Type | Permitted Role | Stable Citation | Functional Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-4.2-F01** | Trang chủ | Tab | Tất cả | SRS 4.2, Table Trang chủ, Row 5 | Mặc định khi đăng nhập thành công vào hệ thống. |
| **REQ-4.2-F02** | Thông tin ở trang chủ | Label String | Tất cả | SRS 4.2, Table Trang chủ, Row 6 | Hiển thị thông tin của hệ thống, thông báo hoặc những vấn đề liên quan. |
| **REQ-4.2-F03** | Quản lý nhân viên | Tab | Quản lý | SRS 4.2, Table Trang chủ, Row 7 | Chỉ có Quản lý mới có thể sử dụng Tab này để quản lý. Khi click sẽ hiển thị giao diện Quản lý nhân viên. |
| **REQ-4.2-F04** | Quản lý khách hàng | Tab | Quản lý, Nhân viên | SRS 4.2, Table Trang chủ, Row 8 | Khi click vào sẽ hiển thị ra giao diện Quản lý khách hàng. |
| **REQ-4.2-F05** | Quản lý xe vào/ra | Tab | Quản lý, Nhân viên | SRS 4.2, Table Trang chủ, Row 9 | Khi click vào sẽ hiển thị ra giao diện Quản lý xe vào ra. |
| **REQ-4.2-F06** | Quản lý vé | Tab | Quản lý, Nhân viên | SRS 4.2, Table Trang chủ, Row 10 | Khi click vào sẽ hiển thị ra giao diện Quản lý vé. |
| **REQ-4.2-F07** | Thống kê | Tab | Quản lý | SRS 4.2, Table Trang chủ, Row 11 | Khi click vào sẽ hiển thị ra giao diện thống kê. |
| **REQ-4.2-F08** | Quản lý bãi đổ xe | Tab | Quản lý | SRS 4.2, Table Trang chủ, Row 12 | Khi click vào sẽ hiển thị ra giao diện Quản lý bãi đỗ xe. |
| **REQ-4.2-F09** | Bảng thông báo | Table | Tất cả | SRS 4.2, Table Trang chủ, Row 13 | Hiển thị các thông báo từ hệ thống đến người dùng. |

#### 4.2.2. Danh Sách Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Thông Báo Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.2-A01** | Thoát | SRS 4.2, Table Trang chủ, Row 16 | Đăng xuất khỏi hệ thống. | `Thông báo lỗi hệ thống` (**MSG-4.2-M01**) |
| **ACT-4.2-A02** | Điều hướng Tab | SRS 4.2, Table Trang chủ, Rows 17-22 | Đi đến giao diện tương ứng của Tab được chọn. | `Thông báo lỗi hệ thống, hoặc lỗi kết nối mạng` (**MSG-4.2-M02**) |

---

### 4.3. Quản Lý Nhân Viên

#### 4.3.1. Danh Sách Nhân Viên

- **Stable Citation**: SRS Section 4.3.1, Bảng `Quản lý nhân viên`. Wireframe: `image4.png`.
- **Description**: Người quản lý có thể Xem được danh sách Nhân viên / Tìm kiếm / Sửa / Xóa thông tin Nhân viên.

##### Danh Sách Trường Hiển Thị & Tìm Kiếm

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Độ Dài | Bắt Buộc (inferred) | Trích Dẫn Ổn Định | Mô Tả & Ánh Xạ CSDL |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **REQ-4.3.1-F01** | ID | Label - Alpha numeric | 5 | Có | SRS 4.3.1, Row 5 | Lấy từ `NHAN_VIEN.ID_NV`. Mã định danh nhân viên. |
| **REQ-4.3.1-F02** | Họ tên | Label - String | 45 | Có | SRS 4.3.1, Row 6 | Lấy từ `NHANVIEN_HoTenNV`. Hiển thị họ tên nhân viên. |
| **REQ-4.3.1-F03** | Ngày Sinh | Label – date | N/A | Có | SRS 4.3.1, Row 7 | Lấy từ `NHANVIEN_NgaySinh`. Hiển thị ngày sinh. |
| **REQ-4.3.1-F04** | Chức vụ | Label - String | 45 | Có | SRS 4.3.1, Row 8 | Lấy từ `NHANVIEN_ChucVu`. Hiển thị chức vụ nhân viên. |
| **REQ-4.3.1-F05** | Giới Tính | Label – String | N/A | Có | SRS 4.3.1, Row 9 | Lấy từ `NHANVIEN_GioiTinh`. Hiển thị giới tính. |
| **REQ-4.3.1-F06** | Địa Chỉ | Label - String | N/A | Có | SRS 4.3.1, Row 10 | Lấy từ `NHANVIEN_DiaChi`. Hiển thị địa chỉ. |
| **REQ-4.3.1-F07** | Email | Label - String | N/A | Có | SRS 4.3.1, Row 11 | Lấy từ `NHANVIEN-Email`. Hiển thị email. |
| **REQ-4.3.1-F08** | Họ và tên (Tìm kiếm) | Input – text | 45 (inferred) | Không | SRS 4.3.1, Row 16 | Nhập Họ tên để tìm kiếm nhân viên. |
| **REQ-4.3.1-F09** | Sinh ngày từ | Input - Datepicker | N/A | Không | SRS 4.3.1, Row 17 | Tìm kiếm nhân viên có ngày sinh từ mốc này. |
| **REQ-4.3.1-F10** | Đến ngày | Input - Datepicker | N/A | Không | SRS 4.3.1, Row 18 | Tìm kiếm nhân viên có ngày sinh đến mốc này. |
| **REQ-4.3.1-F11** | ID Nhân viên (Tìm kiếm) | Input – text | 5 (inferred) | Không | SRS 4.3.1, Row 19 | Nhập Mã nhân viên để tìm kiếm. |
| **REQ-4.3.1-F12** | Sống tại | Input – text | 45 (inferred) | Không | SRS 4.3.1, Row 20 | Nhập Địa chỉ nhân viên để tìm kiếm. |

##### Danh Sách Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại & Concurrency (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.3.1-A01** | Xóa | SRS 4.3.1, Row 24 | `Xóa thành công` (**MSG-4.3.1-M01**) | `Kết nối cơ sở dữ liệu hoặc thông tin không tồn tại` (**MSG-4.3.1-M02**) |
| **ACT-4.3.1-A02** | Chỉnh sửa | SRS 4.3.1, Row 25 | Dữ liệu thay đổi được cập nhật | - Concurrency: `Dữ liệu hiện đang được cập nhật bởi user khác` (**MSG-4.3.1-M03**)<br>- Invalid: Hiển thị thông báo phù hợp từng trường<br>- Server: `Server tạm thời không kết nối được` (**MSG-4.3.1-M04**) |
| **ACT-4.3.1-A03** | Tìm kiếm | SRS 4.3.1, Row 26 | Hiển thị thông tin theo điều kiện | - Không có dữ liệu: `Không có dữ liệu trùng` (**MSG-4.3.1-M05**)<br>- Server: `Server hiện tại chưa connect được` (**MSG-4.3.1-M06**) |
| **ACT-4.3.1-A04** | List Nhân viên | SRS 4.3.1, Row 28 | Hiển thị đầy đủ thông tin có phân trang | `Không có dữ liệu được tìm thấy` (**MSG-4.3.1-M07**) |

---

#### 4.3.2. Thêm Mới Nhân Viên

- **Stable Citation**: SRS Section 4.3.2, Bảng `Thêm nhân viên`. Wireframe: `image5.png`.
- **Description**: Người dùng nhập vào thông tin của Nhân viên để thực hiện thêm mới 1 Nhân viên.

##### Danh Sách Trường Dữ Liệu

| Stable ID | Tên Trường (Item) | Kiểu Dữ Liệu (Type) | Độ Dài (Length) | Bắt Buộc (inferred) | Mặc Định | Trích Dẫn Ổn Định | Mô Tả & Quy Tắc Nghiệp Vụ |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- | :--- |
| **REQ-4.3.2-F01** | Họ tên | Text field - String | 45 | Có | Trống | SRS 4.3.2, Row 5 | Nhập họ và tên nhân viên. Lưu vào `NHAN_VIEN.ID_NV`. |
| **REQ-4.3.2-F02** | Ngày sinh | Text field – Date | N/A | Có | Date Picker | SRS 4.3.2, Row 6 | Nhập ngày tháng năm sinh. Cập nhật `NgaySinhNV`. |
| **REQ-4.3.2-F03** | Địa chỉ | Text field - String | **45** | Có | Trống | SRS 4.3.2, Row 7 | **Độ dài tối đa 45 ký tự** (Lưu ý F6). Cập nhật `DiaChiNV`. |
| **REQ-4.3.2-F04** | Chức vụ | Dropdown list - String | 45 | Có | Chọn đầu | SRS 4.3.2, Row 8 | Chọn chức vụ từ bảng Chức vụ. So sánh `NHANVIEN_ChucVu`. |
| **REQ-4.3.2-F05** | Email | Text field - String | 45 | Có | Trống | SRS 4.3.2, Row 9 | Nhập địa chỉ Email. Cập nhật `MailNV`. |
| **REQ-4.3.2-F06** | ID | Text field - Alpha numeric | 5 | Có | Trống | SRS 4.3.2, Row 10 | Nhập Mã Nhân viên (5 ký tự chữ và số). Cập nhật `ID_NV`. |
| **REQ-4.3.2-F07** | Giới tính | Dropdown list – String | 50 | Có | Chọn đầu | SRS 4.3.2, Row 11 | Chọn từ combobox – Nữ/Nam. Chọn ở `NHANVIEN_SexNV`. |
| **REQ-4.3.2-F08** | SĐT | Text field – Number | **15** | Có | Trống | SRS 4.3.2, Row 12 | **Độ dài số tối đa 15 chữ số** (Lưu ý F6). Cập nhật `SDT_NV`. |
| **REQ-4.3.2-F09** | Mật khẩu | Text field - String | 50 | Có | Trống | SRS 4.3.2, Row 13 | Thiết lập mặc định mật khẩu nhân viên. |

##### Danh Sách Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công (Nguyên Văn) | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.3.2-A01** | Lưu | SRS 4.3.2, Row 18 | `Đã thêm thành công nhân viên` (**MSG-4.3.2-M01**) | - Dữ liệu không hợp lệ: `Dữ liệu {item} không hợp lệ, xin mời nhập lại dữ liệu` (**MSG-4.3.2-M02**)<br>- Lỗi server: `server tạm thời không kết nối được` (**MSG-4.3.2-M03**) |
| **ACT-4.3.2-A02** | Hủy | SRS 4.3.2, Row 19 | Tất cả dữ liệu trên popup Thêm mới nhân viên sẽ trở về trạng thái đầu tiên load form. | N/A |

---

#### 4.3.3. Sửa Thông Tin Nhân Viên

- **Stable Citation**: SRS Section 4.3.3, Bảng `Sửa thông tin nhân viên`. Wireframe: `image6.png`.

##### Danh Sách Trường Dữ Liệu

| Stable ID | Tên Trường (Item) | Kiểu Dữ Liệu (Type) | Độ Dài | Quyền Sửa | Trích Dẫn Ổn Định | Quy Tắc Nghiệp Vụ Cụ Thể |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **REQ-4.3.3-F01** | Họ tên | Text field - String | 45 | Có | SRS 4.3.3, Row 5 | Nhập họ và tên nhân viên. |
| **REQ-4.3.3-F02** | Ngày sinh | Text field – Date | N/A | Có | SRS 4.3.3, Row 6 | Cập nhật `NgaySinhNV`. |
| **REQ-4.3.3-F03** | Địa chỉ | Text field - String | 45 | Có | SRS 4.3.3, Row 7 | Nhập địa chỉ (tối đa 45 ký tự). |
| **REQ-4.3.3-F04** | Chức vụ | Dropdown list - String | 45 | Có | SRS 4.3.3, Row 8 | Chọn chức vụ từ danh sách. |
| **REQ-4.3.3-F05** | Email | Text field - String | 45 | Có | SRS 4.3.3, Row 9 | Nhập địa chỉ Email đúng định dạng. |
| **REQ-4.3.3-F06** | ID | Label | 5 | **KHÔNG** | SRS 4.3.3, Row 10 | **Mã nhân viên không được chỉnh sửa** (`read_only=True`). |
| **REQ-4.3.3-F07** | Mật Khẩu | Text | 50 | Có | SRS 4.3.3, Row 11 | **Mật khẩu phải đúng định dạng, có ký tự số, đặc biệt, chữ hoa, chữ thường** (Lưu ý F6). |
| **REQ-4.3.3-F08** | Giới tính | Text | N/A | Có | SRS 4.3.3, Row 12 | Chọn từ dữ liệu dropdownlist Nam/Nữ. |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.3.3-A01** | Cập Nhật | SRS 4.3.3, Row 17 | Dữ liệu được cập nhật vào bảng Nhân viên (NO SRS MESSAGE - see OQ-13) | - Format lỗi: `Dữ liệu {item} không đúng định dạng, ..` (**MSG-4.3.3-M01**)<br>- Server: `lõi kết nối lên Server` (**CASE-4.3.3-TH2**; NO SRS MESSAGE - see OQ-13) |
| **ACT-4.3.3-A02** | Hủy | SRS 4.3.3, Row 18 | Đóng popup Sửa Nhân viên và quay lại danh sách | `Thông báo lỗi Server` (**MSG-4.3.3-M02**) |

---

#### 4.3.4. Xóa Thông Tin Nhân Viên

- **Stable Citation**: SRS Section 4.3.4, Bảng `Xóa thông tin Nhân viên`. Wireframe: `image7.png`.

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công (Nguyên Văn) | Thất Bại & Concurrency (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.3.4-A01** | Xác nhận | SRS 4.3.4, Row 10 | `Xóa thành công` (**MSG-4.3.4-M01**) | - Đã bị xóa trước: `Dữ liệu không tồn tại` (**MSG-4.3.4-M02**)<br>- Server: `Lỗi kết nối server` (**MSG-4.3.4-M03**) |
| **ACT-4.3.4-A02** | Hủy | SRS 4.3.4, Row 11 | Dữ liệu cần xóa không xóa và quay lại màn hình danh sách nhân viên | N/A |

---

### 4.4. Quản Lý Khách Hàng

#### 4.4.1. Danh Sách Khách Hàng

- **Stable Citation**: SRS Section 4.4.1, Bảng `Danh sách khách hàng`. Wireframe: `image8.png`.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Độ Dài | Trích Dẫn Ổn Định | Mô Tả |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **REQ-4.4.1-F01** | MaKH | Label - Alpha numeric | 5 | SRS 4.4.1, Row 5 | Hiển thị `KHACH_HANG.ID_KH`. |
| **REQ-4.4.1-F02** | Họ tên | Label - String | 45 | SRS 4.4.1, Row 6 | Hiển thị `KHACH_HANG.HoTenKH`. |
| **REQ-4.4.1-F03** | Ngày sinh | Label – date | N/A | SRS 4.4.1, Row 7 | Hiển thị `KhachHang_NgaySinh`. |
| **REQ-4.4.1-F04** | CMND | Label – string | N/A | SRS 4.4.1, Row 8 | Hiển thị `Khachhang_CMND`. |
| **REQ-4.4.1-F05** | Số điện thoại | Label – string | 11 (inferred) | SRS 4.4.1, Row 9 | Hiển thị `KhachHang_SoDT`. |
| **REQ-4.4.1-F06** | Email | Label - string | 45 | SRS 4.4.1, Row 10 | Hiển thị `KhachHang_Email`. |
| **REQ-4.4.1-F07** | Giới tính | Label - string | N/A | SRS 4.4.1, Row 11 | Hiển thị `KhachHang_GioiTinh`. |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.4.1-A01** | Tìm kiếm | SRS 4.4.1, Row 26 | Dữ liệu thỏa điều kiện hiển thị trên danh sách | - Không có dữ liệu: `Không tìm thấy dữ liệu` (**MSG-4.4.1-M01**)<br>- Server: `Lỗi không kết nối được Server` (**MSG-4.4.1-M02**) |
| **ACT-4.4.1-A02** | Phân trang | SRS 4.4.1, Row 27 | Dữ liệu hiển thị đúng phân trang | Hiển thị trang đầu tiên |
| **ACT-4.4.1-A03** | Thao tác mở Popup | SRS 4.4.1, Rows 28-30 | Mở popup tương ứng (Thêm KH, Thông tin xe, Sửa) | `Lỗi kết nối` (**MSG-4.4.1-M03**) |

---

#### 4.4.2. Màn Hình Thông Tin Xe

- **Stable Citation**: SRS Section 4.4.2, Bảng `Màn hình thông tin xe`. Wireframe: `image9.png`.
- **Description**: Hiển thị danh sách các xe đã đăng ký vào bãi của khách hàng.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Trích Dẫn Ổn Định | Mô Tả |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-4.4.2-F01** | Thông tin KH | Labels | SRS 4.4.2, Rows 5-12 | Họ và tên, Ngày sinh, Mã khách hàng, Giới tính, Email, CMND, Số điện thoại, Địa chỉ. |
| **REQ-4.4.2-F02** | Mã Xe | Label – String | SRS 4.4.2, Row 14 | Hiển thị cột mã xe của KH đã đăng ký (`XeVe_maXe`). |
| **REQ-4.4.2-F03** | Loại xe | Label – String | SRS 4.4.2, Row 15 | Hiển thị loại xe (`XeVe_LoaiXe`). |
| **REQ-4.4.2-F04** | Tên xe | Label – String | SRS 4.4.2, Row 16 | Hiển thị tên xe (`XeVe_TenXe`). |
| **REQ-4.4.2-F05** | Loại vé | Label – String | SRS 4.4.2, Row 17 | Hiển thị loại vé (`XeVe_LoaiVe`). |
| **REQ-4.4.2-F06** | Biển số xe | Label | SRS 4.4.2, Row 18 | Hiển thị biển số xe (`XeVe_BienSoXe`). |
| **REQ-4.4.2-F07** | Ngày hết hạn vé | Label – String | SRS 4.4.2, Row 19 | Hiển thị ngày vé xe hết hạn (`XeVe_NgayHetHan`). |
| **ACT-4.4.2-A01** | Đóng | SRS 4.4.2, Row 23 | Quay lại danh sách Khách hàng | Thất bại: `Lỗi kết nối` (**MSG-4.4.2-M01**) |

---

#### 4.4.3. Thêm Mới Khách Hàng

- **Stable Citation**: SRS Section 4.4.3, Bảng `Giao diện` (dưới tiêu đề Thêm Khách hàng). Wireframe: `image10.png`.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Độ Dài | Bắt Buộc (inferred) | Trích Dẫn Ổn Định | Quy Tắc Nghiệp Vụ |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| **REQ-4.4.3-F01** | Họ tên | Text field - String | 45 | Có | SRS 4.4.3, Row 5 | Nhập họ tên khách hàng. Cập nhật `KHACH_HANG.HoTenKH`. |
| **REQ-4.4.3-F02** | Ngày sinh | Text field - Date | N/A | Có | SRS 4.4.3, Row 6 | Cập nhật `KHACH_HANG.NgaySinhKH`. |
| **REQ-4.4.3-F03** | Giới tính | Text field - String | 5 | Có | SRS 4.4.3, Row 7 | Chọn ở `KHACH_HANG.SexKH`. |
| **REQ-4.4.3-F04** | Địa chỉ | Text field - String | **45** | Có | SRS 4.4.3, Row 8 | **Độ dài tối đa 45 ký tự** (Lưu ý F6). Cập nhật `KHACH_HANG.DiaChiKH`. |
| **REQ-4.4.3-F05** | Email | Text field - String | 45 | Có | SRS 4.4.3, Row 9 | Cập nhật `KHACH_HANG.MailKH`. |
| **REQ-4.4.3-F06** | SĐT | Text field - Number | **11** | Có | SRS 4.4.3, Row 10 | **Độ dài số tối đa 11 chữ số** (Lưu ý F6). Cập nhật `KHACH_HANG.SDTKH`. |
| **REQ-4.4.3-F07** | CMND | Text - Number | N/A | Có | SRS 4.4.3, Row 11 | Nhập chứng minh thư `KhachHang_CMND`. |
| **REQ-4.4.3-F08** | Dòng thông tin xe | Form Table Rows | N/A | Không | SRS 4.4.3, Rows 13-17 | ID xe (5), Loại xe (String 20 / Textfield), Biển số xe, Loại vé (String 10 / Selectbox), Ngày hết hạn vé (DateTime). Kích hoạt vé tính từ ngày đăng ký vé. |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.4.3-A01** | Xóa xe | SRS 4.4.3, Row 23 | Dữ liệu được xóa từ CSDL | `Lỗi hệ thống` (**MSG-4.4.3-M01**) |
| **ACT-4.4.3-A02** | Lưu xe | SRS 4.4.3, Row 24 | Dữ liệu lưu vào CSDL, nút Lưu đổi thành nút Xóa (NO SRS MESSAGE - see OQ-14) | - Invalid: `Dữ liệu trên trường {item} không đúng định dạng …` (**MSG-4.4.3-M02**)<br>- Server: `Không kết nối được Server` (**MSG-4.4.3-M03**) |
| **ACT-4.4.3-A03** | Thêm xe | SRS 4.4.3, Row 25 | Dòng mới cho phép nhập dữ liệu | `Lỗi kết nối` (**MSG-4.4.3-M04**) |
| **ACT-4.4.3-A04** | Đóng | SRS 4.4.3, Row 26 | Đóng màn hình Thêm KH | `Lỗi kế nối` (**MSG-4.4.3-M05**) |

---

#### 4.4.4. Chỉnh Sửa Thông Tin Khách Hàng

- **Stable Citation**: SRS Section 4.4.4, Bảng `Màn hình chỉnh sửa thông tin Khách hàng`. Wireframe: `image11.png`.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Độ Dài | Quyền Sửa | Trích Dẫn Ổn Định |
| :--- | :--- | :--- | :---: | :---: | :--- |
| **REQ-4.4.4-F01** | Mã Khách hàng | Label | 5 | **KHÔNG** | SRS 4.4.4, Row 5 (Hiển thị Mã KH đã chọn, không cho sửa). |
| **REQ-4.4.4-F02** | Các trường thông tin cá nhân | Form fields | 45 / 11 | Có | SRS 4.4.4, Rows 6-12 (Họ tên 45, Ngày sinh, Giới tính 5, Địa chỉ 45, Email 45, SĐT 11, CMND). |
| **REQ-4.4.4-F03** | Cập nhật danh sách xe | Table rows | N/A | Có | SRS 4.4.4, Rows 14-19 (ID xe 5, Loại xe 20, Tên xe, Biển số xe, Loại vé 10, Ngày hết hạn). |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.4.4-A01** | Cập nhật | SRS 4.4.4, Row 27 | Dữ liệu cập nhật vào CSDL (NO SRS MESSAGE - see OQ-15) | - Invalid: `Dữ liệu trên trường {item} không đúng định dạng …` (**MSG-4.4.4-M01**)<br>- Server: `Không kết nối được Server` (**MSG-4.4.4-M02**) |
| **ACT-4.4.4-A02** | Xóa xe | SRS 4.4.4, Row 26 | Dữ liệu xe được xóa từ CSDL | `Lỗi hệ thống` (**MSG-4.4.4-M03**) |
| **ACT-4.4.4-A03** | Đóng | SRS 4.4.4, Row 29 | Đóng form quay lại danh sách | `Lỗi kế nối` (**MSG-4.4.4-M04**) |

---

#### 4.4.5. Xóa Thông Tin Khách Hàng

- **Stable Citation**: SRS Section 4.4.5, Bảng `Thông báo xóa khách hàng`. Wireframe: `image12.png`.

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công (Nguyên Văn) | Thất Bại & Concurrency (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.4.5-A01** | Xác nhận | SRS 4.4.5, Row 6 | `Xóa thành công` (**MSG-4.4.5-M01**) | - Concurrency: `Dữ liệu đang được xóa bởi người dùng khác` (**MSG-4.4.5-M02**)<br>- Server: `Lỗi server` (**MSG-4.4.5-M03**) |
| **ACT-4.4.5-A02** | Hủy | SRS 4.4.5, Row 7 | Tắt popup xác nhận xóa | N/A |

---

### 4.5. Quản Lý Xe Vào/Ra & Bản Đồ Bãi Đỗ Xe

#### 4.5.1. Quản Lý Xe Vào/ Ra

- **Stable Citation**: SRS Section 4.5.1, Bảng `Quản lý xe Vào/ Ra`. Wireframe: `image13.png`.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Trích Dẫn Ổn Định | Mô Tả & Quy Tắc Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-4.5.1-F01** | Xe vào | Label - Image | SRS 4.5.1, Row 5 | Camera chụp ảnh Biển số xe vào hiển thị và lưu vào CSDL. |
| **REQ-4.5.1-F02** | Xe ra | Label - Image | SRS 4.5.1, Row 6 | Camera chụp ảnh Biển số xe ra hiển thị để so khớp. |
| **REQ-4.5.1-F03** | Thời gian vào | Label - Date time | SRS 4.5.1, Row 7 | Hệ thống thời gian thực theo định dạng `hh:mm:ss dd/mm/yyyy`. |
| **REQ-4.5.1-F04** | Thời gian ra | Label - Date time | SRS 4.5.1, Row 8 | Hệ thống thời gian thực theo định dạng `hh:mm:ss dd/mm/yyyy`. |
| **REQ-4.5.1-F05** | Biển số xe | Label – string | SRS 4.5.1, Row 10 | Hiển thị biển số xe (`Xe_bienSoXe`). |
| **REQ-4.5.1-F06** | Tên Xe | Label – string | SRS 4.5.1, Row 11 | Hiển thị tên xe như cerato (`Xe_TenXe`). |
| **REQ-4.5.1-F07** | Hãng xe | Label – string | SRS 4.5.1, Row 12 | Hiển thị hãng xe như Kia (`Xe_hangXe`). |
| **REQ-4.5.1-F08** | Loại Xe | Label – string | SRS 4.5.1, Row 13 | Xe 4 chỗ / 7 chỗ hay 12 chỗ (`Xe_LoaiXe`). |
| **REQ-4.5.1-F09** | Họ tên Khách hàng | Label – string | SRS 4.5.1, Row 14 | Hiển thị tên khách hàng (`KhachHang_HoTen`). |
| **REQ-4.5.1-F10** | Số điện thoại | Label – string | SRS 4.5.1, Row 15 | Hiển thị số điện thoại KH (`KhachHang_SoDT`). |
| **REQ-4.5.1-F11** | Tầng | Label – string | SRS 4.5.1, Row 16 | Hiển thị Tầng đăng ký đậu xe (`DoXe_Tang`). |
| **REQ-4.5.1-F12** | Vị trí đỗ | Label – string | SRS 4.5.1, Row 17 | Hiển thị vị trí đậu xe (`DoXe_ViTri`). |
| **REQ-4.5.1-F13** | Thời gian vé hiệu lực từ ngày | Label - datetime | SRS 4.5.1, Row 18 | Thời gian vé bắt đầu có hiệu lực (`Ve_ThoiGianBD`). |
| **REQ-4.5.1-F14** | Thời gian vé hiệu lực đến ngày | Label - datetime | SRS 4.5.1, Row 19 | Thời gian vé kết thúc có hiệu lực (`Ve_ThoiGianKT`). |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.5.1-A01** | Tìm xe | SRS 4.5.1, Row 23 | Hiển thị thông tin trùng khớp với biển số xe từ camera | `Không tìm thấy dữ liệu trùng khớp` (**MSG-4.5.1-M01**) |
| **ACT-4.5.1-A02** | Lưu thông tin | SRS 4.5.1, Row 24 | Hệ thống lưu thông tin vào cơ sở dữ liệu | - Chưa tìm thấy thông tin mà bấm Lưu: `Lỗi dữ liệu không tìm thấy đê lưu` (**MSG-4.5.1-M02**)<br>- Lỗi server: `lỗi kết nối` (**MSG-4.5.1-M03**) |

---

#### 4.5.2. Bản Đồ Vị Trí Bãi Đỗ Xe

- **Stable Citation**: SRS Section 4.5.2, Bảng `Bãi đỗ xe ô tô`. Wireframe: `image14.png`.
- **Description**: Hiển thị bản đồ vị trí trống hoặc vị trí đã có xe trong bãi. Khi xe vào vị trí thì số thứ tự vị trí chuyển sang màu đỏ, nếu chưa có xe thì màu xanh. Wireframe thể hiện **10 tầng**, mỗi tầng **108 vị trí** (đánh số 1..108), Cửa vào / Cửa ra, Số chỗ trống.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Trích Dẫn Ổn Định | Mô Tả & Quy Tắc Nghiệp Vụ |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-4.5.2-F01** | Số chỗ trống | Label – Number (3) | SRS 4.5.2, Row 5 | Hiển thị tổng số chỗ trống còn lại trong bãi đỗ xe ở tầng hiện tại. |
| **REQ-4.5.2-F02** | Bản đồ tầng | Button – Number (2) | SRS 4.5.2, Row 6 | Khi click vào sẽ hiện ra bản đồ các tầng được lựa chọn. |
| **REQ-4.5.2-F03** | [Thông tin vị trí] | Label – String | SRS 4.5.2, Row 7 | Hiển thị Vị trí đỗ - Chiều dài/rộng/cao khi mouse over vị trí trên bản đồ. |
| **REQ-4.5.2-F04** | [Link vị trí] | Label - String | SRS 4.5.2, Row 8 | Click vào hiển thị menu: 1. Xem thông tin xe (quyền quản lý, nhân viên); 2. Đăng ký đỗ xe (quyền quản lý, nhân viên, khách hàng). |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.5.2-A01** | [Phân tầng] | SRS 4.5.2, Row 13 | Hiển thị các vị trí đỗ xe của tầng đó | `Lỗi kết nối` (**MSG-4.5.2-M01**) |
| **ACT-4.5.2-A02** | [Link vị trí] | SRS 4.5.2, Row 14 | Mở màn hình mua vé tương ứng với vị trí đã chọn | - Vị trí đã có xe: `Vị trí này đã có xe đk vé và đang sử dụng` (**MSG-4.5.2-M02**)<br>- Lỗi server: `lỗi kết nối` (**MSG-4.5.2-M03**) |

---

### 4.6. Quản Lý Vé

#### 4.6.1. Danh Sách Vé

- **Stable Citation**: SRS Section 4.6.1, Bảng `Danh sách vé`. Wireframe: `image15.png`.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Trích Dẫn Ổn Định | Mô Tả |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-4.6.1-F01** | Mã vé | Col – String | SRS 4.6.1, Row 5 | Hiển thị `Ve_MaVe`. |
| **REQ-4.6.1-F02** | Biển số Xe | Col - String | SRS 4.6.1, Row 6 | Hiển thị `Ve_BienSoXe`. |
| **REQ-4.6.1-F03** | Họ tên Khách hàng | Col - String | SRS 4.6.1, Row 7 | Hiển thị `Ve_TenKhachHang`. |
| **REQ-4.6.1-F04** | Mã Khách hàng | Col - String | SRS 4.6.1, Row 8 | Hiển thị `Ve_maKhachHang`. |
| **REQ-4.6.1-F05** | Số điện thoại | Col - String | SRS 4.6.1, Row 9 | Hiển thị `Ve_SoDT`. |
| **REQ-4.6.1-F06** | Thời gian bắt đầu hiệu lực | Col - datetime | SRS 4.6.1, Row 10 | Hiển thị `Ve_TGBD`. |
| **REQ-4.6.1-F07** | Thời gian kết thúc hiệu lực | Col - datetime | SRS 4.6.1, Row 11 | Hiển thị `Ve_TGkT`. |
| **REQ-4.6.1-F08** | Loại vé | Col - String | SRS 4.6.1, Row 12 | Hiển thị `Ve_LoaiVe`. |
| **REQ-4.6.1-F09** | Giá vé | Col - number | SRS 4.6.1, Row 13 | Hiển thị `Ve_GiaVe`. |
| **REQ-4.6.1-F10** | Vị trí & Tầng | Col – string | SRS 4.6.1, Rows 14-15 | Hiển thị `Ve_VịTri` và `Ve_Tang`. |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.6.1-A01** | Tìm kiếm vé | SRS 4.6.1, Row 27 | Dữ liệu hợp lệ hiển thị trên danh sách vé | - Không tìm thấy: `Không tìm thấy dữ liệu` (**MSG-4.6.1-M01**)<br>- Server: `Lỗi kết nối` (**MSG-4.6.1-M02**) |
| **ACT-4.6.1-A02** | Thao tác mở Form | SRS 4.6.1, Rows 28-30 | Mở màn hình Thêm vé, Sửa vé, Xác nhận xóa | `Lỗi kết nối` (**MSG-4.6.1-M03**) |

---

#### 4.6.2. Thêm Mới Vé (Mua Vé)

- **Stable Citation**: SRS Section 4.6.2, Bảng `Màn hình Thêm vé`. Wireframe: `image16.png`.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Bắt Buộc (inferred) | Trích Dẫn Ổn Định | Mô Tả & Quy Tắc Nghiệp Vụ |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **REQ-4.6.2-F01** | Mã vé | Input – text | Có | SRS 4.6.2, Row 5 | Cập nhật `Vé_Mave`. |
| **REQ-4.6.2-F02** | Biển số Xe | Input từ popup | Có | SRS 4.6.2, Row 6 | Cập nhật `Vé_bienSoXe`. Nhập xe từ màn hình thông tin xe của KH. |
| **REQ-4.6.2-F03** | Thông tin khách hàng | Input từ popup | Có | SRS 4.6.2, Row 7 | Chọn từ popup hiển thị Mã KH, Họ tên KH, SĐT. |
| **REQ-4.6.2-F04** | Thời gian vé hiệu lực bắt đầu | Input – datetimepicker | Có | SRS 4.6.2, Row 8 | Cập nhật `Ve_TGBD`. |
| **REQ-4.6.2-F05** | Thời gian vé kết thúc | Input – datetime picker | Có | SRS 4.6.2, Row 9 | Cập nhật `Ve_TGKT`. |
| **REQ-4.6.2-F06** | Tầng & Vị trí | Input – dropdownlist | Có | SRS 4.6.2, Rows 10-11 | Cập nhật `Ve_tang` và `Ve_Vịtri`. Chọn vị trí theo Tầng từ danh sách. |
| **REQ-4.6.2-F07** | Loại vé | Input – dropdownlist | Có | SRS 4.6.2, Row 12 | Cập nhật `Ve_Loai`. |
| **REQ-4.6.2-F08** | Giá | Input - number | Có | SRS 4.6.2, Row 13 | Cập nhật `Ve_gia`. |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.6.2-A01** | Lưu | SRS 4.6.2, Row 18 | Một vé đã được thêm mới vào database và quay lại danh sách (NO SRS MESSAGE - see OQ-16) | - Invalid: `Dữ liệu {item} không hợp lệ` (**MSG-4.6.2-M01**)<br>- Server: `Lỗi kết nối` (**MSG-4.6.2-M02**) |
| **ACT-4.6.2-A02** | Hủy | SRS 4.6.2, Row 19 | Quay lại màn hình danh sách | `Lỗi kết nối` (**MSG-4.6.2-M03**) |

---

#### 4.6.3. Chỉnh Sửa Vé (Gia Hạn Vé)

- **Stable Citation**: SRS Section 4.6.3, Bảng `Chỉnh sửa vé`. Wireframe: `image17.png`.
- **Description**: Cho phép gia hạn vé đối với những vé gần hết hạn.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Quyền Sửa | Trích Dẫn Ổn Định | Quy Tắc Nghiệp Vụ Cụ Thể |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **REQ-4.6.3-F01** | Mã vé | Label - string | **KHÔNG** | SRS 4.6.3, Row 5 | Hiển thị từ danh sách vé, không cho người dùng chỉnh sửa. |
| **REQ-4.6.3-F02** | Thông tin vé cũ | Labels | **KHÔNG** | SRS 4.6.3, Rows 6-10 | Biển số xe, Tên KH, SĐT, Ngày bắt đầu, Ngày kết thúc. |
| **REQ-4.6.3-F03** | Ngày Gia hạn | Input- datetime picker | **CÓ** | SRS 4.6.3, Row 11 | **Ngày Gia hạn phải lớn hơn ngày kết thúc vé** (Cập nhật `Ve_TGKT update`). |
| **REQ-4.6.3-F04** | Loại vé | Dropdownlist | CÓ | SRS 4.6.3, Row 12 | Cho chọn loại vé muốn cập nhật từ dropdownlist. |
| **REQ-4.6.3-F05** | Tầng & Vị trí | Dropdownlist | CÓ | SRS 4.6.3, Rows 13-14 | Cho chọn tầng và vị trí mới tương ứng. |
| **REQ-4.6.3-F06** | Giá | Input-text | CÓ | SRS 4.6.3, Row 15 | Cho người dùng nhập vào giá. |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.6.3-A01** | Gia Hạn vé | SRS 4.6.3, Row 19 | Dữ liệu cập nhật vào bảng Vé và quay lại danh sách (NO SRS MESSAGE - see OQ-17) | - Invalid: `Lỗi dữ liệu trên {item} không hợp lệ` (**MSG-4.6.3-M01**)<br>- Server: `Lỗi kết nối` (**MSG-4.6.3-M02**) |
| **ACT-4.6.3-A02** | Hủy | SRS 4.6.3, Row 20 | Hủy màn hình gia hạn vé và quay lại danh sách | `Lỗi kết nối` (**MSG-4.6.3-M03**) |

---

#### 4.6.4. Xóa Vé

- **Stable Citation**: SRS Section 4.6.4, Bảng `Xác nhận xóa vé`. Wireframe: `image18.png`.
- **Business Rule Description**: **"Xóa vé muốn xóa chỉ cho phép xóa những vé nào đã quá hạn và không gia hạn"**.

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công (Nguyên Văn) | Thất Bại & Concurrency (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.6.4-A01** | Yes (Xác nhận) | SRS 4.6.4, Row 6 | `Xóa thành công` (**MSG-4.6.4-M01**) | - TH1: `vé được xóa là vé chưa hết hạn thì không được xóa` (**CASE-4.6.4-TH1**; NO SRS MESSAGE - see OQ-18)<br>- TH2: `vé được xóa đang được xóa bởi 1 người dùng khác thì không được xóa` (**CASE-4.6.4-TH2**; NO SRS MESSAGE - see OQ-19)<br>- TH3: `Vé được xóa không kết nối được` (**CASE-4.6.4-TH3**; NO SRS MESSAGE - see OQ-20)<br>- Record không tồn tại / Đã bị xóa: (NO SRS MESSAGE - see OQ-21) |
| **ACT-4.6.4-A02** | No (Hủy) | SRS 4.6.4, Row 7 | Tắt popup xác nhận xóa vé | N/A |

---

### 4.7. Giao Diện Thống Kê

#### 4.7.1. Thống Kê Tổng Hợp (Doanh Thu)

- **Stable Citation**: SRS Section 4.7.1, Bảng `Thống kê tổng hợp`. Wireframe: `image19.png`.
- **Description**: Thống kê Doanh thu theo Tháng / Quý / Năm.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Trích Dẫn Ổn Định | Mô Tả |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-4.7.1-F01** | Tháng | Dropdownlist | SRS 4.7.1, Row 6 | Chọn từ 12 tháng trong năm. |
| **REQ-4.7.1-F02** | Quý | Dropdownlist | SRS 4.7.1, Row 7 | Chọn từ 4 quý trong năm. |
| **REQ-4.7.1-F03** | Năm | Datepicker | SRS 4.7.1, Row 8 | Chọn năm thống kê. |
| **REQ-4.7.1-F04** | [Chart] | Lược đồ | SRS 4.7.1, Row 10 | Có 3 tùy chọn: Cột / Tròn / Đường. |
| **REQ-4.7.1-F05** | Export file pdf | File | SRS 4.7.1, Row 12 | File export bao gồm các trường `[Tháng/ Quý/Năm]`, `Doanh thu` được sắp xếp giảm dần. |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.7.1-A01** | Thống kê / Chart | SRS 4.7.1, Rows 15-16 | Hiển thị doanh thu trên biểu đồ đã chọn | - Không có dữ liệu: `Dữ liệu không tìm thấy` (**MSG-4.7.1-M01**)<br>- Invalid: `Không thống kê được do lỗi dữ liệu chọn không hợp lệ` (**CASE-4.7.1-TH2**; NO SRS MESSAGE - see OQ-34)<br>- Server: `Không thống kê được do lỗi kết nối` (**CASE-4.7.1-TH3**; NO SRS MESSAGE - see OQ-35) |

---

#### 4.7.2. Giao Diện Thống Kê Theo Ngày/ Tháng/ Năm

- **Stable Citation**: SRS Section 4.7.2, Bảng `Thống kê theo điều kiện cụ thể`. Wireframe: `image20.png`.
- **Description**: Thống kê theo số lượng xe.

##### Trường Dữ Liệu & Biểu Đồ

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Trích Dẫn Ổn Định | Mô Tả |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-4.7.2-F01** | Từ ngày | Input – date picker | SRS 4.7.2, Row 5 | Nhập vào ngày bắt đầu. |
| **REQ-4.7.2-F02** | Đến ngày | Input – date picker | SRS 4.7.2, Row 6 | Nhập vào ngày kết thúc. |
| **REQ-4.7.2-F03** | Chart xe | Hình cột | SRS 4.7.2, Row 8 | Hiển thị Số lượng xe theo từng ngày. |
| **REQ-4.7.2-F04** | Chart Tầng | Hình cột | SRS 4.7.2, Row 9 | Hiển thị số lượng Xe theo từng Tầng. |
| **REQ-4.7.2-F05** | Chart Khách Hàng | Hình cột | SRS 4.7.2, Row 10 | Hiển thị số lượng xe được ĐK theo từng khách hàng. |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.7.2-A01** | Thống kê | SRS 4.7.2, Rows 13-14 | Hiển thị biểu đồ thống kê theo khoảng ngày | - Không có dữ liệu: `Không có dữ liệu để thống kê` (**CASE-4.7.2-TH1**; NO SRS MESSAGE - see OQ-36)<br>- Sai điều kiện: `Dữ liệu nhập từ điều kiện thống kê chưa đúng` (**CASE-4.7.2-TH2**; NO SRS MESSAGE - see OQ-37)<br>- Server: `Lỗi kết nối` (**CASE-4.7.2-TH3**; NO SRS MESSAGE - see OQ-38) |

---

### 4.8. Màn Hình Quản Lý Bãi

#### 4.8.1. Màn Hình Danh Sách Các Vị Trí Trong Bãi Xe

- **Stable Citation**: SRS Section 4.8.1, Bảng `Màn hình danh sách vị trí các xe đậu trong bãi`. Wireframe: `image21.png`.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Trích Dẫn Ổn Định | Mô Tả |
| :--- | :--- | :--- | :--- | :--- |
| **REQ-4.8.1-F01** | Số tầng | Dropdown | SRS 4.8.1, Row 5 | Hiển thị số tầng của bãi xe. |
| **REQ-4.8.1-F02** | Vị trí | Label - Text | SRS 4.8.1, Row 6 | Hiển thị vị trí đậu xe trong tầng đã chọn (Wireframe thể hiện dạng `A-1, A-2...`). |
| **REQ-4.8.1-F03** | Tầng | Label - Text | SRS 4.8.1, Row 7 | Hiển thị tầng đang chọn. |
| **ACT-4.8.1-A01** | Thao tác điều hướng | Links | SRS 4.8.1, Rows 8-11 | Sửa, Xoá, Chi tiết, Thêm vị trí đậu xe. |

---

#### 4.8.2. Màn Hình Thêm Mới Vị Trí Đỗ

- **Stable Citation**: SRS Section 4.8.2, Bảng `Màn hình thêm mới vị trí các xe đậu trong bãi`. Wireframe: `image22.png`.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Bắt Buộc (inferred) | Trích Dẫn Ổn Định | Mô Tả |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **REQ-4.8.2-F01** | Tầng | Text Field - Number | Có | SRS 4.8.2, Row 5 | Nhập số tầng của bãi xe. |
| **REQ-4.8.2-F02** | Số | Text Field - Number | Có | SRS 4.8.2, Row 6 | Nhập vị trí đậu xe trong tầng đã chọn. |
| **REQ-4.8.2-F03** | Chiều rộng | Text Field - Number | Có | SRS 4.8.2, Row 7 | Nhập chiều rộng cho vị trí đỗ. |
| **REQ-4.8.2-F04** | Chiều dài | Text Field - Number | Có | SRS 4.8.2, Row 8 | Nhập chiều dài cho vị trí đỗ. |
| **REQ-4.8.2-F05** | Loại xe cho phép | Check box - Text | Có | SRS 4.8.2, Row 9 | Chọn các loại xe có thể đỗ được ở vị trí này (Loại xe 4 chỗ / 7 chỗ / 12 chỗ …). |
| **REQ-4.8.2-F06** | Chiều cao | Text - Number | Có | SRS 4.8.2, Row 10 | Nhập chiều cao. |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.8.2-A01** | Thêm | SRS 4.8.2, Row 14 | Chuyển đến trang danh sách vị trí (NO SRS MESSAGE - see OQ-22) | - Invalid: `Dữ liệu thêm không hợp lệ` (**CASE-4.8.2-TH1**; NO SRS MESSAGE - see OQ-23)<br>- Trùng: `Đã tồn tại` (**CASE-4.8.2-TH2**; NO SRS MESSAGE - see OQ-24)<br>- Server: `Lỗi kết nối` (**CASE-4.8.2-TH3**; NO SRS MESSAGE - see OQ-25) |

---

#### 4.8.3. Màn Hình Sửa Thông Tin Vị Trí Đỗ

- **Stable Citation**: SRS Section 4.8.3, Bảng `Màn hình sửa vị trí các xe đậu trong bãi`. Wireframe: `image23.png`.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Kiểu Dữ Liệu | Quyền Sửa | Trích Dẫn Ổn Định | Mô Tả |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **REQ-4.8.3-F01** | Mã vị trí | Label – string | **KHÔNG** | SRS 4.8.3, Row 5 | Lấy từ bảng danh sách vị trí và không chỉnh sửa. |
| **REQ-4.8.3-F02** | Tầng, Số, Rộng, Dài, Cao, Loại xe | Form fields | CÓ | SRS 4.8.3, Rows 6-11 | Cập nhật thông số kích thước và loại xe cho phép của vị trí đỗ. |

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại & Concurrency (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.8.3-A01** | Lưu | SRS 4.8.3, Row 16 | Dữ liệu cập nhật vào hệ thống và quay lại danh sách (NO SRS MESSAGE - see OQ-26) | - Invalid: `Lỗi do dữ liệu update không hợp lệ` (**CASE-4.8.3-TH1**; NO SRS MESSAGE - see OQ-27)<br>- Concurrency: `Lỗi do dữ liệu đang được update bởi 1 user khác` (**CASE-4.8.3-TH2**; NO SRS MESSAGE - see OQ-28)<br>- Server: `Lỗi do kết nối` (**CASE-4.8.3-TH3**; NO SRS MESSAGE - see OQ-29) |
| **ACT-4.8.3-A02** | Hủy | SRS 4.8.3, Row 17 | Quay lại màn hình danh sách | N/A |

---

#### 4.8.4. Màn Hình Thông Tin Chi Tiết Vị Trí Đỗ

- **Stable Citation**: SRS Section 4.8.4, Bảng `Màn hình thông tin chi tiết vị trí trong bãi`. Wireframe: `image24.png`.

##### Trường Dữ Liệu

| Stable ID | Tên Trường | Trích Dẫn Ổn Định | Mô Tả Dữ Liệu Hiển Thị |
| :--- | :--- | :--- | :--- |
| **REQ-4.8.4-F01** | Thông tin vị trí & khách hàng | SRS 4.8.4, Rows 5-14 | Vị trí đỗ, Tầng, Họ và tên Khách hàng, Email, Số điện thoại, Ngày sinh, Loại xe, Hãng xe, Tên xe, Biển số xe. |
| **ACT-4.8.4-A01** | Quay lại | SRS 4.8.4, Row 17 | Chuyển đến trang danh sách vị trí. Thất bại: `Có vấn đề, Không thể quay lại trang danh sách vị trí` (**MSG-4.8.4-M01**). |

---

#### 4.8.5. Xóa Vị Trí Đỗ Xe

- **Stable Citation**: SRS Section 4.8.5, Bảng `Hiển thị màn hình xác nhận xóa vị trí đỗ`. Wireframe: `image25.png`.

##### Hành Động & Thông Báo

| Stable ID | Tên Hành Động | Trích Dẫn Ổn Định | Thành Công | Thất Bại & Ràng Buộc Nghiệp Vụ (Nguyên Văn) |
| :--- | :--- | :--- | :--- | :--- |
| **ACT-4.8.5-A01** | Xóa | SRS 4.8.5, Row 9 | Vị trí đỗ được xóa và quay lại màn hình danh sách (NO SRS MESSAGE - see OQ-30) | - Ràng buộc vé active: `TH: Xóa vị trí đang được xe đk vé đỗ` (**CASE-4.8.5-TH1**; NO SRS MESSAGE - see OQ-31)<br>- Concurrency: `TH: Xoa vị trí đang được xóa bởi người khác` (**CASE-4.8.5-TH2**; NO SRS MESSAGE - see OQ-32)<br>- Server: `TH: xóa nhưng không kết nối được` (**CASE-4.8.5-TH3**; NO SRS MESSAGE - see OQ-33) |
| **ACT-4.8.5-A02** | Hủy | SRS 4.8.5, Row 10 | Quay lại màn hình danh sách | `Lỗi kết nối` (**MSG-4.8.5-M04**) |
