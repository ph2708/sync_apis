#!/usr/bin/env bash
set -e
# Start the centralized Postgres instance (repository root)
cd "$(dirname "$0")/.."
docker-compose -f db/docker-compose.yml up -d db
echo "Aguardando Postgres e_track subir..."
for i in {1..30}; do
  CONTAINER_ID=$(docker-compose -f db/docker-compose.yml ps -q db || true)
  if [ -n "$CONTAINER_ID" ] && docker exec "$CONTAINER_ID" pg_isready -U sync_user >/dev/null 2>&1; then
    echo "Postgres e_track pronto"
    exit 0
  fi
  sleep 1
done
echo "Timeout esperando Postgres e_track"
exit 1
