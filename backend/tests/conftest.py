import pytest
from rest_framework.test import APIClient

from accounts.models import User
from organizations.models import Organization


@pytest.fixture
def org(db):
    return Organization.objects.create(name='Acme', slug='acme')


@pytest.fixture
def other_org(db):
    return Organization.objects.create(name='Globex', slug='globex')


def make_user(org, role='admin', username=None, **extra):
    return User.objects.create_user(
        username=username or f'{role}-{org.slug}',
        password='Sup3r-Secret-pw',
        email=f'{role}@{org.slug}.test',
        organization=org,
        role=role,
        **extra,
    )


@pytest.fixture
def admin_user(org):
    return make_user(org, 'admin', is_staff=True)


@pytest.fixture
def viewer_user(org):
    return make_user(org, 'viewer')


@pytest.fixture
def analyst_user(org):
    return make_user(org, 'analyst')


def client_for(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def admin_client(admin_user):
    return client_for(admin_user)


@pytest.fixture
def viewer_client(viewer_user):
    return client_for(viewer_user)


class FakeProvider:
    """Stands in for ElasticsearchProvider in alert tests."""

    def __init__(self, counts=None, disk=50.0):
        self.counts = list(counts or [])
        self.disk = disk
        self.queries = []

    def count(self, organization, query):
        self.queries.append(query)
        return self.counts.pop(0) if self.counts else 0

    def search(self, organization, query):
        from search.providers.base import SearchResult

        return SearchResult(
            provider='fake',
            total=1,
            hits=[
                {
                    'id': '1',
                    'timestamp': '2026-01-01T00:00:00Z',
                    'level': 'error',
                    'service': 'api',
                    'hostname': 'h',
                    'message': 'boom',
                    'source': {},
                }
            ],
        )

    def storage(self, organization=None):
        return {'disk': {'used_percent': self.disk}}


@pytest.fixture
def fake_provider():
    return FakeProvider
