# Frontend API Guide — Troubleshooting & Cloudinary Images

[← Previous: 09-reference-data-and-tooling.md](09-reference-data-and-tooling.md) | [↑ Back to Index](../01-frontend-api-guide.md)

## 14. Troubleshooting Table & Unavailable Features

### 14.1 9 Common Troubleshooting Scenarios (Troubleshooting Table)

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
| 9 | **Broken Image on History Screen (`Lịch sử ra/vào`)** | Cloudinary credentials missing/invalid, network connectivity failure during upload, or historical/seed session has `null` image URL without frontend null-guard fallback. | Verify `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, and `CLOUDINARY_API_SECRET` in `.env` and verify outgoing HTTPS connectivity. For historical sessions with `null` image URLs, ensure frontend implements a null-guard placeholder (see Section 15). |

### 14.2 Features Not Implemented Yet (What Is Not Available Yet)

To prevent frontend developers from spending time searching for or awaiting APIs that do not currently exist, the backend team explicitly documents the following status of modules and features that **are not currently implemented**:

1. **Self-service User Registration**:
   - The system does not provide a public user self-registration API. All user accounts are provisioned via the initial seed script (`db/02-seed.sql`) or created by Managers.
2. **Self-service Password Reset**:
   - No public API is provided for OTP or password reset links via Email/SMS. Development passwords are reset using the administrative server command `set_account_password`.
3. **Unbuilt Standalone Management CRUD Modules**:
   - **Ticket (`tickets`)**: Unbuilt; no standalone CRUD endpoints exposed.
   - **Parking Map (`parking-map` / `Sơ đồ bãi`)**: Unbuilt; no standalone slot management endpoints exposed.
   - **Report (`reports`)**: Unbuilt; no standalone report endpoints exposed.
   - *(Note: Vehicle Management (`apps/vehicles/`) was fully implemented in Round 63 under `/api/v1/vehicles/` and `/api/v1/vehicle-types/`).*
   - *(Note: Customer Management (`apps/customers/`) was fully implemented in Round 66 under `/api/v1/customers/`).*
   - *(Note: Administrative Units (`apps/core/`) was fully implemented in Round 67 under `/api/v1/administrative/provinces/`, `/api/v1/administrative/districts/`, and `/api/v1/administrative/wards/`).*
   - *(Note: Employee Management (`apps/employees/`) was fully implemented in Round 67 under `/api/v1/employees/` and `/api/v1/positions/`).*
4. **Static File Serving in Production**:
   - Direct serving of Swagger UI static assets via Django (`staticfiles_urlpatterns`) applies exclusively to development (`DEBUG=True`). In production (`DEBUG=False`), static file serving is an architectural decision reserved for the System Owner (using Nginx/Caddy reverse proxy or WhiteNoise, currently marked `UNVERIFIED`).

---

## 15. Cloudinary Parking Scan Image URLs

Per [ADR-0010](../../adr/0010-cloudinary-only-image-storage.md) (which supersedes [ADR-0009](../../adr/0009-dual-image-storage-backend-and-media-serving.md)), the backend exclusively uses **Cloudinary** as the sole cloud image storage backend for parking scan images.

### 15.1 Cloudinary-Only HTTPS URL Format

All vehicle scan image URLs returned by the API (`image_url` in plate scan responses, `entry_image_url` and `exit_image_url` in parking session endpoints) are fully qualified, absolute HTTPS URLs served directly via Cloudinary CDN:

```text
https://res.cloudinary.com/<cloud_name>/image/upload/(v<version>/)?parking_scans/<YYYY>/<MM>/<DD>/<32-hex-uuid>.<ext>
```

Key characteristics:

- **Absolute HTTPS**: Image URLs are always absolute HTTPS URLs. Frontend applications can bind them directly to `<img src={imageUrl} />` without any hostname resolution or URL prefixing.
- **Decree 13/2023/ND-CP Personal Data Protection**: All public IDs use cryptographically random 128-bit UUIDs (`uuid4().hex`) with zero license plate characters or PII. GPS location coordinates and EXIF metadata are stripped before upload.

### 15.2 Null-Guard Requirement for Historical & Seed Data

In accordance with ADR-0010, the seed dataset (`db/02-seed.sql`) sets all historical `entry_image_url` and `exit_image_url` to `null`. Furthermore, parking sessions created without scan images or where plate recognition occurred without image capture return `null`.

Frontend components must implement defensive null checks (or fallback placeholder images) when rendering scan images:

```tsx
export function ParkingHistoryItem({ session }: { session: SessionListItem }) {
  return (
    <div className="session-card">
      <span className="plate-text">{session.license_plate}</span>
      {/* 1. Direct consumption with null guard / fallback placeholder */}
      <img
        src={session.entry_image_url ?? "/placeholder-car.png"}
        alt={`Entry scan for ${session.license_plate}`}
        loading="lazy"
        className="scan-thumbnail"
      />
      {session.exit_image_url && (
        <img
          src={session.exit_image_url}
          alt={`Exit scan for ${session.license_plate}`}
          loading="lazy"
          className="scan-thumbnail"
        />
      )}
    </div>
  );
}
```
