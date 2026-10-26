from django.conf import settings
from django.db import models


class Dashboard(models.Model):
    """A LogHub-native dashboard: a list of widgets rendered by the Angular portal.

    widgets: [{"id", "title", "type": "timeseries|bar|pie|table|stat|logs",
               "query": {q, mode, filters, field_filters}, "agg": {type, field, split_by, metric, ...},
               "layout": {"cols": 1-4}}]
    """

    CATEGORIES = [
        ('application', 'Application errors'),
        ('api', 'API requests'),
        ('auth', 'Authentication'),
        ('web', 'Web server access'),
        ('database', 'Database'),
        ('docker', 'Docker containers'),
        ('infrastructure', 'Infrastructure'),
        ('security', 'Security events'),
        ('custom', 'Custom'),
    ]

    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE, related_name='dashboards')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    folder = models.CharField(max_length=100, blank=True, default='General')
    category = models.CharField(max_length=32, choices=CATEGORIES, default='custom')
    widgets = models.JSONField(default=list, blank=True)
    time_range = models.CharField(max_length=16, default='24h')
    grafana_uid = models.CharField(max_length=64, blank=True, help_text='Optional linked Grafana dashboard.')
    is_template = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['folder', 'name']

    def __str__(self):
        return self.name
