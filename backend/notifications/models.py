from django.db import models


class NotificationChannel(models.Model):
    TYPES = [('email', 'Email'), ('webhook', 'Webhook')]

    organization = models.ForeignKey(
        'organizations.Organization', on_delete=models.CASCADE, related_name='notification_channels'
    )
    name = models.CharField(max_length=255)
    channel_type = models.CharField(max_length=16, choices=TYPES)
    config = models.JSONField(default=dict, blank=True, help_text='email: {"recipients": [...]}; webhook: {"url"}')
    secret = models.CharField(
        max_length=255, blank=True, help_text='Webhook HMAC signing secret; write-only through the API.'
    )
    enabled = models.BooleanField(default=True)
    send_resolved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('organization', 'name')

    def __str__(self):
        return self.name


class NotificationDelivery(models.Model):
    STATUS = [('pending', 'Pending'), ('sent', 'Sent'), ('failed', 'Failed')]

    channel = models.ForeignKey(NotificationChannel, on_delete=models.CASCADE, related_name='deliveries')
    alert_event = models.ForeignKey(
        'alerts.AlertEvent', on_delete=models.CASCADE, null=True, blank=True, related_name='deliveries'
    )
    kind = models.CharField(max_length=16, default='firing')  # firing | resolved | test
    status = models.CharField(max_length=16, choices=STATUS, default='pending')
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    subject = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.kind} via {self.channel_id}: {self.status}'
