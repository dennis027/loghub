from rest_framework import serializers

from core.serializers import UniqueNameInOrganizationMixin

from .models import Environment, Organization, Team


class OrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = ['id', 'name', 'slug', 'description', 'is_active', 'masked_fields', 'created_at', 'updated_at']
        read_only_fields = ['id', 'slug', 'is_active', 'created_at', 'updated_at']

    def validate_masked_fields(self, value):
        from search.query import FIELD_NAME

        if (
            not isinstance(value, list)
            or len(value) > 100
            or not all(isinstance(v, str) and FIELD_NAME.match(v) for v in value)
        ):
            raise serializers.ValidationError('Provide a list of up to 100 field names.')
        return value


class TeamSerializer(UniqueNameInOrganizationMixin, serializers.ModelSerializer):
    member_count = serializers.IntegerField(source='members.count', read_only=True)

    class Meta:
        model = Team
        fields = ['id', 'name', 'description', 'member_count', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class EnvironmentSerializer(UniqueNameInOrganizationMixin, serializers.ModelSerializer):
    class Meta:
        model = Environment
        fields = ['id', 'name', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']
