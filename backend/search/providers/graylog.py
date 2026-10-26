import logging
import time
from urllib.parse import urlencode

import requests
from django.conf import settings

from core.exceptions import InvalidQuery, ProviderUnavailable
from core.tenancy import org_index_key

from .base import HealthResult, LogProvider, SearchResult

logger = logging.getLogger(__name__)

TIMEOUT = 10
# GELF carries syslog severities; map back to LogHub's level names.
GELF_LEVELS = {0: 'critical', 1: 'critical', 2: 'critical', 3: 'error', 4: 'warning', 5: 'info', 6: 'info', 7: 'debug'}
_session = requests.Session()  # pooled keep-alive connections


def _cfg():
    cfg = settings.LOGHUB
    return cfg['GRAYLOG_URL'].rstrip('/'), (cfg['GRAYLOG_USERNAME'], cfg['GRAYLOG_PASSWORD'])


def _lucene_escape(value):
    return ''.join('\\' + c if c in '+-=&|><!(){}[]^"~*?:\\/ ' else c for c in str(value))


class GraylogProvider(LogProvider):
    """Search through Graylog's REST API (universal relative/absolute search).

    Graylog has no tenant model in this deployment; events carry the
    `organization` field stamped by Fluent Bit. The adapter refuses queries that
    reference that field and also discards any returned message whose
    organization does not match, so a crafted query cannot read another tenant.
    """

    name = 'graylog'
    label = 'Graylog'

    def _get(self, path, params=None):
        base, auth = _cfg()
        try:
            resp = _session.get(
                f'{base}{path}',
                params=params,
                auth=auth,
                timeout=TIMEOUT,
                headers={'Accept': 'application/json', 'X-Requested-By': 'loghub'},
            )
        except requests.RequestException as exc:
            raise ProviderUnavailable(f'Graylog is unreachable: {exc.__class__.__name__}') from None
        if resp.status_code == 400:
            raise InvalidQuery(f'Graylog rejected the query: {resp.text[:300]}')
        if resp.status_code in (401, 403):
            raise ProviderUnavailable('Graylog rejected the LogHub service credentials.')
        if resp.status_code >= 400:
            raise ProviderUnavailable(f'Graylog error {resp.status_code}.')
        return resp.json()

    def _graylog_query(self, organization, query):
        if 'organization' in query.q:
            raise InvalidQuery('Queries may not reference the organization field.')
        clauses = [f'organization:{_lucene_escape(org_index_key(organization.slug))}']
        if query.q:
            clauses.append(f'({query.q})')
        for field, values in query.filters.items():
            clauses.append('(' + ' OR '.join(f'{field}:{_lucene_escape(v)}' for v in values) + ')')
        for ff in query.field_filters:
            if ff.op == 'eq':
                clauses.append(f'{ff.field}:{_lucene_escape(ff.value)}')
            elif ff.op == 'neq':
                clauses.append(f'NOT {ff.field}:{_lucene_escape(ff.value)}')
            elif ff.op == 'exists':
                clauses.append(f'_exists_:{ff.field}')
            elif ff.op == 'missing':
                clauses.append(f'NOT _exists_:{ff.field}')
            elif ff.op in ('gt', 'gte', 'lt', 'lte'):
                op = {'gt': '>', 'gte': '>=', 'lt': '<', 'lte': '<='}[ff.op]
                clauses.append(f'{ff.field}:{op}{_lucene_escape(ff.value)}')
        return ' AND '.join(clauses)

    def search(self, organization, query):
        params = {
            'query': self._graylog_query(organization, query),
            'from': query.start.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            'to': query.end.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            'limit': query.size,
            'sort': f'timestamp:{query.order}',
            'decorate': 'false',
        }
        started = time.monotonic()
        data = self._get('/api/search/universal/absolute', params)
        key = org_index_key(organization.slug)
        hits = []
        for item in data.get('messages', []):
            msg = item.get('message', {})
            if msg.get('organization') != key:
                continue
            hits.append(
                {
                    'id': msg.get('_id'),
                    'index': item.get('index'),
                    'timestamp': msg.get('timestamp'),
                    'level': GELF_LEVELS.get(msg.get('level'), msg.get('level')),
                    'service': msg.get('service'),
                    'environment': msg.get('environment'),
                    'hostname': msg.get('source') or msg.get('hostname'),
                    'container': msg.get('container'),
                    'source_id': msg.get('source_id'),
                    'message': msg.get('message', ''),
                    'trace_id': msg.get('trace_id'),
                    'demo': str(msg.get('demo')).lower() == 'true',
                    'source': {
                        k: v
                        for k, v in msg.items()
                        if k not in ('gl2_source_input', 'gl2_source_node', 'gl2_accounted_message_size', 'streams')
                    },
                }
            )
        return SearchResult(
            provider=self.name,
            hits=hits,
            total=data.get('total_results', len(hits)),
            took_ms=int((time.monotonic() - started) * 1000),
        )

    def inputs(self):
        return self._get('/api/system/inputs').get('inputs', [])

    def streams(self):
        return self._get('/api/streams').get('streams', [])

    def health(self):
        base, auth = _cfg()
        started = time.monotonic()
        try:
            resp = _session.get(f'{base}/api/system/lbstatus', timeout=5)
            alive = resp.status_code == 200 and 'ALIVE' in resp.text
            info = _session.get(f'{base}/api', auth=auth, timeout=5, headers={'Accept': 'application/json'})
        except requests.RequestException as exc:
            return HealthResult('unhealthy', message=f'unreachable: {exc.__class__.__name__}')
        latency = round((time.monotonic() - started) * 1000, 1)
        if not alive:
            return HealthResult(
                'unhealthy', message=f'load balancer status {resp.text.strip()[:50]}', latency_ms=latency
            )
        if info.status_code in (401, 403):
            return HealthResult(
                'degraded', message='alive, but LogHub reader credentials are rejected', latency_ms=latency
            )
        version = info.json().get('version', '') if info.ok else ''
        details = {}
        try:
            details['inputs'] = [
                {'title': i['title'], 'type': i['type'].rsplit('.', 1)[-1], 'port': i.get('attributes', {}).get('port')}
                for i in self.inputs()
            ]
        except (ProviderUnavailable, InvalidQuery, KeyError):
            details['inputs'] = None
        return HealthResult(
            'healthy', message='Graylog node is alive', latency_ms=latency, version=version, details=details
        )

    def external_link(self, query):
        base = settings.LOGHUB['GRAYLOG_PUBLIC_URL'].rstrip('/')
        params = {
            'q': query.q or '*',
            'rangetype': 'absolute',
            'from': query.start.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
            'to': query.end.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
        }
        return f'{base}/search?{urlencode(params)}'
