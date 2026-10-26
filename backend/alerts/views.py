from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from audit.services import record_audit
from core.permissions import ROLE_ANALYST, RoleRequired
from core.tenancy import OrganizationScopedMixin
from search.providers.elasticsearch import ElasticsearchProvider

from .engine import evaluate, process_rule
from .models import AlertEvent, AlertRule
from .serializers import AlertEventSerializer, AlertRuleSerializer
from .templates import RULE_TEMPLATES


class AlertRuleViewSet(OrganizationScopedMixin, viewsets.ModelViewSet):
    queryset = AlertRule.objects.select_related('source').prefetch_related('channels')
    serializer_class = AlertRuleSerializer
    permission_classes = [RoleRequired]
    search_fields = ['name', 'description', 'query']
    ordering_fields = ['name', 'severity', 'last_evaluated_at']
    audit_target_type = 'alert_rule'

    def get_queryset(self):
        qs = super().get_queryset()
        if category := self.request.query_params.get('category'):
            qs = qs.filter(category=category)
        return qs

    @action(detail=False, methods=['get'])
    def templates(self, request):
        return Response(RULE_TEMPLATES)

    @action(detail=True, methods=['post'])
    def preview(self, request, pk=None):
        """Dry-run the rule now without changing state or notifying."""
        rule = self.get_object()
        result = evaluate(rule, ElasticsearchProvider())
        return Response(
            {'firing': result.firing, 'value': result.value, 'summary': result.summary, 'context': result.context}
        )

    @action(detail=True, methods=['post'])
    def evaluate(self, request, pk=None):
        """Evaluate immediately and apply state transitions (may notify)."""
        rule = self.get_object()
        event = process_rule(rule)
        rule.refresh_from_db()
        record_audit(request, 'evaluate', target_type='alert_rule', target_id=rule.pk, target_repr=rule.name)
        return Response(
            {'rule': self.get_serializer(rule).data, 'event': AlertEventSerializer(event).data if event else None}
        )


class AlertEventViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = AlertEventSerializer
    permission_classes = [RoleRequired]
    write_role = ROLE_ANALYST
    search_fields = ['title', 'message', 'rule_name']
    ordering_fields = ['started_at', 'severity', 'status']

    def get_queryset(self):
        qs = AlertEvent.objects.filter(organization=self.request.user.organization).select_related('acknowledged_by')
        for param in ('status', 'severity', 'category', 'rule'):
            if value := self.request.query_params.get(param):
                qs = qs.filter(**{param: value})
        return qs

    @action(detail=True, methods=['post'])
    def acknowledge(self, request, pk=None):
        event = self.get_object()
        if event.status != 'firing':
            raise ValidationError('Only firing alerts can be acknowledged.')
        event.status = 'acknowledged'
        event.acknowledged_by, event.acknowledged_at = request.user, timezone.now()
        event.note = str(request.data.get('note', ''))[:2000]
        event.save()
        record_audit(request, 'acknowledge', target_type='alert_event', target_id=event.pk, target_repr=event.title)
        return Response(self.get_serializer(event).data)

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        event = self.get_object()
        if event.status == 'resolved':
            raise ValidationError('Already resolved.')
        event.status, event.resolved_at = 'resolved', timezone.now()
        event.note = str(request.data.get('note', event.note))[:2000]
        event.save()
        record_audit(request, 'resolve', target_type='alert_event', target_id=event.pk, target_repr=event.title)
        return Response(self.get_serializer(event).data)
