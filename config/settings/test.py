"""
Test settings.
"""
import os
from .base import *

# Use in-memory database for testing
# DATABASES = {
#     "default": {
#         "ENGINE": "django.db.backends.sqlite3",
#         "NAME": ":memory:",
#     }
# }


DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "parking_ci_test"),
        "USER": os.environ.get("POSTGRES_USER", "postgres"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "postgres"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

# Disable migrations for faster tests
# class DisableMigrations:
#     def __contains__(self, item):
#         return True

#     def __getitem__(self, item):
#         return None


# MIGRATION_MODULES = DisableMigrations()

# Password hashing for testing (faster)
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable file system storage during testing
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"

# Test runner
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# Seed password for test users
SEED_PASSWORD = "testpass123"

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
