---
name: 02-screen-to-api-breakdown
description: Deconstruct SRS screen specifications into RESTful API endpoints and OpenAPI 3.0 contracts using drf-spectacular.
---

# Skill: Screen-to-API Breakdown & OpenAPI 3.0 Contracts

## 1. Objective

Design API endpoints for each business screen and establish OpenAPI 3.0 interface contracts, ensuring RESTful conventions, RBAC enforcement, and standard HTTP response status codes.

## 2. Step-by-Step Deconstruction Workflow

1. **Identify Screen Business Actions**: Categorize into List/Search, Retrieve, Create, Update, Soft Delete, and Auth actions.
2. **Design URI & HTTP Methods**: Adhere to RESTful resource-oriented naming (`GET/POST /api/v1/employees/`, `GET/PUT/PATCH/DELETE /api/v1/employees/{id}/`).
3. **Define RBAC Permission Matrix**: Apply roles from SRS: Manager (`IsManager`) or Employee (`IsEmployeeOrManager`).
4. **Design Request/Response Schemas**: Define JSON schemas and standard error envelopes.
5. **Generate OpenAPI 3.0 via `drf-spectacular`**: Annotate viewsets with `@extend_schema`.

## 3. Generic Contract Skeleton

```yaml
openapi: 3.0.3
info: { title: Car Parking API, version: 1.0.0 }
paths:
  /api/v1/employees/:
    get:
      summary: Employee list and filtering (SRS 4.3.1)
      responses:
        '200': { description: Paginated list }
        '403': { description: Forbidden }
```

## 4. Verification Checklist

- [ ] Endpoints adhere to plural noun conventions (`/api/v1/<resources>/`).
- [ ] RBAC permissions match the SRS actor matrix.
- [ ] Error responses conform to standardized JSON error envelopes.
- [ ] Response payloads exclude sensitive fields (passwords, tokens).
- [ ] `DELETE` operations conform to safe soft-delete policies.
