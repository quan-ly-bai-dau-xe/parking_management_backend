# Tài liệu Tích hợp API: Khách hàng, Nhân sự & Modal Phương tiện

Tài liệu này chuẩn hóa giao thức API phục vụ tính năng `feature/feat/Qminh-003-customer-staff-modal-car`:
- **CRUD Khách hàng (Customer Management)**
- **CRUD Nhân viên (Staff / Employee Management)**
- **Xem thông tin chi tiết xe & Modal Thêm thông tin xe mới (Vehicle Management)**

---

## 1. Nhóm API Khách hàng (Customer API)

### 1.1. Danh sách khách hàng
- **Method & URL:** `GET /api/v1/customers/`
- **Quyền hạn:** `[IsAuthenticated, IsEmployeeOrManager]`
- **Query Params:**
  - `q`: Tìm kiếm theo Tên, SĐT, CCCD, Mã KH
  - `status`: `ACTIVE` / `INACTIVE`
  - `page`, `page_size`: Phân trang kết quả
- **Response:**
  ```json
  {
    "count": 12,
    "total_pages": 1,
    "current_page": 1,
    "results": [
      {
        "id": 1,
        "code": "KH0001",
        "full_name": "Nguyễn Văn A",
        "phone": "0901234567",
        "email": "vana@gmail.com",
        "identity_card_number": "048099001234",
        "gender": "Nam",
        "status": "ACTIVE",
        "status_display": "Đang hoạt động",
        "vehicles_count": 2,
        "row_version": 1
      }
    ]
  }
  ```

### 1.2. Thêm mới khách hàng
- **Method & URL:** `POST /api/v1/customers/`
- **Payload:**
  ```json
  {
    "full_name": "Trần Thị B",
    "phone": "0912345678",
    "email": "tranb@gmail.com",
    "identity_card_number": "048099005678",
    "gender": "Nữ",
    "date_of_birth": "1998-10-20"
  }
  ```

---

## 2. Nhóm API Phương tiện & Modal Thêm / Xem xe (Vehicle API)

### 2.1. Danh mục Loại xe (Vehicle Types)
- **Method & URL:** `GET /api/v1/vehicle-types/`
- **Response:**
  ```json
  [
    { "id": 1, "code": "CAR", "name": "Ô tô" },
    { "id": 2, "code": "EV", "name": "Xe điện" }
  ]
  ```

### 2.2. Đăng ký xe mới (Modal Thêm thông tin xe mới)
- **Method & URL:** `POST /api/v1/vehicles/`
- **Payload:**
  ```json
  {
    "license_plate": "51K-992.14",
    "model_name": "VF8 Plus",
    "brand": "VinFast",
    "color": "Trắng",
    "vehicle_type_id": 2,
    "customer_id": 1,
    "notes": "Xe điện cá nhân sạc qua đêm"
  }
  ```

### 2.3. Xem thông tin chi tiết xe (Modal Xem thông tin xe)
- **Method & URL:** `GET /api/v1/vehicles/{id}/`
- **Response:**
  - `id`, `code`, `license_plate`
  - `model_name`, `brand`, `color`
  - `vehicle_type`: `{ "id": 2, "code": "EV", "name": "Xe điện" }`
  - `customer`: `{ "id": 1, "code": "KH0001", "full_name": "...", "phone": "..." }`
  - `ticket`: Trạng thái vé tháng hoặc vé lượt, ngày hết hạn, số ngày còn lại
  - `current_slot`: Ô đỗ đang sử dụng (nếu đang đỗ trong bãi)

---

## 3. Nhóm API Nhân sự (Employee / Staff API)

### 3.1. Danh mục chức vụ
- **Method & URL:** `GET /api/v1/positions/`
- **Quyền hạn:** `[IsAuthenticated, IsManager]`

### 3.2. Thêm mới nhân viên
- **Method & URL:** `POST /api/v1/employees/`
- **Payload:**
  ```json
  {
    "full_name": "Lê Văn C",
    "email": "levanc@smartpark.vn",
    "phone": "0935111222",
    "position_id": 2,
    "password": "SmartPark@2026",
    "address": "Hải Châu, Đà Nẵng",
    "status": "ACTIVE"
  }
  ```

### 3.3. Cập nhật nhân viên & Chống xung đột OCC
- **Method & URL:** `PATCH /api/v1/employees/{id}/`
- **Bắt buộc:** `row_version` để đảm bảo kiểm soát tương tranh lạc quan.

### 3.4. Rào chắn xóa mềm an toàn (DEL-01)
- **Method & URL:** `DELETE /api/v1/employees/{id}/`
- Hệ thống tự động chặn đứng nếu Quản lý cố gắng xóa tài khoản của chính mình (Trả về lỗi `409 Conflict`).
