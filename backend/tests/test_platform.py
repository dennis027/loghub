from unittest import mock

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

from audit.services import record_audit
from dashboards.models import Dashboard
from integrations.models import Integration
from organizations.models import Organization
from retention.models import RetentionPolicy

pytestmark = pytest.mark.django_db


def test_no_pending_migrations():
    executor = MigrationExecutor(connection)
    assert not executor.migration_plan(executor.loader.graph.leaf_nodes())
    from django.core.management import call_command as cc

    cc('makemigrations', '--check', '--dry-run', verbosity=0)


def test_bootstrap_is_idempotent(monkeypatch):
    monkeypatch.setenv('DJANGO_SUPERUSER_USERNAME', 'root')
    monkeypatch.setenv('DJANGO_SUPERUSER_PASSWORD', 'Sup3r-Secret-pw')
    monkeypatch.setenv('DJANGO_SUPERUSER_EMAIL', 'root@example.com')
    call_command('bootstrap_platform', verbosity=0)
    call_command('bootstrap_platform', verbosity=0)
    org = Organization.objects.get(slug='default')
    assert org.members.get(username='root').role == 'admin'
    assert Dashboard.objects.filter(organization=org, is_template=True).count() == 8
    assert Integration.objects.count() == 7
    assert RetentionPolicy.objects.count() == 1


def test_audit_redacts_sensitive_changes(org, admin_user):
    request = mock.Mock(
        user=admin_user, META={'REMOTE_ADDR': '10.0.0.1'}, headers={'User-Agent': 'pytest'}, request_id='abc12345'
    )
    event = record_audit(
        request,
        'update',
        target_type='channel',
        changes={'name': 'x', 'secret': 'hunter2', 'config': {'api_key': 'k', 'url': 'u'}},
    )
    assert event.changes == {'name': 'x', 'secret': '[REDACTED]', 'config': {'api_key': '[REDACTED]', 'url': 'u'}}
    assert event.ip_address == '10.0.0.1' and event.organization == org


def test_writes_are_audited(admin_client):
    from audit.models import AuditEvent

    resp = admin_client.post('/api/dashboards/', {'name': 'Mine', 'widgets': []}, format='json')
    assert resp.status_code == 201
    assert AuditEvent.objects.filter(action='create', target_type='dashboard').exists()


def test_dashboard_widget_validation_and_duplicate(admin_client):
    bad = admin_client.post(
        '/api/dashboards/', {'name': 'x', 'widgets': [{'type': 'iframe', 'title': 't'}]}, format='json'
    )
    assert bad.status_code == 400
    ok = admin_client.post(
        '/api/dashboards/',
        {'name': 'x', 'widgets': [{'type': 'stat', 'title': 'Errors', 'agg': {'type': 'metric'}}]},
        format='json',
    )
    dup = admin_client.post(f"/api/dashboards/{ok.data['id']}/duplicate/", {}, format='json')
    assert dup.status_code == 201 and dup.data['name'] == 'x (copy)'


def test_health_endpoints(client):
    assert client.get('/health/live').status_code == 200
    resp = client.get('/health/ready')
    assert resp.json()['checks']['database'] == 'ok'


def test_integration_health_is_resilient():
    from integrations import providers

    def boom():
        raise RuntimeError('adapter bug')

    with mock.patch.dict(providers.REGISTRY, {'kibana': ('Kibana', '', boom, None, 'KIBANA_URL')}):
        result = providers.check('kibana')
    assert result.status == 'unhealthy' and 'RuntimeError' in result.message


def test_graylog_health_handles_unreachable():
    import requests

    from search.providers.graylog import GraylogProvider

    with mock.patch('search.providers.graylog._session.get', side_effect=requests.ConnectionError()):
        assert GraylogProvider().health().status == 'unhealthy'


def test_overview_degrades_when_elasticsearch_down(admin_client):
    from core.exceptions import ProviderUnavailable

    with mock.patch(
        'search.providers.elasticsearch.ElasticsearchProvider.aggregate', side_effect=ProviderUnavailable()
    ):
        resp = admin_client.get('/api/stats/overview/')
    assert resp.status_code == 200 and resp.data['elasticsearch_available'] is False
    assert 'total_events' not in resp.data  # never fabricated


def test_reports_csv_requires_analyst(viewer_client):
    with mock.patch('reports.generators.LogSource.objects') as _:
        resp = viewer_client.get('/api/reports/source-availability/?format=csv')
    assert resp.status_code == 403


def test_report_alert_history_json(admin_client):
    resp = admin_client.get('/api/reports/alert-history/?range=7d')
    assert resp.status_code == 200 and resp.data['columns'][0] == 'started_at'


def test_report_pdf(admin_client):
    resp = admin_client.get('/api/reports/source-availability/?format=pdf')
    assert resp.status_code == 200 and resp.content.startswith(b'%PDF')


def test_openapi_schema(admin_client):
    resp = admin_client.get('/api/schema/')
    assert resp.status_code == 200


def test_builtin_widget_queries_apply_their_filters():
    """Regression: widget filters must be in the flat shape the search API reads."""
    from dashboards.templates import DASHBOARD_TEMPLATES
    from search.query import LogQuery

    errors = next(t for t in DASHBOARD_TEMPLATES if t['category'] == 'application')['widgets'][0]
    assert 'filters' not in errors['query']
    assert LogQuery.from_params(errors['query']).filters == {'level': ['error', 'critical']}


def test_bootstrap_flattens_legacy_widget_queries(monkeypatch, org):
    from core.management.commands.bootstrap_platform import seed_organization

    legacy = Dashboard.objects.create(
        organization=org,
        name='Application errors',
        is_template=True,
        widgets=[{'id': 'e1', 'title': 'Errors', 'type': 'stat', 'query': {'filters': {'level': ['error']}}}],
    )
    seed_organization(org)
    legacy.refresh_from_db()
    assert legacy.widgets[0]['query'] == {'level': ['error']}


def test_default_rules_seeded_once_with_admin_channel(org, admin_user):
    from alerts.models import AlertRule
    from core.management.commands.bootstrap_platform import seed_default_rules, seed_organization

    seed_organization(org, admin_user)
    assert seed_default_rules(org) == 4
    assert seed_default_rules(org) == 0
    rule = AlertRule.objects.get(organization=org, name='Critical errors exceed threshold')
    assert rule.enabled and rule.channels.filter(channel_type='email').exists()
