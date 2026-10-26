"""Built-in dashboards seeded for every organization (editable copies)."""


def w(wid, title, wtype, agg=None, query=None, cols=2, source='logs', promql=None, unit=None):
    # Widget queries use the same flat shape as the search API: {q, level: [...], service: [...], field_filters}.
    query = dict(query or {})
    query.update(query.pop('filters', {}))
    widget = {'id': wid, 'title': title, 'type': wtype, 'source': source, 'layout': {'cols': cols}, 'query': query}
    if agg:
        widget['agg'] = agg
    if promql:
        widget['promql'] = promql
    if unit:
        widget['unit'] = unit
    return widget


ERRORS = {'level': ['error', 'critical']}
HIST_LEVEL = {'type': 'histogram', 'split_by': 'level'}

DASHBOARD_TEMPLATES = [
    {
        'name': 'Application errors',
        'category': 'application',
        'folder': 'Built-in',
        'grafana_uid': 'loghub-logs',
        'description': 'Error and critical events across applications.',
        'widgets': [
            w('e1', 'Errors', 'stat', {'type': 'metric'}, {'filters': ERRORS}, cols=1),
            w('e2', 'Critical', 'stat', {'type': 'metric'}, {'filters': {'level': ['critical']}}, cols=1),
            w(
                'e3',
                'Services with errors',
                'stat',
                {'type': 'metric', 'metric': 'cardinality', 'metric_field': 'service'},
                {'filters': ERRORS},
                cols=2,
            ),
            w(
                'e4',
                'Errors over time by service',
                'timeseries',
                {'type': 'histogram', 'split_by': 'service'},
                {'filters': ERRORS},
                cols=4,
            ),
            w(
                'e5',
                'Top error services',
                'bar',
                {'type': 'terms', 'field': 'service', 'size': 10},
                {'filters': ERRORS},
            ),
            w(
                'e6',
                'Most frequent error messages',
                'table',
                {'type': 'terms', 'field': 'message.keyword', 'size': 10},
                {'filters': ERRORS},
            ),
            w('e7', 'Latest errors', 'logs', None, {'filters': ERRORS}, cols=4),
        ],
    },
    {
        'name': 'API request activity',
        'category': 'api',
        'folder': 'Built-in',
        'grafana_uid': 'loghub-web',
        'description': 'Request volume, status codes and latency from structured access logs.',
        'widgets': [
            w(
                'a1',
                'Requests',
                'stat',
                {'type': 'metric'},
                {'field_filters': [{'field': 'http.status', 'op': 'exists'}]},
                1,
            ),
            w(
                'a2',
                'p95 latency (ms)',
                'stat',
                {'type': 'metric', 'metric': 'p95', 'metric_field': 'http.duration_ms'},
                {'field_filters': [{'field': 'http.duration_ms', 'op': 'exists'}]},
                1,
                unit='ms',
            ),
            w(
                'a3',
                '5xx responses',
                'stat',
                {'type': 'metric'},
                {'field_filters': [{'field': 'http.status', 'op': 'gte', 'value': 500}]},
                2,
            ),
            w(
                'a4',
                'Requests by status',
                'timeseries',
                {'type': 'histogram', 'split_by': 'http.status'},
                {'field_filters': [{'field': 'http.status', 'op': 'exists'}]},
                4,
            ),
            w(
                'a5',
                'Top endpoints',
                'table',
                {
                    'type': 'terms',
                    'field': 'http.path',
                    'size': 15,
                    'metric': 'avg',
                    'metric_field': 'http.duration_ms',
                },
                {'field_filters': [{'field': 'http.path', 'op': 'exists'}]},
            ),
            w(
                'a6',
                'Methods',
                'pie',
                {'type': 'terms', 'field': 'http.method'},
                {'field_filters': [{'field': 'http.method', 'op': 'exists'}]},
            ),
        ],
    },
    {
        'name': 'Authentication events',
        'category': 'auth',
        'folder': 'Built-in',
        'description': 'Logins, failures and the accounts involved.',
        'widgets': [
            w('u1', 'Failed logins', 'stat', {'type': 'metric'}, {'filters': {'event_type': ['auth_failure']}}, 2),
            w('u2', 'Successful logins', 'stat', {'type': 'metric'}, {'filters': {'event_type': ['auth_success']}}, 2),
            w(
                'u3',
                'Authentication events',
                'timeseries',
                {'type': 'histogram', 'split_by': 'event_type'},
                {'filters': {'event_type': ['auth_failure', 'auth_success']}},
                4,
            ),
            w(
                'u4',
                'Most targeted accounts',
                'table',
                {'type': 'terms', 'field': 'user'},
                {'filters': {'event_type': ['auth_failure']}},
            ),
            w(
                'u5',
                'Failures by client IP',
                'table',
                {'type': 'terms', 'field': 'client_ip'},
                {'filters': {'event_type': ['auth_failure']}},
            ),
        ],
    },
    {
        'name': 'Web server access',
        'category': 'web',
        'folder': 'Built-in',
        'grafana_uid': 'loghub-web',
        'description': 'Nginx/Apache access logs parsed by Logstash.',
        'widgets': [
            w(
                'w1',
                'Access log volume by status',
                'timeseries',
                {'type': 'histogram', 'split_by': 'http.status'},
                {'filters': {'event_type': ['http_access']}},
                4,
            ),
            w(
                'w2',
                'Top paths',
                'bar',
                {'type': 'terms', 'field': 'http.path', 'size': 10},
                {'filters': {'event_type': ['http_access']}},
            ),
            w(
                'w3',
                'User agents',
                'table',
                {'type': 'terms', 'field': 'http.user_agent', 'size': 10},
                {'filters': {'event_type': ['http_access']}},
            ),
        ],
    },
    {
        'name': 'Database logs',
        'category': 'database',
        'folder': 'Built-in',
        'description': 'PostgreSQL / MySQL log events.',
        'widgets': [
            w(
                'd1',
                'Database events by level',
                'timeseries',
                HIST_LEVEL,
                {'filters': {'source_type': ['postgres', 'mysql']}},
                4,
            ),
            w(
                'd2',
                'Slow or failing statements',
                'logs',
                None,
                {'q': 'duration | deadlock | timeout | error', 'filters': {'source_type': ['postgres', 'mysql']}},
                4,
            ),
        ],
    },
    {
        'name': 'Docker containers',
        'category': 'docker',
        'folder': 'Built-in',
        'description': 'Logs shipped by the Docker fluentd driver.',
        'widgets': [
            w(
                'c1',
                'Log volume by container',
                'timeseries',
                {'type': 'histogram', 'split_by': 'container'},
                {'filters': {'source_type': ['docker']}},
                4,
            ),
            w(
                'c2',
                'Containers',
                'table',
                {'type': 'terms', 'field': 'container', 'size': 20},
                {'filters': {'source_type': ['docker']}},
            ),
            w(
                'c3',
                'stderr vs stdout',
                'pie',
                {'type': 'terms', 'field': 'stream'},
                {'filters': {'source_type': ['docker']}},
            ),
        ],
    },
    {
        'name': 'Infrastructure metrics',
        'category': 'infrastructure',
        'folder': 'Built-in',
        'grafana_uid': 'loghub-infra',
        'description': 'Host metrics from Prometheus node-exporter.',
        'widgets': [
            w(
                'i1',
                'CPU usage %',
                'timeseries',
                source='prometheus',
                unit='%',
                promql='100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[2m])) * 100)',
            ),
            w(
                'i2',
                'Memory used %',
                'timeseries',
                source='prometheus',
                unit='%',
                promql='(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
            ),
            w('i3', 'Load average (1m)', 'timeseries', source='prometheus', promql='node_load1'),
            w(
                'i4',
                'Root disk used %',
                'timeseries',
                source='prometheus',
                unit='%',
                promql=(
                    '(1 - node_filesystem_avail_bytes{mountpoint="/"}'
                    ' / node_filesystem_size_bytes{mountpoint="/"}) * 100'
                ),
            ),
        ],
    },
    {
        'name': 'Security events',
        'category': 'security',
        'folder': 'Built-in',
        'description': 'Detections, auth failures and suspicious requests.',
        'widgets': [
            w(
                's1',
                'Auth failures over time',
                'timeseries',
                {'type': 'histogram'},
                {'filters': {'event_type': ['auth_failure']}},
                4,
            ),
            w(
                's2',
                'Suspicious requests',
                'logs',
                None,
                {'q': '"union select" | "or 1=1" | ".env" | "wp-admin" | "Failed password"'},
                4,
            ),
            w(
                's3',
                'Security event types',
                'pie',
                {'type': 'terms', 'field': 'event_type'},
                {'filters': {'event_type': ['auth_failure', 'permission_denied', 'suspicious_request']}},
            ),
        ],
    },
]
