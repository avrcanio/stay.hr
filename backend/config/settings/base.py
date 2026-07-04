from pathlib import Path

import environ
from celery.schedules import crontab

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_CSRF_TRUSTED_ORIGINS=(list, []),
    DB_CONN_MAX_AGE=(int, 60),
)

BASE_DIR = Path(__file__).resolve().parent.parent.parent

environ.Env.read_env(BASE_DIR.parent / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
STAY_INTEGRATION_FERNET_KEY = env("STAY_INTEGRATION_FERNET_KEY", default="")
WHATSAPP_WEBHOOK_VERIFY_TOKEN = env("WHATSAPP_WEBHOOK_VERIFY_TOKEN", default="")
WHATSAPP_APP_SECRET = env("WHATSAPP_APP_SECRET", default="")
WHATSAPP_API_VERSION = env("WHATSAPP_API_VERSION", default="v23.0")
ALLOW_WHATSAPP_CONNECT_TOKEN = env.bool("ALLOW_WHATSAPP_CONNECT_TOKEN", default=False)
META_APP_ID = env("META_APP_ID", default="")
CF_DNS_API_TOKEN = env("CF_DNS_API_TOKEN", default="")
STAY_SERVER_IP = env("STAY_SERVER_IP", default="")
CLOUDFLARE_ZONE_STAY = env("CLOUDFLARE_ZONE_STAY", default="stay.hr")
STAY_API_INTERNAL_URL = env("STAY_API_INTERNAL_URL", default="http://stay_django:8000")
STAY_PUBLIC_API_URL = env("STAY_PUBLIC_API_URL", default="https://api.stay.hr")
FIREBASE_SERVICE_ACCOUNT_PATH = env("FIREBASE_SERVICE_ACCOUNT_PATH", default="")
FIREBASE_PROJECT_ID = env("FIREBASE_PROJECT_ID", default="hospira-fc0dc")
FCM_PUSH_ENABLED = env.bool("FCM_PUSH_ENABLED", default=True)
FCM_PUSH_ALLOWED_TENANT_SLUGS = env.list("FCM_PUSH_ALLOWED_TENANT_SLUGS", default=[])
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.tenants",
    "apps.properties",
    "apps.reservations",
    "apps.integrations",
    "apps.communications",
    "apps.legacy_import",
    "apps.tourist_tax",
    "apps.billing",
    "apps.api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "apps.tenants.middleware.TenantHostMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

if DEBUG:
    MIDDLEWARE.insert(0, "apps.core.dev_cors.DevCorsMiddleware")

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME", default="stay_platform_db"),
        "USER": env("DB_USER", default="stay"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST", default="postgis"),
        "PORT": env("DB_PORT", default="5432"),
        "CONN_MAX_AGE": env("DB_CONN_MAX_AGE"),
    }
}

_uzorita_db_name = env("UZORITA_DB_NAME", default="")
if _uzorita_db_name:
    DATABASES["uzorita_legacy"] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _uzorita_db_name,
        "USER": env("UZORITA_DB_USER", default="postgres"),
        "PASSWORD": env("UZORITA_DB_PASSWORD", default=""),
        "HOST": env("UZORITA_DB_HOST", default="localhost"),
        "PORT": env("UZORITA_DB_PORT", default="5432"),
        "CONN_MAX_AGE": env("DB_CONN_MAX_AGE"),
        "OPTIONS": {
            "options": "-c default_transaction_read_only=on",
        },
    }

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

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
DOCUMENT_PHOTO_MAX_BYTES = 8 * 1024 * 1024
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@stay.hr")

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.api.authentication.AppKeyAuthentication",
    ],
    "UNAUTHENTICATED_USER": None,
}

REDIS_URL = env("REDIS_URL", default="redis://redis:6379/0")

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "core-ping": {
        "task": "apps.core.tasks.ping",
        "schedule": 3600.0,
    },
    "auto-checkout": {
        "task": "apps.reservations.tasks.run_auto_checkouts",
        "schedule": 900.0,
    },
    "whatsapp-autocheckin-welcome": {
        "task": "apps.communications.whatsapp_autocheckin_tasks.run_whatsapp_autocheckin_welcome",
        "schedule": 900.0,
    },
    "channex-messages-upcoming-checkins": {
        "task": "apps.integrations.channex.message_tasks.sync_channex_messages_for_upcoming_checkins",
        "schedule": 900.0,
        "kwargs": {"tenant_slug": "uzorita"},
    },
    "channex-booking-revisions-feed": {
        "task": "apps.integrations.channex.booking_tasks.process_channex_booking_revisions_feed_periodic",
        "schedule": 900.0,
        "kwargs": {"tenant_slug": "uzorita"},
    },
    "channex-reviews-periodic": {
        "task": "apps.integrations.channex.review_tasks.sync_channex_reviews_periodic",
        "schedule": 21600.0,
        "kwargs": {"tenant_slug": "uzorita"},
    },
    "guest-email-imap-poll": {
        "task": "apps.communications.email_ingest_tasks.poll_guest_email_inbox",
        "schedule": 120.0,
        "kwargs": {"tenant_slug": "uzorita"},
    },
    "detect-overbooking-daily": {
        "task": "apps.reservations.overbooking_tasks.detect_overbooking_daily",
        "schedule": crontab(hour=6, minute=0),
        "kwargs": {"tenant_id": 2},
    },
    "detect-multi-room-gaps-daily": {
        "task": "apps.reservations.overbooking_tasks.detect_multi_room_gaps_daily",
        "schedule": crontab(hour=6, minute=15),
        "kwargs": {"tenant_id": 2},
    },
    "reconcile-guest-document-batches": {
        "task": "apps.integrations.whatsapp.guest_document_batch_reconcile.reconcile_guest_document_batches",
        "schedule": 900.0,
        "kwargs": {"apply": True},
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "mask_sensitive_headers": {
            "()": "config.settings.logging.SensitiveHeaderFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["mask_sensitive_headers"],
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
}
