# Frontend API Guide — Authentication Flow

[← Previous: 01-getting-started.md](01-getting-started.md) | [↑ Back to Index](../01-frontend-api-guide.md) | [Next: 03-client-code-cors-cookies.md →](03-client-code-cors-cookies.md)

## 4. Step-by-Step Authentication Flow

The authentication architecture combines **Django Session Cookie** (`sessionid`), **Double Submit CSRF** protection (`csrftoken` and `X-CSRFToken` header), and **Persistent Remember-Me** functionality (`parking_remember_token`).

### 4.1 Step 1: CSRF Cookie Bootstrap

Before sending any state-mutating requests (`POST`, `PUT`, `PATCH`, `DELETE`), the Frontend must perform a CSRF handshake to obtain the `csrftoken` cookie:

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

### 4.2 Step 2: Login (`POST /api/v1/auth/login/`)

Login requests must include the `X-CSRFToken` header containing the value read from the `csrftoken` cookie:

#### Case 1: Missing `X-CSRFToken` Header (403 Forbidden)

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

#### Case 2: Incorrect Password or Non-Existent Account (401 Unauthorized)

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

#### Case 3: Empty Required Fields (400 Bad Request)

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

#### Case 4: Successful Login WITHOUT Remember-Me (`remember: false`)

The browser receives the session cookie `sessionid` (no `Max-Age` or `expires`, automatically deleted when the browser closes) and a freshly rotated `csrftoken`:

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

#### Case 5: Successful Login WITH Remember-Me (`remember: true`)

When `remember: true` is enabled, in addition to `sessionid`, the backend sets a long-lived `parking_remember_token` cookie (`Max-Age=2592000` = 30 days):

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

### 4.3 Technical Specifications of Cookies

| Cookie Name | `HttpOnly` Flag | `SameSite` Flag | `Secure` Flag | Lifetime | Technical Purpose |
|---|:---:|:---:|:---:|---|---|
| `csrftoken` | **False** | `Lax` | False (dev) / True (prod) | 1 year (31,449,600 seconds) | CSRF protection token; readable by JavaScript via `document.cookie`. |
| `sessionid` | **True** | `Lax` | False (dev) / True (prod) | Browser session (max 12 hours / 43,200 seconds server-side) | Identifies current user session; stored in browser memory, cleared on close. |
| `parking_remember_token` | **True** | `Lax` | False (dev) / True (prod) | 30 days (2,592,000 seconds) | Long-term persistent login token formatted as `<series>:<raw_token>`. Stored on disk by browser. |

### 4.4 Step 3: Fetch Current User Info (`GET /api/v1/auth/me/`)

After authentication, the Frontend invokes this endpoint to verify identity or restore user state on application start:

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

### 4.5 Step 4: Automatic Session Recovery on Page Reload (Silent Re-authentication)

When a user reopens the browser (losing `sessionid`), or after the 12-hour session lifetime expires:

1. The browser sends `GET /api/v1/auth/me/` with only the `parking_remember_token` cookie.
2. The backend `PersistentRememberMeMiddleware` looks up the SHA-256 hash matching the `series` key in the `persistent_login_token` table.
3. Upon validation, the backend logs in the user automatically, issues a new `sessionid`, performs atomic token rotation (after a 30-second grace period), and returns fresh `Set-Cookie` headers without requiring password re-entry:

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

### 4.6 Step 5: Logout (`POST /api/v1/auth/logout/`)

On logout, the backend revokes all persistent tokens from the database and clears all cookies:

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

### 4.7 Step 6: Password Reset via Email

For users requesting password recovery by email per REQ-4.1-F04 and TL-36:

#### Case 1: Request Password Reset (`POST /api/v1/auth/forgot-password/`)

Accepts email, enforces anti-enumeration (always 200 OK) and rate limiting (3 requests/hour per email, 10/hour per IP):

```http
POST /api/v1/auth/forgot-password/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: application/json

{"email": "hoang.dinh.khang@example.com"}

HTTP/1.1 200 OK
Content-Type: application/json

{
  "detail": "Nếu email tồn tại trong hệ thống, hướng dẫn đặt lại mật khẩu đã được gửi."
}
```

