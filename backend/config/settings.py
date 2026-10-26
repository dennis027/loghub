import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return str(os.environ.get(name, default)).lower() in ('1', 'true', 'yes', 'on')


def env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


DEBUG = env_bool('DEBUG', False)
SECRET_KEY = env('DJANGO_SECRET_KEY')
if not SECRET_KEY:
    if not DEBUG and not env_bool('TESTING'):
        raise RuntimeError('DJANGO_SECRET_KEY must be set (run scripts/init-env.sh)')
    SECRET_KEY = 'insecure-dev-only-key'

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1,django-api')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS', 'http://localhost:4200')
PUBLIC_BASE_URL = env('PUBLIC_BASE_URL', 'http://localhost:4200')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'core',
    'organizations',
    'accounts',
    'log_sources',
    'integrations',
    'search',
    'notifications',
    'alerts',
    'retention',
    'dashboards',
    'audit',
    'health',
    'reports',
]

MIDDLEWARE = [
    'core.middleware.RequestIdMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': env('POSTGRES_DB', 'loghub'),
        'USER': env('POSTGRES_USER', 'loghub'),
        'PASSWORD': env('POSTGRES_PASSWORD', ''),
        'HOST': env('POSTGRES_HOST', 'localhost'),
        'PORT': env('POSTGRES_PORT', '5432'),
        # Persistent connections act as a per-thread pool under gunicorn gthread.
        'CONN_MAX_AGE': int(env('DB_CONN_MAX_AGE', 60)),
        'CONN_HEALTH_CHECKS': True,
        'OPTIONS': {'connect_timeout': 5},
    }
}

REDIS_URL = env('REDIS_URL', 'redis://localhost:6379/0')
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL.rsplit('/', 1)[0] + '/1',
        'TIMEOUT': 300,
    }
}
if env_bool('TESTING'):
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}

AUTH_USER_MODEL = 'accounts.User'
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---- security --------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = env_bool('SECURE_COOKIES', False)
CSRF_COOKIE_SECURE = env_bool('SECURE_COOKIES', False)
SECURE_HSTS_SECONDS = int(env('SECURE_HSTS_SECONDS', 0))
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024  # ingest batches

# ---- REST framework --------------------------------------------------------
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ('rest_framework_simplejwt.authentication.JWTAuthentication',),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticated',
        'core.permissions.IsOrganizationMember',
    ),
    'DEFAULT_PAGINATION_CLASS': 'core.pagination.StandardPagination',
    'PAGE_SIZE': 25,
    'DEFAULT_FILTER_BACKENDS': (
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ),
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'EXCEPTION_HANDLER': 'core.exceptions.api_exception_handler',
    # `?format=csv|json|pdf` is an export parameter here, not DRF's renderer override.
    'URL_FORMAT_OVERRIDE': None,
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '1200/min',
        'login': '10/min',
        'search': '120/min',
        'export': '20/hour',
        'ingest': '1200/min',
    },
}
if env_bool('TESTING'):
    REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'] = ()

SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=int(env('JWT_ACCESS_TOKEN_LIFETIME_MINUTES', 30))),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=int(env('JWT_REFRESH_TOKEN_LIFETIME_DAYS', 1))),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'LogHub API',
    'DESCRIPTION': 'Centralized log management and observability platform.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
}

# ---- Celery ----------------------------------------------------------------
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_RESULT_EXPIRES = 3600
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 120
CELERY_TASK_SOFT_TIME_LIMIT = 90
CELERY_TASK_ALWAYS_EAGER = env_bool('TESTING')
CELERY_BEAT_SCHEDULE = {
    'evaluate-alert-rules': {'task': 'alerts.tasks.evaluate_due_rules', 'schedule': 30.0},
    'refresh-source-status': {'task': 'log_sources.tasks.refresh_source_status', 'schedule': 60.0},
    'check-integrations': {'task': 'integrations.tasks.check_all_integrations', 'schedule': 60.0},
    'refresh-collectors': {'task': 'log_sources.tasks.refresh_collectors', 'schedule': 60.0},
    'purge-metadata': {'task': 'retention.tasks.purge_platform_metadata', 'schedule': 6 * 3600.0},
}

