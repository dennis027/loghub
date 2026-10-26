"""Token-authenticated HTTP ingestion.

Clients send events with `X-LogHub-Token`. The API stamps tenant and source
fields from the token (payload values are overwritten) and forwards the batch
to the internal Fluent Bit HTTP input, so routing and masking stay identical to
every other path. Delivery: the request succeeds once Fluent Bit has accepted
the batch into its filesystem buffer (at-least-once from there on).
"""

import logging

import requests
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework import authentication, exceptions, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from .models import LogSource, hash_token

logger = logging.getLogger(__name__)
_session = requests.Session()

MAX_EVENTS = 1000
RESERVED = ('organization', 'source_id', 'source_type', 'collector')


class IngestTokenAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        token = request.headers.get('X-LogHub-Token')
        if not token:
            raise exceptions.NotAuthenticated('X-LogHub-Token header is required.')
        source = (
            LogSource.objects.select_related('organization')
            .filter(token_hash=hash_token(token), enabled=True, organization__is_active=True)
            .first()
        )
        if source is None:
            raise exceptions.AuthenticationFailed('Invalid or disabled ingest token.')
        request.log_source = source
        return (None, source)

    def authenticate_header(self, request):
        return 'X-LogHub-Token'


class SourceRateThrottle(SimpleRateThrottle):
    scope = 'ingest'

    def get_cache_key(self, request, view):
        source = getattr(request, 'log_source', None)
        return f'throttle_ingest_{source.pk}' if source else None


class IngestView(APIView):
    authentication_classes = [IngestTokenAuthentication]
    permission_classes = [AllowAny]
    throttle_classes = [SourceRateThrottle]

    def post(self, request):
        source = request.log_source
        payload = request.data
        events = payload if isinstance(payload, list) else [payload]
        if not events or len(events) > MAX_EVENTS:
            raise exceptions.ValidationError(f'Send between 1 and {MAX_EVENTS} events per request.')

        now = timezone.now().isoformat()
        batch = []
        for i, event in enumerate(events):
            if not isinstance(event, dict):
                raise exceptions.ValidationError({str(i): 'Each event must be a JSON object.'})
            msg = event.get('message', event.get('msg'))
            if not isinstance(msg, str):
                raise exceptions.ValidationError({str(i): '"message" (string) is required.'})
            clean = {k: v for k, v in event.items() if k not in RESERVED and isinstance(k, str) and len(k) <= 100}
            clean.setdefault('timestamp', now)
            clean.setdefault('service', source.name)
            clean.setdefault('environment', source.environment)
            if source.hostname:
                clean.setdefault('hostname', source.hostname)
            clean.update(
                {
                    'organization': source.organization.slug,
                    'source_id': source.source_key,
                    'source_type': source.source_type,
                    'collector': 'loghub-api',
                    'log_route': source.log_route,
                }
            )
            batch.append(clean)

        url = settings.LOGHUB['FLUENT_BIT_INGEST_URL']
        try:
            resp = _session.post(url, json=batch, timeout=10)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error('ingest forward failed: %s', exc, extra={'source_id': source.source_key})
            return Response(
                {
                    'error': {
                        'code': 'collector_unavailable',
                        'message': 'The collector is unavailable; retry with backoff.',
                        'details': None,
                    }
                },
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                headers={'Retry-After': '10'},
            )

        # Cheap liveness marker; the periodic task computes authoritative status from the index.
        if cache.add(f'ingest-seen:{source.pk}', 1, timeout=30):
            LogSource.objects.filter(pk=source.pk).update(last_seen=timezone.now(), status='active')
        return Response(
            {'accepted': len(batch), 'source': source.source_key, 'route': source.log_route},
            status=status.HTTP_202_ACCEPTED,
        )
