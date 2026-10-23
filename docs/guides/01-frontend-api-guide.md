# Cẩm Nang Tích Hợp API Frontend — Parking Management Backend

Tài liệu kỹ thuật chính thức dành cho lập trình viên Frontend tích hợp hệ thống Quản lý Bãi đỗ xe thông minh (**Parking Management Backend**). Toàn bộ ví dụ HTTP, JSON, SQL và TypeScript trong cẩm nang đều được trích xuất nguyên văn từ các cuộc gọi thực tế trên môi trường live stack (lưu tại `.agents/round47_guide_examples.log`, với mọi giá trị bí mật được che bằng `[MASKED]`).

---

## 1. Tổng quan Backend & Danh mục URLs

Hệ thống backend được xây dựng trên nền tảng **Django 6.1.2**, **Django REST Framework (DRF) 3.18.3**, cơ sở dữ liệu **PostgreSQL 18.6**, máy chủ ứng dụng **Gunicorn (4 workers, 6 threads)** và công cụ tự động sinh đặc tả OpenAPI **drf-spectacular 0.30.0**.

### 1.1 Danh mục URLs tài liệu và hạ tầng

| Đường dẫn (URL) | Mục đích | Quyền truy cập | Định dạng |
|---|---|:---:|:---:|
| `http://127.0.0.1:8000/api/docs/` | Giao diện tương tác Swagger UI | Public | HTML / JS / CSS |
| `http://127.0.0.1:8000/api/redoc/` | Giao diện tài liệu dạng ReDoc | Public | HTML / JS |
| `http://127.0.0.1:8000/api/schema/` | Đặc tả kỹ thuật OpenAPI 3.0 Schema | Public | YAML / JSON |
| `http://127.0.0.1:8000/api/health/` | Health check hạ tầng (Docker, K8s, Load Balancer) | Public | JSON |
| `http://127.0.0.1:8000/api/v1/health/` | Health check phiên bản API v1 dành cho Frontend | Public | JSON |

> **Lưu ý về thiết kế**: Hai đường dẫn `/api/health/` và `/api/v1/health/` đều được cung cấp có chủ đích. Đường dẫn `/api/health/` phục vụ các hệ thống giám sát hạ tầng tầng mạng (Load Balancer, Reverse Proxy, Docker compose healthcheck), trong khi `/api/v1/health/` phục vụ frontend gọi thăm dò trạng thái kết nối theo tiền tố định tuyến phiên bản (`/api/v1/*`).

### 1.2 Phản hồi Health Check thực tế từ Live Stack

Cả hai endpoint health check đều trả về trạng thái hoạt động của cơ sở dữ liệu PostgreSQL và cờ sẵn sàng của mô hình AI FastALPR OCR:

```http
GET /api/health/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "healthy",
  "database": "connected",
  "ocr_ready": false
}
```

> **Lưu ý**: Trường `ocr_ready` mang giá trị `true` sau khi Gunicorn worker chạy hook `post_fork` (`warmup_ocr()`), hoặc `false` khi mô hình OCR chưa thực hiện warm-up lần đầu.

Trường hợp cơ sở dữ liệu mất kết nối, hệ thống trả về HTTP `503 Service Unavailable`:

```json
{
  "status": "unhealthy",
  "database": "disconnected",
  "ocr_ready": false
}
```

---

## 2. Khởi động môi trường phát triển trong 1 phút

Toàn bộ dịch vụ Backend và Cơ sở dữ liệu được đóng gói chuẩn hóa trong `docker-compose.yml`.

### 2.1 Lệnh khởi động

Mở terminal tại thư mục gốc của dự án và thực thi lệnh:

```bash
docker compose up --build
```

### 2.2 Quy trình khởi động và nhật ký kỳ vọng (Expected Startup Log)

1. Container `db` (`postgres:18.6-alpine`) khởi tạo và tự động kiểm tra sức khỏe qua lệnh nội bộ `pg_isready`.
2. Sau khi `db` chuyển sang trạng thái `healthy`, container `web` khởi động, tự động thực thi di chuyển dữ liệu (`RUN_MIGRATIONS=1` tương đương `python manage.py migrate --noinput`) và khởi chạy 4 tiến trình worker Gunicorn tại địa chỉ `http://127.0.0.1:8000`:

```text
[INFO] Starting gunicorn 25.3.0
[INFO] Listening at: http://0.0.0.0:8000 (1)
[INFO] Using worker: gthread
[INFO] Booting worker with pid: 14
[INFO] Booting worker with pid: 15
[INFO] Booting worker with pid: 16
[INFO] Booting worker with pid: 17
FastAlprPlateRecognizer (Dual-OCR Ensemble) initialized successfully.
```

### 2.3 Nạp dữ liệu mẫu ban đầu (Seed Data)

Để nạp đầy đủ bãi xe, tầng, cổng barrier, ô đỗ và 20 tài khoản mẫu, thực thi:

```bash
docker compose exec web python manage.py load_sample_data --force-production
```

Nhật ký phản hồi thực tế:

```text
Loading seed data from: D:\GitHub\codegym\parking_management_backend\db\02-seed.sql
Executing seed SQL...
Sample seed data loaded successfully.
```

### 2.4 Kiểm tra trạng thái sẵn sàng

Kiểm tra hệ thống đã hoạt động bình thường bằng lệnh:

```bash
curl -i http://127.0.0.1:8000/api/health/
```

Khi nhận được mã trạng thái `HTTP/1.1 200 OK` cùng nội dung JSON `{"status": "healthy", ...}`, hệ thống đã sẵn sàng phục vụ frontend.

---

## 3. Thiết lập mật khẩu phát triển & Danh sách tài khoản mẫu

Nhằm tuân thủ tiêu chuẩn an toàn bảo mật nghiêm ngặt, 20 tài khoản mẫu được nạp từ `db/02-seed.sql` đều mang hash mật khẩu bị khóa không thể đăng nhập trực tiếp (tiền tố `!` theo chuẩn Django). Lập trình viên bắt buộc phải tự đặt mật khẩu phát triển thông qua lệnh quản trị CLI.

### 3.1 Lệnh đặt mật khẩu tài khoản phát triển

Lệnh quản trị `set_account_password` nhận mật khẩu độc quyền thông qua biến môi trường `ACCOUNT_PASSWORD` (tuyệt đối không truyền mật khẩu qua cờ dòng lệnh nhằm tránh lưu vết trong lịch sử terminal):

- **Trên máy chủ Docker**:

  ```bash
  docker compose exec -e ACCOUNT_PASSWORD="<your-dev-password>" web python manage.py set_account_password --identifier hoang.dinh.khang@example.com
  ```

- **Khi chạy trực tiếp trên máy cục bộ**:

  ```bash
  # Linux / macOS / Git Bash
  ACCOUNT_PASSWORD="<your-dev-password>" python manage.py set_account_password --identifier hoang.dinh.khang@example.com

  # Windows PowerShell
  $env:ACCOUNT_PASSWORD="<your-dev-password>"
  python manage.py set_account_password --identifier hoang.dinh.khang@example.com
  ```

Kết quả phản hồi thực tế:

```text
$ ACCOUNT_PASSWORD=[MASKED] python manage.py set_account_password --identifier hoang.dinh.khang@example.com
Successfully updated password for account #1 (hoang.dinh.khang@example.com).
$ ACCOUNT_PASSWORD=[MASKED] python manage.py set_account_password --identifier luong.mai.phuong@example.org
Successfully updated password for account #2 (luong.mai.phuong@example.org).
$ ACCOUNT_PASSWORD=[MASKED] python manage.py set_account_password --identifier trinh.xuan.truong@example.com
Successfully updated password for account #9 (trinh.xuan.truong@example.com).
```

### 3.2 Bảng danh sách tài khoản mẫu trong hệ thống

Hệ thống phân cấp 3 vai trò người dùng chính: **MANAGER** (Quản lý), **EMPLOYEE** (Nhân viên vận hành) và **CUSTOMER** (Khách hàng).

| ID | Email đăng nhập | Số điện thoại | Vai trò (`role`) | Trạng thái | Mục đích sử dụng thử nghiệm |
|:---:|---|:---:|:---:|:---:|---|
| 1 | `hoang.dinh.khang@example.com` | `0880721788` | `MANAGER` | `Active` | Toàn quyền quản trị, ghi đè xe trong blacklist, xem báo cáo |
| 2 | `luong.mai.phuong@example.org` | `0385211625` | `EMPLOYEE` | `Active` | Trực cổng barrier: quét biển số, check-in, check-out, tra cứu xe |
| 3 | `do.minh.quan@example.net` | `0760098704` | `EMPLOYEE` | `Active` | Nhân viên vận hành ca trực |
| 4 | `truong.ngoc.bich@example.com` | `0374179898` | `EMPLOYEE` | `Inactive` | Kiểm thử tài khoản bị khóa (`is_active=False`, trả về 401 khi đăng nhập) |
| 5 | `vu.quoc.hung@example.org` | `0361681236` | `EMPLOYEE` | `Active` | Nhân viên kiểm soát bãi đỗ |
| 6 | `phan.thanh.thao@example.net` | `0356582610` | `EMPLOYEE` | `Active` | Nhân viên kiểm soát bãi đỗ |
| 7 | `ngo.gia.bao@example.com` | `0864769738` | `EMPLOYEE` | `Active` | Nhân viên kiểm soát bãi đỗ |
| 8 | `dinh.lan.anh@example.org` | `0707739639` | `EMPLOYEE` | `Active` | Nhân viên kiểm soát bãi đỗ |
| 9 | `trinh.xuan.truong@example.com` | `0868851325` | `CUSTOMER` | `Active` | Chủ xe `43K-860.50`; kiểm thử quyền khách hàng (nhận 403 khi gọi API đỗ xe) |
| 10 | `bui.khanh.doan@example.org` | `0348083802` | `CUSTOMER` | `Active` | Khách hàng sở hữu phương tiện cá nhân |
| 11 | `lam.hoang.viet@example.net` | `0790226163` | `CUSTOMER` | `Active` | Khách hàng |
| 12 | `doan.tuyet.mai@example.com` | `0779009950` | `CUSTOMER` | `Active` | Khách hàng |
| 13 | `ho.trong.nghia@example.org` | `0789632200` | `CUSTOMER` | `Active` | Khách hàng |
| 14 | `ta.minh.chau@example.net` | `0708960990` | `CUSTOMER` | `Active` | Khách hàng |
| 15 | `cao.tien.dung@example.com` | `0327855040` | `CUSTOMER` | `Active` | Khách hàng |
| 16 | `duong.hong.nhung@example.org` | `0332790866` | `CUSTOMER` | `Active` | Khách hàng |
| 17 | `ha.manh.cuong@example.net` | `0861032661` | `CUSTOMER` | `Active` | Khách hàng |
| 18 | `mai.phuong.thao@example.com` | `0781281571` | `CUSTOMER` | `Active` | Khách hàng |
| 19 | `kieu.quoc.tuan@example.org` | `0392758924` | `CUSTOMER` | `Active` | Khách hàng |
| 20 | `chu.kim.oanh@example.net` | `0387755825` | `CUSTOMER` | `Active` | Khách hàng |

