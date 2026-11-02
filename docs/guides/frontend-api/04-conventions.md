# Frontend API Guide — API Conventions

[← Previous: 03-client-code-cors-cookies.md](03-client-code-cors-cookies.md) | [↑ Back to Index](../01-frontend-api-guide.md) | [Next: 05-parking-endpoints.md →](05-parking-endpoints.md)

## 7. Standard Error Envelope & Comprehensive Error Code Table

All error responses from the API adhere to the standardized **Error Envelope** structure:

```json
{
  "code": "MSG-...",
  "message": "<detailed error message, in Vietnamese>",
  "details": {}
}
```

- `code`: Unique error identifier (in `MSG-*` format from SRS v4.1 or `PROP-*` from proposed extensions).
- `message`: Verbatim Vietnamese error message defined in `apps/core/messages.py`.
- `details`: Object containing supplementary error details (e.g., field-level validation errors, database constraint violations).

### 7.1 Lookup Table of All 27 Error Codes in Auth and Parking Modules

The table below quotes 100% verbatim message strings from the `apps/core/messages.py` catalog:

| Error Code (`code`) | HTTP Status | Verbatim Vietnamese Message (`apps/core/messages.py`) | Trigger Condition | Recommended UI Action |
|---|:---:|---|---|---|
| `PROP-4.1-P01` | 429 | `Quá nhiều lần đăng nhập không thành công, vui lòng thử lại sau.` <br>*(Too many failed login attempts, please try again later.)* | Exceeded failed login threshold: 5 attempts per username+IP pair, 20 attempts per username, 30 attempts per IP. | Read `Retry-After` header, disable login form, and display countdown timer. |
| `PROP-4.1-P02` | 200 | `Khởi tạo cookie CSRF thành công.` <br>*(CSRF cookie initialized successfully.)* | Successful call to `GET /api/v1/auth/csrf/`. | Acknowledge successful bootstrap and proceed with state-mutating requests. |
| `PROP-4.1-P03` | 200 | `Đăng xuất thành công.` <br>*(Logged out successfully.)* | Successful call to `POST /api/v1/auth/logout/`. | Clear user state in Store (Redux/Pinia) and redirect to login screen. |
| `PROP-4.1-P06` | 403 | `Mã CSRF không hợp lệ hoặc bị thiếu.` <br>*(CSRF token missing or invalid.)* | State-mutating request missing `X-CSRFToken` header or token does not match `csrftoken` cookie. | Automatically re-fetch `GET /api/v1/auth/csrf/` to acquire a new token, then retry request. |
| `MSG-4.1-M02` | 401 | `Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu` <br>*(Please re-enter your Username or Password.)* | Invalid credentials, locked account (`is_active=False`), or expired session. | Highlight username/password fields with red border; redirect to login if session expired. |
| `MSG-4.1-M03` | 400 | `Xin nhập đầy đủ Tên đăng nhập và Mật khẩu` <br>*(Please enter both Username and Password.)* | User submitted form with empty `identifier` or `password`. | Display inline validation error messages directly beneath the corresponding empty input fields. |
| `MSG-4.2-M01` | 403 | `Thông báo lỗi hệ thống` *(or `Bạn không có quyền thực hiện thao tác này.`)* <br>*(System error notification / You do not have permission to perform this action.)* | Insufficient permissions (e.g., `CUSTOMER` attempting to call parking management APIs). | Display a "403 Forbidden" alert and hide internal action buttons. |
| `PROP-4.5.1-P01` | 400 | `Định dạng biển số xe không hợp lệ.` <br>*(Invalid license plate format.)* | License plate string is empty or fails motor vehicle standard format validation. | Prompt user to inspect and enter a valid vehicle license plate (e.g., `43K-860.50`). |
| `PROP-4.5.1-P02` | 400 | `Tệp hình ảnh biển số xe không được để trống.` <br>*(License plate image file must not be empty.)* | No file attached in `image` field when calling `POST /api/v1/parking/plate-scans/`. | Require selecting an image file before enabling the "Scan Plate" button. |
| `PROP-4.5.1-P03` | 400 | `Kích thước tệp hình ảnh vượt quá giới hạn cho phép.` <br>*(Image file size exceeds allowed limit.)* | Image file size exceeds 5MB limit (`MAX_IMAGE_SIZE_MB`). | Display file size error and advise user to compress or re-capture at appropriate resolution. |
| `PROP-4.5.1-P04` | 400 | `Định dạng tệp hình ảnh không được hỗ trợ.` <br>*(Unsupported image file format.)* | Uploaded file is not JPEG, PNG, or WebP. | Show format error; only accept files with extensions `.jpg`, `.jpeg`, `.png`, `.webp`. |
| `PROP-4.5.1-P05` | 400 | `Tệp hình ảnh bị hỏng hoặc không thể xử lý an toàn.` <br>*(Corrupted image file or cannot be processed safely.)* | Binary image data corrupted or decompressed dimensions exceed safety limits (decompression bomb). | Report corrupted image and ask user to retake a clear photo or check the file. |
| `PROP-4.5.1-P06` | 422 | `Không nhận diện được biển số xe từ hình ảnh đã cung cấp.` <br>*(Failed to recognize license plate from the provided image.)* | AI OCR pipeline completed but detected no valid plate in the image. | Display notification and present a dialog allowing operator manual plate entry. |
| `PROP-4.5.1-P07` | 409 | `Biển số xe đã có phiên đỗ xe đang mở chưa hoàn thành.` <br>*(Vehicle already has an ongoing active parking session.)* | Vehicle already checked in previously and has not checked out. | Warn that vehicle is currently parked inside; navigate to active session details. |
| `PROP-4.5.1-P08` | 409 | `Biển số xe nằm trong danh sách đen, không được phép vào bãi.` <br>*(Vehicle is blacklisted and not allowed entry.)* | Vehicle is on security blacklist and prohibited from entry without manager authorization. | Trigger red security alert; require manager approval to override (`override_blacklist`). |
| `PROP-4.5.1-P09` | 400 | `Yêu cầu chọn phương thức thanh toán hợp lệ khi cước phí đỗ xe lớn hơn 0.` <br>*(A valid payment method is required when parking fee is greater than 0.)* | Transient vehicle with parking fee > 0 submitted without `payment_method`. | Require operator to select a payment method (`CASH` or `VIETQR`) on screen. |
| `PROP-4.5.1-P10` | 409 | `Phiên đỗ xe này đã được kết thúc trước đó.` <br>*(This parking session has already been completed.)* | Attempting to check out an already closed parking session. | Reload session info and notify operator that session payment and exit were already finalized. |
| `PROP-4.5.1-P11` | 400 | `Yêu cầu cung cấp chính xác một trong hai tiêu chí: mã phiên đỗ xe hoặc biển số xe.` <br>*(Must provide exactly one criterion: session code or license plate.)* | Provided both or neither of `session_code` and `license_plate`. | Validate check-out form logic; send exactly one of the two parameters. |
| `PROP-4.5.1-P12` | 400 | `Cổng ra không hợp lệ hoặc không phải cổng có hướng ra (OUT).` <br>*(Invalid exit gate or gate direction is not OUT.)* | Selected an entry gate (direction=`IN`) for vehicle check-out. | Filter gate selection list to only display gates with property `direction="OUT"`. |
| `PROP-4.5.1-P13` | 400 | `Đường dẫn hình ảnh không hợp lệ hoặc tệp không tồn tại.` <br>*(Invalid image URL or file does not exist.)* | Provided `entry_image_url` or `exit_image_url` is invalid or missing on storage. | Verify image URL returned by the plate scan/upload API. |
| `PROP-4.5.1-P14` | 403 | `Nhân viên không có quyền ghi đè danh sách đen.` <br>*(Operator lacks permission to override blacklist.)* | Non-manager operator attempted to set `override_blacklist=True`. | Only enable and display blacklist override controls for accounts with `MANAGER` role. |
| `PROP-4.5.1-P15` | 503 | `Hệ thống nhận diện biển số xe đang quá tải, vui lòng thử lại sau.` <br>*(License plate recognition system is overloaded, please try again later.)* | OCR worker pool saturated (concurrency semaphore exhausted). | Read `Retry-After` header (default 3s) and show "System busy, retrying..." message. |
| `PROP-4.5.1-P16` | 400 | `Biển số xe có định dạng chưa được định nghĩa trong danh mục quy chuẩn hoặc thuộc nhóm cần xác minh thủ công.` <br>*(Unrecognized license plate format or requires manual verification.)* | Unconventional plate format or does not match national vehicle standards. | Switch to manual operator review workflow (`NEEDS_REVIEW`). |
| `PROP-4.5.2-P01` | 409 | `Vị trí này đang bảo trì.` <br>*(This parking space is currently under maintenance.)* | Assigned parking slot is in `MAINTENANCE` status. | Highlight slot in gray on parking map and request selecting another space. |
| `MSG-4.5.1-M01` | 404 | `Không tìm thấy dữ liệu trùng khớp` <br>*(No matching records found.)* | Vehicle not found in `vehicle-lookup` or active session not found during checkout. | Indicate vehicle not found; offer option to initiate new session or recheck plate. |
| `MSG-4.4.1-M01` | 404 | `Không tìm thấy dữ liệu` <br>*(Data not found.)* | Parking session details not found for requested ID. | Display 404 screen or return user to session list view. |
| `PROP-GEN-P01` | 400 | `Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu` <br>*(Invalid data, please re-enter.)* | Request payload validation error (e.g. search keyword `< 2` characters). | Parse `details` object to display granular field errors next to input controls. |

