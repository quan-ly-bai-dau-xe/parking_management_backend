# Tổng Quan Về Endpoints & Hướng Dẫn Tích Hợp / Kiểm Thử

Tóm tắt các Endpoint hiện có trong mã nguồn backend:

1. **Kiểm tra trạng thái (Health Check)**:
   - `GET /api/health/`: Kiểm tra hạ tầng (Database & OCR ready status).
   - `GET /api/v1/health/`: Kiểm tra kết nối cho Frontend clients.

2. **Xác thực & Phiên làm việc (`apps/accounts/urls.py`)**:
   - `GET /api/v1/auth/csrf/`: Khởi tạo cookie `csrftoken`.
   - `POST /api/v1/auth/login/`: Đăng nhập (nhận `identifier`, `password`, `remember`).
   - `POST /api/v1/auth/logout/`: Đăng xuất và thu hồi session.
   - `GET /api/v1/auth/me/`: Lấy thông tin tài khoản đang đăng nhập.

3. **Nghiệp vụ Ra/Vào Bãi xe & Đỗ xe (`apps/parking/urls.py`)**:
   - `POST /api/v1/parking/plate-scans/`: Nhận diện biển số xe bằng OCR từ ảnh chụp.
   - `GET /api/v1/parking/vehicle-lookup/`: Tra cứu thông tin phương tiện theo biển số chuẩn hóa.
   - `GET /api/v1/parking/vehicle-search/`: Tìm kiếm phương tiện theo nhiều tiêu chí.
   - `POST /api/v1/parking/sessions/check-in/`: Check-in xe vào bãi đỗ.
   - `POST /api/v1/parking/sessions/check-out/`: Check-out xe và tính toán phí đỗ.
   - `GET /api/v1/parking/gates/`: Lấy danh sách cổng kiểm soát barrier.
   - `GET /api/v1/parking/sessions/`: Danh sách lịch sử các phiên đỗ xe.
   - `GET /api/v1/parking/sessions/<id>/`: Xem chi tiết một phiên đỗ xe.

4. **Quản lý Phương tiện (`apps/vehicles/urls.py`)**:
   - `GET /api/v1/vehicle-types/`: Danh mục loại xe (`CAR`, `EV`).
   - `GET /api/v1/vehicles/`: Danh sách phương tiện kèm bộ lọc, tìm kiếm, phân trang.
   - `POST /api/v1/vehicles/`: Thêm mới phương tiện.
   - `GET /api/v1/vehicles/<id>/`: Xem chi tiết phương tiện.
   - `PATCH /api/v1/vehicles/<id>/`: Cập nhật thông tin phương tiện (bảo vệ OCC `row_version`).
   - `DELETE /api/v1/vehicles/<id>/`: Xóa mềm phương tiện (ràng buộc DEL-03).
   - `GET /api/v1/vehicles/summary/`: Tổng hợp chỉ số KPI xe.
   - `GET /api/v1/vehicles/export/`: Xuất báo cáo CSV chuẩn RFC 4180.

5. **Quản lý Khách hàng (`apps/customers/urls.py`)**:
   - `GET /api/v1/customers/`: Danh sách khách hàng (tìm kiếm, lọc nhóm/trạng thái).
   - `POST /api/v1/customers/`: Thêm mới khách hàng.
   - `GET /api/v1/customers/<id>/`: Xem chi tiết khách hàng.
   - `PATCH /api/v1/customers/<id>/`: Cập nhật khách hàng (bảo vệ OCC).
   - `DELETE /api/v1/customers/<id>/`: Xóa mềm khách hàng (ràng buộc DEL-02).
   - `GET /api/v1/customers/summary/`: Tổng hợp chỉ số KPI khách hàng.
   - `GET /api/v1/customers/export/`: Xuất báo cáo CSV khách hàng.

