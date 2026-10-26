"""Alert rule evaluation.

Semantics
- One open (firing/acknowledged) event per rule: while the condition holds,
  the open event is updated (occurrences, value) instead of creating new ones,
  and no new notifications are sent (deduplication).
- When the condition clears, the open event auto-resolves and channels with
  send_resolved get a resolution notice.
- After a resolution, the rule cannot open a new event for cooldown_minutes.
"""

import contextlib
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core.exceptions import InvalidQuery, ProviderUnavailable
from notifications.tasks import queue_notification
from search.providers.elasticsearch import ElasticsearchProvider
from search.query import LogQuery

from .models import AlertEvent

logger = logging.getLogger(__name__)
COMPARE = {'gt': lambda v, t: v > t, 'gte': lambda v, t: v >= t, 'lt': lambda v, t: v < t, 'lte': lambda v, t: v <= t}
SYMBOL = {'gt': '>', 'gte': '≥', 'lt': '<', 'lte': '≤'}


@dataclass
class Evaluation:
    firing: bool
    value: float
    summary: str
    context: dict = field(default_factory=dict)
    query: LogQuery = None


def rule_query(rule, start, end, size=5):
    params = {
        'q': rule.query,
        'mode': rule.query_mode,
        'start': start,
        'end': end,
        'size': size,
        'field_filters': list(rule.field_filters or []),
        **(rule.filters or {}),
    }
    if rule.source_id:
        src = rule.source
        params['field_filters'].append({'field': src.match_field, 'op': 'eq', 'value': src.effective_match_value})
    return LogQuery.from_params(params)


def evaluate(rule, provider, now=None):
    now = now or timezone.now()
    org = rule.organization
    window = timedelta(minutes=rule.window_minutes)

    if rule.rule_type == 'storage':
        disk = provider.storage().get('disk') or {}
        used = disk.get('used_percent', 0.0)
        firing = COMPARE[rule.comparator](used, rule.threshold)
        return Evaluation(
            firing,
            used,
            f'Elasticsearch disk usage is {used}% ' f'({SYMBOL[rule.comparator]} {rule.threshold:g}% threshold)',
            {'disk': disk},
        )

    query = rule_query(rule, now - window, now)
    count = provider.count(org, query)

    if rule.rule_type == 'threshold':
        firing = COMPARE[rule.comparator](count, rule.threshold)
        return Evaluation(
            firing,
            count,
            f'{count} matching events in the last {rule.window_minutes} min '
            f'({SYMBOL[rule.comparator]} {rule.threshold:g})',
            query=query,
        )

    if rule.rule_type == 'spike':
        previous = provider.count(org, rule_query(rule, now - 2 * window, now - window))
        ratio = count / previous if previous else (float('inf') if count else 0)
        firing = count >= rule.min_count and ratio >= rule.spike_factor
        ratio_txt = f'{ratio:.1f}×' if previous else 'from zero'
        return Evaluation(
            firing,
            count,
            f'{count} events in the last {rule.window_minutes} min vs {previous} in the '
            f'previous window ({ratio_txt}; trigger at {rule.spike_factor:g}× and '
            f'≥ {rule.min_count})',
            {'previous': previous},
            query=query,
        )

    if rule.rule_type == 'absence':
        target = (
            rule.source.name
            if rule.source_id
            else (
                rule.query
                or ', '.join(
                    f'{k}={",".join(v) if isinstance(v, list) else v}' for k, v in (rule.filters or {}).items()
                )
                or 'all logs'
            )
        )
        return Evaluation(
            count == 0,
            count,
            f'No events from {target} in the last {rule.window_minutes} min'
            if count == 0
            else f'{count} events from {target}',
            query=query,
        )

    raise InvalidQuery(f'Unknown rule type {rule.rule_type}')


