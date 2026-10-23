"""
Django settings for config project.
"""

import os
from pathlib import Path
from datetime import timedelta
from django.core.exceptions import ImproperlyConfigured
import dj_database_url

# ========================
# Base
# ========================

BASE_DIR = Path(__file__).resolve().parent.parent


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "on")


def env_list(name, default=""):
    value = os.environ.get(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


# Load .env file manually — strip both key and value to handle spaces around "="
env_path = BASE_DIR / ".env"
if env_path.exists():
    with open(env_path) as env_file:
        for line in env_file:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                key, _, value = stripped.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

# ========================
# Security
# ========================

# Accept both DJANGO_SECRET_KEY (preferred) and legacy SECRET_KEY.
# Neither may be empty — raise early rather than running with a weak key.
_secret_key = os.environ.get("DJANGO_SECRET_KEY") or os.environ.get("SECRET_KEY", "")
if not _secret_key:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY environment variable is not set. "
        "Copy .env.example to .env and set a strong random key. "
        'Generate one with: python -c "from django.core.management.utils import '
        'get_random_secret_key; print(get_random_secret_key())"'
    )
SECRET_KEY = _secret_key

GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "")
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "")
GOOGLE_BROWSER_MAPS_API_KEY = (
    os.environ.get("GOOGLE_BROWSER_MAPS_API_KEY", "")
    or GOOGLE_PLACES_API_KEY
    or GOOGLE_MAPS_API_KEY
)

DEBUG = env_bool("DJANGO_DEBUG", False)

ALLOWED_HOSTS = [
    "tizahab-web.onrender.com",
    "localhost",
    "127.0.0.1",
]

# ========================
# Applications
# ========================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "tailwind",
    "theme",
    "core",
    "accounts",
    "events",
    "rest_framework",
    "rest_framework.authtoken",
    "rest_framework_simplejwt",
    "daily_plan",
    "social_django",
]

# Match the five project primary keys already declared in historical migrations.
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PARSER_CLASSES": (
        "core.parsers.ObjectJSONParser",
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ),
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 100,
    "DEFAULT_THROTTLE_RATES": {
        "login": os.environ.get("LOGIN_RATE_LIMIT", "100/hour"),
        "signup": os.environ.get("SIGNUP_RATE_LIMIT", "20/hour"),
        "change_password": os.environ.get("CHANGE_PASSWORD_RATE_LIMIT", "30/hour"),
    },
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}

SIMPLE_JWT = {
    "CHECK_REVOKE_TOKEN": True,
    "TOKEN_REFRESH_SERIALIZER": "accounts.tokens.PasswordAwareRefreshSerializer",
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

TAILWIND_APP_NAME = "theme"

# Provider access is opt-in; live reads never depend on these jobs.
CATALOG_SYNC_ENABLED = os.environ.get("CATALOG_SYNC_ENABLED", "false").lower() == "true"
CATALOG_USER_AGENT = os.environ.get("CATALOG_USER_AGENT", "")

# ========================
# Middleware
# ========================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise must be directly after SecurityMiddleware so it can serve
    # compressed static files before any auth/session logic runs.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.NoIndexMiddleware",
    "social_django.middleware.SocialAuthExceptionMiddleware",
]

ROOT_URLCONF = "config.urls"

# ========================
# Templates
# ========================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.google_maps_api_key",
                "core.context_processors.language_switch_next",
                "social_django.context_processors.backends",
                "social_django.context_processors.login_redirect",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ========================
# Database
# ========================

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}",
        conn_max_age=600,
        conn_health_checks=True,
    )
}

# ========================
# Auth
# ========================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = [
    "social_core.backends.google.GoogleOAuth2",
    "social_core.backends.facebook.FacebookOAuth2",
    "django.contrib.auth.backends.ModelBackend",
]

SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", "")

SOCIAL_AUTH_FACEBOOK_KEY = os.environ.get("FACEBOOK_APP_ID", "")
SOCIAL_AUTH_FACEBOOK_SECRET = os.environ.get("FACEBOOK_APP_SECRET", "")

SOCIAL_AUTH_LOGIN_REDIRECT_URL = "/home/"
SOCIAL_AUTH_LOGIN_ERROR_URL = "/login/"

SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]
SOCIAL_AUTH_FACEBOOK_SCOPE = ["email"]
SOCIAL_AUTH_FACEBOOK_PROFILE_EXTRA_PARAMS = {"fields": "id,name,email"}

# ========================
# Internationalization
# ========================

LANGUAGE_CODE = "en"

TIME_ZONE = "Asia/Riyadh"

USE_I18N = True
USE_L10N = True
USE_TZ = True

LANGUAGES = [
    ("en", "English"),
    ("ar", "Arabic"),
]

LOCALE_PATHS = [
    BASE_DIR / "locale",
]

# ========================
# Static
# ========================

STATIC_URL = "/static/"

# Where collectstatic writes files for production serving by WhiteNoise / CDN.
# Must NOT overlap with any path inside STATICFILES_DIRS.
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# WhiteNoise: compress files and append content-hash to filenames for
# cache-busting. Requires `python manage.py collectstatic` before deployment.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# ========================
# Email
# ========================
# Default: console backend so password-reset emails print to stdout in dev.
# Production: set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# and supply SMTP credentials via environment variables.

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").strip().lower() in (
    "true",
    "1",
    "yes",
)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@tizahab.com")

# ========================
# Logging
# ========================

from config.logging_config import LOGGING_CONFIG as _LOGGING_CONFIG

LOGGING = _LOGGING_CONFIG


# ========================
# Custom Settings
# ========================

# API Rate Limiting
API_RATE_LIMIT = os.environ.get("API_RATE_LIMIT", "100/hour")

# Max events per API response
MAX_EVENTS_PER_RESPONSE = 100

# Daily plan batch size
DAILY_PLAN_BATCH_SIZE = 5

# ========================
# Production Security
# ========================

if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = "DENY"
    CSRF_TRUSTED_ORIGINS = [
        "https://tizahab-web-06kt.onrender.com",
    ]

    ALLOWED_HOSTS = env_list(
        "DJANGO_ALLOWED_HOSTS", "tizahab-web-06kt.onrender.com,localhost,127.0.0.1"
    )

    # Required for reverse proxy
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    USE_X_FORWARDED_HOST = True

    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True

    SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", False)

    if env_bool("DJANGO_ENABLE_HSTS", SECURE_SSL_REDIRECT):
        SECURE_HSTS_SECONDS = 31536000
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True
