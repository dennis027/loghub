"""Setup snippets per source type.

Tokens are never embedded: snippets reference <INGEST_TOKEN>, which the user
pastes from the one-time reveal (or reads from their secret store).
"""

from django.conf import settings


def _ctx(source):
    base = settings.PUBLIC_BASE_URL.rstrip('/')
    return {
        'name': source.name,
        'env': source.environment,
        'route': source.log_route,
        'ingest_url': f'{base}/api/ingest/',
        'collector': '<collector-host>',
        'match': source.effective_match_value,
        'source_key': source.source_key,
    }


def _http(c):
    return {
        'title': 'Send events over HTTPS (token authenticated)',
        'description': 'POST a JSON object or an array (max 1000 events, 5 MB). LogHub stamps organization, '
        'source and environment from the token; payload values for those are ignored.',
        'language': 'bash',
        'filename': 'send-log.sh',
        'content': f"""curl -X POST '{c['ingest_url']}' \\
  -H 'Content-Type: application/json' \\
  -H 'X-LogHub-Token: <INGEST_TOKEN>' \\
  -d '{{"message": "user signed in", "level": "info", "service": "{c['name']}", "user": "alice"}}'""",
    }


def _fluent_bit_tail(c, path, parser=None):
    parser_line = f'\n    Parser            {parser}' if parser else ''
    return {
        'title': 'Fluent Bit agent on the host (tail files)',
        'description': 'Install Fluent Bit 3.x on the host and forward to the LogHub collector. '
        f'Events are attributed to this source by {c["match"]!r}.',
        'language': 'ini',
        'filename': 'fluent-bit.conf',
        'content': f"""[INPUT]
    Name              tail
    Path              {path}
    Tag               host.{c['name']}{parser_line}
    DB                /var/lib/fluent-bit/{c['name']}.db
    Mem_Buf_Limit     16MB

[FILTER]
    Name    modify
    Match   host.*
    Set     service {c['name']}
    Set     environment {c['env']}
    Set     log_route {c['route']}

[OUTPUT]
    Name    forward
    Match   *
    Host    {c['collector']}
    Port    24224
    Retry_Limit 10""",
    }


def _docker(c):
    return {
        'title': 'Docker logging driver',
        'description': 'Point the container at the LogHub Fluent Bit forward input. fluentd-async keeps the '
        'container running if the collector is down; `docker logs` keeps working.',
        'language': 'yaml',
        'filename': 'docker-compose.yml',
        'content': f"""services:
  {c['name']}:
    image: your/image
    labels:
      com.docker.compose.service: {c['name']}
    logging:
      driver: fluentd
      options:
        fluentd-address: "{c['collector']}:24224"
        fluentd-async: "true"
        tag: "docker.{{{{.Name}}}}"
        labels: "com.docker.compose.service"
# Or for one container:
# docker run --log-driver fluentd --log-opt fluentd-address={c['collector']}:24224 \\
#   --log-opt fluentd-async=true --log-opt tag=docker.{c['name']} your/image""",
    }


def _syslog(c):
    return {
        'title': 'rsyslog forwarding',
        'description': 'Forward syslog (RFC 3164/5424) to the collector on port 5140 (UDP or TCP).',
        'language': 'bash',
        'filename': '/etc/rsyslog.d/60-loghub.conf',
        'content': f"""# TCP (@@) is reliable; use a single @ for UDP.
*.* @@{c['collector']}:5140
# then: sudo systemctl restart rsyslog
# Network devices: set the syslog server to {c['collector']} port 5140.""",
    }


def _django(c):
    return {
        'title': 'Django LOGGING (structured JSON to stdout)',
        'description': 'Emit one JSON object per line; ship stdout with the Docker driver or Fluent Bit. '
        'Logstash parses level/logger/message automatically.',
        'language': 'python',
        'filename': 'settings.py',
        'content': f"""import json, logging

class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({{
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname.lower(), "logger": record.name,
            "message": record.getMessage(), "service": "{c['name']}", "environment": "{c['env']}",
        }})

LOGGING = {{
    "version": 1, "disable_existing_loggers": False,
    "formatters": {{"json": {{"()": JsonFormatter}}}},
    "handlers": {{"stdout": {{"class": "logging.StreamHandler", "formatter": "json"}}}},
    "root": {{"handlers": ["stdout"], "level": "INFO"}},
}}
# Never log request bodies, passwords or Authorization headers.""",
    }


