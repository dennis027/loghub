from unittest import mock

import pytest
from django.http import QueryDict

from core.exceptions import InvalidQuery, ProviderUnavailable
from search.masking import mask_hit
from search.providers.elasticsearch import ElasticsearchProvider, auto_interval, build_query
from search.providers.graylog import GraylogProvider
from search.query import LogQuery, decode_cursor, encode_cursor


class Org:
    slug = 'acme-corp'
    masked_fields = ['customer.email']


ORG = Org()


def test_query_always_filters_by_organization():
    q = LogQuery.from_params({'q': 'error'})
    body = build_query(ORG, q)
    assert {'term': {'organization': 'acme_corp'}} in body['bool']['filter']


def test_standard_filters_from_querydict():
    params = QueryDict('service=api&service=web&level=error,critical')
    q = LogQuery.from_params(params)
    assert q.filters == {'service': ['api', 'web'], 'level': ['error', 'critical']}
    body = build_query(ORG, q)
    assert {'terms': {'service': ['api', 'web']}} in body['bool']['filter']


@pytest.mark.parametrize('field', ['organization', 'bad field', 'x;drop', '', '../etc'])
def test_field_filters_reject_unsafe_fields(field):
    with pytest.raises(InvalidQuery):
        LogQuery.from_params({'field_filters': [{'field': field, 'op': 'eq', 'value': 'x'}]})


def test_field_filter_operators():
    q = LogQuery.from_params(
        {
            'field_filters': [
                {'field': 'http.status', 'op': 'gte', 'value': 500},
                {'field': 'user', 'op': 'neq', 'value': 'bot'},
                {'field': 'trace_id', 'op': 'exists'},
                {'field': 'message.keyword', 'op': 'contains', 'value': 'a*b?'},
            ]
        }
    )
    body = build_query(ORG, q)['bool']
    assert {'range': {'http.status': {'gte': 500}}} in body['filter']
    assert {'term': {'user': 'bot'}} in body['must_not']
    assert {'exists': {'field': 'trace_id'}} in body['filter']
    wildcard = next(f for f in body['filter'] if 'wildcard' in f)
    assert wildcard['wildcard']['message.keyword']['value'] == '*a\\*b\\?*'


def test_lucene_mode_is_constrained():
    q = LogQuery.from_params({'q': 'level:error', 'mode': 'lucene'})
    qs = build_query(ORG, q)['bool']['must'][0]['query_string']
    assert qs['allow_leading_wildcard'] is False
    with pytest.raises(InvalidQuery):
        build_query(ORG, LogQuery.from_params({'q': 'organization:other', 'mode': 'lucene'}))


def test_simple_mode_default():
    body = build_query(ORG, LogQuery.from_params({'q': 'timeout'}))
    assert 'simple_query_string' in body['bool']['must'][0]


@pytest.mark.parametrize(
    'params',
    [
        {'mode': 'sql'},
        {'range': '10y'},
        {'start': 'yesterday'},
        {'range': '200d'},
        {'start': '2026-01-02T00:00:00Z', 'end': '2026-01-01T00:00:00Z'},
        {'size': 'many'},
        {'order': 'random'},
        {'q': 'x' * 2001},
        {'field_filters': 'not-json'},
    ],
)
def test_invalid_queries_rejected(params):
    with pytest.raises(InvalidQuery):
        LogQuery.from_params(params)


def test_size_is_capped():
    assert LogQuery.from_params({'size': 100000}, max_size=500).size == 500


def test_cursor_roundtrip_and_tamper():
    cursor = encode_cursor([1700000000000, 'abc'])
    assert decode_cursor(cursor) == [1700000000000, 'abc']
    with pytest.raises(InvalidQuery):
        decode_cursor('not-a-cursor!!')


def test_auto_interval():
    q = LogQuery.from_params({'range': '1h'})
    assert auto_interval(q.start, q.end) == '1m'
    q = LogQuery.from_params({'range': '7d'})
    assert auto_interval(q.start, q.end) == '3h'


def _es_hit(i, **src):
    return {
        '_id': f'id{i}',
        '_index': '.ds-logs-loghub-acme_corp',
        'sort': [i, f'fp{i}'],
        '_source': {'@timestamp': '2026-01-01T00:00:00Z', 'message': f'm{i}', 'level': 'info', **src},
    }


