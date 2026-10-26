from django.conf import settings
from django.db import models


class RetentionPolicy(models.Model):
    """Lifecycle for indexed log data.

    The Elasticsearch policy maps to the `loghub-logs` ILM policy applied (via
    the index template) to every organization's data stream, so it is cluster
    wide and only platform administrators may change it. Graylog manages its
    own index-set retention in its UI (see README).
    """

    TARGETS = [('elasticsearch', 'Elasticsearch log data streams')]

    target = models.CharField(max_length=32, choices=TARGETS, unique=True)
    name = models.CharField(max_length=255)
    rollover_days = models.PositiveIntegerField(default=1, help_text='Start a new backing index after N days.')
    delete_after_days = models.PositiveIntegerField(
        default=14, help_text='Delete backing indices N days after rollover.'
    )
    is_active = models.BooleanField(default=True)
    sync_status = models.CharField(max_length=16, default='pending')  # pending | synced | error
    sync_message = models.CharField(max_length=500, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'retention policies'

    def __str__(self):
        return self.name