---

## 4. Luồng xác thực chi tiết từng bước (Step-by-Step Auth Flow)

Hệ thống xác thực kết hợp giữa **Django Session Cookie** (`sessionid`), cơ chế chống giả mạo **Double Submit CSRF** (`csrftoken` và header `X-CSRFToken`), và cơ chế ghi nhớ đăng nhập dài hạn **Persistent Remember-Me** (`parking_remember_token`).

### 4.1 Bước 1: Khởi tạo cookie CSRF (CSRF Bootstrap)

Trước khi gửi bất kỳ yêu cầu đột biến dữ liệu nào (`POST`, `PUT`, `PATCH`, `DELETE`), Frontend bắt buộc phải thực hiện bước bắt tay CSRF để lấy cookie `csrftoken`:

```http
GET /api/v1/auth/csrf/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json

HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: csrftoken=[MASKED]; expires=Thu, 21 Oct 2027 15:00:26 GMT; Max-Age=31449600; Path=/; SameSite=Lax

{
  "detail": "Khởi tạo cookie CSRF thành công."
}
```

### 4.2 Bước 2: Đăng nhập (`POST /api/v1/auth/login/`)

Yêu cầu đăng nhập phải đính kèm header `X-CSRFToken` mang giá trị đọc được từ cookie `csrftoken`:

#### Trường hợp 1: Thiếu header `X-CSRFToken` (Lỗi 403 Forbidden)

```http
POST /api/v1/auth/login/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
Content-Type: application/json

{"identifier": "hoang.dinh.khang@example.com", "password": "[MASKED]", "remember": false}

HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "code": "PROP-4.1-P06",
  "message": "Mã CSRF không hợp lệ hoặc bị thiếu.",
  "details": {
    "reason": "CSRF token missing."
  }
}
```

#### Trường hợp 2: Sai mật khẩu hoặc tài khoản không tồn tại (Lỗi 401 Unauthorized)

```http
POST /api/v1/auth/login/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: application/json

{"identifier": "hoang.dinh.khang@example.com", "password": "[MASKED]", "remember": false}

HTTP/1.1 401 Unauthorized
Content-Type: application/json

{
  "code": "MSG-4.1-M02",
  "message": "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu",
  "details": {}
}
```

#### Trường hợp 3: Để trống trường thông tin (Lỗi 400 Bad Request)

```http
POST /api/v1/auth/login/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: application/json

{"identifier": "", "password": "[MASKED]", "remember": false}

HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "MSG-4.1-M03",
  "message": "Xin nhập đầy đủ Tên đăng nhập và Mật khẩu",
  "details": {}
}
```

#### Trường hợp 4: Đăng nhập thành công KHÔNG chọn Remember-Me (`remember: false`)

Trình duyệt nhận được cookie phiên làm việc `sessionid` (không có `Max-Age` hay `expires`, tự xóa khi đóng trình duyệt) và một `csrftoken` mới đã được xoay vòng bảo mật:

```http
POST /api/v1/auth/login/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: application/json

{"identifier": "hoang.dinh.khang@example.com", "password": "[MASKED]", "remember": false}

HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: csrftoken=[MASKED]; expires=Thu, 21 Oct 2027 15:00:26 GMT; Max-Age=31449600; Path=/; SameSite=Lax
Set-Cookie: sessionid=[MASKED]; HttpOnly; Path=/; SameSite=Lax

{
  "id": 1,
  "email": "hoang.dinh.khang@example.com",
  "phone": "0880721788",
  "role": "MANAGER"
}
```

#### Trường hợp 5: Đăng nhập thành công CÓ chọn Remember-Me (`remember: true`)

Khi bật `remember: true`, ngoài `sessionid`, Backend gửi thêm cookie dài hạn `parking_remember_token` (`Max-Age=2592000` = 30 ngày):

```http
POST /api/v1/auth/login/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: application/json

{"identifier": "luong.mai.phuong@example.org", "password": "[MASKED]", "remember": true}

HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: parking_remember_token=[MASKED]; expires=Sat, 21 Nov 2026 15:00:26 GMT; HttpOnly; Max-Age=2592000; Path=/; SameSite=Lax
Set-Cookie: csrftoken=[MASKED]; expires=Thu, 21 Oct 2027 15:00:26 GMT; Max-Age=31449600; Path=/; SameSite=Lax
Set-Cookie: sessionid=[MASKED]; HttpOnly; Path=/; SameSite=Lax

{
  "id": 2,
  "email": "luong.mai.phuong@example.org",
  "phone": "0385211625",
  "role": "EMPLOYEE"
}
```

### 4.3 Bảng đặc tính kỹ thuật các loại Cookies

| Tên Cookie | Cờ `HttpOnly` | Cờ `SameSite` | Cờ `Secure` | Thời hạn sống (Lifetime) | Mục đích kỹ thuật |
|---|:---:|:---:|:---:|---|---|
| `csrftoken` | **False** | `Lax` | False (dev) / True (prod) | 1 năm (31,449,600 giây) | Mã bảo vệ chống giả mạo request CSRF; JavaScript đọc được qua `document.cookie`. |
| `sessionid` | **True** | `Lax` | False (dev) / True (prod) | Browser session (tối đa 12 giờ / 43,200 giây trên máy chủ) | Định danh phiên làm việc hiện thời của người dùng; lưu trong RAM trình duyệt, mất khi đóng trình duyệt. |
| `parking_remember_token` | **True** | `Lax` | False (dev) / True (prod) | 30 ngày (2,592,000 giây) | Ghi nhớ đăng nhập dài hạn định dạng `<series>:<raw_token>`. Trình duyệt lưu vào ổ đĩa. |

### 4.4 Bước 3: Lấy thông tin người dùng (`GET /api/v1/auth/me/`)

Sau khi đăng nhập, Frontend gọi endpoint này để xác nhận danh tính hoặc lấy lại thông tin tài khoản khi khởi chạy ứng dụng:

```http
GET /api/v1/auth/me/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: sessionid=[MASKED]

HTTP/1.1 200 OK
Content-Type: application/json

{
  "id": 1,
  "email": "hoang.dinh.khang@example.com",
  "phone": "0880721788",
  "role": "MANAGER"
}
```

### 4.5 Bước 4: Tự động phục hồi phiên khi tải lại trang (Silent Re-authentication)

Khi người dùng đóng trình duyệt rồi mở lại (làm mất `sessionid`), hoặc khi `sessionid` hết hạn 12 giờ:

1. Trình duyệt gửi request `GET /api/v1/auth/me/` chỉ với cookie `parking_remember_token`.
2. Middleware `PersistentRememberMeMiddleware` tại backend tự động tra cứu hash SHA-256 theo chuỗi `series` trong bảng `persistent_login_token`.
3. Khi hợp lệ, backend tự động đăng nhập người dùng, cấp phát `sessionid` mới, thực hiện xoay vòng token nguyên tử (`token rotation` sau cửa sổ ân hạn 30 giây) và gửi `Set-Cookie` mới về client mà không cần người dùng nhập lại mật khẩu:

```http
GET /api/v1/auth/me/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: parking_remember_token=[MASKED]

HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: parking_remember_token=[MASKED]; expires=Sat, 21 Nov 2026 15:00:26 GMT; HttpOnly; Max-Age=2592000; Path=/; SameSite=Lax
Set-Cookie: csrftoken=[MASKED]; expires=Thu, 21 Oct 2027 15:00:26 GMT; Max-Age=31449600; Path=/; SameSite=Lax
Set-Cookie: sessionid=[MASKED]; HttpOnly; Path=/; SameSite=Lax

{
  "id": 2,
  "email": "luong.mai.phuong@example.org",
  "phone": "0385211625",
  "role": "EMPLOYEE"
}
```

### 4.6 Bước 5: Đăng xuất (`POST /api/v1/auth/logout/`)

Khi đăng xuất, backend thu hồi toàn bộ token ghi nhớ trong cơ sở dữ liệu và xóa sạch các cookies:

```http
POST /api/v1/auth/logout/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
X-CSRFToken: [MASKED]

HTTP/1.1 200 OK
Content-Type: application/json
Set-Cookie: sessionid=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/; SameSite=Lax
Set-Cookie: parking_remember_token=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; Path=/

{
  "detail": "Đăng xuất thành công."
}
```

---

## 5. Mã mẫu chuẩn cho `fetch` và `axios` (Copy-Paste Ready)

Toàn bộ các đoạn mã dưới đây đã được kiểm tra tính hợp lệ cú pháp nghiêm ngặt bằng trình phân giải `node --check` (Node.js v25.9.0, kết quả: `Exit code 0`).

### 5.1 Đoạn mã mẫu sử dụng Native `fetch`

