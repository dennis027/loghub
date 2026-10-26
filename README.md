# LogHub

**Centralized log management and observability platform.** LogHub collects logs from containers, servers, applications and network devices, then indexes, searches, visualizes and alerts on them from one access-controlled portal. It brings Elasticsearch, Logstash, Kibana, Grafana, Graylog, Fluent Bit and Prometheus together behind a Django REST API and an Angular console.

![Overview](docs/images/overview.png)

| | |
|---|---|
| ![Log Explorer](docs/images/log-explorer.png) | ![Dashboard](docs/images/dashboard.png) |

## Highlights

- **One pipeline, explicit routing.** Fluent Bit collects (Docker, HTTP, syslog, token API), masks secrets and routes each event to Elasticsearch, Graylog, or both. Nothing is duplicated by default.
- **Search that fits operations work.** Simple or Lucene queries, field filters, cursor pagination, surrounding events, trace correlation, saved searches, CSV/JSON export, and live tail over Server-Sent Events. Every result shows which engine ran it and links to Kibana or Graylog.
- **Alerting.** Threshold, spike, silence and disk-usage rules plus security detections, with deduplication, cooldowns, auto-resolve, and email/webhook delivery with retries.
- **Multi-tenant and auditable.** Per-organization data streams with enforced query filters, four roles, hashed show-once ingest tokens, PII masking for viewers, and an audit trail for every administrative action.
- **Operable.** Health checks on every service, a pipeline page backed by the Fluent Bit and Logstash monitoring APIs, a dead-letter replay pipeline, ILM retention, backup/restore scripts, and pinned image versions.

## Quick start

Requires Docker with Compose v2 and about **6 GB of RAM** for the full stack (about 3 GB without Graylog; see [operations](docs/operations.md#configuration)).

```bash
make env     # writes .env with random secrets and prints the admin password
make up      # first run pulls ~4 GB of images
make demo    # optional: synthetic, clearly labeled demo traffic
```

Open **http://localhost:4200** and sign in as `admin` (password: `DJANGO_SUPERUSER_PASSWORD` in `.env`).

| Service | URL | Login |
|---|---|---|
| LogHub portal | http://localhost:4200 | `admin` / `DJANGO_SUPERUSER_PASSWORD` |
| API docs | http://localhost:4200/api/docs/ | Bearer token from `/api/auth/login/` |
| Kibana | http://localhost:5601 | `elastic` / `ELASTIC_PASSWORD` |
| Grafana | http://localhost:3000 | `admin` / `GRAFANA_ADMIN_PASSWORD` |
| Graylog | http://localhost:9000 | `admin` / `GRAYLOG_ROOT_PASSWORD` |
| Mailpit (dev email) | http://localhost:8025 | – |

All ports bind to `127.0.0.1` by default. Send a first event with:

```bash
curl -X POST localhost:9880 -H 'Content-Type: application/json' \
  -d '{"message":"hello from curl","level":"info","service":"my-app"}'
```

## Architecture at a glance

```
 Docker · HTTP · syslog · token API ──► Fluent Bit ──┬─ elk ──► Logstash ──► Elasticsearch ◄── Kibana · Grafana
                (mask secrets, enforce tenant, route) └─ graylog ─► Graylog ─► OpenSearch + MongoDB
                                                              ▲
             Angular portal ──► Django API (Postgres, Redis) ─┤ search · aggregations · live tail
                                Celery: alert rules, source status, health, retention ─► email / webhooks
```

Details, component responsibilities and design decisions are in **[docs/architecture.md](docs/architecture.md)**.

## Documentation

| Doc | For |
|---|---|
| [Architecture](docs/architecture.md) | Data flow, component ownership, event schema, design decisions, delivery semantics, known limitations |
| [User guide](docs/user-guide.md) | Ingesting, registering sources, searching, dashboards, alerts, retention, reports, roles, API |
| [Operations](docs/operations.md) | Configuration, resource sizing, backup/restore, scheduled jobs, troubleshooting, production deployment |
| [Security](docs/security.md) | Credentials and least privilege, network exposure, masking, query safety, hardening checklist |
| [Development](docs/development.md) | Workflow, quality gates, conventions, extension points, repository layout |

## Development

```bash
make help     # all tasks
make check    # lint (Ruff, angular-eslint) + backend and frontend unit tests, as CI runs them
make test-integration   # end-to-end through the running pipeline
```

| | |
|---|---|
| Backend | Python 3.12, Django 5.1, DRF, Celery, PostgreSQL 16, Redis 7 |
| Frontend | Angular 18 (standalone, signals), Angular Material, ECharts |
| Data plane | Elasticsearch/Logstash/Kibana 8.15.3, Fluent Bit 3.1.9, Grafana 11.2.2, Graylog 6.1.4 + OpenSearch 2.15.0 + MongoDB 7.0, Prometheus 2.54 |
| Quality | 97 backend unit tests + 2 end-to-end tests, 14 frontend tests, Ruff, angular-eslint (incl. accessibility), ShellCheck, GitHub Actions CI |
# loghub
