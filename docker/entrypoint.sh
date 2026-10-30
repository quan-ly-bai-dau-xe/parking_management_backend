#!/bin/sh
set -eu

# Dynamic handling if container is launched as root: drop privileges to appuser (UID 10001)
if [ "$(id -u)" = "0" ]; then
    if command -v gosu >/dev/null 2>&1; then
        exec gosu appuser /usr/local/bin/entrypoint.sh "$@"
    fi
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