```javascript
// File: src/services/apiFetch.js

/**
 * Tiện ích trích xuất giá trị cookie theo tên từ document.cookie
 * @param {string} name - Tên cookie cần lấy
 * @returns {string|null} Giá trị cookie hoặc null nếu không tìm thấy
 */
export function getCookie(name) {
  if (typeof document === "undefined") return null;
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) {
    return parts.pop().split(";").shift();
  }
  return null;
}

/**
 * Wrapper cho fetch tự động gắn CSRF token và tự động retry khi phiên hết hạn
 * @param {string} url - Đường dẫn API (ví dụ: '/api/v1/parking/gates/')
 * @param {RequestInit} options - Tùy chọn fetch
 * @param {boolean} isRetry - Cờ đánh dấu lượt gọi thử lại nội bộ
 * @returns {Promise<Response>}
 */
export async function apiFetch(url, options = {}, isRetry = false) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});

  // Đính kèm CSRF token cho các thao tác thay đổi dữ liệu
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    const csrfToken = getCookie("csrftoken");
    if (csrfToken && !headers.has("X-CSRFToken")) {
      headers.set("X-CSRFToken", csrfToken);
    }
  }

  const mergedOptions = {
    ...options,
    method,
    headers,
    credentials: "include", // Bắt buộc gửi kèm session cookie và remember token
  };

  const response = await fetch(url, mergedOptions);

  // Xử lý tự động Silent Re-auth khi nhận HTTP 401 do hết hạn session
  if (response.status === 401 && !isRetry && !url.includes("/api/v1/auth/login/")) {
    try {
      // Gọi endpoint /api/v1/auth/me/ để kích hoạt middleware phục hồi session qua remember token
      const reauthResp = await fetch("/api/v1/auth/me/", {
        method: "GET",
        credentials: "include",
      });

      if (reauthResp.ok) {
        // Phục hồi phiên thành công: thử lại yêu cầu ban đầu duy nhất 1 lần
        return await apiFetch(url, options, true);
      }
    } catch (err) {
      console.error("Lỗi phục hồi phiên làm việc tự động:", err);
    }
  }

  return response;
}
```

### 5.2 Đoạn mã mẫu sử dụng thư viện `axios`

```javascript
// File: src/services/apiClient.js
import axios from "axios";

export const apiClient = axios.create({
  baseURL: "/api/v1",
  withCredentials: true, // Bắt buộc để gửi cookie xuyên origin hoặc qua dev proxy
  xsrfCookieName: "csrftoken", // Tên cookie chứa CSRF token
  xsrfHeaderName: "X-CSRFToken", // Tên header gửi CSRF token lên Django
  headers: {
    "Accept": "application/json",
    "Content-Type": "application/json",
  },
});

// Response Interceptor xử lý phục hồi phiên tự động khi gặp lỗi 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Kiểm tra lỗi 401, tránh vòng lặp vô tận và không retry trên chính API đăng nhập
    if (
      error.response &&
      error.response.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url.includes("/auth/login/")
    ) {
      originalRequest._retry = true;

      try {
        // Thử phục hồi phiên bằng cookie parking_remember_token qua endpoint /auth/me/
        await apiClient.get("/auth/me/");

        // Cập nhật lại CSRF token mới từ cookie trước khi gửi lại
        return apiClient(originalRequest);
      } catch (reauthError) {
        // Phục hồi thất bại (remember token đã hết hạn hoặc không tồn tại) -> Chuyển về màn hình login
        console.warn("Phiên làm việc đã kết thúc. Vui lòng đăng nhập lại.", reauthError);
        if (typeof window !== "undefined") {
          window.location.href = "/login";
        }
        return Promise.reject(reauthError);
      }
    }

    return Promise.reject(error);
  }
);
```

---

## 6. Xử lý CORS & Cookie trong môi trường phát triển

### 6.1 Biến môi trường Backend liên quan

Trong file `.env` của backend, các biến sau điều khiển chính sách CORS và CSRF:

```env
# Danh sách origins được phép gọi API cross-origin
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173

# Danh sách origins được Django tin cậy để duyệt CSRF token
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
```

### 6.2 Bản chất kỹ thuật & Bảng quyết định Cookie Scoping (3 Trường hợp cấu hình)

Phạm vi truy cập Cookie giữa ứng dụng Frontend và API Backend được chi phối bởi hai tiêu chuẩn cốt lõi:

1. **Phạm vi cổng mạng (Port Scoping theo [RFC 6265](https://www.rfc-editor.org/rfc/rfc6265.txt), Section 8.5 "Weak Confidentiality")**:
   > "Cookies do not provide isolation by port."  
   *(Ngày truy cập: 2026-10-22)*.
2. **Quy tắc Same-Site (theo [HTML Standard](https://html.spec.whatwg.org/multipage/origin.html#same-site))**:
   > "Unlike the same origin and same origin-domain concepts, for schemelessly same site and same site, the port and domain components are ignored."  
   *(Ngày truy cập: 2026-10-22)*.

Kiểm tra trực tiếp phản hồi thực tế từ backend cho thấy các header `Set-Cookie` (`csrftoken` và `sessionid`) hoàn toàn **không mang thuộc tính `Domain`** (`Domain: ''`), đồng nghĩa với việc cookie mang tính chất host-only gắn liền với host của request.

#### Bảng quyết định cấu hình Frontend & Cookie

| Trường hợp | Ngữ cảnh kiến trúc | Cơ chế Cookie & Same-Site | Khả năng đọc `csrftoken` từ JS | Giải pháp kỹ thuật bắt buộc |
|---|---|---|:---:|---|
| **(a) Cùng host, khác port** | Frontend: `http://localhost:3000`<br>Backend: `http://localhost:8000` | Cùng host `localhost`. Cổng mạng bị bỏ qua trong tính toán same-site; cookie scoped theo host không bị cô lập theo port (RFC 6265). | **Đọc được**<br>(vì `HttpOnly=False` và cùng host `localhost`) | **Không cần Dev Proxy**.<br>Chỉ cần cấu hình `CORS_ALLOWED_ORIGINS` và `CSRF_TRUSTED_ORIGINS` chứa origin frontend, đồng thời frontend gọi API với cờ credentials (`credentials: "include"` hoặc `withCredentials: true`). |
| **(b) Khác host** | Frontend: `http://localhost:3000`<br>Backend: `http://127.0.0.1:8000`<br>*(hoặc 2 tên miền máy ảo khác nhau)* | Khác host (`localhost` != `127.0.0.1`). Cookie của backend không gắn với host của frontend. | **Không thể đọc**<br>(bị chặn bởi Same-Origin Policy) | **Bắt buộc dùng Same-Origin Dev Proxy**.<br>Cấu hình dev proxy trên Vite/Next.js/Webpack (xem mục 6.3) để chuyển hướng `/api/*` sang backend, biến các request thành cùng origin. |
| **(c) Khác registrable domain khi triển khai** | Frontend: `https://app.example.com`<br>Backend: `https://api.anotherdomain.net` | Khác registrable domain (Cross-Site hoàn toàn). Trình duyệt cô lập cookie và chặn cookie bên thứ ba. | **Tuyệt đối không thể đọc** | **Bắt buộc dùng Same-Origin Reverse Proxy** (Nginx/Caddy định tuyến cùng domain) **hoặc thay đổi kiến trúc API** (trả CSRF token trong response body / dùng Bearer Token). Đây là quyết định kiến trúc thuộc thẩm quyền Owner và hiện chưa được triển khai. |

> **Minh bạch hóa kiểm chứng**:
>
> - **ĐÃ XÁC MINH**: Thuộc tính thực tế của `Set-Cookie` phát hành từ backend (không có `Domain`) và các trích dẫn chuẩn hóa quốc tế đã được kiểm chứng bằng công cụ tự động.
> - **UNVERIFIED**: Hành vi thực tế của các trình duyệt thương mại (Chrome, Firefox, Safari) đối với việc chia sẻ cookie giữa hai port khác nhau trên môi trường thực tế chưa được kiểm chứng trực tiếp bằng headless browser trong đợt kiểm thử này.

### 6.3 Giải pháp chuẩn: Cấu hình Same-Origin Dev Proxy

Giải pháp tối ưu và chuẩn mực nhất cho Frontend SPA là sử dụng **Reverse Proxy** tích hợp sẵn của công cụ phát triển. Mọi yêu cầu từ giao diện gửi tới đường dẫn cục bộ `/api/*` (cùng origin `localhost:3000`), sau đó Dev Server sẽ proxy ngầm sang backend `http://127.0.0.1:8000`:

#### Cấu hình cho Vite (`vite.config.ts`)

```typescript
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
      "/static": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
    },
  },
});
```

#### Cấu hình cho Next.js (`next.config.js`)

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: "http://127.0.0.1:8000/api/:path*",
      },
      {
        source: "/static/:path*",
        destination: "http://127.0.0.1:8000/static/:path*",
      },
    ];
  },
};

