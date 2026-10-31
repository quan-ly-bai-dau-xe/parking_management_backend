# ADR-0009: Dual Image Storage Backend (Local & Cloudinary) and Production Media Serving

- **Status**: Superseded by ADR-0010
- **Date**: 2026-10-29
- **Deciders**: Owner, Tech Lead, Engineering Team
- **Technical Context**: Image Storage Architecture, Cloudinary SDK Integration, Decree 13/2023/ND-CP Personal Data Protection, Media Serving, Frontend Origin Resolution

---

## 1. Context & Problem Statement

The frontend engineering team reported an image display defect on the vehicle entry/exit history screen ("Lịch sử ra/vào") immediately upon starting the application with seed data. Investigation in throwaway containers reproduced causes 2 and 3 with raw HTTP evidence; cause 1 is an inference from how browsers resolve relative URLs and from the frontend dev setup, and was not reproduced with the real frontend:

1. **Frontend Origin Mismatch (likely cause, not reproduced against the real frontend)**: The backend serializers (`SessionListItemSerializer` and `SessionDetailSerializer`) return relative paths (e.g., `/media/parking_scans/...` or `/media/gates/...`). When the frontend single-page application (SPA) rendered these paths in `<img src={entry_image_url} />` from its own development origin (e.g., `http://localhost:3000`), the browser resolved the URLs against the frontend origin (`http://localhost:3000/media/...`) rather than the backend API host (`http://127.0.0.1:8000`), resulting in resource retrieval failures.
2. **Media Routing Disabled Under `DEBUG=False`**: In `config/urls.py`, media URL routing was enclosed in `if settings.DEBUG:`. In the container environment running Gunicorn (`DEBUG=False`), `django.conf.urls.static.static()` evaluates to an empty list `[]`. Consequently, any HTTP request directed to `/media/...` bypassed static file handling and fell through to `custom_json_404`, returning HTTP 404 with JSON envelope `{"code": "MSG-4.4.1-M01", "message": "Không tìm thấy dữ liệu", "details": {}}` and `Content-Type: application/json`. Web browsers cannot render JSON payloads as images, triggering broken image placeholders.
3. **Missing Physical Seed Image Files on Disk**: The baseline sample dataset (`db/02-seed.sql`) inserted 86 gate snapshot paths (e.g., `/media/gates/pk-20261017-001_in.jpg`) across 50 parking sessions. However, the physical directory `/app/media/gates` was absent from the disk filesystem, causing immediate HTTP 404 responses even when `DEBUG=True`.

To resolve these defects permanently and scale the system for cloud deployments, an architectural decision is required to:

- Maintain local disk storage as the default backend for offline development, air-gapped staging, and CI/CD pipelines.
- Provide an optional, production-grade cloud storage backend using Cloudinary (`IMAGE_STORAGE_BACKEND=cloudinary`) to offload file storage, bandwidth, and edge distribution.
- Ensure strict compliance with personal data protection regulations under Vietnamese law (Decree 13/2023/ND-CP).
- Preserve database schema authority ([ADR-0006](0006-django-skeleton-v2-schema-authority.md)) without requiring schema migrations.
- Establish a uniform, deterministic URL consumption contract between backend serializers and frontend consumers.

---

## 2. Decision Outcome

### 2.1. Dual-Backend Configuration & Fail-Fast Startup Safety

The application utilizes `django-environ` within `config/settings/base.py` to manage storage configuration via the environment variable `IMAGE_STORAGE_BACKEND`.

```python
# Image Storage Backend Settings
IMAGE_STORAGE_BACKEND: str = (
    env.str("IMAGE_STORAGE_BACKEND", default="local").strip().lower()
)

ALLOWED_STORAGE_BACKENDS = ("local", "cloudinary")
if IMAGE_STORAGE_BACKEND not in ALLOWED_STORAGE_BACKENDS:
    raise ImproperlyConfigured(
        f"Invalid IMAGE_STORAGE_BACKEND: '{IMAGE_STORAGE_BACKEND}'. "
        f"Permitted values are: {', '.join(ALLOWED_STORAGE_BACKENDS)}."
    )

CLOUDINARY_CLOUD_NAME: str = env.str("CLOUDINARY_CLOUD_NAME", default="").strip()
CLOUDINARY_API_KEY: str = env.str("CLOUDINARY_API_KEY", default="").strip()
CLOUDINARY_API_SECRET: str = env.str("CLOUDINARY_API_SECRET", default="").strip()
```

