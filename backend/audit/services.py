import logging
import re

logger = logging.getLogger('loghub.audit')

_SENSITIVE = re.compile(r'pass|secret|token|key|credential', re.I)


def _sanitize(value, depth=0):
    if depth > 4:
        return '…'
    if isinstance(value, dict):
        return {
            str(k): '[REDACTED]' if _SENSITIVE.search(str(k)) else _sanitize(v, depth + 1) for k, v in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_sanitize(v, depth + 1) for v in list(value)[:50]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, 'pk'):
        return value.pk
    return str(value)


def client_ip(request):
    # nginx sets X-Real-IP; trust only that single hop, not arbitrary X-Forwarded-For chains.
    return request.META.get('HTTP_X_REAL_IP') or request.META.get('REMOTE_ADDR')


def record_audit(
    request, action, *, target_type='', target_id='', target_repr='', changes=None, user=None, organization=None
):
    from .models import AuditEvent

    actor = user or (request.user if request is not None and request.user.is_authenticated else None)
    org = organization or (actor.organization if actor is not None else None)
    event = AuditEvent.objects.create(
        organization=org,
        actor=actor,
        actor_username=actor.username if actor else (changes or {}).get('username', '')[:150],
        action=action,
        target_type=target_type,
        target_id=str(target_id or ''),
        target_repr=str(target_repr or '')[:255],
        changes=_sanitize(changes or {}),
        ip_address=client_ip(request) if request is not None else None,
        user_agent=(request.headers.get('User-Agent', '') if request is not None else '')[:255],
        request_id=getattr(request, 'request_id', '') or '',
    )
    logger.info(
        'audit %s %s:%s',
        action,
        target_type,
        target_id,
        extra={
            'event_type': 'audit',
            'audit_action': action,
            'user': event.actor_username,
            'organization': org.slug if org else None,
        },
    )
    return event
