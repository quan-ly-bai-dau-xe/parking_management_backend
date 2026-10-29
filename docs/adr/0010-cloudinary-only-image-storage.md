# ADR-0010: Cloudinary-Only Image Storage Architecture

- **Status**: Accepted
- **Date**: 2026-10-29
- **Deciders**: Owner, Tech Lead, Engineering Team
- **Technical Context**: Image Storage Architecture, Cloudinary SDK Integration, PR #37 Refactoring, Stateless Application Containers, Decree 13/2023/ND-CP Personal Data Protection

---

## 1. Context & Problem Statement

In [ADR-0009](0009-dual-image-storage-backend-and-media-serving.md), the system introduced a dual storage backend architecture (`IMAGE_STORAGE_BACKEND=local|cloudinary`) to address frontend image display errors and missing disk assets. While this allowed offline local development, operating dual backends introduced substantial architectural and operational liabilities:

1. **Dual Backend Code Complexity & Branching**: Business services (`apps/parking/services/upload.py`, `plate_scan.py`), serializers, and views had to branch on `IMAGE_STORAGE_BACKEND`, maintaining two divergent file-saving paths, cleanup mechanisms, and validation schemes.
2. **Container Statefulness & Persistence Hurdles**: Local disk storage required Docker host volume mounts (`/app/media`), filesystem permission synchronizations across host and Linux containers, and custom orphan cleanup management commands (`purge_orphan_scans`).
3. **Production Static/Media Serving Violations**: Serving user media via Django's `django.views.static.serve` within application containers violates twelve-factor stateless architecture, degrades Gunicorn worker throughput, and complicates horizontal scaling.
4. **Pull Request #37 Objectives**: Refactor PR #37 (`bugfix/parking-history-image-urls`) to completely retire local-disk image storage, eliminate dual-backend branching, and establish Cloudinary as the single, exclusive cloud storage backend for parking scan snapshots.

---

## 2. Decision Outcome

We decided to adopt **Cloudinary as the exclusive image storage backend** across all runtime environments (development, staging, production) and dismantle all local-disk storage mechanisms.

### 2.1. Complete Removal of Local Storage Subsystem

- Removed `IMAGE_STORAGE_BACKEND` setting and all conditional logic branching on it across `config/`, `apps/`, and `tests/`.
- Removed local file saving (`save_processed_image` local branch), local file path tracking (`result.file_path`), and local URL validation from `apps/parking/services/upload.py`.
- Removed the `/media/` URL route from `config/urls.py` and deleted the import of `django.views.static.serve`.
- Removed `apps/parking/management/commands/purge_orphan_scans.py` and its associated unit/edge test suites.
- Removed `MEDIA_URL` and `MEDIA_ROOT` from `config/settings/base.py`.
- Removed media directory creation (`mkdir /app/media/...`) from `Dockerfile` and `docker/entrypoint.sh`.

### 2.2. Centralized Configuration & Fail-Fast Startup

- Cloudinary SDK is initialized centrally in Django settings (`config/settings/base.py`, `local.py`, `production.py`) using three mandatory environment variables:
  - `CLOUDINARY_CLOUD_NAME`
  - `CLOUDINARY_API_KEY`
  - `CLOUDINARY_API_SECRET`
- In `local` and `production` environments, missing any of these variables immediately halts application initialization with `django.core.exceptions.ImproperlyConfigured` citing the missing variable names.
- In `test` environments (`config/settings/test.py`), deterministic fake credentials (`test-cloud`, `test-key`, `test-secret`) are provided to allow offline test execution.
- In `docker-compose.yml`, the three variables are forwarded with `:?` mandatory syntax matching `SECRET_KEY`.

### 2.3. Strict Image URL Contract

All vehicle entry/exit scan image URLs stored in `vehicle_entry_exit_log` and returned by REST API endpoints must conform strictly to the Cloudinary HTTPS pattern:

```regex
^https://res\.cloudinary\.com/<CLOUDINARY_CLOUD_NAME>/image/upload/(v\d+/)?parking_scans/\d{4}/\d{2}/\d{2}/[0-9a-f]{32}\.(jpg|png|webp)$
```

