# Frontend API Integration Guide — Parking Management Backend

Official technical documentation for Frontend developers integrating the Intelligent Parking Management System (**Parking Management Backend**). All HTTP, JSON, SQL, and TypeScript examples in this guide are extracted verbatim from live stack executions (recorded in `.agents/round47_guide_examples.log`, with all secrets masked as `[MASKED]`).

---

## 1. Backend Overview & URL Directory

The backend system is built on **Django 6.1.2**, **Django REST Framework (DRF) 3.18.3**, **PostgreSQL 18.6** database, **Gunicorn (4 workers, 6 threads)** application server, and **drf-spectacular 0.30.0** for automated OpenAPI specification generation.

### 1.1 Documentation and Infrastructure URLs

| URL Path | Purpose | Access Permission | Format |
|---|---|:---:|:---:|
| `http://127.0.0.1:8000/api/docs/` | Interactive Swagger UI | Public | HTML / JS / CSS |
| `http://127.0.0.1:8000/api/redoc/` | ReDoc API documentation UI | Public | HTML / JS |
| `http://127.0.0.1:8000/api/schema/` | OpenAPI 3.0 specification schema | Public | YAML / JSON |
| `http://127.0.0.1:8000/api/health/` | Infrastructure health check (Docker, K8s, Load Balancer) | Public | JSON |
| `http://127.0.0.1:8000/api/v1/health/` | API v1 versioned health check for Frontend | Public | JSON |

> **Architecture Note**: Both `/api/health/` and `/api/v1/health/` paths are provided deliberately. The `/api/health/` path serves network-level infrastructure monitoring (Load Balancer, Reverse Proxy, Docker Compose healthcheck), while `/api/v1/health/` serves frontend connection probing under the versioned routing prefix (`/api/v1/*`).

### 1.2 Live Stack Health Check Response

Both health check endpoints return the operational status of the PostgreSQL database and the readiness flag of the FastALPR OCR model:

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

> **Note**: The `ocr_ready` field is `true` after a Gunicorn worker runs the `post_fork` hook (`warmup_ocr()`), or `false` when the OCR models have not yet completed their initial warm-up.

When the database is unreachable, the system returns HTTP `503 Service Unavailable`:

```json
{
  "status": "unhealthy",
  "database": "disconnected",
  "ocr_ready": false
}
```

---

## 2. Quick Start Development Environment in 1 Minute

All backend services and the database are containerized in `docker-compose.yml`.

### 2.1 Startup Command

Open a terminal at the project root directory and run:

```bash
docker compose up --build
```

### 2.2 Startup Flow and Expected Startup Log

1. The `db` container (`postgres:18.6-alpine`) initializes and automatically performs health checks via internal `pg_isready`.
2. Once `db` reaches `healthy` status, the `web` container starts, automatically runs database migrations (`RUN_MIGRATIONS=1` equivalent to `python manage.py migrate --noinput`), and launches 4 Gunicorn worker processes at `http://127.0.0.1:8000`:

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

### 2.3 Load Initial Seed Data

To populate parking lots, floors, barrier gates, parking slots, and 20 sample accounts, run:

```bash
docker compose exec web python manage.py load_sample_data --force-production
```

Actual response log:

```text
Loading seed data from: /app/db/02-seed.sql
Executing seed SQL...
Sample seed data loaded successfully.
```

### 2.4 Verify Readiness Status

Verify that the system is functioning properly using:

```bash
curl -i http://127.0.0.1:8000/api/health/
```

When receiving status `HTTP/1.1 200 OK` with JSON content `{"status": "healthy", ...}`, the backend is ready to serve the frontend.

---

## 3. Development Password Setup & Sample Account Directory

To comply with strict security standards, all 20 sample accounts loaded from `db/02-seed.sql` have unusable password hashes (Django `!` prefix). Developers must set development passwords via the management CLI command.

### 3.1 Command to Set Development Account Passwords

The `set_account_password` management command accepts passwords exclusively via the `ACCOUNT_PASSWORD` environment variable (passwords must never be passed via CLI flags to avoid terminal history leaks):

- **In Docker**:

  ```bash
  docker compose exec -e ACCOUNT_PASSWORD="<your-dev-password>" web python manage.py set_account_password --identifier hoang.dinh.khang@example.com
  ```

