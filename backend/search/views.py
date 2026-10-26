import csv
import io
import json
import logging
import time

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q
from django.http import StreamingHttpResponse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.renderers import BaseRenderer, JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import record_audit
from core.exceptions import InvalidQuery, ProviderUnavailable
from core.permissions import ROLE_ANALYST, ROLE_EDITOR, CanExportData, RoleRequired, has_role
from core.tenancy import OrganizationScopedMixin

from .masking import mask_hit
from .models import SavedSearch
from .providers.elasticsearch import ElasticsearchProvider
from .providers.registry import get_provider
from .query import LogQuery, decode_cursor
from .serializers import SavedSearchSerializer

logger = logging.getLogger(__name__)

QUERY_PARAMS = [
    OpenApiParameter('q', str, description='Search text'),
    OpenApiParameter(
        'mode',
        str,
        enum=['simple', 'lucene'],
        description='simple = forgiving simple_query_string; lucene = Kibana/Lucene syntax',
    ),
    OpenApiParameter('provider', str, enum=['elasticsearch', 'graylog']),
    OpenApiParameter('range', str, description='Relative range, e.g. 15m, 1h, 7d (default 1h)'),
    OpenApiParameter('start', str),
    OpenApiParameter('end', str),
    OpenApiParameter('service', str),
    OpenApiParameter('environment', str),
    OpenApiParameter('level', str),
    OpenApiParameter('hostname', str),
    OpenApiParameter('container', str),
    OpenApiParameter('source_id', str),
    OpenApiParameter('field_filters', str, description='JSON list of {field, op, value}'),
    OpenApiParameter('size', int),
    OpenApiParameter('cursor', str),
    OpenApiParameter('order', str),
]


def _params(request):
    """Accept both GET query params and POST JSON bodies."""
    return request.query_params if request.method == 'GET' else request.data


class LogSearchView(APIView):
    """Search log events through a provider adapter.

    The response states which engine executed the query (`provider`) and links
    to the equivalent search in the product's native UI (`external_url`).
    """

    throttle_scope = 'search'

    @extend_schema(parameters=QUERY_PARAMS)
    def get(self, request):
        return self._search(request)

    def post(self, request):
        return self._search(request)

    def _search(self, request):
        params = _params(request)
        provider = get_provider(params.get('provider'))
        query = LogQuery.from_params(params, max_size=settings.LOGHUB['SEARCH_MAX_RESULTS'])
        org = request.user.organization
        result = provider.search(org, query)
        return Response(
            {
                'provider': result.provider,
                'executed_by': f'LogHub API → {provider.label}',
                'external_url': provider.external_link(query),
                'total': result.total,
                'total_relation': result.total_relation,
                'took_ms': result.took_ms,
                'timed_out': result.timed_out,
                'cursor': result.cursor,
                'query': query.describe(),
                'hits': [mask_hit(h, request.user, org) for h in result.hits],
            }
        )


class LogAggregateView(APIView):
    """Aggregations (histograms, top-N terms, metrics) over the caller's logs.

    Body: {"q", "range", ...filters, "aggs": {"name": {"type": "histogram"|"terms"|"metric", ...}}}
    """

    throttle_scope = 'search'

    def post(self, request):
        specs = request.data.get('aggs')
        if not isinstance(specs, dict) or not 0 < len(specs) <= 12:
            raise InvalidQuery('Provide between 1 and 12 named aggregations in "aggs".')
        query = LogQuery.from_params(request.data)
        return Response(ElasticsearchProvider().aggregate(request.user.organization, query, specs))


