---
name: 11-verification-before-done
description: Comprehensive verification workflow and independent evidence generation before reporting completion of engineering tasks.
---

# Skill: Verification Before Done & Evidence Generation

## 1. Objective

Enforce independent inspection, real terminal command execution, and attached verbatim evidence before declaring any task or PR complete.

## 2. 5-Step Verification Workflow

1. **Review Task Scope**: Verify deliverables systematically against assignment checklist.
2. **Static Quality Checks**:
   - `ruff check . && ruff format --check .` (Format and style).
   - `mypy .` (Type integrity).
3. **Automated Test Execution**:
   - `pytest --cov=apps --cov-report=term-missing` (Pass rate 100%, coverage >= 80%).
4. **Schema Integrity Check**:
   - `python manage.py makemigrations --check --dry-run` (No uncommitted schema changes).
5. **Security & Repository Hygiene Scan**:
   - `python manage.py check --deploy` (Deployment security flags).
   - `git status --ignored` (Ensure zero secrets, dumps, or private keys are tracked).

## 3. Evidence Report Template

```markdown
## VERIFICATION EVIDENCE
- Static checks: `ruff check .` -> Passed cleanly
- Tests: `pytest` -> XX passed, 0 failures, coverage >= 80%
- Migrations: `makemigrations --check --dry-run` -> No changes detected
- Deploy check: `check --deploy` -> 0 issues identified
```

## 4. Verification Checklist

- [ ] No fabricated test outputs, dummy facades, or simulated strings.
- [ ] Verification commands executed live with verbatim output recorded.
- [ ] All defects caught during verification are remediated before handover.
