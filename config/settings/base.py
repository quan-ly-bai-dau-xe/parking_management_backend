"""
Django settings for config project.
Shared core settings for all environments.

For more information on this file, see
https://docs.djangoproject.com/en/6.1/topics/settings/
"""

from decimal import Decimal
from pathlib import Path

import environ

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Initialize environment variables
env = environ.Env(
    # Set casting and default values
    DEBUG=(bool, False),
    SECRET_KEY=(str, ""),
    ALLOWED_HOSTS=(list, []),
    POSTGRES_DB=(str, ""),
    POSTGRES_USER=(str, ""),
    POSTGRES_PASSWORD=(str, ""),
    POSTGRES_HOST=(str, ""),
    POSTGRES_PORT=(str, ""),
    DB_CONN_MAX_AGE=(int, 60),
    DB_SSLMODE=(str, "prefer"),
    DB_POOL_ENABLE=(bool, False),
    DB_CONN_HEALTH_CHECKS=(bool, True),
    DB_POOL_MIN_SIZE=(int, 2),
    DB_POOL_MAX_SIZE=(int, 8),
    DB_POOL_TIMEOUT=(float, 10.0),
)

# Read environment variables from .env file
environ.Env.read_env(BASE_DIR / ".env")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env("DEBUG")

ALLOWED_HOSTS = env("ALLOWED_HOSTS")


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party apps
    "corsheaders",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    # Local apps
    "apps.core",
    "apps.accounts",
    "apps.customers",
    "apps.employees",
    "apps.vehicles",
    "apps.tickets",
    "apps.parking",
    "apps.content",
    "apps.audit",
    "apps.reports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.accounts.middleware.PersistentRememberMeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Database
# https://docs.djangoproject.com/en/6.1/ref/settings/#databases

DB_POOL_ENABLE = env("DB_POOL_ENABLE")
DB_CONN_HEALTH_CHECKS = env("DB_CONN_HEALTH_CHECKS")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("POSTGRES_HOST"),
        "PORT": env("POSTGRES_PORT"),
        "CONN_MAX_AGE": 0 if DB_POOL_ENABLE else env("DB_CONN_MAX_AGE"),
        "CONN_HEALTH_CHECKS": DB_CONN_HEALTH_CHECKS,
        "OPTIONS": {
            "sslmode": env("DB_SSLMODE"),
            **(
                {
                    "pool": {
                        "min_size": env("DB_POOL_MIN_SIZE"),
                        "max_size": env("DB_POOL_MAX_SIZE"),
                        "timeout": env("DB_POOL_TIMEOUT"),
                    }
                }
                if DB_POOL_ENABLE
                else {}
            ),
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Password hashers
# https://docs.djangoproject.com/en/6.1/topics/auth/passwords/#how-django-stores-passwords
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]


# Internationalization
# https://docs.djangoproject.com/en/6.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.1/howto/static-files/

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media files (User uploads)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ==============================================================================
# Parking Domain & Storage Settings (J6)
# ==============================================================================
# MAX_IMAGE_SIZE_MB: Maximum allowed scan image file size in Megabytes.
# Safe range: 1 to 50 MB (Default: 5 MB).
MAX_IMAGE_SIZE_MB: int = env.int("MAX_IMAGE_SIZE_MB", default=5)

# PARKING_HOURLY_RATE_VND: Standard hourly parking tariff for ad-hoc customers.
# Safe range: >= 1000.00 VND (Default: 10000.00 VND).
PARKING_HOURLY_RATE_VND: Decimal = Decimal(
    env.str("PARKING_HOURLY_RATE_VND", default="10000.00")
)

# PARKING_OCR_ENGINE: Backend license plate recognition engine.
# Permitted: "fast_alpr", "dual_ensemble", "dummy" (test environment only).
PARKING_OCR_ENGINE: str = env.str("PARKING_OCR_ENGINE", default="fast_alpr")
if PARKING_OCR_ENGINE == "dummy":
    import os

    from django.core.exceptions import ImproperlyConfigured

    current_settings = os.environ.get("DJANGO_SETTINGS_MODULE", "")
    if current_settings and current_settings != "config.settings.test":
        raise ImproperlyConfigured(
            "PARKING_OCR_ENGINE='dummy' is only permitted under 'config.settings.test'. "
            f"Current DJANGO_SETTINGS_MODULE is '{current_settings}'."
        )

# ==============================================================================
# OCR Accuracy & Review Policy Calibration Settings (J3, J6)
# ==============================================================================
# PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD: Minimum character confidence (%) required
# for automated approval (AUTO). Calibrated to 90.0% to reject Row 0 (min_conf 88.50%),
# achieving wrong-in-AUTO 0.99% <= 1.0% and AUTO coverage 93.79% >= 90.0% on 322 dataset.
# Safe range: 80.0% to 99.0% (Default: 90.0%).
PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD: float = env.float(
    "PARKING_OCR_AUTO_CONFIDENCE_THRESHOLD", default=90.0
)

