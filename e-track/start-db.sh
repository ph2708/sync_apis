#!/usr/bin/env bash
set -e
# Start Postgres container for e-track
cd "$(dirname "$0")"
docker-compose up -d db
echo "Aguardando Postgres e_track subir..."
for i in {1..30}; do
  CONTAINER_ID=$(docker-compose ps -q db)
  if [ -n "$CONTAINER_ID" ] && docker exec "$CONTAINER_ID" pg_isready -U etrack >/dev/null 2>&1; then
    echo "Postgres e_track pronto"
    exit 0
  fi
  sleep 1
done
echo "Timeout esperando Postgres e_track"
exit 1
