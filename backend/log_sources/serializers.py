from rest_framework import serializers

from core.serializers import UniqueNameInOrganizationMixin

from .models import Collector, LogSource

# Only custom HTTP sources default to token attribution; everything else usually ships
# through Docker/Fluent Bit/syslog and is attributed by service name.
TOKEN_TYPES = {'custom'}


class LogSourceSerializer(UniqueNameInOrganizationMixin, serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.username', read_only=True, default=None)
    source_key = serializers.CharField(read_only=True)
    effective_match_value = serializers.CharField(read_only=True)
    has_token = serializers.SerializerMethodField()

    class Meta:
        model = LogSource
        fields = [
            'id',
            'name',
            'description',
            'source_type',
            'environment',
            'hostname',
            'endpoint',
            'owner',
            'owner_username',
            'team',
            'log_route',
            'match_field',
            'match_value',
            'effective_match_value',
            'source_key',
            'stale_after_minutes',
            'enabled',
            'status',
            'last_seen',
            'events_24h',
            'has_token',
            'token_prefix',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'status', 'last_seen', 'events_24h', 'token_prefix', 'created_at', 'updated_at']

    def get_has_token(self, obj):
        return bool(obj.token_hash)

    def validate(self, attrs):
        org = self.context['request'].user.organization
        for field in ('owner', 'team'):
            obj = attrs.get(field)
            if obj is not None and obj.organization_id != org.id:
                raise serializers.ValidationError({field: 'Must belong to your organization.'})
        if (
            self.instance is None
            and 'match_field' not in attrs
            and attrs.get('source_type', 'custom') not in TOKEN_TYPES
        ):
            attrs['match_field'] = 'service'
        if attrs.get('match_field', getattr(self.instance, 'match_field', 'source_id')) != 'source_id' and not (
            attrs.get('match_value') or attrs.get('name') or getattr(self.instance, 'name', '')
        ):
            raise serializers.ValidationError({'match_value': 'Required for this match field.'})
        if not 1 <= attrs.get('stale_after_minutes', 15) <= 10080:
            raise serializers.ValidationError({'stale_after_minutes': 'Between 1 minute and 7 days.'})
        return attrs


class CollectorSerializer(UniqueNameInOrganizationMixin, serializers.ModelSerializer):
    class Meta:
        model = Collector
        fields = [
            'id',
            'name',
            'collector_type',
            'endpoint',
            'managed',
            'status',
            'status_message',
            'last_heartbeat',
            'metrics',
            'created_at',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'managed',
            'status',
            'status_message',
            'last_heartbeat',
            'metrics',
            'created_at',
            'updated_at',
        ]


class IngestEventSerializer(serializers.Serializer):
    """Shape check only; arbitrary extra fields are allowed and stored."""

    message = serializers.CharField(max_length=32768, allow_blank=True)
    level = serializers.CharField(max_length=32, required=False)
    timestamp = serializers.CharField(max_length=64, required=False)
