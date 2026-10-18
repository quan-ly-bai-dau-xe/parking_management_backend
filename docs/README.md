# Documentation Index — Car Parking Lot Management System Backend

This directory contains the verified requirements specifications and Architecture Decision Records (ADRs) for `parking_management_backend`.

## 1. Requirements Specifications (`docs/requirements/`)

Requirements specifications under the Frontend-First (`FE-First`) hierarchy, where the Frontend design ([`06-frontend-srs-db-alignment.md`](requirements/06-frontend-srs-db-alignment.md)) is the primary source of truth and the SRS ([`00-srs-catalog.md`](requirements/00-srs-catalog.md)) is authoritative for the SRS content and secondary to the Frontend design (`TL-19`, `TL-22`):

- [`00-srs-catalog.md`](requirements/00-srs-catalog.md): Authoritative catalog of the SRS v4.1 content (secondary to the Frontend design).
- [`01-decision-log.md`](requirements/01-decision-log.md): Compact decision log (`OQ-01` to `OQ-84`) recording decided outcomes and deferrals (`TL-22`).
- [`02-scope-additions-from-plan.md`](requirements/02-scope-additions-from-plan.md): Scope additions verified from project plan and wireframes.
- [`03-delete-rules-catalog.md`](requirements/03-delete-rules-catalog.md): Complete entity deletion governance, immutability, and dependency guard matrix.
- [`04-dod-and-quality-check.md`](requirements/04-dod-and-quality-check.md): Definition of Done (DoD) criteria and quality verification gates.
- [`05-proposed-messages.md`](requirements/05-proposed-messages.md): Canonical error, warning, and confirmation message inventory.
- [`06-frontend-srs-db-alignment.md`](requirements/06-frontend-srs-db-alignment.md): Frontend-first specification, Team Lead decisions (`TL-01`–`TL-47`), and Schema v2 alignment record.
- [`07-fe-srs-traceability.md`](requirements/07-fe-srs-traceability.md): Bidirectional Frontend (11 UI screens) and SRS v4.1 requirements traceability matrix and `TL-28` SQL proof queries.

## 2. Architecture Decision Records (`docs/adr/`)

Formal architectural decisions governing backend technology, security, and data integrity:

- [`0001-fixed-tech-stack-and-lts-roadmap.md`](adr/0001-fixed-tech-stack-and-lts-roadmap.md): Technology stack version pins (Python 3.14.7, Django 6.1.2, Postgres 18.6) and LTS upgrade roadmap.
- [`0002-git-branching-and-collaboration-workflow.md`](adr/0002-git-branching-and-collaboration-workflow.md): Git branching model (`dev`-centric), commit conventions, and peer review policy.
- [`0003-data-deletion-soft-delete-protect-and-audit.md`](adr/0003-data-deletion-soft-delete-protect-and-audit.md): Soft delete architecture, `models.PROTECT`, service-layer guards, and audit trail.
- [`0004-authentication-session-and-remember-token.md`](adr/0004-authentication-session-and-remember-token.md): Session authentication with CSRF for SPA and persistent remember token design.
- [`0005-local-docker-compose-for-postgresql.md`](adr/0005-local-docker-compose-for-postgresql.md): Local PostgreSQL 18.6 container environment and volume mount specification (`/var/lib/postgresql`).
- [`0006-django-skeleton-v2-schema-authority.md`](adr/0006-django-skeleton-v2-schema-authority.md): PostgreSQL Schema v2 authority, unmanaged Django models (`managed = False`), `RunSQL` initial migration, and 3-tier API foundation.

## 3. Database Catalog & Physical Schema (`db/`)

Physical PostgreSQL 18.6 schema definitions, seed catalog, and execution guides:

- [`00-README.md`](../db/00-README.md): Database architecture guide, entity directory, execution instructions, and design decisions.
- [`01-schema.sql`](../db/01-schema.sql): Canonical PostgreSQL 18.6 DDL script with surrogate identity keys, natural business codes, btree_gist exclusion constraints, soft-delete partial indexes, and statistical views.
- [`02-seed.sql`](../db/02-seed.sql): Idempotent two-part seed script containing Part 1 reference lookup catalogs (`CAR`/`EV` car-only vehicle types, positions, ticket types, administrative units, parking lot) and Part 2 removable synthetic operational sample data.
- [`03-erd.asta`](../db/03-erd.asta): Native Astah UML 12.0.0 Entity-Relationship Diagram (ERD) model across `28` tables and `8` analytical views.
- [`04-erd.png`](../db/04-erd.png): High-resolution rendered Master ERD overview (`4486 x 1997 px`, `400` DPI) accompanied by module diagrams [`05-erd-account-staff.png`](../db/05-erd-account-staff.png)–[`09-erd-reference-views.png`](../db/09-erd-reference-views.png).
