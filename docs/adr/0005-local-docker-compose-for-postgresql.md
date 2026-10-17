# ADR-0005: Local PostgreSQL 18 via Docker Compose Environment

- **Status**: Proposed - pending Owner approval
- **Date**: 2026-10-11
- **Deciders**: Owner, Tech Lead, Engineering Team
- **Technical Context**: Local Database Infrastructure, PG18 Persistence & Security Boundary

## 1. Context & Problem Statement

Developers require a repeatable, local PostgreSQL 18 environment matching production runtime without native host installation. We must ensure reliable volume persistence and prevent credential leakage or unauthorized network exposure.

## 2. Decision Outcome

### 2.1. Container Image & Volume Mount Fact

- **Image**: `postgres:18.6-alpine` (strictly pinned).
- **PG18 Volume Mount Fact**: PostgreSQL 18 defines `PGDATA=/var/lib/postgresql/18/docker` and `VOLUME /var/lib/postgresql`. Therefore, the named volume `postgres_data` (name `parking_postgres_data`) MUST be mounted directly at `/var/lib/postgresql` (never at `/var/lib/postgresql/data`) to prevent Docker from creating dangling anonymous volumes and causing silent data loss on container recreation.

### 2.2. Network Security Boundary

- The database port is bound exclusively to the local loopback interface: `127.0.0.1:${POSTGRES_PORT:-5432}:5432`. Wildcard binding (`0.0.0.0`) is strictly forbidden to prevent LAN/Wi-Fi exposure.

### 2.3. Canonical `docker-compose.yml` Specification

```yaml
services:
  db:
    image: postgres:18.6-alpine
    restart: unless-stopped
    ports:
      - "127.0.0.1:${POSTGRES_PORT:-5432}:5432"
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-parking_db}
      POSTGRES_USER: ${POSTGRES_USER:-parking_user}
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:?Error: POSTGRES_PASSWORD is required}"
    volumes:
      - postgres_data:/var/lib/postgresql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-parking_user} -d ${POSTGRES_DB:-parking_db}"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  postgres_data:
    name: parking_postgres_data
```

### 2.4. Environment Credentials

- Passwords must never be committed to git. Credentials are configured via local `.env` copied from `.env.example`.

## 3. Consequences & References

- **Consequences**: Zero accidental data loss upon container restart; safe loopback-only network exposure; automated healthchecks via `pg_isready`.
- PostgreSQL Docker Official: <https://hub.docker.com/_/postgres>
- Docker Compose Environment: <https://docs.docker.com/compose/environment-variables/>
