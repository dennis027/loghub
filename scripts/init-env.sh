#!/usr/bin/env bash
# Generate a .env file with random secrets from .env.example.
# Usage: ./scripts/init-env.sh [--force]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
EXAMPLE="$ROOT/.env.example"

if [[ -f "$ENV_FILE" && "${1:-}" != "--force" ]]; then
  echo ".env already exists; pass --force to regenerate (this rotates every secret)." >&2
  exit 1
fi

# Reads fixed-size chunks (no SIGPIPE from an endless pipe under pipefail).
rand() {
  local len="${1:-32}" out=""
  while [[ ${#out} -lt $len ]]; do
    out+="$(head -c 96 /dev/urandom | LC_ALL=C tr -dc 'A-Za-z0-9')"
  done
  printf '%s' "${out:0:$len}"
}

GRAYLOG_ROOT_PASSWORD="$(rand 20)"
GRAYLOG_ROOT_SHA2="$(printf '%s' "$GRAYLOG_ROOT_PASSWORD" | sha256sum | cut -d' ' -f1)"

declare -A V=(
  [DJANGO_SECRET_KEY]="$(rand 50)"
  [POSTGRES_PASSWORD]="$(rand 24)"
  [REDIS_PASSWORD]="$(rand 24)"
  [ELASTIC_PASSWORD]="$(rand 24)"
  [KIBANA_SYSTEM_PASSWORD]="$(rand 24)"
  [KIBANA_ENCRYPTION_KEY]="$(rand 32)"
  [LOGSTASH_WRITER_PASSWORD]="$(rand 24)"
  [LOGSTASH_HTTP_PASSWORD]="$(rand 24)"
  [GRAFANA_READER_PASSWORD]="$(rand 24)"
  [LOGHUB_ES_PASSWORD]="$(rand 24)"
  [GRAFANA_ADMIN_PASSWORD]="$(rand 20)"
  [GRAFANA_VIEWER_PASSWORD]="$(rand 20)"
  [MONGO_PASSWORD]="$(rand 24)"
  [GRAYLOG_PASSWORD_SECRET]="$(rand 64)"
  [GRAYLOG_ROOT_PASSWORD]="$GRAYLOG_ROOT_PASSWORD"
  [GRAYLOG_ROOT_PASSWORD_SHA2]="$GRAYLOG_ROOT_SHA2"
  [GRAYLOG_READER_PASSWORD]="$(rand 24)"
  [DJANGO_SUPERUSER_PASSWORD]="$(rand 16)"
)

cp "$EXAMPLE" "$ENV_FILE"
for key in "${!V[@]}"; do
  sed -i "s|^${key}=.*|${key}=${V[$key]}|" "$ENV_FILE"
done
chmod 600 "$ENV_FILE"

echo "Wrote $ENV_FILE (mode 600)."
echo "Portal login:   admin / $(grep '^DJANGO_SUPERUSER_PASSWORD=' "$ENV_FILE" | cut -d= -f2)"
echo "Other service credentials are in .env; never commit it."
