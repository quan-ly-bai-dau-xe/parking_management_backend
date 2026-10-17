---
name: 13-api-first-contract-and-mock-data
description: API-first contract development with drf-spectacular OpenAPI 3.0 schemas, automatic serializer mapping, and mock data workflows for frontend independence.
---

# Skill: API-First Contract & Mock Data Workflows

## 1. Objective

Establish an API-first (contract-first) workflow where REST interfaces, serializers, and OpenAPI 3.0 specifications are finalized before backend implementation, enabling frontend developers to build against realistic mock data without manual mapping.

## 2. API Contract-First Development Workflow

1. **Define Serializers & DTOs**: Create request/response serializers in `apps/<module>/serializers/` using DRF's `ModelSerializer` to leverage automatic field mapping. Avoid manual dictionary mappings.
2. **Annotate with `drf-spectacular`**: Use `@extend_schema` on ViewSets to specify tags, descriptions, query parameters, request bodies, and response envelopes.
3. **Generate OpenAPI Schema**:

   ```bash
   python manage.py spectacular --file docs/api/schema.yml
   ```

4. **Access Interactive Swagger UI**: Available locally at `/api/docs/` or `/api/schema/swagger-ui/`.

## 3. Mock Data Strategies for Frontend Independence

### Option A: DRF Stub ViewSets with Seed Fixtures (Recommended for Local Dev)

- Load baseline mock data from `db/02-seed.sql` into the local PostgreSQL database.
- Export modular Django JSON fixtures (e.g., `apps/customers/fixtures/sample_customers.json`) matching seed records.
- Before implementing complex business services, return data directly from serializers or fixture querysets in the ViewSet. Frontend engineers receive live, schema-compliant responses immediately.

### Option B: Stoplight Prism Mock Server (Zero-Backend Dependency)

- Frontend engineers can run an independent mock server directly from `schema.yml` without running Python/PostgreSQL:

  ```bash
  npx @stoplight/prism-cli mock docs/api/schema.yml -p 8000
  ```

- Prism dynamically serves realistic responses based on OpenAPI `examples` and types.

## 4. Avoiding Manual Mapping (Meeting 16/10/2026, Point a)

- **Use ModelSerializer**: Let DRF introspect model fields, validators, and relationships automatically.
- **Form/Payload Hydration**: Utilize `serializer.validated_data` directly in services instead of manual unpacking (`data['field']`).
- **Nested Representation**: Use nested serializers or `PrimaryKeyRelatedField` rather than hand-coded dictionary lookups.

## 5. Trigram Substring Search Pattern (TL-41, G4)

When filtering columns indexed with GIN trigram (`full_name`, `phone`, `identity_card_number`, `license_plate_norm`, `session_code`), always query directly on the column using `ILIKE '%x%'` (or `icontains` in DRF/Django filters) to leverage `Bitmap Index Scan`. Do NOT wrap the indexed column in SQL functions like `lower(column) LIKE ...`, which breaks index match and triggers a slow sequential scan.

```sql
-- GOOD: Uses GIN trigram index (Bitmap Index Scan ~2.5ms)
SELECT id, full_name FROM customer WHERE full_name ILIKE '%Thắng%' AND deleted_at IS NULL;

-- BAD: Defeats GIN trigram index, forces full table Seq Scan (~15.8ms)
SELECT id, full_name FROM customer WHERE lower(full_name) LIKE '%thắng%' AND deleted_at IS NULL;
```

## 6. Verification Checklist

- [ ] OpenAPI 3.0 schema generates with 0 warnings (`python manage.py spectacular --file schema.yml`).
- [ ] All request/response schemas include realistic examples matching 11 Frontend screens.
- [ ] No manual dictionary parsing exists in views or serializers.
- [ ] Frontend developers can successfully interact with endpoints via Prism or seed-backed stubs.
- [ ] Substring filters on trigram-indexed columns use direct `ILIKE` / `icontains` without `lower()` wrapping.
