---
name: 05-django-feature-implementation
description: Guidelines for implementing backend business features in Django adhering to 3-tier architecture, DRF standards, domain services, data locking, and pytest-django test suites.
---

# Skill: Django Feature Implementation

## 1. Objective

Guide the implementation of backend REST API features following clear 3-tier architectural separation (Selectors, Services, ViewSets) with automated tests.

## 2. 3-Tier Layer Responsibilities

- **`models.py`**: Declare `managed = False` in `Meta` (Schema Authority). Inherit from `SoftDeleteModel` (for soft-deletable business tables) or `SoftDeleteBaseModel` / `TimeStampedModel`. Foreign keys use `on_delete=models.DO_NOTHING` and `db_constraint=False`. Partial unique indexes enforce uniqueness on active rows (`deleted_at__isnull=True`).
- **`serializers/`**: Validate payloads, coerce types, trim text whitespace, enforce max lengths, and aggregate validation errors using standard envelope `{code, message, details}`.
- **`selectors/`**: Encapsulate read queries. Use `.select_related()` and `.prefetch_related()` to eliminate N+1 hazards.
- **`services/`**: Handle write operations and business logic inside `@transaction.atomic`. Enforce row locking via `.select_for_update()`. Perform safe soft deletes via `.soft_delete(user=...)`.
- **`views/`**: Thin HTTP controllers. Dispatch to selectors/services, enforce RBAC permissions (`permission_classes = [IsAuthenticated]`), and return standard response envelopes.
- **`tests/`**: Automated tests using `pytest-django` running against real PostgreSQL 18.6 covering happy path, validation errors, permission checks (403), trigger guards, and concurrency.

## 3. 3-Tier Code Skeleton

```python
# apps/<module>/selectors/<entity>.py (Read)
def list_entities(*, filter_val: str | None = None) -> QuerySet[Entity]:
    qs = Entity.objects.all()  # Excludes deleted records
    return qs.filter(name__icontains=filter_val.strip()) if filter_val else qs


# apps/<module>/services/<entity>.py (Write)
@transaction.atomic
def mutate_entity_service(*, entity_id: int, user, **data) -> Entity:
    entity = Entity.objects.select_for_update().filter(id=entity_id).first()
    if not entity:
        raise NotFoundError("Entity does not exist.")
    for k, v in data.items():
        setattr(entity, k, v)
    entity.save()
    return entity


# apps/<module>/views/<entity>.py (Thin Controller)
class EntityViewSet(viewsets.ModelViewSet):
    permission_classes = [IsManager]
    serializer_class = EntitySerializer

    def get_queryset(self):
        return list_entities()
```

## 4. Verification Checklist

- [ ] Views remain thin with zero direct ORM write or business logic.
- [ ] Mutating operations execute within `@transaction.atomic` with row locking.
- [ ] Read queries eliminate N+1 hazards via proper prefetching.
- [ ] Serializers trim whitespace and enforce maximum length constraints.
- [ ] Automated tests cover happy path, validation, and permissions.
