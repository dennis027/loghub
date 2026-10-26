from datetime import timedelta
from unittest import mock

import pytest
from django.core import mail
from django.utils import timezone

from alerts.engine import process_rule
from alerts.models import AlertEvent, AlertRule
from notifications.backends import WebhookBackend
from notifications.models import NotificationChannel, NotificationDelivery

pytestmark = pytest.mark.django_db


@pytest.fixture
def channel(org):
    return NotificationChannel.objects.create(
        organization=org, name='ops', channel_type='email', config={'recipients': ['ops@acme.test']}
    )


def make_rule(org, channel=None, **kw):
    defaults = dict(
        organization=org,
        name=kw.pop('name', 'Errors'),
        rule_type='threshold',
        severity='error',
        filters={'level': ['error']},
        window_minutes=5,
        comparator='gt',
        threshold=3,
        cooldown_minutes=10,
    )
    defaults.update(kw)
    rule = AlertRule.objects.create(**defaults)
    if channel:
        rule.channels.add(channel)
    return rule


def test_threshold_rule_fires_and_emails(org, channel, fake_provider):
    rule = make_rule(org, channel)
    event = process_rule(rule, fake_provider([10]))
    assert event.status == 'firing' and event.value == 10 and event.samples
    assert rule.last_state == 'firing'
    assert len(mail.outbox) == 1
    assert '[ERROR] Errors' in mail.outbox[0].subject and 'ops@acme.test' in mail.outbox[0].to
    delivery = NotificationDelivery.objects.get()
    assert delivery.status == 'sent' and delivery.attempts == 1


def test_query_uses_rule_filters(org, fake_provider):
    provider = fake_provider([0])
    process_rule(make_rule(org), provider)
    assert provider.queries[0].filters == {'level': ['error']}
    assert (provider.queries[0].end - provider.queries[0].start) == timedelta(minutes=5)


def test_deduplicates_while_firing(org, channel, fake_provider):
    rule = make_rule(org, channel)
    provider = fake_provider([10, 12, 15])
    first = process_rule(rule, provider)
    process_rule(rule, provider)
    process_rule(rule, provider)
    first.refresh_from_db()
    assert AlertEvent.objects.count() == 1 and first.occurrences == 3 and first.value == 15
    assert len(mail.outbox) == 1


def test_auto_resolves_and_notifies(org, channel, fake_provider):
    rule = make_rule(org, channel)
    provider = fake_provider([10, 0])
    event = process_rule(rule, provider)
    process_rule(rule, provider)
    event.refresh_from_db()
    assert event.status == 'resolved' and event.resolved_at
    assert len(mail.outbox) == 2 and 'RESOLVED' in mail.outbox[1].subject


def test_cooldown_suppresses_refire(org, channel, fake_provider):
    rule = make_rule(org, channel, cooldown_minutes=30)
    provider = fake_provider([10, 0, 10])
    process_rule(rule, provider)
    process_rule(rule, provider)
    assert process_rule(rule, provider) is None
    assert rule.last_state == 'cooldown'
    assert AlertEvent.objects.count() == 1
    # after cooldown it fires again
    AlertEvent.objects.update(resolved_at=timezone.now() - timedelta(minutes=31))
    assert process_rule(rule, fake_provider([10])) is not None


def test_spike_rule(org, fake_provider):
    rule = make_rule(org, rule_type='spike', spike_factor=3, min_count=10)
    assert process_rule(rule, fake_provider([40, 10])).value == 40  # 4x previous
    rule2 = make_rule(org, name='s2', rule_type='spike', spike_factor=3, min_count=10)
    assert process_rule(rule2, fake_provider([25, 10])) is None  # 2.5x
    rule3 = make_rule(org, name='s3', rule_type='spike', spike_factor=3, min_count=10)
    assert process_rule(rule3, fake_provider([5, 0])) is None  # below min_count


def test_absence_rule(org, fake_provider):
    from log_sources.models import LogSource

    source = LogSource.objects.create(organization=org, name='billing', match_field='service')
    rule = make_rule(org, rule_type='absence', source=source, filters={})
    provider = fake_provider([0])
    event = process_rule(rule, provider)
    assert event and 'No events from billing' in event.message
    assert provider.queries[0].field_filters[0].field == 'service'