- **Running directly on local host**:

  ```bash
  # Linux / macOS / Git Bash
  ACCOUNT_PASSWORD="<your-dev-password>" python manage.py set_account_password --identifier hoang.dinh.khang@example.com

  # Windows PowerShell
  $env:ACCOUNT_PASSWORD="<your-dev-password>"
  python manage.py set_account_password --identifier hoang.dinh.khang@example.com
  ```

Actual CLI execution output:

```text
$ ACCOUNT_PASSWORD=[MASKED] python manage.py set_account_password --identifier hoang.dinh.khang@example.com
Successfully updated password for account #1 (hoang.dinh.khang@example.com).
$ ACCOUNT_PASSWORD=[MASKED] python manage.py set_account_password --identifier luong.mai.phuong@example.org
Successfully updated password for account #2 (luong.mai.phuong@example.org).
$ ACCOUNT_PASSWORD=[MASKED] python manage.py set_account_password --identifier trinh.xuan.truong@example.com
Successfully updated password for account #9 (trinh.xuan.truong@example.com).
```

### 3.2 Sample Accounts Table in the System

The system establishes three main user roles: **MANAGER**, **EMPLOYEE**, and **CUSTOMER**.

| ID | Login Email | Phone Number | Role (`role`) | Status | Testing Purpose |
|:---:|---|:---:|:---:|:---:|---|
| 1 | `hoang.dinh.khang@example.com` | `0880721788` | `MANAGER` | `Active` | Full administrative access, override blacklisted vehicles, view reports |
| 2 | `luong.mai.phuong@example.org` | `0385211625` | `EMPLOYEE` | `Active` | Barrier gate operator: plate scanning, check-in, check-out, vehicle lookup |
| 3 | `do.minh.quan@example.net` | `0760098704` | `EMPLOYEE` | `Active` | Shift operations staff |
| 4 | `truong.ngoc.bich@example.com` | `0374179898` | `EMPLOYEE` | `Inactive` | Test locked account (`is_active=False`, returns 401 on login) |
| 5 | `vu.quoc.hung@example.org` | `0361681236` | `EMPLOYEE` | `Active` | Parking lot attendant |
| 6 | `phan.thanh.thao@example.net` | `0356582610` | `EMPLOYEE` | `Active` | Parking lot attendant |
| 7 | `ngo.gia.bao@example.com` | `0864769738` | `EMPLOYEE` | `Active` | Parking lot attendant |
| 8 | `dinh.lan.anh@example.org` | `0707739639` | `EMPLOYEE` | `Active` | Parking lot attendant |
| 9 | `trinh.xuan.truong@example.com` | `0868851325` | `CUSTOMER` | `Active` | Owner of vehicle `43K-860.50`; test customer permissions (receives 403 when invoking parking APIs) |
| 10 | `bui.khanh.doan@example.org` | `0348083802` | `CUSTOMER` | `Active` | Customer owning personal vehicles |
| 11 | `lam.hoang.viet@example.net` | `0790226163` | `CUSTOMER` | `Active` | Customer |
| 12 | `doan.tuyet.mai@example.com` | `0779009950` | `CUSTOMER` | `Active` | Customer |
| 13 | `ho.trong.nghia@example.org` | `0789632200` | `CUSTOMER` | `Active` | Customer |
| 14 | `ta.minh.chau@example.net` | `0708960990` | `CUSTOMER` | `Active` | Customer |
| 15 | `cao.tien.dung@example.com` | `0327855040` | `CUSTOMER` | `Active` | Customer |
| 16 | `duong.hong.nhung@example.org` | `0332790866` | `CUSTOMER` | `Active` | Customer |
| 17 | `ha.manh.cuong@example.net` | `0861032661` | `CUSTOMER` | `Active` | Customer |
| 18 | `mai.phuong.thao@example.com` | `0781281571` | `CUSTOMER` | `Active` | Customer |
| 19 | `kieu.quoc.tuan@example.org` | `0392758924` | `CUSTOMER` | `Active` | Customer |
| 20 | `chu.kim.oanh@example.net` | `0387755825` | `CUSTOMER` | `Active` | Customer |

---

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

---

## 5. Reference Code for `fetch` and `axios` (Copy-Paste Ready)

All code snippets below have been strictly validated with `node --check` (Node.js v25.9.0, result: `Exit code 0`).

