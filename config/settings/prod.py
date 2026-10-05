"""Configuración para producción."""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403
from .base import SECRET_KEY, SIMPLE_JWT

DEBUG = False

if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY es obligatorio en producción.")

_WEAK_JWT_SECRETS = {"", "supersecretkey", "secret", "changeme"}
if SIMPLE_JWT["SIGNING_KEY"] in _WEAK_JWT_SECRETS or len(SIMPLE_JWT["SIGNING_KEY"]) < 32:
    raise ImproperlyConfigured("JWT_SECRET es débil: usa una cadena aleatoria de al menos 32 caracteres.")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_CONTENT_TYPE_NOSNIFF = True
