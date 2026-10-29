# Tổng Quan Về Endpoints

Tóm tắt các Endpoint hiện có trong mã nguồn

Hiện tại, các endpoint nghiệp vụ đã được triển khai và cấu hình route gồm có:

Kiểm tra trạng thái (Health Check):
GET /api/health/: Kiểm tra hạ tầng (Database & OCR ready status).
GET /api/v1/health/: Kiểm tra kết nối cho Frontend clients.
Xác thực & Phiên làm việc (apps/accounts/urls.py):
GET /api/v1/auth/csrf/: Khởi tạo cookie csrftoken.
POST /api/v1/auth/login/: Đăng nhập (nhận identifier, password, remember).
POST /api/v1/auth/logout/: Đăng xuất và thu hồi session.
GET /api/v1/auth/me/: Lấy thông tin tài khoản đang đăng nhập.
Nghiệp vụ Ra/Vào Bãi xe & Đỗ xe (apps/parking/urls.py):
POST /api/v1/parking/plate-scans/: Nhận diện biển số xe bằng OCR từ ảnh chụp.
GET /api/v1/parking/vehicle-lookup/: Tra cứu thông tin phương tiện theo biển số chuẩn hóa.
GET /api/v1/parking/vehicle-search/: Tìm kiếm phương tiện theo nhiều tiêu chí.
POST /api/v1/parking/sessions/check-in/: Check-in xe vào bãi đỗ.
POST /api/v1/parking/sessions/check-out/: Check-out xe và tính toán phí đỗ.
GET /api/v1/parking/gates/: Lấy danh sách cổng kiểm soát barrier.
GET /api/v1/parking/sessions/: Danh sách lịch sử các phiên đỗ xe.
GET /api/v1/parking/sessions/{id}/: Xem chi tiết một phiên đỗ xe.

(Các module khác như customers, employees, vehicles, tickets, reports đang trong lộ trình hoàn thiện theo hợp đồng API-first).

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
  pytest tests/parking/test_check_in_api.py::test_check_in_blacklisted_no_override -v --no-cov
  ```

### B. API Check-out & Tính phí (`/api/v1/parking/sessions/check-out/`)

File test: [`tests/parking/test_check_out_api.py`](file:///E:/parking_management_backend/tests/parking/test_check_out_api.py)

- **Test check-out xe và tính phí thành công**:

  ```bash
  pytest tests/parking/test_check_out_api.py::test_check_out_visitor_success -v --no-cov
  ```

### C. API Tra cứu xe (`/api/v1/parking/vehicle-lookup/` & `vehicle-search/`)

File test: [`tests/parking/test_vehicle_lookup_api.py`](file:///E:/parking_management_backend/tests/parking/test_vehicle_lookup_api.py) & [`test_vehicle_search_api.py`](file:///E:/parking_management_backend/tests/parking/test_vehicle_search_api.py)

- **Test tra cứu xe theo biển số chuẩn hóa**:

  ```bash
  pytest tests/parking/test_vehicle_lookup_api.py::test_vehicle_lookup_success -v --no-cov
  ```

- **Test tìm kiếm xe theo nhiều tiêu chí (Full-text / Trigram GIN)**:

  ```bash
  pytest tests/parking/test_vehicle_search_api.py::test_search_by_license_plate -v --no-cov
  ```

### D. API Xác thực / Authentication (`/api/v1/auth/login/`, `logout/`, `me/`)

File test: [`tests/accounts/test_core_auth.py`](file:///E:/parking_management_backend/tests/accounts/test_core_auth.py)

- **Test đăng nhập thành công**:

  ```bash
  pytest tests/accounts/test_core_auth.py::CoreAuthEndpointsTest::test_login_success -v --no-cov
  ```

- **Test sai mật khẩu hoặc tài khoản bị khóa**:

  ```bash
  pytest tests/accounts/test_core_auth.py::CoreAuthEndpointsTest::test_login_invalid_password -v --no-cov
  ```

### E. API Kiểm tra Hạ tầng / Health Check (`/api/health/`)

File test: [`tests/test_health.py`](file:///E:/parking_management_backend/tests/test_health.py)

- **Test health check thành công**:

  ```bash
  pytest tests/test_health.py::test_health_check_endpoint_success -v --no-cov
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