- Relative paths (e.g. `/media/...`), non-HTTPS schemes, other hosts, or altered path hierarchies are rejected with HTTP 400 (`PROP-4.5.1-P13`).
- URL maximum length remains bounded at 255 characters (`ParkingImageRelativeUrlField` / `db/01-schema.sql`).

### 2.4. Resilient Upload & Compensating Destroy

- Images are pre-processed in-memory (JPEG conversion, EXIF GPS stripping, dimension bounding) and uploaded directly to Cloudinary as binary streams (`io.BytesIO`).
- Fail-closed validation ensures that if Cloudinary returns an empty or missing `secure_url`, the upload aborts with HTTP 502 (`PROP-4.5.1-P17`).
- If an OCR processing error, database transaction abort, or unhandled exception occurs after a successful Cloudinary upload in `execute_plate_scan`, the service triggers a compensating destroy (`cloudinary.uploader.destroy(public_id)`).
- If the compensating destroy fails, a single generic warning is logged containing only the exception class name (never credentials, URLs, or raw messages), and the original error propagates to the client as HTTP 502.

### 2.5. In-Memory Mocking for Testing & CI

- An autouse fixture in `tests/conftest.py` replaces `cloudinary.uploader.upload` and `cloudinary.uploader.destroy` with an in-memory fake (`FakeCloudinaryStorage`).
- The test suite runs 100% offline with zero network latency, deterministic URL outputs, and comprehensive failure injection capabilities.
- Live verification against real Cloudinary endpoints is isolated in dedicated tests marked `@pytest.mark.network`.

---

## 3. Consequences & Trade-offs

### 3.1. Positive Consequences

- **Stateless Containers**: Application containers require zero disk persistence or volume mounting for user media, simplifying horizontal scaling on Kubernetes and cloud container services.
- **High Performance CDN**: Offloads media bandwidth, caching, and edge delivery to Cloudinary's global content delivery network.
- **Architectural Simplicity**: Eliminates dual-backend conditional branches, local directory creation scripts, and filesystem cleanup cron jobs.
- **Consistent API Contract**: Frontend applications receive absolute HTTPS URLs directly usable in HTML `<img src="..." />` tags without needing host-prefix resolution logic.

### 3.2. Liabilities, Costs & Operational Requirements

1. **Mandatory Cloudinary Credentials**:
   - Developers and operations teams must provision and supply valid Cloudinary API credentials in `.env` for both local development and production runtime. The application will not start without them.
2. **Third-Party Processing & Cost**:
   - Vehicle scan snapshots are transmitted and stored on Cloudinary infrastructure. Usage incurs storage and bandwidth costs based on parking volume. Compliance with Vietnamese data sovereignty and personal data protection regulations (Decree 13/2023/ND-CP) must be reviewed.
3. **Unguessable Public URLs**:
   - Stored assets use public URLs structured with random 32-hex UUIDs and date partitioning (`parking_scans/YYYY/MM/DD/<uuid32>.<ext>`). While unguessable, assets are publicly accessible if the URL is disclosed, avoiding signed URL expiration complexity for read operations.
4. **Orphan Assets on Failed Transactions**:
   - While compensating destroy removes uploaded assets when synchronous scan transactions fail, abnormal worker termination (SIGKILL, container crash, host power loss) during the scan lifecycle can leave orphan assets in Cloudinary. Periodic audit or lifecycle tags may be required.
5. **No Offline Mode for Runtime**:
   - Unlike the previous dual-backend design, local development and staging environments require active internet connectivity to Cloudinary to upload scan images. Offline development is only supported within the automated test suite via `FakeCloudinaryStorage`.
6. **Operator Responsibility for Seed & Historical Data**:
   - Seed data in `db/02-seed.sql` sets historical `entry_image_url` and `exit_image_url` to `NULL`.
   - Operators upgrading existing deployments from previous versions must execute database update scripts to set any obsolete relative `/media/...` values to `NULL` (or migrate them to Cloudinary), as backend serializers no longer provide backward-compatibility shims for relative URLs.
   - Frontend clients must implement defensive null guards to render placeholder images when image URLs are `null`.
