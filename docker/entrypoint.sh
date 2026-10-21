#!/bin/sh
set -eu

# Dynamic handling if container is launched as root (e.g. for automatic host volume permission fix)
if [ "$(id -u)" = "0" ]; then
    echo "[entrypoint] Running as root (UID 0): ensuring permissions on /app/media for appuser (UID 10001)..."
    mkdir -p /app/media/parking_scans
    chown -R appuser:appgroup /app/media
    if command -v gosu >/dev/null 2>&1; then
        exec gosu appuser /usr/local/bin/entrypoint.sh "$@"
    fi
fi

# Pre-flight check: Verify /app/media is writable by the current user
if [ "${SKIP_MEDIA_PERMISSION_CHECK:-0}" != "1" ] && [ -d "/app/media" ]; then
    if [ ! -w "/app/media" ]; then
        echo "================================================================================" >&2
        echo "CRITICAL CONFIGURATION ERROR: /app/media is NOT writable!" >&2
        echo "Current container user: $(id -u -n 2>/dev/null || echo 'UID') ($(id -u):$(id -g))" >&2
        echo "" >&2
        echo "On Linux host systems, bind mounts (-v ./media:/app/media) inherit host file" >&2
        echo "permissions. If the host directory is owned by a different UID (e.g. 1000 or 0)" >&2
        echo "with mode 755, unprivileged container UID 10001 cannot write scan images," >&2
        echo "leading to PermissionError [Errno 13] when uploading plates." >&2
        echo "" >&2
        echo "To resolve this on your Linux host, apply one of the following solutions:" >&2
        echo "  1) Adjust host directory ownership to container UID 10001:" >&2
        echo "     sudo chown -R 10001:10001 ./media" >&2
        echo "  2) Grant group write access on the host:" >&2
        echo "     chmod -R 775 ./media" >&2
        echo "  3) Configure docker-compose.yml to run as your host UID:" >&2
        echo "     user: \"\$(id -u):\$(id -g)\"" >&2
        echo "================================================================================" >&2
        exit 1
    fi
    mkdir -p /app/media/parking_scans 2>/dev/null || true
fi

# Wait for PostgreSQL database if POSTGRES_HOST is specified
if [ -n "${POSTGRES_HOST:-}" ]; then
    echo "Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT:-5432}..."
    while ! python -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(1)
try:
    s.connect(('${POSTGRES_HOST}', int('${POSTGRES_PORT:-5432}')))
    s.close()
    exit(0)
except Exception:
    exit(1)
" 2>/dev/null; do
        sleep 1
    done
    echo "PostgreSQL is available."
fi

# Apply database migrations if RUN_MIGRATIONS is enabled and POSTGRES_HOST is set
if [ "${RUN_MIGRATIONS:-1}" = "1" ] && [ -n "${POSTGRES_HOST:-}" ]; then
    echo "Applying database migrations..."
    python manage.py migrate --noinput
fi

# Load sample data if requested and POSTGRES_HOST is set (fail loudly, no silent fallback)
if [ "${LOAD_SAMPLE_DATA:-0}" = "1" ] && [ -n "${POSTGRES_HOST:-}" ]; then
    echo "Loading sample data..."
    python manage.py load_sample_data
fi

exec "$@"
