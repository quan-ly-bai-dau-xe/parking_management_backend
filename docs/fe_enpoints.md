
Ran list src subdirectories
Ran list src services
Ran list config and features
Ran list mocks and root files in src
Ran list docs directory
Analyzed apiClient.js:L1-86
Analyzed authService.js:L1-87
Analyzed dashboardService.js:L1-100
Analyzed dashboardService.js:L101-193
Analyzed plateScanService.js:L1-100
Analyzed plateScanService.js:L101-274
Analyzed vehicleService.js:L1-100
Ran search API usages across src · Exited with code 1
Ran search API usages across src
Analyzed vite.config.js:L1-28
Ran search API endpoints in docs
Ran search architecture docs
Ran list src pages
Ran check data source imports in pages

Hiện tại trong dự án frontend, các API kết nối đến Django backend (qua proxy Vite tại cổng `8000`) được tổ chức tập trung tại [`apiClient.js`](file:///e:/parking_management_frontend/src/services/apiClient.js) và các service trong thư mục `src/features/`.

Dưới đây là danh sách chi tiết các API đang có trong dự án:

---

### 1. Nhóm Xác thực & CSRF (Auth)

*Được triển khai trong [`src/services/apiClient.js`](file:///e:/parking_management_frontend/src/services/apiClient.js) và [`src/features/authService.js`](file:///e:/parking_management_frontend/src/features/authService.js)*

| Phương thức | Endpoint                | Mô tả                                                                 | Hàm gọi                                                                                         |
| :------------- | :---------------------- | :---------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------ |
| `GET`        | `/api/v1/auth/csrf/`  | Khởi tạo cookie `csrftoken` từ Django backend                      | [`fetchCsrfToken`](file:///e:/parking_management_frontend/src/services/apiClient.js#L23-L34)     |
| `POST`       | `/api/v1/auth/login/` | Đăng nhập tài khoản (Body: `{ identifier, password, remember }`) | [`authService.login`](file:///e:/parking_management_frontend/src/features/authService.js#L4-L22) |

*(Lưu ý: Các luồng Forgot password, Verify OTP, Reset password trong [`authService.js`](file:///e:/parking_management_frontend/src/features/authService.js#L49-L76) hiện vẫn đang xử lý giả lập Promise nội bộ).*

---

### 2. Nhóm Quét biển số & Phiên đỗ xe (Parking & OCR)

*Được triển khai trong [`src/features/plateScanService.js`](file:///e:/parking_management_frontend/src/features/plateScanService.js)*

| Phương thức | Endpoint                                                  | Mô tả                                                                                                                      | Hàm gọi                                                                                                     |
| :------------- | :-------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------ |
| `POST`       | `/api/v1/parking/plate-scans/`                          | Gửi ảnh chụp (`multipart/form-data`) lên server để OCR nhận diện biển số và kiểm tra xe/vé                    | [`scanPlateImage`](file:///e:/parking_management_frontend/src/features/plateScanService.js#L17-L44)          |
| `GET`        | `/api/v1/parking/vehicle-lookup/?license_plate={plate}` | Tra cứu xe theo biển số (thông tin chủ xe, vé đang dùng, vị trí đỗ, blacklist)                                   | [`lookupVehicleByPlate`](file:///e:/parking_management_frontend/src/features/plateScanService.js#L51-L54)    |
| `GET`        | `/api/v1/parking/sessions/?{filters}`                   | Lấy danh sách lịch sử phiên xe ra/vào (lọc theo biển số, mã phiên, ngày giờ vào/ra, trạng thái, phân trang) | [`getParkingSessions`](file:///e:/parking_management_frontend/src/features/plateScanService.js#L73-L83)      |
| `GET`        | `/api/v1/parking/sessions/{id}/`                        | Lấy thông tin chi tiết một phiên đỗ xe theo ID                                                                        | [`getParkingSessionDetail`](file:///e:/parking_management_frontend/src/features/plateScanService.js#L90-L92) |

---

### 3. Nhóm Quản lý phương tiện (Vehicles)

*Được triển khai trong [`src/features/vehicleService.js`](file:///e:/parking_management_frontend/src/features/vehicleService.js)*

| Phương thức | Endpoint                                      | Mô tả                                                                                       | Hàm gọi                                                                                                 |
| :------------- | :-------------------------------------------- | :-------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------- |
| `GET`        | `/api/v1/parking/vehicle-search/?q={query}` | Tìm kiếm nhanh phương tiện theo từ khóa                                                | [`searchVehicles`](file:///e:/parking_management_frontend/src/features/vehicleService.js#L3-L10)         |
| `GET`        | `/api/v1/vehicles/?{params}`                | Lấy danh sách phương tiện (lọc theo loại xe, loại vé, trạng thái vé, phân trang) | [`fetchVehicles`](file:///e:/parking_management_frontend/src/features/vehicleService.js#L12-L23)         |
| `GET`        | `/api/v1/vehicles/summary/`                 | Lấy các chỉ số thống kê tổng hợp về xe (tổng số xe, tỷ lệ, số xe đang đỗ...) | [`fetchVehicleSummary`](file:///e:/parking_management_frontend/src/features/vehicleService.js#L25-L27)   |
| `GET`        | `/api/v1/vehicles/{id}/`                    | Lấy thông tin chi tiết một phương tiện                                                 | [`fetchVehicleDetail`](file:///e:/parking_management_frontend/src/features/vehicleService.js#L29-L31)    |
| `POST`       | `/api/v1/vehicles/`                         | Thêm mới phương tiện vào hệ thống                                                     | [`vehicleService.create`](file:///e:/parking_management_frontend/src/features/vehicleService.js#L42-L45) |
| `PATCH`      | `/api/v1/vehicles/{id}/`                    | Cập nhật thông tin phương tiện                                                          | [`vehicleService.update`](file:///e:/parking_management_frontend/src/features/vehicleService.js#L46-L49) |
| `DELETE`     | `/api/v1/vehicles/{id}/`                    | Xóa phương tiện khỏi hệ thống                                                          | [`vehicleService.remove`](file:///e:/parking_management_frontend/src/features/vehicleService.js#L50-L52) |

---

### 4. Các module hiện đang dùng Mock Data (chưa nối API backend thực tế)

Hiện một số trang chức năng vẫn đang sử dụng mock data tĩnh trong thư mục `src/mocks/`:

- **Dashboard / Thống kê trang chủ** ([`dashboardService.js`](file:///e:/parking_management_frontend/src/features/dashboardService.js)): Đang dùng mock cho sơ đồ tầng, cảnh báo bất thường và số liệu thống kê.
- **Quản lý khách hàng** ([`CustomerManagement.jsx`](file:///e:/parking_management_frontend/src/pages/CustomerManagement.jsx)): Đang dùng [`customerData.js`](file:///e:/parking_management_frontend/src/mocks/customerData.js).
- **Quản lý vé** ([`TicketManagement.jsx`](file:///e:/parking_management_frontend/src/pages/TicketManagement.jsx)): Đang dùng [`ticketsData.js`](file:///e:/parking_management_frontend/src/mocks/ticketsData.js).
- **Sơ đồ bãi xe** ([`ParkingLotManagement.jsx`](file:///e:/parking_management_frontend/src/pages/ParkingLotManagement.jsx)): Đang dùng [`parkingLotData.js`](file:///e:/parking_management_frontend/src/mocks/parkingLotData.js).
- **Quản lý nhân viên** ([`EmployeeManagement.jsx`](file:///e:/parking_management_frontend/src/pages/EmployeeManagement.jsx)): Dữ liệu nội bộ component.
