# Danh Mục Tiêu Chí DoD (Definition of Done) Và Quality Check

Tài liệu này đặc tả chính xác nguyên văn (copy-exact) các tiêu chí nghiệm thu hoàn thành (Definition of Done - DoD) và tiêu chí kiểm soát chất lượng (Check_Quality) từ các tài liệu gốc của dự án, đồng thời ánh xạ trực tiếp các tiêu chí này sang các yêu cầu kỹ thuật và hành vi API của Backend (Python / Django REST Framework / PostgreSQL).

---

## 1. Danh Mục 10 Tiêu Chí Definition of Done (DoD)

### 1.1. Bảng Trích Dẫn Nguyên Văn (Copy-Exact)

- **Nguồn tài liệu gốc**: `01-Reference/05. [BM] DoD Template.docx` (và được dẫn chiếu trong `01-Reference/04. [BM] Team Charter.docx`).
- **Phần trích xuất**: Đoạn văn bản (Paragraphs) 4 đến 13 dưới tiêu đề `ĐỊNH NGHĨA HOÀN THÀNH CỦA NHÓM`.

| STT | Nguyên Văn Tiêu Chí (Source Text) | Vị Trí Trích Dẫn Ổn Định | Phạm Vi Áp Dụng Cho Backend Repo | Ghi Chú & Ánh Xạ Kỹ Thuật |
| :---: | :--- | :--- | :---: | :--- |
| 1 | Code đã đuợc Review chéo | `01-Reference/05. [BM] DoD Template.docx`, Paragraph 4 | BẮT BUỘC (APPLICABLE) | Mọi Pull Request vào nhánh `dev` phải được ít nhất 01 thành viên trong nhóm review và phê duyệt (Approved) trước khi merge. |
| 2 | Chức năng đã đưọc test chéo | `01-Reference/05. [BM] DoD Template.docx`, Paragraph 5 | BẮT BUỘC (APPLICABLE) | API endpoint và use case phải được kiểm thử chéo bởi thành viên khác trong nhóm hoặc QA thông qua test suite / API client. |
| 3 | Test trên nhiều trình duyệt (IE, Chrome , Firefox) | `01-Reference/05. [BM] DoD Template.docx`, Paragraph 6 | **N/A for the backend repo (frontend owner)** | Tiêu chí thuộc phạm vi Frontend UI. Backend cung cấp REST API chuẩn HTTP/JSON độc lập trình duyệt. |
| 4 | Phải validate dữ liệu | `01-Reference/05. [BM] DoD Template.docx`, Paragraph 7 | BẮT BUỘC (APPLICABLE) | Toàn bộ dữ liệu đầu vào (request body, query params, path variables) phải được validate nghiêm ngặt qua DRF Serializers và Django Model validators trước khi xử lý nghiệp vụ. |
| 5 | Đã hỗ trợ I18n | `01-Reference/05. [BM] DoD Template.docx`, Paragraph 8 | BẮT BUỘC (APPLICABLE) | Thông báo trả về từ API phải chuẩn hóa, hỗ trợ mã lỗi i18n và thông điệp tiếng Việt nguyên văn theo đặc tả SRS v4.1. |
| 6 | Dữ liệu phải đẹp | `01-Reference/05. [BM] DoD Template.docx`, Paragraph 9 | BẮT BUỘC (APPLICABLE) | Dữ liệu trả về (JSON response) phải được chuẩn hóa schema, định dạng ngày giờ chuẩn ISO 8601 (UTC/Asia/Ho_Chi_Minh), số thực/tiền tệ định dạng chuẩn, không chứa trường thừa hoặc giá trị null vô nghĩa. Dữ liệu seed/fixture phải thực tế và hợp lệ. |
| 7 | Đã refactor ít nhất 1 lần | `01-Reference/05. [BM] DoD Template.docx`, Paragraph 10 | BẮT BUỘC (APPLICABLE) | Mã nguồn phải qua bước refactor: loại bỏ code lặp lại (DRY), tách biệt rõ ràng giữa View - Service - Model, tối ưu hóa truy vấn CSDL (`select_related`, `prefetch_related` tránh lỗi N+1). |
| 8 | Đã merge vào nhánh dev | `01-Reference/05. [BM] DoD Template.docx`, Paragraph 11 | BẮT BUỘC (APPLICABLE) | Mã nguồn sau khi vượt qua review chéo và CI pipeline phải được merge vào nhánh tích hợp `dev` bằng lệnh merge có commit `--no-ff`. |
| 9 | Sử dụng màu mặc định của Bootstrap | `01-Reference/05. [BM] DoD Template.docx`, Paragraph 12 | **N/A for the backend repo (frontend owner)** | Tiêu chí giao diện người dùng HTML/CSS thuộc phạm vi Frontend. |
| 10 | Giao diện đúng với thiết kế | `01-Reference/05. [BM] DoD Template.docx`, Paragraph 13 | **N/A for the backend repo (frontend owner)** | Tiêu chí giao diện người dùng thuộc phạm vi Frontend. Đối với Backend, tiêu chuẩn tương đương là "Contract API khớp 100% với đặc tả OpenAPI / Swagger". |

