"""Report generators. Each returns {"title", "columns", "rows", "summary"} built from real data."""

from django.db.models import Count
from django.utils import timezone

from alerts.models import AlertEvent
from log_sources.models import LogSource
from search.providers.elasticsearch import ElasticsearchProvider
from search.query import LogQuery

ERRORS = ['error', 'critical']


def _query(range_):
    return LogQuery.from_params({'range': range_})


def _daily(range_):
    return 'day' if range_.endswith('d') and int(range_[:-1]) > 2 else None


def log_volume(org, range_):
    q = _query(range_)
    agg = ElasticsearchProvider().aggregate(
        org, q, {'h': {'type': 'histogram', 'split_by': 'level', 'interval': '1d' if _daily(range_) else '1h'}}
    )
    levels = ['debug', 'info', 'warning', 'error', 'critical']
    rows = [[b['time'], b['count'], *[b.get('series', {}).get(lvl, 0) for lvl in levels]] for b in agg['h']['buckets']]
    return {
        'title': 'Log volume trend',
        'columns': ['period', 'total', *levels],
        'rows': rows,
        'summary': {'total_events': agg['_total']},
    }


def error_trend(org, range_):
    q = _query(range_)
    agg = ElasticsearchProvider().aggregate(
        org,
        q,
        {
            'h': {
                'type': 'histogram',
                'split_by': 'service',
                'split_size': 8,
                'interval': '1d' if _daily(range_) else '1h',
                'filter': {'level': ERRORS},
            }
        },
    )
    series = agg['h']['series']
    rows = [[b['time'], b['count'], *[b.get('series', {}).get(s, 0) for s in series]] for b in agg['h']['buckets']]
    return {
        'title': 'Application error trend',
        'columns': ['period', 'errors', *series],
        'rows': rows,
        'summary': {'services': len(series)},
    }


def top_error_services(org, range_):
    services = ElasticsearchProvider().services_summary(org, _query(range_))
    services.sort(key=lambda s: s['errors'], reverse=True)
    rows = [[s['service'], s['errors'], s['events'], s['error_rate'], s['last_seen']] for s in services[:25]]
    return {
        'title': 'Top error-producing services',
        'columns': ['service', 'errors', 'events', 'error_rate_%', 'last_seen'],
        'rows': rows,
        'summary': {'services_reporting': len(services)},
    }


def source_availability(org, range_):
    rows = [
        [
            s.name,
            s.source_type,
            s.environment,
            s.status,
            s.last_seen.isoformat() if s.last_seen else '',
            s.events_24h,
            s.stale_after_minutes,
        ]
        for s in LogSource.objects.filter(organization=org)
    ]
    counts = LogSource.objects.filter(organization=org).values('status').annotate(n=Count('id'))
    return {
        'title': 'Source availability',
        'columns': ['source', 'type', 'environment', 'status', 'last_seen', 'events_24h', 'stale_after_min'],
        'rows': rows,
        'summary': {c['status']: c['n'] for c in counts},
    }


def _since(range_):
    from search.query import parse_relative

    return timezone.now() - parse_relative(range_)


def alert_history(org, range_):
    events = AlertEvent.objects.filter(organization=org, started_at__gte=_since(range_))
    rows = [
        [
            e.started_at.isoformat(),
            e.rule_name,
            e.severity,
            e.category,
            e.status,
            e.occurrences,
            e.resolved_at.isoformat() if e.resolved_at else '',
            round((e.resolved_at - e.started_at).total_seconds() / 60, 1) if e.resolved_at else '',
        ]
        for e in events[:1000]
    ]
    by_sev = events.values('severity').annotate(n=Count('id'))
    return {
        'title': 'Alert history',
        'columns': [
            'started_at',
            'rule',
            'severity',
            'category',
            'status',
            'occurrences',
            'resolved_at',
            'duration_min',
        ],
        'rows': rows,
        'summary': {'total': events.count(), **{f"severity_{s['severity']}": s['n'] for s in by_sev}},
    }


def storage(org, range_):
    st = ElasticsearchProvider().storage(org)
    ds, disk = st.get('data_stream') or {}, st.get('disk') or {}
    rows = [
        ['data_stream', ds.get('name')],
        ['backing_indices', ds.get('backing_indices')],
        ['store_size_bytes', ds.get('store_size_bytes')],
        ['disk_total_bytes', disk.get('total_bytes')],
        ['disk_available_bytes', disk.get('available_bytes')],
        ['disk_used_percent', disk.get('used_percent')],
    ]
    return {'title': 'Storage utilization', 'columns': ['metric', 'value'], 'rows': rows, 'summary': {}}


def security_summary(org, range_):
    q = _query(range_)
    agg = ElasticsearchProvider().aggregate(
        org,
        q,
        {
            'types': {
                'type': 'terms',
                'field': 'event_type',
                'size': 20,
                'filter': {'event_type': ['auth_failure', 'auth_success', 'permission_denied', 'suspicious_request']},
            },
            'users': {'type': 'terms', 'field': 'user', 'size': 10, 'filter': {'event_type': ['auth_failure']}},
            'ips': {'type': 'terms', 'field': 'client_ip', 'size': 10, 'filter': {'event_type': ['auth_failure']}},
        },
    )
    detections = AlertEvent.objects.filter(organization=org, category='security', started_at__gte=_since(range_))
    rows = [['event_type', b['key'], b['count']] for b in agg['types']['buckets']]
    rows += [['failed_login_user', b['key'], b['count']] for b in agg['users']['buckets']]
    rows += [['failed_login_ip', b['key'], b['count']] for b in agg['ips']['buckets']]
    rows += [['detection', e.rule_name, e.occurrences] for e in detections[:50]]
    return {
        'title': 'Security event summary',
        'columns': ['category', 'key', 'count'],
        'rows': rows,
        'summary': {'security_detections': detections.count()},
    }


REPORTS = {
    'log-volume': log_volume,
    'error-trend': error_trend,
    'top-error-services': top_error_services,
    'source-availability': source_availability,
    'alert-history': alert_history,
    'storage': storage,
    'security-summary': security_summary,
}
REPORT_TITLES = {
    'log-volume': 'Log volume trends',
    'error-trend': 'Application error trends',
    'top-error-services': 'Top error-producing services',
    'source-availability': 'Source availability',
    'alert-history': 'Alert history',
    'storage': 'Storage utilization',
    'security-summary': 'Security event summary',
}