#### Fail-Fast Startup & Zero-Secret-Leakage

When `IMAGE_STORAGE_BACKEND` is set to `cloudinary`, the application enforces fail-fast startup validation. If any of the required credentials (`CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`) are missing or empty:

1. Startup is aborted immediately by raising `django.core.exceptions.ImproperlyConfigured`.
2. The exception message strictly lists only the names of missing environment variables (e.g., `Missing: CLOUDINARY_API_SECRET`).
3. **Zero-Secret-Leakage**: Under no circumstances does the application print, log, or stringify existing secret values, API keys, or configurations (e.g., calling string conversion on Cloudinary configuration is forbidden).
4. Environment template documentation (`.env.example`) declares variable names with empty values only:

```bash
# Image Storage Backend (local | cloudinary, default: local)
IMAGE_STORAGE_BACKEND=local
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

---

### 2.2. SDK Dependency Selection & Python 3.14.7 Compatibility

The project pins the official Cloudinary Python SDK in `requirements/01-base.txt`:

```text
cloudinary==1.46.3
```

- **Distribution Format**: Distributed as a pure Python wheel (`cloudinary-1.46.3-py3-none-any.whl`). It requires zero C-extensions, C compilers, or native build tools, avoiding compilation failures across container and host architectures.
- **Runtime Compatibility**: Verified 100% compatible with the project runtime baseline Python `3.14.7` and standard libraries `urllib3>=1.26.5`, standard TLS certificate packages, and `six>=1.9.0`.
- **Pure In-Memory Streaming**: The upload pipeline transfers processed image bytes directly from memory buffers (`io.BytesIO(processed.image_bytes)`) to Cloudinary's upload API over HTTPS. No intermediate files are written to local disk when operating in Cloudinary mode, preventing disk churn, orphan file accumulation, and container volume leakage.

---

### 2.3. Database Schema Parity & Zero Migrations Authority

Per [ADR-0006](0006-django-skeleton-v2-schema-authority.md), the PostgreSQL database schema defined in `db/01-schema.sql` serves as the absolute Single Source of Truth.

- In `db/01-schema.sql` (lines 1323–1324), table `vehicle_entry_exit_log` specifies:

```sql
entry_image_url TEXT NULL,
exit_image_url TEXT NULL,
```

- In `apps/parking/models.py` (lines 354–355), the corresponding model attributes are declared as `models.TextField(null=True, blank=True)`.
- The `TEXT` data type in PostgreSQL imposes no arbitrary length ceiling (unlike `VARCHAR(n)`), natively accommodating relative local URIs (e.g., `/media/parking_scans/2026/10/29/b068f56813a84124a900554a299759f0.jpg`, ~70 characters) as well as full Cloudinary HTTPS URLs (e.g., `https://res.cloudinary.com/<cloud_name>/image/upload/v1730178490/parking_scans/...`, ~115 characters).
- No schema modifications, column alterations, or new migrations are required. Running `python manage.py makemigrations --check --dry-run` remains completely clean.

---

### 2.4. Personal Data Protection (Decree 13/2023/ND-CP) Compliance

Under Vietnamese Government Decree 13/2023/ND-CP on Personal Data Protection, vehicle license plate photographs, timestamps, and entry/exit movements constitute personal data as they can be linked to identifiable individuals. The storage architecture incorporates four mandatory technical safeguards:

1. **Cryptographically Unguessable Random `public_id`**:
   - The Cloudinary `public_id` and local filename are generated exclusively using UUID4 hexadecimal strings (`uuid.uuid4().hex`).
   - Entropy: 128 bits of cryptographic randomness ($2^{128} \approx 3.4 \times 10^{38}$ states), completely eliminating URL enumeration, sequential guessing, and brute-force harvesting attacks.
   - **Strict Privacy Prohibition**: License plate characters, vehicle registration numbers, session identifiers, customer IDs, employee numbers, and gate codes are strictly prohibited from appearing in the `public_id`, filename, or remote folder path.
2. **Fixed Folder Isolation**:
   - Remote assets are strictly organized under a structured date-partitioned prefix: `parking_scans/YYYY/MM/DD/`.
   - Prevents root namespace clutter and facilitates folder-level access control policies on Cloudinary.