class LogEventView(APIView):
    """One event by id, plus surrounding context from the same service/host."""

    def get(self, request, event_id):
        org = request.user.organization
        provider = ElasticsearchProvider()
        event = provider.get_event(org, event_id)
        if event is None:
            raise NotFound('Event not found.')
        context = []
        if request.query_params.get('context') == 'true' and event['timestamp']:
            ts = timezone.datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00'))
            window = timezone.timedelta(minutes=2)
            filters = {k: event[k] for k in ('service', 'hostname') if event.get(k)}
            ctx_query = LogQuery.from_params(
                {**filters, 'start': ts - window, 'end': ts + window, 'size': 40, 'order': 'asc'}
            )
            context = [mask_hit(h, request.user, org) for h in provider.search(org, ctx_query).hits]
        related = []
        if event.get('trace_id'):
            trace_query = LogQuery.from_params(
                {
                    'range': '7d',
                    'size': 50,
                    'order': 'asc',
                    'field_filters': [{'field': 'trace_id', 'op': 'eq', 'value': event['trace_id']}],
                }
            )
            related = [mask_hit(h, request.user, org) for h in provider.search(org, trace_query).hits]
        return Response({'event': mask_hit(event, request.user, org), 'context': context, 'trace': related})


class FieldValuesView(APIView):
    """Top values of a field, for filter dropdowns."""

    def get(self, request, field):
        query = LogQuery.from_params({**request.query_params.dict(), 'range': request.query_params.get('range', '24h')})
        result = ElasticsearchProvider().aggregate(
            request.user.organization, query, {'values': {'type': 'terms', 'field': field, 'size': 50}}
        )
        return Response({'field': field, 'values': result['values']['buckets']})


class LogExportView(APIView):
    """CSV or JSON export (analyst role or higher). Capped and audited."""

    permission_classes = [CanExportData]
    throttle_scope = 'export'
    COLUMNS = ['timestamp', 'level', 'service', 'environment', 'hostname', 'container', 'message', 'id']

    def get(self, request):
        fmt = request.query_params.get('format', 'csv')
        if fmt not in ('csv', 'json'):
            raise InvalidQuery('format must be csv or json.')
        org = request.user.organization
        limit = settings.LOGHUB['EXPORT_MAX_ROWS']
        provider = ElasticsearchProvider()
        base = LogQuery.from_params(request.query_params, max_size=500)
        base.size = 500
        record_audit(
            request,
            'export',
            target_type='logs',
            target_repr=f'{fmt} export',
            changes={**base.describe(), 'limit': limit},
        )

        def rows():
            query, sent = base, 0
            while sent < limit:
                result = provider.search(org, query)
                for hit in result.hits:
                    yield mask_hit(hit, request.user, org)
                    sent += 1
                    if sent >= limit:
                        return
                if not result.cursor:
                    return
                query.cursor = decode_cursor(result.cursor)

        def csv_stream():
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(self.COLUMNS)
            yield buf.getvalue()
            for hit in rows():
                buf.seek(0)
                buf.truncate()
                # Neutralize spreadsheet formula injection from untrusted log content.
                writer.writerow(
                    [
                        ("'" + v) if isinstance(v, str) and v[:1] in ('=', '+', '-', '@') else v
                        for v in (hit.get(c) for c in self.COLUMNS)
                    ]
                )
                yield buf.getvalue()

        def json_stream():
            yield '['
            for i, hit in enumerate(rows()):
                yield (',' if i else '') + json.dumps(hit['source'], default=str)
            yield ']'

        stamp = timezone.now().strftime('%Y%m%d-%H%M%S')
        response = StreamingHttpResponse(
            csv_stream() if fmt == 'csv' else json_stream(),
            content_type='text/csv' if fmt == 'csv' else 'application/json',
        )
        response['Content-Disposition'] = f'attachment; filename="loghub-logs-{stamp}.{fmt}"'
        return response


class EventStreamRenderer(BaseRenderer):
    """Lets DRF content negotiation accept `Accept: text/event-stream` (errors render as JSON text)."""

    media_type = 'text/event-stream'
    format = 'sse'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        return json.dumps(data, default=str).encode()