### 7.2 Standard Pagination Envelope

Endpoints returning paginated lists (such as `/api/v1/parking/sessions/` and `/api/v1/parking/vehicle-search/`) adhere to the `StandardResultsSetPagination` structure:

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

- `count`: Total number of records matching the filter criteria.
- `total_pages`: Total number of pages.
- `current_page`: Current page index.
- `page_size`: Number of records per page (default 20, max 50).
- `next` / `previous`: URL for next or previous page (`null` if on the last or first page).

### 7.3 Rate Limiting Mechanism

The system enforces rate limiting on the login endpoint `POST /api/v1/auth/login/` (maximum 5 consecutive failed login attempts per username + IP pair in a 900-second window). When exceeding the threshold on the 6th attempt, the API returns HTTP `429 Too Many Requests` with code `PROP-4.1-P01` and the `Retry-After` header:

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

Frontend applications should parse the integer value from the `Retry-After` header (unit: seconds), disable the login button, and display a countdown timer indicating the wait duration to the user.

> **Multi-worker Gunicorn Environment Note**: When running with multiple worker processes (such as Docker Compose with 4 Gunicorn workers using per-process `LocMemCache` per `docker/gunicorn.conf.py`), failed attempt counters are tracked independently in each worker's memory. Because client requests are distributed among workers by the socket scheduler, the HTTP `429` response may appear after more than 5 attempts (probing 40 consecutive failed attempts with the same account and IP on a 4-worker stack yielded the first HTTP `429` at the 9th attempt, with a total distribution of 10 HTTP `401` and 30 HTTP `429` responses).

---