3. **Two-Tier Metadata Stripping**:
   - **Tier 1 (In-Memory Pillow Processing)**: Prior to storage, Pillow re-encodes the image without preserving raw EXIF blocks. Camera hardware identifiers, firmware versions, shutter parameters, and GPS location coordinates embedded by high-resolution camera sensors are completely discarded.
   - **Tier 2 (Cloudinary CDN Ingestion)**: Upload operations explicitly pass `transformation=[{"flags": "force_strip"}]`, directing the Cloudinary processing engine to strip all remaining metadata headers, color profiles, and maker notes before publishing to CDN edges.
4. **Strict Boundary Validation**:
   - Maximum upload size capped at 5 MB (`MAX_IMAGE_SIZE_MB`).
   - Magic bytes verification restricting files to JPEG, PNG, and WEBP formats.
   - Image dimension constraints (`MAX_IMAGE_PIXELS = 16_000_000`, `MAX_IMAGE_DIMENSION = 4096`) protecting against image decompression bomb vulnerabilities.

---

### 2.5. Architectural Trade-Off Analysis: Signed URLs vs. Public URLs

The engineering team evaluated two distinct URL distribution models for Cloudinary assets:

| Architectural Dimension | Signed URLs (`type="authenticated"`) | Public URLs (`type="upload"`) with UUID4 |
|---|---|---|
| **Access Control Mechanism** | Requires cryptographic SHA signature and expiration timestamp (`s--<signature>--` / `expires_at`). | Relies on 128-bit cryptographic UUID4 unguessable path over HTTPS. |
| **Frontend Display Reliability** | **Fragile / High Defect Risk**: URLs expire after time-to-live (TTL, e.g., 1 hour). When users browse historical parking sessions from previous days or months, links fail (HTTP 401/404) unless the backend re-signs every URL dynamically on each read query. | **Robust / Deterministic**: URLs remain valid and directly displayable in standard HTML `<img src="..." />` tags without expiration or re-signing overhead. |
| **Edge Caching & Performance** | **Severe Degradation**: Re-signing generates distinct query signatures over time, busting browser and CDN cache keys. Imposes CPU signature computation overhead for every item in paginated responses (e.g., 20 items $\times$ 2 images = 40 cryptographic signatures per page request). | **Optimal**: Highly efficient caching on browser and Cloudinary CDN edges. Supports HTTP 304 Not Modified and standard `Cache-Control` / ETag headers. |
| **Architectural Consistency** | Inconsistent: Local storage does not support signed URL generation. | Consistent: Both local and Cloudinary backends yield immutable, directly loadable string URLs. |
| **Security & Residual Risk** | Time-limited exposure; links shared externally expire after TTL. | Unrestricted read access if the exact 128-bit URL is disclosed. Protected by cryptographic unpredictability ($2^{128}$ space). |

#### Architectural Decision & Residual Risk Disclosure

- **Decision**: The system implements **Public `upload` URLs with 128-bit UUID4 entropy and two-tier metadata stripping**. This ensures seamless frontend rendering and optimal CDN edge performance while meeting the privacy requirements of Decree 13/2023/ND-CP.
- **Residual Risk Disclosure for Tech Lead**: Assets hosted on public Cloudinary URLs do not require authorization headers to be downloaded directly from the CDN edge. Security relies entirely on the cryptographic unpredictability of the 128-bit UUID4 token. If an authorized user deliberately copies and leaks an image URL, any recipient possessing that exact URL can view the photo without authenticating against the backend API.

---

### 2.6. Fail-Closed Upload Pipeline & Transactional Integrity

The image upload workflow in `apps/parking/services/upload.py` follows a strict fail-closed contract to guarantee database consistency:

1. **Pre-Transaction / Atomic Execution**: Storage operations (local disk write or Cloudinary upload) occur before or within the transactional boundary of plate scanning and session check-in.
2. **Fail-Closed on Error**: If Cloudinary upload fails due to network outage, DNS failure, or API rejection:
   - The upload service immediately raises a `BusinessAPIException` with registered error code `PROP-4.5.1-P14` (HTTP 502 Bad Gateway or HTTP 400 Bad Request).
   - The database transaction rolls back, ensuring that no orphaned or partial session records are created in `vehicle_entry_exit_log`.
3. **Compensating Rollback Cleanup**: If a Cloudinary upload succeeds but downstream operations (e.g., database constraint failure, OCR parsing exception) subsequently abort the transaction:
   - The exception handler invokes `cloudinary.uploader.destroy(public_id)` to delete the remote asset, preventing storage quota leaks.
