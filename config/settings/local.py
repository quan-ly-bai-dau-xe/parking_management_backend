"""
Local development settings.
"""

from .base import *

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-local-development-key-override-in-production"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Use SQLite for development (easier setup)
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
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