### 5.1 Reference Implementation Using Native `fetch`

```javascript
// File: src/services/apiFetch.js

/**
 * Utility to extract cookie value by name from document.cookie
 * @param {string} name - Name of the cookie to retrieve
 * @returns {string|null} Cookie value or null if not found
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
 * Fetch wrapper that automatically attaches CSRF token and retries on session expiration
 * @param {string} url - API path (e.g., '/api/v1/parking/gates/')
 * @param {RequestInit} options - Fetch options
 * @param {boolean} isRetry - Internal retry flag
 * @returns {Promise<Response>}
 */
export async function apiFetch(url, options = {}, isRetry = false) {
  const method = (options.method || "GET").toUpperCase();
  const headers = new Headers(options.headers || {});

  // Attach CSRF token for state-mutating requests
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
    credentials: "include", // Mandatory to send session cookie and remember token
  };

  const response = await fetch(url, mergedOptions);

  // Handle automatic silent re-auth when receiving HTTP 401 due to session expiration
  if (response.status === 401 && !isRetry && !url.includes("/api/v1/auth/login/")) {
    try {
      // Call /api/v1/auth/me/ to trigger session recovery via remember token middleware
      const reauthResp = await fetch("/api/v1/auth/me/", {
        method: "GET",
        credentials: "include",
      });

      if (reauthResp.ok) {
        // Session recovered successfully: retry original request exactly once
        return await apiFetch(url, options, true);
      }
    } catch (err) {
      console.error("Automatic session re-auth failed:", err);
    }
  }

  return response;
}
```

### 5.2 Reference Implementation Using `axios`

```javascript
// File: src/services/apiClient.js
import axios from "axios";

export const apiClient = axios.create({
  baseURL: "/api/v1",
  withCredentials: true, // Mandatory to send cookies across origins or through dev proxy
  xsrfCookieName: "csrftoken", // Name of cookie containing CSRF token
  xsrfHeaderName: "X-CSRFToken", // Name of request header sent to Django
  headers: {
    "Accept": "application/json",
    "Content-Type": "application/json",
  },
});

// Response interceptor to handle automatic session recovery on 401 error
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Check for 401 error, avoid infinite loops, and do not retry the login request itself
    if (
      error.response &&
      error.response.status === 401 &&
      !originalRequest._retry &&
      !originalRequest.url.includes("/auth/login/")
    ) {
      originalRequest._retry = true;

      try {
        // Attempt session recovery using parking_remember_token via /auth/me/
        await apiClient.get("/auth/me/");

        // Re-send original request with fresh CSRF token from updated cookie
        return apiClient(originalRequest);
      } catch (reauthError) {
        // Recovery failed (remember token expired or missing) -> redirect to login
        console.warn("Session expired. Please log in again.", reauthError);
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

## 6. Handling CORS & Cookies in Development

### 6.1 Relevant Backend Environment Variables

In the `.env` file at the backend root directory (read by Docker Compose on host to interpolate and forward to `web` container via `docker-compose.yml`, as `.dockerignore` excludes `.env` from image build), the following variables control CORS and CSRF policies:

```env
# List of origins allowed to make cross-origin API calls
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173