def test_elasticsearch_search_adapter_normalizes_and_paginates():
    client = mock.Mock()
    client.search.return_value = {
        'took': 3,
        'timed_out': False,
        'hits': {'total': {'value': 2, 'relation': 'eq'}, 'hits': [_es_hit(1), _es_hit(2)]},
    }
    provider = ElasticsearchProvider(client=client)
    result = provider.search(ORG, LogQuery.from_params({'size': 2}))
    kwargs = client.search.call_args.kwargs
    assert kwargs['index'] == 'logs-loghub-acme_corp'
    assert kwargs['timeout'] == '10s'
    assert result.total == 2 and [h['message'] for h in result.hits] == ['m1', 'm2']
    assert decode_cursor(result.cursor) == [2, 'fp2']


def test_elasticsearch_errors_map_to_api_errors():
    from elasticsearch import ApiError
    from elasticsearch import ConnectionError as ESConnectionError

    client = mock.Mock()
    meta = mock.Mock(status=400)
    client.search.side_effect = ApiError('bad', meta, {'error': {'root_cause': [{'reason': 'parse failure'}]}})
    with pytest.raises(InvalidQuery, match='parse failure'):
        ElasticsearchProvider(client=client).search(ORG, LogQuery.from_params({}))
    client.search.side_effect = ESConnectionError('down')
    with pytest.raises(ProviderUnavailable):
        ElasticsearchProvider(client=client).search(ORG, LogQuery.from_params({}))


def test_aggregate_parses_histogram_terms_and_metrics():
    client = mock.Mock()
    client.search.return_value = {
        'took': 1,
        'hits': {'total': {'value': 10}},
        'aggregations': {
            'volume': {
                'buckets': [
                    {
                        'key': 1,
                        'key_as_string': 't1',
                        'doc_count': 4,
                        'split': {'buckets': [{'key': 'error', 'doc_count': 4}]},
                    }
                ]
            },
            'top': {'buckets': [{'key': 'api', 'doc_count': 7}], 'sum_other_doc_count': 3},
            'errs': {'doc_count': 5, 'inner': {'value': 5}},
            'p95': {'values': {'95.0': 120.5}},
        },
    }
    out = ElasticsearchProvider(client=client).aggregate(
        ORG,
        LogQuery.from_params({}),
        {
            'volume': {'type': 'histogram', 'split_by': 'level'},
            'top': {'type': 'terms', 'field': 'service'},
            'errs': {'type': 'metric', 'filter': {'level': ['error']}},
            'p95': {'type': 'metric', 'metric': 'p95', 'metric_field': 'http.duration_ms'},
        },
    )
    assert out['volume']['buckets'][0]['series'] == {'error': 4}
    assert out['top'] == {'buckets': [{'key': 'api', 'count': 7}], 'other': 3}
    assert out['errs']['value'] == 5
    assert out['p95']['value'] == 120.5


def test_aggregate_rejects_unknown_metric():
    with pytest.raises(InvalidQuery):
        ElasticsearchProvider(client=mock.Mock()).aggregate(
            ORG, LogQuery.from_params({}), {'x': {'type': 'metric', 'metric': 'script', 'metric_field': 'a'}}
        )


def test_graylog_adapter_scopes_and_filters_by_org():
    provider = GraylogProvider()
    with mock.patch.object(provider, '_get') as get:
        get.return_value = {
            'total_results': 2,
            'messages': [
                {'index': 'g_0', 'message': {'_id': 'a', 'organization': 'acme_corp', 'message': 'mine'}},
                {'index': 'g_0', 'message': {'_id': 'b', 'organization': 'globex', 'message': 'leak'}},
            ],
        }
        result = provider.search(ORG, LogQuery.from_params({'q': 'x) OR (y', 'service': 'api'}))
    sent = get.call_args.args[1]['query']
    assert sent.startswith('organization:acme_corp AND (x) OR (y)')
    assert [h['message'] for h in result.hits] == ['mine']  # foreign org discarded


def test_graylog_rejects_org_field():
    with pytest.raises(InvalidQuery):
        GraylogProvider()._graylog_query(ORG, LogQuery.from_params({'q': 'organization:globex'}))


def test_kibana_link():
    link = ElasticsearchProvider(client=mock.Mock()).external_link(
        LogQuery.from_params({'q': "it's", 'service': 'api'})
    )
    assert '/app/discover#/' in link and 'loghub-logs' in link


