"""Structured JSON logging for a Django app shipped to LogHub.

Add to settings.py. Logstash parses the JSON line (level, logger, message,
timestamp, any extra fields). Never log passwords, tokens or Authorization
headers; LogHub redacts common secret patterns at ingest, but that is a safety
net, not a substitute.
"""
import json
import logging


class JsonFormatter(logging.Formatter):
    def __init__(self, service='my-django-app', environment='production'):
        super().__init__()
        self.service, self.environment = service, environment

    def format(self, record):
        payload = {
            'timestamp': self.formatTime(record, '%Y-%m-%dT%H:%M:%S%z'),
            'level': record.levelname.lower(),
            'logger': record.name,
            'message': record.getMessage(),
            'service': self.service,
            'environment': self.environment,
        }
        for key in ('user', 'trace_id', 'event_type', 'http'):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload['error'] = {'type': record.exc_info[0].__name__, 'stack_trace': self.formatException(record.exc_info)}
        return json.dumps(payload, default=str)


LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'json': {'()': JsonFormatter, 'service': 'my-django-app'}},
    'handlers': {'stdout': {'class': 'logging.StreamHandler', 'formatter': 'json'}},
    'root': {'handlers': ['stdout'], 'level': 'INFO'},
}

# Example: logger.warning('login failed', extra={'event_type': 'auth_failure', 'user': username})
