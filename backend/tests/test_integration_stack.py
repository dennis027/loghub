"""End-to-end checks against the running stack.

Run inside the django-api container:  pytest -m integration
They push real events through Fluent Bit -> Logstash -> Elasticsearch and read
them back through the API adapters.
"""

import time
import uuid

import pytest
import requests
from django.conf import settings

from search.providers.elasticsearch import ElasticsearchProvider
from search.query import LogQuery

pytestmark = [pytest.mark.integration, pytest.mark.django_db]


class Org:
    slug = 'default'
    masked_fields = []


def _wait_for(fn, timeout=40):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = fn()
        if result:
            return result
        time.sleep(2)
    return None


def test_event_flows_from_fluent_bit_to_search():
    marker = f'it-{uuid.uuid4().hex[:12]}'
    resp = requests.post(
        settings.LOGHUB['FLUENT_BIT_INGEST_URL'],
        timeout=10,
        json=[
            {
                'message': f'integration {marker} password=hunter2',
                'level': 'ERR',
                'service': 'pytest',
                'organization': 'default',
                'environment': 'test',
                'demo': True,
            }
        ],
    )
    assert resp.status_code in (200, 201)
    provider = ElasticsearchProvider()
    hits = _wait_for(lambda: provider.search(Org(), LogQuery.from_params({'q': marker, 'range': '15m'})).hits)
    assert hits, 'event did not reach Elasticsearch'
    event = hits[0]
    assert event['level'] == 'error'  # normalized by the pipeline
    assert 'hunter2' not in event['message']  # masked at ingest
    assert event['source']['fingerprint']


def test_health_of_core_services():
    assert ElasticsearchProvider().health().status == 'healthy'
    from integrations.providers import fluentbit_health, logstash_health

    assert fluentbit_health().status in ('healthy', 'degraded')
    assert logstash_health().status in ('healthy', 'degraded')
