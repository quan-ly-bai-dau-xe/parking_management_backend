# Scope Additions From Project Plan

This document synthesizes all work items, functional additions, and technical scope notes introduced in the project plan (`[CGDN]_Project_Plan.xlsx`, Sheet `Tasks_Sprint_1`) that extend or augment the original software specification (`Quan ly bai dau xe oto_SRS_v4.1.docx`). It explicitly delineates engineering responsibilities between Backend (Python / Django REST Framework) and Frontend.

---

## 1. Stable Source Citations
- **Source File**: `[CGDN]_Project_Plan.xlsx`
- **Sheet**: `Tasks_Sprint_1`
- **Cited Rows**: Row 3 (A3:F3), Row 4 (A4:F4), Row 9 (A9:F9), Row 10 (A10:F10), Row 11 (A11:F11), Row 12 (A12:F12), Row 14 (A14:F14), Row 19 (A19:F19).

---

## 2. Inventory of Scope Additions Beyond SRS v4.1

| Item ID | Scope Item / Screen | Citation in `Tasks_Sprint_1` | Verbatim Content From Plan / Scope Notes | Responsibility Assignment (Backend vs Frontend) | Detailed Backend Technical Specification |
| :---: | :--- | :--- | :--- | :---: | :--- |
| **SCO-01** | **License Plate OCR Scan** (Vehicle In/Out OCR Scan) | Row 10 (A10:F10), Task 8 (Screen 4.5.1 Vehicle In/Out) | `Lưu ý: - Tích hợp chức năng scan biển số xe từ hình ảnh. Nếu thông tin xe đã tồn tại trong hệ thống, thì sẽ tự động hiển thị trên màn hình: Tên xe, Hãng xe, Tên khách hàng, Số điện thoại, Vị trí đỗ. - Phần Tìm xe (không cần làm, đã có thành viên khác đảm nhiệm)` | **BACKEND PRIMARY RESPONSIBILITY (Core API)** | - Build endpoint `POST /api/v1/vehicle-records/scan-plate/` accepting image file uploads (or base64 payloads).<br>- Integrate OCR module for license plate recognition (utilizing computer vision / OCR libraries such as OpenCV, EasyOCR, Tesseract, or a configurable mock engine for CI).<br>- Auto-lookup in database: If the plate number exists in `Vehicle`, return full details: Vehicle Name, Brand, Customer Name, Phone, Current Slot.<br>- Enforce secure upload validation (max file size, PNG/JPEG MIME types, malicious payload scanning). |
| **SCO-02** | **Multi-Criteria Vehicle Search Modal** (Vehicle Search Modal) | Row 11 (A11:F11), Task 9 (`Other. Modal tìm xe.`) | `Lưu ý: Tìm thông tin xe qua tên khách hàng, Số điện thoại hoặc Biển số xe.` | **BACKEND PROVIDES SEARCH API** (Frontend renders Modal) | - Build quick lookup endpoint: `GET /api/v1/vehicles/search/?q=...` or filtered query: `GET /api/v1/vehicles/?customer_name=...&phone=...&plate_number=...`.<br>- Support unaccented and case-insensitive matching (`icontains`).<br>- Optimize queries with indexes on `bien_so_xe`, `sdt`, `ho_ten_kh`.<br>- Return structured results: License Plate, Vehicle Name, Brand, Owner, Phone, Parking Slot, Ticket Status. |
| **SCO-03** | **News Management** (News Management: List, Add, Edit) | Row 4 (A4:F4), Task 2 (`Other. Danh sách tin tức bãi đỗ xe.`) & Row 19 (A19:F19), Task 17 (`Other. Thêm tin tức`, `Other. Sửa tin tức`) | `Lưu ý: Các thông tin cho mỗi tin tức, thì tham khảo trang bên dưới. https://hethongdoxe.com/tin-tuc-ve-bai-do-xe-tu-dong-nc57636.html. Sau đó cần QA với PO để confirm, xem đã đầy đủ item hay chưa.` | **BACKEND PROVIDES CRUD NEWS API** (Frontend renders UI) | - Design database model `News` referencing the external reference site:<br>  + `id`: Primary key.<br>  + `title`: Headline string (max 255, required).<br>  + `summary`: Short summary text (optional).<br>  + `content`: Detailed rich text / markdown content.<br>  + `thumbnail_url`: Image URL string.<br>  + `published_at`: Publication timestamp.<br>  + `is_published`: Visibility flag (Boolean).<br>  + `author`: Foreign key referencing `Employee`.<br>- Provide RESTful endpoints:<br>  + `GET /api/v1/news/`: Public article listing for Home Screen 4.2.<br>  + `GET /api/v1/news/{id}/`: Article detail.<br>  + `POST /api/v1/news/`: Create article (Manager/Employee only).<br>  + `PUT /api/v1/news/{id}/`: Update article (Manager/Employee only).<br>  + `DELETE /api/v1/news/{id}/`: Soft-delete article. |
| **SCO-04** | **Parking Map Context Menu Permissions** (Slot Context Menu Permissions) | Row 12 (A12:F12), Task 10 (Screen 4.5.2 Parking Lot Map) | `Lưu ý: Khi click vào vị trí thì sẽ hiển thị menu: 1. Xem thông tin xe (quyền quản lý, nhân viên). 2. Đăng ký đỗ xe (quyền quản lý, nhân viên, khách hàng).` | **BACKEND ENFORCES AUTHORIZATION (RBAC)** | - Comparison with SRS 4.5.2 (which only allowed Manager to view vehicle; Manager and Customer to register): Plan expands permission to allow **Employee** to also: View vehicle information and Register parking slot.<br>- Backend permission classes:<br>  + Endpoint viewing vehicle info at slot: Permits `MANAGER` and `EMPLOYEE`.<br>  + Endpoint registering parking slot / reservation: Permits `MANAGER`, `EMPLOYEE`, and `CUSTOMER`. |
| **SCO-05** | **Password Recovery Flow** (Password Recovery Flow) | Row 3 (A3:F3), Task 1 (`Other. Quên mật khẩu`) | `Other. Quên mật khẩu` (Linked to SRS 4.1 item: "Khi quên mật khẩu, click vào để lấy lại mật khẩu thông qua email đã đăng ký") | **BACKEND TOKEN HANDLING & EMAIL DELIVERY** | - Build secure endpoints:<br>  + `POST /api/v1/auth/forgot-password/`: Accepts email, generates single-use reset token (15-minute expiration), sends email with reset link.<br>  + `POST /api/v1/auth/reset-password/`: Accepts token and new password, verifies token validity, validates password policy, and updates hashed credentials. |
| **SCO-06** | **Standalone Add Vehicle Modal** (Standalone Add Vehicle Modal) | Row 9 (A9:F9), Task 7 (`Other. Modal thêm mới xe`) | `Other. Modal thêm mới xe` (Extends Customer Form 4.4.4) | **BACKEND VEHICLE MANAGEMENT API** | - Provide endpoint: `POST /api/v1/customers/{customer_id}/vehicles/` allowing adding vehicles directly to a customer without full customer profile updates. |
| **SCO-07** | **Admin Header, Footer, and Sidebar** | Row 4 (`Other. Header/Footer`), Row 14 (`Other. Sidebar cho các chức năng quản lý`) | `Other. Header/Footer`, `Other. Sidebar cho các chức năng quản lý` | **FRONTEND UI RESPONSIBILITY** (Backend provides RBAC menu endpoint) | - Backend provides `GET /api/v1/auth/me/` returning current user profile with permissions and active role, enabling dynamic menu rendering on the frontend. |

