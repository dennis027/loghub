#!/bin/sh
set -e

case "$1" in
  web)
    python manage.py migrate --noinput
    python manage.py bootstrap_platform
    exec gunicorn config.wsgi:application \
      --bind 0.0.0.0:8000 \
      --worker-class gthread \
      --workers "${GUNICORN_WORKERS:-2}" \
      --threads "${GUNICORN_THREADS:-8}" \
      --timeout 120 \
      --graceful-timeout 30 \
      --access-logfile - \
      --access-logformat '{"message": "%(m)s %(U)s %(s)s", "level": "info", "logger": "gunicorn.access", "http": {"method": "%(m)s", "path": "%(U)s", "status": %(s)s, "duration_ms": %(M)s}, "event_type": "http_access", "service": "django-api"}'
    ;;
  worker)
    exec celery -A config worker -l info --concurrency "${CELERY_CONCURRENCY:-2}"
    ;;
  beat)
    exec celery -A config beat -l info --schedule /tmp/celerybeat-schedule
    ;;
  *)
    exec "$@"
    ;;
esac
