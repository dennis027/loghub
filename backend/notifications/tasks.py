import logging

from celery import shared_task
from django.utils import timezone

from .backends import BACKENDS, DeliveryError
from .models import NotificationDelivery

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 4


@shared_task(bind=True, max_retries=MAX_ATTEMPTS - 1, ignore_result=True)
def deliver_notification(self, delivery_id, subject, body, payload):
    delivery = NotificationDelivery.objects.select_related('channel').get(pk=delivery_id)
    channel = delivery.channel
    delivery.attempts += 1
    try:
        BACKENDS[channel.channel_type].send(channel, subject, body, payload)
    except DeliveryError as exc:
        delivery.error = str(exc)[:2000]
        final = self.request.retries >= self.max_retries
        delivery.status = 'failed' if final else 'pending'
        delivery.save(update_fields=['attempts', 'error', 'status'])
        logger.warning(
            'notification delivery failed',
            extra={
                'channel': channel.name,
                'attempt': delivery.attempts,
                'final': final,
                'event_type': 'notification_failure',
            },
        )
        if not final:
            raise self.retry(exc=exc, countdown=min(30 * 2**self.request.retries, 600)) from exc
        return
    except ValueError as exc:  # permanent: bad config / rejected
        delivery.status, delivery.error = 'failed', str(exc)[:2000]
        delivery.save(update_fields=['attempts', 'error', 'status'])
        return
    delivery.status, delivery.error, delivery.sent_at = 'sent', '', timezone.now()
    delivery.save(update_fields=['attempts', 'error', 'status', 'sent_at'])
    logger.info('notification sent', extra={'channel': channel.name, 'kind': delivery.kind})


def queue_notification(channel, subject, body, payload, alert_event=None, kind='firing'):
    delivery = NotificationDelivery.objects.create(
        channel=channel, alert_event=alert_event, kind=kind, subject=subject[:255]
    )
    deliver_notification.delay(delivery.pk, subject, body, payload)
    return delivery