def _node(c):
    return {
        'title': 'Node.js with pino',
        'description': 'pino writes JSON lines; ship them with the Docker driver, or post batches to the '
        'HTTP ingest endpoint with the snippet below.',
        'language': 'javascript',
        'filename': 'logger.js',
        'content': f"""const pino = require('pino');
const logger = pino({{ base: {{ service: '{c['name']}', environment: '{c['env']}' }},
  redact: ['req.headers.authorization', '*.password'] }});
logger.info({{ user: 'alice' }}, 'user signed in');

// Direct HTTP (token from your secret store, never from the browser):
// await fetch('{c['ingest_url']}', {{ method: 'POST',
//   headers: {{ 'Content-Type': 'application/json', 'X-LogHub-Token': process.env.LOGHUB_TOKEN }},
//   body: JSON.stringify([{{ message: 'job done', level: 'info' }}]) }});""",
    }


def _go(c):
    return {
        'title': 'Go with log/slog',
        'description': 'slog.NewJSONHandler produces JSON lines that Logstash parses (level, msg, time).',
        'language': 'go',
        'filename': 'main.go',
        'content': f"""logger := slog.New(slog.NewJSONHandler(os.Stdout, nil)).With(
    "service", "{c['name']}", "environment", "{c['env']}")
logger.Info("order created", "order_id", 42)
logger.Error("payment failed", "error", err)""",
    }


def _kubernetes(c):
    return {
        'title': 'Kubernetes (Fluent Bit DaemonSet via Helm)',
        'description': 'Deploy the official chart and forward to the LogHub collector.',
        'language': 'yaml',
        'filename': 'values.yaml',
        'content': f"""# helm repo add fluent https://fluent.github.io/helm-charts
# helm install fluent-bit fluent/fluent-bit -f values.yaml
config:
  filters: |
    [FILTER]
        Name kubernetes
        Match kube.*
        Merge_Log On
    [FILTER]
        Name modify
        Match kube.*
        Set environment {c['env']}
        Set log_route {c['route']}
  outputs: |
    [OUTPUT]
        Name forward
        Match *
        Host {c['collector']}
        Port 24224""",
    }


def _graylog_note(c):
    return {
        'title': 'Routing',
        'description': {
            'elk': 'Events go to Elasticsearch through Logstash and are searchable in LogHub, Kibana and Grafana.',
            'graylog': 'Events go only to Graylog (GELF input). Search them with provider=graylog or in Graylog.',
            'both': 'Events are copied to Elasticsearch and Graylog. This doubles storage; use deliberately.',
        }[c['route']],
        'language': 'text',
        'filename': None,
        'content': f'log_route = {c["route"]}  (set on events as the "log_route" field, or via the source)',
    }


def instructions_for(source):
    c = _ctx(source)
    by_type = {
        'docker': [_docker(c)],
        'linux': [_fluent_bit_tail(c, '/var/log/syslog,/var/log/auth.log'), _syslog(c)],
        'nginx': [_fluent_bit_tail(c, '/var/log/nginx/access.log,/var/log/nginx/error.log')],
        'apache': [_fluent_bit_tail(c, '/var/log/apache2/*.log')],
        'django': [_django(c), _docker(c)],
        'node': [_node(c), _docker(c)],
        'go': [_go(c), _docker(c)],
        'postgres': [_fluent_bit_tail(c, '/var/log/postgresql/*.log')],
        'mysql': [_fluent_bit_tail(c, '/var/log/mysql/error.log,/var/log/mysql/mysql-slow.log')],
        'kubernetes': [_kubernetes(c)],
        'syslog': [_syslog(c)],
        'custom': [],
    }
    return by_type.get(source.source_type, []) + [_http(c), _graylog_note(c)]
