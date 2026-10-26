from rest_framework import serializers

from .models import SavedSearch
from .providers.registry import PROVIDERS
from .query import QUERY_MODES, STANDARD_FILTERS, FieldFilter, parse_relative


class SavedSearchSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)

    class Meta:
        model = SavedSearch
        fields = [
            'id',
            'name',
            'description',
            'provider',
            'query',
            'query_mode',
            'filters',
            'field_filters',
            'time_range',
            'is_shared',
            'created_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']

    def validate_provider(self, value):
        if value not in PROVIDERS:
            raise serializers.ValidationError(f'Choose one of: {", ".join(PROVIDERS)}')
        return value

    def validate_query_mode(self, value):
        if value not in QUERY_MODES:
            raise serializers.ValidationError('Use simple or lucene.')
        return value

    def validate_time_range(self, value):
        parse_relative(value)
        return value

    def validate_filters(self, value):
        if not isinstance(value, dict) or any(k not in STANDARD_FILTERS for k in value):
            raise serializers.ValidationError(f'Keys must be among: {", ".join(STANDARD_FILTERS)}')
        return value

    def validate_field_filters(self, value):
        if not isinstance(value, list) or len(value) > 20:
            raise serializers.ValidationError('At most 20 field filters.')
        for item in value:
            FieldFilter.from_dict(item)
        return value
