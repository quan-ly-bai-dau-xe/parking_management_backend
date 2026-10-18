"""
Test settings for PostgreSQL 18.6 per TL-46, TL-47, and TL-48.
"""

import secrets

from .base import *

# Generate runtime random secret key for tests if not set in environment
SECRET_KEY = env("SECRET_KEY", default="") or secrets.token_urlsafe(50)

# Ensure DEBUG is False during tests
DEBUG = env.bool("DEBUG", default=False)

# PostgreSQL 18.6 database configuration loaded from environment variables
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", default="parking_db"),
        "USER": env("POSTGRES_USER", default="postgres"),
        "PASSWORD": env("POSTGRES_PASSWORD", default=""),
        "HOST": env("POSTGRES_HOST", default="127.0.0.1"),
        "PORT": env("POSTGRES_PORT", default="5432"),
        "CONN_MAX_AGE": env.int("DB_CONN_MAX_AGE", default=0),
        "OPTIONS": {
            "sslmode": env("DB_SSLMODE", default="prefer"),
        },
    }
}

# Password hashers
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.Argon2PasswordHasher",
]

# Test runner
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# Logging during tests
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
