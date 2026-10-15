---
name: postgresql-schema-migration-design
description: Design PostgreSQL database entities, partial unique indexes, CHECK constraints, and safe schema migrations via Django ORM.
---

# Skill: PostgreSQL Schema Design & Safe Migrations

## 1. Objective
Guide PostgreSQL 18.6 schema design via Django migrations, ensuring soft-delete partial indexes, CHECK constraints, and `on_delete=models.PROTECT`.

## 2. Entity Design Standards
- **Data Types**: `BigAutoField` (Identity BigInt), `DateTimeField` (`TIMESTAMPTZ`), `DecimalField(max_digits=12, decimal_places=2)` (`NUMERIC(12,2)` for currency), `CharField` (exact SRS lengths: 5, 11, 15, 45).
- **Partial Unique Constraints**: Traditional unique indexes block re-creating records with the same code after soft deletion. Use `UniqueConstraint` filtered by `deleted_at__isnull=True`.
- **CHECK Constraints**: Validate positive dimensions and enum ranges at the DB level.

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=["ma_nhan_vien"],
            condition=models.Q(deleted_at__isnull=True),
            name="uniq_active_employee_code",
        ),
        models.CheckConstraint(
            condition=models.Q(chieu_dai__gt=0) & models.Q(chieu_rong__gt=0),
            name="check_slot_dimensions_positive",
        ),
    ]
```

## 3. Safe Migration Workflow
1. Declare models in `models.py`. Generate migrations: `python manage.py makemigrations <app_name>`.
2. Inspect operations: ensure reversible, zero destructive `DROP`/`TRUNCATE` in `RunSQL`.
3. Validate cleanliness: `python manage.py makemigrations --check --dry-run`.
4. Never edit applied migration files in-place.

## 4. Verification Checklist
- [ ] Strictly prohibit `models.CASCADE` across domain relationships.
- [ ] Unique constraints on soft-deletable entities use partial indexes (`deleted_at__isnull=True`).
- [ ] Applied migrations are immutable.
- [ ] Static check `makemigrations --check --dry-run` passes.