def _notify(rule, event, kind):
    link = f"{settings.PUBLIC_BASE_URL.rstrip('/')}/alerts/events/{event.pk}"
    if kind == 'firing':
        subject = f'[LogHub][{event.severity.upper()}] {event.title}'
        body = f'{event.message}\n\nRule: {rule.name}\nStarted: {event.started_at:%Y-%m-%d %H:%M:%S} UTC\n'
        if event.samples:
            body += '\nSample events:\n' + '\n'.join(
                f"  - [{s.get('level')}] {s.get('service')}: " f"{str(s.get('message'))[:200]}" for s in event.samples
            )
        body += f'\n\nOpen in LogHub: {link}\n'
    else:
        subject = f'[LogHub][RESOLVED] {event.title}'
        body = f'Resolved at {event.resolved_at:%Y-%m-%d %H:%M:%S} UTC after {event.occurrences} evaluations.\n{link}\n'
    payload = {
        'kind': kind,
        'event_id': event.pk,
        'rule': rule.name,
        'severity': event.severity,
        'status': event.status,
        'value': event.value,
        'organization': rule.organization.slug,
        'url': link,
    }
    for channel in rule.channels.filter(enabled=True):
        if kind == 'resolved' and not channel.send_resolved:
            continue
        queue_notification(channel, subject, body, payload, alert_event=event, kind=kind)


def process_rule(rule, provider=None, now=None):
    """Evaluate and apply state transitions. Returns the open/created AlertEvent or None."""
    provider = provider or ElasticsearchProvider()
    now = now or timezone.now()
    rule.last_evaluated_at = now
    try:
        result = evaluate(rule, provider, now)
    except (ProviderUnavailable, InvalidQuery) as exc:
        rule.last_state, rule.last_error = 'error', str(exc.detail)[:500]
        rule.save(update_fields=['last_evaluated_at', 'last_state', 'last_error'])
        logger.warning('alert rule evaluation failed', extra={'rule': rule.name, 'error_message': rule.last_error})
        return None

    rule.last_value, rule.last_error = result.value, ''
    rule.last_state = 'firing' if result.firing else 'ok'
    rule.save(update_fields=['last_evaluated_at', 'last_value', 'last_state', 'last_error'])

    open_event = rule.events.filter(status__in=['firing', 'acknowledged']).first()
    if result.firing:
        if open_event:
            open_event.occurrences += 1
            open_event.value = result.value
            open_event.last_seen_at = now
            open_event.save(update_fields=['occurrences', 'value', 'last_seen_at'])
            return open_event
        last_resolved = rule.events.filter(status='resolved').order_by('-resolved_at').first()
        if last_resolved and last_resolved.resolved_at > now - timedelta(minutes=rule.cooldown_minutes):
            rule.last_state = 'cooldown'
            rule.save(update_fields=['last_state'])
            logger.info('alert suppressed by cooldown', extra={'rule': rule.name})
            return None
        samples = []
        if result.query is not None and rule.rule_type in ('threshold', 'spike'):
            with contextlib.suppress(ProviderUnavailable):  # samples are best-effort
                samples = [
                    {k: h.get(k) for k in ('id', 'timestamp', 'level', 'service', 'hostname', 'message')}
                    for h in provider.search(rule.organization, result.query).hits[:5]
                ]
        event = AlertEvent.objects.create(
            organization=rule.organization,
            rule=rule,
            rule_name=rule.name,
            severity=rule.severity,
            category=rule.category,
            title=rule.name,
            message=result.summary,
            value=result.value,
            threshold=rule.threshold,
            samples=samples,
            context=result.context,
        )
        logger.warning(
            'alert fired',
            extra={'rule': rule.name, 'severity': rule.severity, 'value': result.value, 'event_type': 'alert_fired'},
        )
        _notify(rule, event, 'firing')
        return event

    if open_event:
        open_event.status, open_event.resolved_at = 'resolved', now
        open_event.save(update_fields=['status', 'resolved_at'])
        logger.info('alert resolved', extra={'rule': rule.name, 'event_type': 'alert_resolved'})
        _notify(rule, open_event, 'resolved')
    return None