---

## 3. Technical Specifications for Core Backend Features

### 3.1. License Plate OCR Recognition (SCO-01)
- **Problem Context**: SRS 4.5.1 only states "Camera chụp ảnh Biển số xe vào hiển thị và lưu vào CSDL". Sprint 1 plan explicitly requires "Tích hợp chức năng scan biển số xe từ hình ảnh".
- **Backend Architecture**:
  1. `PlateRecognitionService`:
     - Receives image upload payload from client.
     - Performs image pre-processing (grayscale, thresholding, contour detection).
     - Extracts alphanumeric characters matching Vietnamese license plate conventions (e.g. `43A-123.45`, `29B-987.65`).
     - Supports fallback/mock mode for local development and CI via `ENABLE_OCR_MOCK=True`.
  2. Vehicle Lookup and Auto-population:
     - Queries `Vehicle` model by `license_plate`.
     - If record exists: Returns JSON payload including `vehicle_id`, `license_plate`, `vehicle_name`, `vehicle_brand`, `customer_name`, `customer_phone`, `slot_id`, `floor`, `active_ticket`.
     - If record does not exist: Returns recognized `license_plate` with `is_registered: false` flag to facilitate walk-in vehicle entry.

### 3.2. News Management (SCO-03)
- **Database Model Specification**:
  ```python
  class News(models.Model):
      title = models.CharField(max_length=255, verbose_name="Tiêu đề tin tức")
      slug = models.SlugField(max_length=255, unique=True)
      summary = models.TextField(blank=True, default="", verbose_name="Tóm tắt")
      content = models.TextField(verbose_name="Nội dung chi tiết")
      thumbnail = models.URLField(
          max_length=500, blank=True, null=True, verbose_name="Ảnh đại diện"
      )
      author = models.ForeignKey(
          "Employee", on_delete=models.PROTECT, related_name="news_articles"
      )
      is_published = models.BooleanField(
          default=True, verbose_name="Trạng thái công khai"
      )
      created_at = models.DateTimeField(auto_now_add=True)
      updated_at = models.DateTimeField(auto_now=True)
      deleted_at = models.DateTimeField(null=True, blank=True)
  ```
- **API Endpoints**:
  - `GET /api/v1/news/`: Public listing for Home Screen 4.2 (`is_published=True`, `deleted_at IS NULL`). Supports pagination and title search.
  - `POST /api/v1/news/`: Requires `IsAuthenticated` with `MANAGER` or `EMPLOYEE` role.

### 3.3. Parking Lot Map Context Menu Permissions (SCO-04)
- **RBAC Matrix**:
  - Action **View Vehicle Info at Slot**:
    - Manager (`MANAGER`): **ALLOWED** (Full access).
    - Employee (`EMPLOYEE`): **ALLOWED** (Expanded per `Tasks_Sprint_1`, augmenting SRS 4.5.2).
    - Customer (`CUSTOMER`): **DENIED** (HTTP 403 Forbidden).
  - Action **Register Parking Slot**:
    - Manager (`MANAGER`): **ALLOWED**.
    - Employee (`EMPLOYEE`): **ALLOWED**.
    - Customer (`CUSTOMER`): **ALLOWED** (Customers may reserve available slots for registered vehicles).