# List of origins trusted by Django for CSRF token validation
CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173
```

### 6.2 Technical Mechanics & Cookie Scoping Decision Matrix (3 Scenarios)

Cookie scoping between Frontend applications and Backend APIs is governed by two core standards:

1. **Port Scoping (per [RFC 6265](https://www.rfc-editor.org/rfc/rfc6265.txt), Section 8.5 "Weak Confidentiality")**:
   > "Cookies do not provide isolation by port."  
   *(Accessed: 2026-10-22)*.
2. **Same-Site Rules (per [HTML Standard](https://html.spec.whatwg.org/multipage/origin.html#same-site))**:
   > "Unlike the same origin and same origin-domain concepts, for schemelessly same site and same site, the port and domain components are ignored."  
   *(Accessed: 2026-10-22)*.

Direct inspection of actual backend HTTP responses confirms that `Set-Cookie` headers (`csrftoken` and `sessionid`) **do not specify a `Domain` attribute** (`Domain: ''`), meaning cookies are host-only and strictly tied to the request host.

#### Frontend & Cookie Configuration Decision Matrix

| Scenario | Architecture Context | Cookie & Same-Site Mechanism | JavaScript `csrftoken` Readability | Mandatory Technical Solution |
|---|---|---|:---:|---|
| **(a) Same host, different ports** | Frontend: `http://localhost:3000`<br>Backend: `http://localhost:8000` | Same host `localhost`. Ports are ignored in same-site calculation; host-scoped cookies are not isolated by port (RFC 6265). | **Readable**<br>(since `HttpOnly=False` and same host `localhost`) | **No Dev Proxy Required**.<br>Configure `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` with frontend origin, and make API calls with credentials flag (`credentials: "include"` or `withCredentials: true`). |
| **(b) Different hosts** | Frontend: `http://localhost:3000`<br>Backend: `http://127.0.0.1:8000`<br>*(or two different VM domain names)* | Different hosts (`localhost` != `127.0.0.1`). Backend cookies are not attached to frontend host. | **Cannot Read**<br>(blocked by Same-Origin Policy) | **Mandatory Same-Origin Dev Proxy**.<br>Configure dev proxy in Vite/Next.js/Webpack (see Section 6.3) to forward `/api/*` requests to backend, converting them to same-origin requests. |
| **(c) Different registrable domains in production** | Frontend: `https://app.example.com`<br>Backend: `https://api.anotherdomain.net` | Different registrable domains (completely Cross-Site). Browsers isolate cookies and block third-party cookies. | **Strictly Unreadable** | **Mandatory Same-Origin Reverse Proxy** (Nginx/Caddy routing on same domain) **or API architecture change** (return CSRF token in response body / use Bearer Token). This is an Owner architectural decision and is currently not implemented. |

> **Verification Transparency**:
>
> - **VERIFIED**: Actual attributes of `Set-Cookie` issued by backend (no `Domain`) and international standards citations have been verified using automated tooling.
> - **UNVERIFIED**: Real-world browser behavior (Chrome, Firefox, Safari) regarding cross-port cookie sharing in live environments was not directly probed with headless browsers during this test round.

### 6.3 Recommended Solution: Same-Origin Dev Proxy Configuration

The most robust and standard solution for Frontend SPAs is leveraging the **Reverse Proxy** built into modern development servers. All UI requests target the local `/api/*` path (same-origin `localhost:3000`), and the Dev Server proxies them behind the scenes to `http://127.0.0.1:8000`:

#### Vite Configuration (`vite.config.ts`)

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

#### Next.js Configuration (`next.config.js`)

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

#### Webpack Dev Server Configuration (`webpack.config.js`)

