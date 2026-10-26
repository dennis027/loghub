#!/usr/bin/env bash
# Restore a backup created by scripts/backup.sh.
# Usage: ./scripts/restore.sh backups/<timestamp> [--with-graylog]
# The stack must be running (docker compose up -d). Existing LogHub log data streams
# and the PostgreSQL schema are REPLACED by the backup's contents.
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="${1:?usage: restore.sh backups/<timestamp> [--with-graylog]}"
[[ -f "$DIR/postgres.sql.gz" ]] || { echo "not a backup directory: $DIR" >&2; exit 1; }
# Load only the variables this script needs from .env.
# shellcheck source=/dev/null
source <(grep -E '^(POSTGRES_USER|POSTGRES_DB|ELASTIC_PASSWORD)=' .env)
es() { docker compose exec -T elasticsearch curl -fsS -u "elastic:$ELASTIC_PASSWORD" -H 'Content-Type: application/json' "$@"; }

read -r -p "This replaces current LogHub data with $DIR. Type 'restore' to continue: " answer
[[ "$answer" == "restore" ]] || { echo "aborted"; exit 1; }

echo "==> PostgreSQL"
docker compose stop celery-beat celery-worker django-api >/dev/null
gunzip -c "$DIR/postgres.sql.gz" | docker compose exec -T postgres psql -q -U "$POSTGRES_USER" -d "$POSTGRES_DB" >/dev/null

echo "==> Elasticsearch"
SNAP="$(cat "$DIR/elasticsearch-snapshot.txt")"
docker compose stop logstash >/dev/null   # Fluent Bit buffers to disk meanwhile
docker run --rm -v loghub_elasticsearch_snapshots:/snap -v "$PWD/$DIR":/in:ro alpine:3.20 \
  sh -c 'tar xzf /in/elasticsearch-snapshots.tar.gz -C /snap && chown -R 1000:0 /snap'
es -X PUT "http://localhost:9200/_snapshot/loghub_backup" \
   -d '{"type":"fs","settings":{"location":"/usr/share/elasticsearch/snapshots","compress":true}}' >/dev/null
es -X DELETE "http://localhost:9200/_data_stream/logs-loghub-*" >/dev/null || true
es -X POST "http://localhost:9200/_snapshot/loghub_backup/$SNAP/_restore?wait_for_completion=true" \
   -d '{"indices":"logs-loghub-*","include_global_state":false}' >/dev/null
docker compose start logstash django-api celery-worker celery-beat >/dev/null

if [[ "${2:-}" == "--with-graylog" ]]; then
  echo "==> Graylog volumes"
  docker compose stop graylog mongodb opensearch >/dev/null
  for v in mongo_data opensearch_data graylog_data; do
    docker run --rm -v "loghub_$v":/data -v "$PWD/$DIR":/in:ro alpine:3.20 \
      sh -c "rm -rf /data/* && tar xzf /in/$v.tar.gz -C /data"
  done
  docker compose start mongodb opensearch graylog >/dev/null
fi
echo "Restore complete. Grafana dashboards are provisioned from the repository; grafana.tar.gz holds UI-made changes."
