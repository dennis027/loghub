from django.conf import settings
from django.db import models

SEVERITIES = [('info', 'Info'), ('warning', 'Warning'), ('error', 'Error'), ('critical', 'Critical')]


class AlertRule(models.Model):
    CATEGORIES = [('operational', 'Operational'), ('security', 'Security detection')]
    RULE_TYPES = [
        ('threshold', 'Event count crosses a threshold'),
        ('spike', 'Event count increases suddenly versus the previous window'),
        ('absence', 'No matching events (source/app stopped sending)'),
        ('storage', 'Elasticsearch disk usage percent'),
    ]
    COMPARATORS = [('gt', '>'), ('gte', '≥'), ('lt', '<'), ('lte', '≤')]

    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE, related_name='alert_rules')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=16, choices=CATEGORIES, default='operational')
    rule_type = models.CharField(max_length=16, choices=RULE_TYPES, default='threshold')
    severity = models.CharField(max_length=16, choices=SEVERITIES, default='warning')
    enabled = models.BooleanField(default=True)

    query = models.CharField(max_length=2000, blank=True)
    query_mode = models.CharField(max_length=16, default='simple')
    filters = models.JSONField(default=dict, blank=True)
    field_filters = models.JSONField(default=list, blank=True)
    source = models.ForeignKey(
        'log_sources.LogSource',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='alert_rules',
        help_text='Restrict to one source (absence rules).',
    )

    window_minutes = models.PositiveIntegerField(default=5)
    comparator = models.CharField(max_length=4, choices=COMPARATORS, default='gt')
    threshold = models.FloatField(default=0)
    spike_factor = models.FloatField(default=3.0)
    min_count = models.PositiveIntegerField(default=10)

    evaluation_interval_seconds = models.PositiveIntegerField(default=60)
    cooldown_minutes = models.PositiveIntegerField(default=15)
    channels = models.ManyToManyField('notifications.NotificationChannel', blank=True, related_name='rules')

    last_evaluated_at = models.DateTimeField(null=True, blank=True)
    last_value = models.FloatField(null=True, blank=True)
    last_state = models.CharField(max_length=16, default='unknown')  # ok | firing | cooldown | error | unknown
    last_error = models.CharField(max_length=500, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'alerts_rule'
        ordering = ['name']
        unique_together = ('organization', 'name')

    def __str__(self):
        return self.name


class AlertEvent(models.Model):
    STATUS = [('firing', 'Firing'), ('acknowledged', 'Acknowledged'), ('resolved', 'Resolved')]

    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE, related_name='alert_events'
    )
    rule = models.ForeignKey(AlertRule, on_delete=models.SET_NULL, null=True, related_name='events')
    rule_name = models.CharField(max_length=255)
    status = models.CharField(max_length=16, choices=STATUS, default='firing', db_index=True)
    severity = models.CharField(max_length=16, choices=SEVERITIES)
    category = models.CharField(max_length=16, default='operational')
    title = models.CharField(max_length=255)
    message = models.TextField(blank=True)
    value = models.FloatField(null=True)
    threshold = models.FloatField(null=True)
    occurrences = models.PositiveIntegerField(default=1)
    samples = models.JSONField(default=list, blank=True)
    context = models.JSONField(default=dict, blank=True)
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+'
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']
        indexes = [models.Index(fields=['organization', 'status', '-started_at'])]

    def __str__(self):
        return self.title
