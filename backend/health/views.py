import contextlib
import time

import requests
from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from alerts.models import AlertEvent
from core.exceptions import InvalidQuery, ProviderUnavailable
from integrations.models import Integration
from integrations.providers import prometheus_query, prometheus_range
from log_sources.models import Collector, LogSource
from search.providers.elasticsearch import ElasticsearchProvider
from search.query import LogQuery, parse_relative

ERRORS = {'level': ['error', 'critical']}


def live(request):
    """Process liveness (used by the container healthcheck)."""
    return JsonResponse({'status': 'ok'})


def ready(request):
    """Readiness: database and cache reachable."""
    checks = {}
    try:
        with connection.cursor() as cur:
            cur.execute('SELECT 1')
        checks['database'] = 'ok'
    except Exception as exc:
        checks['database'] = f'error: {exc.__class__.__name__}'
    try:
        cache.set('readiness-probe', 1, 5)
        checks['cache'] = 'ok' if cache.get('readiness-probe') == 1 else 'error'
    except Exception as exc:
        checks['cache'] = f'error: {exc.__class__.__name__}'
    ok = all(v == 'ok' for v in checks.values())
    return JsonResponse({'status': 'ok' if ok else 'unavailable', 'checks': checks}, status=200 if ok else 503)


class PlatformHealthView(APIView):
    """Health of every integrated service (refreshed every minute by Celery)."""

    def get(self, request):
        items = [
            {
                'provider': i.provider,
                'name': i.name,
                'status': i.status,
                'message': i.status_message,
                'version': i.version,
                'latency_ms': i.latency_ms,
                'last_checked': i.last_checked,
                'public_url': i.public_url,
                'enabled': i.enabled,
            }
            for i in Integration.objects.all()
        ]
        statuses = {i['status'] for i in items if i['enabled']}
        overall = 'unhealthy' if 'unhealthy' in statuses else ('degraded' if 'degraded' in statuses else 'healthy')
        return Response({'status': overall, 'services': items, 'checked_at': timezone.now()})


class OverviewView(APIView):
    """Everything the Overview page shows, computed from indexed data — never synthesized."""

    def get(self, request):
        org = request.user.organization
        range_ = request.query_params.get('range', '24h')
        query = LogQuery.from_params({'range': range_})
        provider = ElasticsearchProvider()
        sources = LogSource.objects.filter(organization=org)
        collectors = Collector.objects.filter(organization=org)

        failures, dlq_bytes = 0, 0
        for c in collectors.filter(managed=True):
            failures += int(c.metrics.get('failures', 0) or 0)
            dlq_bytes = max(dlq_bytes, int(c.metrics.get('dead_letter_queue_bytes', 0) or 0))

        data = {
            'range': range_,
            'generated_at': timezone.now(),
            'sources': {
                'total': sources.count(),
                'active': sources.filter(status='active').count(),
                'stale': sources.filter(status='stale').count(),
                'pending': sources.filter(status='pending').count(),
            },
            'collectors': {
                'total': collectors.count(),
                'unhealthy': collectors.exclude(status='healthy').count(),
                'items': [
                    {
                        'name': c.name,
                        'type': c.collector_type,
                        'status': c.status,
                        'message': c.status_message,
                        'last_heartbeat': c.last_heartbeat,
                    }
                    for c in collectors
                ],
            },
            'ingestion_failures': failures,
            'dead_letter_queue_bytes': dlq_bytes,
            'recent_alerts': [
                {'id': e.id, 'title': e.title, 'severity': e.severity, 'status': e.status, 'started_at': e.started_at}
                for e in AlertEvent.objects.filter(organization=org)[:8]
            ],
            'open_alerts': AlertEvent.objects.filter(organization=org, status__in=['firing', 'acknowledged']).count(),
            'services_health': [
                {'provider': i.provider, 'name': i.name, 'status': i.status, 'message': i.status_message}
                for i in Integration.objects.all()
            ],
            'elasticsearch_available': True,
        }
        try:
            aggs = provider.aggregate(
                org,
                query,
                {
                    'volume': {'type': 'histogram', 'split_by': 'level'},
                    'by_level': {'type': 'terms', 'field': 'level', 'size': 6},
                    'by_environment': {'type': 'terms', 'field': 'environment', 'size': 10},
                    'by_service': {'type': 'terms', 'field': 'service', 'size': 10},
                    'top_error_services': {
                        'type': 'terms',
                        'field': 'service',
                        'size': 10,
                        'filter': {'level': ERRORS['level']},
                    },
                    'frequent_errors': {
                        'type': 'terms',
                        'field': 'message.keyword',
                        'size': 10,
                        'filter': {'level': ERRORS['level']},
                    },
                    'errors': {'type': 'metric', 'filter': {'level': ['error']}},
                    'warnings': {'type': 'metric', 'filter': {'level': ['warning']}},
                    'critical': {'type': 'metric', 'filter': {'level': ['critical']}},
                },
            )
            last_minute = provider.count(org, LogQuery.from_params({'range': '1m'}))
            storage = provider.storage(org)
        except ProviderUnavailable as exc:
            data.update({'elasticsearch_available': False, 'elasticsearch_error': str(exc.detail)})
            return Response(data)

        totals = {b['key']: b['count'] for b in aggs['by_service']['buckets']}
        error_rate = [
            {
                'service': b['key'],
                'errors': b['count'],
                'events': totals.get(b['key']),
                'error_rate': round(100 * b['count'] / totals[b['key']], 2) if totals.get(b['key']) else None,
            }
            for b in aggs['top_error_services']['buckets']
        ]
        data.update(
            {
                'total_events': aggs['_total'],
                'events_per_second': round(last_minute / 60, 2),
                'events_last_minute': last_minute,
                'errors': aggs['errors']['value'],
                'warnings': aggs['warnings']['value'],
                'critical': aggs['critical']['value'],
                'volume': aggs['volume'],
                'by_level': aggs['by_level']['buckets'],
                'by_environment': aggs['by_environment']['buckets'],
                'top_error_services': aggs['top_error_services']['buckets'],
                'error_rate_by_service': error_rate,
                'frequent_errors': aggs['frequent_errors']['buckets'],
                'storage': storage,
            }
        )
        return Response(data)


