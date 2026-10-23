# ADR-0004: Authentication Strategy, SPA Session Management, and Persistent Login Tokens

- **Status**: Accepted
- **Date**: 2026-10-11 (Updated 2026-10-17 per TL-36, Updated 2026-10-21 per D7, D8, Updated 2026-10-22 per Round 44 Q1-Q6)
- **Deciders**: Owner, Tech Lead, Engineering Team
- **Technical Context**: User Authentication, SPA Integration, and OWASP Compliance

## 1. Context & Problem Statement

The system requires secure authentication for Manager and Employee roles. SRS 4.1 specifies storing the password in a cookie ("mật khẩu sẽ được lưu trên cookie của máy"), which violates fundamental security rules (CWE-312). We must evaluate session vs JWT and secure persistent login.

## 2. Decision Outcome

### 2.1. Cookie-based Session + CSRF

- **Session Auth**: Selected over stateless JWT. Session IDs reside in `HttpOnly`, `Secure`, `SameSite=Lax` cookies, eliminating XSS token exfiltration hazards and enabling immediate server-side revocation.
- **CSRF Defense**: Double-submit cookie with `X-CSRFToken` request header for mutating API requests. Explicitly enforced on `POST /api/v1/auth/login/` and `POST /api/v1/auth/logout/` via `@method_decorator(csrf_protect)` for both anonymous and authenticated callers to prevent Login CSRF and Logout CSRF. A CSRF validation failure invokes `custom_csrf_failure_view` (`CSRF_FAILURE_VIEW`), returning HTTP 403 Forbidden with the project's standard JSON error envelope (`PROP-4.1-P06`: `"Mã CSRF không hợp lệ hoặc bị thiếu."`) rather than Django's default HTML 403.
- **Session Expiry & Lifecycle**: `request.session.set_expiry(0)` is invoked upon login (both `remember=False` and `remember=True`) and upon remember-me re-authentication. Consequently, the `sessionid` cookie sent to the client is a browser-session cookie (no `Max-Age` or `Expires` attribute), ensuring the session is cleared upon closing the browser tab/window on shared workstations. The server-side session lifetime is bounded by `SESSION_COOKIE_AGE` (default: 43200 seconds / 12 hours, representing one work shift).
- **Session Fixation**: Calls `request.session.cycle_key()` upon successful login.

### 2.2. Persistent Login Token Pattern (Replacing Cookie Password)

- Plaintext or hashed passwords in client cookies are strictly banned.
- **Token Generation**: When "Ghi nhớ mật khẩu" is checked, the backend issues a 256-bit secure random token (`secrets.token_hex(32)`).
- **Storage**: Stored as SHA-256 hash in table `persistent_login_token` (`series VARCHAR(64) UNIQUE`, `token_hash VARCHAR(255)`, `account_id BIGINT`, `ip_address VARCHAR(45)`, `user_agent VARCHAR(255)`, `created_at TIMESTAMP`, `last_used_at TIMESTAMP`, `expires_at TIMESTAMP`).
  - *Referential Integrity & Plain DELETE Exemption (TL-36)*: All foreign keys to `account` strictly preserve `ON DELETE RESTRICT` (0 non-RESTRICT foreign keys in the database catalog per ADR-0003). The token tables (`persistent_login_token`, `password_reset_token`) are exempted from immutable table guards, permitting plain `DELETE` for session rotation, logout, and token revocation. When purging expired accounts via `fn_controlled_purge()`, the purge procedure explicitly deletes linked tokens within the same transaction prior to purging the account row.
- **Client Cookie & Configuration**: Token transmitted in `parking_remember_token` (`HttpOnly=True`, `Secure=True`, `SameSite='Lax'`). Configuration parameters are extracted into named settings: `REMEMBER_COOKIE_NAME` (`"parking_remember_token"`), `REMEMBER_TOKEN_LIFETIME_DAYS` (default `30`), `REMEMBER_ROTATION_GRACE_SECONDS` (default `30`), `REMEMBER_MAX_TOKENS_PER_ACCOUNT` (default `10`). Model column lengths are inspected dynamically from model metadata.
- **Rotation, Grace Window & Anti-Theft**: Upon re-authentication, the token is evaluated inside `transaction.atomic()` with `select_for_update()` on `persistent_login_token`. To prevent false-positive session revocations caused by concurrent SPA page-load bursts across isolated Gunicorn worker processes, a 30-second rotation grace window is enforced based on `last_used_at` (`REMEMBER_ROTATION_GRACE_SECONDS`). During rotation, a composite hash `f"{current_hash}:{previous_hash}"` (129 characters) is stored in `token_hash VARCHAR(255)`. If a request presents a valid token within 30 seconds of `last_used_at`, token rotation is skipped (or the previous token hash is accepted during a rotation race) without triggering revocation. After 30 seconds, token rotation issues a fresh token and cookie. If a series matches but the presented hash does not match (or a previous token is replayed outside the 30-second grace window), token theft is detected: all persistent tokens for the account are immediately revoked via plain `DELETE` (`TL-36`), the client cookie is cleared, and a security alert is logged.
- **Database Resilience**: Middleware catches `django.db.Error` and logs without clearing cookies or deleting tokens, ensuring transient database errors (deadlocks, timeouts, temporary lost connections) do not destroy user sessions. Deletion occurs only on explicit verdicts.

### 2.3. Atomic Reserve-then-Verify Brute-Force Rate Limiting (`LoginAttemptLimiter`)

- **Atomic Reserve-then-Verify**: Replaces check-then-act with an atomic increment counter (`cache.add` with timeout, then `cache.incr`) before credential verification, eliminating parallel race condition bypasses.
- **Three Quota Buckets**:
  1. (normalized identifier, client IP): 5 attempts / 15 minutes (`AUTH_THROTTLE_PAIR_LIMIT`).
  2. per-identifier ceiling: 20 attempts / 15 minutes (`AUTH_THROTTLE_IDENTIFIER_LIMIT`), preventing distributed attackers from locking victims while still mitigating targeted guessing.
  3. per-IP failure ceiling: 30 attempts / 15 minutes (`AUTH_THROTTLE_IP_LIMIT`), preventing IP-wide credential stuffing.
- **Successful Login Handling**: Successful logins call `release_on_success` to decrement the IP failure counter and clear identifier attempts, preventing false-positive HTTP 429 lockouts on shared corporate NATs after 30 valid logins.
- **Client IP Resolution**: Respects DRF `NUM_PROXIES` semantics (default 0 = `REMOTE_ADDR`). Behind a reverse proxy, the operator must configure `NUM_PROXIES` or all clients share one IP bucket (marked `UNVERIFIED-for-production`).
- **Multi-Worker Concurrency Limitation**: In-memory `LocMemCache` is process-local. In multi-worker deployments (e.g. 4 Gunicorn workers), each worker maintains an independent counter. A shared cache backend (e.g. Redis via `django-redis`) is recommended for multi-process production (marked `UNVERIFIED-for-production`; requires ADR and Owner approval).

## 3. Consequences & References

- **Consequences**: Eliminates plaintext password exposure; complies with OWASP ASVS and CWE-312; requires token database maintenance.
- OWASP Session Management: <https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html>
- Django CSRF: <https://docs.djangoproject.com/en/6.1/ref/csrf/>
- CWE-312: <https://cwe.mitre.org/data/definitions/312.html>
