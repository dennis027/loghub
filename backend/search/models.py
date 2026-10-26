from django.conf import settings
from django.db import models


class SavedSearch(models.Model):
    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE, related_name='saved_searches'
    )
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=500, blank=True)
    provider = models.CharField(max_length=32, default='elasticsearch')
    query = models.CharField(max_length=2000, blank=True)
    query_mode = models.CharField(max_length=16, default='simple')
    filters = models.JSONField(default=dict, blank=True)
    field_filters = models.JSONField(default=list, blank=True)
    time_range = models.CharField(max_length=16, default='1h')
    is_shared = models.BooleanField(default=True, help_text='Visible to everyone in the organization.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name
