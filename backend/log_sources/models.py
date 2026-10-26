import hashlib
import secrets

from django.conf import settings
from django.db import models

ROUTE_CHOICES = [
    ('elk', 'Elasticsearch (via Logstash)'),
    ('graylog', 'Graylog only'),
    ('both', 'Both (duplicates storage)'),
]


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()


class LogSource(models.Model):
    SOURCE_TYPES = [
        ('docker', 'Docker container'),
        ('linux', 'Linux server'),
        ('nginx', 'Nginx'),
        ('apache', 'Apache'),
        ('django', 'Django application'),
        ('node', 'Node.js application'),
        ('go', 'Go application'),
        ('postgres', 'PostgreSQL'),
        ('mysql', 'MySQL'),
        ('kubernetes', 'Kubernetes workload'),
        ('syslog', 'Syslog device'),
        ('custom', 'Custom HTTP application'),
    ]
    MATCH_FIELDS = [
        ('source_id', 'Source id (token ingestion)'),
        ('service', 'Service name'),
        ('hostname', 'Hostname'),
        ('container', 'Container name'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Waiting for first event'),
        ('active', 'Active'),
        ('stale', 'No recent events'),
        ('disabled', 'Disabled'),
    ]

    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE, related_name='log_sources')
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    source_type = models.CharField(max_length=32, choices=SOURCE_TYPES, default='custom')
    environment = models.CharField(max_length=64, default='production')
    hostname = models.CharField(max_length=255, blank=True)
    endpoint = models.CharField(max_length=500, blank=True, help_text='Optional URL or address of the system.')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_sources'
    )
    team = models.ForeignKey('organizations.Team', on_delete=models.SET_NULL, null=True, blank=True)
    log_route = models.CharField(max_length=16, choices=ROUTE_CHOICES, default='elk')
    match_field = models.CharField(
        max_length=32,
        choices=MATCH_FIELDS,
        default='source_id',
        help_text='Field used to attribute indexed events to this source.',
    )
    match_value = models.CharField(
        max_length=255, blank=True, help_text='Value of match_field; defaults to the source id.'
    )
    stale_after_minutes = models.PositiveIntegerField(default=15)
    enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending')
    last_seen = models.DateTimeField(null=True, blank=True)
    events_24h = models.PositiveBigIntegerField(default=0)
    token_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    token_prefix = models.CharField(max_length=12, blank=True, editable=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'log_sources_logsource'
        ordering = ['name']
        unique_together = ('organization', 'name')

    def __str__(self):
        return self.name

    @property
    def source_key(self):
        return f'src-{self.pk}'

    @property
    def effective_match_value(self):
        if self.match_field == 'source_id':
            return self.source_key
        return self.match_value or self.name

    def issue_token(self):
        """Create a new ingest token; only its hash is stored. Returns the plaintext once."""
        token = 'lh_' + secrets.token_urlsafe(32)
        self.token_hash = hash_token(token)
        self.token_prefix = token[:10]
        self.save(update_fields=['token_hash', 'token_prefix', 'updated_at'])
        return token


class Collector(models.Model):
    """A shipping agent or ingestion endpoint (Fluent Bit, Logstash, Graylog input...)."""

    TYPES = [
        ('fluent-bit', 'Fluent Bit'),
        ('logstash', 'Logstash'),
        ('graylog-input', 'Graylog input'),
        ('beats', 'Beats'),
        ('other', 'Other'),
    ]

    organization = models.ForeignKey('organizations.Organization', on_delete=models.CASCADE, related_name='collectors')
    name = models.CharField(max_length=255)
    collector_type = models.CharField(max_length=32, choices=TYPES)
    endpoint = models.CharField(max_length=500, blank=True)
    managed = models.BooleanField(default=False, help_text='Part of the bundled stack; health is polled.')
    status = models.CharField(max_length=16, default='unknown')
    status_message = models.CharField(max_length=500, blank=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        unique_together = ('organization', 'name')

    def __str__(self):
        return self.name
