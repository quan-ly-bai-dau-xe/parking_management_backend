---
paths:
  - "tests/**"
  - "apps/**/tests.py"
  - "apps/**/tests/**"
---

# 08-testing-and-definition-of-done.md — Testing & Definition of Done

## 1. Verified Definition of Done (DoD) Catalog

Adapted from `docs/requirements/04-dod-and-quality-check.md` (source: `01-Reference/05. [BM] DoD Template.docx`) with source typos marked [sic]:

1. **Code đã đuợc Review chéo** [sic]: Mandatory. Every PR to `dev` must be reviewed and approved by at least 1 team member.
2. **Chức năng đã đưọc test chéo** [sic]: Mandatory. Feature tested independently by another developer or QA.
3. **Test trên nhiều trình duyệt (IE, Chrome , Firefox)** [sic]: *N/A for the backend repo (frontend owner)*.
4. **Phải validate dữ liệu**: Mandatory. Rigorous validation on serializers and models.
5. **Đã hỗ trợ I18n**: Mandatory. Standardized error codes and verbatim Vietnamese SRS messages.
6. **Dữ liệu phải đẹp**: Mandatory. Consistent JSON schemas, ISO 8601 timestamps, clean seed fixtures.
7. **Đã refactor ít nhất 1 lần**: Mandatory. Zero code duplication (DRY), 3-tier layering, zero N+1 queries.
8. **Đã merge vào nhánh dev**: Mandatory. Integrated via merge commit (`--no-ff`) into `dev`.
9. **Sử dụng màu mặc định của Bootstrap**: *N/A for the backend repo (frontend owner)*.
10. **Giao diện đúng với thiết kế**: *N/A for the backend repo (frontend owner)*. Backend equivalent is 100% compliance with OpenAPI 3.0 contract.

## 2. Team Lead Backend Engineering Quality Gates

Every PR and release must satisfy all seven technical gates prior to merge:

- **[TL-GATE-01] Automated Testing**: 100% test pass rate using `pytest-django`; line coverage **>= 80%** across views, services, selectors, and models.
- **[TL-GATE-02] Linting & Formatting**: Clean run with `ruff check .` and `ruff format --check .` (0 warnings, 0 errors).
- **[TL-GATE-03] Static Type Checking**: Clean run with `mypy .` using `django-stubs` (0 type errors).
- **[TL-GATE-04] Migration Integrity**: `python manage.py makemigrations --check --dry-run` reports zero unapplied model changes.
- **[TL-GATE-05] OpenAPI Contract**: `python manage.py spectacular --file schema.yml` generates valid OpenAPI 3.0 specification without schema warnings.
- **[TL-GATE-06] Security & Dependency Hygiene**: Clean execution of `check --deploy`, `pip-audit`, and zero secret leaks.
- **[TL-GATE-07] Safe Delete Compliance**: Full adherence to `06-data-deletion-and-destructive-operations.md`.
