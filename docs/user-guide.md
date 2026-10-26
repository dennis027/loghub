# User guide

[README](../README.md) · [Architecture](architecture.md) · [User guide](user-guide.md) · [Operations](operations.md) · [Security](security.md) · [Development](development.md)

Day-to-day use of the portal: ingesting, searching, dashboards, alerting and administration.

## Ingest your first log

```bash
# 1. Unauthenticated collector HTTP input (localhost only by default):
curl -X POST localhost:9880 -H 'Content-Type: application/json' \
  -d '{"message":"hello from curl","level":"info","service":"my-app","environment":"dev"}'

# 2. Token-authenticated API (works from anywhere the portal is reachable):
#    Log Sources → Register source (type "Custom HTTP application") → Issue ingest token
curl -X POST http://localhost:4200/api/ingest/ -H 'Content-Type: application/json' \
  -H 'X-LogHub-Token: lh_...' -d '[{"message":"payment failed","level":"error","order":42}]'
```

Events are searchable within about 5 seconds: Fluent Bit flushes every 2 s and Elasticsearch refreshes every 2 s.

## Register log sources

**Log Sources → Register source** records name, type, environment, host, owner, routing and **attribution**. Attribution decides how indexed events are matched to the source: by service name (the default for collector-based types), by hostname or container, or by ingest token (custom HTTP). Each source has a **Set up** panel with ready-to-paste configurations for Docker, Fluent Bit (tail), rsyslog, Django, Node.js, Go, Kubernetes and HTTP. More samples live in [examples/](../examples/).

Source **status** comes from what Elasticsearch has actually indexed, checked every 60 s. `active` means an event arrived within `stale_after_minutes`. `stale` means older events but nothing recent. `pending` means nothing has ever arrived.

Ingest tokens are stored only as SHA-256 hashes. The plaintext is shown once when issued or rotated, and is never embedded in setup snippets (`<INGEST_TOKEN>` placeholder). For provisioning scripts: `docker compose exec django-api python manage.py rotate_ingest_token <source-id>`.

## Search logs