```javascript
module.exports = {
  // ... other configurations ...
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

> **Verification Transparency**:
>
> - **VERIFIED**: CORS mechanism, CSRF handshake, and backend cookie issuance were tested directly on the live stack.
> - **UNVERIFIED**: Proxy configuration examples for Vite, Next.js, and Webpack above are standard guidelines for Frontend; the test server did not run a dedicated Frontend Dev Server process.

---

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

## 8. Details of All 8 Parking Endpoints

All parking module endpoints require staff or manager authentication (`IsEmployeeOrManager`). Customer accounts (`CUSTOMER`) receive `403 Forbidden` (`MSG-4.2-M01`):

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

### 8.1 Retrieve Gate List (`GET /api/v1/parking/gates/`)

- **Purpose**: Retrieve barrier gate list to populate entry/exit gate dropdown selectors.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters**:
  - `direction` (optional): Filter by gate direction (`IN` or `OUT`).
  - `is_active` (optional): Filter active gates (`true` or `false`).
- **Live Stack Example**:

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

### 8.2 License Plate Recognition Scan (`POST /api/v1/parking/plate-scans/`)

- **Purpose**: Recognize license plates from camera feed or uploaded files, automatically apply Position-Aware Corrections, evaluate `AUTO` / `NEEDS_REVIEW` policy, look up registered vehicle records, and provide nearest plate `suggestions`.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Request Format**: `multipart/form-data` (with `X-CSRFToken` header).
- **Form Fields**:
  - `image` (required): Plate image file (JPEG, PNG, WebP; max size 5MB).
  - `gate_id` (optional): ID of barrier gate submitting the scan.

#### Example 1: Successful Automatic Approval (`review_status: "AUTO"`)

When AI confidence is high and conforms to Vietnamese vehicle plate standards (`43K-860.50` owned by customer `Trịnh Xuân Trường`):

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

#### Example 2: Operator Review Required (`review_status: "NEEDS_REVIEW"`)

When image has low confidence or positional character correction was applied (`43K-86O.59` with `O` at pos 5 corrected to `0` -> `43K86059`, suggesting registered plate `43K-860.50`):

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

#### Example 3: License Plate Not Detected in Image (HTTP `422 Unprocessable Content`)

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

#### Table of 9 Review Reason Codes (`ReviewReasonCode` in `apps/parking/enums.py`)

| Reason Code (`review_reasons`) | Technical Meaning | Recommended UI Action |
|---|---|---|
| `MODEL_DISAGREEMENT` | The two AI OCR models yielded differing plate recognition outputs. | Display both candidates side-by-side so operator can select correct plate. |
| `LOW_CHAR_CONFIDENCE` | One or more characters fall below confidence threshold (< 90.0%). | Highlight low-confidence characters with yellow alert badge on UI. |
| `INVALID_FORMAT` | Recognized plate string does not conform to Vietnamese motor vehicle standards. | Prompt operator to inspect and verify plate structure. |
| `UNKNOWN_PLATE_PATTERN` | Unconventional plate format not cataloged in standard rules. | Provide manual text input field for operator verification. |
| `NO_DETECTION_RETRY` | Primary detector missed plate, triggered fallback crop. | Alert that camera angle or lighting may be suboptimal. |
| `LOW_DETECTION_CONFIDENCE` | License plate bounding box confidence is `< 80.0%`. | Warn that vehicle may not be aligned with optimal detection zone. |
| `IRREGULAR_ASPECT_RATIO` | Plate aspect ratio is irregular (`< 1.3` or `> 6.0`). | Warn that plate angle is excessively skewed or distorted. |
| `LOW_IMAGE_SHARPNESS` | Low image sharpness score (Laplacian variance `< 30.0`, blurry image). | Notify that image is blurry due to vehicle motion or adverse weather. |
| `POSITION_CORRECTED` | Positional grammar rule correction applied (e.g., letter `O` corrected to digit `0`). | Display `corrections` list for operator confirmation. |

#### UI Handling Guidelines for `NEEDS_REVIEW`

When `review_status === "NEEDS_REVIEW"`:

1. **Warning Badge**: Display yellow/amber badge "Review Required" next to plate number.
2. **Enable Editing**: Provide text input enabling gate operator to correct the plate based on camera image shown on screen.
3. **Show Suggestions**: Render `suggestions` list as quick-selection action buttons for one-touch operator confirmation.
4. **Do Not Open Barrier Automatically**: Never auto-trigger barrier gate opening until the operator clicks "Confirm Check-In".

### 8.3 Lookup Vehicle by Plate Number (`GET /api/v1/parking/vehicle-lookup/`)

- **Purpose**: Instantly retrieve vehicle specifications, customer details, assigned slot, active monthly pass, active session, and blacklist status upon gate approach.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameter**: `license_plate` (license plate string, required).
- **Live Stack Example When Vehicle Found (`43K-860.50`)**:

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

- **Live Stack Example When Not Found** (HTTP `404 Not Found` with code `MSG-4.5.1-M01`):

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

### 8.4 Multi-Criteria Vehicle Search (`GET /api/v1/parking/vehicle-search/`)

- **Purpose**: Assist staff in locating parked vehicles for customers or looking up vehicle history across multiple search criteria.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters**:
  - `q` (optional): Unified search keyword (automatically matches customer name, phone number, or plate; minimum 2 characters).
  - `customer_name` (optional): Filter by customer name.
  - `phone` (optional): Filter by phone number (supports `+84` and `0` formats).
  - `license_plate` (optional): Filter by license plate.
  - `page` / `page_size`: Pagination parameters.
- **Example 1: Matching Search Results (`?q=43K-860`)**:

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

- **Example 2: No Matching Results (`200 OK` with `message`)**:

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

- **Example 3: Search Keyword Shorter Than 2 Characters (`400 Bad Request` with `PROP-GEN-P01`)**:

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

### 8.5 Vehicle Check-In (`POST /api/v1/parking/sessions/check-in/`)

- **Purpose**: Record vehicle entry at the barrier gate, generating session code `#PK-YYYYMMDD-NNN`.
- **Required Permission**: `EMPLOYEE` or `MANAGER` (`override_blacklist=true` flag restricted to `MANAGER`).
- **Required Headers**: `X-CSRFToken`.
- **Body Fields**: `license_plate` (required), `entry_gate_id` (optional), `slot_id` (optional), `entry_image_url` (optional), `recognition_source` (`AI` or `MANUAL`), `ai_confidence` (0–100), `review_status` (`AUTO` or `NEEDS_REVIEW`), `override_blacklist` (`false` default), `notes` (optional).
- **Live Stack Example (HTTP `201 Created`)**:

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