module.exports = nextConfig;
```

#### Cấu hình cho Webpack Dev Server (`webpack.config.js`)

```javascript
module.exports = {
  // ... các cấu hình khác ...
  devServer: {
    port: 3000,
    proxy: [
      {
        context: ["/api", "/static"],
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        secure: false,
      },
    ],
  },
};
```

> **Minh bạch hóa kiểm chứng**:
>
> - **ĐÃ XÁC MINH**: Cơ chế CORS, CSRF handshake và cấp phát cookie của Backend đã được kiểm thử trực tiếp trên live stack.
> - **UNVERIFIED**: Các tệp cấu hình proxy mẫu cho Vite, Next.js và Webpack nêu trên là hướng dẫn quy chuẩn cho phía Frontend; máy chủ kiểm thử hiện tại không khởi chạy một tiến trình Frontend Dev Server cụ thể.

---

## 7. Cấu trúc lỗi chuẩn (Error Envelope) & Bảng mã lỗi toàn diện

Toàn bộ các phản hồi lỗi từ hệ thống API đều tuân thủ cấu trúc đóng gói **Error Envelope**:

```json
{
  "code": "MSG-...",
  "message": "Thông điệp lỗi chi tiết bằng tiếng Việt.",
  "details": {}
}
```

- `code`: Mã định danh lỗi duy nhất (dạng `MSG-*` trích từ SRS v4.1 hoặc `PROP-*` từ bảng đề xuất mở rộng).
- `message`: Thông điệp tiếng Việt nguyên văn được quy định tại `apps/core/messages.py`.
- `details`: Đối tượng bổ sung chi tiết lỗi (ví dụ: các trường vi phạm validation, lỗi ràng buộc cơ sở dữ liệu).

### 7.1 Bảng tra cứu toàn bộ 27 Mã Lỗi của Phân hệ Auth và Parking

Bảng dưới đây trích dẫn nguyên văn 100% các chuỗi thông báo từ danh mục `apps/core/messages.py`:

| Mã lỗi (`code`) | HTTP Status | Thông điệp tiếng Việt nguyên văn (`apps/core/messages.py`) | Điều kiện kích hoạt | Hành động xử lý đề xuất cho UI Frontend |
|---|:---:|---|---|---|
| `PROP-4.1-P01` | 429 | `Quá nhiều lần đăng nhập không thành công, vui lòng thử lại sau.` | Vượt ngưỡng đăng nhập sai: 5 lần/cặp tài khoản+IP, 20 lần/tài khoản, 30 lần/IP. | Đọc header `Retry-After`, vô hiệu hóa form và hiển thị đồng hồ đếm ngược chờ thử lại. |
| `PROP-4.1-P02` | 200 | `Khởi tạo cookie CSRF thành công.` | Gọi `GET /api/v1/auth/csrf/` thành công. | Ghi nhận khởi tạo thành công, sẵn sàng cho các request đột biến. |
| `PROP-4.1-P03` | 200 | `Đăng xuất thành công.` | Gọi `POST /api/v1/auth/logout/` thành công. | Xóa sạch state người dùng trong Store (Redux/Pinia) và chuyển về màn hình đăng nhập. |
| `PROP-4.1-P06` | 403 | `Mã CSRF không hợp lệ hoặc bị thiếu.` | Request đột biến thiếu header `X-CSRFToken` hoặc token không khớp cookie `csrftoken`. | Tự động gọi lại `GET /api/v1/auth/csrf/` để lấy token mới, sau đó thử lại request. |
| `MSG-4.1-M02` | 401 | `Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu` | Sai tên đăng nhập/mật khẩu, tài khoản bị khóa (`is_active=False`), hoặc phiên hết hạn. | Đánh dấu viền đỏ trường đăng nhập/mật khẩu; nếu đang thao tác thì chuyển hướng về Login. |
| `MSG-4.1-M03` | 400 | `Xin nhập đầy đủ Tên đăng nhập và Mật khẩu` | Người dùng bỏ trống trường `identifier` hoặc `password` khi gửi form đăng nhập. | Hiển thị thông báo validation trực tiếp dưới các ô nhập liệu còn thiếu. |
| `MSG-4.2-M01` | 403 | `Thông báo lỗi hệ thống` *(hoặc `Bạn không có quyền thực hiện thao tác này.`)* | Tài khoản không đủ quyền (ví dụ vai trò `CUSTOMER` cố tình truy cập API bãi xe). | Hiển thị thông báo từ chối truy cập "403 Forbidden", ẩn các nút tính năng nội bộ. |
| `PROP-4.5.1-P01` | 400 | `Định dạng biển số xe không hợp lệ.` | Chuỗi biển số truyền vào rỗng hoặc sai quy cách biển số xe cơ giới. | Yêu cầu người dùng kiểm tra và nhập đúng biển số xe (ví dụ: `43K-860.50`). |
| `PROP-4.5.1-P02` | 400 | `Tệp hình ảnh biển số xe không được để trống.` | Không đính kèm tệp tin trong trường `image` khi gọi `POST /api/v1/parking/plate-scans/`. | Bắt buộc chọn tệp ảnh trước khi cho phép ấn nút "Quét biển số". |
| `PROP-4.5.1-P03` | 400 | `Kích thước tệp hình ảnh vượt quá giới hạn cho phép.` | Dung lượng tệp ảnh vượt quá giới hạn 5MB (`MAX_IMAGE_SIZE_MB`). | Báo lỗi dung lượng, hướng dẫn người dùng nén ảnh hoặc chụp ở độ phân giải phù hợp. |
| `PROP-4.5.1-P04` | 400 | `Định dạng tệp hình ảnh không được hỗ trợ.` | Tệp tải lên không phải định dạng JPEG, PNG hoặc WebP. | Báo lỗi định dạng, chỉ chấp nhận tệp có phần mở rộng `.jpg`, `.jpeg`, `.png`, `.webp`. |
| `PROP-4.5.1-P05` | 400 | `Tệp hình ảnh bị hỏng hoặc không thể xử lý an toàn.` | Tệp ảnh lỗi cấu trúc nhị phân hoặc kích thước giải nén vượt ngưỡng an toàn. | Báo tệp ảnh lỗi, yêu cầu chụp lại ảnh rõ nét hoặc kiểm tra lại file. |
| `PROP-4.5.1-P06` | 422 | `Không nhận diện được biển số xe từ hình ảnh đã cung cấp.` | Mô hình AI OCR chạy xong nhưng không phát hiện được biển số xe nào trong ảnh. | Hiển thị thông báo, mở hộp thoại cho phép nhân viên vận hành nhập biển số thủ công. |
| `PROP-4.5.1-P07` | 409 | `Biển số xe đã có phiên đỗ xe đang mở chưa hoàn thành.` | Xe này đã check-in vào bãi trước đó và chưa check-out. | Cảnh báo xe đang trong bãi, mở màn hình xem chi tiết phiên đỗ hiện tại. |
| `PROP-4.5.1-P08` | 409 | `Biển số xe nằm trong danh sách đen, không được phép vào bãi.` | Xe thuộc danh sách đen và không được phép vào bãi khi không có xác nhận của Quản lý. | Bật còi/cảnh báo an ninh màu đỏ, yêu cầu Quản lý xác nhận ghi đè (`override_blacklist`). |
| `PROP-4.5.1-P09` | 400 | `Yêu cầu chọn phương thức thanh toán hợp lệ khi cước phí đỗ xe lớn hơn 0.` | Xe vãng lai phát sinh cước phí đỗ xe nhưng không gửi trường `payment_method`. | Bắt buộc nhân viên chọn phương thức thanh toán (`CASH` hoặc `VIETQR`) trên màn hình. |
| `PROP-4.5.1-P10` | 409 | `Phiên đỗ xe này đã được kết thúc trước đó.` | Thực hiện check-out trên một phiên đỗ xe đã đóng. | Tải lại thông tin phiên, thông báo phiên xe đã hoàn tất thanh toán trước đó. |
| `PROP-4.5.1-P11` | 400 | `Yêu cầu cung cấp chính xác một trong hai tiêu chí: mã phiên đỗ xe hoặc biển số xe.` | Gửi cả 2 hoặc không gửi tiêu chí nào trong `session_code` và `license_plate`. | Kiểm tra lại logic form check-out, chỉ gửi duy nhất 1 trong 2 tiêu chí. |
| `PROP-4.5.1-P12` | 400 | `Cổng ra không hợp lệ hoặc không phải cổng có hướng ra (OUT).` | Chọn nhầm cổng vào (direction=`IN`) để thực hiện check-out xe ra. | Khóa danh sách chọn cổng, chỉ hiển thị các cổng có thuộc tính `direction="OUT"`. |
| `PROP-4.5.1-P13` | 400 | `Đường dẫn hình ảnh không hợp lệ hoặc tệp không tồn tại.` | Đường dẫn ảnh `entry_image_url` hoặc `exit_image_url` không hợp lệ. | Kiểm tra lại URL trả về từ API upload ảnh. |
| `PROP-4.5.1-P14` | 403 | `Nhân viên không có quyền ghi đè danh sách đen.` | Nhân viên vận hành cố tình bật cờ `override_blacklist=True`. | Chỉ kích hoạt và hiển thị tùy chọn ghi đè cho tài khoản có vai trò `MANAGER`. |
| `PROP-4.5.1-P15` | 503 | `Hệ thống nhận diện biển số xe đang quá tải, vui lòng thử lại sau.` | Hàng đợi OCR quá tải (hết semaphore xử lý đồng thời). | Đọc header `Retry-After` (thường là 3s), hiển thị thông báo "Hệ thống bận, đang thử lại...". |
| `PROP-4.5.1-P16` | 400 | `Biển số xe có định dạng chưa được định nghĩa trong danh mục quy chuẩn hoặc thuộc nhóm cần xác minh thủ công.` | Mẫu biển số lạ hoặc không khớp quy chuẩn quốc gia. | Chuyển sang luồng rà soát thủ công (`NEEDS_REVIEW`). |
| `PROP-4.5.2-P01` | 409 | `Vị trí này đang bảo trì.` | Chỉ định ô đỗ xe đang ở trạng thái bảo trì (`MAINTENANCE`). | Hiển thị ô đỗ màu xám trên sơ đồ bãi xe, yêu cầu chọn vị trí đỗ khác. |
| `MSG-4.5.1-M01` | 404 | `Không tìm thấy dữ liệu trùng khớp` | Không tìm thấy xe trong `vehicle-lookup` hoặc phiên mở trong checkout. | Báo không tìm thấy xe, gợi ý tạo lượt đỗ mới hoặc kiểm tra lại biển số. |
| `MSG-4.4.1-M01` | 404 | `Không tìm thấy dữ liệu` | Không tìm thấy chi tiết phiên đỗ xe theo ID được yêu cầu. | Hiển thị màn hình 404 hoặc quay về danh sách phiên đỗ xe. |
| `PROP-GEN-P01` | 400 | `Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu` | Lỗi kiểm tra dữ liệu đầu vào (ví dụ từ khóa tìm kiếm `< 2` ký tự). | Đọc đối tượng `details` để hiển thị lỗi chi tiết cạnh từng ô nhập liệu. |

### 7.2 Cấu trúc phân trang chuẩn (Pagination Envelope)

Các endpoint trả về danh sách phân trang (như `/api/v1/parking/sessions/` và `/api/v1/parking/vehicle-search/`) đều áp dụng cấu trúc `StandardResultsSetPagination`:

```json
{
  "count": 15,
  "total_pages": 8,
  "current_page": 1,
  "page_size": 2,
  "next": "http://127.0.0.1:8000/api/v1/parking/sessions/?page=2&page_size=2&status=open",
  "previous": null,
  "results": []
}
```

- `count`: Tổng số bản ghi thỏa mãn điều kiện lọc.
- `total_pages`: Tổng số trang.
- `current_page`: Trang hiện tại.
- `page_size`: Số bản ghi trên mỗi trang (mặc định 20, tối đa 50).
- `next` / `previous`: URL lấy trang tiếp theo hoặc trang trước đó (`null` nếu đang ở trang cuối/đầu).

### 7.3 Cơ chế giới hạn tần suất (Rate Limiting)

Hệ thống áp dụng giới hạn tần suất trên endpoint đăng nhập `POST /api/v1/auth/login/` (tối đa 5 lần đăng nhập sai liên tiếp cho mỗi cặp tài khoản + IP trong cửa sổ 900 giây). Khi vượt ngưỡng ở lần thứ 6, API trả về HTTP `429 Too Many Requests` kèm mã `PROP-4.1-P01` và header `Retry-After`:

```http
POST /api/v1/auth/login/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: application/json

