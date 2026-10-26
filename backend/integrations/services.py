from django.conf import settings
from django.utils import timezone

from .models import Integration
from .providers import REGISTRY, check


def ensure_integrations():
    for key, (label, description, _, public_setting, internal_setting) in REGISTRY.items():
        Integration.objects.update_or_create(
            provider=key,
            defaults={
                'name': label,
                'description': description,
                'internal_url': settings.LOGHUB[internal_setting],
                'public_url': settings.LOGHUB[public_setting] if public_setting else '',
            },
        )


def refresh_integration(integration):
    if not integration.enabled:
        result_status, message = 'disabled', 'Disabled by an administrator'
        integration.status, integration.status_message = result_status, message
    else:
        result = check(integration.provider)
        integration.status = result.status
        integration.status_message = result.message[:500]
        integration.version = result.version or integration.version
        integration.latency_ms = result.latency_ms
        integration.details = result.details
    integration.last_checked = timezone.now()
    integration.save()
    return integration