class ServicesView(APIView):
    """Applications and services discovered from indexed logs."""

    def get(self, request):
        query = LogQuery.from_params({**request.query_params.dict(), 'range': request.query_params.get('range', '24h')})
        services = ElasticsearchProvider().services_summary(request.user.organization, query)
        registered = {
            s.effective_match_value: {'id': s.id, 'name': s.name}
            for s in LogSource.objects.filter(organization=request.user.organization, match_field='service')
        }
        for s in services:
            s['registered_source'] = registered.get(s['service'])
        return Response({'range': request.query_params.get('range', '24h'), 'services': services})


INFRA_QUERIES = {
    'cpu_percent': '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
    'memory_percent': '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
    'memory_total_bytes': 'node_memory_MemTotal_bytes',
    'load1': 'node_load1',
    'cpu_count': 'count(node_cpu_seconds_total{mode="idle"})',
    'uptime_seconds': 'time() - node_boot_time_seconds',
    'disk_percent': 'max by (mountpoint) ((1 - node_filesystem_avail_bytes{fstype!~"tmpfs|overlay|squashfs"} '
    '/ node_filesystem_size_bytes{fstype!~"tmpfs|overlay|squashfs"}) * 100)',
}


class InfrastructureView(APIView):
    """Host metrics (Prometheus/node-exporter) and Elasticsearch cluster state."""

    def get(self, request):
        out = {'prometheus_available': True, 'metrics': {}, 'disks': [], 'elasticsearch': None}
        try:
            for key, expr in INFRA_QUERIES.items():
                result = prometheus_query(expr)
                if key == 'disk_percent':
                    out['disks'] = [
                        {'mountpoint': r['metric'].get('mountpoint'), 'used_percent': round(float(r['value'][1]), 1)}
                        for r in result
                    ]
                else:
                    out['metrics'][key] = round(float(result[0]['value'][1]), 2) if result else None
        except (requests.RequestException, KeyError, ValueError) as exc:
            out.update(
                {
                    'prometheus_available': False,
                    'prometheus_error': f'{exc.__class__.__name__}: enable the "metrics" profile',
                }
            )
        health = ElasticsearchProvider().health()
        out['elasticsearch'] = {
            'status': health.status,
            'message': health.message,
            'version': health.version,
            **health.details,
        }
        with contextlib.suppress(ProviderUnavailable):
            out['elasticsearch']['storage'] = ElasticsearchProvider().storage(request.user.organization)
        return Response(out)


class MetricsRangeView(APIView):
    """Read-only PromQL range queries for dashboard widgets."""

    def get(self, request):
        expr = request.query_params.get('query', '')
        if not expr or len(expr) > 1000:
            raise InvalidQuery('query (PromQL, ≤1000 chars) is required.')
        span = parse_relative(request.query_params.get('range', '1h')).total_seconds()
        end = time.time()
        step = max(15, int(span / 120))
        try:
            result = prometheus_range(expr, end - span, end, step)
        except requests.HTTPError as exc:
            raise InvalidQuery(f'Prometheus rejected the query ({exc.response.status_code}).') from None
        except requests.RequestException:
            raise ProviderUnavailable('Prometheus is unreachable (is the "metrics" profile enabled?).') from None
        return Response(
            {
                'step': step,
                'series': [
                    {'labels': r['metric'], 'points': [[int(t * 1000), float(v)] for t, v in r['values']]}
                    for r in result
                ],
            }
        )