4. **Redacted Exception Logging**: Error logs record only the exception class name and registered error codes (e.g., `logger.error("Cloudinary upload failed: %s", exc.__class__.__name__)`). Under no circumstances are API secrets, request signatures, or authorization headers logged.

---

### 2.7. Dual URL Validation in Serializers & Consumers

The path validator `validate_parking_image_path` in `apps/parking/services/upload.py` and the serializer field `ParkingImageRelativeUrlField` in `apps/parking/serializers/sessions.py` are updated to support dual-mode URLs while preventing web application vulnerabilities:

```python
def validate_parking_image_path(url: str | None) -> str | None:
    """Validate parking scan image paths for both Local and Cloudinary backends.

    1. Allows None (nullable field).
    2. Enforces maximum length of 255 characters.
    3. Rejects hostile schemes (javascript:, data:, file:, ftp:, http://).
    4. Validates Cloudinary HTTPS URLs strictly against configured cloud_name.
    5. Validates Local relative paths against MEDIA_URL and filesystem existence.
    6. Raises BusinessAPIException(code="PROP-4.5.1-P13", status_code=400) on invalid input.
    """
```

- **Cloudinary HTTPS URL Validation**:
  - Must use the `https://` protocol.
  - Domain and path must strictly match `https://res.cloudinary.com/<configured_cloud_name>/image/upload/...`.
  - Rejects foreign domains, unauthorized cloud accounts, and manipulated URL paths.
  - Supports both standard date-partitioned paths (`parking_scans/YYYY/MM/DD/<32_hex_uuid>.(jpg|png|webp)`).
- **Local Relative Path Validation**:
  - Must start with `settings.MEDIA_URL` (default `/media/`).
  - Path format strictly matches `/media/parking_scans/YYYY/MM/DD/<32_hex_uuid>.(jpg|png|webp)`.
  - Path traversal attempts (`..`, directory hopping) are blocked, and file existence within `MEDIA_ROOT` is confirmed.
- **Hostile Scheme Rejection**:
  - Immediately rejects `javascript:`, `data:`, `file:`, `ftp:`, and insecure plain `http://` schemes with code `PROP-4.5.1-P13`.

---

### 2.8. Safe Local Purge Command (`purge_orphan_scans`)

The administrative command `python manage.py purge_orphan_scans` identifies and removes local image files not referenced by database session records. When Cloudinary storage is enabled, session records contain absolute HTTPS URLs.

In `apps/parking/management/commands/purge_orphan_scans.py`, URL normalization handles remote URLs gracefully:

- When an image URL in the database begins with `http://` or `https://` (such as Cloudinary assets), `normalize_db_url_to_rel_path` immediately returns `None`.
- The orphan purge scanner safely skips these entries, ensuring no filesystem checks or deletions are performed against cloud assets.
- For relative URLs (Local storage), the function normalizes the string to a canonical relative path against `MEDIA_ROOT`.

**Safety Guarantee**: Remote Cloudinary URLs are skipped entirely, ensuring that the local file scanner never attempts local filesystem operations on external URLs and never issues unintended remote deletion commands.

---

### 2.9. Production Media Serving Architecture & `DEBUG=False` Fix

#### Minimal Safe Fix in Django Application (`config/urls.py`)

Under Gunicorn in containerized testing or local deployments (`DEBUG=False`), `django.conf.urls.static.static()` disables media routing. To enable direct local media serving when running the local backend without a reverse proxy, `config/urls.py` registers a safe fallback route guarded by the backend setting:

```python
from django.urls import re_path
from django.views.static import serve

if settings.IMAGE_STORAGE_BACKEND == "local":
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
```

- **Security Verification**: `django.views.static.serve` internally applies `django.utils._os.safe_join` to verify that resolved file paths remain strictly inside `settings.MEDIA_ROOT`, preventing directory traversal attacks.

#### Production Architecture Recommendation (Reverse Proxy & CDN)

For enterprise production deployments, static and media file serving should not be handled directly by Python application worker processes:

1. **Cloud-First Architecture (`IMAGE_STORAGE_BACKEND=cloudinary`)**:
   - Primary recommendation for cloud environments.
   - All image serving and thumbnail transformations are handled directly by Cloudinary's global CDN edges, completely isolating media traffic from Django/Gunicorn containers.
