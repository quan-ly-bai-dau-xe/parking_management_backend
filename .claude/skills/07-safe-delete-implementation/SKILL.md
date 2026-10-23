---
name: 07-safe-delete-implementation
description: Standardized implementation guide for business entity soft deletion, serializer isDeleted mapping, domain guards, and concurrency locking.
---

# Skill: Safe Delete Implementation

## 1. Objective

Standardize the implementation of soft deletion for daily business entities adhering to `06-data-deletion-and-destructive-operations.md`, [ADR-0003](../../../docs/adr/0003-data-deletion-soft-delete-protect-and-audit.md), and `TL-23`–`TL-27` across `DEL-01` (`employee`, `account`), `DEL-02` (`customer`), `DEL-03` (`vehicle`), `DEL-04` (`ticket`), `DEL-05` (`parking_slot`), and `DEL-06` (`parking_lot`, `parking_floor`, `parking_zone`, `ticket_type`, `position`, `vehicle_type`, `parking_gate`).

## 2. API Contract & Database Duality (TL-23)

- **Serializer Layer**: Expose `isDeleted: bool` (read-only boolean field computed from `obj.deleted_at is not None`).
- **Model / Database Layer**: Under the hood, set `deleted_at = timezone.now()` and `deleted_by = request.user` (`ck_<table_short>_soft_delete_pair CHECK (deleted_by IS NULL OR deleted_at IS NOT NULL)`). Never execute physical `DELETE FROM`.

## 3. Implementation Workflow

1. **Serializer Mapping**:

   ```python
   class EntitySerializer(serializers.ModelSerializer):
       isDeleted = serializers.SerializerMethodField()

       def get_isDeleted(self, obj) -> bool:
           return obj.deleted_at is not None
   ```

2. **Domain Service**: Wrap in `@transaction.atomic` with pessimistic row locking (`select_for_update()`):

   ```python
   @transaction.atomic
   def soft_delete_entity_service(*, entity_id: int, user) -> Entity:
       entity = (
           Entity.objects.select_for_update()
           .filter(id=entity_id, deleted_at__isnull=True)
           .first()
       )
       if not entity:
           raise NotFoundError("Dữ liệu không tồn tại")
       # Service-layer pre-flight check (backed by DB trigger fn_guard_soft_delete_and_restore, TL-25)
       if entity.has_active_dependencies():
           raise BusinessValidationError("Cannot delete entity with active dependencies.")
       entity.deleted_at = timezone.now()
       entity.deleted_by = user
       entity.save(update_fields=["deleted_at", "deleted_by"])
       # Note: DB trigger trg_audit_soft_delete_and_restore_* (fn_audit_soft_delete_and_restore)
       # automatically appends action='SOFT_DELETE' to activity_log (TL-26).
       return entity
   ```

3. **Thin ViewSet**: Call service from `destroy()`, returning HTTP 200 with verbatim SRS message (e.g., `Xóa thành công`).

## 4. Verification Checklist

- [ ] API response serializes `isDeleted: true` upon deletion.
- [ ] Database stores valid `deleted_at` and `deleted_by` (`ck_*_soft_delete_pair`).
- [ ] Database `BEFORE DELETE` triggers block physical SQL deletion on 25 business tables (`TL-24`), while explicitly permitting plain `DELETE` on `persistent_login_token`, `password_reset_token` (`TL-36`) and `slot_allowed_vehicle_type` (`TL-37`, guarded by `trg_guard_slot_allowed_vehicle_type_delete`).
- [ ] Database `BEFORE UPDATE OF deleted_at` triggers (`fn_guard_soft_delete_and_restore`) block prohibited soft deletions (`DEL-01`–`DEL-06`, `TL-25`) and strictly reject soft-deleting `payment` records with `status IN ('PAID', 'REFUNDED')` (`PROP-DEL-PAYMENT-SETTLED`, `TL-39`).
- [ ] Database `payment` mutation trigger (`trg_guard_payment_update`, `TL-42`) blocks invalid payment status transitions (`PROP-PAY-STATUS-TRANSITION`) and enforces immutability of settled/refunded payment financial and link columns (`PROP-PAY-SETTLED-IMMUTABLE`).
- [ ] Database `AFTER UPDATE OF deleted_at` triggers (`fn_audit_soft_delete_and_restore`) record `'SOFT_DELETE'` in `activity_log` (`TL-26`).
- [ ] Querysets for `list`/`detail`/`update`/`create` automatically exclude soft-deleted rows (`deleted_at IS NULL`, `TL-27`).
