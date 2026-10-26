"""Synthetic log generator for demos.

Every event carries "demo": true and the tag "synthetic" so it can never be
mistaken for production data (the UI shows a "demo" badge). Events are posted
to the Fluent Bit HTTP collector input, i.e. through the real pipeline.

    python demo/generate_logs.py --rate 5            # continuous
    python demo/generate_logs.py --burst 200 --once  # one batch, e.g. to trigger alerts
"""

import argparse
import json
import os
import random
import sys
import time
import urllib.request
import uuid
from datetime import UTC, datetime

SERVICES = {
    'checkout-api': {'env': 'production', 'hosts': ['web-01', 'web-02'], 'kind': 'api'},
    'payments': {'env': 'production', 'hosts': ['pay-01'], 'kind': 'worker'},
    'auth-service': {'env': 'production', 'hosts': ['auth-01'], 'kind': 'auth'},
    'inventory': {'env': 'staging', 'hosts': ['stg-01'], 'kind': 'api'},
    'nginx-edge': {'env': 'production', 'hosts': ['edge-01'], 'kind': 'nginx'},
    'orders-db': {'env': 'production', 'hosts': ['db-01'], 'kind': 'postgres'},
}
PATHS = ['/api/cart', '/api/checkout', '/api/products', '/api/orders/{id}', '/healthz', '/api/search', '/login']
USERS = ['alice', 'bob', 'carol', 'dave', 'erin', 'frank']
ERRORS = [
    ('error', 'TimeoutError: upstream payments-gateway did not respond within 5000ms'),
    ('error', 'psycopg.OperationalError: connection to server at "db-01" failed: too many connections'),
    ('warning', 'Retrying request to inventory (attempt 2/3)'),
    ('critical', "Unhandled exception in worker: KeyError: 'currency'"),
    ('error', 'Payment declined by processor: insufficient_funds'),
]
SUSPICIOUS = [
    '/.env',
    '/wp-admin/install.php',
    "/api/products?id=1' or 1=1--",
    '/.git/config',
    '/api/search?q=1 union select password from users',
]


def now():
    return datetime.now(UTC).isoformat()


def base(service):
    meta = SERVICES[service]
    return {
        'timestamp': now(),
        'service': service,
        'environment': meta['env'],
        'hostname': random.choice(meta['hosts']),
        'demo': True,
        'tags': ['synthetic'],
        'trace_id': uuid.uuid4().hex[:16],
    }


def api_event(service, error_bias=0.0):
    path = random.choice(PATHS).replace('{id}', str(random.randint(1000, 9999)))
    roll = random.random()
    status = 500 + random.choice([0, 2, 3]) if roll < 0.03 + error_bias else (404 if roll < 0.08 else 200)
    duration = round(random.lognormvariate(3.6, 0.6) * (4 if status >= 500 else 1), 1)
    level = 'error' if status >= 500 else ('warning' if status >= 400 else 'info')
    method = random.choice(['GET', 'GET', 'GET', 'POST', 'PUT'])
    return {
        **base(service),
        'level': level,
        'message': f'{method} {path} {status} {duration}ms',
        'event_type': 'http_access',
        'user': random.choice(USERS),
        'http': {'method': method, 'path': path.split('?')[0], 'status': status, 'duration_ms': duration},
    }


def auth_event(fail_bias=0.0):
    user = random.choice(USERS + ['admin', 'root'])
    ip = f'203.0.113.{random.randint(1, 254)}'
    if random.random() < 0.15 + fail_bias:
        return {
            **base('auth-service'),
            'level': 'warning',
            'event_type': 'auth_failure',
            'user': user,
            'client_ip': ip,
            'message': f'Login failed for user {user} from {ip}: invalid credentials',
        }
    return {
        **base('auth-service'),
        'level': 'info',
        'event_type': 'auth_success',
        'user': user,
        'client_ip': ip,
        'message': f'User {user} signed in from {ip}',
    }


def nginx_event():
    ip = f'198.51.100.{random.randint(1, 254)}'
    path = random.choice(SUSPICIOUS) if random.random() < 0.02 else random.choice(PATHS).replace('{id}', '42')
    status = 404 if path in SUSPICIOUS else random.choice([200, 200, 200, 304, 499])
    ts = datetime.now(UTC).strftime('%d/%b/%Y:%H:%M:%S +0000')
    line = f'{ip} - - [{ts}] "GET {path} HTTP/1.1" {status} {random.randint(200, 9000)} "-" "Mozilla/5.0 (demo)"'
    return {
        **base('nginx-edge'),
        'message': line,
        'source_type': 'nginx',
        **({'event_type': 'suspicious_request'} if path in SUSPICIOUS else {}),
    }


def worker_event(error_bias=0.0):
    if random.random() < 0.05 + error_bias:
        level, msg = random.choice(ERRORS)
        return {
            **base('payments'),
            'level': level,
            'message': msg,
            'logger': 'payments.worker',
            'error': {'type': msg.split(':')[0]},
        }
    return {
        **base('payments'),
        'level': random.choice(['info', 'info', 'debug']),
        'logger': 'payments.worker',
        'message': f'Processed payment batch of {random.randint(1, 40)} transactions',
    }


def db_event():
    if random.random() < 0.04:
        return {
            **base('orders-db'),
            'level': 'warning',
            'source_type': 'postgres',
            'message': f'duration: {random.randint(1200, 9000)} ms  statement: SELECT * FROM orders WHERE status = $1',
        }
    return {
        **base('orders-db'),
        'level': 'info',
        'source_type': 'postgres',
        'message': 'checkpoint complete: wrote 312 buffers',
    }


def make(error_bias=0.0):
    kind = random.choices(['api', 'auth', 'nginx', 'worker', 'db'], weights=[45, 15, 20, 15, 5])[0]
    if kind == 'api':
        return api_event(random.choice(['checkout-api', 'inventory']), error_bias)
    if kind == 'auth':
        return auth_event(error_bias)
    if kind == 'nginx':
        return nginx_event()
    if kind == 'worker':
        return worker_event(error_bias)
    return db_event()


def send(url, events):
    req = urllib.request.Request(
        url, data=json.dumps(events).encode(), method='POST', headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return resp.status


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--url', default=os.environ.get('FLUENT_BIT_HTTP_URL', 'http://localhost:9880'))
    parser.add_argument('--rate', type=float, default=5, help='events per second (continuous mode)')
    parser.add_argument('--burst', type=int, default=0, help='send N events at once')
    parser.add_argument('--error-bias', type=float, default=0.0, help='0..1 extra error/auth-failure probability')
    parser.add_argument('--once', action='store_true')
    args = parser.parse_args()

    if args.burst:
        events = [make(args.error_bias) for _ in range(args.burst)]
        print(f'sent burst of {len(events)} demo events -> HTTP {send(args.url, events)}', flush=True)
        if args.once:
            return
    interval = 1.0
    print(f'generating ~{args.rate} demo events/s to {args.url} (Ctrl-C to stop)', flush=True)
    while True:
        # An incident every ~10 minutes keeps alert rules meaningful in long demos.
        bias = 0.6 if int(time.time() / 60) % 10 == 0 else args.error_bias
        batch = [make(bias) for _ in range(max(1, int(random.gauss(args.rate * interval, 1))))]
        try:
            send(args.url, batch)
        except OSError as exc:
            print(f'collector unavailable ({exc}); retrying', file=sys.stderr, flush=True)
            time.sleep(5)
        time.sleep(interval)


if __name__ == '__main__':
    main()