### 8.6 Vehicle Check-Out (`POST /api/v1/parking/sessions/check-out/`)

- **Purpose**: Conclude vehicle parking session at exit gate, automatically calculate parking fee (0 VND for `ACTIVE` monthly passes; otherwise calculated by hourly block: 10,000 VND/hour), and record payment record `payment`.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Required Headers**: `X-CSRFToken`.
- **Input Rules**:
  - Provide exactly **one of two criteria**: `session_code` OR `license_plate`.
  - Exit gate `exit_gate_id` must have attribute `direction="OUT"` (selecting an `IN` gate returns error `PROP-4.5.1-P12`).
  - If transient parking fee is `> 0`, `payment_method` is mandatory (`CASH` or `VIETQR`).
- **Live Stack Example (HTTP `200 OK`)**:

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

### 8.7 List Parking Sessions (`GET /api/v1/parking/sessions/`)

- **Purpose**: Retrieve historical parking session log table for management and statistics.
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Query Parameters**: `session_code`, `license_plate`, `status` (`open` or `closed`), `entry_time_from`, `entry_time_to`, `page`, `page_size`.
- **Live Stack Example**:

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

### 8.8 Parking Session Details (`GET /api/v1/parking/sessions/{id}/`)

- **Purpose**: View granular parking session details by integer ID (entry/exit timestamps, barrier camera photos, handling staff, slot assignment, billing).
- **Required Permission**: `EMPLOYEE` or `MANAGER`.
- **Live Stack Example When Found (`GET /api/v1/parking/sessions/51/`)**:

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

- **Live Stack Example When Not Found (`404 Not Found` with `MSG-4.4.1-M01`)**:

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

## 9. Automatically Generate Typed Client or Postman Collection

### 9.1 Automatically Generate TypeScript Types with `openapi-typescript`

The Frontend can automatically extract type-safe TypeScript interfaces for every Request, Response, and Schema directly from the `/api/schema/` endpoint:

```bash
# Run directly against running server or downloaded schema.yaml
npx --yes openapi-typescript@7.13.0 http://127.0.0.1:8000/api/schema/ -o src/types/api.d.ts
```

#### Actual Extraction Output (`openapi-typescript 7.13.0` — 1,553 lines)

```text
$ npx --yes openapi-typescript@7.13.0 schema.yaml -o src/types/api.d.ts
Exit code: 0
✨ openapi-typescript 7.13.0
🚀 schema.yaml → src/types/api.d.ts [61.2ms]
```

Verbatim excerpt from generated `src/types/api.d.ts`:

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
         * System readiness status check
         * @description Checks system readiness status, PostgreSQL database connectivity, and OCR model availability.
         *     Both `/api/health/` (infrastructure monitoring) and `/api/v1/health/` (API v1) are intentionally provided for compatibility with infrastructure health checkers (Docker/K8s/reverse proxy) and frontend version routing.
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
         * Initialize CSRF cookie
         * @description Public endpoint initializing and returning the csrftoken cookie for SPA double-submit CSRF protection.
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

### 9.2 Import into Postman (Postman Collection Import)

1. Open Postman, select **Import** in the upper-left corner.
2. Select the **Link** tab and paste the URL: `http://127.0.0.1:8000/api/schema/`.
3. Click **Continue** and select **Import as API with a Collection**.
4. The full API catalog and request/response examples will synchronize automatically into Postman.

---

## 10. Troubleshooting Table & Unavailable Features

### 10.1 8 Common Troubleshooting Scenarios (Troubleshooting Table)

