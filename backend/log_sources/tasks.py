import logging
from collections import defaultdict
from datetime import timedelta

import requests
from celery import shared_task
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.exceptions import ProviderUnavailable
from integrations.providers import fluentbit_stats, logstash_stats
from organizations.models import Organization
from search.providers.elasticsearch import ElasticsearchProvider

from .models import Collector, LogSource

logger = logging.getLogger(__name__)


def refresh_org_sources(org, provider=None):
    """Derive each source's status from what is actually indexed, not from heartbeats."""
    provider = provider or ElasticsearchProvider()
    sources = list(LogSource.objects.filter(organization=org))
    by_field = defaultdict(list)
    for source in sources:
        if source.enabled:
            by_field[source.match_field].append(source)
    now = timezone.now()
    for field, group in by_field.items():
        values = {s.effective_match_value for s in group}
        seen_30d = provider.last_seen(org, field, values, since='now-30d')
        seen_24h = provider.last_seen(org, field, values, since='now-24h')
        for source in group:
            key = source.effective_match_value
            info = seen_30d.get(key)
            source.events_24h = seen_24h.get(key, {}).get('count', 0)
            if info and info['last_seen']:
                source.last_seen = parse_datetime(info['last_seen'])
                fresh = now - source.last_seen <= timedelta(minutes=source.stale_after_minutes)
                source.status = 'active' if fresh else 'stale'
            elif source.last_seen is None:
                source.status = 'pending'
            else:
                source.status = 'stale'
            source.save(update_fields=['events_24h', 'last_seen', 'status', 'updated_at'])
    LogSource.objects.filter(organization=org, enabled=False).exclude(status='disabled').update(status='disabled')


@shared_task(ignore_result=True)
def refresh_source_status():
    provider = ElasticsearchProvider()
    for org in Organization.objects.filter(is_active=True):
        try:
            refresh_org_sources(org, provider)
        except ProviderUnavailable as exc:
            logger.warning('source status refresh skipped for %s: %s', org.slug, exc.detail)
            return


@shared_task(ignore_result=True)
def refresh_collectors():
    """Poll the bundled Fluent Bit and Logstash and record their health on managed collectors."""
    now = timezone.now()
    results = {}
    for ctype, fn in (('fluent-bit', fluentbit_stats), ('logstash', logstash_stats)):
        try:
            stats = fn()
            healthy = stats.get('healthy', stats.get('status') == 'green')
            dlq = stats.get('dead_letter_queue_bytes', 0)
            problems = []
            if stats['failures']:
                problems.append(f"{stats['failures']} events lost since start")
            if dlq and not stats.get('dlq_replay_running', True):
                problems.append(f'{dlq} B in the dead-letter queue and the replay pipeline is not running')
            status = 'unhealthy' if not healthy else ('degraded' if problems else 'healthy')
            message = '; '.join(problems) or 'ok'
            results[ctype] = (status, message, stats, now)
        except (requests.RequestException, ValueError) as exc:
            results[ctype] = ('unhealthy', f'unreachable: {exc.__class__.__name__}', None, None)
    for collector in Collector.objects.filter(managed=True):
        if collector.collector_type not in results:
            continue
        status, message, stats, heartbeat = results[collector.collector_type]
        collector.status, collector.status_message = status, message
        if stats is not None:
            collector.metrics = {k: v for k, v in stats.items() if k != 'plugins'}
            collector.last_heartbeat = heartbeat
        collector.save()
