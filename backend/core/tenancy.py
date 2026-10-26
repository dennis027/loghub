import re

from django.conf import settings

from audit.services import record_audit

_UNSAFE = re.compile(r'[^a-z0-9_]')


def org_index_key(slug):
    """Mirror of the Logstash rule that turns an organization into an index suffix."""
    key = _UNSAFE.sub('_', (slug or '').lower())
    return key or 'default'


def org_index(organization):
    return settings.LOGHUB['INDEX_PREFIX'] + org_index_key(organization.slug)


class OrganizationScopedMixin:
    """Restricts a ModelViewSet to the caller's organization and audits writes."""

    audit_target_type = None

    def get_queryset(self):
        return super().get_queryset().filter(organization=self.request.user.organization)

    def perform_create(self, serializer):
        extra = {'organization': self.request.user.organization}
        if 'created_by' in {f.name for f in serializer.Meta.model._meta.fields}:
            extra['created_by'] = self.request.user
        instance = serializer.save(**extra)
        self._audit('create', instance, serializer.validated_data)

    def perform_update(self, serializer):
        instance = serializer.save()
        self._audit('update', instance, serializer.validated_data)

    def perform_destroy(self, instance):
        self._audit('delete', instance, None)
        instance.delete()

    def _audit(self, action, instance, changes):
        record_audit(
            self.request,
            action,
            target_type=self.audit_target_type or instance._meta.model_name,
            target_id=instance.pk,
            target_repr=str(instance),
            changes=changes,
        )
