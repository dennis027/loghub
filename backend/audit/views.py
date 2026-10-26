from rest_framework import viewsets

from core.permissions import ROLE_ADMIN, RoleRequired

from .models import AuditEvent
from .serializers import AuditEventSerializer


class AuditEventViewSet(viewsets.ReadOnlyModelViewSet):
    """Administrative audit trail for the caller's organization (admins only)."""

    serializer_class = AuditEventSerializer
    permission_classes = [RoleRequired]
    read_role = ROLE_ADMIN
    search_fields = ['actor_username', 'action', 'target_type', 'target_repr']
    ordering_fields = ['created_at', 'action']

    def get_queryset(self):
        qs = AuditEvent.objects.filter(organization=self.request.user.organization)
        for param in ('action', 'target_type', 'actor_username'):
            if value := self.request.query_params.get(param):
                qs = qs.filter(**{param: value})
        return qs