---

### 1.2. Các Cổng Kỹ Thuật Bổ Sung Cho Backend (TEAM LEAD DECISION)

Để đảm bảo chất lượng kỹ thuật cao cấp (enterprise-grade) cho dự án Backend công khai (`parking_management_backend`), Team Lead quy định các cổng kiểm soát kỹ thuật bắt buộc sau đây (áp dụng cho mọi Pull Request):

1. **[TL-GATE-01] Kiểm thử tự động (Automated Test Suite)**:
   - 100% test cases trong bộ kiểm thử (pytest-django) phải pass.
   - Test coverage tối thiểu đạt **>= 80%** trên toàn bộ các tầng nghiệp vụ (models, serializers, services/selectors).
2. **[TL-GATE-02] Linting & Format chuẩn hóa**:
   - Sử dụng `ruff` (linter và formatter) với cấu hình nghiêm ngặt; **0 lỗi, 0 cảnh báo**.
3. **[TL-GATE-03] Kiểm tra kiểu tĩnh (Static Type Checking)**:
   - Kiểm tra kiểu dữ liệu với `mypy` (django-stubs); **0 lỗi kiểu**.
4. **[TL-GATE-04] Tính toàn vẹn của Migration CSDL**:
   - Chạy lệnh `python manage.py makemigrations --check --dry-run` trong CI để đảm bảo không có thay đổi model nào chưa được tạo migration.
   - Tuyệt đối không sửa đổi các file migration đã áp dụng.
5. **[TL-GATE-05] OpenAPI Contract Validation**:
   - `drf-spectacular` sinh tài liệu OpenAPI 3.0 không phát sinh lỗi hoặc cảnh báo schema rỗng.
6. **[TL-GATE-06] An toàn bảo mật & Vệ sinh Repository công khai**:
   - Chạy `python manage.py check --deploy` không vi phạm các cảnh báo an ninh P0/P1.
   - Quét phụ thuộc bằng `pip-audit` / `bandit`; không có lỗ hổng bảo mật mức High/Critical.
   - Quét rò rỉ mã bí mật (Secret Scan): Tuyệt đối không lưu token, mật khẩu, credential vào git repository.
7. **[TL-GATE-07] Tuân thủ chính sách xóa an toàn (Safe Delete Policy)**:
   - Mọi thao tác xóa dữ liệu nghiệp vụ phải tuân thủ chính sách Soft Delete và ràng buộc bảo vệ (`PROTECT`) theo tài liệu `docs/requirements/03-delete-rules-catalog.md`.

---

## 2. Danh Mục 20 Tiêu Chí Check_Quality (Copy-Exact & Ánh Xạ Backend)

### 2.1. Nguồn Dữ Liệu Gốc

- **File**: `00-Product/10-Check_Quality/Sprint_2/[CGDN]_Check_Quality.xlsx`
- **Sheet**: `Account`
- **Dòng**: `Row 5 (A5:E5)` đến `Row 24 (A24:E24)`.
- **Tiêu đề bảng (Row 4)**: `No` (Cột A) | `Content` (Cột B) | `Description` (Cột C) | `Status (Yes, No, N/A)` (Cột D) | `Note` (Cột E).

### 2.2. Bảng 20 Tiêu Chí Nguyên Văn Và Ánh Xạ Hành Vi API Backend

