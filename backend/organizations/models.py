from django.db import models


class Organization(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, help_text='Also determines the log data stream name.')
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    masked_fields = models.JSONField(
        default=list, blank=True, help_text='Extra event fields replaced with [MASKED] in API responses and exports.'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organizations_org'
        ordering = ['name']

    def __str__(self):
        return self.name


class Team(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'organizations_team'
        unique_together = ('organization', 'name')
        ordering = ['name']

    def __str__(self):
        return self.name


class Environment(models.Model):
    """Deployment environments (production, staging, ...) used to tag and filter sources."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name='environments')
    name = models.SlugField(max_length=64)
    description = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('organization', 'name')
        ordering = ['name']

    def __str__(self):
        return self.name