{"identifier": "hoang.dinh.khang@example.com", "password": "[MASKED]", "remember": false}

HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 900

{
  "code": "PROP-4.1-P01",
  "message": "Quá nhiều lần đăng nhập không thành công, vui lòng thử lại sau.",
  "details": {}
}
```

Frontend cần đọc giá trị số nguyên trong header `Retry-After` (đơn vị: giây), khóa nút đăng nhập và hiển thị đồng hồ đếm ngược thông báo thời gian chờ cho người dùng.

> **Lưu ý về môi trường đa tiến trình (Multi-worker Gunicorn)**: Khi máy chủ chạy nhiều tiến trình worker (như trong Docker Compose với 4 Gunicorn workers sử dụng `LocMemCache` độc lập trên mỗi worker theo `docker/gunicorn.conf.py`), bộ đếm số lần đăng nhập sai được duy trì riêng rẽ trong bộ nhớ của từng tiến trình worker. Do các yêu cầu từ client được bộ lập lịch socket phân phối lần lượt tới các worker khác nhau, lần đăng nhập nhận phản hồi HTTP `429` có thể xuất hiện muộn hơn lần thứ 6 (thực nghiệm probe 40 lần đăng nhập sai liên tiếp với cùng tài khoản và IP trên stack 4-worker ghi nhận lần đầu tiên trả về HTTP `429` tại lượt thứ 9, với tổng phân bố 10 lần HTTP `401` và 30 lần HTTP `429`).

---

## 8. Chi tiết toàn bộ 8 Endpoints Đỗ Xe (Parking Endpoints)

Tất cả các endpoint thuộc phân hệ đỗ xe đều yêu cầu quyền xác thực của tài khoản nhân viên hoặc quản lý (`IsEmployeeOrManager`). Tài khoản khách hàng (`CUSTOMER`) truy cập sẽ nhận lỗi `403 Forbidden` (`MSG-4.2-M01`):

```http
GET /api/v1/parking/gates/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

HTTP/1.1 403 Forbidden
Content-Type: application/json

{
  "code": "MSG-4.2-M01",
  "message": "Bạn không có quyền thực hiện thao tác này.",
  "details": {
    "detail": "Bạn không có quyền thực hiện thao tác này."
  }
}
```

### 8.1 Lấy danh sách cổng barrier (`GET /api/v1/parking/gates/`)

- **Mục đích**: Lấy danh sách các cổng kiểm soát barrier của bãi xe để hiển thị lên dropdown chọn cổng vào/ra.
- **Quyền yêu cầu**: `EMPLOYEE` hoặc `MANAGER`.
- **Query Parameters**:
  - `direction` (tùy chọn): Lọc theo hướng cổng (`IN` hoặc `OUT`).
  - `is_active` (tùy chọn): Lọc cổng đang hoạt động (`true` hoặc `false`).
- **Ví dụ thực tế từ Live Stack**:

  ```http
  GET /api/v1/parking/gates/?direction=IN HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  [
    {
      "id": 1,
      "lot_id": 1,
      "code": "IN_01",
      "name": "Cổng vào 1",
      "direction": "IN",
      "camera_status": "ONLINE",
      "is_auto_scan": true,
      "is_active": true
    },
    {
      "id": 2,
      "lot_id": 1,
      "code": "IN_02",
      "name": "Cổng vào 2",
      "direction": "IN",
      "camera_status": "ONLINE",
      "is_auto_scan": true,
      "is_active": true
    }
  ]
  ```

### 8.2 Quét nhận diện biển số xe (`POST /api/v1/parking/plate-scans/`)

- **Mục đích**: Nhận diện biển số xe từ ảnh chụp camera barrier hoặc tệp tải lên qua form, tự động áp dụng sửa lỗi ngữ cảnh vị trí (Position-Aware Corrections), đánh giá chính sách duyệt `AUTO` / `NEEDS_REVIEW`, tra cứu phương tiện đã đăng ký và gợi ý biển số gần giống (`suggestions`).
- **Quyền yêu cầu**: `EMPLOYEE` hoặc `MANAGER`.
- **Định dạng gửi**: `multipart/form-data` (kèm header `X-CSRFToken`).
- **Các trường dữ liệu Form**:
  - `image` (bắt buộc): Tệp hình ảnh biển số (JPEG, PNG, WebP; dung lượng tối đa 5MB).
  - `gate_id` (tùy chọn): ID cổng barrier gửi ảnh.

#### Ví dụ 1: Phản hồi thành công tự động duyệt (`review_status: "AUTO"`)

Khi độ tin cậy AI cao và khớp quy chuẩn biển số Việt Nam (`43K-860.50` thuộc khách hàng `Trịnh Xuân Trường`):

```http
POST /api/v1/parking/plate-scans/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW

[Multipart Form Data: image=car_43k86050.jpg (image/jpeg), gate_id=1]

HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: 53b70530673b41b8a7a4d75de93bf5e2

{
  "plate_raw": "43K-860.50",
  "plate_final": "43K86050",
  "candidates": [
    {
      "plate_text": "43K-860.50",
      "plate_normalized": "43K86050",
      "confidence": 98.5,
      "char_confidences": [
        98.5,
        98.5,
        98.5,
        98.5,
        98.5,
        98.5,
        98.5,
        98.5
      ],
      "min_char_confidence": 98.5,
      "bounding_box": {
        "x1": 50,
        "y1": 50,
        "x2": 350,
        "y2": 150
      }
    }
  ],
  "best_candidate": {
    "plate_text": "43K86050",
    "plate_normalized": "43K86050",
    "confidence": 98.5,
    "char_confidences": [
      98.5,
      98.5,
      98.5,
      98.5,
      98.5,
      98.5,
      98.5,
      98.5
    ],
    "min_char_confidence": 98.5,
    "bounding_box": {
      "x1": 50,
      "y1": 50,
      "x2": 350,
      "y2": 150
    }
  },
  "image_url": "/media/parking_scans/2026/10/22/3b571536e9084d9f8bc679f027904cee.jpg",
  "vehicle_lookup": {
    "vehicle": {
      "id": 1,
      "code": "XE0001",
      "license_plate": "43K-860.50",
      "license_plate_norm": "43K86050",
      "model_name": "Vios 1.5G",
      "brand": "Toyota",
      "color": "Trắng",
      "vehicle_type": "Ô tô",
      "vehicle_type_code": "CAR"
    },
    "customer": {
      "id": 16,
      "code": "KH0001",
      "full_name": "Trịnh Xuân Trường",
      "phone": "0868851325",
      "is_anonymized": false
    },
    "parking_position": {
      "slot_id": 1,
      "slot_code": "A-01",
      "zone_code": "A",
      "floor_code": "B1",
      "floor_name": "Tầng B1",
      "display_text": "Tầng B1 - Zone A - A-01"
    },
    "active_ticket": {
      "id": 1,
      "code": "VT0001",
      "ticket_type_name": "Vé tháng",
      "price": "500000.00",
      "effective_from": "2026-03-31T17:00:00+00:00",
      "effective_to": "2026-11-30T17:00:00+00:00",
      "status": "ACTIVE"
    },
    "open_session": {
      "id": 37,
      "session_code": "#PK-20261017-037",
      "entry_time": "2026-10-17T00:20:00+00:00",
      "entry_gate_name": "Cổng vào 1",
      "entry_image_url": "/media/gates/pk-20261017-037_in.jpg",
      "recognition_source": "AI",
      "ai_confidence": 97.1,
      "review_status": "MATCHED"
    },
    "is_blacklisted": false
  },
  "is_blacklisted": false,
  "open_session": {
    "id": 37,
    "session_code": "#PK-20261017-037",
    "entry_time": "2026-10-17T00:20:00+00:00",
    "entry_gate_name": "Cổng vào 1",
    "entry_image_url": "/media/gates/pk-20261017-037_in.jpg",
    "recognition_source": "AI",
    "ai_confidence": 97.1,
    "review_status": "MATCHED"
  },
  "engine_name": "dummy",
  "latency_ms": 1.0,
  "review_status": "AUTO",
  "review_reasons": [],
  "corrections": [],
  "suggestions": []
}
```

#### Ví dụ 2: Phản hồi yêu cầu nhân viên rà soát (`review_status: "NEEDS_REVIEW"`)

Khi ảnh có độ tin cậy thấp hoặc đã áp dụng sửa ký tự theo vị trí (`43K-86O.59` được sửa ký tự `O` tại vị trí 5 thành `0` -> `43K86059` và gợi ý biển số đã đăng ký `43K-860.50`):

```http
POST /api/v1/parking/plate-scans/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW

[Multipart Form Data: image=car_review.jpg (image/jpeg), gate_id=1]

HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: d50c117a75c14f67a35af4e14c93ffc5

