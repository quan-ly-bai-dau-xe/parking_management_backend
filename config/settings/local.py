"""
Local development settings.
"""

from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
# SECRET_KEY is loaded from environment variables via environ.Env (inherited from base.py)
SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG", default=True)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1", "[::1]"])

# PostgreSQL 18.6 database configuration loaded from environment variables
# (POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_HOST, POSTGRES_PORT)
# SQLite configuration completely removed per architecture specification.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST"),
        "PORT": env("POSTGRES_PORT"),
        "CONN_MAX_AGE": env("DB_CONN_MAX_AGE", default=60),
        "OPTIONS": {
            "sslmode": env("DB_SSLMODE", default="prefer"),
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

# Logging
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
        # Enable SQL logging for development
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG",
        },
    },
}
