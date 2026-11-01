# Accessibility statement

## Commitment and scope

The `quan-ly-bai-dau-xe` project contributors aim to keep
`parking_management_backend` predictable and usable for developers, operators,
and client applications that rely on assistive technologies.

This repository provides a backend REST API only. User interface accessibility
— including HTML semantics, WAI-ARIA attributes, keyboard focus order, screen
reader announcements, and visual contrast — belongs to the separate frontend
repository (`parking_management_frontend`) and any other client applications.

## What the API provides for accessibility

1. **Stable machine-readable error codes**: Every error response pairs its
   human-readable message with a stable code (`MSG-*` from SRS v4.1 or
   `PROP-*` from the approved catalog in
   [`apps/core/messages.py`](apps/core/messages.py)) so clients and assistive
   tooling can handle errors deterministically without parsing prose.
2. **Consistent JSON error envelope**: All API errors use the same three-field
   JSON structure implemented in
   [`apps/core/exceptions.py`](apps/core/exceptions.py):

   ```json
   {
     "code": "MSG-...",
     "message": "...",
     "details": {}
   }
   ```

3. **No reliance on color or visual layout**: Responses communicate state
   exclusively through structured JSON fields, standard HTTP status codes, and
   standard headers such as `Retry-After` on HTTP `429` and `503` responses.
4. **Verbatim documented message catalog**: User-facing messages are defined in
   [`apps/core/messages.py`](apps/core/messages.py) and documented with HTTP
   statuses and recommended client actions in
   [`docs/guides/frontend-api/04-conventions.md`](docs/guides/frontend-api/04-conventions.md).

## Supported environments

OpenAPI 3.0 documentation and schema endpoints are served via
`drf-spectacular` and `drf-spectacular-sidecar` (configured in
[`config/urls.py`](config/urls.py)):

- Machine-readable OpenAPI schema: `/api/schema/`
- Swagger UI: `/api/docs/`
- ReDoc: `/api/redoc/`

Swagger UI and ReDoc are bundled third-party web viewers rendered by
`drf-spectacular-sidecar`; their browser UI accessibility is not audited in
this repository.

## Known limitations

- **Third-party API viewers not audited**: Neither Swagger UI (`/api/docs/`)
  nor ReDoc (`/api/redoc/`) has been audited for accessibility here, and this
  repository does not claim WCAG conformance or any formal accessibility
  certification.
- **Vietnamese human-readable messages**: By product specification (SRS v4.1),
  the `message` string in API responses is written in Vietnamese. Clients that
  need localized or assistive announcements should map the stable `code` field
  documented in
  [`docs/guides/frontend-api/04-conventions.md`](docs/guides/frontend-api/04-conventions.md).

## How to report an accessibility barrier

To report an accessibility barrier in API responses, OpenAPI metadata, or
repository documentation, open an issue using the
[Accessibility Barrier Report](.github/ISSUE_TEMPLATE/accessibility_barrier.yml)
form (tagged with the `accessibility` label). Include the endpoint path,
observed JSON response, assistive technology or client tooling used, and a
description of the barrier, with all secrets, tokens, personal data, and real
license plates removed.
