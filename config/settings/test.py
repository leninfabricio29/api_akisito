"""Configuración para la suite de pruebas: sin Cloudinary, SMTP ni Firebase."""

from .dev import *  # noqa: F401,F403
from .dev import REST_FRAMEWORK

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.InMemoryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}
FIREBASE_CREDENTIALS = None
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {k: "10000/min" for k in REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]},
}
