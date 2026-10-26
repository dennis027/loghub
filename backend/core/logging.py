import json
import logging
from datetime import UTC, datetime

from .middleware import get_request_id

_RESERVED = set(vars(logging.LogRecord('', 0, '', 0, '', (), None))) | {'message', 'asctime', 'request_id'}


class RequestIdFilter(logging.Filter):
    def filter(self, record):
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line; Logstash parses these into structured fields."""

    def __init__(self, service='django-api', **kwargs):
        super().__init__(**kwargs)
        self.service = service

    def format(self, record):
        payload = {
            'timestamp': datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            'level': record.levelname.lower(),
            'logger': record.name,
            'message': record.getMessage(),
            'service': self.service,
        }
        if getattr(record, 'request_id', None):
            payload['request_id'] = record.request_id
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith('_'):
                payload[key] = value
        if record.exc_info:
            payload['error'] = {
                'type': record.exc_info[0].__name__,
                'stack_trace': self.formatException(record.exc_info),
            }
        return json.dumps(payload, default=str)
