# Rule 02: Frontend Design Primary Source & SRS Secondary Source of Truth

## 1. Source of Truth Hierarchy

- **Primary Source — Frontend Design (`FE`)**: The 11 Frontend UI screens in `Parking Project` and the Team Lead decisions (`TL-01`–`TL-16`) recorded in `docs/requirements/06-frontend-srs-db-alignment.md` are the **primary source of truth** for screens, fields, labels, status values, filters, and workflows.
- **Secondary Source — SRS v4.1 (`SRS`)**: The software requirements catalog in `docs/requirements/00-srs-catalog.md` and delete rules in `docs/requirements/03-delete-rules-catalog.md` are the **secondary source of truth** and apply only where the Frontend design is silent.
- **Tertiary Source — Explicit Proposals (`[PROPOSAL]`)**: Any requirement, status value, tariff rule, or message not explicitly defined in the Frontend or SRS must be tagged `[PROPOSAL]` and registered in `docs/requirements/01-open-questions.md` and `docs/requirements/05-proposed-messages.md`.
- Every database table, column, constraint, API endpoint, serializer field, and validation check must trace directly to a `TL-XX` decision, a Frontend screen item (`S01`–`S11`), an SRS `REQ-*` / `ACT-*` / `MSG-*` ID, or a `DEL-*` / `PROP-*` rule.

## 2. Prohibition of Unapproved Fabrication

- **NEVER** invent screens, fields, validation constraints, business rules, or user roles not grounded in the Frontend design (`06-frontend-srs-db-alignment.md`) or SRS (`00-srs-catalog.md`).
- **NEVER** alter Frontend UI labels or verbatim SRS Vietnamese error/success message strings.

## 3. Handling Ambiguities and Contradictions

- When the Frontend design and the SRS conflict, the **Frontend design takes precedence** per `TL-01`–`TL-16` in `docs/requirements/06-frontend-srs-db-alignment.md`.
- When both the Frontend and the SRS are silent or ambiguous, consult `docs/requirements/01-open-questions.md`:
  1. Follow the documented **Proposed Default Assumption** tagged `[PROPOSAL]`.
  2. Cite the corresponding `OQ-XX` identifier in code comments and PR descriptions.
  3. Escalate unresolved blockers to the designated owner (**Product Owner** for business rules; **Team Lead** for technical architecture).
