from django.contrib import admin

from .models import AlertEvent, AlertRule


@admin.register(AlertRule)
class AlertRuleAdmin(admin.ModelAdmin):
    list_display = [
        'name',
        'organization',
        'category',
        'rule_type',
        'severity',
        'enabled',
        'last_state',
        'last_evaluated_at',
    ]
    list_filter = ['organization', 'category', 'rule_type', 'severity', 'enabled']
    search_fields = ['name', 'query']
    readonly_fields = ['last_evaluated_at', 'last_value', 'last_state', 'last_error']


@admin.register(AlertEvent)
class AlertEventAdmin(admin.ModelAdmin):
    list_display = ['title', 'organization', 'severity', 'status', 'occurrences', 'started_at', 'resolved_at']
    list_filter = ['organization', 'status', 'severity', 'category']
    search_fields = ['title', 'message']