6. **Đơn vị Hành chính & Quản lý Nhân viên (`apps/core/urls.py`, `apps/employees/urls.py`)**:
   - `GET /api/v1/administrative/provinces/`: Danh sách tỉnh/thành phố.
   - `GET /api/v1/administrative/districts/?province_id={id}`: Danh sách quận/huyện.
   - `GET /api/v1/administrative/wards/?district_id={id}`: Danh sách phường/xã.
   - `GET /api/v1/positions/`: Danh sách chức vụ nhân viên.
   - `GET /api/v1/employees/`: Danh sách nhân viên kèm bộ lọc, tìm kiếm, phân trang.
   - `POST /api/v1/employees/`: Thêm mới nhân viên và tự động cấp tài khoản.
   - `GET /api/v1/employees/{id}/`: Xem chi tiết hồ sơ nhân viên.
   - `PATCH /api/v1/employees/{id}/`: Cập nhật nhân viên (bảo vệ OCC, DEL-01).
   - `DELETE /api/v1/employees/{id}/`: Xóa mềm nhân viên và thu hồi phiên làm việc.
   - `GET /api/v1/employees/summary/`: Tổng hợp chỉ số KPI nhân viên.

7. **Dashboard / Trang chủ (`apps/reports/urls.py` - TL-13, TL-14, TL-28.6)**:
   - `GET /api/v1/dashboard/`: Toàn cảnh Trang chủ — trả về 5 nhóm dữ liệu (`kpis`, `floors`, `traffic_chart`, `alerts`, `recent_activities`) trong 1 lần gọi.
   - `GET /api/v1/dashboard/kpis/`: 4 nhóm chỉ số KPI (Kho vị trí, Lưu lượng, Doanh thu - chỉ MANAGER, Nhận diện AI).
   - `GET /api/v1/dashboard/floors/`: Thanh tỉ lệ lấp đầy theo tầng B1/B2/B3 (TL-28.6).
   - `GET /api/v1/dashboard/traffic/`: Biểu đồ lưu lượng xe 24 giờ gần nhất (theo giờ).
   - `GET /api/v1/dashboard/alerts/`: Danh sách cảnh báo khẩn cấp & bất thường (TL-13), tối đa 10 mục (hoặc theo `?limit=N`).
   - `GET /api/v1/dashboard/activities/`: Nhật ký hoạt động gần đây — 10 lượt ra/vào bãi xe gần nhất (hoặc theo `?limit=N`).
