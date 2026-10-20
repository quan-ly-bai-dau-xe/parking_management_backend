"""
Test settings.
"""

from .base import *

# Use in-memory database for testing
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}


# Disable migrations for faster tests
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None


MIGRATION_MODULES = DisableMigrations()

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
