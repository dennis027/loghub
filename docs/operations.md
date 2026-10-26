# Operations

[README](../README.md) · [Architecture](architecture.md) · [User guide](user-guide.md) · [Operations](operations.md) · [Security](security.md) · [Development](development.md)

Configuration, resource requirements, backup/restore, troubleshooting and production deployment.

## Resource requirements

| | Minimum (all services) | Without Graylog (`COMPOSE_PROFILES=metrics`) |
|---|---|---|
| RAM available to Docker | **6 GB** (measured steady state ≈ 5.0 GB) | ≈ 3 GB |
| CPU | 2 cores (4 recommended) | 2 cores |
| Disk | 10 GB + log volume | 5 GB + log volume |
| Software | Docker 24+ with Compose v2.20+, bash, Linux/macOS (WSL2 on Windows) | |

On Linux hosts running production-sized Elasticsearch, also set `sysctl -w vm.max_map_count=262144`. The bundled single-node setup starts without it.

## Starting and stopping

```bash
./scripts/init-env.sh            # writes .env with random secrets; prints the admin password
docker compose up -d --build     # first start pulls ~4 GB of images and takes a few minutes
docker compose ps                # wait until services report (healthy)
```

Open **http://localhost:4200** and sign in as `admin` with the password `init-env.sh` printed (`DJANGO_SUPERUSER_PASSWORD` in `.env`).

On every start, the API container runs the database migrations (`python manage.py migrate`) and an idempotent bootstrap. The bootstrap creates the `default` organization, the administrator, the built-in dashboards, the managed collectors, the integration registry and the retention policy. To run them by hand:

```bash
docker compose exec django-api python manage.py migrate
docker compose exec django-api python manage.py bootstrap_platform
docker compose exec django-api python manage.py createsuperuser   # extra admins; then set organization/role in /django-admin/
```

```bash
docker compose stop           # keep containers
docker compose down           # remove containers, keep data volumes
docker compose down -v        # also DELETE all data (logs, database, dashboards)
```

## Configuration

All configuration lives in `.env` (template: [.env.example](../.env.example)). Notable settings:

| Variable | Purpose |
|---|---|
| `COMPOSE_PROFILES` | `graylog,metrics` by default. Remove `graylog` to save ~2 GB. Add `demo` for the generator. |
| `BIND_ADDRESS` / `INGEST_BIND_ADDRESS` | Interfaces for UI and ingestion ports (default `127.0.0.1`) |
| `ES_JAVA_OPTS`, `LS_JAVA_OPTS`, `OPENSEARCH_JAVA_OPTS`, `GRAYLOG_JAVA_OPTS` | JVM heaps (768m / 384m / 512m / 512m) |
| `COLLECTOR_DEFAULT_ORG` | Organization for events from collector inputs |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | SMTP relay (defaults to Mailpit) |
| `*_PUBLIC_URL`, `PUBLIC_BASE_URL` | Browser-facing links (Kibana/Grafana/Graylog, alert emails) |
| `JWT_ACCESS_TOKEN_LIFETIME_MINUTES`, `JWT_REFRESH_TOKEN_LIFETIME_DAYS` | Session lifetime |
| `WEBHOOK_ALLOW_PRIVATE_NETWORKS`, `AUDIT_RETENTION_DAYS`, `ALERT_EVENT_RETENTION_DAYS` | Policy knobs |

Pinned images: Elasticsearch/Logstash/Kibana 8.15.3, Grafana 11.2.2, Fluent Bit 3.1.9, Graylog 6.1.4, OpenSearch 2.15.0, MongoDB 7.0.14, PostgreSQL 16.4, Redis 7.2.5, Prometheus 2.54.1, node-exporter 1.8.2, Mailpit 1.20.5, Python 3.12.7, Node 22.11.0, nginx 1.27.2.

## Backup

```bash
./scripts/backup.sh               # PostgreSQL dump, Elasticsearch snapshot, Grafana and Graylog volumes, .env copy
./scripts/backup.sh --skip-graylog
```

The result is `backups/<timestamp>/`. It includes a copy of `.env` with secrets, so store it encrypted. Elasticsearch uses native snapshots (repository `loghub_backup` on the `elasticsearch_snapshots` volume). Backing up Graylog stops Graylog, MongoDB and OpenSearch for a few seconds to get consistent volume copies.

## Restore

```bash
docker compose up -d
./scripts/restore.sh backups/<timestamp>                # asks you to type "restore"
./scripts/restore.sh backups/<timestamp> --with-graylog
```

The restore replaces the PostgreSQL contents and the `logs-loghub-*` data streams. Logstash is paused during the restore while Fluent Bit buffers incoming events to disk.

## Scheduled jobs (Celery beat)

| Every | Job |
|---|---|
| 30 s | evaluate due alert rules |
| 60 s | source status from the index; integration health; collector health |
| 6 h | purge old audit and alert metadata |

## Troubleshooting

