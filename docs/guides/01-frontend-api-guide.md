# Frontend API Integration Guide — Parking Management Backend

Official technical documentation for Frontend developers integrating the Intelligent Parking Management System (**Parking Management Backend**). All HTTP, JSON, SQL, and TypeScript examples in this guide are extracted verbatim from live stack executions (recorded in `.agents/round47_guide_examples.log`, with all secrets masked as `[MASKED]`).

Welcome to the comprehensive Frontend API Integration Guide for the Parking Management Backend. This guide has been modularized into 10 focused topic guides under `frontend-api/` to make navigation, client integration, and maintenance seamless.

---

## Topic Guides Directory

| # | Topic Guide | Sections Covered | Key Topics & Endpoints |
|---|-------------|------------------|------------------------|
| 01 | [`01-getting-started.md`](frontend-api/01-getting-started.md) | Sections 1–3 | Backend URLs, 1-minute dev setup, seed data, sample test accounts |
| 02 | [`02-authentication-flow.md`](frontend-api/02-authentication-flow.md) | Section 4 | CSRF bootstrap, login scenarios, cookie specifications, silent session recovery, logout |
| 03 | [`03-client-code-cors-cookies.md`](frontend-api/03-client-code-cors-cookies.md) | Sections 5–6 | Copy-paste `fetch` & `axios` snippets, CORS & cookie scoping, Vite/Next.js/Webpack dev proxies |
| 04 | [`04-conventions.md`](frontend-api/04-conventions.md) | Section 7 | Standard error envelope, 27 error codes lookup table, pagination, rate limiting |
| 05 | [`05-parking-endpoints.md`](frontend-api/05-parking-endpoints.md) | Section 8 | Gates, plate scan OCR (AUTO, NEEDS_REVIEW, 422), vehicle lookup/search, check-in, check-out, sessions |
| 06 | [`06-vehicle-endpoints.md`](frontend-api/06-vehicle-endpoints.md) | Section 9 | Vehicle CRUD, summary KPI cards, OCC concurrency, soft-delete DEL-03 guards, streaming CSV export, vehicle types |
| 07 | [`07-customer-endpoints.md`](frontend-api/07-customer-endpoints.md) | Section 10 | Customer CRUD, summary KPI cards, OCC concurrency, soft-delete DEL-02 guards, vehicle creation alias |
| 08 | [`08-employee-endpoints.md`](frontend-api/08-employee-endpoints.md) | Section 11 | Employee CRUD, positions catalog, summary KPI cards, atomic account creation, OCC concurrency, soft-delete DEL-01 guards |
| 09 | [`09-reference-data-and-tooling.md`](frontend-api/09-reference-data-and-tooling.md) | Sections 12–13 | Administrative unit cascading hierarchy (provinces, districts, wards), TypeScript types generation (`openapi-typescript`), Postman import |
| 10 | [`10-troubleshooting-and-cloudinary.md`](frontend-api/10-troubleshooting-and-cloudinary.md) | Sections 14–15 | 9 common troubleshooting scenarios, unimplemented feature caveats, Cloudinary HTTPS image URLs & null-guard handling |

---

## Recommended Reading Order

For a smooth onboarding experience, frontend developers are encouraged to follow this learning path:

1. **Phase 1: Environment & Setup**
   - Start with [`01-getting-started.md`](frontend-api/01-getting-started.md) to launch the backend in Docker and verify the live health check.
   - Familiarize yourself with sample credentials for MANAGER, EMPLOYEE, and CUSTOMER roles.

2. **Phase 2: Authentication & Transport Setup**
   - Read [`02-authentication-flow.md`](frontend-api/02-authentication-flow.md) to understand the CSRF cookie handshake and cookie-based session lifecycle.
   - Read [`03-client-code-cors-cookies.md`](frontend-api/03-client-code-cors-cookies.md) to configure your development proxy (Vite, Next.js, or Webpack) and copy the ready-to-use API client wrapper.

3. **Phase 3: Core API Conventions**
   - Review [`04-conventions.md`](frontend-api/04-conventions.md) to understand the standard error envelope `{"error": {"code", "message", "details"}}`, pagination format, and rate limit headers.

4. **Phase 4: Business Feature Implementation**
   - Implement parking operations with [`05-parking-endpoints.md`](frontend-api/05-parking-endpoints.md) (OCR plate scanning, barrier control, check-in/out).
   - Implement vehicle management with [`06-vehicle-endpoints.md`](frontend-api/06-vehicle-endpoints.md).
   - Implement customer records with [`07-customer-endpoints.md`](frontend-api/07-customer-endpoints.md).
   - Implement staff administration with [`08-employee-endpoints.md`](frontend-api/08-employee-endpoints.md).
   - Populate address selectors using [`09-reference-data-and-tooling.md`](frontend-api/09-reference-data-and-tooling.md).

5. **Phase 5: Diagnostics & Media Handling**
   - Consult [`10-troubleshooting-and-cloudinary.md`](frontend-api/10-troubleshooting-and-cloudinary.md) for solutions to common integration hurdles and guidelines on rendering Cloudinary parking images safely.