2. **On-Premise / Local Storage Architecture (Nginx Reverse Proxy)**:
   - When retaining local disk storage in production, deploy an Nginx reverse proxy in front of Gunicorn.
   - Nginx handles TLS termination, request buffering, and serves `/media/` directly from the shared volume mount using kernel zero-copy socket transfers and aggressive caching headers (`Cache-Control: public, max-age=86400`), completely bypassing Python worker threads.

---

### 2.10. Frontend URL Resolution Contract

To decouple frontend components from backend storage backend choices and resolve the origin mismatch defect, the frontend client application must implement a standard URL resolution helper in `docs/guides/frontend-api/10-troubleshooting-and-cloudinary.md#15-cloudinary-parking-scan-image-urls`:

```typescript
/**
 * Resolves image URLs received from the Parking Management API.
 * Handles both absolute HTTPS URLs (Cloudinary) and relative paths (Local storage).
 *
 * @param imageUrl - Raw image URL from API response (entry_image_url, exit_image_url, image_url)
 * @returns Fully qualified URL suitable for HTML <img> src attribute, or null
 */
export function resolveImageUrl(imageUrl: string | null | undefined): string | null {
  if (!imageUrl) {
    return null;
  }

  // 1. Absolute HTTPS/HTTP URL (Cloudinary storage): render directly
  if (imageUrl.startsWith("https://") || imageUrl.startsWith("http://")) {
    return imageUrl;
  }

  // 2. Relative path (Local storage): prepend backend API base origin
  const apiBase = (
    // Vite exposes env vars as import.meta.env (process.env does not exist in the browser)
    import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000"
  ).replace(/\/+$/, "");

  const cleanPath = imageUrl.startsWith("/") ? imageUrl : `/${imageUrl}`;
  return `${apiBase}${cleanPath}`;
}
```

---

## 3. Consequences & Compliance

### 3.1. Positive Consequences

- **Root Cause Remediation**: Permanently eliminates the broken image defect across development, testing, and production environments under both `DEBUG=True` and `DEBUG=False`.
- **Hybrid Storage Flexibility**: Zero-effort switching between local disk storage (development/air-gapped) and Cloudinary (production/cloud) via a single environment variable.
- **Strict Privacy Compliance**: Adheres fully to Decree 13/2023/ND-CP through 128-bit random UUID4 identifiers, fixed folder structure, two-tier metadata stripping, and absence of vehicle license plate data in URLs.
- **Zero Schema Migrations**: Preserves absolute PostgreSQL Schema Authority ([ADR-0006](0006-django-skeleton-v2-schema-authority.md)) by utilizing existing `TEXT NULL` columns.
- **Safe Maintenance Operations**: Prevents crashes and accidental data loss during local orphan image purging.

### 3.2. Trade-offs & Mitigations

- **Public Cloudinary URLs**: Relies on 128-bit cryptographic UUID4 unpredictability rather than per-request signed tokens. *Mitigation*: Unpredictability of $3.4 \times 10^{38}$ states prevents brute-force enumeration, while preserving instant browser rendering and CDN caching.
- **Local Media Serving Overhead**: Serving local media through Gunicorn in local mode consumes worker thread capacity. *Mitigation*: Recommended strictly for development and testing; production guidance specifies Nginx reverse proxy or Cloudinary CDN.

---

## 4. References

- [ADR-0001: Fixed Tech Stack and Django LTS Roadmap](0001-fixed-tech-stack-and-lts-roadmap.md)
- [ADR-0005: Local PostgreSQL 18 via Docker Compose](0005-local-docker-compose-for-postgresql.md)
- [ADR-0006: Django Skeleton v2, Database Schema Authority, and Architectural Baseline](0006-django-skeleton-v2-schema-authority.md)
- [ADR-0007: Backend Service in Docker Compose and Plate OCR Engine Selection](0007-backend-service-in-docker-compose-and-plate-ocr-engine.md)
- Government of Vietnam: Decree No. 13/2023/ND-CP on Personal Data Protection (Effective July 1, 2023)
- Cloudinary Python SDK Documentation: <https://cloudinary.com/documentation/django_integration>
- Django Documentation: Serving files stored outside static directories (<https://docs.djangoproject.com/en/6.1/howto/static-files/#serving-files-uploaded-by-a-user-during-development>)
