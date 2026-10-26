from unittest import mock

import pytest
import requests
from rest_framework.test import APIClient

from log_sources.models import LogSource, hash_token
from log_sources.tasks import refresh_org_sources

pytestmark = pytest.mark.django_db


def test_register_source_defaults(admin_client, admin_user):
    resp = admin_client.post(
        '/api/log-sources/', {'name': 'nginx-edge', 'source_type': 'nginx', 'environment': 'production'}, format='json'
    )
    assert resp.status_code == 201
    data = resp.data
    assert data['match_field'] == 'service'  # collector-type sources match on service by default
    assert data['owner'] == admin_user.pk
    assert data['status'] == 'pending' and data['has_token'] is False


def test_duplicate_name_rejected(admin_client):
    admin_client.post('/api/log-sources/', {'name': 'a'}, format='json')
    assert admin_client.post('/api/log-sources/', {'name': 'a'}, format='json').status_code == 400


def test_token_is_shown_once_and_stored_hashed(admin_client, org):
    source = LogSource.objects.create(organization=org, name='app')
    resp = admin_client.post(f'/api/log-sources/{source.pk}/rotate-token/')
    token = resp.data['token']
    source.refresh_from_db()
    assert token.startswith('lh_') and source.token_hash == hash_token(token)
    assert token not in str(admin_client.get(f'/api/log-sources/{source.pk}/').data)


def test_instructions_never_embed_token(admin_client, org):
    source = LogSource.objects.create(organization=org, name='app', source_type='django')
    token = source.issue_token()
    resp = admin_client.get(f'/api/log-sources/{source.pk}/instructions/')
    assert resp.status_code == 200 and len(resp.data['steps']) >= 2
    assert token not in str(resp.data) and '<INGEST_TOKEN>' in str(resp.data)


class TestIngest:
    def _post(self, token, body):
        return APIClient().post('/api/ingest/', body, format='json', HTTP_X_LOGHUB_TOKEN=token)

    def test_requires_valid_token(self):
        assert APIClient().post('/api/ingest/', {'message': 'x'}, format='json').status_code == 401
        assert self._post('lh_wrong', {'message': 'x'}).status_code == 401

    def test_stamps_tenant_fields_and_forwards(self, org):
        source = LogSource.objects.create(organization=org, name='billing', environment='staging', log_route='both')
        token = source.issue_token()
        with mock.patch('log_sources.ingest._session.post') as post:
            post.return_value = mock.Mock(raise_for_status=lambda: None)
            resp = self._post(
                token,
                [
                    {'message': 'paid', 'organization': 'evil', 'source_id': 'spoof'},
                    {'msg': 'second', 'service': 'custom-svc'},
                ],
            )
        assert resp.status_code == 202 and resp.data['accepted'] == 2
        batch = post.call_args.kwargs['json']
        assert all(e['organization'] == 'acme' and e['source_id'] == source.source_key for e in batch)
        assert batch[0]['environment'] == 'staging' and batch[0]['service'] == 'billing'
        assert batch[1]['service'] == 'custom-svc' and batch[0]['log_route'] == 'both'
        source.refresh_from_db()
        assert source.status == 'active' and source.last_seen is not None

    def test_validation(self, org):
        token = LogSource.objects.create(organization=org, name='x').issue_token()
        assert self._post(token, [{'level': 'info'}]).status_code == 400
        assert self._post(token, ['not-an-object']).status_code == 400
        assert self._post(token, [{'message': 'm'}] * 1001).status_code == 400

    def test_disabled_source_rejected(self, org):
        source = LogSource.objects.create(organization=org, name='x', enabled=False)
        assert self._post(source.issue_token(), {'message': 'm'}).status_code == 401

    def test_collector_down_returns_503_with_retry_after(self, org):
        token = LogSource.objects.create(organization=org, name='x').issue_token()
        with mock.patch('log_sources.ingest._session.post', side_effect=requests.ConnectionError()):
            resp = self._post(token, {'message': 'm'})
        assert resp.status_code == 503 and resp['Retry-After'] == '10'


def test_source_status_from_index(org):
    fresh = LogSource.objects.create(organization=org, name='api', match_field='service', stale_after_minutes=15)
    old = LogSource.objects.create(organization=org, name='batch', match_field='service', stale_after_minutes=15)
    never = LogSource.objects.create(organization=org, name='new')
    from django.utils import timezone

    now = timezone.now()
    provider = mock.Mock()
    provider.last_seen.side_effect = lambda org_, field, values, since: {
        'service': {
            'api': {'last_seen': now.isoformat(), 'count': 5},
            'batch': {'last_seen': (now - timezone.timedelta(hours=3)).isoformat(), 'count': 1},
        },
        'source_id': {},
    }[field]
    refresh_org_sources(org, provider)
    for s in (fresh, old, never):
        s.refresh_from_db()
    assert (fresh.status, old.status, never.status) == ('active', 'stale', 'pending')
    assert fresh.events_24h == 5
