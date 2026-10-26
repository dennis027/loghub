import requests
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from audit.services import record_audit
from core.exceptions import ProviderUnavailable
from core.permissions import IsPlatformAdmin
from search.providers.graylog import GraylogProvider

from .models import Integration
from .providers import fluentbit_stats, logstash_stats
from .serializers import IntegrationSerializer
from .services import refresh_integration


class IntegrationViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    """Integrated products. Everyone can read status; only platform admins can toggle them."""

    queryset = Integration.objects.all()
    serializer_class = IntegrationSerializer
    permission_classes = [IsPlatformAdmin]
    pagination_class = None
    lookup_field = 'provider'

    def perform_update(self, serializer):
        integration = serializer.save()
        record_audit(
            self.request,
            'update',
            target_type='integration',
            target_id=integration.provider,
            target_repr=integration.name,
            changes=serializer.validated_data,
        )

    @action(detail=True, methods=['post'])
    def check(self, request, provider=None):
        return Response(self.get_serializer(refresh_integration(self.get_object())).data)

    @action(detail=False, methods=['get'], url_path='graylog/overview')
    def graylog_overview(self, request):
        provider = GraylogProvider()
        try:
            inputs = provider.inputs()
            streams = provider.streams()
        except ProviderUnavailable as exc:
            return Response({'available': False, 'message': str(exc.detail), 'inputs': [], 'streams': []})
        return Response(
            {
                'available': True,
                'inputs': [
                    {
                        'id': i['id'],
                        'title': i['title'],
                        'type': i['type'].rsplit('.', 1)[-1],
                        'port': i.get('attributes', {}).get('port'),
                        'global': i.get('global'),
                    }
                    for i in inputs
                ],
                'streams': [
                    {
                        'id': s['id'],
                        'title': s['title'],
                        'disabled': s.get('disabled'),
                        'description': s.get('description'),
                    }
                    for s in streams
                ],
            }
        )


class PipelineStatusView(APIView):
    """Live ingestion pipeline statistics from Fluent Bit and Logstash."""

    def get(self, request):
        out = {}
        for key, fn in (('fluent_bit', fluentbit_stats), ('logstash', logstash_stats)):
            try:
                out[key] = {'available': True, **fn()}
            except (requests.RequestException, ValueError) as exc:
                out[key] = {'available': False, 'message': exc.__class__.__name__}
        out['routes'] = [
            {
                'route': 'elk',
                'path': ['Fluent Bit', 'Logstash', 'Elasticsearch'],
                'consumers': ['LogHub search', 'Kibana', 'Grafana', 'Alerts'],
            },
            {
                'route': 'graylog',
                'path': ['Fluent Bit', 'Graylog GELF input', 'OpenSearch (Graylog)'],
                'consumers': ['Graylog UI', 'LogHub search (provider=graylog)'],
            },
            {
                'route': 'both',
                'path': ['Fluent Bit', 'copy to both routes'],
                'consumers': ['all of the above'],
                'note': 'Doubles storage; opt-in per source.',
            },
        ]
        return Response(out)
