# Documentation Index — Car Parking Lot Management System Backend

This directory contains the verified requirements specifications and Architecture Decision Records (ADRs) for `parking_management_backend`.

## 1. Requirements Specifications (`docs/requirements/`)

The single source of truth for functional and non-functional requirements extracted and verified from the SRS:

- [`00-srs-catalog.md`](requirements/00-srs-catalog.md): Comprehensive SRS requirements catalog and field-level traceability matrix.
- [`01-open-questions.md`](requirements/01-open-questions.md): Prioritized open questions (OQ-01 to OQ-51) and proposed default assumptions.
- [`02-scope-additions-from-plan.md`](requirements/02-scope-additions-from-plan.md): Scope additions verified from project plan and wireframes.
- [`03-delete-rules-catalog.md`](requirements/03-delete-rules-catalog.md): Complete entity deletion governance, immutability, and dependency guard matrix.
- [`04-dod-and-quality-check.md`](requirements/04-dod-and-quality-check.md): Definition of Done (DoD) criteria and quality verification gates.
- [`05-proposed-messages.md`](requirements/05-proposed-messages.md): Canonical error, warning, and confirmation message inventory.

## 2. Architecture Decision Records (`docs/adr/`)

Formal architectural decisions governing backend technology, security, and data integrity:

- [`0001-fixed-tech-stack-and-lts-roadmap.md`](adr/0001-fixed-tech-stack-and-lts-roadmap.md): Technology stack version pins (Python 3.14.7, Django 6.1.2, Postgres 18.6) and LTS upgrade roadmap.
- [`0002-git-branching-and-collaboration-workflow.md`](adr/0002-git-branching-and-collaboration-workflow.md): Git branching model (`dev`-centric), commit conventions, and peer review policy.
- [`0003-data-deletion-soft-delete-protect-and-audit.md`](adr/0003-data-deletion-soft-delete-protect-and-audit.md): Soft delete architecture, `models.PROTECT`, service-layer guards, and audit trail.
- [`0004-authentication-session-and-remember-token.md`](adr/0004-authentication-session-and-remember-token.md): Session authentication with CSRF for SPA and persistent remember token design.
- [`0005-local-docker-compose-for-postgresql.md`](adr/0005-local-docker-compose-for-postgresql.md): Local PostgreSQL 18.6 container environment and volume mount specification (`/var/lib/postgresql`).

## 3. Database Catalog & Physical Schema (`db/`)

Physical PostgreSQL 18.6 schema definitions, seed catalog, and execution guides:

- [`00-README.md`](../db/00-README.md): Database architecture guide, entity directory, execution instructions, and design decisions.
- [`01-schema.sql`](../db/01-schema.sql): Canonical PostgreSQL 18.6 DDL script with surrogate identity keys, natural business codes, btree_gist exclusion constraints, soft-delete partial indexes, and statistical views.
- [`02-seed.sql`](../db/02-seed.sql): Production-safe lookup and reference seed data for positions, vehicle types, ticket types, and administrative boundaries.
- [`03-erd.puml`](../db/03-erd.puml): PlantUML enterprise Entity-Relationship Diagram (ERD) source with Crow's Foot notation across 19 tables and 4 analytical views.
- [`04-erd.png`](../db/04-erd.png): High-resolution rendered ERD diagram (3838 x 3194 px, >= 3000px width) covering full PostgreSQL 18.6 schema.
