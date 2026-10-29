# Phân Tích Đối Chiếu Màn Hình UI/UX và API Backend

> Ghi chú của Team Lead: tài liệu này phản ánh backend tại thời điểm tác giả viết. Từ đó các API vehicles, customers, employees và administrative units đã được triển khai; nguồn hiện hành là `docs/api-endpoints.md` và OpenAPI schema.

Dưới đây là bảng đối chiếu và phân tích chi tiết giữa **danh sách API hiện có trong mã nguồn backend** ([`docs/hd_lay_api.md`](file:///E:/parking_management_backend/docs/hd_lay_api.md)) và **các file ảnh thiết kế UI/UX trong thư mục** [`Parking Project/`](<file:///E:/parking_management_backend/Parking%20Project/>).

Thư mục [`Parking Project/`](<file:///E:/parking_management_backend/Parking%20Project/>) chứa tổng cộng **9 màn hình giao diện chính** và **2 file icon đồ họa**.

---

## 1. Bảng ma trận đối chiếu Màn hình UI/UX và API Backend

| STT | File ảnh UI/UX (`Parking Project/`)                                                                                                                                                              | Chức năng / Nghiệp vụ trên UI                                                                                                                                         | API hiện có trong `hd_lay_api.md`                                                                                                                                                                                                                      |                     Mức độ đáp ứng                     |
| :-: | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------------------: |
|  1  | [`login-container.png`](<file:///E:/parking_management_backend/Parking%20Project/login-container.png>)                                                                                             | **Đăng nhập & Xác thực**: Nhập Email/SĐT, Mật khẩu, Ghi nhớ đăng nhập (`Remember Me`), Đăng ký                                                     | • `GET /api/v1/auth/csrf/`• `POST /api/v1/auth/login/`• `POST /api/v1/auth/logout/`• `GET /api/v1/auth/me/`                                                                                                                                    |                🟢 **100% (Đầy đủ)**                |
|  2  | [`Main Page.png`](<file:///E:/parking_management_backend/Parking%20Project/Main%20Page.png>)                                                                                                       | **Trang điều hành tại Cổng Barrier**: Nhận diện biển số OCR camera, thông tin xe, check-in, check-out, tính phí, mở cổng, tìm xe                      | • `POST /api/v1/parking/plate-scans/`• `GET /api/v1/parking/vehicle-lookup/`• `GET /api/v1/parking/vehicle-search/`• `POST /api/v1/parking/sessions/check-in/`• `POST /api/v1/parking/sessions/check-out/`• `GET /api/v1/parking/gates/` |                🟢 **100% (Đầy đủ)**                |
|  3  | [`Lịch sử ra\vào — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Lịch%20sử%20ra/vào%20—%20Smart%20Mobility.png>)                                           | **Lịch sử phiên đỗ xe**: Bảng danh sách phiên, mã phiên `#PK-...`, biển số, giờ vào/ra, tổng thời gian đỗ, cước phí, ảnh đối soát         | • `GET /api/v1/parking/sessions/`• `GET /api/v1/parking/sessions/<id>/`                                                                                                                                                                              |                🟢 **100% (Đầy đủ)**                |
|  4  | [`Quản lý xe — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Quản%20lý%20xe%20—%20Smart%20Mobility.png>)                                                     | **Quản lý phương tiện**: Danh sách xe, phân loại (Ô tô, Xe điện), trạng thái (Đang đỗ, Đang hoạt động, Đã rời bãi), Thêm/Sửa/Xóa xe      | • `GET /api/v1/parking/vehicle-search/` *(Mới có API tìm kiếm)*                                                                                                                                                                                   | 🟡 **Một phần (~20%)***(Thiếu toàn bộ CRUD xe)* |
|  5  | [`Trang chủ — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Trang%20chủ%20—%20Smart%20Mobility.png>)                                                           | **Dashboard / Thống kê**: KPI số chỗ trống (342/550), lượt xe trong ngày (52 in), doanh thu hôm nay (150k), tỷ lệ AI (98.4%), biểu đồ giờ             | • `GET /api/health/` *(Chỉ kiểm tra DB/OCR)*                                                                                                                                                                                                        |               🔴 **0% (Chưa có API)**               |
|  6  | [`Khách hàng — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Khách%20hàng%20—%20Smart%20Mobility.png>)                                                       | **Quản lý khách hàng**: KPI tổng KH (1,420), thuê bao active, sắp hết hạn, blacklist; bảng thông tin KH và phương tiện sở hữu                       | *Chưa có endpoint nào*                                                                                                                                                                                                                                |               🔴 **0% (Chưa có API)**               |
|  7  | [`Sơ đồ bãi đậu xe — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Sơ%20đồ%20bãi%20đậu%20xe%20—%20Smart%20Mobility.png>)                             | **Sơ đồ bãi đỗ xe**: Cấu trúc Tầng (B1/B2/F1) - Khu (A/B/C) - Ô đỗ (A-01..A-08); trạng thái ô (Trống, Có xe, Đặt trước, Sạc điện, Bảo trì) | *Chưa có endpoint nào*                                                                                                                                                                                                                                |               🔴 **0% (Chưa có API)**               |
|  8  | [`Quản lý vé — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Quản%20lý%20vé%20—%20Smart%20Mobility.png>)                                                   | **Quản lý vé**: Danh sách vé thuê bao, ngày hết hạn, vị trí ô đỗ cố định, phát hành vé mới, gia hạn vé, trạng thái hiệu lực               | *Chưa có endpoint nào*                                                                                                                                                                                                                                |               🔴 **0% (Chưa có API)**               |
|  9  | [`Quản lý nhân viên - Smart mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Quản%20lý%20nhân%20viên%20-%20Smart%20mobility.png>)                                   | **Quản lý nhân sự**: Danh sách nhân viên (Mã NV001, Họ tên, Email, Chức vụ: Quản lý/Kỹ thuật/Bảo vệ/Thu ngân), Phân quyền                       | *Chưa có endpoint nào*                                                                                                                                                                                                                                |               🔴 **0% (Chưa có API)**               |
| 10 | [`Vector.png`](<file:///E:/parking_management_backend/Parking%20Project/Vector.png>) & [`clarity_edit-line.png`](<file:///E:/parking_management_backend/Parking%20Project/clarity_edit-line.png>) | **Icon đồ họa UI**: Icon Thùng rác (Xóa) và Cây bút (Chỉnh sửa)                                                                                           | *N/A (Tài nguyên tĩnh phía Frontend)*                                                                                                                                                                                                                |                ⚪ *Không cần API (TL-16)*                |

---

## 2. Phân tích chi tiết mức độ đáp ứng

### 🟢 Nhóm 1: Các màn hình ĐÃ CÓ API hoàn thiện 100%

Đây là nhóm chức năng vận hành trực tiếp tại trạm kiểm soát bãi đỗ xe (Barrier & Gate):

1. **Màn hình Đăng nhập ([`login-container.png`](<file:///E:/parking_management_backend/Parking%20Project/login-container.png>))**:
   - `GET /api/v1/auth/csrf/`: Cấp token bảo vệ form đăng nhập.
   - `POST /api/v1/auth/login/`: Hỗ trợ đăng nhập linh hoạt bằng cả `Email` hoặc `Số điện thoại` kèm checkbox `Remember Me` (đúng như giao diện thiết kế).
   - `GET /api/v1/auth/me/`: Tự động phục hồi trạng thái người dùng khi mở lại web.
2. **Màn hình Điều hành Cổng ([`Main Page.png`](<file:///E:/parking_management_backend/Parking%20Project/Main%20Page.png>))**:
   - `POST /api/v1/parking/plate-scans/`: Nhận ảnh từ camera và quét OCR biển số tự động.
   - `GET /api/v1/parking/vehicle-lookup/`: Hiển thị tức thì thông tin xe, chủ xe, vé hiện tại.
   - `POST /api/v1/parking/sessions/check-in/` & `check-out/`: Nút bấm xác nhận vào bãi (sinh mã phiên `#PK-...`) và tính cước ra bãi.
   - `GET /api/v1/parking/gates/`: Nạp danh sách các làn/cổng vào-ra barrier.
   - `GET /api/v1/parking/vehicle-search/`: Hỗ trợ modal tìm kiếm xe bằng tay khi biển số bị mờ/hỏng.
3. **Màn hình Lịch sử phiên ([`Lịch sử ra\vào — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Lịch%20sử%20ra/vào%20—%20Smart%20Mobility.png>))**:
   - `GET /api/v1/parking/sessions/`: Cung cấp danh sách lịch sử phân trang kèm bộ lọc thời gian, biển số.
   - `GET /api/v1/parking/sessions/<id>/`: Xem chi tiết ảnh chụp đối soát và thời gian đỗ.

---

### 🟡 Nhóm 2: Màn hình mới đáp ứng MỘT PHẦN

- **Màn hình Quản lý xe ([`Quản lý xe — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Quản%20lý%20xe%20—%20Smart%20Mobility.png>))**:
  - Backend mới chỉ có API tra cứu/tìm kiếm phương tiện (`/api/v1/parking/vehicle-search/`).
  - **Còn thiếu**: Toàn bộ nghiệp vụ CRUD xe của màn hình này (`GET` danh sách xe, `POST` thêm xe mới, `PATCH` sửa thông tin xe, `DELETE` xóa xe).

---

### 🔴 Nhóm 3: Các màn hình HOÀN TOÀN THIẾU API trong `hd_lay_api.md`

Các màn hình này hiện tại Backend chưa mở route (`apps/*/urls.py` đang trống) và Frontend đang phải chạy bằng mock data:

1. **[`Trang chủ — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Trang%20chủ%20—%20Smart%20Mobility.png>)**: Thiếu API tổng hợp số liệu Dashboard (chỗ trống theo tầng, doanh thu hôm nay theo phương thức Tiền mặt/VietQR, tỷ lệ chính xác của AI).
2. **[`Khách hàng — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Khách%20hàng%20—%20Smart%20Mobility.png>)**: Thiếu API danh sách khách hàng, thống kê số lượng thuê bao kích hoạt, khách sắp hết hạn vé và quản lý blacklist nợ phí.
3. **[`Sơ đồ bãi đậu xe — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Sơ%20đồ%20bãi%20đậu%20xe%20—%20Smart%20Mobility.png>)**: Thiếu API sơ đồ cấu trúc Tầng/Khu/Ô đỗ, trạng thái ô đỗ (Trống/Có xe/Bảo trì/EV) và hành động đặt trước ô đỗ (`slot_reservation`).
4. **[`Quản lý vé — Smart Mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Quản%20lý%20vé%20—%20Smart%20Mobility.png>)**: Thiếu API quản lý các gói vé tháng/ngày, phát hành vé và quy trình gia hạn vé.
5. **[`Quản lý nhân viên - Smart mobility.png`](<file:///E:/parking_management_backend/Parking%20Project/Quản%20lý%20nhân%20viên%20-%20Smart%20mobility.png>)**: Thiếu API quản lý danh sách nhân sự và phân 4 vị trí công việc (Quản lý, Kỹ thuật, Bảo vệ, Thu ngân).

---

## 3. Kết luận

- **Tiến độ Backend hiện tại**: Đã tập trung hoàn thiện và kiểm thử kỹ lưỡng **2 màn hình cốt lõi nhất** của hệ thống là **Xác thực (`login-container.png`)** và **Vận hành trạm kiểm soát xe ra/vào trực tiếp (`Main Page.png`, `Lịch sử ra/vào`)**.
- **Công việc tiếp theo**: Cần bổ sung các API quản trị cho 5 màn hình còn lại (Xe -> Khách hàng -> Vé -> Sơ đồ bãi -> Nhân viên -> Dashboard) để hoàn tất 100% khớp nối với bản vẽ UI/UX.
