"""
Configuración base compartida por todos los entornos.

Todas las variables sensibles se leen del archivo .env en la raíz del proyecto.
"""

import base64
import json
import re
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")


def parse_duration(value: str, default: timedelta) -> timedelta:
    """Convierte duraciones estilo '7d', '12h', '30m', '45s' a timedelta."""
    match = re.fullmatch(r"\s*(\d+)\s*([dhms])\s*", value or "")
    if not match:
        return default
    amount, unit = int(match.group(1)), match.group(2)
    return {
        "d": timedelta(days=amount),
        "h": timedelta(hours=amount),
        "m": timedelta(minutes=amount),
        "s": timedelta(seconds=amount),
    }[unit]


# ─── Núcleo ────────────────────────────────────────────────────────────────────

SECRET_KEY = env("DJANGO_SECRET_KEY", default="")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

INSTALLED_APPS = [
    # unfold debe ir antes de django.contrib.admin
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "corsheaders",
    # Proyecto
    "apps.core",
    "apps.accounts",
    "apps.businesses",
    "apps.loyalty",
    "apps.checkins",
    "apps.reviews",
    "apps.rewards",
    "apps.notifications",
    "apps.analytics",
    "apps.content",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

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
            ],
        },
    },
]

# ─── Base de datos ─────────────────────────────────────────────────────────────

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["ATOMIC_REQUESTS"] = False
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ─── Autenticación ─────────────────────────────────────────────────────────────

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_RESET_CODE_TTL = parse_duration(env("RESET_PASSWORD_EXPIRES_IN", default="1h"), timedelta(hours=1))
PASSWORD_RESET_MAX_ATTEMPTS = 5
SIGNUP_CODE_TTL = timedelta(minutes=30)

# ─── Internacionalización ──────────────────────────────────────────────────────

LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

# ─── Archivos estáticos y multimedia (Cloudinary) ──────────────────────────────

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

CLOUDINARY_STORAGE = {
    "CLOUD_NAME": env("CLOUDINARY_CLOUD_NAME", default=""),
    "API_KEY": env("CLOUDINARY_API_KEY", default=""),
    "API_SECRET": env("CLOUDINARY_API_SECRET", default=""),
    "SECURE": True,
}

STORAGES = {
    "default": {"BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

MEDIA_URL = "/media/"
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
MAX_IMAGE_SIZE_MB = 5

# ─── Correo (Django 6.1 MAILERS) ───────────────────────────────────────────────

_email_port = env.int("EMAIL_PORT", default=465)

MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": env("EMAIL_HOST", default="smtp.zoho.com"),
            "port": _email_port,
            "username": env("EMAIL_USER", default=""),
            "password": env("EMAIL_PASSWORD", default=""),
            "use_ssl": _email_port == 465,
            "use_tls": _email_port == 587,
            "timeout": 15,
        },
    },
}
DEFAULT_FROM_EMAIL = env("EMAIL_FROM", default=env("EMAIL_USER", default="noreply@akisito.com"))
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# ─── Firebase (push) ───────────────────────────────────────────────────────────


def _decode_firebase_credentials(raw: str) -> dict | None:
    if not raw:
        return None
    try:
        data = json.loads(base64.b64decode(raw).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if "private_key" in data:
        data["private_key"] = data["private_key"].replace("\\n", "\n")
    return data


FIREBASE_CREDENTIALS = _decode_firebase_credentials(env("FIREBASE_CREDENTIALS_BASE64", default=""))

# ─── Django REST Framework ─────────────────────────────────────────────────────

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/min",
        "user": "240/min",
        "auth": "10/min",
        "password_reset": "5/hour",
        "signup": "10/hour",
        "checkin": "20/hour",
    },
}

SIMPLE_JWT = {
    "SIGNING_KEY": env("JWT_SECRET"),
    "ACCESS_TOKEN_LIFETIME": parse_duration(env("JWT_EXPIRES_IN", default="7d"), timedelta(days=7)),
    "REFRESH_TOKEN_LIFETIME": parse_duration(env("JWT_REFRESH_EXPIRES_IN", default="30d"), timedelta(days=30)),
    "ROTATE_REFRESH_TOKENS": True,
    "UPDATE_LAST_LOGIN": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_CLAIM": "user_id",
}

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

# ─── Reglas de negocio (valores de arranque) ───────────────────────────────────
# Los valores editables en caliente viven en el modelo LoyaltySettings (admin).

REDEMPTION_CODE_TTL = timedelta(hours=env.int("REDEMPTION_CODE_EXPIRES_HOURS", default=24))

# ─── Logging ───────────────────────────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"simple": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "simple"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"django.db.backends": {"level": "WARNING"}},
}

# ─── Admin (django-unfold) ─────────────────────────────────────────────────────

from .unfold import UNFOLD  # noqa: E402,F401