Để chạy test các method của API trong dự án `parking_management_backend`, dự án sử dụng framework **`pytest`** kết hợp **`pytest-django`** (cấu hình tại [`pyproject.toml`](file:///E:/parking_management_backend/pyproject.toml) với `DJANGO_SETTINGS_MODULE = "config.settings.test"`).

---

## 1. Điều kiện tiên quyết trước khi chạy Test

Hầu hết các API test đều có đánh dấu `pytest.mark.django_db` (yêu cầu kết nối PostgreSQL để kiểm thử tính toàn vẹn dữ liệu, trigger và hàm lưu trữ).

- **Khởi động database container**:

  ```bash
  docker compose up -d db
  ```

---

## 2. Cú pháp chạy một Test Method cụ thể

Cú pháp tổng quát của `pytest`:

```bash
pytest <đường_dẫn_file_test>::<tên_hàm_test> [tham_số]
# Hoặc nếu test nằm trong TestCase Class:
pytest <đường_dẫn_file_test>::<Tên_Class>::<tên_hàm_test> [tham_số]
```

> [!IMPORTANT]
> **Lưu ý về cờ `--no-cov`**: Trong [`pyproject.toml`](file:///E:/parking_management_backend/pyproject.toml), cấu hình mặc định có cờ `--cov-fail-under=80` (yêu cầu coverage $\ge 80\%$). Khi bạn chỉ chạy một vài method đơn lẻ, tổng coverage sẽ thấp và khiến pytest báo lỗi `FAIL Required test coverage of 80% not reached`. Do đó, khi test nhanh từng method, hãy thêm cờ `--no-cov` (hoặc `-o addopts=""`).

---

## 3. Ví dụ chạy test method cho từng API cụ thể

### A. API Check-in Bãi xe (`/api/v1/parking/sessions/check-in/`)

File test: [`tests/parking/test_check_in_api.py`](file:///E:/parking_management_backend/tests/parking/test_check_in_api.py)

- **Test check-in xe vãng lai thành công**:

  ```bash
  pytest tests/parking/test_check_in_api.py::test_check_in_visitor_success -v --no-cov
  ```

- **Test từ chối khi chưa đăng nhập (401 Unauthorized)**:

  ```bash
  pytest tests/parking/test_check_in_api.py::test_check_in_anonymous_rejected -v --no-cov
  ```

- **Test từ chối quyền khách hàng (403 Forbidden)**:

  ```bash
  pytest tests/parking/test_check_in_api.py::test_check_in_customer_forbidden -v --no-cov
  ```

- **Test xe trong danh sách đen (Blacklist - 409 Conflict)**:

  ```bash
  pytest tests/parking/test_check_in_api.py::test_check_in_blacklisted_plate_rejected_and_alerted -v --no-cov
  ```

### B. API Check-out & Tính phí (`/api/v1/parking/sessions/check-out/`)

File test: [`tests/parking/test_check_out_api.py`](file:///E:/parking_management_backend/tests/parking/test_check_out_api.py)

- **Test check-out xe và tính phí thành công**:

  ```bash
  pytest tests/parking/test_check_out_api.py::test_check_out_visitor_paid_by_cash -v --no-cov
  ```

### C. API Tra cứu xe (`/api/v1/parking/vehicle-lookup/` & `vehicle-search/`)

File test: [`tests/parking/test_vehicle_lookup_api.py`](file:///E:/parking_management_backend/tests/parking/test_vehicle_lookup_api.py) & [`test_vehicle_search_api.py`](file:///E:/parking_management_backend/tests/parking/test_vehicle_search_api.py)

- **Test tra cứu xe theo biển số chuẩn hóa**:

  ```bash
  pytest tests/parking/test_vehicle_lookup_api.py::test_vehicle_lookup_success_existing_vehicle -v --no-cov
  ```

- **Test tìm kiếm xe theo nhiều tiêu chí (Full-text / Trigram GIN)**:

  ```bash
  pytest tests/parking/test_vehicle_search_api.py::test_search_explicit_license_plate -v --no-cov
  ```

### D. API Xác thực / Authentication (`/api/v1/auth/login/`, `logout/`, `me/`)

File test: [`tests/accounts/test_core_auth.py`](file:///E:/parking_management_backend/tests/accounts/test_core_auth.py)

- **Test đăng nhập thành công**:

  ```bash
  pytest tests/accounts/test_core_auth.py::LoginEndpointTest::test_login_success_by_email_case_insensitive -v --no-cov
  ```

- **Test sai mật khẩu hoặc tài khoản bị khóa**:

  ```bash
  pytest tests/accounts/test_core_auth.py::LoginEndpointTest::test_auth_failures_return_uniform_401_msg_m02 -v --no-cov
  ```

### E. API Kiểm tra Hạ tầng / Health Check (`/api/health/`)

File test: [`tests/test_health.py`](file:///E:/parking_management_backend/tests/test_health.py)

- **Test health check thành công**:

  ```bash
  pytest tests/test_health.py::test_health_check_endpoint_success -v --no-cov
  ```

#### F. API Trang chủ & Báo cáo / Dashboard (`/api/v1/dashboard/`)

File test: [`tests/reports/test_dashboard_api.py`](file:///E:/parking_management_backend/tests/reports/test_dashboard_api.py)

- **Test từ chối khi chưa đăng nhập (401 Unauthorized)**:
  ```bash
  pytest tests/reports/test_dashboard_api.py::test_dashboard_overview_anonymous_rejected -v --no-cov
  ```
- **Test từ chối quyền khách hàng CUSTOMER (403 Forbidden)**:
  ```bash
  pytest tests/reports/test_dashboard_api.py::test_dashboard_overview_customer_forbidden -v --no-cov
  ```
- **Test Quản lý (MANAGER) lấy toàn bộ dữ liệu kèm doanh thu tài chính (200 OK)**:
  ```bash
  pytest tests/reports/test_dashboard_api.py::test_dashboard_overview_manager_full_access -v --no-cov
  ```
- **Test Nhân viên (EMPLOYEE) bị ẩn doanh thu `revenue: null` (200 OK - Rule 01 § 2)**:
  ```bash
  pytest tests/reports/test_dashboard_api.py::test_dashboard_overview_employee_revenue_masked -v --no-cov
  ```
- **Test các endpoint con riêng lẻ (kpis, floors, traffic, alerts, activities)**:
  ```bash
  pytest tests/reports/test_dashboard_api.py::test_dashboard_kpis_endpoint -v --no-cov
  pytest tests/reports/test_dashboard_api.py::test_dashboard_floors_endpoint -v --no-cov
  pytest tests/reports/test_dashboard_api.py::test_dashboard_traffic_endpoint -v --no-cov
  pytest tests/reports/test_dashboard_api.py::test_dashboard_alerts_endpoint -v --no-cov
  pytest tests/reports/test_dashboard_api.py::test_dashboard_activities_endpoint -v --no-cov
  ```
- **Chạy toàn bộ test suite Trang chủ (đo coverage apps/reports $\ge 80\%$)**:
  ```bash
  pytest tests/reports/test_dashboard_api.py -o addopts="" --cov=apps/reports --cov-report=term --cov-fail-under=80 -v
  ```

---

## 4. Các tùy chọn chạy linh hoạt khác

1. **Chạy qua môi trường Docker Container** (đảm bảo môi trường giống 100% server):

   ```bash
   docker compose exec web pytest tests/parking/test_check_in_api.py::test_check_in_visitor_success -v --no-cov
   ```

2. **Chạy bằng bộ lọc từ khóa (`-k`)**:
   Tìm và chạy tất cả các test method có tên chứa chữ `check_in`:

   ```bash
   pytest -k "check_in" -v --no-cov
   ```

3. **Chạy toàn bộ test trong một file**:

   ```bash
   pytest tests/parking/test_check_in_api.py -v --no-cov
   ```

4. **In log ra màn hình khi test (`-s`)**:

   ```bash
   pytest tests/parking/test_check_in_api.py::test_check_in_visitor_success -s -v --no-cov
   ```

5. **Chạy toàn bộ test suite để nghiệm thu DoD (Kèm kiểm tra Coverage $\ge 80\%$)**:

   ```bash
   pytest
   # hoặc: docker compose exec web pytest
   ```

---

## 5. Cấu trúc chuẩn của 1 test method API trong dự án

Khi bạn viết thêm test method mới cho API theo quy chuẩn của dự án ([`05-django-feature-implementation`](file:///E:/parking_management_backend/.claude/skills/05-django-feature-implementation/SKILL.md) & [`08-testing-and-definition-of-done.md`](file:///E:/parking_management_backend/.claude/rules/08-testing-and-definition-of-done.md)):

```python
import pytest
from rest_framework import status
from rest_framework.test import APIClient

# 1. Bật database cho test
pytestmark = pytest.mark.django_db


def test_api_endpoint_sample(auth_employee):
    # 2. Khởi tạo DRF test client
    client = APIClient()

    # 3. Giả lập đăng nhập bằng user/role tương ứng
    client.force_authenticate(user=auth_employee)

    # 4. Gửi request đến API
    payload = {"license_plate": "51A-123.45"}
    response = client.post("/api/v1/parking/sessions/check-in/", payload, format="json")

    # 5. Khẳng định mã HTTP Status và cấu trúc JSON trả về
    assert response.status_code == status.HTTP_201_CREATED
    assert "session_code" in response.data
```

---

### 6. Hướng dẫn tích hợp và gọi API Trang chủ cho Frontend (Frontend Integration Guide)

Phần này hướng dẫn các lập trình viên Frontend tích hợp dữ liệu vào màn hình **Trang chủ — Smart Mobility** theo tài liệu phân tích nghiệp vụ và UI/UX (TL-13, TL-14, TL-28.6).

#### A. Nguyên tắc chung khi gọi API Trang chủ

1. **Giao thức & Phương thức**: Tất cả 6 endpoint Trang chủ đều sử dụng phương thức `GET` (chỉ đọc dữ liệu thống kê tổng hợp từ views/tables, không tạo ra đột biến trạng thái).
2. **Không yêu cầu CSRF token**: Vì là `GET` request, Frontend không cần gửi header `X-CSRFToken`.
3. **Xác thực phiên (Session Cookie)**: Phải gửi kèm cookie `sessionid` thông qua tùy chọn `credentials: 'include'` (với fetch API) hoặc `withCredentials: true` (với Axios / `apiClient.js`).
4. **Phân quyền người dùng (Role-based Access Control)**:
   - Chỉ người dùng có vai trò `EMPLOYEE` hoặc `MANAGER` mới được truy cập.
   - Người dùng vai trò `CUSTOMER` sẽ nhận mã `403 Forbidden` (`MSG-4.2-M01`).
   - Chưa đăng nhập sẽ nhận mã `401 Unauthorized` (`MSG-4.1-M02`).
   - **Bảo mật dữ liệu Doanh thu (Rule 01 § 2)**:
     - Nếu tài khoản là `MANAGER`: Trường `kpis.revenue` trả về đầy đủ số liệu tài chính (`total_revenue`, `cash_revenue`, `vietqr_revenue`, `cash_pct`, `vietqr_pct`, `revenue_date`).
     - Nếu tài khoản là `EMPLOYEE`: Trường `kpis.revenue` luôn trả về `null`. Frontend cần kiểm tra điều kiện `if (!data.kpis.revenue)` để ẩn thẻ doanh thu hoặc hiển thị thông báo "Chỉ dành cho Quản lý".

---

#### B. Danh sách các Endpoints Trang chủ

| Endpoint | Mục đích hiển thị trên UI | Khuyến nghị tần suất gọi |
|---|---|---|
| `GET /api/v1/dashboard/` | Lấy toàn bộ 5 khối dữ liệu cùng lúc | Khi vừa load/mở Trang chủ lần đầu |
| `GET /api/v1/dashboard/kpis/` | Lấy 4 thẻ chỉ số KPI trên đầu | Polling mỗi 30 - 60 giây |
| `GET /api/v1/dashboard/floors/` | 3 thanh tỷ lệ lấp đầy tầng B1, B2, B3 | Polling mỗi 60 giây |
| `GET /api/v1/dashboard/traffic/` | Dữ liệu vẽ biểu đồ 24 giờ | Khi load trang hoặc đổi khoảng xem |
| `GET /api/v1/dashboard/alerts/?limit=10` | Khối cảnh báo khẩn cấp & bất thường (TL-13) | Polling mỗi 15 - 30 giây |
| `GET /api/v1/dashboard/activities/?limit=10` | Nhật ký hoạt động xe ra/vào gần nhất | Polling mỗi 15 - 30 giây |

---

#### C. Ví dụ mã nguồn Frontend tích hợp (JavaScript / Fetch / Axios)

##### 1. Khởi tạo service gọi API (`src/features/dashboardService.js`)

```javascript
// src/features/dashboardService.js
import apiClient from '../services/apiClient';

export const dashboardService = {
  /**
   * Lấy toàn bộ dữ liệu tổng quan Trang chủ (Single Call)
   */
  async getOverview() {
    const response = await apiClient.get('/api/v1/dashboard/');
    return response.data;
  },

  /**
   * Cập nhật riêng 4 thẻ chỉ số KPI
   */
  async getKPIs() {
    const response = await apiClient.get('/api/v1/dashboard/kpis/');
    return response.data;
  },

  /**
   * Cập nhật danh sách cảnh báo khẩn cấp (TL-13)
   */
  async getAlerts(limit = 10) {
    const response = await apiClient.get(`/api/v1/dashboard/alerts/?limit=${limit}`);
    return response.data;
  },

  /**
   * Cập nhật dòng hoạt động ra/vào xe mới nhất
   */
  async getRecentActivities(limit = 10) {
    const response = await apiClient.get(`/api/v1/dashboard/activities/?limit=${limit}`);
    return response.data;
  },
};
```

##### 2. Hoặc sử dụng Fetch API gốc (Native Fetch)

```javascript
async function fetchDashboardOverview() {
  const response = await fetch('/api/v1/dashboard/', {
    method: 'GET',
    credentials: 'include', // Bắt buộc để gửi kèm cookie sessionid
    headers: {
      'Accept': 'application/json',
    },
  });

  if (response.status === 401) {
    // Phiên làm việc hết hạn -> Chuyển hướng sang trang đăng nhập
    window.location.href = '/login';
    return;
  }
  if (response.status === 403) {
    alert('Tài khoản của bạn không có quyền truy cập Trang chủ quản trị.');
    return;
  }

  const data = await response.json();
  console.log('Dữ liệu Trang chủ:', data);
  return data;
}
```

---

#### D. Hướng dẫn hiển thị các khối dữ liệu lên giao diện

##### 1. Khối 4 Thẻ KPI (`data.kpis`)
- **Thẻ 1: Kho vị trí đỗ (`data.kpis.slots`)**:
  - Số chỗ còn trống: `slots.available_slots` (ví dụ: `120`).
  - Tổng số chỗ hoạt động: `slots.operational_slots` (ví dụ: `285`).
  - Tỷ lệ lấp đầy: `slots.occupancy_rate_pct` (ví dụ: `57.9%`).
  - Trạng thái chữ: `slots.status_text` (ví dụ: `"Còn chỗ"` hoặc `"Sắp đầy"`).
- **Thẻ 2: Lượt xe hôm nay (`data.kpis.traffic`)**:
  - Lượt vào: `traffic.today_entries`.
  - Lượt ra: `traffic.today_exits`.
  - Xe đang đỗ trong bãi: `traffic.active_parking`.
- **Thẻ 3: Doanh thu hôm nay (`data.kpis.revenue`)**:
  - **Kiểm tra null**: Nếu người dùng là nhân viên vận hành thông thường (`EMPLOYEE`), `revenue` sẽ là `null`.
  - Nếu là Quản lý (`MANAGER`):
    - Tổng doanh thu: Format tiền tệ VNĐ `revenue.total_revenue`.
    - Cơ cấu thanh toán: Tiền mặt `revenue.cash_pct%` vs VietQR `revenue.vietqr_pct%`.
- **Thẻ 4: Tỷ lệ nhận diện AI (`data.kpis.ai_recognition`)**:
  - Tỷ lệ tự động: `ai_recognition.ai_recognition_rate_pct%` (mục tiêu hệ thống $\ge 90\%$).
  - Độ tin cậy trung bình: `ai_recognition.avg_ai_confidence%`.
  - Số cổng quét tự động đang online: `ai_recognition.active_auto_scan_gates`.

##### 2. Khối Thanh tỷ lệ lấp đầy theo tầng (`data.floors` - TL-28.6)
Mỗi phần tử trong danh sách `data.floors` đại diện cho một tầng hầm (`B1`, `B2`, `B3`):
- `fe_display_label`: Chuỗi định dạng sẵn theo chuẩn thiết kế, ví dụ: `"Tầng B1 - Xe ô tô & EV · 93% (88/95 chỗ)"` — Frontend có thể hiển thị trực tiếp lên tiêu đề thanh tiến trình (progress bar header) mà không cần tự format.
- `occupancy_percentage`: Giá trị phần trăm float (ví dụ: `92.6`) để set `width: ${occupancy_percentage}%` cho progress bar.
- `status_badge`: Trả về `"Sắp đầy"` nếu $\ge 90\%$ (đổi màu cảnh báo vàng/đỏ) hoặc `"Còn chỗ"` (màu xanh).

##### 3. Khối Biểu đồ lưu lượng 24 giờ (`data.traffic_chart`)
Mảng gồm 24 điểm dữ liệu theo các mốc giờ:
- `traffic_hour`: Thời gian chuẩn ISO 8601 (ví dụ: `"2026-11-01T08:00:00Z"`). Dùng `new Date(item.traffic_hour).getHours() + 'h'` để hiển thị trục hoành X.
- `entry_count`: Đường biểu diễn lượt xe vào.
- `exit_count`: Đường biểu diễn lượt xe ra.

##### 4. Khối Cảnh báo khẩn cấp & bất thường (`data.alerts` - TL-13)
Danh sách cảnh báo từ bảng `system_alert`, các cảnh báo chưa xử lý (`resolved_at === null`) được ưu tiên lên đầu:
- `severity`: Mức độ cảnh báo để đổi màu badge:
  - `CRITICAL`: Màu đỏ (cảnh báo khẩn cấp: xe blacklist, mất an ninh).
  - `WARNING`: Màu vàng/cam (cảnh báo xe đỗ quá hạn overstay, lỗi camera mờ).
  - `INFO`: Màu xanh dương (thông báo hệ thống).
- `message`: Nội dung cảnh báo bằng tiếng Việt.
- `occurred_at`: Thời điểm phát sinh cảnh báo.

##### 5. Khối Nhật ký hoạt động gần đây (`data.recent_activities`)
Dòng thời gian hiển thị 10 lượt xe ra/vào mới nhất:
- `license_plate`: Biển số xe (ví dụ: `"51A-888.88"`).
- `direction`: Hướng xe — `'IN'` (Xe vào - icon xanh mũi tên vào) hoặc `'OUT'` (Xe ra - icon cam mũi tên ra).
- `timestamp`: Thời gian xe qua trạm.
- `fee_amount`: Phí đỗ xe (nếu là lượt xe ra `OUT`).
- `recognition_source`: Phương thức nhận diện (`'AI'` hoặc `'MANUAL'`).

