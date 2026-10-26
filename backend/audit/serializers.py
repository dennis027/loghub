from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            'id',
            'actor_username',
            'action',
            'target_type',
            'target_id',
            'target_repr',
            'changes',
            'ip_address',
            'user_agent',
            'request_id',
            'created_at',
        ]
        read_only_fields = fields
