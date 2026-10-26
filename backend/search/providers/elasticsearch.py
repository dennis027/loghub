import logging
import threading
import time
from urllib.parse import quote

from django.conf import settings
from elasticsearch import ApiError, Elasticsearch, TransportError

from core.exceptions import InvalidQuery, ProviderUnavailable
from core.tenancy import org_index, org_index_key

from ..query import validate_field
from .base import HealthResult, LogProvider, SearchResult

logger = logging.getLogger(__name__)

SIMPLE_QUERY_FIELDS = ['message', 'service', 'hostname', 'container', 'event_type', 'logger', 'user']
# fixed_interval candidates for auto histograms (seconds, label)
INTERVALS = [
    (1, '1s'),
    (5, '5s'),
    (10, '10s'),
    (30, '30s'),
    (60, '1m'),
    (300, '5m'),
    (600, '10m'),
    (1800, '30m'),
    (3600, '1h'),
    (10800, '3h'),
    (21600, '6h'),
    (43200, '12h'),
    (86400, '1d'),
]
METRICS = {'avg', 'max', 'min', 'sum', 'cardinality', 'p95', 'p99'}
QUERY_TIMEOUT = '10s'

_client = None
_client_lock = threading.Lock()


def get_client():
    """Process-wide client; elastic-transport keeps a pooled urllib3 connection set."""
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                cfg = settings.LOGHUB
                auth = (
                    (cfg['ELASTICSEARCH_USERNAME'], cfg['ELASTICSEARCH_PASSWORD'])
                    if cfg['ELASTICSEARCH_USERNAME']
                    else None
                )
                _client = Elasticsearch(
                    cfg['ELASTICSEARCH_URL'],
                    basic_auth=auth,
                    request_timeout=cfg['ELASTICSEARCH_TIMEOUT'],
                    max_retries=2,
                    retry_on_timeout=True,
                    connections_per_node=20,
                )
    return _client


def auto_interval(start, end, buckets=60):
    span = max((end - start).total_seconds(), 1)
    target = span / buckets
    for seconds, label in INTERVALS:
        if seconds >= target:
            return label
    return INTERVALS[-1][1]


def _escape_wildcard(value):
    return ''.join('\\' + c if c in '*?\\' else c for c in str(value))


def build_query(organization, query):
    """Translate a LogQuery into an Elasticsearch bool query.

    The organization filter is always applied as a non-scoring filter clause,
    in addition to querying only the organization's own data stream.
    """
    must, filters, must_not = [], [], []
    filters.append({'term': {'organization': org_index_key(organization.slug)}})
    filters.append({'range': {'@timestamp': {'gte': query.start.isoformat(), 'lte': query.end.isoformat()}}})

    if query.q:
        if query.mode == 'lucene':
            if 'organization:' in query.q:
                raise InvalidQuery('Queries may not reference the organization field.')
            must.append(
                {
                    'query_string': {
                        'query': query.q,
                        'default_operator': 'AND',
                        'lenient': True,
                        'allow_leading_wildcard': False,
                        'analyze_wildcard': False,
                        'max_determinized_states': 10000,
                    }
                }
            )
        else:
            must.append(
                {
                    'simple_query_string': {
                        'query': query.q,
                        'fields': SIMPLE_QUERY_FIELDS,
                        'default_operator': 'AND',
                        'lenient': True,
                        'flags': 'AND|OR|NOT|PHRASE|PREFIX|PRECEDENCE|ESCAPE|WHITESPACE',
                    }
                }
            )

    for field, values in query.filters.items():
        filters.append({'terms': {field: values}})

    for ff in query.field_filters:
        field, value = ff.field, ff.value
        if ff.op == 'eq':
            filters.append({'terms': {field: value}} if isinstance(value, list) else {'term': {field: value}})
        elif ff.op == 'neq':
            must_not.append({'terms': {field: value}} if isinstance(value, list) else {'term': {field: value}})
        elif ff.op == 'exists':
            filters.append({'exists': {'field': field}})
        elif ff.op == 'missing':
            must_not.append({'exists': {'field': field}})
        elif ff.op in ('gt', 'gte', 'lt', 'lte'):
            filters.append({'range': {field: {ff.op: value}}})
        elif ff.op == 'contains':
            filters.append({'wildcard': {field: {'value': f'*{_escape_wildcard(value)}*', 'case_insensitive': True}}})
    return {'bool': {'must': must or [{'match_all': {}}], 'filter': filters, 'must_not': must_not}}


def normalize_hit(hit):
    src = hit.get('_source', {})
    return {
        'id': hit['_id'],
        'index': hit.get('_index'),
        'timestamp': src.get('@timestamp'),
        'level': src.get('level'),
        'service': src.get('service'),
        'environment': src.get('environment'),
        'hostname': src.get('hostname'),
        'container': src.get('container'),
        'source_id': src.get('source_id'),
        'message': src.get('message', ''),
        'trace_id': src.get('trace_id'),
        'demo': bool(src.get('demo')),
        'source': src,
    }


