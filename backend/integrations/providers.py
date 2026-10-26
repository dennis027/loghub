"""Health checks and metadata for every integrated product.

Credentials come from settings.LOGHUB (environment); nothing secret is stored in
the database or returned to the browser.
"""

import time

import requests
from django.conf import settings

from search.providers.base import HealthResult
from search.providers.elasticsearch import ElasticsearchProvider
from search.providers.graylog import GraylogProvider

_session = requests.Session()


def _cfg(key):
    return settings.LOGHUB[key]


def _timed_get(url, **kwargs):
    started = time.monotonic()
    resp = _session.get(url, timeout=kwargs.pop('timeout', 5), **kwargs)
    return resp, round((time.monotonic() - started) * 1000, 1)


def kibana_health():
    try:
        resp, latency = _timed_get(
            f"{_cfg('KIBANA_URL')}/api/status", auth=(_cfg('ELASTICSEARCH_USERNAME'), _cfg('ELASTICSEARCH_PASSWORD'))
        )
    except requests.RequestException as exc:
        return HealthResult('unhealthy', message=f'unreachable: {exc.__class__.__name__}')
    if resp.status_code == 503:
        return HealthResult('unhealthy', message='Kibana is starting or cannot reach Elasticsearch', latency_ms=latency)
    if resp.status_code in (401, 403):
        return HealthResult(
            'healthy', message='Kibana is up (status details need Kibana privileges)', latency_ms=latency
        )
    if not resp.ok:
        return HealthResult('unhealthy', message=f'HTTP {resp.status_code}', latency_ms=latency)
    data = resp.json()
    level = data.get('status', {}).get('overall', {}).get('level', 'unknown')
    status = {'available': 'healthy', 'degraded': 'degraded'}.get(level, 'unhealthy')
    return HealthResult(
        status,
        message=f'overall status: {level}',
        latency_ms=latency,
        version=data.get('version', {}).get('number', ''),
    )


def grafana_health():
    try:
        resp, latency = _timed_get(f"{_cfg('GRAFANA_URL')}/api/health")
    except requests.RequestException as exc:
        return HealthResult('unhealthy', message=f'unreachable: {exc.__class__.__name__}')
    if not resp.ok:
        return HealthResult('unhealthy', message=f'HTTP {resp.status_code}', latency_ms=latency)
    data = resp.json()
    status = 'healthy' if data.get('database') == 'ok' else 'degraded'
    details = {}
    try:
        dash = _session.get(
            f"{_cfg('GRAFANA_URL')}/api/search",
            params={'type': 'dash-db'},
            timeout=5,
            auth=(_cfg('GRAFANA_USERNAME'), _cfg('GRAFANA_PASSWORD')),
        )
        if dash.ok:
            details['dashboards'] = [{'title': d['title'], 'uid': d['uid'], 'url': d['url']} for d in dash.json()]
        elif dash.status_code in (401, 403):
            status, details['note'] = 'degraded', 'LogHub viewer credentials rejected'
    except requests.RequestException:
        pass
    return HealthResult(
        status,
        message=f"database {data.get('database')}",
        latency_ms=latency,
        version=data.get('version', ''),
        details=details,
    )


def prometheus_health():
    try:
        resp, latency = _timed_get(f"{_cfg('PROMETHEUS_URL')}/-/ready")
    except requests.RequestException as exc:
        return HealthResult(
            'disabled', message=f'not reachable ({exc.__class__.__name__}); ' 'enable the "metrics" compose profile'
        )
    return HealthResult('healthy' if resp.ok else 'unhealthy', message=resp.text.strip()[:100], latency_ms=latency)


def logstash_stats():
    resp, latency = _timed_get(f"{_cfg('LOGSTASH_MONITORING_URL')}/_node/stats")
    resp.raise_for_status()
    data = resp.json()
    main = data.get('pipelines', {}).get('main', {})
    replay = data.get('pipelines', {}).get('dlq')
    events = main.get('events', {})
    plugins = []
    retried_requests = non_retryable = 0
    for kind in ('inputs', 'filters', 'outputs'):
        for p in main.get('plugins', {}).get(kind, []):
            bulk = p.get('bulk_requests', {})
            docs = p.get('documents', {})
            retried_requests += bulk.get('failures', 0)
            non_retryable += docs.get('non_retryable_failures', 0)
            plugins.append(
                {
                    'kind': kind[:-1],
                    'id': p.get('id'),
                    'name': p.get('name'),
                    'events_in': p.get('events', {}).get('in'),
                    'events_out': p.get('events', {}).get('out'),
                    # Filter "failures" are pattern misses (e.g. grok on non-access lines), not data loss.
                    'pattern_misses' if kind == 'filters' else 'failures': p.get('failures', 0),
                    'documents_ok': docs.get('successes'),
                    'non_retryable': docs.get('non_retryable_failures'),
                }
            )
    dlq = main.get('dead_letter_queue', {})
    queue = main.get('queue', {})
    # The DLQ file holds a 1-byte version header when empty.
    dlq_pending = max(0, dlq.get('queue_size_in_bytes', 0) - 1)
    # Events actually lost: DLQ overflow/expiry. Documents waiting in the DLQ are surfaced separately.
    failures = dlq.get('dropped_events', 0) + dlq.get('expired_events', 0)
    return {
        'latency_ms': latency,
        'version': data.get('version'),
        'status': data.get('status'),
        'events': {
            'in': events.get('in', 0),
            'filtered': events.get('filtered', 0),
            'out': events.get('out', 0),
            'duration_ms': events.get('duration_in_millis', 0),
        },
        'failures': failures,
        # 409s (fingerprint already indexed = duplicate suppressed) and 400s (routed to the DLQ).
        'non_retryable_documents': non_retryable,
        # Bulk requests that failed transiently (e.g. ES restarting) and were retried.
        'retried_requests': retried_requests,
        'dead_letter_queue_bytes': dlq_pending,
        # The "dlq" pipeline re-indexes dead-lettered events automatically.
        'dlq_replay_running': replay is not None,
        'dlq_replayed_events': (replay or {}).get('events', {}).get('out', 0),
        'dead_letter_dropped': dlq.get('dropped_events', 0),
        'queue': {
            'type': queue.get('type'),
            'events': queue.get('events_count', queue.get('events', 0)),
            'size_bytes': queue.get('queue_size_in_bytes', 0),
            'max_bytes': queue.get('max_queue_size_in_bytes', 0),
        },
        'jvm_heap_percent': data.get('jvm', {}).get('mem', {}).get('heap_used_percent'),
        'plugins': plugins,
    }


