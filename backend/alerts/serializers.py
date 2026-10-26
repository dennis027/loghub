from rest_framework import serializers

from core.serializers import UniqueNameInOrganizationMixin
from notifications.models import NotificationChannel
from search.query import QUERY_MODES, STANDARD_FILTERS, FieldFilter

from .models import AlertEvent, AlertRule


class AlertRuleSerializer(UniqueNameInOrganizationMixin, serializers.ModelSerializer):
    channels = serializers.PrimaryKeyRelatedField(many=True, queryset=NotificationChannel.objects.all(), required=False)
    open_events = serializers.SerializerMethodField()

    class Meta:
        model = AlertRule
        fields = [
            'id',
            'name',
            'description',
            'category',
            'rule_type',
            'severity',
            'enabled',
            'query',
            'query_mode',
            'filters',
            'field_filters',
            'source',
            'window_minutes',
            'comparator',
            'threshold',
            'spike_factor',
            'min_count',
            'evaluation_interval_seconds',
            'cooldown_minutes',
            'channels',
            'last_evaluated_at',
            'last_value',
            'last_state',
            'last_error',
            'open_events',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'last_evaluated_at',
            'last_value',
            'last_state',
            'last_error',
            'created_at',
            'updated_at',
        ]

    def get_open_events(self, obj):
        return obj.events.filter(status__in=['firing', 'acknowledged']).count()

    def validate(self, attrs):
        org = self.context['request'].user.organization
        for channel in attrs.get('channels', []):
            if channel.organization_id != org.id:
                raise serializers.ValidationError({'channels': 'Channels must belong to your organization.'})
        source = attrs.get('source')
        if source is not None and source.organization_id != org.id:
            raise serializers.ValidationError({'source': 'Source must belong to your organization.'})
        if attrs.get('query_mode', 'simple') not in QUERY_MODES:
            raise serializers.ValidationError({'query_mode': 'Use simple or lucene.'})
        filters = attrs.get('filters', {})
        if not isinstance(filters, dict) or any(
            k not in STANDARD_FILTERS or not isinstance(v, list) for k, v in filters.items()
        ):
            raise serializers.ValidationError({'filters': 'Map standard filter names to lists of values.'})
        ffs = attrs.get('field_filters', [])
        if not isinstance(ffs, list) or len(ffs) > 20:
            raise serializers.ValidationError({'field_filters': 'At most 20 field filters.'})
        for ff in ffs:
            FieldFilter.from_dict(ff)
        if attrs.get('evaluation_interval_seconds', 60) < 30:
            raise serializers.ValidationError({'evaluation_interval_seconds': 'Minimum is 30 seconds.'})
        if not 1 <= attrs.get('window_minutes', 5) <= 1440:
            raise serializers.ValidationError({'window_minutes': 'Between 1 and 1440 minutes.'})
        if attrs.get('spike_factor', 3) <= 1:
            raise serializers.ValidationError({'spike_factor': 'Must be greater than 1.'})
        return attrs


class AlertEventSerializer(serializers.ModelSerializer):
    acknowledged_by = serializers.CharField(source='acknowledged_by.username', read_only=True, default=None)
    deliveries = serializers.SerializerMethodField()

    class Meta:
        model = AlertEvent
        fields = [
            'id',
            'rule',
            'rule_name',
            'status',
            'severity',
            'category',
            'title',
            'message',
            'value',
            'threshold',
            'occurrences',
            'samples',
            'context',
            'started_at',
            'last_seen_at',
            'resolved_at',
            'acknowledged_by',
            'acknowledged_at',
            'note',
            'deliveries',
        ]
        read_only_fields = fields

    def get_deliveries(self, obj):
        return [
            {
                'channel': d.channel.name,
                'kind': d.kind,
                'status': d.status,
                'attempts': d.attempts,
                'error': d.error,
                'sent_at': d.sent_at,
            }
            for d in obj.deliveries.select_related('channel')[:20]
        ]
