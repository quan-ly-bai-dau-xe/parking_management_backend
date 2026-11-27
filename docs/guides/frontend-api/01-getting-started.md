# Frontend API Guide — Getting Started

[← Back to Index](../01-frontend-api-guide.md) | [Next: 02-authentication-flow.md →](02-authentication-flow.md)

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

1. When `COMPOSE_PROFILES=frontend` is enabled in `.env` with the sibling `../parking_management_frontend` directory present, `docker compose up --build` also starts the `frontend` Nginx SPA container at `http://127.0.0.1:5173` proxying `/api/` to `http://backend:8000`.

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

For local development and frontend integration testing, all 20 sample accounts loaded from `db/02-seed.sql` come pre-configured out of the box with the shared development-only password **`Parking@Dev2026`** (**WARNING: Development-only password. In production environments (`DEBUG=False`), all sample account passwords are automatically reset to unusable hashes (`!`) by the loader safety net**).

Sample accounts can log in immediately through `/api/v1/auth/login/` using either their login email or 10-digit mobile phone number as the `identifier`, along with `Parking@Dev2026` as the password.

To refresh sample account passwords on an already-seeded database:

- **In Docker**:

  ```bash
  docker compose exec web python manage.py load_sample_data --refresh-passwords
  ```

- **Local host**:

  ```bash
  python manage.py load_sample_data --refresh-passwords
  ```

### 3.1 Command to Set Individual Account Passwords

If developers wish to assign a custom password to an individual account, the `set_account_password` management command accepts passwords securely via the `ACCOUNT_PASSWORD` environment variable or interactive prompt (passwords must never be passed via CLI flags to avoid terminal history leaks):

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
