from rest_framework import serializers

from .models import Integration


class IntegrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Integration
        fields = [
            'id',
            'provider',
            'name',
            'description',
            'enabled',
            'public_url',
            'config',
            'status',
            'status_message',
            'version',
            'latency_ms',
            'details',
            'last_checked',
            'updated_at',
        ]
        read_only_fields = [
            'id',
            'provider',
            'name',
            'description',
            'status',
            'status_message',
            'version',
            'latency_ms',
            'details',
            'last_checked',
            'updated_at',
        ]
