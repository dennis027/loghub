# Architecture

[README](../README.md) · [Architecture](architecture.md) · [User guide](user-guide.md) · [Operations](operations.md) · [Security](security.md) · [Development](development.md)

How events flow through LogHub, which component owns what, and the delivery guarantees.

```
 Docker containers ──fluentd driver :24224─┐
 Apps (HTTP JSON) ──────────────── :9880 ──┤
 Syslog devices ────────── :5140 udp/tcp ──┼─► Fluent Bit ── normalize · enforce tenant · mask secrets
 Django /api/ingest (per-source token) ────┘        │        route by log_route
                                                    │
               ┌───── log_route = elk (default) / both ─────┐
               ▼                                            ▼  log_route = graylog / both
   Logstash :8080 (parse JSON, grok access logs,       Graylog GELF :12201
   normalize levels, mask, fingerprint)                     │
   Filebeat ──► :5044                                       ▼
               ▼                                     OpenSearch 2.15 + MongoDB 7
   Elasticsearch 8.15  (data stream                  (internal-only network)
   logs-loghub-<org>, ILM retention)
      ▲         ▲            ▲
   Kibana    Grafana    Django API ◄── Angular portal (nginx :4200, same-origin /api)
             ▲           ├─ search / aggregations / live tail (SSE) / exports
   Prometheus ◄ node-exporter, Fluent Bit metrics
                         └─ Celery worker + beat: alert evaluation, source status,
                            integration health, retention sync ─► email (SMTP / Mailpit) · webhooks
```

## Component responsibilities

| Component | Ingestion | Storage | Search | Visualization / alerting |
|---|---|---|---|---|
| **Fluent Bit 3.1** | Collects from Docker, HTTP, syslog; buffers to disk; routes per event | – | – | – |
| **Logstash 8.15** | Parses and enriches, then indexes with idempotent document ids | Persisted queue + dead-letter queue | – | – |
| **Elasticsearch 8.15** | – | **Primary log store**, one data stream per organization | Backend for LogHub search, Kibana, Grafana, alerts | – |
| **Kibana 8.15** | – | – | Ad-hoc exploration (Discover, `LogHub logs` data view) | Kibana dashboards |
| **Grafana 11.2** | – | – | – | Provisioned dashboards over logs (ES) and metrics (Prometheus) |
| **Graylog 6.1** (optional) | Own GELF inputs | Own OpenSearch + MongoDB | Graylog UI, and LogHub search with `provider=graylog` | Graylog streams |
| **Django API** | Token-authenticated `/api/ingest/` | PostgreSQL holds **metadata only** (users, sources, rules, dashboards, audit), never log payloads | Provider adapters (Elasticsearch, Graylog) with tenant enforcement | Alert engine (Celery), reports, notifications |
| **Angular portal** | – | – | Log Explorer, Live Logs | Overview, dashboards, alerts, admin |

**Why Graylog has separate storage:** Graylog 6.1 supports OpenSearch 1.1–2.15 and MongoDB 5.0.7–7.x. It does **not** support Elasticsearch 8, so it cannot share the ELK cluster. It runs on its own OpenSearch and MongoDB, on a Docker network marked `internal: true`.

**No duplicate ingestion by default.** Every event carries `log_route`: `elk` (the default), `graylog`, or `both`. Fluent Bit's `rewrite_tag` filter sends `graylog` events only to Graylog. `both` copies the event to both stores, which doubles storage, so it is an explicit per-source opt-in. Nothing forwards from one store to another, so forwarding loops can't happen. The ingestion stack's own containers (Fluent Bit, Logstash, Elasticsearch) log to `json-file`, never into the pipeline.

## Normalized event fields

`@timestamp`, `message`, `level` (`debug|info|warning|error|critical`), `service`, `environment`, `hostname`, `container`, `organization`, `source_id`, `source_type`, `collector`, `log_route`, `event_type` (e.g. `http_access`, `auth_failure`), `logger`, `user`, `client_ip`, `trace_id`, `http.{method,path,status,duration_ms,bytes,user_agent}`, `error.{type,stack_trace}`, `fingerprint`, `ingested_at`, `demo`. Any other field is indexed as a keyword. See [observability/setup/index-template.json](../observability/setup/index-template.json).

## Key design decisions

