# Deploying to Render and GitHub Pages

[README](../README.md) · [Architecture](architecture.md) · [Operations](operations.md)

The API runs on Render and the Angular console runs on GitHub Pages.

| Piece | Host | Notes |
|---|---|---|
| Django API + Celery worker/beat | Render web service (Docker) | One container, started with `docker-entrypoint.sh render` |
| PostgreSQL | Render Postgres (free) | Free databases expire after 30 days; upgrade for anything you want to keep |
| Redis | Render Key Value (free) | Celery broker and cache |
| Angular console | GitHub Pages | Built by `.github/workflows/pages.yml` |
| Elasticsearch / Logstash / Fluent Bit / Graylog | **Not deployed** | Too large for Render's free tier. Point `ELASTICSEARCH_URL` at a hosted cluster to enable search. |

Without Elasticsearch the portal signs in and manages sources, rules, dashboards and users, but log search, aggregations and the dashboards' data show errors or empty results.

The free web service sleeps after 15 minutes idle, so the first request takes about a minute. Celery runs inside the web container, so alert evaluation also pauses while it sleeps.

## 1. Push the code to GitHub

```bash
git remote add origin https://github.com/<user>/<repo>.git
git push -u origin main
```

## 2. Deploy the API on Render

1. Render dashboard → **New → Blueprint**, pick the repository. Render reads [render.yaml](../render.yaml).
2. When prompted, fill the `sync: false` variables:
   - `CORS_ALLOWED_ORIGINS` = `https://<user>.github.io`
   - `CSRF_TRUSTED_ORIGINS` = `https://<user>.github.io`
   - `PUBLIC_BASE_URL` = `https://<user>.github.io/<repo>`
   - `ELASTICSEARCH_URL`, `ELASTICSEARCH_USERNAME`, `ELASTICSEARCH_PASSWORD`: optional, for a hosted cluster
3. After the first deploy, open the `loghub-api` service → **Environment** and copy `DJANGO_SUPERUSER_PASSWORD`. Sign in as `admin`.
4. Check `https://<service>.onrender.com/health/live` and `/api/docs/`.

## 3. Publish the console on GitHub Pages

1. Repository → **Settings → Pages → Source: GitHub Actions**.
2. **Settings → Secrets and variables → Actions → Variables**: add `LOGHUB_API_URL` = `https://<service>.onrender.com` (no trailing slash).
3. Push to `main`, or run **Deploy console to GitHub Pages** manually. The site appears at `https://<user>.github.io/<repo>/`.

The workflow builds with `--base-href /<repo>/`, writes the API URL into `config.js` at build time and copies `index.html` to `404.html` so deep links work.

## How it connects

The console calls the API cross-origin with a bearer token. `apiBaseInterceptor` prefixes `/api/...` requests with `window.LOGHUB_API_URL`, and the API allows the Pages origin through `CORS_ALLOWED_ORIGINS`. With `LOGHUB_API_URL` empty (docker compose), requests stay same-origin as before.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Browser console shows a CORS error | `CORS_ALLOWED_ORIGINS` must be the origin only (`https://<user>.github.io`), with no path or trailing slash |
| Login fails with a network error | `LOGHUB_API_URL` is wrong or empty, or the free service is still waking up |
| `DisallowedHost` | Add your hostname to `ALLOWED_HOSTS` |
| Search returns errors | `ELASTICSEARCH_*` is not set or the cluster is unreachable |
