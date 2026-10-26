import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from core.exceptions import ProviderUnavailable
from search.providers.elasticsearch import ElasticsearchProvider

from .models import RetentionPolicy

logger = logging.getLogger(__name__)


def sync_policy(policy):
    try:
        ElasticsearchProvider().put_retention(
            settings.LOGHUB['ILM_POLICY'], policy.rollover_days, policy.delete_after_days
        )
    except ProviderUnavailable as exc:
        policy.sync_status, policy.sync_message = 'error', str(exc.detail)[:500]
    else:
        policy.sync_status, policy.sync_message = 'synced', 'ILM policy updated'
        policy.last_synced_at = timezone.now()
    policy.save(update_fields=['sync_status', 'sync_message', 'last_synced_at'])
    return policy


@shared_task(ignore_result=True)
def sync_retention_policy(policy_id):
    sync_policy(RetentionPolicy.objects.get(pk=policy_id))


@shared_task(ignore_result=True)
def purge_platform_metadata():
    """Bounded retention for the app's own Postgres records (log data lives in Elasticsearch)."""
    from alerts.models import AlertEvent
    from audit.models import AuditEvent
    from notifications.models import NotificationDelivery

    now = timezone.now()
    cfg = settings.LOGHUB
    audit_cut = now - timedelta(days=cfg['AUDIT_RETENTION_DAYS'])
    alert_cut = now - timedelta(days=cfg['ALERT_EVENT_RETENTION_DAYS'])
    deleted = {
        'audit_events': AuditEvent.objects.filter(created_at__lt=audit_cut).delete()[0],
        'alert_events': AlertEvent.objects.filter(status='resolved', resolved_at__lt=alert_cut).delete()[0],
        'deliveries': NotificationDelivery.objects.filter(created_at__lt=alert_cut).delete()[0],
    }
    logger.info('purged platform metadata', extra={'deleted': deleted})
    return deleted