# PARKING_OCR_ADAPTIVE_ENSEMBLE: When True, bypasses Model 2 (Mobile-ViT-v2) if
# Model 1 (CCT-xs-v2) achieves high confidence, reducing inference CPU by ~50%.
# Safe range: True or False (Default: True).
PARKING_OCR_ADAPTIVE_ENSEMBLE: bool = env.bool(
    "PARKING_OCR_ADAPTIVE_ENSEMBLE", default=True
)

# PARKING_OCR_ADAPTIVE_THRESHOLD: Minimum per-character confidence (%) required
# on Model 1 to trigger adaptive single-pass bypass.
# Safe range: 85.0% to 99.0% (Default: 94.0%).
PARKING_OCR_ADAPTIVE_THRESHOLD: float = env.float(
    "PARKING_OCR_ADAPTIVE_THRESHOLD", default=94.0
)

# PARKING_OCR_LEADING_CHAR_THRESHOLD: Minimum confidence (%) for leading province
# character required on Model 1 to trigger adaptive single-pass bypass.
# Safe range: 90.0% to 99.9% (Default: 99.2%).
PARKING_OCR_LEADING_CHAR_THRESHOLD: float = env.float(
    "PARKING_OCR_LEADING_CHAR_THRESHOLD", default=99.2
)

# PARKING_OCR_ADAPTIVE_AVG_THRESHOLD: Minimum average character confidence (%)
# required on Model 1 for adaptive single-pass bypass.
# Safe range: 85.0% to 99.0% (Default: 96.0%).
PARKING_OCR_ADAPTIVE_AVG_THRESHOLD: float = env.float(
    "PARKING_OCR_ADAPTIVE_AVG_THRESHOLD", default=96.0
)

# PARKING_OCR_CROP_MARGIN: Margin pixels added around bounding box prior to OCR.
# Safe range: 0 to 20 pixels (Default: 4).
PARKING_OCR_CROP_MARGIN: int = env.int("PARKING_OCR_CROP_MARGIN", default=4)

# ==============================================================================
# Review Policy Secondary Signal Thresholds (H7, J6)
# ==============================================================================
# PARKING_REVIEW_DETECTOR_CONF_THRESHOLD: Detector box confidence (%) threshold.
# Below this threshold, review reason LOW_DETECTION_CONFIDENCE is triggered.
# Safe range: 50.0% to 95.0% (Default: 80.0%).
PARKING_REVIEW_DETECTOR_CONF_THRESHOLD: float = env.float(
    "PARKING_REVIEW_DETECTOR_CONF_THRESHOLD", default=80.0
)

# PARKING_REVIEW_MIN_ASPECT_RATIO: Bounding box width/height ratio minimum.
# Below this threshold, review reason IRREGULAR_ASPECT_RATIO is triggered.
# Safe range: 1.0 to 2.0 (Default: 1.3).
PARKING_REVIEW_MIN_ASPECT_RATIO: float = env.float(
    "PARKING_REVIEW_MIN_ASPECT_RATIO", default=1.3
)

# PARKING_REVIEW_MAX_ASPECT_RATIO: Bounding box width/height ratio maximum.
# Above this threshold, review reason IRREGULAR_ASPECT_RATIO is triggered.
# Safe range: 4.0 to 10.0 (Default: 6.0).
PARKING_REVIEW_MAX_ASPECT_RATIO: float = env.float(
    "PARKING_REVIEW_MAX_ASPECT_RATIO", default=6.0
)

# PARKING_REVIEW_MIN_SHARPNESS: Crop image Laplacian variance sharpness threshold.
# Below this threshold, review reason LOW_IMAGE_SHARPNESS is triggered.
# Safe range: 10.0 to 100.0 (Default: 30.0).
PARKING_REVIEW_MIN_SHARPNESS: float = env.float(
    "PARKING_REVIEW_MIN_SHARPNESS", default=30.0
)

# ==============================================================================
# Concurrency & Backpressure Settings (H3, J2)
# ==============================================================================
# Invariant: GUNICORN_THREADS (6) > PARKING_OCR_CONCURRENCY_LIMIT (4)
PARKING_OCR_CONCURRENCY_LIMIT: int = env.int("PARKING_OCR_CONCURRENCY_LIMIT", default=4)
PARKING_OCR_QUEUE_TIMEOUT: float = env.float("PARKING_OCR_QUEUE_TIMEOUT", default=2.0)
PARKING_OCR_RETRY_AFTER: int = env.int("PARKING_OCR_RETRY_AFTER", default=3)

# ==============================================================================
# ONNX Runtime Execution Settings (H4, H8a, J6)
# ==============================================================================
ONNX_INTRA_OP_THREADS: int = env.int("ONNX_INTRA_OP_THREADS", default=1)
ONNX_INTER_OP_THREADS: int = env.int("ONNX_INTER_OP_THREADS", default=1)
ONNX_ALLOW_SPINNING: bool = env.bool("ONNX_ALLOW_SPINNING", default=False)
PARKING_OCR_MODELS_DIR: str = env.str(
    "PARKING_OCR_MODELS_DIR",
    default=env.str("OCR_MODELS_DIR", default="/app/models/ocr"),
)
OCR_MODELS_DIR: str = PARKING_OCR_MODELS_DIR


