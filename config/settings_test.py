"""Test settings for local pytest runs."""

import os

# Tests run without a real .env file or production credentials.
os.environ.setdefault(
    "DJANGO_SECRET_KEY",
    "test-only-placeholder-key-never-use-for-production-tizahab-v2",
)

from .settings import *  # noqa
from .settings import STORAGES as BASE_STORAGES  # noqa: E402

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Password validation and token revocation remain exercised. Avoid expensive
# production hashing for synthetic accounts in isolated test databases only.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Template tests do not require production collectstatic output.
STORAGES = {
    **BASE_STORAGES,
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