# ---- Email -----------------------------------------------------------------
EMAIL_BACKEND = env('EMAIL_BACKEND', 'django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(env('EMAIL_PORT', 25))
EMAIL_HOST_USER = env('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', False)
EMAIL_TIMEOUT = 15
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'loghub-alerts@example.com')
if env_bool('TESTING'):
    EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# ---- Integrations ----------------------------------------------------------
# Credentials live only in the environment, never in the database or API responses.
LOGHUB = {
    'ELASTICSEARCH_URL': env('ELASTICSEARCH_URL', 'http://localhost:9200'),
    'ELASTICSEARCH_USERNAME': env('ELASTICSEARCH_USERNAME', ''),
    'ELASTICSEARCH_PASSWORD': env('ELASTICSEARCH_PASSWORD', ''),
    'ELASTICSEARCH_TIMEOUT': int(env('ELASTICSEARCH_TIMEOUT', 15)),
    'INDEX_PREFIX': 'logs-loghub-',
    'ILM_POLICY': 'loghub-logs',
    'SEARCH_MAX_RESULTS': 500,
    'EXPORT_MAX_ROWS': 10000,
    'LOGSTASH_HTTP_URL': env('LOGSTASH_HTTP_URL', 'http://localhost:8080'),
    'LOGSTASH_MONITORING_URL': env('LOGSTASH_MONITORING_URL', 'http://localhost:9600'),
    'LOGSTASH_HTTP_USER': env('LOGSTASH_HTTP_USER', ''),
    'LOGSTASH_HTTP_PASSWORD': env('LOGSTASH_HTTP_PASSWORD', ''),
    'FLUENT_BIT_URL': env('FLUENT_BIT_URL', 'http://localhost:2020'),
    'FLUENT_BIT_INGEST_URL': env('FLUENT_BIT_INGEST_URL', 'http://fluent-bit:9881'),
    'KIBANA_URL': env('KIBANA_URL', 'http://localhost:5601'),
    'KIBANA_PUBLIC_URL': env('KIBANA_PUBLIC_URL', 'http://localhost:5601'),
    'GRAFANA_URL': env('GRAFANA_URL', 'http://localhost:3000'),
    'GRAFANA_PUBLIC_URL': env('GRAFANA_PUBLIC_URL', 'http://localhost:3000'),
    'GRAFANA_USERNAME': env('GRAFANA_USERNAME', ''),
    'GRAFANA_PASSWORD': env('GRAFANA_PASSWORD', ''),
    'GRAYLOG_URL': env('GRAYLOG_URL', 'http://localhost:9000'),
    'GRAYLOG_PUBLIC_URL': env('GRAYLOG_PUBLIC_URL', 'http://localhost:9000'),
    'GRAYLOG_USERNAME': env('GRAYLOG_USERNAME', ''),
    'GRAYLOG_PASSWORD': env('GRAYLOG_PASSWORD', ''),
    'PROMETHEUS_URL': env('PROMETHEUS_URL', 'http://localhost:9090'),
    'LIVE_STREAM_MAX_SECONDS': 300,
    'LIVE_STREAM_POLL_SECONDS': 2,
    'LIVE_STREAM_MAX_PER_USER': 3,
    'SOURCE_STALE_MINUTES': 5,
    'WEBHOOK_ALLOW_PRIVATE_NETWORKS': env_bool('WEBHOOK_ALLOW_PRIVATE_NETWORKS', False),
    'AUDIT_RETENTION_DAYS': int(env('AUDIT_RETENTION_DAYS', 365)),
    'ALERT_EVENT_RETENTION_DAYS': int(env('ALERT_EVENT_RETENTION_DAYS', 90)),
    'DEFAULT_ORGANIZATION_SLUG': env('DEFAULT_ORGANIZATION_SLUG', 'default'),
}

# ---- Logging: structured JSON to stdout, shipped by Docker -> Fluent Bit ----
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {'request_id': {'()': 'core.logging.RequestIdFilter'}},
    'formatters': {
        'json': {'()': 'core.logging.JsonFormatter', 'service': env('SERVICE_NAME', 'django-api')},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'json', 'filters': ['request_id']},
    },
    'root': {'handlers': ['console'], 'level': env('LOG_LEVEL', 'INFO')},
    'loggers': {
        'django.db.backends': {'level': 'WARNING'},
        'elastic_transport': {'level': 'WARNING'},
        'urllib3': {'level': 'WARNING'},
    },
}
