# ADR-0004: Authentication Strategy, SPA Session Management, and Persistent Login Tokens

- **Status**: Accepted
- **Date**: 2026-10-11 (Updated 2026-10-17 per TL-36)
- **Deciders**: Owner, Tech Lead, Engineering Team
- **Technical Context**: User Authentication, SPA Integration, and OWASP Compliance

## 1. Context & Problem Statement

The system requires secure authentication for Manager and Employee roles. SRS 4.1 specifies storing the password in a cookie ("mật khẩu sẽ được lưu trên cookie của máy"), which violates fundamental security rules (CWE-312). We must evaluate session vs JWT and secure persistent login.

## 2. Decision Outcome

### 2.1. Cookie-based Session + CSRF

- **Session Auth**: Selected over stateless JWT. Session IDs reside in `HttpOnly`, `Secure`, `SameSite=Lax` cookies, eliminating XSS token exfiltration hazards and enabling immediate server-side revocation.
- **CSRF Defense**: Double-submit cookie with `X-CSRFToken` request header for mutating API requests.
- **Session Fixation**: Calls `request.session.cycle_key()` upon successful login.

### 2.2. Persistent Login Token Pattern (Replacing Cookie Password)

- Plaintext or hashed passwords in client cookies are strictly banned.
- **Token Generation**: When "Ghi nhớ mật khẩu" is checked, the backend issues a 256-bit secure random token (`secrets.token_hex(32)`).
- **Storage**: Stored as SHA-256 hash in table `persistent_login_token` (`account_id`, `token_hash`, `expires_at`, `created_at`, `last_used_ip`).
  - *Referential Integrity & Plain DELETE Exemption (TL-36)*: All foreign keys to `account` strictly preserve `ON DELETE RESTRICT` (0 non-RESTRICT foreign keys in the database catalog per ADR-0003). The token tables (`persistent_login_token`, `password_reset_token`) are exempted from immutable table guards, permitting plain `DELETE` for session rotation, logout, and token revocation. When purging expired accounts via `fn_controlled_purge()`, the purge procedure explicitly deletes linked tokens within the same transaction prior to purging the account row.
- **Client Cookie**: Token transmitted in `parking_remember_token` (`HttpOnly=True`, `Secure=True`, `SameSite='Lax'`, 30-day expiry).
- **Rotation & Anti-Theft**: Upon re-authentication, the consumed token is invalidated, a fresh token is issued, and if an invalid or already-used token is presented, all user remember tokens are revoked.

## 3. Consequences & References

- **Consequences**: Eliminates plaintext password exposure; complies with OWASP ASVS and CWE-312; requires token database maintenance.
- OWASP Session Management: <https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html>
- Django CSRF: <https://docs.djangoproject.com/en/6.1/ref/csrf/>
- CWE-312: <https://cwe.mitre.org/data/definitions/312.html>