| No. (Row) | Nội Dung Nguyên Văn (Content) | Mô Tả Nguyên Văn (Description) | Mức Độ Liên Quan Backend | Ánh Xạ Hành Vi Kỹ Thuật API Backend (Python/Django) |
| :---: | :--- | :--- | :---: | :--- |
| **1** (A5) | Layout đã giống với design chưa? | Vị trí các item trên chương trình phải mapping với design, các lỗi chính tả tên item (thiếu s…). Item bắt buộc phải có dấu * đỏ. | **Có** (Data Contract) | - Tên các trường trong JSON Request/Response phải mapping chính xác 100% với đặc tả SRS (snake_case chuẩn REST hoặc camelCase đồng bộ).<br>- Các trường bắt buộc (`required=True` trong Serializer) phải từ chối khi client không truyền dữ liệu và trả về lỗi rõ ràng. |
| **2** (A6) | Giá trị khởi tạo cho các item trên màn hình đã đúng chưa? | Chú ý set data default khi vừa open màn hình, việc khởi tạo cho các combobox, radio button… | **Có** (Default Values) | - Khởi tạo giá trị mặc định cho Model / Serializer đúng theo SRS (ví dụ: status mặc định, role, timestamp khởi tạo).<br>- Cung cấp các API metadata/options để frontend lấy danh sách lựa chọn khởi tạo (ví dụ: danh sách tầng 1..10, loại xe, loại vé). |
| **3** (A7) | Check thứ tự TAB đã đúng chưa? | Thứ tự TAB theo nguyên tắc từ trên xuống dưới, từ TRÁI sang PHẢI. | **Không** (Frontend UI) | Hành vi điều hướng phím Tab trên trình duyệt; thuộc sở hữu của Frontend. |
| **4** (A8) | Thuộc tính canh phải, canh trái đúng? | Thường item kiểu text thì canh trái, số canh phải. | **Không** (Frontend UI) | Định dạng canh lề CSS hiển thị UI; thuộc sở hữu của Frontend. |
| **5** (A9) | Lỗi đã focus vào item bị lỗi chưa? | Phải focus vào item lỗi đầu tiên. Ví dụ 4 item bắt buộc, input cho 3 item đầu, nhấn Save thì phải focus vào item 4 | **Có** (Error Payload) | Khi có nhiều trường lỗi, API phải trả về đối tượng lỗi có cấu trúc (structured error object) chứa tên trường cụ thể và thứ tự rõ ràng để Frontend định vị và focus vào trường lỗi đầu tiên. |
| **6** (A10) | Tất cả các nội dung message xuất hiện đã đúng chưa? | Các item cần check thì message phải hiện thị đúng vị trí và nội dung. Message phải có chấm câu. Chú ý tên item phải hiển thị trong nội dung message. | **BẮT BUỘC** (Message Text) | - Thông báo lỗi và thành công trả về từ API phải **nguyên văn từng câu chữ** theo đặc tả SRS v4.1.<br>- Phải kết thúc bằng dấu chấm câu theo đúng quy định.<br>- Chứa tên item cụ thể trong nội dung (ví dụ: `Dữ liệu {item} không hợp lệ, xin mời nhập lại dữ liệu`). |
| **7** (A11) | Đã check validate cho format item chưa? | Cần chú ý check validate cho các item có format riêng: item email, Ngày tháng… | **BẮT BUỘC** (Format Validation) | - Email: Regex/EmailValidator chuẩn RFC.<br>- Phone: đúng độ dài số (Nhân viên: tối đa 15 chữ số; Khách hàng: tối đa 11 chữ số).<br>- Date/Datetime: format chuẩn ISO 8601 YYYY-MM-DD hoặc HH:MM:SS DD/MM/YYYY.<br>- Mật khẩu: Chứa ký tự số, đặc biệt, chữ hoa, chữ thường theo SRS 4.3.3. |
| **8** (A12) | Các message check validate có xuất hiện cùng lúc chưa? | Khi vừa open màn hình Add/update, ko input data và nhấn button Save thì message check bắt buộc phải xuất hiện đồng thời. Or tất cả các item có check validate input data invalid và nhấn button save thì message check validate phải xuất hiện đồng thời. | **BẮT BUỘC** (Full Validation) | DRF Serializer phải thực hiện validate toàn diện toàn bộ các trường trong payload và gom toàn bộ lỗi vào một response (HTTP 400 Bad Request) thay vì dừng lại ở lỗi đầu tiên (fail-fast), cho phép hiển thị đồng thời mọi lỗi nhập liệu. |
| **9** (A13) | Data load ở combobox, list box, spread đã hiển thị đúng nội dung chưa? | Nếu fix cứng trong code thì phải hiển thị đúng nội dung | **Có** (Dropdown Enums) | Các trường enum (Loại xe, Loại vé, Chức vụ, Giới tính) phải được định nghĩa chuẩn xác trong backend và trả về đúng nội dung yêu cầu qua các endpoint danh mục hoặc schema options. |
| **10** (A14) | Xử lí enable/disable cho các item đã đúng theo spec chưa? | Nếu tài liệu có mô tả check thì cần cover hết các trường hợp | **Có** (Read-Only Fields) | Các trường không được phép sửa (ví dụ: ID nhân viên ở màn hình Sửa 4.3.3, Mã khách hàng ở 4.4.4, Mã vé ở 4.6.3, Mã vị trí ở 4.8.3) phải được thiết lập `read_only=True` ở Serializer; backend từ chối hoặc bỏ qua việc ghi đè lên các trường này. |
| **11** (A15) | Đã thực hiện Trim character khi input space chưa? | Input space thì cần trim space tại item input (cắt space và focus về đầu) | **BẮT BUỘC** (String Sanitization) | Toàn bộ chuỗi văn bản (tên, địa chỉ, biển số, username...) gửi lên API phải được tự động `strip()` loại bỏ khoảng trắng đầu/cuối trước khi thực hiện validate và lưu vào CSDL. |
| **12** (A16) | Tất cả các item load data hiển thị trên màn hình đã test trường hợp data max length chưa? | Đảm bảo ko bị che khuất data. Check cho cả  các khu vực input data và khu vực hiển thị data | **BẮT BUỘC** (Max Length Constraint) | Backend phải giới hạn chặt chẽ `max_length` ở cả tầng Serializer và Model/DB column (ví dụ: Họ tên 45, Địa chỉ 45, ID 5, Phone 15/11) để ngăn chặn tràn dữ liệu và tấn công DoS. |
| **13** (A17) | Nhấn enter có focus vào button Save/Search chưa? | *(Trống)* | **Không** (Frontend UI) | Xử lý phím Enter trên form người dùng thuộc phạm vi Frontend. |
| **14** (A18) | Data insert vào DB đã confirm hết các field chưa? | *(Trống)* | **BẮT BUỘC** (Complete DB Persistence) | Mọi trường dữ liệu người dùng nhập theo đặc tả SRS phải được lưu đầy đủ vào bảng CSDL tương ứng (không bỏ sót bất kỳ trường nào như Ngày sinh, Giới tính, CMND, Chức vụ, Email...). |
| **15** (A19) | Click vào các button đã di chuyển sang màn hình tương ứng chưa? | Nếu chức năng ko yêu cầu làm màn hình đó thì phải giả lập màn hình tương ứng và di chuyển đến. | **Không** (Frontend Routing) | Quản lý router và chuyển trang của ứng dụng Single Page App (SPA). |
| **16** (A20) | Delete đã có message confirm chưa? | *(Trống)* | **Có** (Delete Semantics) | API cung cấp endpoint `DELETE /api/v1/.../{id}/`. Dù frontend hiển thị modal xác nhận, API backend phải xử lý an toàn: kiểm tra quyền, kiểm tra ràng buộc nghiệp vụ (chặn xóa nếu có dữ liệu liên quan), và trả mã HTTP 200/204 kèm message SRS thích hợp. |
| **17** (A21) | các item khác trên màn hình đã thực hiện đúng, ex button cancel, reset, download… | *(Trống)* | **Có** (Cancel/Reset/Export) | Cung cấp endpoint xuất báo cáo PDF (cho 4.7.1) và đảm bảo các API thao tác dữ liệu có tính lũy kế (idempotent), hỗ trợ hủy bỏ hoặc rollback giao dịch khi cần. |
| **18** (A22) | Pager hiển thị đúng số record/page? Thực hiện đúng cho các button Next, previous, last, first? | *(Trống)* | **BẮT BUỘC** (Pagination API) | Endpoint danh sách (Employee, Customer, Ticket, Slot) phải hỗ trợ phân trang chuẩn: trả về `count`, `next`, `previous`, `results`, `page_size`, và hỗ trợ tham số `page` và `page_size`. |
| **19** (A23) | Chức năng search đã thực hiện đúng? | search cho all item, ko input item nào… | **BẮT BUỘC** (Search / Filtering) | Endpoint tìm kiếm phải hỗ trợ tìm kiếm kết hợp nhiều điều kiện (Họ tên, Mã, Ngày sinh từ-đến, Địa chỉ...) và xử lý chính xác trường hợp không truyền tham số nào (trả về danh sách mặc định có phân trang) cũng như trường hợp không có kết quả trùng khớp (trả về danh sách rỗng kèm HTTP 200). |
| **20** (A24) | Business đã thực hiện đúng? | chạy random 1 số mô tả business ở SRS or design xem OK chưa | **BẮT BUỘC** (Business Logic) | Toàn bộ quy tắc nghiệp vụ trong SRS (vé quá hạn mới được xóa, không được xóa slot đang có xe giữ vé, kiểm tra trùng lặp biển số, khóa dòng khi cập nhật đồng thời) phải được cài đặt chính xác trong tầng Service của Backend. |