- When rate limit is exceeded: returns HTTP `429 Too Many Requests` (`PROP-4.1-P07`).

#### Case 2: Confirm Password Reset (`POST /api/v1/auth/reset-password/`)

Verifies the single-use token, updates password, and revokes prior persistent remember-tokens:

```http
POST /api/v1/auth/reset-password/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: application/json

{"token": "[MASKED]", "new_password": "[MASKED]", "confirm_password": "[MASKED]"}

HTTP/1.1 200 OK
Content-Type: application/json

{
  "detail": "Đặt lại mật khẩu thành công. Vui lòng đăng nhập bằng mật khẩu mới."
}
```

- Invalid, used, or expired token returns HTTP `400 Bad Request` (`PROP-4.1-P08`).
- Password mismatch returns HTTP `400 Bad Request` (`PROP-4.1-P09`).

### 4.8 Step 7: Password Reset via SMS OTP

For users resetting their password using SMS OTP verification per TL-01 and OQ-03:

#### Case 1: Request SMS OTP (`POST /api/v1/auth/forgot-password/sms/`)

```http
POST /api/v1/auth/forgot-password/sms/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: application/json

{"phone": "0880721788"}

HTTP/1.1 200 OK
Content-Type: application/json

{
  "detail": "Mã OTP xác thực đã được gửi tới số điện thoại của bạn qua tin nhắn SMS."
}
```

- Invalid phone format: HTTP `400 Bad Request` (`PROP-4.1-P15`).
- Rate limit exceeded (3/hr phone, 10/hr IP): HTTP `429 Too Many Requests` (`PROP-4.1-P12`).
- Resend within 60s cooldown: HTTP `429 Too Many Requests` (`PROP-4.1-P17`).

#### Case 2: Confirm SMS OTP Reset (`POST /api/v1/auth/reset-password/sms/`)

```http
POST /api/v1/auth/reset-password/sms/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: application/json

{"phone": "0880721788", "otp": "123456", "new_password": "[MASKED]", "confirm_password": "[MASKED]"}

HTTP/1.1 200 OK
Content-Type: application/json

{
  "detail": "Đặt lại mật khẩu thành công. Vui lòng đăng nhập bằng mật khẩu mới."
}
```

- Invalid or expired OTP: HTTP `400 Bad Request` (`PROP-4.1-P11`).
- More than 5 failed attempts: HTTP `400 Bad Request` (`PROP-4.1-P16`).

### 4.9 Step 8: Customer Registration via SMS OTP

Self-registration for new customers (`CUSTOMER` role) authenticated via phone verification:

#### Case 1: Request Registration OTP (`POST /api/v1/auth/register/sms/request/`)

```http
POST /api/v1/auth/register/sms/request/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: application/json

{"phone": "0912345678"}

HTTP/1.1 200 OK
Content-Type: application/json

{
  "detail": "Mã OTP xác thực đã được gửi tới số điện thoại của bạn qua tin nhắn SMS."
}
```

- Duplicate active phone: HTTP `409 Conflict` (`PROP-4.1-P13`).

#### Case 2: Confirm Registration (`POST /api/v1/auth/register/sms/confirm/`)

```http
POST /api/v1/auth/register/sms/confirm/ HTTP/1.1
Host: 127.0.0.1:8000
Accept: application/json
Cookie: csrftoken=[MASKED]
X-CSRFToken: [MASKED]
Content-Type: application/json

{
  "phone": "0912345678",
  "otp": "123456",
  "full_name": "Nguyễn Văn A",
  "id_card_number": "049098012345",
  "password": "[MASKED]",
  "confirm_password": "[MASKED]"
}

HTTP/1.1 201 Created
Content-Type: application/json

{
  "detail": "Đăng ký tài khoản thành công."
}
```

- Duplicate CCCD/CMND: HTTP `409 Conflict` (`PROP-4.1-P18`).

---
