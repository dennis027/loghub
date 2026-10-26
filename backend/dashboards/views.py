from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from core.permissions import RoleRequired
from core.tenancy import OrganizationScopedMixin

from .models import Dashboard

WIDGET_TYPES = {'stat', 'timeseries', 'bar', 'pie', 'table', 'logs'}
WIDGET_SOURCES = {'logs', 'prometheus'}


class DashboardSerializer(serializers.ModelSerializer):
    created_by = serializers.CharField(source='created_by.username', read_only=True, default=None)

    class Meta:
        model = Dashboard
        fields = [
            'id',
            'name',
            'description',
            'folder',
            'category',
            'widgets',
            'time_range',
            'grafana_uid',
            'is_template',
            'created_by',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['id', 'is_template', 'created_by', 'created_at', 'updated_at']

    def validate_widgets(self, widgets):
        if not isinstance(widgets, list) or len(widgets) > 30:
            raise serializers.ValidationError('A dashboard holds at most 30 widgets.')
        for i, widget in enumerate(widgets):
            if not isinstance(widget, dict) or widget.get('type') not in WIDGET_TYPES:
                raise serializers.ValidationError(f'Widget {i}: type must be one of {sorted(WIDGET_TYPES)}.')
            if widget.get('source', 'logs') not in WIDGET_SOURCES:
                raise serializers.ValidationError(f'Widget {i}: unknown source.')
            if not str(widget.get('title', '')).strip() or len(str(widget['title'])) > 200:
                raise serializers.ValidationError(f'Widget {i}: a title (≤200 chars) is required.')
            if widget.get('source') == 'prometheus' and not widget.get('promql'):
                raise serializers.ValidationError(f'Widget {i}: promql is required for Prometheus widgets.')
        return widgets


class DashboardViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = Dashboard.objects.select_related('created_by')
    serializer_class = DashboardSerializer
    permission_classes = [RoleRequired]
    search_fields = ['name', 'description', 'folder']
    ordering_fields = ['name', 'folder', 'updated_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if folder := self.request.query_params.get('folder'):
            qs = qs.filter(folder=folder)
        return qs

    @action(detail=True, methods=['post'])
    def duplicate(self, request, pk=None):
        original = self.get_object()
        name = request.data.get('name') or f'{original.name} (copy)'
        copy = Dashboard.objects.create(
            organization=original.organization,
            name=str(name)[:255],
            description=original.description,
            folder=request.data.get('folder') or 'General',
            category=original.category,
            widgets=original.widgets,
            time_range=original.time_range,
            grafana_uid=original.grafana_uid,
            created_by=request.user,
        )
        self._audit('duplicate', copy, {'source_dashboard': original.pk})
        return Response(self.get_serializer(copy).data, status=201)

    @action(detail=False, methods=['get'])
    def folders(self, request):
        folders = self.get_queryset().values_list('folder', flat=True).distinct()
        return Response(sorted(set(folders)))