def test_storage_rule(org, fake_provider):
    rule = make_rule(org, rule_type='storage', comparator='gt', threshold=85)
    assert process_rule(rule, fake_provider(disk=91.2)).value == 91.2


def test_provider_error_marks_rule(org):
    from core.exceptions import ProviderUnavailable

    provider = mock.Mock()
    provider.count.side_effect = ProviderUnavailable()
    rule = make_rule(org)
    assert process_rule(rule, provider) is None
    assert rule.last_state == 'error' and rule.last_error


def test_rule_api_validation(admin_client, other_org):
    foreign = NotificationChannel.objects.create(
        organization=other_org, name='x', channel_type='email', config={'recipients': ['x@y.z']}
    )
    base = {'name': 'r', 'rule_type': 'threshold'}
    assert admin_client.post('/api/alert-rules/', {**base, 'channels': [foreign.pk]}, format='json').status_code == 400
    assert (
        admin_client.post('/api/alert-rules/', {**base, 'evaluation_interval_seconds': 5}, format='json').status_code
        == 400
    )
    assert (
        admin_client.post('/api/alert-rules/', {**base, 'filters': {'level': 'error'}}, format='json').status_code
        == 400
    )
    assert (
        admin_client.post('/api/alert-rules/', {**base, 'filters': {'level': ['error']}}, format='json').status_code
        == 201
    )
    assert len(admin_client.get('/api/alert-rules/templates/').data) >= 8


def test_acknowledge_flow(org, admin_client, viewer_client, fake_provider):
    event = process_rule(make_rule(org), fake_provider([10]))
    assert viewer_client.post(f'/api/alert-events/{event.pk}/acknowledge/').status_code == 403
    resp = admin_client.post(f'/api/alert-events/{event.pk}/acknowledge/', {'note': 'on it'}, format='json')
    assert resp.status_code == 200 and resp.data['status'] == 'acknowledged'
    assert admin_client.post(f'/api/alert-events/{event.pk}/acknowledge/').status_code == 400


def test_notification_channel_test_endpoint(channel, admin_client):
    resp = admin_client.post(f'/api/notification-channels/{channel.pk}/test/')
    assert resp.status_code == 200 and resp.data['status'] == 'sent'
    assert mail.outbox[0].subject == '[LogHub] Test notification'


def test_email_channel_validation(admin_client):
    resp = admin_client.post(
        '/api/notification-channels/',
        {'name': 'bad', 'channel_type': 'email', 'config': {'recipients': ['not-an-email']}},
        format='json',
    )
    assert resp.status_code == 400


def test_webhook_blocks_private_targets(settings):
    settings.LOGHUB = {**settings.LOGHUB, 'WEBHOOK_ALLOW_PRIVATE_NETWORKS': False}
    with pytest.raises(ValueError):
        WebhookBackend().validate_config({'url': 'http://127.0.0.1:8000/hook'})
    with pytest.raises(ValueError):
        WebhookBackend().validate_config({'url': 'ftp://example.com'})


def test_webhook_secret_is_write_only(admin_client, settings):
    settings.LOGHUB = {**settings.LOGHUB, 'WEBHOOK_ALLOW_PRIVATE_NETWORKS': True}
    resp = admin_client.post(
        '/api/notification-channels/',
        {'name': 'hook', 'channel_type': 'webhook', 'config': {'url': 'http://localhost/hook'}, 'secret': 's3cr3t'},
        format='json',
    )
    assert resp.status_code == 201 and 'secret' not in resp.data and resp.data['has_secret'] is True


def test_webhook_retries_then_fails(org, settings):
    import requests

    settings.LOGHUB = {**settings.LOGHUB, 'WEBHOOK_ALLOW_PRIVATE_NETWORKS': True}
    channel = NotificationChannel.objects.create(
        organization=org, name='hook', channel_type='webhook', config={'url': 'http://localhost/hook'}, secret='k'
    )
    from notifications.tasks import queue_notification

    with mock.patch('notifications.backends.requests.post', side_effect=requests.ConnectionError()) as post:
        delivery = queue_notification(channel, 's', 'b', {})
    delivery.refresh_from_db()
    assert post.call_count == 4  # bounded: initial attempt + 3 retries
    assert delivery.status == 'failed' and delivery.attempts == 4
