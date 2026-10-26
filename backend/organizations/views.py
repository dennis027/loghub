from rest_framework import generics, viewsets

from audit.services import record_audit
from core.permissions import ROLE_ADMIN, RoleRequired
from core.tenancy import OrganizationScopedMixin

from .models import Environment, Team
from .serializers import EnvironmentSerializer, OrganizationSerializer, TeamSerializer


class CurrentOrganizationView(generics.RetrieveUpdateAPIView):
    """The caller's organization. Users only ever see their own tenant."""

    serializer_class = OrganizationSerializer
    permission_classes = [RoleRequired]
    write_role = ROLE_ADMIN

    def get_object(self):
        return self.request.user.organization

    def perform_update(self, serializer):
        org = serializer.save()
        record_audit(
            self.request,
            'update',
            target_type='organization',
            target_id=org.pk,
            target_repr=org.name,
            changes=serializer.validated_data,
        )


class TeamViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Team.objects.all()
    serializer_class = TeamSerializer
    permission_classes = [RoleRequired]
    write_role = ROLE_ADMIN
    search_fields = ['name']


class EnvironmentViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Environment.objects.all()
    serializer_class = EnvironmentSerializer
    permission_classes = [RoleRequired]
    write_role = ROLE_ADMIN
