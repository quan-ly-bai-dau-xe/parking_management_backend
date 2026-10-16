# ADR-0001: Fixed Tech Stack and Django LTS Roadmap

- **Status**: Proposed - pending Owner approval
- **Date**: 2026-10-11
- **Deciders**: Owner, Tech Lead, Engineering Team
- **Technical Context**: Car Parking Lot Management System Backend

## 1. Context & Problem Statement

The backend requires an enterprise-grade REST API stack. We formalize the fixed runtime versions, evaluate DRF vs Django Ninja, forbid Python 3.15, and establish the Django LTS upgrade path.

## 2. Decision Outcome: Fixed Versions Matrix

1. **Python**: `3.14.7` (Host runtime).
2. **Django**: `6.1.2` (Framework core).
3. **Database**: PostgreSQL `18.6` (Docker image `postgres:18.6-alpine`).
4. **API Framework**: Django REST Framework (DRF) `3.18.3` (Selected over Django Ninja for battle-tested serializers, permissions, and mature ecosystem).
5. **Database Adapter**: `psycopg 3.3.6` (`psycopg[binary]==3.3.6` in development).

### Python 3.15 Prohibition

- **Policy**: Python `3.15.0` is strictly forbidden.
- **Rationale**: Per official Django FAQ ("What Python version can I use with Django?"), Django 6.1 and 6.2 certify support exclusively for Python 3.12, 3.13, and 3.14. Running uncertified Python voids upstream stability guarantees.
- **Revisit Trigger**: Re-evaluate only when Django officially certifies Python 3.15 in release notes.

### Django 6.2 LTS Migration Roadmap

- **Current**: Django 6.1 standard release (support ends April 2027; extended support ends Dec 2027).
- **Target**: Django `6.2 LTS` releases in **April 2027** (supported through April 2030).
- **Plan**: Regression test against Django 6.2 release candidates in March 2027; upgrade upon release in April 2027.

### Proposed Auxiliary Libraries

- OpenAPI 3.0: `drf-spectacular`
- Query Filtering: `django-filter`
- Auth Tokens: `djangorestframework-simplejwt` (evaluated alongside session auth in [ADR-0004](0004-authentication-session-and-remember-token.md))

## 3. Consequences

- **Positive**: Fully reproducible environments, zero runtime version discrepancies, LTS upgrade path.
- **Negative**: Virtual environments strictly locked to Python 3.14.

## 4. References

- Python: <https://www.python.org/downloads/>
- Django FAQ: <https://docs.djangoproject.com/en/dev/faq/install/#what-python-version-can-i-use-with-django>
- Django Roadmap: <https://www.djangoproject.com/download/>
- DRF: <https://www.django-rest-framework.org/>
- PostgreSQL: <https://www.postgresql.org/docs/18/release-18.html>
- Psycopg 3: <https://www.psycopg.org/psycopg3/docs/>