class ElasticsearchProvider(LogProvider):
    name = 'elasticsearch'
    label = 'Elasticsearch'
    supports_aggregations = True
    supports_cursor = True

    def __init__(self, client=None):
        self._client = client

    @property
    def client(self):
        return self._client or get_client()

    def _call(self, fn, **kwargs):
        try:
            return fn(**kwargs)
        except ApiError as exc:
            if exc.meta.status == 400:
                reason = self._root_cause(exc)
                raise InvalidQuery(f'Elasticsearch rejected the query: {reason}') from None
            if exc.meta.status in (401, 403):
                logger.error('Elasticsearch denied LogHub service account: %s', exc)
                raise ProviderUnavailable('Elasticsearch rejected the service credentials.') from None
            raise ProviderUnavailable(f'Elasticsearch error {exc.meta.status}.') from None
        except TransportError as exc:
            logger.warning('Elasticsearch unavailable: %s', exc)
            raise ProviderUnavailable('Elasticsearch is unreachable.') from None

    @staticmethod
    def _root_cause(exc):
        try:
            causes = exc.body['error'].get('root_cause') or [exc.body['error']]
            return causes[0].get('reason', 'invalid query')[:300]
        except (TypeError, KeyError, AttributeError):
            return 'invalid query'

    def _search(self, organization, **body):
        return self._call(
            self.client.search,
            index=org_index(organization),
            ignore_unavailable=True,
            allow_no_indices=True,
            timeout=QUERY_TIMEOUT,
            **body,
        )

    # -------------------------------------------------------------- search
    def search(self, organization, query):
        order = query.order
        kwargs = {
            'query': build_query(organization, query),
            'size': query.size,
            'sort': [{'@timestamp': {'order': order}}, {'fingerprint': {'order': order, 'unmapped_type': 'keyword'}}],
            'track_total_hits': 100000,
        }
        if query.cursor:
            kwargs['search_after'] = query.cursor
        resp = self._search(organization, **kwargs)
        hits = resp['hits']['hits']
        total = resp['hits']['total']
        cursor = None
        if len(hits) == query.size and hits:
            from ..query import encode_cursor

            cursor = encode_cursor(hits[-1]['sort'])
        return SearchResult(
            provider=self.name,
            hits=[normalize_hit(h) for h in hits],
            total=total['value'],
            total_relation=total['relation'],
            took_ms=resp.get('took', 0),
            cursor=cursor,
            timed_out=resp.get('timed_out', False),
        )

    def count(self, organization, query):
        resp = self._call(
            self.client.count,
            index=org_index(organization),
            ignore_unavailable=True,
            allow_no_indices=True,
            query=build_query(organization, query),
        )
        return resp['count']

    def get_event(self, organization, event_id):
        resp = self._search(
            organization,
            query={
                'bool': {
                    'filter': [
                        {'ids': {'values': [event_id]}},
                        {'term': {'organization': org_index_key(organization.slug)}},
                    ]
                }
            },
            size=1,
        )
        hits = resp['hits']['hits']
        return normalize_hit(hits[0]) if hits else None

    def tail(self, organization, query, after):
        """Events ingested after a cursor ([ingested_at_ms, fingerprint]) for live streaming."""
        kwargs = {
            'query': build_query(organization, query),
            'size': query.size,
            'sort': [
                {'ingested_at': {'order': 'asc', 'unmapped_type': 'date'}},
                {'fingerprint': {'order': 'asc', 'unmapped_type': 'keyword'}},
            ],
            'track_total_hits': False,
        }
        if after:
            kwargs['search_after'] = after
        resp = self._search(organization, **kwargs)
        hits = resp['hits']['hits']
        return [normalize_hit(h) for h in hits], (hits[-1]['sort'] if hits else after)

    # -------------------------------------------------------------- aggregations
    def _agg_body(self, query, spec):
        kind = spec.get('type', 'terms')
        metric = spec.get('metric')
        sub = {}
        if metric and metric != 'count':
            metric_field = validate_field(spec.get('metric_field', ''))
            if metric not in METRICS:
                raise InvalidQuery(f'Unsupported metric {metric!r}.')
            if metric in ('p95', 'p99'):
                sub['value'] = {'percentiles': {'field': metric_field, 'percents': [float(metric[1:])]}}
            else:
                sub['value'] = {metric: {'field': metric_field}}

        if kind == 'histogram':
            interval = spec.get('interval') or auto_interval(query.start, query.end)
            if interval not in {label for _, label in INTERVALS}:
                raise InvalidQuery(f'Unsupported interval {interval!r}.')
            body = {
                'date_histogram': {
                    'field': '@timestamp',
                    'fixed_interval': interval,
                    'min_doc_count': 0,
                    'extended_bounds': {'min': query.start.isoformat(), 'max': query.end.isoformat()},
                }
            }
            if split := spec.get('split_by'):
                body['aggs'] = {
                    'split': {
                        'terms': {'field': validate_field(split), 'size': min(int(spec.get('split_size', 6)), 12)},
                        **({'aggs': sub} if sub else {}),
                    }
                }
            elif sub:
                body['aggs'] = sub
            return body, interval
        if kind == 'terms':
            body = {'terms': {'field': validate_field(spec['field']), 'size': min(int(spec.get('size', 10)), 50)}}
            if sub:
                body['aggs'] = sub
            return body, None
        if kind == 'metric':
            if not sub:
                return {'value_count': {'field': '@timestamp'}}, None
            return sub['value'], None
        raise InvalidQuery(f'Unknown aggregation type {kind!r}.')

    @staticmethod
    def _metric_value(bucket):
        value = bucket.get('value')
        if isinstance(value, dict):
            if 'values' in value:
                return next(iter(value['values'].values()), None)
            return value.get('value')
        return value

    def aggregate(self, organization, query, specs):
        """Run several named aggregations in one request.

        specs: {name: {type: histogram|terms|metric, field, size, interval, split_by,
                       metric, metric_field, filter: <LogQuery-like dict with q/level/...>}}
        """
        from ..query import LogQuery

        aggs, meta = {}, {}
        for name, spec in specs.items():
            body, interval = self._agg_body(query, spec)
            meta[name] = (spec, interval)
            if spec.get('filter'):
                sub_query = LogQuery.from_params({**spec['filter'], 'start': query.start, 'end': query.end})
                inner = build_query(organization, sub_query)
                aggs[name] = {'filter': inner, 'aggs': {'inner': body}}
            else:
                aggs[name] = body
        resp = self._search(
            organization, query=build_query(organization, query), size=0, aggs=aggs, track_total_hits=True
        )
        out = {'_total': resp['hits']['total']['value'], '_took_ms': resp.get('took', 0)}
        for name, raw in resp.get('aggregations', {}).items():
            spec, interval = meta[name]
            if spec.get('filter'):
                filtered_count = raw.get('doc_count', 0)
                raw = raw.get('inner', raw)
            else:
                filtered_count = None
            kind = spec.get('type', 'terms')
            if kind == 'histogram':
                series = set()
                buckets = []
                for b in raw['buckets']:
                    item = {'key': b['key'], 'time': b['key_as_string'], 'count': b['doc_count']}
                    if 'split' in b:
                        item['series'] = {
                            s['key']: s['doc_count'] if 'value' not in s else self._metric_value(s)
                            for s in b['split']['buckets']
                        }
                        series.update(item['series'])
                    elif 'value' in b:
                        item['value'] = self._metric_value(b)
                    buckets.append(item)
                out[name] = {'interval': interval, 'buckets': buckets, 'series': sorted(series)}
            elif kind == 'terms':
                out[name] = {
                    'buckets': [
                        {
                            'key': b['key'],
                            'count': b['doc_count'],
                            **({'value': self._metric_value(b)} if 'value' in b else {}),
                        }
                        for b in raw['buckets']
                    ],
                    'other': raw.get('sum_other_doc_count', 0),
                }
            else:
                value = (
                    filtered_count
                    if spec.get('filter') and not spec.get('metric')
                    else (
                        raw.get('value')
                        if not isinstance(raw.get('values'), dict)
                        else next(iter(raw['values'].values()), None)
                    )
                )
                out[name] = {'value': value}
        return out

    def last_seen(self, organization, field, values=None, since='now-30d'):
        """Max ingested_at per value of `field` — drives source status."""
        flt = [{'term': {'organization': org_index_key(organization.slug)}}, {'range': {'@timestamp': {'gte': since}}}]
        if values:
            flt.append({'terms': {field: list(values)}})
        resp = self._search(
            organization,
            size=0,
            query={'bool': {'filter': flt}},
            aggs={
                'by': {
                    'terms': {'field': validate_field(field), 'size': 1000},
                    'aggs': {
                        'last': {'max': {'field': '@timestamp'}},
                        'count': {'value_count': {'field': '@timestamp'}},
                    },
                }
            },
        )
        return {
            b['key']: {'last_seen': b['last'].get('value_as_string'), 'count': b['doc_count']}
            for b in resp['aggregations']['by']['buckets']
        }

    def services_summary(self, organization, query, size=100):
        """Per-service volume, error count, last event, environments and hosts."""
        resp = self._search(
            organization,
            size=0,
            query=build_query(organization, query),
            aggs={
                'services': {
                    'terms': {'field': 'service', 'size': size},
                    'aggs': {
                        'errors': {'filter': {'terms': {'level': ['error', 'critical']}}},
                        'warnings': {'filter': {'term': {'level': 'warning'}}},
                        'last': {'max': {'field': '@timestamp'}},
                        'environments': {'terms': {'field': 'environment', 'size': 5}},
                        'hosts': {'cardinality': {'field': 'hostname'}},
                        'containers': {'cardinality': {'field': 'container'}},
                        'source_types': {'terms': {'field': 'source_type', 'size': 3}},
                    },
                }
            },
        )
        out = []
        for b in resp['aggregations']['services']['buckets']:
            total = b['doc_count']
            out.append(
                {
                    'service': b['key'],
                    'events': total,
                    'errors': b['errors']['doc_count'],
                    'warnings': b['warnings']['doc_count'],
                    'error_rate': round(100 * b['errors']['doc_count'] / total, 2) if total else 0,
                    'last_seen': b['last'].get('value_as_string'),
                    'environments': [e['key'] for e in b['environments']['buckets']],
                    'hosts': b['hosts']['value'],
                    'containers': b['containers']['value'],
                    'source_types': [s['key'] for s in b['source_types']['buckets']],
                }
            )
        return out

    # -------------------------------------------------------------- storage / admin
    def storage(self, organization=None):
        result = {'data_stream': None, 'disk': None}
        try:
            if organization is not None:
                stats = self.client.indices.data_streams_stats(name=org_index(organization))
                ds = (stats.get('data_streams') or [{}])[0]
                result['data_stream'] = {
                    'name': ds.get('data_stream'),
                    'backing_indices': ds.get('backing_indices'),
                    'store_size_bytes': ds.get('store_size_bytes'),
                }
        except ApiError as exc:
            if exc.meta.status != 404:
                logger.warning('data stream stats failed: %s', exc)
        except TransportError:
            raise ProviderUnavailable('Elasticsearch is unreachable.') from None
        fs = self._call(self.client.nodes.stats, metric='fs')
        total = available = 0
        for node in fs['nodes'].values():
            total += node['fs']['total']['total_in_bytes']
            available += node['fs']['total']['available_in_bytes']
        if total:
            result['disk'] = {
                'total_bytes': total,
                'available_bytes': available,
                'used_percent': round(100 * (total - available) / total, 1),
            }
        return result

    def put_retention(self, policy_name, rollover_days, delete_days):
        body = {
            'phases': {
                'hot': {'actions': {'rollover': {'max_age': f'{rollover_days}d', 'max_primary_shard_size': '10gb'}}},
                'delete': {'min_age': f'{delete_days}d', 'actions': {'delete': {}}},
            },
            '_meta': {'managed_by': 'loghub'},
        }
        self._call(self.client.ilm.put_lifecycle, name=policy_name, policy=body)
        return body

    def get_retention(self, policy_name):
        resp = self._call(self.client.ilm.get_lifecycle, name=policy_name)
        return resp.get(policy_name)

    def health(self):
        start = time.monotonic()
        try:
            info = self.client.info()
            health = self.client.cluster.health()
        except Exception as exc:
            return HealthResult('unhealthy', message=str(exc)[:300])
        latency = round((time.monotonic() - start) * 1000, 1)
        status = {'green': 'healthy', 'yellow': 'healthy', 'red': 'unhealthy'}[health['status']]
        msg = f"cluster {health['cluster_name']} is {health['status']}"
        if health['status'] == 'yellow':
            msg += ' (expected on a single node: replicas unassigned)'
        return HealthResult(
            status,
            message=msg,
            latency_ms=latency,
            version=info['version']['number'],
            details={
                'nodes': health['number_of_nodes'],
                'active_shards': health['active_shards'],
                'unassigned_shards': health['unassigned_shards'],
            },
        )

    def external_link(self, query):
        """Kibana Discover URL for the same query (Lucene syntax, LogHub data view)."""

        def rison(s):
            return "'" + s.replace('!', '!!').replace("'", "!'") + "'"

        q = query.q or ''
        for field, values in query.filters.items():
            clause = ' OR '.join(f'{field}:"{v}"' for v in values)
            q = f'({clause})' + (f' AND ({q})' if q else '')
        g = f'(time:(from:{rison(query.start.isoformat())},to:{rison(query.end.isoformat())}))'
        a = f"(dataSource:(dataViewId:'loghub-logs',type:dataView),query:(language:lucene,query:{rison(q)}))"
        base = settings.LOGHUB['KIBANA_PUBLIC_URL'].rstrip('/')
        return f"{base}/app/discover#/?_g={quote(g, safe='(),:!')}&_a={quote(a, safe='(),:!')}"
