from django.conf import settings
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.services import record_audit
from core.exceptions import ProviderUnavailable
from core.permissions import IsPlatformAdmin
from search.providers.elasticsearch import ElasticsearchProvider

from .models import RetentionPolicy
from .tasks import sync_policy


class RetentionPolicySerializer(serializers.ModelSerializer):
    updated_by = serializers.CharField(source='updated_by.username', read_only=True, default=None)

    class Meta:
        model = RetentionPolicy
        fields = [
            'id',
            'target',
            'name',
            'rollover_days',
            'delete_after_days',
            'is_active',
            'sync_status',
            'sync_message',
            'last_synced_at',
            'updated_by',
            'updated_at',
        ]
        read_only_fields = ['id', 'target', 'sync_status', 'sync_message', 'last_synced_at', 'updated_by', 'updated_at']

    def validate(self, attrs):
        rollover = attrs.get('rollover_days', getattr(self.instance, 'rollover_days', 1))
        delete = attrs.get('delete_after_days', getattr(self.instance, 'delete_after_days', 14))
        if not 1 <= rollover <= 30:
            raise serializers.ValidationError({'rollover_days': 'Between 1 and 30 days.'})
        if not 1 <= delete <= 3650:
            raise serializers.ValidationError({'delete_after_days': 'Between 1 and 3650 days.'})
        return attrs


class RetentionPolicyViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet
):
    queryset = RetentionPolicy.objects.all()
    serializer_class = RetentionPolicySerializer
    permission_classes = [IsPlatformAdmin]
    pagination_class = None

    def perform_update(self, serializer):
        policy = serializer.save(updated_by=self.request.user)
        record_audit(
            self.request,
            'update',
            target_type='retention_policy',
            target_id=policy.pk,
            target_repr=policy.name,
            changes=serializer.validated_data,
        )
        sync_policy(policy)

    @action(detail=True, methods=['get'])
    def live(self, request, pk=None):
        """The ILM policy as Elasticsearch currently has it, plus storage usage."""
        provider = ElasticsearchProvider()
        try:
            return Response(
                {
                    'ilm': provider.get_retention(settings.LOGHUB['ILM_POLICY']),
                    'storage': provider.storage(request.user.organization),
                }
            )
        except ProviderUnavailable as exc:
            return Response({'ilm': None, 'storage': None, 'error': str(exc.detail)})