---

## 3. Danh Mục 12 Tiêu Chí Check_Quality Sprint 1 (Copy-Exact)

### 3.1. Nguồn Dữ Liệu Gốc

- **File**: `00-Product/10-Check_Quality/Sprint_1/[CGDN]_Check_Quality.xlsx`
- **Sheet**: `Account`
- **Dòng**: `Row 4 (A4:F4)` đến `Row 15 (A15:F15)`.
- **Tiêu đề bảng (Row 3)**: `No` (Cột A) | `Classification` (Cột B) | `Content` (Cột C) | `Description` (Cột D) | `Grade (/10)` (Cột E) | `Note` (Cột F).

### 3.2. Bảng 12 Tiêu Chí Nguyên Văn Sprint 1

| No. (Row) | Phân Loại (Classification) | Nội Dung Nguyên Văn (Content) | Mô Tả Nguyên Văn (Description) | Ánh Xạ Trọng Tâm Kỹ Thuật Backend |
| :---: | :--- | :--- | :--- | :--- |
| **1** (A4) | Layout | Vị trí sắp xếp các item trên màn hình đã hợp lý hay chưa? | N/A | Cấu trúc payload JSON nhất quán và logic giữa các API. |
| **2** (A5) | *(Trống)* | Giá trị khởi tạo cho các item trên màn hình đã đúng chưa? | Chú ý các giá trị mặc định của các combobox (dropdown list), radio button, checkbox… khi vừa load màn hình lên. | Thiết lập giá trị mặc định chuẩn xác trong Django Model fields (`default=...`). |
| **3** (A6) | *(Trống)* | Tất cả các item load data hiển thị trên màn hình có bị che khuất dữ liệu hay không? | Đảm bảo ko bị che khuất dữ liệu. Check cho cả các khu vực input data và khu vực hiển thị data. | Không cắt ngắn (truncate) dữ liệu trả về một cách bất thường; giữ nguyên độ chính xác. |
| **4** (A7) | *(Trống)* | Layout đã thống nhất với các màn hình khác trong toàn bộ hệ thống hay chưa? | Như là vị trí các item, vị trí các message… đã đồng bộ với nhau cả chưa? | Cấu trúc Envelope của API Response đồng bộ trên toàn hệ thống (`{success, data, message, error_code}`). |
| **5** (A8) | *(Trống)* | Tất cả các nội dung message xuất hiện đã đúng chưa? | Cần đảm bảo message thành công hay lỗi thì phải truyền tải đầy đủ đến với người dùng. | Trả về thông điệp chính xác theo catalog thông báo của SRS v4.1. |
| **6** (A9) | Business | Nghiệp vụ đã thực hiện đúng với thực tế hay chưa? | N/A | Toàn bộ luồng nghiệp vụ trong SRS được mô hình hóa chính xác trong Django services. |
| **7** (A10) | *(Trống)* | Delete đã có modal/dialog/popup để confirm hay chưa? | N/A | Endpoint xóa dữ liệu an toàn, kiểm tra ràng buộc trước khi thực hiện. |
| **8** (A11) | *(Trống)* | Đã check validate cho format item chưa? | Cần chú ý check validate cho các item có format riêng: item email, Ngày tháng… | Validate định dạng chặt chẽ bằng Serializers. |
| **9** (A12) | *(Trống)* | Click vào các button đã di chuyển sang màn hình tương ứng chưa? | *(Trống)* | N/A for backend (frontend routing). |
| **10** (A13) | *(Trống)* | Đã xử lý cho việc search không có kết quả? | Đối với các màn hình có chức năng search, nếu trường hợp search không có kết quả thì đã xử lý hay chưa? | Khi không có kết quả tìm kiếm, API trả về mảng rỗng `[]` kèm HTTP 200 OK (không bắn lỗi 500 hoặc 404). |
| **11** (A14) | *(Trống)* | Flow giữa các màn hình đã liên thông với nhau chưa? | Với hệ thống hiện tại, thì flow chính đã bảo xuyên suốt hay chưa? | Luồng dữ liệu nghiệp vụ API liên thông hoàn chỉnh (Tạo khách hàng -> Đăng ký xe -> Cấp vé đỗ xe -> Quản lý vào/ra). |
| **12** (A15) | Khác | Bạn có ý tưởng nào hay để cải thiện chất lượng sản phẩm hay không? | N/A | Đề xuất tối ưu hóa truy vấn CSDL, caching, bảo mật API và soft-delete policy. |