| Symptom | Check / fix |
|---|---|
| `setup` exits non-zero | `docker compose logs setup`. Usually Elasticsearch isn't healthy yet, or `.env` passwords changed after the first start. The `elastic` password is fixed at first boot of the volume, so restore the old `.env` or reset with `docker compose down -v`. |
| Elasticsearch restarts or exits 137 | Out of memory: give Docker more RAM, lower `ES_JAVA_OPTS`, or disable the `graylog` profile. On larger heaps set `vm.max_map_count=262144`. |
| Kibana "server is not ready yet" | It waits for `kibana_system`'s password, which `setup` sets. Check `docker compose logs kibana setup`. |
| No events in LogHub | Check **Log Pipelines**: is Fluent Bit receiving (input records)? Is Logstash's events-out increasing? Then `docker compose logs fluent-bit logstash`. Events from collector inputs go to `COLLECTOR_DEFAULT_ORG`; make sure your user belongs to that organization. |
| Source stays `pending` | Its attribution doesn't match any events. Compare `match_field=match_value` on the source with real event fields in the Log Explorer. |
| Ingest API returns 503 | The collector is down. The response carries `Retry-After: 10`; clients should retry with backoff. |
| Alerts never fire | Is the rule enabled, and does Celery beat run (`docker compose logs celery-beat`)? Use **Dry run** on the rule. Is `last_error` set? |
| No email | Development mail goes to Mailpit (http://localhost:8025). See the per-channel delivery history on the alert event, and test the channel from Alerts → Notification channels. |
| Graylog health "degraded" | `graylog-setup` creates the `loghub_reader` user: `docker compose logs graylog-setup`, and re-run it with `docker compose up graylog-setup`. |
| Graylog route events missing | Graylog not running (profile disabled): Fluent Bit retries 5 times, then drops them. Check the `to_graylog` output on Log Pipelines. |
| DLQ size > 0 | Elasticsearch rejected documents, usually a field type conflict. The `dlq` pipeline replays them automatically; search `tags:dlq_replayed` and read `dlq_reason` to fix the producer. A degraded Logstash means the replay pipeline is not running: check `docker compose logs logstash`. |
| Live Logs reconnecting | Each stream lasts 5 min, then reconnects (normal). A 429 means more than 3 streams are open for one user. |
| Portal shows unstyled page | A reverse proxy is stripping or altering the CSP or assets. Serve the frontend container unchanged. |

Useful commands: `docker compose ps`, `docker compose logs -f <service>`, `docker stats`, `curl -u elastic:$ELASTIC_PASSWORD localhost:9200/_cat/indices/.ds-logs-loghub-*?v`.

## Production deployment

Use the base file only: `docker compose -f docker-compose.yml up -d`. This skips the dev override.

1. **TLS and the edge.** Put a reverse proxy in front of the frontend container ([deploy/nginx/tls.conf.example](../deploy/nginx/tls.conf.example)). Then set `PUBLIC_BASE_URL`, `CSRF_TRUSTED_ORIGINS`, `ALLOWED_HOSTS`, `SECURE_COOKIES=true` and `SECURE_HSTS_SECONDS`. Keep Kibana, Grafana and Graylog behind SSO or a VPN.
2. **Internal TLS.** Enable `xpack.security.http.ssl` / `transport.ssl` with your CA, and switch the clients to `https://`: Logstash, Kibana, Grafana datasource, setup, and `ELASTICSEARCH_URL`.
3. **Ingestion exposure.** Set `INGEST_BIND_ADDRESS` only on hosts behind a firewall, and prefer `/api/ingest/` (token, HTTPS) for remote producers. Fluent Bit's forward input supports TLS (`tls on`, `tls.crt_file`, `tls.key_file`).
4. **SMTP.** Set `EMAIL_HOST/PORT/USER/PASSWORD/USE_TLS` and remove Mailpit.
5. **Scaling.**

   | Layer | How to scale |
   |---|---|
   | Elasticsearch | 3+ master-eligible data nodes with replicas ≥ 1 (`index.number_of_replicas` in the template); heap ≤ 50 % of RAM and ≤ 31 GB; dedicated SSD volumes; `vm.max_map_count=262144`. Size around 1.2–1.5× raw daily log volume × retention days. |
   | Logstash | Run several replicas behind the Fluent Bit output (`Upstream`). Tune `pipeline.workers` and the persisted queue size. |
   | Fluent Bit | One per host (DaemonSet on Kubernetes), forwarding to aggregator instances. |
   | API | Scale `django-api` replicas behind the proxy. Live tail holds a thread per stream (gthread: workers × threads), so size threads for concurrent viewers. |
   | Celery | Scale workers horizontally. Run **exactly one** `celery-beat`. |
   | PostgreSQL / Redis | Managed services, or HA deployments with backups. |
   | Graylog | Follow Graylog's multi-node guide (OpenSearch cluster, MongoDB replica set), or Graylog Data Node. |

6. **Retention.** Size `delete_after_days` from ingest volume and disk, and keep an Elasticsearch disk-usage alert (template provided).
7. **Backups.** Run `scripts/backup.sh` from cron, or point the snapshot repository at S3 (`repository-s3`), and test restores regularly.
8. **Monitoring LogHub itself.** Prometheus scrapes Fluent Bit. Add exporters for Elasticsearch and Postgres as needed. The API's structured logs are shipped and searchable as `service:django-api`.