| Decision | Why | Trade-off |
|---|---|---|
| Elasticsearch is the primary store; Graylog is opt-in per source | One search/alerting path, no duplicate storage by default | Graylog-only events aren't covered by LogHub aggregations or alerts |
| Graylog runs on its own OpenSearch + MongoDB | Graylog 6.1 doesn't support Elasticsearch 8 | Extra ~2 GB RAM, so it sits behind a Compose profile |
| Routing and secret masking happen in Fluent Bit | One enforcement point covers both stores | Lua filter to maintain, unit-tested through the integration test |
| One data stream per organization, plus a mandatory `organization` filter | Defense in depth: index-level and query-level isolation | Retention (ILM) is shared across tenants |
| Fingerprint as the document id (`create`) | Retries become idempotent (409) without a dedup service | Identical lines in the same microsecond from one source collapse into one event |
| Django orchestrates; Elasticsearch, Kibana and Grafana do the heavy lifting | No re-implementing search or dashboards in the API | Kibana and Grafana are linked, not embedded |
| Live tail polls Elasticsearch over SSE | Works through any HTTP proxy; uses the same tenant-safe query path | About 3 s latency, one query every 2 s per viewer |
| Hashed, show-once ingest tokens | A database leak doesn't expose ingest credentials | Lost tokens must be rotated |
| Alert engine in Celery rather than ES Watcher or Grafana alerting | Works on the free tier, tenant-aware, audited, and testable in pytest | Evaluation granularity is about 30 s |

## Reliability and delivery semantics

**Delivery is at-least-once, not exactly-once.**
- **Fluent Bit** buffers every input to disk (`/var/fluent-bit` volume, 1 GB cap toward Logstash) and retries outputs up to 10 times with backoff. Docker's fluentd driver runs in async mode, so applications keep running when the collector is down.
- **Logstash** uses a 512 MB persisted queue (backpressure toward Fluent Bit) and a **dead-letter queue** for documents Elasticsearch rejects (for example mapping conflicts). A second pipeline, `dlq`, replays them automatically: it coerces object-mapped fields that arrived as plain values (`error`, `http`), re-indexes the event with tag `dlq_replayed` and the original `dlq_reason`, and deletes consumed segments. The replay pipeline has no DLQ of its own, so it can't loop. Log Pipelines shows how many events were replayed.
- **Duplicates:** each event's document id is a SHA-256 fingerprint of timestamp, message, service, host, container, source and an optional client `event_id`. A retried batch therefore collides (HTTP 409) instead of creating duplicates. This holds within one backing index (rollovers happen daily). Truly identical lines emitted within the same microsecond by the same source are treated as one event. Send a unique `event_id` if that matters to you.
- **Celery tasks** use `acks_late` with a 90 s soft / 120 s hard time limit. Notification delivery is bounded at 4 attempts. Alert evaluation takes a per-rule lock so evaluations never overlap.
- **Graceful degradation:** when Elasticsearch, Graylog or Prometheus is down, API calls return a `503 provider_unavailable` with a clear message. The Overview hides log metrics instead of estimating them, and integration health is polled every 60 s.

## Known limitations

- **One collector, one tenant.** The bundled Fluent Bit stamps a single organization (`COLLECTOR_DEFAULT_ORG`). Other tenants use token ingestion or their own collector.
- **Graylog is search-and-health only from LogHub.** Inputs, the reader user and routing are provisioned automatically. LogHub lists inputs and streams, and searches through Graylog's REST API (`/api/search/universal/absolute`, deprecated by Graylog in favor of the Views API but still supported in 6.1). Stream rules, pipelines and index-set retention are managed in Graylog's UI. Aggregations, histograms, exports and alerts run on Elasticsearch only.
- **Retention is cluster-wide** (one ILM policy for every organization's data stream).
- **Kibana and Grafana are linked, not embedded.** Embedding would need anonymous or proxy authentication that bypasses their access control. Deep links open the same query or dashboard.
- **Infrastructure metrics** cover the Docker host via node-exporter. Network counters are omitted because the exporter container doesn't share the host network namespace. Run node-exporter with `network_mode: host` if you need them.
- **Live tail** polls Elasticsearch (one query every 2 s per stream, about 3 s behind real time). That suits interactive use, but it isn't a high-fanout streaming bus.
- The **"Integration" model** is platform-level. Organizations share the integrated products, and tenant isolation is enforced in the LogHub API.