def logstash_health():
    try:
        stats = logstash_stats()
    except (requests.RequestException, ValueError) as exc:
        return HealthResult('unhealthy', message=f'monitoring API unreachable: {exc.__class__.__name__}')
    stuck = stats['dead_letter_queue_bytes'] and not stats['dlq_replay_running']
    status = 'healthy' if stats['status'] == 'green' and not stats['failures'] and not stuck else 'degraded'
    msg = (
        f"{stats['events']['out']} events out, {stats['failures']} lost, "
        f"{stats['dlq_replayed_events']} replayed from dead-letter queue"
    )
    return HealthResult(
        status,
        message=msg,
        latency_ms=stats['latency_ms'],
        version=stats['version'] or '',
        details={k: stats[k] for k in ('events', 'failures', 'dead_letter_queue_bytes', 'queue')},
    )


def fluentbit_stats():
    base = _cfg('FLUENT_BIT_URL')
    resp, latency = _timed_get(f'{base}/api/v1/metrics')
    resp.raise_for_status()
    metrics = resp.json()
    health = _session.get(f'{base}/api/v1/health', timeout=5)
    info = _session.get(f'{base}/', timeout=5).json()
    inputs = {
        name: {'records': m.get('records', 0), 'bytes': m.get('bytes', 0)}
        for name, m in metrics.get('input', {}).items()
        if not name.startswith('storage_backlog')
    }
    outputs = {
        name: {
            'records': m.get('proc_records', 0),
            'errors': m.get('errors', 0),
            'retries': m.get('retries', 0),
            'retries_failed': m.get('retries_failed', 0),
            'dropped': m.get('dropped_records', 0),
        }
        for name, m in metrics.get('output', {}).items()
    }
    return {
        'latency_ms': latency,
        'healthy': health.status_code == 200 and 'ok' in health.text,
        'version': info.get('fluent-bit', {}).get('version', ''),
        'inputs': inputs,
        'outputs': outputs,
        'failures': sum(o['errors'] + o['retries_failed'] + o['dropped'] for o in outputs.values()),
    }


def fluentbit_health():
    try:
        stats = fluentbit_stats()
    except (requests.RequestException, ValueError) as exc:
        return HealthResult('unhealthy', message=f'HTTP server unreachable: {exc.__class__.__name__}')
    status = 'healthy' if stats['healthy'] else 'degraded'
    total_in = sum(i['records'] for i in stats['inputs'].values())
    return HealthResult(
        status,
        message=f"{total_in} records in, {stats['failures']} output failures",
        latency_ms=stats['latency_ms'],
        version=stats['version'],
        details={'inputs': stats['inputs'], 'outputs': stats['outputs']},
    )


# provider key -> (label, role, health fn, public url setting, internal url setting)
REGISTRY = {
    'elasticsearch': (
        'Elasticsearch',
        'Indexed log storage and search',
        lambda: ElasticsearchProvider().health(),
        None,
        'ELASTICSEARCH_URL',
    ),
    'logstash': (
        'Logstash',
        'Parsing, enrichment, masking and indexing',
        logstash_health,
        None,
        'LOGSTASH_MONITORING_URL',
    ),
    'fluent-bit': ('Fluent Bit', 'Collection, buffering and routing', fluentbit_health, None, 'FLUENT_BIT_URL'),
    'kibana': (
        'Kibana',
        'Ad-hoc exploration (Discover) of indexed logs',
        kibana_health,
        'KIBANA_PUBLIC_URL',
        'KIBANA_URL',
    ),
    'grafana': ('Grafana', 'Dashboards over logs and metrics', grafana_health, 'GRAFANA_PUBLIC_URL', 'GRAFANA_URL'),
    'graylog': (
        'Graylog',
        'Optional separate log engine (own OpenSearch/MongoDB)',
        lambda: GraylogProvider().health(),
        'GRAYLOG_PUBLIC_URL',
        'GRAYLOG_URL',
    ),
    'prometheus': (
        'Prometheus',
        'Infrastructure metrics (node-exporter, Fluent Bit)',
        prometheus_health,
        None,
        'PROMETHEUS_URL',
    ),
}


def check(provider):
    label, _, fn, _, _ = REGISTRY[provider]
    try:
        return fn()
    except Exception as exc:
        return HealthResult('unhealthy', message=f'{label} check failed: {exc.__class__.__name__}')


def prometheus_query(expr):
    resp = _session.get(f"{_cfg('PROMETHEUS_URL')}/api/v1/query", params={'query': expr}, timeout=10)
    resp.raise_for_status()
    return resp.json()['data']['result']


def prometheus_range(expr, start, end, step):
    resp = _session.get(
        f"{_cfg('PROMETHEUS_URL')}/api/v1/query_range",
        params={'query': expr, 'start': start, 'end': end, 'step': step},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()['data']['result']
