---
name: 01-requirement-extraction
description: Extract functional requirements, data fields, business rules, and verbatim SRS messages with stable citations and traceability matrices.
---

# Skill: Requirement Extraction & Traceability Matrix

## 1. Objective

This skill defines the standardized procedure for extracting and mapping business requirements from the primary Frontend-First specification (`docs/requirements/06-frontend-srs-db-alignment.md`) and secondary SRS catalog (`docs/requirements/00-srs-catalog.md`, where the Frontend is silent) into backend architectural components without fabricating specifications.

## 2. Step-by-Step Execution Workflow

1. **Step 1: Identify Target Screen / Use Case**:
   - Locate the target Frontend screen (`S01`–`S11`) and Team Lead decision (`TL-01`–`TL-35`) in `docs/requirements/06-frontend-srs-db-alignment.md` and `docs/requirements/07-fe-srs-traceability.md`, and consult `docs/requirements/00-srs-catalog.md` (Sections 4.1 through 4.8) where the Frontend is silent.
   - Review project plan scope additions in `docs/requirements/02-scope-additions-from-plan.md` if applicable.
2. **Step 2: Extract Field Inventory**:
   - Collect Stable IDs (`REQ-<Screen>-F<N>`), Field Name, Data Type, Maximum Length, Mandatory flag, and Default Value.
   - Record stable citations (Section + Table + Row, or wireframe image element).
3. **Step 3: Extract Actions and Verbatim Messages**:
   - Collect Action IDs (`ACT-<Screen>-A<N>`).
   - Copy verbatim success and error message strings (`MSG-<Screen>-M<N>`) and proposed messages (`PROP-*`, `PROP-DEL-*`). Strictly avoid rewriting, translating, or fabricating dialogue text.
4. **Step 4: Check Deletion and Destruction Rules**:
   - If the use case involves deletion, inspect the corresponding protection rules in `docs/requirements/03-delete-rules-catalog.md` (`DEL-01` through `DEL-06`).
5. **Step 5: Construct Traceability Matrix**:
   - Map each data field to a Django Model field / Serializer field.
   - Map each action to an API Endpoint / Service method.

## 3. Output Format Template

```markdown
### Use Case: [Use Case Name / Endpoint]
- **SRS Screen Identifier**: [e.g. SRS 4.3.2 Add Employee]
- **Source Citation**: [e.g. SRS 4.3.2, Table 6, Rows 5-13]

#### 1. Data Field Matrix
| Stable ID | Field Name | Data Type | Max Length | Required | Source Citation | Django Model / Serializer Mapping |
| :--- | :--- | :--- | :---: | :---: | :--- | :--- |
| REQ-... | ... | ... | ... | Yes/No | SRS ... | `models.CharField(...)` |

#### 2. Verbatim Message Matrix
| Stable ID | Type | Exact SRS Message Text | Trigger Condition | HTTP Status |
| :--- | :---: | :--- | :--- | :---: |
| MSG-... | Error/Success | `...` | ... | 400 / 200 |
```

## 4. Verification Checklist

- [ ] Every data field has a Stable ID and stable Section + Table + Row citation.
- [ ] Zero fabricated error messages (cross-verified against canonical catalog).
- [ ] Zero ungrounded validation rules (e.g. invented 18-60 age bounds).
- [ ] Decisions and proposals verified against `docs/requirements/01-decision-log.md`.
