"""Validated, provider-neutral representation of a log query."""

import base64
import binascii
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from core.exceptions import InvalidQuery

FIELD_NAME = re.compile(r'^[A-Za-z_@][A-Za-z0-9_.@-]{0,99}$')
RELATIVE = re.compile(r'^(\d{1,4})([smhdw])$')
UNIT_SECONDS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'w': 604800}
MAX_RANGE = timedelta(days=90)

# Shorthand filter parameters accepted by the API and their indexed field names.
STANDARD_FILTERS = {
    'service': 'service',
    'environment': 'environment',
    'hostname': 'hostname',
    'container': 'container',
    'level': 'level',
    'source_id': 'source_id',
    'source_type': 'source_type',
    'collector': 'collector',
    'event_type': 'event_type',
    'log_route': 'log_route',
}
OPERATORS = {'eq', 'neq', 'exists', 'missing', 'gt', 'gte', 'lt', 'lte', 'contains'}
QUERY_MODES = {'simple', 'lucene'}
LEVELS = ['debug', 'info', 'warning', 'error', 'critical']


def validate_field(name):
    if not isinstance(name, str) or not FIELD_NAME.match(name):
        raise InvalidQuery(f'Invalid field name: {name!r}')
    if name == 'organization':
        raise InvalidQuery('Filtering on the organization field is not allowed.')
    return name


def parse_relative(value):
    match = RELATIVE.match(value or '')
    if not match:
        raise InvalidQuery(f'Invalid relative range {value!r}; use e.g. 15m, 1h, 7d.')
    return timedelta(seconds=int(match.group(1)) * UNIT_SECONDS[match.group(2)])


def parse_time(value, name):
    if value in (None, ''):
        return None
    if isinstance(value, datetime):
        return value
    if value == 'now':
        return timezone.now()
    if str(value).startswith('now-'):
        return timezone.now() - parse_relative(value[4:])
    parsed = parse_datetime(str(value))
    if parsed is None:
        raise InvalidQuery(f'Invalid {name} timestamp: {value!r}')
    return parsed if parsed.tzinfo else timezone.make_aware(parsed, timezone.utc)


def encode_cursor(sort_values):
    return base64.urlsafe_b64encode(json.dumps(sort_values).encode()).decode() if sort_values else None


def decode_cursor(cursor):
    if not cursor:
        return None
    try:
        values = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, binascii.Error):
        raise InvalidQuery('Invalid pagination cursor.') from None
    if not isinstance(values, list) or len(values) > 4 or not all(isinstance(v, (str, int, float)) for v in values):
        raise InvalidQuery('Invalid pagination cursor.')
    return values


@dataclass
class FieldFilter:
    field: str
    op: str
    value: object = None

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise InvalidQuery('Each field filter must be an object.')
        op = data.get('op', 'eq')
        if op not in OPERATORS:
            raise InvalidQuery(f'Unsupported operator {op!r}.')
        value = data.get('value')
        if op not in ('exists', 'missing'):
            if value is None or (isinstance(value, str) and len(value) > 512):
                raise InvalidQuery(f'Filter on {data.get("field")!r} needs a value (max 512 chars).')
            if not isinstance(value, (str, int, float, bool, list)):
                raise InvalidQuery('Filter values must be scalars or lists of scalars.')
        return cls(field=validate_field(data.get('field')), op=op, value=value)


@dataclass
class LogQuery:
    q: str = ''
    mode: str = 'simple'
    start: datetime = None
    end: datetime = None
    filters: dict = field(default_factory=dict)  # field -> [values]
    field_filters: list = field(default_factory=list)  # [FieldFilter]
    size: int = 100
    cursor: list = None
    order: str = 'desc'

    @classmethod
    def from_params(cls, params, *, max_size=500, default_range='1h'):
        """Build from request data (query params or JSON body)."""
        get = params.get
        q = (get('q') or '').strip()
        if len(q) > 2000:
            raise InvalidQuery('Query text is limited to 2000 characters.')
        mode = get('mode') or 'simple'
        if mode not in QUERY_MODES:
            raise InvalidQuery(f'Unknown query mode {mode!r}; use simple or lucene.')

        end = parse_time(get('end'), 'end') or timezone.now()
        start = parse_time(get('start'), 'start')
        if start is None:
            start = end - parse_relative(get('range') or default_range)
        if start >= end:
            raise InvalidQuery('start must be before end.')
        if end - start > MAX_RANGE:
            raise InvalidQuery('Time range is limited to 90 days.')

        filters = {}
        for param, es_field in STANDARD_FILTERS.items():
            raw = params.getlist(param) if hasattr(params, 'getlist') else get(param)
            values = raw if isinstance(raw, list) else ([raw] if raw else [])
            values = [str(v) for item in values for v in str(item).split(',') if v]
            if values:
                filters[es_field] = values[:50]

        raw_field_filters = get('field_filters') or []
        if isinstance(raw_field_filters, str):
            try:
                raw_field_filters = json.loads(raw_field_filters)
            except ValueError:
                raise InvalidQuery('field_filters must be a JSON list.') from None
        if not isinstance(raw_field_filters, list) or len(raw_field_filters) > 20:
            raise InvalidQuery('field_filters must be a list of at most 20 filters.')

        try:
            size = int(get('size') or 100)
        except (TypeError, ValueError):
            raise InvalidQuery('size must be an integer.') from None
        order = get('order') or 'desc'
        if order not in ('asc', 'desc'):
            raise InvalidQuery('order must be asc or desc.')

        return cls(
            q=q,
            mode=mode,
            start=start,
            end=end,
            filters=filters,
            field_filters=[FieldFilter.from_dict(f) for f in raw_field_filters],
            size=max(1, min(size, max_size)),
            cursor=decode_cursor(get('cursor')),
            order=order,
        )

    def describe(self):
        return {
            'q': self.q,
            'mode': self.mode,
            'start': self.start.isoformat(),
            'end': self.end.isoformat(),
            'filters': self.filters,
            'field_filters': [vars(f) for f in self.field_filters],
        }