{
  "plate_raw": "43K-86O.59",
  "plate_final": "43K86059",
  "candidates": [
    {
      "plate_text": "43K-86O.59",
      "plate_normalized": "43K86O59",
      "confidence": 78.0,
      "char_confidences": [
        78.0,
        78.0,
        78.0,
        78.0,
        78.0,
        78.0,
        78.0,
        78.0
      ],
      "min_char_confidence": 78.0,
      "bounding_box": {
        "x1": 50,
        "y1": 50,
        "x2": 350,
        "y2": 150
      }
    }
  ],
  "best_candidate": {
    "plate_text": "43K86059",
    "plate_normalized": "43K86059",
    "confidence": 78.0,
    "char_confidences": [
      78.0,
      78.0,
      78.0,
      78.0,
      78.0,
      78.0,
      78.0,
      78.0
    ],
    "min_char_confidence": 78.0,
    "bounding_box": {
      "x1": 50,
      "y1": 50,
      "x2": 350,
      "y2": 150
    }
  },
  "image_url": "/media/parking_scans/2026/10/22/a98af4bc71a941d2a79cac484d323ab9.jpg",
  "vehicle_lookup": null,
  "is_blacklisted": false,
  "open_session": null,
  "engine_name": "dummy",
  "latency_ms": 1.0,
  "review_status": "NEEDS_REVIEW",
  "review_reasons": [
    "LOW_CHAR_CONFIDENCE",
    "POSITION_CORRECTED"
  ],
  "corrections": [
    {
      "position": 5,
      "from": "O",
      "to": "0",
      "rule": "number_group_digit_fix_pos_5",
      "reason": "Positional grammar requires digit at position 5; corrected 'O' to '0'",
      "original_char": "O",
      "corrected_char": "0"
    }
  ],
  "suggestions": [
    "43K-860.50"
  ]
}
```

#### Ví dụ 3: Không phát hiện được biển số trong ảnh (HTTP `422 Unprocessable Content`)

```http
POST /api/v1/parking/plate-scans/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW

[Multipart Form Data: image=empty_scan.jpg (image/jpeg), gate_id=1]

HTTP/1.1 422 Unprocessable Content
Content-Type: application/json
X-Request-ID: bb89b602b5694d7fb7c66f7158faf1ec

{
  "code": "PROP-4.5.1-P06",
  "message": "Không nhận diện được biển số xe từ hình ảnh đã cung cấp.",
  "details": {}
}
```

#### Bảng 9 Mã lý do duyệt (`ReviewReasonCode` trong `apps/parking/enums.py`)

| Mã lý do (`review_reasons`) | Ý nghĩa kỹ thuật | Hành động đề xuất cho UI |
|---|---|---|
| `MODEL_DISAGREEMENT` | Hai mô hình AI OCR cho ra kết quả biển số khác nhau. | Hiển thị cả 2 kết quả để nhân viên chọn kết quả đúng. |
| `LOW_CHAR_CONFIDENCE` | Tồn tại ký tự có độ tin cậy dưới ngưỡng (dưới 90.0%). | Đánh dấu màu vàng các ký tự có độ tin cậy thấp trên màn hình. |
| `INVALID_FORMAT` | Chuỗi ký tự nhận diện không khớp quy chuẩn biển số Việt Nam. | Yêu cầu nhân viên kiểm tra lại cấu trúc biển số. |
| `UNKNOWN_PLATE_PATTERN` | Định dạng biển số lạ chưa định nghĩa trong danh mục quy chuẩn. | Mở ô cho nhân viên nhập tay xác nhận. |
| `NO_DETECTION_RETRY` | Bộ nhận diện detector ban đầu không bắt được, phải crop fallback. | Cảnh báo góc chụp camera có thể bị lệch. |
| `LOW_DETECTION_CONFIDENCE` | Hộp bao biển số (bounding box) có độ tin cậy `< 80.0%`. | Cảnh báo xe chưa vào đúng vị trí nhận diện tối ưu. |
| `IRREGULAR_ASPECT_RATIO` | Tỷ lệ dài/rộng của biển số bất thường (`< 1.3` hoặc `> 6.0`). | Cảnh báo biển số chụp quá nghiêng. |
| `LOW_IMAGE_SHARPNESS` | Độ sắc nét của ảnh thấp (phương sai Laplacian `< 30.0`, ảnh mờ). | Thông báo ảnh mờ do xe di chuyển nhanh hoặc trời mưa. |
| `POSITION_CORRECTED` | Đã áp dụng quy tắc sửa ký tự theo vị trí ngữ pháp (ví dụ chữ `O` thành số `0`). | Hiển thị danh sách `corrections` để nhân viên xác nhận sửa đổi. |

#### Hướng dẫn xử lý trên giao diện cho `NEEDS_REVIEW`

Khi `review_status === "NEEDS_REVIEW"`:

1. **Hiển thị Badge cảnh báo**: Đặt nhãn màu vàng/cam "Cần xác minh" cạnh biển số xe.
2. **Cho phép chỉnh sửa**: Mở ô nhập liệu cho phép nhân viên trực cổng sửa lại biển số theo hình ảnh thực tế đang hiển thị trên màn hình.
3. **Hiển thị gợi ý**: Render danh sách `suggestions` dưới dạng các nút bấm nhanh để nhân viên chọn một chạm.
4. **Không tự động mở barrier**: Tuyệt đối không tự động kích hoạt barrier mở cho đến khi nhân viên nhấn nút "Xác nhận Check-in".

### 8.3 Tra cứu thông tin xe theo biển số (`GET /api/v1/parking/vehicle-lookup/`)

- **Mục đích**: Tra cứu tức thời thông tin phương tiện, chủ xe, vị trí đỗ cố định, vé tháng đang hoạt động, phiên đỗ đang mở và trạng thái blacklist khi xe tiến vào cổng.
- **Quyền yêu cầu**: `EMPLOYEE` hoặc `MANAGER`.
- **Query Parameter**: `license_plate` (chuỗi biển số xe, bắt buộc).
- **Ví dụ thực tế khi tìm thấy phương tiện đã đăng ký (`43K-860.50`)**:

  ```http
  GET /api/v1/parking/vehicle-lookup/?license_plate=43K-860.50 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "vehicle": {
      "id": 1,
      "code": "XE0001",
      "license_plate": "43K-860.50",
      "license_plate_norm": "43K86050",
      "model_name": "Vios 1.5G",
      "brand": "Toyota",
      "color": "Trắng",
      "vehicle_type": "Ô tô",
      "vehicle_type_code": "CAR"
    },
    "customer": {
      "id": 16,
      "code": "KH0001",
      "full_name": "Trịnh Xuân Trường",
      "phone": "0868851325",
      "is_anonymized": false
    },
    "parking_position": {
      "slot_id": 1,
      "slot_code": "A-01",
      "zone_code": "A",
      "floor_code": "B1",
      "floor_name": "Tầng B1",
      "display_text": "Tầng B1 - Zone A - A-01"
    },
    "active_ticket": {
      "id": 1,
      "code": "VT0001",
      "ticket_type_name": "Vé tháng",
      "price": "500000.00",
      "effective_from": "2026-03-31T17:00:00+00:00",
      "effective_to": "2026-11-30T17:00:00+00:00",
      "status": "ACTIVE"
    },
    "open_session": {
      "id": 37,
      "session_code": "#PK-20261017-037",
      "entry_time": "2026-10-17T00:20:00+00:00",
      "entry_gate_name": "Cổng vào 1",
      "entry_image_url": "/media/gates/pk-20261017-037_in.jpg",
      "recognition_source": "AI",
      "ai_confidence": 97.1,
      "review_status": "MATCHED"
    },
    "is_blacklisted": false
  }
  ```

- **Ví dụ thực tế khi không tìm thấy** (HTTP `404 Not Found` kèm mã `MSG-4.5.1-M01`):

  ```http
  GET /api/v1/parking/vehicle-lookup/?license_plate=99Z-999.99 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 404 Not Found
  Content-Type: application/json

  {
    "code": "MSG-4.5.1-M01",
    "message": "Không tìm thấy dữ liệu trùng khớp",
    "details": {}
  }
  ```

### 8.4 Tìm kiếm xe nâng cao đa tiêu chí (`GET /api/v1/parking/vehicle-search/`)

- **Mục đích**: Hỗ trợ nhân viên tìm xe cho khách quên vị trí đỗ hoặc tra cứu thông tin phương tiện theo nhiều tiêu chí.
- **Quyền yêu cầu**: `EMPLOYEE` hoặc `MANAGER`.
- **Query Parameters**:
  - `q` (tùy chọn): Từ khóa tìm kiếm hợp nhất (tự động so khớp họ tên, số điện thoại hoặc biển số xe; tối thiểu 2 ký tự).
  - `customer_name` (tùy chọn): Lọc theo tên khách hàng.
  - `phone` (tùy chọn): Lọc theo số điện thoại (hỗ trợ cả định dạng `+84` và `0`).
  - `license_plate` (tùy chọn): Lọc theo biển số xe.
  - `page` / `page_size`: Phân trang.
- **Ví dụ 1: Tìm kiếm khớp kết quả (`?q=43K-860`)**:

  ```http
  GET /api/v1/parking/vehicle-search/?q=43K-860 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "count": 1,
    "total_pages": 1,
    "current_page": 1,
    "page_size": 20,
    "next": null,
    "previous": null,
    "results": [
      {
        "vehicle": {
          "id": 1,
          "code": "XE0001",
          "license_plate": "43K-860.50",
          "license_plate_norm": "43K86050",
          "model_name": "Vios 1.5G",
          "brand": "Toyota",
          "color": "Trắng",
          "vehicle_type": "Ô tô",
          "vehicle_type_code": "CAR"
        },
        "customer": {
          "id": 16,
          "code": "KH0001",
          "full_name": "Trịnh Xuân Trường",
          "phone": "0868851325",
          "is_anonymized": false
        },
        "parking_position": {
          "slot_id": 1,
          "slot_code": "A-01",
          "zone_code": "A",
          "floor_code": "B1",
          "floor_name": "Tầng B1",
          "display_text": "Tầng B1 - Zone A - A-01"
        },
        "active_ticket": {
          "id": 1,
          "code": "VT0001",
          "ticket_type_name": "Vé tháng",
          "price": "500000.00",
          "effective_from": "2026-03-31T17:00:00+00:00",
          "effective_to": "2026-11-30T17:00:00+00:00",
          "status": "ACTIVE"
        },
        "open_session": {
          "id": 37,
          "session_code": "#PK-20261017-037",
          "entry_time": "2026-10-17T00:20:00+00:00",
          "entry_gate_name": "Cổng vào 1",
          "entry_image_url": "/media/gates/pk-20261017-037_in.jpg",
          "recognition_source": "AI",
          "ai_confidence": 97.1,
          "review_status": "MATCHED"
        },
        "is_blacklisted": false,
        "currently_parked": true
      }
    ],
    "message": null
  }
  ```

- **Ví dụ 2: Không có kết quả khớp (`200 OK` kèm `message`)**:

  ```http
  GET /api/v1/parking/vehicle-search/?q=99Z-999 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "count": 0,
    "total_pages": 0,
    "current_page": 1,
    "page_size": 20,
    "next": null,
    "previous": null,
    "results": [],
    "message": "Không tìm thấy dữ liệu trùng khớp"
  }
  ```

- **Ví dụ 3: Từ khóa ngắn hơn 2 ký tự (`400 Bad Request` kèm `PROP-GEN-P01`)**:

  ```http
  GET /api/v1/parking/vehicle-search/?q=a HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 400 Bad Request
  Content-Type: application/json

  {
    "code": "PROP-GEN-P01",
    "message": "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu",
    "details": {
      "q": [
        "Từ khóa tìm kiếm phải có độ dài tối thiểu 2 ký tự sau khi loại bỏ khoảng trắng."
      ]
    }
  }
  ```

### 8.5 Check-in phương tiện vào bãi (`POST /api/v1/parking/sessions/check-in/`)

- **Mục đích**: Ghi nhận lượt xe vào bãi tại barrier cổng vào, sinh mã phiên `#PK-YYYYMMDD-NNN`.
- **Quyền yêu cầu**: `EMPLOYEE` hoặc `MANAGER` (cờ `override_blacklist=true` chỉ dành cho `MANAGER`).
- **Headers bắt buộc**: `X-CSRFToken`.
- **Các trường Body**: `license_plate` (bắt buộc), `entry_gate_id` (tùy chọn), `slot_id` (tùy chọn), `entry_image_url` (tùy chọn), `recognition_source` (`AI` hoặc `MANUAL`), `ai_confidence` (0–100), `review_status` (`AUTO` hoặc `NEEDS_REVIEW`), `override_blacklist` (`false` mặc định), `notes` (tùy chọn).
- **Ví dụ thực tế từ Live Stack (HTTP `201 Created`)**:

  ```http
  POST /api/v1/parking/sessions/check-in/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]
  Content-Type: application/json

  {"license_plate": "29A-999.99", "entry_gate_id": 1, "recognition_source": "AI", "ai_confidence": 98.2, "slot_id": 6}

  HTTP/1.1 201 Created
  Content-Type: application/json
  X-Request-ID: 4ebeaa8918d84ad8a3673bf8b3d629ac

  {
    "session": {
      "id": 51,
      "session_code": "#PK-20261022-001",
      "vehicle_id": null,
      "slot_id": 6,
      "slot_display": "Tầng B1 - Zone A - A-06",
      "ticket_id": null,
      "entry_gate_id": 1,
      "entry_gate_name": "Cổng vào 1",
      "exit_gate_id": null,
      "exit_gate_name": null,
      "license_plate": "29A-999.99",
      "license_plate_norm": "29A99999",
      "ai_confidence": "98.20",
      "recognition_source": "AI",
      "review_status": "AUTO",
      "fee_amount": "0.00",
      "entry_time": "2026-10-22T15:00:27.280374Z",
      "exit_time": null,
      "duration_seconds": 0,
      "duration_text": "0 giây",
      "entry_image_url": null,
      "exit_image_url": null,
      "entry_handled_by": 5,
      "entry_handled_by_name": "Lương Thị Mai Phương",
      "exit_handled_by": null,
      "exit_handled_by_name": null,
      "notes": null,
      "created_at": "2026-10-22T15:00:27.293351Z"
    },
    "vehicle_lookup": null
  }
  ```

