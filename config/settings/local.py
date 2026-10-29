"""
Local development settings.
"""

from .base import *

# Validate and configure Cloudinary SDK for runtime
validate_cloudinary_credentials(
    CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
)
configure_cloudinary_sdk(
    CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET
)

# SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY is loaded from environment variables via environ.Env (inherited from base.py)
SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG", default=True)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"])

# PostgreSQL 18.6 database configuration loaded from environment variables
# (POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT)
# SQLite configuration completely removed per architecture specification.
DB_POOL_ENABLE = env.bool("DB_POOL_ENABLE", default=False)
DB_CONN_HEALTH_CHECKS = env.bool("DB_CONN_HEALTH_CHECKS", default=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST"),
        "PORT": env("POSTGRES_PORT"),
        "CONN_MAX_AGE": (
            0 if DB_POOL_ENABLE else env.int("DB_CONN_MAX_AGE", default=60)
        ),
        "CONN_HEALTH_CHECKS": DB_CONN_HEALTH_CHECKS,
        "OPTIONS": {
            "sslmode": env("DB_SSLMODE", default="prefer"),
            **(
                {
                    "pool": {
                        "min_size": env.int("DB_POOL_MIN_SIZE", default=2),
                        "max_size": env.int("DB_POOL_MAX_SIZE", default=8),
                        "timeout": env.float("DB_POOL_TIMEOUT", default=10.0),
                    }
                }
                if DB_POOL_ENABLE
                else {}
            ),
        },
    }
}

# Email backend for development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Development specific apps
INSTALLED_APPS += [
    # Add any development-only apps here
]

# Disable password validation for development (optional)
# AUTH_PASSWORD_VALIDATORS = []

# Logging: Rule 07 Section 5 compliance - default False to prevent customer PII leakage
LOG_SQL_QUERIES = env.bool("DJANGO_LOG_SQL_QUERIES", default=False)

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
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.parking": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # SQL logging silenced by default in container to protect customer PII
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG" if LOG_SQL_QUERIES else "WARNING",
            "propagate": False,
        },
    },
}
