import os

from celery import Celery
from celery.signals import setup_logging

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('loghub')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()


@setup_logging.connect
def configure_logging(**kwargs):
    """Use Django's JSON logging config in workers instead of Celery's plain-text default."""
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)
