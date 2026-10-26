"""Provider adapter interface.

Each log backend (Elasticsearch, Graylog, ...) implements LogProvider so the API,
alert engine and reports never depend on a concrete product. Add a backend by
subclassing LogProvider and registering it in search.providers.registry.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class HealthResult:
    status: str  # healthy | degraded | unhealthy | disabled
    message: str = ''
    latency_ms: float = None
    version: str = ''
    details: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    provider: str
    hits: list
    total: int
    total_relation: str = 'eq'
    took_ms: int = 0
    cursor: str = None
    timed_out: bool = False


class LogProvider(ABC):
    name = 'base'
    label = 'Base'
    supports_aggregations = False
    supports_cursor = False

    @abstractmethod
    def search(self, organization, query):
        """Return a SearchResult for a search.query.LogQuery."""

    def aggregate(self, organization, query, spec):
        raise NotImplementedError(f'{self.label} does not support aggregations')

    def count(self, organization, query):
        return self.search(organization, query).total

    @abstractmethod
    def health(self):
        """Return a HealthResult; must never raise."""

    def external_link(self, query):
        """URL to open the equivalent search in the product's own UI, if any."""
        return None
