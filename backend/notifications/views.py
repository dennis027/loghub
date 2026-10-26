from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audit.services import record_audit
from core.permissions import ROLE_ADMIN, RoleRequired
from core.tenancy import OrganizationScopedMixin

from .models import NotificationChannel, NotificationDelivery
from .serializers import NotificationChannelSerializer, NotificationDeliverySerializer
from .tasks import queue_notification


class NotificationChannelViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = NotificationChannel.objects.all()
    serializer_class = NotificationChannelSerializer
    permission_classes = [RoleRequired]
    write_role = ROLE_ADMIN

    @action(detail=True, methods=['post'])
    def test(self, request, pk=None):
        channel = self.get_object()
        delivery = queue_notification(
            channel,
            '[LogHub] Test notification',
            f'This is a test notification from LogHub sent by {request.user.username} '
            f'at {timezone.now():%Y-%m-%d %H:%M:%S} UTC.',
            {'kind': 'test', 'organization': request.user.organization.slug},
            kind='test',
        )
        record_audit(
            request,
            'test_notification',
            target_type='notification_channel',
            target_id=channel.pk,
            target_repr=channel.name,
        )
        delivery.refresh_from_db()
        return Response(NotificationDeliverySerializer(delivery).data)


class NotificationDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationDeliverySerializer

    def get_queryset(self):
        qs = NotificationDelivery.objects.select_related('channel').filter(
            channel__organization=self.request.user.organization
        )
        if event := self.request.query_params.get('alert_event'):
            qs = qs.filter(alert_event_id=event)
        return qs
