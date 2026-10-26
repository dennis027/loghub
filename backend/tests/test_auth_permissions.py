import pytest
from rest_framework.test import APIClient

from audit.models import AuditEvent
from log_sources.models import LogSource
from tests.conftest import client_for, make_user

pytestmark = pytest.mark.django_db


def test_login_returns_tokens_and_audits(admin_user):
    resp = APIClient().post(
        '/api/auth/login/', {'username': admin_user.username, 'password': 'Sup3r-Secret-pw'}, format='json'
    )
    assert resp.status_code == 200
    assert {'access', 'refresh'} <= set(resp.data)
    assert AuditEvent.objects.filter(action='login', actor=admin_user).exists()


def test_failed_login_is_audited_with_error_envelope(admin_user):
    resp = APIClient().post('/api/auth/login/', {'username': admin_user.username, 'password': 'wrong'}, format='json')
    assert resp.status_code == 401
    assert resp.data['error']['code']
    assert AuditEvent.objects.filter(action='login_failed', target_repr=admin_user.username).exists()


def test_user_without_organization_cannot_log_in(db):
    from accounts.models import User

    User.objects.create_user(username='orphan', password='Sup3r-Secret-pw')
    resp = APIClient().post('/api/auth/login/', {'username': 'orphan', 'password': 'Sup3r-Secret-pw'}, format='json')
    assert resp.status_code == 403


def test_logout_blacklists_refresh(admin_user):
    client = APIClient()
    tokens = client.post(
        '/api/auth/login/', {'username': admin_user.username, 'password': 'Sup3r-Secret-pw'}, format='json'
    ).data
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    assert client.post('/api/auth/logout/', {'refresh': tokens['refresh']}, format='json').status_code == 204
    assert APIClient().post('/api/auth/refresh/', {'refresh': tokens['refresh']}, format='json').status_code == 401


def test_anonymous_requests_are_rejected():
    assert APIClient().get('/api/log-sources/').status_code == 401


def test_viewer_can_read_but_not_write(viewer_client, org):
    assert viewer_client.get('/api/log-sources/').status_code == 200
    resp = viewer_client.post('/api/log-sources/', {'name': 'x', 'source_type': 'custom'}, format='json')
    assert resp.status_code == 403


def test_only_admins_manage_users(org, viewer_client, admin_client):
    payload = {'username': 'newbie', 'password': 'An0ther-Secret-pw', 'role': 'viewer', 'email': 'n@acme.test'}
    assert viewer_client.post('/api/users/', payload, format='json').status_code == 403
    resp = admin_client.post('/api/users/', payload, format='json')
    assert resp.status_code == 201
    assert 'password' not in resp.data


def test_admin_cannot_demote_self(admin_client, admin_user):
    resp = admin_client.patch(f'/api/users/{admin_user.pk}/', {'role': 'viewer'}, format='json')
    assert resp.status_code == 400


def test_weak_passwords_rejected(admin_client):
    resp = admin_client.post('/api/users/', {'username': 'weak', 'password': '12345678'}, format='json')
    assert resp.status_code == 400
    assert resp.data['error']['code'] == 'validation_error'


def test_audit_log_is_admin_only(viewer_client, admin_client):
    assert viewer_client.get('/api/audit-events/').status_code == 403
    assert admin_client.get('/api/audit-events/').status_code == 200


def test_export_requires_analyst(viewer_client):
    assert viewer_client.get('/api/logs/export/').status_code == 403


def test_retention_changes_require_platform_admin(org, admin_user):
    from retention.models import RetentionPolicy

    policy = RetentionPolicy.objects.create(target='elasticsearch', name='Logs')
    non_staff_admin = make_user(org, 'admin', username='orgadmin')
    resp = client_for(non_staff_admin).patch(
        f'/api/retention-policies/{policy.pk}/', {'delete_after_days': 30}, format='json'
    )
    assert resp.status_code == 403


class TestOrganizationIsolation:
    def test_sources_of_other_org_are_invisible(self, org, other_org, admin_client):
        LogSource.objects.create(organization=other_org, name='secret-app')
        mine = LogSource.objects.create(organization=org, name='my-app')
        names = [s['name'] for s in admin_client.get('/api/log-sources/').data['results']]
        assert names == [mine.name]

    def test_cannot_fetch_or_modify_other_org_objects(self, other_org, admin_client):
        theirs = LogSource.objects.create(organization=other_org, name='secret-app')
        assert admin_client.get(f'/api/log-sources/{theirs.pk}/').status_code == 404
        assert admin_client.delete(f'/api/log-sources/{theirs.pk}/').status_code == 404
        assert LogSource.objects.filter(pk=theirs.pk).exists()

    def test_created_objects_are_bound_to_callers_org(self, org, other_org, admin_client):
        resp = admin_client.post(
            '/api/log-sources/', {'name': 'svc', 'source_type': 'custom', 'organization': other_org.pk}, format='json'
        )
        assert resp.status_code == 201
        assert LogSource.objects.get(pk=resp.data['id']).organization == org

    def test_cannot_reference_other_org_team(self, other_org, admin_client):
        from organizations.models import Team

        team = Team.objects.create(organization=other_org, name='ops')
        resp = admin_client.post('/api/log-sources/', {'name': 'svc', 'team': team.pk}, format='json')
        assert resp.status_code == 400

    def test_users_list_scoped(self, org, other_org, admin_client):
        make_user(other_org, 'viewer', username='stranger')
        usernames = {u['username'] for u in admin_client.get('/api/users/').data['results']}
        assert 'stranger' not in usernames
