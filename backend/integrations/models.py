from django.db import models


class Integration(models.Model):
    """A platform-level connection to an integrated product (shared by all organizations).

    Connection credentials are read from the environment; `config` holds only
    non-secret options.
    """

    STATUS_CHOICES = [
        ('unknown', 'Unknown'),
        ('healthy', 'Healthy'),
        ('degraded', 'Degraded'),
        ('unhealthy', 'Unhealthy'),
        ('disabled', 'Disabled'),
    ]

    provider = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=255)
    description = models.CharField(max_length=255, blank=True)
    enabled = models.BooleanField(default=True)
    internal_url = models.CharField(max_length=500, blank=True)
    public_url = models.CharField(max_length=500, blank=True)
    config = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='unknown')
    status_message = models.CharField(max_length=500, blank=True)
    version = models.CharField(max_length=64, blank=True)
    latency_ms = models.FloatField(null=True, blank=True)
    details = models.JSONField(default=dict, blank=True)
    last_checked = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'integrations_integration'
        ordering = ['name']

    def __str__(self):
        return self.name