class LiveTailView(APIView):
    """Server-Sent Events stream of newly ingested events.

    One Elasticsearch query every LIVE_STREAM_POLL_SECONDS per connection, on the
    `ingested_at` cursor, lagging a few seconds behind real time so late index
    refreshes are not skipped. Streams close after LIVE_STREAM_MAX_SECONDS and
    the client reconnects with its last cursor; per-user connections are capped.
    """

    SETTLE_MS = 3000
    renderer_classes = [JSONRenderer, EventStreamRenderer]

    def get(self, request):
        cfg = settings.LOGHUB
        user, org = request.user, request.user.organization
        query = LogQuery.from_params(request.query_params, max_size=200, default_range='1d')
        query.size = 200
        slot_key = f'live-tail:{user.pk}'
        cache.add(slot_key, 0, timeout=cfg['LIVE_STREAM_MAX_SECONDS'] + 60)
        if cache.incr(slot_key) > cfg['LIVE_STREAM_MAX_PER_USER']:
            cache.decr(slot_key)
            return Response(
                {'error': {'code': 'too_many_streams', 'message': 'Too many open live streams.', 'details': None}},
                status=429,
            )

        provider = ElasticsearchProvider()
        cursor_param = request.query_params.get('after')
        now_ms = int(time.time() * 1000)
        after = None
        if cursor_param:
            try:
                ts, fp = cursor_param.split(':', 1)
                after = [max(int(ts), now_ms - 600_000), fp]
            except ValueError:
                after = None
        after = after or [now_ms - 10_000, '']

        def stream():
            nonlocal after
            deadline = time.monotonic() + cfg['LIVE_STREAM_MAX_SECONDS']
            try:
                yield 'retry: 3000\n\n'
                while time.monotonic() < deadline:
                    query.start = timezone.now() - timezone.timedelta(days=1)
                    query.end = timezone.now() + timezone.timedelta(minutes=5)
                    settle = int(time.time() * 1000) - self.SETTLE_MS
                    try:
                        hits, new_after = provider.tail(org, query, after)
                    except (ProviderUnavailable, InvalidQuery) as exc:
                        yield f'event: error\ndata: {json.dumps({"message": str(exc.detail)})}\n\n'
                        time.sleep(cfg['LIVE_STREAM_POLL_SECONDS'] * 3)
                        continue
                    # Hold back events newer than the settle window; they'll come next poll.
                    ready = []
                    for hit in hits:
                        ingested = hit['source'].get('ingested_at')
                        ts = (
                            int(timezone.datetime.fromisoformat(ingested.replace('Z', '+00:00')).timestamp() * 1000)
                            if ingested
                            else 0
                        )
                        if ts > settle:
                            break
                        ready.append((hit, [ts, hit['source'].get('fingerprint', '')]))
                    if ready:
                        after = ready[-1][1]
                        payload = [mask_hit(h, user, org) for h, _ in ready]
                        yield (
                            f'id: {after[0]}:{after[1]}\nevent: logs\n' f'data: {json.dumps(payload, default=str)}\n\n'
                        )
                    else:
                        yield ': keepalive\n\n'
                    if len(ready) < len(hits) or len(hits) < query.size:
                        time.sleep(cfg['LIVE_STREAM_POLL_SECONDS'])
                yield 'event: end\ndata: {}\n\n'
            finally:
                cache.decr(slot_key)

        response = StreamingHttpResponse(stream(), content_type='text/event-stream')
        response['Cache-Control'] = 'no-cache'
        response['X-Accel-Buffering'] = 'no'  # tell nginx not to buffer the stream
        return response


class SavedSearchViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = SavedSearch.objects.select_related('created_by')
    serializer_class = SavedSearchSerializer
    permission_classes = [RoleRequired]
    write_role = ROLE_ANALYST
    search_fields = ['name', 'description', 'query']

    def get_queryset(self):
        return super().get_queryset().filter(Q(is_shared=True) | Q(created_by=self.request.user))

    def _check_owner(self, instance):
        if instance.created_by_id != self.request.user.pk and not has_role(self.request.user, ROLE_EDITOR):
            raise PermissionDenied('Only the owner or an editor can change this saved search.')

    def perform_update(self, serializer):
        self._check_owner(serializer.instance)
        super().perform_update(serializer)

    def perform_destroy(self, instance):
        self._check_owner(instance)
        super().perform_destroy(instance)