**Log Explorer** supports:
- **Simple** syntax (forgiving): `timeout -healthcheck "payment failed" | declined`, `pay*`
- **Lucene** syntax (as in Kibana's Lucene mode): `level:error AND service:checkout-api AND http.status:>=500`
- filters for level, service, environment, host, container, source and collector, plus arbitrary **field filters** (`=, ≠, contains, >, ≥, <, ≤, exists, missing`)
- an engine switch between **Elasticsearch** and **Graylog**. Every result states which engine ran it ("Executed by LogHub API → Elasticsearch") and links to the same query in Kibana Discover or Graylog.
- cursor pagination (`search_after`), a histogram, expandable details, raw JSON, copy, surrounding events (±2 min) and related events by `trace_id`
- saved searches (shared or private), and CSV/JSON export (analyst role and up, capped at 10,000 rows, audited)

**Live Logs** streams newly indexed events over Server-Sent Events. The server runs one query every 2 s per connection, about 3 s behind real time so late index refreshes aren't skipped. Streams reconnect automatically and resume from the last event id. Each user can hold at most 3 concurrent streams.

**Kibana**: the `LogHub logs` data view (`logs-loghub-*`) is created at startup. Use Discover for ad-hoc analysis.
**Graylog**: events routed to Graylog land in the *All messages* stream. Search them in Graylog, or in LogHub with engine = Graylog.

## Dashboards

- **LogHub dashboards** (Dashboards page) render live aggregations and PromQL panels. Eight built-ins are seeded: application errors, API activity, authentication, web access, database, Docker, infrastructure and security. Editors can create, edit, duplicate, move to folders and delete them. Widget types are stat, time series, bar, donut, table and log list.
- **Grafana** has three provisioned dashboards in the *LogHub* folder: Log Overview, Web & API Traffic, Infrastructure. Add your own in Grafana. Provisioned ones are read-only and versioned in [observability/grafana/dashboards](../observability/grafana/dashboards).

## Alerts and notifications

**Alert Rules** cover operational conditions and **Detection Rules** cover security. Both come from the same engine, and both offer templates.

| Rule type | Fires when | Example template |
|---|---|---|
| `threshold` | count of matching events in the window crosses a threshold | Critical errors > 0 in 5 min; auth failures ≥ 10 in 5 min; SQL-injection patterns |
| `spike` | count ≥ *factor* × the previous window, and ≥ *minimum* | HTTP 5xx tripled |
| `absence` | no matching events in the window (an app or source went silent) | Application stopped sending logs |
| `storage` | Elasticsearch disk usage % crosses a threshold | Disk > 85 % |

Celery beat evaluates due rules every 30 s, honoring each rule's interval. **Deduplication:** a rule has at most one open event, and later evaluations increment `occurrences` instead of notifying again. When the condition clears, the event auto-resolves and sends a resolved notice. A **cooldown** suppresses re-firing for N minutes after a resolution. Analysts and above can acknowledge or resolve events.

**Channels:** email (SMTP; Mailpit in development) and webhooks (JSON body, optional `X-LogHub-Signature: sha256=<HMAC>`). Deliveries are retried up to 4 times with exponential backoff, and each attempt is recorded. Webhooks to private or loopback addresses are blocked unless `WEBHOOK_ALLOW_PRIVATE_NETWORKS=true`. To add a channel type, subclass `ChannelBackend` in [backend/notifications/backends.py](../backend/notifications/backends.py).

## Retention

**Retention Policies** edits the `loghub-logs` ILM policy: rollover after N days, delete N days after rollover. The default is 1 + 14 days. The policy is cluster-wide (every organization's data stream uses it), so only platform administrators (`is_staff` plus the admin role) can change it. Graylog retention is configured per index set in Graylog. Celery purges LogHub's own metadata on a schedule: audit events after `AUDIT_RETENTION_DAYS` (365) and resolved alerts and deliveries after `ALERT_EVENT_RETENTION_DAYS` (90).

## Reports

Available reports: log volume trend, application error trend, top error services, source availability, alert history, storage, security summary. Each can be viewed in the portal or downloaded as CSV or PDF (analyst role and up; audited).

## Appearance

LogHub opens in dark mode. Switch to light with the sun/moon button in the top bar or under **System Settings → Appearance**. The choice is saved per browser and is never taken from the OS setting.

## Users, roles and organizations

| Role | Can |
|---|---|
| viewer | read dashboards and alerts, search logs (`user`, `client_ip` and raw payloads masked) |
| analyst | + export, saved searches, acknowledge/resolve alerts, see personal fields |
| editor | + manage sources, rules, dashboards |
| admin | + users, teams, notification channels, audit log, organization settings |

**Multi-tenancy:** every user belongs to one organization, and every API object is scoped to it. Each organization's logs live in their own data stream (`logs-loghub-<org>`), and every query also filters on `organization`, which user queries cannot reference. Collector inputs (forward/HTTP/syslog/Beats) stamp `COLLECTOR_DEFAULT_ORG`, so one bundled collector serves one organization. Additional tenants send through token-authenticated `/api/ingest/` or their own collector. Create organizations in `/django-admin/`.

## API

OpenAPI schema at `/api/schema/` and Swagger UI at `/api/docs/`. Authenticate with `POST /api/auth/login/` (JWT pair, 30-min access token), refresh with `/api/auth/refresh/` (rotating, blacklisted on logout). Errors use one envelope: `{"error": {"code", "message", "details"}}`. Main resources: `/api/logs/{search,aggregate,export,live,events/<id>,fields/<f>/values}`, `/api/log-sources`, `/api/collectors`, `/api/saved-searches`, `/api/dashboards`, `/api/alert-rules`, `/api/alert-events`, `/api/notification-channels`, `/api/retention-policies`, `/api/integrations`, `/api/pipelines/status`, `/api/stats/overview`, `/api/services`, `/api/infrastructure`, `/api/reports/<key>`, `/api/audit-events`, `/api/users`, `/api/teams`, `/api/organization`.
