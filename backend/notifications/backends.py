"""Notification channel backends. Add a channel by subclassing ChannelBackend and registering it."""

import hashlib
import hmac
import ipaddress
import json
import socket
from urllib.parse import urlparse

import requests
from django.conf import settings
from django.core.mail import send_mail


class DeliveryError(Exception):
    """Raised for failures worth retrying."""


class ChannelBackend:
    def validate_config(self, config):
        return config

    def send(self, channel, subject, body, payload):
        raise NotImplementedError


class EmailBackend(ChannelBackend):
    def validate_config(self, config):
        from django.core.validators import validate_email

        recipients = config.get('recipients')
        if not isinstance(recipients, list) or not 1 <= len(recipients) <= 50:
            raise ValueError('Provide 1–50 recipients.')
        for r in recipients:
            validate_email(r)
        return {'recipients': recipients}

    def send(self, channel, subject, body, payload):
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, channel.config['recipients'], fail_silently=False)
        except (OSError, Exception) as exc:  # smtplib errors subclass OSError/SMTPException
            raise DeliveryError(f'SMTP delivery failed: {exc}') from exc


def _is_private(host):
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ValueError(f'Cannot resolve {host}.') from None
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return True
    return False


class WebhookBackend(ChannelBackend):
    def validate_config(self, config):
        url = config.get('url', '')
        parsed = urlparse(url)
        if parsed.scheme not in ('https', 'http') or not parsed.hostname:
            raise ValueError('Provide an http(s) URL.')
        if not settings.LOGHUB['WEBHOOK_ALLOW_PRIVATE_NETWORKS'] and _is_private(parsed.hostname):
            raise ValueError(
                'Webhooks to private or loopback addresses are blocked '
                '(set WEBHOOK_ALLOW_PRIVATE_NETWORKS=true to allow).'
            )
        return {'url': url}

    def send(self, channel, subject, body, payload):
        url = channel.config['url']
        self.validate_config({'url': url})  # re-check at send time (DNS may have changed)
        data = json.dumps({'subject': subject, 'text': body, **payload}, default=str).encode()
        headers = {'Content-Type': 'application/json', 'User-Agent': 'LogHub-Alerts/1.0'}
        if channel.secret:
            headers['X-LogHub-Signature'] = (
                'sha256=' + hmac.new(channel.secret.encode(), data, hashlib.sha256).hexdigest()
            )
        try:
            resp = requests.post(url, data=data, headers=headers, timeout=10, allow_redirects=False)
        except requests.RequestException as exc:
            raise DeliveryError(f'Webhook request failed: {exc.__class__.__name__}') from exc
        if resp.status_code >= 500 or resp.status_code == 429:
            raise DeliveryError(f'Webhook returned {resp.status_code}')
        if resp.status_code >= 400:
            raise ValueError(f'Webhook rejected the notification ({resp.status_code}); not retrying.')


BACKENDS = {'email': EmailBackend(), 'webhook': WebhookBackend()}