| No. | Issue Symptom | Root Cause | Definitive Solution |
|:---:|---|---|---|
| 1 | **Swagger UI / ReDoc Blank Page** | In `DEBUG=True`, Gunicorn does not automatically serve static assets for `drf-spectacular-sidecar` if `staticfiles_urlpatterns` route is omitted. | Ensure `config/urls.py` appends `staticfiles_urlpatterns()` when `settings.DEBUG` is True. Inspect browser console to confirm `.css` and `.js` files do not return 404 errors. |
| 2 | **HTTP 403 `PROP-4.1-P06`** (`Mã CSRF không hợp lệ hoặc bị thiếu` - Invalid or missing CSRF token) | State-mutating request (`POST`, `PUT`, `DELETE`) sent without `X-CSRFToken` header or token does not match `csrftoken` cookie. | Call `GET /api/v1/auth/csrf/` before sending mutations; read value from `csrftoken` cookie and set into `X-CSRFToken` header. If running cross-origin, configure a Dev Proxy. |
| 3 | **HTTP 401 `MSG-4.1-M02`** (`Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu` - Please re-enter your Username or Password) | Session expired, `sessionid` cookie missing, or credentials invalid. | Check whether `parking_remember_token` cookie is present to perform silent re-auth via `GET /api/v1/auth/me/`. If re-auth fails, redirect user to the login screen. |
| 4 | **HTTP 429 `PROP-4.1-P01`** (`Quá nhiều lần đăng nhập không thành công, vui lòng thử lại sau.` - Too many failed login attempts, please try again later) | User entered incorrect password more than 5 consecutive times within a 15-minute window. | Read `Retry-After` response header (seconds to wait), disable login button, and display a countdown timer before allowing retry. |
| 5 | **Browser Console CORS Error** (`No 'Access-Control-Allow-Origin' header...`) | Frontend SPA domain (e.g. `localhost:3000`) is not declared in backend configuration. | Add frontend domain to `CORS_ALLOWED_ORIGINS` and `CSRF_TRUSTED_ORIGINS` in backend `.env`, or configure a Same-Origin Dev Proxy. |
| 6 | **Cookies Not Saved in Browser** | Request sent from Frontend lacks cross-origin cookie configuration. | Add `credentials: "include"` when using `fetch` or `withCredentials: true` when using `axios`. Do not leave default `credentials: "same-origin"`. |
| 7 | **Error `"Invalid HTTP_HOST header: ..."`** (DisallowedHost) | Received `Host` header is not included in Django `ALLOWED_HOSTS` list. | Add frontend hostname or dev machine host to `ALLOWED_HOSTS` in backend `.env` (e.g., `ALLOWED_HOSTS=localhost,127.0.0.1,web`). |
| 8 | **HTTP 503 `PROP-4.5.1-P15`** (`Hệ thống nhận diện biển số xe đang quá tải, vui lòng thử lại sau.` - License plate recognition system is overloaded, please try again later) | Number of concurrent plate scan requests exceeds OCR queue capacity (`PARKING_OCR_CONCURRENCY_LIMIT=4`). | Read `Retry-After` response header (default 3 seconds), display "System busy, retrying..." message, and retry automatically after specified delay. |

### 10.2 Features Not Implemented Yet (What Is Not Available Yet)

To prevent frontend developers from spending time searching for or awaiting APIs that do not currently exist, the backend team explicitly documents the following features that **are not currently implemented**:

1. **Self-service User Registration**:
   - The system does not provide a public user self-registration API. All user accounts are provisioned via the initial seed script (`db/02-seed.sql`) or created by Managers.
2. **Self-service Password Reset**:
   - No public API is provided for OTP or password reset links via Email/SMS. Development passwords are reset using the administrative server command `set_account_password`.
3. **Other Standalone Management CRUD Modules**:
   - Customer (`customers`), Employee (`employees`), Vehicle (`vehicles`), Ticket (`tickets`), and Report (`reports`) modules currently have their database models and relational constraints established; however, standalone CRUD management API endpoints for these modules are not currently exposed in routing. Associated data is accessed indirectly through parking APIs (`/api/v1/parking/*`).
4. **Static File Serving in Production**:
   - Direct serving of Swagger UI static assets via Django (`staticfiles_urlpatterns`) applies exclusively to development (`DEBUG=True`). In production (`DEBUG=False`), static file serving is an architectural decision reserved for the System Owner (using Nginx/Caddy reverse proxy or WhiteNoise, currently marked `UNVERIFIED`).
