# Development

[README](../README.md) · [Architecture](architecture.md) · [User guide](user-guide.md) · [Operations](operations.md) · [Security](security.md) · [Development](development.md)

Local workflow, quality gates, conventions, and how to extend the platform. The host needs only **Docker** and **make**. Python, Node and the linters all run in containers.

## Daily workflow

```bash
make env          # once: generate .env with random secrets
make up           # build + start (dev overrides: DEBUG, bind-mounted backend, API on :8000)
make demo         # optional synthetic traffic
make logs S=django-api
make check        # lint + unit tests (what CI runs)
```

`make help` lists every target. `docker-compose.override.yml` is applied automatically in development. It bind-mounts `backend/`, so after editing Python run `docker compose restart django-api celery-worker celery-beat`.

For Angular hot reload, run `cd frontend && npm ci && npm start` (port 4200, proxies `/api` to `:8000`). Stop the `frontend` container first, or change its port.

## Quality gates

| Gate | Command | Scope |
|---|---|---|
| Python lint | `make lint-backend` | Ruff: pyflakes, pycodestyle, isort, bugbear, pyupgrade, Django, bandit security rules; `ruff format --check` (config in `backend/pyproject.toml`) |
| TypeScript/template lint | `make lint-frontend` | angular-eslint recommended + **template accessibility** rules; TypeScript runs with `strict` and `strictTemplates` |
| Backend unit tests | `make test-backend` | 97 tests: auth and roles, tenant isolation, query builder and provider adapters, ingest, alert engine, notifications, reports, migrations, bootstrap |
| End-to-end | `make test-integration` | Real event through Fluent Bit, Logstash, Elasticsearch and the API adapters (needs the stack running) |
| Frontend unit tests | `make test-frontend` | Headless Chromium: auth/refresh flow, SSE parser, XSS-safe rendering, chart color rules |
| Migrations | `python manage.py makemigrations --check` | Also asserted by a unit test |
| Shell scripts | `shellcheck scripts/*.sh` | CI only |

CI ([.github/workflows/ci.yml](../.github/workflows/ci.yml)) runs the backend job against a real PostgreSQL service, then the frontend lint/build/test job, then Compose validation and ShellCheck. `make fmt` auto-fixes Python lint findings and formatting.

## Conventions

- **Backend layout:** one Django app per bounded context (`log_sources`, `search`, `alerts`, …). Views stay thin. Domain logic lives in `services.py` / `engine.py` / `providers/`, and periodic work in `tasks.py`.
- **Tenancy is not optional:** organization-owned models are served through `core.tenancy.OrganizationScopedMixin`, which filters by the caller's organization and audits writes. Log queries are built only by `search.providers.elasticsearch.build_query`, which always adds the organization filter.
- **Permissions:** declare `read_role` / `write_role` on a view and use `core.permissions.RoleRequired`. Cluster-wide settings use `IsPlatformAdmin`.
- **Errors:** raise DRF exceptions, or `core.exceptions.InvalidQuery` / `ProviderUnavailable`. The handler renders `{"error": {"code", "message", "details"}}`.
- **Logging:** use `logging.getLogger(__name__)` with structured `extra={...}`. Logs are JSON and are ingested by LogHub itself. Don't log secrets. Don't reuse the object-mapped field names `error` or `http` for plain strings (see the index template).
- **Frontend:** standalone components and signals. API access only through `core/api.service.ts`. Log content is rendered with interpolation only, never `innerHTML`. Chart colors come from `shared/charts.ts` (validated palette). Builders produce dark options; `<lh-chart>` maps them to the light palette when light mode is on, so new charts get both themes for free. Theme tokens live as CSS variables in `styles.scss` (`:root` dark, `[data-theme='light']` light).
- **Migrations:** create them with `make migrations` (files are owned by your user, not the container's).

## Extending

| To add… | Implement | Register in |
|---|---|---|
| A log search backend | `search.providers.base.LogProvider` (`search`, `health`, optional `aggregate`) | `search/providers/registry.py` |
| A health-checked integration | a function returning `HealthResult` | `integrations/providers.py:REGISTRY` |
| A notification channel | `notifications.backends.ChannelBackend` (`validate_config`, `send`) | `notifications/backends.py:BACKENDS` |
| An alert condition | a branch in `alerts.engine.evaluate` returning `Evaluation` | `AlertRule.RULE_TYPES` (+ migration) |
| A report | a generator returning `{title, columns, rows, summary}` | `reports/generators.py:REPORTS` |
| A built-in dashboard | a dict in `dashboards/templates.py` | seeded by `bootstrap_platform` |

## Repository layout

```
backend/        Django project
  config/         settings, URLs, Celery app
  core/           tenancy, permissions, errors, JSON logging, management commands
  accounts/ organizations/ audit/            identity, tenants, audit trail
  log_sources/    source registry, collectors, token ingest endpoint
  search/         query model, provider adapters (Elasticsearch, Graylog), SSE live tail
  alerts/ notifications/                     rule engine, delivery backends
  dashboards/ reports/ retention/ health/ integrations/
  demo/           synthetic log generator
  tests/          pytest suite (unit + integration)
frontend/       Angular 18 portal (core/, layout/, pages/, shared/)
observability/  Fluent Bit, Logstash pipelines, Grafana provisioning, Prometheus, setup bootstrap
scripts/        init-env, backup, restore
examples/       shipper configs (Fluent Bit agent, Docker logging, rsyslog, Django, Filebeat)
deploy/         TLS reverse-proxy example
docs/           this documentation
```
