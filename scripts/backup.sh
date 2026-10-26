#!/usr/bin/env bash
# Back up LogHub state into ./backups/<timestamp>/
#   - PostgreSQL (users, sources, rules, dashboards, audit) as a pg_dump
#   - Elasticsearch log data streams as a native snapshot (repository "loghub_backup")
#   - Grafana and Graylog volumes as tarballs (Graylog: MongoDB config + OpenSearch data)
# Usage: ./scripts/backup.sh [--skip-graylog]
set -euo pipefail
cd "$(dirname "$0")/.."
# Load only the variables this script needs from .env.
# shellcheck source=/dev/null
source <(grep -E '^(POSTGRES_USER|POSTGRES_DB|ELASTIC_PASSWORD)=' .env)

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="backups/$STAMP"
mkdir -p "$OUT"
es() { docker compose exec -T elasticsearch curl -fsS -u "elastic:$ELASTIC_PASSWORD" -H 'Content-Type: application/json' "$@"; }

echo "==> PostgreSQL"
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists | gzip > "$OUT/postgres.sql.gz"

echo "==> Elasticsearch snapshot"
# A fresh named volume is root-owned; Elasticsearch runs as uid 1000.
docker run --rm -v loghub_elasticsearch_snapshots:/snap alpine:3.20 chown 1000:0 /snap
es -X PUT "http://localhost:9200/_snapshot/loghub_backup" \
   -d '{"type":"fs","settings":{"location":"/usr/share/elasticsearch/snapshots","compress":true}}' >/dev/null
es -X PUT "http://localhost:9200/_snapshot/loghub_backup/loghub-${STAMP,,}?wait_for_completion=true" \
   -d '{"indices":"logs-loghub-*","include_global_state":false}' \
  | python3 -c 'import sys,json; s=json.load(sys.stdin)["snapshot"]; print("   ", s["snapshot"], s["state"], s["shards"])'
echo "loghub-${STAMP,,}" > "$OUT/elasticsearch-snapshot.txt"
# Copy the snapshot repository off the volume so the backup directory is self-contained.
docker run --rm -v loghub_elasticsearch_snapshots:/snap:ro -v "$PWD/$OUT":/out alpine:3.20 \
  tar czf /out/elasticsearch-snapshots.tar.gz -C /snap .

echo "==> Grafana"
docker run --rm -v loghub_grafana_data:/data:ro -v "$PWD/$OUT":/out alpine:3.20 tar czf /out/grafana.tar.gz -C /data .

if [[ "${1:-}" != "--skip-graylog" ]] && docker volume inspect loghub_mongo_data >/dev/null 2>&1; then
  echo "==> Graylog (stopping graylog/mongodb/opensearch briefly for a consistent copy)"
  docker compose stop graylog mongodb opensearch >/dev/null
  for v in mongo_data opensearch_data graylog_data; do
    docker run --rm -v "loghub_$v":/data:ro -v "$PWD/$OUT":/out alpine:3.20 tar czf "/out/$v.tar.gz" -C /data .
  done
  docker compose start mongodb opensearch graylog >/dev/null
fi

docker run --rm -v "$PWD/$OUT":/out alpine:3.20 chown -R "$(id -u):$(id -g)" /out
cp .env "$OUT/env.backup" && chmod 600 "$OUT/env.backup"
echo "Backup written to $OUT ($(du -sh "$OUT" | cut -f1)). It contains secrets (env.backup): store it encrypted."