def get_validated_ocr_models_dir(
    configured_path: str | Path | None = None,
) -> Path:
    """
    Validates and resolves the baked ONNX models directory (Standard 4 & H4d).
    Raises FileNotFoundError with an actionable diagnostic message if the directory does not exist.
    """
    target = Path(configured_path or PARKING_OCR_MODELS_DIR)
    if not target.is_dir():
        raise FileNotFoundError(
            f"OCR models directory '{target}' does not exist or is not a directory. "
            "Please configure PARKING_OCR_MODELS_DIR to point to valid ONNX model files."
        )
    return target


# ==============================================================================
# Observability & Log Privacy Mode (Rule 07, J9)
# ==============================================================================
PARKING_LOG_PRIVACY_MODE: bool = env.bool(
    "PARKING_LOG_PRIVACY_MODE",
    default=env.bool("PARKING_LOG_MASK_PLATES", default=True),
)
PARKING_LOG_MASK_PLATES: bool = PARKING_LOG_PRIVACY_MODE

# Default primary key field type
# https://docs.djangoproject.com/en/6.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Custom user model
AUTH_USER_MODEL = "accounts.Account"

# Silenced system checks for unmanaged models & partial unique index auth
SILENCED_SYSTEM_CHECKS = ["auth.W004", "fields.W342"]

# Django REST Framework settings
REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardResultsSetPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
}

# drf-spectacular settings
SPECTACULAR_SETTINGS = {
    "TITLE": "Parking Management API",
    "DESCRIPTION": (
        "Backend REST API for Car Parking Lot Management System per SRS 4.5.1 and ADR-0004.\n\n"
        "### Authentication & CSRF Protection\n"
        "- This API uses **SessionAuthentication** (`sessionid` cookie).\n"
        "- All unsafe HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`) require the **`X-CSRFToken`** header "
        "matching the value of the `csrftoken` cookie.\n"
        "- When executing 'Try it out' in Swagger UI with session authentication, ensure you pass the "
        "`X-CSRFToken` header or mint an authenticated session as documented in `README.md`.\n\n"
        "### Error Envelope\n"
        "- All error responses follow the standard envelope format: `{'code': '...', 'message': '...', 'details': {...}}`."
    ),
    "VERSION": "v2.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_SETTINGS": {
        "deepLinking": True,
        "persistAuthorization": True,
        "withCredentials": True,
    },
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
    "ENUM_NAME_OVERRIDES": {
        "RecognitionSourceEnum": "apps.parking.models.VehicleEntryExitLog.RECOGNITION_SOURCE_CHOICES",
        "VehicleEntryExitReviewStatusEnum": "apps.parking.models.VehicleEntryExitLog.REVIEW_STATUS_CHOICES",
        "PlateScanReviewStatusEnum": "apps.parking.enums.ReviewStatus.CHOICES",
        "ReviewReasonEnum": "apps.parking.enums.ReviewReasonCode.CHOICES",
    },
}

# Logging configuration
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
    },
}

# ==============================================================================
# CORS & CSRF Settings (Rule 07, ADR-0004, TL-52, TL-53)
# ==============================================================================
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_ALL_ORIGINS = False
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])
CSRF_COOKIE_HTTPONLY = False
CSRF_FAILURE_VIEW = "apps.accounts.views.csrf.custom_csrf_failure_view"


# ==============================================================================
# Session & Cookie Security (Rule 07, ADR-0004, TL-53)
# ==============================================================================
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=43200)

# ==============================================================================
# Persistent Remember-Me Token Settings (OQ-87, ADR-0004, TL-53)
# ==============================================================================
REMEMBER_COOKIE_NAME = "parking_remember_token"
REMEMBER_ROTATION_GRACE_SECONDS = env.int("REMEMBER_ROTATION_GRACE_SECONDS", default=30)
REMEMBER_TOKEN_LIFETIME_DAYS = env.int("REMEMBER_TOKEN_LIFETIME_DAYS", default=30)
REMEMBER_MAX_TOKENS_PER_ACCOUNT = env.int("REMEMBER_MAX_TOKENS_PER_ACCOUNT", default=10)

# ==============================================================================
# Authentication Throttle Limits (ADR-0004, TL-53)
# ==============================================================================
AUTH_THROTTLE_PAIR_LIMIT = env.int("AUTH_THROTTLE_PAIR_LIMIT", default=5)
AUTH_THROTTLE_IDENTIFIER_LIMIT = env.int("AUTH_THROTTLE_IDENTIFIER_LIMIT", default=20)
AUTH_THROTTLE_IP_LIMIT = env.int("AUTH_THROTTLE_IP_LIMIT", default=30)
AUTH_THROTTLE_WINDOW_SECONDS = env.int("AUTH_THROTTLE_WINDOW_SECONDS", default=900)

# DRF Proxy Configuration
NUM_PROXIES = env.int("NUM_PROXIES", default=0)