### 8.6 Check-out phương tiện rời bãi (`POST /api/v1/parking/sessions/check-out/`)

- **Mục đích**: Kết thúc lượt đỗ xe tại cổng ra, tự động tính cước phí (0đ nếu có vé tháng `ACTIVE`, ngược lại tính theo block giờ: 10.000đ/giờ), ghi nhận hóa đơn thanh toán `payment`.
- **Quyền yêu cầu**: `EMPLOYEE` hoặc `MANAGER`.
- **Headers bắt buộc**: `X-CSRFToken`.
- **Quy tắc đầu vào**:
  - Cung cấp chính xác **1 trong 2 tiêu chí**: `session_code` HOẶC `license_plate`.
  - Cổng ra `exit_gate_id` bắt buộc phải là cổng có thuộc tính `direction="OUT"` (nếu chọn cổng `IN` sẽ bị từ chối `PROP-4.5.1-P12`).
  - Nếu xe vãng lai phát sinh cước phí `> 0`, bắt buộc cung cấp `payment_method` (`CASH` hoặc `VIETQR`).
- **Ví dụ thực tế từ Live Stack (HTTP `200 OK`)**:

  ```http
  POST /api/v1/parking/sessions/check-out/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]
  X-CSRFToken: [MASKED]
  Content-Type: application/json

  {"session_code": "#PK-20261022-001", "exit_gate_id": 3, "payment_method": "CASH"}

  HTTP/1.1 200 OK
  Content-Type: application/json
  X-Request-ID: 090ff478119748eeabe0232654092df4

  {
    "session": {
      "id": 51,
      "session_code": "#PK-20261022-001",
      "vehicle_id": null,
      "slot_id": 6,
      "slot_display": "Tầng B1 - Zone A - A-06",
      "ticket_id": null,
      "entry_gate_id": 1,
      "entry_gate_name": "Cổng vào 1",
      "exit_gate_id": 3,
      "exit_gate_name": "Cổng ra 1",
      "license_plate": "29A-999.99",
      "license_plate_norm": "29A99999",
      "ai_confidence": "98.20",
      "recognition_source": "AI",
      "review_status": "AUTO",
      "fee_amount": "10000.00",
      "entry_time": "2026-10-22T15:00:27.280374Z",
      "exit_time": "2026-10-22T15:00:27.362731Z",
      "duration_seconds": 0,
      "duration_text": "0 giây",
      "entry_image_url": null,
      "exit_image_url": null,
      "entry_handled_by": 5,
      "entry_handled_by_name": "Lương Thị Mai Phương",
      "exit_handled_by": 5,
      "exit_handled_by_name": "Lương Thị Mai Phương",
      "notes": null,
      "created_at": "2026-10-22T15:00:27.293351Z"
    },
    "payment": {
      "id": 54,
      "code": "PAY-SES-PK-20261022-001",
      "amount": "10000.00",
      "method": "CASH",
      "status": "PAID",
      "paid_at": "2026-10-22T15:00:27.362731Z"
    },
    "vehicle_lookup": null
  }
  ```

### 8.7 Danh sách phiên đỗ xe (`GET /api/v1/parking/sessions/`)

- **Mục đích**: Hiển thị bảng nhật ký phiên xe ra vào phục vụ quản lý và thống kê.
- **Quyền yêu cầu**: `EMPLOYEE` hoặc `MANAGER`.
- **Query Parameters**: `session_code`, `license_plate`, `status` (`open` hoặc `closed`), `entry_time_from`, `entry_time_to`, `page`, `page_size`.
- **Ví dụ thực tế từ Live Stack**:

  ```http
  GET /api/v1/parking/sessions/?status=open&page=1&page_size=2 HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "count": 15,
    "total_pages": 8,
    "current_page": 1,
    "page_size": 2,
    "next": "http://127.0.0.1:8000/api/v1/parking/sessions/?page=2&page_size=2&status=open",
    "previous": null,
    "results": [
      {
        "id": 51,
        "session_code": "#PK-20261022-001",
        "license_plate": "29A-999.99",
        "license_plate_norm": "29A99999",
        "entry_time": "2026-10-22T15:00:27.280374Z",
        "exit_time": null,
        "duration_seconds": 0,
        "duration_text": "0 giây",
        "fee_amount": "0.00",
        "entry_image_url": null,
        "exit_image_url": null,
        "entry_gate_name": "Cổng vào 1",
        "exit_gate_name": null,
        "ai_confidence": "98.20",
        "recognition_source": "AI",
        "review_status": "AUTO",
        "vehicle_model": null,
        "vehicle_brand": null,
        "customer_name": null,
        "customer_phone": null,
        "slot_code": "A-06"
      },
      {
        "id": 50,
        "session_code": "#PK-20261017-050",
        "license_plate": "30C-468.58",
        "license_plate_norm": "30C46858",
        "entry_time": "2026-10-17T05:28:00Z",
        "exit_time": null,
        "duration_seconds": 466347,
        "duration_text": "5 ngày 9 giờ 32 phút",
        "fee_amount": "30000.00",
        "entry_image_url": "/media/gates/pk-20261017-050_in.jpg",
        "exit_image_url": null,
        "entry_gate_name": "Cổng vào 2",
        "exit_gate_name": null,
        "ai_confidence": "97.30",
        "recognition_source": "AI",
        "review_status": "MATCHED",
        "vehicle_model": null,
        "vehicle_brand": null,
        "customer_name": null,
        "customer_phone": null,
        "slot_code": "C-01"
      }
    ]
  }
  ```

### 8.8 Chi tiết một phiên đỗ xe (`GET /api/v1/parking/sessions/{id}/`)

