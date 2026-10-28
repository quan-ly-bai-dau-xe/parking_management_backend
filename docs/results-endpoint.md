
Ran search for comparison files
Checked task Search for comparison files
Analyzed hd_lay_api.md:L1-187
Analyzed fe_enpoints.md:L1-78

Dưới đây là phân tích và đối chiếu chi tiết giữa hai tài liệu:

- [`docs/hd_lay_api.md`](file:///E:/parking_management_backend/docs/hd_lay_api.md): **Góc nhìn Backend thực tế** (các API đã được code và kích hoạt route trong Django backend).
- [`docs/fe_enpoints.md`](file:///E:/parking_management_backend/docs/fe_enpoints.md): **Góc nhìn Frontend** (các API mà mã nguồn frontend đang gọi hoặc kỳ vọng kết nối).

---

### 1. Bảng đối chiếu tổng hợp giữa hai tài liệu

| Nhóm chức năng        | Endpoint                                     | Có ở Backend (`hd_lay_api.md`) | Có ở Frontend (`fe_enpoints.md`) | Tình trạng thực tế                                       |
| :----------------------- | :------------------------------------------- | :--------------------------------: | :----------------------------------: | :----------------------------------------------------------- |
| **Health Check**   | `GET /api/health/`                         |                Có                |              ❌ Thiếu              | BE có sẵn kiểm tra DB & OCR, FE chưa dùng               |
|                          | `GET /api/v1/health/`                      |                Có                |              ❌ Thiếu              | BE có sẵn cho FE ping kết nối, FE chưa dùng            |
| **Authentication** | `GET /api/v1/auth/csrf/`                   |                Có                |                 Có                 | Khớp hoàn toàn (FE lấy token trước khi POST)           |
|                          | `POST /api/v1/auth/login/`                 |                Có                |                 Có                 | Khớp hoàn toàn                                            |
|                          | `POST /api/v1/auth/logout/`                |                Có                |              ❌ Thiếu              | BE đã có thu hồi session/cookie, FE chưa khai báo API  |
|                          | `GET /api/v1/auth/me/`                     |                Có                |              ❌ Thiếu              | BE đã có trả profile & phục hồi phiên, FE chưa nối  |
| **Parking & OCR**  | `POST /api/v1/parking/plate-scans/`        |                Có                |                 Có                 | Khớp hoàn toàn (OCR quét biển số)                      |
|                          | `GET /api/v1/parking/vehicle-lookup/`      |                Có                |                 Có                 | Khớp hoàn toàn (Tra cứu xe theo biển số)               |
|                          | `GET /api/v1/parking/vehicle-search/`      |                Có                |                 Có                 | Khớp hoàn toàn (Tìm kiếm đa tiêu chí)                |
|                          | `GET /api/v1/parking/sessions/`            |                Có                |                 Có                 | Khớp hoàn toàn (Lịch sử phiên ra/vào)                 |
|                          | `GET /api/v1/parking/sessions/{id}/`       |                Có                |                 Có                 | Khớp hoàn toàn (Chi tiết phiên đỗ xe)                 |
|                          | `POST /api/v1/parking/sessions/check-in/`  |                Có                |              ❌ Thiếu              | BE đã xong nghiệp vụ check-in, FE chưa liệt kê gọi   |
|                          | `POST /api/v1/parking/sessions/check-out/` |                Có                |              ❌ Thiếu              | BE đã xong tính phí & check-out, FE chưa liệt kê gọi |
|                          | `GET /api/v1/parking/gates/`               |                Có                |              ❌ Thiếu              | BE có API lấy cổng barrier, FE chưa liệt kê gọi       |
| **Vehicle CRUD**   | `GET /api/v1/vehicles/`                    |       ❌ **Chưa có**       |         **Đã gọi**         | **Lệch pha (FE gọi sẽ bị 404)**                    |
|                          | `GET /api/v1/vehicles/summary/`            |       ❌ **Chưa có**       |         **Đã gọi**         | **Lệch pha (FE gọi sẽ bị 404)**                    |
|                          | `GET /api/v1/vehicles/{id}/`               |       ❌ **Chưa có**       |         **Đã gọi**         | **Lệch pha (FE gọi sẽ bị 404)**                    |
|                          | `POST /api/v1/vehicles/`                   |       ❌ **Chưa có**       |         **Đã gọi**         | **Lệch pha (FE gọi sẽ bị 404)**                    |
|                          | `PATCH /api/v1/vehicles/{id}/`             |       ❌ **Chưa có**       |         **Đã gọi**         | **Lệch pha (FE gọi sẽ bị 404)**                    |
|                          | `DELETE /api/v1/vehicles/{id}/`            |       ❌ **Chưa có**       |         **Đã gọi**         | **Lệch pha (FE gọi sẽ bị 404)**                    |

---

### 2. Những điểm khác biệt và thiếu sót chính

#### A. Backend đã có nhưng Frontend (`fe_enpoints.md`) đang thiếu / chưa nối:

1. **API Auth**:
   - `POST /api/v1/auth/logout/`: Đăng xuất và xóa session/cookie. Hiện FE có thể chỉ đang clear state/token ở client mà chưa gọi API thu hồi phiên ở BE.
   - `GET /api/v1/auth/me/`: Lấy thông tin user hiện tại (rất quan trọng khi F5 trang để khôi phục phiên qua Remember-me cookie).
2. **Nghiệp vụ Ra/Vào bãi đỗ cốt lõi (Check-in / Check-out)**:
   - `POST /api/v1/parking/sessions/check-in/`: Check-in xe vào bãi, sinh mã phiên, kiểm tra blacklist.
   - `POST /api/v1/parking/sessions/check-out/`: Check-out xe và tính phí đỗ.
   - `GET /api/v1/parking/gates/`: Lấy danh sách cổng barrier để chọn làn vào/ra.
     *(Ở FE hiện mới chỉ có OCR ảnh và tra cứu lịch sử phiên, chưa thấy đưa 3 API check-in/out/gates này vào bảng tài liệu)*.
3. **Health Check**:
   - `GET /api/health/` và `GET /api/v1/health/`: Chưa được tích hợp vào frontend để kiểm tra kết nối hệ thống trước khi thực hiện tác vụ nặng.

#### B. Frontend đã code gọi nhưng Backend (`hd_lay_api.md`) CHƯA CÓ (Nguy cơ lỗi 404):

> [!WARNING]
> **Toàn bộ nhóm Quản lý Phương tiện (`/api/v1/vehicles/*`)**:
> Trong `fe_enpoints.md`, file `src/features/vehicleService.js` đã viết sẵn code gọi các API:
>
> - Danh sách xe: `GET /api/v1/vehicles/?{params}`
> - Thống kê xe: `GET /api/v1/vehicles/summary/`
> - Chi tiết xe: `GET /api/v1/vehicles/{id}/`
> - Thêm/Sửa/Xóa xe: `POST`, `PATCH`, `DELETE` trên `/api/v1/vehicles/`
>
> Tuy nhiên, ở Backend ([`apps/vehicles/urls.py`](file:///E:/parking_management_backend/apps/vehicles/urls.py)), các endpoint này **chưa được cài đặt** (file `urls.py` vẫn đang để trống). Khi Frontend kích hoạt các chức năng này sẽ bị lỗi `404 Not Found`.

#### C. Các Module cả hai bên đều chưa nối (Đang chạy Mock Data ở Frontend):

Cả hai tài liệu đều xác nhận các module sau đây chưa có API thực tế và Frontend đang phải dùng mock:

- **Khách hàng** (`CustomerManagement`): Frontend dùng `customerData.js`, Backend `apps/customers/urls.py` chưa triển khai.
- **Quản lý Vé** (`TicketManagement`): Frontend dùng `ticketsData.js`, Backend `apps/tickets/urls.py` chưa triển khai.
- **Sơ đồ bãi xe / Slots** (`ParkingLotManagement`): Frontend dùng `parkingLotData.js`, Backend chưa có API sơ đồ vị trí.
- **Quản lý Nhân viên** (`EmployeeManagement`): Frontend dùng mock nội bộ, Backend `apps/employees/urls.py` chưa triển khai.
- **Thống kê Dashboard / Báo cáo**: Frontend dùng `dashboardService.js` mock, Backend `apps/reports/urls.py` chưa triển khai.

---

### 3. Đề xuất hành động tiếp theo

1. **Phía Backend**: Cần ưu tiên triển khai module `apps/vehicles/` (Viết Serializer, Service, Selector và ViewSet theo chuẩn 3-tier) để khớp ngay với `vehicleService.js` mà Frontend đã dựng sẵn.
2. **Phía Frontend**:
   - Đấu nối 2 API nghiệp vụ quan trọng đã có sẵn ở backend: `check-in` và `check-out` vào giao diện vận hành bãi xe.
   - Bổ sung gọi `logout` và `me` vào `authService.js`.
