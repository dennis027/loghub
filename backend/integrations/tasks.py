from celery import shared_task

from .models import Integration
from .services import refresh_integration


@shared_task(ignore_result=True)
def check_all_integrations():
    for integration in Integration.objects.all():
        refresh_integration(integration)
