from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE, null=True, related_name='audit_events'
    )
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    actor_username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=64, db_index=True)
    target_type = models.CharField(max_length=64, blank=True)
    target_id = models.CharField(max_length=64, blank=True)
    target_repr = models.CharField(max_length=255, blank=True)
    changes = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    request_id = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['organization', '-created_at'])]

    def __str__(self):
        return f'{self.actor_username} {self.action} {self.target_type}:{self.target_id}'
