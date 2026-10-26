from datetime import timedelta

from celery import shared_task
from django.core.cache import cache
from django.utils import timezone

from search.providers.elasticsearch import ElasticsearchProvider

from .engine import process_rule
from .models import AlertRule


@shared_task(ignore_result=True)
def evaluate_due_rules():
    """Evaluate every enabled rule whose interval has elapsed. A per-rule lock prevents overlap."""
    now = timezone.now()
    provider = ElasticsearchProvider()
    rules = AlertRule.objects.select_related('organization', 'source').filter(
        enabled=True, organization__is_active=True
    )
    for rule in rules:
        if rule.last_evaluated_at and rule.last_evaluated_at + timedelta(
            seconds=rule.evaluation_interval_seconds
        ) > now + timedelta(seconds=2):
            continue
        lock = f'alert-rule-lock:{rule.pk}'
        if not cache.add(lock, 1, timeout=120):
            continue
        try:
            process_rule(rule, provider, now)
        finally:
            cache.delete(lock)


@shared_task(ignore_result=True)
def evaluate_rule(rule_id):
    rule = AlertRule.objects.select_related('organization', 'source').get(pk=rule_id)
    process_rule(rule)
