#!/usr/bin/env bash
set -euo pipefail

# Apply Auvo and e-track migrations to the centralized DB.
# Usage: ./db/apply-all-migrations.sh

HERE="$(cd "$(dirname "$0")/.." && pwd)"
cd "$HERE"

# load .env if present
if [ -f .env ]; then
  # shellcheck disable=SC1091
  source .env
fi

: ${PGHOST:=127.0.0.1}
: ${PGPORT:=5432}
: ${PGDATABASE:=sync_apis}
: ${PGUSER:=sync_user}
: ${PGPASSWORD:=sync_pass}

echo "Waiting for Postgres to be available at $PGHOST:$PGPORT..."
for i in {1..30}; do
  if command -v psql >/dev/null 2>&1; then
    if PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -U "$PGUSER" -p "$PGPORT" -d "$PGDATABASE" -c '\q' >/dev/null 2>&1; then
      echo "Postgres reachable (psql host)"
      break
    fi
  else
    # no local psql — try via container (docker compose). If container not ready, continue waiting.
    CONTAINER_ID=$(docker compose -f db/docker-compose.yml ps -q db 2>/dev/null || true)
    if [ -n "$CONTAINER_ID" ] && docker exec "$CONTAINER_ID" pg_isready -U "$PGUSER" >/dev/null 2>&1; then
      echo "Postgres reachable (container)"
      break
    fi
  fi
  sleep 1
done

echo "Applying Auvo schema (auvo/schema.sql)"
if command -v psql >/dev/null 2>&1; then
  PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -U "$PGUSER" -p "$PGPORT" -d "$PGDATABASE" -f auvo/schema.sql
else
  docker compose -f db/docker-compose.yml exec -T db psql -U "$PGUSER" -d "$PGDATABASE" < auvo/schema.sql
fi

echo "Applying Auvo migration (auvo/migrate_schema.sql)"
if command -v psql >/dev/null 2>&1; then
  PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -U "$PGUSER" -p "$PGPORT" -d "$PGDATABASE" -f auvo/migrate_schema.sql
else
  docker compose -f db/docker-compose.yml exec -T db psql -U "$PGUSER" -d "$PGDATABASE" < auvo/migrate_schema.sql
fi

echo "Applying e-track schema (e-track/schema.sql)"
if command -v psql >/dev/null 2>&1; then
  PGPASSWORD="$PGPASSWORD" psql -h "$PGHOST" -U "$PGUSER" -p "$PGPORT" -d "$PGDATABASE" -f e-track/schema.sql
else
  docker compose -f db/docker-compose.yml exec -T db psql -U "$PGUSER" -d "$PGDATABASE" < e-track/schema.sql
fi

echo "All migrations applied."
