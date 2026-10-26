"""Idempotent platform bootstrap, run on every API start.

- default organization and initial administrator (from DJANGO_SUPERUSER_* env)
- managed collectors, integration registry, Elasticsearch retention policy
- built-in dashboards and an email channel for the admin
"""

import os

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from alerts.models import AlertRule
from alerts.templates import RULE_TEMPLATES
from dashboards.models import Dashboard
from dashboards.templates import DASHBOARD_TEMPLATES
from integrations.services import ensure_integrations
from log_sources.models import Collector
from notifications.models import NotificationChannel
from organizations.models import Environment, Organization
from retention.models import RetentionPolicy

MANAGED_COLLECTORS = [
    ('Fluent Bit (bundled)', 'fluent-bit', 'forward :24224 · http :9880 · syslog :5140'),
    ('Logstash (bundled)', 'logstash', 'http :8080 (internal) · beats :5044'),
]


# Enabled out of the box for new organizations; editable/deletable afterwards.
DEFAULT_RULES = ('critical-errors', 'http-5xx-spike', 'disk-usage', 'auth-bruteforce')


def seed_default_rules(org):
    channels = list(NotificationChannel.objects.filter(organization=org, enabled=True))
    created = 0
    for tpl in RULE_TEMPLATES:
        if tpl['key'] not in DEFAULT_RULES:
            continue
        fields = {k: v for k, v in tpl.items() if k != 'key'}
        rule, was_created = AlertRule.objects.get_or_create(organization=org, name=fields.pop('name'), defaults=fields)
        if was_created:
            rule.channels.set(channels)
            created += 1
    return created


def seed_organization(org, admin=None):
    for name in ('production', 'staging', 'development'):
        Environment.objects.get_or_create(organization=org, name=name)
    for name, ctype, endpoint in MANAGED_COLLECTORS:
        Collector.objects.get_or_create(
            organization=org, name=name, defaults={'collector_type': ctype, 'endpoint': endpoint, 'managed': True}
        )
    for tpl in DASHBOARD_TEMPLATES:
        dash, created = Dashboard.objects.get_or_create(
            organization=org,
            name=tpl['name'],
            is_template=True,
            defaults={
                'description': tpl['description'],
                'folder': tpl['folder'],
                'category': tpl['category'],
                'widgets': tpl['widgets'],
                'grafana_uid': tpl.get('grafana_uid', ''),
                'created_by': admin,
            },
        )
        # Built-ins seeded by earlier versions nested filters under query.filters; flatten them in place.
        if not created and any('filters' in (w.get('query') or {}) for w in dash.widgets):
            for w in dash.widgets:
                q = w.get('query') or {}
                q.update(q.pop('filters', {}))
                w['query'] = q
            dash.save(update_fields=['widgets', 'updated_at'])
    if admin and admin.email:
        NotificationChannel.objects.get_or_create(
            organization=org,
            name='Administrators (email)',
            defaults={'channel_type': 'email', 'config': {'recipients': [admin.email]}},
        )


class Command(BaseCommand):
    help = 'Create the default organization, admin user and platform metadata (idempotent).'

    @transaction.atomic
    def add_arguments(self, parser):
        parser.add_argument(
            '--seed-default-rules',
            action='store_true',
            help='Create the default alert rules in the default organization (idempotent).',
        )

    def handle(self, *args, **options):
        slug = settings.LOGHUB['DEFAULT_ORGANIZATION_SLUG']
        org, created = Organization.objects.get_or_create(slug=slug, defaults={'name': slug.replace('-', ' ').title()})
        if created:
            self.stdout.write(f'created organization {slug}')

        admin = None
        username = os.environ.get('DJANGO_SUPERUSER_USERNAME')
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD')
        if username and password:
            User = get_user_model()
            admin = User.objects.filter(username=username).first()
            if admin is None:
                admin = User.objects.create_superuser(
                    username=username,
                    password=password,
                    email=os.environ.get('DJANGO_SUPERUSER_EMAIL', ''),
                    organization=org,
                    role='admin',
                )
                self.stdout.write(f'created administrator {username}')
            elif admin.organization_id is None:
                admin.organization, admin.role = org, 'admin'
                admin.save(update_fields=['organization', 'role'])

        seed_organization(org, admin)
        if created or options.get('seed_default_rules'):
            self.stdout.write(f'default alert rules created: {seed_default_rules(org)}')
        ensure_integrations()
        RetentionPolicy.objects.get_or_create(
            target='elasticsearch',
            defaults={
                'name': 'Log data (Elasticsearch)',
                'rollover_days': 1,
                'delete_after_days': 14,
                'sync_status': 'synced',
                'sync_message': 'Created by the stack bootstrap (14 days)',
            },
        )
        self.stdout.write(self.style.SUCCESS('platform bootstrap complete'))