- **Mục đích**: Xem toàn bộ thông tin chi tiết của phiên đỗ xe theo ID số nguyên (thời gian vào/ra, ảnh chụp barrier, nhân viên xử lý, vị trí đỗ, cước phí).
- **Quyền yêu cầu**: `EMPLOYEE` hoặc `MANAGER`.
- **Ví dụ thực tế khi tìm thấy (`GET /api/v1/parking/sessions/51/`)**:

  ```http
  GET /api/v1/parking/sessions/51/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 200 OK
  Content-Type: application/json

  {
    "id": 51,
    "session_code": "#PK-20261022-001",
    "vehicle_id": null,
    "slot_id": 6,
    "slot_display": "Tầng B1 - Zone A - A-06",
    "ticket_id": null,
    "entry_gate_id": 1,
    "entry_gate_name": "Cổng vào 1",
    "exit_gate_id": null,
    "exit_gate_name": null,
    "license_plate": "29A-999.99",
    "license_plate_norm": "29A99999",
    "ai_confidence": "98.20",
    "recognition_source": "AI",
    "review_status": "AUTO",
    "fee_amount": "0.00",
    "entry_time": "2026-10-22T15:00:27.280374Z",
    "exit_time": null,
    "duration_seconds": 0,
    "duration_text": "0 giây",
    "entry_image_url": null,
    "exit_image_url": null,
    "entry_handled_by": 5,
    "entry_handled_by_name": "Lương Thị Mai Phương",
    "exit_handled_by": null,
    "exit_handled_by_name": null,
    "notes": null,
    "created_at": "2026-10-22T15:00:27.293351Z"
  }
  ```

- **Ví dụ thực tế khi không tìm thấy (`404 Not Found` kèm `MSG-4.4.1-M01`)**:

  ```http
  GET /api/v1/parking/sessions/999999/ HTTP/1.1
  Host: 127.0.0.1:8000
  Accept: application/json
  Cookie: csrftoken=[MASKED]; sessionid=[MASKED]

  HTTP/1.1 404 Not Found
  Content-Type: application/json

  {
    "code": "MSG-4.4.1-M01",
    "message": "Không tìm thấy dữ liệu",
    "details": {}
  }
  ```

---

## 9. Tự động sinh Typed Client hoặc Postman Collection

### 9.1 Tự động sinh TypeScript Types với `openapi-typescript`

Frontend có thể tự động trích xuất toàn bộ kiểu dữ liệu Type-Safe (TypeScript interfaces) cho mọi Request, Response và Schema trực tiếp từ endpoint đặc tả `/api/schema/`:

```bash
# Chạy trực tiếp đối với máy chủ đang chạy hoặc file schema.yaml đã tải về
npx --yes openapi-typescript@7.13.0 http://127.0.0.1:8000/api/schema/ -o src/types/api.d.ts
```

#### Kết quả trích xuất thực tế (`openapi-typescript 7.13.0` — 1,553 dòng)

```text
$ npx --yes openapi-typescript@7.13.0 schema.yaml -o src/types/api.d.ts
Exit code: 0
✨ openapi-typescript 7.13.0
🚀 schema.yaml → src/types/api.d.ts [61.2ms]
```

Đoạn trích nguyên văn từ tệp `src/types/api.d.ts` được sinh ra:

```typescript
/**
 * This file was auto-generated by openapi-typescript.
 * Do not make direct changes to the file.
 */

export interface paths {
    "/api/health/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Kiểm tra trạng thái sẵn sàng của hệ thống
         * @description Kiểm tra trạng thái sẵn sàng của hệ thống, kết nối cơ sở dữ liệu PostgreSQL và mô hình OCR.
         *     Cả hai đường dẫn `/api/health/` (hạ tầng hệ thống) và `/api/v1/health/` (API v1) đều được cung cấp có chủ đích để tương thích với các bộ kiểm tra sức khỏe hạ tầng (Docker/K8s/reverse proxy) và định tuyến phiên bản của frontend.
         */
        get: operations["health_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/csrf/": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Khởi tạo CSRF cookie
         * @description Endpoint công khai khởi tạo và trả về cookie csrftoken phục vụ cơ chế bảo vệ CSRF hai lớp của SPA.
         */
        get: operations["v1_auth_csrf_retrieve"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
```

### 9.2 Nhập vào Postman (Postman Collection Import)

1. Mở Postman, chọn **Import** ở góc trên bên trái.
2. Chọn tab **Link** và dán địa chỉ URL: `http://127.0.0.1:8000/api/schema/`.
3. Nhấn **Continue** và chọn **Import as API with a Collection**.
4. Toàn bộ danh mục API và ví dụ request/response sẽ được tự động đồng bộ vào Postman.

---

## 10. Bảng xử lý sự cố thường gặp & Các tính năng chưa phát triển

### 10.1 Bảng xử lý 8 sự cố thường gặp (Troubleshooting Table)

| STT | Triệu chứng sự cố | Nguyên nhân gốc rễ (Root Cause) | Giải pháp khắc phục triệt để |
|:---:|---|---|---|
| 1 | **Swagger UI / ReDoc trắng trang (Blank Page)** | Trong môi trường `DEBUG=True`, Gunicorn không tự động phục vụ static assets của `drf-spectacular-sidecar` nếu thiếu route `staticfiles_urlpatterns`. | Đảm bảo `config/urls.py` đã gắn `staticfiles_urlpatterns()` khi `settings.DEBUG` là True. Kiểm tra console trình duyệt để xác nhận các file `.css` và `.js` không bị mã lỗi 404. |
| 2 | **Lỗi HTTP 403 `PROP-4.1-P06`** (`Mã CSRF không hợp lệ hoặc bị thiếu`) | Request đột biến (`POST`, `PUT`, `DELETE`) không gửi kèm header `X-CSRFToken` hoặc token không khớp với cookie `csrftoken`. | Gọi `GET /api/v1/auth/csrf/` trước khi gửi request; đọc giá trị từ cookie `csrftoken` và gán vào request header `X-CSRFToken`. Nếu chạy cross-origin, sử dụng Dev Proxy. |
| 3 | **Lỗi HTTP 401 `MSG-4.1-M02`** (`Xin vui lòng nhập lại Tên đăng nhập...`) | Phiên làm việc đã hết hạn, hoặc cookie `sessionid` bị thiếu, hoặc thông tin đăng nhập không chính xác. | Kiểm tra xem cookie `parking_remember_token` còn tồn tại không để thực hiện silent re-auth qua `GET /api/v1/auth/me/`. Nếu thất bại, chuyển hướng người dùng về trang Login. |
| 4 | **Lỗi HTTP 429 `PROP-4.1-P01`** (`Quá nhiều lần đăng nhập không thành công...`) | Người dùng đã nhập sai mật khẩu quá 5 lần liên tiếp trong cửa sổ 15 phút. | Đọc giá trị header `Retry-After` trong response (số giây cần chờ), vô hiệu hóa nút đăng nhập và hiển thị đồng hồ đếm ngược chờ thử lại. |
| 5 | **Lỗi CORS Console** (`No 'Access-Control-Allow-Origin' header...`) | Domain của Frontend SPA (ví dụ `localhost:3000`) chưa được khai báo trong backend. | Thêm domain frontend vào biến môi trường `CORS_ALLOWED_ORIGINS` và `CSRF_TRUSTED_ORIGINS` trong file `.env` của backend, hoặc sử dụng Same-Origin Dev Proxy. |
| 6 | **Cookie không được lưu trong trình duyệt** | Request gọi từ Frontend thiếu cấu hình gửi/nhận cookie xuyên nguồn. | Thêm cấu hình `credentials: "include"` khi dùng `fetch` hoặc `withCredentials: true` khi dùng `axios`. Tuyệt đối không để mặc định `credentials: "same-origin"`. |
| 7 | **Lỗi `"Invalid HTTP_HOST header: ..."`** (DisallowedHost) | Header `Host` gửi lên không nằm trong danh sách `ALLOWED_HOSTS` của Django. | Khai báo bổ sung hostname của frontend hoặc máy phát triển vào biến môi trường `ALLOWED_HOSTS` trong backend (ví dụ: `ALLOWED_HOSTS=localhost,127.0.0.1,web`). |
| 8 | **Lỗi HTTP 503 `PROP-4.5.1-P15`** (`Hệ thống nhận diện biển số xe đang quá tải...`) | Số lượng yêu cầu quét biển số đồng thời vượt quá giới hạn hàng đợi OCR (`PARKING_OCR_CONCURRENCY_LIMIT=4`). | Đọc header `Retry-After` trong response (mặc định 3 giây), hiển thị thông báo "Hệ thống bận, đang thử lại..." và tự động gửi lại request sau thời gian chỉ định. |

### 10.2 Các tính năng chưa phát triển (What Is Not Available Yet)

Nhằm giúp lập trình viên Frontend không mất thời gian tìm kiếm hoặc chờ đợi các API chưa tồn tại, hệ thống Backend ghi nhận rõ ràng các phạm vi tính năng hiện **chưa được hiện thực**:

1. **Đăng ký tài khoản tự phục vụ (Self-service User Registration)**:
   - Hệ thống hiện tại không cung cấp API tự đăng ký tài khoản công khai. Mọi tài khoản người dùng được tạo sẵn thông qua tệp nạp dữ liệu mẫu ban đầu (`db/02-seed.sql`) hoặc do Quản lý khởi tạo.
2. **Quên mật khẩu / Đặt lại mật khẩu tự phục vụ (Self-service Password Reset)**:
   - Chưa cung cấp API gửi mã OTP hoặc đường dẫn khôi phục mật khẩu qua Email/SMS. Mật khẩu phát triển được cấp phát lại bằng lệnh quản trị máy chủ `set_account_password`.
3. **Các phân hệ quản trị CRUD độc lập khác**:
   - Các phân hệ Khách hàng (`customers`), Nhân viên (`employees`), Phương tiện (`vehicles`), Vé xe (`tickets`), Báo cáo (`reports`) hiện mới chỉ hoàn thiện mô hình dữ liệu (Database Models) và kiểm soát toàn vẹn ràng buộc; các endpoint API quản lý CRUD riêng biệt của các phân hệ này chưa được kích hoạt định tuyến. Các thông tin liên quan chỉ được truy xuất gián tiếp qua các API đỗ xe (`/api/v1/parking/*`).
4. **Phục vụ Static Files trong môi trường Production**:
   - Cơ chế phục vụ static assets của Swagger UI trực tiếp qua Django (`staticfiles_urlpatterns`) chỉ áp dụng trong môi trường phát triển (`DEBUG=True`). Trong môi trường Production (`DEBUG=False`), việc phục vụ static files là quyết định thuộc thẩm quyền của Chủ sở hữu hệ thống (sử dụng Reverse Proxy Nginx/Caddy hoặc WhiteNoise, hiện ghi nhận trạng thái `UNVERIFIED`).
