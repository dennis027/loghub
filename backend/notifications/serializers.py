from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.serializers import UniqueNameInOrganizationMixin

from .backends import BACKENDS
from .models import NotificationChannel, NotificationDelivery


class NotificationChannelSerializer(UniqueNameInOrganizationMixin, serializers.ModelSerializer):
    secret = serializers.CharField(write_only=True, required=False, allow_blank=True, max_length=255)
    has_secret = serializers.SerializerMethodField()

    class Meta:
        model = NotificationChannel
        fields = [
            'id',
            'name',
            'channel_type',
            'config',
            'secret',
            'has_secret',
            'enabled',
            'send_resolved',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def get_has_secret(self, obj):
        return bool(obj.secret)

    def validate(self, attrs):
        channel_type = attrs.get('channel_type', getattr(self.instance, 'channel_type', None))
        config = attrs.get('config', getattr(self.instance, 'config', {}))
        try:
            attrs['config'] = BACKENDS[channel_type].validate_config(config or {})
        except (ValueError, DjangoValidationError) as exc:
            message = '; '.join(exc.messages) if hasattr(exc, 'messages') else str(exc)
            raise serializers.ValidationError({'config': message}) from exc
        return attrs


class NotificationDeliverySerializer(serializers.ModelSerializer):
    channel_name = serializers.CharField(source='channel.name', read_only=True)

    class Meta:
        model = NotificationDelivery
        fields = [
            'id',
            'channel',
            'channel_name',
            'alert_event',
            'kind',
            'status',
            'attempts',
            'error',
            'subject',
            'created_at',
            'sent_at',
        ]
        read_only_fields = fields
