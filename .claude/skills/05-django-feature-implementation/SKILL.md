---
name: django-feature-implementation
description: Guidelines for implementing backend business features in Django adhering to 3-tier architecture, DRF standards, domain services, data locking, and pytest-django test suites.
---

# Skill: Django Feature Implementation

## 1. Objective
Guide the implementation of backend REST API features following clear 3-tier architectural separation (Selectors, Services, ViewSets) with automated tests.

## 2. 3-Tier Layer Responsibilities
- **`models.py`**: Inherit from `SafeDeleteModel` and `HistoricalRecords`. Foreign keys use `on_delete=models.PROTECT`. Partial unique indexes enforce uniqueness on active rows (`deleted_at__isnull=True`).
- **`serializers.py`**: Validate payloads, coerce types, trim text whitespace, enforce max lengths, and aggregate validation errors.
- **`selectors.py`**: Encapsulate read queries. Use `.select_related()` and `.prefetch_related()` to eliminate N+1 hazards.
- **`services.py`**: Handle write operations and business logic inside `@transaction.atomic`. Enforce row locking via `.select_for_update()`.
- **`views.py`**: Thin HTTP controllers. Dispatch to selectors/services, enforce RBAC permissions (`permission_classes`), and return standard response envelopes.
- **`tests/`**: Automated tests using `pytest-django` covering happy path, validation errors, permission checks (403), and concurrency.

## 3. 3-Tier Code Skeleton
```python
# selectors.py (Read)
def list_entities(*, filter_val: str | None = None) -> QuerySet[Entity]:
    qs = Entity.objects.all()  # Excludes deleted records
    return qs.filter(name__icontains=filter_val.strip()) if filter_val else qs

# services.py (Write)
@transaction.atomic
def mutate_entity_service(*, entity_id: int, user, **data) -> Entity:
    entity = Entity.objects.select_for_update().filter(id=entity_id).first()
    if not entity:
        raise NotFoundError("Entity does not exist.")
    for k, v in data.items(): setattr(entity, k, v)
    entity.save()
    return entity

# views.py (Thin Controller)
class EntityViewSet(viewsets.ModelViewSet):
    permission_classes = [IsManager]
    serializer_class = EntitySerializer
    def get_queryset(self): return list_entities()
```

## 4. Verification Checklist
- [ ] Views remain thin with zero direct ORM write or business logic.
- [ ] Mutating operations execute within `@transaction.atomic` with row locking.
- [ ] Read queries eliminate N+1 hazards via proper prefetching.
- [ ] Serializers trim whitespace and enforce maximum length constraints.
- [ ] Automated tests cover happy path, validation, and permissions.
