from rest_framework import serializers


class UniqueNameInOrganizationMixin:
    """Turn the (organization, name) unique constraint into a 400 instead of a database error."""

    def validate_name(self, value):
        model = self.Meta.model
        org = self.context['request'].user.organization
        qs = model.objects.filter(organization=org, name=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError(f'A {model._meta.verbose_name} with this name already exists.')
        return value
