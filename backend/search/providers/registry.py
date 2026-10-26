from core.exceptions import InvalidQuery

from .elasticsearch import ElasticsearchProvider
from .graylog import GraylogProvider

PROVIDERS = {
    ElasticsearchProvider.name: ElasticsearchProvider,
    GraylogProvider.name: GraylogProvider,
}
DEFAULT_PROVIDER = ElasticsearchProvider.name


def get_provider(name=None):
    cls = PROVIDERS.get(name or DEFAULT_PROVIDER)
    if cls is None:
        raise InvalidQuery(f'Unknown search provider {name!r}; available: {", ".join(PROVIDERS)}')
    return cls()
