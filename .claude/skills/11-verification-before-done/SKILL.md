---
name: 11-verification-before-done
description: Comprehensive verification workflow and independent evidence generation before reporting completion of engineering tasks.
---

# Skill: Verification Before Done & Evidence Generation

## 1. Objective

Enforce independent inspection, real terminal command execution, and attached verbatim evidence before declaring any task or PR complete.

## 2. 6-Step Verification Workflow

1. **Review Task Scope**: Verify deliverables systematically against assignment checklist.
2. **Static Quality Checks**:
   - `ruff check .` (Linter validation).
   - `ruff format --check .` (Formatting validation).
   - `mypy .` (Type integrity check, 0 errors).
3. **OpenAPI Schema Contract Validation**:
   - `python manage.py spectacular --validate --fail-on-warn` (drf-spectacular schema validation).
4. **Automated Test Execution**:
   - `pytest -v --cov=apps --cov-report=term-missing` (Pass rate 100%, line coverage >= 80%).
5. **Database Schema Authority & Parity**:
   - `pytest tests/test_schema_parity.py` (Live PostgreSQL 18.6 vs unmanaged models parity).
   - `git status db/ .github/workflows/01-db-schema-check.yml` (Ensure frozen files are 100% byte-identical).
6. **Security & Repository Hygiene Scan**:
   - `python manage.py check --deploy` (Deployment security flags).
   - `git status --ignored` (Ensure zero secrets, dumps, or private keys are tracked).

## 3. Evidence Report Template

```markdown
## VERIFICATION EVIDENCE
- Ruff Lint: `ruff check .` -> All checks passed!
- Ruff Format: `ruff format --check .` -> XX files already formatted
- Mypy: `mypy .` -> Success: no issues found
- OpenAPI Contract: `spectacular --validate --fail-on-warn` -> Schema valid with 0 warnings
- Tests & Coverage: `pytest -v --cov=apps` -> 53 passed, coverage >= 80%
- DB Parity: `test_schema_parity.py` -> 13 passed, 100% parity
- Schema Authority: `git status db/` -> Clean (100% byte-identical)
- Deploy check: `check --deploy` -> 0 issues identified
```

## 4. Verification Checklist

- [ ] No fabricated test outputs, dummy facades, or simulated strings.
- [ ] Verification commands executed live with verbatim output recorded.
- [ ] All defects caught during verification are remediated before handover.
