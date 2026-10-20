---
name: safe-delete-implementation
description: Step-by-step implementation guide for safe soft deletion, domain guards, concurrency locking, and comprehensive verification test matrices.
disable-model-invocation: true
---

# Skill: Safe Delete Implementation

## 1. Objective
Standardize entity soft deletion adhering to `06-data-deletion-and-destructive-operations.md` and [ADR-0003](../../../docs/adr/0003-data-deletion-soft-delete-protect-and-audit.md) across DEL-01 (Employee), DEL-02 (Customer), DEL-03 (Vehicle), DEL-04 (Ticket), DEL-05 (Slot).

## 2. Core Architectural Principle: PROTECT vs Domain Guards
- **Critical Architectural Truth**: Django's `on_delete=models.PROTECT` operates strictly at the ORM/DB level during physical hard deletions (raising `ProtectedError`). It does NOT prevent soft deletions (which only execute SQL `UPDATE` setting `deleted_at`).
- Therefore, the Service layer MUST implement explicit domain guards to inspect active dependent relations (e.g. active tickets or parked vehicles) before setting `deleted_at`.

## 3. Implementation Workflow
1. **Model**: Inherit from `SafeDeleteModel` (`deleted_at`, `deleted_by`).
2. **Domain Service**: Wrap in `@transaction.atomic` with row-locking (`select_for_update()`):
```python
@transaction.atomic
def delete_entity_service(*, entity_id: int, user) -> Entity:
    entity = Entity.objects.select_for_update().filter(id=entity_id).first()
    if not entity:
        raise NotFoundError("Entity does not exist.")
    # Domain guard: evaluate business constraints
    if entity.has_active_dependencies():
        raise BusinessValidationError("Cannot delete entity with active dependencies.")
    entity.deleted_at = timezone.now()
    entity.deleted_by = user
    entity.save(update_fields=["deleted_at", "deleted_by"])
    return entity
```
3. **Thin ViewSet**: Call service from `destroy()`, return HTTP 200 with verbatim success message (`Xóa thành công`).
4. **Financial Immutability**: Statistics (SRS 4.7) query through `all_objects` to include soft-deleted tickets.

## 4. 6-Criteria Test Matrix
1. **Happy Path**: Soft deletion updates `deleted_at` and `deleted_by`.
2. **Business Guard Block**: Rejection with exact SRS message when constraints violated.
3. **Not Found / Already Deleted**: Returns HTTP 404.
4. **Referential Integrity**: Physical delete blocked by DB `on_delete=PROTECT`; soft delete blocked by service guards if active children exist.
5. **Concurrency**: Pessimistic row locking resolves simultaneous deletion safely.
6. **Unique Re-creation**: Entity with same code can be created after soft delete.

## 5. Verification Checklist
- [ ] Zero physical `DELETE FROM` SQL statements execute against domain tables.
- [ ] Tickets and vehicle entry/exit records are immutable (never hard deleted).
- [ ] Service layer guards active relations before soft delete.
- [ ] Error messages cite canonical SRS catalog strings.
