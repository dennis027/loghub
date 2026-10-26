from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.services import record_audit
from core.permissions import ROLE_ADMIN, RoleRequired
from core.tenancy import OrganizationScopedMixin

from .instructions import instructions_for
from .models import Collector, LogSource
from .serializers import CollectorSerializer, LogSourceSerializer


class LogSourceViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = LogSource.objects.select_related('owner')
    serializer_class = LogSourceSerializer
    permission_classes = [RoleRequired]
    search_fields = ['name', 'hostname', 'description']
    ordering_fields = ['name', 'last_seen', 'status', 'events_24h']
    audit_target_type = 'log_source'

    def get_queryset(self):
        qs = super().get_queryset()
        for param in ('source_type', 'environment', 'status'):
            if value := self.request.query_params.get(param):
                qs = qs.filter(**{param: value})
        return qs

    def perform_create(self, serializer):
        serializer.validated_data.setdefault('owner', self.request.user)
        super().perform_create(serializer)

    @action(detail=True, methods=['get'])
    def instructions(self, request, pk=None):
        source = self.get_object()
        return Response({'source': source.source_key, 'steps': instructions_for(source)})

    @action(detail=True, methods=['post'], url_path='rotate-token')
    def rotate_token(self, request, pk=None):
        """Issue a new ingest token. The plaintext is returned exactly once and never stored."""
        source = self.get_object()
        token = source.issue_token()
        record_audit(request, 'rotate_token', target_type='log_source', target_id=source.pk, target_repr=source.name)
        return Response(
            {
                'token': token,
                'token_prefix': source.token_prefix,
                'warning': 'Store this token in your secret manager now; it cannot be shown again.',
            }
        )

    @action(detail=True, methods=['post'], url_path='revoke-token')
    def revoke_token(self, request, pk=None):
        source = self.get_object()
        source.token_hash = ''
        source.token_prefix = ''
        source.save(update_fields=['token_hash', 'token_prefix', 'updated_at'])
        record_audit(request, 'revoke_token', target_type='log_source', target_id=source.pk, target_repr=source.name)
        return Response(status=204)


class CollectorViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Collector.objects.all()
    serializer_class = CollectorSerializer
    permission_classes = [RoleRequired]
    write_role = ROLE_ADMIN

    def perform_destroy(self, instance):
        if instance.managed:
            from rest_framework.exceptions import ValidationError

            raise ValidationError('Bundled collectors cannot be deleted.')
        super().perform_destroy(instance)