class TestMasking:
    def _hit(self):
        return {
            'user': 'alice',
            'message': 'x',
            'source': {'user': 'alice', 'client_ip': '1.2.3.4', 'raw': '{}', 'customer': {'email': 'a@b.c'}},
        }

    def test_viewer_does_not_see_personal_fields(self, viewer_user):
        hit = mask_hit(self._hit(), viewer_user, ORG)
        assert hit['user'] == '[MASKED]' and hit['source']['client_ip'] == '[MASKED]'
        assert hit['source']['customer']['email'] == '[MASKED]'

    def test_analyst_sees_personal_but_not_configured_fields(self, analyst_user):
        hit = mask_hit(self._hit(), analyst_user, ORG)
        assert hit['user'] == 'alice'
        assert hit['source']['customer']['email'] == '[MASKED]'


@pytest.mark.django_db
class TestSearchApi:
    def test_search_endpoint_uses_provider_and_masks(self, viewer_client):
        from search.providers.base import SearchResult

        result = SearchResult(
            provider='elasticsearch',
            total=1,
            hits=[{'id': '1', 'message': 'hi', 'user': 'bob', 'source': {'user': 'bob'}}],
        )
        with mock.patch('search.providers.elasticsearch.ElasticsearchProvider.search', return_value=result):
            resp = viewer_client.get('/api/logs/search/?q=hi')
        assert resp.status_code == 200
        assert resp.data['executed_by'] == 'LogHub API → Elasticsearch'
        assert resp.data['hits'][0]['user'] == '[MASKED]'

    def test_live_tail_accepts_event_stream(self, viewer_client):
        """Browsers send Accept: text/event-stream; content negotiation must not 406."""
        with (
            mock.patch('search.providers.elasticsearch.ElasticsearchProvider.tail', return_value=([], None)),
            mock.patch('search.views.time.sleep'),
            mock.patch.dict('django.conf.settings.LOGHUB', {'LIVE_STREAM_MAX_SECONDS': 0}),
        ):
            resp = viewer_client.get('/api/logs/live/', HTTP_ACCEPT='text/event-stream')
            body = b''.join(resp.streaming_content).decode()
        assert resp.status_code == 200 and resp['Content-Type'] == 'text/event-stream'
        assert body.startswith('retry: 3000') and 'event: end' in body

    def test_unknown_provider(self, viewer_client):
        resp = viewer_client.get('/api/logs/search/?provider=splunk')
        assert resp.status_code == 400 and resp.data['error']['code'] == 'invalid_query'

    def test_backend_down_returns_503(self, viewer_client):
        with mock.patch(
            'search.providers.elasticsearch.ElasticsearchProvider.search', side_effect=ProviderUnavailable()
        ):
            resp = viewer_client.get('/api/logs/search/')
        assert resp.status_code == 503 and resp.data['error']['code'] == 'provider_unavailable'

    def test_aggregate_requires_specs(self, viewer_client):
        assert viewer_client.post('/api/logs/aggregate/', {}, format='json').status_code == 400

    def test_saved_search_validation_and_visibility(self, org, analyst_user, viewer_client):
        from tests.conftest import client_for

        analyst = client_for(analyst_user)
        bad = analyst.post('/api/saved-searches/', {'name': 'x', 'filters': {'organization': ['y']}}, format='json')
        assert bad.status_code == 400
        ok = analyst.post('/api/saved-searches/', {'name': 'mine', 'query': 'err', 'is_shared': False}, format='json')
        assert ok.status_code == 201
        assert viewer_client.get('/api/saved-searches/').data['count'] == 0

    def test_export_csv_escapes_formulas(self, org, analyst_user):
        from search.providers.base import SearchResult
        from tests.conftest import client_for

        result = SearchResult(
            provider='elasticsearch',
            total=1,
            hits=[{'id': '1', 'message': '=HYPERLINK("http://evil")', 'timestamp': 't', 'source': {}}],
        )
        with mock.patch('search.providers.elasticsearch.ElasticsearchProvider.search', return_value=result):
            resp = client_for(analyst_user).get('/api/logs/export/?format=csv')
            body = b''.join(resp.streaming_content).decode()
        assert resp.status_code == 200
        assert "'=HYPERLINK" in body
        from audit.models import AuditEvent

        assert AuditEvent.objects.filter(action='export').exists()
