# Frontend API Guide — Client Code, CORS & Cookies

[← Previous: 02-authentication-flow.md](02-authentication-flow.md) | [↑ Back to Index](../01-frontend-api-guide.md) | [Next: 04-conventions.md →](04-conventions.md)

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
