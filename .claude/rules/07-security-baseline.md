# 07-security-baseline.md — Security Baseline & Privacy Standards

## 1. Environment Secrets & Public Repo Security

- **Strict Environment Injection**: `SECRET_KEY`, database credentials, and external API keys must be loaded exclusively from OS environment variables via `django-environ`. Hardcoding credentials is a Critical P0 security violation.
- **Production Hardening**: In production, `DEBUG` must be `False`. `ALLOWED_HOSTS` must explicitly whitelist domain names.
- **Security Check**: Every deployment pipeline must run `python manage.py check --deploy` and fail if any high/medium security flags are raised.

## 2. HTTPS, Cookies & Session Architecture (ADR-0004)

- **Cookie Security**:
  - `SESSION_COOKIE_SECURE = True`
  - `SESSION_COOKIE_HTTPONLY = True`
  - `SESSION_COOKIE_SAMESITE = 'Lax'`
  - `CSRF_COOKIE_SECURE = True`
  - `CSRF_COOKIE_HTTPONLY = False` (enabling SPA to transmit `X-CSRFToken` header).
- **Remember Password**: Under no circumstances may plaintext or hashed passwords be stored in client cookies. Use cryptographically random persistent login tokens hashed via SHA-256 with rotation on use (ADR-0004).
- **CORS Whitelist**: Configure `django-cors-headers` with explicit allowed origins (`CORS_ALLOWED_ORIGINS`). Never use `CORS_ALLOW_ALL_ORIGINS = True`.

## 3. Password Policy & Hashing

- **Hasher Algorithm**: Primary hasher must be Argon2 (`argon2-cffi`), backed by Django's `Argon2PasswordHasher`:

  ```python
  PASSWORD_HASHERS = [
      "django.contrib.auth.hashers.Argon2PasswordHasher",
      "django.contrib.auth.hashers.PBKDF2PasswordHasher",
  ]
  ```

- **SRS v4.1 Password Validator (SRS 4.3.3)**:
  Passwords must contain at least:
  1. At least 1 lowercase letter.
  2. At least 1 uppercase letter.
  3. At least 1 numerical digit.
  4. At least 1 special character (`!@#$%^&*()_+-=[]{}|;:,.<>?`).

## 4. RBAC & Endpoint Permissions

- Every DRF viewset/view must declare explicit `permission_classes`:
  - `IsManager`: Grants access to Employee management (4.3), Financial Statistics (4.7), Slot Configuration (4.8), and Ticket Deletion (`DELETE /api/v1/tickets/{id}/`, DEL-04; conservative default per OQ-39).
  - `IsEmployeeOrManager`: Grants access to Customer management (4.4), Vehicle entry/exit (4.5), and Ticket create/view/renewal operations (4.6.1-4.6.3). (Note: Ticket deletion is restricted to `IsManager` by default; Employee deletion access is an open question proposal `[PROPOSAL]` under OQ-39).
- Never rely on default `AllowAny` except for public login, CSRF cookie endpoint, and health check.

## 5. Privacy & Vietnam Personal Data Protection (Nghị định 13/2023/NĐ-CP)

- Redact customer and employee Personal Identifiable Information (PII) such as Identity Card (CMND/CCCD), Phone, and Email in all system logs and diagnostic traces.
- Enforce the Right to Erasure via the customer soft-delete and PII anonymization workflow defined in `docs/requirements/03-delete-rules-catalog.md`.
